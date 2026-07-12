"""Headless sweep CLI: ``python -m pdsim.sweep <spec.yaml>``.

Loads a sweep spec, validates it through the single shared path
(:func:`~pdsim.sweep.spec.sweep_validation_messages` — the same one the future
Sweep tab will use), and runs it across worker processes, writing a
``sweeps/<name>/`` folder. Validation errors print as plain sentences (never
tracebacks) and exit 1; Ctrl+C exits 130 leaving a resumable partial.

Like ``run.py``/``bench.py``/``gendocs.py`` this is orchestration tier
(DECISIONS #48): it wires together config, engine, io, and viz, but stays free
of Streamlit so M9.5b can reuse the runner.

Standing note (#51/#59): for large campaigns, point ``--out`` outside the
OneDrive-synced tree — OneDrive holding freshly written member folders slows a
sweep and makes transient locks likelier.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pdsim.sweep.runner import run_sweep
from pdsim.sweep.spec import load_sweep_spec, sweep_validation_messages


def _parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        The configured parser (kept in one place for --help and tests).
    """
    parser = argparse.ArgumentParser(
        prog="python -m pdsim.sweep",
        description="Run a family of experiments (a sweep) and summarise it (DECISIONS #59).",
    )
    parser.add_argument("spec", help="Path to a sweep spec YAML file.")
    parser.add_argument(
        "--out", default="sweeps", help="Parent directory for sweep folders (default: sweeps/)."
    )
    parser.add_argument(
        "--processes",
        type=int,
        default=None,
        help="Worker process count (default: CPU count - 1).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a partial sweep (also automatic if it exists).",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress per-member progress lines.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the sweep CLI.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``; injectable for
            tests).

    Returns:
        Process exit code: 0 on success, 1 on a bad spec, 130 on Ctrl+C.
    """
    args = _parser().parse_args(argv)
    try:
        spec = load_sweep_spec(args.spec)
    except FileNotFoundError:
        print(f"error: sweep spec not found: {args.spec}", file=sys.stderr)
        return 1
    except Exception as error:  # any structural error becomes a plain message, never a traceback
        print(f"error: could not read sweep spec: {str(error).strip(chr(39))}", file=sys.stderr)
        return 1

    messages = sweep_validation_messages(spec)
    if messages:
        for message in messages:
            print(f"error: {message}", file=sys.stderr)
        return 1

    try:
        run_sweep(
            spec,
            out_dir=Path(args.out),
            processes=args.processes,
            resume=args.resume,
            quiet=args.quiet,
        )
    except KeyboardInterrupt:
        # Finalized members stay on disk; the status file reflects reality, so
        # re-running with --resume continues where this left off (#70).
        print("\nInterrupted — finalized members kept; re-run with --resume.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
