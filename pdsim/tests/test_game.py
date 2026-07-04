"""Tests for the Game ABC and PrisonersDilemma (``pdsim/core/game.py``)."""

from __future__ import annotations

import pytest

from pdsim.config.experiment import GameConfig
from pdsim.core.game import Action, PrisonersDilemma

C = Action.COOPERATE
D = Action.DEFECT


class TestAction:
    """The Action enum's tiny surface."""

    def test_flipped_round_trips(self) -> None:
        """Flipping twice returns the original action."""
        assert C.flipped() is D
        assert D.flipped() is C
        assert C.flipped().flipped() is C


class TestPrisonersDilemma:
    """Payoff correctness and arity enforcement."""

    def test_all_four_action_pairs_with_defaults(self) -> None:
        """T/R/P/S defaults (5/3/1/0) land on the right players."""
        game = PrisonersDilemma(GameConfig())
        assert game.play({1: C, 2: C}) == {1: 3.0, 2: 3.0}  # mutual cooperation: R
        assert game.play({1: D, 2: D}) == {1: 1.0, 2: 1.0}  # mutual defection: P
        assert game.play({1: C, 2: D}) == {1: 0.0, 2: 5.0}  # sucker S vs temptation T
        assert game.play({1: D, 2: C}) == {1: 5.0, 2: 0.0}  # temptation T vs sucker S

    def test_custom_relaxed_payoffs_flow_through(self) -> None:
        """A deliberately non-PD payoff set (toggles off) is honored as-is."""
        config = GameConfig(
            payoff_temptation=2.0,  # Stag Hunt-like: R > T
            payoff_reward=3.0,
            enforce_pd_ordering=False,
            enforce_alternation_constraint=False,
        )
        game = PrisonersDilemma(config)
        assert game.play({1: D, 2: C}) == {1: 2.0, 2: 0.0}
        assert game.play({1: C, 2: C}) == {1: 3.0, 2: 3.0}

    def test_wrong_participant_count_rejected(self) -> None:
        """The two-player game refuses 1 or 3 participants."""
        game = PrisonersDilemma(GameConfig())
        with pytest.raises(ValueError, match="two-player"):
            game.play({1: C})
        with pytest.raises(ValueError, match="two-player"):
            game.play({1: C, 2: D, 3: C})
