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

## Session continuity (context-limit protocol)

The end-of-session ritual has one blind spot: a session that runs out of
context never reaches its end. This protocol covers that gap (DECISIONS #43).

**When a session approaches its context limit mid-work, STOP working** and
write `docs/WIP.md` containing:

1. **State of the work**, at file-and-task granularity: what is done, what is
   in flight, what comes next.
2. **Pending docs obligations**: every decision made this session that is NOT
   yet logged in `docs/DECISIONS.md` or reflected in `docs/DESIGN.md` /
   `docs/ROADMAP.md`. These obligations transfer to the resuming session.
3. Anything else the resuming session must know that exists only in this
   conversation.

Then tell the owner to start a fresh session — and still perform the
mandatory end-of-session ritual (report DOCS CHANGED/UNCHANGED as usual;
`WIP.md` itself does NOT count as a docs change).

**Every session MUST check for `docs/WIP.md` at start.** If it exists: read
it, resume from it (including the pending docs obligations), and delete it
once its contents are absorbed. A `WIP.md` left behind after its work is
complete is a bug.

`docs/WIP.md` is **ephemeral**: it is not part of the knowledge-preservation
contract (never uploaded to the design chat), it is git-ignored, and it must
never appear in a suggested commit file list.

## Current phase

v2 per `docs/ROADMAP.md`, on the economy-first milestone spine
M9 → M9.5 → M10 → M12 → M11 → M13 → M14 (DECISIONS #58). v1 — pairwise
repeated PD, object-per-agent engine, Fermi selection, strategy-switch
mutation, Streamlit UI, persistence + headless CLI — is complete (M8,
2026-07-07). Next up: M9 (selection rules, score accounting, pairwise
cooperation recording). Design everything to not block the v2/v3 extensions
listed in `docs/DESIGN.md` §6.
