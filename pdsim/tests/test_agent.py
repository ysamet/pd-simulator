"""Tests for Agent: per-opponent history, memory cap, score, reset."""

from __future__ import annotations

from pdsim.core.agent import Agent
from pdsim.core.game import Action
from pdsim.tests.stub_strategies import StubAlwaysCooperate

C = Action.COOPERATE
D = Action.DEFECT


def _agent(agent_id: int = 0, memory_depth: int | None = None) -> Agent:
    """Build a test agent with a trivial strategy.

    Args:
        agent_id: Identity to assign.
        memory_depth: Optional history cap to exercise.

    Returns:
        A fresh Agent.
    """
    return Agent(agent_id=agent_id, strategy=StubAlwaysCooperate(), memory_depth=memory_depth)


def test_unknown_opponent_yields_empty_view() -> None:
    """Meeting someone for the first time: empty history, round 0."""
    view = _agent().view_of(opponent_id=42)
    assert view.my_moves == ()
    assert view.opponent_moves == ()
    assert view.round_number == 0


def test_histories_are_per_opponent() -> None:
    """Rounds against opponent 1 must be invisible when facing opponent 2."""
    agent = _agent()
    agent.record_round(opponent_id=1, my_action=C, opponent_action=D, payoff=0.0)
    agent.record_round(opponent_id=1, my_action=D, opponent_action=D, payoff=1.0)
    assert agent.view_of(1).round_number == 2
    assert agent.view_of(1).opponent_moves == (D, D)
    # Opponent 2 is a stranger — direct reciprocity requires recognition.
    assert agent.view_of(2).round_number == 0
    assert agent.view_of(2).my_moves == ()


def test_recorded_actions_and_score_accumulate() -> None:
    """Executed actions are stored verbatim; payoffs add up in score."""
    agent = _agent()
    agent.record_round(opponent_id=1, my_action=C, opponent_action=C, payoff=3.0)
    agent.record_round(opponent_id=1, my_action=D, opponent_action=C, payoff=5.0)
    assert agent.view_of(1).my_moves == (C, D)
    assert agent.view_of(1).opponent_moves == (C, C)
    assert agent.score == 8.0


def test_memory_cap_truncates_moves_but_not_round_number() -> None:
    """Depth 2 after 5 rounds: last 2 moves visible, true count intact."""
    agent = _agent(memory_depth=2)
    moves = [C, C, D, C, D]
    for move in moves:
        agent.record_round(opponent_id=1, my_action=move, opponent_action=move, payoff=0.0)
    view = agent.view_of(1)
    assert view.my_moves == (C, D)  # only the last two
    assert view.opponent_moves == (C, D)
    assert view.round_number == 5  # awareness of time is never capped


def test_reset_for_new_generation_clears_score_and_history() -> None:
    """The M4 hook zeroes the score and forgets all opponents."""
    agent = _agent()
    agent.record_round(opponent_id=1, my_action=C, opponent_action=C, payoff=3.0)
    agent.reset_for_new_generation()
    assert agent.score == 0.0
    assert agent.view_of(1).round_number == 0
