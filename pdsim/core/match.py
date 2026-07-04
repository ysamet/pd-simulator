"""Plays one match between two agents: length modes, noise, transcript.

A match is a sequence of rounds between the same two agents. This module owns
the two length modes (fixed rounds / continuation probability, DESIGN §2.5),
execution noise ε (§2.6), and the per-round bookkeeping. Mechanics are pinned
down in DECISIONS #23; the executed-actions-only rule is DECISIONS #20.

Reproducibility contract — the fixed RNG draw order per round is:
    1. agent A decides, 2. agent B decides (stochastic strategies may draw),
    3. noise draw for A, 4. noise draw for B (only when ε > 0),
    5. in continuation mode, the continue/stop draw.
Any change to this order changes every seeded run's history — treat it as a
breaking change requiring a DECISIONS entry.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pdsim.config.experiment import MatchConfig
from pdsim.core.agent import Agent
from pdsim.core.game import Action, AgentId, Game, Payoff


@dataclass(frozen=True, slots=True)
class RoundRecord:
    """What happened in one round of a match.

    Attributes:
        actions: Each participant's *executed* action (post-noise), by id.
        payoffs: Each participant's payoff for the round, by id.
    """

    actions: dict[AgentId, Action]
    payoffs: dict[AgentId, Payoff]


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Complete transcript and totals for one finished match.

    This is the raw material for milestone 5's event stream and for the
    golden validation tests (DESIGN §7).

    Attributes:
        agent_ids: The two participants, in (a, b) play order.
        total_payoffs: Sum of each participant's round payoffs, by id.
        rounds: Per-round records, in play order.
    """

    agent_ids: tuple[AgentId, AgentId]
    total_payoffs: dict[AgentId, Payoff]
    rounds: tuple[RoundRecord, ...]

    @property
    def n_rounds(self) -> int:
        """Number of rounds actually played.

        Returns:
            The transcript length (varies per match in continuation mode).
        """
        return len(self.rounds)


class Match:
    """Reusable match-runner: build once, call :meth:`play` per pairing.

    Holds the game, the match settings, and the run's single seeded RNG
    (hard rule 5) — the pieces that are the same for every pairing in a
    generation.
    """

    def __init__(self, game: Game, config: MatchConfig, rng: np.random.Generator) -> None:
        """Create a match-runner.

        Args:
            game: The game scoring each round (e.g. :class:`PrisonersDilemma`).
            config: Length mode, round count / continuation probability, and
                noise level (a validated, frozen model — DECISIONS #24).
            rng: The run's seeded random generator.
        """
        self._game = game
        self._config = config
        self._rng = rng

    def play(self, agent_a: Agent, agent_b: Agent) -> MatchResult:
        """Play one full match between two agents.

        Both agents' scores and per-opponent histories are updated as rounds
        complete; the returned result additionally carries the full
        transcript.

        Args:
            agent_a: First participant.
            agent_b: Second participant.

        Returns:
            The finished match's transcript and totals.
        """
        records: list[RoundRecord] = []
        while True:
            records.append(self._play_round(agent_a, agent_b))
            if not self._continues(rounds_played=len(records)):
                break
        totals: dict[AgentId, Payoff] = {agent_a.agent_id: 0.0, agent_b.agent_id: 0.0}
        for record in records:
            for agent_id, payoff in record.payoffs.items():
                totals[agent_id] += payoff
        return MatchResult(
            agent_ids=(agent_a.agent_id, agent_b.agent_id),
            total_payoffs=totals,
            rounds=tuple(records),
        )

    def _play_round(self, agent_a: Agent, agent_b: Agent) -> RoundRecord:
        """Play a single round: decide, apply noise, score, record.

        Args:
            agent_a: First participant.
            agent_b: Second participant.

        Returns:
            The round's executed actions and payoffs.
        """
        # Simultaneous play: both decide from views that predate this round.
        intended_a = agent_a.decide(agent_b.agent_id, self._rng)
        intended_b = agent_b.decide(agent_a.agent_id, self._rng)
        executed_a = self._apply_noise(intended_a)
        executed_b = self._apply_noise(intended_b)
        payoffs = self._game.play({agent_a.agent_id: executed_a, agent_b.agent_id: executed_b})
        # Executed actions are the single truth (DECISIONS #20): they are what
        # got scored, what the opponent saw, and what each agent remembers.
        agent_a.record_round(agent_b.agent_id, executed_a, executed_b, payoffs[agent_a.agent_id])
        agent_b.record_round(agent_a.agent_id, executed_b, executed_a, payoffs[agent_b.agent_id])
        return RoundRecord(
            actions={agent_a.agent_id: executed_a, agent_b.agent_id: executed_b},
            payoffs=payoffs,
        )

    def _apply_noise(self, action: Action) -> Action:
        """Flip an intended action with probability ε (execution error).

        No RNG draw happens when ε is 0, so noise-free runs consume the
        random stream identically whether or not noise support exists.

        Args:
            action: The strategy's intended action.

        Returns:
            The executed action — flipped with probability ε.
        """
        epsilon = self._config.noise_epsilon
        if epsilon > 0.0 and self._rng.random() < epsilon:
            return action.flipped()
        return action

    def _continues(self, rounds_played: int) -> bool:
        """Decide whether the match goes on after a completed round.

        Fixed mode plays exactly ``rounds_per_match`` rounds. Continuation
        mode draws after every round: continue with probability w, so match
        lengths follow a geometric distribution with mean 1 / (1 - w), and
        every match plays at least one round (DECISIONS #23).

        Args:
            rounds_played: Number of rounds completed so far (>= 1).

        Returns:
            True if another round should be played.
        """
        if self._config.length_mode == "fixed":
            return rounds_played < self._config.rounds_per_match
        # numpy comparison yields a numpy bool; bool() keeps the contract exact.
        return bool(self._rng.random() < self._config.continuation_probability)
