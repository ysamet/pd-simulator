"""Benchmark rider: measure wall-clock seconds per generation (DECISIONS #58).

Usage (with the project venv active)::

    python -m pdsim.bench                       # default N x matcher grid
    python -m pdsim.bench --sizes 50,100 --generations 3
    python -m pdsim.bench --out bench.csv       # also write CSV

Purpose: make the vectorized-backend trigger EMPIRICAL. The v2 plan
deliberately does not schedule vectorization (DECISIONS #58) — it lands when
data shows the sampling matchers cannot buy the needed scale. This script
produces that data: median wall-clock seconds per generation over a grid of
population sizes and matchers, printed as a table (and optionally CSV via
``--out``; there is no default output file — results are environment-specific
and never committed).

Grid defaults: N in {50, 100, 200, 400} x matcher in {round_robin,
random_k(k=5)}, evolution mode, fixed 50-round matches, the default roster
mix (even split), 3 generations per cell with the first discarded as warmup.

Like ``run.py`` and ``gendocs.py``, this module lives at the package top
level (DECISIONS #48) and imports config/core only — no UI, no plotting
(hard rule 4).
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from pathlib import Path

import numpy as np

from pdsim.config.experiment import ExperimentConfig
from pdsim.core.dynamics import EconomyDynamics, PopulationDynamics
from pdsim.core.strategies import all_strategy_names

DEFAULT_SIZES = (50, 100, 200, 400)
"""Population sizes benchmarked by default."""

DEFAULT_MATCHERS = ("round_robin", "random_k")
"""Matchers benchmarked by default."""


def _even_composition(size: int) -> dict[str, int]:
    """Split a population evenly across the registered roster.

    The same neutral mix the UI's "Custom" start uses (DECISIONS #40),
    re-implemented here because this module may not import the UI layer.

    Args:
        size: Total number of agents to distribute.

    Returns:
        Strategy machine name -> count (zero-count entries dropped, since
        configs require every listed strategy to have at least one agent).
    """
    names = all_strategy_names()
    base, remainder = divmod(size, len(names))
    mix = {name: base + (1 if i < remainder else 0) for i, name in enumerate(names)}
    return {name: count for name, count in mix.items() if count > 0}


def _cell_config(
    size: int,
    matcher: str,
    k: int,
    rounds: int,
    generations: int,
    seed: int,
    reproduction_mode: str = "imitation",
) -> ExperimentConfig:
    """Build the experiment config for one benchmark grid cell.

    Args:
        size: Population size N.
        matcher: Matching scheme machine name.
        k: Opponents per agent (used only under random_k).
        rounds: Fixed rounds per match.
        generations: Generations to run (timed; first is warmup).
        seed: Random seed (identical across cells — timing, not science).
        reproduction_mode: ``"imitation"`` (the v1 loop) or
            ``"energy_economy"`` (M10a). The economy cell is tuned to keep N
            CONSTANT — an unreachable breeding bar and a zero living cost —
            so the timing isolates the economy bookkeeping (ledger,
            boundary, snapshots, persistent histories) at the same N as the
            imitation cell instead of timing a drifting population.

    Returns:
        A validated evolution-mode config.
    """
    dynamics: dict[str, object] = {"generations": generations}
    if reproduction_mode == "energy_economy":
        dynamics.update(
            {
                "reproduction_mode": "energy_economy",
                "reproduction_threshold": 1e12,  # nobody breeds
                "offspring_stake": 0.0,
                "basic_living_cost": 0.0,  # nobody starves
                "carrying_capacity": max(size, 200),
            }
        )
    return ExperimentConfig.model_validate(
        {
            "seed": seed,
            "population": {"size": size, "composition": _even_composition(size)},
            "matching": {"matcher": matcher, "opponents_per_agent": k},
            "match": {"length_mode": "fixed", "rounds_per_match": rounds},
            "dynamics": dynamics,
        }
    )


def time_cell(config: ExperimentConfig, generations: int) -> float:
    """Run one grid cell and return its median seconds per generation.

    The first generation is discarded as warmup (imports, allocator, CPU
    caches all settle during it); the median of the rest is robust against
    a stray slow generation (antivirus, OneDrive, scheduler noise).

    Args:
        config: The cell's experiment config (its ``reproduction_mode``
            picks the loop class, mirroring the engine's dispatch — M10a).
        generations: Total generations to run (>= 2 so at least one
            post-warmup timing exists; enforced by the CLI).

    Returns:
        Median wall-clock seconds per post-warmup generation.
    """
    dynamics: PopulationDynamics | EconomyDynamics
    if config.dynamics.reproduction_mode == "energy_economy":
        dynamics = EconomyDynamics(config, np.random.default_rng(config.seed))
    else:
        dynamics = PopulationDynamics(config, np.random.default_rng(config.seed))
    timings: list[float] = []
    for _ in range(generations):
        start = time.perf_counter()  # monotonic, high-resolution clock
        dynamics.step()
        timings.append(time.perf_counter() - start)
    return statistics.median(timings[1:])


def _parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        The configured parser (kept in one place for --help and tests).
    """
    parser = argparse.ArgumentParser(
        prog="python -m pdsim.bench",
        description=(
            "Benchmark wall-clock seconds per generation across an N x matcher "
            "grid — the data source for the vectorization trigger (DECISIONS #58)."
        ),
    )
    parser.add_argument(
        "--sizes",
        default=",".join(str(n) for n in DEFAULT_SIZES),
        help=f"Comma-separated population sizes (default: {','.join(map(str, DEFAULT_SIZES))}).",
    )
    parser.add_argument(
        "--matchers",
        default=",".join(DEFAULT_MATCHERS),
        help=f"Comma-separated matcher names (default: {','.join(DEFAULT_MATCHERS)}).",
    )
    parser.add_argument(
        "--k", type=int, default=5, help="Opponents per agent under random_k (default: 5)."
    )
    parser.add_argument(
        "--rounds", type=int, default=50, help="Fixed rounds per match (default: 50)."
    )
    parser.add_argument(
        "--generations",
        type=int,
        default=3,
        help="Generations per cell, first discarded as warmup (default: 3, minimum: 2).",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42).")
    parser.add_argument(
        "--reproduction-mode",
        choices=("imitation", "energy_economy"),
        default="imitation",
        help=(
            "Which loop to time (default: imitation). 'energy_economy' times the "
            "M10a boundary at CONSTANT N (no births, no deaths), isolating the "
            "economy bookkeeping overhead."
        ),
    )
    parser.add_argument(
        "--out", default=None, help="Optional CSV output path (no default — never committed)."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the benchmark grid and report the results.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``; injectable for
            tests).

    Returns:
        Process exit code: 0 on success, 1 on bad arguments.
    """
    args = _parser().parse_args(argv)
    try:
        sizes = [int(part) for part in args.sizes.split(",") if part.strip()]
        matchers = [part.strip() for part in args.matchers.split(",") if part.strip()]
    except ValueError:
        print("error: --sizes must be comma-separated whole numbers.", file=sys.stderr)
        return 1
    if args.generations < 2:
        print("error: --generations must be at least 2 (the first is warmup).", file=sys.stderr)
        return 1

    rows: list[dict[str, object]] = []
    print(f"{'N':>6}  {'matcher':<12}  {'s/generation':>12}")
    for size in sizes:
        for matcher in matchers:
            try:
                config = _cell_config(
                    size,
                    matcher,
                    args.k,
                    args.rounds,
                    args.generations,
                    args.seed,
                    reproduction_mode=args.reproduction_mode,
                )
            except ValueError as error:
                print(f"error: N={size}, {matcher}: {error}", file=sys.stderr)
                return 1
            seconds = time_cell(config, args.generations)
            rows.append({"n": size, "matcher": matcher, "seconds_per_generation": seconds})
            print(f"{size:>6}  {matcher:<12}  {seconds:>12.4f}")

    if args.out is not None:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["n", "matcher", "seconds_per_generation"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
