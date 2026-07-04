r"""Quickstart demo: watch evolution reshape a population, in the terminal.

Runs the milestone-4 generation loop on a classic scenario — Tit for Tat,
Always Defect, and Random sharing one population — and prints each
generation's composition as a little text bar chart. With repeated matches
and score-driven (Fermi) selection, reciprocity should visibly take over.

Run it from the repo root **with the project's virtual environment** — that
is where ``pdsim`` and its dependencies are installed; the system Python
does not know them (``ModuleNotFoundError: No module named 'pdsim'``):

    .venv\Scripts\python examples\quickstart.py        # Windows PowerShell

or activate the venv once per terminal session, then use plain ``python``:

    .venv\Scripts\Activate.ps1
    python examples/quickstart.py

Change the numbers below and re-run — β (selection intensity), μ (mutation),
match length, and the starting mix are the interesting knobs. Same seed +
same settings = exactly the same output (reproducibility, hard rule 8).
The real front ends arrive later: milestone 5 saves runs to disk
(``python -m pdsim.run config.yaml``), milestone 6 adds the live web UI.
"""

from __future__ import annotations

import numpy as np

from pdsim.config.experiment import ExperimentConfig
from pdsim.core.dynamics import GenerationReport, PopulationDynamics

# One display letter per strategy machine name (mutation can introduce any
# roster strategy mid-run, so all seven need a letter).
LETTERS = {
    "always_cooperate": "C",
    "always_defect": "D",
    "generous_tit_for_tat": "G",
    "grim_trigger": "X",
    "pavlov": "P",
    "random": "R",
    "tit_for_tat": "T",
}


def bar(report: GenerationReport) -> str:
    """Render one generation's composition as a letter bar.

    Args:
        report: The generation to render.

    Returns:
        One character per agent (sorted by strategy name), plus counts —
        e.g. ``"DDDDDDRRRTTTTTTTTT  D:6 R:3 T:9"``.
    """
    chunks = sorted(report.composition.items())
    letters = "".join(LETTERS[name] * count for name, count in chunks)
    counts = " ".join(f"{LETTERS[name]}:{count}" for name, count in chunks)
    return f"{letters}  {counts}"


def main() -> None:
    """Run the demo scenario and print one line per generation."""
    config = ExperimentConfig.model_validate(
        {
            "seed": 42,
            "population": {
                "size": 24,
                "composition": {"tit_for_tat": 8, "always_defect": 8, "random": 8},
            },
            "match": {"length_mode": "fixed", "rounds_per_match": 20},
            "dynamics": {
                "generations": 30,
                "selection_beta": 0.02,  # gentle enough to watch the takeover
                "mutation_rate": 0.02,
            },
        }
    )
    rng = np.random.default_rng(config.seed)  # the run's single RNG (hard rule 5)
    dynamics = PopulationDynamics(config, rng)

    legend = ", ".join(f"{letter}={name}" for name, letter in sorted(LETTERS.items()))
    print(f"Legend: {legend}")
    # ASCII on purpose: Windows terminals often use a codepage (cp1252)
    # that cannot print Greek letters.
    print(
        f"Seed {config.seed}; beta={config.dynamics.selection_beta}, "
        f"mu={config.dynamics.mutation_rate}, {config.match.rounds_per_match} rounds/match\n"
    )

    reports = []
    for report in dynamics.run():
        reports.append(report)
        print(f"gen {report.index:2d}  {bar(report)}")

    first, last = reports[0], reports[-1]
    print("\nMean scores in generation 0 (why selection moved where it did):")
    for name, score in sorted(first.mean_scores.items(), key=lambda item: -item[1]):
        print(f"  {name:22s} {score:7.1f}")
    print(f"\nFinal composition after {len(reports)} generations: {last.composition}")


if __name__ == "__main__":
    main()
