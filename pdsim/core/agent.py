"""Agent: identity, strategy instance, score, and per-opponent history.

Agents have stable identities within a generation (DESIGN §2.2), so an agent
meeting a repeat opponent recognizes it — this per-opponent memory is what
makes direct reciprocity possible. The agent is also where the optional
``memory_depth`` cap is enforced: strategies only ever see the view built
here, so they physically cannot look further back (DECISIONS #21/#22).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pdsim.core.game import Action, AgentId, Payoff
from pdsim.core.strategy import HistoryView, Strategy


@dataclass
class _PairHistory:
    """Parallel move lists for the relationship with one specific opponent.

    Attributes:
        my_moves: This agent's executed actions, oldest first.
        opponent_moves: That opponent's executed actions, aligned per round.
    """

    # `field(default_factory=list)` (new concept recap from the config layer):
    # each _PairHistory gets its own fresh lists — a shared `= []` default
    # would be one list reused by every instance, a classic Python trap.
    my_moves: list[Action] = field(default_factory=list)
    opponent_moves: list[Action] = field(default_factory=list)


class Agent:
    """One member of the population: a strategy plus its accumulated state.

    Performance note: :meth:`view_of` copies the visible history into fresh
    tuples every round, making a full match O(length²) in moves. That is fine
    for the v1 envelope (~50-round matches, populations in the hundreds) and
    is the known hotspot for the future vectorized backend (DESIGN §3.1).
    """

    def __init__(
        self, agent_id: AgentId, strategy: Strategy, memory_depth: int | None = None
    ) -> None:
        """Create an agent.

        Args:
            agent_id: Stable identity within the current generation.
            strategy: The decision rule this agent plays.
            memory_depth: How many recent rounds per opponent the strategy may
                see; ``None`` means unlimited (registry:
                ``population.memory_depth``).
        """
        self.agent_id = agent_id
        self.strategy = strategy
        self.memory_depth = memory_depth
        self.score: float = 0.0
        self._histories: dict[AgentId, _PairHistory] = {}

    def view_of(self, opponent_id: AgentId) -> HistoryView:
        """Build the (possibly capped) history view against one opponent.

        Args:
            opponent_id: The opponent about to be faced.

        Returns:
            A :class:`HistoryView` with at most ``memory_depth`` visible
            rounds; ``round_number`` always reports the true total. A
            never-met opponent yields an empty view with ``round_number`` 0.
        """
        history = self._histories.get(opponent_id)
        if history is None:
            return HistoryView(my_moves=(), opponent_moves=(), round_number=0)
        rounds_played = len(history.my_moves)
        # Negative-index slicing: [-k:] is "the last k items" (and safely the
        # whole list when it has fewer than k). None slices to full history.
        window = slice(None) if self.memory_depth is None else slice(-self.memory_depth, None)
        return HistoryView(
            my_moves=tuple(history.my_moves[window]),
            opponent_moves=tuple(history.opponent_moves[window]),
            round_number=rounds_played,
        )

    def decide(self, opponent_id: AgentId, rng: np.random.Generator) -> Action:
        """Ask this agent's strategy for its next action against an opponent.

        Args:
            opponent_id: The opponent being faced this round.
            rng: The run's seeded random generator.

        Returns:
            The intended action (noise, if any, is applied later by the
            match — see DECISIONS #20/#23).
        """
        return self.strategy.decide(self.view_of(opponent_id), rng)

    def record_round(
        self,
        opponent_id: AgentId,
        my_action: Action,
        opponent_action: Action,
        payoff: Payoff,
    ) -> None:
        """Record one completed round: executed actions and the payoff earned.

        Args:
            opponent_id: The opponent this round was played against.
            my_action: This agent's *executed* action (post-noise —
                DECISIONS #20).
            opponent_action: The opponent's executed action.
            payoff: Points this agent earned this round; added to ``score``.
        """
        # dict.setdefault (new concept): fetch the existing entry, or insert
        # and return the given default in one step — tidier than an if/else.
        history = self._histories.setdefault(opponent_id, _PairHistory())
        history.my_moves.append(my_action)
        history.opponent_moves.append(opponent_action)
        self.score += payoff

    def reset_for_new_generation(self) -> None:
        """Zero the score and forget all opponents.

        The hook milestone 4's generation loop will call between generations
        (DESIGN §2.7: scores reset each generation in v1; histories reset
        with them since opponents' strategies change under selection).
        """
        self.score = 0.0
        self._histories.clear()
