"""Matcher interface: who plays whom each generation (DESIGN §2.4).

v1 ships RoundRobin; RandomK and the spatial kernel plug into the same ABC
later — which is why the interface already takes an ``rng`` (RandomK needs
it) and full ``Agent`` objects (SpatialKernel will need ``agent.position``).
Widening an ABC's signature after implementations exist breaks all of them,
so the interface is future-proofed now (hard rule 6).
"""

from __future__ import annotations

import itertools
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence

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


def build_matcher(config: MatchingConfig) -> Matcher:
    """Construct the matcher named by a validated config.

    Maps the registry choice string (``matching.matcher``) to a class, so
    callers (milestone 4's generation loop) stay declarative.

    Args:
        config: The matching section of an experiment config.

    Returns:
        A ready-to-use :class:`Matcher`.

    Raises:
        ValueError: If the name is unknown (defensive — the registry's
            choices should have caught it already).
    """
    matchers: dict[str, type[Matcher]] = {"round_robin": RoundRobin}
    try:
        return matchers[config.matcher]()
    except KeyError:
        raise ValueError(
            f"Unknown matcher {config.matcher!r}; known matchers: {sorted(matchers)}"
        ) from None
