"""Tests for selection rules (``pdsim/core/selection.py``, DECISIONS #32).

Covers: the Fermi rule's score-blindness at β = 0 and near-determinism at
large β, numerical stability at extreme β·Δscore, the documented per-slot
RNG draw order, and the ``build_selection_rule`` factory.

Statistical tests use fixed seeds and generous tolerances, so they are
deterministic — a failure means behavior changed, not bad luck.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pdsim.config.experiment import DynamicsConfig
from pdsim.core.selection import FermiSelection, SelectionRule, build_selection_rule


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
