"""Tests for pairwise cooperation-rate recording (M9b, DECISIONS #60/#65).

Covers: the no-RNG-change regression (seeded trajectories captured on
pre-M9b code replay exactly, in both modes), hand-computed pair rates, the
two-actor-records-per-round identity, the evolution-resets/tournament-
accumulates asymmetry, RunTimeseries aggregation (actions-weighted), schema-2
persistence round-trips, the schema-1 compatibility path, and the cooperation
chart builders.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest

from pdsim.config.experiment import ExperimentConfig
from pdsim.core import engine
from pdsim.core.dynamics import PopulationDynamics, TournamentDynamics
from pdsim.core.events import CycleFinished, GenerationFinished, RunFinished
from pdsim.core.timeseries import RunTimeseries
from pdsim.io.results import RunRecorder, load_run
from pdsim.viz import charts


def _evolution_config(**overrides: object) -> ExperimentConfig:
    """Build the evolution config the regression trajectory was captured on.

    Args:
        **overrides: Top-level ExperimentConfig fields to replace.

    Returns:
        A validated config (noise on, so noise draws are covered too).
    """
    fields: dict = {
        "seed": 99,
        "population": {
            "size": 10,
            "composition": {"tit_for_tat": 4, "always_defect": 3, "pavlov": 3},
        },
        "match": {"length_mode": "fixed", "rounds_per_match": 5, "noise_epsilon": 0.05},
        "dynamics": {"generations": 6, "selection_beta": 0.1, "mutation_rate": 0.1},
    }
    fields.update(overrides)
    return ExperimentConfig.model_validate(fields)


def _tournament_config() -> ExperimentConfig:
    """Build the tournament config the regression trajectory was captured on.

    Returns:
        A validated config (continuation mode, so length draws are covered).
    """
    return ExperimentConfig.model_validate(
        {
            "mode": "tournament",
            "tournament_cycles": 4,
            "seed": 99,
            "population": {
                "size": 6,
                "composition": {"tit_for_tat": 2, "always_defect": 2, "random": 2},
            },
            "match": {"length_mode": "continuation", "continuation_probability": 0.7},
        }
    )


def _trajectory(config: ExperimentConfig) -> list[tuple[dict, dict, dict]]:
    """Run a config and collect (composition, mean_scores, rounds_played).

    Args:
        config: The experiment to run.

    Returns:
        One name-sorted triple per period.
    """
    rows = []
    for event in engine.run(config):
        if isinstance(event, GenerationFinished | CycleFinished):
            rows.append(
                (
                    dict(sorted(event.composition.items())),
                    dict(sorted(event.mean_scores.items())),
                    dict(sorted(event.rounds_played.items())),
                )
            )
    return rows


class TestNoRngChange:
    """The M9b hard constraint: bookkeeping only, no RNG draw touched."""

    # Captured by running these exact configs on the pre-M9b engine (M9a
    # code, commit 4ef17cd) — not computed by the code under test. A
    # failure means a seeded-history contract was broken (hard rule 8).
    EXPECTED_EVOLUTION: ClassVar[list] = [
        (
            {"always_defect": 3, "pavlov": 3, "tit_for_tat": 4},
            {
                "always_defect": 97.66666666666667,
                "pavlov": 94.66666666666667,
                "tit_for_tat": 100.0,
            },
            {"always_defect": 135, "pavlov": 135, "tit_for_tat": 180},
        ),
        (
            {
                "always_cooperate": 1,
                "always_defect": 1,
                "pavlov": 4,
                "random": 1,
                "tit_for_tat": 3,
            },
            {
                "always_cooperate": 90.0,
                "always_defect": 131.0,
                "pavlov": 119.5,
                "random": 112.0,
                "tit_for_tat": 115.0,
            },
            {
                "always_cooperate": 45,
                "always_defect": 45,
                "pavlov": 180,
                "random": 45,
                "tit_for_tat": 135,
            },
        ),
        (
            {"always_defect": 5, "pavlov": 1, "random": 2, "tit_for_tat": 2},
            {"always_defect": 85.2, "pavlov": 64.0, "random": 77.0, "tit_for_tat": 72.0},
            {"always_defect": 225, "pavlov": 45, "random": 90, "tit_for_tat": 90},
        ),
        (
            {
                "always_cooperate": 1,
                "always_defect": 5,
                "pavlov": 1,
                "random": 2,
                "tit_for_tat": 1,
            },
            {
                "always_cooperate": 46.0,
                "always_defect": 102.6,
                "pavlov": 67.0,
                "random": 77.5,
                "tit_for_tat": 69.0,
            },
            {
                "always_cooperate": 45,
                "always_defect": 225,
                "pavlov": 45,
                "random": 90,
                "tit_for_tat": 45,
            },
        ),
        (
            {"always_cooperate": 1, "always_defect": 6, "pavlov": 1, "random": 2},
            {
                "always_cooperate": 37.0,
                "always_defect": 97.66666666666667,
                "pavlov": 47.0,
                "random": 64.0,
            },
            {"always_cooperate": 45, "always_defect": 270, "pavlov": 45, "random": 90},
        ),
        (
            {"always_defect": 6, "pavlov": 1, "random": 3},
            {"always_defect": 91.5, "pavlov": 47.0, "random": 55.666666666666664},
            {"always_defect": 270, "pavlov": 45, "random": 135},
        ),
    ]
    EXPECTED_TOURNAMENT: ClassVar[list] = [
        (
            {"always_defect": 2, "random": 2, "tit_for_tat": 2},
            {"always_defect": 35.5, "random": 28.0, "tit_for_tat": 36.0},
            {"always_defect": 31, "random": 31, "tit_for_tat": 44},
        ),
        (
            {"always_defect": 2, "random": 2, "tit_for_tat": 2},
            {"always_defect": 53.5, "random": 56.5, "tit_for_tat": 69.0},
            {"always_defect": 55, "random": 61, "tit_for_tat": 80},
        ),
        (
            {"always_defect": 2, "random": 2, "tit_for_tat": 2},
            {"always_defect": 81.0, "random": 74.0, "tit_for_tat": 91.0},
            {"always_defect": 90, "random": 86, "tit_for_tat": 108},
        ),
        (
            {"always_defect": 2, "random": 2, "tit_for_tat": 2},
            {"always_defect": 94.5, "random": 97.0, "tit_for_tat": 116.5},
            {"always_defect": 113, "random": 108, "tit_for_tat": 139},
        ),
    ]

    def test_evolution_trajectory_is_byte_identical(self) -> None:
        """Seeded evolution (noise draws included) replays the capture."""
        assert _trajectory(_evolution_config()) == self.EXPECTED_EVOLUTION

    def test_tournament_trajectory_is_byte_identical(self) -> None:
        """Seeded tournament (continuation draws included) replays the capture."""
        assert _trajectory(_tournament_config()) == self.EXPECTED_TOURNAMENT


class TestBookkeeping:
    """Hand-computed pair rates (DECISIONS #65 semantics)."""

    def test_tft_vs_alld_hand_computed(self) -> None:
        """1 TFT vs 1 AllD, 3 noise-free rounds: rates 1/3 and 0.

        TFT plays C, D, D (mirroring); AllD plays D, D, D.
        """
        config = ExperimentConfig.model_validate(
            {
                "population": {"size": 2, "composition": {"tit_for_tat": 1, "always_defect": 1}},
                "match": {"length_mode": "fixed", "rounds_per_match": 3},
                "dynamics": {"generations": 1},
            }
        )
        report = PopulationDynamics(config, np.random.default_rng(0)).step()
        assert report.cooperation == {
            ("tit_for_tat", "always_defect"): (1 / 3, 3),
            ("always_defect", "tit_for_tat"): (0.0, 3),
        }

    def test_each_round_contributes_two_actor_records(self) -> None:
        """Total actions across all pairs = 2 x total rounds played."""
        config = ExperimentConfig.model_validate(
            {
                "population": {
                    "size": 6,
                    "composition": {"tit_for_tat": 2, "always_defect": 2, "pavlov": 2},
                },
                "match": {"length_mode": "fixed", "rounds_per_match": 4},
                "dynamics": {"generations": 1},
            }
        )
        report = PopulationDynamics(config, np.random.default_rng(1)).step()
        total_actions = sum(count for _rate, count in report.cooperation.values())
        total_agent_rounds = sum(report.rounds_played.values())
        assert total_actions == total_agent_rounds  # each agent-round is one action
        assert total_actions == 2 * 15 * 4  # C(6,2) matches x 4 rounds x 2 actors

    def test_self_pairs_are_recorded(self) -> None:
        """Same-strategy matches land on the diagonal (actor == opponent)."""
        config = ExperimentConfig.model_validate(
            {
                "population": {"size": 2, "composition": {"tit_for_tat": 2}},
                "match": {"length_mode": "fixed", "rounds_per_match": 5},
                "dynamics": {"generations": 1},
            }
        )
        report = PopulationDynamics(config, np.random.default_rng(2)).step()
        assert report.cooperation == {("tit_for_tat", "tit_for_tat"): (1.0, 10)}

    def test_evolution_counts_reset_each_generation(self) -> None:
        """The #65 asymmetry, evolution side: per-generation counts."""
        config = ExperimentConfig.model_validate(
            {
                "population": {"size": 2, "composition": {"tit_for_tat": 2}},
                "match": {"length_mode": "fixed", "rounds_per_match": 5},
                "dynamics": {"generations": 3, "mutation_rate": 0.0},
            }
        )
        dynamics = PopulationDynamics(config, np.random.default_rng(3))
        for _ in range(3):
            report = dynamics.step()
            # If counts accumulated, actions would grow 10 -> 20 -> 30.
            assert report.cooperation == {("tit_for_tat", "tit_for_tat"): (1.0, 10)}

    def test_tournament_counts_accumulate_across_cycles(self) -> None:
        """The #65 asymmetry, tournament side: cumulative counts.

        TFT vs AllD over 5-round cycles: TFT cooperates exactly once (round
        1 of cycle 1 — afterwards it mirrors D forever, and the grudge
        survives cycle boundaries per #34).
        """
        config = ExperimentConfig.model_validate(
            {
                "mode": "tournament",
                "tournament_cycles": 2,
                "population": {"size": 2, "composition": {"tit_for_tat": 1, "always_defect": 1}},
                "match": {"length_mode": "fixed", "rounds_per_match": 5},
            }
        )
        dynamics = TournamentDynamics(config, np.random.default_rng(4))
        first = dynamics.step()
        second = dynamics.step()
        assert first.cooperation[("tit_for_tat", "always_defect")] == (0.2, 5)
        assert second.cooperation[("tit_for_tat", "always_defect")] == (0.1, 10)
        assert second.cooperation[("always_defect", "tit_for_tat")] == (0.0, 10)


class TestTimeseriesAggregation:
    """RunTimeseries folds pairs into exact actions-weighted aggregates."""

    def _event(self, index: int, cooperation: dict) -> GenerationFinished:
        """Build a minimal generation event carrying a cooperation table.

        Args:
            index: Generation index.
            cooperation: The pair table.

        Returns:
            The event (other payloads are irrelevant to these tests).
        """
        return GenerationFinished(
            index=index,
            composition={"tit_for_tat": 2},
            mean_scores={"tit_for_tat": 1.0},
            rounds_played={"tit_for_tat": 2},
            cooperation=cooperation,
        )

    def test_aggregates_are_actions_weighted(self) -> None:
        """Per-actor and overall rates weight each pair by its action count."""
        series = RunTimeseries(mode="evolution")
        series.add(
            self._event(
                0,
                {
                    ("a", "b"): (1.0, 10),  # 10 cooperations
                    ("a", "c"): (0.0, 30),  # 0 cooperations
                    ("b", "a"): (0.5, 20),  # 10 cooperations
                },
            )
        )
        assert series.cooperation_by_strategy["a"][-1] == pytest.approx(10 / 40)
        assert series.cooperation_by_strategy["b"][-1] == pytest.approx(0.5)
        assert series.cooperation_overall[-1] == pytest.approx(20 / 60)

    def test_new_pairs_backfill_and_absent_pairs_gap(self) -> None:
        """Pair series stay aligned with periods like every other series."""
        series = RunTimeseries(mode="evolution")
        series.add(self._event(0, {("a", "a"): (1.0, 4)}))
        series.add(self._event(1, {("a", "a"): (0.5, 4), ("a", "b"): (0.25, 8)}))
        assert series.cooperation_pairs[("a", "a")] == [1.0, 0.5]
        assert series.cooperation_pairs[("a", "b")] == [None, 0.25]  # backfilled
        assert series.cooperation_pair_actions[("a", "b")] == [0, 8]

    def test_events_without_cooperation_leave_series_empty(self) -> None:
        """Pre-M9b events (schema-1 loads) produce NO cooperation series."""
        series = RunTimeseries(mode="evolution")
        series.add(
            GenerationFinished(
                index=0,
                composition={"tit_for_tat": 2},
                mean_scores={"tit_for_tat": 1.0},
                rounds_played={"tit_for_tat": 2},
            )
        )
        assert series.cooperation_overall == []
        assert series.cooperation_pairs == {}


def _record(config: ExperimentConfig, out_dir: Path) -> tuple[Path, RunTimeseries]:
    """Run the engine through a recorder and finalize.

    Args:
        config: The experiment to run and record.
        out_dir: Runs directory (a tmp path).

    Returns:
        The finished run folder and the live accumulator.
    """
    recorder = RunRecorder(config, out_dir=out_dir)
    for event in engine.run(config):
        recorder.add(event)
    return recorder.finalize(), recorder.timeseries


class TestPersistence:
    """Schema 2 round-trips; schema 1 stays loadable (DECISIONS #65)."""

    @pytest.mark.parametrize("mode", ["evolution", "tournament"])
    def test_schema_2_round_trips_cooperation_exactly(self, mode: str, tmp_path: Path) -> None:
        """Loaded cooperation series equal the live accumulation."""
        config = (
            _evolution_config(dynamics={"generations": 4, "mutation_rate": 0.1})
            if mode == "evolution"
            else _tournament_config()
        )
        folder, live = _record(config, tmp_path)
        assert (folder / "cooperation.parquet").is_file()
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        assert summary["schema_version"] == 2
        assert summary["final_cooperation_rate"] == pytest.approx(live.cooperation_overall[-1])
        loaded = load_run(folder).timeseries
        assert loaded.cooperation_pairs == live.cooperation_pairs
        assert loaded.cooperation_pair_actions == live.cooperation_pair_actions
        assert loaded.cooperation_by_strategy == live.cooperation_by_strategy
        assert loaded.cooperation_overall == live.cooperation_overall

    def test_synthesized_schema_1_folder_loads_without_cooperation(self, tmp_path: Path) -> None:
        """The compatibility path: a pre-M9b folder renders, minus the chart.

        Synthesized by recording a schema-2 run, then deleting
        cooperation.parquet and rewriting summary.json as schema 1 — exactly
        what an M7/M8-era folder looks like.
        """
        config = _evolution_config(dynamics={"generations": 3})
        folder, live = _record(config, tmp_path)
        (folder / "cooperation.parquet").unlink()
        summary_path = folder / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["schema_version"] = 1
        del summary["final_cooperation_rate"]
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        loaded = load_run(folder)
        assert loaded.summary["schema_version"] == 1
        assert loaded.timeseries.cooperation_overall == []
        assert loaded.timeseries.cooperation_pairs == {}
        # Everything that existed before M9b still round-trips:
        assert loaded.timeseries.periods == live.periods
        assert loaded.timeseries.mean_scores == live.mean_scores
        # And the chart layer skips the cooperation figure without error:
        assert charts.cooperation_pair_rows(loaded.timeseries) == []
        written = charts.export_run_charts(loaded.timeseries, folder)
        assert not any("cooperation" in path.name for path in written)


class TestCharts:
    """The cooperation chart builders (pure, headless)."""

    def _timeseries(self) -> RunTimeseries:
        """Run a small noise-free mixed population and accumulate it.

        One generation, so the final period still holds the original mix —
        selection cannot have removed any pair from the matrix.

        Returns:
            A finished evolution RunTimeseries with cooperation data.
        """
        config = ExperimentConfig.model_validate(
            {
                "population": {"size": 4, "composition": {"tit_for_tat": 2, "always_defect": 2}},
                "match": {"length_mode": "fixed", "rounds_per_match": 4},
                "dynamics": {"generations": 1, "mutation_rate": 0.0},
            }
        )
        series = RunTimeseries(mode="evolution")
        for event in engine.run(config):
            series.add(event)
        return series

    def test_cooperation_chart_has_population_plus_strategy_lines(self) -> None:
        """One line per actor strategy plus the overall population line."""
        series = self._timeseries()
        figure = charts.cooperation_chart(series)
        names = [trace.name for trace in figure.data]
        assert names[-1] == "Population"
        assert len(names) == len(series.cooperation_by_strategy) + 1
        assert figure.layout.yaxis.range == (0, 1)

    def test_pair_rows_report_the_final_period(self) -> None:
        """Rows carry display names, rounded rates, and action counts."""
        series = self._timeseries()
        rows = charts.cooperation_pair_rows(series)
        assert rows  # the pair matrix exists
        by_pair = {(row["Actor"], row["Opponent"]): row for row in rows}
        alld_vs_tft = by_pair[("Always Defect", "Tit for Tat")]
        assert alld_vs_tft["Cooperation rate"] == 0.0
        tft_vs_tft = by_pair[("Tit for Tat", "Tit for Tat")]
        assert tft_vs_tft["Cooperation rate"] == 1.0
        assert all(row["Actions counted"] > 0 for row in rows)

    def test_export_includes_cooperation_for_schema_2_runs(self, tmp_path: Path) -> None:
        """export_run_charts writes cooperation.html when data exists."""
        series = self._timeseries()
        written = charts.export_run_charts(series, tmp_path)
        assert any(path.name == "cooperation.html" for path in written)


class TestFinalCooperationInRunFinished:
    """The engine's stream stays coherent: overall rate is derivable."""

    def test_overall_series_has_one_value_per_period(self) -> None:
        """The derived overall series aligns with periods in both modes."""
        for config in (_evolution_config(), _tournament_config()):
            series = RunTimeseries(mode=config.mode)
            for event in engine.run(config):
                series.add(event)
            assert len(series.cooperation_overall) == len(series.periods)
            assert all(rate is not None for rate in series.cooperation_overall)
            assert isinstance(series.final, RunFinished)
