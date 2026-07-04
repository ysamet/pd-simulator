"""Smoke tests for the Streamlit app via ``streamlit.testing.v1.AppTest``.

AppTest executes ``pdsim/ui/app.py`` headlessly, so these tests cover what a
browser session would exercise: the app renders without exceptions, every
scenario loads its config into the panel, and a tiny custom run completes
end to end (the live loop runs synchronously inside AppTest). Deeper logic
lives in the plain helpers and is tested without Streamlit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from pdsim.config.scenarios import all_scenarios
from pdsim.core.strategies import all_strategies

APP_PATH = str(Path(__file__).resolve().parents[1] / "ui" / "app.py")


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
        app.run()
        assert not app.exception
        app.button(key="run_button").click()
        app.run()
        assert not app.exception
        assert len(app.success) == 1
        assert "2 generations" in app.success[0].value
