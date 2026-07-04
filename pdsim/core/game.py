"""Game interface and the two-player Prisoner's Dilemma.

Defines the engine's foundational types (:class:`Action`, :data:`AgentId`,
:data:`Payoff`), the arity-agnostic :class:`Game` ABC from ``docs/DESIGN.md``
§3, and :class:`PrisonersDilemma` (§2.1). These types live here — at the root
of the core import graph — so every other core module can import them without
creating circular imports.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from enum import Enum

from pdsim.config.experiment import GameConfig

# Type aliases (new concept): alternative names for existing types. They cost
# nothing at runtime but make signatures say what they *mean* — compare
# `dict[AgentId, Payoff]` with `dict[int, float]`.
AgentId = int
"""Identifies one agent for the duration of a generation (DESIGN §2.2)."""

Payoff = float
"""Points earned in a single round of a game."""


class Action(Enum):
    """The two moves available in the Prisoner's Dilemma.

    New concept — ``Enum``: a fixed set of named constants. Unlike plain
    strings, a typo (``Action.COOPERAT``) is an immediate ``AttributeError``,
    and type checkers know exactly which values exist.
    """

    COOPERATE = "C"
    DEFECT = "D"

    def flipped(self) -> Action:
        """Return the opposite action.

        Used by the execution-noise mechanism (a trembling hand plays the
        opposite of what was intended) and handy in tests.

        Returns:
            ``DEFECT`` for ``COOPERATE`` and vice versa.
        """
        return Action.DEFECT if self is Action.COOPERATE else Action.COOPERATE


class Game(ABC):
    """What it means to be a game: participants' actions in, payoffs out.

    New concept — ABC (Abstract Base Class): a class that declares an
    interface but can't be instantiated itself. Subclasses *must* implement
    every ``@abstractmethod`` or Python refuses to construct them. This is
    hard rule 6 in code form: new games plug in as subclasses.

    The signature is deliberately arity-agnostic (a mapping of any number of
    participants) so v2's n-player Public Goods Game fits the same interface
    (DESIGN §3).
    """

    @abstractmethod
    def play(self, actions: Mapping[AgentId, Action]) -> dict[AgentId, Payoff]:
        """Score one round of the game.

        Args:
            actions: Each participant's executed action, keyed by agent id.

        Returns:
            Each participant's payoff for this round, keyed by agent id
            (same keys as ``actions``).

        Raises:
            ValueError: If the number of participants doesn't fit the game.
        """


class PrisonersDilemma(Game):
    """The classic two-player Prisoner's Dilemma (DESIGN §2.1).

    Payoffs come from a validated :class:`~pdsim.config.experiment.GameConfig`
    — the T/R/P/S values and their ordering rules are enforced at config
    construction, so this class only reads them (DECISIONS #24).
    """

    def __init__(self, config: GameConfig) -> None:
        """Build the payoff lookup table from a validated config.

        Args:
            config: Payoff matrix values (ordering toggles already enforced
                by the config model itself).
        """
        c, d = Action.COOPERATE, Action.DEFECT
        # One dict lookup per player per round: key is (my action, their action).
        self._payoffs: dict[tuple[Action, Action], Payoff] = {
            (c, c): config.payoff_reward,
            (c, d): config.payoff_sucker,
            (d, c): config.payoff_temptation,
            (d, d): config.payoff_punishment,
        }

    def play(self, actions: Mapping[AgentId, Action]) -> dict[AgentId, Payoff]:
        """Score one round between exactly two participants.

        Args:
            actions: The two participants' executed actions, keyed by agent id.

        Returns:
            Both participants' payoffs for this round, keyed by agent id.

        Raises:
            ValueError: If ``actions`` does not contain exactly two
                participants.
        """
        if len(actions) != 2:
            raise ValueError(
                f"PrisonersDilemma is a two-player game; got {len(actions)} participant(s)."
            )
        (id_a, action_a), (id_b, action_b) = actions.items()
        return {
            id_a: self._payoffs[(action_a, action_b)],
            id_b: self._payoffs[(action_b, action_a)],
        }
