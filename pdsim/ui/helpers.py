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

from pdsim.config.experiment import (
    ExperimentConfig,
    resolve_initial_energy,
    resolve_senescence_factor,
)
from pdsim.config.registry import ParameterSpec, ParamValue, all_specs

# Registry-key prefix -> ExperimentConfig section name. "run" is special:
# its parameters live at the top level of the config (DECISIONS #34).
_SECTIONS = ("game", "matching", "match", "population", "dynamics", "output")

IGNORED_IN_TOURNAMENT = (
    "dynamics.generations",
    "dynamics.reproduction_mode",
    "dynamics.selection_rule",
    "dynamics.selection_beta",
    "dynamics.selection_tournament_k",
    "dynamics.selection_elite_fraction",
    "dynamics.selection_threshold_multiplier",
    "dynamics.mutation_rate",
    "dynamics.score_accounting",
    "dynamics.accounting_window",
    "dynamics.accounting_discount",
    "dynamics.reproduction_threshold",
    "dynamics.offspring_stake",
    "dynamics.initial_energy",
    "dynamics.basic_living_cost",
    "dynamics.engagement_cost",
    "dynamics.reproduction_overhead",
    "dynamics.capital_return_rate",
    "dynamics.carrying_capacity",
    "dynamics.base_hazard",
    "dynamics.senescence_factor",
    "dynamics.max_age",
)
"""Parameters that exist but have no effect in tournament mode (DECISIONS #34)."""

_ECONOMY_PARAMS = (
    "dynamics.reproduction_threshold",
    "dynamics.offspring_stake",
    "dynamics.initial_energy",
    "dynamics.basic_living_cost",
    "dynamics.engagement_cost",
    "dynamics.reproduction_overhead",
    "dynamics.capital_return_rate",
    "dynamics.carrying_capacity",
    "dynamics.base_hazard",
    "dynamics.senescence_factor",
    "dynamics.max_age",
)
"""The eleven economy knobs — read only under 'energy_economy' (M10a)."""

_IMITATION_PARAMS = (
    "dynamics.selection_rule",
    "dynamics.selection_beta",
    "dynamics.selection_tournament_k",
    "dynamics.selection_elite_fraction",
    "dynamics.selection_threshold_multiplier",
    "dynamics.score_accounting",
    "dynamics.accounting_window",
    "dynamics.accounting_discount",
)
"""The selection + accounting families — inert under 'energy_economy' (M10a).

``dynamics.mutation_rate`` is deliberately NOT here: both reproduction modes
consume μ (imitation slots and economy newborns alike).
"""

_RULE_PARAMS = {
    "dynamics.selection_beta": "fermi",
    "dynamics.selection_tournament_k": "tournament_k",
    "dynamics.selection_elite_fraction": "truncation",
    "dynamics.selection_threshold_multiplier": "threshold_cloning",
}
"""Selection-rule parameter -> the one rule that reads it (DECISIONS #63)."""

_ACCOUNTING_PARAMS = {
    "dynamics.accounting_window": "sliding_window",
    "dynamics.accounting_discount": "exponential_discount",
}
"""Accounting parameter -> the one accounting choice that reads it (#64)."""


def greying(key: str, values: Mapping[str, ParamValue]) -> tuple[bool, str]:
    """Decide whether a panel widget is greyed out right now, and why.

    The #34 greyed-never-hidden pattern, centralized: a parameter that the
    current widget choices make irrelevant is disabled with an explanatory
    tooltip note — never removed from the panel. The cases:

    * every dynamics parameter, ignored in tournament mode;
    * ``run.tournament_cycles``, ignored in evolution mode;
    * ``matching.opponents_per_agent``, ignored under round-robin matching
      (keyed off the matcher widget's current value, not the run mode, #57);
    * the COARSE reproduction-mode split (M10a): under ``energy_economy``
      the whole selection + accounting families are inert (differential
      survival IS the selection); under ``imitation`` the eleven economy
      knobs are. This check runs BEFORE the per-rule/per-accounting checks
      below, so the paradigm-level note wins over the rule-level one;
    * each selection rule's parameters, ignored unless that rule is
      selected (keyed off the selection-rule widget, #63);
    * each accounting rule's parameter, ignored unless that accounting is
      selected (keyed off the score-accounting widget, #64).

    The app renders widgets in registry order, so by the time a dependent
    widget renders, the value it keys off (``run.mode``, a matcher or rule
    selectbox) is already in ``values``.

    Args:
        key: The registry key of the widget about to render.
        values: The widget values gathered so far this script run.

    Returns:
        ``(disabled, note)`` — whether to grey the widget out, and the
        tooltip line explaining why (empty when enabled).
    """
    tournament = values.get("run.mode") == "tournament"
    if key == "run.tournament_cycles" and not tournament:
        return True, "NOTE: only used in tournament mode — ignored right now."
    if key in IGNORED_IN_TOURNAMENT and tournament:
        return True, (
            "NOTE: this parameter exists but is IGNORED in tournament mode — "
            "nothing evolves there (see the run-mode help)."
        )
    if key == "matching.opponents_per_agent" and values.get("matching.matcher") == "round_robin":
        return True, (
            "NOTE: this parameter exists but is IGNORED under round-robin "
            "matching — every pair plays once anyway. Switch the matching "
            "scheme to 'random_k' to use it."
        )
    reproduction = values.get("dynamics.reproduction_mode")
    if key in _IMITATION_PARAMS and reproduction == "energy_economy":
        return True, (
            "NOTE: this parameter exists but is IGNORED in the energy economy "
            "— nobody copies anyone; differential survival IS the selection."
        )
    if key in _ECONOMY_PARAMS and reproduction == "imitation":
        return True, (
            "NOTE: this parameter is only read in the energy economy — "
            "IGNORED under imitation dynamics."
        )
    rule = values.get("dynamics.selection_rule")
    if key in _RULE_PARAMS and rule is not None and rule != _RULE_PARAMS[key]:
        return True, (
            f"NOTE: this parameter is only read by the {_RULE_PARAMS[key]!r} "
            "selection rule — IGNORED under the currently selected rule."
        )
    accounting = values.get("dynamics.score_accounting")
    if key in _ACCOUNTING_PARAMS and accounting not in (None, _ACCOUNTING_PARAMS[key]):
        return True, (
            f"NOTE: this parameter is only read by the {_ACCOUNTING_PARAMS[key]!r} "
            "score accounting — IGNORED under the currently selected choice."
        )
    return False, ""


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
    # The two derived defaults (M10a): a validated config always holds the
    # RESOLVED plain numbers (hard rule 8), so "auto" is not stored. The
    # loss-free inverse: a stored value that equals what the auto rule
    # would produce is presented as auto (None) — re-assembling the widget
    # values resolves it straight back to the same number, so the round
    # trip is exact, and the auto widgets load unchecked as expected.
    if values["dynamics.initial_energy"] == resolve_initial_energy(
        None,
        values["dynamics.offspring_stake"],  # type: ignore[arg-type]
    ):
        values["dynamics.initial_energy"] = None
    if values["dynamics.senescence_factor"] == resolve_senescence_factor(
        None,
        values["dynamics.base_hazard"],  # type: ignore[arg-type]
        values["dynamics.max_age"],  # type: ignore[arg-type]
    ):
        values["dynamics.senescence_factor"] = None
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
