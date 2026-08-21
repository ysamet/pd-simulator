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
    def test_cell_produces_positive_seconds_and_counted_matches(self, matcher: str) -> None:
        """A tiny cell times out to positive figures, matches counted.

        round_robin plays N(N−1)/2 = 28 at N = 8; random_k plays N·k = 16 —
        the counted figures must equal the arithmetic (M11b Phase C,
        #174(e): matches are COUNTED via the read-only observer).
        """
        config = _cell_config(8, matcher, k=2, rounds=2, generations=2, seed=0)
        timing = time_cell(config, generations=2)
        assert timing.seconds_per_generation > 0.0
        assert timing.matches_per_generation == (28 if matcher == "round_robin" else 16)


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
        """--out writes one CSV row per cell with the documented columns.

        The match-count and per-match columns joined at M11b Phase C
        (#174(e): per-match cost must be reported, matches counted).
        """
        out = tmp_path / "bench.csv"
        exit_code = main(["--sizes", "8", "--rounds", "2", "--generations", "2", "--out", str(out)])
        assert exit_code == 0
        with out.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 2  # one size x two matchers
        assert set(rows[0]) == {
            "n",
            "matcher",
            "seconds_per_generation",
            "matches_per_generation",
            "us_per_match",
        }
        assert float(rows[0]["seconds_per_generation"]) > 0.0
        assert float(rows[0]["matches_per_generation"]) > 0.0
        assert float(rows[0]["us_per_match"]) > 0.0

    def test_generations_below_two_rejected(self, capsys: pytest.CaptureFixture) -> None:
        """The warmup discard needs at least one timed generation left."""
        assert main(["--generations", "1"]) == 1
        assert "at least 2" in capsys.readouterr().err

    def test_bad_sizes_rejected(self, capsys: pytest.CaptureFixture) -> None:
        """A malformed --sizes list fails with a plain message."""
        assert main(["--sizes", "fifty"]) == 1
        assert "whole numbers" in capsys.readouterr().err


class TestStructureCells:
    """The M11a structure columns (spec Phase E, the #91 discipline)."""

    def test_structure_cell_builds_a_spatial_imitation_config(self) -> None:
        """A lattice label sets the toggle, the lattice, and the radius."""
        config = _cell_config(9, "lattice_moore_r5", k=2, rounds=2, generations=2, seed=0)
        assert config.matching.spatial_interaction is True
        assert config.structure.kind == "lattice"
        assert config.structure.neighbourhood_shape == "moore"
        assert config.structure.interaction_radius == 5
        # Constant N: the structure cells stay on the imitation loop.
        assert config.dynamics.reproduction_mode == "imitation"

    def test_structure_cell_produces_positive_seconds(self) -> None:
        """A tiny lattice cell times out to a positive figure."""
        config = _cell_config(9, "lattice_vn_r1", k=2, rounds=2, generations=2, seed=0)
        assert time_cell(config, generations=2).seconds_per_generation > 0.0

    def test_per_pair_cell_builds_the_dedup_config(self) -> None:
        """A `_per_pair` label is its parent's tuning plus the encounter mode."""
        config = _cell_config(9, "lattice_vn_r1_per_pair", k=5, rounds=2, generations=2, seed=0)
        parent = _cell_config(9, "lattice_vn_r1", k=5, rounds=2, generations=2, seed=0)
        assert config.matching.encounter_mode == "per_pair"
        assert parent.matching.encounter_mode == "per_initiator"
        # Identical tunings otherwise (#174(e)): only the mode differs.
        assert config.model_dump(exclude={"matching"}) == parent.model_dump(exclude={"matching"})
        assert config.structure.neighbourhood_shape == "von_neumann"
        assert config.structure.interaction_radius == 1

    def test_per_pair_cell_counts_exactly_half_in_the_forced_regime(self) -> None:
        """N = 9 von Neumann torus at k = 5: 36 matches per_initiator, 18 per_pair.

        The 3x3 von Neumann torus is the #139/#174(b) forced regime (k ≥
        degree 4), where the halving is exact — the counted figures pin
        that the bench's per-match denominators are real.
        """
        doubled = _cell_config(9, "lattice_vn_r1", k=5, rounds=2, generations=2, seed=0)
        halved = _cell_config(9, "lattice_vn_r1_per_pair", k=5, rounds=2, generations=2, seed=0)
        assert time_cell(doubled, generations=2).matches_per_generation == 36
        assert time_cell(halved, generations=2).matches_per_generation == 18

    def test_structure_cell_rejects_the_other_tunings(self) -> None:
        """A lattice label under the economy/async tunings is an error."""
        with pytest.raises(ValueError, match="synchronous imitation"):
            _cell_config(
                9,
                "lattice_vn_r1",
                k=2,
                rounds=2,
                generations=2,
                seed=0,
                reproduction_mode="energy_economy",
            )
        with pytest.raises(ValueError, match="synchronous imitation"):
            _cell_config(
                9,
                "lattice_vn_r1",
                k=2,
                rounds=2,
                generations=2,
                seed=0,
                time_model="asynchronous",
            )

    def test_structure_flag_runs_the_seven_column_grid(self, capsys: pytest.CaptureFixture) -> None:
        """--structure prints one row per (N, column) over all seven columns.

        Five at M11a Phase E; the two per_pair columns joined at M11b
        Phase C (#174(e)).
        """
        exit_code = main(["--sizes", "9", "--rounds", "2", "--generations", "2", "--structure"])
        assert exit_code == 0
        lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
        assert len(lines) == 1 + 7  # header + seven columns at one N
        assert any("lattice_moore_r5" in line for line in lines[1:])
        assert any("lattice_vn_r1_per_pair" in line for line in lines[1:])
        assert any("lattice_moore_r1_per_pair" in line for line in lines[1:])

    def test_structure_flag_rejects_the_async_grid(self, capsys: pytest.CaptureFixture) -> None:
        """--structure with --time-model asynchronous fails plainly."""
        assert main(["--structure", "--time-model", "asynchronous"]) == 1
        assert "synchronous imitation" in capsys.readouterr().err


class TestAsyncCells:
    """The M10b event-time column (spec Phase E, the #91 discipline)."""

    def test_async_cell_produces_positive_seconds(self) -> None:
        """An async cell times per generation-equivalent and stays sane."""
        config = _cell_config(
            8, "random_k", k=2, rounds=2, generations=2, seed=0, time_model="asynchronous"
        )
        assert config.dynamics.time_model == "asynchronous"
        # The constant-N tuning: nobody breeds, nobody starves.
        assert config.dynamics.reproduction_threshold == 1e12
        assert config.dynamics.basic_living_cost == 0.0
        assert time_cell(config, generations=2).seconds_per_generation > 0.0

    def test_async_grid_varies_n_only(self, capsys: pytest.CaptureFixture) -> None:
        """--time-model asynchronous collapses the matcher axis honestly."""
        exit_code = main(
            [
                "--sizes",
                "8,10",
                "--rounds",
                "2",
                "--generations",
                "2",
                "--time-model",
                "asynchronous",
            ]
        )
        assert exit_code == 0
        lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
        assert len(lines) == 1 + 2  # header + one event_time row per N
        assert all("event_time" in line for line in lines[1:])
