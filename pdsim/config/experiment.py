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

from pathlib import Path
from typing import Any, ClassVar, Self

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
    "PopulationConfig",
    "load_config",
    "resolve_initial_energy",
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
        matcher: Matching scheme name — ``"round_robin"`` (every pair plays
            once) or ``"random_k"`` (each agent initiates matches against k
            randomly drawn opponents).
        opponents_per_agent: k for the ``"random_k"`` scheme. Ignored — valid
            but without effect, consuming no RNG draws — under
            ``"round_robin"`` (the DECISIONS #34 ignored-parameter pattern).
            Must be at most N - 1; checked at the experiment level, where the
            population size is known.
    """

    _registry_keys: ClassVar[dict[str, str]] = {
        "matcher": "matching.matcher",
        "opponents_per_agent": "matching.opponents_per_agent",
    }

    matcher: str = _registry_field("matching.matcher")
    opponents_per_agent: int = _registry_field("matching.opponents_per_agent")


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
            below it. Must be at least the starting population size
            (checked at the experiment level).
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
    carrying_capacity: int = _registry_field("dynamics.carrying_capacity")
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
        """Check σ ≤ θ: a parent must survive its own reproduction (M10a).

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
            ValueError: If the offspring stake exceeds the reproduction
                threshold while the birth machinery consumes them.
        """
        consumed = (
            self.time_model == "synchronous" and self.reproduction_mode == "energy_economy"
        ) or (self.time_model == "asynchronous" and self.async_population == "variable_n")
        if consumed and self.offspring_stake > self.reproduction_threshold:
            raise ValueError(
                f"dynamics.offspring_stake is {self.offspring_stake}, which is more "
                f"than dynamics.reproduction_threshold ({self.reproduction_threshold}). "
                "The stake a parent pays its newborn cannot exceed the energy bar "
                "for breeding, or reproduction would kill the parent. Lower the "
                "stake (or raise the threshold)."
            )
        return self


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
        dynamics: Selection and mutation settings.
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
    dynamics: DynamicsConfig = Field(default_factory=DynamicsConfig)
    strategy_params: dict[str, dict[str, registry.ParamValue]] = Field(default_factory=dict)

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
        The validated configuration.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not a YAML mapping at the top level.
        pydantic.ValidationError: If any value is missing, unknown, or invalid.
    """
    text = Path(path).read_text(encoding="utf-8")
    # yaml.safe_load parses standard YAML types only — it cannot execute
    # arbitrary Python the way yaml.load can, so it is the right call for
    # user-supplied files.
    data: Any = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(
            f"Config file {path} must contain a YAML mapping (key: value pairs) at the "
            f"top level, got {type(data).__name__}."
        )
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
