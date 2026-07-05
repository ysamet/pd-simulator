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
        Machine name → CSS color string.
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


def mean_score_chart(timeseries: RunTimeseries, *, per_round: bool = False) -> go.Figure:
    """Per-strategy mean-score trajectories over time (both modes).

    Two views of the same run (DECISIONS #44): the raw totals are exactly
    what selection sees; the per-round view divides by rounds actually
    played, landing on the payoff-matrix scale (S..T) so runs with
    different population sizes and match lengths compare directly.

    Args:
        timeseries: The run's accumulated series.
        per_round: If True, plot mean payoff per round instead of the raw
            mean score.

    Returns:
        One line per strategy; in evolution mode that generation's figure,
        in tournament mode the cumulative one.
    """
    if per_round:
        return _line_chart(
            timeseries,
            timeseries.mean_scores_per_round,
            "Mean payoff per round",
            "Mean payoff per round",
        )
    y_title = (
        "Cumulative mean score per agent"
        if timeseries.mode == "tournament"
        else "Mean score (this generation)"
    )
    return _line_chart(timeseries, timeseries.mean_scores, "Mean scores", y_title)


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
