"""Tests for the chart builders (``pdsim/viz/charts.py``).

Headless on purpose: the builders take a RunTimeseries and return plotly
figures, no Streamlit anywhere — which is exactly the property these tests
pin (the viz layer must survive a future dashboard migration, DESIGN §6.4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pdsim.core.events import AgentSnapshot, CycleFinished, GenerationFinished, RunFinished
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
            rounds_played={"tit_for_tat": 2, "always_defect": 2},
        )
    )
    timeseries.add(
        GenerationFinished(
            index=1,
            composition={"tit_for_tat": 3, "always_defect": 1},
            mean_scores={"tit_for_tat": 4.0, "always_defect": 6.0},
            rounds_played={"tit_for_tat": 3, "always_defect": 1},
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

    def test_per_round_view_lands_on_the_payoff_scale(self) -> None:
        """DECISIONS #44: totals / rounds — hand-checked values."""
        figure = charts.mean_score_chart(_evolution_series(), per_round=True)
        # Gen 0: TFT total 4.0 over 2 agent-rounds = 2.0/round;
        # gen 1: total 12.0 over 3 agent-rounds = 4.0/round.
        assert list(figure.data[0].y) == [2.0, 4.0]
        assert "per round" in figure.layout.yaxis.title.text.lower()

    def test_whole_game_view_uses_running_averages(self) -> None:
        """DECISIONS #45: cumulative score / cumulative agents so far.

        TFT: gen 0 total 4.0 over 2 agents; gen 1 total 12.0 over 3 agents
        → whole-game means [2.0, 16/5 = 3.2].
        """
        figure = charts.mean_score_chart(_evolution_series(), whole_game=True)
        assert list(figure.data[0].y) == [2.0, 3.2]
        assert "whole game" in figure.layout.title.text.lower()

    def test_whole_game_flag_is_ignored_in_tournament_mode(self) -> None:
        """Tournament series are already cumulative — same chart either way."""
        plain = charts.mean_score_chart(_tournament_series())
        flagged = charts.mean_score_chart(_tournament_series(), whole_game=True)
        assert [list(t.y) for t in flagged.data] == [list(t.y) for t in plain.data]

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


def _economy_series() -> RunTimeseries:
    """Build a small hand-made economy timeseries with snapshots (M10a).

    Returns:
        Two generations of a growing TFT/AllD economy.
    """
    timeseries = RunTimeseries(mode="evolution")
    timeseries.add(
        GenerationFinished(
            index=0,
            composition={"tit_for_tat": 2, "always_defect": 2},
            mean_scores={"tit_for_tat": 2.0, "always_defect": 7.0},
            rounds_played={"tit_for_tat": 4, "always_defect": 4},
            agents=(
                AgentSnapshot(
                    agent_id=0, parent_id=None, age=1, energy=50.0, strategy="tit_for_tat"
                ),
                AgentSnapshot(
                    agent_id=1, parent_id=None, age=1, energy=70.0, strategy="tit_for_tat"
                ),
                AgentSnapshot(
                    agent_id=2, parent_id=None, age=1, energy=30.0, strategy="always_defect"
                ),
                AgentSnapshot(
                    agent_id=3, parent_id=None, age=1, energy=20.0, strategy="always_defect"
                ),
            ),
        )
    )
    timeseries.add(
        GenerationFinished(
            index=1,
            composition={"tit_for_tat": 2, "always_defect": 2},
            mean_scores={"tit_for_tat": 3.0, "always_defect": 5.0},
            rounds_played={"tit_for_tat": 4, "always_defect": 4},
            agents=(
                AgentSnapshot(
                    agent_id=0, parent_id=None, age=2, energy=90.0, strategy="tit_for_tat"
                ),
                AgentSnapshot(
                    agent_id=1, parent_id=None, age=2, energy=110.0, strategy="tit_for_tat"
                ),
                AgentSnapshot(agent_id=4, parent_id=0, age=0, energy=40.0, strategy="tit_for_tat"),
                AgentSnapshot(
                    agent_id=2, parent_id=None, age=2, energy=10.0, strategy="always_defect"
                ),
            ),
        )
    )
    return timeseries


class TestEconomyCharts:
    """M10a: the population / mean-energy / mean-age figures."""

    def test_population_chart_plots_the_derived_total(self) -> None:
        """One line, y = sum of the composition per period."""
        figure = charts.population_chart(_economy_series())
        assert len(figure.data) == 1
        assert list(figure.data[0].y) == [4, 4]

    def test_population_chart_draws_the_capacity_line_when_given(self) -> None:
        """K arrives as a dashed horizontal reference line."""
        with_k = charts.population_chart(_economy_series(), carrying_capacity=200.0)
        without_k = charts.population_chart(_economy_series())
        assert len(with_k.layout.shapes) == 1
        assert with_k.layout.shapes[0].y0 == 200.0
        assert len(without_k.layout.shapes) == 0

    def test_mean_energy_and_age_charts_have_one_line_per_strategy(self) -> None:
        """The derived snapshot series feed the house line chart."""
        series = _economy_series()
        energy = charts.mean_energy_chart(series)
        age = charts.mean_age_chart(series)
        assert len(energy.data) == 2
        assert len(age.data) == 2
        by_name = {trace.name: list(trace.y) for trace in energy.data}
        assert by_name["Tit for Tat"] == [60.0, 80.0]  # (50+70)/2, (90+110+40)/3

    def test_export_includes_economy_charts_only_with_snapshots(self, tmp_path: Path) -> None:
        """A schema-1/2 series exports no economy figures and does not error."""
        economy_files = {
            path.name
            for path in charts.export_run_charts(
                _economy_series(), tmp_path, carrying_capacity=200.0
            )
        }
        assert {"population.html", "mean_energy.html", "mean_age.html"} <= economy_files
        plain_files = {
            path.name for path in charts.export_run_charts(_evolution_series(), tmp_path)
        }
        assert not {"population.html", "mean_energy.html", "mean_age.html"} & plain_files
