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
    economy_inactive_summary,
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
        """spatial_reciprocity: k = 5 clamps to 4, so 8 matches, window 0 < L < 24."""
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

    def test_async_context_uses_the_spatial_branch(self) -> None:
        """The #154 pin RETIRED WITH THIS REPLACEMENT (#120(f); M11b Phase D).

        Retired: ``test_async_context_keeps_its_current_behaviour`` pinned
        the async context to the pre-#154 aspatial report (round_robin's
        N − 1 = 99 on donation_game_threshold) so the spatial branch could
        not silently extend without a design ruling. The ruling came
        (#169) and its measurement gate PASSED (#176/#177: asynchronous
        fixed_n spatial runs play EXACTLY 2 × min(k, degree) matches per
        agent per generation-equivalent as the population mean, every
        window), so the branch now extends to the asynchronous clock and
        this replacement pins the NEW behaviour: the spatial branch
        active, 8 matches (2 × min(4, 4)), ``CalibrationReport.spatial``
        True.
        """
        report = calibration_report(get_scenario_info("donation_game_threshold").config)
        assert report.spatial is True
        assert report.expected_matches == 8.0  # 2 × min(k = 4, degree 4)
        assert SPATIAL_FINE_PRINT in report.regime_note

    def test_async_regime_note_marked_expected_where_sync_is_exact(self) -> None:
        """#169's fine-print clause: the async figure is EXPECTED, sync exact.

        The (?) and the caption may never contradict the number (#154's
        rule): the async caption carries the expected qualifier; the
        synchronous caption stays the pre-Phase-D text without it.
        """
        async_report = calibration_report(get_scenario_info("donation_game_threshold").config)
        assert "EXPECTED figure per generation-equivalent" in async_report.regime_note
        sync_report = calibration_report(get_scenario_info("spatial_reciprocity").config)
        assert "EXPECTED figure" not in sync_report.regime_note
        # The help text behind the (?) carries the same clause (#154's rule).
        assert "asynchronous clock" in ECONOMY_HELP["expected_matches"]

    def test_async_forces_per_initiator_for_a_stranded_per_pair(self) -> None:
        """#176 R3, pinned both ways: async 2× regardless of the stranded knob.

        The async loop never deduplicates (#175(a)), so a stranded
        ``per_pair`` widget value must not reach the arithmetic — the
        report shows 2 × min(k, degree) = 8, not 4 — while the synchronous
        control genuinely halves to 1× under the same knob.
        """
        data = get_scenario_info("donation_game_threshold").config.model_dump(mode="json")
        data["matching"]["encounter_mode"] = "per_pair"
        stranded = calibration_report(ExperimentConfig.model_validate(data))
        assert stranded.spatial is True
        assert stranded.expected_matches == 8.0  # forced per_initiator: 2×
        assert "per_pair" not in stranded.regime_note
        # The synchronous control: the same knob genuinely halves (#174(a)).
        sync_data = get_scenario_info("spatial_reciprocity").config.model_dump(mode="json")
        sync_data["matching"]["encounter_mode"] = "per_pair"
        control = calibration_report(ExperimentConfig.model_validate(sync_data))
        assert control.expected_matches == 4.0  # 1 × min(k = 5, degree 4)
        assert "per_pair" in control.regime_note

    def test_async_memory_note_forces_per_initiator_too(self) -> None:
        """#176 R3's second clause: the #175(f3) memory note obeys the forcing.

        With a stranded ``per_pair`` under the asynchronous clock the note
        must keep the per-initiator wording (a pair meets twice), because
        the engine never deduplicates there; the synchronous control under
        the same knob says once.
        """
        data = get_scenario_info("donation_game_threshold").config.model_dump(mode="json")
        data["dynamics"]["reproduction_mode"] = "energy_economy"  # the note's gate
        data["matching"]["encounter_mode"] = "per_pair"
        report = calibration_report(ExperimentConfig.model_validate(data))
        assert report.memory_note is not None
        assert "twice" in report.memory_note
        sync_data = get_scenario_info("spatial_reciprocity").config.model_dump(mode="json")
        sync_data["matching"]["encounter_mode"] = "per_pair"
        control = calibration_report(ExperimentConfig.model_validate(sync_data))
        assert control.memory_note is not None
        assert "once" in control.memory_note

    def test_the_window_lower_bound_is_strict(self) -> None:
        """#176 R1: cost exactly at the all-D income sits BELOW the window.

        At L = all-D income a defector nets exactly zero and never
        starves — the boundary point defeats the filter, so the verdict
        must say "below", matching the strict printed window and advisory
        A1's inclusive trigger.
        """
        report = calibration_report(_economy_config(basic_living_cost=100.0))
        assert report.all_d_income == 100.0
        assert report.window_verdict == "below"
        assert report.defector_net == pytest.approx(0.0)

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


class TestEconomyInactiveSummary:
    """The collapsed panel's cause-naming summary (M11b Phase E1, #178 R9)."""

    def test_sync_imitation_cause(self) -> None:
        """Under the synchronous clock the inactive cause is imitation."""
        values = {
            "run.mode": "evolution",
            "dynamics.time_model": "synchronous",
            "dynamics.reproduction_mode": "imitation",
        }
        label, explanation = economy_inactive_summary(values)
        assert label == "Economy — inactive under imitation"
        assert "imitation" in explanation
        assert "energy_economy" in explanation

    def test_async_fixed_n_cause(self) -> None:
        """Under the asynchronous clock the inactive corner is fixed_n."""
        values = {
            "run.mode": "evolution",
            "dynamics.time_model": "asynchronous",
            "dynamics.async_population": "fixed_n",
        }
        label, explanation = economy_inactive_summary(values)
        assert label == "Economy — inactive under fixed_n (living cost not charged)"
        assert "variable_n" in explanation
