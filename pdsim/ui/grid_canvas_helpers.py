"""Streamlit-free helpers for the grid component (M11c; spec §1–§2; DECISIONS #194–#196).

The grid component (``pdsim_grid_canvas``, declared in ``ui/grid_canvas.py``)
is a small web page Streamlit hosts in an iframe; everything it draws
arrives as the keyword arguments of one Python call. This module builds
those arguments — and ONLY builds them: it imports no Streamlit, so every
function here is a pure function pinned by plain pytest (#190 R6, #194 R13),
while the page's JavaScript is tested by the spec's Validation checklist.

The contract (spec §2, as refined by #195 F3/F4):

* ``cells`` — the WHOLE grid, one byte per site in row-major site order
  (site id = row × cols + col): 0 for an empty site, the strategy's
  registry position + 1 otherwise. Sent as a Python ``bytes`` argument,
  which Streamlit 1.58 delivers to the page as a binary ``Uint8Array``
  (1.1 Task 0 (a), #196) — 250,000 bytes for a 500 × 500 grid.
* ``palette`` / ``names`` — index 0 is the empty site (colour ``None``:
  the page takes it from the theme; name "Empty"), index i ≥ 1 the i-th
  registered strategy's colour and display name.
* ``key_entries`` — palette indices for the colour key, in display order,
  Empty (0) last.
* ``version`` — the text ``"<run>:<period>"``; the page skips a frame whose
  version, size and colours it has already drawn.

Only view mode (the Run lab's run-area grid) is built so far: the painter's
argument builder and stroke applier are sub-prompt 1.3's; the timer's
interval and work-budget functions sub-prompt 1.2's.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from pdsim.config.experiment import ExperimentConfig
from pdsim.core.events import AgentSnapshot
from pdsim.core.strategies import all_strategies
from pdsim.viz import charts

EMPTY_INDEX = 0
"""The palette index — and cell byte — of an empty site."""

EMPTY_NAME = "Empty"
"""The empty site's name in the colour key."""

VIEW_MODE = "view"
"""The component's read-only mode: zoom, pan and hover, never a value sent back."""


def strategy_codes() -> dict[str, int]:
    """Map every registered strategy to its cell byte: registry position + 1.

    Returns:
        Machine name → code in ``1..len(registered strategies)``.

    Raises:
        ValueError: If more strategies are registered than one byte can
            index (255) — the one-byte-per-site contract would break.
    """
    names = [info.name for info in all_strategies()]
    if len(names) > 255:
        raise ValueError(f"{len(names)} strategies do not fit one byte per site (at most 255).")
    return {name: position + 1 for position, name in enumerate(names)}


def grid_palette() -> list[str | None]:
    """The component's palette: ``None`` for an empty site, then each strategy's colour.

    Strategy colours come from :func:`pdsim.viz.charts.strategy_colors` — the
    one stable per-strategy mapping every chart uses (#37) — in registry
    order, so palette index i is the i-th registered strategy, matching the
    cell bytes of :func:`encode_cells`.

    Returns:
        ``[None, colour of strategy 1, colour of strategy 2, …]`` (``"#rrggbb"``).
    """
    colors = charts.strategy_colors()
    return [None, *(colors[info.name] for info in all_strategies())]


def grid_names() -> list[str]:
    """The component's names: "Empty", then each strategy's display name, in registry order.

    Returns:
        A list aligned index for index with :func:`grid_palette`.
    """
    return [EMPTY_NAME, *(info.display_name for info in all_strategies())]


def placements_from_snapshots(snapshots: Sequence[AgentSnapshot]) -> dict[int, str]:
    """The run-area grid's per-site data from one period's agent snapshots.

    The latest snapshot IS the render state (DESIGN §2.12, Design 10): each
    :class:`~pdsim.core.events.AgentSnapshot` names its site and strategy.
    Agents without a site (a well-mixed run) are skipped.

    Args:
        snapshots: One period's agent snapshots.

    Returns:
        Site id → strategy machine name, for occupied sites only.
    """
    return {
        snapshot.site_id: snapshot.strategy
        for snapshot in snapshots
        if snapshot.site_id is not None
    }


def encode_cells(rows: int, cols: int, placements: Mapping[int, str]) -> bytes:
    """Encode the whole grid as one byte per site, row-major (spec §2; #194 R1).

    The source is site-keyed (site id → strategy, the form the live grid's
    snapshots give), so the output always has exactly ``rows × cols`` bytes;
    a placement that cannot belong to this grid — a site id outside
    ``0 … rows × cols − 1`` — is the "wrong length" refusal. Vectorised with
    numpy: the ids and codes become two arrays and one fancy-indexed
    assignment writes every occupied byte at once.

    Args:
        rows: Grid row count (≥ 1).
        cols: Grid column count (≥ 1).
        placements: Site id → strategy machine name, occupied sites only.

    Returns:
        ``rows × cols`` bytes: 0 for an empty site, the strategy's registry
        position + 1 otherwise.

    Raises:
        ValueError: On a non-positive dimension, a site id outside the
            grid, or a strategy the registry does not know.
    """
    if rows < 1 or cols < 1:
        raise ValueError(f"A grid needs at least one row and one column, not {rows} × {cols}.")
    site_count = rows * cols
    out = np.zeros(site_count, dtype=np.uint8)
    if placements:
        codes = strategy_codes()
        count = len(placements)
        sites = np.fromiter(placements.keys(), dtype=np.int64, count=count)
        try:
            # `map` with the dict's own lookup method is the fast way to
            # translate 250,000 names (≈ 15 ms against ≈ 23 ms for the
            # equivalent generator expression at 500 × 500; #196).
            values = np.fromiter(
                map(codes.__getitem__, placements.values()), dtype=np.uint8, count=count
            )
        except KeyError as error:
            raise ValueError(f"Unknown strategy {error.args[0]!r} in the grid.") from None
        if int(sites.min()) < 0 or int(sites.max()) >= site_count:
            bad = int(sites.min()) if int(sites.min()) < 0 else int(sites.max())
            raise ValueError(f"Site id {bad} lies outside the {rows} × {cols} grid.")
        out[sites] = values
    return out.tobytes()


def live_key_entries(config: ExperimentConfig) -> list[int]:
    """The live grid's colour key: every strategy the run CAN contain, then Empty (#195 F4).

    With ``dynamics.mutation_rate`` above 0 a mutant can be any registered
    strategy (mutation draws from the full roster, DESIGN §2.7), so the key
    lists them all; at 0 the run can only ever contain the strategies
    founded at generation 0 (composition count above zero). Computed once
    from the config frozen at the Run click, so the key never changes
    mid-run — neither the key nor the frame height jumps.

    Args:
        config: The run's frozen config.

    Returns:
        Palette indices in registry order, with Empty (0) last.
    """
    codes = strategy_codes()
    if config.dynamics.mutation_rate > 0:
        entries = list(codes.values())
    else:
        founded = {name for name, count in config.population.composition.items() if count > 0}
        entries = [code for name, code in codes.items() if name in founded]
    return [*entries, EMPTY_INDEX]


def frame_version(run_number: int, period: int) -> str:
    """A live frame's version, unique across runs: ``"<run>:<period>"`` (#195 F3).

    The period index alone repeats from one run to the next, and the page
    skips a frame whose version, size and colours match the last one drawn
    — so a second short run could leave the first run's grid on screen.
    The run number (increased at every Run click) makes every run's frames
    distinct.

    Args:
        run_number: The browser session's Run-click counter.
        period: The period index of the snapshot drawn.

    Returns:
        The version text sent to the page.
    """
    return f"{run_number}:{period}"


def live_grid_args(
    rows: int,
    cols: int,
    placements: Mapping[int, str],
    *,
    key_entries: Sequence[int],
    version: str,
    debug: bool = False,
) -> dict[str, object]:
    """The view-mode argument dict for the Run lab's run-area grid (spec §2).

    Args:
        rows: Grid row count.
        cols: Grid column count.
        placements: Site id → strategy machine name, occupied sites only.
        key_entries: Palette indices for the colour key (see
            :func:`live_key_entries`).
        version: The frame's version (see :func:`frame_version`).
        debug: Show the page's frame-time line (``?grid_debug=1``).

    Returns:
        Keyword arguments for :func:`pdsim.ui.grid_canvas.grid_canvas`:
        ``cells`` (bytes), ``rows``, ``cols``, ``palette``, ``names``,
        ``key_entries``, ``mode`` ("view"), ``border_min_px`` (the ONE home,
        :data:`pdsim.viz.charts.BORDER_MIN_SIDE_PX`), ``version`` and
        ``debug``.
    """
    return {
        "cells": encode_cells(rows, cols, placements),
        "rows": int(rows),
        "cols": int(cols),
        "palette": grid_palette(),
        "names": grid_names(),
        "key_entries": [int(index) for index in key_entries],
        "mode": VIEW_MODE,
        "border_min_px": charts.BORDER_MIN_SIDE_PX,
        "version": str(version),
        "debug": bool(debug),
    }
