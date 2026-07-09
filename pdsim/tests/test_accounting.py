"""Tests for score accounting (``pdsim/core/accounting.py``, DECISIONS #64).

Covers: hand-computed effective-score sequences for both stateful rules
(including warmup), the W = 1 and λ = 0 per-generation equivalences, the
slot-carry semantics (state survives strategy switches — it belongs to the
slot), tournament-mode ignored-parameter behavior, the factory, and the
v1-equivalence regression: with the default per_generation accounting, a
seeded run's trajectory is byte-identical to the pre-M9a engine (the
expected literal below was captured by running the pre-change code).
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from pdsim.config.experiment import DynamicsConfig, ExperimentConfig
from pdsim.core import engine
from pdsim.core.accounting import (
    ExponentialDiscountAccounting,
    PerGenerationAccounting,
    ScoreAccounting,
    SlidingWindowAccounting,
    build_score_accounting,
)
from pdsim.core.events import GenerationFinished


class TestPerGeneration:
    """The default: effective = raw, statelessly."""

    def test_returns_raw_scores_unchanged(self) -> None:
        """Identity, generation after generation."""
        accounting = PerGenerationAccounting(DynamicsConfig())
        assert accounting.effective_scores([3.0, 1.0]) == (3.0, 1.0)
        assert accounting.effective_scores([-2.0, 9.0]) == (-2.0, 9.0)


class TestSlidingWindow:
    """Mean of the last W raw generation scores (DECISIONS #64)."""

    def _accounting(self, window: int) -> SlidingWindowAccounting:
        """Build the rule with window W.

        Args:
            window: The window size.

        Returns:
            The configured accounting rule.
        """
        return SlidingWindowAccounting(DynamicsConfig(accounting_window=window))

    def test_hand_computed_sequence_with_warmup(self) -> None:
        """W = 2, one slot: warmup means over what exists, then a true window."""
        accounting = self._accounting(2)
        assert accounting.effective_scores([10.0]) == (10.0,)  # 1 entry: itself
        assert accounting.effective_scores([20.0]) == (15.0,)  # (10+20)/2
        assert accounting.effective_scores([40.0]) == (30.0,)  # (20+40)/2 — 10 dropped

    def test_window_one_equals_per_generation(self) -> None:
        """W = 1 must reproduce the default accounting exactly."""
        window = self._accounting(1)
        for raw in ([5.0, 1.0], [2.0, 8.0], [-3.0, 0.0]):
            assert window.effective_scores(raw) == tuple(raw)

    def test_slots_are_independent(self) -> None:
        """Each slot's window holds its own history."""
        accounting = self._accounting(3)
        accounting.effective_scores([0.0, 100.0])
        assert accounting.effective_scores([30.0, 100.0]) == (15.0, 100.0)


class TestExponentialDiscount:
    """EMA of the raw generation scores (DECISIONS #64)."""

    def _accounting(self, discount: float) -> ExponentialDiscountAccounting:
        """Build the rule with discount λ.

        Args:
            discount: The EMA discount.

        Returns:
            The configured accounting rule.
        """
        return ExponentialDiscountAccounting(DynamicsConfig(accounting_discount=discount))

    def test_hand_computed_sequence(self) -> None:
        """λ = 0.5, one slot: effective(0)=raw(0), then the blend."""
        accounting = self._accounting(0.5)
        assert accounting.effective_scores([8.0]) == (8.0,)  # effective(0) = raw(0)
        assert accounting.effective_scores([0.0]) == (4.0,)  # 0.5·0 + 0.5·8
        assert accounting.effective_scores([4.0]) == (4.0,)  # 0.5·4 + 0.5·4

    def test_discount_zero_equals_per_generation(self) -> None:
        """λ = 0 must reproduce the default accounting exactly."""
        accounting = self._accounting(0.0)
        for raw in ([5.0, 1.0], [2.0, 8.0], [-3.0, 0.0]):
            assert accounting.effective_scores(raw) == tuple(raw)

    def test_constant_raw_score_is_a_fixed_point(self) -> None:
        """Scale stability: a steady score stays itself at any λ."""
        accounting = self._accounting(0.9)
        for _ in range(5):
            assert accounting.effective_scores([7.0]) == (7.0,)


class TestSlotCarry:
    """Accounting state belongs to the slot and survives strategy switches."""

    def test_state_survives_a_strategy_switch(self) -> None:
        """A slot's history persists whatever strategy occupies it (#64).

        The engine never resets accounting: the fold sees only slots, so a
        strategy "switch" changes nothing about the state a slot carries —
        generation 2's window still averages over the slot's own past.
        """
        accounting = SlidingWindowAccounting(DynamicsConfig(accounting_window=2))
        accounting.effective_scores([10.0, 0.0])
        # Generation 2: slot 0's occupant "switched strategy" — the window
        # still averages over the slot's own past.
        assert accounting.effective_scores([0.0, 0.0])[0] == 5.0

    def test_engine_run_with_stateful_accounting_is_reproducible(self) -> None:
        """Same config + seed ⇒ identical trajectory under sliding_window.

        Selection and mutation switch strategies constantly; slot-carried
        state must not break determinism.
        """
        config = _seeded_config(accounting={"score_accounting": "sliding_window"})
        first = _trajectory(config)
        second = _trajectory(config)
        assert first == second


def _seeded_config(
    accounting: dict[str, object] | None = None,
    rule: dict[str, object] | None = None,
) -> ExperimentConfig:
    """Build the shared seeded config for engine-level accounting tests.

    Args:
        accounting: Extra dynamics fields for the accounting under test.
        rule: Extra dynamics fields for the selection rule under test.

    Returns:
        A validated 12-agent, 10-generation evolution config (seed 2026).
    """
    return ExperimentConfig.model_validate(
        {
            "seed": 2026,
            "population": {
                "size": 12,
                "composition": {"tit_for_tat": 4, "always_defect": 4, "random": 4},
            },
            "match": {"length_mode": "fixed", "rounds_per_match": 6},
            "dynamics": {
                "generations": 10,
                "selection_beta": 0.05,
                "mutation_rate": 0.1,
                **(accounting or {}),
                **(rule or {}),
            },
        }
    )


def _trajectory(config: ExperimentConfig) -> list[dict[str, int]]:
    """Run a config and collect its composition trajectory.

    Args:
        config: The experiment to run.

    Returns:
        One name-sorted composition dict per generation.
    """
    return [
        dict(sorted(event.composition.items()))
        for event in engine.run(config)
        if isinstance(event, GenerationFinished)
    ]


class TestV1Equivalence:
    """With per_generation accounting, pre-M9a seeded runs replay exactly."""

    # Captured by running THIS config on the pre-M9a engine (M8 code, commit
    # b169cf7) — not computed by the code under test. If this fails, a
    # seeded-history contract was broken (hard rule 8).
    EXPECTED: ClassVar[list[dict[str, int]]] = [
        {"always_defect": 4, "random": 4, "tit_for_tat": 4},
        {"always_defect": 4, "random": 3, "tit_for_tat": 5},
        {"always_defect": 3, "random": 3, "tit_for_tat": 6},
        {"always_defect": 2, "random": 3, "tit_for_tat": 7},
        {"always_defect": 1, "pavlov": 1, "random": 4, "tit_for_tat": 6},
        {"random": 6, "tit_for_tat": 6},
        {"random": 5, "tit_for_tat": 7},
        {"random": 5, "tit_for_tat": 7},
        {"always_cooperate": 1, "generous_tit_for_tat": 1, "random": 2, "tit_for_tat": 8},
        {"always_cooperate": 1, "random": 1, "tit_for_tat": 10},
    ]

    def test_default_accounting_reproduces_the_pre_m9a_trajectory(self) -> None:
        """The default config path is byte-identical to v1 (zero RNG draws)."""
        assert _trajectory(_seeded_config()) == self.EXPECTED

    def test_explicit_per_generation_matches_too(self) -> None:
        """Naming the default explicitly changes nothing."""
        config = _seeded_config(accounting={"score_accounting": "per_generation"})
        assert _trajectory(config) == self.EXPECTED


class TestTournamentModeIgnoresAccounting:
    """#34: accounting settings are valid but inert in tournament mode."""

    def test_streams_are_identical_across_accounting_choices(self) -> None:
        """Two tournament runs differing only in accounting are identical."""

        def tournament(accounting: dict[str, object]) -> list[object]:
            config = ExperimentConfig.model_validate(
                {
                    "mode": "tournament",
                    "tournament_cycles": 2,
                    "population": {
                        "size": 4,
                        "composition": {"tit_for_tat": 2, "always_defect": 2},
                    },
                    "match": {"length_mode": "fixed", "rounds_per_match": 3},
                    "dynamics": accounting,
                }
            )
            return list(engine.run(config, granularity="round"))

        plain = tournament({})
        windowed = tournament({"score_accounting": "sliding_window", "accounting_window": 3})
        assert plain == windowed


class TestBuildScoreAccounting:
    """The declarative factory, mirroring build_selection_rule."""

    @pytest.mark.parametrize(
        ("name", "cls"),
        [
            ("per_generation", PerGenerationAccounting),
            ("sliding_window", SlidingWindowAccounting),
            ("exponential_discount", ExponentialDiscountAccounting),
        ],
    )
    def test_choices_map_to_classes(self, name: str, cls: type[ScoreAccounting]) -> None:
        """Every registry choice builds its implementation."""
        accounting = build_score_accounting(DynamicsConfig(score_accounting=name))
        assert isinstance(accounting, cls)

    def test_unknown_choice_rejected(self) -> None:
        """Defensive branch for names that bypass config validation."""
        config = DynamicsConfig.model_construct(score_accounting="telepathy")
        with pytest.raises(ValueError, match="Unknown score accounting"):
            build_score_accounting(config)


class TestSelectionRulesInsideTheEngine:
    """Per-rule seeded stability: same config + seed ⇒ identical trajectory."""

    @pytest.mark.parametrize(
        "rule",
        [
            {"selection_rule": "proportional"},
            {"selection_rule": "tournament_k", "selection_tournament_k": 3},
            {"selection_rule": "truncation", "selection_elite_fraction": 0.25},
            {"selection_rule": "threshold_cloning", "selection_threshold_multiplier": 1.0},
        ],
    )
    def test_seeded_runs_replay_identically(self, rule: dict[str, object]) -> None:
        """Two identical seeded runs agree generation for generation."""
        config = _seeded_config(rule=rule)
        assert _trajectory(config) == _trajectory(config)
