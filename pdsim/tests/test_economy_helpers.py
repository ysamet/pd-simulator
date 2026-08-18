"""Tests for the Streamlit-free Economy panel arithmetic (M10a Task 10)."""

from __future__ import annotations

import pytest

from pdsim.config.experiment import ExperimentConfig
from pdsim.config.scenarios import get_scenario_info
from pdsim.ui.economy_helpers import (
    ECONOMY_HELP,
    SPATIAL_FINE_PRINT,
    blocked_parents_metric,
    blocked_parents_visible,
    calibration_report,
    chart_carrying_capacity,
    infeasible_parents_metric,
    infeasible_parents_visible,
    spatial_income_arithmetic,
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


def _spatial_arithmetic_for(scenario_name: str) -> object:
    """Run the #154 pure function on a shipped scenario's registry values.

    Args:
        scenario_name: The registered scenario whose configuration to use.

    Returns:
        The scenario's :class:`~pdsim.ui.economy_helpers.SpatialIncome`.
    """
    config = get_scenario_info(scenario_name).config
    return spatial_income_arithmetic(
        neighbourhood_shape=config.structure.neighbourhood_shape,
        boundary=config.structure.boundary,
        opponents_per_agent=config.matching.opponents_per_agent,
        length_mode=config.match.length_mode,
        rounds_per_match=config.match.rounds_per_match,
        continuation_probability=config.match.continuation_probability,
        payoff_reward=config.game.payoff_reward,
        payoff_punishment=config.game.payoff_punishment,
    )


class TestSpatialCalibration:
    """The #154 spatial branch: the gate, the worked numbers, the fine print."""

    def test_pure_function_flagship_numbers(self) -> None:
        """spatial_reciprocity: k = 5 clamps to 4, so 8 matches, window 0 ≤ L < 24."""
        arithmetic = _spatial_arithmetic_for("spatial_reciprocity")
        assert arithmetic.matches_per_agent == 8.0
        assert arithmetic.rounds_per_agent == 8.0  # one round per match
        assert arithmetic.all_c_income == 24.0
        assert arithmetic.all_d_income == 0.0
        assert (arithmetic.window_low, arithmetic.window_high) == (0.0, 24.0)

    def test_pure_function_filling_grid_numbers(self) -> None:
        """the_filling_grid: Moore play-all, 16 matches, all-D 160, all-C 480."""
        arithmetic = _spatial_arithmetic_for("the_filling_grid")
        assert arithmetic.matches_per_agent == 16.0
        assert arithmetic.rounds_per_agent == 160.0  # 16 matches × 10 rounds
        assert arithmetic.all_c_income == 480.0
        assert arithmetic.all_d_income == 160.0
        assert (arithmetic.window_low, arithmetic.window_high) == (160.0, 480.0)

    def test_flagship_report_uses_the_spatial_branch(self) -> None:
        """The report shows 8 matches and 0 ≤ cost < 24, not the matcher's 199."""
        report = calibration_report(get_scenario_info("spatial_reciprocity").config)
        assert report.spatial is True
        assert report.expected_matches == 8.0
        assert report.all_c_income == 24.0
        assert report.all_d_income == 0.0
        assert report.total_cost == 12.0  # L = 12, engagement free
        assert report.window_verdict == "inside"

    def test_filling_grid_report_uses_the_spatial_branch(self) -> None:
        """16 matches; L = 40 sits BELOW the saturated 160 ≤ cost < 480 window."""
        report = calibration_report(get_scenario_info("the_filling_grid").config)
        assert report.spatial is True
        assert report.expected_matches == 16.0
        assert report.all_c_income == 480.0
        assert report.all_d_income == 160.0
        assert report.window_verdict == "below"  # the scenario text's own point

    def test_drifting_frontier_stays_aspatial(self) -> None:
        """Spatial deliberately OFF: the random_k arithmetic is unchanged."""
        report = calibration_report(get_scenario_info("the_drifting_frontier").config)
        assert report.spatial is False
        assert report.expected_matches == 10.0
        assert report.all_c_income == 300.0
        assert report.all_d_income == 100.0
        assert report.total_cost == 200.0
        assert report.window_verdict == "inside"

    def test_stranded_toggle_under_well_mixed_uses_aspatial(self) -> None:
        """Toggle on without a lattice: the configured matcher IS consulted.

        The #137(e) validator forbids this state for a run, so it cannot be
        built through validation — but the widget layer strands exactly this
        combination (#141(c)/#142: a greyed checkbox keeps its value), and
        the gate must answer the aspatial branch for it. ``model_copy``
        deliberately skips re-validation, letting the test state the
        stranded combination directly.
        """
        flagship = get_scenario_info("spatial_reciprocity").config
        stranded = flagship.model_copy(
            update={"structure": flagship.structure.model_copy(update={"kind": "well_mixed"})}
        )
        report = calibration_report(stranded)
        assert report.spatial is False
        assert report.expected_matches == 199.0  # round_robin's N − 1 at N = 200

    def test_async_context_keeps_its_current_behaviour(self) -> None:
        """The #154 scope clause: no spatial branch under the async clock.

        The asynchronous per-generation-equivalent match count has not been
        measured (#139 measured the synchronous engine), so the async
        context keeps the pre-#154 report — the configured (greyed)
        matcher's arithmetic — until the design layer rules on a formula.
        This pin guards that the spatial branch does not silently extend.
        """
        report = calibration_report(get_scenario_info("donation_game_threshold").config)
        assert report.spatial is False
        assert report.expected_matches == 99.0  # round_robin's N − 1 at N = 100

    def test_fine_print_present_in_the_spatial_readout(self) -> None:
        """The single-source sentence rides the spatial regime note only."""
        assert "fully-occupied" in SPATIAL_FINE_PRINT
        spatial = calibration_report(get_scenario_info("spatial_reciprocity").config)
        assert SPATIAL_FINE_PRINT in spatial.regime_note
        aspatial = calibration_report(get_scenario_info("the_drifting_frontier").config)
        assert SPATIAL_FINE_PRINT not in aspatial.regime_note

    def test_memory_note_names_fixed_neighbours_on_the_spatial_branch(self) -> None:
        """The E4b audit fix: no matcher attribution while spatial is active.

        Pre-fix the note branched on the CONFIGURED matcher even while the
        matcher was greyed and unconsulted — a round_robin ghost got "every
        pair meets every generation", and the random_k wording ("recurs only
        occasionally") is the OPPOSITE of the lattice truth, where neighbours
        are fixed and an adjacent pair meets twice per generation (#139).
        The flagship (spatial, unlimited memory depth, greyed round_robin)
        must now get the fixed-neighbour wording with the 2× worst case:
        2 meetings × 1 round × 100 generations = 200 recorded moves.
        """
        report = calibration_report(get_scenario_info("spatial_reciprocity").config)
        assert report.memory_note is not None
        assert "neighbours are FIXED" in report.memory_note
        assert "200" in report.memory_note
        assert "round_robin" not in report.memory_note
        # And the aspatial branches keep their matcher-based wording.
        frontier = calibration_report(get_scenario_info("the_drifting_frontier").config)
        assert frontier.memory_note is not None
        assert "random_k" in frontier.memory_note


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
            "blocked_parents",
            "infeasible_parents",
        }

    def test_the_parent_readouts_are_clock_aware(self) -> None:
        """Both (?) texts say what each clock means (M11b Phase A, #171 ruling R1)."""
        blocked = ECONOMY_HELP["blocked_parents"].lower()
        infeasible = ECONOMY_HELP["infeasible_parents"].lower()
        assert "synchronous" in blocked and "asynchronous" in blocked
        assert "contest" in blocked
        assert "asynchronous" in infeasible and "does not apply" in infeasible
        assert "full grid" in infeasible  # ruling R2's saturation consequence

    def test_texts_are_real_prose(self) -> None:
        """Each explainer is a sentence, not a stub."""
        for key, text in ECONOMY_HELP.items():
            assert len(text.split()) >= 10, f"ECONOMY_HELP[{key!r}] too thin"


class TestParentReadoutVisibility:
    """Where the blocked and infeasible readouts apply (M11a Phase C; M11b Phase A)."""

    def _lattice(self, **dynamics: object) -> ExperimentConfig:
        """A 3x3 stripes lattice evolution config with the given dynamics."""
        return ExperimentConfig.model_validate(
            {
                "population": {
                    "size": 8,
                    "composition": {"always_cooperate": 4, "always_defect": 4},
                },
                "structure": {"kind": "lattice", "rows": 3, "cols": 3, "initial_layout": "stripes"},
                "dynamics": {"generations": 2, **dynamics},
            }
        )

    def test_sync_lattice_economy_shows_both(self) -> None:
        """The three-way gate: the feasibility filter runs, both readouts apply."""
        config = self._lattice(reproduction_mode="energy_economy", carrying_capacity=9)
        assert blocked_parents_visible(config)
        assert infeasible_parents_visible(config)

    def test_async_variable_n_shows_blocked_only(self) -> None:
        """Ruling R1: the async clock keeps its undivided blocked count."""
        config = self._lattice(
            time_model="asynchronous", async_population="variable_n", carrying_capacity=9
        )
        assert blocked_parents_visible(config)
        assert not infeasible_parents_visible(config)

    def test_well_mixed_and_imitation_show_neither(self) -> None:
        """Off the gate nothing can be blocked or infeasible."""
        well_mixed = ExperimentConfig.model_validate(
            {
                "population": {
                    "size": 8,
                    "composition": {"always_cooperate": 4, "always_defect": 4},
                },
                "dynamics": {"generations": 2, "reproduction_mode": "energy_economy"},
            }
        )
        imitation = self._lattice()
        for config in (well_mixed, imitation):
            assert not blocked_parents_visible(config)
            assert not infeasible_parents_visible(config)

    def test_the_metrics_read_latest_and_total(self) -> None:
        """Same shape for both: (latest period, run total); None before any period."""
        assert blocked_parents_metric([]) is None
        assert infeasible_parents_metric([]) is None
        assert blocked_parents_metric([0, 2, 1]) == (1, 3)
        assert infeasible_parents_metric([6, 8, 8]) == (8, 22)
