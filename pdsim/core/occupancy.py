"""Occupancy: who sits where (DESIGN §2.12; M11a Phase B, spec Design 3).

:class:`~pdsim.core.structure.Structure` says which sites exist and how far
apart they are; ``Occupancy`` says which agent is in which site *right now*.
The split is architectural, not stylistic (spec Design 3):

- the **structure is immutable** — derived once from the config, never
  changed during a run, so it can be shared, cached, and (in Phase E)
  precomputed;
- the **occupancy is mutable per-run state owned by the dynamics**, exactly
  like the population list.

Keeping them apart is the difference between M19 writing a *builder* and M19
writing an *engine*: a new site-set shape (municipalities, raster cells) has
to define sites and distances, and inherits all of the placement bookkeeping
below unchanged.

**Phase B status.** The occupancy is written once, at founding, and then
only read — by the grid renderer and by the recorder. Births and deaths do
not touch it yet: :meth:`Occupancy.vacate` and the rest of the mutation path
exist and are tested, but no engine event calls them until Phase C adds
local birth. That is this phase's exit condition — structure exists and is
visible, and nothing reads it.

A note on the capacity check (forward-guard 2, spec Design 12): the
exclusivity test is written as ``occupants < capacity`` against the site's
own capacity field rather than as "is this site empty". Capacity is pinned
at 1 for all of M11, so the two are the same test today — but writing it the
second way would make M19's per-site capacity a migration of this seam
instead of a parameter change.
"""

from __future__ import annotations

from pdsim.core.structure import SiteId, Structure

__all__ = ["Occupancy"]


class Occupancy:
    """Mutable bookkeeping of which agent occupies which site.

    Two mappings are kept mutually consistent at all times — site → agent and
    agent → site. Every mutation updates both, and every read is O(1) in
    either direction, because the placement code needs "who is in this site"
    and the recorder needs "where is this agent" equally often.

    The structure is held (not copied) so the occupancy can validate site ids
    and read each site's capacity without every caller passing the topology
    back in. That does not blur the split above: the structure stays an
    immutable value shared by anyone who wants it, and all the mutable state
    lives here.
    """

    def __init__(self, structure: Structure) -> None:
        """Create an empty occupancy over a structure.

        Args:
            structure: The topology whose sites may be occupied. Held by
                reference; never mutated.
        """
        self._structure = structure
        self._agent_by_site: dict[SiteId, int] = {}
        self._site_by_agent: dict[int, SiteId] = {}

    @property
    def structure(self) -> Structure:
        """The topology this occupancy is defined over.

        Returns:
            The structure passed at construction.
        """
        return self._structure

    def __len__(self) -> int:
        """Return how many sites are currently occupied.

        Returns:
            The number of occupied sites, which under capacity 1 equals the
            number of placed agents.
        """
        return len(self._agent_by_site)

    def occupy(self, site_id: SiteId, agent_id: int) -> None:
        """Place an agent in a site.

        Args:
            site_id: The site to fill.
            agent_id: The agent moving in.

        Raises:
            KeyError: If ``site_id`` names no site in the structure.
            ValueError: If the site is already at capacity, or the agent is
                already placed somewhere. Both are programming errors rather
                than user errors — an agent occupies exactly one site, and a
                site holds at most :data:`~pdsim.core.structure.SITE_CAPACITY`
                agents — so they raise rather than silently relocating.
        """
        site = self._structure.site(site_id)
        occupants = 1 if site_id in self._agent_by_site else 0
        if not occupants < site.capacity:
            raise ValueError(
                f"Site {site_id} already holds agent {self._agent_by_site[site_id]} "
                f"(capacity {site.capacity}); it cannot also hold agent {agent_id}."
            )
        if agent_id in self._site_by_agent:
            raise ValueError(
                f"Agent {agent_id} already occupies site {self._site_by_agent[agent_id]}; "
                "vacate it before occupying another (agents do not move in M11a)."
            )
        self._agent_by_site[site_id] = agent_id
        self._site_by_agent[agent_id] = site_id

    def vacate(self, site_id: SiteId) -> int:
        """Empty a site and return the agent that was in it.

        Args:
            site_id: The site to empty.

        Returns:
            The id of the agent that occupied the site.

        Raises:
            KeyError: If ``site_id`` names no site in the structure, or the
                site is already empty.
        """
        self._structure.site(site_id)
        try:
            agent_id = self._agent_by_site.pop(site_id)
        except KeyError:
            raise KeyError(f"Site {site_id} is already empty; nothing to vacate.") from None
        del self._site_by_agent[agent_id]
        return agent_id

    def remove_agent(self, agent_id: int) -> SiteId:
        """Remove an agent from wherever it is, and return the freed site.

        The death-side counterpart of :meth:`vacate`: deaths know the agent,
        placement knows the site, and forcing either caller to look the other
        one up first is how the two mappings drift apart.

        Args:
            agent_id: The agent to remove.

        Returns:
            The site id the agent vacated.

        Raises:
            KeyError: If the agent occupies no site.
        """
        try:
            site_id = self._site_by_agent.pop(agent_id)
        except KeyError:
            raise KeyError(f"Agent {agent_id} occupies no site; nothing to remove.") from None
        del self._agent_by_site[site_id]
        return site_id

    def site_of(self, agent_id: int) -> SiteId | None:
        """Return the site an agent occupies, if it occupies one.

        Args:
            agent_id: The agent to look up.

        Returns:
            The site id, or ``None`` when the agent is not placed. ``None``
            rather than an exception because this is exactly what the
            recorder asks of every agent in a well-mixed run.
        """
        return self._site_by_agent.get(agent_id)

    def agent_at(self, site_id: SiteId) -> int | None:
        """Return the agent occupying a site, if any.

        Args:
            site_id: The site to look up.

        Returns:
            The occupant's agent id, or ``None`` if the site is empty.

        Raises:
            KeyError: If ``site_id`` names no site in the structure.
        """
        self._structure.site(site_id)
        return self._agent_by_site.get(site_id)

    def is_occupied(self, site_id: SiteId) -> bool:
        """Report whether a site currently holds an agent.

        Args:
            site_id: The site to test.

        Returns:
            True if occupied, False if empty.

        Raises:
            KeyError: If ``site_id`` names no site in the structure.
        """
        return self.agent_at(site_id) is not None

    def occupied_sites(self) -> frozenset[SiteId]:
        """Return every occupied site id.

        Returns:
            A frozenset of occupied site ids — the shape
            :func:`~pdsim.core.structure.neighbourhood_sample` takes as its
            ``eligible`` argument for the interaction and victim draws.
        """
        return frozenset(self._agent_by_site)

    def empty_sites(self) -> frozenset[SiteId]:
        """Return every empty site id.

        Returns:
            A frozenset of unoccupied site ids — the ``eligible`` set for
            the placement draw (Phase C).
        """
        return frozenset(self._structure.site_ids) - frozenset(self._agent_by_site)

    def empty_sites_within(self, origin: SiteId, radius: int | None) -> tuple[SiteId, ...]:
        """Return the empty sites within reach of an origin, ascending by id.

        This is the read the local placement gate is built on (Design 4): a
        parent can only put a child somewhere there is somewhere to put it.
        The ordering is ascending site id, per the determinism rule — every
        candidate list is built in id order before any draw touches it.

        Args:
            origin: The site reach is measured from (never itself a
                candidate, and in any case occupied by the parent).
            radius: Support radius R, or ``None`` for unlimited reach.

        Returns:
            The empty candidate site ids in ascending order; empty when the
            neighbourhood is full.

        Raises:
            KeyError: If ``origin`` names no site in the structure.
            ValueError: If ``radius`` is negative.
        """
        # Imported here rather than at module scope purely for readability of
        # the dependency direction: occupancy is bookkeeping over a topology,
        # and sites_within is the topology's own pure enumerator.
        from pdsim.core.structure import sites_within

        return tuple(
            site_id
            for site_id in sites_within(self._structure, origin, radius)
            if site_id not in self._agent_by_site
        )

    def sites_by_agent(self) -> dict[int, SiteId]:
        """Return a copy of the agent → site mapping.

        Returns:
            A plain dict copy, safe for the caller to keep or mutate. The
            recorder and the renderer both want the whole mapping at once
            rather than one lookup per agent.
        """
        return dict(self._site_by_agent)

    def isolated_agents(self) -> tuple[int, ...]:
        """Return the agents whose neighbouring sites are all empty.

        The Design 8 mandatory guard, computed rather than eyeballed: a
        scattered founding layout under a sparse population can leave an
        agent with no occupied neighbour at all. Such an agent plays nothing,
        earns nothing, and starves at the next boundary once local
        interaction lands — which is *correct* (it is #81's lone-survivor
        thermodynamics, locally) but bewildering to watch unexplained.

        Returns:
            The ids of agents with zero occupied neighbours, ascending.
        """
        isolated = [
            agent_id
            for agent_id, site_id in self._site_by_agent.items()
            if not any(
                neighbour in self._agent_by_site
                for neighbour in self._structure.neighbours(site_id)
            )
        ]
        return tuple(sorted(isolated))
