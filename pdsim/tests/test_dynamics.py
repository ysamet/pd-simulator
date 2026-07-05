"""Tests for the generation loop (``pdsim/core/dynamics.py``) — DESIGN §7.

Covers: initial-population construction (composition order, strategy_params,
memory depth), a fully hand-computed single generation, the generation-
boundary reset (DECISIONS #31), determinism under a fixed seed, and the
golden validation scenarios from DESIGN §7: reciprocity taking over a
TFT/AllD mix under selection, β = 0 behaving as neutral drift, and μ > 0
keeping every strategy recurring.

All stochastic scenarios run with fixed seeds and generous tolerances, so
every test is deterministic — a failure means behavior changed, not luck.
"""

from __future__ import annotations

import itertools

import numpy as np

from pdsim.config.experiment import ExperimentConfig
from pdsim.core.dynamics import (
    GenerationReport,
    PopulationDynamics,
    TournamentDynamics,
    build_initial_population,
)
from pdsim.core.match import MatchResult
from pdsim.core.strategies import strategy_name_of
from pdsim.core.strategies.random_strategy import Random


def _config(
    composition: dict[str, int],
    *,
    rounds: int = 3,
    beta: float = 1.0,
    mu: float = 0.0,
    generations: int = 5,
    memory_depth: int | None = None,
    strategy_params: dict[str, dict[str, float]] | None = None,
) -> ExperimentConfig:
    """Build an experiment config for dynamics tests.

    Args:
        composition: Initial strategy mix; population size is its sum.
        rounds: Fixed rounds per match.
        beta: Selection intensity β.
        mu: Mutation rate μ.
        generations: Number of generations to run.
        memory_depth: Optional per-opponent memory cap.
        strategy_params: Optional per-run parameter overrides.

    Returns:
        A validated config with noise off and fixed-length matches.
    """
    return ExperimentConfig.model_validate(
        {
            "population": {
                "size": sum(composition.values()),
                "composition": composition,
                "memory_depth": memory_depth,
            },
            "match": {"length_mode": "fixed", "rounds_per_match": rounds},
            "dynamics": {
                "selection_beta": beta,
                "mutation_rate": mu,
                "generations": generations,
            },
            "strategy_params": strategy_params or {},
        }
    )


class TestBuildInitialPopulation:
    """Generation 0 must come straight from the config."""

    def test_composition_order_and_ids(self) -> None:
        """Agents appear in composition declaration order, ids 0..N-1."""
        config = _config({"tit_for_tat": 2, "always_defect": 1})
        agents = build_initial_population(config)
        assert [agent.agent_id for agent in agents] == [0, 1, 2]
        names = [strategy_name_of(agent.strategy) for agent in agents]
        assert names == ["tit_for_tat", "tit_for_tat", "always_defect"]

    def test_same_strategy_agents_share_one_instance(self) -> None:
        """Stateless strategies are shared, not copied (DECISIONS #21/#25)."""
        config = _config({"tit_for_tat": 2, "always_defect": 1})
        agents = build_initial_population(config)
        assert agents[0].strategy is agents[1].strategy

    def test_strategy_params_reach_initial_strategies(self) -> None:
        """Per-run overrides (DECISIONS #30) apply from generation 0."""
        config = _config(
            {"random": 2},
            strategy_params={"random": {"cooperation_probability": 0.9}},
        )
        agents = build_initial_population(config)
        strategy = agents[0].strategy
        assert isinstance(strategy, Random)
        assert strategy.cooperation_probability == 0.9

    def test_memory_depth_reaches_agents(self) -> None:
        """The population's memory cap lands on every agent."""
        config = _config({"tit_for_tat": 2}, memory_depth=4)
        agents = build_initial_population(config)
        assert all(agent.memory_depth == 4 for agent in agents)


class TestSingleGeneration:
    """One fully hand-computed generation (TFT vs AllD, 3 rounds)."""

    def test_report_matches_hand_computed_scores(self) -> None:
        """TFT: S+P+P = 2; AllD: T+P+P = 7 (default payoffs)."""
        dynamics = PopulationDynamics(
            _config({"tit_for_tat": 1, "always_defect": 1}), np.random.default_rng(0)
        )
        report = dynamics.step()
        assert report == GenerationReport(
            index=0,
            composition={"tit_for_tat": 1, "always_defect": 1},
            mean_scores={"tit_for_tat": 2.0, "always_defect": 7.0},
            rounds_played={"tit_for_tat": 3, "always_defect": 3},
        )

    def test_generation_boundary_resets_scores_and_histories(self) -> None:
        """The reset boundary wipes scores and histories (DECISIONS #31).

        After a step, scores are 0 and no opponent is remembered —
        round_number restarts, cumulative within a generation only (#22).
        """
        dynamics = PopulationDynamics(
            _config({"tit_for_tat": 1, "always_defect": 1}), np.random.default_rng(0)
        )
        dynamics.step()
        agent_a, agent_b = dynamics.population
        assert agent_a.score == 0.0
        assert agent_b.score == 0.0
        assert agent_a.view_of(agent_b.agent_id).round_number == 0
        assert agent_b.view_of(agent_a.agent_id).round_number == 0

    def test_without_mutation_offspring_come_from_current_generation(self) -> None:
        """With μ = 0, selection only recombines existing strategies.

        Every next-generation strategy is one of the (shared)
        current-generation instances.
        """
        config = _config({"tit_for_tat": 2, "always_defect": 2})
        dynamics = PopulationDynamics(config, np.random.default_rng(1))
        originals = {id(agent.strategy) for agent in dynamics.population}
        dynamics.step()
        assert all(id(agent.strategy) in originals for agent in dynamics.population)


class TestRun:
    """The run() generator and reproducibility (hard rules 5 and 8)."""

    def test_run_yields_one_report_per_generation(self) -> None:
        """Exactly `generations` reports, indexed 0..G-1."""
        config = _config({"tit_for_tat": 1, "always_defect": 1}, generations=4)
        reports = list(PopulationDynamics(config, np.random.default_rng(0)).run())
        assert [report.index for report in reports] == [0, 1, 2, 3]

    def test_same_seed_reproduces_identical_runs(self) -> None:
        """Two runs with one config and seed must match report-for-report."""
        config = _config(
            {"tit_for_tat": 4, "always_defect": 4, "random": 2},
            beta=0.5,
            mu=0.1,
            generations=6,
        )
        run_1 = list(PopulationDynamics(config, np.random.default_rng(42)).run())
        run_2 = list(PopulationDynamics(config, np.random.default_rng(42)).run())
        assert run_1 == run_2


class TestGoldenScenarios:
    """The DESIGN §7 validation scenarios, seeded and tolerant."""

    def test_reciprocity_takes_over_a_tft_alld_mix(self) -> None:
        """The classic result: reciprocity beats defection under selection.

        With long matches and meaningful β, Tit for Tat outscores Always
        Defect in a mixed population and selection drives it to fixation.
        Generation-0 scores are exactly hand-computable (30-round matches,
        default payoffs): each TFT agent earns 9·90 + 10·29 = 1100; each
        AllD agent earns 10·34 + 9·30 = 610. ``memory_depth=1`` is set purely
        for speed — TFT and AllD read at most the last move, so behavior is
        identical to unlimited memory.
        """
        config = _config(
            {"tit_for_tat": 10, "always_defect": 10},
            rounds=30,
            beta=1.0,
            mu=0.0,
            generations=15,
            memory_depth=1,
        )
        reports = list(PopulationDynamics(config, np.random.default_rng(3)).run())
        assert reports[0].mean_scores == {"tit_for_tat": 1100.0, "always_defect": 610.0}
        assert reports[-1].composition == {"tit_for_tat": 20}

    def test_beta_zero_is_neutral_drift(self) -> None:
        """β = 0 is neutral drift: scores stop mattering (DESIGN §7).

        Always Defect outscores Always Cooperate every generation, yet its
        frequency only drifts (the run-long average stays near the initial
        50%). The contrast test below shows the same population under β = 5,
        where AllD's score advantage fixates it.
        """
        config = _config(
            {"always_cooperate": 10, "always_defect": 10},
            rounds=1,
            beta=0.0,
            mu=0.0,
            generations=30,
        )
        reports = list(PopulationDynamics(config, np.random.default_rng(5)).run())
        cooperate_counts = [report.composition.get("always_cooperate", 0) for report in reports]
        mean_count = sum(cooperate_counts) / len(cooperate_counts)
        assert 5.0 <= mean_count <= 15.0  # ~50% ± 25%: drifting, not driven
        assert cooperate_counts[0] == 10  # sanity: starts at the initial mix

    def test_beta_five_fixates_the_higher_scorer(self) -> None:
        """Contrast for the drift test: at β = 5 the higher scorer fixates.

        Same mix and seed as the drift test; AllD (the higher scorer
        against cooperators) takes over completely.
        """
        config = _config(
            {"always_cooperate": 10, "always_defect": 10},
            rounds=1,
            beta=5.0,
            mu=0.0,
            generations=30,
        )
        reports = list(PopulationDynamics(config, np.random.default_rng(5)).run())
        assert reports[-1].composition == {"always_defect": 20}

    def test_mutation_keeps_every_strategy_recurring(self) -> None:
        """With μ > 0 no strategy is permanently extinct (DESIGN §7).

        Starting from an all-AllD monoculture, every roster strategy (all
        seven) appears in the population at some point.
        """
        config = _config(
            {"always_defect": 12},
            rounds=1,
            beta=1.0,
            mu=0.3,
            generations=40,
        )
        reports = list(PopulationDynamics(config, np.random.default_rng(7)).run())
        seen = {name for report in reports for name in report.composition}
        assert seen == {
            "always_cooperate",
            "always_defect",
            "generous_tit_for_tat",
            "grim_trigger",
            "pavlov",
            "random",
            "tit_for_tat",
        }


def _tournament_config(
    composition: dict[str, int],
    *,
    rounds: int = 5,
    cycles: int = 3,
) -> ExperimentConfig:
    """Build a tournament-mode config for dynamics tests.

    Args:
        composition: The fixed cast; population size is its sum.
        rounds: Fixed rounds per match.
        cycles: Number of complete matcher passes.

    Returns:
        A validated tournament config with noise off.
    """
    return ExperimentConfig.model_validate(
        {
            "mode": "tournament",
            "tournament_cycles": cycles,
            "population": {"size": sum(composition.values()), "composition": composition},
            "match": {"length_mode": "fixed", "rounds_per_match": rounds},
        }
    )


class TestTournamentDynamics:
    """Tournament mode: one long generation, nothing evolves (DECISIONS #34)."""

    def test_composition_is_identical_at_every_cycle(self) -> None:
        """No selection, no mutation: the cast never changes."""
        config = _tournament_config({"tit_for_tat": 2, "always_defect": 2, "pavlov": 2}, cycles=4)
        reports = list(TournamentDynamics(config, np.random.default_rng(0)).run())
        assert len(reports) == 4
        expected = {"tit_for_tat": 2, "always_defect": 2, "pavlov": 2}
        assert all(report.composition == expected for report in reports)

    def test_cumulative_totals_never_decrease(self) -> None:
        """Scores accumulate for the whole run (non-negative payoffs)."""
        config = _tournament_config({"tit_for_tat": 2, "always_defect": 2, "random": 2}, cycles=5)
        reports = list(TournamentDynamics(config, np.random.default_rng(1)).run())
        # itertools.pairwise (new concept): successive overlapping pairs —
        # (r0, r1), (r1, r2), ... — exactly "each cycle vs the next".
        for earlier, later in itertools.pairwise(reports):
            for name, total in earlier.total_scores.items():
                assert later.total_scores[name] >= total

    def test_hand_computed_tft_vs_alld_totals(self) -> None:
        """Golden: cumulative totals follow the hand-worked arithmetic.

        Cycle 1 (fresh relationship, 5 rounds): TFT earns S+4P = 4, AllD
        earns T+4P = 9. TFT *remembers* the betrayal across the cycle
        boundary, so every later cycle is all-defection: +5P = +5 each.
        """
        config = _tournament_config({"tit_for_tat": 1, "always_defect": 1}, rounds=5, cycles=3)
        reports = list(TournamentDynamics(config, np.random.default_rng(0)).run())
        totals = [report.total_scores for report in reports]
        assert totals == [
            {"tit_for_tat": 4.0, "always_defect": 9.0},
            {"tit_for_tat": 9.0, "always_defect": 14.0},
            {"tit_for_tat": 14.0, "always_defect": 19.0},
        ]
        assert reports[-1].mean_scores == {"tit_for_tat": 14.0, "always_defect": 19.0}
        # Rounds played are cumulative like the scores (DECISIONS #44).
        assert [r.rounds_played["tit_for_tat"] for r in reports] == [5, 10, 15]

    def test_histories_accumulate_across_cycles(self) -> None:
        """The run is one long generation: round_number spans cycles (#34)."""
        config = _tournament_config({"tit_for_tat": 1, "always_defect": 1}, rounds=5, cycles=3)
        dynamics = TournamentDynamics(config, np.random.default_rng(0))
        dynamics.step()
        dynamics.step()
        agent_a, agent_b = dynamics.population
        assert agent_a.view_of(agent_b.agent_id).round_number == 10  # 2 cycles x 5 rounds
        assert agent_a.score > 0.0  # never reset

    def test_grim_stays_grim_about_a_cycle_one_betrayal(self) -> None:
        """Direct reciprocity across cycles: no generation-boundary amnesty.

        GrimTrigger faces Random; the seeded cycle-1 match contains at least
        one Random defection, so Grim must play pure defection for the
        whole of cycle 2 — the grudge survives the cycle boundary.
        """
        config = _tournament_config({"grim_trigger": 1, "random": 1}, rounds=4, cycles=2)
        dynamics = TournamentDynamics(config, np.random.default_rng(1))
        results: list[MatchResult] = []
        dynamics.step(on_match=results.append)
        dynamics.step(on_match=results.append)
        cycle_1, cycle_2 = results
        grim_id = 0  # composition order: grim_trigger first
        random_id = 1
        # Precondition for the scenario: Random betrayed at least once early.
        assert any(record.actions[random_id].value == "D" for record in cycle_1.rounds)
        assert all(record.actions[grim_id].value == "D" for record in cycle_2.rounds)
