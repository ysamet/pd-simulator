"""Tests for the Matcher ABC, RoundRobin, and the factory."""

from __future__ import annotations

import numpy as np
import pytest

from pdsim.config.experiment import MatchingConfig
from pdsim.core.agent import Agent
from pdsim.core.matcher import RoundRobin, build_matcher
from pdsim.tests.stub_strategies import StubAlwaysCooperate


def _population(n: int) -> list[Agent]:
    """Build n agents with sequential ids and a trivial strategy.

    Args:
        n: Population size.

    Returns:
        Agents with ids 0..n-1.
    """
    return [Agent(agent_id=i, strategy=StubAlwaysCooperate()) for i in range(n)]


def test_round_robin_yields_every_unordered_pair_once() -> None:
    """4 agents -> exactly the 6 unordered pairs, no self-pairs."""
    agents = _population(4)
    pairs = list(RoundRobin().pairings(agents, np.random.default_rng(0)))
    id_pairs = {(a.agent_id, b.agent_id) for a, b in pairs}
    assert len(pairs) == 6
    assert id_pairs == {(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)}
    assert all(a is not b for a, b in pairs)


def test_round_robin_order_is_deterministic() -> None:
    """Two calls yield the same pairs in the same order (reproducibility)."""
    agents = _population(5)
    rng = np.random.default_rng(0)
    first = [(a.agent_id, b.agent_id) for a, b in RoundRobin().pairings(agents, rng)]
    second = [(a.agent_id, b.agent_id) for a, b in RoundRobin().pairings(agents, rng)]
    assert first == second


def test_pairings_is_lazy() -> None:
    """The matcher returns an iterator, not a prebuilt list."""
    pairings = RoundRobin().pairings(_population(3), np.random.default_rng(0))
    assert iter(pairings) is pairings  # an iterator is its own iterator


def test_build_matcher_resolves_registry_choice() -> None:
    """The default config's choice string maps to RoundRobin."""
    assert isinstance(build_matcher(MatchingConfig()), RoundRobin)


def test_build_matcher_rejects_unknown_name() -> None:
    """Defensive error for names that bypass config validation.

    model_construct (new concept) builds a pydantic model WITHOUT validation —
    exactly what's needed to simulate a corrupted/bypassed config in a test.
    """
    bogus = MatchingConfig.model_construct(matcher="telepathy")
    with pytest.raises(ValueError, match="Unknown matcher"):
        build_matcher(bogus)
