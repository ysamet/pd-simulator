"""Tests for run-folder persistence (``pdsim/io/results.py``, DECISIONS #47).

Covers: live-vs-loaded RunTimeseries round trips in both modes, the
end-to-end reproducibility guarantee (recorded config re-runs to identical
results), schema guards (schema_version, future-version rejection), the
runs index, and folder-collision handling.
"""

from __future__ import annotations

import json
import shutil
import stat
import sys
from pathlib import Path

import pytest

from pdsim.config.experiment import ExperimentConfig, load_config
from pdsim.core import engine
from pdsim.core.timeseries import RunTimeseries
from pdsim.io.results import (
    SCHEMA_VERSION,
    RunRecorder,
    _rmtree_robust,
    _unique_folder,
    delete_run,
    list_runs,
    load_run,
    read_index,
    rename_run,
    sync_index,
)


def _config(mode: str = "evolution") -> ExperimentConfig:
    """Build a tiny config whose run exercises the interesting cases.

    Args:
        mode: ``"evolution"`` (with mutation, so strategies appear and
            vanish mid-run — the alignment-sensitive case) or
            ``"tournament"``.

    Returns:
        A validated config.
    """
    return ExperimentConfig.model_validate(
        {
            "mode": mode,
            "tournament_cycles": 3,
            "seed": 11,
            "population": {
                "size": 6,
                "composition": {"tit_for_tat": 3, "always_defect": 3},
            },
            "match": {"length_mode": "fixed", "rounds_per_match": 4},
            "dynamics": {"generations": 5, "mutation_rate": 0.3},
        }
    )


def _record(
    config: ExperimentConfig, out_dir: Path, **kwargs: str | None
) -> tuple[Path, RunTimeseries]:
    """Run the engine through a recorder and finalize.

    Args:
        config: The experiment to run and record.
        out_dir: Runs directory (a tmp path in tests).
        **kwargs: Extra RunRecorder arguments (slug, scenario).

    Returns:
        The finished run folder and the live accumulator for comparison.
    """
    recorder = RunRecorder(config, out_dir=out_dir, **kwargs)
    for event in engine.run(config):
        recorder.add(event)
    return recorder.finalize(), recorder.timeseries


class TestRoundTrip:
    """Loaded runs must equal the live accumulation, series for series."""

    @pytest.mark.parametrize("mode", ["evolution", "tournament"])
    def test_loaded_timeseries_equals_live(self, mode: str, tmp_path: Path) -> None:
        """Raw persistence + recomputation reproduces every series exactly."""
        folder, live = _record(_config(mode), tmp_path)
        loaded = load_run(folder).timeseries
        assert loaded.mode == live.mode
        assert loaded.periods == live.periods
        assert loaded.composition == live.composition
        assert loaded.mean_scores == live.mean_scores
        assert loaded.rounds_played == live.rounds_played
        assert loaded.total_scores == live.total_scores
        # Derived views are recomputed, not persisted (DECISIONS #47) —
        # and still come out identical, the point of persisting raw data.
        assert loaded.mean_scores_per_round == live.mean_scores_per_round
        assert loaded.running_mean_scores == live.running_mean_scores
        assert loaded.running_mean_scores_per_round == live.running_mean_scores_per_round
        assert loaded.final == live.final

    def test_recorded_config_reruns_to_identical_results(self, tmp_path: Path) -> None:
        """Hard rule 8, end to end: config.yaml alone reproduces the run."""
        folder, live = _record(_config(), tmp_path)
        reloaded = load_config(folder / "config.yaml")  # comments are ignored
        events = list(engine.run(reloaded))
        assert events[-1] == live.final

    def test_loaded_config_equals_original(self, tmp_path: Path) -> None:
        """The version-comment header does not disturb the config itself."""
        config = _config("tournament")
        folder, _ = _record(config, tmp_path)
        assert load_config(folder / "config.yaml") == config


class TestSchemaGuards:
    """DECISIONS #46/#47: room to grow without breaking migrations."""

    def test_summary_carries_schema_version_and_code_version(self, tmp_path: Path) -> None:
        """The run card fields and the schema stamp are all present."""
        folder, _ = _record(_config(), tmp_path, scenario="my_scenario")
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        assert summary["schema_version"] == SCHEMA_VERSION
        assert summary["code_version"]["package"]
        assert summary["scenario"] == "my_scenario"
        assert summary["mode"] == "evolution"
        assert summary["periods_completed"] == 5
        assert "top strategy" in summary["headline"]

    def test_future_schema_version_is_rejected(self, tmp_path: Path) -> None:
        """Loading a run from a newer pdsim fails loudly, not weirdly."""
        folder, _ = _record(_config(), tmp_path)
        summary_path = folder / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["schema_version"] = SCHEMA_VERSION + 1
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        with pytest.raises(ValueError, match="schema_version"):
            load_run(folder)

    def test_unfinished_recording_cannot_finalize(self, tmp_path: Path) -> None:
        """No RunFinished event -> no fake 'completed' folder."""
        recorder = RunRecorder(_config(), out_dir=tmp_path)
        with pytest.raises(ValueError, match="RunFinished"):
            recorder.finalize()

    def test_discard_removes_the_partial_folder(self, tmp_path: Path) -> None:
        """DECISIONS #53: a stopped run leaves no ghost folder behind."""
        config = _config()
        recorder = RunRecorder(config, out_dir=tmp_path)
        for i, event in enumerate(engine.run(config)):
            recorder.add(event)
            if i > 2:
                break  # abandon mid-run, like the UI's Stop button
        assert recorder.folder.exists()  # config.yaml was written up front
        recorder.discard()
        assert not recorder.folder.exists()
        assert list_runs(tmp_path) == []  # nothing to browse, nothing on disk


class TestIndexAndFolders:
    """The runs catalog and folder naming."""

    def test_index_gains_exactly_one_row_per_run_newest_first(self, tmp_path: Path) -> None:
        """Two recordings -> two rows, most recent on top."""
        _record(_config(), tmp_path, slug="first")
        second_folder, _ = _record(_config(), tmp_path, slug="second")
        rows = read_index(tmp_path)
        assert len(rows) == 2
        assert rows[0]["run_id"] == second_folder.name
        assert rows[0]["seed"] == "11"
        assert rows[0]["mode"] == "evolution"

    def test_empty_directory_reads_as_no_runs(self, tmp_path: Path) -> None:
        """No index file yet -> an empty catalog, not an error."""
        assert read_index(tmp_path / "nothing_here") == []

    def test_folder_name_collisions_get_numeric_suffixes(self, tmp_path: Path) -> None:
        """Same timestamp + slug -> -2, -3 suffixes, never an overwrite."""
        first = _unique_folder(tmp_path, "20260706-120000_x")
        second = _unique_folder(tmp_path, "20260706-120000_x")
        assert first.name == "20260706-120000_x"
        assert second.name == "20260706-120000_x-2"


class TestListAndDelete:
    """Folder truth for the browser listing (DECISIONS #50)."""

    def test_list_runs_survives_hand_deletes_and_renames(self, tmp_path: Path) -> None:
        """Deleted folders vanish; renamed folders show their new name."""
        first, _ = _record(_config(), tmp_path, slug="one")
        second, _ = _record(_config(), tmp_path, slug="two")
        assert {card["run_id"] for card in list_runs(tmp_path)} == {first.name, second.name}
        shutil.rmtree(first)  # the owner deletes a folder by hand...
        second.rename(second.with_name("renamed-by-hand"))  # ...and renames one
        cards = list_runs(tmp_path)
        assert [card["run_id"] for card in cards] == ["renamed-by-hand"]
        # The renamed run is still fully loadable under its new name.
        assert load_run(tmp_path / "renamed-by-hand").timeseries.final is not None

    def test_delete_run_removes_folder_and_index_row(self, tmp_path: Path) -> None:
        """Deleting through the API keeps the CSV catalog in sync."""
        first, _ = _record(_config(), tmp_path, slug="one")
        second, _ = _record(_config(), tmp_path, slug="two")
        delete_run(tmp_path, first.name)
        assert not first.exists()
        assert [row["run_id"] for row in read_index(tmp_path)] == [second.name]
        assert [card["run_id"] for card in list_runs(tmp_path)] == [second.name]

    def test_delete_run_rejects_path_tricks_and_missing_runs(self, tmp_path: Path) -> None:
        """Only a direct child of the runs directory may be deleted."""
        with pytest.raises(ValueError, match="plain folder name"):
            delete_run(tmp_path, "../evil")
        with pytest.raises(FileNotFoundError, match="No recorded run"):
            delete_run(tmp_path, "no_such_run")

    def test_delete_survives_read_only_files(self, tmp_path: Path) -> None:
        """DECISIONS #51: read-only attributes must not block deletion.

        On Windows a read-only file makes plain ``shutil.rmtree`` raise
        WinError 5; the robust deleter clears the attribute and retries.
        """
        folder, _ = _record(_config(), tmp_path, slug="readonly")
        target = folder / "summary.json"
        target.chmod(stat.S_IREAD)
        delete_run(tmp_path, folder.name)
        assert not folder.exists()

    def test_sync_index_reconciles_hand_edits(self, tmp_path: Path) -> None:
        """DECISIONS #52: the catalog follows the folders on disk."""
        first, _ = _record(_config(), tmp_path, slug="one")
        second, _ = _record(_config(), tmp_path, slug="two")
        shutil.rmtree(first)  # hand-deleted...
        second.rename(second.with_name("renamed"))  # ...and hand-renamed
        cards = sync_index(tmp_path)
        assert [card["run_id"] for card in cards] == ["renamed"]
        assert [row["run_id"] for row in read_index(tmp_path)] == ["renamed"]
        # A second sync with nothing changed must not rewrite the file
        # (pointless writes would churn OneDrive sync).
        before = (tmp_path / "index.csv").stat().st_mtime_ns
        sync_index(tmp_path)
        assert (tmp_path / "index.csv").stat().st_mtime_ns == before

    def test_rename_run_updates_folder_summary_and_index(self, tmp_path: Path) -> None:
        """Renaming keeps every artifact coherent under the new name."""
        folder, _ = _record(_config(), tmp_path, slug="original")
        new_id = rename_run(tmp_path, folder.name, "my better name")
        assert new_id == "my better name"
        assert not folder.exists()
        loaded = load_run(tmp_path / "my better name")
        assert loaded.summary["run_id"] == "my better name"
        assert loaded.timeseries.final is not None
        assert [row["run_id"] for row in read_index(tmp_path)] == ["my better name"]

    def test_rename_run_rejects_bad_targets(self, tmp_path: Path) -> None:
        """Path tricks, collisions, and ghosts all fail loudly."""
        folder, _ = _record(_config(), tmp_path, slug="one")
        other, _ = _record(_config(), tmp_path, slug="two")
        with pytest.raises(ValueError, match="Invalid name"):
            rename_run(tmp_path, folder.name, "../evil")
        with pytest.raises(FileExistsError, match="already exists"):
            rename_run(tmp_path, folder.name, other.name)
        with pytest.raises(FileNotFoundError, match="No recorded run"):
            rename_run(tmp_path, "ghost", "whatever")

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows file-lock semantics")
    def test_locked_folder_fails_cleanly_after_retries(self, tmp_path: Path) -> None:
        """A genuinely held file ends in PermissionError, not a hang.

        Simulates what OneDrive/Explorer do: hold an open handle inside
        the folder. With shortened retries the robust deleter must give up
        with the original error (the UI turns it into advice).
        """
        folder, _ = _record(_config(), tmp_path, slug="locked")
        with (folder / "summary.json").open(encoding="utf-8"):
            with pytest.raises(PermissionError):
                _rmtree_robust(folder, attempts=2, base_delay=0.01)
