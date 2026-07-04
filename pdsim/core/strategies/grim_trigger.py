"""GrimTrigger — one betrayal and it never cooperates again (``docs/DESIGN.md`` §2.3).

The maximally unforgiving reciprocator. Its threat sustains cooperation
perfectly in a noise-free world, but a single accidental defection (ε > 0)
dooms the relationship forever — the classic brittleness that forgiving
strategies like Generous Tit for Tat and Pavlov are measured against.
"""

from __future__ import annotations

import numpy as np

from pdsim.core.game import Action

# Full submodule path: the package __init__ is mid-execution during
# auto-discovery, so its re-exported names are not available yet.
from pdsim.core.strategies.registry import StrategyInfo, register_strategy
from pdsim.core.strategy import HistoryView, Strategy


class GrimTrigger(Strategy):
    """Cooperates until the first visible defection, then defects forever.

    "Forever" is bounded by what the strategy can see: strategies are
    stateless, so all memory lives in the engine-owned history view. Under a
    ``memory_depth`` cap this is therefore "grim within the visible window"
    — once the betrayal scrolls out of the window, GrimTrigger cooperates
    again (DECISIONS #21).
    """

    def decide(self, view: HistoryView, rng: np.random.Generator) -> Action:
        """Defect on any visible betrayal, else cooperate.

        Args:
            view: History against this opponent (window may be capped).
            rng: Ignored (deterministic strategy).

        Returns:
            ``DEFECT`` if any visible opponent move is a defection, else
            ``COOPERATE``.
        """
        if Action.DEFECT in view.opponent_moves:
            return Action.DEFECT
        return Action.COOPERATE


register_strategy(
    StrategyInfo(
        name="grim_trigger",
        display_name="Grim Trigger",
        description=(
            "Cooperates until the other player defects even once — then defects "
            "for the rest of the relationship, with no forgiveness ever. Its "
            "grim threat keeps honest partners honest, but a single accidental "
            "slip poisons the relationship for good."
        ),
        factory=GrimTrigger,
        learn_more=(
            "Also called 'Grudger' or the Friedman strategy (Friedman 1971), the "
            "trigger strategy behind many repeated-game folk theorems."
        ),
    )
)
