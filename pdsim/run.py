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
from pathlib import Path

from pydantic import ValidationError

from pdsim.config.experiment import ExperimentConfig, load_config
from pdsim.config.scenarios import all_scenario_names, get_scenario_info
from pdsim.core import engine
from pdsim.core.events import CycleFinished, GenerationFinished, RunFinished
from pdsim.io.results import RunRecorder
from pdsim.ui.helpers import validation_messages  # Streamlit-free by design (#38)
from pdsim.viz import charts


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

    recorder = RunRecorder(config, out_dir=Path(args.out), slug=args.slug, scenario=scenario)
    period_label = "cycle" if config.mode == "tournament" else "generation"
    try:
        for event in engine.run(config):
            recorder.add(event)
            if isinstance(event, GenerationFinished | CycleFinished) and not args.quiet:
                counts = ", ".join(f"{name}:{n}" for name, n in sorted(event.composition.items()))
                print(f"{period_label} {event.index + 1}: {counts}")
            elif isinstance(event, RunFinished):
                print(f"\nRun complete: {event.completed} {period_label}s, seed {config.seed}.")
                for row in charts.final_summary_rows(event):
                    print("  " + "  ".join(f"{key}={value}" for key, value in row.items()))
    except KeyboardInterrupt:
        # Ctrl+C is a deliberate abandonment, like the UI's Stop button:
        # no ghost folders for partial runs (DECISIONS #53).
        recorder.discard()
        print("\nInterrupted — partial run discarded.", file=sys.stderr)
        return 130  # conventional exit code for SIGINT
    folder = recorder.finalize()
    charts.export_run_charts(recorder.timeseries, folder)
    print(f"\nRecorded to {folder} (re-run exactly: python -m pdsim.run {folder / 'config.yaml'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
