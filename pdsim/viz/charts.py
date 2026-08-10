"""Chart builders: RunTimeseries in, plotly Figure out (DESIGN §4).

Pure functions with no Streamlit imports — they are importable and testable
headlessly, which is what lets the viz layer survive a future dashboard
migration (§6.4): any UI that can render a plotly figure can render these.

Colors are stable per strategy (DECISIONS #37): the mapping is derived once
from the Strategy Registry's order, so a strategy keeps its color across
charts, modes, and reruns. Legends show display names; machine names stay
internal.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative

from pdsim.core.events import RunFinished
from pdsim.core.strategies import all_strategies
from pdsim.core.timeseries import RunTimeseries

_FALLBACK_COLOR = "#888888"
"""Color for strategy names outside the registry (defensive only)."""

PIXEL_ARRAY_THRESHOLD = 2500
"""Site count above which the grid renders as one pixel array (DECISIONS #145).

The rendering contract (#109, DESIGN §6.3) says that past a few thousand
cells the grid must stop being drawn as individually bordered, individually
hover-labelled cells, or redraw crawls. 2,500 — a 50×50 grid — sits
comfortably inside "a few thousand": beyond it, rebuilding the bordered
heatmap's per-cell gap strokes and hover-label array on every live redraw
(#94's cadence) is wasted work at cell sizes where the borders are barely
visible anyway. A named constant so the choice is inspectable and adjustable.
"""

CELL_FLOOR_PX = 3
"""The cell-side floor in pixels (#109): below ≈ 3 px cells are indistinguishable."""

BORDER_MIN_SIDE_PX = 6
"""The naive cell side below which the bordered path stops earning its keep.

The bordered heatmap spends 1 px of every cell on its gap stroke; at 6 px
that is a sixth of the cell and the borders still read as borders, but
below it the gaps eat the cells and the grid degrades into disconnected
dots (the owner's 200×10 validation finding — DECISIONS #149). So the
pixel-array path also takes over, whatever the site count, once cells
would be this small: an elongated grid shrinks its cells long before its
site count reaches :data:`PIXEL_ARRAY_THRESHOLD`.
"""

_NOMINAL_MAX_WIDTH = 700
"""Canvas width the floor is judged against — Streamlit's content-column width."""

_NOMINAL_MAX_HEIGHT = 450
"""Canvas height the floor is judged against — plotly's default figure height."""

_MIN_CANVAS_WIDTH = 320
"""The narrowest explicit canvas a floored figure may take.

A floored tall-narrow grid needs only ``cols × 3 px`` for its cells, but
the figure chrome does not shrink with it: the title and the plotly
modebar (zoom/pan/autoscale buttons) collide on a strip a few dozen
pixels wide (DECISIONS #149). The canvas therefore never drops below
this width; the square-cell constraint simply centres the narrow grid in
the extra room.
"""


def strategy_colors() -> dict[str, str]:
    """Map every registered strategy to a stable color.

    The Strategy Registry's registration order indexes into plotly's
    qualitative palette, so the mapping never depends on which strategies
    happen to appear in a particular run.

    Returns:
        Machine name -> CSS color string.
    """
    palette = qualitative.Plotly
    return {info.name: palette[i % len(palette)] for i, info in enumerate(all_strategies())}


def _naive_cell_side(rows: int, cols: int) -> float:
    """The cell side the nominal canvas would give this grid, un-floored.

    The rendering contract's arithmetic (#109): the side is
    ``min(max_width / cols, max_height / rows)`` — cells are square, so the
    tighter dimension decides.

    Args:
        rows: Grid row count.
        cols: Grid column count.

    Returns:
        The naive side in pixels (fractional).
    """
    return min(_NOMINAL_MAX_WIDTH / cols, _NOMINAL_MAX_HEIGHT / rows)


def pixel_array_active(rows: int, cols: int) -> bool:
    """Report whether a grid renders as a pixel array rather than bordered cells.

    The switch behind :func:`grid_chart`'s two paths, exposed so the app's
    §12 readout ("pixel-array rendering active") and the renderer can never
    disagree — both read this one predicate (DECISIONS #145/#149). Two
    triggers, either sufficient:

    * the site count exceeds :data:`PIXEL_ARRAY_THRESHOLD` — the DESIGN
      §6.3 "past a few thousand cells" regime, where per-cell borders and
      hover labels make redraw crawl; or
    * the naive cell side falls below :data:`BORDER_MIN_SIDE_PX` — the
      small-cell regime an ELONGATED grid reaches long before its site
      count does (200×10 is only 2,000 sites, but its cells sit at the
      3 px floor, where the bordered path's gaps reduce the grid to
      disconnected dots).

    On square grids the second trigger never fires first, so the 50×50
    parity with the plain threshold is unchanged.

    Args:
        rows: Grid row count.
        cols: Grid column count.

    Returns:
        True when either trigger holds.
    """
    return rows * cols > PIXEL_ARRAY_THRESHOLD or _naive_cell_side(rows, cols) < BORDER_MIN_SIDE_PX


def floored_canvas(rows: int, cols: int) -> tuple[int, int] | None:
    """Return an explicit canvas size when the ≈ 3 px cell floor binds.

    The rendering contract (#109): when the naive cell side
    (:func:`_naive_cell_side`, against the nominal canvas — Streamlit's
    content column by plotly's default height) falls below
    :data:`CELL_FLOOR_PX`, the side is floored and the CANVAS grows
    instead — the container may scroll, but cells never vanish. The width
    never drops below :data:`_MIN_CANVAS_WIDTH`, so the figure chrome
    (title, modebar) keeps its room on tall-narrow grids (#149).

    Args:
        rows: Grid row count.
        cols: Grid column count.

    Returns:
        ``(width, height)`` in pixels — the floored cell grid plus the
        figure margins — when the floor binds; ``None`` when the grid fits
        the nominal canvas at ≥ 3 px per cell. Callers rendering a floored
        figure must NOT stretch it back into the container (that would
        shrink the cells below the floor again).
    """
    if _naive_cell_side(rows, cols) >= CELL_FLOOR_PX:
        return None
    # The layout margins below: l=20 + r=20 horizontally, t=40 + b=20
    # vertically.
    return (max(cols * CELL_FLOOR_PX + 40, _MIN_CANVAS_WIDTH), rows * CELL_FLOOR_PX + 60)


def _parse_css_color(color: str) -> tuple[int, int, int]:
    """Turn a palette colour string into an RGB triple for pixel data.

    Args:
        color: ``"#rrggbb"`` or ``"rgb(r, g, b)"`` — the two forms plotly's
            qualitative palettes use.

    Returns:
        ``(red, green, blue)``, each 0-255.

    Raises:
        ValueError: For any other colour syntax (nothing in the palette
            produces one; defensive).
    """
    if color.startswith("#") and len(color) == 7:
        return (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))
    if color.startswith("rgb"):
        inside = color[color.index("(") + 1 : color.index(")")]
        red, green, blue = (int(float(part)) for part in inside.split(",")[:3])
        return (red, green, blue)
    raise ValueError(f"Unsupported CSS colour {color!r}.")


def _bordered_cells_trace(
    rows: int, cols: int, placements: dict[int, str], colors: dict[str, str]
) -> go.Heatmap:
    """Build the small-grid trace: bordered, hover-labelled cells.

    Args:
        rows: Grid row count.
        cols: Grid column count.
        placements: Site id -> strategy machine name (occupied sites only).
        colors: The one strategy -> colour mapping both render paths share.

    Returns:
        A heatmap trace with 1 px cell borders and per-cell hover labels.
    """
    names = sorted({name for name in placements.values()})
    index_of = {name: i for i, name in enumerate(names)}
    # z holds the strategy INDEX per cell (None where empty); the discrete
    # colorscale below turns those indices into the project's stable
    # per-strategy colours rather than a continuous gradient.
    z: list[list[float | None]] = [[None] * cols for _ in range(rows)]
    labels: list[list[str]] = [["empty"] * cols for _ in range(rows)]
    for site_id, name in placements.items():
        row, col = divmod(site_id, cols)
        if 0 <= row < rows and 0 <= col < cols:
            z[row][col] = float(index_of[name])
            labels[row][col] = _display_name(name)

    if names:
        # One flat band per strategy: stop i covers [i/n, (i+1)/n], so a cell
        # holding index i lands squarely inside its own band.
        span = 1.0 / len(names)
        colorscale: list[list[float | str]] = []
        for i, name in enumerate(names):
            color = colors.get(name, _FALLBACK_COLOR)
            colorscale.append([i * span, color])
            colorscale.append([min(1.0, (i + 1) * span), color])
    else:
        colorscale = [[0.0, _FALLBACK_COLOR], [1.0, _FALLBACK_COLOR]]

    return go.Heatmap(
        z=z,
        text=labels,
        colorscale=colorscale,
        zmin=-0.5,
        zmax=max(len(names) - 0.5, 0.5),
        showscale=False,
        xgap=1,
        ygap=1,
        hovertemplate="row %{y}, col %{x}<br>%{text}<extra></extra>",
    )


def _pixel_array_trace(
    rows: int, cols: int, placements: dict[int, str], colors: dict[str, str]
) -> go.Image:
    """Build the large-grid trace: the whole world as one RGBA image.

    Visually equivalent to :func:`_bordered_cells_trace` apart from the cell
    borders, which this path drops (at ≤ 3 px they are invisible anyway):
    same colours from the same mapping, empty sites transparent so the same
    plot background shows through them.

    Args:
        rows: Grid row count.
        cols: Grid column count.
        placements: Site id -> strategy machine name (occupied sites only).
        colors: The one strategy -> colour mapping both render paths share.

    Returns:
        An image trace, one pixel of z-data per site.
    """
    transparent = (0, 0, 0, 0)
    pixels: list[list[tuple[int, int, int, int]]] = [[transparent] * cols for _ in range(rows)]
    for site_id, name in placements.items():
        row, col = divmod(site_id, cols)
        if 0 <= row < rows and 0 <= col < cols:
            red, green, blue = _parse_css_color(colors.get(name, _FALLBACK_COLOR))
            pixels[row][col] = (red, green, blue, 255)
    return go.Image(
        z=pixels,
        colormodel="rgba",
        hovertemplate="row %{y}, col %{x}<extra></extra>",
    )


def grid_chart(
    rows: int,
    cols: int,
    placements: dict[int, str],
    *,
    title: str = "Founding layout",
) -> go.Figure:
    """Draw the lattice: one square cell per site, coloured by its occupant.

    The rendering contract (#109, ``docs/DESIGN.md`` §6.3): **cells are always
    exactly square.** That is enforced here rather than by sizing arithmetic
    in the caller — plotly's ``scaleanchor`` ties one pixel of the y axis to
    one pixel of the x axis, so the canvas takes whatever aspect the grid has
    and a cell can never come out oblong at any container width.

    This is the ONE grid renderer every consumer uses — panel preview, live
    run view, results browser — and it has two paths behind one signature
    (DECISIONS #145): up to :data:`PIXEL_ARRAY_THRESHOLD` sites, bordered
    hover-labelled cells; above it, the whole world as a single image whose
    pixels are the cells, because rebuilding thousands of bordered cells per
    redraw crawls (the regime where #94's wall-clock throttling matters).
    Both paths draw from the same :func:`strategy_colors` mapping and both
    respect the ≈ 3 px cell floor (:func:`floored_canvas`).

    Args:
        rows: Grid row count.
        cols: Grid column count.
        placements: Site id -> strategy machine name, for occupied sites
            only. Site ids are row-major (``id = row * cols + col``), matching
            :class:`~pdsim.core.structure.LatticeStructure`.
        title: Figure title.

    Returns:
        A plotly figure. Empty sites render in the background colour, so a
        sparsely occupied grid reads as a population inside a world rather
        than as a grid with holes in it. When the cell floor binds, the
        figure carries an explicit width and height that callers must not
        stretch away.
    """
    colors = strategy_colors()
    if pixel_array_active(rows, cols):
        trace: go.Heatmap | go.Image = _pixel_array_trace(rows, cols, placements, colors)
    else:
        trace = _bordered_cells_trace(rows, cols, placements, colors)
    figure = go.Figure(trace)
    figure.update_layout(
        title=title,
        margin={"l": 20, "r": 20, "t": 40, "b": 20},
        plot_bgcolor="rgba(0,0,0,0.06)",
    )
    figure.update_xaxes(showticklabels=False, showgrid=False, zeroline=False)
    # scaleanchor + scaleratio 1 is what makes the cells exactly square; the
    # y axis is reversed so row 0 renders at the top, matching how a layout
    # file is written and read. (An image trace defaults to both already;
    # setting them explicitly keeps the two paths on one contract.)
    figure.update_yaxes(
        showticklabels=False,
        showgrid=False,
        zeroline=False,
        scaleanchor="x",
        scaleratio=1,
        autorange="reversed",
    )
    canvas = floored_canvas(rows, cols)
    if canvas is not None:
        width, height = canvas
        figure.update_layout(width=width, height=height)
    return figure


def _display_name(name: str) -> str:
    """Return a strategy's display name, tolerating unregistered names.

    Args:
        name: Strategy machine name.

    Returns:
        The registry display name, or the machine name itself as fallback.
    """
    for info in all_strategies():
        if info.name == name:
            return info.display_name
    return name


def _period_label(mode: str) -> str:
    """Return the x-axis label for a run mode.

    Args:
        mode: ``"evolution"`` or ``"tournament"``.

    Returns:
        ``"Generation"`` or ``"Cycle"``.
    """
    return "Cycle" if mode == "tournament" else "Generation"


def _x_axis(timeseries: RunTimeseries) -> tuple[list[float | int | None], str]:
    """Return the shared x-axis values and label for a run's charts (M10b).

    An event-time (asynchronous) run stamps every period with its
    generation-equivalent clock reading, and those stamps ARE the honest
    x-axis: under ``per_event`` or ``every_m_events`` recording cadences
    the periods are NOT equally spaced in time, so plotting against the
    period index would distort every trajectory. Synchronous and
    tournament runs carry no clock (all stamps ``None`` — spec Design 5)
    and keep the period index with the classic label.

    Args:
        timeseries: The run's accumulated series.

    Returns:
        ``(x_values, x_label)`` — clock stamps and the
        generation-equivalents label for event-time runs; period indices
        and Generation/Cycle otherwise.
    """
    if any(t is not None for t in timeseries.gen_equiv_times):
        return list(timeseries.gen_equiv_times), "Generation-equivalents (event time)"
    return list(timeseries.periods), _period_label(timeseries.mode)


def _line_chart(
    timeseries: RunTimeseries,
    series: dict[str, list[float | None]],
    title: str,
    y_title: str,
) -> go.Figure:
    """Build a per-strategy line chart over periods.

    Args:
        timeseries: The run's accumulated series (for periods and mode).
        series: The per-strategy values to plot.
        title: Figure title.
        y_title: Y-axis label.

    Returns:
        One line trace per strategy, colored stably.
    """
    colors = strategy_colors()
    x, x_label = _x_axis(timeseries)
    figure = go.Figure()
    for name, values in series.items():
        figure.add_trace(
            go.Scatter(
                x=x,
                y=values,
                mode="lines",
                name=_display_name(name),
                line={"color": colors.get(name, _FALLBACK_COLOR)},
            )
        )
    figure.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_title,
        margin={"t": 40, "b": 40},
    )
    return figure


def composition_chart(timeseries: RunTimeseries) -> go.Figure:
    """Stacked-area population composition over time (evolution's headliner).

    Args:
        timeseries: The run's accumulated series.

    Returns:
        One stacked area trace per strategy; y sums to the population size.
    """
    colors = strategy_colors()
    x, x_label = _x_axis(timeseries)
    figure = go.Figure()
    for name, counts in timeseries.composition.items():
        figure.add_trace(
            go.Scatter(
                x=x,
                y=counts,
                mode="lines",
                stackgroup="population",  # plotly stacks traces sharing a group
                name=_display_name(name),
                line={"width": 0.5, "color": colors.get(name, _FALLBACK_COLOR)},
            )
        )
    figure.update_layout(
        title="Population composition",
        xaxis_title=x_label,
        yaxis_title="Agents",
        margin={"t": 40, "b": 40},
    )
    return figure


def mean_score_chart(
    timeseries: RunTimeseries, *, per_round: bool = False, whole_game: bool = False
) -> go.Figure:
    """Per-strategy mean-score trajectories over time (both modes).

    Two orthogonal views of the same run (DECISIONS #44/#45):

    * ``per_round`` — divide by rounds actually played, landing on the
      payoff-matrix scale (S..T) so different setups compare directly;
      otherwise plot the raw scores selection acts on.
    * ``whole_game`` — running whole-game-so-far averages instead of each
      generation's own figure: the lines move gradually as evidence
      accumulates. Evolution only; in tournament mode the plain series are
      already whole-game cumulative, so the flag is ignored there.

    Args:
        timeseries: The run's accumulated series.
        per_round: If True, plot mean payoff per round.
        whole_game: If True (evolution), plot running whole-game averages.

    Returns:
        One line per strategy.
    """
    whole_game = whole_game and timeseries.mode != "tournament"
    if per_round:
        series = (
            timeseries.running_mean_scores_per_round
            if whole_game
            else timeseries.mean_scores_per_round
        )
        title = "Mean payoff per round" + (" (whole game so far)" if whole_game else "")
        return _line_chart(timeseries, series, title, title)
    if whole_game:
        return _line_chart(
            timeseries,
            timeseries.running_mean_scores,
            "Mean scores (whole game so far)",
            "Mean score per agent-generation, whole game",
        )
    y_title = (
        "Cumulative mean score per agent"
        if timeseries.mode == "tournament"
        else "Mean score (this generation)"
    )
    return _line_chart(timeseries, timeseries.mean_scores, "Mean scores", y_title)


def cooperation_chart(timeseries: RunTimeseries) -> go.Figure:
    """Cooperation rate over time: population overall + per-strategy lines.

    The M9b observability chart (DECISIONS #60/#65): executed-action
    cooperation, which composition alone cannot show — a 100%-TitForTat
    population mid-noise-spiral plays D constantly while its composition
    looks fully cooperative. Per-strategy lines are the actions-weighted
    aggregates over each actor's opponents; the thicker dotted line is the
    whole population. Rates are per-generation in evolution mode and
    run-cumulative in tournament mode (the #65 asymmetry). The y-axis is
    pinned to 0-1 so runs compare at a glance.

    Args:
        timeseries: The run's accumulated series (must carry cooperation
            data — callers skip this chart for pre-schema-2 recordings).

    Returns:
        One line per actor strategy plus the population line.
    """
    colors = strategy_colors()
    x, x_label = _x_axis(timeseries)
    figure = go.Figure()
    for name, values in timeseries.cooperation_by_strategy.items():
        figure.add_trace(
            go.Scatter(
                x=x,
                y=values,
                mode="lines",
                name=_display_name(name),
                line={"color": colors.get(name, _FALLBACK_COLOR)},
            )
        )
    figure.add_trace(
        go.Scatter(
            x=x,
            y=timeseries.cooperation_overall,
            mode="lines",
            name="Population",
            line={"color": "#444444", "width": 3, "dash": "dot"},
        )
    )
    cumulative = " (cumulative)" if timeseries.mode == "tournament" else ""
    figure.update_layout(
        title=f"Cooperation rate{cumulative}",
        xaxis_title=x_label,
        yaxis_title="Cooperation rate",
        yaxis={"range": [0, 1]},
        margin={"t": 40, "b": 40},
    )
    return figure


def cooperation_pair_rows(timeseries: RunTimeseries) -> list[dict[str, object]]:
    """Build the final cooperation pair matrix as plain table rows.

    Plain rows rather than a figure, per the #37 convention — a pair-matrix
    heatmap is deferred to M12, where the diagonal-vs-off-diagonal contrast
    becomes the in-group/out-group diagnostic (DECISIONS #60/#65).

    Args:
        timeseries: The run's accumulated series.

    Returns:
        One row per ordered pair that played in the final period: actor,
        opponent, cooperation rate, actions counted — sorted by machine
        names for a stable, scannable matrix. Empty when the run carries no
        cooperation data (pre-schema-2 recordings).
    """
    if not timeseries.cooperation_overall:
        return []
    rows: list[dict[str, object]] = []
    for actor, opponent in sorted(timeseries.cooperation_pairs):
        count = timeseries.cooperation_pair_actions[(actor, opponent)][-1]
        rate = timeseries.cooperation_pairs[(actor, opponent)][-1]
        if not count or rate is None:
            continue  # the pair did not play in the final period
        rows.append(
            {
                "Actor": _display_name(actor),
                "Opponent": _display_name(opponent),
                "Cooperation rate": round(rate, 3),
                "Actions counted": count,
            }
        )
    return rows


def population_chart(
    timeseries: RunTimeseries, carrying_capacity: float | None = None
) -> go.Figure:
    """Total population per period, against the carrying-capacity line (M10a).

    The stacked composition chart already shows growth in its total height;
    this figure makes N versus K legible — which is the point of the K
    story: watch the growth curve hit the cap and flatten.

    Args:
        timeseries: The run's accumulated series (``population_size`` is
            derived from the raw composition, #47).
        carrying_capacity: K, drawn as a dashed reference line when given
            (callers pass it only for energy-economy runs — it comes from
            the config, never from the recorded data).

    Returns:
        A single population line, plus the dashed K line when provided.
    """
    x, x_label = _x_axis(timeseries)
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=x,
            y=timeseries.population_size,
            mode="lines",
            name="Population",
            line={"color": "#444444", "width": 2},
        )
    )
    if carrying_capacity is not None:
        figure.add_hline(
            y=carrying_capacity,
            line_dash="dash",
            line_color="#888888",
            annotation_text=f"carrying capacity K = {carrying_capacity:g}",
            annotation_position="bottom right",
        )
    figure.update_layout(
        title="Population size",
        xaxis_title=x_label,
        yaxis_title="Agents",
        margin={"t": 40, "b": 40},
    )
    return figure


def mean_energy_chart(timeseries: RunTimeseries) -> go.Figure:
    """Mean carried-forward energy per strategy over time (M10a).

    Args:
        timeseries: The run's accumulated series (the energy means are
            derived from the per-agent snapshots).

    Returns:
        One line per strategy, in the stable house colors.
    """
    return _line_chart(timeseries, timeseries.mean_energy, "Mean energy", "Mean energy per agent")


def mean_age_chart(timeseries: RunTimeseries) -> go.Figure:
    """Mean entering age per strategy over time (M10a).

    Args:
        timeseries: The run's accumulated series (the age means are derived
            from the per-agent snapshots).

    Returns:
        One line per strategy, in the stable house colors.
    """
    return _line_chart(timeseries, timeseries.mean_age, "Mean age", "Mean age (generations)")


def total_score_chart(timeseries: RunTimeseries) -> go.Figure:
    """Cumulative total score per strategy over cycles (tournament only).

    Args:
        timeseries: The run's accumulated series.

    Returns:
        One line per strategy, monotonically non-decreasing.

    Raises:
        ValueError: If called for an evolution run — scores reset each
            generation there, so a cumulative total does not exist (#31).
    """
    if timeseries.mode != "tournament":
        raise ValueError("total_score_chart is tournament-only; evolution scores reset (#31).")
    return _line_chart(
        timeseries, timeseries.total_scores, "Cumulative total scores", "Total score"
    )


def export_run_charts(
    timeseries: RunTimeseries, folder: Path, carrying_capacity: float | None = None
) -> list[Path]:
    """Write a run's charts as standalone HTML files into a run folder.

    The chart-export seam (DECISIONS #48): recording (``pdsim/io``) never
    imports plotting code — the CLI and the UI call this after a recording
    finalizes, so a run folder is complete without charts and charts are a
    bonus artifact on top.

    Args:
        timeseries: The run's accumulated (or reconstructed) series.
        folder: The run folder to write into.
        carrying_capacity: K for the population chart's reference line;
            callers pass it for energy-economy runs (it lives in the
            config, not the recorded series).

    Returns:
        The written file paths (composition or totals, plus mean scores;
        cooperation and the three economy charts when their data exists).
    """
    if timeseries.mode == "tournament":
        figures = {"total_scores": total_score_chart(timeseries)}
    else:
        figures = {"composition": composition_chart(timeseries)}
    figures["mean_scores"] = mean_score_chart(timeseries)
    if timeseries.cooperation_overall:  # absent for pre-schema-2 recordings
        figures["cooperation"] = cooperation_chart(timeseries)
    if any(timeseries.agent_snapshots):  # absent for imitation / pre-schema-3
        figures["population"] = population_chart(timeseries, carrying_capacity)
        figures["mean_energy"] = mean_energy_chart(timeseries)
        figures["mean_age"] = mean_age_chart(timeseries)
    written = []
    for name, figure in figures.items():
        path = folder / f"{name}.html"
        # include_plotlyjs="cdn" keeps each file ~10 kB instead of ~3 MB.
        figure.write_html(path, include_plotlyjs="cdn")
        written.append(path)
    return written


def sweep_metric_chart(
    summary_frame: pd.DataFrame,
    axis_column: str,
    metric_column: str,
    *,
    replicate_column: str = "seed",
    metric_label: str | None = None,
) -> go.Figure:
    """Plot one sweep metric against one axis, with replicate spread (M9.5).

    At each axis value the metric is aggregated across the replicate seeds
    into a mean line plus a shaded min-max band, so the band shows how much
    the outcome varied between repeats (companion §4) — the honest picture,
    since invasion is a probability, not a certainty. Pure (frame in, Figure
    out; no Streamlit), so the future Sweep tab reuses it (DECISIONS #71).

    Args:
        summary_frame: The sweep summary table (one row per member run).
        axis_column: The column to put on the x-axis (an axis value).
        metric_column: The metric column to put on the y-axis.
        replicate_column: The column distinguishing repeats (default
            ``"seed"``); rows are grouped by ``axis_column`` across it.
        metric_label: Y-axis label; defaults to ``metric_column``.

    Returns:
        A figure with a mean line and a min-max band over the axis values.
    """
    frame = summary_frame[[axis_column, metric_column]].dropna()
    grouped = frame.groupby(axis_column)[metric_column]
    x = sorted(grouped.groups)
    means = [grouped.get_group(value).mean() for value in x]
    lows = [grouped.get_group(value).min() for value in x]
    highs = [grouped.get_group(value).max() for value in x]

    figure = go.Figure()
    # Band: an upper trace, then a lower trace filled back up to it. Plotly
    # draws the fill between the two by giving the lower trace fill="tonexty".
    figure.add_trace(
        go.Scatter(
            x=x, y=highs, mode="lines", line={"width": 0}, showlegend=False, hoverinfo="skip"
        )
    )
    figure.add_trace(
        go.Scatter(
            x=x,
            y=lows,
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor="rgba(68,68,68,0.15)",
            name="replicate spread (min-max)",
            hoverinfo="skip",
        )
    )
    figure.add_trace(
        go.Scatter(x=x, y=means, mode="lines+markers", name="mean", line={"color": "#444444"})
    )
    figure.update_layout(
        title=f"{metric_label or metric_column} vs {axis_column}",
        xaxis_title=axis_column,
        yaxis_title=metric_label or metric_column,
        margin={"t": 40, "b": 40},
    )
    return figure


def _slugify_column(name: str) -> str:
    """Turn a summary column name into a filesystem-safe fragment.

    Args:
        name: A column name, possibly containing ``[`` / ``]`` / ``.``.

    Returns:
        The name with non-alphanumeric runs collapsed to single underscores.
    """
    return "".join(ch if ch.isalnum() else "_" for ch in name).strip("_")


def export_sweep_charts(
    summary_frame: pd.DataFrame,
    folder: Path,
    axes: list[str],
    metrics: list[str],
    *,
    metric_labels: dict[str, str] | None = None,
) -> list[Path]:
    """Write one metric-vs-axis chart HTML per (metric x axis) pair.

    The sweep analog of :func:`export_run_charts` (DECISIONS #71): called by
    the runner after a sweep finishes. Plotting stays in ``viz`` and is
    invoked from the orchestration tier — ``pdsim/io`` and ``pdsim/sweep``
    persistence code never import it (hard rule 4).

    Args:
        summary_frame: The sweep summary table.
        folder: The sweep folder to write into.
        axes: Axis column names (the x-candidates).
        metrics: Metric column names (the y-candidates).
        metric_labels: Optional metric column -> display label map.

    Returns:
        The written file paths.
    """
    labels = metric_labels or {}
    written: list[Path] = []
    for metric in metrics:
        for axis in axes:
            figure = sweep_metric_chart(
                summary_frame, axis, metric, metric_label=labels.get(metric)
            )
            path = folder / f"{_slugify_column(metric)}_vs_{_slugify_column(axis)}.html"
            figure.write_html(path, include_plotlyjs="cdn")
            written.append(path)
    return written


def final_summary_rows(final: RunFinished) -> list[dict[str, object]]:
    """Build the mode-appropriate final summary table as plain rows.

    Plain data instead of a figure so any front end can render it as a
    native table (the Streamlit app uses ``st.dataframe``) — and so this
    module stays trivially testable (DECISIONS #37).

    Args:
        final: The run's closing event.

    Returns:
        Evolution: rows of strategy / agent count / mean score, sorted by
        count (the final composition). Tournament: standings rows with
        rank / strategy / mean per agent / total / agents, sorted by mean
        score per agent, like the tournament demo.
    """
    if final.mode == "tournament":
        standings = sorted(final.mean_scores.items(), key=lambda kv: -kv[1])
        totals = final.total_scores or {}
        return [
            {
                "Rank": rank,
                "Strategy": _display_name(name),
                "Mean score per agent": round(mean, 1),
                "Total score": round(totals.get(name, 0.0), 1),
                "Agents": final.composition.get(name, 0),
            }
            for rank, (name, mean) in enumerate(standings, start=1)
        ]
    rows = sorted(final.composition.items(), key=lambda kv: -kv[1])
    return [
        {
            "Strategy": _display_name(name),
            "Agents": count,
            "Mean score": round(final.mean_scores.get(name, 0.0), 1),
        }
        for name, count in rows
    ]
