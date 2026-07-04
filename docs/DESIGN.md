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
  - **β = selection intensity**: 0 → pure drift (score irrelevant);
    large → near-deterministic copying of higher scorers. First-class experimental knob.
- **Mutation**: with probability **μ**, a newly produced agent receives a uniformly
  random strategy from the enabled roster instead of the copied one (strategy-switch
  mutation). μ=0 ⇒ perfect cloning. Parameter-perturbation mutation (Gaussian noise on
  continuous strategy parameters, enabling true strategy evolution) is a v2 mode behind
  the same `ReproductionConfig`.
- **Score accounting**: scores reset each generation (v1). Cumulative / sliding-window /
  exponentially discounted accounting are future `ScoreAccounting` options.
- Additional selection rules planned behind the same interface: fitness-proportional
  (roulette), tournament(k), truncation/elitist, threshold-based cloning (see §6.1).

### 2.8 Randomness

Single seeded RNG (numpy `Generator`) injected everywhere; seed recorded in every
run's saved config. No module may create its own unseeded RNG.

## 3. Architecture

```
pdsim/
  core/
    game.py          # Game ABC; PrisonersDilemma; (v2: PublicGoodsGame)
    strategy.py      # Strategy ABC; history/memory views handed to strategies
    strategies/      # one module per strategy
    agent.py         # Agent: identity, strategy instance, score, history store
    matcher.py       # Matcher ABC; RoundRobin; RandomK; (future: SpatialKernel)
    match.py         # plays one match (length mode, noise ε) between participants
    selection.py     # SelectionRule ABC; Fermi; (future: proportional, tournament, ...)
    reproduction.py  # ReproductionConfig; strategy-switch mutation; (v2: perturbation)
    dynamics.py      # generation loop; PopulationDynamics config (fixed size v1;
                     #   v2: growth/energy economy, carrying capacity, async/Moran)
    engine.py        # orchestrates a run; emits event stream (see §4)
  config/
    registry.py      # Parameter Registry (single source of truth; see §5)
    experiment.py    # ExperimentConfig schema (pydantic); YAML load/save; validation
  io/
    results.py       # persistence: run folder = config.yaml + results.parquet + meta
  viz/
    charts.py        # Plotly figure builders (composition area, score trajectories, summary)
  ui/
    app.py           # Streamlit app: parameter panel (from registry) + live charts
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
- `Engine.run(config) -> Iterator[Event]` — the engine **yields events** rather than
  returning a final blob (see §4). The CLI, file writer, and live UI are all just
  event consumers.

### 3.1 Performance strategy

- v1 engine is object-per-agent, optimized for readability and debuggability.
  Practical envelope (order of magnitude, 50 rounds/match, round-robin):
  N=100 → several generations/sec; N=300 → seconds/generation; N≥1000 → too slow.
- The interfaces are designed so a **vectorized NumPy backend** (strategies as batch
  state machines over arrays) can be added later for N in the thousands (~10–100×).
  Rule: nothing in configs, UI, or persistence may assume the object backend.

## 4. Event stream and live visualization

The engine emits typed events: `RoundPlayed`, `MatchFinished`, `GenerationFinished`
(carrying population composition, score stats), `RunFinished`. Consumers:

- **Live UI**: renders population-composition stacked area, per-strategy mean score
  trajectories, updating at a user-chosen granularity (**every round / every match /
  every generation**) with playback speed control. Fine granularity is for small N;
  per-generation updates for large N.
- **Recorder**: writes the time series to disk regardless of UI granularity.

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
