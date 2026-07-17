"""Tests for RunTimeseries (``pdsim/core/timeseries.py``, DECISIONS #37).

Covers: folding period events into aligned per-strategy series, backfill
when a strategy first appears mid-run, fill values when one disappears,
indifference to fine-grained events, and capturing the final summary.
"""

from __future__ import annotations

from pdsim.core.events import (
    AgentSnapshot,
    CycleFinished,
    GenerationFinished,
    MatchFinished,
    RunFinished,
)
from pdsim.core.timeseries import RunTimeseries


class TestEvolutionFolding:
    """GenerationFinished events become composition/mean-score columns."""

    def test_series_stay_aligned_through_appear_and_vanish(self) -> None:
        """Newcomers are backfilled; the vanished get fill values."""
        timeseries = RunTimeseries(mode="evolution")
        timeseries.add(GenerationFinished(index=0, composition={"a": 3}, mean_scores={"a": 1.0}))
        timeseries.add(
            GenerationFinished(
                index=1, composition={"a": 2, "b": 1}, mean_scores={"a": 2.0, "b": 5.0}
            )
        )
        timeseries.add(GenerationFinished(index=2, composition={"b": 3}, mean_scores={"b": 6.0}))
        assert timeseries.periods == [0, 1, 2]
        assert timeseries.composition == {"a": [3, 2, 0], "b": [0, 1, 3]}
        assert timeseries.mean_scores == {"a": [1.0, 2.0, None], "b": [None, 5.0, 6.0]}
        assert timeseries.total_scores == {}  # evolution never fills totals

    def test_per_round_means_divide_by_agent_rounds(self) -> None:
        """Per-round = (mean x count) / rounds; None without rounds info."""
        timeseries = RunTimeseries(mode="evolution")
        timeseries.add(
            GenerationFinished(
                index=0,
                composition={"a": 2, "b": 1},
                mean_scores={"a": 30.0, "b": 50.0},
                rounds_played={"a": 20, "b": 10},
            )
        )
        timeseries.add(GenerationFinished(index=1, composition={"a": 3}, mean_scores={"a": 33.0}))
        assert timeseries.mean_scores_per_round["a"] == [3.0, None]  # no rounds info in gen 1
        assert timeseries.mean_scores_per_round["b"] == [5.0, None]
        # The raw rounds series is kept for the recorder (DECISIONS #47).
        assert timeseries.rounds_played == {"a": [20, 0], "b": [10, 0]}

    def test_running_means_average_over_the_whole_game(self) -> None:
        """DECISIONS #45: cumulative score / cumulative agents (or rounds).

        Gen 0: strategy "a" totals 60 over 2 agents and 20 rounds; gen 1:
        totals 99 over 3 agents and 30 rounds. Whole-game so far at gen 1:
        159/5 = 31.8 per agent-generation, 159/50 = 3.18 per round. A
        strategy absent from a generation carries forward flat.
        """
        timeseries = RunTimeseries(mode="evolution")
        timeseries.add(
            GenerationFinished(
                index=0,
                composition={"a": 2, "b": 1},
                mean_scores={"a": 30.0, "b": 50.0},
                rounds_played={"a": 20, "b": 10},
            )
        )
        timeseries.add(
            GenerationFinished(
                index=1,
                composition={"a": 3},
                mean_scores={"a": 33.0},
                rounds_played={"a": 30},
            )
        )
        assert timeseries.running_mean_scores["a"] == [30.0, 31.8]
        assert timeseries.running_mean_scores_per_round["a"] == [3.0, 3.18]
        # "b" sat generation 1 out: its whole-game average stays flat.
        assert timeseries.running_mean_scores["b"] == [50.0, 50.0]
        assert timeseries.running_mean_scores_per_round["b"] == [5.0, 5.0]

    def test_fine_events_are_ignored_and_final_is_kept(self) -> None:
        """Only period events build columns; RunFinished is stored."""
        timeseries = RunTimeseries(mode="evolution")
        timeseries.add(MatchFinished(agent_ids=(0, 1), total_payoffs={0: 1.0, 1: 1.0}, n_rounds=1))
        assert timeseries.periods == []
        final = RunFinished(
            mode="evolution",
            completed=1,
            composition={"a": 3},
            mean_scores={"a": 1.0},
            total_scores=None,
        )
        timeseries.add(final)
        assert timeseries.final == final

    def test_strategy_names_in_first_appearance_order(self) -> None:
        """The name order is stable — it drives chart trace order."""
        timeseries = RunTimeseries(mode="evolution")
        timeseries.add(
            GenerationFinished(
                index=0, composition={"b": 1, "a": 2}, mean_scores={"b": 0.0, "a": 0.0}
            )
        )
        assert timeseries.strategy_names() == ("b", "a")


class TestTournamentFolding:
    """CycleFinished events also fill the cumulative-totals series."""

    def test_per_round_means_use_cumulative_rounds(self) -> None:
        """Tournament per-round = cumulative total / cumulative rounds."""
        timeseries = RunTimeseries(mode="tournament")
        timeseries.add(
            CycleFinished(
                index=0,
                composition={"a": 1},
                total_scores={"a": 15.0},
                mean_scores={"a": 15.0},
                rounds_played={"a": 5},
            )
        )
        timeseries.add(
            CycleFinished(
                index=1,
                composition={"a": 1},
                total_scores={"a": 20.0},
                mean_scores={"a": 20.0},
                rounds_played={"a": 10},
            )
        )
        assert timeseries.mean_scores_per_round == {"a": [3.0, 2.0]}

    def test_totals_and_means_fold_per_cycle(self) -> None:
        """All three series grow one column per cycle."""
        timeseries = RunTimeseries(mode="tournament")
        timeseries.add(
            CycleFinished(
                index=0,
                composition={"a": 1, "b": 1},
                total_scores={"a": 4.0, "b": 9.0},
                mean_scores={"a": 4.0, "b": 9.0},
            )
        )
        timeseries.add(
            CycleFinished(
                index=1,
                composition={"a": 1, "b": 1},
                total_scores={"a": 9.0, "b": 14.0},
                mean_scores={"a": 9.0, "b": 14.0},
            )
        )
        assert timeseries.periods == [0, 1]
        assert timeseries.total_scores == {"a": [4.0, 9.0], "b": [9.0, 14.0]}
        assert timeseries.composition == {"a": [1, 1], "b": [1, 1]}


class TestAgentSnapshotFolding:
    """M10a: per-agent snapshots and the derived economy series."""

    @staticmethod
    def _snapshot(agent_id: int, energy: float, age: int, strategy: str = "a") -> AgentSnapshot:
        """Build a snapshot with the fields these tests care about."""
        return AgentSnapshot(
            agent_id=agent_id, parent_id=None, age=age, energy=energy, strategy=strategy
        )

    def test_imitation_events_leave_economy_series_empty(self) -> None:
        """No snapshots ever → charts know to skip the economy figures."""
        timeseries = RunTimeseries(mode="evolution")
        timeseries.add(GenerationFinished(index=0, composition={"a": 2}, mean_scores={"a": 1.0}))
        assert timeseries.agent_snapshots == []
        assert timeseries.mean_energy == {}
        assert timeseries.mean_age == {}

    def test_snapshots_fold_into_derived_means(self) -> None:
        """Per-strategy mean energy and age come straight from the snapshots."""
        timeseries = RunTimeseries(mode="evolution")
        timeseries.add(
            GenerationFinished(
                index=0,
                composition={"a": 2, "b": 1},
                mean_scores={"a": 1.0, "b": 2.0},
                agents=(
                    self._snapshot(0, energy=100.0, age=1, strategy="a"),
                    self._snapshot(1, energy=300.0, age=3, strategy="a"),
                    self._snapshot(2, energy=50.0, age=0, strategy="b"),
                ),
            )
        )
        assert timeseries.mean_energy == {"a": [200.0], "b": [50.0]}
        assert timeseries.mean_age == {"a": [2.0], "b": [0.0]}
        assert len(timeseries.agent_snapshots) == 1

    def test_extinction_period_still_appends(self) -> None:
        """Once economy data exists, an empty snapshot is meaningful."""
        timeseries = RunTimeseries(mode="evolution")
        timeseries.add(
            GenerationFinished(
                index=0,
                composition={"a": 1},
                mean_scores={"a": 1.0},
                agents=(self._snapshot(0, energy=10.0, age=1),),
            )
        )
        timeseries.add(
            GenerationFinished(index=1, composition={"a": 1}, mean_scores={"a": 0.5}, agents=())
        )
        assert timeseries.agent_snapshots == [
            (self._snapshot(0, energy=10.0, age=1),),
            (),
        ]
        assert timeseries.mean_energy == {"a": [10.0, None]}

    def test_population_size_is_derived_from_composition(self) -> None:
        """#47: N per period is a recomputation, never a stored series."""
        timeseries = RunTimeseries(mode="evolution")
        timeseries.add(GenerationFinished(index=0, composition={"a": 3}, mean_scores={"a": 1.0}))
        timeseries.add(
            GenerationFinished(
                index=1, composition={"a": 2, "b": 4}, mean_scores={"a": 1.0, "b": 1.0}
            )
        )
        assert timeseries.population_size == [3, 6]
