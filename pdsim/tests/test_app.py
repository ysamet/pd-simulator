"""Smoke tests for the Streamlit app via ``streamlit.testing.v1.AppTest``.

AppTest executes ``pdsim/ui/app.py`` headlessly, so these tests cover what a
browser session would exercise: the app renders without exceptions, every
scenario loads its config into the panel, and a tiny custom run completes
end to end (the live loop runs synchronously inside AppTest). Deeper logic
lives in the plain helpers and is tested without Streamlit.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
import streamlit
import yaml
from streamlit.testing.v1 import AppTest

from pdsim.config.experiment import ExperimentConfig
from pdsim.config.scenarios import all_scenarios
from pdsim.core import engine, layouts
from pdsim.core.layouts import format_layout_file
from pdsim.core.strategies import all_strategies
from pdsim.core.timeseries import RunTimeseries
from pdsim.io.results import RunRecorder, list_runs, load_run
from pdsim.run import main as cli_main
from pdsim.ui import painter_helpers

APP_PATH = str(Path(__file__).resolve().parents[1] / "ui" / "app.py")


def _record_tiny(out_dir: Path, seed: int = 12345) -> Path:
    """Record a minimal run into a test directory.

    Args:
        out_dir: Runs directory for the recording.
        seed: The run's seed (asserted on by panel-loading tests).

    Returns:
        The recorded run folder.
    """
    config = ExperimentConfig.model_validate(
        {
            "seed": seed,
            "population": {"size": 4, "composition": {"tit_for_tat": 2, "always_defect": 2}},
            "match": {"rounds_per_match": 5},
            "dynamics": {"generations": 2},
        }
    )
    recorder = RunRecorder(config, out_dir=out_dir, scenario="browser_test")
    for event in engine.run(config):
        recorder.add(event)
    return recorder.finalize()


def _fresh_app() -> AppTest:
    """Load and run the app once.

    Returns:
        The AppTest handle after the first script run.
    """
    app = AppTest.from_file(APP_PATH, default_timeout=60)
    app.run()
    return app


class TestAppLoads:
    """The app must render from a cold start."""

    def test_first_render_has_no_exception(self) -> None:
        """A cold start renders the full panel without raising."""
        app = _fresh_app()
        assert not app.exception
        assert app.selectbox(key="scenario_choice").value is not None
        assert app.button(key="run_button") is not None

    def test_default_scenario_populates_the_panel(self) -> None:
        """The initially selected scenario's values reach the widgets."""
        app = _fresh_app()
        # Default selection is the first registered scenario: the tournament.
        assert app.session_state["run.mode"] == "tournament"
        assert app.number_input(key="run.tournament_cycles").value == 10


class TestScenarioSelection:
    """Selecting each scenario loads its config; Custom loads defaults."""

    @pytest.mark.parametrize("display_name", [info.display_name for info in all_scenarios()])
    def test_each_scenario_loads_without_exception(self, display_name: str) -> None:
        """Every registry scenario populates the panel cleanly."""
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select(display_name)
        app.run()
        assert not app.exception

    def test_scenario_values_reach_widgets_and_survive_edits(self) -> None:
        """Loading fills widgets; a later edit is not fought (DECISIONS #40)."""
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Defectors' Paradise")
        app.run()
        assert app.session_state["match.length_mode"] == "continuation"
        assert app.number_input(key="composition.always_defect").value == 20
        app.number_input(key="composition.always_defect").set_value(19)
        app.run()
        assert not app.exception
        assert app.number_input(key="composition.always_defect").value == 19
        assert app.selectbox(key="scenario_choice").value == "Defectors' Paradise"

    def test_custom_starts_from_registry_defaults(self) -> None:
        """'Custom' = documented defaults + an even population split."""
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Custom")
        app.run()
        assert app.session_state["run.mode"] == "evolution"
        assert app.number_input(key="population.size").value == 100
        composition = [
            app.number_input(key=f"composition.{info.name}").value for info in all_strategies()
        ]
        assert sum(composition) == 100


class TestTinyRunCompletes:
    """A minimal custom run flows through the live loop to the summary."""

    def test_run_button_produces_a_completed_run(self) -> None:
        """4 agents, 2 generations, 5-round matches: success + summary.

        The #39 tiny-live-run pin, re-expressed on the E3 per-pass loop
        (#184) without a change: the loop schedules each pass with
        ``st.rerun()`` and AppTest's runner follows that chain to its end,
        so the one ``run()`` after the click still drives the whole run —
        three passes here — to the success message.
        """
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Custom")
        app.run()
        app.number_input(key="population.size").set_value(4)
        for name in (
            "always_cooperate",
            "generous_tit_for_tat",
            "grim_trigger",
            "pavlov",
            "random",
        ):
            app.number_input(key=f"composition.{name}").set_value(0)
        app.number_input(key="composition.tit_for_tat").set_value(2)
        app.number_input(key="composition.always_defect").set_value(2)
        app.number_input(key="dynamics.generations").set_value(2)
        app.number_input(key="match.rounds_per_match").set_value(5)
        app.slider(key="playback_delay").set_value(0.0)
        app.checkbox(key="record_run").set_value(False)  # keep tests folder-free
        app.run()
        assert not app.exception
        app.button(key="run_button").click()
        app.run()
        assert not app.exception
        assert len(app.success) == 1
        assert "2 generations" in app.success[0].value

    def test_results_persist_and_score_view_toggles_after_the_run(self) -> None:
        """The score view re-renders the last run without re-running it.

        DECISIONS #44: results persist in session state, so flipping the
        toggle after a run redraws the same data on the per-round scale.
        """
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Custom")
        app.run()
        app.number_input(key="population.size").set_value(4)
        for name in (
            "always_cooperate",
            "generous_tit_for_tat",
            "grim_trigger",
            "pavlov",
            "random",
        ):
            app.number_input(key=f"composition.{name}").set_value(0)
        app.number_input(key="composition.tit_for_tat").set_value(2)
        app.number_input(key="composition.always_defect").set_value(2)
        app.number_input(key="dynamics.generations").set_value(2)
        app.number_input(key="match.rounds_per_match").set_value(5)
        app.slider(key="playback_delay").set_value(0.0)
        app.checkbox(key="record_run").set_value(False)  # keep tests folder-free
        app.run()
        app.button(key="run_button").click()
        app.run()
        assert "last_run" in app.session_state
        app.radio(key="score_view").set_value("per_round")
        app.run()
        assert not app.exception  # persisted charts re-rendered per-round
        app.radio(key="time_scope").set_value("whole_game")
        app.run()
        assert not app.exception  # and again under the whole-game scope (#45)


class TestResultsBrowser:
    """The Results browser tab (M7, DECISIONS #49).

    ``PDSIM_RUNS_DIR`` points the app at a per-test directory, so these
    tests never touch the repository's real ``runs/`` folder.
    """

    def test_empty_state_is_a_friendly_pointer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No runs recorded yet -> guidance, not an error."""
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path / "empty"))
        app = _fresh_app()
        assert not app.exception
        assert any("No recorded runs yet" in item.value for item in app.info)

    def test_recorded_run_renders_and_loads_into_panel(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A recorded run appears, renders charts, and refills the panel."""
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path))
        config = ExperimentConfig.model_validate(
            {
                "seed": 12345,
                "population": {"size": 4, "composition": {"tit_for_tat": 2, "always_defect": 2}},
                "match": {"rounds_per_match": 5},
                "dynamics": {"generations": 2},
            }
        )
        recorder = RunRecorder(config, out_dir=tmp_path, scenario="browser_test")
        for event in engine.run(config):
            recorder.add(event)
        recorder.finalize()

        app = _fresh_app()
        assert not app.exception
        assert app.selectbox(key="browser_run").value  # newest run preselected
        app.button(key="browser_load").click()
        app.run()
        assert not app.exception
        assert app.selectbox(key="scenario_choice").value == "Custom"
        assert app.number_input(key="run.seed").value == 12345
        assert app.number_input(key="composition.tit_for_tat").value == 2

    def test_hand_deleted_folder_leaves_the_dropdown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A folder deleted outside the app leaves the dropdown quietly.

        The listing is folder truth (DECISIONS #50) — no more stale names
        erroring on selection.
        """
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path))
        folder = _record_tiny(tmp_path)
        shutil.rmtree(folder)  # deleted by hand; index.csv still lists it
        app = _fresh_app()
        assert not app.exception
        assert any("No recorded runs yet" in item.value for item in app.info)

    def test_renamed_folder_appears_under_its_new_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A hand-renamed folder shows (and loads) under the new name."""
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path))
        folder = _record_tiny(tmp_path)
        folder.rename(folder.with_name("my-renamed-run"))
        app = _fresh_app()
        assert not app.exception
        assert app.selectbox(key="browser_run").value == "my-renamed-run"

    def test_delete_button_confirms_then_removes_the_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Delete asks for confirmation, then removes folder + listing."""
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path))
        folder = _record_tiny(tmp_path)
        app = _fresh_app()
        app.button(key="browser_delete").click()
        app.run()
        assert not app.exception
        assert folder.exists()  # not yet — confirmation pending
        app.button(key="browser_delete_confirm").click()
        app.run()
        assert not app.exception
        assert not folder.exists()
        assert any("No recorded runs yet" in item.value for item in app.info)

    def test_delete_can_be_cancelled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cancel keeps the run untouched."""
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path))
        folder = _record_tiny(tmp_path)
        app = _fresh_app()
        app.button(key="browser_delete").click()
        app.run()
        app.button(key="browser_delete_cancel").click()
        app.run()
        assert not app.exception
        assert folder.exists()
        assert app.selectbox(key="browser_run").value == folder.name

    def test_deleted_run_leaves_the_dropdown_immediately(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DECISIONS #52: the dropdown moves to a surviving run at once."""
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path))
        _record_tiny(tmp_path, seed=1)
        _record_tiny(tmp_path, seed=2)
        app = _fresh_app()
        doomed = app.selectbox(key="browser_run").value
        app.button(key="browser_delete").click()
        app.run()
        app.button(key="browser_delete_confirm").click()
        app.run()
        assert not app.exception
        survivor = app.selectbox(key="browser_run").value
        assert survivor is not None
        assert survivor != doomed

    def test_rename_from_the_app(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Rename moves the folder and the dropdown follows the new name."""
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path))
        folder = _record_tiny(tmp_path)
        app = _fresh_app()
        run_id = app.selectbox(key="browser_run").value
        app.text_input(key=f"browser_rename#{run_id}").set_value("shiny-new-name")
        app.run()
        app.button(key="browser_rename_apply").click()
        app.run()
        assert not app.exception
        assert app.selectbox(key="browser_run").value == "shiny-new-name"
        assert (tmp_path / "shiny-new-name").is_dir()
        assert not folder.exists()

    def test_custom_runs_record_the_custom_scenario_label(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DECISIONS #52: a recorded Custom run shows 'Custom', not blank."""
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path))
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Custom")
        app.run()
        app.number_input(key="population.size").set_value(4)
        for name in (
            "always_cooperate",
            "generous_tit_for_tat",
            "grim_trigger",
            "pavlov",
            "random",
        ):
            app.number_input(key=f"composition.{name}").set_value(0)
        app.number_input(key="composition.tit_for_tat").set_value(2)
        app.number_input(key="composition.always_defect").set_value(2)
        app.number_input(key="dynamics.generations").set_value(2)
        app.number_input(key="match.rounds_per_match").set_value(5)
        app.slider(key="playback_delay").set_value(0.0)
        app.run()  # record_run stays default ON — pointed at tmp_path
        app.button(key="run_button").click()
        app.run()
        assert not app.exception
        cards = list_runs(tmp_path)
        assert cards and cards[0]["scenario"] == "Custom"
        # A cleanly completed run clears the write-ahead note (#55):
        # no stray "cleaned up" banner on later renders.
        app.run()
        assert not any("cleaned up" in item.value for item in app.info)

    def test_run_killed_mid_stream_leaves_no_ghost_folder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DECISIONS #53: abnormal termination discards the recording.

        In live Streamlit, Stop (or a mid-run Run click) KILLS the running
        script rather than setting our flag — modeled here by an engine
        that dies mid-stream. The try/finally must still discard the
        partial folder so no ghost is left behind.
        """
        from pdsim.core import engine as core_engine

        real_run = core_engine.run

        def dying_run(*args: object, **kwargs: object) -> Iterator[object]:
            """Yield a few real events, then die like an interrupted script."""
            stream = real_run(*args, **kwargs)
            for _ in range(3):
                yield next(stream)
            raise RuntimeError("script killed mid-run")

        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path))
        monkeypatch.setattr(core_engine, "run", dying_run)
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Custom")
        app.run()
        app.number_input(key="population.size").set_value(4)
        for name in (
            "always_cooperate",
            "generous_tit_for_tat",
            "grim_trigger",
            "pavlov",
            "random",
        ):
            app.number_input(key=f"composition.{name}").set_value(0)
        app.number_input(key="composition.tit_for_tat").set_value(2)
        app.number_input(key="composition.always_defect").set_value(2)
        app.number_input(key="match.rounds_per_match").set_value(5)
        app.slider(key="playback_delay").set_value(0.0)
        app.run()  # record_run stays default ON — pointed at tmp_path
        app.button(key="run_button").click()
        app.run()
        assert app.exception  # the mid-run death surfaced
        assert not any(p.is_dir() for p in tmp_path.iterdir())  # no ghost folder
        # The staged note shows on the next render.
        app.run()
        assert any("partial folder was cleaned up" in item.value for item in app.info)


def _set_tiny_population(app: AppTest) -> None:
    """Point the mix widgets at a 4-agent TFT/AD population (test speed).

    Args:
        app: The AppTest handle, with the panel in evolution mode.
    """
    app.number_input(key="population.size").set_value(4)
    for name in (
        "always_cooperate",
        "generous_tit_for_tat",
        "grim_trigger",
        "pavlov",
        "random",
    ):
        app.number_input(key=f"composition.{name}").set_value(0)
    app.number_input(key="composition.tit_for_tat").set_value(2)
    app.number_input(key="composition.always_defect").set_value(2)


class TestModeTabs:
    """The E1 run-mode tab split (#158 executed per #178).

    Hiding, preservation, the collapse summaries, and the Economy
    panel's gate.
    """

    def test_tournament_tab_hides_sections_but_greys_matching(self) -> None:
        """R3: no Structure/Movement/Dynamics widgets; Matching greys (R10).

        The default scenario is The Classic Tournament, so the cold start
        IS the tournament tab.
        """
        app = _fresh_app()
        assert app.session_state["run.mode"] == "tournament"
        with pytest.raises(KeyError):
            app.selectbox(key="structure.kind")
        with pytest.raises(KeyError):
            app.number_input(key="movement.rate")
        with pytest.raises(KeyError):
            app.number_input(key="dynamics.generations")
        with pytest.raises(KeyError):
            app.selectbox(key="dynamics.reproduction_mode")
        # The Matching section stays, its spatial keys greyed, not hidden.
        spatial = app.checkbox(key="matching.spatial_interaction")
        assert spatial.disabled is True
        encounter = app.selectbox(key="matching.encounter_mode")
        assert encounter.disabled is True
        # The Economy panel is absent in BOTH of its shapes.
        with pytest.raises(KeyError):
            app.toggle(key="economy_concepts")
        with pytest.raises(KeyError):
            app.toggle(key="economy_inactive_summary")
        assert not any("Economy calibration" in item.value for item in app.markdown)

    def test_mode_round_trip_preserves_hidden_values(self) -> None:
        """R1/R2: the mode round trip keeps every widget value.

        Covered: a choice widget, a nullable checkbox/value pair, and a
        composition count.
        """
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Custom")
        app.run()
        assert app.session_state["run.mode"] == "evolution"
        app.selectbox(key="structure.kind").select("lattice")
        app.selectbox(key="structure.neighbourhood_shape").select("von_neumann")
        app.checkbox(key="structure.rows#limit").set_value(True)
        app.number_input(key="structure.rows#value").set_value(20)
        app.number_input(key="composition.tit_for_tat").set_value(37)
        app.run()
        assert not app.exception
        app.segmented_control(key="run.mode").set_value("tournament")
        app.run()
        assert not app.exception
        with pytest.raises(KeyError):  # hidden on the tournament tab...
            app.selectbox(key="structure.kind")
        assert app.session_state["structure.kind"] == "lattice"  # ...but preserved
        assert app.session_state["structure.neighbourhood_shape"] == "von_neumann"
        assert app.session_state["structure.rows#limit"] is True
        assert app.session_state["structure.rows#value"] == 20
        app.segmented_control(key="run.mode").set_value("evolution")
        app.run()
        assert not app.exception
        assert app.selectbox(key="structure.kind").value == "lattice"
        assert app.selectbox(key="structure.neighbourhood_shape").value == "von_neumann"
        assert app.checkbox(key="structure.rows#limit").value is True
        assert app.number_input(key="structure.rows#value").value == 20
        assert app.number_input(key="composition.tit_for_tat").value == 37

    def test_tournament_config_carries_preserved_hidden_values(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R2: a tournament recording carries preserved hidden values.

        Not registry defaults — so recorded-config → load → run stays a
        faithful round trip in both directions.
        """
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path))
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Custom")
        app.run()
        _set_tiny_population(app)
        app.number_input(key="match.rounds_per_match").set_value(5)
        app.number_input(key="dynamics.generations").set_value(7)  # hidden below
        app.run()
        app.segmented_control(key="run.mode").set_value("tournament")
        app.run()
        app.number_input(key="run.tournament_cycles").set_value(2)
        app.slider(key="playback_delay").set_value(0.0)
        app.run()  # record_run stays default ON — pointed at tmp_path
        app.button(key="run_button").click()
        app.run()
        assert not app.exception
        cards = list_runs(tmp_path)
        assert cards
        loaded = load_run(tmp_path / str(cards[0]["run_id"]))
        assert loaded.config.mode == "tournament"
        assert loaded.config.dynamics.generations == 7  # preserved, not default

    def test_structure_and_movement_collapse_summaries(self) -> None:
        """R4/R5: inert sections collapse under cause-naming labels.

        Custom (well-mixed) collapses Structure and Movement; a lattice
        reopens Structure and gives Movement its imitation cause.
        """
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Custom")
        app.run()
        labels = [item.label for item in app.expander]
        assert "Structure — well-mixed, inactive" in labels
        assert "Movement — inactive (well-mixed)" in labels
        app.selectbox(key="structure.kind").select("lattice")
        app.run()
        labels = [item.label for item in app.expander]
        assert "Structure" in labels  # live again, plain label
        assert "Movement — inactive under imitation" in labels  # Custom is imitation

    def test_economy_panel_follows_economy_active(self) -> None:
        """R9: the Economy panel renders per economy_active.

        The summary under sync imitation; the readout as loaded for an
        async variable_n config with a STRANDED imitation widget — the
        #177(f1) corner.
        """
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Custom")
        app.run()
        summary = app.toggle(key="economy_inactive_summary")
        assert "inactive under imitation" in summary.label
        assert not any("Economy calibration" in item.value for item in app.markdown)
        # Async variable_n while reproduction_mode stays stranded at
        # imitation: the economy IS active and now calibrates as loaded.
        app.selectbox(key="dynamics.time_model").select("asynchronous")
        app.run()
        assert not app.exception
        assert app.session_state["dynamics.reproduction_mode"] == "imitation"
        assert any("Economy calibration" in item.value for item in app.markdown)
        with pytest.raises(KeyError):
            app.toggle(key="economy_inactive_summary")

    def test_bc_threshold_scenario_shows_the_fixed_n_summary(self) -> None:
        """R9 under fixed_n: the b/c > k scenario shows the summary.

        The scenario is async fixed_n, so it states its cause instead of
        a calibration that would describe an uncharged living cost.
        """
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("The b/c > k Threshold")
        app.run()
        assert not app.exception
        summary = app.toggle(key="economy_inactive_summary")
        assert "inactive under fixed_n" in summary.label
        assert not any("Economy calibration" in item.value for item in app.markdown)

    def test_output_cadence_loads_from_the_scenario(self) -> None:
        """#172(f6)/#178 C1: a per_event cadence loads into the widgets.

        'Async: Imitation Only' records per_event and the Output
        section's cadence selectbox shows it as loaded.
        """
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Async: Imitation Only")
        app.run()
        assert not app.exception
        assert app.selectbox(key="output.recording_cadence").value == "per_event"


MATCHES_READOUT = "Expected matches per agent per generation"
"""The Structure section's matches readout label (M11b Phase E2, #181 R7)."""


def _fold_labels(app: AppTest) -> list[str]:
    """Every "Advanced settings" expander header currently rendered.

    Args:
        app: The AppTest handle after a script run.

    Returns:
        The fold labels in tree order (the section list order).
    """
    return [item.label for item in app.expander if item.label.startswith("Advanced settings")]


def _matches_readout(app: AppTest) -> str | None:
    """The matches readout's value, or ``None`` when it is not rendered.

    Args:
        app: The AppTest handle after a script run.

    Returns:
        The metric's body text, or ``None`` when the gate is false.
    """
    values = [item.value for item in app.metric if item.label == MATCHES_READOUT]
    assert len(values) <= 1
    return values[0] if values else None


class TestAdvancedFold:
    """The E2 disclosure fold and the matches readout (#181 as built)."""

    def test_fold_present_in_exactly_the_four_sections(self) -> None:
        """(i) Matching, Structure, Movement, Dynamics carry a fold; nothing else.

        The fold is nested inside its section, so in the flattened
        expander list it directly follows its section's own expander.
        """
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Cooperation Survives in Clusters")
        app.run()
        assert not app.exception
        labels = [item.label for item in app.expander]
        assert _fold_labels(app) == ["Advanced settings"] * 4
        for section in ("Matching", "Structure", "Movement", "Dynamics"):
            assert labels[labels.index(section) + 1] == "Advanced settings", section
        for section in ("Game", "Match", "Population", "Output"):
            assert not labels[labels.index(section) + 1].startswith("Advanced settings"), section

    def test_folded_widgets_are_in_the_tree_while_collapsed(self) -> None:
        """(ii) R5: a collapsed fold still instantiates its widgets."""
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Cooperation Survives in Clusters")
        app.run()
        assert app.selectbox(key="matching.encounter_mode").value == "per_initiator"
        assert app.number_input(key="structure.birth_decay").value == 0.0
        assert app.selectbox(key="structure.placement_contest").value == "random"
        assert app.number_input(key="movement.decay").value == 0.0
        assert app.selectbox(key="dynamics.boundary_order").value == "death_first"
        assert app.number_input(key="dynamics.capital_return_rate").value == 0.0
        # No new session state: a keyed expander registers no widget (R5).
        for section in ("Matching", "Structure", "Movement", "Dynamics"):
            assert f"advanced_{section}" not in app.session_state

    def test_folded_edit_reaches_the_gathered_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(iii) boundary_order edited inside the fold lands in the recorded config."""
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path))
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Custom")
        app.run()
        _set_tiny_population(app)
        app.number_input(key="match.rounds_per_match").set_value(5)
        app.number_input(key="dynamics.generations").set_value(2)
        app.selectbox(key="dynamics.boundary_order").select("birth_first")
        app.slider(key="playback_delay").set_value(0.0)
        app.run()
        assert not app.exception
        app.button(key="run_button").click()
        app.run()
        assert not app.exception
        cards = list_runs(tmp_path)
        assert cards
        loaded = load_run(tmp_path / str(cards[0]["run_id"]))
        assert loaded.config.dynamics.boundary_order == "birth_first"

    def test_fold_label_reports_and_reverts(self) -> None:
        """(iv) The R3 header after an edit; the plain header after reverting."""
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Cooperation Survives in Clusters")
        app.run()
        app.selectbox(key="dynamics.boundary_order").select("birth_first")
        app.run()
        assert not app.exception
        assert "Advanced settings — 1 changed: Boundary order = birth_first" in _fold_labels(app)
        app.number_input(key="dynamics.capital_return_rate").set_value(0.02)
        app.run()
        assert (
            "Advanced settings — 2 changed: Capital return rate (r) = 0.02, "
            "Boundary order = birth_first"
        ) in _fold_labels(app)
        app.selectbox(key="dynamics.boundary_order").select("death_first")
        app.number_input(key="dynamics.capital_return_rate").set_value(0.0)
        app.run()
        assert _fold_labels(app) == ["Advanced settings"] * 4

    def test_tournament_tab_keeps_matchings_fold_with_encounter_mode_greyed(self) -> None:
        """(v) Under tournament only Matching's fold renders; encounter_mode greys inside."""
        app = _fresh_app()  # The Classic Tournament: the cold start IS the tournament tab
        assert app.session_state["run.mode"] == "tournament"
        assert _fold_labels(app) == ["Advanced settings"]
        encounter = app.selectbox(key="matching.encounter_mode")
        assert encounter.disabled is True
        assert "IGNORED in tournament mode" in encounter.proto.help

    def test_matches_readout_follows_mode_clock_and_gate(self) -> None:
        """(vi) 8 → 4 (per_pair) → 8 (async, stranded) → absent (well-mixed) → 8 (fixed_n).

        The last leg is the #179(d) resolution pinned: donation_game_threshold
        shows 8 in Structure while the Economy panel shows its fixed_n
        summary exactly as E1 built it.
        """
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Cooperation Survives in Clusters")
        app.run()
        assert _matches_readout(app) == "8"
        neighbours = [item.value for item in app.metric if item.label == "Effective neighbours (k)"]
        assert neighbours == ["4"]
        app.selectbox(key="matching.encounter_mode").select("per_pair")
        app.run()
        assert not app.exception
        assert _matches_readout(app) == "4"
        economy = [item.value for item in app.metric if item.label == "Matches per agent"]
        assert economy == ["4"]  # the Economy panel agrees (one arithmetic source)
        app.selectbox(key="dynamics.time_model").select("asynchronous")
        app.run()
        assert not app.exception
        assert app.session_state["matching.encounter_mode"] == "per_pair"  # stranded
        assert _matches_readout(app) == "8"  # #176 R3 forcing
        readout_help = [item.help for item in app.metric if item.label == MATCHES_READOUT]
        assert "EXPECTED value per generation-equivalent" in readout_help[0]
        app.selectbox(key="scenario_choice").select("Custom")
        app.run()
        assert _matches_readout(app) is None  # well-mixed: the gate is false
        app.selectbox(key="scenario_choice").select("The b/c > k Threshold")
        app.run()
        assert not app.exception
        assert _matches_readout(app) == "8"  # 2 × min(4, 4), exact under fixed_n
        summary = app.toggle(key="economy_inactive_summary")
        assert "inactive under fixed_n" in summary.label
        assert not any("Economy calibration" in item.value for item in app.markdown)

    def test_moran_scenario_shows_its_changed_weights_as_loaded(self) -> None:
        """(vii) The Task 0(d) scenario: the R3 summary before any click."""
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Async: Mixed Moran Rules")
        app.run()
        assert not app.exception
        assert (
            "Advanced settings — 2 changed: Moran weight: birth-death = 0.8, "
            "Moran weight: death-birth = 0.2"
        ) in _fold_labels(app)


LIVE_RUN_KEY = "_live_run"
"""The app's session-state key for the run in progress (M11b Phase E3)."""


@pytest.fixture
def one_pass_per_run(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Make each ``AppTest.run()`` exactly ONE pass of the live loop.

    The loop schedules its next pass with ``st.rerun()``, and AppTest's
    runner follows a rerun chain to its end inside a single ``run()`` (which
    is how the whole-run pin in :class:`TestTinyRunCompletes` drives a run
    to completion in one call). Neutralising ``st.rerun`` here leaves every
    other mechanism intact — the holder, the per-pass advance, the toggles
    read fresh — so a test can flip a widget between passes.

    Args:
        monkeypatch: pytest's patcher (restores ``st.rerun`` afterwards).

    Returns:
        The list of keyword-argument dicts the loop passed to ``st.rerun``,
        one entry per scheduled pass — so a test can assert nothing was
        scheduled after a stop.
    """
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(streamlit, "rerun", lambda **kwargs: calls.append(kwargs))
    return calls


def _prepare_tiny_evolution(app: AppTest, generations: int, record: bool = False) -> None:
    """Point the panel at a 4-agent Custom evolution run and settle it.

    Args:
        app: The AppTest handle after its first run.
        generations: The exact "Generations" value to set.
        record: The "Record this run" checkbox value.
    """
    app.selectbox(key="scenario_choice").select("Custom")
    app.run()
    _set_tiny_population(app)
    app.number_input(key="dynamics.generations").set_value(generations)
    app.number_input(key="match.rounds_per_match").set_value(5)
    app.slider(key="playback_delay").set_value(0.0)
    app.checkbox(key="record_run").set_value(record)
    app.run()
    assert not app.exception


def _prepare_tiny_tournament(app: AppTest, cycles: int) -> None:
    """Point the panel at a 4-agent Custom TOURNAMENT run and settle it.

    Args:
        app: The AppTest handle after its first run.
        cycles: The exact "Tournament cycles" value to set.
    """
    app.selectbox(key="scenario_choice").select("Custom")
    app.run()
    _set_tiny_population(app)
    app.number_input(key="match.rounds_per_match").set_value(5)
    app.segmented_control(key="run.mode").set_value("tournament")
    app.run()
    app.number_input(key="run.tournament_cycles").set_value(cycles)
    app.slider(key="playback_delay").set_value(0.0)
    app.checkbox(key="record_run").set_value(False)
    app.run()
    assert not app.exception


def _fold(events: Iterator[object]) -> RunTimeseries:
    """Fold an uninterrupted headless event stream into a RunTimeseries.

    Args:
        events: An ``engine.run`` stream (its first event decides nothing;
            the mode comes from the events themselves via the accumulator).

    Returns:
        The accumulator after every event.
    """
    first = next(events)
    mode = "tournament" if type(first).__name__ == "CycleFinished" else "evolution"
    series = RunTimeseries(mode=mode)
    series.add(first)  # type: ignore[arg-type]
    for event in events:
        series.add(event)  # type: ignore[arg-type]
    return series


def _assert_series_equal(actual: RunTimeseries, expected: RunTimeseries) -> None:
    """Assert two accumulators carry the same periods, compositions, and scores.

    Args:
        actual: The series the live loop accumulated.
        expected: The series an uninterrupted headless run accumulated.
    """
    assert actual.periods == expected.periods
    assert actual.composition == expected.composition
    assert actual.mean_scores == expected.mean_scores
    assert actual.mean_scores_per_round == expected.mean_scores_per_round
    assert actual.running_mean_scores == expected.running_mean_scores
    assert actual.running_mean_scores_per_round == expected.running_mean_scores_per_round
    assert actual.total_scores == expected.total_scores
    assert actual.cooperation_overall == expected.cooperation_overall
    assert actual.final == expected.final


def _captions(app: AppTest) -> list[str]:
    """Every caption currently rendered.

    Args:
        app: The AppTest handle after a script run.

    Returns:
        Caption texts in tree order.
    """
    return [item.value for item in app.caption]


def _choose_another_run(app: AppTest) -> str:
    """Pick, in the Results browser, a run other than the one preselected.

    Args:
        app: The AppTest handle after a script run, with at least two runs.

    Returns:
        The chosen folder name — a stored choice the next run must displace
        or leave alone (#189 R2).
    """
    box = app.selectbox(key="browser_run")
    other = next(option for option in box.options if option != box.value)
    box.select(other)
    app.run()
    assert not app.exception
    assert app.selectbox(key="browser_run").value == other
    return str(other)


class TestLiveRunContinuity:
    """The E3 per-pass live loop (#168; #183 rulings; #184 build record).

    One ``app.run()`` per pass via the ``one_pass_per_run`` fixture; the
    whole-chain pin (a single ``run()`` driving a run to completion) is
    :class:`TestTinyRunCompletes`, re-expressed unchanged on the new loop.
    """

    def test_toggles_flipped_mid_run_yield_the_headless_series(
        self, one_pass_per_run: list[dict[str, object]]
    ) -> None:
        """(i)/(iii) Score view after pass 2, time scope after pass 3: same series.

        Each pass advances exactly one period, a flip never resets the
        count, and the finished series equals an uninterrupted headless
        run of the frozen config and seed.
        """
        app = _fresh_app()
        _prepare_tiny_evolution(app, generations=4)
        app.button(key="run_button").click()
        app.run()  # pass 1: the click's own script run advances period 1
        assert not app.exception
        live = app.session_state[LIVE_RUN_KEY]
        assert live.periods == 1
        config = live.config
        app.run()  # pass 2
        assert app.session_state[LIVE_RUN_KEY].periods == 2
        app.radio(key="score_view").set_value("per_round")
        app.run()  # pass 3, per-round view
        assert not app.exception
        assert app.session_state[LIVE_RUN_KEY].periods == 3
        app.radio(key="time_scope").set_value("whole_game")
        app.run()  # pass 4, whole-game scope
        assert not app.exception
        assert app.session_state[LIVE_RUN_KEY].periods == 4
        assert app.session_state[LIVE_RUN_KEY].view == (True, True)
        app.run()  # pass 5: RunFinished — finalise
        assert not app.exception
        assert LIVE_RUN_KEY not in app.session_state
        assert len(app.success) == 1
        assert "4 generations" in app.success[0].value
        _assert_series_equal(
            app.session_state["last_run"]["timeseries"], _fold(iter(engine.run(config)))
        )
        assert len(one_pass_per_run) == 4  # passes 1-4 scheduled a successor; 5 did not

    def test_recorded_folder_equals_a_headless_cli_recording(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        one_pass_per_run: list[dict[str, object]],
    ) -> None:
        """(ii) With "Record this run" on, the period tables equal the CLI's."""
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path / "app"))
        app = _fresh_app()
        _prepare_tiny_evolution(app, generations=3, record=True)
        app.button(key="run_button").click()
        app.run()  # pass 1
        app.radio(key="score_view").set_value("per_round")
        app.run()  # pass 2
        app.radio(key="time_scope").set_value("whole_game")
        app.run()  # pass 3
        app.run()  # pass 4: finalise
        assert not app.exception
        assert any("Recorded to" in text for text in _captions(app))
        cards = list_runs(tmp_path / "app")
        assert len(cards) == 1
        folder = tmp_path / "app" / str(cards[0]["run_id"])
        # The same config + seed through `python -m pdsim.run`.
        cli_out = str(tmp_path / "cli")
        assert cli_main([str(folder / "config.yaml"), "--out", cli_out, "--quiet"]) == 0
        cli_folders = [p for p in (tmp_path / "cli").iterdir() if p.is_dir()]
        assert len(cli_folders) == 1
        for name in ("timeseries.parquet", "cooperation.parquet"):
            pd.testing.assert_frame_equal(
                pd.read_parquet(folder / name), pd.read_parquet(cli_folders[0] / name)
            )

    def test_stop_after_pass_two_halts_and_nothing_advances_after(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        one_pass_per_run: list[dict[str, object]],
    ) -> None:
        """(iv) Stop is honoured on the next pass; the recording is discarded (R5)."""
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path))
        app = _fresh_app()
        _prepare_tiny_evolution(app, generations=6, record=True)
        app.button(key="run_button").click()
        app.run()  # pass 1
        app.run()  # pass 2
        assert app.session_state[LIVE_RUN_KEY].periods == 2
        assert any(p.is_dir() for p in tmp_path.iterdir())  # the open recording
        app.button(key="stop_button").click()
        app.run()  # pass 3 sees the flag: halts before advancing
        assert not app.exception
        assert LIVE_RUN_KEY not in app.session_state
        assert any("Run stopped" in item.value for item in app.warning)
        last = app.session_state["last_run"]
        assert last["note"].endswith("stopped early")
        assert last["timeseries"].periods == [0, 1]
        assert not any(p.is_dir() for p in tmp_path.iterdir())  # discarded, not ghosted
        assert any("partial folder was cleaned up" in text for text in _captions(app))
        scheduled = len(one_pass_per_run)
        app.run()  # a further pass advances nothing
        assert not app.exception
        assert LIVE_RUN_KEY not in app.session_state
        assert app.session_state["last_run"]["timeseries"].periods == [0, 1]
        assert len(one_pass_per_run) == scheduled
        assert not any("cleaned up" in item.value for item in app.info)  # no stray banner

    def test_finished_recorded_run_opens_itself_in_the_browser(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        one_pass_per_run: list[dict[str, object]],
    ) -> None:
        """#189 R2: the finishing pass of a RECORDED run selects the new folder.

        The Task 0 (iii) reproduction turned into a pin: with older runs
        present and one of them deliberately chosen, "Open a run" shows the
        newly recorded folder once the run finishes — and not before (an
        open recording has no summary yet, so it is not listed mid-run).
        """
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path))
        _record_tiny(tmp_path, seed=1)
        _record_tiny(tmp_path, seed=2)
        app = _fresh_app()
        chosen = _choose_another_run(app)
        _prepare_tiny_evolution(app, generations=2, record=True)
        before = {p.name for p in tmp_path.iterdir() if p.is_dir()}
        app.button(key="run_button").click()
        app.run()  # pass 1
        app.run()  # pass 2: the last period
        assert app.session_state[LIVE_RUN_KEY].periods == 2
        assert app.selectbox(key="browser_run").value == chosen  # untouched mid-run
        app.run()  # pass 3: RunFinished — the recorder finalises
        assert not app.exception
        assert LIVE_RUN_KEY not in app.session_state
        new = {p.name for p in tmp_path.iterdir() if p.is_dir()} - before
        assert len(new) == 1
        (new_run,) = new
        assert new_run in app.selectbox(key="browser_run").options
        assert app.selectbox(key="browser_run").value == new_run
        assert "_select_run" not in app.session_state  # consumed by the browser
        app.run()  # a further pass keeps it
        assert app.selectbox(key="browser_run").value == new_run

    def test_stopped_run_leaves_the_browser_selection_alone(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        one_pass_per_run: list[dict[str, object]],
    ) -> None:
        """#189 R2: a run stopped after pass two (the #184 shape) changes nothing."""
        monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path))
        _record_tiny(tmp_path, seed=1)
        _record_tiny(tmp_path, seed=2)
        app = _fresh_app()
        chosen = _choose_another_run(app)
        _prepare_tiny_evolution(app, generations=6, record=True)
        app.button(key="run_button").click()
        app.run()  # pass 1
        app.run()  # pass 2
        app.button(key="stop_button").click()
        app.run()  # pass 3: stopped, the recording discarded
        assert not app.exception
        assert LIVE_RUN_KEY not in app.session_state
        assert app.session_state["last_run"]["note"].endswith("stopped early")
        assert app.selectbox(key="browser_run").value == chosen
        assert len(app.selectbox(key="browser_run").options) == 2
        assert "_select_run" not in app.session_state

    def test_run_disabled_and_granularity_greyed_while_running(
        self, one_pass_per_run: list[dict[str, object]]
    ) -> None:
        """(v)/(vi) Run is disabled and granularity greyed mid-run; both live after.

        The click's own script run paints the controls BEFORE the holder
        exists (the button's return value is what starts the run), so that
        one pass still shows them pre-run; the immediately scheduled second
        pass greys them (#184 finding f3). The finishing pass paints them
        live again in the SAME pass (the row is filled after the pass).
        """
        app = _fresh_app()
        _prepare_tiny_evolution(app, generations=3)
        assert app.button(key="run_button").disabled is False
        assert app.selectbox(key="granularity").disabled is False
        app.button(key="run_button").click()
        app.run()  # pass 1: the click pass — controls painted before the holder
        assert app.session_state[LIVE_RUN_KEY].periods == 1
        assert app.button(key="run_button").disabled is False  # the one-pass lag (f3)
        app.run()  # pass 2
        assert app.button(key="run_button").disabled is True
        granularity = app.selectbox(key="granularity")
        assert granularity.disabled is True
        assert "applies from the next Run" in granularity.proto.help
        assert granularity.value == "generation"
        app.run()  # pass 3
        assert app.button(key="run_button").disabled is True
        app.run()  # pass 4: finalise — and the row already shows the idle state
        assert LIVE_RUN_KEY not in app.session_state
        assert app.button(key="run_button").disabled is False
        granularity = app.selectbox(key="granularity")
        assert granularity.disabled is False
        assert "applies from the next Run" not in granularity.proto.help

    def test_mode_switch_and_scenario_load_mid_run_leave_the_run_untouched(
        self, one_pass_per_run: list[dict[str, object]]
    ) -> None:
        """(vii)/R4: a run.mode switch neither stops the run nor changes the series.

        The time-scope toggle stays live (an evolution run is displayed),
        the caption still counts generations, and a scenario load mid-run
        changes the panel only — the frozen config keeps its seed.
        """
        app = _fresh_app()
        _prepare_tiny_evolution(app, generations=5)
        app.button(key="run_button").click()
        app.run()  # pass 1
        seed = app.session_state[LIVE_RUN_KEY].config.seed
        app.segmented_control(key="run.mode").set_value("tournament")
        app.run()  # pass 2, panel on the tournament tab
        assert not app.exception
        live = app.session_state[LIVE_RUN_KEY]
        assert live.periods == 2
        assert live.mode == "evolution"
        assert live.timeseries.mode == "evolution"
        assert "generation 2 finished" in _captions(app)
        assert app.radio(key="time_scope").disabled is False
        app.selectbox(key="scenario_choice").select("Defectors' Paradise")
        app.run()  # pass 3, a scenario loaded into the panel
        assert not app.exception
        live = app.session_state[LIVE_RUN_KEY]
        assert live.periods == 3
        assert live.config.seed == seed
        assert app.number_input(key="composition.always_defect").value == 20  # the panel moved

    def test_time_scope_greying_follows_the_displayed_finished_run(
        self, one_pass_per_run: list[dict[str, object]]
    ) -> None:
        """(vii) A finished evolution run under the tournament tab keeps the toggle live.

        And the converse: a finished tournament run under the evolution tab
        keeps it greyed — the #45 corner keyed to the widget, corrected.
        """
        app = _fresh_app()
        _prepare_tiny_evolution(app, generations=2)
        app.button(key="run_button").click()
        app.run()
        app.run()
        app.run()  # finalise
        assert LIVE_RUN_KEY not in app.session_state
        app.segmented_control(key="run.mode").set_value("tournament")
        app.run()
        assert not app.exception
        assert app.radio(key="time_scope").disabled is False
        assert "last_run" in app.session_state
        # The converse, on a fresh session.
        app = _fresh_app()
        _prepare_tiny_tournament(app, cycles=2)
        assert app.radio(key="time_scope").disabled is False  # nothing displayed yet
        app.button(key="run_button").click()
        app.run()  # the click pass: the row painted before the holder (f3)
        app.run()  # pass 2
        assert app.radio(key="time_scope").disabled is True  # a tournament is displayed
        app.run()  # finalise
        assert LIVE_RUN_KEY not in app.session_state
        app.segmented_control(key="run.mode").set_value("evolution")
        app.run()
        assert not app.exception
        assert app.radio(key="time_scope").disabled is True

    def test_tournament_advances_by_cycle(self, one_pass_per_run: list[dict[str, object]]) -> None:
        """(viii) One cycle per pass, then the cycles-elapsed message."""
        app = _fresh_app()
        _prepare_tiny_tournament(app, cycles=3)
        app.button(key="run_button").click()
        app.run()
        assert "cycle 1 finished" in _captions(app)
        app.run()
        assert "cycle 2 finished" in _captions(app)
        app.run()
        assert "cycle 3 finished" in _captions(app)
        assert app.session_state[LIVE_RUN_KEY].periods == 3
        app.run()
        assert not app.exception
        assert LIVE_RUN_KEY not in app.session_state
        assert "3 cycles" in app.success[0].value
        assert app.session_state["last_run"]["timeseries"].mode == "tournament"


PAINTER_DRAFT_KEY = "_layout_draft"
"""The app's session-state key for the Layout painter's draft (M11b Phase E4)."""

PAINTER_WIDGET_KEYS = {
    "number_input": ("painter_rows", "painter_cols"),
    "button": (
        "painter_new",
        "painter_load",
        "painter_from_preview",
        "painter_undo",
        "painter_fill",
        "painter_clear",
        "painter_save",
        "painter_delete",
        "painter_handoff",
    ),
    "selectbox": ("painter_source",),
    "radio": ("painter_tool", "painter_brush"),
    "text_input": ("painter_file_name",),
    "checkbox": ("painter_replace", "painter_confirm_delete"),
}
"""Every painter widget that renders on EVERY pass, by AppTest accessor.

"Resize grid" (`painter_resize`) is conditional — it appears only while the
Rows / Columns boxes differ from the grid on the canvas — and the canvas
itself is a plotly element AppTest models only as an unknown element.
"""


@pytest.fixture
def painter_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the app at a per-test runs folder AND a per-test templates folder.

    ``PDSIM_RUNS_DIR`` is the browser tests' idiom; the templates folder is
    redirected by patching ``pdsim.core.layouts.GRID_TEMPLATES_DIR`` — every
    painter path, the config validator, and the recorder read that attribute
    at call time, so the redirect holds inside AppTest's in-process script
    run. The three protected examples are copied in.

    Args:
        tmp_path: pytest's per-test directory.
        monkeypatch: pytest's patcher.

    Returns:
        The redirected templates folder.
    """
    monkeypatch.setenv("PDSIM_RUNS_DIR", str(tmp_path / "runs"))
    templates = tmp_path / "templates"
    templates.mkdir()
    for name in painter_helpers.SHIPPED_TEMPLATES:
        shutil.copy(Path("grid_templates") / name, templates / name)
    monkeypatch.setattr(layouts, "GRID_TEMPLATES_DIR", templates)
    return templates


def _painter_metric(app: AppTest, label: str) -> str | None:
    """A painter readout's value, or ``None`` when it is not rendered.

    Args:
        app: The AppTest handle after a script run.
        label: The metric label ("Sites", "Painted agents", ...).

    Returns:
        The metric's body text.
    """
    values = [item.value for item in app.metric if item.label == label]
    assert len(values) <= 1, label
    return values[0] if values else None


def _canvases(app: AppTest) -> list[object]:
    """The painter canvas elements currently rendered (zero or one).

    AppTest models a plotly chart as an unknown element carrying the
    PlotlyChart proto; the canvas is told apart from the app's other charts
    by its user key, which Streamlit folds into the element id.

    Args:
        app: The AppTest handle after a script run.

    Returns:
        The matching elements.
    """
    return [element for element in app.get("plotly_chart") if "painter_canvas" in element.proto.id]


def _canvas_spec(app: AppTest) -> dict[str, object]:
    """The one canvas's figure spec as a dictionary.

    Args:
        app: The AppTest handle after a script run.

    Returns:
        The parsed plotly JSON spec.
    """
    canvases = _canvases(app)
    assert len(canvases) == 1
    return json.loads(canvases[0].proto.spec)  # type: ignore[attr-defined]


def _new_grid(app: AppTest, rows: int, cols: int) -> None:
    """Press "New blank grid" at the given size.

    Args:
        app: The AppTest handle after a script run.
        rows: The "Rows" value to set.
        cols: The "Columns" value to set.
    """
    app.number_input(key="painter_rows").set_value(rows)
    app.number_input(key="painter_cols").set_value(cols)
    app.button(key="painter_new").click()
    app.run()
    assert not app.exception


def _load_template(app: AppTest, name: str) -> None:
    """Choose a file under "Existing layout file" and press "Load into painter".

    Args:
        app: The AppTest handle after a script run.
        name: The bare file name to load.
    """
    app.selectbox(key="painter_source").select(name)
    app.run()
    app.button(key="painter_load").click()
    app.run()
    assert not app.exception


def _save_as(app: AppTest, name: str, replace: bool = False) -> None:
    """Type a name, set the replace box, press "Save layout".

    Args:
        app: The AppTest handle after a script run.
        name: The "Layout file name" text.
        replace: The "Replace the existing file" checkbox value.
    """
    app.text_input(key="painter_file_name").set_value(name)
    app.checkbox(key="painter_replace").set_value(replace)
    app.run()
    app.button(key="painter_save").click()
    app.run()
    assert not app.exception


class TestLayoutPainter:
    """The Layout painter tab (M11b Phase E4; DECISIONS #186 rulings, #187 build).

    Every pin drives the painter through its BUTTONS (#186 R12): the mouse
    stroke itself is owner-validated, its translation to cells is pinned in
    ``test_painter_helpers.py``. Where a test needs a painted cell without a
    stroke, it paints the session-state draft through the same pure
    ``apply_brush`` the stroke callback calls. Pin (x) — that factoring the
    lookahead out of the panel changed nothing — is the panel's existing
    suite, which runs unchanged.
    """

    def test_cold_start_renders_the_tab_with_every_widget(self, painter_env: Path) -> None:
        """(i) The four tabs in OC1's order; every painter widget by key; no canvas yet."""
        app = _fresh_app()
        assert not app.exception
        assert [tab.label for tab in app.tabs] == [
            "Run lab",
            "Layout painter",
            "Results browser",
            "Sweep",
        ]
        for accessor, keys in PAINTER_WIDGET_KEYS.items():
            for key in keys:
                assert getattr(app, accessor)(key=key) is not None, key
        assert app.number_input(key="painter_rows").value == 10
        assert app.number_input(key="painter_cols").value == 10
        assert app.selectbox(key="painter_source").options == sorted(
            painter_helpers.SHIPPED_TEMPLATES
        )
        assert app.radio(key="painter_brush").options == painter_helpers.brush_options()
        assert app.radio(key="painter_tool").options == list(painter_helpers.TOOL_OPTIONS)
        assert app.radio(key="painter_tool").value == painter_helpers.TOOL_DRAW
        # Without a grid the editing controls are greyed, never hidden.
        for key in ("painter_fill", "painter_clear", "painter_undo", "painter_save"):
            assert app.button(key=key).disabled is True, key
        assert app.button(key="painter_handoff").disabled is True
        assert app.button(key="painter_new").disabled is False
        with pytest.raises(KeyError):
            app.button(key="painter_resize")
        assert _canvases(app) == []
        assert PAINTER_DRAFT_KEY not in app.session_state

    def test_new_blank_grid_readouts_canvas_and_unsaved_handoff(self, painter_env: Path) -> None:
        """(ii) 6 x 8: Sites 48, Painted agents 0; canvas sized to the grid; hand-off greyed."""
        app = _fresh_app()
        _new_grid(app, 6, 8)
        assert _painter_metric(app, "Sites") == "48"
        assert _painter_metric(app, "Painted agents") == "0"
        assert _painter_metric(app, "Empty cells") == "48"
        assert _painter_metric(app, "Saved as") == "not saved yet"
        assert app.button(key="painter_handoff").disabled is True
        assert any("Save the layout first" in text for text in _captions(app))
        spec = _canvas_spec(app)
        layout = spec["layout"]
        assert layout["dragmode"] == "lasso"  # type: ignore[index]  # the Draw tool (#188)
        assert (layout["width"], layout["height"]) == (640, 580)  # type: ignore[index]
        assert len(spec["data"][0]["x"]) == 48  # type: ignore[index]
        # Changing a box never resizes implicitly: the "Resize grid" button appears.
        app.number_input(key="painter_rows").set_value(7)
        app.run()
        assert _painter_metric(app, "Sites") == "48"
        assert any("Resize grid" in text for text in _captions(app))
        app.button(key="painter_resize").click()
        app.run()
        assert not app.exception
        assert _painter_metric(app, "Sites") == "56"
        with pytest.raises(KeyError):
            app.button(key="painter_resize")

    def test_tool_radio_sets_the_canvas_drag_mode(self, painter_env: Path) -> None:
        """(#188) Draw and Lasso put the canvas in lasso mode, Rectangle in box mode.

        The drag mode lives in the figure's own layout, so it survives the
        canvas remount after every stroke; the cached figure carries it.
        """
        app = _fresh_app()
        _new_grid(app, 6, 8)
        assert _canvas_spec(app)["layout"]["dragmode"] == "lasso"  # type: ignore[index]
        app.radio(key="painter_tool").set_value(painter_helpers.TOOL_RECTANGLE)
        app.run()
        assert not app.exception
        assert _canvas_spec(app)["layout"]["dragmode"] == "select"  # type: ignore[index]
        app.radio(key="painter_tool").set_value(painter_helpers.TOOL_LASSO)
        app.run()
        assert _canvas_spec(app)["layout"]["dragmode"] == "lasso"  # type: ignore[index]
        app.radio(key="painter_tool").set_value(painter_helpers.TOOL_DRAW)
        app.run()
        assert _canvas_spec(app)["layout"]["dragmode"] == "lasso"  # type: ignore[index]

    def test_load_into_painter_reads_the_island(self, painter_env: Path) -> None:
        """(iii) example_island.txt: 24 painted, the counts caption, the boxes follow."""
        app = _fresh_app()
        _load_template(app, "example_island.txt")
        assert _painter_metric(app, "Painted agents") == "24"
        assert _painter_metric(app, "Sites") == "24"
        assert any("Always Defect 18, Tit for Tat 6" in text for text in _captions(app))
        assert app.number_input(key="painter_rows").value == 4
        assert app.number_input(key="painter_cols").value == 6
        # A loaded file IS saved and unchanged, so a shipped example hands off as it is.
        assert _painter_metric(app, "Saved as") == "example_island.txt"
        assert app.button(key="painter_handoff").disabled is False

    def test_fill_clear_undo(self, painter_env: Path) -> None:
        """(iv) Fill all 48, Clear all 0, Undo last stroke 48; one level only."""
        app = _fresh_app()
        _new_grid(app, 6, 8)
        assert app.button(key="painter_undo").disabled is True
        app.radio(key="painter_brush").set_value("Tit for Tat")
        app.run()
        app.button(key="painter_fill").click()
        app.run()
        assert _painter_metric(app, "Painted agents") == "48"
        assert _painter_metric(app, "Saved as") == "unsaved changes"
        assert any("Tit for Tat 48" in text for text in _captions(app))
        app.button(key="painter_clear").click()
        app.run()
        assert _painter_metric(app, "Painted agents") == "0"
        app.button(key="painter_undo").click()
        app.run()
        assert not app.exception
        assert _painter_metric(app, "Painted agents") == "48"
        assert app.button(key="painter_undo").disabled is True  # the one level is spent

    def test_save_refusals_and_acceptance(self, painter_env: Path) -> None:
        """(v) Blank, protected, and existing-without-replace refused; the text byte-exact."""
        app = _fresh_app()
        _load_template(app, "example_island.txt")
        _save_as(app, "")
        assert any("Give the layout a file name" in item.value for item in app.error)
        for shipped in painter_helpers.SHIPPED_TEMPLATES:
            _save_as(app, shipped, replace=True)
            assert any("shipped examples" in item.value for item in app.error), shipped
            assert not app.success
        _save_as(app, "island_copy")
        assert not app.error
        assert any("island_copy.txt" in item.value for item in app.success)
        path = painter_env / "island_copy.txt"
        assert path.is_file()
        draft = app.session_state[PAINTER_DRAFT_KEY]
        expected = format_layout_file(painter_helpers.draft_layout_file(draft), comment=True)
        assert path.read_bytes() == expected.encode("utf-8")
        assert _painter_metric(app, "Saved as") == "island_copy.txt"
        app.run()  # the file list renders before the save row, so it catches up next pass
        assert "island_copy.txt" in app.selectbox(key="painter_source").options
        _save_as(app, "island_copy")
        assert any("already exists" in item.value for item in app.error)
        _save_as(app, "island_copy", replace=True)
        assert not app.error
        assert any("island_copy.txt" in item.value for item in app.success)

    def test_handoff_fills_the_run_lab(self, painter_env: Path) -> None:
        """(vi) The island saved as island_copy.txt hands off every panel key."""
        app = _fresh_app()
        assert app.session_state["run.mode"] == "tournament"  # the cold-start scenario
        _load_template(app, "example_island.txt")
        _save_as(app, "island_copy")
        app.button(key="painter_handoff").click()
        app.run()
        assert not app.exception
        assert app.session_state["run.mode"] == "evolution"
        assert app.selectbox(key="structure.kind").value == "lattice"
        assert app.checkbox(key="structure.rows#limit").value is True
        assert app.number_input(key="structure.rows#value").value == 4
        assert app.checkbox(key="structure.cols#limit").value is True
        assert app.number_input(key="structure.cols#value").value == 6
        assert app.selectbox(key="structure.initial_layout").value == "from_file"
        assert app.text_input(key="structure.layout_file").value == "island_copy.txt"
        assert app.number_input(key="population.size").value == 24
        assert app.number_input(key="composition.always_defect").value == 18
        assert app.number_input(key="composition.tit_for_tat").value == 6
        assert "Population mix OK: 24 agents." in _captions(app)
        assert [item.value for item in app.metric if item.label == "Occupied"] == ["24 (100%)"]
        assert any("island_copy.txt" in item.value for item in app.success)  # the load note

    def test_a_one_agent_draft_saves_but_cannot_hand_off(self, painter_env: Path) -> None:
        """(vi-b) Amendment (d): saving is allowed; the hand-off stays greyed with its reason."""
        app = _fresh_app()
        _new_grid(app, 4, 6)
        # One cell, through the same pure function the stroke callback calls.
        painter_helpers.apply_brush(app.session_state[PAINTER_DRAFT_KEY], [0], "tit_for_tat")
        app.run()
        assert _painter_metric(app, "Painted agents") == "1"
        panel_keys = ("run.mode", "structure.kind", "structure.initial_layout", "population.size")
        panel_before = {key: app.session_state[key] for key in panel_keys}
        _save_as(app, "lonely")
        assert not app.error
        assert (painter_env / "lonely.txt").is_file()
        assert _painter_metric(app, "Saved as") == "lonely.txt"
        assert app.button(key="painter_handoff").disabled is True
        assert any("at least two agents" in text for text in _captions(app))
        panel_after = {key: app.session_state[key] for key in panel_keys}
        assert panel_after == panel_before

    def test_validation_pin_recorded_layout_and_cli_rerun(
        self, painter_env: Path, tmp_path: Path
    ) -> None:
        """(vii) Hand off, record a run: layout.txt is the saved text; the CLI re-run is identical.

        The spec's V5 chain for E4. The recorded copy is compared after
        normalising line endings: the recorder writes its copy with
        ``Path.write_text``, which on Windows translates LF to CRLF — a
        pre-existing io-layer behaviour reported in #187, not changed here
        (the parser reads both identically, so the re-run is unaffected).
        """
        app = _fresh_app()
        _load_template(app, "example_island.txt")
        _save_as(app, "island_copy")
        saved = (painter_env / "island_copy.txt").read_bytes()
        app.button(key="painter_handoff").click()
        app.run()
        app.number_input(key="dynamics.generations").set_value(2)
        app.number_input(key="match.rounds_per_match").set_value(5)
        app.slider(key="playback_delay").set_value(0.0)
        app.checkbox(key="record_run").set_value(True)
        app.run()
        assert not app.exception
        app.button(key="run_button").click()
        app.run()  # the one run() follows the pass chain to the end (#184(e))
        assert not app.exception
        assert any("2 generations" in item.value for item in app.success)
        runs_dir = tmp_path / "runs"
        cards = list_runs(runs_dir)
        assert len(cards) == 1
        folder = runs_dir / str(cards[0]["run_id"])
        recorded = (folder / "layout.txt").read_bytes().replace(b"\r\n", b"\n")
        assert recorded == saved
        # The recorded config names the local copy by its bare name; loading
        # it back resolves that name beside the config (the #122 rule), so
        # the raw YAML is what carries "layout.txt".
        recorded_config = yaml.safe_load((folder / "config.yaml").read_text(encoding="utf-8"))
        assert recorded_config["structure"]["layout_file"] == "layout.txt"
        loaded = load_run(folder)
        assert Path(str(loaded.config.structure.layout_file)) == folder / "layout.txt"
        assert loaded.config.structure.initial_layout == "from_file"
        assert (loaded.config.structure.rows, loaded.config.structure.cols) == (4, 6)
        cli_out = str(tmp_path / "cli")
        assert cli_main([str(folder / "config.yaml"), "--out", cli_out, "--quiet"]) == 0
        cli_folders = [p for p in (tmp_path / "cli").iterdir() if p.is_dir()]
        assert len(cli_folders) == 1
        for name in ("timeseries.parquet", "cooperation.parquet"):
            pd.testing.assert_frame_equal(
                pd.read_parquet(folder / name), pd.read_parquet(cli_folders[0] / name)
            )

    def test_start_from_the_run_labs_founding_preview(self, painter_env: Path) -> None:
        """(viii) The clusters scenario seeds a 20 x 20 draft; the tournament tab refuses."""
        app = _fresh_app()
        app.selectbox(key="scenario_choice").select("Cooperation Survives in Clusters")
        app.run()
        app.button(key="painter_from_preview").click()
        app.run()
        assert not app.exception
        draft = app.session_state[PAINTER_DRAFT_KEY]
        assert (draft.rows, draft.cols) == (20, 20)
        counts = painter_helpers.draft_layout_file(draft).strategy_counts()
        assert counts == {"always_cooperate": 100, "always_defect": 100}
        assert app.number_input(key="painter_rows").value == 20
        assert app.number_input(key="painter_cols").value == 20
        assert _painter_metric(app, "Painted agents") == "200"
        assert len(_canvases(app)) == 1
        assert not app.warning
        # The converse on a fresh session: the cold start is the tournament.
        app = _fresh_app()
        assert app.session_state["run.mode"] == "tournament"
        app.button(key="painter_from_preview").click()
        app.run()
        assert not app.exception
        assert any("no founding preview" in item.value for item in app.warning)
        assert PAINTER_DRAFT_KEY not in app.session_state
        assert _canvases(app) == []

    def test_a_grid_too_fine_to_paint_shows_the_sentence_and_no_canvas(
        self, painter_env: Path
    ) -> None:
        """(ix) 200 x 10 is the pixel-array regime: the R3 sentence replaces the canvas."""
        app = _fresh_app()
        _new_grid(app, 200, 10)
        assert any("too fine to paint" in item.value for item in app.info)
        assert _canvases(app) == []
        assert _painter_metric(app, "Sites") == "2000"  # the readouts still render

    def test_delete_refused_unticked_and_for_a_protected_example(self, painter_env: Path) -> None:
        """#189 R1: the button is greyed until the box is ticked; a shipped example is refused."""
        app = _fresh_app()
        assert app.button(key="painter_delete").disabled is True
        assert app.checkbox(key="painter_confirm_delete").value is False
        app.checkbox(key="painter_confirm_delete").set_value(True)
        app.run()
        assert app.button(key="painter_delete").disabled is False
        app.selectbox(key="painter_source").select("example_island.txt")
        app.run()
        app.button(key="painter_delete").click()
        app.run()
        assert not app.exception
        assert any("shipped examples" in item.value for item in app.error)
        assert not app.success
        assert (painter_env / "example_island.txt").is_file()
        assert "example_island.txt" in app.selectbox(key="painter_source").options
        assert app.checkbox(key="painter_confirm_delete").value is True  # a refusal keeps the box

    def test_delete_accepted_for_a_saved_painting(self, painter_env: Path) -> None:
        """#189 R1: the file goes; the painting stays, unsaved again; the hand-off greys."""
        app = _fresh_app()
        _new_grid(app, 4, 6)
        painter_helpers.apply_brush(app.session_state[PAINTER_DRAFT_KEY], [0, 1, 2], "tit_for_tat")
        app.run()
        _save_as(app, "delete_me")
        assert (painter_env / "delete_me.txt").is_file()
        assert app.button(key="painter_handoff").disabled is False
        app.run()  # the file list catches up with the save
        app.selectbox(key="painter_source").select("delete_me.txt")
        app.checkbox(key="painter_confirm_delete").set_value(True)
        app.run()
        app.button(key="painter_delete").click()
        app.run()
        assert not app.exception
        assert not app.error
        assert any(
            "Deleted" in item.value and "delete_me.txt" in item.value for item in app.success
        )
        assert not (painter_env / "delete_me.txt").exists()
        draft = app.session_state[PAINTER_DRAFT_KEY]
        assert painter_helpers.draft_layout_file(draft).occupied_count == 3
        assert draft.saved_as is None
        assert len(_canvases(app)) == 1
        assert _painter_metric(app, "Painted agents") == "3"
        assert _painter_metric(app, "Saved as") == "not saved yet"
        assert app.button(key="painter_handoff").disabled is True
        assert any(text.startswith("Save the layout first") for text in _captions(app))
        assert app.checkbox(key="painter_confirm_delete").value is False  # unticked on that pass
        app.run()  # the list catches up; the stale choice resets without an exception
        assert not app.exception
        assert app.button(key="painter_delete").disabled is True
        source = app.selectbox(key="painter_source")
        assert "delete_me.txt" not in source.options
        assert source.value in source.options
