"""Experiment configuration: validated pydantic models + YAML load/save.

An :class:`ExperimentConfig` is the complete description of one simulation run.
It is what the UI builds, what the engine consumes, and what gets saved next to
every run's results so the run can be replayed exactly (hard rule 8).

Design notes (see ``docs/DESIGN.md`` §3 and DECISIONS #15/#18):

* **The registry stays the single source of truth.** No default or range is
  written in this module: every field pulls its default from the Parameter
  Registry and is re-validated against its :class:`~pdsim.config.registry.ParameterSpec`.
* **Configs are immutable** (``frozen=True``): a config is a *value* describing
  a run, not a bag of state — nothing can quietly change it mid-run. (This is
  the same functional-programming idea as the frozen ``ParameterSpec``.)
* **Unknown keys are rejected** (``extra="forbid"``): a typo'd key in a YAML
  file fails loudly instead of being silently ignored, which would otherwise
  make a run subtly different from the config the user thought they wrote.

Why pydantic and not a plain dataclass? A dataclass just *stores* what you give
it; a pydantic model *validates* at construction — types are coerced and
checked, and our validators run — so an ``ExperimentConfig`` that exists is an
``ExperimentConfig`` that is valid.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, ClassVar, NamedTuple, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.fields import FieldInfo

from pdsim.config import registry

__all__ = [
    "DynamicsConfig",
    "ExperimentConfig",
    "GameConfig",
    "MatchConfig",
    "MatchingConfig",
    "OutputConfig",
    "PayoffAdditivity",
    "PopulationConfig",
    "StructureConfig",
    "effective_neighbour_count",
    "load_config",
    "payoff_additivity",
    "resolve_carrying_capacity",
    "resolve_initial_energy",
    "resolve_lattice_dimensions",
    "resolve_senescence_factor",
    "save_config",
]


def resolve_initial_energy(initial_energy: float | None, offspring_stake: float) -> float:
    """Resolve the ``dynamics.initial_energy`` derived default (M10a).

    ``None`` means "auto": founders start with the offspring stake, so they
    begin life exactly like newborns. A pure function so the rule is
    unit-testable on its own — the config validator only *calls* it, and the
    resolved plain number is what ``save_config`` writes (hard rule 8: the
    auto rule can never retroactively change a saved run).

    Args:
        initial_energy: The configured value, or ``None`` for auto.
        offspring_stake: The configured offspring stake σ.

    Returns:
        The energy each founder starts the run with.
    """
    return offspring_stake if initial_energy is None else initial_energy


def resolve_senescence_factor(
    senescence_factor: float | None, base_hazard: float, max_age: int
) -> float:
    """Resolve the ``dynamics.senescence_factor`` derived default (M10a).

    ``None`` means "auto": when a base hazard and a maximum age are both set,
    pick the factor that makes the per-boundary death chance climb from
    ``base_hazard`` at age 0 to exactly 1.0 at ``max_age`` —
    ``(1 / base_hazard) ** (1 / max_age)``. Without both, aging has nothing
    to calibrate against and auto means "age never matters" (factor 1.0).

    Args:
        senescence_factor: The configured value, or ``None`` for auto.
        base_hazard: The configured per-boundary death chance at age 0.
        max_age: The configured hard age cap (0 = no cap).

    Returns:
        The per-generation multiplier applied to the death chance.
    """
    if senescence_factor is not None:
        return senescence_factor
    if base_hazard > 0 and max_age > 0:
        return (1.0 / base_hazard) ** (1.0 / max_age)
    return 1.0


def resolve_lattice_dimensions(
    rows: int | None, cols: int | None, population_size: int
) -> tuple[int, int]:
    """Resolve the ``structure.rows`` / ``structure.cols`` derived defaults (M11a).

    ``None`` means "auto". With BOTH blank, the grid is the most-square
    factor pair of the population size N: the pair of whole numbers whose
    product is exactly N, as close to square as possible (400 gives 20×20,
    60 gives 6×10; rows never exceed columns). A prime N factorises only as
    1×N — a single line of cells, a legitimate one-dimensional lattice that
    the app announces rather than lets look like a bug. With ONE blank, the
    blank dimension resolves to the smallest count that fits N over the
    given one (rows = 8 with N = 60 gives cols = 8, since 8×8 = 64 is the
    smallest 8-row grid holding 60 agents). With both given, they are used
    as-is.

    A pure free function — the M10a :func:`resolve_initial_energy` pattern
    (spec Design 11, extension 2) — so the parameter panel can call the same
    arithmetic at paint time ("auto → 10 × 10") and can never drift from the
    validator. The validator only *calls* it, and the resolved plain numbers
    are what ``save_config`` writes (hard rule 8: the auto rule can never
    retroactively change a saved run).

    Args:
        rows: The configured row count, or ``None`` for auto.
        cols: The configured column count, or ``None`` for auto.
        population_size: N — the founding population size the auto rule
            sizes the grid around.

    Returns:
        The resolved ``(rows, cols)`` pair, both at least 1.
    """
    if rows is None and cols is None:
        # math.isqrt (new concept) is the exact whole-number square root.
        # The largest divisor of N at or below it is the "rows" half of the
        # most-square pair; scanning downward finds it (1 always divides, so
        # the search cannot fail — for a prime N it lands exactly there).
        square_root = math.isqrt(population_size)
        best = next(d for d in range(square_root, 0, -1) if population_size % d == 0)
        return best, population_size // best
    if rows is None:
        # cols is not None here — the both-blank case returned above.
        return math.ceil(population_size / cols), cols
    if cols is None:
        return rows, math.ceil(population_size / rows)
    return rows, cols


WELL_MIXED_CAPACITY_DEFAULT = 200
"""What a blank carrying capacity resolves to when no lattice decides it.

The pre-M11a registry default, kept as the aspatial fallback so every
existing config and every untouched panel behaves exactly as before the
capacity became a derived default (hard rule 8).
"""


def resolve_carrying_capacity(carrying_capacity: int | None, site_count: int | None) -> int:
    """Resolve the ``dynamics.carrying_capacity`` derived default (M11a Phase C).

    ``None`` means "auto": on a lattice the capacity becomes the site count
    — the grid decides, the zero-effort spatial setting (#106) — and in a
    well-mixed world, where there is no grid to decide, it falls back to
    :data:`WELL_MIXED_CAPACITY_DEFAULT`. A pure free function (the #78 /
    spec Design 11 pattern) so the parameter panel can call the same
    arithmetic at paint time and can never drift from the validator; the
    resolved plain number is what ``save_config`` writes.

    Args:
        carrying_capacity: The configured value, or ``None`` for auto.
        site_count: The lattice's site count (rows × cols), or ``None``
            when the run has no lattice.

    Returns:
        The carrying capacity K the run actually uses.
    """
    if carrying_capacity is not None:
        return carrying_capacity
    if site_count is not None:
        return site_count
    return WELL_MIXED_CAPACITY_DEFAULT


def effective_neighbour_count(
    neighbourhood_shape: str, boundary: str, opponents_per_agent: int
) -> int:
    """The neighbour count an interior cell actually plays — the threshold's k.

    ``opponents_per_agent`` clamps rather than errors when it exceeds the
    neighbourhood size (#81): an interior cell has 8 neighbours on a Moore
    neighbourhood and 4 on von Neumann, so the number of matches a cell
    starts per generation under spatial interaction is
    ``min(k, interior degree)`` — and that number is the k the b/c > k
    cooperation threshold counts (M11a spec §12 readout 4).

    A pure free function on the spec Design 11 paint-time pattern, so the
    panel readout and any future validator arithmetic cannot drift. The
    ``boundary`` argument completes the readout's inputs but does not move
    the number: the interior degree is the same on a torus and a bounded
    grid — the difference is that a torus has ONLY interior cells, while a
    bounded grid's edge and corner cells clamp lower still (a corner keeps
    3 of Moore's 8), which the readout's explanation notes rather than
    averages over.

    Args:
        neighbourhood_shape: ``"moore"`` (8 neighbours) or ``"von_neumann"``
            (4 neighbours).
        boundary: ``"torus"`` or ``"bounded"`` — documented above; accepted
            so the signature states the full geometry the readout describes.
        opponents_per_agent: The configured k.

    Returns:
        ``min(opponents_per_agent, interior degree)``.
    """
    interior_degree = 8 if neighbourhood_shape == "moore" else 4
    return min(opponents_per_agent, interior_degree)


class PayoffAdditivity(NamedTuple):
    """The payoff-additivity readout's result (§12 readout 9, DECISIONS #111).

    A ``NamedTuple`` (new concept): an immutable tuple whose fields have
    names — lighter than a dataclass, and it unpacks like a plain tuple.

    Attributes:
        additive: Whether ``T − R = P − S`` holds — only then do b and c
            exist as single numbers.
        benefit: b = T − P (equivalently R − S), or ``None`` when the
            matrix is not additive.
        cost: c = T − R (equivalently P − S), or ``None`` when the matrix
            is not additive.
        ratio: b/c, or ``None`` when not additive — or when c = 0, where
            cooperating is free and the ratio is not a finite number.
    """

    additive: bool
    benefit: float | None
    cost: float | None
    ratio: float | None


def payoff_additivity(
    temptation: float, reward: float, punishment: float, sucker: float
) -> PayoffAdditivity:
    """Inspect the four payoffs for donation-game additivity (#111).

    The b/c > k threshold is derived for the DONATION GAME: a cooperator
    pays a cost c so the opponent receives a benefit b (T = b, R = b − c,
    P = 0, S = −c). Reading the cost of cooperating off a general matrix
    twice gives ``T − R`` against a cooperator and ``P − S`` against a
    defector; only when the two agree ("equal gains from switching") do b
    and c exist at all. With a non-additive matrix the ratio is AMBIGUOUS
    rather than merely inapplicable — two defensible benefits over two
    defensible costs give four different readings.

    A pure free function of the four registry values, on the spec Design 11
    paint-time resolver pattern — callable from the panel at paint time and
    from anything that later needs the same arithmetic, so displayed text
    and validator logic cannot drift.

    Args:
        temptation: T — defecting against a cooperator.
        reward: R — mutual cooperation.
        punishment: P — mutual defection.
        sucker: S — cooperating against a defector.

    Returns:
        The additivity verdict with the resolved b, c, and b/c (fields
        ``None`` where undefined).
    """
    cost_vs_cooperator = temptation - reward
    cost_vs_defector = punishment - sucker
    if not math.isclose(cost_vs_cooperator, cost_vs_defector):
        return PayoffAdditivity(additive=False, benefit=None, cost=None, ratio=None)
    benefit = temptation - punishment
    cost = cost_vs_cooperator
    ratio = benefit / cost if cost != 0 else None
    return PayoffAdditivity(additive=True, benefit=benefit, cost=cost, ratio=ratio)


def _registry_field(key: str) -> FieldInfo:
    """Build a pydantic field whose default and help text come from the registry.

    Args:
        key: Registry key, e.g. ``"game.payoff_temptation"``.

    Returns:
        A pydantic ``Field`` carrying the registry default and description
        (the description also flows into generated JSON schemas).
    """
    spec = registry.get_spec(key)
    return Field(default=spec.default, description=spec.description)


class _RegistryBackedModel(BaseModel):
    """Shared base for config models whose fields mirror registry parameters.

    Subclasses map field names to registry keys via ``_registry_keys``; the
    inherited validator below then re-checks every mapped field against its
    :class:`~pdsim.config.registry.ParameterSpec`, so ranges and choices are
    enforced from the registry alone.

    New concept — ``ClassVar``: it marks an attribute as belonging to the
    class itself rather than to instances, which is how pydantic knows
    ``_registry_keys`` is bookkeeping, not a model field.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    _registry_keys: ClassVar[dict[str, str]] = {}

    # New concept — `@model_validator(mode="after")`: a hook pydantic runs on
    # the fully-constructed model, ideal for checks that involve several
    # fields. It must return the model (`Self` is the 3.11+ way to spell
    # "an instance of whatever class this is").
    @model_validator(mode="after")
    def _check_fields_against_registry(self) -> Self:
        """Validate every mapped field against the Parameter Registry.

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If any field violates its registry spec (pydantic
                surfaces this to the caller as a ``ValidationError``).
        """
        for field_name, key in self._registry_keys.items():
            registry.get_spec(key).validate(getattr(self, field_name))
        return self


class GameConfig(_RegistryBackedModel):
    """Payoff matrix and game-shape validation toggles (``docs/DESIGN.md`` §2.1).

    Attributes:
        payoff_temptation: T — defect while the opponent cooperates.
        payoff_reward: R — both cooperate.
        payoff_punishment: P — both defect.
        payoff_sucker: S — cooperate while the opponent defects.
        enforce_pd_ordering: Require T > R > P > S (a true Prisoner's Dilemma).
        enforce_alternation_constraint: Require 2R > T + S (mutual cooperation
            beats taking turns exploiting each other).
    """

    _registry_keys: ClassVar[dict[str, str]] = {
        "payoff_temptation": "game.payoff_temptation",
        "payoff_reward": "game.payoff_reward",
        "payoff_punishment": "game.payoff_punishment",
        "payoff_sucker": "game.payoff_sucker",
        "enforce_pd_ordering": "game.enforce_pd_ordering",
        "enforce_alternation_constraint": "game.enforce_alternation_constraint",
    }

    payoff_temptation: float = _registry_field("game.payoff_temptation")
    payoff_reward: float = _registry_field("game.payoff_reward")
    payoff_punishment: float = _registry_field("game.payoff_punishment")
    payoff_sucker: float = _registry_field("game.payoff_sucker")
    enforce_pd_ordering: bool = _registry_field("game.enforce_pd_ordering")
    enforce_alternation_constraint: bool = _registry_field("game.enforce_alternation_constraint")

    @model_validator(mode="after")
    def _check_game_shape(self) -> Self:
        """Enforce whichever payoff-ordering rules are switched on.

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If an enabled ordering rule is violated. The message
                explains which toggle to disable for deliberate exploration
                of neighboring games.
        """
        t, r = self.payoff_temptation, self.payoff_reward
        p, s = self.payoff_punishment, self.payoff_sucker
        if self.enforce_pd_ordering and not (t > r > p > s):
            raise ValueError(
                f"Payoffs must satisfy T > R > P > S for a true Prisoner's Dilemma; "
                f"got T={t}, R={r}, P={p}, S={s}. Disable 'enforce_pd_ordering' to "
                "explore neighboring games (Chicken, Stag Hunt) on purpose."
            )
        if self.enforce_alternation_constraint and not (2 * r > t + s):
            raise ValueError(
                f"Payoffs must satisfy 2R > T + S so steady cooperation beats "
                f"alternating exploitation; got R={r}, T={t}, S={s}. Disable "
                "'enforce_alternation_constraint' to allow this on purpose."
            )
        return self


class MatchingConfig(_RegistryBackedModel):
    """Who plays whom each generation (``docs/DESIGN.md`` §2.4).

    Attributes:
        spatial_interaction: Whether partners are sampled from within the
            interaction radius by the reach kernel (M11a Phase D, #108)
            instead of from the whole population. Requires
            ``structure.kind = "lattice"`` (checked at the experiment
            level); while on, ``matcher`` is not consulted and
            ``opponents_per_agent`` does the work (k clamps to the
            neighbours that exist — the #81 idiom).
        matcher: Matching scheme name — ``"round_robin"`` (every pair plays
            once) or ``"random_k"`` (each agent initiates matches against k
            randomly drawn opponents). Not consulted while
            ``spatial_interaction`` is on (the DECISIONS #34 pattern).
        opponents_per_agent: k for the ``"random_k"`` scheme and for spatial
            interaction (where k at or above the neighbourhood size means
            "play all your neighbours"). Ignored — valid but without
            effect, consuming no RNG draws — under ``"round_robin"`` (the
            DECISIONS #34 ignored-parameter pattern). Must be at most
            N - 1; checked at the experiment level, where the population
            size is known.
        encounter_mode: ``"per_initiator"`` (the default: every drawn
            match plays — the historical behaviour, where two neighbours
            drawing each other play twice per generation) or ``"per_pair"``
            (duplicate pairs collapse after the draws, so each pair plays
            at most once per generation; M11b Phase C, DECISIONS #166).
            Live only while ``spatial_interaction`` is on; ignored — valid
            but without effect, consuming no RNG draws — everywhere else
            (the #34 pattern), so a pre-M11b config loads at the default
            and re-runs identically (hard rule 8).
    """

    _registry_keys: ClassVar[dict[str, str]] = {
        "spatial_interaction": "matching.spatial_interaction",
        "matcher": "matching.matcher",
        "opponents_per_agent": "matching.opponents_per_agent",
        "encounter_mode": "matching.encounter_mode",
    }

    spatial_interaction: bool = _registry_field("matching.spatial_interaction")
    matcher: str = _registry_field("matching.matcher")
    opponents_per_agent: int = _registry_field("matching.opponents_per_agent")
    encounter_mode: str = _registry_field("matching.encounter_mode")


class MatchConfig(_RegistryBackedModel):
    """Match length mode and execution noise (``docs/DESIGN.md`` §2.5-2.6).

    Attributes:
        length_mode: ``"fixed"`` (exact round count) or ``"continuation"``
            (coin-flip after each round).
        rounds_per_match: Round count used in ``"fixed"`` mode.
        continuation_probability: Per-round continue chance (w) used in
            ``"continuation"`` mode; expected match length is 1 / (1 - w).
        noise_epsilon: Chance an agent's action flips against its intention.
    """

    _registry_keys: ClassVar[dict[str, str]] = {
        "length_mode": "match.length_mode",
        "rounds_per_match": "match.rounds_per_match",
        "continuation_probability": "match.continuation_probability",
        "noise_epsilon": "match.noise_epsilon",
    }

    length_mode: str = _registry_field("match.length_mode")
    rounds_per_match: int = _registry_field("match.rounds_per_match")
    continuation_probability: float = _registry_field("match.continuation_probability")
    noise_epsilon: float = _registry_field("match.noise_epsilon")


class PopulationConfig(_RegistryBackedModel):
    """Population size, memory constraint, and initial strategy mix.

    Attributes:
        size: Number of agents (constant across generations in v1).
        memory_depth: Per-opponent history rounds a strategy may see;
            ``None`` means unlimited.
        composition: Initial population mix as a mapping of strategy machine
            name to agent count, e.g. ``{"tit_for_tat": 60, "always_defect": 40}``.
            Counts must be positive and sum to ``size``.
    """

    _registry_keys: ClassVar[dict[str, str]] = {
        "size": "population.size",
        "memory_depth": "population.memory_depth",
    }

    size: int = _registry_field("population.size")
    memory_depth: int | None = _registry_field("population.memory_depth")
    # No default: an experiment must say which strategies it starts with.
    composition: dict[str, int]

    @model_validator(mode="after")
    def _check_composition(self) -> Self:
        """Validate the strategy mix: known names, positive counts, exact sum.

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If the composition is empty, names an unknown
                strategy, contains a non-positive count, or does not sum to
                ``size``.
        """
        # Lazy import (new concept): importing inside the function, at call
        # time, instead of at the top of the module. Necessary here because
        # the modules import each other in a cycle otherwise (core.game
        # imports this module; the strategies import core.game). By the time
        # a config is *constructed*, both modules exist and the import is
        # cheap. Importing the package also runs strategy auto-discovery,
        # so the roster is guaranteed to be populated.
        from pdsim.core.strategies import all_strategy_names

        if not self.composition:
            raise ValueError(
                "population.composition must list at least one strategy with its agent count."
            )
        valid = all_strategy_names()
        unknown = sorted(name for name in self.composition if name not in valid)
        if unknown:
            raise ValueError(
                f"population.composition contains unknown strategy name(s): "
                f"{', '.join(unknown)}. Valid strategy names: {', '.join(sorted(valid))}."
            )
        for name, count in self.composition.items():
            if count < 1:
                raise ValueError(
                    f"population.composition entry {name!r} has count {count}; every listed "
                    "strategy needs at least one agent — remove the entry instead of using 0."
                )
        total = sum(self.composition.values())
        if total != self.size:
            raise ValueError(
                f"population.composition counts sum to {total}, but population.size is "
                f"{self.size}. They must match exactly."
            )
        return self


class StructureConfig(_RegistryBackedModel):
    """The shape of the world: sites, lattice geometry, boundary (M11a, §2.12).

    As of Phase D this section decides all three localities: where founding
    agents live (Phase B), where children land (Phase C — the birth kernel),
    and — while ``matching.spatial_interaction`` is on — who plays whom
    (Phase D — the interaction kernel). The well-mixed engine does not route
    through structure code at all, which is what keeps every pre-M11a run
    byte-identical (spec Defining principle 1).

    Attributes:
        kind: ``"well_mixed"`` (the classic aspatial world, the default) or
            ``"lattice"`` (a rectangular grid of exclusive sites).
        rows: Lattice row count. ``None`` in the raw input means "auto =
            most-square factor pair of the population size" and is resolved
            to a plain number at experiment validation (never stored as
            null — hard rule 8; see :func:`resolve_lattice_dimensions`).
            ``None`` survives only in a standalone-built section, where no
            population size is in sight.
        cols: Lattice column count; same auto rule as ``rows``.
        neighbourhood_shape: ``"moore"`` (8 neighbours; Chebyshev distance)
            or ``"von_neumann"`` (4 neighbours; Manhattan distance). The
            shape IS the grid's distance metric.
        boundary: ``"torus"`` (edges wrap; uniform degree) or ``"bounded"``
            (hard edges; corners have fewer neighbours).
        initial_layout: How founding agents are arranged on the grid — one
            of the seven values in
            :data:`~pdsim.core.layouts.LAYOUT_CHOICES`. Arrangement only:
            the per-strategy counts are already resolved (#67).
        layout_file: Path to a hand-authored layout file, read only under
            ``initial_layout = "from_file"`` and ``None`` otherwise.
        birth_radius: Support radius R of the birth kernel (M11a Phase C):
            how far from its parent a newborn can land. ``None`` means
            unlimited reach. Under ``fixed_n`` this pair defines the set
            of competitors for a freed site instead (spec Design 7).
        birth_decay: Decay β of the birth kernel — how steeply placement
            prefers sites closer to the parent. Irrelevant at R = 1.
        placement_contest: Who places first when several synchronous births
            contend for neighbourhood room — ``"random"`` (one shuffle of
            the admitted parents, Hammond–Axelrod's reproduction order) or
            ``"energy_priority"`` (richest places first). Consumed only
            under synchronous + lattice + ``energy_economy`` (#107).
        interaction_radius: Support radius R of the interaction kernel
            (M11a Phase D): how far away a match partner can be. ``None``
            means unlimited reach. Consumed only while
            ``matching.spatial_interaction`` is on.
        interaction_decay: Decay β of the interaction kernel — how steeply
            partner choice prefers closer agents. Irrelevant at R = 1.
            Consumed only while ``matching.spatial_interaction`` is on.
    """

    _registry_keys: ClassVar[dict[str, str]] = {
        "kind": "structure.kind",
        "rows": "structure.rows",
        "cols": "structure.cols",
        "neighbourhood_shape": "structure.neighbourhood_shape",
        "boundary": "structure.boundary",
        "initial_layout": "structure.initial_layout",
        "layout_file": "structure.layout_file",
        "birth_radius": "structure.birth_radius",
        "birth_decay": "structure.birth_decay",
        "placement_contest": "structure.placement_contest",
        "interaction_radius": "structure.interaction_radius",
        "interaction_decay": "structure.interaction_decay",
    }

    kind: str = _registry_field("structure.kind")
    rows: int | None = _registry_field("structure.rows")
    cols: int | None = _registry_field("structure.cols")
    neighbourhood_shape: str = _registry_field("structure.neighbourhood_shape")
    boundary: str = _registry_field("structure.boundary")
    initial_layout: str = _registry_field("structure.initial_layout")
    layout_file: str | None = _registry_field("structure.layout_file")
    birth_radius: int | None = _registry_field("structure.birth_radius")
    birth_decay: float = _registry_field("structure.birth_decay")
    placement_contest: str = _registry_field("structure.placement_contest")
    interaction_radius: int | None = _registry_field("structure.interaction_radius")
    interaction_decay: float = _registry_field("structure.interaction_decay")

    @model_validator(mode="after")
    def _check_layout_file(self) -> Self:
        """Require a path when the layout is read from a file.

        The converse is deliberately NOT an error: a path left behind after
        switching the layout away from ``from_file`` is simply ignored, the
        same idiom as ``match.continuation_probability`` under a fixed match
        length. Only the missing-path direction can silently produce a run
        that is not the one the user asked for.

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If ``initial_layout`` is ``"from_file"`` without a
                ``layout_file``.
        """
        if self.initial_layout == "from_file" and not self.layout_file:
            raise ValueError(
                "structure.initial_layout is 'from_file' but structure.layout_file is "
                "empty — name the file that paints the grid, or choose one of the "
                "generated layouts."
            )
        return self


class MovementConfig(_RegistryBackedModel):
    """Agent movement on the grid (M11b Phase B, DESIGN §2.12; DECISIONS #165/#172).

    The third parameterisation of the reach kernel: a per-agent per-period
    move probability and the walk's radius/decay pair. Consumed only under
    lattice + energy economy (synchronous ``energy_economy``, asynchronous
    ``variable_n``) and only while ``rate > 0`` — at the default rate 0 the
    engines make no movement draw at all, so every pre-M11b config re-runs
    identically (hard rule 8).

    Attributes:
        rate: Per-agent per-period probability of attempting one move —
            at the synchronous boundary's final step, or at the agent's
            asynchronous activation. 0 = movement off.
        radius: Support radius R of the walk — how far one move can carry
            an agent; ``None`` means unlimited reach.
        decay: Decay β of the walk — how steeply nearer empty sites are
            preferred. Irrelevant at R = 1.
    """

    _registry_keys: ClassVar[dict[str, str]] = {
        "rate": "movement.rate",
        "radius": "movement.radius",
        "decay": "movement.decay",
    }

    rate: float = _registry_field("movement.rate")
    radius: int | None = _registry_field("movement.radius")
    decay: float = _registry_field("movement.decay")


class DynamicsConfig(_RegistryBackedModel):
    """Evolutionary dynamics: selection, mutation, and the economy (§2.7/§2.10).

    Attributes:
        generations: Number of generations to simulate. Under the
            asynchronous time model (M10b) this is the run length in
            generation-equivalents — same name, same scale, different
            clock.
        time_model: Which clock the run uses (M10b) — ``"synchronous"``
            (the generational clock, all earlier behaviour unchanged) or
            ``"asynchronous"`` (event time: one focal activation at a
            time, births and deaths firing immediately; the M10b spec).
            Under ``"asynchronous"``, ``reproduction_mode``, the selection
            family, score accounting, and ``matching.matcher`` are ignored
            (the DECISIONS #34 pattern).
        reproduction_mode: How the next generation comes to be —
            ``"imitation"`` (the classic fixed-N setting: selection rule +
            copying) or ``"energy_economy"`` (M10a birth-death dynamics:
            agents earn/pay/inherit energy and the population size varies).
            Under ``"energy_economy"`` the whole selection family and score
            accounting are ignored (the DECISIONS #34 pattern); under
            ``"imitation"`` all the economy parameters below are ignored.
        selection_rule: Selection rule name — ``"fermi"``, ``"proportional"``,
            ``"tournament_k"``, ``"truncation"``, or ``"threshold_cloning"``
            (M9a; each rule reads only its own parameters below, the others
            are ignored — the DECISIONS #34 pattern).
        selection_beta: Selection intensity β for ``"fermi"`` (0 = pure drift).
        selection_tournament_k: Candidates per slot for ``"tournament_k"``.
            Must be at most N; checked at the experiment level.
        selection_elite_fraction: Top score-share parents are drawn from
            under ``"truncation"`` (0 < q ≤ 1).
        selection_threshold_multiplier: Survival bar for
            ``"threshold_cloning"``, as a multiple of the mean score.
        mutation_rate: Strategy-switch mutation probability μ (consumed by
            BOTH reproduction modes: imitation slots and economy newborns).
        score_accounting: Which score selection consumes —
            ``"per_generation"`` (raw, the classic setting),
            ``"sliding_window"``, or ``"exponential_discount"`` (M9a).
        accounting_window: Window W for ``"sliding_window"``.
        accounting_discount: Discount λ for ``"exponential_discount"``.
        reproduction_threshold: θ — end-of-generation energy required to
            breed (energy economy only).
        offspring_stake: σ — energy transferred from parent to newborn at
            birth. Must not exceed θ (validated), so a parent survives its
            own reproduction.
        initial_energy: Founders' starting energy. ``None`` in the raw input
            means "auto = same as the offspring stake" and is resolved to a
            plain number at validation time (never stored as null — hard
            rule 8; see :func:`resolve_initial_energy`).
        basic_living_cost: L — energy every agent pays per generation simply
            for existing (the metabolic bill).
        engagement_cost: Energy paid per match played.
        reproduction_overhead: Extra energy burned (not transferred) by the
            parent at each birth.
        capital_return_rate: r — interest on energy carried between
            generations (carried-in energy is multiplied by 1 + r).
        carrying_capacity: K — the population cap; births only fill seats
            below it. Must be at least the starting population size and,
            on a lattice, at most the site count (both checked at the
            experiment level). ``None`` in the raw input means "auto = the
            lattice's site count, or 200 in a well-mixed world" and is
            resolved to a plain number at experiment validation (see
            :func:`resolve_carrying_capacity`); like the lattice
            dimensions, ``None`` survives only in a standalone-built
            section, where no structure is in sight.
        boundary_order: The order of deaths and births at each synchronous
            generation boundary (M11a Phase C, #107) —
            ``"death_first"`` (the frozen #80 sequence: deaths land, then
            survivors breed into the freed room) or ``"birth_first"``
            (Hammond–Axelrod's period order: births first — rationed
            against the pre-death population, so fewer are admitted — then
            the death phase, which newborns face in their birth round).
            Never read under the asynchronous time model.
        base_hazard: Per-boundary death chance at age 0 (the mortality trio,
            with the two below).
        senescence_factor: Per-generation multiplier on the death chance.
            ``None`` in the raw input means "auto = reach certainty exactly
            at max_age" and is resolved to a plain number at validation time
            (see :func:`resolve_senescence_factor`).
        max_age: Hard age cap; 0 means no cap.
        async_population: What happens to the population size under the
            asynchronous time model (M10b) — ``"variable_n"`` (the energy
            economy in event time: θ-births, insolvency/age deaths,
            extinction) or ``"fixed_n"`` (textbook Moran: size pinned, one
            death paired with one birth per event; ``carrying_capacity``,
            the mortality trio, and the θ/σ birth gate are ignored). Only
            read when ``time_model`` is ``"asynchronous"``.
        moran_rule: The replacement order under ``"fixed_n"`` —
            ``"death_birth"``, ``"birth_death"``, or ``"random"`` (a
            weighted per-event roll between the two, using the weight pair
            below). Ignored under ``"variable_n"``.
        moran_weight_birth_death: Weight of the birth-death branch when
            ``moran_rule`` is ``"random"``; normalised against the
            death-birth weight at use. Ignored otherwise.
        moran_weight_death_birth: Weight of the death-birth branch when
            ``moran_rule`` is ``"random"``. The pair cannot both be zero
            while consumed (checked at the experiment level).
        fixed_n_death_rule: How the dying agent of a fixed-size replacement
            is picked — ``"pure_random"`` (uniform, the textbook setting) or
            ``"energy_decides"`` (the poorest candidate, deterministically;
            ties to the lowest id). Ignored under ``"variable_n"``.
        imitation_overlay: Whether the cultural imitation channel runs on top
            of the async demographics (M10b spec Design 4): after every
            finished match the lower-scoring participant considers copying
            the higher scorer's strategy, with the Fermi probability that
            ``selection_beta`` tunes. Strategy-copy only — no birth, death,
            energy transfer, or identity change. Layerable on BOTH async
            population modes; ignored under the synchronous clock.
    """

    _registry_keys: ClassVar[dict[str, str]] = {
        "generations": "dynamics.generations",
        "reproduction_mode": "dynamics.reproduction_mode",
        "time_model": "dynamics.time_model",
        "selection_rule": "dynamics.selection_rule",
        "selection_beta": "dynamics.selection_beta",
        "selection_tournament_k": "dynamics.selection_tournament_k",
        "selection_elite_fraction": "dynamics.selection_elite_fraction",
        "selection_threshold_multiplier": "dynamics.selection_threshold_multiplier",
        "mutation_rate": "dynamics.mutation_rate",
        "score_accounting": "dynamics.score_accounting",
        "accounting_window": "dynamics.accounting_window",
        "accounting_discount": "dynamics.accounting_discount",
        "reproduction_threshold": "dynamics.reproduction_threshold",
        "offspring_stake": "dynamics.offspring_stake",
        "initial_energy": "dynamics.initial_energy",
        "basic_living_cost": "dynamics.basic_living_cost",
        "engagement_cost": "dynamics.engagement_cost",
        "reproduction_overhead": "dynamics.reproduction_overhead",
        "capital_return_rate": "dynamics.capital_return_rate",
        "carrying_capacity": "dynamics.carrying_capacity",
        "boundary_order": "dynamics.boundary_order",
        "base_hazard": "dynamics.base_hazard",
        "senescence_factor": "dynamics.senescence_factor",
        "max_age": "dynamics.max_age",
        "async_population": "dynamics.async_population",
        "moran_rule": "dynamics.moran_rule",
        "moran_weight_birth_death": "dynamics.moran_weight_birth_death",
        "moran_weight_death_birth": "dynamics.moran_weight_death_birth",
        "fixed_n_death_rule": "dynamics.fixed_n_death_rule",
        "imitation_overlay": "dynamics.imitation_overlay",
    }

    generations: int = _registry_field("dynamics.generations")
    reproduction_mode: str = _registry_field("dynamics.reproduction_mode")
    time_model: str = _registry_field("dynamics.time_model")
    selection_rule: str = _registry_field("dynamics.selection_rule")
    selection_beta: float = _registry_field("dynamics.selection_beta")
    selection_tournament_k: int = _registry_field("dynamics.selection_tournament_k")
    selection_elite_fraction: float = _registry_field("dynamics.selection_elite_fraction")
    selection_threshold_multiplier: float = _registry_field(
        "dynamics.selection_threshold_multiplier"
    )
    mutation_rate: float = _registry_field("dynamics.mutation_rate")
    score_accounting: str = _registry_field("dynamics.score_accounting")
    accounting_window: int = _registry_field("dynamics.accounting_window")
    accounting_discount: float = _registry_field("dynamics.accounting_discount")
    reproduction_threshold: float = _registry_field("dynamics.reproduction_threshold")
    offspring_stake: float = _registry_field("dynamics.offspring_stake")
    # Annotated plain float, not float | None: the mode="before" resolver
    # below guarantees a number is present before field validation runs, so
    # a constructed config always holds the resolved value (hard rule 8).
    initial_energy: float = _registry_field("dynamics.initial_energy")
    basic_living_cost: float = _registry_field("dynamics.basic_living_cost")
    engagement_cost: float = _registry_field("dynamics.engagement_cost")
    reproduction_overhead: float = _registry_field("dynamics.reproduction_overhead")
    capital_return_rate: float = _registry_field("dynamics.capital_return_rate")
    # int | None like the lattice dimensions: the experiment-level resolver
    # always writes a plain number into a full config (hard rule 8); None
    # survives only in a standalone-built section.
    carrying_capacity: int | None = _registry_field("dynamics.carrying_capacity")
    boundary_order: str = _registry_field("dynamics.boundary_order")
    base_hazard: float = _registry_field("dynamics.base_hazard")
    senescence_factor: float = _registry_field("dynamics.senescence_factor")
    max_age: int = _registry_field("dynamics.max_age")
    async_population: str = _registry_field("dynamics.async_population")
    moran_rule: str = _registry_field("dynamics.moran_rule")
    moran_weight_birth_death: float = _registry_field("dynamics.moran_weight_birth_death")
    moran_weight_death_birth: float = _registry_field("dynamics.moran_weight_death_birth")
    fixed_n_death_rule: str = _registry_field("dynamics.fixed_n_death_rule")
    imitation_overlay: bool = _registry_field("dynamics.imitation_overlay")

    # New concept — `@model_validator(mode="before")`: unlike the "after"
    # hooks elsewhere in this module (which see the finished, FROZEN model
    # and so cannot assign fields), a "before" validator receives the raw
    # input mapping and may rewrite it. That is exactly what a derived
    # default needs: replace None/absent with the resolved number BEFORE
    # pydantic fills defaults and freezes the model. Because it runs before
    # defaults are applied, an absent key and an explicit None are treated
    # identically, and any inputs the arithmetic needs are read from the
    # mapping with the Parameter Registry default as fallback.
    @model_validator(mode="before")
    @classmethod
    def _resolve_derived_defaults(cls, data: object) -> object:
        """Resolve the two auto ("None") defaults into plain numbers (M10a).

        Args:
            data: The raw input mapping (or an already-built model, passed
                through untouched).

        Returns:
            The mapping with ``initial_energy`` and ``senescence_factor``
            always present as numbers — so ``save_config`` writes plain
            numbers and the auto rules can never retroactively change a
            stored run (hard rule 8).
        """
        if not isinstance(data, dict):
            return data

        def raw(field: str, key: str) -> registry.ParamValue:
            value = data.get(field)
            return registry.get_spec(key).default if value is None else value

        resolved = dict(data)
        resolved["initial_energy"] = resolve_initial_energy(
            data.get("initial_energy"), raw("offspring_stake", "dynamics.offspring_stake")
        )
        resolved["senescence_factor"] = resolve_senescence_factor(
            data.get("senescence_factor"),
            raw("base_hazard", "dynamics.base_hazard"),
            raw("max_age", "dynamics.max_age"),
        )
        return resolved

    @model_validator(mode="after")
    def _check_stake_fits_threshold(self) -> Self:
        """Check σ + overhead ≤ θ: a parent survives its own reproduction.

        The parent pays the offspring stake PLUS the reproduction overhead
        at each birth, so the threshold must cover their SUM — checking σ
        alone (the M10a check this tightens; ``docs/ADVISORIES.md`` "Not an
        advisory", discharged in M11a Phase C) let a parent at exactly θ
        end the boundary at −overhead and die of insolvency one boundary
        later, silently breaking the documented guarantee.

        Runs only when θ actually gates births — under the synchronous
        ``"energy_economy"`` mode, or under the asynchronous time model
        with the ``"variable_n"`` population (M10b Phase B refinement:
        ``"fixed_n"`` has no θ gate and explicitly allows a parent to be
        driven negative by the stake, so nothing there consumes this pair
        as a birth bar). Under synchronous ``"imitation"`` both are
        ignored, and ignored parameters are never validation errors
        (DECISIONS #34).

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If stake plus overhead exceeds the reproduction
                threshold while the birth machinery consumes them. The
                message names all three quantities.
        """
        consumed = (
            self.time_model == "synchronous" and self.reproduction_mode == "energy_economy"
        ) or (self.time_model == "asynchronous" and self.async_population == "variable_n")
        total = self.offspring_stake + self.reproduction_overhead
        if consumed and total > self.reproduction_threshold:
            raise ValueError(
                f"dynamics.offspring_stake ({self.offspring_stake}) plus "
                f"dynamics.reproduction_overhead ({self.reproduction_overhead}) "
                f"is {total}, which is more than dynamics.reproduction_threshold "
                f"({self.reproduction_threshold}). A breeding parent pays stake "
                "AND overhead, so their sum cannot exceed the energy bar for "
                "breeding — or reproduction would kill the parent. Lower the "
                "stake or the overhead (or raise the threshold)."
            )
        return self


class OutputConfig(_RegistryBackedModel):
    """What the run records — never what it simulates (M10b spec Design 6).

    The recording cadence sits in the config, unlike the engine's
    ``granularity`` argument, because it decides what the persisted record
    CONTAINS — and what a run recorded is part of reproducing it (hard
    rule 8). Like granularity it is an observer control (DECISIONS #35):
    the same config + seed produces the identical simulation history at
    every cadence; only the number of recorded data points changes.

    Attributes:
        recording_cadence: When an asynchronous run emits a period record —
            ``"per_generation_equivalent"`` (at each integer crossing of
            the event-time clock, comparable to a synchronous run),
            ``"per_event"`` (after every event; maximum resolution,
            largest files), or ``"every_m_events"`` (after every m-th
            event). Ignored by synchronous runs, which always record once
            per generation (the DECISIONS #34 pattern).
        recording_cadence_m: The m for ``"every_m_events"``; ignored under
            the other cadences (#34).
    """

    _registry_keys: ClassVar[dict[str, str]] = {
        "recording_cadence": "output.recording_cadence",
        "recording_cadence_m": "output.recording_cadence_m",
    }

    recording_cadence: str = _registry_field("output.recording_cadence")
    recording_cadence_m: int = _registry_field("output.recording_cadence_m")


class ExperimentConfig(_RegistryBackedModel):
    """The complete, validated description of one simulation run.

    Everything the engine needs — and everything that must be persisted for
    the run to be reproducible — lives here. Only ``population`` is required
    (an experiment must declare its starting strategy mix); every other
    section falls back to registry defaults.

    Attributes:
        mode: What kind of run this is — ``"evolution"`` (selection and
            mutation reshape the population each generation) or
            ``"tournament"`` (a fixed cast plays repeated matcher passes and
            scores simply accumulate; selection/mutation/generation settings
            are ignored — valid but without effect, DECISIONS #34).
        tournament_cycles: Number of complete matcher passes in a
            ``"tournament"`` run; ignored in ``"evolution"`` mode.
        seed: Random seed; with the same seed and settings, a run replays
            exactly (hard rules 5 and 8).
        game: Payoff matrix and game-shape toggles.
        matching: Who plays whom each generation.
        match: Match length mode and noise.
        population: Size, memory constraint, and initial strategy mix.
        structure: The shape of the world — well-mixed or a lattice of
            sites (M11a; consumed by nothing in Phase A).
        movement: Agent movement on the grid (M11b Phase B) — the move
            rate and the walk's radius/decay; consumed only under lattice +
            energy economy while the rate is positive.
        dynamics: Selection and mutation settings.
        output: Recording cadence — what the run records, never what it
            simulates (M10b; consumed by asynchronous runs only, #34).
        strategy_params: Optional per-run strategy parameter overrides, as a
            mapping of strategy machine name → ``{parameter: value}``, e.g.
            ``{"random": {"cooperation_probability": 0.9}}``. Omitted
            parameters keep their Parameter Registry defaults. One parameter
            set per strategy per run (DECISIONS #30); a strategy may be named
            here even if it is not in the composition — mutation can still
            introduce it mid-run, and then these values apply.
    """

    _registry_keys: ClassVar[dict[str, str]] = {
        "mode": "run.mode",
        "tournament_cycles": "run.tournament_cycles",
        "seed": "run.seed",
    }

    # Run-mode fields live at the top level next to `seed` (the "run.*"
    # registry section maps to top-level config fields) — a nested `run:`
    # section would have moved `seed:` and broken every existing YAML
    # (hard rule 8; DECISIONS #34).
    mode: str = _registry_field("run.mode")
    tournament_cycles: int = _registry_field("run.tournament_cycles")
    seed: int = _registry_field("run.seed")
    # New concept — `default_factory`: for defaults that are *objects*, pydantic
    # (like dataclasses) takes a zero-argument function that builds a fresh
    # default per instance, rather than one shared object created at import.
    game: GameConfig = Field(default_factory=GameConfig)
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    match: MatchConfig = Field(default_factory=MatchConfig)
    population: PopulationConfig
    structure: StructureConfig = Field(default_factory=StructureConfig)
    movement: MovementConfig = Field(default_factory=MovementConfig)
    dynamics: DynamicsConfig = Field(default_factory=DynamicsConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    strategy_params: dict[str, dict[str, registry.ParamValue]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _resolve_structure_dimensions(cls, data: object) -> object:
        """Resolve blank rows/cols — and, from them, a blank K (M11a).

        The cross-section counterpart of ``DynamicsConfig``'s derived
        defaults: the auto rules read values from OTHER sections (rows/cols
        read the population size; the carrying capacity reads the resolved
        site count), so they must run here on the full experiment where
        every section is visible — and in this order, dimensions first,
        because K's auto rule consumes their result. Both run regardless of
        ``structure.kind`` — like every #78 derived default, the stored
        config always holds plain numbers, so an auto rule can never
        retroactively change a saved run (hard rule 8). Anything malformed
        (a missing population, a non-integer size) is passed through
        untouched so pydantic's own field validation reports it with its
        usual message.

        Args:
            data: The raw input mapping (or a non-mapping, passed through
                untouched).

        Returns:
            The mapping with ``structure.rows``, ``structure.cols``, and
            ``dynamics.carrying_capacity`` present as plain numbers
            wherever the inputs allow them to be resolved.
        """
        if not isinstance(data, dict):
            return data

        structure = data.get("structure")
        if isinstance(structure, StructureConfig):
            current_rows, current_cols = structure.rows, structure.cols
            kind = structure.kind
        elif isinstance(structure, dict):
            current_rows, current_cols = structure.get("rows"), structure.get("cols")
            kind = structure.get("kind", registry.get_spec("structure.kind").default)
        elif structure is None:
            current_rows = current_cols = None
            kind = registry.get_spec("structure.kind").default
        else:
            return data

        def valid_dimension(value: object) -> bool:
            # bool is a subclass of int (the registry gotcha), so reject it
            # explicitly; a present-but-invalid value passes through untouched
            # for the registry's own message.
            return value is None or (
                isinstance(value, int) and not isinstance(value, bool) and value >= 1
            )

        resolved = dict(data)
        rows, cols = current_rows, current_cols
        if (
            (current_rows is None or current_cols is None)
            and valid_dimension(current_rows)
            and valid_dimension(current_cols)
        ):
            population = data.get("population")
            if isinstance(population, PopulationConfig):
                size = population.size
            elif isinstance(population, dict):
                raw = population.get("size")
                size = registry.get_spec("population.size").default if raw is None else raw
            else:
                size = None
            if not isinstance(size, bool) and isinstance(size, int) and size >= 1:
                rows, cols = resolve_lattice_dimensions(current_rows, current_cols, size)
                if isinstance(structure, StructureConfig):
                    # model_copy (new concept): the way to "change" a frozen
                    # pydantic model — it builds a new instance with the
                    # listed fields replaced.
                    resolved["structure"] = structure.model_copy(
                        update={"rows": rows, "cols": cols}
                    )
                elif isinstance(structure, dict):
                    resolved["structure"] = {**structure, "rows": rows, "cols": cols}
                else:
                    resolved["structure"] = {"rows": rows, "cols": cols}

        # The carrying-capacity step (M11a Phase C): blank K resolves off
        # the site count the dimensions above just settled — or off nothing,
        # in a well-mixed world, where the aspatial fallback applies.
        dynamics = data.get("dynamics")
        if isinstance(dynamics, DynamicsConfig):
            current_k: object = dynamics.carrying_capacity
        elif isinstance(dynamics, dict):
            current_k = dynamics.get("carrying_capacity")
        elif dynamics is None:
            current_k = None
        else:
            return resolved
        if current_k is None:
            site_count = (
                rows * cols
                if (
                    kind == "lattice"
                    and valid_dimension(rows)
                    and valid_dimension(cols)
                    and rows is not None
                    and cols is not None
                )
                else None
            )
            capacity = resolve_carrying_capacity(None, site_count)
            if isinstance(dynamics, DynamicsConfig):
                resolved["dynamics"] = dynamics.model_copy(update={"carrying_capacity": capacity})
            elif isinstance(dynamics, dict):
                resolved["dynamics"] = {**dynamics, "carrying_capacity": capacity}
            else:
                resolved["dynamics"] = {"carrying_capacity": capacity}
        return resolved

    @model_validator(mode="after")
    def _check_matching_fits_population(self) -> Self:
        """Check that random_k's k fits the population (k at most N - 1).

        A cross-parameter check, like the composition-sum rule: it involves
        two config sections, so it lives here on the full experiment, where
        both are visible. Under ``"round_robin"`` the k value is ignored
        entirely (DECISIONS #34), so no check applies — configs can switch
        matchers without surgery. EXCEPT under the asynchronous time model
        (M10b): there the matcher itself is ignored but k is always
        consumed (each activation draws k partners), so the check applies
        regardless of the matcher widget — validate exactly what is
        consumed (#34).

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If k is consumed and each agent would need more
                distinct opponents than the population offers.
        """
        # In tournament mode time_model itself is ignored (#34), so only the
        # matcher widget can make k consumed there.
        async_consumes_k = self.mode == "evolution" and self.dynamics.time_model == "asynchronous"
        if self.matching.matcher == "random_k" or async_consumes_k:
            k = self.matching.opponents_per_agent
            available = self.population.size - 1
            if k > available:
                raise ValueError(
                    f"matching.opponents_per_agent is {k}, but in a population of "
                    f"{self.population.size} each agent has only {available} possible "
                    "opponents. Lower the opponents per agent (or grow the "
                    "population) so k is at most N - 1."
                )
        return self

    @model_validator(mode="after")
    def _check_selection_fits_population(self) -> Self:
        """Check that tournament_k's k fits the population (k at most N).

        The #57 cross-parameter precedent, applied to selection: the check
        runs only when the parameter is actually consumed — the rule is
        ``"tournament_k"`` AND the mode is ``"evolution"`` (in tournament
        mode every dynamics parameter is ignored, and ignored parameters
        are never validation errors — DECISIONS #34).

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If tournament selection would need more candidates
                than the population offers.
        """
        if self.mode == "evolution" and self.dynamics.selection_rule == "tournament_k":
            k = self.dynamics.selection_tournament_k
            if k > self.population.size:
                raise ValueError(
                    f"dynamics.selection_tournament_k is {k}, but the population "
                    f"only has {self.population.size} agents to draw candidates "
                    "from. Lower the tournament size (or grow the population) so "
                    "k is at most N."
                )
        return self

    @model_validator(mode="after")
    def _check_capacity_fits_population(self) -> Self:
        """Check K ≥ N: generation 0 must not already exceed capacity (M10a).

        A cross-section check like ``_check_matching_fits_population`` — it
        spans dynamics and population, so it lives on the full experiment.
        Runs only when the carrying capacity is actually consumed: evolution
        mode with synchronous ``"energy_economy"`` reproduction, or with
        the asynchronous time model's ``"variable_n"`` population (M10b
        Phase B refinement: ``"fixed_n"`` pins the population at its
        starting size and ignores K entirely). Under synchronous imitation
        (or in tournament mode) the capacity is ignored, and ignored
        parameters are never validation errors (DECISIONS #34) — which also
        keeps every pre-M10a config loading unchanged (hard rule 8).

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If the starting population is bigger than the
                carrying capacity while births are gated on it.
        """
        consumed = (
            self.dynamics.time_model == "synchronous"
            and self.dynamics.reproduction_mode == "energy_economy"
        ) or (
            self.dynamics.time_model == "asynchronous"
            and self.dynamics.async_population == "variable_n"
        )
        if (
            self.mode == "evolution"
            and consumed
            and self.dynamics.carrying_capacity is not None
            and self.dynamics.carrying_capacity < self.population.size
        ):
            raise ValueError(
                f"dynamics.carrying_capacity is {self.dynamics.carrying_capacity}, "
                f"but the population starts with {self.population.size} agents — "
                "generation 0 would already exceed capacity. Raise the carrying "
                "capacity (or start with fewer agents)."
            )
        return self

    @model_validator(mode="after")
    def _check_moran_weights(self) -> Self:
        """Reject an all-zero Moran weight pair — but only when consumed (M10b).

        The pair is normalised at use (``w_bd / (w_bd + w_db)``), so
        both-zero would divide by zero — but only when the roll actually
        happens: evolution mode, asynchronous time model, ``"fixed_n"``
        population, ``"random"`` Moran rule. In every other configuration
        the weights are ignored, and ignored parameters are never
        validation errors (DECISIONS #34) — the same
        validate-exactly-what-is-consumed discipline as the k and capacity
        checks above.

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If both weights are zero while the ``"random"``
                Moran rule would roll between them.
        """
        dynamics = self.dynamics
        if (
            self.mode == "evolution"
            and dynamics.time_model == "asynchronous"
            and dynamics.async_population == "fixed_n"
            and dynamics.moran_rule == "random"
            and dynamics.moran_weight_birth_death == 0.0
            and dynamics.moran_weight_death_birth == 0.0
        ):
            raise ValueError(
                "dynamics.moran_weight_birth_death and "
                "dynamics.moran_weight_death_birth are both 0, but the Moran "
                "rule is 'random' — there would be nothing to roll between. "
                "Give at least one branch a positive weight (or pick "
                "'birth_death' / 'death_birth' directly)."
            )
        return self

    @model_validator(mode="after")
    def _check_layout_file_agrees(self) -> Self:
        """Validate a from-file layout against the run it will found (M11a, #126).

        Spec Design 8 names the layout-file checks as VALIDATORS, so they
        belong here — at config-validation time, where the app's Run button
        and the CLI already render failures as plain sentences — not at
        founding time inside the engine, where a mistake surfaced as a raw
        traceback. The composition-equality half is what keeps a recorded
        ``config.yaml`` honest (hard rule 8): with it, a from-file run can
        never record a composition other than the one that actually runs.

        Runs only when the layout file is actually consumed — evolution
        mode, lattice, ``from_file`` — because ignored parameters are never
        validation errors (#34). The engine's own founding-time checks stay
        as defence in depth for programmatically built configs.

        Reading the file here is read-to-VALIDATE, not read-to-derive:
        #119(d)'s rejection stands — no derived default reads file contents
        — while a cross-check validator consults the file precisely to
        confirm the widgets agree with it, deriving nothing.

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If the file is missing or unreadable, malformed,
                sized differently from the resolved grid, names an
                unregistered strategy, places fewer than two agents, or
                implies a composition different from the configured one.
                Every message says how to fix it; the composition message
                points at the app's one-click populate button.
        """
        structure = self.structure
        if (
            self.mode != "evolution"
            or structure.kind != "lattice"
            or structure.initial_layout != "from_file"
        ):
            return self
        # Lazy import, as elsewhere in this module: config -> core at
        # module scope would put an import cycle one refactor away.
        from pdsim.core.layouts import (
            read_layout_file,
            resolve_layout_path,
            validate_layout_file,
        )
        from pdsim.core.strategies import all_strategy_names

        path = resolve_layout_path(structure.layout_file or "")
        try:
            layout = read_layout_file(path)
        except FileNotFoundError as error:
            # pydantic wraps ValueError into a ValidationError; a raw
            # FileNotFoundError would escape as a traceback instead.
            raise ValueError(str(error)) from None
        # rows/cols are plain numbers by now — the before-validator resolved
        # them — so the dimension check compares against the real grid.
        validate_layout_file(
            layout,
            rows=int(structure.rows or 0),
            cols=int(structure.cols or 0),
            known_strategies=frozenset(all_strategy_names()),
            # Self-consistent on purpose: size disagreement is reported by
            # the composition check below, whose message knows the fix.
            population_size=layout.occupied_count,
        )
        if layout.occupied_count < 2:
            raise ValueError(
                f"Layout file {structure.layout_file!r} places "
                f"{layout.occupied_count} agent(s); a run needs at least 2. "
                "Name more cells, or choose a generated layout."
            )
        file_counts = layout.strategy_counts()
        widget_counts = {
            name: self.population.composition[name] for name in sorted(self.population.composition)
        }
        if file_counts != widget_counts:

            def _mix(counts: dict[str, int]) -> str:
                return ", ".join(f"{name} {count}" for name, count in counts.items())

            raise ValueError(
                "The layout file and the Population section disagree: the file "
                f"places {layout.occupied_count} agents ({_mix(file_counts)}), "
                f"while the population is {self.population.size} "
                f"({_mix(widget_counts)}). The file decides both the arrangement "
                "and the mixture, so in the app press 'Populate the Population "
                "section from the file' to adopt the file's numbers in one "
                "click — or switch structure.initial_layout away from "
                "'from_file' to keep the numbers you typed."
            )
        return self

    # The three lattice-bound checks below are deliberately defined AFTER
    # _check_layout_file_agrees: pydantic runs after-validators in definition
    # order, and a from-file config whose numbers disagree should get the
    # layout validator's message — the one that knows about the one-click
    # populate button — not a generic size complaint.

    @model_validator(mode="after")
    def _check_population_fits_lattice(self) -> Self:
        """Check N ≤ site count: every agent needs a site (M11a Phase C).

        Every site holds at most one agent (capacity is pinned at 1 —
        Design 12), so a founding population larger than the grid cannot be
        placed. Before this validator the mistake surfaced as a raw
        founding-time error inside the engine; the #126 discipline — a user
        must never see a traceback for a configuration mistake — puts it
        here. Tournament runs ignore structure entirely (#34), so only
        evolution mode checks.

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If a lattice run's population exceeds its site
                count. The message names both numbers.
        """
        structure = self.structure
        if self.mode != "evolution" or structure.kind != "lattice":
            return self
        if structure.rows is None or structure.cols is None:
            return self
        site_count = structure.rows * structure.cols
        if self.population.size > site_count:
            raise ValueError(
                f"population.size is {self.population.size}, but the "
                f"{structure.rows}x{structure.cols} lattice has only "
                f"{site_count} sites and every site holds at most one agent. "
                "Enlarge the grid (or leave rows/columns blank to auto-size "
                "it), or shrink the population."
            )
        return self

    @model_validator(mode="after")
    def _check_capacity_fits_lattice(self) -> Self:
        """Check K ≤ site count: the grid is the outer bound (M11a, #106).

        The carrying capacity is an optional INNER cap under a lattice — a
        K below the site count leaves deliberate slack the occupied region
        can drift through — but a K above it promises room the world does
        not have. Runs only when K is actually consumed (the same predicate
        as the K ≥ N check above: sync economy, or async ``variable_n``;
        ``fixed_n`` ignores K wholesale per #97d), because ignored
        parameters are never validation errors (#34).

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If a lattice run's carrying capacity exceeds its
                site count. The message names both numbers.
        """
        structure = self.structure
        consumed = (
            self.dynamics.time_model == "synchronous"
            and self.dynamics.reproduction_mode == "energy_economy"
        ) or (
            self.dynamics.time_model == "asynchronous"
            and self.dynamics.async_population == "variable_n"
        )
        if (
            self.mode != "evolution"
            or not consumed
            or structure.kind != "lattice"
            or structure.rows is None
            or structure.cols is None
            or self.dynamics.carrying_capacity is None
        ):
            return self
        site_count = structure.rows * structure.cols
        if self.dynamics.carrying_capacity > site_count:
            raise ValueError(
                f"dynamics.carrying_capacity is {self.dynamics.carrying_capacity}, "
                f"but the {structure.rows}x{structure.cols} lattice has only "
                f"{site_count} sites — the grid is the outer bound on the "
                "population, and the capacity can only tighten it. Lower the "
                "capacity to at most the site count (or leave it blank to let "
                "the grid decide)."
            )
        return self

    @model_validator(mode="after")
    def _check_fixed_n_fills_lattice(self) -> Self:
        """Check N = site count under ``fixed_n`` + lattice (M11a, Design 1).

        The fixed-size Moran engine keeps every site occupied at all times:
        a death frees exactly one site and the newborn has nowhere else to
        go, which is what makes site recycling the only possible Moran
        placement (the textbook death-birth corner arises structurally,
        from full occupancy, rather than from an imposed rule). A
        population above the site count cannot be placed; one below it
        would leave permanent holes the Moran replacement could never fill
        or move.

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If an async ``fixed_n`` lattice run's population
                differs from its site count. The message states why
                equality is required.
        """
        structure = self.structure
        if (
            self.mode != "evolution"
            or self.dynamics.time_model != "asynchronous"
            or self.dynamics.async_population != "fixed_n"
            or structure.kind != "lattice"
            or structure.rows is None
            or structure.cols is None
        ):
            return self
        site_count = structure.rows * structure.cols
        if self.population.size != site_count:
            raise ValueError(
                f"population.size is {self.population.size}, but a 'fixed_n' "
                f"run on a {structure.rows}x{structure.cols} lattice needs "
                f"exactly {site_count} agents — one per site. Full occupancy "
                "is what makes site recycling the only possible Moran "
                "placement (a death frees exactly one site and the newborn "
                "takes it); with holes in the grid the fixed-size replacement "
                "would have nowhere coherent to happen. Match the population "
                "to the site count, or leave rows/columns blank to auto-size "
                "the grid to the population."
            )
        return self

    @model_validator(mode="after")
    def _check_spatial_interaction_needs_lattice(self) -> Self:
        """Check spatial interaction runs on a lattice (M11a Phase D, #108).

        Sampling partners "within the interaction radius" needs a world in
        which distance exists — in a well-mixed world there is no radius to
        sample within, so the toggle would promise a locality the structure
        cannot supply. The #126 discipline puts the check here, at config
        validation, where the app and the CLI render it as a plain
        sentence. Tournament mode skips the check: structure is ignored
        wholesale there (#120(a)), and this toggle gets the identical
        ignored-under-tournament treatment — ignored parameters are never
        validation errors (#34).

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If spatial interaction is on without a lattice.
                The message names both settings and says why.
        """
        if (
            self.mode == "evolution"
            and self.matching.spatial_interaction
            and self.structure.kind != "lattice"
        ):
            raise ValueError(
                "matching.spatial_interaction is on, but structure.kind is "
                f"{self.structure.kind!r} — partners are sampled from within "
                "the interaction radius, and a well-mixed world has no "
                "distance to sample within. Set structure.kind to 'lattice' "
                "(or switch spatial interaction off)."
            )
        return self

    @model_validator(mode="after")
    def _check_strategy_params(self) -> Self:
        """Validate overrides against the strategy roster and their specs.

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If an override names an unknown strategy, a parameter
                the strategy does not declare, or a value that violates the
                parameter's registry spec.
        """
        # Lazy import for the same cycle-breaking reason as in
        # PopulationConfig._check_composition above.
        from pdsim.core.strategies import all_strategy_names, get_strategy_info

        valid_names = all_strategy_names()
        for name, params in self.strategy_params.items():
            if name not in valid_names:
                raise ValueError(
                    f"strategy_params names unknown strategy {name!r}. "
                    f"Valid strategy names: {', '.join(sorted(valid_names))}."
                )
            info = get_strategy_info(name)
            # zip(strict=True) (new concept): pairs two sequences and raises
            # if their lengths differ — a silent-mismatch guard.
            declared = dict(zip(info.param_names(), info.params, strict=True))
            for param_name, value in params.items():
                if param_name not in declared:
                    allowed = ", ".join(declared) if declared else "none — it has no parameters"
                    raise ValueError(
                        f"strategy_params for {name!r} names unknown parameter "
                        f"{param_name!r}. Valid parameters: {allowed}."
                    )
                declared[param_name].validate(value)
        return self


def load_config(path: str | Path) -> ExperimentConfig:
    """Load and validate an experiment configuration from a YAML file.

    Args:
        path: Path to a YAML file with the :class:`ExperimentConfig` layout.

    Returns:
        The validated configuration. A ``structure.layout_file`` is resolved
        per the #122 rule BEFORE validation — bare names prefer the copy
        beside this config file (a recorded folder is self-contained, hard
        rule 8), then ``grid_templates/`` — so the from-file validator
        (#126) checks the file the engine will actually read, and a
        recorded run folder re-runs from anywhere.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not a YAML mapping at the top level.
        pydantic.ValidationError: If any value is missing, unknown, or
            invalid — including every layout-file problem (missing,
            malformed, wrong dimensions, unknown tokens, or a composition
            that disagrees with the file).
    """
    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    # yaml.safe_load parses standard YAML types only — it cannot execute
    # arbitrary Python the way yaml.load can, so it is the right call for
    # user-supplied files.
    data: Any = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(
            f"Config file {path} must contain a YAML mapping (key: value pairs) at the "
            f"top level, got {type(data).__name__}."
        )
    structure_section = data.get("structure")
    if isinstance(structure_section, dict):
        layout_file = structure_section.get("layout_file")
        if layout_file and isinstance(layout_file, str):
            # Resolution must precede validation: the #126 validator reads
            # the file, and only THIS function knows the config's own folder
            # — where a recorded run keeps its layout copy under a bare
            # name. Imported lazily: config -> core at module scope would
            # put an import cycle one refactor away.
            from pdsim.core.layouts import resolve_layout_path

            resolved = resolve_layout_path(layout_file, config_dir=config_path.parent)
            if str(resolved) != layout_file and resolved.is_file():
                structure_section["layout_file"] = str(resolved)
    return ExperimentConfig.model_validate(data)


def save_config(config: ExperimentConfig, path: str | Path) -> Path:
    """Write an experiment configuration to a YAML file.

    The output round-trips: ``load_config(save_config(cfg, p))`` reproduces an
    equal config. Keys are written in declaration order (not alphabetized) so
    the file reads like the documentation.

    Args:
        config: The configuration to persist.
        path: Destination file path; parent directories are created if needed.

    Returns:
        The path written to (handy for chaining/logging).
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="json")
    out.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return out
