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

**v1 is complete** — all eight milestones landed (see
[docs/ROADMAP.md](docs/ROADMAP.md)). The interactive web app is live (curated
scenarios, plain-language tooltips, live mode-aware charts), and every run can
be **recorded and reproduced**: run folders with the exact config + raw time
series, a one-command headless CLI, and a results browser built into the app.
Under it all sits the headless platform: seven classic strategies
(cross-validated against the `axelrod` library), evolutionary dynamics, two
run modes, two matching schemes (round-robin, plus sampled `random_k` for
larger populations), and a typed event stream. Every tunable parameter is
documented in the generated reference, [docs/PARAMETERS.md](docs/PARAMETERS.md).

## Launch the app

[if .venv not running then first run ".venv\Scripts\activate" from project root folder]

```powershell
streamlit run pdsim/ui/app.py
```

Your browser opens the simulator: choose a scenario from the dropdown (each
states the question it explores and what to try changing), press **Run**, and
watch. Every parameter is editable — hover any widget for a plain-language
explanation, or read them all in one place in
[docs/PARAMETERS.md](docs/PARAMETERS.md). Same seed + same settings = the
same run, exactly.

For larger populations, switch the **Matching scheme** to `random_k`: instead
of every pair playing every generation (which grows with the square of the
population), each agent starts matches against k randomly drawn opponents.

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

## Run parameter sweeps

A **sweep** runs not one experiment but a whole family of them — one base
configuration varied along one or more axes (how many invaders you seed, a
parameter grid, a list of random seeds) — then summarises the family as a
table and a chart. Its first use is *invasion-threshold* questions: how large a
cluster of cooperators must you drop into a population of defectors before
cooperation takes over? See
[docs/explainers/M9.5-sweeps-and-invasion.md](docs/explainers/M9.5-sweeps-and-invasion.md)
for the science and worked examples.

A sweep is a **config generator**: every experiment it produces is a normal,
fully-validated config that could have been written by hand, so any single
member run reproduces on its own with `python -m pdsim.run`. The runner is
headless (there is no Sweep tab in the app yet — that is a later milestone).

### The command

```powershell
python -m pdsim.sweep <spec.yaml> [--out DIR] [--processes N] [--resume] [--quiet]
```

| Argument | Default | What it does |
|---|---|---|
| `spec` (positional) | — | Path to a sweep spec YAML file (required). |
| `--out DIR` | `sweeps` | Parent directory for the sweep's result folder. For large campaigns, point this **outside** the OneDrive-synced tree — OneDrive holding freshly written files slows a sweep and can cause transient file locks. |
| `--processes N` | CPU count − 1 (min 1) | Number of worker processes to run members in parallel. `1` runs them one at a time. |
| `--resume` | off | Continue a partial sweep: members already finished are skipped, only missing or failed ones re-run. Resume is **also automatic** whenever the sweep's folder already exists; this flag just makes the intent explicit. |
| `--quiet` | off | Suppress the per-member progress lines. |

Exit codes: **0** on success, **1** if the spec is invalid (the problems print
as plain sentences *before* any run starts — a bad sweep never half-runs),
**130** on Ctrl+C (finished members are kept; re-run with `--resume`).

Run the bundled example (finishes in a couple of minutes):

```powershell
python -m pdsim.sweep examples\sweeps\tft_invasion.yaml --out sweeps
```

### Writing a spec

A spec is a small YAML file. The bundled
[examples/sweeps/tft_invasion.yaml](examples/sweeps/tft_invasion.yaml) is fully
commented; its shape:

```yaml
name: tft_invasion            # names the result folder: sweeps/<name>/
base: path/to/base.yaml       # the base config every member starts from
# base_scenario: reciprocity_takes_over   # ...or a registered scenario, instead of `base`

composition:                  # the "three-bucket" population axis (optional)
  vary: tit_for_tat           #   the invader whose count we march upward
  counts: [2, 4, 6, 8, 10]    #   one member per count
  fixed: {}                   #   strategies held at a constant count (optional)
  fill: {always_defect: 100}  #   strategies dividing the remaining seats, by % (summing to 100)

parameters:                   # parameter grids (optional); each key is a registry key
  - key: dynamics.selection_beta
    values: [0.01, 0.1, 1.0]

seeds: [1, 2, 3, 4, 5]        # replicate each combination across these seeds (required)

metrics:                      # the numbers to compute from each finished run (required)
  - metric: final_share
    strategy: tit_for_tat
  - metric: time_to_fixation
    strategy: tit_for_tat
```

The sweep runs the **cross product** of the axes — every composition count ×
every parameter value × every seed. The full catalogue of `metrics` (final
share, fixation flag, time-to-fixation with censoring, quasi-fixation and
cooperation-collapse measures) is in the **Outcome metrics** section of
[docs/PARAMETERS.md](docs/PARAMETERS.md).

### What you get

Results land in `sweeps/<name>/`:

```
sweeps/tft_invasion/
  sweep_spec.yaml          the spec, copied verbatim (reproducibility)
  runs/                    one ordinary run folder per member (each re-runnable)
    000_tit_for_tat2_seed1/
    001_tit_for_tat2_seed2/
    ...
  sweep_status.json        progress + resume state
  sweep_summary.parquet    one row per member: its axis values and its metric values
  sweep_summary.json       run counts + the axis/metric column names
  <metric>_vs_<axis>.html  a chart of each metric against the primary axis,
                           with a band showing the spread across replicate seeds
```

Load `sweep_summary.parquet` with pandas for your own analysis, or open a
member run in the app's **Results browser** to inspect it in full detail.

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
| **M8 — done** | Read the generated parameter reference; sample k random opponents per agent instead of full round-robin | [docs/PARAMETERS.md](docs/PARAMETERS.md); the Matching section in the app |

In short: **v1 is done and everything works today** — the web app
(`streamlit run pdsim/ui/app.py`), one-command recorded runs
(`python -m pdsim.run`), the example scripts, and the Python API. Next comes
v2 (see [docs/ROADMAP.md](docs/ROADMAP.md)): growing populations, more
selection rules, n-player games, and a vectorized engine for thousands of
agents.

## Repository layout

```
pdsim/
  core/       # headless engine: game, strategies, dynamics, engine + event stream
  config/     # Parameter Registry + ExperimentConfig + Scenario Registry
  io/         # run-folder persistence
  viz/        # pure plotly chart builders
  sweep/      # sweep/search layer (python -m pdsim.sweep)
  ui/         # Streamlit app + testable helpers
  tests/      # pytest suite
  run.py      # headless CLI (python -m pdsim.run)
  bench.py    # wall-clock benchmark rider (python -m pdsim.bench)
  gendocs.py  # regenerates docs/PARAMETERS.md (python -m pdsim.gendocs)
examples/     # runnable demos (event-stream consumers) + sweeps/ example specs
docs/         # design spec, roadmap, decision log — the project's source of truth
              # (+ PARAMETERS.md reference, specs/, explainers/)
```
