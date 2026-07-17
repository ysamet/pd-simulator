"""The Streamlit app: scenario picker, generated parameter panel, live charts.

Launch from the repo root (with the venv active):

    streamlit run pdsim/ui/app.py

This module is deliberately thin (DECISIONS #38): presentation and Streamlit
calls only. It does exactly three things with the platform — builds an
``ExperimentConfig`` from widget state, consumes the
``engine.run(config, granularity)`` event stream, and (the Sweep tab, M9.5b)
authors a ``SweepSpec`` and spawns the headless sweep CLI — via the testable
logic in :mod:`pdsim.ui.helpers`, :mod:`pdsim.ui.sweep_helpers`,
:mod:`pdsim.core.timeseries`, and :mod:`pdsim.viz.charts`.
The parameter panel is *generated* from the
Parameter Registry, so every widget's tooltip is the registry's
novice-friendly description (hard rule 3): a parameter added to the registry
appears here with zero UI edits.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pandas as pd
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
from pdsim.sweep.metrics import all_metrics
from pdsim.sweep.spec import (
    SweepSpec,
    expand,
    resolve_composition,
    sweep_spec_yaml,
    sweep_validation_messages,
)
from pdsim.ui import economy_helpers, helpers, sweep_helpers
from pdsim.ui.economy_helpers import ECONOMY_HELP
from pdsim.viz import charts

CUSTOM = "Custom"
"""The dropdown entry that starts from registry defaults (DECISIONS #36/#40)."""

PROGRESS_EVERY = 200
"""Fine-grained events between progress-line refreshes (DECISIONS #39)."""

RUNS_DIR = Path(os.environ.get("PDSIM_RUNS_DIR", "runs"))
"""Where recordings go; the env override exists for tests (DECISIONS #49)."""

SWEEPS_DIR = Path(os.environ.get("PDSIM_SWEEPS_DIR", "sweeps"))
"""Where the Sweep tab launches sweeps into (mirrors RUNS_DIR, DECISIONS #72)."""

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
    int/float → number_input with the spec's bounds, nullable → a checkbox
    plus a number input ("Limit ...?" for nullable ints, whose None means
    unlimited; "Set ... manually?" for nullable floats, whose None means
    auto — the M10a derived defaults). Widget keys are the registry keys,
    so scenario loading can address every widget by parameter.

    Args:
        spec: The parameter to render.
        disabled: Grey the widget out (mode-awareness), never hide it.
        note: Extra tooltip line explaining why it is greyed out.

    Returns:
        The widget's current value (``None`` for an unlimited/auto
        nullable).
    """
    help_text = _help_text(spec, note)
    if spec.nullable and spec.kind == "int":
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
    if spec.nullable:  # nullable float: None means "auto" (M10a)
        manual = st.checkbox(
            f"Set {spec.label.lower()} manually?",
            key=f"{spec.key}#limit",
            help=help_text,
            disabled=disabled,
        )
        value = st.number_input(
            spec.label,
            min_value=None if spec.minimum is None else float(spec.minimum),
            step=0.01,
            format="%.4g",
            key=f"{spec.key}#value",
            help=help_text,
            disabled=disabled or not manual,
        )
        return float(value) if manual else None
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
        if spec.nullable and spec.kind == "int":
            st.session_state[f"{spec.key}#limit"] = value is not None
            st.session_state[f"{spec.key}#value"] = (
                int(value) if value is not None else int(spec.minimum or 1)
            )
        elif spec.nullable:  # nullable float: None means "auto" (M10a)
            st.session_state[f"{spec.key}#limit"] = value is not None
            st.session_state[f"{spec.key}#value"] = (
                float(value) if value is not None else float(spec.minimum or 0.0)
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
    col_seed, col_cycles = st.columns(2)
    with col_seed:
        values["run.seed"] = _widget(specs["run.seed"])
    with col_cycles:
        disabled, note = helpers.greying("run.tournament_cycles", values)
        values["run.tournament_cycles"] = _widget(
            specs["run.tournament_cycles"], disabled=disabled, note=note
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
                # Widgets render in registry order, so the values a widget's
                # greying keys off (run.mode, matching.matcher,
                # dynamics.reproduction_mode) are already gathered when it
                # renders (helpers.greying, DECISIONS #34).
                disabled, note = helpers.greying(spec.key, values)
                with columns[i % 2]:
                    values[spec.key] = _widget(spec, disabled=disabled, note=note)
            if section == "Population":
                composition = _composition_panel()
            if (
                section == "Dynamics"
                and values.get("run.mode") == "evolution"
                and values.get("dynamics.reproduction_mode") == "energy_economy"
            ):
                # The Population section renders before Dynamics (registry
                # order), so the composition is already gathered here.
                _economy_panel(values, composition)

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


def _economy_panel(values: dict[str, ParamValue], composition: dict[str, int]) -> None:
    """Render the Economy calibration readout inside the Dynamics expander.

    Presentation only (the #38 split): all arithmetic lives in the
    Streamlit-free :func:`pdsim.ui.economy_helpers.calibration_report`, and
    every inline (?) text comes from the single ``ECONOMY_HELP`` source so
    app wording and docs cannot drift. Verdict line first, then the window,
    then the conditional readouts (M10a spec Task 11).

    Args:
        values: The widget values gathered so far this script run (every
            section before Dynamics has already rendered).
        composition: The population mix gathered by the Population section.
    """
    st.markdown("---")
    st.markdown("**Economy calibration** — where the survival window lies for these settings.")
    try:
        config = helpers.build_config(values, composition)
    except ValidationError as error:
        st.info("The calibration readout appears once the configuration is valid:")
        for message in helpers.validation_messages(error):
            st.caption(f"• {message}")
        return
    report = economy_helpers.calibration_report(config)

    # The verdict line first (the spec's order), then the window.
    st.markdown(
        f"A cooperator nets **{report.cooperator_net:+g}** per generation; "
        f"a defector nets **{report.defector_net:+g}** per generation."
    )
    col_matches, col_c, col_d, col_window = st.columns(4)
    col_matches.metric(
        "Matches per agent",
        f"{report.expected_matches:g}",
        help=ECONOMY_HELP["expected_matches"],
    )
    col_c.metric("All-C income", f"{report.all_c_income:g}", help=ECONOMY_HELP["income"])
    col_d.metric("All-D income", f"{report.all_d_income:g}", help=ECONOMY_HELP["income"])
    col_window.metric(
        "Survival window",
        f"{report.all_d_income:g} ≤ cost < {report.all_c_income:g}",
        help=ECONOMY_HELP["window"],
    )
    if report.window_verdict == "inside":
        st.markdown(
            f"Total per-generation cost **{report.total_cost:g}** is **inside** the "
            "window — cooperators can pay the bill, defectors cannot: the "
            "metabolic filter is on."
        )
    elif report.window_verdict == "above":
        st.markdown(
            f"Total per-generation cost **{report.total_cost:g}** is **above** the "
            "window — even an all-cooperator cannot pay the bill; expect the "
            "population to die out."
        )
    else:
        st.markdown(
            f"Total per-generation cost **{report.total_cost:g}** is **below** the "
            "window — even defectors profit; the metabolic filter is switched off."
        )

    if report.escape_velocity is not None:
        st.metric(
            "Escape velocity e*",
            f"{report.escape_velocity:g}",
            help=ECONOMY_HELP["escape_velocity"],
        )
    if report.senescence_factor is not None:
        col_factor, col_eff, col_theta, col_kids = st.columns(4)
        col_factor.metric(
            "Senescence factor (resolved)",
            f"{report.senescence_factor:.4f}",
            help=(
                "The factor actually used this run — a blank 'auto' input "
                "resolves to the value that reaches certain death exactly at "
                "the max age."
            ),
        )
        if report.effective_max_age is not None:
            col_eff.metric(
                "Effective max age",
                f"{report.effective_max_age:.1f}",
                help=ECONOMY_HELP["effective_max_age"],
            )
        if report.generations_to_threshold is not None:
            col_theta.metric(
                "Generations to θ",
                f"{report.generations_to_threshold:.1f}",
                help=ECONOMY_HELP["generations_to_threshold"],
            )
        if report.expected_offspring is not None:
            col_kids.metric(
                "Expected offspring",
                f"{report.expected_offspring:g}",
                help=ECONOMY_HELP["generations_to_threshold"],
            )
    if report.effective_max_age_note:
        st.warning(report.effective_max_age_note)
    if report.memory_note:
        st.info(report.memory_note)
    st.caption(report.regime_note)
    # A toggle, not an expander — Streamlit forbids nesting expanders, and
    # this panel already lives inside the Dynamics expander.
    if st.toggle(
        "Explain the economy concepts (?)",
        key="economy_concepts",
        help="Energy, admission at capacity, estate destruction, passport ids.",
    ):
        st.markdown(f"**Energy (a stock, not a score)** — {ECONOMY_HELP['energy']}")
        st.markdown(f"**Admission at capacity** — {ECONOMY_HELP['admission']}")
        st.markdown(f"**Estate destruction on death** — {ECONOMY_HELP['estate_destruction']}")
        st.markdown(f"**Passport ids and lineage** — {ECONOMY_HELP['passport_id']}")


def _request_stop() -> None:
    """Flag the running event loop to stop (button callback)."""
    st.session_state["stop_requested"] = True


def _economy_placeholders() -> tuple[DeltaGenerator, DeltaGenerator, DeltaGenerator]:
    """Create the three economy chart placeholders (M10a house layout).

    Returns:
        Placeholders for the population and mean-energy charts (a column
        pair) and the mean-age chart (full width below them). They stay
        blank for runs without per-agent snapshots.
    """
    col_pop, col_energy = st.columns(2)
    return col_pop.empty(), col_energy.empty(), st.empty()


def _draw_charts(
    timeseries: RunTimeseries,
    left: DeltaGenerator,
    right: DeltaGenerator,
    cooperation: DeltaGenerator,
    draw_id: int,
    per_round: bool,
    whole_game: bool,
    key_prefix: str = "chart",
    economy: tuple[DeltaGenerator, DeltaGenerator, DeltaGenerator] | None = None,
    carrying_capacity: float | None = None,
) -> None:
    """Redraw the mode-appropriate charts into their placeholders.

    Args:
        timeseries: The run's accumulated series.
        left: Placeholder for composition (evolution) / totals (tournament).
        right: Placeholder for the mean-score chart.
        cooperation: Full-width placeholder for the cooperation-rate chart
            (M9b); left untouched when the run carries no cooperation data
            (recordings from before schema 2 — DECISIONS #65).
        draw_id: Monotonic counter — Streamlit requires a fresh element key
            for each redraw within one script run.
        per_round: Score view for the mean chart (DECISIONS #44).
        whole_game: Time scope for the mean chart (DECISIONS #45).
        key_prefix: Distinguishes chart elements rendered by different app
            areas in the same script run (live view vs results browser).
        economy: Placeholders for the population / mean-energy / mean-age
            charts (M10a); left untouched when the run carries no per-agent
            snapshots (imitation runs, pre-schema-3 recordings — #65 again).
        carrying_capacity: K for the population chart's dashed reference
            line (config-derived; ``None`` outside the energy economy).
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
    if timeseries.cooperation_overall:
        cooperation.plotly_chart(
            charts.cooperation_chart(timeseries),
            use_container_width=True,
            key=f"{key_prefix}_coop_{draw_id}",
        )
    if economy is not None and any(timeseries.agent_snapshots):
        population, energy, age = economy
        population.plotly_chart(
            charts.population_chart(timeseries, carrying_capacity),
            use_container_width=True,
            key=f"{key_prefix}_population_{draw_id}",
        )
        energy.plotly_chart(
            charts.mean_energy_chart(timeseries),
            use_container_width=True,
            key=f"{key_prefix}_energy_{draw_id}",
        )
        age.plotly_chart(
            charts.mean_age_chart(timeseries),
            use_container_width=True,
            key=f"{key_prefix}_age_{draw_id}",
        )


def _final_summary_area(timeseries: RunTimeseries) -> None:
    """Render the final summary table plus the cooperation pair matrix.

    Args:
        timeseries: A finished run's series (``final`` must be set).
    """
    if timeseries.final is None:
        return
    st.dataframe(charts.final_summary_rows(timeseries.final), use_container_width=True)
    pair_rows = charts.cooperation_pair_rows(timeseries)
    if pair_rows:
        st.caption(
            "Cooperation by strategy pair (final period; actor's rate against "
            "that opponent — the M12 in-group/out-group diagnostic in table form)."
        )
        st.dataframe(pair_rows, use_container_width=True)


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
    # The recording is "settled" once it was finalized or deliberately
    # discarded. Anything else — and in live Streamlit that includes the
    # Stop button and a mid-run Run click, both of which KILL this script
    # at its next st.* call rather than setting our flag — lands in the
    # finally block below, which discards the partial folder (#53/#54).
    settled = recorder is None
    if recorder is not None:
        # Write-ahead note (#55): staged NOW, while this script surely
        # runs, because a session-state write from the dying script's
        # finally races the rerun the killing click triggers. Cleared on
        # successful completion; a killed run leaves it for the next
        # render to show.
        st.session_state["_discard_note"] = (
            "The interrupted run was not recorded — its partial folder was cleaned up."
        )
    try:
        timeseries = RunTimeseries(mode=config.mode)
        progress = st.empty()
        col_left, col_right = st.columns(2)
        chart_left, chart_right = col_left.empty(), col_right.empty()
        chart_coop = st.empty()  # full-width, below the pair (M9b)
        chart_economy = _economy_placeholders()  # blank outside the economy (M10a)
        capacity = economy_helpers.chart_carrying_capacity(config)
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
                _draw_charts(
                    timeseries,
                    chart_left,
                    chart_right,
                    chart_coop,
                    draws,
                    per_round,
                    whole_game,
                    economy=chart_economy,
                    carrying_capacity=capacity,
                )
                progress.caption(f"{period_label} {event.index + 1} finished")
                if delay > 0:
                    time.sleep(delay)
        _draw_charts(
            timeseries,
            chart_left,
            chart_right,
            chart_coop,
            draws + 1,
            per_round,
            whole_game,
            economy=chart_economy,
            carrying_capacity=capacity,
        )
        note = f"Results of the last run (seed {config.seed})"
        if stopped:
            st.warning("Run stopped — the charts show progress up to the stop.")
            note += " — stopped early"
            if recorder is not None:
                _discard_recording(recorder)
                settled = True
                st.caption(st.session_state.pop("_discard_note", ""))
        elif timeseries.final is not None:
            final = timeseries.final
            st.success(
                f"Run complete: {final.completed} {period_label}s, seed {config.seed} "
                "(same seed + same settings = same charts)."
            )
            _final_summary_area(timeseries)
            if recorder is not None:
                folder = recorder.finalize()
                settled = True
                st.session_state.pop("_discard_note", None)  # clean end: no banner
                charts.export_run_charts(recorder.timeseries, folder, carrying_capacity=capacity)
                st.caption(f"Recorded to {folder} — see the Results browser tab.")
        st.session_state["last_run"] = {
            "timeseries": timeseries,
            "note": note,
            "carrying_capacity": capacity,
        }
    finally:
        if recorder is not None and not settled:
            _discard_recording(recorder)


def _discard_recording(recorder: RunRecorder) -> None:
    """Discard a partial recording; the banner was write-ahead staged (#55).

    Usually called from a script run Streamlit has already killed (Stop /
    mid-run Run click), so the success message was staged when the run
    STARTED; only a deletion failure rewrites it (best-effort — this
    thread's session writes can race the next render).

    Args:
        recorder: The recorder whose folder should be removed.
    """
    try:
        recorder.discard()
    except OSError as error:
        st.session_state["_discard_note"] = (
            f"A stopped run's partial folder could not be removed ({error}) — "
            f"delete {recorder.folder} by hand once OneDrive/Explorer lets go."
        )


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
    cooperation_rate = summary.get("final_cooperation_rate")
    cooperation_note = (
        f" · cooperation {cooperation_rate:.2f}" if isinstance(cooperation_rate, float) else ""
    )
    st.caption(
        f"{summary['mode']} · N={summary['population_size']} · "
        f"{summary['periods_completed']} periods · seed {summary['seed']} · "
        f"{summary['headline']}{cooperation_note} · recorded by pdsim "
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
        st.empty(),
        0,
        score_view == "per_round",
        scope == "whole_game" and not tournament,
        key_prefix="browser",
        economy=_economy_placeholders(),
        carrying_capacity=economy_helpers.chart_carrying_capacity(loaded.config),
    )
    _final_summary_area(loaded.timeseries)


def _run_lab() -> None:
    """Lay out the live-run experience: scenario, panel, controls, charts."""
    _scenario_area()
    load_note = st.session_state.pop("_load_note", None)
    if load_note:
        st.success(load_note)
    discard_note = st.session_state.pop("_discard_note", None)
    if discard_note:
        st.info(discard_note)  # staged by a run Streamlit killed mid-loop (#53)
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
            _draw_charts(
                timeseries,
                col_left.empty(),
                col_right.empty(),
                st.empty(),
                0,
                per_round,
                whole_game,
                economy=_economy_placeholders(),
                carrying_capacity=last.get("carrying_capacity"),
            )
            _final_summary_area(timeseries)


def _fill_range_field(target_key: str, start: int, stop: int, step: int) -> None:
    """Write a built integer range into a text field (range-builder callback).

    Button callbacks run before the next script render, so writing another
    widget's session-state value here is legal; a bad range stages a plain
    error the next render shows instead.

    Args:
        target_key: Session-state key of the text field to fill.
        start: First value of the range.
        stop: Last candidate value (inclusive when the step lands on it).
        step: Increment between values.
    """
    try:
        values = sweep_helpers.build_range(start, stop, step)
    except ValueError as error:
        st.session_state["_sweep_range_error"] = str(error)
    else:
        st.session_state[target_key] = ", ".join(str(value) for value in values)


def _add_param_axis() -> None:
    """Append a new parameter-axis row (button callback)."""
    next_id = st.session_state.get("_sweep_axis_seq", 0)
    st.session_state["_sweep_axis_seq"] = next_id + 1
    st.session_state["sweep_param_axes"] = [*st.session_state.get("sweep_param_axes", []), next_id]


def _remove_param_axis(axis_id: int) -> None:
    """Remove one parameter-axis row (button callback).

    Args:
        axis_id: The row's stable identity in the session-state list.
    """
    st.session_state["sweep_param_axes"] = [
        existing for existing in st.session_state.get("sweep_param_axes", []) if existing != axis_id
    ]


def _sweep_composition_area(fields: dict[str, object]) -> dict[str, object] | None:
    """Render the composition-axis section; return the authored axis dict.

    The three-bucket model is STRUCTURAL here (DECISIONS #73): the varying
    invader is excluded from the bucket rows, and each remaining strategy
    has ONE bucket radio — so the "buckets disjoint" rule is impossible to
    violate from the UI. A live preview shows the resolved integer
    composition at the largest count, using the real engine arithmetic
    (:func:`~pdsim.sweep.spec.resolve_composition`).

    Args:
        fields: The authored values so far (the base fields drive the
            preview's population size).

    Returns:
        ``{vary, counts, fixed, fill}``, or ``None`` when the axis is off.
    """
    include = st.checkbox(
        "Include a composition axis",
        key="sweep_comp_on",
        help=(
            "March one strategy's starting count across a range while the rest of "
            "the population keeps a constant character — the classic invasion "
            "experiment. Off = every member run keeps the base config's mix."
        ),
    )
    if not include:
        return None
    names = [info.name for info in all_strategies()]
    with st.expander("Composition axis", expanded=True):
        vary = st.selectbox(
            "Varying invader",
            options=names,
            key="sweep_vary",
            help=(
                "The strategy whose starting count the sweep marches upward. "
                "Machine names are shown because they are what the sweep YAML uses."
            ),
        )
        counts_text = st.text_input(
            "Invader counts",
            key="sweep_counts",
            help=(
                "The invader counts to try, e.g. '2, 4, 6, 8'. One member run is "
                "made per count (times every seed and parameter combination)."
            ),
        )
        col_start, col_stop, col_step, col_fill = st.columns([1, 1, 1, 1])
        start = int(
            col_start.number_input(
                "Range start", min_value=0, value=2, step=1, key="sweep_counts_start"
            )
        )
        stop = int(
            col_stop.number_input(
                "Range stop", min_value=0, value=20, step=1, key="sweep_counts_stop"
            )
        )
        step = int(
            col_step.number_input(
                "Range step", min_value=1, value=2, step=1, key="sweep_counts_step"
            )
        )
        col_fill.button(
            "Fill counts",
            key="sweep_counts_fill",
            on_click=_fill_range_field,
            args=("sweep_counts", start, stop, step),
            help="Write start..stop (step apart) into the counts field; edit freely after.",
        )
        counts: list[int] = []
        try:
            counts = sweep_helpers.parse_int_list(counts_text)
        except ValueError as error:
            st.error(str(error))
        st.markdown(
            "**Background buckets** — every other strategy is either absent "
            "(*none*), held at a constant count (*fixed*), or takes a percentage "
            "of the leftover seats (*fill*). Fill percentages must sum to 100."
        )
        fixed: dict[str, int] = {}
        fill: dict[str, float] = {}
        for info in all_strategies():
            if info.name == vary:
                continue
            col_name, col_bucket, col_value = st.columns([2, 3, 2])
            col_name.markdown(f"{info.display_name}")
            bucket = col_bucket.radio(
                f"Bucket for {info.name}",
                options=["none", "fixed", "fill"],
                key=f"sweep_bucket#{info.name}",
                horizontal=True,
                label_visibility="collapsed",
                help=info.description,
            )
            if bucket == "fixed":
                fixed[info.name] = int(
                    col_value.number_input(
                        f"Fixed count for {info.name}",
                        min_value=1,
                        value=1,
                        step=1,
                        key=f"sweep_fixed#{info.name}",
                        label_visibility="collapsed",
                        help="This many agents of the strategy, in every member run.",
                    )
                )
            elif bucket == "fill":
                fill[info.name] = float(
                    col_value.number_input(
                        f"Fill percentage for {info.name}",
                        min_value=0.0,
                        max_value=100.0,
                        value=100.0,
                        step=5.0,
                        key=f"sweep_fill#{info.name}",
                        label_visibility="collapsed",
                        help=(
                            "This strategy's share of the seats left after the "
                            "invader and the fixed counts are placed."
                        ),
                    )
                )
        if fill:
            fill_total = sum(fill.values())
            if abs(fill_total - 100) > 1e-6:
                st.warning(f"Fill percentages sum to {fill_total:g} — they must sum to 100.")
            else:
                st.caption(f"Fill percentages sum to {fill_total:g}.")
        # Live preview: the real three-bucket arithmetic at the largest count
        # (largest-remainder rounding included), so what you see is exactly
        # what the member configs get (explainer §2.2/§4).
        size = sweep_helpers.base_population_size(fields)
        if counts and size is not None:
            try:
                resolved = resolve_composition(size, vary, max(counts), fixed, fill)
            except ValueError as error:
                st.warning(str(error))
            else:
                resolved_text = ", ".join(f"{name} {count}" for name, count in resolved.items())
                st.caption(
                    f"Preview at the largest invader count ({max(counts)}): "
                    f"{resolved_text} — total {size}."
                )
    return {"vary": vary, "counts": counts, "fixed": fixed, "fill": fill}


def _sweep_parameter_axes_area() -> list[dict[str, object]]:
    """Render the add/remove parameter-axis rows; return the authored axes.

    Each axis pairs a Parameter Registry key with a list of values to try;
    the sweep runs the cross product of all axes. Values are parsed and
    checked per axis (``sweep_helpers.parse_value_list`` /
    ``validate_parameter_values``) so errors appear next to their widget.

    Returns:
        One ``{key, values}`` dict per authored axis.
    """
    st.markdown("**Parameter axes** — sweep any registry parameter over a list of values.")
    st.button(
        "Add parameter axis",
        key="sweep_add_axis",
        on_click=_add_param_axis,
        help=(
            "Each axis multiplies the sweep: 3 values on one axis and 4 on another "
            "make 12 combinations (times counts and seeds)."
        ),
    )
    # run.seed is excluded: seeds are their own first-class axis below, and a
    # run.seed parameter axis would be silently overwritten by the seed loop.
    keys = [spec.key for spec in helpers.panel_specs() if spec.key != "run.seed"]
    axes: list[dict[str, object]] = []
    for axis_id in st.session_state.get("sweep_param_axes", []):
        col_key, col_values, col_remove = st.columns([2, 3, 1])
        key = col_key.selectbox(
            "Parameter",
            options=keys,
            key=f"sweep_axis_key#{axis_id}",
            help="Any Parameter Registry key; its registry rules validate each value.",
        )
        text = col_values.text_input(
            "Values",
            key=f"sweep_axis_values#{axis_id}",
            help="Comma/space-separated values to try, e.g. '0.01, 0.1, 1.0'.",
        )
        col_remove.button(
            "Remove",
            key=f"sweep_axis_remove#{axis_id}",
            on_click=_remove_param_axis,
            args=(axis_id,),
        )
        values: list[ParamValue] = []
        try:
            values = sweep_helpers.parse_value_list(key, text)
        except ValueError as error:
            st.error(str(error))
        for message in sweep_helpers.validate_parameter_values(key, values):
            st.error(message)
        axes.append({"key": key, "values": values})
    return axes


def _sweep_metrics_area() -> list[dict[str, object]]:
    """Render the metric multiselect + per-metric params; return MetricRefs.

    Metrics come from the Outcome Metrics Registry (the fourth registry,
    DECISIONS #69), so a newly registered metric appears here with zero UI
    edits — each declared ``MetricParam`` renders by its kind (a strategy
    selectbox, or a number input).

    Returns:
        One ``{metric, **params}`` dict per selected metric.
    """
    infos = {info.display_name: info for info in all_metrics()}
    chosen = st.multiselect(
        "Metrics",
        options=list(infos),
        key="sweep_metrics",
        help=(
            "The numbers to compute from each finished member run (one summary "
            "column each). Docs: the 'Outcome metrics' section of docs/PARAMETERS.md."
        ),
    )
    strategy_names = [info.name for info in all_strategies()]
    refs: list[dict[str, object]] = []
    for display_name in chosen:
        info = infos[display_name]
        ref: dict[str, object] = {"metric": info.name}
        if info.params:
            columns = st.columns(max(3, len(info.params)))
            for i, param in enumerate(info.params):
                widget_key = f"sweep_metric#{info.name}#{param.name}"
                label = f"{param.name} — {info.display_name}"
                with columns[i % len(columns)]:
                    if param.kind == "strategy":
                        ref[param.name] = st.selectbox(
                            label, options=strategy_names, key=widget_key, help=param.description
                        )
                    elif param.kind == "int":
                        ref[param.name] = int(
                            st.number_input(
                                label,
                                min_value=1,
                                value=int(param.default or 1),
                                step=1,
                                key=widget_key,
                                help=param.description,
                            )
                        )
                    else:  # float params are shares in [0, 1] (threshold)
                        ref[param.name] = float(
                            st.number_input(
                                label,
                                min_value=0.0,
                                max_value=1.0,
                                value=float(param.default or 0.0),
                                step=0.05,
                                key=widget_key,
                                help=param.description,
                            )
                        )
        refs.append(ref)
    return refs


def _sweep_validation_area(fields: dict[str, object]) -> SweepSpec | None:
    """Validate the authored fields; render errors or the expansion size.

    ONE validation path (DECISIONS #72): structural errors surface through
    the same :func:`helpers.validation_messages` extraction the Run lab
    uses, semantic errors through the same
    :func:`~pdsim.sweep.spec.sweep_validation_messages` the CLI prints.

    Args:
        fields: The complete authored-values dict.

    Returns:
        The clean, launchable spec — or ``None`` while anything is wrong.
    """
    try:
        spec = sweep_helpers.build_sweep_spec(fields)
    except ValidationError as error:
        for message in helpers.validation_messages(error):
            st.error(message)
        return None
    messages = sweep_validation_messages(spec)
    for message in messages:
        st.error(message)
    if messages:
        return None
    try:
        member_count = len(expand(spec))
    except ValueError as error:
        st.error(str(error))
        return None
    st.success(
        f"This sweep expands to {member_count} member runs."
        + (" That is a lot — consider fewer values per axis." if member_count > 1000 else "")
    )
    yaml_text = sweep_spec_yaml(spec)
    with st.expander("Authored sweep spec (YAML)"):
        st.caption(
            "Exactly what Launch writes and the CLI reads — you could save this "
            "and run `python -m pdsim.sweep <file> --out sweeps` yourself."
        )
        st.code(yaml_text, language="yaml")
        st.download_button(
            "Download spec YAML",
            data=yaml_text,
            file_name=f"{spec.name}.yaml",
            mime="text/yaml",
            key="sweep_download",
        )
    return spec


def _sweep_launch_area(spec: SweepSpec | None) -> None:
    """Render the resume notice and the Launch button; spawn the runner.

    Launch is a DETACHED subprocess of the unchanged headless CLI
    (DECISIONS #72): the authored spec is written to a named file, then
    ``python -m pdsim.sweep <spec> --out <dir>`` is spawned with its output
    captured to a launch log. The Streamlit script thread never blocks, and
    the running sweep is inspectable/killable exactly like a terminal one.

    Args:
        spec: The validated spec, or ``None`` (button disabled).
    """
    name = str(st.session_state.get("sweep_name", "")).strip()
    if name and sweep_helpers.sweep_folder_exists(SWEEPS_DIR, name):
        st.info(
            f"A sweep named '{name}' already exists under {SWEEPS_DIR}/ — launching "
            "will RESUME it: members already finished are skipped and only missing "
            "or failed ones run. Pick a new name (or delete the folder) for a "
            "fresh sweep."
        )
    if st.button("Launch sweep", type="primary", key="sweep_launch", disabled=spec is None):
        assert spec is not None  # the button is disabled otherwise
        SWEEPS_DIR.mkdir(parents=True, exist_ok=True)
        spec_path = sweep_helpers.write_authored_spec(
            spec, sweep_helpers.authored_spec_path(SWEEPS_DIR, spec.name)
        )
        command = sweep_helpers.build_launch_command(spec_path, SWEEPS_DIR)
        log_path = sweep_helpers.launch_log_path(SWEEPS_DIR, spec.name)
        # The child inherits the log handle; closing the parent's copy right
        # after Popen is safe and keeps this script run non-blocking.
        with open(log_path, "w", encoding="utf-8") as log_handle:
            subprocess.Popen(command, stdout=log_handle, stderr=subprocess.STDOUT)
        st.session_state["_launched_sweep"] = spec.name
        st.success(
            f"Launched `{' '.join(command)}` — the app stays responsive while it "
            f"runs. Follow progress with 'Refresh status' below; output goes to "
            f"{log_path}."
        )


def _sweep_monitor_area() -> None:
    """Render the monitor: sweep picker, manual refresh, status, headline chart.

    Deliberately NOT a browser (DECISIONS #74): status plus ONE
    metric-vs-axis chart, read from the sweep's own files. The status file
    is read-only here — the runner subprocess is its sole writer (#70) —
    and refresh is a manual click (a sweep is a minutes-scale job; no
    auto-poll timer, no add-on dependency).
    """
    st.subheader("Monitor")
    names = sweep_helpers.list_sweep_names(SWEEPS_DIR)
    if not names:
        st.info(
            "No sweeps yet. Author and launch one above, or run one headlessly: "
            "`python -m pdsim.sweep examples/sweeps/tft_invasion.yaml`."
        )
        return
    # A widget's own key may only be written before it exists in a script
    # run (the #52 pattern): a just-launched sweep stages its name here.
    staged = st.session_state.pop("_launched_sweep", None)
    if staged in names:
        st.session_state["monitor_sweep"] = staged
    elif st.session_state.get("monitor_sweep") not in names:
        st.session_state["monitor_sweep"] = names[0]
    col_pick, col_refresh = st.columns([4, 1])
    name = col_pick.selectbox(
        "Sweep",
        options=names,
        key="monitor_sweep",
        help="Every sweep folder currently under sweeps/ (most recently active first).",
    )
    col_refresh.button(
        "Refresh status",
        key="monitor_refresh",
        help=(
            "Re-read this sweep's status file (the runner rewrites it after every "
            "member run). The click is the refresh — there is no auto-polling."
        ),
    )
    status = sweep_helpers.read_sweep_status(SWEEPS_DIR, name)
    if status is None:
        st.info(
            "No status file yet — the runner writes sweep_status.json once it "
            "starts. Press 'Refresh status' in a moment."
        )
    else:
        col_total, col_done, col_failed, col_left = st.columns(4)
        col_total.metric("Total members", int(status.get("total", 0)))
        col_done.metric("Completed", int(status.get("completed", 0)))
        col_failed.metric("Failed", int(status.get("failed", 0)))
        col_left.metric("Remaining", int(status.get("running", 0)))
        st.caption(
            f"Started {status.get('started_at', '?')} · last update {status.get('updated_at', '?')}"
        )
        rows = sweep_helpers.status_rows(status)
        if rows:
            st.dataframe(rows, use_container_width=True)
    log_path = sweep_helpers.launch_log_path(SWEEPS_DIR, name)
    if log_path.is_file():
        with st.expander("Launch log"):
            try:
                st.code(log_path.read_text(encoding="utf-8")[-4000:] or "(empty so far)")
            except OSError as error:
                st.caption(f"Could not read the launch log right now: {error}")
    parquet_path = SWEEPS_DIR / name / "sweep_summary.parquet"
    if parquet_path.is_file():
        meta = None
        try:
            meta = sweep_helpers.read_sweep_summary_meta(SWEEPS_DIR, name)
        except ValueError as error:
            st.error(str(error))
        if meta is not None:
            frame = pd.read_parquet(parquet_path)
            axis_options = [
                column for column in meta.get("axis_columns", []) if column in frame.columns
            ] or ["seed"]
            metric_options = [
                column for column in meta.get("metric_columns", []) if column in frame.columns
            ]
            if metric_options:
                col_axis, col_metric = st.columns(2)
                axis = col_axis.selectbox(
                    "Axis (x)",
                    options=axis_options,
                    key=f"monitor_axis#{name}",  # per-sweep key: switching resets cleanly
                    help="The swept quantity to put on the x-axis.",
                )
                metric = col_metric.selectbox(
                    "Metric (y)",
                    options=metric_options,
                    key=f"monitor_metric#{name}",
                    help="The outcome metric to plot (mean line + replicate-spread band).",
                )
                labels = sweep_helpers.metric_display_labels(meta)
                st.plotly_chart(
                    charts.sweep_metric_chart(frame, axis, metric, metric_label=labels.get(metric)),
                    use_container_width=True,
                    key=f"monitor_chart#{name}",
                )
    else:
        st.caption("The headline chart appears here once the sweep finishes.")
    st.caption(
        f"Member run folders live under {SWEEPS_DIR / name / 'runs'} — each is an "
        "ordinary, independently reproducible run folder. Rich per-member and "
        "cross-sweep browsing arrives in the follow-on sweep-browser increment."
    )


def _sweep_tab() -> None:
    """Lay out the Sweep tab: author a SweepSpec, launch it, monitor it.

    A thin rendering shell (DECISIONS #38 applied again): every branch worth
    testing lives in :mod:`pdsim.ui.sweep_helpers`. The tab authors the SAME
    ``sweep_spec.yaml`` the CLI consumes and spawns the SAME runner —
    execution stays headless (DECISIONS #72; explainer §4).
    """
    st.markdown(
        "Author a **sweep** — a whole family of runs varied along composition, "
        "parameter, and seed axes — then launch it headlessly and watch its "
        "progress. Execution is the unchanged `python -m pdsim.sweep` CLI, so a "
        "launched sweep can equally be resumed, inspected, or stopped from a "
        "terminal."
    )
    range_error = st.session_state.pop("_sweep_range_error", None)
    if range_error:
        st.error(range_error)

    fields: dict[str, object] = {}
    fields["name"] = st.text_input(
        "Sweep name",
        key="sweep_name",
        help=(
            "A safe lowercase token like 'tft_invasion_app' — it becomes the "
            "sweeps/<name>/ folder name."
        ),
    ).strip()
    base_kind = st.radio(
        "Base configuration",
        options=["From a scenario", "From a config file"],
        key="sweep_base_kind",
        horizontal=True,
        help=(
            "Every member run starts from this configuration; the axes below "
            "override its composition, parameters, and seed per member."
        ),
    )
    if base_kind == "From a scenario":
        scenarios = {info.display_name: info for info in all_scenarios()}
        choice = st.selectbox(
            "Base scenario",
            options=list(scenarios),
            key="sweep_base_scenario",
            help="A curated scenario to use as the base configuration.",
        )
        fields["base_kind"] = "scenario"
        fields["base_scenario"] = scenarios[choice].name
    else:
        fields["base_kind"] = "path"
        fields["base_path"] = st.text_input(
            "Config file path",
            key="sweep_base_path",
            help=(
                "Path to a run config YAML — e.g. the config.yaml inside any recorded run folder."
            ),
        )
    fields["composition"] = _sweep_composition_area(fields)
    fields["parameters"] = _sweep_parameter_axes_area()

    seeds_text = st.text_input(
        "Seeds",
        key="sweep_seeds",
        help=(
            "The random seeds to replicate every combination over. Invasion is a "
            "probability, not a certainty — several seeds per point estimate it "
            "(explainer §3.5)."
        ),
    )
    col_seed_start, col_seed_count, col_seed_fill = st.columns([1, 1, 1])
    seed_start = int(
        col_seed_start.number_input(
            "First seed", min_value=0, value=1, step=1, key="sweep_seed_start"
        )
    )
    seed_count = int(
        col_seed_count.number_input(
            "How many seeds", min_value=1, value=10, step=1, key="sweep_seed_count"
        )
    )
    col_seed_fill.button(
        "Fill seeds",
        key="sweep_seeds_fill",
        on_click=_fill_range_field,
        args=("sweep_seeds", seed_start, seed_start + seed_count - 1, 1),
        help="Write a consecutive seed list into the seeds field; edit freely after.",
    )
    try:
        fields["seeds"] = sweep_helpers.parse_int_list(seeds_text)
    except ValueError as error:
        st.error(str(error))
        fields["seeds"] = []

    fields["metrics"] = _sweep_metrics_area()

    st.divider()
    # A completely untouched tab shows a pointer instead of validation errors.
    authored_anything = any(
        (
            fields["name"],
            fields["composition"],
            fields["parameters"],
            fields["seeds"],
            fields["metrics"],
        )
    )
    if authored_anything:
        spec = _sweep_validation_area(fields)
    else:
        st.caption("Fill in the sections above — validation runs as you author.")
        spec = None
    _sweep_launch_area(spec)
    st.divider()
    _sweep_monitor_area()


def main() -> None:
    """Lay out the app: the Run lab, Results browser, and Sweep tabs."""
    st.title("Evolutionary Prisoner's Dilemma Simulator")
    _apply_pending_load()
    tab_lab, tab_browser, tab_sweep = st.tabs(["Run lab", "Results browser", "Sweep"])
    with tab_lab:
        _run_lab()
    with tab_browser:
        _results_browser()
    with tab_sweep:
        _sweep_tab()


main()
