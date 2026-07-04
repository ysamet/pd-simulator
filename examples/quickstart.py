r"""Quickstart demo: watch evolution reshape a population, in the terminal.

Runs the curated "Reciprocity Takes Over" scenario from the Scenario
Registry through the engine's typed **event stream** — exactly the pattern
the web UI (milestone 6) uses: pick a scenario, call ``engine.run(config)``,
and react to the events as they arrive. Here we react to each
``GenerationFinished`` by printing a little text bar chart.

Run it from the repo root **with the project's virtual environment** — that
is where ``pdsim`` and its dependencies are installed; the system Python
does not know them (``ModuleNotFoundError: No module named 'pdsim'``):

    .venv\Scripts\python examples\quickstart.py        # Windows PowerShell

or activate the venv once per terminal session, then use plain ``python``:

    .venv\Scripts\Activate.ps1
    python examples/quickstart.py

Try other scenarios: change SCENARIO below to any name printed at startup.
Same seed + same settings = exactly the same output (hard rule 8).
"""

from __future__ import annotations

from pdsim.config.scenarios import all_scenario_names, get_scenario_info
from pdsim.core import engine
from pdsim.core.events import GenerationFinished, RunFinished

SCENARIO = "reciprocity_takes_over"

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


def bar(composition: dict[str, int]) -> str:
    """Render a population composition as a letter bar.

    Args:
        composition: Agent count per strategy machine name.

    Returns:
        One character per agent (sorted by strategy name), plus counts —
        e.g. ``"DDDDDDRRRTTTTTTTTT  D:6 R:3 T:9"``.
    """
    chunks = sorted(composition.items())
    letters = "".join(LETTERS[name] * count for name, count in chunks)
    counts = " ".join(f"{LETTERS[name]}:{count}" for name, count in chunks)
    return f"{letters}  {counts}"


def main() -> None:
    """Run the scenario and react to its event stream, one line per event."""
    scenario = get_scenario_info(SCENARIO)
    print(f"Scenario: {scenario.display_name} (of: {', '.join(all_scenario_names())})")
    print(f"{scenario.description}\n")
    print(f"Legend: {', '.join(f'{v}={k}' for k, v in sorted(LETTERS.items()))}\n")

    first_scores: dict[str, float] | None = None
    # THE pattern every consumer uses: iterate the engine's event stream and
    # dispatch on event type. The default granularity emits one
    # GenerationFinished per generation plus a final RunFinished.
    for event in engine.run(scenario.config):
        if isinstance(event, GenerationFinished):
            if first_scores is None:
                first_scores = event.mean_scores
            print(f"gen {event.index:2d}  {bar(event.composition)}")
        elif isinstance(event, RunFinished):
            print("\nMean scores in generation 0 (why selection moved where it did):")
            for name, score in sorted((first_scores or {}).items(), key=lambda kv: -kv[1]):
                print(f"  {name:22s} {score:7.1f}")
            print(f"\nFinal composition after {event.completed} generations: {event.composition}")

    print(f"\nThings to try: {scenario.things_to_try}")


if __name__ == "__main__":
    main()
