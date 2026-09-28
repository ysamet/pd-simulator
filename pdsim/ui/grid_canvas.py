"""The grid component's Streamlit side: one declaration and one call (M11c; spec §1).

``pdsim_grid_canvas`` is a Streamlit CUSTOM COMPONENT: a small web page —
``index.html`` and ``grid_canvas.js`` in ``pdsim/ui/frontend/grid_canvas/``,
hand-written, no build step — that Streamlit serves from that folder and
shows inside an iframe. Calling it in the script sends the page its keyword
arguments; because every call passes a ``key``, Streamlit keeps the same
iframe alive from one script pass to the next (keyed identity), so the page
redraws in place instead of being torn down and remounted the way a changed
plotly chart is (DECISIONS #184(a)(vii), #190).

This is the ONLY module that imports Streamlit for the component (spec §1,
#194 R16); the arguments are built by the Streamlit-free
:mod:`pdsim.ui.grid_canvas_helpers`. Call :func:`grid_canvas` as a module
attribute (``grid_canvas.grid_canvas(…)``), never through a from-import, so
tests can observe the call.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import streamlit.components.v1 as components

COMPONENT_NAME = "pdsim_grid_canvas"
"""The name the component is declared under (spec §1).

Streamlit registers it with the declaring module's name in front:
``pdsim.ui.grid_canvas.pdsim_grid_canvas`` (1.1 Task 4B, DECISIONS #196).
"""

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend" / "grid_canvas"
"""The page's folder, inside the package so it ships in the wheel (#194 R16)."""

# Declared ONCE, when this module is first imported — from inside the app's
# script run, which is when Streamlit's server registers the folder it will
# serve the page from.
_component = components.declare_component(COMPONENT_NAME, path=str(FRONTEND_DIR))


def grid_canvas(args: Mapping[str, object], *, key: str) -> object | None:
    """Place (or update) the grid component in the current container.

    Args:
        args: The component's keyword arguments — see
            :func:`pdsim.ui.grid_canvas_helpers.live_grid_args`.
        key: The element key that gives the iframe its stable identity
            (``"live_grid"`` for the Run lab's run-area grid).

    Returns:
        The value the page last sent — always ``None`` in view mode, which
        never sends one.
    """
    return _component(key=key, default=None, **args)
