# CLAUDE.md — Project conventions and context

This repository is an evolutionary Prisoner's Dilemma simulation platform. Read
`docs/DESIGN.md` (model + architecture spec), `docs/ROADMAP.md` (version scoping), and
`docs/DECISIONS.md` (decision log with rationale) before making non-trivial changes.

## About the developer

The project owner is re-entering programming via Python. Prefer clear, idiomatic,
well-explained code over clever code. When introducing a new concept (decorator,
generator, ABC, vectorization trick), add a brief explanatory comment the first time
it appears. Where a design maps to functional-programming ideas (strategies as
composable functions), point it out — it's a learning thread of this project.

The project owner does not hand-edit repo files. All changes — code and docs —
are made by Claude Code, arriving either as prompts pasted by the owner (often
drafted in the design chat) or as decisions made in-session. Never end a session
by asking the owner to manually edit a file; do the edit. Git commits are the
OWNER'S act, never Claude Code's: never run git commit. At every milestone
completion (and whenever a commit is warranted), present: (a) a summary of what
was done, (b) the list of files to stage, and (c) a suggested commit message —
the owner performs the commit himself. Additionally, after EVERY implementation,
show the owner how to run manual validation (with the venv-activation
reminder) — and validation is APP-FIRST (DECISIONS #42/#61): prefer
exercising the feature through the Streamlit app, naming a specific scenario
to load, the widgets to touch, and the observable outcome that confirms it
works. CLI-based validation is acceptable only for inherently headless
features (e.g. `python -m pdsim.bench`, the headless runner itself).
Automated tests complement — never substitute for — the owner seeing the
feature work in the app.

**Validation-instruction precision (owner request 2026-07-28, sharpened
2026-08-20).** Every widget named in validation steps gets its FULL,
VERIFIED path: the tab, the expander and whether it starts collapsed
(only Population and Dynamics start expanded), and the widget's registry
label verbatim. Verify every location by reading `pdsim/ui/app.py` in the
session that writes the instructions — never from assumptions about
typical Streamlit apps. Known traps, learned the hard way: this app has
NO sidebar (the Scenario dropdown sits at the top of the main area), and
that dropdown lists scenarios by their `display_name` — so name the
display title the owner will actually see (e.g. "Cooperation Survives in
Clusters"), with the machine name (`spatial_reciprocity`) at most in
parentheses.

## Hard rules

1. **Documentation is mandatory, always.** Every module, class, function, and method
   gets a Google-style docstring. Every function parameter and return value is
   documented. Every tunable simulation parameter is documented in the Parameter
   Registry with a plain-language, novice-friendly explanation (the user of this
   platform is NOT assumed to know game theory).
2. **Type hints everywhere.** Full annotations on all public signatures.
3. **Parameter Registry is the single source of truth** (`pdsim/config/registry.py`).
   Never add a tunable parameter anywhere else. UI tooltips, docs, and validation are
   generated from it. A parameter without a registry entry is a bug.
4. **Headless engine.** Nothing under `pdsim/core/`, `pdsim/config/`, or `pdsim/io/`
   may import UI or plotting code. The engine communicates via the typed event stream.
5. **Seeded randomness only.** All randomness flows from the single injected
   numpy `Generator`. Never call unseeded `random`/`np.random` module functions.
6. **Interfaces before implementations.** New mechanisms (selection rules, matchers,
   games, mutation kinds, score accounting) are added as implementations of the
   existing ABCs. If an ABC doesn't fit, update `docs/DESIGN.md` first, log the decision
   in `docs/DECISIONS.md`, then change code.
7. **Tests accompany features.** pytest; every strategy has decision-table tests;
   engine changes must keep the golden validation tests (`docs/DESIGN.md` §7) green.
8. **Reproducibility.** Every run saves complete config + seed. Never break the
   ability to re-run an old `config.yaml`.

## Style

- Python ≥ 3.11. `ruff` for lint+format (config in `pyproject.toml`). Google-style
  docstrings. Dataclasses/pydantic models for configs — no bare dicts across
  module boundaries.
- Names: strategies in `pdsim/core/strategies/`, one module each, registered via the
  strategy registry so the UI discovers them automatically.

## Commands

All commands assume the project venv is active (`.venv\Scripts\Activate.ps1`
in PowerShell), or prefix them with `.venv\Scripts\` — the system Python does
not have `pdsim` or its dependencies installed.

- Run tests: `pytest`
- Lint/format: `ruff check . && ruff format .`
- Launch UI: `streamlit run pdsim/ui/app.py`
- Headless recorded run: `python -m pdsim.run path/to/config.yaml` or
  `python -m pdsim.run --scenario <name>` (folders land in `runs/`)
- Regenerate parameter docs: `python -m pdsim.gendocs` (rewrites the committed
  `docs/PARAMETERS.md`; a pytest drift test fails while it is stale — rerun
  this after ANY registry change and stage the result)
- Benchmark: `python -m pdsim.bench` (median wall-clock seconds/generation
  across an N x matcher grid — the vectorization-trigger data, DECISIONS #58;
  `--out PATH` writes CSV; output is environment-specific, never committed)
- Run a sweep: `python -m pdsim.sweep path/to/spec.yaml` (a family of runs
  varied along composition/parameter/seed axes; results land in `sweeps/`;
  DECISIONS #66-#71). `--resume` continues a partial sweep; for large
  campaigns point `--out` outside the OneDrive-synced tree. The app's
  **Sweep tab** authors and launches the same sweeps from the UI — it
  writes the spec YAML and spawns this exact command as a detached
  subprocess, so execution stays headless and a tab-launched sweep is
  resumable/killable from the terminal like any other (DECISIONS #72-#74).
- Terminal demos: `python examples/quickstart.py`, `python examples/tournament_demo.py`

(Keep this section updated as tooling lands.)

## Design-layer documentation: the knowledge-preservation contract

This project is developed across multiple AI environments. Design discussion happens
in the Claude.ai project chat; implementation happens here in Claude Code. **The
files in `docs/` are the ONLY shared memory between these environments.** The chat
side never sees this conversation, the code, or the commit history — it sees only
the `docs/` files the user uploads to it.

**The standard every `docs/` file must meet:** an external advisor (human or AI)
who reads ONLY `docs/DESIGN.md`, `docs/DECISIONS.md`, `docs/ROADMAP.md`, and
`docs/specs/*` must be able to give correct, current advice about this project —
without seeing the code. If knowledge exists only in code, in commit messages, or
in this conversation, it is invisible to every other advisor. Capture it.

**Triggers that REQUIRE a `docs/` update in the same session** (not "when
convenient" — same session, before finishing):

- A designed interface or contract changed, or didn't fit and was adapted.
- A new mechanism, parameter, module, or dependency was introduced that
  `docs/DESIGN.md` doesn't describe.
- A design decision was made during implementation — anything where a reasonable
  alternative existed and one path was chosen (append to `docs/DECISIONS.md`:
  number, date, decision, rationale, alternatives).
- A modeling ambiguity, performance wall, or open question was discovered
  (log it, even if unresolved — open questions are design state too).
- A milestone completed or scope shifted (update `docs/ROADMAP.md`; append a
  one-line status, e.g. "✅ M2 landed 2026-07-12, 38 tests passing").
- Anything the user decided in conversation here that a future session would
  need to know.

**`docs/DECISIONS.md` is append-only**: number, date, decision, rationale,
alternatives considered. Reversals get a new entry referencing the old one.

**Milestone specs (`docs/specs/`) and the division of labor.** The design
chat (Claude.ai) delivers milestone-scale work as a single Claude Code
prompt that FIRST creates the milestone's spec file under `docs/specs/` and
THEN implements it. The spec file — not the chat prompt — is the durable
statement of intent; specs are part of the knowledge-preservation contract
(the advisor standard above already includes `docs/specs/*`). Every spec
must contain a `## Validation` section, WRITTEN AT SPEC TIME, describing how
the owner will confirm the milestone's features in the app: the scenario to
load, the widget interactions, and the expected observable behavior — CLI
steps only for inherently headless features (DECISIONS #61).

Spec mechanics (DECISIONS #62, naming amended by #92): file names are
`M<zero-padded milestone><letter>-<slug>-spec.md` (and explainers end
`-explainer.md`); older files predating #92 keep their names; each spec opens with
`Status: draft | in progress | implemented (see DECISIONS #...)`, updated as
work proceeds. Specs are **frozen intent** — authoritative until the
milestone lands; deviations during implementation are logged in
`docs/DECISIONS.md` and the spec is not retro-edited beyond its status
line; after landing, DESIGN/DECISIONS are the truth and the spec is
historical record. Specs count as docs for the DOCS CHANGED ritual and are
uploaded to project knowledge. Small fixes still travel as plain prompts —
specs are for milestone-scale work.

**Prompt size limit.** A single prompt must stay under 50,000 characters. The
harness truncates silently past that, marking the cut but leaving the
receiving session with no way to recover the tail. Deliverables that would
exceed the limit are split into numbered sub-prompts at a natural section
boundary, each self-contained, each with its own `Action required:` line, and
each stating explicitly where it stops so the receiving session knows the file
is deliberately incomplete.

**Markdown must arrive as source, not as rendered text.** Prompts containing
markdown are delivered as `.md` files or inside fenced code blocks, never as
text copied from a rendered chat view. Copying from a rendered view strips
headings and emphasis, converts tables to tab-separated lines, and silently
corrupts literal asterisks — an `e*` becomes an italic marker and the asterisk
vanishes. If a received prompt shows any of these symptoms, report it and
request re-delivery rather than writing the damaged text.

**Mandatory end-of-session ritual.** Every session that changed code or made
decisions ends with these steps, in order:

1. Re-check the triggers above; make any missing `docs/` updates now.
2. Report to the user explicitly, in this exact shape:
   - `DOCS CHANGED: <list of changed docs/ files> — please refresh these in the
     Claude.ai project knowledge before your next design conversation.`
   - or `DOCS UNCHANGED: no design-layer changes this session.`
3. If DECISIONS.md gained entries, mention the new entry numbers so the chat
   side can spot the delta at a glance.

Never end a significant session without step 2. Stale or silent docs are bugs —
they cause other advisors to give wrong advice with full confidence.

## Session continuity (the WIP.md protocol)

The end-of-session ritual has one blind spot: a session that runs out of
context never reaches its end. This protocol covers that gap (DECISIONS
#43) — and one scheduled job besides: the phase-boundary hand-off at ▲
session resets. `docs/WIP.md` has two sanctioned roles:

**(a) The context-limit escape hatch.** When a session approaches its
context limit mid-work, STOP working and write `docs/WIP.md` containing:

1. **State of the work**, at file-and-task granularity: what is done, what is
   in flight, what comes next.
2. **Pending docs obligations**: every decision made this session that is NOT
   yet logged in `docs/DECISIONS.md` or reflected in `docs/DESIGN.md` /
   `docs/ROADMAP.md`. These obligations transfer to the resuming session.
3. Anything else the resuming session must know that exists only in this
   conversation.

Then tell the owner to start a fresh session — and still perform the
mandatory end-of-session ritual.

**(b) The phase-boundary baton.** At the end of a COMPLETED phase whose
phase plan schedules a ▲ session reset, write `docs/WIP.md` deliberately:
phase state, staged-awaiting-commit status, and the next phase's entry
point (including any verification tasks it carries).

In both roles the next session reads it at start and deletes it once its
contents are absorbed. **Every session MUST check for `docs/WIP.md` at
start.** The leftover rule, restated: a `WIP.md` existing BETWEEN sessions
is legitimate; one still present after its successor session has started
and absorbed it is a bug.

**Never the sole carrier.** `docs/WIP.md` is git-ignored — invisible to the
design layer (Claude.ai) and to commits. It must NEVER be the only place a
decision, deviation, pending docs obligation, or verification-task answer
lives: all such content goes in tracked docs (`docs/DECISIONS.md`, the
spec, regenerated docs) and in the end-of-phase handback text, with WIP.md
at most duplicating it. A WIP.md states explicitly whether it carries
pending obligations — and the answer should always be "none beyond what
tracked docs already hold."

`docs/WIP.md` is **ephemeral**: it is not part of the knowledge-preservation
contract (never uploaded to the design chat), it must never appear in a
suggested commit file list, and it is never counted in the DOCS CHANGED /
DOCS UNCHANGED report.

## Current phase

v2 per `docs/ROADMAP.md`, on the renumbered economy-first spine
**M10 → M11 → M12 → M13 → M14 → M15 → M16 → M17 → M18 → M19** (DECISIONS
#76; execution order = numeric order, no gaps; M19 — geographic
structures — appended 2026-07-28, purely additive, #103). v1 — pairwise repeated PD,
object-per-agent engine, Fermi selection, strategy-switch mutation,
Streamlit UI, persistence + headless CLI — is complete (M8, 2026-07-07).
M9 (selection rules, accounting, cooperation recording), M9.5 (sweep layer
+ Sweep tab), **M10a (the score-as-energy growth economy, synchronous
generational — variable N, energy ledger, births/deaths, extinction,
schema 3; DECISIONS #76-#84)**, and **M10b (the asynchronous / Moran-style
event time-model — `time_model` clock choice, focal-bundle events on the
1/N(t) generation-equivalent clock, variable_n + fixed_n demographic
engines, symmetric imitation overlay, explicit birth/death/imitation
events, recording cadence + schema 4; DECISIONS #85-#92, #93-#102)** are
complete. M11 (population structure) is chat-designed (DESIGN §2.12,
DECISIONS #103-#110) and splits into **M11a** (structure, local birth,
local interaction) and **M11b** (movement + layout painter).

**M11a is COMPLETE (2026-08-14; DECISIONS #111-#160; spec
`docs/specs/M11a-population-structure-spec.md`, status: implemented;
1059 tests passing).** What it delivered, phase by phase: **A** (#112) —
`pdsim/core/structure.py` (graph of sites, lattice builder, the reach
kernel, the ONE `neighbourhood_sample` primitive), wired to nothing.
**B** (#116-#126) — occupancy, the seven founding layouts plus the
layout file, site-id persistence at schema 5, the grid renderer.
**C — local birth** (#127-#136) — occupancy LIVE in all three engines,
the amended #80 birth step (contest permutation, kernel placement,
place-before-pay, blocked parents counted and shown live),
`birth_radius`/`birth_decay`/`placement_contest`/`boundary_order`, K's
site-count derived default + the K-family validators, the localised
`fixed_n` draws with the R = 1 Ohtsuki reduction (#132), four negative
+ three positive golden masters with the counting-wrapper no-draw pins
(#133). **D — local interaction** (#137-#140) —
`matching.spatial_interaction` + `interaction_radius`/`interaction_decay`,
the thin `SpatialKernel` sync adapter and the async partner-draw
substitution (both single calls into the one primitive), the
draw-unconditionally/empty-eligible RNG contract, the fourth positive
golden (#138); VT-6(b) measured EXACTLY 8 matches per agent per
generation (#139); V6: no visible b/c > k separation at this engine's
strong selection, reported honestly (#140). **E — polish, five
sub-prompts** — E1 (#141-#144): the `STRUCTURE_GREYING` predicate table
consumed by both clock branches + the §12 paint-time readouts; E2
(#145-#149): pixel-array rendering fallback + ≈ 3 px cell floor in the
one `grid_chart` path, the ninth §12 readout, the results browser's
Founding | Final selector, golden suite renamed
`pdsim/tests/test_golden_masters.py`; E2b (#150): the sparse-`stripes`
band, with the milestone's ONLY golden re-record (logged, confined,
two pins); E3 (#151-#153): the four registered scenarios
(`spatial_reciprocity` flagship, `donation_game_threshold`,
`the_drifting_frontier`, `the_filling_grid`), E3's findings reported
and held; E4a (#154-#155): the Economy panel's spatial calibration
branch (sync-gated; async pinned on current behaviour) and the Filling
Grid's rise-then-freeze rewrite; E4b (#156-#160): reach-kernel
precomputation in the ENGINE (`Structure.reach` +
`distance_weight_table`, draw-neutral, pinned by equality tests +
eight goldens zero re-recording + counting pins), the bench's
five-column structure grid (`python -m pdsim.bench --structure`;
hypothesis flat-in-R CONFIRMED, lattice-≤-random_k SPLIT — Moore
4-17% above, attributed to re-met fixed neighbours' history copies,
held for the design layer), the 54-item §12 audit (54/54 covered; one
text fix — the memory-depth note's spatial branch), the tabs decision
recorded (#158), the admission-quota OPEN question logged (#159,
deadline M11b, explicitly before M12), and the close-out (#160).

The M11a explainer shipped 2026-08-16
(`docs/explainers/M11a-population-structure-explainer.md`) after the
design-layer literature verification pass discharged the four #103/#111
publisher-record checks (DECISIONS #161). **Next per ROADMAP: M11b —
spec FROZEN 2026-08-17** (`docs/specs/M11b-movement-and-panel-spec.md`;
design rulings DECISIONS #164–#170: feasibility-aware admission resolves
#159, the in-activation / end-of-boundary movement schedule resolves the
#103 open item, `encounter_mode`, the `advanced` disclosure flag,
live-run display continuity, the measurement-gated async calibration,
and the A2 trigger amendment). Phases A–E, one per fresh session. **Phase A —
feasibility-aware admission (#164) — landed 2026-08-17 (DECISIONS #171;
the re-recording budget went UNUSED). Phase B — movement — landed
2026-08-18 (DECISIONS #172; `pdsim/core/movement.py`, the `movement.*`
registry section, two movement-on goldens RECORDED, zero re-recording;
1129 tests). Phase C — `matching.encounter_mode` — landed 2026-08-20
(DECISIONS #174 pre-drafting rulings + #175 build record;
dedup-after-draws in `SpatialKernel.pairings`, the greying row, the
#174(a) calibration display branch (2× vs 1×), the bench's two
`per_pair` columns with counted matches — the #156 held hypothesis
SUPPORTED; zero re-recordings, zero new goldens; 1157 tests). The next
implementation effort is Phase D (calibration + advisories A1-A3)**;
then E (tabs, disclosure, live-run continuity, layout painter,
close-out).
Design everything to not block the v2/v3 extensions listed in
`docs/DESIGN.md` §6.
