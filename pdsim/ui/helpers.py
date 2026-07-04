"""Streamlit-free helpers behind the app: config <-> widget-state mapping.

Everything with a branch worth testing lives here, importable without
Streamlit (DECISIONS #38): flattening a config into widget values,
assembling widget values back into a validated ``ExperimentConfig``,
choosing a default population mix, and turning pydantic errors into
plain-language strings. ``app.py`` stays presentation-only.

Widget state is a flat mapping keyed by Parameter Registry keys (e.g.
``"dynamics.selection_beta"``), which is also how the app names its
Streamlit widget keys — the registry key is the single identifier a
parameter has everywhere.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import ValidationError

from pdsim.config.experiment import ExperimentConfig
from pdsim.config.registry import ParameterSpec, ParamValue, all_specs

# Registry-key prefix -> ExperimentConfig section name. "run" is special:
# its parameters live at the top level of the config (DECISIONS #34).
_SECTIONS = ("game", "matching", "match", "population", "dynamics")


def panel_specs() -> tuple[ParameterSpec, ...]:
    """Return the specs the generated parameter panel renders.

    Everything in the Parameter Registry except strategy parameters
    (``strategy.*``), which the app renders in its own per-strategy
    expander, and ``population.composition``, which has no spec (it is a
    structural section, rendered bespoke).

    Returns:
        Specs in registration (= display) order.
    """
    return tuple(spec for spec in all_specs() if not spec.key.startswith("strategy."))


def widget_values_from_config(config: ExperimentConfig) -> dict[str, ParamValue]:
    """Flatten a config into registry-keyed widget values.

    The inverse of :func:`build_config` for every scalar parameter —
    used to load a scenario into the parameter panel.

    Args:
        config: Any validated experiment config (e.g. a scenario's).

    Returns:
        Registry key → value for every registry-backed field
        (composition and strategy_params are separate — see
        ``config.population.composition`` / ``config.strategy_params``).
    """
    models = [
        config,
        config.game,
        config.matching,
        config.match,
        config.population,
        config.dynamics,
    ]
    values: dict[str, ParamValue] = {}
    for model in models:
        for field, key in type(model)._registry_keys.items():
            values[key] = getattr(model, field)
    return values


def default_widget_values() -> dict[str, ParamValue]:
    """Return registry defaults for every panel parameter ("Custom" start).

    Returns:
        Registry key → default value.
    """
    return {spec.key: spec.default for spec in panel_specs()}


def default_composition(size: int, names: Sequence[str]) -> dict[str, int]:
    """Split a population size evenly across strategies ("Custom" start).

    The Parameter Registry has no composition default (an experiment must
    say what it starts with), so the UI picks the most neutral one: an even
    split, remainder going to the earliest names (DECISIONS #40).

    Args:
        size: Total number of agents to distribute.
        names: Strategy machine names, in display order.

    Returns:
        Name → count, always summing to ``size`` (some counts may be 0
        when there are more strategies than agents).
    """
    base, remainder = divmod(size, len(names))
    return {name: base + (1 if i < remainder else 0) for i, name in enumerate(names)}


def build_config(
    values: Mapping[str, ParamValue],
    composition: Mapping[str, int],
    strategy_params: Mapping[str, Mapping[str, ParamValue]] | None = None,
) -> ExperimentConfig:
    """Assemble widget state into a validated experiment config.

    Args:
        values: Registry key → widget value for every scalar parameter.
        composition: Strategy machine name → agent count from the mix
            widgets; zero counts are dropped here (configs require every
            listed strategy to have at least one agent).
        strategy_params: Optional per-strategy parameter overrides.

    Returns:
        The validated config.

    Raises:
        pydantic.ValidationError: If any value is out of range, the mix
            doesn't sum to the population size, and so on — with the
            registry's plain-language messages.
    """
    data: dict[str, object] = {section: {} for section in _SECTIONS}
    for key, value in values.items():
        prefix, field = key.split(".", maxsplit=1)
        if prefix == "run":
            data[field] = value
        else:
            data[prefix][field] = value  # type: ignore[index]
    data["population"]["composition"] = {  # type: ignore[index]
        name: count for name, count in composition.items() if count > 0
    }
    if strategy_params:
        data["strategy_params"] = {
            name: dict(params) for name, params in strategy_params.items() if params
        }
    return ExperimentConfig.model_validate(data)


def collect_strategy_params(
    values: Mapping[str, ParamValue],
) -> dict[str, dict[str, ParamValue]]:
    """Turn strategy-parameter widget values into a config override mapping.

    Only values that differ from their registry defaults are included, so
    an untouched panel produces a config with no ``strategy_params``
    section at all — the defaults stay implicit (DECISIONS #41).

    Args:
        values: ``strategy.<name>.<param>`` registry key → widget value.

    Returns:
        Strategy name → {param: value} for the changed values only.
    """
    overrides: dict[str, dict[str, ParamValue]] = {}
    for spec in all_specs():
        if not spec.key.startswith("strategy."):
            continue
        value = values.get(spec.key, spec.default)
        if value != spec.default:
            _, name, param = spec.key.split(".", maxsplit=2)
            overrides.setdefault(name, {})[param] = value
    return overrides


def validation_messages(error: ValidationError) -> list[str]:
    """Extract the plain-language messages from a pydantic error.

    The registry writes user-facing messages already; this strips
    pydantic's framing so ``st.error`` shows clean sentences.

    Args:
        error: The exception raised by config validation.

    Returns:
        One human-readable message per failed check.
    """
    messages = []
    for item in error.errors():
        message = item["msg"]
        for prefix in ("Value error, ", "Assertion error, "):
            message = message.removeprefix(prefix)
        messages.append(message)
    return messages
