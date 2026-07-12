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
    figure = go.Figure()
    for name, values in series.items():
        figure.add_trace(
            go.Scatter(
                x=timeseries.periods,
                y=values,
                mode="lines",
                name=_display_name(name),
                line={"color": colors.get(name, _FALLBACK_COLOR)},
            )
        )
    figure.update_layout(
        title=title,
        xaxis_title=_period_label(timeseries.mode),
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
    figure = go.Figure()
    for name, counts in timeseries.composition.items():
        figure.add_trace(
            go.Scatter(
                x=timeseries.periods,
                y=counts,
                mode="lines",
                stackgroup="population",  # plotly stacks traces sharing a group
                name=_display_name(name),
                line={"width": 0.5, "color": colors.get(name, _FALLBACK_COLOR)},
            )
        )
    figure.update_layout(
        title="Population composition",
        xaxis_title=_period_label(timeseries.mode),
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
    figure = go.Figure()
    for name, values in timeseries.cooperation_by_strategy.items():
        figure.add_trace(
            go.Scatter(
                x=timeseries.periods,
                y=values,
                mode="lines",
                name=_display_name(name),
                line={"color": colors.get(name, _FALLBACK_COLOR)},
            )
        )
    figure.add_trace(
        go.Scatter(
            x=timeseries.periods,
            y=timeseries.cooperation_overall,
            mode="lines",
            name="Population",
            line={"color": "#444444", "width": 3, "dash": "dot"},
        )
    )
    cumulative = " (cumulative)" if timeseries.mode == "tournament" else ""
    figure.update_layout(
        title=f"Cooperation rate{cumulative}",
        xaxis_title=_period_label(timeseries.mode),
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


def export_run_charts(timeseries: RunTimeseries, folder: Path) -> list[Path]:
    """Write a run's charts as standalone HTML files into a run folder.

    The chart-export seam (DECISIONS #48): recording (``pdsim/io``) never
    imports plotting code — the CLI and the UI call this after a recording
    finalizes, so a run folder is complete without charts and charts are a
    bonus artifact on top.

    Args:
        timeseries: The run's accumulated (or reconstructed) series.
        folder: The run folder to write into.

    Returns:
        The written file paths (composition or totals, plus mean scores).
    """
    if timeseries.mode == "tournament":
        figures = {"total_scores": total_score_chart(timeseries)}
    else:
        figures = {"composition": composition_chart(timeseries)}
    figures["mean_scores"] = mean_score_chart(timeseries)
    if timeseries.cooperation_overall:  # absent for pre-schema-2 recordings
        figures["cooperation"] = cooperation_chart(timeseries)
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
