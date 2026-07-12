"""The parallel sweep runner: expand, run members in parallel, summarise.

Given a validated :class:`~pdsim.sweep.spec.SweepSpec`, the runner writes a
``sweeps/<name>/`` folder holding the spec, one recorded run folder per member,
a single-writer progress/resume file, a wide summary table, and a
metric-vs-axis chart per metric (DECISIONS #70).

Parallelism (companion §2, performance dimension 3 of DESIGN §3.1): whole runs
are independent, so members run across processes at once. The worker is a
top-level, picklable function (Windows uses *spawn*, which re-imports and
pickles — no closures, no lambdas; the #51 environment note), and a failing
member is isolated — it never kills the sweep (#59). The **parent** is the sole
writer of ``sweep_status.json``, so there is no concurrency on it.

Resume (#70): if ``sweeps/<name>/`` already exists, members already finalized
are skipped and only missing or failed indices re-run — important because this
project lives under OneDrive, where mid-sweep interruption is likelier (#51).
"""

from __future__ import annotations

import json
import multiprocessing
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from pdsim.config.experiment import ExperimentConfig
from pdsim.io.results import load_run
from pdsim.run import execute_run
from pdsim.sweep.metrics import get_metric
from pdsim.sweep.spec import MemberPlan, SweepSpec, expand, load_sweep_spec, save_sweep_spec

SUMMARY_SCHEMA_VERSION = 1
"""Bump on any breaking change to the sweep-summary layout (the #47 guard, 4th use)."""


@dataclass(frozen=True, slots=True)
class _MemberResult:
    """One worker's outcome (the picklable worker return, unpacked)."""

    run_index: int
    status: str  # "done" | "failed"
    folder: str | None
    error: str | None
    duration: float


def _run_member(job: dict[str, Any]) -> _MemberResult:
    """Run one sweep member in a worker process (top-level = picklable).

    Receives the member's config as a plain dict and re-validates it here, so
    nothing but picklable primitives crosses the process boundary (spawn-safe).
    Any exception is caught and returned as a ``"failed"`` result — a bad
    member must never kill the sweep (failure isolation, #59).

    Args:
        job: ``{run_index, config (dict), out_dir, folder_name}``.

    Returns:
        The member's :class:`_MemberResult`.
    """
    start = time.monotonic()
    run_index = int(job["run_index"])
    try:
        config = ExperimentConfig.model_validate(job["config"])
        folder = execute_run(
            config,
            out_dir=job["out_dir"],
            export_charts=False,
            on_period=None,
            append_index=False,
            folder_name=job["folder_name"],
        )
        return _MemberResult(run_index, "done", folder.name, None, time.monotonic() - start)
    except Exception as error:  # failure isolation: a bad member must not kill the sweep
        return _MemberResult(run_index, "failed", None, str(error)[:200], time.monotonic() - start)


def _axis_columns(spec: SweepSpec) -> list[str]:
    """Return the summary table's axis columns, in order.

    Args:
        spec: The sweep spec.

    Returns:
        The composition vary strategy (if any) followed by each parameter
        axis's registry key. ``seed`` is a base column, not listed here.
    """
    columns: list[str] = []
    if spec.composition is not None:
        columns.append(spec.composition.vary)
    columns.extend(axis.key for axis in spec.parameters)
    return columns


def _primary_axis(spec: SweepSpec) -> str:
    """Return the axis to chart metrics against (composition, else first param).

    Args:
        spec: The sweep spec.

    Returns:
        The composition vary strategy if present, else the first parameter
        key, else ``"seed"``.
    """
    if spec.composition is not None:
        return spec.composition.vary
    if spec.parameters:
        return spec.parameters[0].key
    return "seed"


def _load_status(folder: Path) -> dict[str, Any]:
    """Read a sweep's status file, or an empty skeleton if absent.

    Args:
        folder: The sweep folder.

    Returns:
        The parsed status dict (``{}``-safe ``per_index``).
    """
    path = folder / "sweep_status.json"
    if not path.is_file():
        return {"per_index": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"per_index": {}}


def _write_status(folder: Path, status: dict[str, Any]) -> None:
    """Write the status file (parent is the sole writer — no concurrency).

    Args:
        folder: The sweep folder.
        status: The status dict to persist.
    """
    status["updated_at"] = datetime.now().isoformat(timespec="seconds")
    (folder / "sweep_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")


def _done_indices(status: dict[str, Any], runs_dir: Path) -> set[int]:
    """Return the run indices already finalized (for resume).

    A member counts as done only if its recorded folder still exists — a
    status entry whose folder was hand-deleted is re-run (#70).

    Args:
        status: The loaded status dict.
        runs_dir: The sweep's ``runs/`` directory.

    Returns:
        The set of ``run_index`` values to skip.
    """
    done: set[int] = set()
    for key, entry in status.get("per_index", {}).items():
        if entry.get("status") == "done" and entry.get("folder"):
            if (runs_dir / entry["folder"]).is_dir():
                done.add(int(key))
    return done


def run_sweep(
    spec: SweepSpec,
    *,
    out_dir: Path | str = "sweeps",
    processes: int | None = None,
    resume: bool = False,
    quiet: bool = False,
) -> Path:
    """Run a full sweep and write its ``sweeps/<name>/`` folder.

    Args:
        spec: The validated sweep spec (call
            :func:`~pdsim.sweep.spec.sweep_validation_messages` first).
        out_dir: Parent directory for sweep folders (default ``sweeps/``).
        processes: Worker process count (default ``cpu_count() - 1``, min 1).
            ``1`` runs members serially in-process (fast, deterministic — used
            by tests); higher counts use a ``multiprocessing.Pool``.
        resume: Explicit resume intent; resume is also automatic when the
            sweep folder already exists.
        quiet: Suppress the per-member progress lines.

    Returns:
        The sweep folder.
    """
    plans = expand(spec)  # full validation of every member, before anything runs
    folder = Path(out_dir) / spec.name
    resuming = resume or folder.exists()
    folder.mkdir(parents=True, exist_ok=True)
    runs_dir = folder / "runs"
    runs_dir.mkdir(exist_ok=True)

    # Copy the spec verbatim up front (write-ahead reproducibility, the #47(d)
    # analog) — but never clobber the original on a resume.
    spec_path = folder / "sweep_spec.yaml"
    if not spec_path.is_file():
        save_sweep_spec(spec, spec_path)

    status = _load_status(folder) if resuming else {"per_index": {}}
    skip = _done_indices(status, runs_dir) if resuming else set()
    todo = [plan for plan in plans if plan.run_index not in skip]

    status.update(
        {
            "name": spec.name,
            "total": len(plans),
            "started_at": status.get("started_at", datetime.now().isoformat(timespec="seconds")),
        }
    )
    if skip and not quiet:
        print(f"Resuming {spec.name}: {len(skip)} of {len(plans)} members already done.")

    processes = _process_count(processes)
    jobs = [
        {
            "run_index": plan.run_index,
            "config": plan.config.model_dump(mode="json"),
            "out_dir": str(runs_dir),
            "folder_name": f"{plan.run_index:03d}_{plan.slug}",
        }
        for plan in todo
    ]

    def record(result: _MemberResult) -> None:
        """Fold one member result into the status file and print a line."""
        status["per_index"][str(result.run_index)] = {
            "status": result.status,
            "folder": result.folder,
            "error": result.error,
        }
        finished = len(
            [e for e in status["per_index"].values() if e["status"] in ("done", "failed")]
        )
        status["completed"] = len(
            [e for e in status["per_index"].values() if e["status"] == "done"]
        )
        status["failed"] = len([e for e in status["per_index"].values() if e["status"] == "failed"])
        status["running"] = len(plans) - finished
        _write_status(folder, status)
        if not quiet:
            axes = _plan_by_index[result.run_index].axis_values
            axis_text = " ".join(f"{key}={value}" for key, value in axes.items())
            if result.status == "done":
                print(f"[{finished}/{len(plans)}] {axis_text} -> ok {result.duration:.1f}s")
            else:
                print(f"[{finished}/{len(plans)}] {axis_text} -> FAILED: {result.error}")

    _plan_by_index = {plan.run_index: plan for plan in plans}
    if todo:
        if processes == 1:
            # Serial path: identical worker, no Pool — deterministic and fast
            # for small sweeps and tests (the Pool path is the same worker).
            for job in jobs:
                record(_run_member(job))
        else:
            # multiprocessing.Pool.imap_unordered (new concept): hands each job
            # to a worker process and yields results AS THEY FINISH (not in
            # submission order) — so the parent updates status the moment any
            # member completes, and slow members don't hold up fast ones.
            with multiprocessing.Pool(processes=processes) as pool:
                for result in pool.imap_unordered(_run_member, jobs):
                    record(result)

    summary_frame = _build_summary(spec, plans, status, runs_dir)
    _write_summary(spec, folder, summary_frame, status)
    _export_charts(spec, folder, summary_frame)
    if not quiet:
        print(
            f"\nSweep complete: {status.get('completed', 0)}/{len(plans)} members "
            f"({status.get('failed', 0)} failed). Results in {folder}."
        )
    return folder


def _process_count(processes: int | None) -> int:
    """Resolve the worker count (default cpu_count - 1, floor 1).

    Args:
        processes: The requested count, or ``None`` for the default.

    Returns:
        A worker count of at least 1.
    """
    if processes is not None:
        return max(1, processes)
    return max(1, (multiprocessing.cpu_count() or 2) - 1)


def _build_summary(
    spec: SweepSpec, plans: list[MemberPlan], status: dict[str, Any], runs_dir: Path
) -> pd.DataFrame:
    """Build the wide summary table: one row per member, axes + metrics.

    Metrics are computed by the parent, by loading each successful member and
    running the spec's metrics over it (pure post-processing, #69). Rows are
    sorted by ``run_index`` (never completion order).

    Args:
        spec: The sweep spec.
        plans: Every member plan.
        status: The final status dict.
        runs_dir: The sweep's ``runs/`` directory.

    Returns:
        The summary DataFrame with a stable column order.
    """
    axis_columns = _axis_columns(spec)
    metric_columns = [ref.label() for ref in spec.metrics]
    rows: list[dict[str, Any]] = []
    for plan in plans:
        entry = status["per_index"].get(str(plan.run_index), {})
        member_status = entry.get("status", "missing")
        folder_name = entry.get("folder")
        row: dict[str, Any] = {
            "run_index": plan.run_index,
            "run_id": folder_name,
            "status": member_status,
            "seed": plan.axis_values["seed"],
        }
        for column in axis_columns:
            row[column] = plan.axis_values.get(column)
        metrics = _compute_metrics(spec, runs_dir / folder_name) if folder_name else None
        for column in metric_columns:
            row[column] = metrics.get(column) if metrics else None
        rows.append(row)
    ordered_columns = ["run_index", "run_id", "status", "seed", *axis_columns, *metric_columns]
    return pd.DataFrame(rows, columns=ordered_columns)


def _compute_metrics(spec: SweepSpec, member_folder: Path) -> dict[str, Any]:
    """Compute the spec's metrics for one finalized member run.

    Args:
        spec: The sweep spec.
        member_folder: The member's run folder.

    Returns:
        Metric label -> value; a metric that raises yields ``None`` for that
        column (a failed metric never sinks the whole summary).
    """
    try:
        run = load_run(member_folder)
    except (OSError, ValueError):
        return {}
    values: dict[str, Any] = {}
    for ref in spec.metrics:
        try:
            values[ref.label()] = get_metric(ref.metric).compute(run, **ref.params())
        except Exception:  # one bad metric must not sink the whole summary row
            values[ref.label()] = None
    return values


def _write_summary(
    spec: SweepSpec, folder: Path, summary_frame: pd.DataFrame, status: dict[str, Any]
) -> None:
    """Write ``sweep_summary.parquet`` and ``sweep_summary.json``.

    Args:
        spec: The sweep spec.
        folder: The sweep folder.
        summary_frame: The built summary table.
        status: The final status dict (for the completed/failed counts).
    """
    summary_frame.to_parquet(folder / "sweep_summary.parquet", index=False)
    metadata = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "name": spec.name,
        "spec": spec.model_dump(mode="json"),
        "total": int(status.get("total", len(summary_frame))),
        "completed": int(status.get("completed", 0)),
        "failed": int(status.get("failed", 0)),
        "axis_columns": _axis_columns(spec),
        "metric_columns": [ref.label() for ref in spec.metrics],
    }
    (folder / "sweep_summary.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def _export_charts(spec: SweepSpec, folder: Path, summary_frame: pd.DataFrame) -> None:
    """Write one metric-vs-primary-axis chart HTML per metric (#71).

    Plotting stays in ``viz`` and is imported lazily here (orchestration may
    import viz; the sweep persistence code must not — hard rule 4).

    Args:
        spec: The sweep spec.
        folder: The sweep folder.
        summary_frame: The summary table.
    """
    from pdsim.viz import charts

    axis = _primary_axis(spec)
    metric_columns = [ref.label() for ref in spec.metrics]
    labels = {ref.label(): get_metric(ref.metric).display_name for ref in spec.metrics}
    charts.export_sweep_charts(
        summary_frame, folder, axes=[axis], metrics=metric_columns, metric_labels=labels
    )


def run_sweep_file(
    path: Path | str,
    *,
    out_dir: Path | str = "sweeps",
    processes: int | None = None,
    resume: bool = False,
    quiet: bool = False,
) -> Path:
    """Load a spec from a YAML file and run it.

    Convenience wrapper for the CLI and tests.

    Args:
        path: Path to the sweep spec YAML.
        out_dir: Parent directory for sweep folders.
        processes: Worker process count.
        resume: Explicit resume intent.
        quiet: Suppress per-member progress lines.

    Returns:
        The sweep folder.
    """
    return run_sweep(
        load_sweep_spec(path), out_dir=out_dir, processes=processes, resume=resume, quiet=quiet
    )
