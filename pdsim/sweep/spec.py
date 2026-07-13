"""SweepSpec: describe a config family, validate it, expand it into runs.

A :class:`SweepSpec` mirrors :class:`~pdsim.config.experiment.ExperimentConfig`
conventions (frozen pydantic models, ``extra="forbid"``, plain-language errors).
It names a base configuration and one or more *axes* of variation — a
composition axis (the three-bucket invader model), parameter grids, a seed list
— and the layer expands the cross product into fully-validated member configs
(DECISIONS #66/#67).

**The load-bearing principle (#59):** expansion is a *generator, never a
weakener*. Every member config passes the platform's full validation — the same
range, payoff-ordering, and composition-sum checks any hand-written config
faces — and only the *resolved integer composition* is written into a member's
``config.yaml``, so each member is independently reproducible with no knowledge
of the sweep (hard rule 8).

Validation lives in one Streamlit-free function,
:func:`sweep_validation_messages` — the analog of
:func:`pdsim.ui.helpers.validation_messages` — so the CLI and the future Sweep
tab (M9.5b) share exactly one validation path (the #38/#48 reuse pattern).
"""

from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from pdsim.config.experiment import ExperimentConfig, load_config
from pdsim.config.registry import get_spec, validate_value
from pdsim.sweep.metrics import get_metric

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
"""Sweep names follow the registry-idiom token convention."""

_FILL_TOLERANCE = 1e-6
"""Slack allowed when checking that fill percentages sum to 100."""


class _FrozenModel(BaseModel):
    """Shared base: frozen, reject unknown keys (the ExperimentConfig idiom)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class CompositionAxis(_FrozenModel):
    """The three-bucket invader-composition axis (companion §2.1).

    Every strategy in a swept population is in exactly one bucket: the varying
    invader, a fixed count, or a percentage fill of the remainder.

    Attributes:
        vary: Machine name of the varying invader strategy. Modelled as a
            single strategy in M9.5a, but a future set is a small change
            (companion §3.2).
        counts: The invader counts to march across (each ≥ 0).
        fixed: Strategies held at a constant count in every run.
        fill: Strategies dividing the leftover seats, by percentage
            (values summing to 100).
    """

    vary: str
    counts: list[int]
    fixed: dict[str, int] = Field(default_factory=dict)
    fill: dict[str, float] = Field(default_factory=dict)


class ParameterAxis(_FrozenModel):
    """One Parameter Registry key swept over a list of values.

    Attributes:
        key: A registry key, e.g. ``"dynamics.selection_beta"``.
        values: The values to try (each validated against the key's spec).
    """

    key: str
    values: list[Any]


class MetricRef(_FrozenModel):
    """A reference to a registered outcome metric plus its call-time params.

    Authored flat in YAML, e.g. ``{metric: ever_exceeded, strategy:
    tit_for_tat, threshold: 0.9}``; the metric name is a declared field and the
    rest are collected as params (``extra="allow"`` here, unlike the frozen
    base — a metric's params vary by metric).

    Attributes:
        metric: A registered outcome-metric machine name.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    metric: str

    def params(self) -> dict[str, Any]:
        """Return the metric-specific parameters (everything but ``metric``).

        Returns:
            The extra keys as a plain dict.
        """
        return dict(self.model_extra or {})

    def label(self) -> str:
        """Return the summary-column label for this metric instance.

        Returns:
            ``metric`` alone if it has no params, else
            ``metric[v1,v2,...]`` with the param values in declaration order
            (e.g. ``"time_to_fixation[tit_for_tat]"``).
        """
        info = get_metric(self.metric)
        params = self.params()
        ordered = [params[name] for name in info.param_names() if name in params]
        if not ordered:
            return self.metric
        return f"{self.metric}[{','.join(str(value) for value in ordered)}]"


class SweepSpec(_FrozenModel):
    """A complete sweep description: base config, axes, seeds, metrics.

    Attributes:
        name: Safe lowercase token naming the sweep (its folder name).
        base: Path to a base config YAML (mutually exclusive with
            ``base_scenario``).
        base_scenario: A registered scenario name to use as the base.
        composition: The optional composition axis.
        parameters: Parameter-grid axes, applied in listed order.
        seeds: The random seeds to replicate over (non-empty).
        metrics: The outcome metrics to compute per member (non-empty).
    """

    name: str
    base: str | None = None
    base_scenario: str | None = None
    composition: CompositionAxis | None = None
    parameters: list[ParameterAxis] = Field(default_factory=list)
    seeds: list[int] = Field(default_factory=list)
    metrics: list[MetricRef] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MemberPlan:
    """One expanded, fully-validated member of a sweep.

    Attributes:
        run_index: 0-based position in the pinned expansion order.
        config: The member's validated experiment config.
        axis_values: The axis value per varied column (the vary strategy's
            count, each parameter key, and ``seed``) — the summary row's
            axis fields.
        slug: A short folder-name suffix built from the axis values.
    """

    run_index: int
    config: ExperimentConfig
    axis_values: dict[str, Any]
    slug: str


def load_sweep_spec(path: str | Path) -> SweepSpec:
    """Load and validate a sweep spec from a YAML file.

    Args:
        path: Path to a YAML file with the :class:`SweepSpec` layout.

    Returns:
        The validated spec (structural validation only — semantic checks are
        :func:`sweep_validation_messages`).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not a YAML mapping at the top level.
        pydantic.ValidationError: If the structure is malformed.
    """
    text = Path(path).read_text(encoding="utf-8")
    data: Any = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(
            f"Sweep spec {path} must contain a YAML mapping at the top level, "
            f"got {type(data).__name__}."
        )
    return SweepSpec.model_validate(data)


def sweep_spec_yaml(spec: SweepSpec) -> str:
    """Return a spec's YAML text (the one serialization path, M9.5b).

    :func:`save_sweep_spec` writes exactly this string, so the Sweep tab's
    YAML preview/download and the persisted file can never diverge.

    Args:
        spec: The spec to serialize.

    Returns:
        YAML text that round-trips through :func:`load_sweep_spec`.
    """
    data = spec.model_dump(mode="json", exclude_none=True)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def save_sweep_spec(spec: SweepSpec, path: str | Path) -> Path:
    """Write a sweep spec to a YAML file (round-trips through load_sweep_spec).

    Args:
        spec: The spec to persist.
        path: Destination file path; parent directories are created.

    Returns:
        The path written to.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sweep_spec_yaml(spec), encoding="utf-8")
    return out


def _base_config(spec: SweepSpec) -> ExperimentConfig:
    """Load the sweep's base configuration.

    Args:
        spec: The sweep spec.

    Returns:
        The base experiment config (from a scenario or a YAML path).

    Raises:
        ValueError: If neither or both base sources are set.
        KeyError: If ``base_scenario`` names no registered scenario.
        FileNotFoundError: If ``base`` points to a missing file.
    """
    from pdsim.config.scenarios import get_scenario_info

    if (spec.base is None) == (spec.base_scenario is None):
        raise ValueError("Provide exactly one of: base (a config path), or base_scenario (a name).")
    if spec.base_scenario is not None:
        return get_scenario_info(spec.base_scenario).config
    assert spec.base is not None
    return load_config(spec.base)


def resolve_composition(
    size: int,
    vary: str,
    vary_count: int,
    fixed: dict[str, int],
    fill: dict[str, float],
) -> dict[str, int]:
    """Resolve the three-bucket model to whole-agent counts (companion §2.2).

    The fill bucket divides the remainder by the **largest-remainder rule**
    (the seat-allocation arithmetic used to apportion legislative seats): each
    fill strategy gets the floor of its ideal share, then the leftover seats go
    one at a time to the largest fractional parts, ties broken by ascending
    machine name — so the result is perfectly deterministic (DECISIONS #67).

    Args:
        size: Total population size N.
        vary: The varying invader's machine name.
        vary_count: This member's invader count.
        fixed: Fixed strategy counts.
        fill: Fill strategy percentages (values summing to 100).

    Returns:
        Strategy machine name -> count, summing to ``size``, with zero-count
        entries dropped (configs require positive counts).

    Raises:
        ValueError: If the remainder is negative (more agents requested than
            exist) — defensive; validation catches this earlier.
    """
    remainder = size - vary_count - sum(fixed.values())
    if remainder < 0:
        raise ValueError(
            f"composition needs {vary_count + sum(fixed.values())} agents "
            f"(invader {vary_count} + fixed {sum(fixed.values())}) but the population "
            f"size is {size}."
        )
    # Largest-remainder allocation of `remainder` seats across the fill bucket.
    allocated: dict[str, int] = {}
    fractional: list[tuple[float, str]] = []
    for name, pct in fill.items():
        ideal = pct / 100.0 * remainder
        floor = math.floor(ideal)
        allocated[name] = floor
        fractional.append((ideal - floor, name))
    leftover = remainder - sum(allocated.values())
    # Hand out leftover seats to the largest fractional parts; ascending name
    # breaks ties (deterministic — the reproducibility contract, #67).
    fractional.sort(key=lambda item: (-item[0], item[1]))
    for _, name in fractional[:leftover]:
        allocated[name] += 1

    counts: dict[str, int] = {}
    for name, count in [(vary, vary_count), *fixed.items(), *allocated.items()]:
        counts[name] = counts.get(name, 0) + count
    return {name: count for name, count in counts.items() if count > 0}


def _apply_override(data: dict[str, Any], key: str, value: object) -> None:
    """Set one registry-keyed parameter into a config dict (in place).

    Reuses the config layer's section->field mapping (the #38 convention): a
    ``run.*`` key maps to a top-level field, everything else to
    ``data[section][field]``.

    Args:
        data: A mutable config dict (from ``config.model_dump``).
        key: A dotted registry key, e.g. ``"dynamics.selection_beta"``.
        value: The value to set.
    """
    prefix, field = key.split(".", maxsplit=1)
    if prefix == "run":
        data[field] = value
    else:
        data.setdefault(prefix, {})[field] = value


def expand(spec: SweepSpec) -> list[MemberPlan]:
    """Expand a spec into its member plans, in pinned deterministic order.

    The order is the cross product **composition counts (outermost) x each
    parameter axis's values (in listed order) x seeds (innermost)** — this
    fixes ``run_index`` and is a reproducibility contract (DECISIONS #66).
    Every member is fully validated here, before any run executes; a failure
    is a hard error naming the offending ``run_index`` (fail fast — the
    "generator, never a weakener" rule).

    Args:
        spec: The sweep spec (assumed already checked by
            :func:`sweep_validation_messages`).

    Returns:
        One :class:`MemberPlan` per combination, indexed 0..N-1.

    Raises:
        ValueError / pydantic.ValidationError: If any expanded combination
            fails to build a valid config (message names the ``run_index``).
    """
    base = _base_config(spec)
    counts = spec.composition.counts if spec.composition is not None else [None]
    param_value_lists = [axis.values for axis in spec.parameters]

    plans: list[MemberPlan] = []
    # itertools.product yields the rightmost element fastest, so listing seeds
    # last makes seeds the innermost loop and composition the outermost —
    # exactly the pinned order.
    for run_index, combo in enumerate(itertools.product(counts, *param_value_lists, spec.seeds)):
        vary_count = combo[0]
        param_values = combo[1:-1]
        seed = combo[-1]

        data = base.model_dump(mode="json")
        axis_values: dict[str, Any] = {}
        slug_parts: list[str] = []

        if spec.composition is not None:
            composition = resolve_composition(
                base.population.size,
                spec.composition.vary,
                vary_count,
                spec.composition.fixed,
                spec.composition.fill,
            )
            data.setdefault("population", {})["composition"] = composition
            axis_values[spec.composition.vary] = vary_count
            slug_parts.append(f"{spec.composition.vary}{vary_count}")

        for axis, value in zip(spec.parameters, param_values, strict=True):
            _apply_override(data, axis.key, value)
            axis_values[axis.key] = value
            slug_parts.append(f"{axis.key.split('.')[-1]}{value}")

        data["seed"] = seed
        axis_values["seed"] = seed
        slug_parts.append(f"seed{seed}")

        try:
            config = ExperimentConfig.model_validate(data)
        except Exception as error:  # re-raised with the run_index for diagnosis
            raise ValueError(
                f"sweep member run_index {run_index} ({', '.join(slug_parts)}) "
                f"is not a valid configuration: {error}"
            ) from error

        plans.append(
            MemberPlan(
                run_index=run_index,
                config=config,
                axis_values=axis_values,
                slug="_".join(slug_parts),
            )
        )
    return plans


def _validate_metric(ref: MetricRef) -> list[str]:
    """Validate one metric reference against the registry.

    Args:
        ref: The metric reference.

    Returns:
        Plain-language messages (empty if the reference is well-formed).
    """
    messages: list[str] = []
    try:
        info = get_metric(ref.metric)
    except KeyError as error:
        return [str(error).strip("'")]
    declared = {param.name: param for param in info.params}
    params = ref.params()
    for name in params:
        if name not in declared:
            allowed = ", ".join(declared) or "none - it takes no parameters"
            messages.append(
                f"metric {ref.metric!r} got unknown parameter {name!r}. "
                f"Valid parameters: {allowed}."
            )
    for name, param in declared.items():
        if param.default is None and name not in params:
            messages.append(
                f"metric {ref.metric!r} requires parameter {name!r} ({param.description})"
            )
    return messages


def sweep_validation_messages(spec: SweepSpec) -> list[str]:
    """Return every semantic problem with a sweep spec, in plain language.

    The single shared validation path (the #38/#48 pattern): the CLI and the
    future Sweep tab both call this, so the two never diverge. Structural
    problems (wrong types, unknown keys) are caught earlier by pydantic in
    :func:`load_sweep_spec`; this covers the cross-field, registry, and
    population-arithmetic rules.

    Args:
        spec: The structurally-valid spec to check.

    Returns:
        One message per failed check; an empty list means the spec is ready
        to expand.
    """
    from pdsim.core.strategies import all_strategy_names

    messages: list[str] = []
    roster = set(all_strategy_names())

    # --- Name --------------------------------------------------------------
    # The name becomes the sweeps/<name>/ folder, so it must be a safe token.
    # (_NAME_PATTERN was declared in M9.5a but wired to a check only in
    # M9.5b, when the Sweep tab made free-typed names likely.)
    if not _NAME_PATTERN.match(spec.name):
        messages.append(
            f"sweep name {spec.name!r} must be a lowercase token like 'tft_invasion' "
            "(letters, digits, and underscores, starting with a letter)."
        )

    # --- Base source -------------------------------------------------------
    base: ExperimentConfig | None = None
    if (spec.base is None) == (spec.base_scenario is None):
        messages.append(
            "Provide exactly one of: 'base' (a config path) or 'base_scenario' (a name)."
        )
    else:
        try:
            base = _base_config(spec)
        except (ValueError, KeyError, FileNotFoundError, OSError) as error:
            messages.append(f"base could not be loaded: {str(error).strip(chr(39))}")

    # --- Composition axis --------------------------------------------------
    comp = spec.composition
    if comp is not None:
        buckets = {"vary": {comp.vary}, "fixed": set(comp.fixed), "fill": set(comp.fill)}
        for name in [comp.vary, *comp.fixed, *comp.fill]:
            if name not in roster:
                messages.append(
                    f"composition names unknown strategy {name!r}. "
                    f"Valid strategies: {', '.join(sorted(roster))}."
                )
        if comp.vary in comp.fixed or comp.vary in comp.fill:
            messages.append(
                f"strategy {comp.vary!r} is the varying invader and cannot also be a "
                "fixed or fill strategy."
            )
        overlap = buckets["fixed"] & buckets["fill"]
        if overlap:
            messages.append(
                f"strateg{'ies' if len(overlap) > 1 else 'y'} {', '.join(sorted(overlap))} "
                "appear in both 'fixed' and 'fill' — each strategy belongs to one bucket."
            )
        if comp.fill:
            total = sum(comp.fill.values())
            if abs(total - 100) > _FILL_TOLERANCE:
                messages.append(
                    f"fill percentages sum to {total:g}, but they must sum to 100 "
                    "(they divide up the leftover seats)."
                )
            if any(pct < 0 for pct in comp.fill.values()):
                messages.append("fill percentages must not be negative.")
        if not comp.counts:
            messages.append("composition 'counts' must list at least one invader count.")
        if any(count < 0 for count in comp.counts):
            messages.append("composition 'counts' must all be zero or positive.")

        if base is not None and comp.counts:
            size = base.population.size
            fixed_total = sum(comp.fixed.values())
            vary_max = max(comp.counts)
            if vary_max + fixed_total > size:
                messages.append(
                    f"at the largest invader count ({vary_max}), the population needs "
                    f"{vary_max + fixed_total} agents (invader + fixed) but the base "
                    f"population size is {size}. Lower the counts, the fixed totals, or "
                    "raise the population size."
                )
            elif not comp.fill and any((size - count - fixed_total) > 0 for count in comp.counts):
                messages.append(
                    "some invader counts leave empty seats, but no 'fill' strategies are "
                    "given to occupy them. Add a fill bucket (summing to 100%) or choose "
                    "counts that fill the population exactly."
                )

    # --- Parameter axes ----------------------------------------------------
    for axis in spec.parameters:
        try:
            get_spec(axis.key)
        except KeyError as error:
            messages.append(str(error).strip("'"))
            continue
        if not axis.values:
            messages.append(f"parameter axis {axis.key!r} has no values to sweep.")
        for value in axis.values:
            try:
                validate_value(axis.key, value)
            except (ValueError, KeyError) as error:
                messages.append(str(error).strip("'"))

    # --- Seeds and metrics -------------------------------------------------
    if not spec.seeds:
        messages.append("'seeds' must list at least one random seed.")
    if not spec.metrics:
        messages.append("'metrics' must list at least one outcome metric.")
    for ref in spec.metrics:
        messages.extend(_validate_metric(ref))

    return messages
