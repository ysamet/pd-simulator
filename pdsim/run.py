"""Headless CLI: run an experiment from a YAML file (or scenario), record it.

Usage (with the project venv active)::

    python -m pdsim.run path/to/config.yaml
    python -m pdsim.run --scenario classic_tournament
    python -m pdsim.run my.yaml --out results/ --slug baseline --quiet

Loads the config through the same validated loader as everything else, runs
the engine, records a run folder via :mod:`pdsim.io.results`, exports chart
HTML, and prints one plain-language line per generation/cycle plus a final
summary. Exit codes: 0 on success, 1 on any failure (validation errors are
printed as the same plain sentences the UI shows, never tracebacks).

This module lives at the package top level, outside ``pdsim/io`` on purpose
(DECISIONS #48): it *orchestrates* config loading, the engine, the recorder,
and chart export — the recorder itself may never import plotting code
(hard rule 4).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from pdsim.config.experiment import ExperimentConfig, load_config
from pdsim.config.scenarios import all_scenario_names, get_scenario_info
from pdsim.core import engine
from pdsim.core.events import CycleFinished, Event, GenerationFinished, RunFinished
from pdsim.io.results import RunRecorder
from pdsim.ui.helpers import validation_messages  # Streamlit-free by design (#38)

# NOTE: `pdsim.viz.charts` is imported *lazily* inside execute_run's export
# branch (not at module top) — importing this module must not pull plotly into
# every process. The sweep runner imports execute_run into worker processes
# (DECISIONS #66), and a top-level plotly import would load it in each worker
# even though members never export charts.


def execute_run(
    config: ExperimentConfig,
    *,
    out_dir: Path | str = "runs",
    slug: str | None = None,
    scenario: str | None = None,
    export_charts: bool = True,
    on_period: Callable[[Event], None] | None = None,
    append_index: bool = True,
    folder_name: str | None = None,
) -> Path:
    """Run one experiment through the recorder and finalize its folder.

    The shared run→record→finalize orchestration behind both the CLI
    (:func:`main`) and the sweep runner (DECISIONS #66): the CLI passes a
    per-period printer and exports charts; sweep workers pass ``on_period=None``,
    ``export_charts=False`` (member chart HTML is waste, #48), and
    ``append_index=False`` (parallel members must not contend on the shared
    ``runs/index.csv``, #47e).

    Args:
        config: The validated experiment to run and record.
        out_dir: Directory for the run folder.
        slug: Folder-name suffix (defaults to scenario or run mode).
        scenario: Scenario name for the index/summary, if any.
        export_charts: Write chart HTML into the folder after finalizing.
        on_period: Optional callback invoked on each ``GenerationFinished`` /
            ``CycleFinished`` event (the CLI's progress printer).
        append_index: Append a row to ``runs/index.csv`` on finalize.
        folder_name: Exact run-folder name (collision-suffixed), passed by
            sweep members for index-sorted folders (DECISIONS #66).

    Returns:
        The completed run folder.

    Raises:
        KeyboardInterrupt: Re-raised after discarding the partial recording,
            so the caller chooses the exit code (the CLI returns 130 — #53).
    """
    recorder = RunRecorder(
        config,
        out_dir=out_dir,
        slug=slug,
        scenario=scenario,
        append_index=append_index,
        folder_name=folder_name,
    )
    try:
        for event in engine.run(config):
            recorder.add(event)
            if on_period is not None and isinstance(event, GenerationFinished | CycleFinished):
                on_period(event)
    except KeyboardInterrupt:
        recorder.discard()
        raise
    folder = recorder.finalize()
    if export_charts:
        # Lazy import (see the module-level note): keeps plotly out of
        # plotting-free consumers such as the sweep workers.
        from pdsim.ui.economy_helpers import chart_carrying_capacity
        from pdsim.viz import charts

        charts.export_run_charts(
            recorder.timeseries, folder, carrying_capacity=chart_carrying_capacity(config)
        )
    return folder


def _parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        The configured parser (kept in one place for --help and tests).
    """
    parser = argparse.ArgumentParser(
        prog="python -m pdsim.run",
        description="Run a pdsim experiment headlessly and record it to a run folder.",
    )
    parser.add_argument(
        "config", nargs="?", default=None, help="Path to an experiment config YAML file."
    )
    parser.add_argument(
        "--scenario",
        default=None,
        help="Run a registered scenario by machine name instead of a YAML file.",
    )
    parser.add_argument("--out", default="runs", help="Directory for run folders (default: runs/).")
    parser.add_argument(
        "--slug", default=None, help="Folder-name suffix (default: scenario or run mode)."
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress per-period progress lines.")
    return parser


def _load(args: argparse.Namespace) -> tuple[ExperimentConfig, str | None]:
    """Resolve the config to run from the CLI arguments.

    Args:
        args: Parsed CLI arguments.

    Returns:
        The validated config and the scenario name (``None`` for YAML runs).

    Raises:
        SystemExit: Via the caller — this function raises the underlying
            errors (ValueError/ValidationError/KeyError/FileNotFoundError)
            for :func:`main` to render.
    """
    if (args.config is None) == (args.scenario is None):
        raise ValueError(
            "Provide exactly one of: a config YAML path, or --scenario NAME. "
            f"Registered scenarios: {', '.join(all_scenario_names())}."
        )
    if args.scenario is not None:
        return get_scenario_info(args.scenario).config, args.scenario
    return load_config(args.config), None


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``; injectable for
            tests).

    Returns:
        Process exit code: 0 on success, 1 on failure.
    """
    args = _parser().parse_args(argv)
    try:
        config, scenario = _load(args)
    except ValidationError as error:
        for message in validation_messages(error):
            print(f"error: {message}", file=sys.stderr)
        return 1
    except (ValueError, KeyError, FileNotFoundError, OSError) as error:
        # KeyError carries quotes around its message; strip them for humans.
        print(f"error: {str(error).strip(chr(39))}", file=sys.stderr)
        return 1

    period_label = "cycle" if config.mode == "tournament" else "generation"
    # Capture the final period event so the standings table can be printed
    # without re-reading the folder — execute_run consumes the stream, but the
    # last GenerationFinished/CycleFinished carries the final figures the
    # RunFinished mirrors (engine.py builds RunFinished from exactly this).
    last: list[GenerationFinished | CycleFinished] = []

    def on_period(event: Event) -> None:
        """Record and (unless quiet) print each finished generation/cycle."""
        assert isinstance(event, GenerationFinished | CycleFinished)
        last[:] = [event]
        if not args.quiet:
            counts = ", ".join(f"{name}:{n}" for name, n in sorted(event.composition.items()))
            print(f"{period_label} {event.index + 1}: {counts}")

    try:
        folder = execute_run(
            config,
            out_dir=Path(args.out),
            slug=args.slug,
            scenario=scenario,
            export_charts=True,
            on_period=on_period,
        )
    except KeyboardInterrupt:
        # Ctrl+C is a deliberate abandonment, like the UI's Stop button:
        # execute_run already discarded the partial folder (DECISIONS #53).
        print("\nInterrupted — partial run discarded.", file=sys.stderr)
        return 130  # conventional exit code for SIGINT
    # The true count comes from the last period event, not the config: an
    # energy-economy run can end EARLY at extinction (M10a), and under
    # imitation/tournament the two are equal anyway.
    completed = last[0].index + 1 if last else 0
    extinct = config.mode != "tournament" and completed < config.dynamics.generations
    print(
        f"\nRun complete: {completed} {period_label}s, seed {config.seed}."
        + (" Population extinct." if extinct else "")
    )
    if last:
        from pdsim.viz import charts  # lazy: keep plotting out of importers

        # The standings table prints the LAST period that played — for an
        # extinct run that is the final population as it played, which is
        # more informative on a console than the empty final composition.
        final = last[0]
        run_finished = RunFinished(
            mode=config.mode,
            completed=completed,
            composition=final.composition,
            mean_scores=final.mean_scores,
            total_scores=getattr(final, "total_scores", None),
        )
        for row in charts.final_summary_rows(run_finished):
            print("  " + "  ".join(f"{key}={value}" for key, value in row.items()))
    print(f"Recorded to {folder} (re-run exactly: python -m pdsim.run {folder / 'config.yaml'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
