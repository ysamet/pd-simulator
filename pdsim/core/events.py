"""Typed events: what the engine tells the world as a run unfolds (DESIGN §4).

The engine *yields* these instead of returning one final blob, so every
consumer — the live UI (M6), the recorder (M7), the demo scripts — is just a
loop over the same stream. Events are immutable values (frozen dataclasses,
like the reports and specs elsewhere): a consumer can hold onto one forever
and it will never change under its feet.

Five event types, coarse to fine (DECISIONS #35):

* :class:`RunFinished` — always emitted, exactly once, last.
* :class:`GenerationFinished` (evolution) / :class:`CycleFinished`
  (tournament) — one per generation/cycle. Two distinct types because their
  payloads differ: a generation reports the (changing) composition and that
  generation's scores; a cycle reports *cumulative* standings.
* :class:`MatchFinished` — one per match, at "match" granularity or finer.
* :class:`RoundPlayed` — one per round, at "round" granularity only.

A functional-programming note: ``Event`` below is a *union type* — "one of
these five" — so consumers dispatch with ``isinstance`` (or
``match``/``case``) and type checkers know every case they must handle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pdsim.core.game import Action, AgentId, Payoff


@dataclass(frozen=True, slots=True)
class RoundPlayed:
    """One round of one match, as it was executed (post-noise, #20).

    Attributes:
        agent_ids: The two participants, in (a, b) play order.
        round_index: 0-based position of this round within its match.
        actions: Each participant's executed action, by agent id.
        payoffs: Each participant's payoff for the round, by agent id.
    """

    agent_ids: tuple[AgentId, AgentId]
    round_index: int
    actions: dict[AgentId, Action]
    payoffs: dict[AgentId, Payoff]


@dataclass(frozen=True, slots=True)
class MatchFinished:
    """One completed match between two agents.

    Attributes:
        agent_ids: The two participants, in (a, b) play order.
        total_payoffs: Each participant's summed payoffs for this match.
        n_rounds: How many rounds the match ran (varies in continuation
            mode).
    """

    agent_ids: tuple[AgentId, AgentId]
    total_payoffs: dict[AgentId, Payoff]
    n_rounds: int


@dataclass(frozen=True, slots=True)
class GenerationFinished:
    """One completed generation (evolution mode only).

    Carries what the composition and score-trajectory charts need: who was
    in the population as it played, and how each strategy scored.

    Attributes:
        index: 0-based generation number.
        composition: Agent count per strategy machine name, as played.
        mean_scores: Mean end-of-generation score per strategy machine name.
        rounds_played: Rounds played per strategy this generation, summed
            over its agents — the denominator for the per-round score view
            (DECISIONS #44).
    """

    index: int
    composition: dict[str, int]
    mean_scores: dict[str, float]
    rounds_played: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CycleFinished:
    """One completed tournament cycle (tournament mode only).

    Tournament charts plot cumulative and per-agent mean score per strategy
    over time, so — unlike a generation — the payload is cumulative.

    Attributes:
        index: 0-based cycle number.
        composition: Agent count per strategy machine name (constant across
            the run — nothing evolves in a tournament).
        total_scores: Cumulative score per strategy over all cycles so far.
        mean_scores: Cumulative mean score per agent, per strategy.
        rounds_played: Cumulative rounds played per strategy, summed over
            its agents (cumulative like the scores — DECISIONS #44).
    """

    index: int
    composition: dict[str, int]
    total_scores: dict[str, float]
    mean_scores: dict[str, float]
    rounds_played: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunFinished:
    """The run is over; final summary (always emitted, exactly once, last).

    Attributes:
        mode: ``"evolution"`` or ``"tournament"``.
        completed: How many generations (evolution) or cycles (tournament)
            were played.
        composition: Final population composition by strategy machine name.
        mean_scores: Final per-strategy mean scores — the last generation's
            means in evolution mode; cumulative per-agent means in
            tournament mode.
        total_scores: Final cumulative totals per strategy (tournament
            mode); ``None`` in evolution mode, where scores reset each
            generation and a run-long total has no meaning (#31).
    """

    mode: str
    completed: int
    composition: dict[str, int]
    mean_scores: dict[str, float]
    total_scores: dict[str, float] | None


Event = RoundPlayed | MatchFinished | GenerationFinished | CycleFinished | RunFinished
"""Anything the engine can yield — see the module docstring for the taxonomy."""
