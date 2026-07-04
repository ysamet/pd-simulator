# DESIGN.md — Evolutionary Prisoner's Dilemma Simulation Platform

> Model and architecture specification. This is the authoritative reference for what the
> platform is and how it is structured. Changes to the model design are made here first,
> with rationale logged in `DECISIONS.md`. See `ROADMAP.md` for version scoping.

## 1. Vision

A simulation platform for studying how success accumulates in populations of agents
playing repeated Prisoner's Dilemma (and, later, n-player social dilemma) games under
evolutionary selection. Long-term goal: model real-world societal and geopolitical
conflict dynamics (reputation, sanctions, alliances, geography) within this framework.

Guiding principles:

1. **Every model dimension is a parameter.** All mechanisms discussed in design are
   eventually tunable from the GUI. v1 implements a subset, but every subsystem is
   built behind an interface so later options plug in without surgery.
2. **Headless engine, thin UI.** The simulation engine has zero UI dependencies. The UI
   only (a) builds an `ExperimentConfig` and (b) renders result streams. The UI layer is
   replaceable (Streamlit in v1; richer dashboard later).
3. **Novice-first explanations.** The user is not assumed to be a game-theory expert.
   Every parameter and every strategy has a plain-language explanation, maintained in a
   single Parameter Registry from which UI tooltips and documentation are generated.
4. **Reproducibility.** Every run persists its full config + RNG seed + results. Any
   experiment can be exactly re-run and compared.

## 2. Core model (v1)

### 2.1 Game: pairwise repeated Prisoner's Dilemma

- Two actions per round: **C** (cooperate) / **D** (defect).
- Payoff matrix (tunable; standard defaults): T=5 (temptation), R=3 (reward),
  P=1 (punishment), S=0 (sucker).
- Validation toggles: enforce `T > R > P > S` (PD ordering) and `2R > T + S`
  (mutual cooperation beats alternating exploitation). Both ON by default; user may
  relax them to explore neighboring games (e.g., Chicken, Stag Hunt orderings).
- The engine treats the game behind a `Game` interface (participants + actions →
  payoffs) so n-player games (Public Goods Game and variants) are v2 drop-ins.

### 2.2 Population and memory

- Population of N agents; each agent holds one strategy instance.
- **Memory:** each agent has access to its full per-opponent interaction history
  (multi-player repeated environment → built-in direct reciprocity/reputation between
  pairs). An optional `memory_depth` constraint caps how far back strategies may look.
- Agents have stable identities across a generation, so an agent meeting a repeat
  opponent can recognize it (this is what makes per-opponent memory meaningful).

### 2.3 Strategy roster (v1)

All strategies implement the `Strategy` ABC. Initial set:

| Strategy | Summary |
|---|---|
| AlwaysCooperate | Cooperates unconditionally. |
| AlwaysDefect | Defects unconditionally. |
| Random(p) | Cooperates with probability p each round. |
| TitForTat | Cooperates first; then mirrors opponent's previous move. |
| GenerousTitForTat(g) | TFT, but forgives a defection with probability g. |
| GrimTrigger | Cooperates until first opponent defection; defects forever after. |
| Pavlov (Win-Stay-Lose-Shift) | Repeats last action if it paid well (T or R); switches otherwise. |

Each strategy carries: machine name, display name, novice-friendly description,
parameter definitions (registered in the Parameter Registry), and literature notes.
This metadata lives in the **Strategy Registry**
(`pdsim/core/strategies/registry.py`): one `StrategyInfo` declaration per strategy
module, auto-discovered by importing the package (see DECISIONS #25). The v1
machine names — the identifiers configs use — are `always_cooperate`,
`always_defect`, `random`, `tit_for_tat`, `generous_tit_for_tat`, `grim_trigger`,
`pavlov`. Strategy parameters use registry keys `strategy.<machine_name>.<param>`;
defaults: Random p = 0.5, GTFT g = 1/3 (see DECISIONS #26, including Pavlov's
moves-only "win = opponent cooperated" derivation).

Per-run parameter overrides live in the optional top-level `strategy_params`
config section, mapping machine name → `{parameter: value}` — one parameter set
per strategy per run, overriding the registry defaults (DECISIONS #30).
Heterogeneous same-strategy variants in one population are a v2 concern
(parameter-perturbation mutation). A strategy may appear in `strategy_params`
without being in the composition: mutation can still introduce it mid-run, and
its configured parameters then apply.

### 2.4 Matching (who plays whom)

Behind a `Matcher` interface:

- **RoundRobin** (v1 default): every pair plays one match per generation. O(N²) matches.
- **RandomK** (v1 if cheap, else v1.5): each agent plays k randomly drawn opponents.
- **SpatialKernel** (future): agents have positions; interaction probability decays
  with distance. See §6.3.

### 2.5 Match length

Per-match round count, two modes (both in v1, UI-selectable):

- **Fixed**: exactly `rounds_per_match` rounds.
- **Continuation probability**: after each round the match continues with probability
  `w` (expected length 1/(1−w)). Theoretically important: a known fixed horizon invites
  end-game defection by backward induction; probabilistic continuation models "the
  shadow of the future."

### 2.6 Noise

- **Execution error ε** (v1): with probability ε an agent's played action flips from
  its intended action. The classic robustness test separating brittle strategies
  (GrimTrigger) from forgiving ones (GTFT, Pavlov).
- **Perception error** (future option): an agent misreads the opponent's action.

### 2.7 Selection and reproduction (v1 dynamics package)

- **Fixed population size** N; synchronous generations (all matches played → scores
  computed → entire next generation selected at once).
- **Selection rule** behind a `SelectionRule` interface. v1 ships **Fermi
  (pairwise-comparison)**: for each next-generation slot, sample agents A (incumbent)
  and B (model); A adopts B's strategy with probability `1 / (1 + exp(-β (s_B − s_A)))`.
  All slots sample the current generation's scores and apply simultaneously; exact
  sampling and RNG-order semantics in DECISIONS #32.
  - **β = selection intensity**: 0 → pure drift (score irrelevant);
    large → near-deterministic copying of higher scorers. First-class experimental knob.
- **Mutation**: with probability **μ**, a newly produced agent receives a uniformly
  random strategy from the enabled roster instead of the copied one (strategy-switch
  mutation). In v1 the enabled roster is the **full registered roster** — mutation may
  introduce strategies absent from the initial composition; mutants are constructed
  with the run's `strategy_params` (DECISIONS #30/#32). μ=0 ⇒ perfect cloning.
  Parameter-perturbation mutation (Gaussian noise on continuous strategy parameters,
  enabling true strategy evolution) is a v2 mode behind the same reproduction interface.
- **Score accounting**: scores reset each generation (v1), and per-opponent histories
  reset with them — selection changes who your neighbors are, so remembered
  relationships would be stale (DECISIONS #31). Cumulative / sliding-window /
  exponentially discounted accounting are future `ScoreAccounting` options.
- Additional selection rules planned behind the same interface: fitness-proportional
  (roulette), tournament(k), truncation/elitist, threshold-based cloning (see §6.1).

### 2.8 Randomness

Single seeded RNG (numpy `Generator`) injected everywhere; seed recorded in every
run's saved config. No module may create its own unseeded RNG.

### 2.9 Run modes

Every experiment runs in one of two modes (registry: `run.mode`; DECISIONS #34):

- **evolution** (default): the full evolutionary loop of §2.7 — synchronous
  generations, selection, mutation, per-generation resets.
- **tournament**: Axelrod-style — a fixed cast of agents keeps its initial
  strategies for the entire run. Each **cycle** (`run.tournament_cycles`) is one
  complete matcher pass (round-robin: every pair plays one match). There is no
  selection, no mutation, no generation boundary, and no reset: scores and
  per-opponent histories accumulate across the ENTIRE run. With respect to the
  history-view semantics (DECISIONS #22/#31), a tournament behaves as **one long
  generation** — `round_number` is cumulative across all cycles. This is the
  intended direct-reciprocity behavior, not an accident: GrimTrigger stays grim
  in cycle 2 about a betrayal from cycle 1. RNG draw order: the match-phase
  order of DECISIONS #23, repeated per cycle — no selection or mutation phases.

Selection, mutation, and generation-count parameters are **ignored** in
tournament mode — valid in the config but without effect, NOT a validation
error — so configs can switch modes without surgery and the UI can simply grey
those parameters out (DECISIONS #34).

## 3. Architecture

```
pdsim/
  core/
    game.py          # Game ABC; PrisonersDilemma; (v2: PublicGoodsGame)
    strategy.py      # Strategy ABC; history/memory views handed to strategies
    strategies/      # one module per strategy, auto-discovered on package import
      registry.py    #   Strategy Registry: StrategyInfo metadata + create_strategy
    agent.py         # Agent: identity, strategy instance, score, history store
    matcher.py       # Matcher ABC; RoundRobin; RandomK; (future: SpatialKernel)
    match.py         # plays one match (length mode, noise ε) between participants
    selection.py     # SelectionRule ABC; Fermi; (future: proportional, tournament, ...)
    reproduction.py  # StrategySwitchReproduction (mutation μ); (v2: perturbation)
    dynamics.py      # run loops: PopulationDynamics + GenerationReport (evolution);
                     #   TournamentDynamics + CycleReport (tournament) (fixed size v1;
                     #   v2: growth/energy economy, carrying capacity, async/Moran)
    events.py        # typed event dataclasses (see §4)
    engine.py        # run(config, granularity) -> Iterator[Event] (see §4)
    timeseries.py    # RunTimeseries: folds period events into chart/recorder series
  config/
    registry.py      # Parameter Registry (single source of truth; see §5)
    experiment.py    # ExperimentConfig schema (pydantic); YAML load/save; validation
    scenarios.py     # Scenario Registry: curated presets (see §5.1; v3 scenario home)
  io/
    results.py       # persistence: run folder = config.yaml + results.parquet + meta (M7)
  viz/
    charts.py        # pure builders: RunTimeseries -> plotly figures; summary rows (§4)
  ui/
    app.py           # Streamlit app: scenario picker + generated panel + live charts (§4.1)
    helpers.py       # Streamlit-free config <-> widget-state mapping (testable)
  tests/             # pytest; includes validation against known results (see §7)
```

Key contracts:

- `Strategy.decide(view, rng) -> Action` where `view` exposes: my history vs this opponent,
  opponent's actions vs me, round number, (optionally, later: public reputation info);
  `rng` is the injected seeded generator, so stochastic strategies stay reproducible
  (see DECISIONS #21). Strategies are stateless — pure functions of (view, rng) — and
  never see engine internals.
- `Game.play(actions: Mapping[AgentId, Action]) -> Mapping[AgentId, Payoff]` —
  arity-agnostic so PGG fits the same interface.
- `engine.run(config, granularity="generation") -> Iterator[Event]` — a
  module-level generator function: the engine **yields events** rather than
  returning a final blob (see §4). The CLI, recorder, and live UI are all just
  event consumers. `granularity` is an observer concern, never a model
  parameter (DECISIONS #35).

### 3.1 Performance strategy

- v1 engine is object-per-agent, optimized for readability and debuggability.
  Practical envelope (order of magnitude, 50 rounds/match, round-robin):
  N=100 → several generations/sec; N=300 → seconds/generation; N≥1000 → too slow.
- The interfaces are designed so a **vectorized NumPy backend** (strategies as batch
  state machines over arrays) can be added later for N in the thousands (~10–100×).
  Rule: nothing in configs, UI, or persistence may assume the object backend.

## 4. Event stream and live visualization

The engine (`pdsim/core/engine.py`) is a generator: `engine.run(config,
granularity)` yields immutable typed events (`pdsim/core/events.py`) as the run
unfolds. Five event types (DECISIONS #35):

- `RoundPlayed` — pair identity, round index, executed actions, payoffs.
- `MatchFinished` — pair identity, per-agent match totals, match length.
- `GenerationFinished` (evolution mode) — generation index, population
  composition (strategy → count), per-strategy mean scores.
- `CycleFinished` (tournament mode) — cycle index, composition (constant), and
  per-strategy **cumulative** totals + per-agent mean scores. A distinct type
  from `GenerationFinished` because the payloads differ: a generation reports
  that generation's scores; a cycle reports run-long cumulative standings.
- `RunFinished` — always emitted, exactly once, last: mode, periods completed,
  final composition, and final scores/standings.

**Granularity** (`"round" | "match" | "generation"`, default `"generation"`) is
an argument to `engine.run` controlling the *finest* event level emitted;
coarser events are always emitted, and `RunFinished` always. In tournament mode
the "generation" level is the cycle level. Granularity is an **observer**
concern, not a model parameter — deliberately NOT in the Parameter Registry or
`ExperimentConfig`: the same config + seed produces identical simulation
results at every granularity (DECISIONS #35). Fine-granularity events are
buffered one generation/cycle at a time and arrive in play order.

Consumers:

- **Live UI** (M6): stacked-area composition + per-strategy score trajectories
  in evolution mode; cumulative/mean standings in tournament mode; user-chosen
  granularity with playback speed. Fine granularity is for small N;
  per-generation updates for large N.
- **Recorder** (M7): writes the time series to disk regardless of UI granularity.
- **Demos**: `examples/quickstart.py` (evolution) and
  `examples/tournament_demo.py` (tournament) show the consumer pattern.

All charting consumers share one intermediate shape: `RunTimeseries`
(`pdsim/core/timeseries.py`) folds period events into aligned per-strategy
series (newcomers backfilled, the extinct gap out). It lives in `core` — pure
data processing, no plotting imports — so M7's recorder can reuse it without
touching the viz layer (DECISIONS #37). `pdsim/viz/charts.py` holds pure
builders (`RunTimeseries` in → plotly Figure out; final summaries as plain
table rows) with a per-strategy color map derived from Strategy Registry
order, stable across charts, modes, and reruns.

### 4.1 The v1 Streamlit app (`pdsim/ui/app.py`)

Launched with `streamlit run pdsim/ui/app.py`. Layout (NetLogo-style: model on
top, parameters, live plots below):

1. **Scenario dropdown** — Scenario Registry entries by display name plus
   "Custom" (registry defaults + an even population split). Selecting loads
   the scenario's config into the widgets *once*; every widget stays editable
   (a scenario is a starting point, not a lock — DECISIONS #40) and its
   question/things-to-try text is shown.
2. **Generated parameter panel** — built from the Parameter Registry: widget
   kind from each spec (bool→checkbox, choice→selectbox, numeric→bounded
   number input, nullable→"limit?" checkbox + input), tooltips from the
   novice descriptions, one expander per registry section, widget keys =
   registry keys (DECISIONS #38). Bespoke pieces: the per-strategy
   composition inputs (names/descriptions from the Strategy Registry, live
   sum check gating Run) and a per-strategy parameter expander writing only
   non-default values into `strategy_params` (DECISIONS #41).
3. **Mode-awareness** — `run.mode` as a prominent radio; ignored parameters
   are greyed out (never hidden) with a tooltip explaining why (#34).
4. **Run controls** — granularity (labelled "cycle" at the coarse level in
   tournament mode), playback delay, Run (disabled while the mix ≠ size),
   Stop (session-state flag checked per event).
5. **Live charts** — placeholders redrawn only on period events; fine-grained
   events advance a progress line, batched every 200 events (DECISIONS #39);
   after the run, the final summary table and periods-elapsed message.

Config assembly and scenario↔widget mapping live in the Streamlit-free
`pdsim/ui/helpers.py`; pydantic validation errors surface as plain sentences
via `st.error`. The seed is an ordinary, visible widget: same seed + same
settings = same charts.

## 5. Parameter Registry (novice-first explanations)

Every tunable parameter and every strategy is declared exactly once in
`config/registry.py` with: key, type, range/choices, default, display name,
**plain-language description written for a non-expert**, and (optionally) a "learn
more" note. From this registry we generate:

1. UI widgets with hover/click help text (Streamlit `help=`),
2. the auto-generated `docs/PARAMETERS.md` reference,
3. config validation (types, ranges, cross-parameter constraints).

It is structurally impossible for a parameter to exist without an explanation: the
registry entry *is* the parameter's existence.

### 5.1 Scenario Registry (curated presets)

The third instance of the registry idiom (`pdsim/config/scenarios.py`, after the
Parameter and Strategy Registries). Each scenario is a frozen `ScenarioInfo`:
machine name, display name, a novice-friendly "what question does this
explore?" description, a **complete validated `ExperimentConfig`**, and a
"things to try" note with concrete tweaks to experiment with. The UI's scenario
dropdown (M6) reads this registry; "Custom" is a UI concept (start anywhere,
then edit), not a registry entry. One scenario = one config — comparative
questions live in the things-to-try text; run-both-and-compare is a possible
future UI mechanism (DECISIONS #36).

v1 ships five seed scenarios: `classic_tournament`, `reciprocity_takes_over`,
`noise_breaks_the_grim`, `drift_vs_meritocracy`, `defectors_paradise`.

This registry is also the designated future home of the v3 real-world scenario
presets (§6.3): geographic/geopolitical setups will register here exactly like
the seed scenarios.

## 6. Designed-for future extensions (build nothing that blocks these)

### 6.1 Growing populations — score-as-energy economy (v2)
Reproduction costs a score threshold T (deducted from parent / staked to offspring);
optional per-round living cost with death at score ≤ 0; carrying capacity K (at K,
births require deaths → Moran-like). Growth regime vs at-capacity regime as distinct
experimental phases. Requires: variable-size population handling in dynamics,
offspring-initial-score policy, score accounting options — all already isolated in
`dynamics.py` / `reproduction.py` / `ScoreAccounting`.

### 6.2 N-player games, reputation, punishment (v2)
Public Goods Game and variants (threshold/step-level, volunteer's dilemma, n-player
snowdrift) via the arity-agnostic `Game` interface. Reciprocity machinery for group
games: public reputation scores, targeted peer punishment (pay a cost to fine a
defector), exclusion. These enter as engine mechanics + strategy-view extensions.

### 6.3 Spatial / geographic layer (v3+)
Agents get an optional `position`; `SpatialKernel` matcher makes interaction
probability decay with distance; initial population dispersion configurable; positions
may map onto real geographies (countries/states/municipalities via GeoJSON), rendered
as map visualizations. Implication now: `Agent` carries an optional position attribute
from day one; matching is already an interface; the results schema reserves room for
per-agent spatial snapshots.

### 6.4 GUI evolution
Streamlit v1 → richer dashboard (Dash or FastAPI+React) when maps and heavy
interactivity arrive. Safe because of the headless-engine rule (§1.2). YAML configs
remain first-class alongside the UI forever — they are the batch/scripting interface
(e.g., scheduled experiment sweeps in Claude Cowork).

## 7. Validation

- Unit tests per strategy (decision tables against hand-worked histories).
- Engine-level golden tests: TFT vs AlwaysDefect known score sequences; noise-free
  TFT vs TFT = mutual cooperation; GrimTrigger collapse under ε > 0.
- Cross-validation of strategy behavior against the open-source `axelrod` Python
  library (reference implementation of hundreds of PD strategies). We build our own
  engine, but `axelrod` is the correctness oracle for v1 strategies.
- Statistical sanity checks: with β=0, strategy frequencies follow neutral drift;
  with μ>0, no strategy goes permanently extinct.

## 8. Results and conventions (chosen defaults; see DECISIONS.md #9)

- Each run writes a folder `runs/<timestamp>_<slug>/` containing `config.yaml`
  (complete, including seed and code version), `timeseries.parquet` (per-generation
  per-strategy counts and score stats; Parquet chosen over CSV for size/speed with
  long runs — pandas reads both trivially), `summary.json`, and exported Plotly HTML
  charts. A `runs/index.csv` catalogs all runs for cross-experiment comparison.
