"""Pure helpers for the energy-economy boundary (M10a, DESIGN §2.10).

The arithmetic of the growth economy, kept out of the generation loop so each
rule is unit-testable on its own: the energy ledger, the mortality curve, the
capacity gate, the feasibility filter in front of it (M11b Phase A), the
structural placement gate, and founder age staggering.
Headless (hard rule 4) and side-effect-free — every function here is a pure
function of its arguments (a functional-programming note: the boundary in
``dynamics.py`` is a pipeline of these, which is what makes its nine steps
individually checkable).

Companion reading: `docs/specs/M10a-growth-economy.md` (the boundary
sequence) and `docs/explainers/M10-growth-economy-explainer.md` (the science).
"""

from __future__ import annotations

from collections.abc import Sequence

from pdsim.config.experiment import DynamicsConfig
from pdsim.core.agent import Agent
from pdsim.core.occupancy import Occupancy


def energy_update(
    carried_in: float, raw_score: float, matches_played: int, dynamics: DynamicsConfig
) -> float:
    """Apply one generation's energy ledger to one agent (M10a step 3).

    The ledger: carried-in energy earns capital returns, the generation's
    raw PD score is income, and two costs are charged — the basic living
    cost (existence) and the engagement cost (per match actually played).

    Args:
        carried_in: Energy the agent carried into this generation.
        raw_score: The agent's raw PD score for this generation.
        matches_played: How many matches the agent took part in this
            generation (initiated + drawn — the Task 0a tally).
        dynamics: The run's dynamics config (reads ``capital_return_rate``,
            ``basic_living_cost``, ``engagement_cost``).

    Returns:
        The agent's end-of-generation energy — the frozen snapshot value
        deaths and births are computed against.
    """
    return (
        carried_in * (1.0 + dynamics.capital_return_rate)
        + raw_score
        - dynamics.basic_living_cost
        - dynamics.engagement_cost * matches_played
    )


def mortality_probability(age: int, dynamics: DynamicsConfig) -> float:
    """The chance an agent of a given age dies at this boundary (M10a step 4).

    A hard age cap is certain death; below it, the hazard climbs
    geometrically with age (the Gompertz-style curve): ``base_hazard ×
    senescence_factor ** age``, capped at 1.

    Args:
        age: The agent's age in completed generations.
        dynamics: The run's dynamics config (reads ``max_age``,
            ``base_hazard``, ``senescence_factor`` — the latter always a
            resolved plain number by config time).

    Returns:
        A probability in [0, 1].
    """
    if dynamics.max_age > 0 and age >= dynamics.max_age:
        return 1.0
    return min(1.0, dynamics.base_hazard * dynamics.senescence_factor**age)


def age_mortality_active(dynamics: DynamicsConfig) -> bool:
    """Whether the mortality sub-phase runs at all (M10a step 4 gate).

    This gate — not any individual hazard value — is what decides whether
    mortality coins are drawn: whenever it is True, exactly one coin is
    consumed per living agent per boundary, even in the deterministic
    corners (p = 0.0 or 1.0), so the RNG stream depends only on this flag
    and the population size.

    Args:
        dynamics: The run's dynamics config.

    Returns:
        True if any of the mortality trio is switched on.
    """
    return dynamics.base_hazard > 0 or dynamics.senescence_factor != 1.0 or dynamics.max_age > 0


def admit_births(eligible: Sequence[Agent], slots: int) -> list[Agent]:
    """The CAPACITY gate: choose which eligible parents get a birth slot.

    Admission is by energy priority — sort by ``(energy DESC, agent_id
    ASC)`` and take the first ``slots``. Deterministic and RNG-FREE: a
    deliberate choice over a random lottery, which would inject fresh RNG
    into the birth phase for no scientific gain. NOTE: this decides only
    *the set* of parents; the birth loop then iterates that set in
    parent-id order (the RNG-reproducibility contract) — two distinct
    orderings, kept separate on purpose.

    Args:
        eligible: Parents at or above the reproduction threshold.
        slots: Free seats under the carrying capacity (may be 0).

    Returns:
        The admitted parents, in energy-priority order (richest first,
        ties broken by ascending id).
    """
    ranked = sorted(eligible, key=lambda agent: (-agent.energy, agent.agent_id))
    return ranked[: max(0, slots)]


def feasible_parents(
    eligible: Sequence[Agent], occupancy: Occupancy, birth_radius: int | None
) -> list[Agent]:
    """The FEASIBILITY filter in front of the capacity gate (M11b Phase A, #164).

    A parent is *feasible* when at least one EMPTY site lies within its
    birth reach — the same support the placement draw samples
    (``Structure.reach`` at the birth radius, filtered to empty sites), so
    "feasible" means exactly "the placement draw would return a site if it
    ran now". Under the synchronous energy economy on a lattice the capacity
    gate ranks and seats ONLY feasible parents: a seat is an economic
    licence to breed, and #153(c)'s Filling Grid freeze showed what happens
    when licences go to parents who physically cannot use them — the rich
    walled-in interior consumed the whole quota every generation while the
    poorer rim, beside empty sites, never ranked inside it. With this
    filter a seated parent always has somewhere to place, so at least one
    admitted parent places every generation and a permanent freeze of that
    kind is impossible.

    Pure and RNG-FREE: a read of live occupancy through the memoised reach
    cache (#156), consuming zero generator calls — pinned by the counting
    wrapper. The order of the returned list is the caller's order (this is
    a filter, not a ranking; ``admit_births`` ranks). Callers OFF the
    three-way gate (well-mixed, imitation, the asynchronous clock) never
    call it — the asynchronous engine keeps its undivided blocked count
    (DECISIONS #171, ruling R1).

    Args:
        eligible: Parents at or above the reproduction threshold, in any
            order.
        occupancy: The live occupancy at the moment of assessment — the same
            snapshot the slot ration reads (post-death under
            ``death_first``, pre-death under ``birth_first``).
        birth_radius: The birth kernel's support radius R, or ``None`` for
            unlimited reach.

    Returns:
        The eligible parents that have at least one empty site within
        reach, in the input order.
    """
    feasible: list[Agent] = []
    for agent in eligible:
        origin = occupancy.site_of(agent.agent_id)
        assert origin is not None  # every living agent holds a site
        if occupancy.empty_sites_within(origin, birth_radius):
            feasible.append(agent)
    return feasible


def place_offspring(population: Sequence[Agent], parent: Agent) -> bool:
    """The STRUCTURAL gate: can this parent's child be placed in the world?

    In M10a's well-mixed world there is no structure, so placement always
    succeeds — this is the fully-connected corner of the model. The
    function is named NOW so M11's population structure can swap in a
    neighbourhood-aware body (a child needs an adjacent free site) without
    touching the birth loop. Deliberately not an ABC (hard rule 6: M11
    updates DESIGN first, then generalises). The birth loop must check this
    gate BEFORE paying the stake — pay-then-place would charge a blocked
    parent for a child never born.

    Args:
        population: The current (post-cull) population.
        parent: The admitted parent about to reproduce.

    Returns:
        Always True in the well-mixed model.
    """
    return True


def staggered_founder_ages(n: int, max_age: int) -> list[int]:
    """Founder ages at demographic steady state (M10a construction).

    A fixed-lifespan population breeding at a steady rate has a uniform age
    distribution in equilibrium, so founders get ages ``0, 1, ..., max_age
    − 1, 0, 1, ...`` instead of all starting at 0 — which would be a
    colony-ship moment where the entire founding cohort dies at once at
    generation ``max_age``. Automatic, with no parameter (a synchronized
    cohort is a possible future option). Without an age cap there is
    nothing to stagger against and everyone starts at 0.

    Args:
        n: Number of founders.
        max_age: The hard age cap (0 = no cap).

    Returns:
        One age per founder, in founder order.
    """
    if max_age > 0:
        return [i % max_age for i in range(n)]
    return [0] * n
