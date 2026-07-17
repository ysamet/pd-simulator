"""Tests for the Streamlit-free Economy panel arithmetic (M10a Task 10)."""

from __future__ import annotations

import pytest

from pdsim.config.experiment import ExperimentConfig
from pdsim.config.scenarios import get_scenario_info
from pdsim.ui.economy_helpers import (
    ECONOMY_HELP,
    calibration_report,
    chart_carrying_capacity,
)


def _economy_config(**overrides: object) -> ExperimentConfig:
    """Build the growth-economy scenario config with dynamics overrides.

    Args:
        **overrides: Dynamics field values to override.

    Returns:
        A validated economy config.
    """
    data = get_scenario_info("the_growth_economy").config.model_dump(mode="json")
    data["dynamics"].update(overrides)
    return ExperimentConfig.model_validate(data)


class TestScenarioCalibration:
    """The spec's worked arithmetic for The Growth Economy, exactly."""

    def test_the_worked_numbers(self) -> None:
        """2k = 10 matches, all-C 300, all-D 100, L = 200 inside the window."""
        report = calibration_report(get_scenario_info("the_growth_economy").config)
        assert report.matcher == "random_k"
        assert report.expected_matches == 10.0
        assert report.expected_rounds_per_match == 10.0
        assert report.all_c_income == 300.0
        assert report.all_d_income == 100.0
        assert report.total_cost == 200.0
        assert report.cooperator_net == pytest.approx(100.0)
        assert report.defector_net == pytest.approx(-100.0)
        assert report.window_verdict == "inside"
        assert report.escape_velocity is None
        assert report.senescence_factor is None
        # random_k + unlimited memory: the SOFT memory note, naming the bound.
        assert report.memory_note is not None
        assert "memory depth" in report.memory_note
        assert "stays put" in report.regime_note

    def test_cost_above_the_window(self) -> None:
        """L = 320 > all-C income: the verdict flips (validation step 2)."""
        report = calibration_report(_economy_config(basic_living_cost=320.0))
        assert report.window_verdict == "above"
        assert report.cooperator_net == pytest.approx(-20.0)

    def test_cost_below_the_window(self) -> None:
        """L = 80 < all-D income: even defectors profit."""
        report = calibration_report(_economy_config(basic_living_cost=80.0))
        assert report.window_verdict == "below"
        assert report.defector_net == pytest.approx(20.0)

    def test_engagement_cost_enters_the_total(self) -> None:
        """The bill is L + engagement × matches."""
        report = calibration_report(_economy_config(engagement_cost=5.0))
        assert report.total_cost == pytest.approx(200.0 + 5.0 * 10)

    def test_escape_velocity_appears_with_capital_returns(self) -> None:
        """e* = total cost / r (validation step 6: 200 / 0.05 = 4000)."""
        report = calibration_report(_economy_config(capital_return_rate=0.05))
        assert report.escape_velocity == pytest.approx(4000.0)

    def test_mortality_readouts(self) -> None:
        """Validation step 5: resolved factor ≈ 1.2589 plus the age lines.

        The scenario dump carries the RESOLVED factor (1.0), so auto has to
        be requested explicitly — None in the raw input means auto.
        """
        report = calibration_report(
            _economy_config(base_hazard=0.01, max_age=20, senescence_factor=None)
        )
        assert report.senescence_factor == pytest.approx(1.2589, abs=1e-4)
        assert report.effective_max_age == pytest.approx(20.0)
        assert report.effective_max_age_note is None  # auto meets the cap exactly
        # (θ − e0) / net = (500 − 400) / 100 = 1 generation to θ; then one
        # child every σ/net = 4 generations: 1 + (20 − 1) // 4 = 5 children.
        assert report.generations_to_threshold == pytest.approx(1.0)
        assert report.expected_offspring == pytest.approx(5.0)

    def test_explicit_steep_senescence_gets_the_soft_note(self) -> None:
        """Factor 1.6 drops the effective max age to ≈ 9.8 — warn, don't forbid."""
        report = calibration_report(
            _economy_config(base_hazard=0.01, max_age=20, senescence_factor=1.6)
        )
        assert report.effective_max_age == pytest.approx(9.8, abs=0.1)
        assert report.effective_max_age_note is not None
        assert "below" in report.effective_max_age_note

    def test_round_robin_regime(self) -> None:
        """N − 1 matches, the moving-window warning, and the hard memory note."""
        data = get_scenario_info("the_growth_economy").config.model_dump(mode="json")
        data["matching"] = {"matcher": "round_robin", "opponents_per_agent": 5}
        report = calibration_report(ExperimentConfig.model_validate(data))
        assert report.expected_matches == 39.0  # N − 1 at N = 40
        assert "MOVES" in report.regime_note
        # Worst-case history length is named: 10 rounds × 60 generations.
        assert report.memory_note is not None
        assert "600" in report.memory_note

    def test_memory_note_disappears_with_a_depth_bound(self) -> None:
        """Setting memory_depth silences the note — the bound exists."""
        data = get_scenario_info("the_growth_economy").config.model_dump(mode="json")
        data["population"]["memory_depth"] = 10
        report = calibration_report(ExperimentConfig.model_validate(data))
        assert report.memory_note is None

    def test_continuation_mode_uses_expected_length(self) -> None:
        """Expected rounds per match = 1 / (1 − w)."""
        data = get_scenario_info("the_growth_economy").config.model_dump(mode="json")
        data["match"] = {"length_mode": "continuation", "continuation_probability": 0.9}
        report = calibration_report(ExperimentConfig.model_validate(data))
        assert report.expected_rounds_per_match == pytest.approx(10.0)


class TestChartCarryingCapacity:
    """The K line is config-derived and economy-only."""

    def test_economy_run_gets_the_line(self) -> None:
        """An energy-economy evolution run draws K."""
        assert chart_carrying_capacity(get_scenario_info("the_growth_economy").config) == 200.0

    def test_imitation_run_gets_none(self) -> None:
        """K is ignored under imitation — no line."""
        assert chart_carrying_capacity(get_scenario_info("reciprocity_takes_over").config) is None


class TestEconomyHelp:
    """The single-source (?) texts exist and are novice-grade prose."""

    def test_every_concept_and_readout_is_covered(self) -> None:
        """The spec's checklist keys are all present."""
        assert set(ECONOMY_HELP) >= {
            "energy",
            "admission",
            "estate_destruction",
            "passport_id",
            "expected_matches",
            "income",
            "window",
            "escape_velocity",
            "generations_to_threshold",
            "effective_max_age",
        }

    def test_texts_are_real_prose(self) -> None:
        """Each explainer is a sentence, not a stub."""
        for key, text in ECONOMY_HELP.items():
            assert len(text.split()) >= 10, f"ECONOMY_HELP[{key!r}] too thin"
