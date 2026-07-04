"""Pavlov (Win-Stay-Lose-Shift) — repeat what paid, switch what didn't.

The outcome-based member of the roster (``docs/DESIGN.md`` §2.3): instead of
reacting to what the *opponent* did (like Tit for Tat), Pavlov reacts to how
the round *went for itself*.

**Moves-only derivation (DECISIONS #22/#26).** History views expose moves,
not payoffs, so "paid well" must be derived: under the Prisoner's Dilemma
ordering T > R > P > S, my round paid T or R — a "win" — exactly when the
opponent cooperated, and S or P — a "loss" — exactly when it defected. So
Win-Stay-Lose-Shift becomes: *repeat my last executed move if the opponent's
last visible move was C; flip it if D.* (The executed, post-noise move is
what both sides remember — DECISIONS #20 — so after a trembling hand, Pavlov
reacts to what its hand actually did.) If the payoff-ordering toggles are
relaxed (Chicken, Stag Hunt), Pavlov keeps this moves-based definition even
though T/R may no longer be the two best payoffs.
"""

from __future__ import annotations

import numpy as np

from pdsim.core.game import Action

# Full submodule path: the package __init__ is mid-execution during
# auto-discovery, so its re-exported names are not available yet.
from pdsim.core.strategies.registry import StrategyInfo, register_strategy
from pdsim.core.strategy import HistoryView, Strategy


class Pavlov(Strategy):
    """Win-Stay-Lose-Shift: keeps a winning move, flips a losing one.

    Like the other reciprocators, the rule reads only the *visible* history
    window and cooperates when nothing is visible (DECISIONS #22, #26).
    """

    def decide(self, view: HistoryView, rng: np.random.Generator) -> Action:
        """Repeat my last move after a win, flip it after a loss.

        Args:
            view: History against this opponent (window may be capped).
            rng: Ignored (deterministic strategy).

        Returns:
            ``COOPERATE`` if no round is visible; otherwise my last executed
            move if the opponent's last visible move was cooperation ("win
            — stay"), or its flip if the opponent defected ("lose — shift").
        """
        if not view.my_moves:
            return Action.COOPERATE
        if view.opponent_moves[-1] is Action.COOPERATE:
            return view.my_moves[-1]
        return view.my_moves[-1].flipped()


register_strategy(
    StrategyInfo(
        name="pavlov",
        display_name="Pavlov (Win-Stay-Lose-Shift)",
        description=(
            "Judges each round by its own result: if the round went well, it "
            "repeats its move; if it went badly, it tries the opposite. This "
            "makes it quick to re-establish cooperation after mistakes, and — "
            "unlike Tit for Tat — able to exploit players who never retaliate."
        ),
        factory=Pavlov,
        learn_more=(
            "Nowak & Sigmund (1993, Nature): 'Win-stay, lose-shift' outperforms "
            "Tit for Tat in noisy evolutionary simulations."
        ),
    )
)
