"""Decision-table tests for the seven v1 strategies (``docs/DESIGN.md`` §2.3, §7).

Each strategy gets a table of hand-worked histories → expected action
(CLAUDE.md hard rule 7). Because strategies are pure functions of
``(view, rng)`` (DECISIONS #21), a decision table is a complete behavioral
spec: build a view, call ``decide``, compare. Stochastic strategies get
their deterministic extremes tabled the same way, plus seeded frequency and
RNG-draw-discipline checks.

Views here are often built directly — including shapes the current engine
cannot produce (an empty visible window with ``round_number > 0``) — because
the tables pin the *contract*: strategies key off what they can see, never
off ``round_number`` (DECISIONS #26).
"""

from __future__ import annotations

import numpy as np
import pytest

from pdsim.config.registry import get_spec
from pdsim.core.game import Action
from pdsim.core.strategies.always_cooperate import AlwaysCooperate
from pdsim.core.strategies.always_defect import AlwaysDefect
from pdsim.core.strategies.generous_tit_for_tat import GenerousTitForTat
from pdsim.core.strategies.grim_trigger import GrimTrigger
from pdsim.core.strategies.pavlov import Pavlov
from pdsim.core.strategies.random_strategy import Random
from pdsim.core.strategies.tit_for_tat import TitForTat
from pdsim.core.strategy import HistoryView

C = Action.COOPERATE
D = Action.DEFECT


def _view(my: str, opp: str, round_number: int | None = None) -> HistoryView:
    """Build a HistoryView from compact move strings.

    Args:
        my: My visible moves as a string of ``C``/``D``, oldest first.
        opp: The opponent's visible moves, aligned with ``my``.
        round_number: True rounds played; defaults to the visible length
            (i.e. an uncapped window).

    Returns:
        The corresponding view. ``Action("C")`` works because the enum's
        values are the letters themselves.
    """
    my_moves = tuple(Action(ch) for ch in my)
    opp_moves = tuple(Action(ch) for ch in opp)
    return HistoryView(
        my_moves=my_moves,
        opponent_moves=opp_moves,
        round_number=len(my_moves) if round_number is None else round_number,
    )


def _rng() -> np.random.Generator:
    """Return a fresh seeded generator for deterministic-strategy calls.

    Returns:
        A generator none of the deterministic strategies should touch.
    """
    return np.random.default_rng(0)


class TestAlwaysCooperate:
    """AlwaysCooperate: C regardless of anything."""

    # New concept — @pytest.mark.parametrize is a *decorator*: a function
    # that takes the test function and returns an enhanced one (here: one
    # test run per table row). Decorators are plain higher-order functions —
    # the same functional-programming idea as strategies-as-functions.
    @pytest.mark.parametrize(
        ("view", "expected"),
        [
            (_view("", ""), C),
            (_view("CDC", "CCD"), C),
            (_view("CCC", "DDD"), C),
        ],
        ids=["first-round", "mixed-history", "relentless-betrayal"],
    )
    def test_decision_table(self, view: HistoryView, expected: Action) -> None:
        """Every row of the table must produce the expected action."""
        assert AlwaysCooperate().decide(view, _rng()) is expected


class TestAlwaysDefect:
    """AlwaysDefect: D regardless of anything."""

    @pytest.mark.parametrize(
        ("view", "expected"),
        [
            (_view("", ""), D),
            (_view("DCD", "CCD"), D),
            (_view("DDD", "CCC"), D),
        ],
        ids=["first-round", "mixed-history", "unanswered-kindness"],
    )
    def test_decision_table(self, view: HistoryView, expected: Action) -> None:
        """Every row of the table must produce the expected action."""
        assert AlwaysDefect().decide(view, _rng()) is expected


class TestTitForTat:
    """TitForTat: C first, then mirror the opponent's last visible move."""

    @pytest.mark.parametrize(
        ("view", "expected"),
        [
            (_view("", ""), C),
            (_view("", "", round_number=7), C),
            (_view("C", "C"), C),
            (_view("C", "D"), D),
            (_view("D", "C"), C),
            (_view("CD", "DC"), C),
            (_view("CC", "CD"), D),
            (_view("D", "D", round_number=5), D),
            (_view("C", "C", round_number=9), C),
        ],
        ids=[
            "first-round",
            "empty-window-is-fresh-start",
            "reciprocate-cooperation",
            "retaliate-defection",
            "mirror-regardless-of-own-move",
            "forgive-when-cooperation-resumes",
            "punish-latest-betrayal",
            "capped-window-sees-defection",
            "capped-window-sees-cooperation",
        ],
    )
    def test_decision_table(self, view: HistoryView, expected: Action) -> None:
        """Every row of the table must produce the expected action."""
        assert TitForTat().decide(view, _rng()) is expected


class TestGrimTrigger:
    """GrimTrigger: C until any visible defection, then D."""

    @pytest.mark.parametrize(
        ("view", "expected"),
        [
            (_view("", ""), C),
            (_view("", "", round_number=4), C),
            (_view("CCC", "CCC"), C),
            (_view("CCC", "DCC"), D),
            (_view("CCC", "CDC"), D),
            (_view("CC", "CD"), D),
            (_view("C", "C", round_number=5), C),
        ],
        ids=[
            "first-round",
            "empty-window-is-fresh-start",
            "spotless-record",
            "old-betrayal-never-forgotten",
            "mid-window-betrayal",
            "fresh-betrayal",
            "betrayal-scrolled-out-of-capped-window",
        ],
    )
    def test_decision_table(self, view: HistoryView, expected: Action) -> None:
        """Every row of the table must produce the expected action."""
        assert GrimTrigger().decide(view, _rng()) is expected


class TestPavlov:
    """Pavlov: repeat my last move after a win, flip it after a loss.

    "Win" = the opponent's last visible move was C (moves-only derivation
    of "paid T or R" — see the module docstring and DECISIONS #26).
    """

    @pytest.mark.parametrize(
        ("view", "expected"),
        [
            (_view("", ""), C),
            (_view("", "", round_number=3), C),
            (_view("C", "C"), C),
            (_view("C", "D"), D),
            (_view("D", "C"), D),
            (_view("D", "D"), C),
            (_view("CCD", "CCC"), D),
            (_view("CCC", "CCD"), D),
            (_view("CDD", "CDD"), C),
        ],
        ids=[
            "first-round",
            "empty-window-is-fresh-start",
            "CC-win-stay-cooperating",
            "CD-loss-shift-to-defect",
            "DC-win-stay-defecting",
            "DD-loss-shift-to-cooperate",
            "only-last-round-matters-stay",
            "only-last-round-matters-shift",
            "recovers-cooperation-after-mutual-defection",
        ],
    )
    def test_decision_table(self, view: HistoryView, expected: Action) -> None:
        """Every row of the table must produce the expected action."""
        assert Pavlov().decide(view, _rng()) is expected


class TestRandom:
    """Random(p): one draw per round, C iff it lands below p."""

    @pytest.mark.parametrize(
        "view",
        [_view("", ""), _view("CD", "DC"), _view("DDD", "DDD")],
        ids=["first-round", "mixed-history", "all-defection"],
    )
    def test_p_zero_always_defects(self, view: HistoryView) -> None:
        """p=0 is deterministic: rng.random() < 0 is impossible."""
        assert Random(cooperation_probability=0.0).decide(view, _rng()) is D

    @pytest.mark.parametrize(
        "view",
        [_view("", ""), _view("CD", "DC"), _view("DDD", "DDD")],
        ids=["first-round", "mixed-history", "all-defection"],
    )
    def test_p_one_always_cooperates(self, view: HistoryView) -> None:
        """p=1 is deterministic: rng.random() is always in [0, 1)."""
        assert Random(cooperation_probability=1.0).decide(view, _rng()) is C

    def test_default_comes_from_registry(self) -> None:
        """Random() must pick up the registry default, not a local literal."""
        spec = get_spec("strategy.random.cooperation_probability")
        assert Random().cooperation_probability == spec.default

    def test_default_frequency_is_about_half(self) -> None:
        """Seeded frequency check: default p produces ≈ 50% cooperation."""
        rng = np.random.default_rng(42)
        strategy = Random()
        decisions = [strategy.decide(_view("", ""), rng) for _ in range(3000)]
        rate = sum(action is C for action in decisions) / len(decisions)
        assert 0.45 < rate < 0.55

    @pytest.mark.parametrize("p", [0.0, 0.5, 1.0], ids=["p0", "p05", "p1"])
    def test_exactly_one_draw_per_decision(self, p: float) -> None:
        """Draw discipline: one rng draw per decide, whatever p is.

        Twin generators with the same seed produce the same stream; after
        the strategy consumes exactly one draw from the first, the two
        streams must be exactly one draw apart.
        """
        rng_used = np.random.default_rng(9)
        rng_twin = np.random.default_rng(9)
        Random(cooperation_probability=p).decide(_view("", ""), rng_used)
        rng_twin.random()  # skip the one draw the strategy should have used
        assert rng_used.random() == rng_twin.random()

    def test_out_of_range_p_rejected(self) -> None:
        """Constructor validation flows through the registry spec."""
        with pytest.raises(ValueError, match="at most"):
            Random(cooperation_probability=1.5)


class TestGenerousTitForTat:
    """GTFT(g): TFT that forgives a defection with probability g."""

    @pytest.mark.parametrize(
        ("view", "expected"),
        [
            (_view("", ""), C),
            (_view("", "", round_number=7), C),
            (_view("C", "C"), C),
            (_view("C", "D"), D),
            (_view("CD", "DC"), C),
        ],
        ids=[
            "first-round",
            "empty-window-is-fresh-start",
            "reciprocate-cooperation",
            "zero-generosity-retaliates",
            "forgive-when-cooperation-resumes",
        ],
    )
    def test_g_zero_is_exactly_tit_for_tat(self, view: HistoryView, expected: Action) -> None:
        """g=0 collapses to plain TFT — the same table must hold."""
        assert GenerousTitForTat(generosity=0.0).decide(view, _rng()) is expected

    @pytest.mark.parametrize(
        "view",
        [_view("C", "D"), _view("CC", "DD"), _view("D", "D")],
        ids=["single-betrayal", "repeated-betrayal", "mutual-defection"],
    )
    def test_g_one_always_forgives(self, view: HistoryView) -> None:
        """g=1 never retaliates: every defection is met with cooperation."""
        assert GenerousTitForTat(generosity=1.0).decide(view, _rng()) is C

    def test_default_comes_from_registry(self) -> None:
        """GTFT() must pick up the registry default (1/3), not a literal."""
        spec = get_spec("strategy.generous_tit_for_tat.generosity")
        assert GenerousTitForTat().generosity == spec.default
        assert GenerousTitForTat().generosity == pytest.approx(1 / 3)

    def test_default_forgiveness_frequency_is_about_a_third(self) -> None:
        """Seeded frequency check: default g forgives ≈ 1/3 of betrayals."""
        rng = np.random.default_rng(42)
        strategy = GenerousTitForTat()
        view = _view("C", "D")
        decisions = [strategy.decide(view, rng) for _ in range(3000)]
        rate = sum(action is C for action in decisions) / len(decisions)
        assert abs(rate - 1 / 3) < 0.03

    def test_no_draw_when_opponent_cooperated(self) -> None:
        """Draw discipline: the rng is untouched unless reacting to a D.

        Conditional draws are allowed because the draw count is a
        deterministic function of the visible history (DECISIONS #23/#26).
        """
        rng_used = np.random.default_rng(9)
        rng_twin = np.random.default_rng(9)
        strategy = GenerousTitForTat()
        strategy.decide(_view("", ""), rng_used)
        strategy.decide(_view("C", "C"), rng_used)
        assert rng_used.random() == rng_twin.random()  # streams still aligned

    def test_exactly_one_draw_when_opponent_defected(self) -> None:
        """Draw discipline: reacting to a defection costs exactly one draw."""
        rng_used = np.random.default_rng(9)
        rng_twin = np.random.default_rng(9)
        GenerousTitForTat().decide(_view("C", "D"), rng_used)
        rng_twin.random()  # skip the forgiveness draw
        assert rng_used.random() == rng_twin.random()

    def test_out_of_range_g_rejected(self) -> None:
        """Constructor validation flows through the registry spec."""
        with pytest.raises(ValueError, match="at least"):
            GenerousTitForTat(generosity=-0.1)
