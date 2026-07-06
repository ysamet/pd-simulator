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
[docs/ROADMAP.md](docs/ROADMAP.md)). **Currently completed: Milestone 7 of 8** —
the interactive web app is live (curated scenarios, plain-language tooltips,
live mode-aware charts), and every run can now be **recorded and reproduced**:
run folders with the exact config + raw time series, a one-command headless
CLI, and a results browser built into the app. Under it all sits the headless
platform: seven classic strategies (cross-validated against the `axelrod`
library), evolutionary dynamics, two run modes, and a typed event stream.
Next up: polish (M8).

## Launch the app

```powershell
streamlit run pdsim/ui/app.py
```

Your browser opens the simulator: choose a scenario from the dropdown (each
states the question it explores and what to try changing), press **Run**, and
watch. Every parameter is editable — hover any widget for a plain-language
explanation. Same seed + same settings = the same run, exactly.

## Record and browse runs

With **Record this run** enabled (it is by default), every run is saved to a
folder under `runs/` — the exact config (re-runnable), the raw time series
(parquet), a summary, and chart exports. The app's **Results browser** tab
lists all recorded runs, re-renders their charts with the same view toggles,
and can load any run's config back into the panel. Headless runs record too:

```powershell
python -m pdsim.run my_experiment.yaml          # run a config file
python -m pdsim.run --scenario classic_tournament
python -m pdsim.run runs\<some-run>\config.yaml # reproduce a recorded run
```

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

The web app above is the main event. The same simulations also run from the
terminal, streamed as typed events (the exact pattern the app consumes):

```powershell
python examples\quickstart.py        # evolution: watch reciprocity take over
python examples\tournament_demo.py   # Axelrod-style tournament: who wins?
```

Both demos run curated scenarios from the Scenario Registry
([pdsim/config/scenarios.py](pdsim/config/scenarios.py)) — five ready-made
experiments, each with a plain-language question and "things to try". Point
`SCENARIO` in [examples/quickstart.py](examples/quickstart.py) at any of them.

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
| **M2 — done** | Play matches between strategies and inspect moves and scores | Python API |
| **M3 — done** | Use all seven classic strategies (cross-validated against the `axelrod` library) | Python API |
| **M4 — done** | Run a full evolutionary simulation (generations, selection, mutation) | `python examples\quickstart.py` |
| **M5 — done** | Run **tournament or evolution** modes as an event stream; launch curated scenarios | both example scripts |
| **M6 — done** | Use the **interactive web app**: scenario picker, parameter panel with tooltips, live mode-aware charts | `streamlit run pdsim/ui/app.py` |
| **M7 — done** | Run headless from a YAML file with results saved to `runs/`; browse past runs in the UI | `python -m pdsim.run my_experiment.yaml` |
| M8 — polish | Read generated parameter docs; use the RandomK matcher | — |

In short: everything except the final polish works **today** — the web app
(`streamlit run pdsim/ui/app.py`), one-command recorded runs
(`python -m pdsim.run`), the example scripts, and the Python API.

## Repository layout

```
pdsim/
  core/       # headless engine: game, strategies, dynamics, engine + event stream
  config/     # Parameter Registry + ExperimentConfig + Scenario Registry
  io/         # run-folder persistence (M7)  ← next
  viz/        # pure plotly chart builders
  ui/         # Streamlit app + testable helpers
  tests/      # pytest suite
examples/     # runnable demos (event-stream consumers)
docs/         # design spec, roadmap, decision log — the project's source of truth
```
