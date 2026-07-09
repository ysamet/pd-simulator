"""Tests for selection rules (``pdsim/core/selection.py``, DECISIONS #32/#63).

Covers: the Fermi rule's score-blindness at β = 0 and near-determinism at
large β, numerical stability at extreme β·Δscore, the documented per-slot
RNG draw orders, decision-style tests for the four M9a rules (proportional,
tournament_k, truncation, threshold_cloning) with hand-constructed score
vectors, and the ``build_selection_rule`` factory.

Statistical tests use fixed seeds and generous tolerances, so they are
deterministic — a failure means behavior changed, not bad luck.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pdsim.config.experiment import DynamicsConfig
from pdsim.core.selection import (
    FermiSelection,
    ProportionalSelection,
    SelectionRule,
    ThresholdCloningSelection,
    TournamentKSelection,
    TruncationSelection,
    build_selection_rule,
)


def _high_scorer_fraction(beta: float, low: float, high: float, seed: int) -> float:
    """Run one big Fermi selection and measure how often high scorers win.

    The population is half low scorers, half high scorers, so with a
    saturating β the expected winning fraction is 3/4: a slot keeps a low
    scorer only when both the incumbent and the model draws land on low
    scorers (probability 1/4).

    Args:
        beta: Selection intensity for the rule under test.
        low: Score given to the first half of the population.
        high: Score given to the second half.
        seed: RNG seed (fixed by each caller — determinism).

    Returns:
        Fraction of the 4000 slots whose parent is a high scorer.
    """
    scores = [low] * 2000 + [high] * 2000
    rule = FermiSelection(DynamicsConfig(selection_beta=beta))
    parents = rule.select_parents(scores, np.random.default_rng(seed))
    return sum(parent >= 2000 for parent in parents) / len(parents)


class TestFermiSelection:
    """The pairwise-comparison rule from DESIGN §2.7."""

    def test_returns_one_in_range_parent_per_slot(self) -> None:
        """N scores in → N parent indices out, all valid."""
        scores = [1.0, 5.0, 3.0]
        rule = FermiSelection(DynamicsConfig())
        parents = rule.select_parents(scores, np.random.default_rng(0))
        assert len(parents) == 3
        assert all(0 <= parent < 3 for parent in parents)

    def test_beta_zero_ignores_scores(self) -> None:
        """β = 0 is pure drift: a huge score gap must not matter (≈ 1/2)."""
        fraction = _high_scorer_fraction(beta=0.0, low=0.0, high=1000.0, seed=1)
        assert abs(fraction - 0.5) < 0.04

    def test_equal_scores_are_a_coin_flip_at_any_beta(self) -> None:
        """With no score gap the adoption probability is exactly 1/2."""
        fraction = _high_scorer_fraction(beta=10.0, low=7.0, high=7.0, seed=2)
        assert abs(fraction - 0.5) < 0.04

    def test_large_beta_is_nearly_deterministic(self) -> None:
        """Saturating β: high scorers win every comparison (fraction ≈ 3/4).

        The 1/4 floor is drift, not selection: slots where both draws land
        on low scorers never see a high scorer to copy.
        """
        fraction = _high_scorer_fraction(beta=50.0, low=0.0, high=10.0, seed=3)
        assert abs(fraction - 0.75) < 0.04

    def test_extreme_beta_times_gap_does_not_overflow(self) -> None:
        """β·Δscore in the ±10⁹ range must stay stable (DECISIONS #32).

        A naive logistic would raise ``OverflowError`` here; the stable
        implementation must both survive and still saturate correctly.
        """
        fraction = _high_scorer_fraction(beta=1000.0, low=0.0, high=1_000_000.0, seed=4)
        assert abs(fraction - 0.75) < 0.04

    def test_documented_draw_order_reproduces_selection(self) -> None:
        """The per-slot draw order (incumbent, model, adoption) is a contract.

        A twin generator replaying the documented order must reproduce the
        rule's output exactly — this is the #32 analogue of the match-level
        draw-order tests for #23.
        """
        scores = [3.0, 1.0, 4.0, 1.0, 5.0]
        beta = 1.3
        rule = FermiSelection(DynamicsConfig(selection_beta=beta))
        parents = rule.select_parents(scores, np.random.default_rng(11))

        twin = np.random.default_rng(11)
        expected = []
        for _ in scores:
            incumbent = int(twin.integers(5))
            model = int(twin.integers(5))
            adopt = 1.0 / (1.0 + math.exp(-beta * (scores[model] - scores[incumbent])))
            expected.append(model if twin.random() < adopt else incumbent)
        assert parents == tuple(expected)


class TestProportionalSelection:
    """Fitness-proportional (roulette) selection — DECISIONS #63."""

    def test_zero_weight_agent_is_never_drawn(self) -> None:
        """The min-shift gives the worst scorer weight 0: never a parent."""
        scores = [1.0, 5.0, 9.0]
        rule = ProportionalSelection(DynamicsConfig())
        parents = rule.select_parents(scores * 100, np.random.default_rng(0))
        assert all(scores[parent % 3] != 1.0 for parent in parents)

    def test_negative_scores_are_shifted_not_rejected(self) -> None:
        """Weights come from the gap above min(s), so negatives are fine."""
        scores = [-10.0, -10.0, 30.0]
        rule = ProportionalSelection(DynamicsConfig())
        parents = rule.select_parents(scores, np.random.default_rng(1))
        assert len(parents) == 3
        # Agent 2's weight is 40 vs 0 and 0: it must win every slot.
        assert parents == (2, 2, 2)

    def test_all_equal_scores_fall_back_to_uniform(self) -> None:
        """All-zero weights ⇒ uniform draw, not a crash or a constant."""
        scores = [7.0] * 400
        rule = ProportionalSelection(DynamicsConfig())
        parents = rule.select_parents(scores, np.random.default_rng(2))
        assert len(set(parents)) > 100  # uniform over 400: many distinct parents

    def test_weight_proportionality_statistically(self) -> None:
        """An agent with 3x the weight is drawn ~3x as often (fixed seed)."""
        scores = [0.0, 10.0, 30.0]  # weights 0, 10, 30
        rule = ProportionalSelection(DynamicsConfig())
        parents = rule.select_parents(scores * 1000, np.random.default_rng(3))
        counts = [sum(p % 3 == i for p in parents) for i in range(3)]
        assert counts[0] == 0
        assert 2.6 < counts[2] / counts[1] < 3.4

    def test_always_exactly_one_draw_per_slot(self) -> None:
        """RNG contract: N draws — a twin consuming N choice draws aligns."""
        scores = [1.0, 2.0, 3.0, 4.0]
        rng = np.random.default_rng(4)
        ProportionalSelection(DynamicsConfig()).select_parents(scores, rng)
        # After exactly N weighted draws, the streams must coincide:
        twin = np.random.default_rng(4)
        weights = [s - 1.0 for s in scores]
        total = sum(weights)
        for _ in scores:
            twin.choice(4, p=[w / total for w in weights])
        assert rng.integers(1 << 30) == twin.integers(1 << 30)


class TestTournamentKSelection:
    """k-candidate contests per slot — DECISIONS #63."""

    def _rule(self, k: int) -> TournamentKSelection:
        """Build the rule with tournament size k.

        Args:
            k: Candidates per slot.

        Returns:
            The configured rule.
        """
        return TournamentKSelection(DynamicsConfig(selection_tournament_k=k))

    def test_k_equals_n_always_selects_the_top_scorer(self) -> None:
        """With every agent a candidate, the best one wins every slot."""
        scores = [3.0, 9.0, 1.0, 4.0]
        parents = self._rule(4).select_parents(scores, np.random.default_rng(0))
        assert parents == (1, 1, 1, 1)

    def test_ties_break_by_earliest_drawn_position(self) -> None:
        """All-equal scores: the FIRST drawn candidate wins (no extra draw).

        A twin generator replaying the documented draw order — one k-sized
        without-replacement choice per slot — must predict every winner.
        """
        scores = [5.0] * 6
        parents = self._rule(3).select_parents(scores, np.random.default_rng(7))
        twin = np.random.default_rng(7)
        expected = tuple(int(twin.choice(6, size=3, replace=False)[0]) for _ in range(6))
        assert parents == expected

    def test_winner_is_best_among_candidates_only(self) -> None:
        """The global best can lose a slot it was never drawn for."""
        scores = [0.0, 1.0, 2.0, 3.0, 100.0]
        parents = self._rule(2).select_parents(scores, np.random.default_rng(1))
        twin = np.random.default_rng(1)
        for parent in parents:
            candidates = twin.choice(5, size=2, replace=False)
            best = int(candidates[0])
            for candidate in candidates[1:]:
                if scores[int(candidate)] > scores[best]:
                    best = int(candidate)
            assert parent == best

    def test_k_beyond_population_fails_plainly(self) -> None:
        """The defensive matcher-style guard names both numbers."""
        with pytest.raises(ValueError, match="only has 3"):
            self._rule(4).select_parents([1.0, 2.0, 3.0], np.random.default_rng(0))


class TestTruncationSelection:
    """Elitist selection from the top q — DECISIONS #63."""

    def _rule(self, fraction: float) -> TruncationSelection:
        """Build the rule with elite fraction q.

        Args:
            fraction: The elite share (0 < q <= 1).

        Returns:
            The configured rule.
        """
        return TruncationSelection(DynamicsConfig(selection_elite_fraction=fraction))

    def test_parents_come_only_from_the_elite(self) -> None:
        """At q = 0.25 of 8 agents, only the top 2 scorers are ever parents."""
        scores = [1.0, 8.0, 2.0, 7.0, 3.0, 4.0, 5.0, 6.0]
        parents = self._rule(0.25).select_parents(scores, np.random.default_rng(0))
        assert set(parents) <= {1, 3}  # the two top scorers

    def test_elite_count_floors_at_one(self) -> None:
        """A tiny fraction still yields one parent: the single best agent."""
        scores = [4.0, 9.0, 2.0]
        parents = self._rule(0.01).select_parents(scores, np.random.default_rng(1))
        assert parents == (1, 1, 1)

    def test_boundary_ties_break_by_lower_agent_id(self) -> None:
        """Two agents tie at the elite boundary: the lower id gets the seat."""
        scores = [5.0, 9.0, 5.0, 1.0]  # elite_count = 2; agents 0 and 2 tie at 5.0
        parents = self._rule(0.5).select_parents(scores, np.random.default_rng(2))
        assert set(parents) <= {1, 0}  # agent 2's tie loses to agent 0's lower id

    def test_fraction_one_is_uniform_over_everyone(self) -> None:
        """At q = 1 the elite is the whole population — even the worst scorer.

        600 uniform draws over 600 agents leave ~63% distinct parents; far
        more than any true elite subset could produce, and the minimum
        scorer (impossible under q < 1 here) must appear among them.
        """
        scores = [3.0, 1.0, 2.0]
        parents = self._rule(1.0).select_parents(scores * 200, np.random.default_rng(3))
        assert len(set(parents)) > 300
        assert any(scores[parent % 3] == 1.0 for parent in parents)


class TestThresholdCloningSelection:
    """Survive-above-the-bar cloning — DECISIONS #63."""

    def _rule(self, multiplier: float) -> ThresholdCloningSelection:
        """Build the rule with threshold multiplier θ.

        Args:
            multiplier: The survival bar as a multiple of the mean score.

        Returns:
            The configured rule.
        """
        return ThresholdCloningSelection(DynamicsConfig(selection_threshold_multiplier=multiplier))

    def test_survivors_keep_their_own_slot(self) -> None:
        """Every above-mean agent's parent is itself."""
        scores = [10.0, 0.0, 10.0, 0.0]  # mean 5; survivors: 0 and 2
        parents = self._rule(1.0).select_parents(scores, np.random.default_rng(0))
        assert parents[0] == 0
        assert parents[2] == 2
        assert parents[1] in (0, 2)
        assert parents[3] in (0, 2)

    def test_survivors_consume_no_draws(self) -> None:
        """RNG contract: draws happen for NON-survivors only (#26 precedent).

        With every agent surviving (θ = 0), the generator must be untouched.
        """
        scores = [1.0, 2.0, 3.0]
        rng = np.random.default_rng(5)
        before = rng.bit_generator.state["state"]["state"]
        parents = self._rule(0.0).select_parents(scores, rng)
        assert parents == (0, 1, 2)  # everyone kept their slot
        assert rng.bit_generator.state["state"]["state"] == before  # zero draws

    def test_empty_survivor_set_falls_back_to_the_tied_maximum(self) -> None:
        """θ high enough that nobody qualifies: the top scorers survive."""
        scores = [4.0, 8.0, 8.0, 4.0]  # mean 6; θ=1.5 → bar 9 → nobody
        parents = self._rule(1.5).select_parents(scores, np.random.default_rng(1))
        assert parents[1] == 1  # the tied maxima survive in place
        assert parents[2] == 2
        assert parents[0] in (1, 2)
        assert parents[3] in (1, 2)

    def test_exactly_at_threshold_survives(self) -> None:
        """The bar is inclusive: score == θ·mean survives."""
        scores = [5.0, 5.0, 5.0]  # mean 5, bar 5 — all survive
        parents = self._rule(1.0).select_parents(scores, np.random.default_rng(2))
        assert parents == (0, 1, 2)


class TestBuildSelectionRule:
    """The declarative factory, mirroring build_matcher."""

    def test_fermi_is_built_from_config(self) -> None:
        """The registry choice string maps to the Fermi implementation."""
        rule = build_selection_rule(DynamicsConfig())
        assert isinstance(rule, FermiSelection)
        assert isinstance(rule, SelectionRule)

    def test_unknown_rule_rejected(self) -> None:
        """Defensive branch: an unvalidated name fails with a clear error.

        ``model_construct`` (new concept) builds a pydantic model WITHOUT
        validation — normally dangerous, here exactly what's needed to reach
        the factory's defensive error path.
        """
        config = DynamicsConfig.model_construct(selection_rule="telepathy")
        with pytest.raises(ValueError, match="Unknown selection rule"):
            build_selection_rule(config)
