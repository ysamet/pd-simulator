"""Tests for RunTimeseries (``pdsim/core/timeseries.py``, DECISIONS #37).

Covers: folding period events into aligned per-strategy series, backfill
when a strategy first appears mid-run, fill values when one disappears,
indifference to fine-grained events, and capturing the final summary.
"""

from __future__ import annotations

from pdsim.core.events import CycleFinished, GenerationFinished, MatchFinished, RunFinished
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
