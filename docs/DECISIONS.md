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
