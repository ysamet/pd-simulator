"""Matcher interface: who plays whom each generation (DESIGN §2.4).

v1 shipped RoundRobin (every pair plays once) and RandomK (each agent
initiates matches against k sampled opponents — DECISIONS #57); M11a Phase D
adds SpatialKernel, which plugs into the same ABC. The interface takes an
``rng`` (the sampling matchers need it; RoundRobin ignores it and consumes
no draws) and full ``Agent`` objects. The full-object choice was
future-proofing that paid off, though not the way the original comment here
predicted: an early plan gave agents a continuous ``position`` attribute,
but that was dropped when the world became a graph of sites (DECISIONS
#104) — an agent's location is its SITE, and ``SpatialKernel`` holds the
structure and the occupancy at construction, so it looks agents' sites up
by id rather than reading anything spatial off the ``Agent``. What the full
objects actually buy is identity: pairings are (Agent, Agent) tuples the
match runner can play directly. Widening an ABC's signature after
implementations exist breaks all of them, so the interface was
future-proofed from day one (hard rule 6).
"""

from __future__ import annotations

import itertools
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Sequence

import numpy as np

from pdsim.config.experiment import MatchingConfig
from pdsim.core.agent import Agent
from pdsim.core.game import AgentId
from pdsim.core.occupancy import Occupancy
from pdsim.core.structure import Structure, neighbourhood_sample


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

        **The variable-N contract (M10a):** the draw size is clamped to
        ``min(k, N − 1)``, so a population the energy economy has shrunk
        below k + 1 agents keeps playing — everyone simply meets everyone.
        At every N ≥ k + 1 (the only regime the fixed-N engine could ever
        occupy) the clamp is a literal no-op, so every pre-M10a seeded
        ``random_k`` history is byte-identical (#57 preserved). Corners: at
        N = 2 each agent plays the one other; at N = 1 the lone survivor
        draws ``size=0`` — an empty draw that consumes NO RNG — plays 0
        matches, earns 0, and still pays its living cost (the intended
        thermodynamics of a population of one under a metabolic bill); at
        N = 0 there are no initiators and the run has already ended.
        Rejected alternatives: *raising* (a valid config must not crash
        because the population got small mid-run — a metabolic filter is
        supposed to be able to shrink a population, that is the science) and
        *skipping* (0 matches when N − 1 < k — a discontinuous cliff: one
        death away from k matches you would play none, with no mechanism
        motivating the jump). Config validation still enforces k ≤ N − 1
        for generation 0.

        Args:
            agents: The current population, in agent-id order.
            rng: The run's seeded random generator; consumes exactly one
                without-replacement draw of ``min(k, N − 1)`` opponents per
                agent, in agent order (no draw at all when N ≤ 1).

        Returns:
            An iterator over N·min(k, N−1) (initiator, opponent) pairs, in
            draw order.
        """
        pairs: list[tuple[Agent, Agent]] = []
        for initiator in agents:
            others = [agent for agent in agents if agent is not initiator]
            drawn = rng.choice(len(others), size=min(self._k, len(others)), replace=False)
            pairs.extend((initiator, others[index]) for index in drawn)
        return iter(pairs)


class SpatialKernel(Matcher):
    """Each agent initiates matches against k neighbours sampled by the reach kernel.

    The synchronous adapter for local interaction (M11a Phase D, spec Design
    6, #108): constructed by the engine IN PLACE of the configured matcher
    when a synchronous lattice run has ``matching.spatial_interaction`` on.
    Genuinely THIN — all sampling logic lives in
    :func:`~pdsim.core.structure.neighbourhood_sample` (the one Phase A
    primitive every locality shares); this class is plumbing: it walks the
    agents, hands the primitive each focal's site, and maps the returned
    sites back to agents.

    Two behaviours are inherited from :class:`RandomK` DELIBERATELY — both
    look like defects on first reading and neither is:

    1. **No deduplication under the default** (#57): agent A can draw B
       while B draws A, so a pair can meet twice in one generation. Kept so
       income statistics stay comparable to the well-mixed baseline (and
       with it the existing ``len(agent._histories)`` sharp edge,
       unchanged). Since M11b Phase C the doubling has a switch:
       ``matching.encounter_mode = "per_pair"`` collapses duplicate
       UNORDERED pairs AFTER all draws complete (#166/#174 — see
       :meth:`pairings`); the default ``"per_initiator"`` leaves the pair
       list untouched.
    2. **Clamp, don't raise** (#81): when k exceeds the number of reachable
       occupied neighbours, the agent simply plays the neighbours that
       exist — a corner cell with 3 neighbours under bounded Moore plays 3
       matches at k = 8. Geometry, not a misconfiguration.

    RNG contract (spec Design 6, the resolved draw-unconditionally fork):
    exactly ONE ``neighbourhood_sample`` call per focal agent, in ascending
    agent-id order, EVEN when k ≥ neighbourhood size and the outcome is
    forced — the stream position is predictable from the config alone,
    never from how full a neighbourhood happened to be. The one
    data-conditional corner is the primitive's own existing contract: with
    an EMPTY eligible set (an isolated focal — zero occupied neighbours in
    reach) it returns an empty tuple BEFORE drawing, so an isolated agent
    plays zero matches and consumes zero RNG — correct, and announced by
    the founding-isolation readout rather than crashed on.
    """

    def __init__(
        self,
        structure: Structure,
        occupancy: Occupancy,
        radius: int | None,
        decay: float,
        k: int,
        encounter_mode: str = "per_initiator",
    ) -> None:
        """Create the kernel adapter over a run's structure and occupancy.

        Args:
            structure: The run's immutable topology (supplies the metric).
            occupancy: The run's LIVE site bookkeeping, held by reference —
                pairings always read the occupancy as it is at the moment
                they are drawn, so births and deaths between generations
                are seen automatically.
            radius: ``structure.interaction_radius`` — support radius R of
                the interaction kernel; ``None`` means unlimited reach.
            decay: ``structure.interaction_decay`` — β, how steeply partner
                preference falls with distance inside the radius.
            k: ``matching.opponents_per_agent`` — how many partners each
                focal agent draws (clamped to the reachable occupied
                neighbours by the primitive).
            encounter_mode: ``matching.encounter_mode`` (M11b Phase C,
                #166) — ``"per_initiator"`` (the default: every drawn
                match plays, the historical behaviour) or ``"per_pair"``
                (duplicate unordered pairs collapse after the draws, so
                each pair plays at most once per generation).
        """
        self._structure = structure
        self._occupancy = occupancy
        self._radius = radius
        self._decay = decay
        self._k = k
        self._encounter_mode = encounter_mode

    def pairings(
        self, agents: Sequence[Agent], rng: np.random.Generator
    ) -> Iterator[tuple[Agent, Agent]]:
        """Draw every pairing up front, then yield them in draw order.

        Eager like :meth:`RandomK.pairings`, and for the same #57 reason:
        the whole pairing sequence is drawn before the first match plays,
        so pairing draws never interleave with in-match draws. Per focal
        agent — walked in ascending id order (spec Defining principle 5) —
        one :func:`~pdsim.core.structure.neighbourhood_sample` call with
        ``size = k`` and ``eligible`` = the occupied sites minus the
        focal's own; the drawn sites map back to agents through the
        occupancy. Nothing else.

        **Encounter-mode contract** (M11b Phase C, #166(b)/#174): the
        partner draws above are made EXACTLY the same in both modes — same
        calls, same order, same random-number consumption — and under
        ``"per_pair"`` deduplication applies to the RESULTING pair list,
        after ALL draws complete and before ANY match is played: duplicate
        UNORDERED pairs collapse, the first occurrence in pair-list order
        survives (keeping its initiator seat — since focals walk in
        ascending id order, in a forced-draw regime every survivor's
        initiator is the lower id of its pair, #174(c)), and later
        duplicates are dropped. The knob changes WHICH matches run, never
        how randomness is consumed; under the default ``"per_initiator"``
        the drawn list is returned untouched — not rebuilt, not reordered.

        Args:
            agents: The current population (any order; walked ascending).
            rng: The run's seeded generator; consumes exactly one kernel
                draw per focal agent whose eligible set is non-empty (in
                BOTH encounter modes — deduplication draws nothing).

        Returns:
            An iterator over the (initiator, partner) pairs, in draw order
            (under ``"per_pair"``, minus the dropped later duplicates).
        """
        by_id = {agent.agent_id: agent for agent in agents}
        pairs: list[tuple[Agent, Agent]] = []
        for focal in sorted(agents, key=lambda agent: agent.agent_id):
            origin = self._occupancy.site_of(focal.agent_id)
            assert origin is not None  # every living agent holds a site
            drawn = neighbourhood_sample(
                self._structure,
                origin,
                radius=self._radius,
                decay=self._decay,
                size=self._k,
                rng=rng,
                eligible=self._occupancy.occupied_sites() - {origin},
            )
            for site_id in drawn:
                partner_id = self._occupancy.agent_at(site_id)
                assert partner_id is not None  # eligible sites are occupied
                pairs.append((focal, by_id[partner_id]))
        if self._encounter_mode == "per_pair":
            # Dedup AFTER all draws (#166(b)): consumes no RNG, first
            # occurrence survives with its initiator seat.
            seen: set[frozenset[AgentId]] = set()
            survivors: list[tuple[Agent, Agent]] = []
            for initiator, partner in pairs:
                key = frozenset((initiator.agent_id, partner.agent_id))
                if key not in seen:
                    seen.add(key)
                    survivors.append((initiator, partner))
            return iter(survivors)
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
