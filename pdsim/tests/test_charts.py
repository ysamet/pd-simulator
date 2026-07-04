"""Tests for the chart builders (``pdsim/viz/charts.py``).

Headless on purpose: the builders take a RunTimeseries and return plotly
figures, no Streamlit anywhere — which is exactly the property these tests
pin (the viz layer must survive a future dashboard migration, DESIGN §6.4).
"""

from __future__ import annotations

import pytest

from pdsim.core.events import CycleFinished, GenerationFinished, RunFinished
from pdsim.core.strategies import all_strategy_names
from pdsim.core.timeseries import RunTimeseries
from pdsim.viz import charts


def _evolution_series() -> RunTimeseries:
    """Build a small hand-made evolution timeseries.

    Returns:
        Two generations of a TFT/AllD population.
    """
    timeseries = RunTimeseries(mode="evolution")
    timeseries.add(
        GenerationFinished(
            index=0,
            composition={"tit_for_tat": 2, "always_defect": 2},
            mean_scores={"tit_for_tat": 2.0, "always_defect": 7.0},
        )
    )
    timeseries.add(
        GenerationFinished(
            index=1,
            composition={"tit_for_tat": 3, "always_defect": 1},
            mean_scores={"tit_for_tat": 4.0, "always_defect": 6.0},
        )
    )
    return timeseries


def _tournament_series() -> RunTimeseries:
    """Build a small hand-made tournament timeseries.

    Returns:
        Two cycles of cumulative TFT/AllD standings.
    """
    timeseries = RunTimeseries(mode="tournament")
    for index, (tft, alld) in enumerate([(4.0, 9.0), (9.0, 14.0)]):
        timeseries.add(
            CycleFinished(
                index=index,
                composition={"tit_for_tat": 1, "always_defect": 1},
                total_scores={"tit_for_tat": tft, "always_defect": alld},
                mean_scores={"tit_for_tat": tft, "always_defect": alld},
            )
        )
    return timeseries


class TestColors:
    """The stable per-strategy color contract (DECISIONS #37)."""

    def test_every_registered_strategy_has_a_stable_distinct_color(self) -> None:
        """Same mapping on every call; all seven distinct."""
        first = charts.strategy_colors()
        second = charts.strategy_colors()
        assert first == second
        assert set(first) == set(all_strategy_names())
        assert len(set(first.values())) == len(first)

    def test_charts_share_the_color_mapping(self) -> None:
        """A strategy keeps its color across different chart types."""
        colors = charts.strategy_colors()
        composition = charts.composition_chart(_evolution_series())
        means = charts.mean_score_chart(_evolution_series())
        for figure in (composition, means):
            for trace in figure.data:
                if trace.name == "Tit for Tat":
                    assert trace.line.color == colors["tit_for_tat"]


class TestEvolutionCharts:
    """Stacked composition + mean-score trajectories."""

    def test_composition_chart_traces(self) -> None:
        """One stacked trace per strategy with the right data and names."""
        figure = charts.composition_chart(_evolution_series())
        assert [trace.name for trace in figure.data] == ["Tit for Tat", "Always Defect"]
        assert list(figure.data[0].y) == [2, 3]
        assert list(figure.data[1].y) == [2, 1]
        assert all(trace.stackgroup == "population" for trace in figure.data)
        assert figure.layout.xaxis.title.text == "Generation"

    def test_mean_score_chart_traces(self) -> None:
        """One line per strategy; per-generation axis label."""
        figure = charts.mean_score_chart(_evolution_series())
        assert list(figure.data[0].y) == [2.0, 4.0]
        assert "generation" in figure.layout.yaxis.title.text.lower()

    def test_total_score_chart_is_tournament_only(self) -> None:
        """Evolution has no run-long totals (#31) — asking is an error."""
        with pytest.raises(ValueError, match="tournament-only"):
            charts.total_score_chart(_evolution_series())


class TestTournamentCharts:
    """Cumulative totals + cumulative per-agent means over cycles."""

    def test_total_score_chart_traces(self) -> None:
        """Cumulative totals per strategy over the cycle axis."""
        figure = charts.total_score_chart(_tournament_series())
        assert list(figure.data[0].y) == [4.0, 9.0]
        assert figure.layout.xaxis.title.text == "Cycle"

    def test_mean_score_chart_uses_cumulative_label(self) -> None:
        """Tournament means are cumulative per agent — the label says so."""
        figure = charts.mean_score_chart(_tournament_series())
        assert "cumulative" in figure.layout.yaxis.title.text.lower()


class TestFinalSummary:
    """The mode-appropriate final table, as plain rows."""

    def test_tournament_standings_sorted_by_mean(self) -> None:
        """Ranked rows, best mean per agent first, display names shown."""
        final = RunFinished(
            mode="tournament",
            completed=10,
            composition={"tit_for_tat": 3, "always_defect": 3},
            mean_scores={"tit_for_tat": 100.0, "always_defect": 140.0},
            total_scores={"tit_for_tat": 300.0, "always_defect": 420.0},
        )
        rows = charts.final_summary_rows(final)
        assert [row["Rank"] for row in rows] == [1, 2]
        assert rows[0]["Strategy"] == "Always Defect"
        assert rows[0]["Total score"] == 420.0

    def test_evolution_composition_sorted_by_count(self) -> None:
        """Final composition rows, most numerous strategy first."""
        final = RunFinished(
            mode="evolution",
            completed=30,
            composition={"tit_for_tat": 17, "grim_trigger": 5},
            mean_scores={"tit_for_tat": 90.0, "grim_trigger": 88.0},
            total_scores=None,
        )
        rows = charts.final_summary_rows(final)
        assert rows[0] == {"Strategy": "Tit for Tat", "Agents": 17, "Mean score": 90.0}
        assert rows[1]["Strategy"] == "Grim Trigger"
