"""The strategy roster: one module per strategy, discovered automatically.

Importing this package guarantees the full roster is registered: the
discovery loop below imports every module in the folder, and each module's
trailing ``register_strategy(StrategyInfo(...))`` call runs as a side effect
of that import. Adding a strategy is therefore just dropping a new module in
this folder — the UI, config validation, and mutation all see it with zero
further edits (``docs/DESIGN.md`` §2.3, DECISIONS #25).

The registry API itself lives in :mod:`pdsim.core.strategies.registry` and
is re-exported here for convenient importing.
"""

from __future__ import annotations

# `importlib` imports modules from their dotted-path *names* at runtime —
# the programmatic equivalent of an `import` statement.
import importlib

# `pkgutil.iter_modules` lists the modules sitting inside a package folder
# WITHOUT importing them; combined with importlib we get auto-discovery.
import pkgutil

from pdsim.core.strategies.registry import (
    StrategyInfo,
    all_strategies,
    all_strategy_names,
    create_strategy,
    get_strategy_info,
    register_strategy,
    strategy_name_of,
)

__all__ = [
    "StrategyInfo",
    "all_strategies",
    "all_strategy_names",
    "create_strategy",
    "get_strategy_info",
    "register_strategy",
    "strategy_name_of",
]


def _discover() -> None:
    """Import every strategy module so its registration call runs.

    Modules are discovered in alphabetical order, which therefore becomes
    the roster's registration (= UI display) order. The ``registry`` module
    itself is skipped — it is the catalog, not an entry in it.

    Note for strategy authors: while this loop runs, this ``__init__`` is
    only partially executed, so strategy modules must import the registry
    through its full path (``pdsim.core.strategies.registry``), never from
    the package itself.
    """
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name == "registry":
            continue
        importlib.import_module(f"{__name__}.{module_info.name}")


_discover()
