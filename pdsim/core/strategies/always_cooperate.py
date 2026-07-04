"""AlwaysCooperate — cooperates unconditionally (``docs/DESIGN.md`` §2.3).

The trusting baseline of the roster: it thrives among reciprocators but is
defenseless against exploitation, which makes it the classic control case
for whether an environment protects cooperation.
"""

from __future__ import annotations

import numpy as np

from pdsim.core.game import Action

# NOTE: strategy modules import the registry by its full submodule path.
# During auto-discovery the package __init__ is still executing, so names
# re-exported there are not bound yet — the submodule itself always is.
from pdsim.core.strategies.registry import StrategyInfo, register_strategy
from pdsim.core.strategy import HistoryView, Strategy


class AlwaysCooperate(Strategy):
    """Cooperates every round, no matter what the opponent does."""

    def decide(self, view: HistoryView, rng: np.random.Generator) -> Action:
        """Cooperate, whatever happened.

        Args:
            view: Ignored — the decision never depends on history.
            rng: Ignored (deterministic strategy).

        Returns:
            Always ``COOPERATE``.
        """
        return Action.COOPERATE


register_strategy(
    StrategyInfo(
        name="always_cooperate",
        display_name="Always Cooperate",
        description=(
            "Cooperates every single round, no matter what the other player does. "
            "It does wonderfully among fellow cooperators but is easy prey for "
            "anyone willing to betray it."
        ),
        factory=AlwaysCooperate,
        learn_more=(
            "Unconditional cooperation ('ALLC') is the standard baseline in the "
            "evolutionary game theory literature."
        ),
    )
)
