"""Tests for Match: golden-style scores, noise, length modes, reproducibility.

These are the milestone-2 analogues of the DESIGN §7 golden validation tests,
using stub strategies until the real roster lands in milestone 3.
"""

from __future__ import annotations

import numpy as np

from pdsim.config.experiment import GameConfig, MatchConfig
from pdsim.core.agent import Agent
from pdsim.core.game import Action, PrisonersDilemma
from pdsim.core.match import Match, MatchResult
from pdsim.core.strategy import Strategy
from pdsim.tests.stub_strategies import (
    RecordingStrategy,
    StubAlwaysCooperate,
    StubAlwaysDefect,
    StubDefectOnceThenCooperate,
    StubGrimWindow,
    StubMirror,
)

C = Action.COOPERATE
D = Action.DEFECT


def _play(
    strategy_a: Strategy,
    strategy_b: Strategy,
    config: MatchConfig,
    seed: int = 0,
    memory_depth: int | None = None,
) -> tuple[MatchResult, Agent, Agent]:
    """Run one match between two fresh agents with default payoffs.

    Args:
        strategy_a: Strategy for agent 0.
        strategy_b: Strategy for agent 1.
        config: Match settings under test.
        seed: RNG seed (only matters for noise/continuation draws here).
        memory_depth: Optional per-opponent memory cap for both agents.

    Returns:
        The match result and both agents (for state assertions).
    """
    agent_a = Agent(agent_id=0, strategy=strategy_a, memory_depth=memory_depth)
    agent_b = Agent(agent_id=1, strategy=strategy_b, memory_depth=memory_depth)
    match = Match(PrisonersDilemma(GameConfig()), config, np.random.default_rng(seed))
    return match.play(agent_a, agent_b), agent_a, agent_b


class TestGoldenScores:
    """Hand-computed score sequences (DESIGN §7 analogues)."""

    def test_mirror_vs_always_defect(self) -> None:
        """TFT-analogue vs AllD over n rounds: S+(n-1)P vs T+(n-1)P.

        Round 0 the mirror cooperates and is exploited (S vs T); from round 1
        on it mirrors the defection, so both take P. With defaults and n=5:
        mirror 0+4*1=4, defector 5+4*1=9.
        """
        result, _, _ = _play(StubMirror(), StubAlwaysDefect(), MatchConfig(rounds_per_match=5))
        assert result.total_payoffs == {0: 4.0, 1: 9.0}
        assert [r.actions[0] for r in result.rounds] == [C, D, D, D, D]
        assert [r.actions[1] for r in result.rounds] == [D, D, D, D, D]

    def test_mirror_vs_mirror_is_mutual_cooperation(self) -> None:
        """Noise-free reciprocators lock into all-C: n*R each."""
        result, _, _ = _play(StubMirror(), StubMirror(), MatchConfig(rounds_per_match=5))
        assert result.total_payoffs == {0: 15.0, 1: 15.0}
        assert all(r.actions == {0: C, 1: C} for r in result.rounds)


class TestNoise:
    """Execution error ε at its deterministic extremes."""

    def test_epsilon_zero_never_flips(self) -> None:
        """ε=0: executed actions equal intentions, always."""
        result, _, _ = _play(
            StubAlwaysCooperate(),
            StubAlwaysCooperate(),
            MatchConfig(rounds_per_match=20, noise_epsilon=0.0),
        )
        assert all(r.actions == {0: C, 1: C} for r in result.rounds)

    def test_epsilon_one_always_flips(self) -> None:
        """ε=1: two would-be cooperators play mutual defection (n*P each)."""
        result, _, _ = _play(
            StubAlwaysCooperate(),
            StubAlwaysCooperate(),
            MatchConfig(rounds_per_match=5, noise_epsilon=1.0),
        )
        assert all(r.actions == {0: D, 1: D} for r in result.rounds)
        assert result.total_payoffs == {0: 5.0, 1: 5.0}

    def test_noisy_flips_are_recorded_as_executed(self) -> None:
        """DECISIONS #20: histories hold the flipped (executed) actions."""
        _, agent_a, _ = _play(
            StubAlwaysCooperate(),
            StubAlwaysCooperate(),
            MatchConfig(rounds_per_match=3, noise_epsilon=1.0),
        )
        assert agent_a.view_of(1).my_moves == (D, D, D)
        assert agent_a.view_of(1).opponent_moves == (D, D, D)


class TestLengthModes:
    """Fixed rounds vs continuation probability (DECISIONS #23)."""

    def test_fixed_mode_plays_exact_round_count(self) -> None:
        """Fixed mode: the transcript has exactly rounds_per_match entries."""
        result, _, _ = _play(StubMirror(), StubMirror(), MatchConfig(rounds_per_match=7))
        assert result.n_rounds == 7

    def test_continuation_w_zero_plays_exactly_one_round(self) -> None:
        """w=0: the guaranteed first round happens, then the match ends."""
        config = MatchConfig(length_mode="continuation", continuation_probability=0.0)
        result, _, _ = _play(StubMirror(), StubMirror(), config)
        assert result.n_rounds == 1

    def test_continuation_mean_length_matches_theory(self) -> None:
        """Mean match length over many matches ≈ 1/(1-w) (loose bound)."""
        w = 0.75  # expected length 4
        config = MatchConfig(length_mode="continuation", continuation_probability=w)
        match = Match(PrisonersDilemma(GameConfig()), config, np.random.default_rng(7))
        lengths = []
        for _ in range(400):
            agent_a = Agent(agent_id=0, strategy=StubAlwaysCooperate())
            agent_b = Agent(agent_id=1, strategy=StubAlwaysCooperate())
            lengths.append(match.play(agent_a, agent_b).n_rounds)
        mean = sum(lengths) / len(lengths)
        assert abs(mean - 1 / (1 - w)) < 0.7  # > 4 sigma of the sample mean


class TestReproducibility:
    """Hard rules 5 and 8: same seed, same history."""

    def test_same_seed_reproduces_identical_match(self) -> None:
        """Noisy continuation-mode matches replay exactly under one seed."""
        config = MatchConfig(
            length_mode="continuation", continuation_probability=0.9, noise_epsilon=0.3
        )
        result_1, _, _ = _play(StubMirror(), StubMirror(), config, seed=123)
        result_2, _, _ = _play(StubMirror(), StubMirror(), config, seed=123)
        assert result_1 == result_2  # frozen dataclasses compare by value

    def test_different_seed_diverges(self) -> None:
        """Different seeds produce different histories (with these settings)."""
        config = MatchConfig(
            length_mode="continuation", continuation_probability=0.9, noise_epsilon=0.3
        )
        result_1, _, _ = _play(StubMirror(), StubMirror(), config, seed=1)
        result_2, _, _ = _play(StubMirror(), StubMirror(), config, seed=2)
        assert result_1 != result_2


class TestAgentStateCoherence:
    """Match-side bookkeeping must agree with agent-side state."""

    def test_scores_and_history_lengths_match_result(self) -> None:
        """After a match: agent.score == result totals; history == n_rounds."""
        result, agent_a, agent_b = _play(
            StubMirror(), StubAlwaysDefect(), MatchConfig(rounds_per_match=5)
        )
        assert agent_a.score == result.total_payoffs[0]
        assert agent_b.score == result.total_payoffs[1]
        assert agent_a.view_of(1).round_number == result.n_rounds
        assert agent_b.view_of(0).round_number == result.n_rounds

    def test_repeat_opponents_continue_their_relationship(self) -> None:
        """DECISIONS #22: history persists across matches within a generation.

        After match 1 vs an unconditional defector, the mirror opens match 2
        with defection — it remembers this opponent.
        """
        agent_a = Agent(agent_id=0, strategy=StubMirror())
        agent_b = Agent(agent_id=1, strategy=StubAlwaysDefect())
        match = Match(
            PrisonersDilemma(GameConfig()),
            MatchConfig(rounds_per_match=3),
            np.random.default_rng(0),
        )
        match.play(agent_a, agent_b)
        result_2 = match.play(agent_a, agent_b)
        assert result_2.rounds[0].actions[0] == D  # no naive cooperation on "round 0"
        assert agent_a.view_of(1).round_number == 6


class TestMemoryCapInMatches:
    """The memory_depth cap changes behavior, live, inside a match."""

    def test_capped_grim_forgives_when_defection_leaves_window(self) -> None:
        """DECISIONS #21: capped Grim is grim only within its visible window.

        vs defect-once-then-cooperate with depth 1: C (nothing seen), D (saw
        the round-0 defection), then C forever (the defection scrolled out).
        Uncapped Grim would defect from round 1 onward.
        """
        capped, _, _ = _play(
            StubGrimWindow(),
            StubDefectOnceThenCooperate(),
            MatchConfig(rounds_per_match=4),
            memory_depth=1,
        )
        assert [r.actions[0] for r in capped.rounds] == [C, D, C, C]

        uncapped, _, _ = _play(
            StubGrimWindow(),
            StubDefectOnceThenCooperate(),
            MatchConfig(rounds_per_match=4),
            memory_depth=None,
        )
        assert [r.actions[0] for r in uncapped.rounds] == [C, D, D, D]


class TestViewSemanticsInsideMatches:
    """What the engine actually shows a strategy, observed from within."""

    def test_views_are_pre_round_and_zero_based(self) -> None:
        """A strategy sees only completed rounds, counted from 0."""
        recorder = RecordingStrategy()
        _play(recorder, StubAlwaysDefect(), MatchConfig(rounds_per_match=3))
        assert [v.round_number for v in recorder.views] == [0, 1, 2]
        # The view for round i shows exactly i completed rounds — never the
        # opponent's current-round move (simultaneous play).
        assert [len(v.opponent_moves) for v in recorder.views] == [0, 1, 2]
        assert recorder.views[2].opponent_moves == (D, D)
