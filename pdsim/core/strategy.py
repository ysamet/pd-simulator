"""Strategy interface and the history view handed to strategies.

The contract (``docs/DESIGN.md`` §3, amended by DECISIONS #21):
``Strategy.decide(view, rng) -> Action``. A strategy is a **pure function** of
the view and the injected RNG — it holds no mutable state. This is the
project's functional-programming thread made concrete: same view + same RNG
state → same decision, which is what makes strategies trivially testable and
the ``memory_depth`` cap enforceable (all memory lives in engine-owned
history, never inside the strategy).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from pdsim.core.game import Action


@dataclass(frozen=True, slots=True)
class HistoryView:
    """Everything a strategy is allowed to know when deciding (DECISIONS #22).

    The two move sequences are parallel: index i of each is the same round,
    and both may be truncated to the last ``memory_depth`` rounds by the
    engine. ``round_number`` is never truncated — a strategy always knows how
    long the relationship is, just not necessarily everything that happened.

    Attributes:
        my_moves: My executed actions against this opponent, oldest first
            (tuples, not lists — immutable, so a strategy cannot rewrite
            history).
        opponent_moves: The opponent's executed actions against me, oldest
            first, aligned with ``my_moves``.
        round_number: 0-based true count of rounds already played against
            this opponent — ``0`` means "this is our first-ever round".
            May exceed ``len(my_moves)`` when memory is capped.
    """

    my_moves: tuple[Action, ...]
    opponent_moves: tuple[Action, ...]
    round_number: int

    def __post_init__(self) -> None:
        """Guard the view's invariants at construction.

        Raises:
            ValueError: If the move sequences differ in length, or
                ``round_number`` is smaller than the visible history (the
                true count can never undercut what is shown).
        """
        if len(self.my_moves) != len(self.opponent_moves):
            raise ValueError(
                f"HistoryView move sequences must be parallel; got {len(self.my_moves)} of "
                f"mine vs {len(self.opponent_moves)} of the opponent's."
            )
        if self.round_number < len(self.my_moves):
            raise ValueError(
                f"round_number ({self.round_number}) cannot be smaller than the visible "
                f"history ({len(self.my_moves)} rounds)."
            )


class Strategy(ABC):
    """A decision rule for playing repeated games (DESIGN §2.3).

    Implementations decide from the :class:`HistoryView` alone — they never
    see agents, matches, or any engine internals. Stochastic strategies (e.g.
    Random(p), coming in milestone 3) draw from the injected ``rng``, never
    from a hidden random source (hard rule 5).

    Strategy metadata (machine name, display name, novice description) and
    registry hookup arrive with the real roster in milestone 3.
    """

    @abstractmethod
    def decide(self, view: HistoryView, rng: np.random.Generator) -> Action:
        """Choose the next action against one opponent.

        Args:
            view: The (possibly memory-capped) history against this opponent.
            rng: The run's seeded random generator, for stochastic decisions.

        Returns:
            The action to play this round.
        """
