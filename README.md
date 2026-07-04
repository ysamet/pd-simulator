# pdsim — Evolutionary Prisoner's Dilemma Simulator

A simulation platform for studying how cooperation and defection evolve in
populations of agents playing repeated Prisoner's Dilemma games.

Agents hold strategies (Tit for Tat, Grim Trigger, Pavlov, ...) and play repeated
matches against each other. After each generation, an evolutionary selection rule
reshapes the population: strategies that scored well spread, strategies that scored
poorly fade, and occasional mutation reintroduces variety. The platform is built
**novice-first** — you don't need to know game theory; every tunable parameter
carries a plain-language explanation, and the UI tooltips are generated from those
explanations.

Longer-term (v2/v3): growing populations with a score-as-energy economy, n-player
social dilemma games (Public Goods Game), reputation and punishment mechanics, and
a geographic layer for modeling real-world scenarios. See
[docs/DESIGN.md](docs/DESIGN.md) for the full model and architecture specification,
[docs/ROADMAP.md](docs/ROADMAP.md) for version scoping, and
[docs/DECISIONS.md](docs/DECISIONS.md) for the design decision log.

## Project status

v1 is under construction, milestone by milestone (see
[docs/ROADMAP.md](docs/ROADMAP.md)). **Currently completed: Milestone 2 of 7**
(skeleton + Parameter Registry + experiment configuration; core game loop —
agents, matches with noise and both length modes, round-robin matching).

## Requirements

- Python 3.11 or newer

## Setup

From the repository root:

```powershell
# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# Install the package plus dev tools (pytest, ruff)
pip install -e ".[dev]"
```

`-e` installs in "editable" mode: code changes take effect without reinstalling.

## What you can run today

With Milestone 2 complete, the core game loop works end to end — you can watch
a round-robin tournament of repeated, noisy Prisoner's Dilemma matches
(evolution itself arrives with Milestone 4):

```powershell
python examples\tournament_demo.py
```

The constants at the top of [examples/tournament_demo.py](examples/tournament_demo.py)
(seed, noise, continuation probability) are meant to be edited — try them.

The configuration layer is also fully functional:

```powershell
pytest                          # run the test suite
ruff check . ; ruff format .    # lint and format
```

You can also build, validate, save, and load experiment configurations — the same
objects every later milestone will consume:

```python
from pdsim.config import ExperimentConfig, load_config, save_config

config = ExperimentConfig.model_validate(
    {
        "seed": 7,
        "population": {
            "size": 100,
            "composition": {"tit_for_tat": 60, "always_defect": 40},
        },
    }
)
save_config(config, "my_experiment.yaml")   # everything else uses documented defaults
config = load_config("my_experiment.yaml")  # round-trips exactly
```

Validation is strict on purpose: out-of-range values, payoffs that break the
Prisoner's Dilemma ordering, a strategy mix that doesn't add up to the population
size, or a typo'd key all fail immediately with a plain-language error message.

## When will I be able to run a simulation?

Each milestone unlocks something concrete:

| After milestone | You will be able to... | How |
|---|---|---|
| **M1 — done** | Build/validate/save/load experiment configs; run the test suite | `pytest`; Python API above |
| **M2 — done** | Play matches/tournaments between (stub) strategies and inspect moves and scores | `python examples\tournament_demo.py` |
| M3 — strategy roster | Use all seven v1 strategies in those matches | Python API |
| **M4 — evolutionary dynamics** | **Run a full evolutionary simulation** (generations, selection, mutation) | Python API |
| **M5 — events + persistence** | **Run a simulation with one command from a YAML file**, with results saved to `runs/` | `python -m pdsim.run my_experiment.yaml` |
| **M6 — Streamlit UI** | Use the full **interactive web app**: parameter panel with tooltips, live charts | `streamlit run pdsim/ui/app.py` |
| M7 — polish | Read generated parameter docs; use the RandomK matcher | — |

In short: the first end-to-end simulation arrives with **Milestone 4** (from
Python), the one-command headless run with **Milestone 5**, and the point-and-click
experience with **Milestone 6**.

## Repository layout

```
pdsim/
  core/       # headless simulation engine (game, strategies, matching, dynamics)
  config/     # Parameter Registry + ExperimentConfig (YAML load/save)  ← current
  io/         # run-folder persistence (M5)
  viz/        # Plotly figure builders (M6)
  ui/         # Streamlit app (M6)
  tests/      # pytest suite
docs/         # design spec, roadmap, decision log — the project's source of truth
```
