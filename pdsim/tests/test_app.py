"""Smoke tests for the Streamlit app via ``streamlit.testing.v1.AppTest``.

AppTest executes ``pdsim/ui/app.py`` headlessly, so these tests cover what a
browser session would exercise: the app renders without exceptions, every
scenario loads its config into the panel, and a tiny custom run completes
end to end (the live loop runs synchronously inside AppTest). Deeper logic
lives in the plain helpers and is tested without Streamlit.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from pdsim.config.experiment import ExperimentConfig
from pdsim.config.scenarios import all_scenarios
from pdsim.core import engine
from pdsim.core.strategies import all_strategies
from pdsim.io.results import RunRecorder, list_runs

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
        """4 agents, 2 generations, 5-round matches: success + summary."""
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
        from collections.abc import Iterator

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
