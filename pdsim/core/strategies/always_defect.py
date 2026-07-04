"""AlwaysDefect — defects unconditionally (``docs/DESIGN.md`` §2.3).

The purely selfish baseline: in a one-shot Prisoner's Dilemma defection is
the dominant move, so this strategy is what repeated play and reciprocity
have to beat for cooperation to evolve.
"""

from __future__ import annotations

import numpy as np

from pdsim.core.game import Action

# Full submodule path: the package __init__ is mid-execution during
# auto-discovery, so its re-exported names are not available yet.
from pdsim.core.strategies.registry import StrategyInfo, register_strategy
from pdsim.core.strategy import HistoryView, Strategy


class AlwaysDefect(Strategy):
    """Defects every round, no matter what the opponent does."""

    def decide(self, view: HistoryView, rng: np.random.Generator) -> Action:
        """Defect, whatever happened.

        Args:
            view: Ignored — the decision never depends on history.
            rng: Ignored (deterministic strategy).

        Returns:
            Always ``DEFECT``.
        """
        return Action.DEFECT


register_strategy(
    StrategyInfo(
        name="always_defect",
        display_name="Always Defect",
        description=(
            "Betrays every single round, no matter what the other player does. "
            "It exploits trusting opponents but earns poorly against anyone who "
            "retaliates — the benchmark that cooperation must beat."
        ),
        factory=AlwaysDefect,
        learn_more=(
            "Unconditional defection ('ALLD') is the dominant strategy of the "
            "one-shot Prisoner's Dilemma."
        ),
    )
)
