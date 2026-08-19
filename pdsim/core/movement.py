"""Agent movement: the ``MovementRule`` interface and the kernel walk (M11b Phase B).

DESIGN §2.12 and §6.3; DECISIONS #165 (the schedule and the parameters, ruled
in the design layer) and #172 (this phase as built). Movement is the third
use of the soft reach kernel (#105): after "where a child lands" (the birth
pair) and "who you play" (the interaction pair), M11b adds "where you may
walk to" — ``movement.radius`` / ``movement.decay`` — over the SAME
structure, drawn through the SAME primitive
(:func:`~pdsim.core.structure.neighbourhood_sample`) as every other locality
draw, reading the #156 cached reach.

**Movement is a population-dynamics concern, orthogonal to strategies**
(#46): strategies never decide movement in the base design. The engines
call this module at their movement step; the strategy roster does not know
it exists.

The interface (:class:`MovementRule`, an abstract base class — the project's
#46 convention for pluggable mechanisms) answers ONE question: given a
mover's current site and the live occupancy, where does it go — a
destination site, or ``None`` when no move is possible. The single shipped
implementation is :class:`KernelWalk`, the kernel-weighted random walk.
Success-driven relocation (move when unhappy) and walk-away rules (leave a
defecting neighbourhood) are FUTURE implementations of this same interface —
named here so the seam is visible, deliberately not built (spec Out of
scope). Such rules will need the mover's state (energy, last scores) as an
extra input; that is an interface extension for the phase that builds them
(DESIGN first, DECISIONS entry, then code — hard rule 6), not something this
phase pre-empts.

The occupancy semantics, pinned here in one place (#172):

- **Candidates are the sites EMPTY at draw time.** The mover's own origin is
  occupied by the mover, so it is never a candidate: a move is a RELOCATION,
  never a possible null move.
- **The origin is vacated only AFTER the destination is drawn** — see
  :func:`attempt_move`. Under the synchronous mover permutation this means
  an earlier-permuted mover's vacated origin IS available to a later mover
  (chains can form), while every agent gets at most ONE attempt per period.
- **A blocked move** — no empty site within walk reach — fails in place, and
  the primitive returns empty BEFORE drawing, so a blocked mover consumes no
  destination RNG (the #133(b) data-conditional shape). The engines count it
  as ONE undivided number (``blocked_moves``): a walled-in mover and one
  whose last reachable site an earlier-permuted mover took are the same
  fact for the readout — deliberately unlike the birth vocabulary's
  blocked/infeasible split (#171).

The GATE (:func:`movement_active`) is decided from the config once per run:
movement is live only under lattice + energy economy — synchronously the
``EconomyDynamics`` lattice half, asynchronously ``variable_n`` + lattice —
and only while ``movement.rate > 0``. ``fixed_n`` is excluded because its
grid is fully occupied by construction (N = site count, #106/#134), so every
move would be blocked; imitation has no demographic boundary to host the
step. Every movement draw sits behind this gate (the #80/#99 active-flag
idiom), which is what lets a movement-off or non-gated run consume ZERO
additional draws — every pre-existing golden master passes untouched.

A functional-programming note (a learning thread of this project): the
walk is a small COMPOSITION — the pure enumeration
(:meth:`~pdsim.core.structure.Structure.reach`), the pure emptiness filter
(:meth:`~pdsim.core.occupancy.Occupancy.empty_sites`), one seeded draw. The
rule object holds only its two parameters; all run state stays in the
occupancy the engine owns.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from pdsim.config.experiment import ExperimentConfig
from pdsim.core.occupancy import Occupancy
from pdsim.core.structure import SiteId, neighbourhood_sample

__all__ = [
    "KernelWalk",
    "MovementRule",
    "attempt_move",
    "build_movement_rule",
    "movement_active",
]


class MovementRule(ABC):
    """Where a mover goes: the pluggable movement interface (#46, #165).

    ``ABC`` + ``@abstractmethod`` (the project's convention for pluggable
    mechanisms — selection rules, matchers, games): subclasses MUST
    implement :meth:`destination`, and the base class cannot be
    instantiated by mistake.

    A rule decides only the DESTINATION. Whether an agent attempts a move
    at all (the ``movement.rate`` coin), in what order movers are iterated
    (the synchronous permutation), and how the occupancy is updated
    (:func:`attempt_move`) are the engines' business — held outside the
    rule so a future rule cannot accidentally change the RNG contract by
    drawing its own coins.
    """

    @abstractmethod
    def destination(
        self, origin: SiteId, occupancy: Occupancy, rng: np.random.Generator
    ) -> SiteId | None:
        """Choose where a mover standing at ``origin`` goes.

        Args:
            origin: The mover's CURRENT site (occupied by the mover, so
                never itself a candidate).
            occupancy: The live occupancy — read for the empty sites and
                for the structure (topology and the reach cache).
            rng: The run's seeded generator. A rule consumes RNG only when
                at least one destination is drawable — the
                data-conditional shape every locality draw shares.

        Returns:
            The destination site id, or ``None`` when no move is possible
            (the mover is BLOCKED and stays where it is).
        """


class KernelWalk(MovementRule):
    """The kernel-weighted random walk — M11b's one shipped movement rule.

    One :func:`~pdsim.core.structure.neighbourhood_sample` call over the
    EMPTY sites within ``radius`` of the mover's current site, weighted
    ``exp(−decay·d)`` — the third parameterisation of the #105 reach kernel
    (``movement.radius`` / ``movement.decay``), through the same primitive
    and the same #156 cached reach as the birth and interaction draws. At
    radius 1 the walk is a hop to an adjacent empty cell; ``None`` radius
    with decay 0 is a jump to a uniformly random empty site anywhere.
    """

    def __init__(self, radius: int | None, decay: float) -> None:
        """Parameterise the walk.

        Args:
            radius: The support radius R of the walk — how far a single move
                may carry the mover; ``None`` for unlimited reach.
            decay: The decay β — how steeply nearer empty sites are
                preferred within the radius (irrelevant at radius 1, where
                every candidate sits at the same distance).

        Raises:
            ValueError: If ``radius`` is negative or ``decay`` is negative
                (the same rules the kernel primitive enforces, checked
                early so a bad rule fails at construction, not mid-run).
        """
        if radius is not None and radius < 0:
            raise ValueError(f"radius must be non-negative or None (unlimited), got {radius}.")
        if decay < 0:
            raise ValueError(f"decay must be non-negative, got {decay}.")
        self._radius = radius
        self._decay = decay

    @property
    def radius(self) -> int | None:
        """The walk's support radius (``None`` = unlimited).

        Returns:
            The radius given at construction.
        """
        return self._radius

    @property
    def decay(self) -> float:
        """The walk's decay β.

        Returns:
            The decay given at construction.
        """
        return self._decay

    def destination(
        self, origin: SiteId, occupancy: Occupancy, rng: np.random.Generator
    ) -> SiteId | None:
        """Draw one empty site within walk reach of ``origin``.

        The eligible set is the occupancy's empty sites AT THIS MOMENT —
        the origin is occupied and therefore excluded, and under the
        synchronous permutation an earlier mover's freshly vacated origin
        is already empty and therefore included. When nothing in reach is
        empty the primitive returns an empty tuple BEFORE drawing (no RNG
        consumed) and the mover is blocked.

        Args:
            origin: The mover's current site.
            occupancy: The live occupancy.
            rng: The run's seeded generator.

        Returns:
            The drawn destination, or ``None`` when blocked.
        """
        drawn = neighbourhood_sample(
            occupancy.structure,
            origin,
            radius=self._radius,
            decay=self._decay,
            size=1,
            rng=rng,
            eligible=occupancy.empty_sites(),
        )
        return drawn[0] if drawn else None


def attempt_move(
    rule: MovementRule, agent_id: int, occupancy: Occupancy, rng: np.random.Generator
) -> bool:
    """Make one move attempt for one agent, updating the occupancy on success.

    The vacate-AFTER-draw contract lives here, in the one function both
    engines call: the destination is drawn while the mover still occupies
    its origin (so the origin is never a candidate and the candidate set is
    exactly "the sites empty right now"); only on success is the origin
    vacated and the destination occupied — one relocation, both mappings
    updated together by the occupancy's own methods.

    Args:
        rule: The movement rule deciding the destination.
        agent_id: The mover.
        occupancy: The live occupancy (mutated on success).
        rng: The run's seeded generator.

    Returns:
        ``True`` if the agent moved, ``False`` if it was blocked (no empty
        site in walk reach — it stays where it is; the caller counts it).

    Raises:
        KeyError: If the agent occupies no site (every living agent on a
            lattice does — a programming error, not a run outcome).
    """
    origin = occupancy.site_of(agent_id)
    if origin is None:
        raise KeyError(f"Agent {agent_id} occupies no site; it cannot move.")
    destination = rule.destination(origin, occupancy, rng)
    if destination is None:
        return False
    occupancy.remove_agent(agent_id)
    occupancy.occupy(destination, agent_id)
    return True


def movement_active(config: ExperimentConfig) -> bool:
    """The movement gate: does this run move agents at all? (#165, #172).

    Live only under lattice + energy economy with a positive rate:

    - synchronous clock: ``reproduction_mode = energy_economy`` (the
      ``EconomyDynamics`` lattice half — imitation has no demographic
      boundary to host the step);
    - asynchronous clock: ``async_population = variable_n`` (``fixed_n`` is
      excluded — its grid is full by construction, N = site count, so every
      move would be blocked);
    - both: ``structure.kind = lattice`` (a well-mixed world has nowhere to
      go) and ``movement.rate > 0`` (rate 0 IS movement off).

    Tournament mode never moves anything (structure is ignored there
    wholesale). This one predicate is read by both engines at construction
    AND by the app's readout visibility, so the gate cannot drift between
    the engine and the panel.

    Args:
        config: The run's validated config.

    Returns:
        ``True`` exactly when the movement step runs and its draws exist.
    """
    if config.mode != "evolution" or config.structure.kind != "lattice":
        return False
    if config.movement.rate <= 0:
        return False
    dynamics = config.dynamics
    if dynamics.time_model == "asynchronous":
        return dynamics.async_population == "variable_n"
    return dynamics.reproduction_mode == "energy_economy"


def build_movement_rule(config: ExperimentConfig) -> MovementRule:
    """Build the run's movement rule from its config.

    M11b ships one rule, so there is no ``movement.rule`` choice parameter
    to dispatch on yet; when a second rule lands it gets a registry entry
    and this function becomes the dispatch (the ``build_matcher`` /
    ``build_selection_rule`` pattern).

    Args:
        config: The run's validated config.

    Returns:
        A :class:`KernelWalk` over ``movement.radius`` / ``movement.decay``.
    """
    return KernelWalk(radius=config.movement.radius, decay=config.movement.decay)
