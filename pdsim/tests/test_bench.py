"""Tests for the benchmark rider (``pdsim/bench.py``, DECISIONS #58).

The rider is a measurement tool, so the tests exercise its plumbing — grid
construction, CLI parsing, table and CSV output — on tiny fast grids; the
actual timing numbers are environment noise and are only checked for shape.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pdsim.bench import _cell_config, _even_composition, main, time_cell


class TestEvenComposition:
    """The default roster mix, re-derived without the UI layer."""

    def test_splits_evenly_with_remainder_to_earliest(self) -> None:
        """50 agents over the 7-strategy roster: one 8, six 7s."""
        mix = _even_composition(50)
        assert sum(mix.values()) == 50
        assert sorted(mix.values(), reverse=True) == [8, 7, 7, 7, 7, 7, 7]

    def test_small_sizes_drop_zero_counts(self) -> None:
        """Fewer agents than strategies: no zero-count entries survive."""
        mix = _even_composition(4)
        assert sum(mix.values()) == 4
        assert all(count >= 1 for count in mix.values())


class TestCellTiming:
    """One grid cell runs and reports a sane number."""

    @pytest.mark.parametrize("matcher", ["round_robin", "random_k"])
    def test_cell_produces_positive_seconds(self, matcher: str) -> None:
        """A tiny cell times out to a positive per-generation figure."""
        config = _cell_config(8, matcher, k=2, rounds=2, generations=2, seed=0)
        seconds = time_cell(config, generations=2)
        assert seconds > 0.0


class TestCli:
    """The python -m pdsim.bench entry point."""

    def test_default_flags_parse_and_tiny_grid_runs(self, capsys: pytest.CaptureFixture) -> None:
        """A small grid prints one table row per (N, matcher) cell."""
        exit_code = main(["--sizes", "8,10", "--rounds", "2", "--generations", "2"])
        assert exit_code == 0
        lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
        assert "s/generation" in lines[0]
        assert len(lines) == 1 + 2 * 2  # header + sizes x matchers

    def test_out_flag_writes_csv(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """--out writes one CSV row per cell with the documented columns."""
        out = tmp_path / "bench.csv"
        exit_code = main(["--sizes", "8", "--rounds", "2", "--generations", "2", "--out", str(out)])
        assert exit_code == 0
        with out.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 2  # one size x two matchers
        assert set(rows[0]) == {"n", "matcher", "seconds_per_generation"}
        assert float(rows[0]["seconds_per_generation"]) > 0.0

    def test_generations_below_two_rejected(self, capsys: pytest.CaptureFixture) -> None:
        """The warmup discard needs at least one timed generation left."""
        assert main(["--generations", "1"]) == 1
        assert "at least 2" in capsys.readouterr().err

    def test_bad_sizes_rejected(self, capsys: pytest.CaptureFixture) -> None:
        """A malformed --sizes list fails with a plain message."""
        assert main(["--sizes", "fifty"]) == 1
        assert "whole numbers" in capsys.readouterr().err
