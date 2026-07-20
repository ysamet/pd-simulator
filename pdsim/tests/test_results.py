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
    PER_AGENT_SCHEMA_VERSION,
    PER_STRATEGY_SCHEMA_VERSION,
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

    @pytest.mark.parametrize("mode", ["evolution", "tournament"])
    def test_random_k_runs_round_trip(self, mode: str, tmp_path: Path) -> None:
        """Recorded random_k runs need no recorder changes (DECISIONS #57).

        The recorder only ever sees period events, so a sampled matcher —
        with its uneven per-agent participation — must persist and reload
        exactly like round-robin. Verified, not assumed.
        """
        data = _config(mode).model_dump()
        data["matching"] = {"matcher": "random_k", "opponents_per_agent": 3}
        config = ExperimentConfig.model_validate(data)
        folder, live = _record(config, tmp_path)
        loaded = load_run(folder).timeseries
        assert loaded.periods == live.periods
        assert loaded.composition == live.composition
        assert loaded.mean_scores == live.mean_scores
        assert loaded.rounds_played == live.rounds_played
        assert loaded.total_scores == live.total_scores
        assert loaded.final == live.final
        assert load_config(folder / "config.yaml") == config


class TestSchemaGuards:
    """DECISIONS #46/#47: room to grow without breaking migrations."""

    def test_summary_carries_schema_version_and_code_version(self, tmp_path: Path) -> None:
        """The run card fields and the schema stamp are all present.

        An imitation run has no per-agent data, so it writes schema 2 —
        byte-identical to pre-M10a recordings (M10a principle 2); economy
        runs write 3, and only async runs write ``SCHEMA_VERSION`` (4).
        """
        folder, _ = _record(_config(), tmp_path, scenario="my_scenario")
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        assert summary["schema_version"] == PER_STRATEGY_SCHEMA_VERSION
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


def _economy_config(**dynamics_overrides: object) -> ExperimentConfig:
    """Build a small energy-economy config for persistence tests (M10a).

    Args:
        **dynamics_overrides: Extra dynamics fields.

    Returns:
        A validated economy config with births and growth in 4 generations.
    """
    dynamics: dict[str, object] = {
        "reproduction_mode": "energy_economy",
        "mutation_rate": 0.0,
        "generations": 4,
        "reproduction_threshold": 40.0,
        "offspring_stake": 30.0,
        "initial_energy": 20.0,
        "basic_living_cost": 5.0,
        "carrying_capacity": 40,
    }
    dynamics.update(dynamics_overrides)
    return ExperimentConfig.model_validate(
        {
            "seed": 11,
            "population": {
                "size": 6,
                "composition": {"tit_for_tat": 3, "always_defect": 3},
            },
            "match": {"length_mode": "fixed", "rounds_per_match": 4},
            "dynamics": dynamics,
        }
    )


class TestEconomyPersistence:
    """M10a schema 3: agents.parquet, the summary fields, and the loader."""

    def test_economy_run_writes_schema_3_with_agents_parquet(self, tmp_path: Path) -> None:
        """The per-agent sibling table and the honest version stamp.

        A SYNCHRONOUS economy run has per-agent data but no event-time
        data, so it keeps writing 3 under M10b code — byte-identical to
        M10a recordings (the honest-presence rule, #83).
        """
        folder, live = _record(_economy_config(), tmp_path)
        assert (folder / "agents.parquet").is_file()
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        assert summary["schema_version"] == PER_AGENT_SCHEMA_VERSION
        assert summary["population_final"] == len(live.agent_snapshots[-1])
        max_id = max(s.agent_id for snapshot in live.agent_snapshots for s in snapshot)
        assert summary["total_agents_born"] == max_id + 1
        # The config header anticipates schema 3 for economy runs.
        assert "# schema_version: 3" in (folder / "config.yaml").read_text(encoding="utf-8")

    def test_imitation_run_writes_no_agents_parquet(self, tmp_path: Path) -> None:
        """Principle 2: imitation folders are byte-compatible with pre-M10a."""
        folder, _ = _record(_config(), tmp_path)
        assert not (folder / "agents.parquet").exists()
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        assert summary["schema_version"] == PER_STRATEGY_SCHEMA_VERSION
        assert summary["total_agents_born"] is None
        assert summary["population_final"] is None
        assert "# schema_version: 2" in (folder / "config.yaml").read_text(encoding="utf-8")

    def test_economy_round_trip_reconstructs_every_series(self, tmp_path: Path) -> None:
        """Loading refeeds the same code the live run used (#47/#65)."""
        folder, live = _record(_economy_config(), tmp_path)
        loaded = load_run(folder).timeseries
        assert loaded.agent_snapshots == live.agent_snapshots
        assert loaded.mean_energy == live.mean_energy
        assert loaded.mean_age == live.mean_age
        assert loaded.population_size == live.population_size
        assert loaded.composition == live.composition

    def test_founder_parent_ids_survive_the_parquet_round_trip(self, tmp_path: Path) -> None:
        """parent_id is a nullable integer: founders are None, children exact."""
        folder, _ = _record(_economy_config(), tmp_path)
        loaded = load_run(folder).timeseries
        first = loaded.agent_snapshots[0]
        assert any(s.parent_id is None for s in first)  # founders
        all_snapshots = [s for snapshot in loaded.agent_snapshots for s in snapshot]
        assert any(isinstance(s.parent_id, int) for s in all_snapshots)  # children

    def test_extinct_run_records_and_reloads(self, tmp_path: Path) -> None:
        """Extinction is a legitimate outcome end to end (spec Task 7).

        An unpayable living cost kills everyone at the second boundary
        (starting energy carries them past boundary 1, then runs dry), so
        the run ends early with an honest headline — and the folder
        round-trips, extinct final period included.
        """
        folder, live = _record(_economy_config(basic_living_cost=50.0), tmp_path)
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        assert summary["periods_completed"] < 4
        assert summary["population_final"] == 0
        assert "extinct" in summary["headline"]
        loaded = load_run(folder)
        assert loaded.timeseries.agent_snapshots == live.agent_snapshots
        assert loaded.timeseries.final is not None
        assert loaded.timeseries.final.composition == {}
        # And the sweep metrics survive an extinct run (spec Task 7).
        from pdsim.sweep.metrics import get_metric

        assert get_metric("final_share").compute(loaded, strategy="tit_for_tat") is not None
        assert get_metric("fixation_flag").compute(loaded, strategy="tit_for_tat") is not None
        assert get_metric("final_cooperation").compute(loaded) is not None


def _async_config(
    output_overrides: dict[str, object] | None = None, **dynamics_overrides: object
) -> ExperimentConfig:
    """Build a small asynchronous config for persistence tests (M10b).

    The defaults (variable_n economy, imitation overlay on, unpayable
    living cost off) produce births, insolvency deaths, AND imitation
    copies within 4 generation-equivalents, so all three explicit-event
    channels have rows to persist.

    Args:
        output_overrides: Optional ``output`` section fields (the
            recording cadence under test).
        **dynamics_overrides: Extra dynamics fields.

    Returns:
        A validated async config (seed 7).
    """
    dynamics: dict[str, object] = {
        "generations": 4,
        "time_model": "asynchronous",
        "imitation_overlay": True,
        "reproduction_threshold": 60.0,
        "offspring_stake": 50.0,
        "basic_living_cost": 25.0,
        "carrying_capacity": 30,
        "mutation_rate": 0.0,
    }
    dynamics.update(dynamics_overrides)
    return ExperimentConfig.model_validate(
        {
            "seed": 7,
            "population": {
                "size": 10,
                "composition": {"tit_for_tat": 5, "always_defect": 5},
            },
            "matching": {"matcher": "random_k", "opponents_per_agent": 2},
            "match": {"length_mode": "fixed", "rounds_per_match": 4},
            "dynamics": dynamics,
            "output": output_overrides or {},
        }
    )


class TestAsyncPersistence:
    """M10b schema 4: the event-time sibling tables and the loader (#83)."""

    def test_async_run_writes_schema_4_with_event_tables(self, tmp_path: Path) -> None:
        """The honest version stamp and the sibling tables that have rows."""
        folder, live = _record(_async_config(), tmp_path)
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        assert summary["schema_version"] == SCHEMA_VERSION
        assert "# schema_version: 4" in (folder / "config.yaml").read_text(encoding="utf-8")
        assert (folder / "periods.parquet").is_file()
        # The seed-7 fixture fires all three channels (verified below), so
        # all three tables exist.
        flat = [event for events in live.demographic_events for event in events]
        assert {type(event).__name__ for event in flat} == {
            "BirthEvent",
            "DeathEvent",
            "ImitationEvent",
        }
        assert (folder / "births.parquet").is_file()
        assert (folder / "deaths.parquet").is_file()
        assert (folder / "imitations.parquet").is_file()

    def test_async_round_trip_reconstructs_event_time_series(self, tmp_path: Path) -> None:
        """Loading refeeds the same code the live run used (#47/#65).

        The demographic events compare as full tuples per period, so this
        also pins the loader's re-interleaving of the three tables back
        into occurrence order (imitation < death < birth within an event).
        """
        folder, live = _record(_async_config(), tmp_path)
        loaded = load_run(folder).timeseries
        assert loaded.periods == live.periods
        assert loaded.gen_equiv_times == live.gen_equiv_times
        assert loaded.demographic_events == live.demographic_events
        assert loaded.agent_snapshots == live.agent_snapshots
        assert loaded.composition == live.composition
        assert loaded.mean_scores == live.mean_scores
        assert loaded.cooperation_pairs == live.cooperation_pairs
        assert loaded.final == live.final

    def test_moran_round_trip_preserves_death_before_birth(self, tmp_path: Path) -> None:
        """fixed_n pairs one death with one birth at the SAME event index.

        The two land in different parquet files, so this is the sharpest
        test of the loader's occurrence-order merge: every replacement
        must come back as death-then-birth, exactly as emitted.
        """
        folder, live = _record(
            _async_config(
                imitation_overlay=False,
                async_population="fixed_n",
                moran_rule="death_birth",
                fixed_n_death_rule="pure_random",
            ),
            tmp_path,
        )
        loaded = load_run(folder).timeseries
        assert loaded.demographic_events == live.demographic_events
        flat = [event for events in loaded.demographic_events for event in events]
        assert flat, "the Moran engine replaces every event — events expected"
        pairs = list(zip(flat[::2], flat[1::2], strict=True))
        for death, birth in pairs:
            assert death.event_index == birth.event_index
            assert type(death).__name__ == "DeathEvent"
            assert type(birth).__name__ == "BirthEvent"

    def test_extinct_async_run_round_trips_with_closing_deaths(self, tmp_path: Path) -> None:
        """Extinction's final partial period survives the round trip.

        That period has NO per-strategy rows (its population is empty at
        the recording point) — the loader's union-of-periods path must
        still deliver its closing deaths and clock stamp.
        """
        folder, live = _record(
            _async_config(imitation_overlay=False, basic_living_cost=60.0), tmp_path
        )
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        assert summary["population_final"] == 0
        assert "extinct" in summary["headline"]
        assert live.demographic_events[-1], "extinction's closing deaths reach the stream"
        loaded = load_run(folder).timeseries
        assert loaded.periods == live.periods
        assert loaded.gen_equiv_times == live.gen_equiv_times
        assert loaded.demographic_events == live.demographic_events
        assert loaded.agent_snapshots == live.agent_snapshots
        assert loaded.final == live.final

    def test_sync_folders_gain_no_event_time_files(self, tmp_path: Path) -> None:
        """The honest-presence rule (#83) protects sync byte-identity.

        Synchronous output must be byte-identical to pre-M10b recordings,
        so no event-time sibling table may appear in a synchronous folder.
        """
        for config in (_config(), _economy_config()):
            folder, _ = _record(config, tmp_path)
            for name in ("births", "deaths", "imitations", "periods"):
                assert not (folder / f"{name}.parquet").exists()

    def test_schema_3_folder_loads_without_async_views(self, tmp_path: Path) -> None:
        """Missing sibling files read as the empty shape (#65).

        A sync economy folder loads with no clock stamps and no
        demographic events — it simply renders without the async views.
        """
        folder, _ = _record(_economy_config(), tmp_path)
        loaded = load_run(folder).timeseries
        assert loaded.gen_equiv_times == [None] * len(loaded.periods)
        assert loaded.demographic_events == [()] * len(loaded.periods)

    def test_per_event_cadence_persists_more_periods(self, tmp_path: Path) -> None:
        """V4's headless counterpart: density changes, content does not.

        The cadence changes how often the record samples the run, never
        the run itself — the same seed reaches the same final population
        however often it is sampled.
        """
        coarse_folder, coarse = _record(_async_config(), tmp_path)
        fine_folder, fine = _record(
            _async_config(output_overrides={"recording_cadence": "per_event"}), tmp_path
        )
        assert len(fine.periods) > len(coarse.periods)
        # RunFinished.completed and the last window's mean scores follow
        # the cadence grain (documented in the spec); the simulation
        # itself — who is alive at the end — does not.
        assert fine.final is not None and coarse.final is not None
        assert fine.final.composition == coarse.final.composition
        assert fine.agent_snapshots[-1] == coarse.agent_snapshots[-1]
        # Both folders load back exactly (the round-trip is cadence-blind).
        assert load_run(coarse_folder).timeseries.periods == coarse.periods
        assert load_run(fine_folder).timeseries.periods == fine.periods
