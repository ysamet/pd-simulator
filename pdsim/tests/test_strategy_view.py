"""Tests for HistoryView invariants (``pdsim/core/strategy.py``)."""

from __future__ import annotations

import dataclasses

import pytest

from pdsim.core.game import Action
from pdsim.core.strategy import HistoryView

C = Action.COOPERATE
D = Action.DEFECT


def test_view_is_immutable() -> None:
    """A strategy cannot rewrite the history it is shown."""
    view = HistoryView(my_moves=(C,), opponent_moves=(D,), round_number=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.round_number = 99  # type: ignore[misc]


def test_parallel_length_invariant_enforced() -> None:
    """The two move sequences must describe the same rounds."""
    with pytest.raises(ValueError, match="parallel"):
        HistoryView(my_moves=(C, C), opponent_moves=(D,), round_number=2)


def test_round_number_cannot_undercut_visible_history() -> None:
    """The true round count can never be less than what is shown."""
    with pytest.raises(ValueError, match="round_number"):
        HistoryView(my_moves=(C, C), opponent_moves=(D, D), round_number=1)


def test_capped_view_shapes_are_valid() -> None:
    """A capped view (fewer visible moves than true rounds) is legal."""
    view = HistoryView(my_moves=(C,), opponent_moves=(D,), round_number=5)
    assert view.round_number == 5
    assert len(view.my_moves) == 1
