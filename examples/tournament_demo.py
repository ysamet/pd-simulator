r"""Demo: Axelrod's classic round-robin tournament, live in the terminal.

Runs the curated "Classic Tournament" scenario in **tournament mode**: a
fixed cast — three agents of each of the seven strategies — plays complete
round-robin passes ("cycles") while scores simply accumulate. Nothing
evolves; this is the original 1980 computer-tournament question: which
strategy wins? Note that agents remember opponents *across* cycles, so
relationships (and grudges) keep developing all run long.

Like ``quickstart.py``, this consumes the engine's typed event stream — the
same pattern the web UI (milestone 6) uses — reacting to ``CycleFinished``
standings as they arrive.

Run it from the repo root with the project's virtual environment:

    .venv\Scripts\python examples\tournament_demo.py   # Windows PowerShell

Things to try: edit the scenario's ideas printed at the end, or change
SCENARIO in ``quickstart.py`` — both demos are just event-stream consumers.
"""

from __future__ import annotations

from pdsim.config.scenarios import get_scenario_info
from pdsim.core import engine
from pdsim.core.events import CycleFinished, RunFinished
from pdsim.core.strategies import get_strategy_info


def main() -> None:
    """Run the tournament scenario and print standings as cycles finish."""
    scenario = get_scenario_info("classic_tournament")
    config = scenario.config
    print(f"Scenario: {scenario.display_name}")
    print(f"{scenario.description}\n")
    print(
        f"{config.population.size} agents, {config.tournament_cycles} cycles, "
        f"{config.match.rounds_per_match} rounds/match, seed {config.seed}\n"
    )

    for event in engine.run(config):
        if isinstance(event, CycleFinished):
            leader = max(event.mean_scores, key=lambda name: event.mean_scores[name])
            print(
                f"cycle {event.index:2d}  leader: {leader:22s} "
                f"(mean/agent {event.mean_scores[leader]:8.1f})"
            )
        elif isinstance(event, RunFinished):
            print(f"\nFinal standings after {event.completed} cycles (mean score per agent):")
            standings = sorted(event.mean_scores.items(), key=lambda kv: -kv[1])
            for rank, (name, score) in enumerate(standings, start=1):
                display = get_strategy_info(name).display_name
                print(f"  {rank}. {display:30s} {score:9.1f}")

    print(f"\nThings to try: {scenario.things_to_try}")


if __name__ == "__main__":
    main()
