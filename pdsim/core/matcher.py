"""Matcher interface: who plays whom each generation (DESIGN §2.4).

v1 ships RoundRobin (every pair plays once) and RandomK (each agent initiates
matches against k sampled opponents — DECISIONS #57); the spatial kernel
plugs into the same ABC later. The interface takes an ``rng`` (RandomK needs
it; RoundRobin ignores it and consumes no draws) and full ``Agent`` objects
(SpatialKernel will need ``agent.position``). Widening an ABC's signature
after implementations exist breaks all of them, so the interface was
future-proofed from day one (hard rule 6).
"""

from __future__ import annotations

import itertools
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Sequence

import numpy as np

from pdsim.config.experiment import MatchingConfig
from pdsim.core.agent import Agent


class Matcher(ABC):
    """Produces the pairings that play matches in one generation."""

    @abstractmethod
    def pairings(
        self, agents: Sequence[Agent], rng: np.random.Generator
    ) -> Iterator[tuple[Agent, Agent]]:
        """Yield the pairs of agents that should play a match.

        Args:
            agents: The current population.
            rng: The run's seeded random generator (unused by deterministic
                matchers like RoundRobin; required by sampling matchers like
                the future RandomK).

        Yields:
            Pairs of distinct agents, one pair per match to be played.
        """


class RoundRobin(Matcher):
    """Every pair plays exactly one match per generation — O(N²) matches."""

    def pairings(
        self, agents: Sequence[Agent], rng: np.random.Generator
    ) -> Iterator[tuple[Agent, Agent]]:
        """Yield every unordered pair of distinct agents exactly once.

        New concept — generators: a function with ``yield`` produces values
        lazily, one at a time, instead of building the whole list up front.
        ``yield from`` delegates to another iterable —
        ``itertools.combinations(agents, 2)`` already yields exactly the
        unordered pairs we want, in a deterministic order.

        Args:
            agents: The current population.
            rng: Unused — round-robin is deterministic.

        Yields:
            Each unordered pair of distinct agents, exactly once.
        """
        yield from itertools.combinations(agents, 2)


class RandomK(Matcher):
    """Each agent initiates matches against k sampled opponents — O(N·k).

    Why this exists: round-robin's match count grows with the *square* of the
    population, and for large N the match phase — not chart rendering — is
    what makes runs slow (DESIGN §3.1). Sampling k opponents per agent plays
    exactly N·k matches per period instead, at the price of participation
    luck: an agent plays its own k matches plus however many times others
    happened to draw it, so raw generation scores vary with popularity. That
    is deliberate — the raw total remains what selection acts on, and the
    "per round" score view is the participation-normalized comparison
    (DECISIONS #44/#57).

    Seeded-history contract (DECISIONS #57): all pairings are drawn at the
    START of the match phase, in agent-id order — one without-replacement
    draw of k distinct opponents per initiator — and the matches then play
    in exactly that order. A pair may appear twice (A drawing B and B
    drawing A produces two matches); an initiator never draws itself or the
    same opponent twice in one pass.
    """

    def __init__(self, config: MatchingConfig) -> None:
        """Create a RandomK matcher from a validated matching config.

        Args:
            config: The matching section of an experiment config (whole
                config models cross module boundaries — DECISIONS #24);
                reads ``opponents_per_agent``.
        """
        self._k = config.opponents_per_agent

    def pairings(
        self, agents: Sequence[Agent], rng: np.random.Generator
    ) -> Iterator[tuple[Agent, Agent]]:
        """Draw every pairing up front, then yield them in draw order.

        Unlike RoundRobin's lazy generator, this method draws ALL pairings
        eagerly, before returning: the RNG contract requires the whole
        pairing sequence to be drawn before the first match plays, so
        pairing draws never interleave with in-match draws (DECISIONS #57).

        Args:
            agents: The current population, in agent-id order.
            rng: The run's seeded random generator; consumes exactly one
                k-sized without-replacement draw per agent, in agent order.

        Returns:
            An iterator over N·k (initiator, opponent) pairs, in draw order.

        Raises:
            ValueError: If k exceeds N - 1 (defensive — config validation
                enforces this for engine runs; the message is for direct
                callers).
        """
        if self._k > len(agents) - 1:
            raise ValueError(
                f"random_k needs {self._k} distinct opponents per agent, but a "
                f"population of {len(agents)} offers only {len(agents) - 1}."
            )
        pairs: list[tuple[Agent, Agent]] = []
        for initiator in agents:
            others = [agent for agent in agents if agent is not initiator]
            drawn = rng.choice(len(others), size=self._k, replace=False)
            pairs.extend((initiator, others[index]) for index in drawn)
        return iter(pairs)


def build_matcher(config: MatchingConfig) -> Matcher:
    """Construct the matcher named by a validated config.

    Maps the registry choice string (``matching.matcher``) to a constructor,
    so callers (the generation loop) stay declarative. Each entry is a
    callable taking the config — a class *is* such a callable, and RoundRobin
    (which needs nothing from the config) gets a small adapter.

    Args:
        config: The matching section of an experiment config.

    Returns:
        A ready-to-use :class:`Matcher`.

    Raises:
        ValueError: If the name is unknown (defensive — the registry's
            choices should have caught it already).
    """
    matchers: dict[str, Callable[[MatchingConfig], Matcher]] = {
        "round_robin": lambda _config: RoundRobin(),
        "random_k": RandomK,
    }
    try:
        return matchers[config.matcher](config)
    except KeyError:
        raise ValueError(
            f"Unknown matcher {config.matcher!r}; known matchers: {sorted(matchers)}"
        ) from None
