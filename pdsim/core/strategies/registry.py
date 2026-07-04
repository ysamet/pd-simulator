"""Strategy Registry — the single source of truth for the strategy roster.

Every playable strategy is declared exactly once as a :class:`StrategyInfo`
and registered here, mirroring the Parameter Registry idiom
(``pdsim/config/registry.py``): a registry is plain immutable *data* in one
module-level dict, written only at import time. The UI's strategy picker,
config validation of ``population.composition`` names, and milestone 4's
strategy-switch mutation ("pick a random strategy from the enabled roster")
all read from this one place (DECISIONS #25).

How to add a strategy:
    1. Create one module in ``pdsim/core/strategies/`` with the class and a
       trailing ``register_strategy(StrategyInfo(...))`` call.
    2. There is no step 2 — the package auto-discovers and imports every
       module in the folder, so the new strategy appears everywhere.

A functional-programming note (a learning thread of this project): a
:class:`StrategyInfo` stores the strategy *class itself* in ``factory``.
Classes are callables — ``info.factory()`` builds an instance — so a class
can be passed around and invoked exactly like a function. That is all a
"factory" is here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pdsim.config.registry import ParameterSpec, ParamValue
from pdsim.core.strategy import Strategy

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
"""Machine names are single lowercase tokens, e.g. ``tit_for_tat``.

A machine name is a *persistence surface*: saved ``config.yaml`` files refer
to strategies by it, so renaming one breaks the ability to re-run old
configs (hard rule 8). Treat renames as breaking changes.
"""


@dataclass(frozen=True, slots=True)
class StrategyInfo:
    """Complete declaration of one strategy (``docs/DESIGN.md`` §2.3).

    Attributes:
        name: Machine name used in configs and mutation, e.g. ``"pavlov"``.
        display_name: Human-readable name for UI widgets, e.g. ``"Pavlov"``.
        description: Plain-language explanation of how the strategy behaves,
            written for a non-expert. Mandatory — mirrors hard rule 3.
        factory: The strategy class; calling it (optionally with the keyword
            arguments described by ``params``) builds a fresh instance.
        params: Registry specs for this strategy's tunable parameters, if
            any. Each spec's key must be ``strategy.<name>.<param>``; the
            final ``<param>`` segment doubles as the constructor keyword.
        learn_more: Optional literature note for the curious.
    """

    name: str
    display_name: str
    description: str
    factory: type[Strategy]
    params: tuple[ParameterSpec, ...] = ()
    learn_more: str | None = None

    def __post_init__(self) -> None:
        """Check that the declaration is well-formed (fail fast at import).

        Raises:
            ValueError: If the machine name is malformed, the description is
                missing, or a parameter key does not live under this
                strategy's ``strategy.<name>.`` namespace.
        """
        if not _NAME_PATTERN.match(self.name):
            raise ValueError(
                f"Strategy machine name {self.name!r} must be a lowercase token like 'tit_for_tat'."
            )
        if not self.description.strip():
            raise ValueError(
                f"Strategy {self.name!r} has no description — hard rule 3 forbids this."
            )
        prefix = f"strategy.{self.name}."
        for spec in self.params:
            if not spec.key.startswith(prefix):
                raise ValueError(
                    f"Strategy {self.name!r} declares parameter {spec.key!r}; strategy "
                    f"parameter keys must start with {prefix!r} so the last key segment "
                    "can serve as the constructor keyword."
                )

    def param_names(self) -> tuple[str, ...]:
        """Return the constructor keyword for each declared parameter.

        Returns:
            The final segment of each parameter key, in declaration order —
            e.g. ``("cooperation_probability",)`` for Random(p).
        """
        return tuple(spec.key.rsplit(".", maxsplit=1)[-1] for spec in self.params)


# One module-level dict, written only via register_strategy(). Insertion
# order (= module discovery order, alphabetical) is the display order.
_STRATEGIES: dict[str, StrategyInfo] = {}


def register_strategy(info: StrategyInfo) -> StrategyInfo:
    """Add a strategy declaration to the roster.

    Args:
        info: The fully-declared strategy.

    Returns:
        The same info, so a strategy module can keep a handle if it wants —
        the same convention as the Parameter Registry's ``register``.

    Raises:
        ValueError: If a strategy with the same machine name is already
            registered — duplicate declarations are always a bug.
    """
    if info.name in _STRATEGIES:
        raise ValueError(
            f"Strategy {info.name!r} is already registered; machine names must be unique."
        )
    _STRATEGIES[info.name] = info
    return info


def get_strategy_info(name: str) -> StrategyInfo:
    """Look up a strategy declaration by machine name.

    Args:
        name: Machine name, e.g. ``"grim_trigger"``.

    Returns:
        The registered :class:`StrategyInfo`.

    Raises:
        KeyError: If no strategy with this name exists (the message lists
            the registered names to make typos easy to spot).
    """
    try:
        return _STRATEGIES[name]
    except KeyError:
        known = ", ".join(sorted(_STRATEGIES))
        raise KeyError(f"Unknown strategy {name!r}. Registered strategies: {known}") from None


def all_strategies() -> tuple[StrategyInfo, ...]:
    """Return every registered strategy, in registration (= display) order.

    Returns:
        An immutable snapshot of the roster.
    """
    return tuple(_STRATEGIES.values())


def all_strategy_names() -> tuple[str, ...]:
    """Return every registered machine name, in registration order.

    Returns:
        The names configs may use in ``population.composition``.
    """
    return tuple(_STRATEGIES)


def strategy_name_of(strategy: Strategy) -> str:
    """Return the machine name a strategy instance was registered under.

    The reverse of :func:`create_strategy` — used by the generation loop and
    the recorder to report population composition by name.

    Args:
        strategy: A live strategy instance.

    Returns:
        The machine name whose registered class is exactly this instance's
        class.

    Raises:
        KeyError: If the instance's class is not registered (e.g. a test
            stub) — such strategies have no reportable identity.
    """
    for info in _STRATEGIES.values():
        if type(strategy) is info.factory:
            return info.name
    raise KeyError(
        f"{type(strategy).__name__} is not a registered strategy class; "
        "only roster strategies have machine names."
    )


def create_strategy(name: str, **overrides: ParamValue) -> Strategy:
    """Build a fresh strategy instance by machine name.

    This is the constructor the engine and UI go through: milestone 4's
    mutation draws a random name and calls this; milestone 6's UI passes
    the user's parameter choices as ``overrides``.

    Args:
        name: Machine name, e.g. ``"random"``.
        **overrides: Parameter values keyed by constructor keyword (the last
            segment of the parameter's registry key). Omitted parameters
            fall back to their registry defaults inside the constructor.

    Returns:
        A new instance of the requested strategy.

    Raises:
        KeyError: If the name is unknown.
        ValueError: If an override names a parameter the strategy does not
            declare, or its value violates the parameter's registry spec
            (raised by the strategy's own constructor — validation lives in
            exactly one place).
    """
    info = get_strategy_info(name)
    valid = info.param_names()
    unknown = sorted(set(overrides) - set(valid))
    if unknown:
        allowed = ", ".join(valid) if valid else "none — it has no parameters"
        raise ValueError(
            f"Strategy {name!r} got unknown parameter(s): {', '.join(unknown)}. "
            f"Valid parameters: {allowed}."
        )
    return info.factory(**overrides)
