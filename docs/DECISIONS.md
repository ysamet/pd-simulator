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

**#53 — 2026-07-06 — Stopped recordings are discarded, not ghosted.**
Owner-observed: stopping a recorded run left a folder holding only
`config.yaml` — on disk but invisible to the browser and index (which know
only finalized runs). Decision: an explicit stop (the UI's Stop button; the
CLI's Ctrl+C, which now exits 130) is a deliberate abandonment —
`RunRecorder.discard()` deletes the partial folder via the lock-tolerant
deleter (#51), and the UI says so (with delete-by-hand advice if OneDrive
holds the folder). This refines #47(d): the write-config-up-front behavior
still protects **crashes** — a crashed run reaches neither `finalize` nor
`discard`, so its config survives for diagnosis. Alternative considered:
finalizing stopped runs as partial recordings marked "stopped" — rejected
for v1 (adds a status dimension to the schema and the browser for little
value at v1 run lengths; can be revisited if long runs make partial data
worth keeping).

**#54 — 2026-07-06 — Discard-on-stop must be a try/finally, not a flag branch
(fixes #53's mechanism; owner-observed).** The #53 implementation discarded
inside the "stop flag seen" branch — which almost never runs in live
Streamlit: clicking Stop (or Run mid-run, or changing any widget) makes
Streamlit **kill the running script** at its next ``st.*`` call by raising a
control-flow exception; the cooperative flag check and everything after the
loop are simply never reached (AppTest is synchronous, so tests passed while
the real app ghosted — the #39 assumption that the rerun interruption was
merely a "backstop" had it backwards). Fix: the UI run loop is wrapped in
``try/finally`` with a ``settled`` flag — any exit that neither finalized
nor deliberately discarded the recording (Stop, mid-run Run click, crash,
rerun) discards it in ``finally``, and stages a note in session state that
the *next* script run renders (the killed run cannot draw its own caption).
Consequence for #53's crash semantics: in the UI, any abnormal end discards
the partial recording; the crash-keeps-config-for-diagnosis property now
applies to headless/CLI runs only (where no finally intervenes except
Ctrl+C). Standing note: **Streamlit kills mid-run scripts on any user
interaction — cleanup for long-running loops must live in try/finally, and
messages for the user must be staged via session state.**

**#55 — 2026-07-06 — Interruption banners are write-ahead staged (fixes #54's
messaging; owner-observed).** #54's banner was written from the dying
script's ``finally`` — the folder deletion (filesystem) took effect, but the
session-state write raced the rerun triggered by the very click that killed
the script, so the banner never appeared. Fix: the "partial folder was
cleaned up" note is staged **when the recorded run starts** (a moment the
script is certainly alive) and **cleared on successful finalization**; a
killed run therefore cannot fail to leave the note for the next render, and
a clean run never shows it. The ``finally`` now only performs the deletion
(and best-effort rewrites the note if deletion fails). Refines #54's
standing note: session-state messages that must survive a script kill are
staged *before* the risky section, write-ahead-log style — never from the
teardown path.

**#56 — 2026-07-07 — `docs/PARAMETERS.md` is a COMMITTED, generated artifact
guarded by a pytest drift test.** New top-level module `pdsim/gendocs.py`
(beside `run.py`, the #48 orchestration-seam convention; it imports the
config and core registries only — no UI or plotting code, hard rule 4),
runnable as `python -m pdsim.gendocs`, renders the Parameter, Strategy, and
Scenario Registries into `docs/PARAMETERS.md`: simulation parameters grouped
by registry section in registry order (key, display name, type,
range/choices, default, novice description, learn-more note), the strategy
roster (display/machine names, descriptions, literature notes, per-strategy
parameters), and the scenarios (names, question explored, things-to-try).
Zero hand-written parameter text; output is deterministic — registry/
definition order only, no timestamps or environment content, LF-normalized —
which is what makes the guard possible: a **drift test** regenerates the
document in memory and compares it to the committed file, so a stale doc is
a failing test whose message says to rerun the command and stage the result.
Rationale: the knowledge-preservation contract (#19) — the design chat sees
only `docs/` files, so an on-demand-only document is invisible to it; the
drift test makes staleness structurally impossible, the same pattern that
makes a parameter-without-explanation impossible in the registry itself.
Alternatives rejected: generate-on-demand only (invisible to the chat side);
committing without a drift test (silent staleness).

**#57 — 2026-07-07 — RandomK matcher: semantics, validation, and RNG draw
order (extends #23/#32 — a seeded-history contract).** The registry's
`matching.matcher` choice gains `"random_k"` (default stays `"round_robin"`)
alongside a new `matching.opponents_per_agent` (int, k ≥ 1). Semantics: per
generation (or tournament cycle — one cycle = one RandomK pass; cumulative
standings and rounds_played accounting unchanged), every agent INITIATES k
matches against k DISTINCT opponents drawn uniformly without replacement
from the other N−1 agents. Duplicate pairs across initiators are allowed
(A drawing B and B drawing A produces two matches). Total matches = N·k;
per-agent participation varies (k initiated + however often the agent is
drawn). Stated consequence: raw generation scores now include participation
luck — deliberate; the raw total remains what selection acts on (#44's
theoretical-honesty stance), and the per-round view is the
participation-normalized comparison (period events already carry the exact
rounds_played denominator, #44). RNG draw order: at the START of the match
phase, ALL pairings are drawn in agent-id order — for each initiator, one
without-replacement draw of k indices (`rng.choice`) over the other agents
in agent-id order — and matches then play in exactly that order, each
following #23's per-round order; the matcher draws eagerly (not lazily) so
pairing draws can never interleave with in-match draws. Selection/mutation
phases are unchanged (#32); RoundRobin continues to consume zero RNG draws.
Any change to this pairing draw order changes every seeded random_k run's
history: breaking change, new DECISIONS entry required. Validation:
cross-parameter check k ≤ N−1 on `ExperimentConfig` (the composition-sum
precedent) with a plain-language error; `opponents_per_agent` is IGNORED
(valid, no effect, no RNG consumed) under round_robin — the #34
ignored-parameter pattern, so configs switch matchers without surgery. UI:
the Matching panel generates from the registry as designed (verified — the
new k widget appeared with zero UI edits); k is greyed (never hidden) while
the *matcher widget's* current value is round_robin — the first greying
keyed off another widget rather than run.mode — via a new
`ui/helpers.greying` function that now centralizes all #34-pattern rules,
Streamlit-free and unit-tested. Recorder and persistence needed no changes
(verified by a random_k round-trip test, not assumed); scenario configs are
untouched (all use the round_robin default).

**#58 — 2026-07-08 — v2 sequencing: ECONOMY-FIRST, milestone spine
M9 → M9.5 → M10 → M12 → M11 → M13 → M14 (deliberate M12/M11 swap).**
Contents per milestone:
- **M9** — additional selection rules (fitness-proportional, tournament(k),
  truncation/elitist, threshold cloning) and score-accounting options
  (sliding window, exponential discounting), all as plug-ins to the
  existing `SelectionRule` / `ScoreAccounting` ABCs; PLUS pairwise
  cooperation-rate recording (#60) and a **benchmark rider**: a small
  script capturing wall-clock per generation across N × matcher
  combinations, so the vectorization trigger becomes data.
- **M9.5** — the sweep/search layer (#59).
- **M10** — the score-as-energy growth economy (possible split:
  synchronous growth first, async/Moran second). Design-in-chat-first
  items before implementation: offspring initial-score policy, death
  semantics and timing, birth/death RNG draw order (a seeded-history
  contract extending #32), selection semantics under energy-driven
  reproduction, matcher behavior under variable N, and event/schema
  changes (a schema_version bump is expected).
- **M12 (before M11)** — agent attributes/tags + attribute-conditional
  strategies (DESIGN §6.5). Pulled ahead of perturbation mutation because
  the owner's research program targets tag-based/ethnocentrism dynamics
  (the Hammond–Axelrod "in-group cooperator / out-group defector"
  species); tags run deliberately AFTER M10 so they are built
  variable-N-aware from birth.
- **M11** — parameter-perturbation mutation plus the variant-identity
  machinery it requires (resolves the deferral noted in #30).
- **M13** — Public Goods Game + group matching. **M14** —
  reputation/punishment/exclusion; design M14 with M12's
  visible-attributes surface in mind — reputation is nearly a dynamic
  public attribute.
- **Vectorized backend: NOT scheduled.** It is empirically triggered:
  it lands when actual experiments/sweeps show the sampling matchers
  cannot buy the needed scale (M9's benchmark rider supplies the data).
Rationale: variable population size is the most infectious invariant
change in the v2 plan — every mechanism built after it is variable-N-aware
from birth and nothing needs retrofitting; the growth economy is
scientifically self-contained on pairwise PD, so it delivers a working new
capability early; and reputation/punishment queue behind group games
either way. Alternative rejected: games-first (PGG before growth) — it
puts the bigger blast radius first (Match, the Matcher contract, history
views, and event payloads all change at once) and then retrofits variable
N into freshly written group-game code.

**#59 — 2026-07-08 — Sweep/search layer at M9.5.** A batch experiment
layer answering search/optimization questions; the motivating example is
invasion thresholds — "what starting share does species X need to
dominate, or to reach staying power?". Four parts:
(a) **SweepSpec** — a YAML config-family specification: one base config
plus axes of variation (parameter grids, including composition shares,
and seed lists), expanded into fully validated `ExperimentConfig`s.
(b) **Parallel batch runner** (`python -m pdsim.sweep`) using
multiprocessing across runs. Noted consequence: per-run parallelism is a
THIRD performance dimension alongside the two in #46 (faster execution of
a given interaction count; fewer interactions per period) — it makes mass
experiments affordable before any vectorization exists.
(c) An **Outcome Metrics Registry** — the fourth instance of the registry
idiom: named, documented metric functions computed from recorded
timeseries. Metrics are pure post-processing over the #47 raw parquet, so
they work retroactively on old recordings. Initial set: final share;
fixation flag (reached 100%); time to fixation WITH censoring semantics
(run ended first = censored, not "never"); mean share over the last k
generations; quasi-fixation variants (ever exceeded x%; held above x% for
k consecutive generations — the meaningful measures when mutation makes
strict fixation unstable); and cooperation-collapse event metrics
(enabled by #60's cooperation-rate series).
(d) **Sweep persistence**: a `sweeps/<name>/` folder holding the member
runs, a `sweep_summary.parquet` (one row per run: varied parameters,
seed, metrics), and one built-in analysis artifact (a metric-vs-axis
curve with per-point replicate spread).
Placement rationale: the layer sits entirely on the M7 substrate
(headless CLI, config layer, run folders), touches no engine semantics,
and the owner's first research program (Always Defect as a degenerate
adversarial species) runs on v1 mechanics the moment the layer lands.
Later increments, explicitly deferred: adaptive threshold search
(bisection), sweep browsing in the UI, and Cowork-scheduled campaigns.

**#60 — 2026-07-08 — Pairwise cooperation-rate recording (lands in M9).**
The platform currently records composition, scores, and rounds but NOT
cooperation itself, so collapse questions could only be proxied — and the
proxies mislead: composition misclassifies (a 100%-TitForTat population
mid-noise-spiral plays D constantly while looking fully cooperative), and
scores are confounded. Decision: record executed-action cooperation rates
at STRATEGY-PAIR resolution — per period: (actor strategy, opponent
strategy, cooperation rate, actions counted). Per-strategy rates remain
derivable by aggregation (weighted by actions counted), and the
diagonal-vs-off-diagonal contrast of the pair matrix is exactly the M12
ethnocentrism diagnostic (in-group vs out-group cooperation). Known
consequences: new bookkeeping in the match phase, extended period-event
payloads, a new persisted table/columns, and a schema_version bump — the
intended use of the #47 schema guard. Cooperation-rate-over-time also
becomes a headline chart in its own right, independent of the sweep
layer. Alternative rejected: a per-strategy scalar cooperation rate —
insufficient both for the owner's foreseen pairwise questions and for
M12. Deliberate non-decision: how the actor "strategy" row key
generalizes when M11 introduces parameter variants and M12 introduces
tags is owned by those milestones, not pre-built in M9.

**#61 — 2026-07-08 — Governance: app-first manual validation, and
spec-time Validation sections (extends #42; forward-extends the docs/specs
convention).** Two workflow conventions, both codified in `CLAUDE.md` this
session:
(a) **Manual validation is app-first.** The #42 end-of-implementation
validation instructions must prefer exercising the feature THROUGH the
Streamlit app — naming a specific scenario to load, the widgets to touch,
and the observable outcome that confirms success — over CLI commands or
test-suite runs. CLI-based validation is acceptable only for inherently
headless features (e.g. `python -m pdsim.bench`, the headless runner
itself). Automated tests complement, never substitute for, seeing the
feature work in the app. Rationale: the app is the owner's actual
acceptance path, and app-level walkthroughs catch integration issues —
widget wiring, greying, chart rendering, session-state behavior — that
unit tests and CLI runs miss.
(b) **Every spec carries a `## Validation` section, written at SPEC
time**, describing how the owner will confirm the milestone's features in
the app — scenario, widget interactions, expected observable behavior —
with CLI steps only for headless features. Standing division of labor,
recorded with it: the design chat (Claude.ai) delivers milestone-scale
work as a single Claude Code prompt that FIRST creates the spec file
under `docs/specs/` and THEN implements it; the spec file, not the chat
prompt, is the durable statement of intent. Rationale: writing validation
at spec time forces "how will this be visible?" to be answered during
scoping, not discovered after implementation.
Note: (b) extends a docs/specs convention whose founding DECISIONS entry
is expected from the M9a session, which has NOT yet run — this is a
deliberate forward reference; when that session lands its convention
entry, it should reference this one and reconcile.

**#62 — 2026-07-08 — The docs/specs/ convention (founding entry; reconciles
#61's forward reference).** `docs/specs/` holds milestone-sized
implementation specs. Conventions:
- **Naming**: `M<zero-padded milestone><letter>-<slug>.md` (first instance:
  `M09a-selection-accounting-bench.md`).
- **Status line**: each spec opens with `Status: draft | in progress |
  implemented (see DECISIONS #...)`, updated as work proceeds.
- **Frozen intent**: a spec is authoritative until its milestone lands.
  Deviations discovered during implementation are logged in DECISIONS.md;
  the spec is NOT retro-edited beyond its status line. After landing,
  DESIGN.md/DECISIONS.md are the truth and the spec remains as historical
  record.
- **Contract membership**: specs are part of the knowledge-preservation
  contract (CLAUDE.md's advisor standard already names `docs/specs/*`) —
  they count as docs for the DOCS CHANGED ritual and are uploaded to the
  design chat's project knowledge.
- **Scope**: small fixes still travel as plain prompts; specs are for
  milestone-scale work.
Per #61(b), every spec carries a `## Validation` section written at spec
time (app-first), and the division of labor stands: the design chat
delivers milestone work as a single Claude Code prompt that FIRST creates
the spec file and THEN implements it — the spec, not the chat prompt, is
the durable statement of intent. This is the founding convention entry
that #61 forward-referenced; #61's two conventions stand unchanged
within it.

**#63 — 2026-07-08 — Four new selection rules: pinned semantics and RNG
draw orders (M9a; extends #32 — seeded-history contracts).** All four plug
into the existing `SelectionRule` ABC via `dynamics.selection_rule`, keep
#32's synchronous frame (all N slot decisions against the same scored
population, applied simultaneously; the mutation phase runs identically
after every rule; Fermi is untouched), and consume the EFFECTIVE score
supplied by score accounting (#64). Tie-breaks are always deterministic,
never a random draw. Any change to these semantics is breaking and
requires a new entry.
- **proportional** (roulette): weights `w_i = s_i - min(s)` — the shift is
  mandatory because scores can be negative; documented consequence: the
  worst scorer has weight 0 and is never drawn. All scores equal ⇒
  all-zero weights ⇒ uniform fallback. Per slot, in slot order: exactly
  one weighted index draw (`rng.choice` with the normalized weights).
  Always N draws.
- **tournament_k**: machine name deliberately NOT "tournament" — it must
  not collide with `run.mode="tournament"`, and the registry description
  disambiguates the two in plain language. New parameter
  `dynamics.selection_tournament_k` (int ≥ 2, default 3), cross-parameter
  validated k ≤ N at the ExperimentConfig level (#57 precedent). The check
  applies only when the rule is selected AND the mode is evolution — in
  tournament mode every dynamics parameter is inert and ignored parameters
  are never validation errors (#34). Per slot, in slot order: one
  without-replacement draw of k candidate indices
  (`rng.choice(n, size=k, replace=False)` over agent-id order); winner =
  highest effective score among the candidates; ties break to the earliest
  position in the drawn array.
- **truncation** (elitist): new parameter
  `dynamics.selection_elite_fraction` (float, 0 < q ≤ 1, default 0.2).
  To express q > 0 the registry's `ParameterSpec` gained a
  `minimum_exclusive` bound — the mirror of #18(d)'s `maximum_exclusive`.
  `elite_count = max(1, floor(q·N))`; elite membership and order: sort by
  (effective score descending, agent id ascending) — boundary ties go to
  the lower agent id. Per slot, in slot order: one uniform draw of an
  index into that ordered elite list. Always N draws.
- **threshold_cloning**: new parameter
  `dynamics.selection_threshold_multiplier` (float θ, 0 ≤ θ ≤ 10, default
  1.0). Survivor set = agents with effective score ≥ θ·mean effective
  score; if empty (possible when θ > 1, and also with θ < 1 when the mean
  is negative), the survivor set is all agents tied at the maximum.
  Surviving slots keep their own strategy and consume NO draw; each
  non-surviving slot, in slot order, consumes one uniform draw of an index
  into the survivor list (ascending agent-id order). The draw count is
  data-conditional — a deterministic function of the scores, the #26
  precedent (GTFT's conditional draw), not a reproducibility hazard.
UI: `ui/helpers.greying` maps each rule parameter to its owning rule,
keyed off the selection-rule widget's current value (the #57
matcher-keyed pattern) — and this includes `selection_beta`: β is fermi's
parameter and now greys under the other rules, a natural extension beyond
the spec's "new rules' parameters" (logged here as the one deliberate
spec-plus). Everything stays visible (#34 greyed-never-hidden).

**#64 — 2026-07-08 — ScoreAccounting: interface and pinned semantics
(M9a; DESIGN §2.7's seam becomes code).** The seam existed only as prose;
it is now `pdsim/core/accounting.py`: a `ScoreAccounting` ABC with one
method — `effective_scores(raw_scores) -> tuple[float, ...]` — called
exactly once per generation, between the match phase and the selection
phase; `PopulationDynamics` folds the raw scores through it and hands the
result to the selection rule. Everything else is unchanged: raw
per-generation scores, the #31 resets, event payloads, charts,
persistence — accounting is invisible outside the selection phase in M9
(surfacing effective scores in events/charts is a possible later
addition; noted, not built). Pinned semantics:
- **State belongs to the agent SLOT** and survives strategy switches from
  selection or mutation — it models the fitness inertia of the lineage
  occupying the slot. Rejected alternative: reset accounting state on
  strategy change — ill-defined, because copying your own strategy from a
  same-strategy model is not a detectable "switch".
- `dynamics.score_accounting` choices: **per_generation** (default;
  identity — exactly v1 behavior); **sliding_window**
  (`dynamics.accounting_window`, int W ≥ 1, default 5): effective = MEAN
  of the last min(W, generations so far) raw generation scores, current
  included — mean rather than sum keeps the scale comparable across W
  values and during warmup, since β interacts with score scale; W = 1 ≡
  per_generation; **exponential_discount**
  (`dynamics.accounting_discount`, float 0 ≤ λ < 1, default 0.5):
  effective(t) = (1−λ)·raw(t) + λ·effective(t−1), effective(0) = raw(0) —
  the EMA form is scale-stable (a constant raw score is a fixed point at
  any λ); λ = 0 ≡ per_generation.
- Greying (#34): W greyed unless sliding_window, λ greyed unless
  exponential_discount (keyed off the accounting widget), and the whole
  accounting group is inert in tournament mode — verified by a test that
  two tournament streams differing only in accounting are byte-identical.
- RNG: accounting consumes zero draws. With per_generation selected,
  every seeded v1 run is byte-identical to the pre-M9a engine — enforced
  by a regression test pinning a 10-generation composition trajectory
  captured by running the same config on the M8 code (commit b169cf7).

**#65 — 2026-07-09 — Pairwise cooperation-rate recording, schema_version 2
(implements #60; completes M9).** Spec:
`docs/specs/M09b-cooperation-recording.md`.
(a) **Bookkeeping location**: the dynamics loops tally executed-action
(#20) cooperation per ordered (actor strategy, opponent strategy) pair
during the match phase; each round contributes TWO actor records, one per
participant. Pure observability: no RNG draw was added, removed, or
reordered — guarded by regression tests pinning seeded trajectories in
both modes (noise and continuation draws included), captured on pre-M9b
code (commit 4ef17cd).
(b) **Pinned asymmetry**: evolution counts RESET each generation
(per-generation rates, matching GenerationFinished's per-generation
character); tournament counts ACCUMULATE across cycles (cumulative rates,
matching CycleFinished's cumulative character — one tally lives for the
whole run, #34/#35).
(c) **Event payloads**: `GenerationFinished`/`CycleFinished` gain
`cooperation: {(actor, opponent): (cooperation_rate, actions_counted)}`.
Rate plus count makes per-strategy and population aggregates exactly
recomputable by actions-weighted averaging. `RunTimeseries` folds the raw
per-pair series plus two derived views — per-actor-strategy aggregates
and an overall population rate — recomputed on load like every derived
view (#47).
(d) **Persistence — schema 2**: new sibling `cooperation.parquet` (period,
actor_strategy, opponent_strategy, cooperation_rate, actions_counted; raw
rows only) — the sibling-file future that #47(c)'s naming convention
reserved. `summary.json` schema_version becomes 2 and gains
`final_cooperation_rate` (the last period's overall rate — per-generation
in evolution, run-cumulative in tournament, per (b)). Loader
compatibility: loaders accept BOTH 1 and 2 — a schema-1 folder simply has
no cooperation data and renders without the cooperation chart, no error,
no migration; versions above 2 are rejected as before.
(e) **Chart**: `viz.charts.cooperation_chart` — overall population line
plus per-actor-strategy aggregate lines, y-axis pinned 0-1, "(cumulative)"
labeled in tournament mode — wired into the live UI (both modes), the
results browser, and `export_run_charts` (skipped for schema-1 loads).
The full pair matrix renders as final-summary TABLE ROWS (#37 convention);
the pair-matrix heatmap is deferred to M12, where the
diagonal-vs-off-diagonal contrast becomes the in-group/out-group
diagnostic.
(f) **Overhead (the spec's Task 5)**: pre-change bench capture (N=50/100
x both matchers, 3 generations, same machine/command): 0.94 / 3.46 s/gen
round_robin and 0.16 / 0.33 random_k. Post-change, three runs: 0.46-0.48 /
1.91-1.95 and 0.10 / 0.19 — consistently FASTER than the capture, meaning
the pre-change numbers were inflated by first-run machine noise (cold
caches, OneDrive), not that bookkeeping sped anything up. Conclusion: no
observable overhead — bounded by measurement noise, far below the ~10%
materiality bar; no speculative optimization performed. Standing note:
single before/after bench pairs on this machine are noisy — repeat runs
before trusting a delta.

**#66 — 2026-07-11 — Sweep layer (M9.5a): as-built design and SweepSpec
shape (implements #59).** Spec: `docs/specs/M09c-sweep-layer.md`; companion
explainer `docs/explainers/M9.5-sweeps-and-invasion.md`. New
orchestration-tier subpackage `pdsim/sweep/` (`spec.py`, `metrics.py`,
`runner.py`, `__main__.py`) — may import config/core/io/viz but stays
Streamlit-free, so the future Sweep tab (M9.5b) reuses it. Run with
`python -m pdsim.sweep <spec.yaml>`. **Defining principle held (#59):** no
`pdsim/core/` change, no RNG change — the layer is a config *generator* plus
post-processing over recorded runs; every member is a fully-validated
`ExperimentConfig` reproducible from its own `config.yaml`.
- **SweepSpec** (pydantic, frozen, `extra="forbid"`): `name`; exactly one of
  `base` (config path) / `base_scenario`; an optional `composition`
  (three-bucket, #67); `parameters` (list of {registry `key`, `values`});
  `seeds`; `metrics` (list of {`metric` name + flat params}). `MetricRef`
  uses `extra="allow"` so params author flat.
- **Shared validation**: `sweep_validation_messages(spec)` — the
  Streamlit-free analog of `ui.helpers.validation_messages`, the ONE path
  the CLI and the M9.5b tab both call (the #38/#48 reuse pattern). Checks:
  exactly-one base source; composition buckets disjoint; roster membership;
  fill percentages sum to 100; `vary_max + Σfixed ≤ base N`; fill required
  when seats remain; each parameter key + value valid; non-empty
  seeds/metrics; each metric registered with valid params.
- **Expansion**: `expand(spec) -> [MemberPlan]` is the cross product in a
  PINNED order — **composition counts outermost, parameter axes in listed
  order, seeds innermost** (via `itertools.product` with seeds last) — which
  fixes `run_index`, a reproducibility contract. Every member is fully
  validated *before any run executes* (fail fast; a failure names the
  `run_index`). Parameter overrides use the config layer's section→field
  mapping (`run.*` → top level, else `section.field`).
Alternative rejected: a bespoke non-cross-product combinator (zip-style
paired axes) — deferred; the cross product covers the invasion program and
keeps `run_index` trivially deterministic.

**#67 — 2026-07-11 — Three-bucket composition model + largest-remainder
rounding (M9.5a).** A swept population splits into the **varying invader**
(V, one strategy in M9.5a — modelled as a set-of-one so a future
multi-invader is a small change, companion §3.2), **fixed** counts, and
**fill** percentages that divide the remainder `R = N − V − Σfixed`.
`resolve_composition(...)` allocates R across the fill bucket by the
**largest-remainder rule**: floor each fill strategy's ideal share, then
hand leftover seats one at a time to the largest fractional parts, **ties
broken by ascending machine name** (deterministic — the reproducibility
contract). Zero-count entries are dropped; the result sums to N. Worked
example pinned in tests: N=100, invader `tit_for_tat`=2, fill 30/30/40
`always_defect`/`always_cooperate`/`generous_tit_for_tat` → 29/30/39 (the
.4/.4 tie goes to `always_cooperate` by name). Only the *resolved integer
composition* is written into each member's `config.yaml`, so a member is
reproducible with no knowledge of the sweep, percentages, or rounding rule
(the generator-never-a-weakener principle, companion §2.3). Alternative
rejected: rounding by simple truncation or by `round()` — both can miss or
overshoot N; largest-remainder always sums exactly and is the standard
apportionment method.

**#68 — 2026-07-11 — `execute_run` orchestration seam + `RunRecorder`
flags + lazy viz import (M9.5a).** The run→record→finalize orchestration
inside `run.py`'s `main()` is extracted into public `execute_run(config,
*, out_dir, slug, scenario, export_charts, on_period, append_index,
folder_name)`, shared by the CLI and the sweep runner. `main()` is now a
thin wrapper (an `on_period` printer + `export_charts=True`), preserving
CLI output and exit codes 0/1/130. `RunRecorder` gains `append_index`
(False for sweep members — parallel workers must not contend on one shared
`runs/index.csv`, #47e) and `folder_name` (sweep members pass
`<NNN>_<axis-slug>` so `runs/` sorts by run index). The
`from pdsim.viz import charts` import is now **lazy** (inside the
export-charts branch and the CLI's standings print) so importing `run.py`
— and thus `execute_run` into spawn-re-imported sweep workers — does not
pull plotly into every worker process. Existing `run.py`/`io` tests stay
green; new tests cover the two flags. Alternative rejected: a top-level
plotly import guarded by a flag — the import cost is paid at import time
regardless, so laziness must be structural.

**#69 — 2026-07-11 — Outcome Metrics Registry: the fourth registry idiom
(M9.5a).** `pdsim/sweep/metrics.py` mirrors the Scenario Registry:
`OutcomeMetricInfo` (frozen: `name`, `display_name`, mandatory
plain-language `description`, `params` as lightweight `MetricParam`
declarations — NOT full `ParameterSpec`, since the sweep UI is M9.5b —
and a `compute` callable) with `register_metric`/`get_metric`/
`all_metrics`. `compute(run: LoadedRun, **params) -> float | None` reads
the reconstructed `timeseries`/`config`, **never raw parquet** — so metrics
are pure post-processing that apply retroactively to any recording and
inherit schema compatibility for free (schema-1 runs lack cooperation, so
the cooperation metrics return `None`, #65). `None` means
not-applicable/undefined. Strategy-param names are checked against the
roster at compute time with a plain error. Seed set: `final_share`,
`fixation_flag`, `time_to_fixation` + `fixation_censored` (a two-column
**survival-analysis encoding** — a never-fixed run reports
`time = periods_completed`, `censored = 1`; no sentinels, companion §3.4),
`mean_share_last_k`, `ever_exceeded`, `held_above_for` (quasi-fixation
measures for the μ>0 regime, companion §3.3), `min_cooperation`,
`final_cooperation`. gendocs renders a new `## Outcome metrics` section
from `all_metrics()`, covered by the existing drift test (#56). Alternative
rejected: metrics computed live during simulation — would tie metric
authorship to engine changes and lose retroactivity.

**#70 — 2026-07-11 — Parallel runner, single-writer status, resume,
failure isolation (M9.5a).** `run_sweep` writes `sweeps/<name>/`:
`sweep_spec.yaml` (copied verbatim up front — the #47(d) write-ahead
analog), `runs/<NNN>_<axis-slug>/` member folders (recorded with
`append_index=False`, `export_charts=False`), `sweep_status.json`,
`sweep_summary.parquet` (WIDE: `run_index`, `run_id`, `status`, `seed`,
one column per axis, one per metric label like `time_to_fixation[tit_for_tat]`;
rows sorted by `run_index`, never completion order), `sweep_summary.json`
(`schema_version` 1 — the #47 guard's fourth application), and one
metric-vs-primary-axis chart HTML per metric. Members run via a top-level,
picklable worker over `multiprocessing.Pool.imap_unordered`; **the parent
is the sole writer of `sweep_status.json`**, so there is no concurrency on
it. **Failure isolation (#59):** a worker catches every exception and
returns a `"failed"` result — a bad member never kills the sweep; its
summary row keeps its axis columns with null metrics. **Resume:** if
`sweeps/<name>/` exists, members whose finalized folder is present are
skipped and only missing/failed indices re-run (automatic on folder
existence; `--resume` makes it explicit) — in scope for M9.5a because
OneDrive makes mid-sweep interruption likelier (#51). Two deliberate
refinements of the spec's letter: (a) the sweep folder uses the **stable
path** `sweeps/<name>/` (no `_unique` suffix) precisely so resume works —
unique-suffixing would spawn a new folder every run and defeat resume;
(b) `processes=1` runs members **serially in-process** (same worker, no
Pool) — fast and deterministic for tests and small sweeps; the Pool path
shares the identical worker and is exercised by the owner's CLI run. The
Windows-spawn constraint (no closures/lambdas as workers; config crosses
as a re-validated dict) follows #51's environment note.

**#71 — 2026-07-11 — `sweep_metric_chart` + `export_sweep_charts` (M9.5a).**
New PURE builders in `viz/charts.py`: `sweep_metric_chart(summary_frame,
axis_column, metric_column, *, replicate_column="seed", metric_label=None)`
plots the metric against an axis, aggregating across replicate seeds into a
mean line plus a shaded min-max band (replicate spread — the honest picture,
since invasion is a probability, companion §4). `export_sweep_charts` writes
one HTML per (metric × axis), called by the runner. Kept in `viz` (frame in,
Figure out; no Streamlit) so the M9.5b tab reuses it, and imported *lazily*
from the runner so `pdsim/sweep` persistence code stays plotting-free
(hard rule 4). The metric's display label is passed in by the runner rather
than looked up, so `viz` never imports `sweep.metrics` (no cycle).

**#72 — 2026-07-13 — Sweep tab launches a detached subprocess of the
unchanged CLI (M9.5b).** The Streamlit **Sweep tab** (third tab; spec
`docs/specs/M09d-sweep-tab.md`) authors the COMPLETE SweepSpec surface,
validates it through the ONE shared path (`sweep_validation_messages`, with
structural pydantic errors extracted by the same
`helpers.validation_messages` the Run lab uses — the #38/#48 reuse rule),
writes the authored spec to a NAMED, re-launchable file
(`sweeps/<name>.authored.yaml`, via `save_sweep_spec`), and launches
`subprocess.Popen([sys.executable, "-m", "pdsim.sweep", <spec>, "--out",
<dir>])` with output captured to `sweeps/<name>.launch.log`. **Execution
changes nothing** (#59: the sweep layer is a config generator; the tab is a
config *author* on top of it): a tab-launched sweep is resumable,
inspectable, and killable by the identical means as a terminal one, and its
`sweep_spec.yaml` is accepted verbatim by the CLI. Monitoring is a manual
"Refresh status" click reading `sweep_status.json` (the tab only READS it;
the runner subprocess remains its sole writer, #70) plus the existing pure
`sweep_metric_chart` over `sweep_summary.parquet`. All tab logic worth
testing lives in the new Streamlit-free `pdsim/ui/sweep_helpers.py` (the
#38 helpers split, applied again; tested in `test_sweep_ui.py`), and
`SWEEPS_DIR` mirrors `RUNS_DIR` including a `PDSIM_SWEEPS_DIR` test
override (#49). Alternatives rejected: running `run_sweep` **in-process**
(blocks Streamlit's single script thread for the sweep's whole duration,
and any rerun/Stop kills it mid-flight, #53); a **background thread**
(spawning a `multiprocessing.Pool` from a daemon thread across the Windows
spawn boundary is fragile (#51), and the sweep would die with the app
session — a detached process survives it); an **auto-refresh timer** (an
add-on dependency to poll a minutes-scale job; the manual click is honest
and dependency-free). Two small shared-path additions ride along:
`sweep_spec_yaml(spec)` in `pdsim/sweep/spec.py` (`save_sweep_spec` now
writes exactly this string, so the tab's YAML preview/download can never
diverge from the persisted file), and the sweep **name rule** wired into
`sweep_validation_messages` (`_NAME_PATTERN` was declared in M9.5a but
never checked — dormant until free-typed tab names made it live).

**#73 — 2026-07-13 — Structural three-bucket composition UI (M9.5b).** The
tab renders bucket membership as ONE radio per non-vary strategy
({none, fixed, fill} plus a count/percentage field), and the varying
invader is excluded from the bucket rows by construction — so the
"buckets disjoint" rule (#66) is impossible to violate from the UI (the
shared validator still enforces it for the CLI path). The live preview
calls the real `resolve_composition` at the largest authored count — the
explainer §4 preview arithmetic, exercised through the engine's own
largest-remainder code rather than a UI reimplementation — and the running
fill-percentage sum warns when ≠ 100. Alternative rejected: free-form
fixed/fill dict editors mirroring the YAML — every overlap error becomes
reachable and needs error messaging; the structural form makes those
states unrepresentable.

**#74 — 2026-07-13 — Full authoring surface in v1; the sweep BROWSER is a
named, deferred follow-on (M9.5b).** The tab authors the complete
SweepSpec surface (name, base scenario/config, composition axis, N
parameter axes, seeds, N metrics), but monitoring deliberately stops at
status + ONE headline metric-vs-axis chart. Member-run drilldown,
multi-sweep interactive browsing, multi-curve overlays, summary-table
filtering, and side-by-side member comparison are deferred to a dedicated
**sweep-browser** increment on the ROADMAP, and the Results browser is
deliberately NOT wired to scan `sweeps/<name>/runs/`. Rationale: the
authoring surface is fully specified by the SweepSpec model that already
exists, while the browser's affordances should be designed from real
campaign evidence (which sweeps get re-opened, what actually gets
compared) rather than guessed up front. Two scope details: parameter axes
exclude `run.seed` (seeds are a first-class axis; a `run.seed` parameter
axis would be silently overwritten by the seed loop), and a name matching
an existing `sweeps/<name>/` folder shows a resume notice — the true #70
runner behaviour, surfaced rather than hidden.

**#75 — 2026-07-13 — The sweep-browser increment is sequenced AFTER M10
(v2 spine update).** The deferred comprehensive sweep browser named in #74
(member-run drilldown, multi-curve overlays, summary-table filtering,
side-by-side member comparison) is deliberately scheduled after M10, not
immediately next. The updated v2 spine is
**M9.5 → M10 → sweep browser → M12 → M11 → M13 → M14** (amending the #58
spine, which predates the browser increment). Rationale: (a) M10 — the
score-as-energy growth economy — is the load-bearing invariant change of
the v2 spine: variable population size is the most *infectious* invariant,
and every downstream milestone (tags/M12, parameter-perturbation
mutation/M11, group games/M13–M14) must be built variable-N-aware from
birth rather than retrofitted around a fixed-population assumption; that
change cannot wait behind a convenience layer. (b) The sweep browser is a
read-only convenience over persistence that already lands correctly
(#70: `sweep_status.json`, `sweep_summary.parquet`/`.json`, ordinary
reproducible member run folders) — nothing breaks and no debt accumulates
by waiting on it. (c) It is nonetheless slated as the FIRST increment
after M10, preserving #74's rationale that the browser's affordances
should be designed from real campaign evidence rather than guessed up
front — running actual invasion campaigns during and after M10 is exactly
what surfaces which affordances matter (which sweeps get re-opened, what
actually gets compared). Alternative rejected: building the browser
immediately after M9.5b while the sweep layer is fresh — that would hold
the spine's invariant change behind a convenience and would guess the
browser's shape without campaign evidence. The browser increment keeps a
descriptive name (no M-number) until it is scoped.

**#76 — 2026-07-16 — Milestone renumbering: execution order = numeric
order, no gaps (v2 spine update).** The v2 milestones are relabelled so the
numbers match the build order. This supersedes the **numbering** — *not*
the substance or rationale — of **#58** and **#75**: the economy-first
argument and the browser-after-campaign-evidence argument both stand; only
the labels move. The old #58 "M12 deliberately before M11" swap
**dissolves** — the numbers now simply match the order. Tags keeps its M12
label (sparing cross-reference churn in DESIGN §6.5 and the code); two NEW
milestones join the spine (population structure at M11, economy policy at
M15); the sweep browser and the vectorized engine get numbers (M13, M18).

| Exec order | Milestone | OLD label | NEW label |
|---|---|---|---|
| 1 | Growth economy (M10a sync, M10b async) | M10 | **M10** |
| 2 | Population structure — adjacency + local birth (NEW) | — | **M11** |
| 3 | Tags / attributes | M12 | **M12** |
| 4 | Sweep browser | (unnumbered) | **M13** |
| 5 | Perturbation mutation | M11 | **M14** |
| 6 | Economy policy (tax / redistribution / immigration / inheritance) (NEW) | — | **M15** |
| 7 | Public Goods Game + group matching | M13 | **M16** |
| 8 | Reputation / punishment / exclusion | M14 | **M17** |
| 9 | Vectorized engine (review-at) | (unnumbered) | **M18** |

Spine: **M10 → M11 → M12 → M13 → M14 → M15 → M16 → M17 → M18.** Population
structure is placed *before* the sweep browser by #75's own logic: the
browser is a read-only view over run data, and structure changes what run
data exists, so the browser is built after structure and is structure-aware
from birth. Entries #1-#75 use the old labels; from this entry on, the new.
Alternative rejected: keeping the swapped numbering — it forced every
conversation to carry the "M12 before M11" caveat for no benefit.

**#77 — 2026-07-16 — M10a: energy REPLACES imitation — a reproduction-mode
fork, not a selection rule (spec `docs/specs/M10a-growth-economy.md`).**
`dynamics.reproduction_mode` ∈ {`imitation`, `energy_economy`} selects
between two evolutionary paradigms: v1's imitation dynamics (fixed N, a
SelectionRule copies strategies between slots) and M10a's birth-death
dynamics (agents hold energy — a persistent STOCK, unlike the score flow —
earn it by playing, pay a living cost, breed at a threshold, die at
insolvency or of age; population size varies; extinction is a legitimate
run ending). Differential survival IS the selection: in `energy_economy`
mode the whole SelectionRule family and ScoreAccounting are ignored (the
#34 greyed-never-hidden pattern, now paradigm-level: `_IMITATION_PARAMS`
grey under the economy, the eleven `_ECONOMY_PARAMS` grey under imitation;
μ is in NEITHER set — both modes consume it, imitation slots and economy
newborns alike). Implementation shape: a **sibling class**
`EconomyDynamics` beside `PopulationDynamics` — never a branch inside it —
so the imitation path stays byte-identical (pinned by the untouched golden
tests plus new regression tests); the engine dispatches on the mode;
tournament mode ignores it (`reproduction_mode` joined
`IGNORED_IN_TOURNAMENT`). The two new cross-field validators (σ ≤ θ on
DynamicsConfig; K ≥ N on ExperimentConfig) run **only in `energy_economy`
mode** — a refinement of the spec's letter forced by #34 (ignored
parameters are never validation errors) and hard rule 8: a pre-M10a config
with N = 300 must keep loading even though the (ignored) default K is 200.
Alternatives rejected: energy as a sixth SelectionRule (it is not a rule
over scores — it changes N, agent identity, and the meaning of a
generation); a branch inside PopulationDynamics (would thread economy
conditionals through the byte-identity-guaranteed loop).

**#78 — 2026-07-16 — The registry's first DERIVED defaults: nullable None
= "auto", resolved to plain numbers at config validation (M10a).**
`dynamics.initial_energy` (auto → the offspring stake σ, so founders start
life exactly like newborns) and `dynamics.senescence_factor` (auto → the
factor that makes the death chance reach exactly 1.0 at `max_age`:
`(1/base_hazard)^(1/max_age)`; 1.0 when either input is off) use
`nullable=True` + `default=None` — reusing the existing
`population.memory_depth` machinery rather than inventing an `"auto"`
string sentinel in a float field (the design freeze said "a sentinel (e.g.
'auto')"; None + nullable IS that sentinel). The arithmetic lives in pure
free functions (`resolve_initial_energy`, `resolve_senescence_factor` in
`config/experiment.py`); a `mode="before"` pydantic validator applies them
to the raw input mapping (a `mode="after"` hook cannot assign on the frozen
models), treating an absent key and an explicit None identically. Because
resolution happens before validation, **a stored `config.yaml` always holds
plain numbers** — hard rule 8: the auto rule can never retroactively change
an existing run. Two ride-alongs this forced: (a) the app's nullable-widget
machinery gained a float branch ("Set … manually?" checkbox; the int
"Limit …?" branch is untouched); (b) `widget_values_from_config` applies
the **inverse** mapping — a stored value that equals what the auto rule
would produce is presented as blank/auto (loss-free: reassembly resolves
straight back), so loading a scenario shows the auto boxes unchecked
instead of a spurious "manually set 1.0".

**#79 — 2026-07-16 — Per-opponent histories PERSIST across generations in
economy mode; scores still reset (M10a; amends the SCOPE of #22, does not
overturn it).** #31's rationale for clearing histories — under selection
the neighbours' strategies change, so a remembered relationship is memory
of a different agent — is selection-specific and dissolves in the economy:
nobody's strategy is overwritten, passport ids are never reused, and agent
7 next generation IS the same agent 7. The blessed precedent is the
tournament's cross-cycle memory (#34): an economy agent is a persistent
creature, and its memory persists with it. Mechanism: a new
`Agent.reset_score_for_new_generation()` beside (never replacing)
`reset_for_new_generation()`; `PopulationDynamics` still calls the full
reset, unchanged. Named consequences: `HistoryView.round_number` is
lifetime-cumulative against a given opponent in economy mode (#22's
"cumulative within one generation only" is now per-mode — it remains true
under imitation); `round_number == 0` detects a first meeting EVER;
**GrimTrigger is lifetime-grim** (a generation-3 betrayal is punished at
generation 200 — pinned by test); `Agent.rounds_played` becomes a lifetime
count there, so `EconomyDynamics` builds `GenerationReport.rounds_played`
(#44's denominator) from a per-generation tally (`_EngagementTally`,
matches + rounds per passport id — the Task 0a fallback: no per-agent
match count existed, and distinct-opponents undercounts because a pair can
play twice per generation, #57). The honest cost: `view_of`'s O(length²)
copy now grows with the RELATIONSHIP, not the match — unbounded under
round_robin (quadratic in run length), barely felt under random_k;
`memory_depth` is the bound, and the calibration readout warns (never
forbids) when it is unlimited. Alternative rejected: clearing histories in
the economy too — it would erase direct reciprocity between persistent
creatures, the very thing the paradigm models.

**#80 — 2026-07-16 — The M10a boundary sequence and its RNG contract
(extends #32; frozen — any change is a breaking change requiring a new
entry).** `EconomyDynamics.step()`: (1) match phase, identical to #23; (2)
report the population AS IT PLAYED (per-strategy fields keep their existing
meanings; energy is additive, never a replacement); (3) deterministic
energy update `e ← e·(1+r) + raw_score − L − engagement·matches` — the one
frozen snapshot deaths and births read; (4) age-mortality sub-phase, ONLY
when active (`base_hazard > 0 or senescence_factor ≠ 1 or max_age > 0`):
exactly one `rng.random()` coin per living agent in ascending agent-id
order, unconditionally — even at p = 0.0 or 1.0 — so the stream depends
only on the active flag and the population size, never on hazard values;
(5) insolvency deaths, deterministic, **strictly negative** (`e < 0`: a
parent that just paid σ can sit at exactly 0 and survives empty-handed —
reproduction is not suicidal at the margin); (6) births: eligible at
`e ≥ θ`; `slots = K − survivors`; **admission by energy priority** (energy
desc, id asc) — deterministic and RNG-FREE, a deliberate choice over a
random lottery that would inject fresh RNG for no scientific gain; then
the admitted SET is iterated in **ascending parent-id order** for
placement-check → σ+overhead payment → passport-id assignment → μ-mutation
draw. TWO ORDERINGS, kept separate on purpose: admission decides *the set*
by energy, id-order is the RNG-reproducibility contract (pinned by a test
where the orders differ). Placement is checked BEFORE the stake is paid —
`place_offspring` never fails in M10a's well-mixed world, but
pay-then-place would bequeath M11 the charged-for-a-child-never-born bug
(pinned by a stub test). One birth per parent per generation, even at
e ≥ 2θ — the dynastic channel runs through breeding frequency, not
endowment. (7) survivors age += 1; (8) score-only reset (#79); (9)
per-agent snapshot of the post-boundary population (the exact set entering
G+1, with carried-forward energy and entering age — an agent that earned,
bred, and died within one boundary has its gross earnings only in the
per-strategy means; accepted grain). **Death-before-birth is a plain design
preference and deviates from Hammond–Axelrod**, whose period order is
immigration → interaction → reproduction → death: in H-A a newborn can die
in its birth period and the first period differs — named honestly, NOT
justified as "spatially correct for M11" (the canonical spatial model does
the opposite). Rejected: fully-simultaneous no-ordering (ambiguous at
capacity). Founder ages are staggered (`i % max_age`) when age-mortality is
active, starting runs at the demographic steady state instead of a
colony-ship cohort collapse. The population list invariant: ALWAYS sorted
by ascending agent_id, explicitly — deaths make ids non-contiguous, so
list position is never a proxy for id. With age-mortality off and μ = 0,
an economy generation consumes exactly the match-phase draws.

**#81 — 2026-07-16 — The variable-N `random_k` contract: clamp, don't
raise (M10a; defines territory #57 never reached).** `RandomK.pairings`
drops its k > N−1 ValueError and clamps the draw to `size = min(k, N−1)`.
Safety against #57's seeded-history contract: at every N ≥ k+1 — the only
regime the fixed-N engine could occupy — the clamp is a literal no-op, so
every existing seeded run is byte-identical (pinned by a regression test
against the pre-clamp algorithm verbatim). The new behaviour exists only in
the N < k+1 regime deaths create. Corners (verified and tested): N = 2 —
each agent plays the one other; N = 1 — `rng.choice(0, size=0)` returns
empty WITHOUT raising and consumes NO RNG, so the lone survivor plays
nothing, earns nothing, still pays its living cost, and starves at the next
boundary unless capital returns clear the bill (the intended thermodynamics
of a population of one under a metabolic bill — observed live in the
all-defector scenario run, where the last defector spends generation 6
alone); N = 0 — extinction, the run has already ended. Config validation
still enforces k ≤ N−1 at generation 0, unchanged. Alternatives rejected:
**raising** (a valid config must not crash because the population got small
mid-run — a metabolic filter is *supposed* to be able to shrink a
population, that is the science); **skipping** (0 matches when N−1 < k — a
discontinuous cliff with no mechanism motivating the jump). `RoundRobin`
needed no change; its income scaling with N is a calibration fact the
Economy panel surfaces, not a correctness one.

**#82 — 2026-07-16 — Per-agent snapshots instead of birth/death events;
extinction ends a run early (M10a observability).** `GenerationFinished`
gains one optional field: `agents: tuple[AgentSnapshot, ...]` (agent_id,
parent_id, age, energy, strategy) — the POST-boundary population, populated
only in economy mode and empty under imitation (keeping those payloads
byte-identical to pre-M10a; `CycleFinished` gains nothing — a tournament
has no economy). **Rejected — explicit birth/death events**: the snapshot
sequence reconstructs the entire birth/death record by diff (an id present
at G but not G−1 was born, `parent_id` names its parent; present at G−1 but
not G died), so event types would duplicate truth (#47) and complicate the
observer-only granularity model (#35) for no gain — in the synchronous
model everything happens at one atomic boundary; explicit events belong to
M10b, where async event time makes per-event ordering meaningful.
**Rejected — a population-size payload field**: `N = sum(composition
.values())` (#47 raw-not-derived); `RunTimeseries.population_size` is a
derived property, and the stacked composition chart already IS the
population-growth chart. Extinction: the engine breaks after yielding the
`GenerationFinished` whose post-boundary population is empty;
`RunFinished.completed` counts generations actually played (still always
equal to the configured count under imitation), an extinct run closes with
empty composition/scores, `_headline` reports "population extinct at
generation N", and the CLI derives its completed count from the last period
event (printing "Population extinct." when the run ended early) instead of
trusting the config. The run card, charts, loader, and sweep metrics all
survive an extinct run (tested).

**#83 — 2026-07-16 — Persistence schema 3: `agents.parquet` + economy
summary fields; the version tracks the PRESENCE of per-agent data (M10a; a
pure application of the #47/#65 pattern).** New sibling table
`agents.parquet` — the filename the module docstring reserved since M7 —
one row per (period, post-boundary agent): period, agent_id, parent_id
(nullable pandas Int64; founders `<NA>`), age, energy, strategy. No
born/died flags (derivable by diff, #47). Written ONLY when the run
produced snapshots, and `summary.json`'s `schema_version` is 3 exactly
then: an imitation run under M10a code writes NO agents.parquet and
schema_version **2** (`PER_STRATEGY_SCHEMA_VERSION`), byte-identical to
pre-M10a recordings — the honest thing for the version to track. (The
config.yaml header comment, written before any event exists, anticipates
the version from the config's reproduction mode.) `summary.json` gains
`total_agents_born` (largest passport id + 1 — free from the id contract)
and `population_final` (size of the last snapshot; 0 for extinct runs);
both `None` for imitation runs; the existing `population_size` field stays
config-derived INITIAL size, documented as such. `timeseries.parquet` and
`cooperation.parquet` untouched — **rejected: widening timeseries with
energy columns**, which would write NaN-filled columns for every imitation
run (#47c forbids exactly that). Loader: accepts 1, 2, and 3; rejects > 3;
`agents.parquet` reads with the same missing-file → empty-mapping shape as
`_read_cooperation`, and snapshots are refed through `GenerationFinished`
so every derived view (per-strategy mean energy/age, population curve) is
recomputed by the exact code the live run used. A schema-1/2 folder simply
renders without the economy views — no migration, no error.

**#84 — 2026-07-16 — M10a bench re-run and validation observations (the
#58/#65 vectorization-trigger discipline).** `python -m pdsim.bench` gained
a `--reproduction-mode` flag; its economy cell is tuned to CONSTANT N (an
unreachable breeding bar, zero living cost) so the timing isolates the
economy bookkeeping at the same N as the imitation cell. This machine,
N ∈ {100, 200}, 50-round matches, 3 timed generations, repeated per #65's
noise warning (repeats agreed): under **random_k** the economy costs ≈
5-10% over imitation (0.36 → 0.38 s/gen at N=200) — the ledger, boundary,
and snapshots are cheap; under **round_robin** it costs ≈ 45-60% (7.6 →
~11.2 s/gen at N=200), and that gap is the **#79 persistent-history
growth** (every pair re-meets every generation, so the O(length²) view
copy grows per generation), not the boundary machinery — exactly what the
calibration readout's memory note warns about, bounded by `memory_depth`.
The cost model's structure is unchanged and the trigger stays **M18,
review-at**. Validation observation worth recording: the spec's all-D
extinction trace ("extinct at generation 5") is exact only in mean-field —
under random_k, participation luck spreads the collapse over boundaries
4-6 (seed 42: 40 → 40 → 40 → 21 → 1 → 0, extinct at generation 6, the last
generation being a lone defector playing zero matches — the #81 N=1 corner
occurring naturally). The growth side ran exactly as calibrated: N grew
40 → 200 = K and plateaued, Always Defect was squeezed out, 220 passports
issued, `population_final` 200.

**#85 — 2026-07-17 — M10 splits into M10a (synchronous) / M10b (async), and
energy-replaces-imitation TIES OFF #64's deferred `cumulative` accounting
(recovered from the design-freeze tail; supplements #77).** The growth
economy ships in two parts: M10a delivers the entire variable-N invariant on
the existing generational clock; M10b — the asynchronous / Moran-style event
time-model — is a separate later spec. Rejected: **one-milestone-both-modes**
(the async time-model dissolves the generation as the unit of time, a second
invariant change that must not ride along with the first) and **async-first**
(the synchronous economy is testable against the existing golden machinery
and freezes the ledger semantics the async model will inherit). Separately,
the paradigm fork resolves an open option: #64 deferred a `cumulative` score
accounting to §6.1. **Energy IS that cumulative stock — but repurposed, so
the option is resolved-by-replacement rather than built.** Accounting
produces "the effective scores selection reads"; energy is "a stock
reproduction spends". Different jobs → the economy *replaces* imitation
instead of composing with it as a fifth accounting rule, and #64's
`cumulative` option should be read as closed by this entry (#64 itself
stands unedited — append-only log).

**#86 — 2026-07-17 — `engagement_cost` is per-MATCH, not per-round — a
deliberate deviation from DESIGN §6.1's "per-round living cost" phrasing
(recovered from the design-freeze tail; supplements #80's ledger).** The
ledger's two cost components are additive and independently switchable:
`basic_living_cost` per generation (existence) and `engagement_cost` per
match played (interaction). Per-ROUND was rejected: it would couple the cost
to `rounds_per_match` — making the match-length knobs silently *economic*
(changing match length would re-price survival) — and under continuation
mode it would inherit a RANDOM match length, entangling a cost term with the
RNG stream. Also rejected: **coupling the two costs by a ratio** — the units
do not work (energy/generation versus energy/match needs a match count to
convert, but N — and with it the match count — changes every generation by
design), and a coupled pair would break M9.5 sweep-axis independence, where
each cost must be sweepable alone.

**#87 — 2026-07-17 — Offspring endowment is the stake transfer, nothing
else (recovered from the design-freeze tail; supplements #78/#80).** A
newborn starts with exactly σ, paid out of its parent's stock. Rejected:
**fixed endowment independent of σ** (creates energy from nothing or
destroys it silently — the ledger stops balancing and reproduction stops
being a transfer); **zero endowment** (not needed as an option — it is
simply the σ = 0 corner of the existing knob); **binary fission** (parent
splits its balance in half — it entangles the child's start in life with the
parent's current wealth, so the dynastic channel would run through
endowment; the frozen design routes dynasty through *breeding frequency*
instead, #80's one-birth-per-generation rule, which keeps σ a clean,
sweepable constant).

**#88 — 2026-07-17 — Capital returns create a STRUCTURALLY PERMANENT
dynasty mechanism — named as a mechanism, not buried (recovered from the
design-freeze tail; supplements #80).** With `capital_return_rate` r > 0,
an agent whose stock exceeds the escape velocity `e* = total cost / r` pays
its bills from returns alone — self-sustaining regardless of play, immune
to the metabolic filter, clearing θ forever. Combined with the
highest-energy-first admission gate (#80), rich lineages breed with
priority at capacity: rentier wealth converts directly into reproductive
privilege, and the dynasty is structurally permanent, not a lucky streak.
This is a deliberate experimental instrument (the Economy panel surfaces e*
whenever r > 0), not an accident. One bound worth recording: capital return
CANNOT compound a debt — insolvency deaths run at every boundary, so every
living agent enters every generation at e ≥ 0, and `(1 + r)` only ever
multiplies non-negative stocks.

**#89 — 2026-07-17 — Recovered design-freeze addenda (small rationales that
lived only in the truncated tail; supplements #76/#77/#78/#80/#83).**
(a) **Carrying capacity K is aspatial-specific, not universal**: a lattice
gets capacity for free from site occupancy — K is the well-mixed model
paying cash for what structure will provide structurally, so under M11
capacity may become emergent from site count rather than a parameter.
(b) The capacity and structural gates are **two named free functions**
(`admit_births`, `place_offspring`) rather than a speculative ABC — hard
rule 6: M11 updates DESIGN first, then generalises; the seam is named now,
the abstraction waits for its second implementation. (c) **Passport-id
reuse was rejected** ("hotel-room splicing"): reusing a dead agent's id
would stitch together the histories of unrelated creatures who happened to
occupy the same slot — with persistent per-opponent memory (#79), an id
must mean one creature forever. (d) The **effective-max-age check is
warn-don't-forbid**: an explicit senescence factor that reaches certainty
before `max_age` is allowed with a soft note — someone may legitimately
want a population where nobody reaches the cap. (e) The **calibration
readout ships IN M10a**, not later — app-first validation ("set up an
economy, observe growth") is not honest if the person cannot see where the
survival window lies. (f) For the record, per the append-only rule: #58 and
#75 were NOT retro-edited by the #76 renumbering; their labels are simply
read through the #76 table.

**#90 — 2026-07-17 — The all-defector trace sits on a KNIFE EDGE at
boundary 4 — fix the text, keep the numbers (refines #84's observation;
design-layer reproduction confirmed the series).** Mechanism, precisely:
in `the_growth_economy` with 40 Always Defect, the mean-field defector
energy at boundary 4 is EXACTLY 0.0 (e₀ 400 + 4×100 income − 4×200 cost),
and the measured population mean and minimum at that boundary are both 0.0.
Death is strictly `e < 0`, so at boundary 4 survival is decided by
participation luck ALONE (#44/#57: under random_k an agent's match count
varies around 2k), which is why the boundary splits the population almost
exactly in half (seed 42: 40 → 40 → 40 → 40 → 21 → 1 → 0, extinct at
generation 6, the finale being the #81 lone-survivor corner). The
extinction GENERATION is therefore seed-sensitive; the scenario pins seed
42, so the observed run is reproducible. **The scenario was deliberately
NOT re-tuned to make the collapse crisp**: the smear across boundaries 4-6
is not noise obscuring the result — it IS participation luck appearing in
the economy exactly where theory says it should; a defector population
dying on a precise schedule would be the suspicious outcome. The
calibration (L = 200 at the window midpoint, ±100 symmetric) stays. What
changed instead: the scenario's `things_to_try` now describes the
generations-4-to-6 collapse and teaches the mechanism (it previously said
"dies at generation 5" — live, user-facing, and wrong), and explainer §4
gained the general lesson: a mean-field trace tells you when the AVERAGE
agent dies, not when the population does. The spec's mean-field trace
stays as written — frozen per #62; this entry is the record.

**#91 — 2026-07-17 — The cost model gains a GENERATIONS term under the
economy with unbounded memory — measured, confirmed, and scoped (completes
#84's attribution; DESIGN §3.1 amended).** #84 attributed the economy's
round-robin overhead to #79's persistent-history growth; that attribution
was a hypothesis with a falsifiable prediction — `view_of` copies the
visible history every round, histories grow by ≈ `rounds` per re-meeting,
so the per-generation cost should rise LINEARLY with the generation index
under round-robin (every pair re-meets every generation) and stay near-flat
under random_k, while imitation stays flat everywhere (histories wiped each
boundary). Measured (N = 50, 50 rounds, median s/gen, each cell run twice
per #65 — repeats agreed within 2%): **imitation round_robin FLAT** (0.44
at G = 20 → 0.45 at G = 100); **economy round_robin GROWS** (1.13 at
G = 20 → 3.47 at G = 100, ×3.1 — matching the ≈ (2G−1) copy-ratio
prediction at the bench's median generation); **economy random_k grows
slowly** (0.15 → 0.24, ×1.6). The random_k cell sharpens the claim rather
than contradicting it: the growth term scales with the PAIR-RECURRENCE
probability — ≈ 1 under round-robin, ≈ 2k/(N−1) under random_k — and at
N = 50, k = 5 that is ≈ 0.20, one-fifth the round-robin rate, visible at
100 generations. It vanishes exactly in the large-N regime random_k is
chosen for. Consequence, now stated in DESIGN §3.1: the
`7.5 µs × N × k × rounds` model holds per-generation for imitation, for
tournaments, and asymptotically for economy + random_k at large N; under
**economy + round_robin with unbounded `memory_depth`** the per-generation
cost grows with the generation index, so a long run is SUPERLINEAR in
`generations` (quadratic total). `memory_depth` is the bound (it caps what
strategies see, hence what `view_of` copies), and the Economy panel's
memory-growth note (#79) is the user-facing warning. A measurement, not a
refactor: the vectorization trigger stays **M18, review-at**; bench output
remains environment-specific and uncommitted.

**#92 — 2026-07-18 — Docs file-naming convention: spec files end
`-spec.md`, explainers end `-explainer.md` (owner decision; supplements
#62's naming rule).** The M10b spec and its companion explainer initially
shared one basename (`M10b-async-event-time.md`), differing only by
directory — ambiguous in editor tabs, project-knowledge uploads, and
cross-references. Going forward, every new spec file name is
`M<zero-padded milestone><letter>-<slug>-spec.md` and every explainer ends
`-explainer.md` (already the de-facto explainer pattern, e.g.
`M10-growth-economy-explainer.md`). Applied immediately to the M10b pair
(`docs/specs/M10b-async-event-time-spec.md` /
`docs/explainers/M10b-async-event-time-explainer.md`, cross-references
updated). Files predating this entry keep their names — renaming shipped
specs would churn every existing cross-reference for no knowledge gain.
#62's other mechanics (status line, frozen intent, DOCS CHANGED ritual)
are unchanged.

**#93 — 2026-07-20 — Async imitation overlay reconciled to the
symmetric (sync-matching) adopter rule; asymmetric "imitate-better"
variant backlogged with a review checkpoint at M12 scoping**

Background. The Fermi imitation mechanism copies one agent's strategy onto
another with probability logistic(β · score_gap), where β = selection_beta
is the selection intensity. There are two ways to choose WHICH agent is the
potential adopter, and they behave differently:
  - Symmetric (the sync rule, selection.py): the adopter is chosen
    independently of score (in sync, a uniformly drawn incumbent). A
    higher-scoring model is copied at probability > ½ and a lower-scoring
    model at probability < ½ — downhill copies are possible. At β = 0 the
    copy is a pure coin flip with no score dependence at all: true neutral
    drift. β is a clean selection-intensity dial from drift (β = 0) to
    deterministic imitation (β → ∞).
  - Asymmetric / "imitate-better": the adopter is forced to be the
    lower-scorer, so every copy is uphill (probability ≥ ½), and the
    higher-scorer never adopts. At β = 0 the loser still copies the winner
    half the time with no reverse flow — fitness-blind in intensity but
    still fitness-DIRECTED. Neutral drift is unreachable by any β, because
    the loser-adopts direction is hardwired.

What happened. M10b Phase C shipped the async imitation overlay using the
ASYMMETRIC rule (frozen in spec Design 4), while sync imitation uses the
SYMMETRIC rule. Because the overlay reuses the same selection_beta, the
identical parameter meant two different things across the two time models —
most visibly at β = 0 (neutral in sync, residually selective in async).
Since a central purpose of having both a synchronous and an asynchronous
clock is to COMPARE them, a β sweep under each clock would have compared two
different rules under one label and misread part of a rule artifact as a
time-model effect. Root cause was an imprecise M10b prompt that both said
"the existing Fermi rule" (implying: match sync) and "the loser may copy the
winner" (implying: asymmetric); Phase C reasonably resolved toward
asymmetric.

Decision (A), implemented in Phase E. The async overlay is reconciled to the
symmetric rule, made match-local: of the two participants who just played,
one is chosen at random as the adopter and the other as the model, and the
adopter copies with logistic(β · (model_score − adopter_score)), downhill
copies possible. β = 0 is now true neutral drift in BOTH clocks, and
selection_beta means one thing everywhere. This SUPERSEDES spec Design 4's
asymmetric pin (Design 4 carries a forward-pointer to this entry; the spec
is not retro-edited — the deviation is recorded here, per the frozen-spec
ritual).

Decision (B), backlogged with a review checkpoint. The asymmetric
"imitate-better" rule is a legitimate, studied imitation dynamic (imitate
whoever did better than you), not a discarded mistake — a genuine scientific
fork against the symmetric rule. It is deferred, not dropped: the intended
shape is a labeled parameter, e.g. dynamics.imitation_adopter ∈ {symmetric,
imitate_better}, default symmetric, governing BOTH time models. It was
deferred rather than built now because exposing it also touches the stable
sync selection path (selection.py), scope we chose not to reopen mid-M10b.

  REVIEW CHECKPOINT — M12 scoping. Examine whether to pull this trigger when
  scoping M12 (tags + Hammond–Axelrod ethnocentrism). M12 is the first
  milestone where the distinction may be load-bearing: ethnocentrism is
  about how strategies spread between in-group and out-group, and
  imitate-the-better vs symmetric drift-plus-selection can push
  in-group/out-group cooperation differently. The M12 spec-creating prompt
  must surface this entry as an explicit early step and ask whether M12
  needs the imitate_better option as a labeled comparison. A "no, not yet"
  outcome is fine and expected — the checkpoint only guarantees the question
  is asked on schedule rather than by chance. If not triggered at M12, the
  checkpoint rolls forward to the next milestone whose research question
  touches imitation dynamics.

**#94 — 2026-07-20 — Live chart redraws are wall-clock throttled (extends
#39's batching); data still accumulates every period.** Owner-reported
during async validation: an async evolution run showed a mostly-black
chart area with brief flashes of results. Root cause, two Streamlit facts
compounding: (1) a reused element key within one script run raises
`StreamlitDuplicateElementKey` (verified against Streamlit 1.58), so the
live loop must give every redraw a fresh key — and a fresh key makes the
frontend tear down the old chart component and mount a new one, which is
BLANK until plotly.js finishes painting; (2) fast runs emit periods
quicker than the browser paints — async event time especially, where a
small-N generation-equivalent computes in milliseconds, so with the
default 0.05 s playback delay the loop replaced up to six growing figures
many times per second and the browser never finished painting before the
next teardown. Decision: `_run_live` still adds EVERY period to the
timeseries and the recorder, but redraws at most once per
`max(playback_delay, LIVE_REDRAW_MIN_SECONDS)` seconds
(`LIVE_REDRAW_MIN_SECONDS = 0.5`, an app constant like #39's
`PROGRESS_EVERY` — deliberately not a registry parameter: it is pure
presentation, an observer control in #35's sense, and it never changes
what a run computes or records). Between redraws nothing touches the DOM,
so the previous frame stays fully visible; skipped periods appear in bulk
at the next redraw; the playback sleep now happens only after an actual
redraw (its documented meaning — "pause after each chart REFRESH"); the
final draw after the loop is unconditional, so the finished charts are
always complete. A slider delay above the floor stretches the window, so
slideshow-style watching (delay 0.5-1.0 s) still redraws every period.
The predicate lives in `helpers.should_redraw` (Streamlit-free, #38) with
unit tests. Alternatives considered: per-period redraw with a larger
default delay (still floods at small N, and punishes slow runs);
downsampling live figures (changes what the owner sees; the #10 ceiling
is a separate concern); moving the engine to a background thread and
redrawing from an `st.fragment(run_every=...)` with STABLE keys — the
only route to fully flicker-free in-place plotly updates, because stable
keys are legal across reruns and let the frontend update the component
without remounting, but it would rework the #53/#54/#55 kill-and-discard
semantics around a thread lifecycle; deferred until the residual
per-redraw blink (~100 ms, at most twice a second) proves bothersome.

**#95 — 2026-07-20 — M10b LANDED: the asynchronous / Moran-style event
time-model (spec `M10b-async-event-time-spec.md`, Phases A-E; this entry
opens the milestone-close batch #95-#102).** The generation is dissolved
as the unit of time: `dynamics.time_model = "asynchronous"` (evolution
mode only) routes to `AsyncDynamics`, where time advances one focal
activation at a time — a focal agent drawn uniformly plays k =
`matching.opponents_per_agent` matches against uniformly drawn distinct
partners (the k-match bundle, chosen so one generation-equivalent carries
the same ≈ 2k per-agent interaction budget as a synchronous `random_k`
generation — comparable in INCOME, not just time), and every consequence
fires immediately. The clock advances Δt = 1/N(t) per event (N read at
event start); `dynamics.generations` keeps its name as run length in
generation-equivalents. Two demographic engines
(`dynamics.async_population`): `variable_n` = the M10a energy economy in
event-time; `fixed_n` = classic Moran (one death paired with one
fitness-proportional birth per event). Both run through the Option B seam
— the loop delegates every birth to `admit_births()` /
`place_offspring()` and never assumes the aspatial admission policy, so
M11 swaps implementations without reopening the loop (the seam dilemma
and rationale are frozen in the spec). The synchronous path is
byte-identical throughout (pinned by regression); the seed-7 variable_n
and seed-13 moran-random golden masters pin the async streams. Landed
across commits `V2-Milestone10b-PhaseA` through `-PhaseE`; 722 tests
green at close.

**#96 — 2026-07-20 — variable_n demography in event-time: the M10a → M10b
conversion choices (spec Design 2a, implementation-refined).** (a) The
**breeding refractory** of 1.0 time units (founders anchored at t = 0) is
the event-time image of #80's one-birth-per-generation rule — without it
a parent at e ≥ 2θ burst-breeds within one generation-equivalent,
rerouting dynasty through stock size, exactly what #80 rejected. (b) The
**mortality trio converts to birthday coins**: one coin per agent per
INTEGER birthday, priced at `mortality_probability(k−1)` — the same
lifetime coin sequence a synchronous agent draws; the `max_age` cap is
DETERMINISTIC in event-time (deaths fire when their trigger evaluates —
a coin-surviving agent at the cap still dies that event), and the
recorded cause `"age"` covers both the hazard coin and the cap, mirroring
the sync taxonomy. (c) **Founder staggering carries over via negative
birth_time** (a founder staggered to age s is "born" at t = −s), so a
staggered population starts at its demographic steady state; breeding
anchors stay at t = 0 regardless. (d) The **accrual sweep** applies
`e ← e·(1+r)^Δt − L·Δt` to every living agent per event, ascending id, no
RNG — compounding to exactly (1+r) and ≈ L per generation-equivalent.
Named honestly: sync applies (1+r) once per boundary, async compounds
over income arriving mid-period, so the two clocks agree exactly ONLY on
a static balance — inherent to event-time, not a bug, and pinned that way
by the V5 comparability tests (`TestSyncAsyncComparability`): same
growth story asserted, byte-identity deliberately NOT. (e) The **async
report grain**: period reports describe the living population AT the
recording point (unlike sync's as-played grain) — window earnings of a
strategy extinct by the recording point drop from `mean_scores` (they
survive in the pair-keyed cooperation table), and an extinct run's final
partial period has empty composition while still carrying its closing
deaths and clock stamp.

**#97 — 2026-07-20 — fixed_n Moran engine choices (spec Design 3,
implementation-refined).** (a) The chat's tuple-valued mixture knob
became **two scalar registry parameters** (`moran_weight_birth_death` /
`moran_weight_death_birth`, normalised at use) — registry kinds are
scalar and two floats reuse the whole widget/validation/docs machinery.
(b) `fixed_n_death_rule` governs the death SLOT of whichever rule fires:
`pure_random` = one uniform draw (textbook); `energy_decides` =
lowest-energy, ties to lowest id, deterministic and drawing nothing (the
#80 active-flag idiom). The recorded cause names the SLOT
(`random_moran` / `replacement`), not the selection rule. (c) The
`birth_death` victim draw is one `rng.integers` over the breeder's
OTHERS (the breeder cannot replace itself). (d) **fixed_n never calls
`admit_births`** — the Moran replacement vacates the seat it fills, so
capacity admission is meaningless there (`carrying_capacity` is ignored
wholesale); `place_offspring` IS still called before σ leaves the parent
(place-before-pay, #80, both engines). (e) **Founders are never
staggered in fixed_n** — there are no age deaths, so staggering would be
dead configuration; the #80 active-flag idiom applied to setup. (f) In
the period buffer the death is recorded BEFORE its paired birth (the
seat empties, then fills) — an ordering the schema-4 loader now depends
on (#100). (g) A parent driven negative by the stake is LEGAL in
fixed_n: no insolvency death exists there, and the #63 fitness shift
absorbs negative balances; σ = 0 recovers the textbook no-endowment
corner.

**#98 — 2026-07-20 — Imitation overlay implementation choices (spec
Design 4; adopter rule superseded to symmetric by #93).** (a) The chat's
`{off, on}` choice pair shipped as a registry **bool** (checkbox — the
two-state switch IS the bool kind). (b) The overlay reuses
`FermiSelection`'s numerically-stable `_logistic` by intra-package
import rather than growing a second copy that could drift. (c) The
no-op test compares strategy NAMES, not instances — strategies are
stateless flyweights (#21), so same-name means same behavior and the
copy would be invisible; a no-op spends its coins but emits no
`ImitationEvent` (the coins, not the event, are the RNG contract).
(d) `_imitate` is called inside the focal bundle immediately after each
match's economics land, so a strategy adopted after match 2 plays in
match 3 — immediacy is what asynchrony means. (e) The overlay layers on
`fixed_n` too: it is a cultural channel, not a fourth Moran rule —
demography answers who exists, imitation answers what the living play.

**#99 — 2026-07-20 — The M10b RNG contract as implemented (spec Design
8), the #34 validator gates, and the RUF001-003 lint rider.** The full
within-event draw order is pinned in `async_dynamics.py`'s module
docstring (focal draw → partner draw → per-match round draws + the two
#93 overlay coins → RNG-free accrual → the demographic step's
mode-specific draws → RNG-free emission); every draw exists only when
its governing flag makes it meaningful (#80 active-flag idiom), and the
moran-random rule roll is pinned as the FIRST demographic draw of the
event (golden-mastered — a mis-pin cannot reproduce the seed-13 trace).
Validator gates follow #34's consumed-only pattern: the weight pair's
both-zero rejection fires only when `moran_rule = "random"` can actually
roll (async + fixed_n), and the async knobs are accepted-but-ignored
under sync so configs stay portable across time models. Lint rider: the
ambiguous-unicode rules RUF001-003 are ignored in `pyproject.toml` —
the project deliberately names its quantities σ, θ, μ, Δt, × and − in
docstrings, comments, and widget labels (matching DESIGN and this log),
and silencing the rules keeps `ruff check .` green without rewriting the
house notation into ASCII.

**#100 — 2026-07-20 — Schema 4 persistence choices (spec Design 10,
Phase D).** (a) **Three-way version constants**: `SCHEMA_VERSION = 4`
(event-time data present), `PER_AGENT_SCHEMA_VERSION = 3` (sync economy),
2 (sync imitation) — the honest-presence rule (#83) reads as
data-presence tiers; sync folders stay byte-identical to M10a output.
(b) Four sibling tables (`births/deaths/imitations/periods.parquet`),
each dense, each written only when it has rows; **missing file = empty
shape is the CONTRACT** (a channel that never fired writes nothing), not
just backward compat. (c) The loader re-interleaves the three event
tables into occurrence order by a STABLE sort on `(event_index, kind)`
with imitation(0) < death(1) < birth(2) — exact because imitations
happen during the match bundle, and deaths precede births within one
event in BOTH engines. This ordering is now LOAD-BEARING: any engine
change that reorders within-event occurrence breaks the loader contract
and needs a DECISIONS entry plus schema thought. (d) Period membership
on load is the UNION of timeseries/periods/event-table periods — an
async run extinct mid-period has a final partial period with empty
composition (the #96 report grain) that would otherwise vanish;
`timeseries.parquet` gained explicit columns so a zero-row table stays
loadable. Sync loads degenerate to the old set. (e) The Output registry
section sits between Dynamics and Run control — the panel/docs order
every consumer inherits. (f) `RunTimeseries.gen_equiv_times` and
`.demographic_events` are per-period lists aligned with `.periods` in
BOTH modes (tournament appends `None`/`()` fills); the writers'
strict-zip is the guard.

**#101 — 2026-07-20 — Phase E UI and scenario choices: the greying map
with the β carve-out and forward lookahead, the event-time x-axis rule,
and the four V-scenarios (including two honesty retunes).** (a) The
spec's ignored-parameter map is implemented as a time-model split in
`helpers.greying`: under sync all eight async knobs grey; under async
the generational machinery (`reproduction_mode`, the SelectionRule
family, ScoreAccounting, `matching.matcher`) greys wholesale, the Moran
knobs key off `fixed_n`, the weights off `moran_rule = "random"`, the
economy demography knobs (θ, K, mortality trio) off `variable_n`, the
Output `_m` off `every_m_events` — and **β follows the OVERLAY, not the
rule or mode** (the #93-adjacent carve-out closing the Phase C authoring
gap: overlay ON reaches β even under `energy_economy` + a non-fermi
rule). Because some dependencies point FORWARD in registry order
(`reproduction_mode` greys off `time_model`, which renders after it; β
off the overlay), the panel now passes a session-state/registry-default
LOOKAHEAD merged under the gathered values — the first paint uses
defaults, every later paint the live widget state. (b) Charts: when a
run carries `gen_equiv_time` stamps, every chart plots against the CLOCK
with the axis labelled "Generation-equivalents (event time)" — under
`per_event`/`every_m_events` cadences periods are not equally spaced, so
the period index would distort trajectories; sync/tournament keep the
period axis untouched. The app shows a one-line axis explainer
(`GEN_EQUIV_AXIS_NOTE`) for async runs, live and in the browser.
(c) Scenarios: `async_death_birth_fixation` (V1, TFT fixates at pinned
N = 24), `imitation_overlay_only` (V2), `moran_random_mix` (V3),
`sync_vs_async_economy` (V5, the M10a growth economy on the async
clock). Two spec-time expectations were corrected by MEASUREMENT during
scenario authoring, and the scenarios teach the true results: (i) V2's
overlay spreads DEFECTION — in any mixed match the defector out-earns
the very reciprocator it exploits, so copying match winners favours
AllD even though reciprocators earn more from each other — and the
cultural churn runs on the MATCH timescale at any β (β sets the bias of
a ~fair per-match coin, not the rate), so the sweep completes within a
couple of generation-equivalents; the scenario records `per_event` and
owns both facts (a genuine V2 finding: the cultural and demographic
channels disagree about cooperation here). (ii) V3's "sits between"
holds for the ENSEMBLE, not per seed — a 24-agent Moran run is a
fixation gamble (the shipped seed fixates AllD via an early lucky
streak), and the scenario text teaches drift honestly instead of
promising a between-trajectory.

**#102 — 2026-07-20 — Async bench column measured (#91 discipline): the
event loop costs ≈ 6-11% over the sync economy at equal N; vectorization
trigger untripped.** `python -m pdsim.bench --time-model asynchronous`
times the M10b loop per GENERATION-EQUIVALENT at constant N (the same
no-demography tuning as the economy cells); the matcher axis collapses
to one honest `event_time` column (async ignores matchers, #34).
Measured 2026-07-20 (50 rounds, k = 5, median s/generation-equivalent,
this machine): N = 50: 0.120 vs 0.111 economy / 0.097 imitation;
N = 100: 0.225 vs 0.212 / 0.189; N = 200: 0.450 vs 0.409 / 0.387;
N = 400: 0.933 vs 0.840 / 0.788. Scaling stays LINEAR in N (×2 N → ×2
time): the O(N) accrual sweep per event — O(N²) per
generation-equivalent — is visible only as the async/economy ratio
creeping from 1.08 (N = 50) to 1.11 (N = 400); at 250 rounds of match
play per event the sweep is bookkeeping-cheap, exactly as spec Design 2a
predicted. Consequence for DESIGN §3.1: the `7.5 µs × N × k × rounds`
model carries to async per generation-equivalent with a ≈ 1.1× constant;
the #91 GENERATIONS term does NOT bite async runs in the regime bench
covers (uniform partner draws have random_k's pair-recurrence, ≈
2k/(N−1)). M18 stays review-at; bench output remains
environment-specific and uncommitted.

**#103 — 2026-07-28 — M11 scope boundary: the M11a/M11b split, and M19
(geographic structures) joins the spine (opens the M11 design batch
#103-#110; DESIGN §2.12).** M11 splits: **M11a** = structure, local birth,
local interaction; **M11b** = movement + the mouse layout painter.
Rationale for the split: movement and natal placement are BOTH mixing
dials, so shipping them together confounds attribution on the very first
spatial experiment — natal locality alone is the regime Kaznatcheev &
Shultz's result concerns, and it gives a clean baseline against which
movement is a measured deviation. Separately, movement inserts a new draw
into #99's golden-mastered event order, and landing the two apart means
each change gets its own goldens rather than a bisect. And the genuinely
unresolved part of movement is the SCHEDULE, which under async either
becomes a new event type or a step inside the focal activation — and a new
event type would break the one-event-one-activation correspondence the
Δt = 1/N(t) convention rests on. Precedent: M10a/M10b and M9.5a/M9.5b; a/b
splits do not disturb #76 numbering. Obligation on M11a: expose the reach
primitive as a NAMED PUBLIC function so M11b is additive and never reopens
structure code (Option B discipline, one milestone forward). **M19 —
geographic structures — appends to the spine after M18** (purely additive;
no renumbering). It is the second real implementation of M11a's structure
abstraction and needs NOTHING from M12-M18, so it can be pulled forward
without renumbering pain provided M11a honours the three forward-guards of
DESIGN §2.12 (graph-of-sites, capacity field present, distance as a
structure method). Also recorded — the DOCUMENTATION/VERIFICATION DEBT
carried out of this design conversation: (i) the M11a explainer must carry
the donation-game walkthrough — b = benefit to receiver, c = cost to
giver, k = number of neighbours; the b/c > k death-birth threshold in
plain words; the worked payoffs b = 5, c = 1 → T = 5, R = 4, P = 0,
S = −1 giving b/c = 5, which CLEARS von Neumann (k = 4) and FAILS Moore
(k = 8) — same grid, opposite prediction; and both honesty caveats
(Ohtsuki assume ONE-SHOT games and weak selection, we play repeated
matches with reciprocators, so the threshold is a calibration compass, not
a promise); (ii) two literature claims are UNVERIFIED and must be checked
against publisher records before entering the explainer or before M12's
replication scenario picks a setting — whether Hammond & Axelrod used
wrap-around on their 50×50 lattice, and the Kaznatcheev & Shultz
300-period figure currently quoted in the M10 explainer without a
verification note of its own.

**#104 — 2026-07-28 — Sites are EXCLUSIVE CAPACITY-BEARING CONTAINERS;
the structure is a GRAPH OF SITES, not a grid (DESIGN §2.12).** A site
carries an id, a neighbour set, a capacity, and an optional coordinate;
the rectangular lattice is ONE BUILDER over that abstraction (the core
never knows rows and columns); distance is a method the STRUCTURE
supplies — the three forward-guards that make M19's irregular site sets a
second builder requiring no core change. Rationale: exclusivity is what
makes density-dependence — and therefore viscosity — mean anything, and it
is what #80's place-before-pay check was carved for. The capacity FIELD
ships now (placement checks `occupants < capacity` even though the RHS is
always 1) because retrofitting it later is a migration of the placement
seam, the schema, and every test that touched them; allowing capacity > 1
is deferred to M19 because it forces the distance-zero kernel question and
the mixed-cell rendering question, neither of which is M11's point.
Alternative rejected: CONTINUOUS AGENT COORDINATES — gridded/raster
representation is the mainstream form for geographic population modelling;
continuity buys only sub-cell precision below the model's content scale;
and it destroys the natural notion of a full world, forcing
density-dependence to be re-invented artificially. This also settles
#89(a)'s open question about K (resolved in #106).

**#105 — 2026-07-28 — The soft reach kernel: SUPPORT RADIUS R plus DECAY
β (DESIGN §2.12).** One functional form, separately parameterised per use:
the weight over a site at distance d is proportional to exp(−β·d) for
d ≤ R and zero beyond. The four recovered corners: R = 1 is
Hammond–Axelrod exactly; β = 0 with R = n is a uniform disc (the "hard
cutoff" the old forward-note reached for); large β with R = n is steeply
viscous with distant sites still reachable; R → ∞ with β = 0 is
well-mixed — recovered by parameters rather than by a branch. M11a
parameterises the kernel twice (`structure.birth_radius` /
`structure.birth_decay` and `structure.interaction_radius` /
`structure.interaction_decay`); M11b adds a third pair for the walk. This
entry explicitly SUPERSEDES the phrasing of the M10b spec Design 9 /
explainer §7 forward-note ("hard cutoff recoverable as temperature → 0"),
which conflated sharpening the decay with shrinking the support —
sharpening a decay recovers nearest-neighbours-only, not a hard-edged
disc. The M10b spec is NOT retro-edited (frozen-spec ritual, #62); this
entry is the record.

**#106 — 2026-07-28 — Carrying capacity SURVIVES under structure as a
second cap (DESIGN §2.12; resolves #89(a)).** K stays live under
`structure.kind = lattice`, validated K ≤ site count, with blank K
resolving to the site count (the #78 derived-default idiom). Rationale:
K < site count leaves permanent slack in which the occupied region
drifts, clusters and migrates as births and deaths reshape it — a
genuinely interesting dynamic that "capacity is purely emergent" would
foreclose. The blank-resolves-to-site-count default keeps the emergent
behaviour as the zero-effort path and prevents the silent-stall failure
mode (population parks at K with half the map empty and nothing
explaining why); the Economy panel reporting BOTH numbers is the second
guard. Consequence worth naming: because K remains live, ENERGY-PRIORITY
ADMISSION STAYS MEANINGFUL under structure — both seams keep real jobs
rather than one withering. Also recorded: `fixed_n` + lattice requires
N = site count (validated), which makes site-recycling the ONLY possible
Moran placement — a death leaves exactly one empty site and the newborn
has nowhere else to go — and DISSOLVES a proposed `moran_placement`
toggle without a parameter. Alternative rejected: K greys wholesale under
a lattice (capacity purely emergent) — simpler, but forecloses the slack
dynamic.

**#107 — 2026-07-28 — Amending the #80 frozen boundary sequence:
placement contention order and `dynamics.boundary_order` (DESIGN §2.12).**
#80 states any change is a breaking change requiring a new entry; this is
that entry. Both changes are gated so well_mixed runs stay byte-identical
(the #80/#99 active-flag idiom), and both were decided in ONE pass
deliberately, so the frozen sequence is amended once. (a)
**`structure.placement_contest`** ∈ {`random`, `energy_priority`}, default
`random`. Contention exists only where several births resolve at one
instant — synchronous + structure + `energy_economy`, and nowhere else
(async resolves one birth per event; `fixed_n` never calls `admit_births`
per #97d; sync well_mixed placement never fails). The admitted birth set
is resolved by ONE permutation then iterated — matching Hammond–Axelrod's
random reproduction order and keeping energy's role at eligibility (θ)
rather than at winning a contested cell. Parent-id order rejected: on a
lattice, id correlates with founding position, so it silently becomes a
spatial priority rule. The `energy_priority` option is retained rather
than defaulted because richest-wins-contested-cell COMPOUNDS spatially
(good neighbourhood → higher earnings → wins more cells → more good
territory) — a substantive modelling claim someone should turn on
deliberately. (b) **`dynamics.boundary_order`** ∈ {`death_first`,
`birth_first`}, default `death_first`, sync-only, greyed under async
(which has no boundary to order). Under a lattice the ordering is no
longer a phase offset but a different model: it decides whether newborns
fill scattered interior graves (deaths-first) or only frontier cells
(births-first) — and the frontier is where the ethnocentrism mechanism
lives. The default preserves hard rule 8 (old configs re-run identically)
and makes H-A's period order opt-in; M12's replication scenario will set
`birth_first` explicitly, which is why building it at M11a means M12 need
not reopen the boundary a third time.

**#108 — 2026-07-28 — Local interaction: the proximity toggle, and where
the kernel lives (DESIGN §2.12, §3.1).** `matching.spatial_interaction`
(bool, default off). Off: today's behaviour — `matching.matcher` picks
round_robin or random_k over the whole population. On: partners are
sampled from within the interaction radius by the reach kernel, and
`matching.matcher` GREYS (round-robin has no local analogue; the
well-mixed matchers are the infinite-radius corner), while
`matching.opponents_per_agent` (k) stays LIVE and does the work — k at or
above the neighbourhood size means "play all neighbours", the
Hammond–Axelrod and Ohtsuki convention, so round-robin's IDEA survives
the greying; k clamps to the number of neighbours that actually exist
(the #81 clamp idiom — edge cells under `bounded`, irregular site sets at
M19). Validator: spatial interaction requires `structure.kind = lattice`.
Rationale for a toggle rather than "structure implies local interaction":
it is what makes local-births-with-global-interaction and
global-births-with-local-interaction separable experiments — the whole
reason for two radii. CODE SHAPE: the Matcher ABC is the WRONG home for
the primary abstraction — a matcher produces a whole pair-list for a
generation and the async loop never calls one, it draws partners inline.
So the structure module owns ONE `neighbourhood_sample(agent, rng)`
primitive; the async loop calls it directly; `SpatialKernel(Matcher)` is
a thin sync-side adapter over the same primitive. One kernel, no
duplication, and both standing DESIGN promises (§6.3's SpatialKernel,
§3.1's dimension 2) stay true.

**#109 — 2026-07-28 — Initial layouts, the layout-file mechanism, and the
rendering contract (DESIGN §2.12).** `structure.initial_layout` ∈
{`random` (default), `checkerboard`, `stripes`, `blocks`, `patches`,
`central_block`} decides ARRANGEMENT only; composition is already set by
the three-bucket model (#67). Ordered mixed → segregated: checkerboard is
the anti-cluster baseline; patches (seed points grown outward) gives the
most natural irregular clusters; central_block leaves the rest of the
grid empty and is the FILLING regime — the one Kaznatcheev & Shultz's
early-run result concerns. The layout-FILE reference mechanism ships in
M11a and the mouse PAINTER in M11b: painting collides with rule 4 (the
engine knows no UI) and rule 8 (runs re-run from config), and the clean
resolution is that the painter is a UI tool that WRITES a layout file
which the config references, so the engine only ever reads DATA; shipping
the file format in M11a means nothing is retrofitted, while the painter
itself is real UI work better done alongside M11b's UI attention.
Rendering contract per §2.12: cells always exactly square (side =
min(max_width/cols, max_height/rows); the canvas takes the grid's
aspect), the side floored at ≈ 3 px, and past a few thousand cells the
grid renders as a pixel ARRAY rather than thousands of individual shapes
— the regime where #94's wall-clock throttling starts to matter.

**#110 — 2026-07-28 — The #93(B) imitation-adopter checkpoint: examined
at M11 scoping, rolled to M12; neighbourhood-proportional imitation
backlogged.** #93's checkpoint was written "review at M12 scoping" with a
rolling clause; the #76 renumbering put M11 first, and M11 is where a
graph — and therefore Ohtsuki's separate imitation threshold b/c > k + 2
— first has any referent, so the question was raised explicitly at M11
scoping rather than allowed to roll by default. ANSWER: NOT TRIGGERED,
for a specific reason. Ohtsuki's imitation updating chooses the
reassessing individual AT RANDOM, INDEPENDENTLY OF PAYOFF — that is the
SYMMETRIC adopter rule, the one #93 already reconciled us to. So the
literature that appears to make the fork urgent is in fact an endorsement
of the shipped rule. `imitate_better` (forcing the lower scorer to adopt)
is not the distinction Ohtsuki draw; their fork is between UPDATE RULES
(birth-death / death-birth / imitation-as-replacement), which is the
existing `dynamics.moran_rule` knob. The checkpoint rolls to M12 as
originally written — M12's rationale (in-group vs out-group strategy
spread) is untouched by the renumbering. SEPARATELY BACKLOGGED: Ohtsuki's
imitation updating picks a model PROPORTIONALLY OVER THE WHOLE
NEIGHBOURHOOD, SELF INCLUDED, whereas our overlay is a pairwise Fermi
comparison after a match. Reproducing b/c > k + 2 exactly would require
neighbourhood-proportional imitation — a NEW MECHANISM, declined for M11a
explicitly (not by omission) on scope grounds; the death-birth threshold
b/c > k is the one testable with what we have.

**#111 — 2026-07-31 — The b/c > k threshold presupposes an ADDITIVE
(donation-game) payoff matrix; additivity becomes the scenario's fourth
stated requirement plus a new derived readout (§12 checklist 53 → 54);
and the flagship's two default-overrides are recorded as decisions
(pre-Phase-A documentation pass on the M11a spec).** The spec is at
`Status: draft` with no code built against it, so these are
pre-implementation corrections rather than #62 deviations; they are
recorded here because they are genuine choices whose reasoning existed
nowhere in the repository. (a) THE FINDING: Ohtsuki's b/c > k rule is
derived for the donation game specifically — a cooperator pays a cost c
so the opponent receives a benefit b, a defector pays and provides
nothing: T = b, R = b − c, P = 0, S = −c. Reading the cost of
cooperating off that matrix twice gives T − R = c against a cooperator
and P − S = c against a defector — the SAME number ("additivity", or
"equal gains from switching"); the compliance test is T − R = P − S
(defining c), equivalently T − P = R − S (defining b). The project
defaults T=5, R=3, P=1, S=0 FAIL it: T − R = 2 ≠ 1 = P − S — a
perfectly valid PD (the ordering and 2R > T + S both hold) that simply
is not a donation game. The consequence is sharper than "the rule does
not apply": with a non-additive matrix, "b/c" is not a well-defined
quantity at all. Two candidate benefits (T − P = 4, R − S = 3) against
two candidate costs (T − R = 2, P − S = 1) give four defensible
readings — 4/2 = 2.0, 4/1 = 4.0, 3/2 = 1.5, 3/1 = 3.0 — of which two
clear von Neumann's k = 4 and two fail it, so a user could "predict"
either outcome by choosing a definition: the signature of a malformed
question, not a hard one. `donation_game_threshold`'s T=5, R=4, P=0,
S=−1 IS additive (c = 1, b = 5, b/c = 5 unambiguous) — which is why
those values were chosen, and why VT-1's negative-payoff question was
load-bearing: additivity with P = 0 FORCES a negative sucker payoff.
(b) DECIDED: additivity becomes the FOURTH stated requirement of the
scenario, with the arithmetic in the scenario text; the §12 concept
explanation for the threshold carries the precondition (b and c only
EXIST when T − R = P − S — under a non-additive matrix the ratio is
ambiguous, not merely inapplicable); and a NEW derived readout inspects
the four live payoff values and reports either "additive: b = 5, c = 1,
b/c = 5" or "not additive — the b/c > k threshold does not apply" with
the one-line reason (cooperating costs a different amount against a
cooperator than against a defector). It is a pure function of four
registry values on the spec Design 11 paint-time resolver pattern — no
new machinery. Count change, stated explicitly: §12 derived readouts
8 → 9, checklist total 53 → 54. (c) The flagship `spatial_reciprocity`
gains two EXPLICIT setting overrides the spec had only implied in
prose: `neighbourhood_shape = von_neumann` (overriding the `moore`
default) — fewer neighbours means stronger viscosity and an easier time
for clustering, so this is the configuration most likely to actually
show cooperation surviving, which is what a flagship scenario is for;
and `payoff_punishment = 0` (overriding the default P = 1) — the
scenario's entire mechanism is that a defector in a defector interior
earns NOTHING and starves against the basic living cost L, whereas at
P = 1 with eight Moore neighbours a defector in a solid block earns 8
per round, which may well clear L — in which case it does not starve,
cooperator clusters gain no relative advantage, and the flagship
demonstrates nothing. Recorded as DECISIONS rather than treated as
clarifications deliberately: P = 0 is not a more precise restatement of
anything — it is an override of a live registry default chosen for a
specific mechanical reason, and a later reader meeting it in scenario
prose alone would have no way to recover that reason; the same logic
covers the shape override. This is the traceability this file exists
for. Conceptual guard, also written into the scenario text: the
flagship does NOT rest on the Ohtsuki mechanism — its story is
ECOLOGICAL (absolute income measured against a survival threshold),
while b/c > k concerns relative fitness in a Moran process under weak
selection, which is `donation_game_threshold`'s story; the two
arguments happen to point the same way and must never be conflated.
(d) UNVERIFIED POINTER, for the explainer's literature pass only: there
is a known generalisation of b/c > k to non-additive matrices via a
structure coefficient — cooperation favoured when σR + S > T + σP, with
σ = (k+1)/(k−1) for death-birth on a regular graph (Tarnita et al.
2009 / Nowak et al. 2009 the likely sources). It was derived during the
design conversation by checking that it collapses correctly to b/c > k
under additivity — a consistency check, NOT a citation — and it enters
no spec or app text until verified against publisher records (the
standing rule now written into the spec's explainer bullet; the σ
inequality itself appears only here). Alternative rejected: leaving the
flagship's values as prose implications and the additivity precondition
as explainer-only knowledge — that ships a flagship that can silently
demonstrate nothing (P = 1 clearing L) and a threshold scenario whose
central quantity dissolves under the default matrix, with no visible
signal in the app either way.

**#112 — 2026-08-01 — Phase A micro-semantics the spec left open: the
one-blank lattice dimension resolves by ceiling division, and zero-weight
candidates clamp out of the kernel draw (M11a Phase A implementation).**
Two small rules were decided during Phase A implementation because the spec
specified the surrounding contract but not these cases. (a) **One blank
dimension.** Design 1 and Design 11 specify blank rows AND cols (the
most-square factor pair of N) but not one-blank-one-given, which the two
independent nullable widgets and hand-written YAML both permit. DECIDED:
the blank dimension resolves to the SMALLEST count that fits N over the
given one — ceil(N / given); rows = 8 with N = 60 gives cols = 8 (8×8 = 64
is the smallest 8-row grid holding 60 agents). This reads "auto" uniformly
as "size the grid to fit the population", keeps blank-means-auto the
zero-effort path, and follows the #78 idiom (resolved at validation;
`config.yaml` stores plain numbers; `resolve_lattice_dimensions` is the
pure free function per spec Design 11 extension 2). Alternative rejected:
requiring both-or-neither (a validation error) — hostile to the obvious
reading "I want 8 rows, you figure out the rest", and an error where a
sensible resolution exists contradicts the derived-default philosophy.
(b) **Partial zero weights in `neighbourhood_sample`.** Design 2 pins the
ALL-zero combined-weight case (uniform fallback over the candidates, the
#63 shift-idiom contract) but not some-zero-some-positive. DECIDED: a
candidate whose combined weight is zero is simply never drawn, and the #81
clamp counts DRAWABLE (positive-weight) candidates — so a draw of size 3
over {0, 0, w} returns one site, not three. This is the mathematical
content of "weight zero" carried through sampling-without-replacement;
the alternative (numpy's own behaviour: raise when size exceeds the
positive-weight count) violates the clamp idiom. No M11a call site
exercises the partial-zero case (site_weights is Design 7's fixed_n
breeder hook, always size 1); the rule exists so the primitive's contract
has no undefined corner. Both rules are documented in their docstrings and
pinned by tests (test_experiment_config.py, test_structure.py).

**#113 — 2026-08-02 — A standalone explainer with no companion
specification, and the naming that follows.**
`docs/explainers/calibration-guide.md` ships without a paired spec. The
companion-explainer rule assumes each explainer documents something a
milestone built; this one documents behaviour that already exists across
M9 through M11a, so there is nothing to specify and nothing to freeze. Two
consequences recorded so a later reader does not conclude a spec was lost.
First, the filename drops the milestone prefix that the explainer
convention assumes and uses `calibration-guide.md` rather than a name
ending `-explainer.md` — it sits in `docs/explainers/` but is a standing
reference rather than a milestone companion, and the name says so. Second,
this establishes the precedent for future standalone documents: a
cross-cutting reference gets a descriptive filename, no spec, and a
DECISIONS entry noting the deviation. Alternative rejected: writing a
retrospective spec purely to satisfy the pairing rule, which would produce
a document with no frozen intent, no validation section and no
implementation to record — a ritual artifact rather than a record.

**#114 — 2026-08-02 — VT-3's second-order claim overstates what the
arithmetic supports; softened in the guide, and Phase B will measure the
open half.** The M11a spec states that because the `fixed_n` breeder draw
reads accumulated energy, relative differences widen as a run proceeds and
effective selection strengthens over time. The first half does not follow
from the shift idiom. Under `w_i = e_i − min(e)`, if agent energies
diverge linearly at rates `r_i`, then `w_i(t) = (r_i − r_min) × t`, and
the draw probability `w_i / Σw` has `t` in both numerator and denominator
— it cancels. Subtracting the poorest normalises steady divergence away
entirely. What IS demonstrable and ships in the guide: (a) selection
begins at exactly zero, because at run start every agent holds identical
energy, every shifted weight is zero, the uniform fallback fires, and the
draw is neutral with no fitness content — so selection strengthens *from
nothing*, which is a real effect but a different one; and (b) the draw
partly selects for AGE rather than strategy, because an incumbent has had
longer to accumulate than a newborn, and at the textbook `offspring_stake
= 0` a newborn's weight sits at the bottom and it effectively cannot breed
until it accumulates. Whether the spread keeps widening after divergence
is established requires super-linear growth in the spread, which is
plausible — richer agents breed more, and the M11a multiply-fork compounds
distance weight with fitness — but is an empirical question, not an
arithmetic one. **Phase B task added: log the shifted-weight spread at
three points in a `fixed_n` run and report whether it grows faster than
linearly.** The spec text is frozen and is NOT edited; this entry is the
deviation record per the standing rule. The `donation_game_threshold`
scenario text uses the softened wording. Alternative rejected: repeating
the spec's wording in the guide, which would put a claim that fails five
lines of algebra into user-facing scenario text.

**#115 — 2026-08-02 — The flagship gains a third explicit override:
`payoff_sucker = −1`.** #111(c) recorded two overrides for
`spatial_reciprocity` — `neighbourhood_shape = von_neumann` and
`payoff_punishment = 0`. With punishment overridden to 0 and sucker left
at its registry default of 0, the configuration has punishment = sucker,
which fails the strict `T > R > P > S` ordering that
`game.enforce_pd_ordering` enforces by default. Three resolutions existed:
also disable the ordering validator; override the sucker payoff to a
negative value; or rely on the validator being lenient. DECIDED: override
`payoff_sucker = −1`, giving T = 5, R = 3, P = 0, S = −1. Reasons. It
keeps the scenario legal under the app's own rules, so nobody loading it
meets a validation error or inherits a scenario exempt from checking. It
makes the sucker payoff carry meaning rather than being a silent zero: a
cooperator at a cluster edge now actively loses energy per defector
neighbour, which sharpens the pressure to cluster — the mechanism the
scenario exists to show. And it does not disturb #111's conceptual guard,
because the matrix remains non-additive: T − R = 2 against P − S = 1, so
the flagship is still emphatically not a donation game and its story is
still ecological rather than Ohtsuki's. Alternative rejected: disabling
the ordering validator for the flagship, which is defensible — punishment
= sucker = 0 is the recognised "weak Prisoner's Dilemma" of the
spatial-games literature (Nowak & May 1992; named and characterised by
Szabó & Fáth 2007) — but buys a tidier matrix at the price of switching
off a safety rail on the project's headline scenario, so that anything the
user subsequently edits is unchecked. Second alternative rejected: relying
on the validator being lenient, which is a fact about the code rather than
a decision, and a rule documented as strict that behaves leniently is a
defect waiting to be fixed out from under the scenario. **A verification
task confirms which behaviour the validator actually has (VT-6(a), in the
M11a spec's post-freeze addendum).**

**#116 — 2026-08-03 — VT-2 answered: synchronous imitation PRESERVES agent
ids, so Design 10's nothing-to-persist branch ships (M11a Phase B).**
Verified against the running code and at runtime, not merely expected.
`PopulationDynamics.step` is the only consumer of a `SelectionRule`'s
parent indices, and it mutates the EXISTING agent objects in place —
`agent.strategy = strategy` then `agent.reset_for_new_generation()` over
`zip(self._population, offspring)` — with `self._population` never rebound
and no `Agent(...)` constructed anywhere after `build_initial_population`.
Slot i therefore holds agent id i for the whole run: score and
per-opponent histories are wiped at each boundary (#31), strategy is
overwritten, id and object identity survive. This confirms #89(c)'s "an id
must mean one creature forever" as a live invariant of the imitation path,
not just of the economy path. CONSEQUENCE, as the spec pre-specified:
under imitation nobody is born and nobody dies, so occupancy never changes
after founding, is fully determined by the config and the seed, and
re-running reproduces it exactly — there is NOTHING TO PERSIST.
Implemented: no `occupancy.parquet`, no widened `agents.parquet` (which
would NaN-fill energy and age for every imitation run, the shape #47c
forbids), and the live renderer obtains occupancy by REPLAYING founding
from the config. The replay is exact because the founding draw is the
first draw of the run (#119), so a fresh generator seeded identically
reproduces it before anything else has touched the stream; a test asserts
the replayed arrangement equals the engine's. The second branch specified
in Design 10 is now dead and should be read as historical. Forward note
stands: once M11b lets agents move, occupancy becomes genuinely
time-varying and `occupancy.parquet` becomes necessary regardless of this
answer.

**#117 — 2026-08-03 — VT-3 answered: the async `fixed_n` breeder draw
reads ACCUMULATED ENERGY through the #63 shift with no intensity knob —
and the #114 measurement finds the shifted-weight spread PLATEAUS rather
than growing super-linearly (M11a Phase B).** (a) VT-3, by inspection:
`AsyncDynamics._proportional_parent` computes `floor = min(agent.energy
for agent in candidates)` then `weights = [agent.energy - floor for agent
in candidates]`, normalises, and draws. It reads `agent.energy` — the
cross-event accumulated STOCK, never `agent.score`; `async_dynamics.py`
never reads `score` at all. The stock is a full ledger (initial energy,
per-match payoffs less engagement cost, the living cost, compounding
capital returns, past stakes), so what is sampled is lifetime wealth. The
shift is exactly `w_i = e_i - min(e)`, so the poorest candidate always has
weight 0 and is never drawn unless all energies are equal, in which case
the uniform fallback fires. On the intensity question the answer is
definitively NO: no beta, no exponent, no temperature anywhere on that
path. `dynamics.selection_beta` is read only by the synchronous `fermi`
rule and, under async, only by the imitation OVERLAY — the app already
greys it out under async unless the overlay is on. Note the asymmetry: the
DEATH side is configurable (`fixed_n_death_rule`), while the BIRTH side is
hard-wired raw-energy roulette. So Ohtsuki's weak-selection limit cannot
be approached in this engine, and the b/c > k threshold stays a
CALIBRATION COMPASS, NOT A PREDICTION — the wording #103 already uses, now
verified rather than expected. (b) The #114 measurement, assigned to this
phase by the spec's phase-task ledger. A well-mixed async `fixed_n` run
(24 agents, seed 21, death-birth, pure-random reaper, stake 0, 300
generation-equivalents, 7200 breeder draws) was instrumented temporarily —
the probe does not ship — to log the spread `max(e) - min(e)` (which under
the shift IS the maximum weight), the standard deviation of the shifted
weights, and the top agent's actual draw probability. Windowed means at
three points across the run, in three variants: TEXTBOOK (no mutation, no
capital return) spread 825 -> 868 -> 739 at t = 88 / 163 / 287, p(top)
0.188 -> 0.183 -> 0.165; MUTATION 0.01 906 -> 680 -> 785, p(top) 0.200 ->
0.163 -> 0.177; CAPITAL RETURN 0.02 858 -> 905 -> 763, p(top) 0.191 ->
0.187 -> 0.167. READING: growth is not merely sub-super-linear, it is FLAT
— the spread reaches a plateau by the first probe and wanders around it,
while `spread / t` falls by roughly a factor of four across the run, and
the top agent's draw probability drifts DOWN rather than up in every
variant. Neither of the two channels #114 named as plausible (richer
agents breeding more; compounding capital) shifts the picture. So the
spec's frozen second-order claim — that effective selection strengthens
over time — is not merely unsupported by the algebra (#114) but
contradicted by measurement: what is real is that selection strengthens
FROM ZERO in the opening moments, and the age effect (an incumbent has had
longer to accumulate than a newborn, which at stake 0 sits at the bottom
and cannot breed until it accumulates). The guide's softened wording
therefore stands unchanged and needs no further edit. Honest scope limit
on the measurement: one seed, one population size, one matcher, one death
rule — enough to refute "strengthens over time", not enough to
characterise the plateau's height as a function of the parameters.

**#118 — 2026-08-03 — The Parameter Registry gains a `str` kind, for
`structure.layout_file` (M11a Phase B).** The spec's Parameters table
types `structure.layout_file` as "str, nullable", but the registry's
`ParamKind` admitted only `int`, `float`, `bool` and `choice` — a
filesystem path is the project's first genuinely open value. DECIDED: add
`"str"` rather than smuggle the path in as a degenerate `choice` or keep
it outside the registry. Keeping it out was never available: hard rule 3
makes a parameter without a registry entry a bug. Encoding it as a
`choice` would be a lie about the value set and would break the UI's
selectbox. The kind carries its own weakness in its documentation: a value
not drawn from a declared set cannot be validated beyond "it is a string",
so anything with a knowable set of values stays a `choice`. Three
consumers were extended with it: `validate` (type check, plus
blank-to-`None` normalisation for a nullable string, so "unset" has one
spelling rather than two), `gendocs` (kind label "text"; allowed values
"any text; may be empty"), and the app's widget dispatcher (a
`text_input`, checked BEFORE the nullable branches, which would otherwise
have routed a nullable string into the nullable-float widget). The sweep
tokeniser needed no change: its fall-through already keeps a raw token,
and a swept layout path is refused for a different reason (#119).

**#119 — 2026-08-03 — Founding-layout mechanics the spec left open: the
centred footprint, the two traversals, deal-to-agent matching, and how
"the file wins" is actually implemented (M11a Phase B).** Design 8 fixes
the layouts' PURPOSES and dealing disciplines but not every mechanism;
these were decided at implementation and are recorded because a later
reader would otherwise have to reverse-engineer them from the code. (a)
FOOTPRINT when N < site count. The patterned layouts take "a centred
contiguous block of N sites", implemented as: order every site by
Chebyshev distance from the grid centre, ties broken ascending by id, take
the first N. Chebyshev regardless of the run's neighbourhood shape — under
the von Neumann metric the same rule would carve a DIAMOND, which is not
what "central block" describes. `random` scatters over the whole grid
instead, per Design 8. (b) TRAVERSALS. `checkerboard` deals round-robin
along a SERPENTINE sweep, not a row-major one: with an even column count,
row-major round-robin restarts each row on the same strategy and produces
vertical stripes rather than a chessboard, which would fail the spec's own
acceptance test ("with two equal-count strategies this reproduces the
literal checkerboard"). The serpentine alternates between vertically
adjacent cells too, giving the checkerboard for any column count. `blocks`
deals run-length along a TILED serpentine (tiles about sqrt(rows) x
sqrt(cols), tiles themselves swept boustrophedon), which is what makes its
runs compact in TWO dimensions rather than in one — the property that
distinguishes it from `stripes`, and it is pinned by a test comparing how
many columns a run spans under each. No new parameter, per Design 8.
`central_block` deals run-length row-major inside its footprint; what
defines it is the empty frame, not the arrangement within. (c) DEAL TO
AGENTS. The deal decides which STRATEGY sits in which site; agents
carrying that strategy are then assigned to those sites in ascending
agent-id order. So the layout never reorders agents and never touches ids
— `build_initial_ population` keeps producing agents in
composition-declaration order, and the ascending-machine-name rule (#67)
governs the DEAL, not the population. (d) "THE FILE WINS", implemented.
Design 8 says a layout file's cell counts ARE the composition and the mix
widgets are superseded. Rather than derive N from the file — which would
feed the auto grid dimensions and K's derived default from a filesystem
read inside a before-validator — the file overwrites each agent's STRATEGY
at founding, and the population SIZE must still match the file's
occupied-cell count, with a validation error naming both numbers when it
does not. So the widgets' mixture is genuinely superseded while N stays
the single arithmetic source everything else derives from. Alternative
rejected: requiring the widgets to reproduce the file's counts, which
Design 8 explicitly calls a trap. (e) VALIDATION PLACEMENT.
`initial_layout = from_file` with a blank path is a config error (only
that direction can silently run a different experiment); a stale path
under another layout is ignored, the `continuation_probability` idiom.
Header dimensions, unregistered tokens, and the population-size match are
checked when the file is READ at founding, because config validation is
deliberately filesystem-free. The sweep-axis incoherence (#a composition
axis over a base whose every cell is pinned by a file) is refused at
sweep-spec validation, as Design 8 requires. (f) RNG POSITION. The
founding draw is placed as the FIRST draw of the run, before the economy's
founder decoration in all three dynamics classes — Design 9 only requires
"once per run, before generation 0", and first is the position that makes
the renderer's replay exact (#116). Exactly one draw is consumed: `random`
takes one permutation, `patches` one seed sample of size "number of
strategies"; the other five layouts and every well-mixed run consume none,
asserted directly against the generator's state.

**#120 — 2026-08-03 — Schema 5 is CONFIG-driven, honest presence reaches
COLUMN grain, and the grid renders the FOUNDING arrangement (M11a Phase
B).** (a) SCHEMA 5. `SCHEMA_VERSION` becomes 5 (the ceiling the loader
accepts) and the tier constants are split out: `STRUCTURE_SCHEMA_VERSION =
5`, `EVENT_TIME_SCHEMA_VERSION = 4` (previously spelled `SCHEMA_VERSION`),
`PER_AGENT_SCHEMA_VERSION = 3`, `PER_STRATEGY_SCHEMA_VERSION = 2`. Design
10 says ANY lattice run writes 5, and that forces the structure tier to be
read from the CONFIG rather than from the recorded rows, unlike every tier
below it: a synchronous imitation lattice run records no per-agent data at
all (#116) yet a reader still must know the run had structure. Both the
anticipated version (the `config.yaml` header comment) and the actual one
(`summary.json`) therefore consult the config for this tier and agree.
Tournament runs are excluded — structure is ignored there. (b)
COLUMN-GRAIN PRESENCE. `site_id` is a nullable `Int64` column present on
`agents.parquet` exactly when the run has structure, and absent otherwise
— the first application of #83's honest-presence rule at column grain
rather than file grain, with the loader made presence-driven to match
(`SITE_COLUMN in frame.columns`). Keyed off the run type, not off whether
any row happens to carry a site, so the shape is stable across periods. A
test pins that a well-mixed run's column tuple is unchanged, since nothing
else in the suite did. (c) PHASE B'S HONEST GAP, recorded rather than
hidden: occupancy is founded at generation 0 and then left alone, because
local birth is Phase C. So under the economy a newborn's `site_id` is null
and a dead agent's site is not reclaimed. This is the phase's exit
condition (nothing reads the structure) rather than an oversight, and it
is pinned by a test that Phase C is expected to break — at which point the
test retires. (d) LAYOUT-FILE SELF-CONTAINMENT. The recorder copies the
file into the run folder as `layout.txt` and records the copy's bare name;
`load_config` resolves a layout path that is not found from the working
directory against the config file's own folder. So a recorded run re-runs
from anywhere even after the original file moves (hard rule 8), at the
cost of the recorded config's path differing from the authored one — which
is the point, and is tested. (e) THE RENDERER shows the FOUNDING
arrangement, computed by replay from (config, seed) rather than from run
output. That is what lets one code path serve imitation runs (which
persist nothing), economy runs, and the results browser alike, and it lets
the panel preview a layout live — change the dropdown and the arrangement
redraws without running anything, which is what V2 actually asks the owner
to do. Cells are exactly square by construction (plotly's `scaleanchor`),
not by sizing arithmetic that a container width could defeat. Three
derived readouts ship beside it — site count, occupancy fraction, and the
Design 8 mandatory guard, the count of agents with no occupied neighbour
at founding — each with its own inline explanation per the §12 rule. (f)
PHASE A'S IMPORT GUARD IS RETIRED, not weakened. Its assertion (no engine
module imports `core.structure`) is false by design now that Phase B wires
the module, and adding exceptions to it would have left a test whose name
and message contradict what it checks. What it protected is now asserted
directly and better: a well-mixed run builds no occupancy and moves the
generator's state not at all. A narrower hard-rule-4 scan (nothing under
core/, config/, io/ imports Streamlit or plotly) takes its place in the
same file.

**#121 — 2026-08-04 — The grid preview validated the WHOLE panel, so a
failing section the grid never reads could hide it; the preview now builds
from exactly the founding inputs, behind a named visibility predicate
(M11a Phase B follow-up).** THE DEFECT, from the owner's manual
validation: with `structure.kind = lattice`, the founding grid vanished
when `reproduction_mode` was switched to `energy_economy`, and likewise
under `time_model = asynchronous`. DIAGNOSED CAUSE — neither of the design
layer's two hypotheses. The grid was never gated to sync imitation, and
founding- replay exactness was never the problem (the founding path reads
mode, seed, population and structure only, and is identical in every
mode). The panel preview built the FULL `ExperimentConfig` from every
widget value and drew the grid only if the whole thing validated — and
`_check_capacity_fits_ population` (K >= N) runs exactly when K is
consumed: synchronous `energy_economy`, or asynchronous `variable_n` (the
async default). With V1's population of 400 and `carrying_capacity` at its
default 200, the check is dormant under imitation (#34: ignored parameters
are never validation errors) and fires the moment either switch flips —
reproduced headlessly with exactly that error. The grid then vanished
behind a misleading caption blaming the population mix. FIX, in three
parts. (a) A NAMED predicate, `helpers.grid_visible` — evolution mode AND
lattice, deliberately consulting neither `reproduction_mode` nor
`time_model` — in the shape Phase E's greying/visibility predicate table
can fold in unchanged; the flagship and drifting frontier are sync-economy
runs and `donation_game_threshold` is async, so any clock or reproduction
gate would make V4-V6 unwatchable. (b) `helpers.grid_preview_config`
builds the preview from ONLY mode, seed, population.* and structure.* (the
`GRID_PREVIEW_SECTIONS` tuple), everything else at registry defaults — so
a validation failure elsewhere in the panel can never take the grid down
with it, while genuinely grid-relevant failures (mix != N, `from_file`
without a file) still show, now with the ACTUAL validation message instead
of the guess. Strategy parameters are omitted on stated reasoning: the
deal reads strategy names and counts, never their tunables. (c)
Replay-versus-engine placement pins added for a sync-economy lattice run
and an async `fixed_n` lattice run, mirroring the existing imitation pin —
founding-replay exactness was hypothesis (b) and deserved pinning in the
modes the later phases watch, even though it was not the cause; the
economy pin reads the engine's placement off the persisted founder
snapshots, exercising the site_id path end to end. The results-browser
grid needed no fix (it renders from the recorded config,
mode-independently) and the live view is untouched. Regression test: the
exact defect state — N = 400, default K, economy — pinned as "full config
raises, preview builds anyway".

**#122 — 2026-08-04 — `grid_templates/` is the layout files' default home;
a bare filename resolves there, a recorded folder's own copy outranks it;
token spellings are surfaced in app, error, and help text (M11a Phase B
follow-up; extends Design 8, which is silent on resolution).** (a) THE
FOLDER: `grid_templates/` at the repository root, shipped with a README
(format rules: header, both separators, the '.' empty-site token, where
machine names come from, the population-size contract) and two small 4x6
examples in real registered machine names — `example_quadrants.txt`
(whitespace-separated, 18 agents) and `example_island.txt`
(comma-separated, 24 agents). A test parses both against the live strategy
registry, so the examples cannot rot. (b) THE RESOLUTION RULE: a
`structure.layout_file` value containing NO path separator is a template
name and resolves against `grid_templates/`; a value containing a
separator, or an absolute path, is used as given. One exception outranks
the template folder, pinned by a test: a recorded run's own beside-config
copy wins for bare names, because a recorded folder must stay
self-contained (hard rule 8) — otherwise re-running an old folder could
silently read a same-named template written later. `load_config` now
routes through the same `resolve_layout_path` so the CLI, the recorder,
and the app share one rule. Alternative rejected: resolving bare names
against the working directory (the pre-existing accident) — a bare name in
a config would then mean different files from different shells, which is
exactly the reproducibility smell hard rule 8 exists to prevent. (c)
COPY-NOT-MOVE pinned explicitly: the recorder test now asserts the user's
original still exists after the run, alongside the run folder's copy. (d)
TOKEN SPELLINGS, three surfaces that cannot drift: the app renders the
registered machine names beside the Layout file widget at paint time (from
the strategy registry, never hardcoded); the unregistered-token error now
names the offending token with its FILE line and cell number (the parser
records per-cell positions for exactly this) and lists the valid names;
and the registry help text for `layout_file` and the `from_file` enum
value states that tokens are registry machine names and points at the
in-app list and the shipped examples.

**#123 — 2026-08-04 — Layout files accept comma-separated bodies; comma
presence anywhere in the body decides for the WHOLE body; an empty field
between commas is an error, never an empty site (M11a Phase B follow-up;
extends Design 8's format).** DETECTION RULE: if any body line contains a
comma, the entire body parses comma-separated with each token stripped of
surrounding whitespace; otherwise the body parses whitespace-separated
exactly as before (existing files are untouched byte-for-byte, and a test
pins that a comma file parses identically to its whitespace twin).
Whole-body detection makes mixed-separator files impossible by
construction — a whitespace-styled line inside a comma file yields one
token and fails the cell-count check rather than being half-reinterpreted.
'.' remains the empty-site token in BOTH modes. A blank token in comma
mode (',,' or a leading/trailing comma) raises a validation error naming
the line and cell and telling the user to write '.' — bare gaps must not
silently mean "empty", or a missing token becomes indistinguishable from a
typo; the same reasoning as #83's honest-presence rule, applied to a text
format. The header is unchanged. Alternatives rejected: a `separator:`
header field — more machinery for no ambiguity gained, since detection is
already unambiguous; and treating blank fields as empty sites — rejected
for the typo-masking reason above.

**#124 — 2026-08-04 — Under `from_file`, the app compares the layout
file's implied population against the Population section and offers a
one-click populate; mismatch is an alert with a choice, never a silent
override of the widgets (M11a Phase B follow-up; interim treatment pending
Phase E's greying).** A layout file names a strategy per cell, so it IS a
population — a size (the occupied-cell count) and a mixture. Design 8
already rules that the file wins on composition and calls the alternative
(making the user reproduce, in the widgets, counts the file states) a
trap; but until Phase E's greying lands, the widgets are live and the user
was left retyping the file's numbers to satisfy the size validator.
DECIDED: a Streamlit-free helper (`helpers.layout_population_mismatch`)
reads the file's (size, per-strategy counts) and compares them with the
current widgets — token-checking the file against the strategy registry
first, so the offer can never propose writing an unknown name into the
widgets, and refusing files below the minimum legal population (2). On
agreement the grid renders as usual. On ANY difference — size or mixture,
because a mixture-only difference would otherwise record a config whose
composition is not what actually runs — the panel shows both populations
and offers two explicit ways out: switch `initial_layout` away from
`from_file` (keeping the widgets as typed), or press "Populate the
Population section from the file", which writes `population.size` and
every registered strategy's mix count (absent strategies to 0) via a
Streamlit button callback — callbacks run in the pre-render window of the
next script run, the one moment widget session state may legally be
written, the same window the scenario loader uses. The grid is withheld
while the mismatch stands, so the alert-with-choice occupies exactly the
spot the preview will fill once the state is coherent. Alternatives
rejected: silently overriding the widgets at run time (two sources of the
same truth disagreeing on screen — the exact trap Design 8 names);
auto-populating without asking (the user may have meant to keep their mix
and switch layouts instead, and an unprompted write to six widgets reads
as the app fighting the user, #40's scenario-is-not-a-lock spirit);
deriving `population.size` from the file inside config validation
(rejected in #119(d) — validation stays filesystem-free and N stays the
single arithmetic source). Registry help and the grid_templates README now
mention the offer; the spec body is untouched.

**#125 — 2026-08-04 — `central_block` was an alias of `stripes` (identical
output in every configuration); it now builds Design 8's definitional
footprint — the most-square centred RECTANGLE of exactly N cells,
orientation-aware, with a stated fallback — and the full-grid coincidence
with `stripes` is documented as inherent (M11a Phase B follow-up; fixes an
unrecorded #119(a) collapse).** THE DEFECT, found by the owner walking V2:
every layout example showed `central_block` identical to `stripes`. A
sweep over five grid sizes and seven populations confirmed zero differing
configurations — the two enum values were one code path. Cause: Design 8
distinguishes them by FOOTPRINT in the sparse case — `central_block` is
definitionally "a centred rectangle sized to N", while the patterned
layouts got "a centred contiguous block of N sites", implemented in
#119(a) as the Chebyshev ball around the grid centre. The implementation
routed `central_block` through the same ball, and since both deal
run-length along a row-major sweep inside their footprint, the two
coincided everywhere. The ball is not generally a rectangle: N = 10 on 5x5
gave a 3x3 blob plus one stray agent at the distance-2 ring's lowest site
id — the grid's corner — for both layouts. TWO REASONS NOBODY SAW IT
EARLIER, both worth recording: with `structure.rows`/`cols` left blank the
grid auto-sizes to EXACTLY N sites, so the world is always full, the empty
frame cannot exist, and at a full grid the two layouts coincide
NECESSARILY (the rectangle sized to N is the whole world); and the Phase B
validation's suggested workaround — population 100 on a manual 20x20 —
collides by accident, because the 100-cell ball is exactly the centred
10x10 square, which is also 100's most-square rectangle. DECIDED:
`central_block` gets its own footprint function. The rectangle is the
most-square factor pair of N that FITS the grid, tried in both
orientations (a wide grid gets a wide block, a tall grid a tall one),
centred by integer division; a prime N makes a single centred line, the
same reading the grid's own auto-sizing gives prime populations. When no
exact rectangle of N cells fits — a prime N exceeding both grid dimensions
— the footprint falls back to the generic centred blob, keeping the layout
total rather than refusing a legal configuration; the fallback is pinned
by a test asserting footprint equality with `stripes` in exactly that
corner. Dealing inside the rectangle stays run-length row-major.
Consequences, stated honestly: at a FULL grid `central_block` still equals
`stripes` (inherent — no frame exists), and the registry help text now
says so and tells the user to set rows/columns larger than the population
to see the frame; at sparse N whose ball happens to equal the rectangle (a
perfect-square N centred on matching parity) the two still coincide;
everywhere else they now visibly differ, pinned by tests at N = 10 on 5x5
(2x5 rectangle vs blob-with-a-knob) and N = 60 on 20x20 (6x10 rectangle vs
banded blob). No RNG is consumed either way (deterministic layout, the
#119(f) gate untouched), no golden master existed on the sparse case, and
engine behaviour is unchanged. Alternatives rejected: filling a
slightly-larger rectangle partially for no-fit N (empty cells INSIDE the
block — the frame stops meaning anything); and amending `stripes` to span
the grid's full width in sparse worlds so the two are categorically
different — that is a Design 8 semantics change and belongs to the design
layer, flagged in the handback rather than taken here.

**#126 — 2026-08-04 — Every layout-file check moves to CONFIG-VALIDATION
time, composition equality becomes a validator (the hard-rule-8 keeper),
and reading the file there is read-to-VALIDATE, which #119(d)'s
read-to-derive rejection does not cover (M11a Phase B follow-up 2).** THE
DEFECT, from the owner's manual validation: 12x12 pinned dimensions,
`initial_layout = from_file`, the 4x6 `example_island.txt`, populate offer
declined, Run pressed — a raw ValueError with a full traceback rendered in
the app, raised from `validate_layout_file` at FOUNDING time inside
`PopulationDynamics.__init__`. Every other configuration mistake in the
app produces a plain validation sentence; and worse, Run was not blocked
while a from-file disagreement stood, so any mismatch the engine happened
to tolerate would let `config.yaml` record a composition that is not what
ran — a hard-rule-8 lie in the recorded config. Spec Design 8 names these
checks as VALIDATORS and its sweep-axis rule demands rejection "at spec
validation", so config-time placement is the spec's intent, not a
deviation. DECIDED: a new `ExperimentConfig` after-validator
(`_check_layout_file_agrees`) runs when the file is consumed — evolution
mode, lattice, `from_file`; ignored parameters are never validation errors
(#34) — and checks, in order: the value resolves (per the #122 rule) to a
readable file (FileNotFoundError is converted to ValueError so pydantic
wraps it — nothing escapes raw); the file parses (the #123
comma/whitespace and blank-field rules); header dimensions match the
RESOLVED rows/cols (the before-validator has already turned blanks into
numbers); every token is a registered strategy (the #122 message: token,
line, cell, valid names); at least two agents are placed; and COMPOSITION
EQUALITY — the configured composition must equal the file's implied one,
with a message naming both sides and pointing at the app's one-click
"Populate the Population section from the file" button. Equality of the
count dicts subsumes the size check, so one message covers size-only,
mixture-only, and both (each pinned by a parametrised test). CHANNELS: the
app's Run handler and the CLI already render ValidationError as plain
sentences, so both lit up with no new display code — the CLI is confirmed
by a test that the defect state prints the message, exits 1, starts no
run, and shows no traceback. The panel additionally gained pre-Run
DIMENSION visibility (`helpers.layout_file_dimension_mismatch`, resolving
blank rows/cols exactly as the run would), the same beside-the-widgets
treatment the #124 composition offer already had; #124's flow is otherwise
unchanged. ORDERING CONSEQUENCE in `load_config`: the #122 beside-config
resolution now happens on the RAW mapping BEFORE `model_validate`, because
the validator reads the file and only `load_config` knows the config's own
folder — without the reorder, every recorded from-file folder would fail
to reload its own `layout.txt` copy (pinned by test). ENGINE checks stay
as defence in depth for programmatically built configs and become
unreachable through the app and CLI; the Design 8 "file wins on
composition" founding seam is likewise now reachable only
programmatically, and its test moved to the `found_occupancy` level to say
so. The sweep-axis rejection was verified already at sweep-spec validation
(`sweep_validation_messages`) — nothing to move. THE #119(d) DISTINCTION,
stated so a later reader does not conclude it was quietly overturned:
#119(d) rejected READ-TO-DERIVE — deriving N (and with it the auto grid
dimensions and K's default) from file contents inside a before-validator —
and that rejection stands: every derived default remains a pure function
of widget values and never of file contents. This validator is
READ-TO-VALIDATE: it consults the file precisely to confirm the widgets
agree with it, derives nothing, and converts every read failure (missing,
unreadable, unparseable) into a validation error rather than letting an
exception escape. Alternative rejected: catching the engine's exception in
the app and reformatting it — that leaves validation timing wrong, keeps
the recorded-config hazard one code path away (any caller that skips the
pretty-printer records the lie), and masks genuine engine bugs behind a
formatter that cannot tell them from configuration mistakes.

**#127 — 2026-08-06 — Sparse `stripes` becomes a centred FULL-WIDTH
horizontal band (design-layer decision carried into the repo; implementation
assigned to Phase E).** #125 fixed `central_block` but explicitly flagged
the companion question — whether sparse `stripes` should span the grid's
full width — to the design layer rather than deciding it there. The design
layer has now decided: when N is below the site count, `stripes` uses a
CENTRED, FULL-WIDTH HORIZONTAL BAND as its footprint — every column
occupied, band height ≈ ceil(N / cols), centred vertically, with the
existing run-length row-major dealing unchanged inside it — so that sparse
stripes read as stripes rather than as a blob. ONLY `stripes` changes:
`blocks`, `checkerboard`, and `patches` keep the #119(a) centred
Chebyshev-ball footprint (their purposes — compact runs, maximal
interleaving, organic patches — are served by a compact blob), and
`central_block` keeps its #125 rectangle. Rationale: `stripes`' purpose
(spec Design 8) is broad horizontal bands, and a blob footprint destroys
exactly the property the layout is named for; the band restores it at the
cost of the footprint no longer being the same function across the
patterned layouts — a cost accepted because footprint-uniformity was an
implementation convenience (#119(a)), never a design commitment.
Implementation is assigned to Phase E, alongside the other layout-adjacent
polish; nothing in Phase C implements it. This entry exists so the decision
reaches the repo now rather than living only in a chat session.

**#128 — 2026-08-06 — The fourth positive golden master (sync imitation +
lattice) moves from Phase C to Phase D (a scheduling correction, not a
design change).** The spec's Design 9 lists four new positive golden
masters and V7 schedules golden masters for Phase C. But the
sync-imitation-plus-lattice golden is described by the spec itself as "the
interaction-only case — structure expressed purely through who plays whom",
and who-plays-whom is `matching.spatial_interaction` — Phase D machinery.
Recorded in Phase C, that golden would pin a run in which the lattice
affects nothing, and Phase D would discard and re-record it immediately.
DECIDED: Phase C records three positive goldens (sync economy + lattice;
async `fixed_n` + lattice + `death_birth`; async `variable_n` + lattice);
the fourth is recorded in Phase D when the behaviour it seals exists. The
spec is not edited (frozen, #62).

**#129 — 2026-08-06 — The reproduction validator tightens to
`offspring_stake + reproduction_overhead <= reproduction_threshold`,
discharging the ADVISORIES.md "Not an advisory" item (M11a Phase C; a
behaviour change — previously-legal configs become illegal).** The old
check compared σ alone against θ, but a breeding parent pays σ PLUS the
overhead, so with overhead 150, stake 400 and threshold 500 a parent at
exactly θ ended the boundary at −50 and died of insolvency one boundary
later — silently breaking the documented parent-survives-its-own-
reproduction guarantee. The check now compares the SUM, the message names
all three quantities, and the guarantee is restored — which Phase C's
`birth_first` order actively leans on: there the insolvency cull runs
AFTER stake payment in the same boundary, so without this fix a
just-bred parent could be culled by its own reproduction within one
generation. Scope of the break checked and reported: no shipped scenario
sets a non-zero overhead, and the one test fixture that does (overhead 50
against θ 500, σ 400) already satisfies the tightened rule — nothing
shipped had to change. The gate stays consumed-only (#34): imitation and
`fixed_n` (which lets parents go negative by design, #97g) are untouched.
The ADVISORIES.md section now carries its discharge note pointing here.

**#130 — 2026-08-06 — VT-4 answered at RUNTIME: `slots = K − survivors`
reads the APPLIED post-death list, so `birth_first` rations births against
the pre-death population (M11a Phase C; completes the code-inspection
evidence the spec held apart from verification).** The probe (temporary,
never shipped): well-mixed sync economy at the risk reading's worked
scale — K = 200, 180 founders, hazard tuned to ≈ 20 deaths per boundary,
everyone always above θ — identical config and seed under both orders.
OBSERVED: at the first boundary both orders drew 16 founder deaths;
`death_first` admitted 36 births (slots = 200 − 164, the post-death
list), `birth_first` admitted 20 (slots = 200 − 180 — no post-death list
exists yet, so the ration reads the pre-death living). Subsequent
generations: `death_first` sat pinned at 200 (deaths 30 → 30 births,
14 → 14); `birth_first` sat visibly lower at 184 / 169 / 179. The
registry help text for `dynamics.boundary_order` states both effects —
the smaller ration AND the newborn death-phase exposure — with the
worked numbers, and closes with "a `birth_first` run sitting at a
visibly lower population is correct, not broken". The slots computation
is deliberately left AS IS (the spec's phase plan pins it): reading
whatever list exists at that moment IS the documented second effect, not
a bug to fix.

**#131 — 2026-08-06 — `dynamics.boundary_order` as implemented: under
`birth_first` the newborns join the death phase as full members, and a
surviving newborn ages to 1 in its birth round (M11a Phase C; the one
micro-decision the spec left open, plus the H-A fidelity record).**
`death_first` is #80's frozen sequence executing byte-identically (pinned
by the negative goldens). `birth_first` runs the birth phase against the
pre-death living, merges the newborns into the population in ascending id
order, and runs the death phase — age-mortality coins (one per living
agent INCLUDING newborns, ascending id, the newborns last since their ids
are highest) then insolvency — over the merged list; the age increment
and score reset then also cover surviving newborns. CONSEQUENCE decided
here: a surviving `birth_first` newborn enters its first played
generation at age 1, its lifetime coin sequence p(0), p(1), ... starting
one boundary earlier than a `death_first` newborn's — one extra exposure,
which is exactly Hammond & Axelrod's ordering, kept deliberately faithful
so their results remain reproducible (owner-confirmed 2026-08-05).
Alternative rejected: keeping newborns out of the increment, which would
make them face p(0) twice — a doubled exposure no model in the lineage
has. Under async the parameter is never read; under sync imitation no
boundary of deaths and births exists, so it is consumed nowhere there
(the greying that expresses "live under all sync, greyed under async" is
Phase E's predicate table). FORWARD NOTE, recorded so the option stays
findable: a sub-toggle letting newborns SKIP the age-mortality coin in
their birth round was raised by the owner and deliberately NOT built —
if H-A fidelity ever needs relaxing, that is the knob to add, with its
own DECISIONS entry.

**#132 — 2026-08-06 — Design 7 as implemented: the `fixed_n` breeder and
victim draws localise through the birth kernel; R = 1 recovers Ohtsuki
exactly; sync imitation's comparison partner stays GLOBAL on scope
grounds, handed to M12 (M11a Phase C; resolves the spec's Open Question
1).** Under `death_birth` + lattice the victim draw is untouched (global,
per `fixed_n_death_rule`) and the BREEDER draw is substituted in place:
candidates are the freed site's occupied sites within the birth kernel
(`birth_radius`/`birth_decay` — under full occupancy, every site within
reach), weighted `exp(−β·d) × (e_i − min(e))` via `neighbourhood_sample`'s
`site_weights` hook — the #63 shift computed over the CANDIDATE set and
applied BEFORE the multiplication, uniform fallback on the COMBINED
vector, #112(b) partial-zero clamp semantics. At R = 1 every candidate
sits at distance 1, the kernel factors cancel out of the normalisation,
and the draw reduces EXACTLY to fitness-proportional over the neighbours
— the Ohtsuki corner, pinned by a draw-for-draw test against a plain #63
roulette over the neighbour set. Under `birth_death` + lattice the
breeder draw is untouched (global fitness-proportional) and the VICTIM
localises to the breeder's neighbours within the birth kernel:
`pure_random` becomes one kernel draw (uniform over the neighbours at
β = 0), `energy_decides` stays deterministic and draws nothing (poorest
candidate, ties to lowest id — the #80 active-flag idiom carried over).
Both are SUBSTITUTIONS — same position, same single draw, changed
candidate set and weights — so neither Moran rule gains or loses a draw
(spec Design 9), and the newborn always takes the freed site: under the
N = site-count validator full occupancy makes site recycling the only
possible placement (Design 1), so no placement draw exists in `fixed_n`.
THE EXPLICIT DECLINE, stated as the spec's docs obligations require:
synchronous IMITATION's `SelectionRule` comparison partner remains drawn
from the WHOLE population under a lattice — a scope-grounds decline, not
an omission (making imitation local is a genuine mechanism change to the
stable sync selection path, and M12 reopens imitation anyway for
in-group/out-group spread; the same shape as #110's
examined-not-triggered checkpoint). `structure.kind`'s `lattice` help
text says so where the choice is made.

**#133 — 2026-08-06 — The Phase C RNG contract as implemented: the
contest permutation is drawn under the three-way gate REGARDLESS of the
contest setting, applies to the id-ordered admitted list, and the
placement kernel draw is data-conditional; blocked parents travel as a
LIVE-only event field; the golden masters pin an explicit field list
(M11a Phase C; amends #80 per #107, the spec's Design 9 diff).**
(a) THE PERMUTATION. Drawn whenever synchronous + lattice +
`energy_economy` holds — the inventory's gate — even under
`placement_contest = energy_priority`, where its result is unused: gating
it on the contest CHOICE would make the stream depend on a widget that
only reorders iteration, and Design 6's draw-unconditionally fork already
settled that trade (a wasted draw costs nothing; a stream that shifts
with a setting costs debugging afternoons). It applies to the admitted
set listed in ASCENDING PARENT-ID order (principle 5) — never to the
energy-sorted admission list, the #107 trap the three-orderings fixture
pins (all three orders pairwise different; iteration follows the
permutation alone under `random`, energy-descending under
`energy_priority`, parent-id ascending with the gate off). Numpy fact
recorded for the contract's honesty: `Generator.permutation` at sizes 0
and 1 advances no bit-generator state (probed on numpy 2.5), so the
"call always happens" contract is physically a no-op in generations that
admit fewer than two parents — the counting-wrapper pins count CALLS,
not state movement. (b) THE PLACEMENT DRAW. One `neighbourhood_sample`
draw per iterated parent, over the empty sites within the birth kernel
of the parent's own site; when NO eligible site is in reach the
primitive returns empty BEFORE drawing, so a blocked parent consumes no
RNG — the draw count is a deterministic function of the occupancy
history, the #26 data-conditional precedent (threshold_cloning), not a
reproducibility hazard. Blocked means: no stake, no μ draw, eligible
next period (async: refractory anchor untouched). (c) THE BLOCKED
CHANNEL. `GenerationReport`/`GenerationFinished` gain
`blocked_parents: int = 0` — populated by the sync economy per
generation and by async `variable_n` per recording window — and the app
shows it as a live Economy metric (`ECONOMY_HELP["blocked_parents"]` is
the §12 single source). Deliberately NOT persisted: recorded folders
stay byte-identical (the #82/#100 additive-field precedent), and
persisting would widen `timeseries.parquet` with a column meaningless
for every non-lattice run (#47c's shape). A later milestone can promote
it with schema thought; the results browser therefore does not show it.
(d) THE GOLDEN TECHNIQUE. Four negative goldens (sync imitation, sync
economy, async `variable_n`, async `fixed_n`; all well-mixed) were
captured from the PRE-Phase-C engine and three positive goldens (#128)
from the finished one, each at two grains: a round-granularity
event-stream digest over an EXPLICIT per-event-type field list (so an
additive default-valued field cannot break a pin, while any changed
value inside the pinned fields does), and a content-grain run-folder
digest (parquet values in canonical CSV; summary.json minus its volatile
fields) that EXCLUDES `config.yaml` — the file legitimately grows a line
per newly registered parameter, as it did at M10a/M10b — with the
recorded config covered instead by a reload-and-re-run-to-the-pinned-
stream assertion. (e) TEST RETIREMENTS, per the Phase B baton and
#120(f)'s retire-with-replacement rule: `test_results.py::
test_newborns_have_no_site_in_phase_b` failed on Phase C's arrival
exactly as predicted and is replaced by
`test_newborns_carry_real_sites_from_birth` (the inverted assertion,
plus round-trip); `test_layouts.py::
test_a_deterministic_lattice_run_matches_the_well_mixed_stream` did NOT
fail — recorded honestly: its fixture was an IMITATION run, and
imitation has no births for local birth to touch — but is retired
anyway, because the general claim its name and docstring pinned
("a deterministic-layout lattice run matches its well-mixed twin") is
false as of Phase C for economy runs; the surviving imitation corner is
asserted more sharply by the no-draw pin (zero contest draws under sync
imitation + lattice) and the golden masters.

**#134 — 2026-08-06 — Carrying capacity becomes the third derived
default: blank K = the lattice's site count, or 200 in a well-mixed
world; the K-family validators land, including an N ≤ site-count check
the spec did not list (M11a Phase C; #106's design, #78's idiom).**
`dynamics.carrying_capacity` is now nullable with a BLANK registry
default, so the untouched panel's zero-effort path on a lattice is "the
grid decides" (K = site count) exactly as Design 1 requires. Blank in a
WELL-MIXED world resolves to 200 — the old registry default, kept as the
aspatial fallback so every existing config and every untouched
well-mixed panel behaves identically to pre-Phase-C (hard rule 8; old
YAMLs stored explicit numbers and never notice). Alternative rejected:
a validation error for blank-K-without-a-lattice — an error where a
sensible resolution exists contradicts the derived-default philosophy
(#112(a)'s reasoning). The resolution is a pure free function
(`resolve_carrying_capacity`, the `resolve_initial_energy` pattern)
running in the same experiment-level before-validator as the lattice
dimensions — dimensions first, K off their result — and `config.yaml`
always stores a plain number. VALIDATORS: K ≤ site count when K is
consumed (the grid is the outer bound, K an optional inner one; error
names both numbers); `fixed_n` + lattice requires N = site count exactly
(full occupancy is what makes site recycling the only possible Moran
placement; the message says why); and — an EXTENSION beyond the spec's
list, recorded as such — N ≤ site count for every evolution-mode lattice
run, because without it an imitation-mode overfull grid still surfaced
as a raw founding-time error inside the engine, and #126's discipline
(no reachable traceback for a configuration mistake) covers imitation
runs too; nothing previously RUNNABLE becomes illegal, since such
configs crashed at founding. ORDERING: the three lattice checks are
defined AFTER the #126 layout-file validator, so a from-file config
whose numbers disagree gets the message that knows about the one-click
populate button rather than a generic size complaint. Consequences
absorbed in tests: the #121 regression pin now sets K = 200 explicitly
(the defect state is no longer constructible from the default, which is
the fix working); the lattice persistence fixture pins K = 9 on its 3×3
grid (its inherited well-mixed K = 40 would no longer reload).

**#135 — 2026-08-06 — `site_capacity`: the field shipped pinned at 1 in
Phase A; the knob is M19's — recorded now with its three deferred
questions, closing a Phase A/B documentation gap (spec Design 12's
mandatory record).** The `Site` record has carried a `capacity` field
since Phase A, validated equal to 1 (`SITE_CAPACITY`), and the placement
seam reads `occupants < capacity` — so M19's capacity-above-1 is a
registry entry plus the removal of one validator, never a migration of
the seam (#104's forward-guard). No registry parameter exists because a
widget with exactly one legal value cannot be operated. The deferral is
not on effort grounds: capacity > 1 forces three questions M11a has no
answers to, recorded verbatim so M19 inherits them — (1) what the reach
kernel does at distance zero (co-residents sit at d = 0, and
exp(−β·0) = 1 is the MAXIMUM weight for every β — allowing capacity > 1
without confronting this would smuggle in "housemates are always the
most-preferred partners" as an arithmetic side-effect); (2) what colour
a cell holding one cooperator and one defector is (blending softens
cluster boundaries — the very signal the Hammond–Axelrod story is
about — so M19 likely wants both a blended and a dominant-strategy
view); (3) what k IS when neighbourhood size becomes
occupancy-dependent and changes every generation, which costs the
b/c > k comparison its fixed reference point. ROADMAP's M19 entry now
carries the explicit registration task line (also added this session —
the same gap). This entry should have been written with #112; logged
now rather than silently backfilled.

**#136 — 2026-08-06 — The live run view renders the CURRENT occupancy
from the latest snapshot (M11a Phase C; Design 10's "the snapshot is the
render state" made literal, and the piece V5 needs to be watchable).**
Phase B's renderer shows the FOUNDING arrangement — the panel preview and
the results browser replay generation 0 from (config, seed), which is
right for them. But V5 asks the owner to WATCH the occupied region drift
under a K below the site count, and nothing displayed occupancy after
generation 0. ADDED: during a live lattice run whose periods carry
per-agent snapshots (sync economy; async both modes), the run area
redraws the grid from the latest period's `site_id`/strategy pairs on
the same wall-clock-throttled cadence as the charts (#94), reusing the
existing `grid_chart`. Imitation runs have empty snapshots and keep the
founding preview — correct, since nothing moves after founding (#116).
No new machinery: the snapshot was designed as the render state (Design
10/#120(b)); this is the first consumer to read it live. The results
browser is unchanged (it still shows founding — rendering a recorded
run's FINAL occupancy from `agents.parquet` is a nicety deferred to
Phase E with the rest of the rendering polish).

**#137 — 2026-08-06 — The Phase D build record: local interaction lands as
two gated substitutions over the one Phase A primitive; the SpatialKernel
seam; the draw-unconditionally and empty-eligible contract; the inherited
RandomK behaviours; the requires-lattice validator; the matcher.py
docstring correction (M11a Phase D; spec Design 6 as implemented).**
(a) THE PARAMETERS. `matching.spatial_interaction` (bool, default off) is
registered FIRST in the Matching section, above `matcher` (Design 11's
clean greying direction — the map itself is Phase E's);
`structure.interaction_radius` (nullable int ≥ 1, default 1, blank =
unlimited via the `memory_depth` machinery) and
`structure.interaction_decay` (float 0–20, default 0) sit after the birth
group. Accepted interim state, deliberate (the spec's Design 5 error
asymmetry, mild direction): while the toggle is on the `matcher` widget
renders live but is not consulted, and while it is off the interaction
pair render live but are not consulted — the help text says plainly when
each is read; the greying predicates arrive with Phase E's table.
(b) THE SYNC SUBSTITUTION. When a synchronous evolution run has structure
AND the toggle on (the conjunction is the gate — Design 9's inventory),
the engine constructs `SpatialKernel(Matcher)` IN PLACE of the configured
matcher, for BOTH sync engines (imitation and economy; tournament ignores
structure wholesale, #120(a), and keeps `build_matcher`). The kernel is
genuinely thin: `pairings()` walks agents ascending-id and makes ONE
`neighbourhood_sample` call per focal (size = k, the interaction kernel,
eligible = occupied sites minus the focal's own site), mapping sites back
to agents; pairings are drawn eagerly before the first match plays (the
#57 no-interleaving contract). MICRO-DECISION, recorded: the matcher is
now constructed AFTER `found_population` in both sync engines' `__init__`
(the seam needs the occupancy); construction consumes no RNG, so the
reorder cannot touch any stream — pinned by the negative goldens passing
unre-recorded. The seam is a module-private factory
(`_build_generation_matcher`), not a `build_matcher` signature change —
the alternative (widening `build_matcher` to take an optional occupancy)
was rejected because the tournament path must never see the kernel and a
config-only factory cannot construct one.
(c) THE ASYNC SUBSTITUTION. Under lattice + toggle (both async population
modes, one call site), the focal-bundle partner draw is SUBSTITUTED in
place: same position in the within-event order, same single-draw shape —
one `neighbourhood_sample` call (size = k, interaction kernel, eligible =
occupied minus the focal's own) instead of one uniform
`rng.choice(N−1, ...)`. No draw gained or lost (#99/#133 discipline),
pinned by a test asserting a spatial `fixed_n` run's per-method call-name
sequence is IDENTICAL to its well-mixed twin's. The `fixed_n`
breeder/victim localisation (#132) is a different mechanism on the BIRTH
kernel and is untouched; sync imitation's comparison partner stays global
(#132's decline stands, handed to M12).
(d) THE RNG CONTRACT. Draw unconditionally (Design 6's resolved fork):
whenever spatial sampling is active the kernel call happens once per
focal agent even when k ≥ neighbourhood size and the outcome is forced —
stream position is a function of the config alone; per #133(a) the
contract counts CALLS (counting wrapper), not bit-generator movement.
Empty eligible set (an isolated focal): the primitive returns () BEFORE
drawing (its existing #133(b) data-conditional contract) — the agent
plays zero matches, consumes zero partner RNG, and no wasted draw is
added for it. Inherited RandomK behaviours, kept deliberately: NO
DEDUPLICATION (A can draw B while B draws A — income statistics stay
comparable to the well-mixed baseline; the `len(agent._histories)` sharp
edge stays as-is) and CLAMP, DON'T RAISE (#81 — a bounded-Moore corner
plays 3 at k = 8). New no-call pins: with the toggle off — well-mixed AND
lattice, sync AND async — zero interaction-kernel calls occur (sync
watched at `pdsim.core.matcher`'s primitive reference, which is
interaction-only by construction; async distinguished from Phase C's
size-1 breeder/victim/placement kernel draws by the interaction draw's
size = k signature), each with a toggle-on positive control.
(e) THE VALIDATOR. `matching.spatial_interaction` on requires
`structure.kind = lattice` — checked at config time in the #126
discipline (the message names both settings and says why: a well-mixed
world has no distance to sample within). Tournament mode skips the check
— structure is ignored wholesale there (#120(a)), and ignored parameters
are never validation errors (#34). No ordering subtlety arose: the
validator is independent of the layout-file and K-family checks.
(f) THE DOCSTRING CORRECTION. `matcher.py`'s module docstring no longer
justifies the Matcher ABC's full-`Agent` signature by a future
`agent.position` (the continuous-coordinate plan #104 dropped); the real
reason recorded in its place: `SpatialKernel` holds the structure and the
occupancy at construction, and an agent's location is its SITE — the
full objects buy identity (playable (Agent, Agent) pairs), not
coordinates. Comment-only; no behavioural effect.
All four negative and all three Phase C positive golden masters pass with
ZERO re-recording — every Phase D draw sits behind the
`spatial_interaction` gate, which no pinned configuration sets. 977 tests
pass; ruff clean.

**#138 — 2026-08-06 — #128 discharged: the fourth positive golden master
(sync imitation + lattice + `spatial_interaction` on) is recorded from
the finished Phase D engine (M11a Phase D).** The interaction-only case —
imitation reproduction, so no births and no deaths; the lattice expressed
purely through who plays whom. Configuration: 3×3 Moore torus, `stripes`
(deterministic — the founding-draw gate stays closed), N = 9, k = 3
(below the neighbourhood size of 8, so the kernel genuinely samples
rather than being forced), 4 generations, μ = 0.05, seed 43. Captured
with exactly the #133(d) technique: the round-grain event-stream digest
over the explicit per-event-type field list, the content-grain run-folder
digest excluding `config.yaml`, AND the reload-and-re-run-to-the-pinned-
stream assertion (the piece that covers the recorded config). Lives in
`test_phase_c_goldens.py`'s positive tables beside the Phase C three,
which keep their recorded scope and constants untouched.

**#139 — 2026-08-06 — VT-6(b) answered: EXACTLY 8 matches per agent per
generation — the ≈ in the spec's expectation dissolves into equality on a
fully occupied uniform-degree grid (M11a Phase D; the measured number the
design layer checks the flagship's `basic_living_cost` and the
calibration guide's §4.2 against).** The probe (temporary, never
shipped — the #117/#130 precedent): synchronous imitation on a fully
occupied 10×10 torus, `neighbourhood_shape = von_neumann`, both kernels
at radius 1, `spatial_interaction` on, 5 generations, measured at k = 4
and k = 6. OBSERVED: min = mean = max = 8.00 for every agent in every
generation at BOTH k values. The arithmetic, so the number is understood
rather than trusted: at k ≥ 4 every focal's draw is forced (or clamped)
to all 4 von Neumann neighbours — 4 initiated — and each of its 4
neighbours' draws are equally forced and include it — 4 received; 4 + 4
= 8, with no variance because degree is uniform on a torus and occupancy
is full and static under imitation. Design 6's no-deduplication text is
CONFIRMED (an engine that deduplicated would have shown 4). Consequences
are the DESIGN LAYER'S to act on, per the phase-task ledger: a
cluster-interior cooperator's income is ≈ 8R (not 4R) against the
flagship's living cost, and the Moore counterfactual is a four-fold
income change; nothing in the repo — no scenario, no living-cost value,
no calibration-guide text — was edited here. Also pinned as a permanent
test (`test_spatial_interaction.py`: every adjacent pair meets exactly
twice; every agent plays exactly 8).

**#140 — 2026-08-06 — V6 run by manual configuration, as the design layer
resolved (the `donation_game_threshold` scenario packages the same
configuration in Phase E); the observed result is MUDDY and is reported
as a finding, not fixed (M11a Phase D; the #117 honesty rule applied).**
Configuration, exactly as prescribed: donation game T = 5, R = 4, P = 0,
S = −1 (additive, b/c = 5), `rounds_per_match = 1`, AllC + AllD only,
asynchronous `fixed_n` (N = 100 = the 10×10 site count),
`moran_rule = death_birth`, `fixed_n_death_rule = pure_random`, torus,
both kernels at radius 1, `spatial_interaction` on; von Neumann at k = 4
(below b/c) versus Moore at k = 8 (above it); `initial_layout = random`,
μ = 0, horizon 150 generation-equivalents. A single seed pair was
ambiguous, so 20 seeds per shape were run. OBSERVED: von Neumann — AllC
fixed 11/20, AllD fixed 8/20, 1 coexisting at horizon, mean final
cooperator share 0.596; Moore — AllC fixed 10/20, AllD fixed 7/20, 3
coexisting, mean final share 0.569. Directionally von Neumann sits a
hair above Moore, but the separation (one seed in twenty) is well inside
sampling noise: NO visible b/c > k reversal at this configuration. The
honest reading, consistent with VT-3/#114's evidence: this engine's
selection is far from the weak-selection limit in which Ohtsuki's
threshold is derived — fitness reads ACCUMULATED energy through the #63
shift, with no intensity knob — so the threshold operates as the
calibration compass #103 said it was, not as a prediction; drift plus
strong selection washes the k-dependence out at these settings. Nothing
was tuned to force the textbook picture. The number and reading go back
to the design layer with the VT-6(b) report; the scenario text Phase E
ships must carry whatever caveat the design layer derives from this.

**#141 — 2026-08-07 — The Phase E1 build record: the Task 0 inspection
answers OUTCOME A, the greying map lands as ONE predicate table consumed
by both clock branches, and the §12 paint-time readouts land on two new
pure functions (M11a Phase E, sub-prompt 1; spec Design 11 as
implemented).** (a) THE INSPECTION (the phase's opening task, spec Design
11 extension 1): `helpers.greying` and `_async_greying` are chains of
plain-Python conditionals evaluated over the FULL widget-value mapping —
compound conditions already exist inline in both shapes (the Moran-weights
rule is an OR over two widgets; the async delegation itself is an AND) —
so predicates over the mapping are trivially admissible and the table was
built directly in that form (Outcome A). No adapter was needed; the
pre-existing rule chains are preserved byte-for-byte outside the cells
Phase E names. (b) THE TABLE: `helpers.STRUCTURE_GREYING`, key →
`GreyingRule(sync, asynchronous)`, each column a predicate over the
values mapping returning the greyed-state note or None-for-live — notes
BY CAUSE (the radii's OR names whichever condition holds;
`placement_contest` has four cause notes), wording drawn from the
registry descriptions where they already state the reason (§12's
single-source rule). `greying` consults the sync column,
`_async_greying` the async column; the tournament wholesale-ignore runs
before either branch, so the two rows reachable under tournament
(`matching.matcher`, the composition pseudo-key) self-guard on the mode.
`grid_visible` (#121) stays BESIDE the table as its visibility sibling —
it decides showing, not greying — and the composition row reuses it
rather than duplicating its logic. M11b's tab/collapse work becomes a
second renderer over this same table (the spec's stated payoff).
(c) PRECISION taken on the matcher's sync cell: it greys on the ENGINE's
actual gate — evolution AND lattice AND toggle (#137(b)) — not on the
toggle alone as the sub-prompt's shorthand had it, because with the
toggle stranded on under `well_mixed` (a greyed checkbox keeps its
value) or under tournament the configured matcher genuinely IS consulted,
and the note would assert something false (#34). Same cell, sharper
predicate. Consequently `matching.opponents_per_agent`'s pre-existing
round-robin greying (#57) gained a guard: it must not fire while spatial
sampling is active, where the (greyed) matcher is unconsulted and k does
the work (#108) — item 9's live-always cell made consistent.
(d) THE ASYNC MATCHER CELL moved into the table from `_async_greying`'s
inline check (and out of `_ASYNC_INERT`), with the Phase D baton's
imprecision corrected: the old note claimed partners are drawn "uniformly
(the well-mixed corner)", true only while the toggle is off (#137(c));
the new note covers both draws. Same answer — always greyed under async.
(e) THE PAINT-TIME FUNCTIONS (spec Design 11 extension 2), both in
`pdsim/config/experiment.py` beside the resolvers:
`effective_neighbour_count(shape, boundary, k)` = min(k, 8|4) — boundary
accepted so the signature states the full geometry but documented as not
moving the interior number — and `payoff_additivity(T, R, P, S)` (#111's
readout 9) returning additive/b/c/ratio with the T − R = P − S test on
`math.isclose` and ratio None when c = 0. THE READOUTS: "Grid (resolved)
auto → r × c" beside blank dimension widgets and "Effective neighbours
(k)" while spatial interaction is on (both above the grid preview);
"Capacity K (resolved) auto → K" as a fourth metric literally beside the
site count whenever K is blank on a lattice (#106's both-numbers guard);
and the additivity verdict beside the payoff widgets in evolution mode
(defaults read NOT additive, T − R = 2 vs P − S = 1; the donation matrix
reads b/c = 5). (f) MACHINERY: the #101 lookahead now also reconstructs
NULLABLE keys' forward values from their checkbox/value widget-state
pairs — needed because K renders in Dynamics, one section after the
Structure readout that displays it; behaviour-neutral for every greying
predicate (none reads a nullable). (g) The `matching.matcher` registry
description's stale sentence ("Distance-based matching arrives with the
geographic layer in a later version" — false since Phase D) is replaced
by the truth the greyed note also tells: while the toggle is on, partners
come from the grid and the scheme is not consulted. `PARAMETERS.md`
regenerated. All eight golden masters (four negative, four positive)
pass with ZERO re-recording; 1006 tests pass; ruff check and format
clean. One prompt discrepancy noted for the record: the sub-prompt's
test list says `boundary_order` is pinned live under "all three
reproduction modes" — `dynamics.reproduction_mode` has exactly two
values (imitation, energy_economy); both are pinned.

**#142 — 2026-08-07 — `matching.spatial_interaction` greys under
`well_mixed`, both branches, note "needs a lattice world structure"
(M11a Phase E1; a design-layer addition beyond the spec's enumerated
map, decided 2026-08-07).** Until now the #137(e) requires-lattice
validator was the ONLY guard, so the toggle rendered live in a
well-mixed world and invited an avoidable validation error; a greyed
widget saying "this exists and does nothing here" is the #34-correct
surface (greyed, never hidden — and never a surprise error for an
ignored parameter's gate). This is the map's genuinely FORWARD-POINTING
rule — the Matching section renders four sections above Structure, so
the predicate reads `structure.kind` through the #101
session-state/default lookahead — exercising exactly the machinery
Design 11's section-order trade-off (#100(e)/spec) accepted. The note's
wording is the validator's own reason: in a well-mixed world there is no
distance to sample within.

**#143 — 2026-08-07 — Under `from_file` the composition widgets GREY
(the #124 interim treatment's designed end-state), the Populate button
remains the write path, and `population.size` stays live (M11a Phase
E1; spec Design 8 consequence 1 delivered).** When evolution + lattice +
`initial_layout = from_file` hold — both clock branches, via the
`population.composition` pseudo-key row of the #141 table — the mix
widgets disable with the note "set by the layout file … use the
Populate button", because the file decides both arrangement and mixture
and editable widgets restating it are two sources of the same truth
that can silently disagree (Design 8's trap). The #124 one-click
populate offer REMAINS as the write path (a Streamlit button callback
may write disabled widgets' session state — greying blocks USER edits
only), and the #126 composition-equality validator REMAINS as defence
in depth: greying changes what the user can edit, never what is
checked. `population.size` deliberately has NO table row — spec Design
11 keeps it live and validated. Under tournament the composition stays
fully live (the layout is ignored wholesale there, and founding still
deals the widgets' mix).

**#144 — 2026-08-07 — Tournament mode now greys structure wholesale:
all twelve `structure.*` keys, `matching.spatial_interaction`, and
`dynamics.boundary_order` join `IGNORED_IN_TOURNAMENT` (M11a Phase E1;
the sub-prompt's item 13 inspect-and-report, resolved as plainly
accidental).** THE INSPECTION FOUND: every structure widget rendered
LIVE under `run.mode = tournament` although tournament ignores structure
wholesale (#120(a)) — the `IGNORED_IN_TOURNAMENT` tuple is dynamics-only
and simply predates M11a, and Phases A-D deferred ALL structure greying
to Phase E; nothing anywhere records a deliberate live-under-tournament
choice (the one deliberate tournament exclusion, `grid_visible`'s, hides
the PREVIEW, not the widgets). The same omission covered
`dynamics.boundary_order` from Phase C: it rendered live under
tournament while every other Dynamics parameter greyed. Both are the
#34 pattern's plain case — a parameter that exists but has no effect in
the mode greys with the explanatory note — and the fix is a tuple
extension the table makes trivial. `structure.kind` itself greys too:
under tournament it gates nothing, exactly like `reproduction_mode`
(#34's precedent for greying a gate in a mode that ignores its whole
family). The generic tournament note is reused unchanged; the
tournament check keeps running BEFORE both table branches, so the
mode-level note wins.

**#145 — 2026-08-09 — The pixel-array rendering fallback and the ≈ 3 px
cell floor land inside the ONE `grid_chart` path, with the ninth §12
readout reading the renderer's own switch (M11a Phase E2; DESIGN §6.3's
rendering contract completed).** (a) THE SWITCH. A named module constant
`PIXEL_ARRAY_THRESHOLD = 2500` in `pdsim/viz/charts.py`: at or below
2,500 sites `grid_chart` builds the Phase B bordered heatmap (1 px cell
gaps, per-cell hover labels); above it, a single `go.Image` trace — one
RGBA pixel block per site, empty sites TRANSPARENT so the shared plot
background shows through them exactly as the heatmap's None cells do.
2,500 (a 50×50 grid) sits comfortably inside the contract's "a few
thousand". FINDING, recorded because the E2 prompt's rationale assumed
otherwise and asked for a report: the Phase B renderer was NEVER
thousands of individual plotly shapes — #120(e) built it as ONE heatmap
trace — so the switch is bordered-heatmap → image trace, not
shapes → image. The threshold value stands anyway: past a few thousand
cells the bordered path rebuilds per-cell gap strokes and a full
hover-label array on every #94-throttled redraw, wasted work at cell
sizes where the borders are invisible; and the two-trace-kind split is
what makes the fallback directly testable (the pin asserts trace kind at
49×49 vs 51×51). Both paths read the SAME `strategy_colors()` mapping —
no second palette — pinned by construction (the heatmap's discrete
colorscale must carry the registry colour verbatim; the image's pixel
must be that colour parsed to RGB). (b) THE FLOOR. `floored_canvas`
computes the contract's naive side min(width/cols, height/rows) against
a NOMINAL canvas of 700×450 (Streamlit's content-column width by
plotly's default figure height — the two numbers the un-floored figure
actually gets); when the side falls below `CELL_FLOOR_PX = 3` the figure
takes an explicit width/height at exactly 3 px per cell plus margins,
and the app renders it UN-STRETCHED (`st.plotly_chart` width "content"
via the `_grid_width` helper, all three consumers) — stretching a
floored figure back into the column would shrink cells below the floor
again. The floor applies on both paths and composes with the pixel
switch (pinned at 300×300). (c) THE NINTH §12 READOUT. "Pixel-array
rendering" (on/off) joins the grid's metric row in `_grid_area`, its (?)
from the new `STRUCTURE_HELP["pixel_array"]` entry (the single described
source, like the E1 readouts), its value from the SAME
`charts.pixel_array_active` predicate the renderer consults — readout
and renderer cannot disagree. This completes the nine derived readouts;
the E4 audit should find it here. (d) ONE CODE PATH, kept: panel
preview, live run view (#136), and results browser all render through
`grid_chart` and inherit both mechanisms; no per-surface renderer was
forked. 1017 tests; all eight golden masters pass with zero
re-recording (presentation only — no draw added, moved, or removed).

**#146 — 2026-08-09 — The results browser renders a recorded run's FINAL
occupancy: a Founding | Final selector defaulting to Final, gated by
PRESENCE of recorded site ids, never by mode (M11a Phase E2; #136's
deferred half delivered).** When a recorded run's per-agent snapshots
carry real site ids (sync economy; async both modes — schema 5), the
browser offers a two-way "Grid view" radio — Founding | Final —
DEFAULTING to Final: the browser answers "what happened", and the final
state is the answer; the founding view stays one click away for
arrangement questions. Final renders the LAST recorded period's
site_id/strategy pairs through the same `grid_chart`; Founding is the
unchanged #120(e) replay. The presence test is
`helpers.final_occupancy(timeseries)` — pure, Streamlit-free, pinned:
it answers None (no selector, founding view exactly as today) when no
snapshot anywhere carries a site id, which covers BOTH legacy shapes at
once — imitation runs (#116: no snapshots persisted at all) and
schema ≤ 4 economy folders (snapshots without the site column) — the
#100(b)/#120 presence-driven discipline, so old folders behave
byte-for-byte as before with no version check anywhere. MICRO-DECISION:
a run that ended EXTINCT returns an EMPTY mapping, not None — earlier
periods carried sites, so the selector stays and Final draws an empty
world, because nobody-left-alive IS that run's final occupancy and
hiding it would misreport what happened.

**#147 — 2026-08-09 — `test_phase_c_goldens.py` → `test_golden_masters.py`
(M11a Phase E2; pure housekeeping).** The file has housed the Phase D
fourth positive golden since #138, so the phase-specific name misled.
Renamed with NO pin re-recorded and no constant, digest, or fixture
touched; the module docstring now states what the file holds — the four
negative and four positive golden masters and the #133(d) capture
technique — with phase names kept only as capture provenance. The two
live comment references (`test_layouts.py`, `test_spatial_interaction.py`)
updated; DECISIONS mentions of the old name are historical record and
stand. The golden suite runs as
`pytest pdsim/tests/test_golden_masters.py`.

**#148 — 2026-08-09 — The #127 sparse-`stripes` band is BLOCKED and NOT
implemented: two of #133's positive golden masters pin sparse-`stripes`
foundings, so the band cannot ship under E2's zero-re-recording guard —
referred to the design layer (M11a Phase E2; an open question logged,
not a decision).** THE CONTRADICTION, found by the session-start check:
the E2 prompt's premise — "#125 and #138 establish that no golden master
covers any sparse layout" — is FALSE. #125's "no golden master existed
on the sparse case" was true when written (2026-08-04, Phase B
follow-up), but Phase C's positive goldens (recorded 2026-08-06, #133)
include two sparse-`stripes` configurations: `sync_economy_lattice`
(N = 6 on 3×4 — 12 sites) and `async_variable_n_lattice` (N = 10 on
4×5 — 20 sites). Verified by computation against the live code: the
band would move `sync_economy_lattice`'s footprint from the #119(a)
ball {1,2,5,6,9,10} to {0,1,2,3,5,6}, and `async_variable_n_lattice`'s
from {1,2,3,6,7,8,11,12,13,16} to {5..14} — different foundings,
different placement-kernel eligible sets, different stream AND folder
digests. The band and the zero-re-recording guard are therefore
IRRECONCILABLE for these two pins: no implementation freedom exists
(#127 fixes the band exactly; the digests pin the ball exactly). Per
the E2 prompt's own tripwire ("if any golden fails, STOP and report" —
though the failure mode here is a false premise, not a band leak) and
the project rule that golden re-recording is a logged design-layer act,
E2 shipped WITHOUT Task 3: no footprint change, no #120(f) test
retirements (the #125 fallback pin still correctly references
`stripes`), no band pins, no stripes-vs-blocks differentiation pin. The
third golden (`async_fixed_n_lattice`, N = 9 on 3×3) and #138's fourth
are full grids and untouched by the band; also checked and unaffected:
every other sparse-`stripes` fixture in the suite (3×3 at N = 4 and
N = 8, where band and ball coincide cell-for-cell; the 6×6 N = 5
orderings fixture, which pins orderings and invariants, not footprints).
THE DECISION THE DESIGN LAYER NOW OWNS: either (a) re-record the two
Phase C positive goldens under a new DECISIONS entry (a deliberate,
logged re-pin — the band is a designed behaviour change and these two
pins were captured 2026-08-06 against the interim ball footprint #127
itself calls wrong for `stripes`), or (b) re-pin those two goldens on
configurations the band cannot touch (full grids, or a non-`stripes`
layout) and then land the band against unchanged constants, or (c)
amend #127. Until that ruling, sparse `stripes` keeps the #119(a) ball
footprint everywhere.

**#149 — 2026-08-09 — Two rendering fixes from the owner's E2 manual
validation: the pixel-array switch gains a small-cell trigger (elongated
grids), and floored figures keep a minimum canvas width for their chrome
(M11a Phase E2 follow-up; owner-reported defect plus an owner-proposed
amendment, decided in-session).** THE DEFECT, from validation step 2
(200 rows × 10 columns): the floored figure took an explicit canvas of
70 px — 10 columns × 3 px plus margins — so the title and the plotly
modebar (zoom/pan/autoscale) collided unusably; and because 200×10 is
only 2,000 sites (below #145's 2,500-site threshold), the grid kept the
BORDERED heatmap path at floor-sized cells, where the 1 px gap stroke
eats a third of every 3 px cell and ten columns degrade into
disconnected dots that read as four or five. TWO FIXES, both in
`pdsim/viz/charts.py`, both presentation-only (no RNG, no goldens):
(a) `floored_canvas` never returns a width below
`_MIN_CANVAS_WIDTH = 320` — room for the title and modebar; the
square-cell constraint centres a narrow grid in the extra width.
(b) `pixel_array_active` gains a SECOND sufficient trigger: the naive
cell side (the #109 arithmetic, min(700/cols, 450/rows)) falling below
`BORDER_MIN_SIDE_PX = 6` — at 6 px the gap is a sixth of the cell and
borders still read as borders; below it they eat the cells. THE RULE
CHOICE: the owner proposed keying the switch on max(rows, cols) rather
than site count; implemented as the cell-side form because it is the
same idea made exact — max(rows, cols) is a proxy for "cells got
small", and the renderer can compute cell size directly. Equivalences
and differences, stated: on square grids the new trigger never fires
before the 2,500-site threshold (50×50 parity intact, #145's pins
unchanged); on the owner's 200×10 both forms switch to the pixel path;
they part company only on small elongated ribbons (e.g. 60×5 — 300
sites, 7.5 px cells), where max(rows,cols) > 50 would drop borders and
per-cell hover labels that still comfortably fit — the cell-side form
keeps them. Pinned: 200×10 renders as an image below the count
threshold; 60×5 keeps its heatmap; floored_canvas(200,10) = (320, 660).
The §12 readout stays honest for free (it reads the same predicate),
and its `STRUCTURE_HELP["pixel_array"]` source now describes both
triggers. DESIGN §6.3's "past a few thousand cells" contract is
EXTENDED, not contradicted: the count trigger stands; the small-cell
trigger adds pixel-array rendering in a regime the contract never
addressed. 1020 tests; all eight golden masters still pass with zero
re-recording.

**#150 — 2026-08-09 — The #148 ruling: option (a). The #127
sparse-`stripes` band lands exactly as decided, and the two colliding
Phase C positive goldens are RE-RECORDED as a logged decision (M11a
Phase E2b; discharges #148, implements #127).** THE RULING. The design
layer chose #148's option (a): land the band as #127 records and
re-record `sync_economy_lattice` (N = 6 on 3×4) and
`async_variable_n_lattice` (N = 10 on 4×5) under this entry — the
#133(d) technique's sanctioned path for deliberate, DECISIONS-logged
behaviour change. Rationale: positive pins exist to catch UNINTENDED
drift, and this change is the opposite — the band was decided (#127,
2026-08-06) BEFORE the pins were recorded the same day, with
implementation assigned to Phase E, so the collision is fixture
accident, not design conflict. Option (b) (re-pin onto configurations
the band cannot touch) was rejected because it forces the same
re-record while REMOVING sparse stripes from golden coverage — after
(a), the band itself is pinned. Option (c) rejected: #127's rationale
stands. THE BAND, as implemented (`layouts._stripes_footprint`): when N
is below the site count — impossible under `fixed_n` by validator —
`stripes` occupies ceil(N ÷ cols) rows, centred vertically by integer
division (top = (rows − rows_needed) // 2); every band row is
full-width except, when N is not a multiple of cols, the band's LAST
row, which holds the remainder centred horizontally (start = (cols −
remainder) // 2). Dealing inside is unchanged (run-length, row-major,
ascending machine name); no RNG on any path — the #119(f) gate stays
closed, asserted via the counting wrapper (zero generator calls of any
kind on the sparse-stripes founding path). ONLY `stripes` changes:
`blocks`/`checkerboard`/`patches` keep the #119(a) ball (pinned as the
replacement test), `central_block` keeps its #125 rectangle, full-grid
`stripes` is untouched (#138's golden passed un-re-recorded). TEST
RETIREMENTS, per #120(f) retire-with-replacement: the Phase B
sparse-stripes ball pin is replaced by band pins — 20×20 N = 60 → rows
8–10 full-width; 20×20 N = 50 → rows 8–9 full plus ten centred cells in
row 10 (cols 5–14); the two #148 footprints (3×4 N = 6 → {0,1,2,3,5,6};
4×5 N = 10 → {5..14}) pinned at the goldens' own compositions — plus a
stripes ≠ blocks differentiation pin at N = 60 on 20×20. The #125
fallback pin is RE-REFERENCED: the no-fit fallback now asserts equality
with `blocks`' footprint (which IS the generic centred blob), stating
what #125 decided instead of coupling to `stripes`. TWO FURTHER
#125-era pins coupled to ball-`stripes` broke by design and got the
same re-referencing treatment, recorded here because the E2b prompt
did not name them: the N = 10-on-5×5 true-rectangle pin's blob contrast
moved to `blocks` (and the NEW coincidence — at that N the band IS the
2×5 rectangle, both centring by the same integer division, both dealing
run-length row-major — is pinned as inherent, the sparse sibling of
#125's full-grid coincidence); and the N = 30-on-12×12
blob-equals-rectangle pin became footprint equality against `blocks`
(placement equality was a ball-stripes accident — `blocks` deals along
its tiled serpentine). THE RE-RECORD, as a verified procedure: (1) with
the band in, the golden suite failed on EXACTLY the two named pins
(stream + folder digest each); the four negative pins, both full-grid
positives, and the Phase D reload assertion all passed — no leak.
(2) Before touching constants, both configs' new foundings were
asserted equal to the #148-computed band footprints, against the actual
golden configs. (3) The two pins were re-recorded with the FULL
#133(d) technique — stream digest over the explicit field list, folder
digest, AND the reload-and-re-run-to-the-pinned-stream assertion, which
the two pins now carry permanently (previously only the negatives and
the Phase D golden did; `async_fixed_n_lattice` alone keeps its
original Phase C recorded scope). (4) The full suite is green (1029
tests) and the diff confirms exactly four constants changed — the two
pins' stream + folder digests — and no other golden constant moved.
The founding-isolation readout needed no code change (a full-width band
has zero isolated agents); no registry entry changed, so no gendocs
run.

**#151 — 2026-08-10 — The four M11a scenarios are REGISTERED:
`spatial_reciprocity` / "Cooperation Survives in Clusters" (the
flagship), `donation_game_threshold` / "The b/c > k Threshold",
`the_drifting_frontier` / "The Drifting Frontier", and
`the_filling_grid` / "The Filling Grid" (M11a Phase E, sub-prompt 3;
the spec Validation section's four named scenarios delivered).** Each
is ONE configuration per #36, comparative questions confined to
things-to-try; every override of a registry default is deliberate, its
reason carried in the scenario text itself, and the worked arithmetic
is written so a novice can reproduce every number in a description
from the settings shown. THE FLAGSHIP packages the #111(c)/#115
design: synchronous `energy_economy` on a 20×20 torus (400 sites for
N = 200 — a half-empty world with room for clusters; blank dimensions
would have auto-sized to a full 200-site grid), AllC 100 / AllD 100
founded as `patches` (contiguous clusters from generation 0, dealt
inside the Design 8 centred blob), `von_neumann` (#111(c): fewer
neighbours, stronger viscosity), spatial interaction on with k left
at 5 clamping to play-all-4, ONE round per match (matches and rounds
become the same number, so every income figure is per-generation),
T = 5, R = 3, P = 0 (#111(c): a defector interior must earn NOTHING
against the living cost), S = −1 (#115: ordering legality with P = 0,
and bleeding cluster edges), ledger L = 12 / θ = 60 / σ = 40 — the
#139-measured 8 matches per fully-neighboured agent give all-C
interior income 24 and all-D interior income 0, window 0 ≤ L < 24
with L at the midpoint; at L = 12 a cooperator with n cooperating
neighbours earns 8n − 8 (interiors +12, flat edges +4, corners −4),
interior defectors die during generation 4, and interior cooperators
first breed at generation 2 (64 ≥ 60) on a three-generation rhythm —
μ = 0 (a copying-rule mutant seeded inside a cluster would muddy the
interior arithmetic the scenario exists to display), horizon 100 (the
drama completes well inside it). The #111 conceptual guard is in the
text verbatim in spirit: the story is ECOLOGICAL, not Ohtsuki's — and
the matrix is not additive (T − R = 2 ≠ 1 = P − S), so "b/c" is not
even defined here. `donation_game_threshold` packages #140's measured
configuration verbatim: asynchronous `fixed_n`, `moran_rule =
death_birth` (stated: the threshold is a death-birth result),
`fixed_n_death_rule = pure_random` overriding `energy_decides`
(Ohtsuki's death is RANDOM, its neighbours then compete by fitness —
the default's deterministic death is a plausible run that is not the
model), N = 100 on an explicit 10×10 (the fixed_n N = site-count
validator satisfied legibly), `von_neumann` (the case that CLEARS
b/c = 5, so the default view shows cooperation succeeding),
opponents = 4 (exact play-all at the von Neumann degree), the
donation matrix T = 5, R = 4, P = 0, S = −1 (additive, c = 1, b = 5
per #111 — the text carries the read-the-cost-off-twice arithmetic
and the fact that additivity with P = 0 FORCES S = −1), one round
with AllC 50 / AllD 50 only (one-shot derivation; reciprocity
parameters inert, and the text says where the roster went), `random`
layout, μ = 0 (fixation must be permanent to be readable), horizon
150 (#140's). Its weak-selection caveat uses the #114/#117 softened
wording — selection begins at exactly zero and strengthens from
nothing; fitness reads a STOCK, so the draw partly selects for age —
plus #140's measured consequence (mean final cooperator share 0.596
von Neumann vs 0.569 Moore at 20 seeds per shape, inside sampling
noise, no visible reversal) and the verbatim compass phrase. THE
NUMBERS THIS DESIGN SESSION FINALISED: `the_drifting_frontier` ships
the growth economy's ledger AT DEFAULTS (θ = 500, σ = 400, L = 200)
on a 20×20 lattice — `random_k` k = 5 with 10 rounds gives matches
≈ 2k = 10, 100 rounds, window 100 ≤ L < 300 with L at the midpoint
(deliberately the calibration guide §4.5 worked example) — K = 240
explicit (60% of the 400 sites, #106's slack live so the occupied
region drifts rather than fills), N = 120 (TitForTat/AllC/AllD 40
each, `patches`), spatial interaction OFF deliberately (local birth
WITHOUT local interaction is a named legitimate configuration; this
scenario demonstrates the separability — children land near parents
while everyone plays everyone — which also keeps the window
arithmetic aspatial), `base_hazard = 0.05` for churn (deaths free
sites anywhere; births refill only near parents), and
`senescence_factor = 1` EXPLICIT: blank would ALSO resolve to 1.0
here (`resolve_senescence_factor` falls back to "age never matters"
unless both a hazard and a max age are set, and max_age is 0), but
the scenario states its intent rather than leaning on a fallback.
`the_filling_grid` ships L = 40 / θ = 200 / σ = 150 with N = 60
(AllC/AllD 30 each) as `central_block` — the centred 6×10 rectangle
with 340 empty sites, the filling regime #109 shipped the layout for,
named at DESIGN §6.3's qualitative level only (the four #103/#111
literature gates honoured: no wrap-around claim, no period figure, no
σ formula, no cited assumption set) — Moore kept deliberately as the
anti-flagship contrast, opponents = 8 play-all, 10 rounds, payoffs at
DEFAULTS with P = 1 deliberate: the saturated defector interior earns
16 × 10 × 1 = 160 and never starves, the saturated interior window is
160 ≤ L < 480 and L = 40 sits BELOW it — the metabolic filter is OFF
for interiors at saturation, only fully-encircled cooperators can
starve (one cooperator contact = 60 clears the bill; zero contacts =
0 does not), so the endgame is a slow one-cell-at-a-time grind and
RISE-THEN-FALL is the expected observable, not cooperation winning;
horizon 300 (the fill is fast, the grind is slow, and the fall half
needs room to be visible). THE FOUR HORIZONS, with their one-line
reasons: 100 (flagship — interiors die by ~4, edges over tens),
150 (#140's measured horizon), 200 (frontier — mean lifetime 20 at a
5% flat hazard, ten full turnovers), 300 (filling — the slow half).
SEEDS: 42/7/11 (flagship, frontier, filling grid) are arbitrary
house-style picks; the donation scenario's seed 4 is CURATED — a
twelve-seed check during E3 validation split 6/6 between the two
fixations (the #140 coin flip made concrete), and the spec's frozen
intent is that the default view shows cooperation succeeding, so a
cooperation-fixing seed ships, with a sentence in the scenario text
saying so plainly (the `moran_random_mix` curated-seed honesty
precedent: "this seed happens to…" is stated, never hidden).
MECHANICS: the four join #36's shrunk-copy smoke test, whose helper
now shrinks a `fixed_n` lattice scenario to N = 9 on 3×3 (composition
topped up cyclically) to preserve the N = site-count validator. Alternatives
rejected: sibling comparison scenarios (#36 — comparisons live in
things-to-try); and letting the load-bearing payoff and ledger values
ride on registry defaults inside the config dicts — scenario configs
are constructed from the registry at import, so a future default
change would silently rewrite a scenario's worked arithmetic; every
payoff is pinned explicitly in all four configs.

**#152 — 2026-08-10 — Three things-to-try rewordings, recorded as one
consolidated deviation from the frozen spec: predictions replaced by
stated arithmetic, per the Phase D measurements (#139, #140) (M11a
Phase E, sub-prompt 3).** The spec's Validation wording is frozen
(#62), so the deviations are logged here rather than edited in, and
all three exist for the same reason: things-to-try text that promises
an outcome the arithmetic does not support — or that walks the user
into a validation error — is worse than a logged rewording.
(a) `donation_game_threshold`: the spec's "switch
`neighbourhood_shape` to `moore` and re-run, predicting the reversal
before doing it" becomes state-the-prediction, run, and EXPECT VERY
LITTLE VISIBLE CHANGE — #140 found no visible reversal at 20 seeds
per shape, so the gap between the prediction and the observation IS
the weak-selection lesson the scenario teaches; the compass points
where the prediction cannot. (b) the flagship's "switch back to
`well_mixed` and watch AllD take everything" gains the required order
of operations — spatial interaction OFF first, while the toggle is
still editable, because under `well_mixed` it greys with its value
stranded (#142 greys, never un-sets) and a stranded-on toggle fails
the #137(e) requires-lattice validator — plus the matcher instruction
(set `random_k`: the default round-robin at N = 200 gives 199 matches
and income two orders of magnitude above L = 12, so the filter would
simply be off; and blank K falls back to the aspatial 200 = N,
freezing the demography) and the honest full arc: AllD sweeps, and
then, with the cooperators gone, all-defector income is 0 < L = 12
and the whole population collapses — the tragedy completes.
(c) the flagship's "switch `neighbourhood_shape` to `moore` and watch
the clusters struggle" becomes income arithmetic with the outcome
left open: the naive reading says von Neumann means 4 matches, the
#139-measured truth is 8, and Moore at k ≥ 8 gives 16 by the same
arithmetic — a FOUR-fold income change against the naive reading but
two-fold against the actual — with the window becoming 0 ≤ L < 48
and L in its lower quarter; whether clusters struggle under the
weaker viscosity is something to watch, not something promised, and
the user is told to recompute the window before trusting any living
cost after the switch. Alternative rejected: shipping the spec's
wording as-is — (b) would trap the user in a validation error by
ordering the structure switch before the toggle, and (a)/(c) would
promise a reversal and a struggle that #140/#139's measurements say
this engine's selection strength does not deliver on cue.

**#153 — 2026-08-10 — Findings from E3's app validation, REPORTED AND
HELD (Rule 7 — nothing fixed in this sub-prompt): the Economy panel's
calibration report ignores `matching.spatial_interaction`, and two of
the E3 prompt's validation expectations mismatch designed panel
behaviour (M11a Phase E, sub-prompt 3).** (a) THE REAL GAP, surfaced
by the first spatial + economy scenarios the platform has shipped:
`economy_helpers.calibration_report` branches on `matching.matcher`
alone (N − 1 under round_robin, ≈ 2k under random_k) and never
consults the spatial toggle, so while spatial interaction is ON the
Economy panel reports the GREYED, unconsulted matcher's arithmetic.
Loaded, `spatial_reciprocity` shows "Matches per agent 199" and
window 0 ≤ cost < 597 where the truth (#139, and the scenario's own
text) is 8 matches and 0 ≤ L < 24; `the_filling_grid` shows
59 / 1770 / 590 where the saturated truth is 16 matches, 480 / 160.
The scenario TEXTS carry the correct arithmetic, and
`the_drifting_frontier` — spatial off deliberately, its calibration
aspatial — reads correctly (10 matches, window 100 ≤ cost < 300).
The readout predates M11a (M10a's Economy panel) and Phase D did not
extend it; the natural formula is the calibration guide §4.2's
matches ≈ 2 × min(k, degree), but the design choice (min-degree
versus a per-site expectation on partially occupied or bounded
grids) is the design layer's to make — E4's §12 audit is the likely
vehicle. (b) TWO EXPECTATION MISMATCHES, recorded so the E4 auditor
does not re-derive them: the E3 prompt expected the flagship to show
"Capacity K (resolved) → 400 beside the site count" and the frontier
"240 beside the 400-site count". Neither renders, by design: #141's
blank-K metric fires only while the K WIDGET is blank, and a
validated scenario config stores K resolved to a plain number (hard
rule 8), which the scenario loader writes into the widget — the
flagship loads with K = 400 explicit, the frontier with 240
explicit, and both numbers are still on screen (the K widget itself
plus the Sites metric), just not via the blank-K metric. Related
presentation note, same mechanism inverted:
`helpers.widget_values_from_config` re-presents stored values that
EQUAL their auto-resolution as blank-auto (its documented loss-free
inverse), so `donation_game_threshold` — whose explicit 10 × 10 IS
the most-square resolution of N = 100 — loads with blank dimension
widgets and shows "Grid (resolved) auto → 10 × 10", and
`the_drifting_frontier`'s explicit senescence factor 1.0 (equal to
the max_age = 0 fallback) loads as auto with the resolved-senescence
readout showing 1.0. The round trips are exact and the stored
configs keep the plain numbers, so nothing is wrong; it is simply
where the numbers appear. (c) THE FILLING GRID'S OBSERVED ENDGAME IS
A FREEZE, NOT THE GRIND — a structural finding, not seed luck. On
the shipped seed the fill happens as designed (60 → ~250 agents by
generation 5; cooperator share 0.50 → 0.61), but growth then STOPS
at ~265 of 400 sites with zero deaths and near-zero births through
generation 300: saturation never arrives and the text's predicted
rise-then-FALL never begins. The mechanism, diagnosed from the event
stream: the capacity gate admits the RICHEST eligible parents first,
rationed to the free-seat count; the richest parents are the
all-cooperator INTERIOR (income 480/generation, compounding), which
is exactly the cohort the placement kernel BLOCKS (no empty site
within Moore radius 1 of an interior parent); the poorer rim parents
— 54 at the freeze point, every one above θ and every one with an
empty neighbour site — never rank inside the admission quota, so the
blocked interior consumes the whole quota every generation. Verified
signature: from generation 6 onward `blocked_parents` equals EXACTLY
400 − population, every generation. With occupancy frozen, neighbour
sets are static, every cooperator keeps at least one cooperator
contact, and deaths stay zero — a true fixed point. This is an
EMERGENT INTERACTION of three separately-designed mechanisms
(wealth-ranked K-admission, the Design 4 gate order in which
admission precedes placement, and Phase C's
blocked-parents-pay-nothing-stay-eligible semantics — a blocked
parent still consumes its admission slot that generation), not a bug
in any one of them. Whether the scenario should be recalibrated
(e.g. a small base hazard for churn, as `the_drifting_frontier`
has) or the admission rule revisited is the design layer's call;
HELD per Rule 7 — the configuration ships exactly as the E3 prompt
prescribes, with its rise-then-fall text standing as design intent
and this finding logged beside it. (The flagship and the frontier do
NOT hit this: the flagship's population sits far below its K = 400,
so admission is never rationed, and the frontier's 5% hazard keeps
deaths freeing seats and churning the rim.)

**#154 — 2026-08-13 — The Economy panel learns about spatial
interaction: a third calibration branch, gated on the engine's own
sharpened predicate, its arithmetic a pure paint-time function shaped
for the M11b advisories (M11a Phase E, sub-prompt E4a; discharges
#153(a); the design layer's 2026-08-13 ruling as implemented).**
THE GATE: `economy_helpers.spatial_calibration_active(config)` —
evolution mode AND synchronous clock AND lattice AND
`matching.spatial_interaction` on — mirroring #141(c)'s sharpened
matcher-cell predicate, NOT the toggle alone. Rationale, as the ruling
requires the entry to carry: with the toggle stranded on under
`well_mixed` (a greyed checkbox keeps its value) or under tournament,
the configured matcher genuinely IS consulted, and the existing
aspatial arithmetic remains the correct report there. The
synchronous-clock conjunct is the config-level equivalent of #141(c)'s
table position — that cell lives in the greying table's SYNC column,
consulted only under the synchronous clock — and it enacts the
prompt's scope caution: code inspection showed the calibration report
IS reachable under the asynchronous clock (`dynamics.reproduction_mode`
is async-inert with its widget value stranded, and the panel renders
on that raw value), and the asynchronous per-generation-equivalent
match count has never been measured (#139 measured the synchronous
engine), so no formula was guessed — the async context keeps its
pre-#154 behaviour (the greyed matcher's arithmetic), pinned by a test
on `donation_game_threshold` (N − 1 = 99) so the spatial branch cannot
silently extend without a design ruling. THE FORMULA: matches per
agent = 2 × `effective_neighbour_count(shape, boundary, k)` — the
#141(e) pure function REUSED, not re-derived — with rounds per agent,
all-C income, all-D income, and the survival window following the
aspatial branches' shape exactly (including 1 ÷ (1 − w) under
continuation, now computed in ONE shared `_expected_rounds` helper so
the two arithmetics cannot drift). THE FINE PRINT, part of the fix:
`SPATIAL_FINE_PRINT`, one sentence from one described source (§12
discipline), rides the spatial branch's regime note — the figure is
the fully-occupied, uniform-degree case (an interior agent on a full
grid); edge agents on a bounded grid, and agents beside empty sites,
play fewer matches and earn less. SHAPE FOR REUSE:
`spatial_income_arithmetic(...)` is pure and Streamlit-free,
registry-value inputs → `SpatialIncome` (matches per agent, rounds per
agent, both incomes, both window bounds), callable at paint time —
advisories A1 and A2 (M11b) trigger on exactly these quantities, so
the M11b advisory becomes a CALLER rather than a re-derivation. Module
home: `pdsim/ui/economy_helpers.py`, beside `calibration_report`,
chosen over `experiment.py` because this is the Economy panel's income
arithmetic (the #38/#48 Streamlit-free-helper module already
unit-tested without the UI), the M11b advisory surfaces are UI-layer
work that imports it with no layering concern, and `experiment.py`'s
paint-time functions are registry-value resolvers and geometry facts —
the function still consumes #141(e)'s `effective_neighbour_count` from
there, so the geometry number has exactly one source. REJECTED
ALTERNATIVE, recorded per the ruling: a per-site expectation over
actual occupancy and true (bounded-edge) degrees — rejected because
the calibration report is a paint-time PLANNING readout: occupancy is
run state that does not exist before Run is pressed and changes every
generation after it, so the "precise" figure would require simulating
the founding at paint time and would be stale one generation into any
run; the min-degree figure matches §4.5's average-agent framing and
the shipped scenario texts' own arithmetic. ALSO IN THE CHANGE:
`CalibrationReport` gained a `spatial` bool (which branch produced the
figures — the `matcher` field's docstring now says it is unconsulted
while True), and `ECONOMY_HELP["expected_matches"]` gained the third
regime's sentence so the (?) beside the number cannot contradict it.
Loaded results: `spatial_reciprocity` now reads 8 matches and
0 ≤ cost < 24 (was 199 and < 597), `the_filling_grid` 16 / 480 / 160
with L = 40 below the saturated window (was 59 / 1770 / 590),
`the_drifting_frontier` unchanged (10 matches, 100 ≤ cost < 300).
One adjacent staleness REPORTED, not fixed (E4b audit territory): the
memory-depth note still branches on the configured matcher, so a
spatial run whose greyed matcher is round_robin gets the "under
round_robin every pair meets every generation" wording — directionally
right on a lattice (fixed neighbours DO recur; adjacent pairs meet
twice per generation, so the named worst case understates by about
2×), but attributed to a mechanism that is not running. No RNG path
touched; all eight golden masters pass with zero re-recording.

**#155 — 2026-08-13 — The Filling Grid tells the truth: the scenario
text now describes the observed RISE-THEN-FREEZE (the design layer's
2026-08-10 ruling), the configuration is byte-unchanged, and the
one-time P = 0 rederivation run is reported honestly — the freeze
broke only transiently and RE-FORMED LOWER, at 235 of 400 (M11a
Phase E, sub-prompt E4a; discharges #153(c)'s text half; the engine
half is explicitly NOT resolved here).** THE TEXT: the description is
kept verbatim through "…cooperation's share can rise early." and the
old rise-then-fall tail (the grind endgame stated as the expected
observable) is replaced by the ruling's rise-then-freeze wording: the
two reproduction gates (wealth-ranked global admission, then local
placement within Moore radius 1) and their population-scale deadlock,
the ~265-of-400 standstill with zero deaths, the verifiable Economy
panel signature ('Blocked parents this generation' = 400 − population,
every generation from about 6 on — the label matches the app's metric
verbatim), the old grind endgame retained in parentheses as the
counterfactual had the grid filled, and the horizon's new reason (rise
completes, freeze proves permanent). The things-to-try is likewise
replaced: the P = 0 rederivation with its defector-starvation
arithmetic, the freed-interior-sites reasoning, and the explicit
MAY-break hedge (arithmetic, not a promise). TWO DEVIATIONS from the
prescribed verbatim text, both reported in-session: (a) the
"**Things to try:**" prefix is NOT stored in the registry string —
both renderers supply that label themselves (`app.py`'s caption and
`gendocs.py`'s PARAMETERS section), so storing it would print it
twice. (b) A RULE 7 COLLISION found during Task 0 verification, fixed
by one inserted clause on the #152 walked-into-a-validation-error
principle: this scenario ships S = 0 (payoffs at the registry
defaults, per #151), so setting P to 0 as instructed ties P and S and
the `enforce_pd_ordering` validator (default ON, untouched by this
scenario) REJECTS the config — the app confirms with "Payoffs must
satisfy T > R > P > S …" and never runs. The shipped things-to-try
therefore tells the user to first untick 'Enforce PD payoff ordering
(T > R > P > S)' in the Game section and says why (P = 0 ties P and
S). The prescribed wording carried no such step; the alternative —
shipping it verbatim and letting the reader dead-end on a validation
error — was rejected on #152's own precedent, and the design layer
owns any better wording. `python -m pdsim.gendocs` rerun;
`docs/PARAMETERS.md` regenerated; the drift test is green. THE P = 0
REDERIVATION RUN, executed and observed (one deviation of method: run
HEADLESSLY via `python -m pdsim.run` on the scenario's exact config
with P = 0 and `enforce_pd_ordering` off, seed 11 unchanged — this
session cannot click the app; same engine path, and the ordering
toggle had to be off for the config to validate at all): the freeze
BROKE ONLY TRANSIENTLY, and what replaced it is a SECOND, LOWER
freeze. Observed trajectory (post-boundary snapshots): the fill runs
75 → 238 agents across generations 0–7 (peak 238 at 7); every death
in the entire run is an always_defect starving — 68 of them, from
generation 3 through 59, in punctuated waves (18 at generation 3,
then bursts of ~5-7 every four generations — all-defector pockets
draining to insolvency exactly as the new text's 16 × 10 × 0 = 0
arithmetic says); cooperation's share climbs 0.50 → 0.906; the freed
interior sites ARE refilled (births continue through the starvation
phase). But the fill never resumes toward saturation: by generation
~60 every surviving defector evidently holds at least one cooperator
contact (one such contact earns 2 × 10 × 5 = 100 against the 40-point
bill, so it never starves), deaths go to zero, births go to
near-zero, and the population sits FLAT at 235 of 400 sites (213
always_cooperate / 22 always_defect) for the remaining ~240
generations — 30 sites BELOW the P = 1 freeze at ~265. Honest
summary, now quoted in no scenario text and owned by the design
layer: P = 0 switches the metabolic filter on for defector pockets
and purges them, but the two-gate admission deadlock is indifferent
to P — once the purge completes the deadlock re-forms around the
(now richer, more cooperative) frozen population. The new
things-to-try's hedge is vindicated: watched, not guaranteed. NOT
RESOLVED HERE, explicitly: the underlying admission-quota design
question — whether wealth-ranked K-admission should see placement
feasibility, or the gate order should change, or the scenario should
carry churn — remains open exactly as #153(c) left it; E4b logs it
as an open design question with its M11b deadline. Zero golden
re-recordings; the run artefacts live outside the repo (scratchpad)
and are not committed.

**#156 — 2026-08-14 — Reach-kernel precomputation lands in the ENGINE
(the design layer's 2026-08-13 ruling), draw-neutral by construction and
pinned three ways; the bench gains the five-column structure grid;
hypothesis (i) — cost flat in R once the cache is warm — CONFIRMED, and
hypothesis (ii) — lattice at or below random_k at equal k — SPLIT: von
Neumann holds, the Moore columns sit 4–17% ABOVE, with the excess
attributed (as a hypothesis, held for the design layer, never tuned) to
re-met fixed neighbours' history copies, NOT to the kernel draw (M11a
Phase E, sub-prompt E4b; the spec's Bench section as implemented).**
THE CACHE: two memoisations on `Structure`, safe precisely because a
Structure is an immutable pure value (spec Design 3).
`reach(origin, radius)` returns a `Reach` named tuple — ascending-id
candidates, an aligned read-only distance array, their maximum — built
on first use for each (origin, radius) key by calling `sites_within`
ITSELF, so there is exactly one implementation of the enumeration and
cached content cannot differ from a fresh one; and
`distance_weight_table(radius, decay, up_to=…)` is the spec's one
distance→weight lookup per (R, β) pair (entry d holds exp(−β·d), the
same elementwise exp `kernel_weights` applies; regrown identically when
an unlimited-radius caller on a bounded grid needs a longer table). The
keys are exactly what the memoised computation reads and nothing else:
the topology is the instance, so (origin, radius) and (radius, decay)
close the input set. BUILD TIMING — lazy on first use, reported with
its why as the prompt requires: the structure module is
config-independent and cannot know which radii a run will consult
(birth, interaction, and None all differ per config), eager building
would either guess radii or plumb config knowledge into the topology
layer, and a lazy first miss costs exactly what EVERY draw paid before
the cache existed. CONSUMERS: `neighbourhood_sample` (all four locality
draws share it), `Occupancy.empty_sites_within` (the placement gate's
read), and the two async `fixed_n` candidate builds — every repeated
per-event enumeration in the engine now reads through the cache, which
is the ruling's point (live runs pay the same per-event cost the bench
measures; bench-only scaffolding was the rejected alternative). DRAW
NEUTRALITY, the whole game: the cached path hands the sampler
value-identical inputs — the candidates ARE sites_within's tuple, and
table[d] and the old per-draw exp(−β·d) are the same IEEE-754
operations on the same numbers, so the bits agree — and everything
downstream (zero-weight filtering, normalisation, the choice call) is
untouched. The three safeguards, all landed as permanent tests and all
green: (a) the equality pins in `test_structure.py` — cached candidate
list AND weight vector asserted identical (`==` and `np.array_equal`,
bit-for-bit) to a fresh direct enumeration across five geometries
INCLUDING Moore R = 5 on torus AND bounded grids and a bounded
von-Neumann case (the regimes outside golden coverage), populated
first and asserted after across interleaved origins so a mis-keyed
cache cannot hide — plus a memoisation identity pin (the repeat call
returns the STORED object; equality alone would pass with the cache
silently off, and the flat-in-R claim rests on it actually being on),
a table-regrowth exactness pin, and a cold-versus-warm draw-identity
pin over mixed radii, decays, and eligible sets; (b) all eight golden
masters pass with ZERO re-recording; (c) every counting-wrapper
draw-count pin unchanged. ONE IMPLEMENTATION FINDING, recorded because
the spec's premise differs: the shipped enumerator was never O(R²) —
`sites_within` walks EVERY site and filters by distance, so each
pre-cache draw paid O(site count) regardless of R (WORSE than the
premise on large grids). Flat-in-R therefore held trivially even
before the cache; what the cache removes is the per-draw site-count
scan. Micro-measured (this machine, scratch script, never shipped):
20×20 — old enumeration+weights 206–276 µs per draw against 63–84 µs
for the ENTIRE cached draw including the RNG call; 50×50 — old
1,307–1,520 µs against 86 µs (R = 5) and 185 µs (R = 10), the residual
R-growth being the per-draw eligibility filter over the candidate
list, O(neighbourhood size), exactly the spec's designed scaling. THE
BENCH COLUMN: `python -m pdsim.bench --structure` runs
N × {round_robin, random_k, lattice_vn_r1, lattice_moore_r1,
lattice_moore_r5} (the labels also parse directly in `--matchers`).
Each lattice cell is synchronous IMITATION at constant N — the
#91/#102 isolation discipline: no demography, so the columns time the
kernel-draw-plus-match phase and nothing else — on a fully occupied
most-square N-site torus (blank dimensions), `spatial_interaction` on,
the same k = 5, the matcher pinned `random_k` as the honest aspatial
counterpart (unconsulted while the toggle is on, #137(b)); combining a
lattice label with the economy or async tunings is a config-time
error (one tuning per measurement). Rendering stays out (#94's
separate axis); output remains environment-specific and UNCOMMITTED —
the numbers live in this entry and the handback only. MEASURED
(2026-08-14, this machine, defaults k = 5 / 50 rounds, median
s/generation, post-change engine, machine otherwise idle) — N = 50:
round_robin 0.494, random_k 0.102, vn_r1 0.101, moore_r1 0.117,
moore_r5 0.104; N = 100: 1.857 / 0.191 / 0.174 / 0.213 / 0.199;
N = 200: 7.827 / 0.412 / 0.406 / 0.481 / 0.470; N = 400: 30.958 /
0.778 / 0.754 / 0.904 / 0.808. (A pre-change control grid was run
first but overlapped a concurrent test-suite load, so only its
within-run column comparisons are usable; they show the same
flat-in-R shape with the lattice columns drifting further above
random_k as N grows — consistent with the O(site count) scan the
cache removes.) VERDICTS, honestly: (i) CONFIRMED — moore_r5 sits at
or marginally below moore_r1 at every N (0.808 vs 0.904 at N = 400).
(ii) SPLIT, and the miss is REPORTED AND HELD: vn_r1 sits at or below
random_k at every N (while playing 4 of k = 5, the #81 clamp — so per
match it is ~21% dearer), and the Moore columns sit 4–17% ABOVE. The
excess is NOT the kernel draw: the whole cached draw costs 63–84 µs
while the moore_r1 excess is ≈ 300 µs per focal at N = 400. Per-match
arithmetic localises it in the matches themselves: random_k ≈ 389
µs/match, moore_r1 ≈ 452, vn_r1 ≈ 471 — lattice matches cost 16–21%
more than random_k matches at every N. The candidate mechanism,
offered to the design layer AS a hypothesis: under spatial interaction
partners are FIXED, so pairs re-meet within a generation — on Moore at
k = 5 each adjacent pair meets twice with probability 25/64 ≈ 39%
(both draws forced at von Neumann's k ≥ 4: EVERY adjacent pair meets
twice, and vn_r1's per-match cost is accordingly the highest), against
≈ 2k/(N − 1) ≈ 2.5% under random_k at N = 400 — and a re-met pair's
second match copies a match-length history through `view_of` every
round: #91's pair-recurrence growth term operating WITHIN the
generation. Nothing was tuned to close the gap; the M18 vectorization
trigger stays untripped (absolute costs remain comparable and linear
in N).

**#157 — 2026-08-14 — The §12 audit ran item by item: 54 of 54 covered
— 14 registry parameters, 17 individually-explained enum values, 14
concepts, 9 derived readouts with visible numbers — with ONE wrong
text found and fixed (the Economy panel's memory-depth note now has a
spatial branch) and NO structural gaps beyond what #154 already holds
by design (M11a Phase E, sub-prompt E4b; DESIGN §2.12's checklist
obligation discharged).** THE PARAMETERS (14/14): every `structure.*`
key, `matching.spatial_interaction`, and `dynamics.boundary_order`
carries a plain-language registry description rendered as its widget's
(?) — structurally guaranteed by DESIGN §5 and walked anyway;
`PARAMETERS.md` regenerates from the same source, so app and docs
cannot drift. THE ENUM VALUES (17/17), each explained individually
inside its parameter's description — the part §12 exists for:
`well_mixed`/`lattice` in `structure.kind` (including the
imitation-stays-global caveat, #132); `moore`/`von_neumann` in
`neighbourhood_shape` (each with its metric and neighbour count);
`torus`/`bounded` in `boundary` (wrap-around, the rim, corner
degrees, and why torus is the default); all seven layouts in
`initial_layout` (`random`, `checkerboard`, `stripes`, `blocks`,
`patches`, `central_block`, `from_file` — each with its arrangement
story; the `stripes` text was re-examined against #150's sparse band
and STANDS: the dealing it describes is unchanged and its
fragment-of-a-row sentence covers the band's centred partial last
row, matching #150's own no-registry-change call);
`random`/`energy_priority` in `placement_contest` (luck versus the
compounding-advantage claim); `death_first`/`birth_first` in
`boundary_order` (both demographic consequences worked). THE CONCEPTS
(14/14), each with a named single source: site and
exclusivity/capacity (`structure.kind` description plus
`STRUCTURE_HELP["site_count"]`); neighbour/neighbourhood
(`neighbourhood_shape`); support radius R (`birth_radius` /
`interaction_radius` — the hard edge); decay β (`birth_decay` /
`interaction_decay` — exp(−β·d) spelled out); the reach kernel (the
same two pairs plus `matching.spatial_interaction`'s pointer);
viscosity (`ECONOMY_HELP["blocked_parents"]` names and defines
spatial viscosity); wrap-around equalising degree (`boundary`);
degree and why thresholds depend on it (`boundary` plus
`STRUCTURE_HELP["effective_neighbours"]` — "the k the b/c > k
threshold counts"); the two gates and why one is not enough, and a
blocked parent (`ECONOMY_HELP["blocked_parents"]`, the #133(c)
single source); arrangement versus composition (`initial_layout`);
the b/c > k threshold with the additivity nuance
(`GAME_HELP["payoff_additivity"]` carries exactly the required
claim: b and c only EXIST when T − R = P − S, and a non-additive
matrix makes the ratio AMBIGUOUS — four defensible readings — rather
than merely inapplicable); spatial reciprocity
(`matching.spatial_interaction`'s learn-more names and defines it).
THE READOUTS (9/9, each a visible number with a (?)): Sites
(`site_count`); Grid (resolved) (`resolved_dimensions`); Capacity K
(resolved) beside the site count (`resolved_capacity`) — fires only
while the K WIDGET is blank, the #141 design, NOT re-derived as a gap
per #153(b), and the loader's loss-free inverse re-presenting
stored-equals-auto values as blank-auto is likewise correct
behaviour, not a gap; Effective neighbours (k)
(`effective_neighbours`); Occupied with its fraction (`occupancy`);
Isolated at founding (`isolated`); Blocked parents this generation
(`ECONOMY_HELP["blocked_parents"]`, live metric, presence-gated by
`blocked_parents_visible`); Pixel-array rendering
(`STRUCTURE_HELP["pixel_array"]`, its value read from the SAME
`charts.pixel_array_active` predicate the renderer consults, both
#149 triggers described — verified present as #145(c) left it);
payoff additivity (`GAME_HELP["payoff_additivity"]`, the #141(e)
metric plus caption reporting b, c, and b/c when additive or the
costs-a-different-amount reason when not). THE ONE TEXT FIX, logged
as the audit's own obligation: the memory-depth note
(`economy_helpers.calibration_report`) branched on the CONFIGURED
matcher even while spatial interaction was active — the very
staleness #154 reported into this audit — so a spatial run with a
greyed round_robin got growth attributed to a mechanism that is not
running, and one with a greyed random_k got "a given opponent recurs
only occasionally", the OPPOSITE of the lattice truth (neighbours are
fixed; an adjacent pair meets twice per generation, #139). The note
now takes a third branch on the SAME #154 gate
(`spatial_calibration_active`): fixed neighbours, twice-per-
generation meetings, and the honest worst case ≈ 2 × rounds ×
generations recorded moves — double round_robin's per-pair rate,
exactly as #154's analysis said. Pinned by test (the flagship's note
names fixed neighbours and 200 moves, never round_robin; the
frontier keeps the random_k wording). The async context is untouched
and keeps its #154-pinned pre-spatial behaviour. NOT GAPS, on
pre-derived grounds honoured per #153(b)/#154: the whole
asynchronous clock's calibration report still uses the configured
matcher's arithmetic (deliberately held — the async
per-generation-equivalent match count is unmeasured; pinned at
N − 1 = 99 on `donation_game_threshold`; carried to M11b's advisory
work by this session's ROADMAP amendment). No registry text changed,
so no gendocs run was needed (the fix lives in the #38/#48
Streamlit-free helper module and its tests).

**#158 — 2026-08-14 — The tabs decision, recorded although nothing is
built (the spec's Docs obligations named this the piece most likely to
be lost, and the design layer confirmed 2026-08-13 it had never been
written): the `run.mode` tab split is the ONE clean fork; everything
else fails the total-fork criterion and gets collapse-with-summary;
novice/advanced disclosure is a separate axis; implementation is
M11b's (M11a Phase E, sub-prompt E4b).** THE SPLIT: evolution and
tournament become separate TABS — the one fork the parameter panel
has where hiding is honest. THE TOTAL-FORK CRITERION, the rule that
makes it the only one: hide a parameter only where EVERY parameter on
the far side of the fork is genuinely ignored, with no exceptions and
no partial cases. The reason: a GREYED widget says "this exists and
does nothing here", while a HIDDEN one says "this is irrelevant here"
— and if that second claim is ever wrong, the user cannot see the
parameter that is affecting their run. Tournament ignores structure,
dynamics, and demography WHOLESALE (#120(a)/#144), so the mode fork
passes; nothing else does. WHY `time_model` FAILS the criterion:
`selection_beta` follows the imitation OVERLAY, not the mode (#101's
carve-out), and the ledger knobs — L, engagement, r, σ — apply under
the synchronous economy AND both asynchronous population modes;
Dynamics has a shared core with two mode-specific wings, not a clean
cut. WHY `reproduction_mode` FAILS it too: the same shared-ledger
problem, plus async `variable_n` BEING the economy under a different
clock. COLLAPSE-WITH-SUMMARY is the treatment for inert sections: a
collapsed section that names itself and its state ("Structure —
well-mixed, inactive"), rather than hiding — the disclosure form of
the #34 grey-never-hide rule. NOVICE/ADVANCED DISCLOSURE is a
separate, orthogonal axis deserving its own decision when M11b takes
the panel apart — it cuts across sections, not along mode forks, and
conflating the two axes is how a parameter ends up invisible for two
unrelated reasons at once. IMPLEMENTATION is M11b, deliberately not
beside this milestone's riskiest phases (the spec's own scoping); the
ENABLING piece — the #141 `STRUCTURE_GREYING` predicate table both
clock branches consume — already shipped, and M11b's tab/collapse
work becomes a second renderer over that same table.

**#159 — 2026-08-14 — OPEN QUESTION, deliberately unresolved here: when
the carrying capacity rations births, is the global quota consumed by
ADMISSION (today's behaviour) or by SUCCESSFUL PLACEMENT? Deadline:
resolved in M11b at the latest, EXPLICITLY BEFORE M12 (M11a Phase E,
sub-prompt E4b; logs the question #153(c) surfaced and #155 confirmed,
as those entries directed).** THE QUESTION, stated for a future
session with no context assumed: under the synchronous energy economy
the capacity gate admits the wealth-ranked richest eligible parents up
to the free-seat count, and only THEN does each admitted parent
attempt local placement within its birth kernel. A parent that wins
admission but finds no empty site in reach is BLOCKED — it pays
nothing and stays eligible — but its admission slot is spent for the
generation. Should unfilled quota instead roll to the next-richest
eligible parent within the same boundary — equivalently, should the
quota count PLACEMENTS rather than ADMISSIONS, or should admission see
placement feasibility at all? THE EVIDENCE that this is a real regime,
not a corner: #153(c)'s Filling Grid freeze — growth stops at ~265 of
400 sites with `blocked_parents` equal to EXACTLY site count −
population every generation from ~6 on, because the rich interior
consumes the whole quota and is precisely the cohort the kernel
blocks, while the poorer rim (all above θ, all with empty neighbour
sites) never ranks inside it — and E4a's P = 0 rederivation (#155):
the freeze broke only transiently and RE-FORMED LOWER at 235 of 400,
so the deadlock is indifferent to payoffs — it is the admission
mechanism itself. WHY IT WAS NOT SLIPPED INTO E4: the contest
permutation is drawn over the ADMITTED set (#133(a)), so ANY change —
roll-forward, placement-counted quota, feasibility-aware admission —
alters RNG consumption and is a #80/#99-governed breaking change
needing its own golden masters; exactly the class of change Phase E's
zero-re-recording guard exists to keep out. THE STAKE, named: the
Hammond–Axelrod frontier replication (M12) runs at K = site count
with rich interior incumbents and poor frontier parents — precisely
the configuration that starves the frontier of admission quota — so
the question must be settled before that scenario can mean anything.

**#160 — 2026-08-14 — M11a IS COMPLETE (M11a Phase E, sub-prompt E4b —
the close-out entry: the V6 discharge record, the docs-obligations
sweep verdict, one housekeeping fix, and the WIP disposition).**
(a) THE V6 DISCHARGE RECORD: the spec's V6 validation item — the
b/c > k threshold observed in the app — is DISCHARGED BY RECORD:
executed in Phase D by manual configuration at 20 seeds per shape
(#140) and re-exercised app-first through the registered
`donation_game_threshold` scenario in E3, including the twelve-seed
fixation check (#151). Per the #117 honesty rule the discharge stands
WITH the observed result: NO visible reversal at this engine's
selection strength — the spec's "von Neumann clears, Moore fails"
expectation is what was measured against and not observed — and the
shipped scenario text carries the caveat (the compass, not a
prediction). (b) THE DOCS-OBLIGATIONS SWEEP, walked against the
spec's list: build decisions #112–#155 exist (spot-checked, not
re-audited); Open Question 1's resolution WITH the explicit
scope-grounds decline of local sync-imitation comparison is #132; the
`site_capacity` pinned-at-1 record with its three deferred questions
is #135 (and ROADMAP's M19 entry carries the registration task line —
verified present); the tabs decision is #158, written this session as
the spec predicted it would need to be. No other missing obligation
was found. (c) HOUSEKEEPING: `pdsim/io/results.py` defined
`PER_AGENT_SCHEMA_VERSION = 3` twice in a row with identical
docstrings (E4a's report); the duplicate is removed — no behaviour
change. (d) WIP DISPOSITION, decided by the design layer: DELETED at
milestone end — ROADMAP and CLAUDE.md now carry the next-effort
pointer (the literature verification pass gating the M11a explainer,
then M11b), and a baton carrying nothing tracked docs don't hold is
clutter. (e) THE DECLARATION: M11a — population structure: sites,
local birth, local interaction — is COMPLETE, Phases A through E4b,
DECISIONS #111–#160, schema 5, eight golden masters (four negative,
four positive) with the only re-recording across the whole milestone
being #150's logged, confined pair; 1059 tests pass; ruff clean. The
M11a explainer remains GATED on the four literature verifications
(spec Out-of-scope; #103/#111) and is NOT part of the milestone;
M11b is next per ROADMAP.

**#161 — 2026-08-14 — The four literature gates are DISCHARGED: all four
claims VERIFIED TRUE against publisher records or author-institutional
deposits, recorded as one consolidated entry since they were gated as one
batch (the design-layer literature verification pass; discharges the
verification debt of #103(ii) and #111(d); unblocks the M11a explainer per
the spec's Out-of-scope section and #160).** (1) Hammond & Axelrod 2006
(JCR 50(6), DOI 10.1177/0022002706293470, authors' institutional deposit):
the 50×50 space IS toroidal — "wraparound borders so that every site has
exactly four neighboring sites" — with von Neumann geometry stated in both
the model section and the appendix. M12's replication scenario inherits a
VERDICT: wrap-around, von Neumann. (2) Kaznatcheev & Shultz 2011 (Proc.
33rd CogSci, 3174–3179, publisher-hosted full text): no-tag local
child-placement matches the full model "up to around 300 cycles";
saturation "at about 300 cycles, on average" is the paper's own figure,
attributed therein to Shultz, Hartshorn & Kaznatcheev 2009; the M10
explainer's "roughly the first 300 periods" is ACCURATE — no correction
required; a one-line verified-note added to its provenance note instead.
Nuance recorded: the tags-maintain effect weakens as b/c rises (no decay
at b/c = 4). (3) Tarnita et al. 2009 (JTB 259(3), DOI
10.1016/j.jtbi.2009.03.035, Harvard DASH deposit): σR + S > T + σP
confirmed; σ = 1 is risk-dominance; σ = (k+1)/(k−1) for death-birth on
regular graphs confirmed WITH the attribution chain — the paper credits
the value to Ohtsuki et al. 2006's online-material eq. 24 via
σ = ((b/c)*+1)/((b/c)*−1); finite-N formula ((k+1)N − 4k)/((k−1)N) is
their eq. 18; birth-death is explicitly outside their proof
(payoff-dependent death step), condition "expected to hold" pending a
different proof. Calibration guide §2.4/§2.5 and its References SHIP
CORRECT — no edits. (4) Ohtsuki, Hauert, Lieberman & Nowak 2006 (Nature
441, DOI 10.1038/nature04605, full Supplementary Information from Hauert's
institutional reprint): assumption set confirmed — donation game, one-shot
summed payoffs, fitness (1−w)+w·payoff with weak selection, N ≫ k, pair
approximation on Bethe lattices with looped-graph discrepancy expected;
b/c > k derived for death-birth in SI §1.5; imitation b/c > k+2 in SI §2;
and SI §3 — titled "'Birth-death' (BD) updating" — proves cooperators are
never favoured for any b > c > 0, so ADVISORIES.md A4's pinpoint
"Supplementary Information §3" ships CORRECT as written. HANDLING DECIDED:
all four claims enter the explainer with citations (no omissions, no
unverified markers); the M10-explainer note rides inside the explainer
prompt rather than as a separate prompt; one consolidated entry rather
than per-claim entries, so M12 inherits a single pointer. The standing
rule restated: claims derived by consistency check are not citations, and
nothing enters an explainer until verified against publisher records.

**#162 — 2026-08-16 — Calibration guide §7.1 corrected to the #139-measured
arithmetic: the Moore defector-interior counterfactual at the default
punishment P = 1 earns 8 neighbours × 2 matches × P = 1 = 16 per
generation, not the naive one-match-per-neighbour 8 (docs-only small fix;
no code, no registry, zero golden re-recording).** THE STALE SPOT: §7.1's
"Punishment set to 0" paragraph, written before #139 dissolved the ≈, said
a Moore defector interior at P = 1 "earns 8 per generation" — a
per-neighbour count that ignores the no-deduplication doubling (every
adjacent pair meets twice, once at each side's initiative). The
correction shows the arithmetic the guide's own way so a reader can
reproduce it, cites §4.2 and #139 inline, and names the flagship's one
round per match (matches = rounds). CASCADE RECOMPUTED, CONCLUSION
SHARPENED NOT REVERSED: the paragraph's hedged conclusion ("which may
well clear the living cost, in which case nobody starves") becomes
definite — the flagship ships L = 12 (#151), and 16 > 12, so under the
all-defaults counterfactual (Moore is the registry default shape, P = 1
the default punishment) the defector interior clears the bill and nobody
starves; worked as a §4.5 window, Moore at P = 1 gives all-D 16 / all-C
8 × 2 × 3 = 48, so 16 ≤ L < 48 and L = 12 sits BELOW the window: the
metabolic filter is switched off outright, not merely loosened. The
exhibit's stated conclusion — that P = 0 is load-bearing because at the
default punishment the scenario "silently demonstrates nothing" — is
UNCHANGED in direction and STRENGTHENED in force (the naive 8 vs L = 12
would have had the defector still starving and the paragraph's own hedge
was doing the work; the measured 16 makes the claim true without the
hedge). No other number in §7.1 depends on that income (the paragraph
never stated a window or a cooperator/defector comparison; those live in
§3.7 and §4.6). NUANCE REPORTED TO THE DESIGN LAYER, NOT EDITED: the
"P = 0 is load-bearing" claim rests on the Moore reading of the
counterfactual; under the flagship's OWN von Neumann shape, P = 1 alone
gives 4 × 2 × 1 = 8 < 12, so interior defectors would still starve —
at a third of the P = 0 deficit (−4 vs −12 per generation) — and the
window 8 ≤ L < 24 keeps L = 12 inside; §3.7's table already carries that
exact figure ("8 × 1 = 8", hedged on where L sits). §7.1 remains
internally consistent because it names Moore explicitly; whether the
paragraph should also say that the von Neumann-only override keeps the
filter on is the design layer's call. THE REST-OF-GUIDE SWEEP (task step
4): §4.2 carries ≈ 2 × min(k, degree) with the #139 measured-note; §4.3's
table (≈ 8 / ≈ 16), §4.4's twice-per-pair statement, §4.6's Moore →
von Neumann drill (16 rounds / 8 rounds), §8 step 4 and §3.7's "8 × 1 = 8"
(von Neumann, 4 × 2) are ALL the doubled arithmetic — no other naive
occurrence found, nothing else edited. One near-miss noted and LEFT: §3.7
says "roughly 8 matches per agent per generation" where #139 measured
EXACTLY 8 on a fully occupied uniform-degree torus — the correct figure
with a now-unnecessary hedge, not the same error, so outside this fix's
"unambiguously the same error" rule; the design layer may tighten it.
HISTORICAL COPIES LEFT BY POLICY: the same pre-#139 sentence survives in
the frozen M11a spec (Validation section, "earns 8 per round, which may
well clear L") and in the archived delivery prompts under
`docs/design-notes/` (BLOCK-A2, M11a-prompt-2); specs are frozen intent
never retro-edited beyond their status line, and design-notes are the
as-delivered record — this entry is the pointer that supersedes both.
RATIONALE: a standing calibration reference must match the platform's
measured arithmetic — the M11a explainer and the Filling Grid scenario
text (#151: 16 × 10 × 1 = 160) already do, and a reader cross-checking
§7.1 against either would have found the guide contradicting them.
Alternatives rejected: leaving the hedge ("may well clear") in place with
only the number changed — the flagship's L is a known scenario fact
(#151) and stating it makes the exhibit reproducible, which is the
guide's own standard ("every number is worked rather than asserted");
and rewording §7.1's P = 0 rationale around the von Neumann nuance — that
is a conclusion-shaping change the design layer must see first (Rule 7),
so it travels in this entry and the handback rather than in the guide.

**#163 — 2026-08-16 — Calibration guide §7.1 gains the von Neumann
sentence the design layer ruled on after #162, and §3.7's "roughly 8" is
LEFT on referent grounds (docs-only micro-fix; no code, no registry, zero
golden re-recording).** (1) THE §7.1 SENTENCE, added directly after the
#162 Moore-counterfactual window: under the shape the flagship actually
ships, von Neumann, the default punishment alone would NOT switch the
metabolic filter off — 4 neighbours × 2 matches × P = 1 = 8 < L = 12, so
interior defectors still starve, at −4 rather than −12 per generation,
with the window 8 ≤ L < 24 and L inside it; therefore the P = 0 override
is BELT-AND-BRACES under the shipped shape and LOAD-BEARING for the Moore
switch the scenario's things-to-try text invites (verified: the flagship's
second things-to-try item is exactly that switch, k raised to 8, P kept at
0, window 0 ≤ L < 48). The false inference this prevents: a reader taking
§7.1's "each override is load-bearing" as "P = 0 is universally necessary
for the mechanism," when the arithmetic says it is Moore-flip-necessary
(flip the shape without zeroing P and defector interiors earn 16 > 12 —
mechanism gone) and shipped-shape belt-and-braces (P = 1 under von
Neumann still starves interiors, only more slowly). §7.1's existing
conclusion is intact; the sentence qualifies its scope. Cross-checked
against #111(c) (the override's original rationale, written pre-#139
with the "8 per round … may well clear L" wording — that rationale is the
Moore reading, now made explicit) and #151 (L = 12, von Neumann, one
round per match). (2) §3.7 REFERENT DETERMINATION — CASE TWO, LEFT
UNCHANGED: the sentence reads "at the flagship's settings: a grid with
four neighbours per site, one round per match, and roughly 8 matches PER
AGENT per generation" — an unspecified-agent statement about the
flagship's world, which is half-empty (N = 200 on 400 sites, #151), where
edge and corner agents have fewer than four occupied neighbour sites and
play fewer than 8; #139's exactly-8 holds for a FULLY-NEIGHBOURED agent
on a fully occupied torus. So "roughly" is the correct hedge for that
referent. The table beneath it ("Defector surrounded by defectors" 8 × 0,
"Cooperator inside a cooperator cluster" 8 × 3) and the following
sentence ("At P = 1 it earns 8 per generation") take the interior case,
where 8 is exact — and they already carry NO hedge, so §3.7 is internally
consistent as written: hedged prose for the population, unhedged
arithmetic for the interior. No tightening applied, no restructuring;
this closes the near-miss #162 flagged. RATIONALE: the design layer
ruled the von Neumann qualification in (Rule 7's report-first path
discharged by ruling); and a hedge is removed only where its referent
makes it wrong, not merely where a stronger statement is available for a
narrower referent. Alternatives rejected: tightening §3.7 to "exactly 8"
— true of interiors, false of the flagship population the sentence
names; and adding an interior-vs-population gloss to §3.7 — that is the
restructuring the ruling excluded, and the table already does the work.

**#164 — 2026-08-17 — #159 RESOLVED: feasibility-aware admission (the
M11b design session's option B), HARDWIRED, no new parameter (M11b Phase
0; spec `docs/specs/M11b-movement-and-panel-spec.md`, ruling 1;
implemented in Phase A).** THE RULING: the synchronous economy's capacity
gate ranks and seats ONLY parents that currently have at least one empty
site within birth reach; the contest permutation is still drawn over the
admitted set (#107/#133 untouched); residual contention waste — two
seated parents sharing one reachable empty site, so the loser's seat is
spent that generation — is accepted as rare, self-healing (the next
generation re-ranks against changed occupancy), and semantically fair;
and a permanent freeze becomes PROVABLY IMPOSSIBLE, because at least one
seated parent always places. RATIONALE: a capacity seat is an economic
license to breed, and handing licenses to parents who physically cannot
use them was never a designed claim — #153(c) records the freeze as an
emergent interaction of three separately designed mechanisms; this
restores each gate to its intended job (K decides HOW MANY, the kernel
decides WHERE). ALTERNATIVES REJECTED: (A) per-scenario churn/hazard —
leaves the artifact as the platform default and would contaminate the
M12 Hammond–Axelrod replication with a foreign mechanism; (C)
placement-counted roll-forward quota — done naively the richest wins
contested cells, silently reintroducing the compounding #107 rejected as
a default, and done correctly it costs rounds of admit-permute-place,
multiplying the draw surface for a benefit B mostly delivers; (D) B plus
roll-forward — both complexities at once. NO COMPATIBILITY KNOB: a
parameter whose only use is reproducing a pathology earns no registry
place; the #150 precedent (a deliberate, logged behaviour change with
its own goldens) is the sanctioned path, and #159 itself anticipated the
re-recording. GATED LATTICE-ACTIVE (#80/#99 idiom): well-mixed runs stay
byte-identical. PHASE A CARRIES: the metric redefinition (blocked =
contention-only; a NEW infeasible-parents count), the Filling Grid
re-run and honest rewrite (#152's arithmetic-not-predictions rule), and
the golden re-record — the affected sync-lattice positive goldens,
re-recorded ONCE under Phase A's own entry with the full #133(d)
technique; that is the milestone's entire re-recording budget. HAND-OFF
TO M12 SCOPING, named so it is not lost: with feasibility filtering at
K = site count, WEALTH still ranks the feasible — Hammond–Axelrod's
reproduction order is purely random — so whether M12 needs
`admission_ranking` ∈ {wealth, random} is M12's question, not resolved
here.

**#165 — 2026-08-17 — The movement schedule (the #103 open item) and the
movement parameters (M11b Phase 0; spec rulings 2 and 3; implemented in
Phase B).** (a) ASYNCHRONOUS CLOCK: movement is a step INSIDE the focal
activation — activate, (possibly) move, play the match bundle,
demographic step — NOT a new event type; a movement event class would
break the one-event-one-activation correspondence the Δt = 1/N(t)
convention rests on, putting a movement-rate-dependent correction factor
into every chart axis, cadence, and calibration figure. (b) SYNCHRONOUS
CLOCK: movement is the FINAL step of the demographic boundary, after
deaths and births — movers see the freshest vacancies; matches are
always played from the positions the previous boundary settled
(move-then-play under BOTH clocks — the cross-clock symmetry); the
founding layout governs generation 0's matches, so a painted arrangement
is honoured before movement reshapes it; newborns may move in the same
boundary — one uniform rule. MOVER CONTENTION: one permutation over the
movers, iterated with occupancy updating (the #107/#133 pattern), no
wealth priority. (c) ONE RATE PARAMETER `movement.rate`: a per-agent
per-period probability, default 0 (hard rule 8 — old configs re-run
identically); sync attempts at the boundary's movement step, async
attempts at activation — the same number means expected moves per agent
per generation(-equivalent) under both clocks. All movement draws are
GATED on rate > 0 (the #80/#99 active-flag idiom): zero additional draws
when off, so no existing golden moves — including Phase A's fresh ones.
A BLOCKED MOVE (no empty site in walk reach) fails in place and is
counted. ALTERNATIVES REJECTED: a separate movement event type (breaks
the clock, above); a cadence schedule (synchronized global reshuffling
pulses are a modelling artifact and have no async meaning). THE
`MovementRule` ABSTRACT BASE CLASS (#46) ships with ONE implementation,
the kernel-weighted random walk over the third radius/decay pair (#105:
`movement.radius`, `movement.decay`), consuming the #156 cached reach;
success-driven and walk-away styles are future implementations of the
same interface. NAMED FUTURE OPTION, deliberately out of M11b: a
movement ENERGY COST — it adds a calibration surface A1/A2 would have to
learn; movement ships free.

**#166 — 2026-08-17 — `matching.encounter_mode` ∈ {`per_initiator`,
`per_pair`}, default `per_initiator`; SPATIAL-ONLY;
deduplicate-after-draws; greyed under the asynchronous clock (M11b Phase
0; spec ruling 4; implemented in Phase C).** (a) SCOPE: the knob is live
only while `matching.spatial_interaction` is on. The well-mixed
`random_k` coincidental doubling (≈ 2k/(N − 1) per pair) is UNTOUCHED —
the lattice is where the artifact is systematic (every adjacent pair,
every generation, the #139 ×2), and reopening the platform's oldest
golden-mastered path to fix a rare coincidence buys near-nothing;
recorded as a possible future extension. (b) IMPLEMENTATION CONTRACT,
protecting the goldens: partner draws are made exactly as today — the
same random-number consumption — and deduplication applies to the
resulting PAIR LIST before matches are played; the knob changes WHICH
matches run, never HOW randomness is consumed, so the default is
byte-identical trivially. (c) ASYNCHRONOUS CLOCK: greyed, with a
greying-table entry (#141's `STRUCTURE_GREYING`) and help text — the
async activation structure is per-initiator by construction, and
cross-event deduplication would require remembering encounters through
time and would distort the activation clock #165 protects. RIPPLES
ASSIGNED: `spatial_income_arithmetic` gains the encounter branch (2× vs
1× the effective neighbour count; Phase D); A3's message becomes
mode-conditional; A2 gains the trigger (#170); the bench gains a
`per_pair` column beside the #156 structure grid (Phase C) — the first
real test of #156's held hypothesis that re-met pairs' within-generation
history copies explain the Moore cost excess. All four shipped scenarios
keep the default; no scenario text changes. ALTERNATIVE REJECTED:
extending the knob to the well-mixed matchers now (above, (a)).

**#167 — 2026-08-17 — Novice/advanced disclosure (the axis #158
deliberately left open) RESOLVED: a registry-level boolean `advanced`
flag, rendered as a collapsed-but-present per-section expander (M11b
Phase 0; spec ruling 5; implemented in Phase E2).** THE MECHANISM: the
flag lives beside the parameter's registry entry (hard rule 3 — single
source of truth, never in UI code); the panel renders each section's
everyday parameters as now and its advanced ones inside a labelled
expander that names itself, opens on a click, and keeps greying LIVE
inside — disclosure by folding, the same honest shape as #158's
collapse-with-summary, one level down. ORTHOGONAL to the mode tabs, as
#158 demanded, sparing the two-unrelated-reasons-at-once invisibility.
FLAGGING CRITERION: the default is the canonical choice AND changing it
presupposes a mechanism the novice tooltips don't assume. The spec
carries the candidate list (`birth_decay`, `interaction_decay`,
`movement.decay`, `dynamics.boundary_order`,
`structure.placement_contest`, `matching.encounter_mode`,
`match.continuation_probability`, the selection-rule internals); the
OWNER confirms it at the Phase E2 prompt. ALTERNATIVES REJECTED:
declining for M11b (M11b IS the panel-rewrite milestone; reopening the
panel later just for this contradicts #158's reason for parking it
here); a global novice/advanced MODE that HIDES advanced widgets
(violates the total-fork criterion — an advanced parameter still affects
the run, which is exactly the false irrelevance claim #158 forbids).

**#168 — 2026-08-17 — Live-run display continuity joins M11b (owner
request, 2026-08-17 design session; spec ruling 6; implemented in Phase
E3).** THE RULING: the four display toggles — update granularity,
playback delay, score view, time scope — become changeable MID-RUN
without stopping the run. MECHANISM: the run loop stops living as an
in-script loop that a widget rerun destroys; engine state survives in
session memory, and each script pass advances the engine, repaints with
the toggles' CURRENT values, and schedules the next pass — so a mid-run
toggle change resumes the run and re-renders on the fly. LEGITIMACY: all
four toggles are display-side — none reaches the engine, the registry
semantics, or any random draw — so hard rules 4 and 8 and the golden
masters are untouched by construction. RULE 7 REPORT REQUIRED from Phase
E3: which toggles govern PAINT CADENCE only (freely switchable in both
directions) versus RECORDING RESOLUTION (finer detail only from the
switch point onward); the granularity toggle's mid-run wording — a
caption versus stays-pre-run — is the OWNER'S call on that report.
ALTERNATIVE REJECTED: leaving the toggles pre-run-only (the status quo,
which forces a stop-and-restart to change what one is watching).

**#169 — 2026-08-17 — The asynchronous spatial calibration branch
EXTENDS, gated on measurement (resolves the question #154 deliberately
held and pinned; M11b Phase 0; spec ruling 7; executed in Phase D).**
THE EXPECTED FORMULA is the SAME 2 × min(k, degree) per
generation-equivalent the synchronous branch uses — on its own
activation an agent plays its k matches (capped at its neighbour count),
and it is also played by each neighbour on theirs, the same two-sided
accounting that produces the synchronous ×2 (#139) — but as an
EXPECTATION rather than an exact count, since activation order is
random. PHASE D instruments an asynchronous spatial run, counts matches
per agent per generation-equivalent, and compares. ON AGREEMENT within
sampling noise: the branch extends (`spatial_calibration_active` loses
its sync-clock conjunct), the #154 pin (N − 1 = 99 on
`donation_game_threshold`) is RETIRED WITH A REPLACEMENT pin on the new
behaviour (#120(f)'s retire-with-replacement rule), advisory A1 works
under both clocks, and the fine print marks the async figure "expected"
where the synchronous figure was exact. ON DISAGREEMENT: Rule 7 — report
the measured number and hold for a design ruling. ALTERNATIVE REJECTED:
leaving the async context pinned wrong — A1 would either stay silent
under async (a warning system dark in one of the two regimes) or warn
from numbers known to be false.

**#170 — 2026-08-17 — ADVISORIES.md A2's trigger list amended (EXECUTED
in M11b Phase 0; spec ruling 8).** ADDED to A2's triggers:
`matching.spatial_interaction` (flipping it swaps the entire income
arithmetic regime — 199 → 8 in the flagship's case),
`matching.encounter_mode` (`per_pair` halves every income figure, #166),
and `matching.interaction_radius` (a larger radius enlarges the
reachable neighbourhood, so where k exceeds the smaller neighbourhood
the effective match count rises). EXCLUDED, with reasons recorded so the
list is not "completed" later by mistake: `movement.rate` — movement
changes WHO an agent's neighbours are, not how many matches it plays; it
moves income around rather than multiplying it — and `interaction_decay`
— it reweights which neighbours are drawn, never how many draws occur.
A2's message, severity, and surface are UNCHANGED. The file predates
M11a's knobs and this session's rulings; ROADMAP anticipated exactly
this re-examination. Phase D implements A1–A3 against the amended list;
any further edit the implementation forces is a Rule 7 report.
