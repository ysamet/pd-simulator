"""Run-folder persistence: record and load complete runs (DESIGN §8).

The recorder is just another event-stream consumer, exactly like the UI and
the demo scripts (hard rule 4: nothing in ``pdsim/io`` imports viz or ui
code — chart HTML export is driven by the CLI/UI layers through
``pdsim/viz``, never from here). Each recorded run becomes a folder:

    runs/<timestamp>_<slug>/
        config.yaml         complete config incl. seed — this file alone
                            exactly reproduces the run (hard rule 8); code
                            version recorded as YAML comments at the top
        timeseries.parquet  RAW per-period, per-strategy rows (DECISIONS
                            #47: derived views like running averages are
                            cheap recomputations and are NOT persisted)
        cooperation.parquet RAW per-period, per-strategy-PAIR cooperation
                            rows (schema 2 — M9b, DECISIONS #65); the
                            sibling-file future that #47(c)'s naming
                            convention reserved
        agents.parquet      RAW per-period, per-AGENT snapshot rows
                            (schema 3 — M10a): passport id, parent id,
                            age, energy, strategy. Written only when the
                            run produced snapshots (energy-economy runs);
                            births/deaths are reconstructed by diff, so no
                            born/died flags (raw-not-derived, #47)
        births.parquet      RAW explicit birth rows (schema 4 — M10b);
        deaths.parquet      likewise deaths;
        imitations.parquet  likewise imitation-overlay strategy copies.
                            Async runs only, each written only when it has
                            rows — the exact intra-period timing and causes
                            that snapshots diff away (spec Design 7)
        periods.parquet     the period -> generation-equivalent-clock
                            mapping (schema 4; async runs only) — the
                            x-axis of every event-time chart
        summary.json        schema_version, mode, final standings, and
                            everything a run card needs without opening
                            the parquet
        *.html              chart exports, written by the CLI/UI layers

plus one appended row in ``runs/index.csv`` cataloguing every run.

Schema guard (DESIGN §8, DECISIONS #46/#47/#65/#83): ``summary.json``
carries ``schema_version``. Loaders accept 1 THROUGH 4 — a schema-1 folder
simply has no cooperation data and renders without the cooperation chart, a
schema-1/2 folder has no per-agent data and renders without the economy
charts, a schema ≤ 3 folder has no event-time data and renders without the
async views; versions above 4 are rejected. The version tracks the
presence of data (the honest-presence rule, #83): only an asynchronous run
produces event-time data and writes 4; a synchronous energy-economy run
still writes 3 and a synchronous imitation run still writes 2, each
byte-identical to what earlier code recorded. The per-strategy table is
named ``timeseries.parquet`` so sibling tables can sit alongside without a
breaking migration — exactly how ``cooperation.parquet`` arrived in schema
2, ``agents.parquet`` in schema 3, and the four event-time tables in
schema 4.

Concurrency note: appending to ``runs/index.csv`` is not guarded against
concurrent writers; simultaneous recording from multiple processes may
interleave rows (out of scope for v1).
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

import pdsim
from pdsim.config.experiment import ExperimentConfig, load_config, save_config
from pdsim.core.events import (
    AgentSnapshot,
    BirthEvent,
    CycleFinished,
    DeathEvent,
    DemographicEvent,
    Event,
    GenerationFinished,
    ImitationEvent,
    RunFinished,
)
from pdsim.core.timeseries import RunTimeseries

SCHEMA_VERSION = 4
"""Bump on any breaking change to the folder layout or file schemas.

History: 1 = M7 original; 2 = M9b adds ``cooperation.parquet`` and the
``final_cooperation_rate`` summary field (DECISIONS #65); 3 = M10a adds
``agents.parquet``, ``total_agents_born``, and ``population_final``;
4 = M10b adds the four event-time tables (``births.parquet``,
``deaths.parquet``, ``imitations.parquet``, ``periods.parquet``).
"""

PER_AGENT_SCHEMA_VERSION = 3
"""What a run with per-agent data but NO event-time data writes.

Synchronous energy-economy runs under M10b code: they produce snapshots
(``agents.parquet``) but no event-time clock or explicit demographic
events, so they keep declaring schema 3, byte-identical to M10a
recordings (the honest-presence rule, #83).
"""

PER_STRATEGY_SCHEMA_VERSION = 2
"""What a run WITHOUT per-agent data writes (synchronous imitation runs).

The schema version tracks the presence of data: only runs that produced
snapshots (energy-economy runs) write ``agents.parquet`` and declare
schema 3 or higher; everything else keeps writing 2, byte-identical to
pre-M10a recordings.
"""

COOPERATION_COLUMNS = (
    "period",
    "actor_strategy",
    "opponent_strategy",
    "cooperation_rate",
    "actions_counted",
)
"""Columns of ``cooperation.parquet``, one row per (period, ordered pair)."""

AGENTS_COLUMNS = (
    "period",
    "agent_id",
    "parent_id",
    "age",
    "energy",
    "strategy",
)
"""Columns of ``agents.parquet``, one row per (period, post-boundary agent).

``parent_id`` is a nullable integer (pandas ``Int64``): founders are
``<NA>``. There is deliberately no born/died flag — any id present at G but
not G−1 was born at G, any id present at G−1 but not G died during G, so
the birth/death record is derivable by diff (raw-not-derived, #47).
"""

BIRTHS_COLUMNS = (
    "period",
    "event_index",
    "gen_equiv_time",
    "agent_id",
    "parent_id",
    "strategy",
    "energy",
    "cause",
)
"""Columns of ``births.parquet``, one row per explicit birth (schema 4).

``parent_id`` is stored as a nullable integer (pandas ``Int64``) like its
``agents.parquet`` counterpart, though every recorded birth has a parent.
"""

DEATHS_COLUMNS = (
    "period",
    "event_index",
    "gen_equiv_time",
    "agent_id",
    "cause",
)
"""Columns of ``deaths.parquet``, one row per explicit death (schema 4)."""

IMITATIONS_COLUMNS = (
    "period",
    "event_index",
    "gen_equiv_time",
    "agent_id",
    "source_agent_id",
    "from_strategy",
    "to_strategy",
)
"""Columns of ``imitations.parquet``, one row per strategy copy (schema 4)."""

PERIODS_COLUMNS = (
    "period",
    "gen_equiv_time",
)
"""Columns of ``periods.parquet``: the period -> event-time clock mapping."""

INDEX_COLUMNS = (
    "run_id",
    "timestamp",
    "mode",
    "population",
    "periods",
    "seed",
    "scenario",
    "outcome",
)
"""Columns of ``runs/index.csv``, one row per recorded run."""


def _code_version() -> dict[str, str | None]:
    """Capture the code version that produced a run (DECISIONS #47).

    Returns:
        The package version, plus the short git commit hash when the
        working directory is a git checkout (best-effort: any failure —
        no git, not a checkout — silently yields ``None``).
    """
    git_hash: str | None = None
    try:
        git_hash = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except Exception:  # best-effort by design: no git, no checkout, no problem
        git_hash = None
    return {"package": pdsim.__version__, "git": git_hash}


def _unique_folder(out_dir: Path, name: str) -> Path:
    """Reserve a run-folder path, dodging collisions with a numeric suffix.

    Args:
        out_dir: The runs directory (created if missing).
        name: Desired folder name, e.g. ``"20260706-101500_my-slug"``.

    Returns:
        A created, previously non-existing folder path (``name``,
        ``name-2``, ``name-3``, ...).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate = out_dir / name
    counter = 2
    while candidate.exists():
        candidate = out_dir / f"{name}-{counter}"
        counter += 1
    candidate.mkdir()
    return candidate


def _headline(final: RunFinished) -> str:
    """Summarize a run's outcome in one plain-language phrase.

    Args:
        final: The run's closing event.

    Returns:
        Evolution: the most numerous final strategy and its count — or the
        extinction notice for an economy run whose population emptied
        (M10a: a legitimate outcome, reported rather than raised).
        Tournament: the winner by mean score per agent.
    """
    if final.mode == "tournament":
        winner = max(final.mean_scores, key=lambda name: final.mean_scores[name])
        return f"winner: {winner} ({final.mean_scores[winner]:.1f}/agent)"
    if not final.composition:
        return f"population extinct at generation {final.completed}"
    top = max(final.composition, key=lambda name: final.composition[name])
    return f"top strategy: {top} ({final.composition[top]}/{sum(final.composition.values())})"


class RunRecorder:
    """Persists one run as it streams: feed it events, then finalize.

    Usage (the CLI's pattern; the UI's live loop does the same)::

        recorder = RunRecorder(config, scenario="classic_tournament")
        for event in engine.run(config):
            recorder.add(event)
        folder = recorder.finalize()

    ``config.yaml`` is written up front, so even a crashed run leaves a
    reproducible config behind.
    """

    def __init__(
        self,
        config: ExperimentConfig,
        out_dir: Path | str = "runs",
        slug: str | None = None,
        scenario: str | None = None,
        append_index: bool = True,
        folder_name: str | None = None,
    ) -> None:
        """Open a run folder and write the config immediately.

        Args:
            config: The exact config about to be run (hard rule 8: what is
                written is what ran).
            out_dir: The runs directory (default ``runs/``).
            slug: Human-readable folder-name suffix; defaults to the
                scenario name or the run mode. Ignored if ``folder_name`` is
                given.
            scenario: Scenario name if the run was launched from one
                (recorded in the index and summary; ``None`` otherwise).
            append_index: Append a row to ``runs/index.csv`` on finalize.
                Sweep members set this False — parallel workers must not
                contend on one shared index file (DECISIONS #47e/#66); their
                catalog is the sweep summary, not ``index.csv``.
            folder_name: Exact folder name to use (still collision-suffixed),
                bypassing the ``<timestamp>_<slug>`` convention. Sweep members
                pass ``<NNN>_<axis-slug>`` so the sweep's ``runs/`` sorts by
                run index (DECISIONS #66).
        """
        self._config = config
        self._out_dir = Path(out_dir)
        self._scenario = scenario
        self._append_index = append_index
        self._started = time.monotonic()
        self.timeseries = RunTimeseries(mode=config.mode)
        if folder_name is not None:
            name = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in folder_name)
        else:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            safe_slug = "".join(
                ch if ch.isalnum() or ch in "-_" else "-"
                for ch in (slug or scenario or config.mode)
            )
            name = f"{stamp}_{safe_slug}"
        self.folder = _unique_folder(self._out_dir, name)
        version = _code_version()
        config_path = save_config(config, self.folder / "config.yaml")
        # The header comment anticipates the schema from the config (the
        # comment is written up front, before any event arrives): only an
        # asynchronous evolution run produces event-time data and schema 4;
        # only a synchronous energy-economy evolution run produces per-agent
        # data (and no event-time data) and schema 3; everything else keeps
        # writing 2, so imitation configs stay byte-identical to pre-M10a
        # recordings. summary.json's version is decided at finalize time
        # from the data actually recorded (the honest-presence rule, #83).
        if config.mode == "evolution" and config.dynamics.time_model == "asynchronous":
            anticipated = SCHEMA_VERSION
        elif config.mode == "evolution" and config.dynamics.reproduction_mode == "energy_economy":
            anticipated = PER_AGENT_SCHEMA_VERSION
        else:
            anticipated = PER_STRATEGY_SCHEMA_VERSION
        # YAML comments carry the code version without breaking load_config
        # (extra *keys* would be rejected by the strict schema — comments
        # are invisible to the parser; DECISIONS #47).
        original = config_path.read_text(encoding="utf-8")
        config_path.write_text(
            f"# recorded by pdsim {version['package']}"
            f" (git {version['git'] or 'unknown'})\n"
            f"# schema_version: {anticipated}\n" + original,
            encoding="utf-8",
        )
        self._version = version

    def add(self, event: Event) -> None:
        """Fold one engine event into the recording.

        Args:
            event: Any engine event; period events and ``RunFinished`` are
                what actually get persisted.
        """
        self.timeseries.add(event)

    def discard(self) -> None:
        """Delete the partially-written run folder (a stopped/abandoned run).

        The counterpart of :meth:`finalize` (DECISIONS #53): an explicitly
        stopped run is a deliberate abandonment, and its half-written folder
        would otherwise linger as a ghost — on disk but invisible to the
        browser and the index, which only know finalized runs. Uses the
        lock-tolerant deleter (#51). Crashes are different: a crashed run
        never reaches either call, so its ``config.yaml`` folder survives
        for diagnosis.
        """
        _rmtree_robust(self.folder)

    def finalize(self) -> Path:
        """Write the parquet, summary, and index row; return the folder.

        Returns:
            The completed run folder.

        Raises:
            ValueError: If no ``RunFinished`` event was recorded — the run
                did not complete, and a partial recording would look like a
                finished one.
        """
        if self.timeseries.final is None:
            raise ValueError("Cannot finalize a recording without a RunFinished event.")
        self._write_parquet()
        self._write_cooperation_parquet()
        self._write_agents_parquet()
        self._write_demographic_parquets()
        self._write_periods_parquet()
        summary = self._write_summary()
        if self._append_index:
            self._append_index_row(summary)
        return self.folder

    def _has_agent_data(self) -> bool:
        """Whether this run produced per-agent snapshots (M10a, schema 3).

        Returns:
            True if any period recorded a non-empty snapshot — the single
            predicate behind ``agents.parquet``, the summary's schema
            version, and the economy summary fields.
        """
        return any(self.timeseries.agent_snapshots)

    def _has_event_time_data(self) -> bool:
        """Whether this run produced event-time data (M10b, schema 4).

        Returns:
            True if any period carries a generation-equivalent clock stamp
            — only asynchronous runs do (synchronous ones leave the stamp
            ``None``, the honest "this run has no event-time clock"). The
            single predicate behind ``periods.parquet`` and the schema-4
            version (the honest-presence rule, #83); the three demographic
            tables are additionally gated on having rows at all.
        """
        return any(t is not None for t in self.timeseries.gen_equiv_times)

    def _write_parquet(self) -> None:
        """Write the raw per-period, per-strategy table (DECISIONS #47).

        One row per (period, strategy-with-agents); columns: period,
        strategy, agents, mean_score, total_score (tournament only — NaN
        in evolution, whose per-generation total is mean x agents),
        rounds_played.
        """
        series = self.timeseries
        rows = []
        for i, period in enumerate(series.periods):
            for name, counts in series.composition.items():
                if counts[i] == 0:
                    continue  # extinct this period: raw events carried no row
                rows.append(
                    {
                        "period": period,
                        "strategy": name,
                        "agents": counts[i],
                        "mean_score": series.mean_scores[name][i],
                        "total_score": (
                            series.total_scores[name][i] if series.mode == "tournament" else None
                        ),
                        "rounds_played": series.rounds_played[name][i],
                    }
                )
        # Explicit columns so even a run with NO per-strategy rows (an async
        # run extinct within its first recording period) writes a well-formed
        # empty table the loader can still group by period.
        columns = ["period", "strategy", "agents", "mean_score", "total_score", "rounds_played"]
        pd.DataFrame(rows, columns=columns).to_parquet(
            self.folder / "timeseries.parquet", index=False
        )

    def _write_cooperation_parquet(self) -> None:
        """Write the raw per-period, per-pair cooperation table (schema 2).

        One row per (period, ordered strategy pair that played); columns per
        ``COOPERATION_COLUMNS``. Raw rows only — per-strategy and population
        aggregates are recomputed on load by the same ``RunTimeseries`` code
        the live run used (#47's raw-vs-derived rule; DECISIONS #65).
        """
        series = self.timeseries
        rows = []
        for i, period in enumerate(series.periods):
            for (actor, opponent), rates in series.cooperation_pairs.items():
                count = series.cooperation_pair_actions[(actor, opponent)][i]
                if not count:
                    continue  # the pair played no actions this period: no raw row
                rows.append(
                    {
                        "period": period,
                        "actor_strategy": actor,
                        "opponent_strategy": opponent,
                        "cooperation_rate": rates[i],
                        "actions_counted": count,
                    }
                )
        frame = pd.DataFrame(rows, columns=list(COOPERATION_COLUMNS))
        frame.to_parquet(self.folder / "cooperation.parquet", index=False)

    def _write_agents_parquet(self) -> None:
        """Write the raw per-period, per-agent snapshot table (schema 3).

        One row per (period, post-boundary agent); columns per
        ``AGENTS_COLUMNS``. Written ONLY when the run produced snapshots —
        imitation runs get no file (and stay schema 2). A period with no
        rows is meaningful: the population was extinct after that boundary.
        Raw rows only — the per-strategy energy/age means are recomputed on
        load by the same ``RunTimeseries`` code the live run used (#47).
        """
        if not self._has_agent_data():
            return
        series = self.timeseries
        rows = []
        for i, period in enumerate(series.periods):
            for snapshot in series.agent_snapshots[i]:
                rows.append(
                    {
                        "period": period,
                        "agent_id": snapshot.agent_id,
                        "parent_id": snapshot.parent_id,
                        "age": snapshot.age,
                        "energy": snapshot.energy,
                        "strategy": snapshot.strategy,
                    }
                )
        frame = pd.DataFrame(rows, columns=list(AGENTS_COLUMNS))
        # Nullable integer dtype: founders' parent_id is a real <NA>, not a
        # float NaN that would corrupt the ids of everyone else.
        frame["parent_id"] = frame["parent_id"].astype("Int64")
        frame.to_parquet(self.folder / "agents.parquet", index=False)

    def _write_demographic_parquets(self) -> None:
        """Write the raw explicit-event tables (schema 4, spec Design 10).

        One row per birth/death/imitation, in occurrence order within each
        period (the stored row order IS the occurrence order — the loader
        relies on it when re-interleaving the three files). Each table is
        written only when it has rows, so a synchronous run — or an async
        run in which that channel never fired — adds no files, and the
        missing file reads back as the empty shape (#65).
        """
        series = self.timeseries
        births, deaths, imitations = [], [], []
        for period, events in zip(series.periods, series.demographic_events, strict=True):
            for event in events:
                stamp = {
                    "period": period,
                    "event_index": event.event_index,
                    "gen_equiv_time": event.gen_equiv_time,
                    "agent_id": event.agent_id,
                }
                if isinstance(event, BirthEvent):
                    births.append(
                        stamp
                        | {
                            "parent_id": event.parent_id,
                            "strategy": event.strategy,
                            "energy": event.energy,
                            "cause": event.cause,
                        }
                    )
                elif isinstance(event, DeathEvent):
                    deaths.append(stamp | {"cause": event.cause})
                else:
                    imitations.append(
                        stamp
                        | {
                            "source_agent_id": event.source_agent_id,
                            "from_strategy": event.from_strategy,
                            "to_strategy": event.to_strategy,
                        }
                    )
        if births:
            frame = pd.DataFrame(births, columns=list(BIRTHS_COLUMNS))
            # Nullable integer dtype, mirroring agents.parquet's parent_id.
            frame["parent_id"] = frame["parent_id"].astype("Int64")
            frame.to_parquet(self.folder / "births.parquet", index=False)
        if deaths:
            frame = pd.DataFrame(deaths, columns=list(DEATHS_COLUMNS))
            frame.to_parquet(self.folder / "deaths.parquet", index=False)
        if imitations:
            frame = pd.DataFrame(imitations, columns=list(IMITATIONS_COLUMNS))
            frame.to_parquet(self.folder / "imitations.parquet", index=False)

    def _write_periods_parquet(self) -> None:
        """Write the period -> event-time clock mapping (schema 4).

        One row per recording period; the x-axis every event-time chart
        needs. Written only when the run produced event-time data —
        asynchronous runs stamp every period, synchronous runs none, so
        this is all-or-nothing per run (the honest-presence rule, #83).
        """
        if not self._has_event_time_data():
            return
        series = self.timeseries
        rows = [
            {"period": period, "gen_equiv_time": stamp}
            for period, stamp in zip(series.periods, series.gen_equiv_times, strict=True)
        ]
        frame = pd.DataFrame(rows, columns=list(PERIODS_COLUMNS))
        frame.to_parquet(self.folder / "periods.parquet", index=False)

    def _write_summary(self) -> dict[str, object]:
        """Write summary.json — everything a run card needs.

        Note the two population fields: ``population_size`` is config-derived
        and therefore means the INITIAL size (left alone on purpose — every
        existing consumer reads it); ``population_final`` (schema 3) is the
        size of the last post-boundary snapshot, which is what a growth
        economy ends with (0 for an extinct run, ``None`` for runs without
        per-agent data).

        Returns:
            The summary mapping (also used for the index row).
        """
        final = self.timeseries.final
        assert final is not None  # guarded by finalize()
        has_agents = self._has_agent_data()
        snapshots = self.timeseries.agent_snapshots
        # The version tracks the presence of data (the honest-presence
        # rule, #83): event-time data -> 4 (async runs), per-agent data
        # only -> 3 (sync economy runs, byte-identical to M10a), neither
        # -> 2 (sync imitation runs, byte-identical to pre-M10a).
        if self._has_event_time_data():
            version = SCHEMA_VERSION
        elif has_agents:
            version = PER_AGENT_SCHEMA_VERSION
        else:
            version = PER_STRATEGY_SCHEMA_VERSION
        summary: dict[str, object] = {
            "schema_version": version,
            "run_id": self.folder.name,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "code_version": self._version,
            "mode": final.mode,
            "seed": self._config.seed,
            "population_size": self._config.population.size,
            "periods_completed": final.completed,
            "scenario": self._scenario,
            "duration_seconds": round(time.monotonic() - self._started, 3),
            "headline": _headline(final),
            # The run card's cooperation figure (schema 2, #65): the last
            # period's overall rate — per-generation in evolution,
            # run-cumulative in tournament (the #65 asymmetry).
            "final_cooperation_rate": (
                self.timeseries.cooperation_overall[-1]
                if self.timeseries.cooperation_overall
                else None
            ),
            "final_composition": final.composition,
            "final_mean_scores": final.mean_scores,
            "final_total_scores": final.total_scores,
        }
        if has_agents:
            # total_agents_born drops out of the id contract for free: ids
            # are issued 0..max and never reused, so the largest passport id
            # ever seen (+1 for 0-based ids) counts every agent ever created,
            # founders included.
            summary["total_agents_born"] = (
                max(s.agent_id for snapshot in snapshots for s in snapshot) + 1
            )
            summary["population_final"] = len(snapshots[-1])
        else:
            summary["total_agents_born"] = None
            summary["population_final"] = None
        (self.folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    def _append_index_row(self, summary: dict[str, object]) -> None:
        """Append this run's row to ``runs/index.csv`` (header on first use).

        Args:
            summary: The summary mapping written by :meth:`_write_summary`.
        """
        index_path = self._out_dir / "index.csv"
        is_new = not index_path.exists()
        with index_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=INDEX_COLUMNS)
            if is_new:
                writer.writeheader()
            writer.writerow(
                {
                    "run_id": summary["run_id"],
                    "timestamp": summary["timestamp"],
                    "mode": summary["mode"],
                    "population": summary["population_size"],
                    "periods": summary["periods_completed"],
                    "seed": summary["seed"],
                    "scenario": summary["scenario"] or "",
                    "outcome": summary["headline"],
                }
            )


@dataclass(frozen=True, slots=True)
class LoadedRun:
    """A recorded run, reconstructed from its folder.

    Attributes:
        config: The exact config that produced the run.
        timeseries: The reconstructed accumulator — identical to what the
            live run accumulated, including recomputed derived views
            (the payoff of persisting raw data, DECISIONS #47).
        summary: The parsed ``summary.json``.
    """

    config: ExperimentConfig
    timeseries: RunTimeseries
    summary: dict[str, object]


def load_run(folder: Path | str) -> LoadedRun:
    """Load a recorded run folder back into memory.

    Rebuilds the period events from the raw parquet rows and refeeds a
    fresh :class:`RunTimeseries` — demographic events first, in occurrence
    order, then each period's ``GenerationFinished`` (the live stream's
    order, spec Design 7) — so every derived view (per-round means,
    whole-game running averages) is recomputed by the exact same code the
    live run used.

    Args:
        folder: The run folder (containing config.yaml etc.).

    Returns:
        The reconstructed run.

    Raises:
        FileNotFoundError: If the folder or a required file is missing.
        ValueError: If the summary's schema version is newer than this
            code understands (older versions load fine — a schema-1 folder
            simply has no cooperation data, a schema ≤ 3 folder no
            event-time data, DECISIONS #65).
    """
    folder = Path(folder)
    summary: dict[str, object] = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    if int(summary.get("schema_version", 0)) > SCHEMA_VERSION:
        raise ValueError(
            f"Run {folder.name} has schema_version {summary['schema_version']}; this code "
            f"understands up to {SCHEMA_VERSION}. Update pdsim to load it."
        )
    config = load_config(folder / "config.yaml")
    frame = pd.read_parquet(folder / "timeseries.parquet")
    cooperation_by_period = _read_cooperation(folder)
    agents_by_period = _read_agents(folder)
    events_by_period = _read_demographic_events(folder)
    period_times = _read_period_times(folder)
    timeseries = RunTimeseries(mode=str(summary["mode"]))
    if timeseries.mode == "tournament":
        for period, group in frame.groupby("period", sort=True):
            composition = dict(zip(group["strategy"], group["agents"].astype(int), strict=True))
            mean_scores = dict(zip(group["strategy"], group["mean_score"], strict=True))
            rounds = dict(zip(group["strategy"], group["rounds_played"].astype(int), strict=True))
            totals = dict(zip(group["strategy"], group["total_score"], strict=True))
            timeseries.add(
                CycleFinished(
                    index=int(period),
                    composition=composition,
                    total_scores=totals,
                    mean_scores=mean_scores,
                    rounds_played=rounds,
                    cooperation=cooperation_by_period.get(int(period), {}),
                )
            )
    else:
        # The per-strategy table has no rows for a period whose population
        # was extinct, but the schema-4 sibling tables can still know it
        # (its closing deaths, its clock stamp) — so evolution periods are
        # the UNION of what the tables mention. For sync folders the union
        # is exactly the per-strategy periods, as before.
        groups = {int(period): group for period, group in frame.groupby("period", sort=True)}
        for period in sorted(set(groups) | set(period_times) | set(events_by_period)):
            group = groups.get(period)
            if group is None:  # extinct at this recording point: no rows
                composition, mean_scores, rounds = {}, {}, {}
            else:
                composition = dict(zip(group["strategy"], group["agents"].astype(int), strict=True))
                mean_scores = dict(zip(group["strategy"], group["mean_score"], strict=True))
                rounds = dict(
                    zip(group["strategy"], group["rounds_played"].astype(int), strict=True)
                )
            # Demographic events precede their period's closing event in
            # the live stream (spec Design 7); refeed in the same order.
            for event in events_by_period.get(period, ()):
                timeseries.add(event)
            timeseries.add(
                GenerationFinished(
                    index=period,
                    composition=composition,
                    mean_scores=mean_scores,
                    rounds_played=rounds,
                    cooperation=cooperation_by_period.get(period, {}),
                    agents=agents_by_period.get(period, ()),
                    gen_equiv_time=period_times.get(period),
                )
            )
    timeseries.add(
        RunFinished(
            mode=str(summary["mode"]),
            completed=int(summary["periods_completed"]),  # type: ignore[arg-type]
            composition=dict(summary["final_composition"]),  # type: ignore[arg-type]
            mean_scores=dict(summary["final_mean_scores"]),  # type: ignore[arg-type]
            total_scores=(
                dict(summary["final_total_scores"])  # type: ignore[arg-type]
                if summary["final_total_scores"] is not None
                else None
            ),
        )
    )
    return LoadedRun(config=config, timeseries=timeseries, summary=summary)


def _read_cooperation(folder: Path) -> dict[int, dict[tuple[str, str], tuple[float, int]]]:
    """Read a run folder's cooperation table, if it has one (schema 2).

    Args:
        folder: The run folder.

    Returns:
        Per period: ordered pair → (rate, actions counted). Empty for
        schema-1 folders (recorded before cooperation existed) — the
        loader's compatibility path, DECISIONS #65.
    """
    path = folder / "cooperation.parquet"
    if not path.is_file():
        return {}
    frame = pd.read_parquet(path)
    by_period: dict[int, dict[tuple[str, str], tuple[float, int]]] = {}
    for row in frame.itertuples(index=False):
        pair = (str(row.actor_strategy), str(row.opponent_strategy))
        by_period.setdefault(int(row.period), {})[pair] = (
            float(row.cooperation_rate),
            int(row.actions_counted),
        )
    return by_period


def _read_agents(folder: Path) -> dict[int, tuple[AgentSnapshot, ...]]:
    """Read a run folder's per-agent snapshot table, if it has one (schema 3).

    Args:
        folder: The run folder.

    Returns:
        Per period: the post-boundary snapshots, in stored (ascending id)
        order. Empty for schema-1/2 folders — the loader's compatibility
        path (#65): those runs simply render without the economy views.
    """
    path = folder / "agents.parquet"
    if not path.is_file():
        return {}
    frame = pd.read_parquet(path)
    by_period: dict[int, list[AgentSnapshot]] = {}
    for row in frame.itertuples(index=False):
        by_period.setdefault(int(row.period), []).append(
            AgentSnapshot(
                agent_id=int(row.agent_id),
                # Founders are stored as pandas <NA>; back to Python None.
                parent_id=None if pd.isna(row.parent_id) else int(row.parent_id),
                age=int(row.age),
                energy=float(row.energy),
                strategy=str(row.strategy),
            )
        )
    return {period: tuple(snapshots) for period, snapshots in by_period.items()}


def _read_demographic_events(folder: Path) -> dict[int, tuple[DemographicEvent, ...]]:
    """Read a run folder's explicit-event tables, if it has any (schema 4).

    The three tables are re-interleaved into each period's occurrence
    order. Within one interaction event, imitations happen during the
    match bundle, deaths during the demographic step, births last (both
    engines empty seats before filling them) — so a stable sort by
    ``(event_index, kind)`` with kind ordered imitation < death < birth,
    over rows appended in stored (occurrence) order per table, restores
    the live stream's order exactly.

    Args:
        folder: The run folder.

    Returns:
        Per period: the demographic events in occurrence order. Empty for
        schema ≤ 3 folders — the loader's compatibility path (#65): those
        runs simply render without the async views. Each missing table
        likewise reads as "that channel never fired".
    """
    by_period: dict[int, list[tuple[int, int, DemographicEvent]]] = {}

    def collect(row_period: int, event_index: int, kind: int, event: DemographicEvent) -> None:
        by_period.setdefault(row_period, []).append((event_index, kind, event))

    path = folder / "imitations.parquet"
    if path.is_file():
        for row in pd.read_parquet(path).itertuples(index=False):
            collect(
                int(row.period),
                int(row.event_index),
                0,
                ImitationEvent(
                    agent_id=int(row.agent_id),
                    from_strategy=str(row.from_strategy),
                    to_strategy=str(row.to_strategy),
                    source_agent_id=int(row.source_agent_id),
                    event_index=int(row.event_index),
                    gen_equiv_time=float(row.gen_equiv_time),
                ),
            )
    path = folder / "deaths.parquet"
    if path.is_file():
        for row in pd.read_parquet(path).itertuples(index=False):
            collect(
                int(row.period),
                int(row.event_index),
                1,
                DeathEvent(
                    agent_id=int(row.agent_id),
                    cause=str(row.cause),
                    event_index=int(row.event_index),
                    gen_equiv_time=float(row.gen_equiv_time),
                ),
            )
    path = folder / "births.parquet"
    if path.is_file():
        for row in pd.read_parquet(path).itertuples(index=False):
            collect(
                int(row.period),
                int(row.event_index),
                2,
                BirthEvent(
                    agent_id=int(row.agent_id),
                    parent_id=int(row.parent_id),
                    strategy=str(row.strategy),
                    energy=float(row.energy),
                    cause=str(row.cause),
                    event_index=int(row.event_index),
                    gen_equiv_time=float(row.gen_equiv_time),
                ),
            )
    return {
        # sorted() is stable, so equal (event_index, kind) keys keep their
        # per-table row order — which is the occurrence order they were
        # written in.
        period: tuple(event for _index, _kind, event in sorted(items, key=lambda t: t[:2]))
        for period, items in by_period.items()
    }


def _read_period_times(folder: Path) -> dict[int, float]:
    """Read a run folder's period -> clock mapping, if it has one (schema 4).

    Args:
        folder: The run folder.

    Returns:
        Per period: the generation-equivalent clock at that recording
        point. Empty for schema ≤ 3 folders (synchronous runs have no
        event-time clock) — the loader then stamps ``None``, exactly what
        the live synchronous stream carried.
    """
    path = folder / "periods.parquet"
    if not path.is_file():
        return {}
    frame = pd.read_parquet(path)
    return {int(row.period): float(row.gen_equiv_time) for row in frame.itertuples(index=False)}


def list_runs(out_dir: Path | str = "runs") -> list[dict[str, object]]:
    """List the run folders that actually exist, newest first.

    The folders on disk are the truth (DECISIONS #50): unlike the
    append-only ``index.csv``, this survives the owner deleting or renaming
    folders by hand — a renamed folder appears under its new name. Each
    card is built from the folder's ``summary.json``; folders without a
    readable summary are skipped silently (they are not loadable runs).

    Args:
        out_dir: The runs directory.

    Returns:
        One card per loadable run: the ``INDEX_COLUMNS`` fields, with
        ``run_id`` taken from the *current* folder name.
    """
    out = Path(out_dir)
    if not out.is_dir():
        return []
    cards: list[dict[str, object]] = []
    for folder in out.iterdir():
        summary_path = folder / "summary.json"
        if not folder.is_dir() or not summary_path.is_file():
            continue
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # unreadable folder: not a loadable run, not an error
        cards.append(
            {
                "run_id": folder.name,
                "timestamp": summary.get("timestamp", ""),
                "mode": summary.get("mode", "?"),
                "population": summary.get("population_size", ""),
                "periods": summary.get("periods_completed", ""),
                "seed": summary.get("seed", ""),
                "scenario": summary.get("scenario") or "",
                "outcome": summary.get("headline", ""),
            }
        )
    return sorted(cards, key=lambda card: str(card["timestamp"]), reverse=True)


def _rmtree_robust(folder: Path, attempts: int = 6, base_delay: float = 0.25) -> None:
    """Delete a directory tree, tolerating Windows' transient file locks.

    On Windows, ``shutil.rmtree`` fails with ``PermissionError`` (WinError 5)
    when anything briefly holds a handle inside the folder — OneDrive's sync
    engine (this project lives under OneDrive), an Explorer window showing
    the folder, antivirus scans — or when a file carries the read-only
    attribute. This wrapper clears read-only bits and retries with a growing
    delay before giving up (DECISIONS #51).

    Args:
        folder: The directory to remove.
        attempts: Total tries before re-raising the last error.
        base_delay: First retry delay in seconds (grows linearly).

    Raises:
        OSError: The last error, if every attempt failed — the caller turns
            it into a plain-language message.
    """
    for attempt in range(attempts):
        try:
            shutil.rmtree(folder)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            # Clear read-only attributes (a common unlink blocker), then
            # give whatever holds a handle a moment to let go.
            for path in [folder, *folder.rglob("*")]:
                try:
                    os.chmod(path, stat.S_IWRITE)
                except OSError:
                    pass  # the path may already be gone mid-walk
            time.sleep(base_delay * (attempt + 1))


def delete_run(out_dir: Path | str, run_id: str) -> None:
    """Delete a recorded run: its folder and its ``index.csv`` row.

    Args:
        out_dir: The runs directory.
        run_id: The run's folder name (a plain name, never a path).

    Raises:
        ValueError: If ``run_id`` contains path separators or ``..`` —
            this function only ever deletes a direct child of ``out_dir``.
        FileNotFoundError: If no such run folder exists.
        PermissionError: If the folder stays locked after several retries
            (e.g. an Explorer window or OneDrive sync holding it open) —
            see :func:`_rmtree_robust`.
    """
    if any(part in run_id for part in ("/", "\\", "..")) or not run_id.strip():
        raise ValueError(f"Invalid run id {run_id!r}: expected a plain folder name.")
    out = Path(out_dir)
    folder = out / run_id
    if not folder.is_dir():
        raise FileNotFoundError(f"No recorded run named {run_id!r} in {out}.")
    _rmtree_robust(folder)
    sync_index(out)


def sync_index(out_dir: Path | str = "runs") -> list[dict[str, object]]:
    """Reconcile ``index.csv`` with the run folders on disk; return the cards.

    The catalog is derived from folder truth (DECISIONS #52, superseding
    the #50 append-only stance): rows for deleted folders vanish, renamed
    folders appear under their current names. The file is rewritten only
    when it is actually stale — pointless writes would churn OneDrive sync.

    Args:
        out_dir: The runs directory.

    Returns:
        The current run cards, newest first (same shape as
        :func:`list_runs`).
    """
    out = Path(out_dir)
    cards = list_runs(out)
    desired = [
        {column: str(card[column]) for column in INDEX_COLUMNS}
        for card in reversed(cards)  # the file stays in oldest-first append order
    ]
    index_path = out / "index.csv"
    existing: list[dict[str, str]] | None = None
    if index_path.exists():
        with index_path.open(newline="", encoding="utf-8") as handle:
            existing = [dict(row) for row in csv.DictReader(handle)]
    if desired != existing and (desired or existing is not None):
        out.mkdir(parents=True, exist_ok=True)
        with index_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=INDEX_COLUMNS)
            writer.writeheader()
            writer.writerows(desired)
    return cards


_RUN_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*$")
"""Folder names accepted by :func:`rename_run` (safe on Windows and POSIX)."""


def rename_run(out_dir: Path | str, run_id: str, new_name: str) -> str:
    """Rename a recorded run's folder (and keep its metadata coherent).

    Updates the ``run_id`` inside ``summary.json`` and reconciles
    ``index.csv`` afterwards, so the catalog and the run cards follow the
    new name (DECISIONS #52).

    Args:
        out_dir: The runs directory.
        run_id: The run's current folder name.
        new_name: The desired folder name.

    Returns:
        The new run id (``new_name``; unchanged names return immediately).

    Raises:
        ValueError: If either name is not a plain, filesystem-safe folder
            name (letters, digits, dots, underscores, spaces, hyphens).
        FileNotFoundError: If no such run folder exists.
        FileExistsError: If a run with the new name already exists.
        PermissionError: If the folder stays locked after retries (see
            DECISIONS #51 — OneDrive/Explorer transient locks).
    """
    if any(part in run_id for part in ("/", "\\", "..")) or not run_id.strip():
        raise ValueError(f"Invalid run id {run_id!r}: expected a plain folder name.")
    new_name = new_name.strip()
    if not _RUN_NAME_PATTERN.match(new_name):
        raise ValueError(
            f"Invalid name {new_name!r}: use letters, digits, dots, underscores, "
            "spaces, or hyphens (no path separators)."
        )
    out = Path(out_dir)
    folder = out / run_id
    if not folder.is_dir():
        raise FileNotFoundError(f"No recorded run named {run_id!r} in {out}.")
    if new_name == run_id:
        return run_id
    target = out / new_name
    if target.exists():
        raise FileExistsError(f"A run named {new_name!r} already exists.")
    for attempt in range(3):  # renames hit the same transient locks as deletes (#51)
        try:
            folder.rename(target)
            break
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.25 * (attempt + 1))
    summary_path = target / "summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["run_id"] = new_name
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        pass  # the folder rename is the source of truth; a stale summary id is cosmetic
    sync_index(out)
    return new_name


def read_index(out_dir: Path | str = "runs") -> list[dict[str, str]]:
    """Read the runs catalog, newest first.

    Note: the index is an append-only catalog for external analysis; it may
    still list folders the owner has since deleted or renamed by hand. The
    UI's browser therefore lists via :func:`list_runs` (folder truth)
    instead (DECISIONS #50).

    Args:
        out_dir: The runs directory.

    Returns:
        One mapping per recorded run (the ``INDEX_COLUMNS`` fields);
        empty if no runs have been recorded yet.
    """
    index_path = Path(out_dir) / "index.csv"
    if not index_path.exists():
        return []
    with index_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return list(reversed(rows))
