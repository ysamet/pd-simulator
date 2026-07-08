"""Tests for the Matcher ABC, RoundRobin, RandomK, and the factory."""

from __future__ import annotations

import numpy as np
import pytest

from pdsim.config.experiment import MatchingConfig
from pdsim.core.agent import Agent
from pdsim.core.matcher import RandomK, RoundRobin, build_matcher
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


def _random_k_config(k: int) -> MatchingConfig:
    """Build a random_k matching config with the given k.

    Args:
        k: Opponents each agent initiates matches against.

    Returns:
        A validated matching config.
    """
    return MatchingConfig(matcher="random_k", opponents_per_agent=k)


def _id_pairs(matcher: RandomK, agents: list[Agent], seed: int) -> list[tuple[int, int]]:
    """Run one pairing pass and return it as (initiator_id, opponent_id) pairs.

    Args:
        matcher: The matcher under test.
        agents: The population to pair.
        seed: Seed for a fresh generator (so passes are independent).

    Returns:
        The pairing sequence, in draw order.
    """
    rng = np.random.default_rng(seed)
    return [(a.agent_id, b.agent_id) for a, b in matcher.pairings(agents, rng)]


class TestRandomK:
    """The sampled matcher's contract (DECISIONS #57)."""

    def test_match_count_is_n_times_k(self) -> None:
        """Every agent initiates exactly k matches: N·k in total."""
        pairs = _id_pairs(RandomK(_random_k_config(3)), _population(8), seed=0)
        assert len(pairs) == 8 * 3

    def test_no_self_matches(self) -> None:
        """An initiator never draws itself."""
        pairs = _id_pairs(RandomK(_random_k_config(4)), _population(6), seed=1)
        assert all(initiator != opponent for initiator, opponent in pairs)

    def test_each_initiators_opponents_are_distinct(self) -> None:
        """Within one pass, an initiator's k draws are without replacement."""
        k = 5
        pairs = _id_pairs(RandomK(_random_k_config(k)), _population(9), seed=2)
        for initiator in range(9):
            opponents = [b for a, b in pairs if a == initiator]
            assert len(opponents) == k
            assert len(set(opponents)) == k

    def test_k_equals_n_minus_one_yields_all_ordered_pairs(self) -> None:
        """At k = N - 1 every agent draws everyone: N·(N-1) matches."""
        n = 5
        pairs = _id_pairs(RandomK(_random_k_config(n - 1)), _population(n), seed=3)
        assert len(pairs) == n * (n - 1)
        # With k = N - 1 the sampling is exhaustive, so the SET of ordered
        # pairs is exactly all (initiator, opponent) pairs — only the order
        # within each initiator's block is random.
        assert set(pairs) == {(a, b) for a in range(n) for b in range(n) if a != b}

    def test_initiators_appear_in_agent_id_order(self) -> None:
        """Pairings are drawn agent 0 first, then agent 1, ... (RNG contract)."""
        pairs = _id_pairs(RandomK(_random_k_config(2)), _population(4), seed=4)
        initiators = [a for a, _ in pairs]
        assert initiators == [0, 0, 1, 1, 2, 2, 3, 3]

    def test_same_seed_reproduces_the_pairing_sequence(self) -> None:
        """Pairing reproducibility: same seed → identical draw order."""
        matcher = RandomK(_random_k_config(3))
        agents = _population(7)
        assert _id_pairs(matcher, agents, seed=42) == _id_pairs(matcher, agents, seed=42)

    def test_k_larger_than_population_fails_plainly(self) -> None:
        """The defensive matcher-level check names both numbers."""
        with pytest.raises(ValueError, match="offers only 3"):
            list(RandomK(_random_k_config(4)).pairings(_population(4), np.random.default_rng(0)))

    def test_opponent_frequencies_are_approximately_uniform(self) -> None:
        """Statistical sanity: draws show no favoritism (fixed seed).

        With N = 8 and k = 3, a given initiator draws a given opponent with
        probability k / (N - 1) = 3/7 per pass. Over 500 passes that is
        ~214 expected draws per (initiator, opponent) pair; the fixed seed
        makes the check deterministic, and the ±25% band is ~5 standard
        deviations wide — a failure means the sampling changed, not luck.
        """
        n, k, passes = 8, 3, 500
        matcher = RandomK(_random_k_config(k))
        agents = _population(n)
        rng = np.random.default_rng(1234)
        counts: dict[tuple[int, int], int] = {}
        for _ in range(passes):
            for agent_a, agent_b in matcher.pairings(agents, rng):
                pair = (agent_a.agent_id, agent_b.agent_id)
                counts[pair] = counts.get(pair, 0) + 1
        expected = passes * k / (n - 1)
        assert len(counts) == n * (n - 1)  # every ordered pair occurred
        assert all(0.75 * expected <= count <= 1.25 * expected for count in counts.values())


def test_build_matcher_resolves_registry_choice() -> None:
    """The default config's choice string maps to RoundRobin."""
    assert isinstance(build_matcher(MatchingConfig()), RoundRobin)


def test_build_matcher_resolves_random_k() -> None:
    """The random_k choice maps to a RandomK built from the config."""
    assert isinstance(build_matcher(_random_k_config(3)), RandomK)


def test_build_matcher_rejects_unknown_name() -> None:
    """Defensive error for names that bypass config validation.

    model_construct (new concept) builds a pydantic model WITHOUT validation —
    exactly what's needed to simulate a corrupted/bypassed config in a test.
    """
    bogus = MatchingConfig.model_construct(matcher="telepathy")
    with pytest.raises(ValueError, match="Unknown matcher"):
        build_matcher(bogus)
