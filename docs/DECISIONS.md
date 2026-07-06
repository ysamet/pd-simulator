# DECISIONS.md — Design decision log

Append-only. Each entry: number, date, decision, rationale, alternatives considered.
Reversals get a new entry referencing the superseded one.

---

**#1 — 2026-07-03 — Development environments split by role.**
Model design in the Claude.ai project chat; implementation in Claude Code (via Cursor);
batch experiment operation later in Claude Cowork. Rationale: chat suits iterative
design debate and keeps project history; Code suits versioned implementation; Cowork
suits scheduled experiment sweeps once the platform exists.

**#2 — 2026-07-03 — v1 game scope: pairwise repeated PD only, with per-opponent memory
in a multi-agent population.** Pairwise repetition with memory gives built-in direct
reciprocity. N-player games (PGG + variants), broader reputation, and punishment
mechanics are v2, behind the arity-agnostic `Game` interface designed now.
Alternative considered: minimal PGG in v1 — rejected to keep v1 validatable against
classic Axelrod-style results.

**#3 — 2026-07-03 — Payoffs: standard T=5, R=3, P=1, S=0 as tunable defaults;
`T>R>P>S` and `2R>T+S` validations togglable.** Relaxing the orderings deliberately
lets the user explore neighboring games (Chicken, Stag Hunt).

**#4 — 2026-07-03 — v1 strategy roster:** AlwaysCooperate, AlwaysDefect, Random(p),
TitForTat, GenerousTitForTat(g), GrimTrigger, Pavlov. Covers the canonical behavioral
archetypes (unconditional, reciprocal, forgiving, unforgiving, outcome-based).

**#5 — 2026-07-03 — Memory: full per-opponent history available to strategies by
default; optional `memory_depth` cap.** Full history future-proofs learning/complex
strategies at negligible cost; the cap is an experimental constraint, not an
implementation shortcut.

**#6 — 2026-07-03 — Matching: RoundRobin default; RandomK as an interface sibling
(shipped in v1 if cheap, else v1.5, may be greyed out in UI); SpatialKernel reserved
for the geographic layer.** Matching is an ABC from day one.

**#7 — 2026-07-03 — Match length: both fixed-rounds and continuation-probability w
modes in v1, UI-selectable.** Known horizons invite end-game defection; w models the
shadow of the future. Cheap to support both.

**#8 — 2026-07-03 — Noise: execution error ε included in v1 as a UI-configurable
parameter.** It is the classic robustness axis (Grim vs GTFT/Pavlov). Perception
error deferred.

**#9 — 2026-07-03 — v1 dynamics package: fixed population N, synchronous generations,
Fermi selection with tunable intensity β, strategy-switch mutation with tunable rate μ,
scores reset each generation.** β sweeps drift→meritocracy as a single knob; μ>0
regenerates extinct strategies and produces the theoretically expected cooperation
cycles. Growth via score-as-energy economy (reproduction cost T, living cost, carrying
capacity K) is v2 but the architecture (dynamics/reproduction/score-accounting
isolation) is designed for it now. Alternatives logged in DESIGN.md §2.7/§6.1:
proportional, tournament(k), truncation, threshold cloning — all future
`SelectionRule` implementations.

**#10 — 2026-07-03 — Engine: readable object-per-agent backend for v1 (practical to
~300 agents with live viz); vectorized NumPy backend planned for thousands of agents.**
Interfaces must never assume the object backend. Population scale ambition: thousands;
v1 target: hundreds.

**#11 — 2026-07-03 — v1 interface: minimal web UI (Streamlit) with full parameter
panel, not config-file-editing.** Streamlit chosen for speed-to-working-app, built-in
per-widget help tooltips, and Plotly integration. UI is a thin layer over the headless
engine + `ExperimentConfig`; YAML configs remain first-class for scripted/batch runs.
Alternatives: Dash, FastAPI+React — deferred until the map/dashboard era (v3+), made
safe by the headless-engine rule.

**#12 — 2026-07-03 — Live visualization: engine emits a typed event stream; UI update
granularity is user-chosen (round / match / generation) with playback speed.**
Round-level watching for small N, generation-level for large N. Recorder persists
full time series regardless of display granularity.

**#13 — 2026-07-03 — v1 charts: stacked-area population composition over time,
per-strategy mean score trajectories, final-outcome summary table.** 2D/geographic map
visualizations (real countries/regions, configurable initial dispersion,
distance-weighted interaction) are a committed future direction shaping today's
architecture: optional `Agent.position`, `Matcher` ABC, spatial room in results schema.

**#14 — 2026-07-03 — Results conventions:** one folder per run
(`runs/<timestamp>_<slug>/`) containing complete `config.yaml` (with seed),
`timeseries.parquet` (Parquet over CSV for size/speed on long runs), `summary.json`,
exported Plotly HTML, plus a global `runs/index.csv` catalog. Rationale:
reproducibility and easy cross-experiment comparison.

**#15 — 2026-07-03 — Parameter Registry as single source of truth.** Every parameter
and strategy declared once with type, range, default, and a novice-friendly
plain-language explanation; UI tooltips, `docs/PARAMETERS.md`, and config validation
are all generated from it. Rationale: the platform's user is a non-expert; explanations
must be structurally impossible to omit.

**#16 — 2026-07-03 — Governance:** Google-style docstrings + type hints on everything;
project context files (`CLAUDE.md`, `DESIGN.md`, `DECISIONS.md`, `ROADMAP.md`)
maintained as the cross-conversation synchronization mechanism between chat (design)
and Claude Code (implementation). `axelrod` library used as correctness oracle for
strategy validation (we build our own engine).

**#17 — 2026-07-03 — Folder structure: design docs live in `docs/`; `CLAUDE.md` stays
at the repo root.** `DESIGN.md`, `ROADMAP.md`, and `DECISIONS.md` (this file) are kept
in `docs/`, keeping the root clear for code and tooling config as modules land.
`CLAUDE.md` remains at the root, where Claude Code auto-loads it. Convention:
references from root-level files use the `docs/` prefix; references between the docs
themselves stay bare filenames (same folder). Generated documentation (e.g.,
`docs/PARAMETERS.md`) also lands in `docs/`. Alternative considered: all docs at the
repo root — rejected as clutter once source modules exist.

**#18 — 2026-07-03 — Milestone 1 implementation conventions (registry + config).**
(a) Config models (pydantic v2) contain **no literal defaults or ranges**: every field
pulls its default from the Parameter Registry and is re-validated against its
`ParameterSpec` via a shared base-model hook, so the registry stays the single source
of truth with zero duplication. (b) Configs are **immutable** (`frozen=True`) and
**reject unknown keys** (`extra="forbid"`): a typo'd YAML key fails loudly instead of
silently producing a different run — a reproducibility guard. (c) Population
composition is an explicit strategy→count mapping that must sum to `population.size`;
strategy-name validation is deferred to milestone 3 when the strategy registry exists.
(d) `match.continuation_probability` gets an *exclusive* upper bound (w < 1), since
w = 1 means matches never end; `ParameterSpec` supports `maximum_exclusive` for this.
(e) Tooling: hatchling build backend; ruff with pydocstyle (Google convention) and
flake8-annotations enabled so hard rules 1–2 (docstrings, type hints) are
machine-enforced; pytest suites live in `pdsim/tests/`. Alternative considered for (a):
plain pydantic `Field(ge=…, le=…)` constraints — rejected because ranges would then be
declared twice (registry + model), violating hard rule 3.

**#19 — 2026-07-03 — Sync protocol strengthened from principle to explicit contract.**
The cross-environment documentation protocol in `CLAUDE.md` was upgraded (supersedes
the "Cross-conversation synchronization protocol" section; complements #16) into a
knowledge-preservation contract with three parts: (a) a **quality standard** — the
`docs/` files alone must suffice for an external advisor (human or AI) to give
correct, current advice about the project without seeing the code; (b) an explicit
**checklist of triggers** that require a same-session `docs/` update (interface or
contract changes, new mechanisms/parameters/modules/dependencies,
implementation-time design decisions, discovered ambiguities/performance
walls/open questions, milestone or scope changes, user decisions made in
conversation); (c) a **mandatory end-of-session ritual** reporting `DOCS CHANGED:
<files>` or `DOCS UNCHANGED` to the user, naming any new DECISIONS entry numbers.
Rationale: the `docs/` files are the only shared memory between the AI environments
this project spans; instructions phrased as explicit triggers and rituals are
followed far more reliably than general principles. Alternative considered:
automated enforcement via session hooks — deferred unless instruction-based
compliance proves insufficient.

**#20 — 2026-07-03 — Noise records executed actions only.** With execution error ε,
the post-flip (executed) action is the single truth per round: payoffs are computed
from it, both agents' histories store it, and an agent observes its own executed
action (your hand trembled; everyone — including you — saw what your hand did).
Intended actions are discarded. Rationale: DESIGN §2.6 defines ε as *execution*
error, a realized-world event; one truth per round reserves divergent observations
cleanly for the future perception-error mechanism. Alternative rejected: the actor
seeing its intended action — conflates execution error with perception error.

**#21 — 2026-07-03 — Strategies are stateless; §3 contract amended to
`Strategy.decide(view, rng) -> Action`.** A strategy is a pure function of the
history view plus the injected RNG; strategies carry no mutable state — all memory
lives in engine-owned history. Rationale: the `memory_depth` cap (#5) is only
enforceable if memory is engine-controlled (a stateful GrimTrigger would remember a
defection forever, silently defeating the cap); the explicit `rng` parameter
satisfies the seeded-randomness rule for Random(p)/GTFT(g) arriving in M3.
Documented consequence: under cap k, GrimTrigger means "grim within the visible
k-round window". Alternatives rejected: mutable per-match strategy state (defeats
the cap); rng smuggled into the view (the view is knowledge, the rng a capability).

**#22 — 2026-07-03 — History-view semantics.** `round_number` is 0-based and equals
the true number of rounds recorded against this opponent, cumulative across matches
within a generation (direct reciprocity per DESIGN §2.2). `memory_depth` truncates
both move sequences (last k, kept aligned) but never `round_number` — the cap
constrains memory of behavior, not awareness of time. Views expose moves only: no
payoffs (every v1 strategy is decidable from moves) and no total match length, so
fixed-horizon backward induction is impossible from the view alone.

**#23 — 2026-07-03 — Match mechanics.** Fixed per-round RNG draw order for
reproducibility: decide A, decide B, noise A, noise B, then (continuation mode) the
continue/stop draw; noise draws occur only when ε > 0. Continuation mode always
plays at least one round, then continues while `rng.random() < w` (geometric
length, E[L] = 1/(1−w); w = 0 ⇒ exactly one round). `Match.play` updates agent
scores/histories as rounds complete and returns a full-transcript `MatchResult`
(feeds M5's event stream and the §7 golden tests).

**#24 — 2026-07-03 — Core constructors take whole config models.**
`PrisonersDilemma(GameConfig)`, `Match(game, MatchConfig, rng)`,
`build_matcher(MatchingConfig)` — validated frozen models cross module boundaries,
never bare primitives/dicts (CLAUDE.md style rule). Test stub strategies live in
`pdsim/tests/stub_strategies.py`, not `pdsim/core/strategies/`, which stays
reserved for M3's auto-discovered roster.

**#25 — 2026-07-04 — Strategy Registry: `StrategyInfo` + auto-discovery in
`pdsim/core/strategies/registry.py`.** Each strategy module declares one frozen
`StrategyInfo` (machine name, display name, novice description, the class as
`factory`, its `ParameterSpec`s, literature note) via a module-level
`register_strategy(...)` call; the package `__init__` auto-imports every module in
the folder (pkgutil), so *importing the package guarantees the roster is populated*
and adding a strategy = dropping in one module, zero other edits. Consequences and
conventions: (a) **machine names are a persistence surface** — saved configs
reference them, so renaming one is a breaking change (hard rule 8); the v1 names
are `always_cooperate`, `always_defect`, `random`, `tit_for_tat`,
`generous_tit_for_tat`, `grim_trigger`, `pavlov`. (b) Strategy parameter keys are
`strategy.<machine_name>.<param>`; the last segment doubles as the constructor
keyword, and `create_strategy(name, **overrides)` is the factory M4's mutation and
M6's UI construct through. Parameter values are validated inside each strategy's
constructor against its registry spec — one validation path. (c)
`population.composition` names are now validated against the roster (closes the
#18c deferral) via a *lazy function-level import* in the config validator, breaking
the `core.game → config.experiment → core.strategies → core.game` import cycle.
(d) Registration order is alphabetical module order (= UI display order for now).
(e) Since strategies are stateless (#21), M4 may share one instance per
(strategy, params) across agents — noted as an option, not built. Alternatives
rejected: a class decorator for registration (needs a decorator factory; the
module-level call matches the Parameter Registry idiom); housing the registry in
`core/strategy.py` (keeps the interface module minimal).

**#26 — 2026-07-04 — Roster semantics under moves-only views.** All reciprocal
strategies key off the *visible* (memory-capped) window, never `round_number`: an
empty window is a fresh start (uniform with #21's "grim within the visible
window"). Pavlov is derived from moves because views expose no payoffs (#22):
under PD ordering my round paid T or R ("win") exactly when the opponent
cooperated, so Win-Stay-Lose-Shift = repeat my last *executed* (post-noise, #20)
move if the opponent's last visible move was C, flip it if D; with the payoff
orderings relaxed (Chicken/Stag Hunt), Pavlov keeps this moves-based definition.
RNG discipline: Random draws exactly once per decision regardless of p; GTFT draws
only when reacting to a defection (a conditional draw is fine — the draw count is
a deterministic function of the visible history, per #23). Defaults: Random
p = 0.5; GTFT g = 1/3 — Nowak & Sigmund (1992)'s optimal generosity
`min(1−(T−R)/(R−S), (R−P)/(T−P))` at standard payoffs, and exactly what the
axelrod library's GTFT derives; a fixed constant (not payoff-derived) because
registry defaults are static data. Both p and g allow the closed extremes 0 and 1
(legitimate degenerate strategies), unlike `continuation_probability`.

**#27 — 2026-07-04 — axelrod cross-validation methodology (DESIGN §7).** Dev-only
dependency `axelrod>=4.13,<4.14` (4.14.0 added a heavyweight torch dependency for
neural-net strategies we don't use); it imports fine on Python 3.13/numpy 2.5, so
the live oracle is used — no pinned-goldens fallback needed. The test module is
guarded by `pytest.importorskip`, so the main suite stands alone and the
headless-engine rule is untouched (nothing outside tests imports axelrod). Method:
full-match **transcript equality** (30 rounds, noise-free, default payoffs — the
same (T,R,P,S) in both engines) for the five deterministic strategies across all
15 pairings incl. self-play, plus scripted Cycler probes ("CCD", "CD") to force
asymmetric histories, plus the stochastic strategies at their deterministic
extremes as exact aliases (Random(0)≡Defector, Random(1)≡Cooperator,
GTFT(0)≡TitForTat, GTFT(1)≡Cooperator). Interior p/g behavior is checked
statistically in our engine only — cross-library RNG stream equality is neither
possible nor needed. One payoff-total check against `Match.final_score()` guards
the scoring path too.

**#28 — 2026-07-04 — Open question (logged, unresolved): per-run strategy
parameters in configs.** `population.composition` maps machine name → count only;
there is currently no way to express `Random(p=0.9)` — or a population mixing two
different p values — in an `ExperimentConfig`/YAML. Strategy parameters exist in
the Parameter Registry and `create_strategy` accepts overrides, so the machinery
is ready; what's missing is the config schema surface. Deferred until M4 (engine
instantiates populations) / M6 (UI) make the need concrete.

**#29 — 2026-07-04 — Workflow: all repo changes flow through Claude Code; commits
are performed exclusively by the owner.** The owner does not hand-edit repo files:
every change — code and docs — is made by Claude Code, arriving either as prompts
the owner pastes (often drafted in the design chat) or as in-session decisions. A
session must never end by asking the owner to edit a file manually; Claude Code
does the edit. Git commits are the owner's act, never Claude Code's (`git commit`
is never run by Claude Code). At every milestone completion — and whenever a
commit is warranted — Claude Code presents (a) a summary of what was done, (b) the
list of files to stage, and (c) a suggested commit message; the owner performs the
commit himself. Rationale: the owner retains sole authorship of repository history
while all mechanical editing stays with Claude Code, matching the environment
split in #1. Codified in `CLAUDE.md` ("About the developer") this session.

**#30 — 2026-07-04 — Per-run strategy parameters: optional top-level
`strategy_params` config section (resolves the #28 open question).**
`ExperimentConfig` gains `strategy_params: {machine_name: {param: value}}`,
overriding Parameter Registry defaults for that run (e.g.
`{"random": {"cooperation_probability": 0.9}}`). **One parameter set per strategy
per run**; heterogeneous same-strategy variants in one population (two different
p values coexisting) are explicitly deferred to v2 — the parameter-perturbation
mutation era, which needs per-variant identity machinery anyway. Validation:
strategy names must exist in the roster; parameter names must be declared by that
strategy's `StrategyInfo`; values validate against their `ParameterSpec`s. Naming
a strategy in `strategy_params` that is absent from the composition is **allowed
but a no-op for the initial population** — allowed because strategy-switch
mutation may still introduce that strategy mid-run, at which point its configured
parameters apply. Alternatives considered: parameterized composition entries
(rejected: conflates the population mix with strategy tuning and complicates the
one-set-per-strategy rule); leaving #28 open (rejected: M4's mutation must
construct strategies from config now).

**#31 — 2026-07-04 — Generation boundary resets scores AND per-opponent
histories.** Rationale: selection changes agents' strategies between
generations, so a remembered relationship would be memory of a behaviorally
different agent — e.g. GrimTrigger would punish a now-cooperative neighbor
forever for a defection its predecessor strategy made. Consequence (restating
\#22): a history view's `round_number` is cumulative within one generation only.
Implementation: the same `Agent` objects persist across the whole run (ids
0..N-1 each generation); after offspring strategies are assigned,
`Agent.reset_for_new_generation()` clears score and histories. Alternative
rejected: score-only reset with histories persisting across generations — that
is cross-generation reputation, a deliberate future mechanism (DESIGN §6.2),
not something to fall into by accident.

**#32 — 2026-07-04 — Dynamics-phase semantics and RNG draw order (extends #23
to the generation level).** Fermi semantics: for each of the N next-generation
slots, sample incumbent A and model B uniformly **with replacement** from the
current generation's scored population (A = B is allowed — a no-op comparison);
the slot adopts B's strategy with probability `1/(1+exp(−β(s_B − s_A)))`,
computed with a sign-branched logistic so extreme β·Δscore never overflows. All
N decisions are made against the same scored population and applied
simultaneously — no mid-selection feedback (synchronous generations, DESIGN
§2.7). RNG draw order per generation: (1) **match phase** — pairings in matcher
order, per-round draws per #23; (2) **selection phase** — per slot: incumbent
index, model index, adoption coin; always exactly three draws, regardless of β;
(3) **mutation phase** — per slot: one coin only when μ > 0, then one
roster-index draw only when the coin hits (the conditional-draw precedent set by
ε in #23). Mutation draws from the **full registered roster**, not just the
composition — mutation can introduce strategies the run did not start with
(which is why #30 allows `strategy_params` for non-composition strategies);
mutants are constructed via `create_strategy` with the run's `strategy_params`.
Offspring *share* the parent's strategy instance rather than copying it — safe
because strategies are stateless (#21; the flyweight option noted in #25). Any
change to these orders changes every seeded run's history: breaking change,
new DECISIONS entry required.

**#33 — 2026-07-04 — ROADMAP restructured to reach a working GUI fastest.** The
old "M5 — event stream + persistence" is split: the typed event stream lands in
the new M5 (the UI needs it); persistence (run folders, parquet, runs index,
headless CLI, results browser) is deferred to a new M7. M5 is rescoped to "GUI
foundations": run modes (#34), the typed event stream (#35), and the Scenario
Registry (#36) — the three things M6's Streamlit UI depends on. M6 = the UI
(scenario dropdown, registry-generated panel, mode-aware charts + greying, live
updates, run launcher; NO results browser). M7 = persistence + CLI + results
browser. M8 = polish (the old M7 content). Rationale: a visible, interactive
app is the project's next proof point; nothing in persistence blocks it.

**#34 — 2026-07-04 — Run modes: evolution vs tournament.** New top-level
`run.mode` ("evolution" default | "tournament") and `run.tournament_cycles`
(default 20) registry parameters, mapped to **top-level `ExperimentConfig`
fields** next to `seed` (the `run.*` registry section maps to top-level config
fields; a nested `run:` section would have relocated `seed:` and broken every
existing YAML — hard rule 8). Tournament semantics: a fixed cast keeps its
initial strategies for the whole run; one cycle = one complete matcher pass;
no selection, no mutation, no generation boundary, no resets — scores and
per-opponent histories accumulate across the entire run, so w.r.t. #22/#31 a
tournament is **one long generation** (`round_number` cumulative across
cycles; intended direct-reciprocity behavior — Grim stays grim about a
cycle-1 betrayal). Selection/mutation/generation parameters are **ignored** in
tournament mode — valid but without effect; rejected alternative: hard
validation error — it would force config surgery when switching modes, and the
UI will grey the parameters out instead (they also consume no RNG draws, so
two tournament runs differing only in β/μ are byte-identical). Engine
integration: a `TournamentDynamics` sibling class beside `PopulationDynamics`
in `dynamics.py`, dispatched by the engine on `config.mode`. Rejected: a
RunMode/Runner abstraction (premature with two modes — hard rule 6 is
satisfied by the existing collaborator interfaces, and a third mode can
motivate the abstraction later); rejected: branching inside
`PopulationDynamics` (would muddy M4-validated code). Tournament RNG order:
the #23 match-phase order, repeated per cycle, nothing else.

**#35 — 2026-07-04 — Typed event stream (DESIGN §4).** New `pdsim/core/events.py`
with five frozen-dataclass events — `RoundPlayed`, `MatchFinished`,
`GenerationFinished`, `CycleFinished`, `RunFinished` — and
`pdsim/core/engine.py` exposing `run(config, granularity) -> Iterator[Event]`
as a **module-level generator function** (rejected: an `Engine` class — the
orchestration holds no state an instance would carry). Two distinct
period-level event types because their payloads differ: a generation reports
that generation's composition and mean scores; a cycle reports cumulative
totals and per-agent means (plus the constant composition, a deliberate
superset of the minimum payload, used by standings tables and goldens).
**Granularity ("round" | "match" | "generation", default "generation") is an
observer concern, not a model parameter**: it is an argument to `engine.run`,
deliberately NOT a Parameter Registry entry or config field, because it only
controls which events are emitted — the same config + seed must produce (and
verifiably does produce) identical simulation results at every granularity.
Emission mechanics: the dynamics classes gained a read-only `on_match`
observer hook; the engine buffers fine-grained events one generation/cycle at
a time and yields them in play order (a match's rounds, then its
`MatchFinished`), followed by the period event; exactly one `RunFinished`
closes every stream. The engine owns turning `config.seed` into the run's
generator; direct dynamics users keep injecting their own.

**#36 — 2026-07-04 — Scenario Registry (third registry-idiom instance).** New
`pdsim/config/scenarios.py`: frozen `ScenarioInfo` (machine name, display
name, novice "what question does this explore?" description, a complete
validated `ExperimentConfig`, and a "things to try" note) + the usual
register/lookup/list functions. **One scenario = one config**: comparative
questions ("re-run with β = 0.5 and compare") live in the things-to-try text;
a run-both-and-compare mechanism is a possible future UI feature, not a
registry concern. "Custom" is a UI concept (start from any scenario, then
edit), not a registry entry. Five seed scenarios registered:
`classic_tournament` (tournament mode, all seven strategies),
`reciprocity_takes_over` (the M4 quickstart mix), `noise_breaks_the_grim`
(ε = 0.05, Grim vs the forgivers), `drift_vs_meritocracy` (β = 0.001 control
experiment), `defectors_paradise` (TFT minority, continuation w = 0.98,
strong selection). The registry is the designated home of the v3 real-world
scenario presets (DESIGN §6.3). Every scenario is smoke-run end-to-end in
tests via a shrunk copy of its config.

**#37 — 2026-07-04 — Viz layer: RunTimeseries accumulator + pure chart
builders.** The intermediate shape between events and charts is
`RunTimeseries` (`pdsim/core/timeseries.py`): folds `GenerationFinished`/
`CycleFinished` into aligned per-strategy series (newcomers backfilled with
0/None; the extinct get 0 agents / `None` score — a gap in charts, the honest
picture) and keeps the closing `RunFinished`. Placed in **core**, not viz,
because it is plotting-free data processing and M7's recorder (in `io/`,
which may never import plotting code — hard rule 4) is expected to share it.
`pdsim/viz/charts.py` holds pure builders — `RunTimeseries` in, plotly Figure
out, no Streamlit — so the viz layer survives the §6.4 dashboard migration;
the final summary is returned as **plain table rows** rather than a figure so
any front end renders it natively. Per-strategy colors come from one mapping
derived from Strategy Registry order (stable across charts/modes/reruns);
legends show display names, machine names stay internal.

**#38 — 2026-07-04 — UI panel is generated from the Parameter Registry.**
Widget mapping per `ParameterSpec`: bool → checkbox, choice → selectbox,
int/float → number_input with the spec's bounds, nullable int → a "limit?"
checkbox plus a number input (None = unlimited). Widget keys ARE registry
keys; tooltips are the registry descriptions (+ learn_more) — hard rule 3 in
the UI with zero duplicated text. Sections render as expanders in registry
order; `run.mode` is a prominent radio. Bespoke pieces: per-strategy
composition inputs (labels and tooltips from the Strategy Registry) with a
live sum indicator that disables Run until the mix equals the population
size. Mode-awareness: ignored parameters are greyed out (`disabled=True`)
with an appended tooltip note — never hidden (#34). `app.py` stays
presentation-only; all branchy logic (config assembly, scenario→widget
mapping, default composition, error formatting) lives in the Streamlit-free
`pdsim/ui/helpers.py`, unit-tested without Streamlit.

**#39 — 2026-07-04 — Live-update batching in the UI event loop.** Charts are
rebuilt **only on period events** (RunTimeseries only changes then);
fine-grained `RoundPlayed`/`MatchFinished` events advance a one-line progress
caption at most every 200 events and never touch a figure. The playback-speed
control is a pause after each period redraw. Each redraw uses a fresh
Streamlit element key (Streamlit forbids duplicate element IDs within one
script run). Stop is a session-state flag checked per event (Streamlit's own
rerun interruption is the backstop). Verified end-to-end with
`streamlit.testing.v1.AppTest`, which proved able to drive everything
including a tiny live run — no coverage limitation to log.

**#40 — 2026-07-04 — Scenario-editing behavior in the UI.** Selecting a
scenario writes its config into widget session state exactly once (on
selection change); afterwards the user's edits are never fought and the
dropdown keeps showing the scenario's name. No "(modified)" indicator in M6
(nice-to-have; revisit in M8 if missed). Re-selecting a *different* scenario
and coming back reloads the original pristine. "Custom" starts from registry
defaults plus an even composition split (remainder to the earliest strategy
names) — the registry deliberately has no composition default, so the UI
supplies the most neutral one.

**#41 — 2026-07-04 — strategy_params exposed in the UI (stretch goal
implemented, not deferred).** A "Per-strategy parameters" expander renders
every `StrategyInfo.params` spec; only values **differing from their registry
defaults** are written into `config.strategy_params`, so an untouched panel
produces a config with no strategy_params section and defaults stay implicit
(consistent with #30's one-set-per-strategy rule).

**#42 — 2026-07-04 — Workflow addition (extends #29): every implementation ends
with manual-validation instructions.** After every implementation, Claude Code
presents the exact commands to launch or exercise what was built (including
the venv-activation reminder) plus a short checklist of what to look at to
confirm it works — automated tests complement, never replace, the owner seeing
the thing run. Owner decision this session; codified in `CLAUDE.md`.

**#43 — 2026-07-04 — Session-continuity protocol: `docs/WIP.md` for
context-limit handoffs.** When a session approaches its context limit
mid-work, it stops working and writes `docs/WIP.md` with (a) work state at
file-and-task granularity (done / in-flight / next), (b) every decision made
but not yet logged in DECISIONS.md or reflected in DESIGN.md/ROADMAP.md —
pending docs obligations that transfer to the resuming session, and (c)
anything else that exists only in that conversation; it then tells the owner
to start a fresh session and still performs the end-of-session ritual
(`WIP.md` does not count as a docs change). Every session checks for
`docs/WIP.md` at start; if present it resumes from it and deletes it once
absorbed — a `WIP.md` outliving its work is a bug. The file is ephemeral: not
part of the knowledge-preservation contract, never uploaded to the design
chat, git-ignored (added to `.gitignore`), and never listed in a suggested
commit. Rationale: interrupted sessions otherwise lose unlogged decisions and
in-flight state — the one gap the end-of-session ritual cannot cover, because
an out-of-context session never reaches its end. Alternative considered:
relying on per-prompt manual instructions to hand sessions over — rejected as
unreliable, for the same reason explicit triggers and rituals replaced
general principles in #19. Codified in `CLAUDE.md` ("Session continuity").

**#44 — 2026-07-04 — Score views: raw totals AND per-round means; period
events carry rounds played.** Owner observation: the mean-score chart plots
each strategy's mean *full-generation total* (scale ≈ payoff × (N−1) ×
rounds_per_match, e.g. ~2,600 at the mutual-cooperation ceiling of a
30-agent/30-round run), which reads as "everything bunched at the top" even
though it is exactly the quantity Fermi selection acts on. Decision: keep the
raw total as the default view (it is selection's input — the theoretically
honest series) and add a per-round view (total ÷ rounds actually played),
which lands on the payoff-matrix scale (S..T) and compares across configs;
the UI gets a "Score view" toggle. To make per-round **exact in both
match-length modes** (continuation-mode lengths vary), `GenerationFinished`
and `CycleFinished` now carry `rounds_played` per strategy (agent-rounds),
computed from a new `Agent.rounds_played` property (histories store all
rounds; the memory cap only limits views, #22). Tournament per-round =
cumulative total ÷ cumulative rounds. The last run's `RunTimeseries` is kept
in Streamlit session state, so toggling the view re-renders finished results
without re-running (previously any interaction cleared them). Alternatives
rejected: per-round only (hides what selection sees); config-derived
denominator (wrong under continuation mode); axis rescaling only (doesn't
answer "who wins per interaction"). No RNG or result changes — bookkeeping
only.

**#45 — 2026-07-04 — Time-scope toggle for the mean-score chart: this
generation vs whole game (running averages).** Owner request: per-generation
scores are jumpy; a whole-game view should move gradually. Decision: a second,
orthogonal "Time scope" toggle. "Whole game" plots running averages over the
run so far — cumulative score ÷ cumulative agent-generations (total view) and
cumulative score ÷ cumulative rounds played (per-round view), accumulated in
`RunTimeseries` (`running_mean_scores`, `running_mean_scores_per_round`,
evolution mode only). A currently-extinct strategy's whole-game line carries
forward flat rather than gapping: its accumulated average is unchanged while
it sits out (unlike the per-generation view, where absence honestly gaps).
In tournament mode the toggle is greyed out with an explanatory tooltip —
tournament scores never reset, so the plain series are already whole-game
figures (the #34 greyed-never-hidden pattern). All four view combinations are
pure re-renderings of the same run: no engine or payload changes this time,
and the persisted last run re-renders under any combination without
re-running (#44).

**#46 — 2026-07-05 — Three future directions logged from owner's hands-on M6
usage; design guards only, M7/M8 order unchanged, nothing implemented now.**
(a) **Performance has two independent dimensions** (DESIGN §3.1 updated):
faster execution/rendering of a given interaction count (v2 vectorized
backend; UI-side headroom in incremental trace updates, downsampling, and the
§6.4 dashboard migration) versus fewer interactions per period (sampling
matchers: RandomK in M8 per #6, SpatialKernel in v3). For large N the binding
constraint is match-phase compute — round-robin's O(N²) — not chart
rendering; the two dimensions pair to reach thousands of agents at
interactive speed (ROADMAP v2 updated). (b) **Agent movement over time is a
v3 mechanism** (DESIGN §6.3, ROADMAP v3): a `MovementRule` ABC (random walk,
drift toward similar neighbors, post-interaction relocation) on a
configurable schedule feeding SpatialKernel matching; movement is a
population-dynamics concern, orthogonal to strategies — strategies do not
decide movement in the base design (a strategy-driven variant is a possible
later option, not a design driver). (c) **Agent attributes +
attribute-conditional strategies** (new DESIGN §6.5): a generic attributes
mapping with per-attribute visibility and inheritance policies; strategies
may condition on an opponent's visible attributes (reference frame: Riolo's
tag-based cooperation, Hammond & Axelrod's ethnocentrism). Placed under
**v2** in the ROADMAP (placement call: tags need no geography and pair with
v2's reciprocity machinery; ethnocentrism variants get richer once v3 adds
space). Guards effective now: the §3 view contract names visible attributes
as an extension surface; composition/mutation/selection/charts must not
permanently assume strategy is the only agent dimension; §8 requires the M7
persistence schema to reserve per-agent attribute-snapshot room alongside
the existing spatial reservation. Rationale throughout: owner observations
from real app usage. Explicit non-decision: M7 (persistence + CLI) and M8
(polish) proceed unchanged.

**#47 — 2026-07-06 — Persistence design: raw data only, schema-versioned,
comment-carried code version.** (a) **Raw-vs-derived**: `timeseries.parquet`
persists only raw per-period per-strategy rows (period, strategy, agents,
mean_score, total_score [tournament], rounds_played); derived views —
per-round means (#44), whole-game running averages (#45) — are recomputed on
load by refeeding the rebuilt events through `RunTimeseries`, so persisted
truth is never duplicated and every future derived view works on old
recordings for free. `RunTimeseries` gained a raw `rounds_played` series to
support this (extended in core with tests, per #37's sharing intent).
(b) **Code version**: `pdsim.__version__` plus a best-effort short git hash
(stdlib subprocess; silently `None` outside a checkout), written into
`config.yaml` as YAML **comments** — extra keys would be rejected by the
strict config schema (#18b), comments are invisible to the parser — and
machine-readably into `summary.json`. (c) **Schema guard** (#46 requirement):
`summary.json` carries `schema_version` (1); loaders reject newer versions;
the per-strategy table's file name (`timeseries.parquet`) leaves
`agents.parquet` free for future per-agent spatial/attribute snapshots — no
empty columns written today. (d) `config.yaml` is written at recorder
construction (a crashed run still leaves its reproducible config); a
recording without a `RunFinished` cannot be finalized (stopped runs never
masquerade as completed). (e) `runs/index.csv` appends one row per run
(id, timestamp, mode, N, periods, seed, scenario, headline); concurrent
writers are out of scope for v1. pandas + pyarrow become explicit main
dependencies.

**#48 — 2026-07-06 — Orchestration seams: chart export lives in viz; the CLI
lives at the package top level.** `pdsim/io` never imports plotting code
(hard rule 4): chart HTML export is `viz.charts.export_run_charts(timeseries,
folder)` (plotly with CDN-hosted JS, ~10 kB per file), called by the CLI and
the UI after a recording finalizes — a run folder is complete without charts.
The CLI is `pdsim/run.py` (`python -m pdsim.run`), matching the command
documented since M1; it sits outside `io/` because it orchestrates config
loading + engine + recorder + chart export. It accepts a YAML path or
`--scenario NAME` (exactly one), plus `--out/--slug/--quiet`; exit codes 0/1;
validation errors print the same plain-language sentences as the UI by
reusing `ui.helpers.validation_messages` (kept Streamlit-free by design,
#38 — reused rather than moved, to avoid churning tested M6 code).

**#49 — 2026-07-06 — Results browser and recording UX.** The app becomes two
`st.tabs` ("Run lab" / "Results browser") — the lightest Streamlit mechanism
that keeps one file and one session state; the live-run experience is
unchanged. **Record this run** is a checkbox in the lab, **default ON**
(reproducibility is the platform's ethos; folders are small); stopped runs
are not finalized (config.yaml remains, noted in the UI). The browser lists
`runs/index.csv` newest-first, reconstructs the selected run via
`io.results.load_run`, and renders the same pure chart builders with its own
#44/#45 toggles — pure re-renderings of persisted raw data, the #47 payoff.
**Load config into panel** shipped (not deferred): a button queues the run's
folder; the next script run reuses the scenario-loading machinery to fill
the panel (landing on "Custom") before widgets render. The runs directory is
overridable via the `PDSIM_RUNS_DIR` environment variable so AppTest suites
never touch the real `runs/`. AppTest proved able to drive the browser
(empty state, run rendering, config loading) — no coverage limitation to
log.

**#50 — 2026-07-06 — Browser lists by folder scan (folder = truth); runs are
deletable from the app.** Owner-observed bug: the browser listed
`runs/index.csv`, so hand-deleted or renamed folders left stale dropdown
entries that crashed on selection. Fixes: (a) the browser now lists via a new
`io.results.list_runs` — a scan of the runs directory for folders containing
a readable `summary.json`, carded from that summary with `run_id` taken from
the *current* folder name (so renamed folders appear under their new names),
sorted by recorded timestamp; unreadable folders are skipped silently.
`index.csv` remains the append-only catalog for external analysis and may
lag hand edits — documented, not reconciled retroactively. (b) The load path
is guarded: a folder vanishing between listing and loading renders an
`st.error`, never a traceback. (c) A **Delete…** control in the browser with
an explicit confirm/cancel step calls `io.results.delete_run`, which removes
the folder AND its index row (keeping the catalog in sync for app-initiated
deletions) and refuses anything but a plain direct-child folder name (no
path traversal). Alternative considered: reconciling `index.csv` against the
disk on every read — rejected: it silently rewrites a file the owner may be
analyzing externally, and still misses renames.

**#51 — 2026-07-06 — Deletion must tolerate Windows transient file locks.**
Owner hit `PermissionError` (WinError 5) deleting a run from the app: plain
`shutil.rmtree` fails when anything briefly holds a handle inside the folder
— and this project lives under **OneDrive**, whose sync engine routinely
holds fresh files, as do Explorer windows and antivirus scans. Fixes:
`io.results._rmtree_robust` clears read-only attributes and retries with a
growing delay (6 attempts, ~4 s worst case) before re-raising; the UI wraps
the delete in a handler that renders a plain-language message with concrete
advice (close Explorer, let OneDrive settle, press delete again) — never a
traceback. Tested both ways: a read-only file is recovered automatically; a
genuinely held handle fails cleanly after retries (Windows-only test).
Standing note for future file operations in this repo: **the working copy
sits under OneDrive — any code that deletes or renames run artifacts must
tolerate transient locks.**

**#52 — 2026-07-06 — Runs-catalog reconciliation, in-app rename, and browser
polish (supersedes part of #50; owner decisions after hands-on use).**
(a) **`index.csv` now follows the disk** (reversing #50's append-only
stance at the owner's direction): `io.results.sync_index` regenerates the
catalog from the run folders — deleted folders' rows vanish, renamed folders
appear under their current names — rewriting the file only when stale
(pointless writes would churn OneDrive sync, #51). The browser calls
`sync_index` on every render; `delete_run`/`rename_run` call it too, so the
catalog stays truthful however a run is removed. `RunRecorder.finalize`
keeps its cheap append. (b) **Stale dropdown fix**: Streamlit resurrects a
*popped* widget value from the frontend, and a widget's own key may only be
written before the widget is instantiated in a script run — so delete/rename
stage the next selection under a separate `_select_run` key and the browser
applies it at the top of the next run. (c) **In-app rename**:
`io.results.rename_run(out_dir, run_id, new_name)` — validates a
filesystem-safe plain name, refuses collisions, retries transient locks
(#51), updates the `run_id` inside `summary.json`, reconciles the index; the
browser exposes it as a "Rename this run" expander whose text field is keyed
per run (switching runs refreshes the prefill). (d) **"Custom" is recorded
as the scenario label** instead of a blank cell — a blank read as missing
data in the runs table.
