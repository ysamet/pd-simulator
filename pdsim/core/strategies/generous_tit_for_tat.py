"""GenerousTitForTat(g) — Tit for Tat that sometimes forgives (``docs/DESIGN.md`` §2.3).

Plain Tit for Tat has a weakness under execution noise: one accidental
defection between two TFT players locks them into alternating (or mutual)
retaliation. Generous Tit for Tat breaks such vendettas by forgiving a
defection with probability g instead of always striking back.
"""

from __future__ import annotations

import numpy as np

from pdsim.config.registry import ParameterSpec, register
from pdsim.core.game import Action

# Full submodule path: the package __init__ is mid-execution during
# auto-discovery, so its re-exported names are not available yet.
from pdsim.core.strategies.registry import StrategyInfo, register_strategy
from pdsim.core.strategy import HistoryView, Strategy

GENEROSITY = register(
    ParameterSpec(
        key="strategy.generous_tit_for_tat.generosity",
        kind="float",
        default=1 / 3,
        minimum=0.0,
        maximum=1.0,
        label="Generosity (g)",
        section="Strategies",
        description=(
            "Chance that Generous Tit for Tat forgives a betrayal and cooperates "
            "anyway instead of striking back. At 0 it behaves exactly like Tit "
            "for Tat; at 1 it never retaliates at all. The default of 1/3 is the "
            "theoretically best level of forgiveness for the standard payoff "
            "values."
        ),
        learn_more=(
            "Nowak & Sigmund (1992) derived the optimal generosity "
            "min(1 - (T-R)/(R-S), (R-P)/(T-P)), which equals 1/3 for the standard "
            "payoffs T=5, R=3, P=1, S=0."
        ),
    )
)


class GenerousTitForTat(Strategy):
    """Tit for Tat, but forgives a defection with probability g.

    Like TitForTat, the rule reads only the *visible* history window and
    cooperates when nothing is visible (DECISIONS #22, #26).
    """

    def __init__(self, generosity: float | None = None) -> None:
        """Create a GenerousTitForTat(g) strategy.

        Args:
            generosity: Forgiveness probability g; ``None`` means "use the
                registry default" — the default is never written here,
                keeping the registry the single source of truth (hard
                rule 3).

        Raises:
            ValueError: If the value violates the registry spec (outside
                [0, 1]); the spec's own message is user-facing.
        """
        raw = GENEROSITY.default if generosity is None else generosity
        self.generosity: float = float(GENEROSITY.validate(raw))

    def decide(self, view: HistoryView, rng: np.random.Generator) -> Action:
        """Mirror cooperation; answer defection with a chance of mercy.

        The RNG is consulted *only* when reacting to a defection — a
        conditional draw is fine under DECISIONS #23 because the number of
        draws is a deterministic function of the visible history. The draw
        happens uniformly even at g = 0 or g = 1 (still deterministic, since
        ``rng.random()`` is in [0, 1)), so the stream does not depend on the
        parameter value.

        Args:
            view: History against this opponent (window may be capped).
            rng: The run's seeded random generator, drawn from when
                deciding whether to forgive.

        Returns:
            ``COOPERATE`` if no opponent move is visible or the last visible
            move was cooperation; after a defection, ``COOPERATE`` with
            probability g, else ``DEFECT``.
        """
        if not view.opponent_moves:
            return Action.COOPERATE
        if view.opponent_moves[-1] is Action.COOPERATE:
            return Action.COOPERATE
        return Action.COOPERATE if rng.random() < self.generosity else Action.DEFECT


register_strategy(
    StrategyInfo(
        name="generous_tit_for_tat",
        display_name="Generous Tit for Tat",
        description=(
            "Plays like Tit for Tat — cooperate first, then copy the other "
            "player's last move — but forgives a betrayal some of the time "
            "instead of always retaliating. That touch of mercy stops accidental "
            "defections from spiralling into endless mutual punishment."
        ),
        factory=GenerousTitForTat,
        params=(GENEROSITY,),
        learn_more=(
            "Nowak & Sigmund (1992): generosity beats strict reciprocity in "
            "noisy evolving populations."
        ),
    )
)
