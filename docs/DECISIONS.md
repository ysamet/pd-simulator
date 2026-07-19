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
