"""The Streamlit app: scenario picker, generated parameter panel, live charts.

Launch from the repo root (with the venv active):

    streamlit run pdsim/ui/app.py

This module is deliberately thin (DECISIONS #38): presentation and Streamlit
calls only. It does exactly two things with the platform — builds an
``ExperimentConfig`` from widget state, and consumes the
``engine.run(config, granularity)`` event stream — via the testable logic in
:mod:`pdsim.ui.helpers`, :mod:`pdsim.core.timeseries`, and
:mod:`pdsim.viz.charts`. The parameter panel is *generated* from the
Parameter Registry, so every widget's tooltip is the registry's
novice-friendly description (hard rule 3): a parameter added to the registry
appears here with zero UI edits.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import streamlit as st
from pydantic import ValidationError
from streamlit.delta_generator import DeltaGenerator

from pdsim.config.experiment import ExperimentConfig
from pdsim.config.registry import ParameterSpec, ParamValue
from pdsim.config.scenarios import all_scenarios
from pdsim.core import engine
from pdsim.core.events import CycleFinished, GenerationFinished, MatchFinished, RoundPlayed
from pdsim.core.strategies import all_strategies
from pdsim.core.timeseries import RunTimeseries
from pdsim.io.results import RunRecorder, delete_run, load_run, rename_run, sync_index
from pdsim.ui import helpers
from pdsim.viz import charts

CUSTOM = "Custom"
"""The dropdown entry that starts from registry defaults (DECISIONS #36/#40)."""

PROGRESS_EVERY = 200
"""Fine-grained events between progress-line refreshes (DECISIONS #39)."""

IGNORED_IN_TOURNAMENT = (
    "dynamics.generations",
    "dynamics.selection_rule",
    "dynamics.selection_beta",
    "dynamics.mutation_rate",
)
"""Widgets greyed out in tournament mode (valid but ignored — DECISIONS #34)."""

RUNS_DIR = Path(os.environ.get("PDSIM_RUNS_DIR", "runs"))
"""Where recordings go; the env override exists for tests (DECISIONS #49)."""

st.set_page_config(page_title="pdsim — Evolutionary Prisoner's Dilemma", layout="wide")


def _help_text(spec: ParameterSpec, note: str = "") -> str:
    """Assemble a widget tooltip from a spec's registry documentation.

    Args:
        spec: The parameter being rendered.
        note: Optional extra line (e.g. the ignored-in-this-mode warning).

    Returns:
        The registry description, learn-more note, and extra note.
    """
    parts = [spec.description]
    if spec.learn_more:
        parts.append(f"Learn more: {spec.learn_more}")
    if note:
        parts.append(note)
    return "\n\n".join(parts)


def _widget(spec: ParameterSpec, *, disabled: bool = False, note: str = "") -> ParamValue:
    """Render the right widget for a ParameterSpec and return its value.

    The mapping (DECISIONS #38): bool → checkbox, choice → selectbox,
    int/float → number_input with the spec's bounds, nullable int → a
    "limit?" checkbox plus a number input. Widget keys are the registry
    keys, so scenario loading can address every widget by parameter.

    Args:
        spec: The parameter to render.
        disabled: Grey the widget out (mode-awareness), never hide it.
        note: Extra tooltip line explaining why it is greyed out.

    Returns:
        The widget's current value (``None`` for an unlimited nullable).
    """
    help_text = _help_text(spec, note)
    if spec.nullable:
        limited = st.checkbox(
            f"Limit {spec.label.lower()}?",
            key=f"{spec.key}#limit",
            help=help_text,
            disabled=disabled,
        )
        value = st.number_input(
            spec.label,
            min_value=int(spec.minimum or 0),
            step=1,
            key=f"{spec.key}#value",
            help=help_text,
            disabled=disabled or not limited,
        )
        return int(value) if limited else None
    if spec.kind == "bool":
        return bool(st.checkbox(spec.label, key=spec.key, help=help_text, disabled=disabled))
    if spec.kind == "choice":
        return st.selectbox(
            spec.label,
            options=list(spec.choices or ()),
            key=spec.key,
            help=help_text,
            disabled=disabled,
        )
    if spec.kind == "int":
        value = st.number_input(
            spec.label,
            min_value=None if spec.minimum is None else int(spec.minimum),
            max_value=None if spec.maximum is None else int(spec.maximum),
            step=1,
            key=spec.key,
            help=help_text,
            disabled=disabled,
        )
        return int(value)
    value = st.number_input(
        spec.label,
        min_value=None if spec.minimum is None else float(spec.minimum),
        max_value=None if spec.maximum is None else float(spec.maximum),
        step=0.01,
        format="%.4g",
        key=spec.key,
        help=help_text,
        disabled=disabled,
    )
    return float(value)


def _load_state(
    values: dict[str, ParamValue],
    composition: dict[str, int],
    strategy_params: dict[str, dict[str, ParamValue]],
) -> None:
    """Write a config's values into widget session state (scenario load).

    Runs before any widget is instantiated in this script run, so every
    widget picks the loaded value up as its state.

    Args:
        values: Registry key → value for the scalar parameters.
        composition: Strategy name → agent count for the mix widgets.
        strategy_params: Per-strategy overrides for the expander widgets.
    """
    for spec in helpers.panel_specs():
        value = values.get(spec.key, spec.default)
        if spec.nullable:
            st.session_state[f"{spec.key}#limit"] = value is not None
            st.session_state[f"{spec.key}#value"] = (
                int(value) if value is not None else int(spec.minimum or 1)
            )
        else:
            st.session_state[spec.key] = value
    for info in all_strategies():
        st.session_state[f"composition.{info.name}"] = int(composition.get(info.name, 0))
        for spec in info.params:
            param = spec.key.rsplit(".", maxsplit=1)[-1]
            st.session_state[spec.key] = strategy_params.get(info.name, {}).get(param, spec.default)


def _scenario_area() -> None:
    """Render the scenario dropdown and load its config on change.

    A scenario is a starting point, not a lock (DECISIONS #40): its values
    are written into widget state exactly once, when the selection changes;
    edits afterwards are never fought, and the dropdown keeps showing the
    scenario's name.
    """
    scenarios = {info.display_name: info for info in all_scenarios()}
    choice = st.selectbox(
        "Scenario",
        options=[CUSTOM, *scenarios],
        index=1,
        key="scenario_choice",
        help=(
            "Curated, ready-to-run experiments — pick one, read its question, press "
            "Run. Every parameter stays editable: a scenario is a starting point. "
            "'Custom' starts from the documented defaults."
        ),
    )
    if st.session_state.get("_loaded_scenario") != choice:
        if choice == CUSTOM:
            values = helpers.default_widget_values()
            names = [info.name for info in all_strategies()]
            composition = helpers.default_composition(int(values["population.size"]), names)
            _load_state(values, composition, {})
        else:
            config = scenarios[choice].config
            _load_state(
                helpers.widget_values_from_config(config),
                dict(config.population.composition),
                config.strategy_params,
            )
        st.session_state["_loaded_scenario"] = choice
    if choice != CUSTOM:
        info = scenarios[choice]
        st.markdown(info.description)
        st.caption(f"**Things to try:** {info.things_to_try}")


def _parameter_panel() -> tuple[dict[str, ParamValue], dict[str, int], dict[str, dict]]:
    """Render the whole generated panel; return everything a run needs.

    Returns:
        The scalar values by registry key, the composition counts, and the
        collected strategy-parameter overrides.
    """
    specs = {spec.key: spec for spec in helpers.panel_specs()}
    values: dict[str, ParamValue] = {}

    # Run row — mode is the prominent radio; its value drives the greying.
    mode_spec = specs["run.mode"]
    mode = st.radio(
        mode_spec.label,
        options=list(mode_spec.choices or ()),
        key="run.mode",
        horizontal=True,
        help=_help_text(mode_spec),
    )
    values["run.mode"] = mode
    tournament = mode == "tournament"
    col_seed, col_cycles = st.columns(2)
    with col_seed:
        values["run.seed"] = _widget(specs["run.seed"])
    with col_cycles:
        values["run.tournament_cycles"] = _widget(
            specs["run.tournament_cycles"],
            disabled=not tournament,
            note="" if tournament else "NOTE: only used in tournament mode — ignored right now.",
        )

    sections: dict[str, list[ParameterSpec]] = {}
    for spec in specs.values():
        if not spec.key.startswith("run."):
            sections.setdefault(spec.section, []).append(spec)

    composition: dict[str, int] = {}
    for section, section_specs in sections.items():
        with st.expander(section, expanded=section in ("Population", "Dynamics")):
            columns = st.columns(2)
            for i, spec in enumerate(section_specs):
                disabled = tournament and spec.key in IGNORED_IN_TOURNAMENT
                note = (
                    "NOTE: this parameter exists but is IGNORED in tournament mode — "
                    "nothing evolves there (see the run-mode help)."
                    if disabled
                    else ""
                )
                with columns[i % 2]:
                    values[spec.key] = _widget(spec, disabled=disabled, note=note)
            if section == "Population":
                composition = _composition_panel()

    with st.expander("Per-strategy parameters"):
        st.caption(
            "Overrides for strategies with tunable parameters. They apply even to "
            "strategies outside the mix — mutation can still introduce them mid-run."
        )
        strategy_values: dict[str, ParamValue] = {}
        for info in all_strategies():
            for spec in info.params:
                strategy_values[spec.key] = _widget(spec)
    strategy_params = helpers.collect_strategy_params(strategy_values)

    return values, composition, strategy_params


def _composition_panel() -> dict[str, int]:
    """Render the per-strategy count inputs for the initial population mix.

    Returns:
        Strategy machine name → count (zeros allowed here; dropped at
        config assembly).
    """
    st.markdown("**Initial population mix** (counts must sum to the population size)")
    counts: dict[str, int] = {}
    columns = st.columns(4)
    for i, info in enumerate(all_strategies()):
        with columns[i % 4]:
            counts[info.name] = int(
                st.number_input(
                    info.display_name,
                    min_value=0,
                    step=1,
                    key=f"composition.{info.name}",
                    help=info.description,
                )
            )
    return counts


def _request_stop() -> None:
    """Flag the running event loop to stop (button callback)."""
    st.session_state["stop_requested"] = True


def _draw_charts(
    timeseries: RunTimeseries,
    left: DeltaGenerator,
    right: DeltaGenerator,
    draw_id: int,
    per_round: bool,
    whole_game: bool,
    key_prefix: str = "chart",
) -> None:
    """Redraw both mode-appropriate charts into their placeholders.

    Args:
        timeseries: The run's accumulated series.
        left: Placeholder for composition (evolution) / totals (tournament).
        right: Placeholder for the mean-score chart.
        draw_id: Monotonic counter — Streamlit requires a fresh element key
            for each redraw within one script run.
        per_round: Score view for the mean chart (DECISIONS #44).
        whole_game: Time scope for the mean chart (DECISIONS #45).
        key_prefix: Distinguishes chart elements rendered by different app
            areas in the same script run (live view vs results browser).
    """
    if not timeseries.periods:
        return
    if timeseries.mode == "tournament":
        left_figure = charts.total_score_chart(timeseries)
    else:
        left_figure = charts.composition_chart(timeseries)
    left.plotly_chart(left_figure, use_container_width=True, key=f"{key_prefix}_left_{draw_id}")
    right.plotly_chart(
        charts.mean_score_chart(timeseries, per_round=per_round, whole_game=whole_game),
        use_container_width=True,
        key=f"{key_prefix}_right_{draw_id}",
    )


def _run_live(
    config: ExperimentConfig,
    granularity: str,
    delay: float,
    per_round: bool,
    whole_game: bool,
    record: bool,
    scenario: str | None,
) -> None:
    """Consume the event stream, updating charts as periods finish.

    Batching (DECISIONS #39): charts are rebuilt only on period events —
    fine-grained events advance a progress line at most every
    ``PROGRESS_EVERY`` events, never a figure. The finished (or stopped)
    run is kept in session state so the results survive later interactions
    — e.g. flipping the score view re-renders without re-running (#44).

    Args:
        config: The validated ExperimentConfig to run.
        granularity: Finest event level to request from the engine.
        delay: Playback pause (seconds) after each chart refresh.
        per_round: Score view for the mean chart (DECISIONS #44).
        whole_game: Time scope for the mean chart (DECISIONS #45).
        record: Persist this run to a run folder as it streams (#49).
        scenario: Scenario name for the recording's index row, if any.
    """
    recorder = RunRecorder(config, out_dir=RUNS_DIR, scenario=scenario) if record else None
    timeseries = RunTimeseries(mode=config.mode)
    progress = st.empty()
    col_left, col_right = st.columns(2)
    chart_left, chart_right = col_left.empty(), col_right.empty()
    period_label = "cycle" if config.mode == "tournament" else "generation"
    fine_events = 0
    draws = 0
    stopped = False
    for event in engine.run(config, granularity):
        if st.session_state.get("stop_requested"):
            stopped = True
            break
        timeseries.add(event)
        if recorder is not None:
            recorder.add(event)
        if isinstance(event, RoundPlayed | MatchFinished):
            fine_events += 1
            if fine_events % PROGRESS_EVERY == 0:
                progress.caption(f"... {fine_events} match/round events so far")
        elif isinstance(event, GenerationFinished | CycleFinished):
            draws += 1
            _draw_charts(timeseries, chart_left, chart_right, draws, per_round, whole_game)
            progress.caption(f"{period_label} {event.index + 1} finished")
            if delay > 0:
                time.sleep(delay)
    _draw_charts(timeseries, chart_left, chart_right, draws + 1, per_round, whole_game)
    note = f"Results of the last run (seed {config.seed})"
    if stopped:
        st.warning("Run stopped — the charts show progress up to the stop.")
        note += " — stopped early"
        if recorder is not None:
            st.caption(
                f"Stopped runs are not recorded (a reproducible config.yaml was still "
                f"kept at {recorder.folder})."
            )
    elif timeseries.final is not None:
        final = timeseries.final
        st.success(
            f"Run complete: {final.completed} {period_label}s, seed {config.seed} "
            "(same seed + same settings = same charts)."
        )
        st.dataframe(charts.final_summary_rows(final), use_container_width=True)
        if recorder is not None:
            folder = recorder.finalize()
            charts.export_run_charts(recorder.timeseries, folder)
            st.caption(f"Recorded to {folder} — see the Results browser tab.")
    st.session_state["last_run"] = {"timeseries": timeseries, "note": note}


def _queue_config_load(folder: str) -> None:
    """Ask the next script run to load a recorded config (button callback).

    Args:
        folder: The run folder whose config should fill the panel.
    """
    st.session_state["_pending_load"] = folder


def _apply_pending_load() -> None:
    """Load a queued recorded config into the panel, before widgets render.

    The browser's "load into panel" button queues a folder; this runs at
    the top of the script (widget state may only be written before the
    widgets are instantiated) and reuses the scenario-loading machinery —
    the panel lands on "Custom" with the run's exact values (#49).
    """
    pending = st.session_state.pop("_pending_load", None)
    if pending is None:
        return
    loaded = load_run(Path(pending))
    _load_state(
        helpers.widget_values_from_config(loaded.config),
        dict(loaded.config.population.composition),
        loaded.config.strategy_params,
    )
    st.session_state["scenario_choice"] = CUSTOM
    st.session_state["_loaded_scenario"] = CUSTOM
    st.session_state["_load_note"] = (
        f"Loaded the config of {Path(pending).name} into the panel — press Run to "
        "reproduce it exactly, or edit it as a starting point."
    )


def _results_browser() -> None:
    """Render the results browser: index table, run charts, config loading.

    Lists the run folders that actually exist (folder truth — survives
    hand-deleted or renamed folders, DECISIONS #50) and reconstructs the
    selected run via :func:`pdsim.io.results.load_run`; the charts are the
    same pure builders the live view uses, with their own #44/#45 toggles —
    pure re-renderings of the persisted raw data.
    """
    rows = sync_index(RUNS_DIR)  # also reconciles index.csv with the folders (#52)
    if not rows:
        st.info(
            "No recorded runs yet. Turn on **Record this run** in the Run lab, or "
            "record one headlessly: `python -m pdsim.run --scenario classic_tournament`."
        )
        return
    st.dataframe(rows, use_container_width=True)
    run_ids = [str(row["run_id"]) for row in rows]
    # A widget's own key may only be written BEFORE the widget exists in a
    # script run, so delete/rename stage the next selection under
    # "_select_run" and we apply it here, at the top (#52). Explicit
    # assignment, not pop: Streamlit resurrects popped widget values from
    # the frontend, which left deleted names showing in the dropdown.
    staged = st.session_state.pop("_select_run", None)
    if staged in run_ids:
        st.session_state["browser_run"] = staged
    elif st.session_state.get("browser_run") not in run_ids:
        st.session_state["browser_run"] = run_ids[0]
    run_id = st.selectbox(
        "Open a run",
        options=run_ids,
        key="browser_run",
        help=(
            "Every run folder currently under runs/ (newest first); each can be "
            "reproduced from its config.yaml."
        ),
    )
    try:
        loaded = load_run(RUNS_DIR / run_id)
    except (FileNotFoundError, ValueError, OSError) as error:
        # E.g. the folder vanished between listing and loading, or a file
        # inside it is missing/corrupt — report, don't crash.
        st.error(f"Could not load {run_id}: {error}")
        return
    summary = loaded.summary
    st.caption(
        f"{summary['mode']} · N={summary['population_size']} · "
        f"{summary['periods_completed']} periods · seed {summary['seed']} · "
        f"{summary['headline']} · recorded by pdsim "
        f"{summary.get('code_version', {}).get('package', '?')}"
    )
    tournament = loaded.timeseries.mode == "tournament"
    col_view, col_scope, col_load, col_delete = st.columns([2, 2, 2, 1])
    score_view = col_view.radio(
        "Score view",
        options=["total", "per_round"],
        key="browser_score_view",
        horizontal=True,
        format_func=lambda view: "Total" if view == "total" else "Per round",
        help="Same views as the live charts — recomputed from the recorded raw data.",
    )
    scope = col_scope.radio(
        "Time scope",
        options=["generation", "whole_game"],
        key="browser_time_scope",
        horizontal=True,
        disabled=tournament,
        format_func=lambda s: "This generation" if s == "generation" else "Whole game",
        help="Greyed out for tournaments: their scores are already whole-game figures.",
    )
    col_load.button(
        "Load config into panel",
        key="browser_load",
        on_click=_queue_config_load,
        args=(str(RUNS_DIR / run_id),),
        help="Fills the Run lab panel with this run's exact config (as 'Custom').",
    )
    if col_delete.button(
        "Delete…",
        key="browser_delete",
        help="Remove this run's folder and its index entry (asks for confirmation).",
    ):
        st.session_state["_confirm_delete"] = run_id
    if st.session_state.get("_confirm_delete") == run_id:
        st.warning(
            f"Permanently delete **{run_id}**? The run folder and its index entry "
            "will be removed — this cannot be undone."
        )
        col_yes, col_no = st.columns([1, 5])
        if col_yes.button("Yes, delete", key="browser_delete_confirm", type="primary"):
            try:
                delete_run(RUNS_DIR, run_id)
            except OSError as error:
                # Windows: something briefly holds the folder (an Explorer
                # window, OneDrive sync, antivirus). Report and let the
                # user retry — never a traceback (DECISIONS #51).
                st.error(
                    f"Could not delete {run_id}: {error}. Something is still "
                    "holding the folder open — close any Explorer window "
                    "showing it, give OneDrive a moment to finish syncing, "
                    "then press 'Yes, delete' again."
                )
            else:
                st.session_state.pop("_confirm_delete", None)
                remaining = [r for r in run_ids if r != run_id]
                if remaining:
                    st.session_state["_select_run"] = remaining[0]
                st.rerun()
        if col_no.button("Cancel", key="browser_delete_cancel"):
            st.session_state.pop("_confirm_delete", None)
            st.rerun()
    with st.expander("Rename this run"):
        new_name = st.text_input(
            "New folder name",
            value=run_id,
            key=f"browser_rename#{run_id}",  # per-run key: switching runs refreshes the field
            help="Letters, digits, dots, underscores, spaces, and hyphens.",
        )
        if st.button("Apply rename", key="browser_rename_apply"):
            try:
                final_name = rename_run(RUNS_DIR, run_id, new_name)
            except (ValueError, FileExistsError, FileNotFoundError) as error:
                st.error(str(error))
            except OSError as error:
                st.error(
                    f"Could not rename {run_id}: {error}. Something is holding the "
                    "folder open — close Explorer windows / let OneDrive settle, "
                    "then try again."
                )
            else:
                st.session_state["_select_run"] = final_name
                st.rerun()
    col_left, col_right = st.columns(2)
    _draw_charts(
        loaded.timeseries,
        col_left.empty(),
        col_right.empty(),
        0,
        score_view == "per_round",
        scope == "whole_game" and not tournament,
        key_prefix="browser",
    )
    if loaded.timeseries.final is not None:
        st.dataframe(charts.final_summary_rows(loaded.timeseries.final), use_container_width=True)


def _run_lab() -> None:
    """Lay out the live-run experience: scenario, panel, controls, charts."""
    _scenario_area()
    load_note = st.session_state.pop("_load_note", None)
    if load_note:
        st.success(load_note)
    values, composition, strategy_params = _parameter_panel()

    mix_total = sum(composition.values())
    size = int(values["population.size"])  # type: ignore[arg-type]
    if mix_total == size:
        st.caption(f"Population mix OK: {mix_total} agents.")
    else:
        st.warning(
            f"The population mix sums to {mix_total}, but the population size is "
            f"{size}. Adjust the counts (or the size) to enable Run."
        )

    tournament = values["run.mode"] == "tournament"
    col_gran, col_speed, col_view, col_scope, col_run, col_stop = st.columns([2, 2, 2, 2, 1, 1])
    granularity = col_gran.selectbox(
        "Update granularity",
        options=["generation", "match", "round"],
        key="granularity",
        format_func=lambda g: "cycle" if g == "generation" and tournament else g,
        help=(
            "The finest event level the engine reports while running. Charts always "
            "update per generation/cycle; finer levels drive the progress line. "
            "Fine granularity is meant for small populations (DESIGN §4). "
            "Granularity never changes results — only what you watch."
        ),
    )
    delay = col_speed.slider(
        "Playback delay (s)",
        min_value=0.0,
        max_value=1.0,
        value=0.05,
        step=0.05,
        key="playback_delay",
        help="Pause after each chart refresh, so you can watch the run unfold.",
    )
    score_view = col_view.radio(
        "Score view",
        options=["total", "per_round"],
        key="score_view",
        horizontal=True,
        format_func=lambda view: "Total" if view == "total" else "Per round",
        help=(
            "'Total' plots the raw score selection acts on — it grows with "
            "population size and match length (roughly payoff x (N-1) x rounds). "
            "'Per round' divides by the rounds actually played, landing on the "
            "payoff-matrix scale (0-5 with the default payoffs) so different "
            "setups compare directly. Switching after a run re-renders the last "
            "results without re-running."
        ),
    )
    per_round = score_view == "per_round"
    record = st.checkbox(
        "Record this run",
        value=True,
        key="record_run",
        help=(
            "Save the run to a folder under runs/ as it streams: the exact config "
            "(re-runnable), the raw time series, a summary, and chart exports. "
            "Recorded runs appear in the Results browser tab. On by default — "
            "reproducibility is the platform's ethos, and the folders are small."
        ),
    )
    scope = col_scope.radio(
        "Time scope",
        options=["generation", "whole_game"],
        key="time_scope",
        horizontal=True,
        disabled=tournament,
        format_func=lambda s: "This generation" if s == "generation" else "Whole game",
        help=(
            "'This generation' plots each generation's own scores — jumpy but "
            "immediate. 'Whole game' plots the running average over the entire run "
            "so far, so lines move gradually as evidence accumulates. In tournament "
            "mode this is greyed out: tournament scores never reset, so they are "
            "already whole-game figures."
        ),
    )
    whole_game = scope == "whole_game" and not tournament
    run_clicked = col_run.button(
        "Run", type="primary", key="run_button", disabled=mix_total != size
    )
    col_stop.button("Stop", key="stop_button", on_click=_request_stop)

    if run_clicked:
        st.session_state["stop_requested"] = False
        try:
            config = helpers.build_config(values, composition, strategy_params)
        except ValidationError as error:
            for message in helpers.validation_messages(error):
                st.error(message)
        else:
            # "Custom" is recorded as the scenario label too — a blank
            # scenario cell in the browser table read as missing data (#52).
            choice = st.session_state.get("_loaded_scenario")
            scenario = str(choice) if choice else CUSTOM
            _run_live(config, granularity, delay, per_round, whole_game, record, scenario)
    else:
        last = st.session_state.get("last_run")
        if last is not None:
            timeseries = last["timeseries"]
            st.caption(f"{last['note']} — switch the score views to re-render, or press Run.")
            col_left, col_right = st.columns(2)
            _draw_charts(timeseries, col_left.empty(), col_right.empty(), 0, per_round, whole_game)
            if timeseries.final is not None:
                st.dataframe(charts.final_summary_rows(timeseries.final), use_container_width=True)


def main() -> None:
    """Lay out the app: the live Run lab and the Results browser tabs."""
    st.title("Evolutionary Prisoner's Dilemma Simulator")
    _apply_pending_load()
    tab_lab, tab_browser = st.tabs(["Run lab", "Results browser"])
    with tab_lab:
        _run_lab()
    with tab_browser:
        _results_browser()


main()
