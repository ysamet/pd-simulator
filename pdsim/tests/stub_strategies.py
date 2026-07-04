"""Trivial Strategy implementations for engine tests.

These are deliberately minimal stand-ins that keep the engine tests
independent of the production roster in ``pdsim/core/strategies/``, plus
test-only probes (:class:`StubCycler`, :class:`RecordingStrategy`) that are
not model strategies at all. They live here — not in the strategies package
— because that package is reserved for the auto-discovered production
roster (DECISIONS #24).
"""

from __future__ import annotations

import numpy as np

from pdsim.core.game import Action
from pdsim.core.strategy import HistoryView, Strategy


class StubAlwaysCooperate(Strategy):
    """Cooperates unconditionally."""

    def decide(self, view: HistoryView, rng: np.random.Generator) -> Action:
        """Cooperate, whatever happened.

        Args:
            view: Ignored.
            rng: Ignored (deterministic strategy).

        Returns:
            Always ``COOPERATE``.
        """
        return Action.COOPERATE


class StubAlwaysDefect(Strategy):
    """Defects unconditionally."""

    def decide(self, view: HistoryView, rng: np.random.Generator) -> Action:
        """Defect, whatever happened.

        Args:
            view: Ignored.
            rng: Ignored (deterministic strategy).

        Returns:
            Always ``DEFECT``.
        """
        return Action.DEFECT


class StubMirror(Strategy):
    """Cooperates first, then copies the opponent's last visible move.

    A Tit-for-Tat stand-in that keeps the match tests decoupled from the
    production roster (the real ``TitForTat`` lives in
    ``pdsim/core/strategies/tit_for_tat.py``).
    """

    def decide(self, view: HistoryView, rng: np.random.Generator) -> Action:
        """Mirror the opponent's most recent visible action.

        Args:
            view: History against this opponent.
            rng: Ignored (deterministic strategy).

        Returns:
            ``COOPERATE`` if no opponent move is visible, else the
            opponent's last visible move.
        """
        if not view.opponent_moves:
            return Action.COOPERATE
        return view.opponent_moves[-1]


class StubGrimWindow(Strategy):
    """Defects if any defection is visible in the (possibly capped) window.

    With unlimited memory this is GrimTrigger; under a ``memory_depth`` cap it
    is "grim within the visible window" — exactly the capped-Grim semantics
    documented in DECISIONS #21, which the match tests pin down.
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


class StubDefectOnceThenCooperate(Strategy):
    """Defects on the very first round of a relationship, cooperates after.

    Used to probe forgiveness/window behavior in other strategies.
    """

    def decide(self, view: HistoryView, rng: np.random.Generator) -> Action:
        """Defect only on round 0.

        Args:
            view: History against this opponent.
            rng: Ignored (deterministic strategy).

        Returns:
            ``DEFECT`` on the first-ever round, ``COOPERATE`` afterwards.
        """
        return Action.DEFECT if view.round_number == 0 else Action.COOPERATE


class StubCycler(Strategy):
    """Plays a fixed move pattern over and over, ignoring the opponent.

    A probe for cross-validation and decision tests: it reproduces
    ``axelrod.Cycler``'s behavior so both engines can face the same scripted
    opponent. Keyed off ``round_number`` (not the visible window) on
    purpose — a script follows the clock, not the relationship.
    """

    def __init__(self, cycle: str) -> None:
        """Create a cycler.

        Args:
            cycle: The repeating pattern as a string of ``C``/``D``,
                e.g. ``"CCD"``.
        """
        self.cycle = tuple(Action(ch) for ch in cycle)

    def decide(self, view: HistoryView, rng: np.random.Generator) -> Action:
        """Play the next move of the cycle.

        Args:
            view: Only ``round_number`` is read, to index into the cycle.
            rng: Ignored (deterministic strategy).

        Returns:
            The cycle move for this round, wrapping around forever.
        """
        return self.cycle[view.round_number % len(self.cycle)]


class RecordingStrategy(Strategy):
    """Cooperates always, while recording every view it receives.

    Test instrumentation, not a model strategy: the mutable ``views`` list
    deliberately breaks the statelessness rule so tests can assert, from
    inside a real match, exactly what the engine shows a strategy.
    """

    def __init__(self) -> None:
        """Start with an empty view log."""
        self.views: list[HistoryView] = []

    def decide(self, view: HistoryView, rng: np.random.Generator) -> Action:
        """Record the view, then cooperate.

        Args:
            view: History against this opponent; appended to ``views``.
            rng: Ignored.

        Returns:
            Always ``COOPERATE``.
        """
        self.views.append(view)
        return Action.COOPERATE
