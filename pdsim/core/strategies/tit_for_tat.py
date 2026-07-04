"""TitForTat — cooperate first, then mirror the opponent (``docs/DESIGN.md`` §2.3).

The famous winner of Axelrod's tournaments: nice (never defects first),
retaliatory (answers defection immediately), forgiving (one cooperation
restores peace), and clear (opponents can see what it is doing).
"""

from __future__ import annotations

import numpy as np

from pdsim.core.game import Action

# Full submodule path: the package __init__ is mid-execution during
# auto-discovery, so its re-exported names are not available yet.
from pdsim.core.strategies.registry import StrategyInfo, register_strategy
from pdsim.core.strategy import HistoryView, Strategy


class TitForTat(Strategy):
    """Cooperates first; afterwards repeats the opponent's previous move.

    The rule reads only the *visible* history window. If ``memory_depth``
    hides everything (an empty window), TitForTat treats the opponent as new
    and cooperates — strategies key off what they can see, never off
    ``round_number`` (DECISIONS #22, #26).
    """

    def decide(self, view: HistoryView, rng: np.random.Generator) -> Action:
        """Mirror the opponent's most recent visible action.

        Args:
            view: History against this opponent (window may be capped).
            rng: Ignored (deterministic strategy).

        Returns:
            ``COOPERATE`` if no opponent move is visible, else the
            opponent's last visible move.
        """
        if not view.opponent_moves:
            return Action.COOPERATE
        return view.opponent_moves[-1]


register_strategy(
    StrategyInfo(
        name="tit_for_tat",
        display_name="Tit for Tat",
        description=(
            "Starts by cooperating, then simply copies whatever the other player "
            "did last round: cooperation is answered with cooperation, betrayal "
            "with betrayal. Simple, never the first to defect, and quick to both "
            "punish and forgive."
        ),
        factory=TitForTat,
        learn_more=(
            "Submitted by Anatol Rapoport, Tit for Tat won both of Robert "
            "Axelrod's computer tournaments (Axelrod, 'The Evolution of "
            "Cooperation', 1984)."
        ),
    )
)
