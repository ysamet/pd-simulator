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
    "save_config",
]


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
        matcher: Matching scheme name; v1 ships ``"round_robin"``.
    """

    _registry_keys: ClassVar[dict[str, str]] = {"matcher": "matching.matcher"}

    matcher: str = _registry_field("matching.matcher")


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
    """Evolutionary dynamics: selection and mutation (``docs/DESIGN.md`` §2.7).

    Attributes:
        generations: Number of generations to simulate.
        selection_rule: Selection rule name; v1 ships ``"fermi"``.
        selection_beta: Selection intensity β (0 = pure drift).
        mutation_rate: Strategy-switch mutation probability μ.
    """

    _registry_keys: ClassVar[dict[str, str]] = {
        "generations": "dynamics.generations",
        "selection_rule": "dynamics.selection_rule",
        "selection_beta": "dynamics.selection_beta",
        "mutation_rate": "dynamics.mutation_rate",
    }

    generations: int = _registry_field("dynamics.generations")
    selection_rule: str = _registry_field("dynamics.selection_rule")
    selection_beta: float = _registry_field("dynamics.selection_beta")
    mutation_rate: float = _registry_field("dynamics.mutation_rate")


class ExperimentConfig(_RegistryBackedModel):
    """The complete, validated description of one simulation run.

    Everything the engine needs — and everything that must be persisted for
    the run to be reproducible — lives here. Only ``population`` is required
    (an experiment must declare its starting strategy mix); every other
    section falls back to registry defaults.

    Attributes:
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

    _registry_keys: ClassVar[dict[str, str]] = {"seed": "run.seed"}

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
