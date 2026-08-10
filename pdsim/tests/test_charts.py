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


class TestGridRenderer:
    """The two-path grid renderer: threshold switch, one palette, the floor.

    M11a Phase E2 (DECISIONS #145/#149): `grid_chart` is the single
    renderer every consumer uses — bordered hover-labelled cells while they
    have the room, one pixel-array image once the site count passes
    ``PIXEL_ARRAY_THRESHOLD`` OR the cells shrink below
    ``BORDER_MIN_SIDE_PX``.
    """

    def test_pixel_array_activates_above_the_threshold_and_not_below(self) -> None:
        """49x49 (2,401 sites) stays a heatmap; 51x51 (2,601) becomes an image."""
        below = charts.grid_chart(49, 49, {0: "always_defect"})
        above = charts.grid_chart(51, 51, {0: "always_defect"})
        assert below.data[0].type == "heatmap"
        assert above.data[0].type == "image"
        assert not charts.pixel_array_active(49, 49)
        assert charts.pixel_array_active(51, 51)

    def test_small_cells_trigger_the_pixel_array_below_the_count_threshold(self) -> None:
        """200x10 is only 2,000 sites, but its ~3 px cells demand the pixel path.

        The #149 finding: on the bordered path a floor-sized cell loses a
        third of itself to the gap stroke and the grid degrades into
        disconnected dots — elongated grids reach small cells long before
        they reach 2,500 sites.
        """
        figure = charts.grid_chart(200, 10, {0: "always_defect"})
        assert figure.data[0].type == "image"
        assert charts.pixel_array_active(200, 10)

    def test_a_small_ribbon_keeps_its_bordered_hover_labelled_cells(self) -> None:
        """60x5: elongated but roomy (7.5 px cells) — borders and hover stay."""
        figure = charts.grid_chart(60, 5, {0: "always_defect"})
        assert figure.data[0].type == "heatmap"
        assert not charts.pixel_array_active(60, 5)

    def test_a_floored_canvas_keeps_room_for_the_figure_chrome(self) -> None:
        """The #149 defect: 10 columns need 70 px, but title + modebar do not fit.

        The canvas width never drops below the chrome minimum; the height
        still comes from the floored cells exactly.
        """
        canvas = charts.floored_canvas(200, 10)
        assert canvas == (320, 200 * charts.CELL_FLOOR_PX + 60)

    def test_both_paths_draw_from_the_one_colour_mapping(self) -> None:
        """Same colour source by construction: both paths read strategy_colors().

        The heatmap's discrete colorscale must carry the registry colour
        verbatim, and the image's pixel must be that same colour parsed to
        RGB — no second palette anywhere.
        """
        color = charts.strategy_colors()["always_defect"]
        shape_path = charts.grid_chart(2, 2, {0: "always_defect"})
        scale_colors = {stop_color for _, stop_color in shape_path.data[0].colorscale}
        assert color in scale_colors
        pixel_path = charts.grid_chart(51, 51, {0: "always_defect"})
        expected = charts._parse_css_color(color)
        assert tuple(pixel_path.data[0].z[0][0][:3]) == expected
        assert pixel_path.data[0].z[0][0][3] == 255

    def test_empty_sites_are_transparent_on_the_pixel_path(self) -> None:
        """Unoccupied cells show the shared plot background, as on the shape path."""
        figure = charts.grid_chart(51, 51, {0: "always_defect"})
        assert figure.data[0].z[0][1][3] == 0  # alpha 0: visibly empty

    def test_the_cell_floor_binds_only_on_oversized_grids(self) -> None:
        """20x20 fits the nominal canvas; 200x10 falls below ~3 px and floors."""
        assert charts.floored_canvas(20, 20) is None
        canvas = charts.floored_canvas(200, 10)
        assert canvas is not None
        width, height = canvas
        assert width >= 10 * charts.CELL_FLOOR_PX
        assert height >= 200 * charts.CELL_FLOOR_PX

    def test_a_floored_figure_carries_its_explicit_canvas(self) -> None:
        """When the floor binds the figure sizes itself; otherwise it stretches."""
        floored = charts.grid_chart(200, 10, {})
        expected = charts.floored_canvas(200, 10)
        assert expected is not None
        assert (floored.layout.width, floored.layout.height) == expected
        assert charts.grid_chart(20, 20, {}).layout.width is None

    def test_the_floor_applies_on_the_pixel_path_too(self) -> None:
        """300x300: pixel array AND floored — the two mechanisms compose."""
        figure = charts.grid_chart(300, 300, {})
        assert figure.data[0].type == "image"
        assert figure.layout.width is not None
        assert figure.layout.width >= 300 * charts.CELL_FLOOR_PX

    def test_cells_stay_exactly_square_on_both_paths(self) -> None:
        """The #109 contract: y is scale-anchored to x on shape and pixel paths."""
        for figure in (
            charts.grid_chart(4, 4, {0: "always_defect"}),
            charts.grid_chart(51, 51, {0: "always_defect"}),
        ):
            assert figure.layout.yaxis.scaleanchor == "x"
            assert figure.layout.yaxis.scaleratio == 1


class TestEventTimeAxis:
    """M10b: async runs plot against the generation-equivalent clock."""

    @staticmethod
    def _async_series() -> RunTimeseries:
        """Two unevenly spaced event-time periods (an every_m cadence)."""
        timeseries = RunTimeseries(mode="evolution")
        for index, stamp in enumerate([0.75, 2.0]):
            timeseries.add(
                GenerationFinished(
                    index=index,
                    composition={"tit_for_tat": 3, "always_defect": 1},
                    mean_scores={"tit_for_tat": 4.0, "always_defect": 6.0},
                    rounds_played={"tit_for_tat": 3, "always_defect": 1},
                    gen_equiv_time=stamp,
                )
            )
        return timeseries

    def test_async_charts_use_the_clock_stamps(self) -> None:
        """The clock readings become x, honestly uneven; label names the unit."""
        figure = charts.composition_chart(self._async_series())
        assert list(figure.data[0].x) == [0.75, 2.0]
        assert "equivalents" in figure.layout.xaxis.title.text

    def test_line_charts_share_the_event_time_axis(self) -> None:
        """The mean-score chart rides the same x-axis helper."""
        figure = charts.mean_score_chart(self._async_series())
        assert list(figure.data[0].x) == [0.75, 2.0]
        assert "event time" in figure.layout.xaxis.title.text

    def test_sync_charts_keep_the_period_axis(self) -> None:
        """No clock stamps -> the classic Generation axis, unchanged."""
        figure = charts.composition_chart(_evolution_series())
        assert list(figure.data[0].x) == [0, 1]
        assert figure.layout.xaxis.title.text == "Generation"
