# M11a — Handoff brief for the Phase A sessions

**Written:** 2026-07-31
**Supersedes:** `M11a-prompt-drafting-session-brief.md`, which is now spent — its
job was to get the spec written, and the spec is written.

**This document is authoritative for the sessions that follow it.** Where it
disagrees with a Claude instance's recalled context, this document wins. Where
it disagrees with the committed repository documents, **the repository wins** —
read them fresh.

---

# PART 1 — STATE

## What exists

`docs/specs/M11a-population-structure-spec.md` — **complete, committed,
`Status: draft`, 96,126 characters.** It contains Designs 0–12, the fourteen-row
Parameters table, four verification tasks, the five-phase plan with its risk
reading, the 54-item §12 checklist, Validation (V1–V8 plus four scenarios plus
the bench column), Out of scope, and Docs obligations.

`docs/DECISIONS.md` — current through **#111**.

**No M11a code exists.** Not one line. Phase A is the first implementation
prompt.

## How the spec was built, and why that matters

Three prompts, each reviewed before the next:

1. **Prompt 1A** — Designs 0–10 and the verification tasks.
2. **Prompt 1B** — Designs 11–12, Parameters, phase plan, §12 checklist,
   Validation, out-of-scope, docs obligations.
3. **Prompt 2** — a documentation-only pass adding the additivity finding, the
   flagship's explicit overrides, and DECISIONS #111.

The relevant inheritance: **the spec has already survived three review passes
and two rounds of contradiction-hunting.** A fresh session should treat it as
settled and read it rather than re-deriving it. The remaining known
imperfections are listed in Part 3 and are small.

## The four verification tasks — evidenced, not yet verified

Prompt 1A's code inspection produced answers to all four. **These are evidence,
not runtime verification**, and the spec deliberately keeps all four tasks open.
The distinction is load-bearing: a session that treats them as settled will skip
the confirmations that catch a wrong reading.

| | Question | Evidenced answer | Confirms in |
|---|---|---|---|
| **VT-1** | Do payoff parameters admit negatives? | **Yes** — floats, −100 to +100 (`registry.py:281-303`). Flagship unblocked; S = −1 ships. | Phase A, **first task** |
| **VT-2** | Does sync imitation preserve agent ids? | **Yes** — same `Agent` objects carry forward (`dynamics.py:311-315`). Selects Design 10's **nothing-to-persist** branch. | Phase B |
| **VT-3** | What does the `fixed_n` breeder draw read? | **Accumulated energy** via #63's shift, **no selection-intensity knob**. Threshold is a calibration compass, not a prediction; effective selection strengthens over time. | Phase B |
| **VT-4** | Is `survivors` pre- or post-death? | **Post-death** (`dynamics.py:577`). `boundary_order` is doubly restrictive — see the risk reading's worked K = 200 example. | Phase C |

## The one thing most likely to be misread

**`spatial_reciprocity` and `donation_game_threshold` rest on different
mechanisms, and the spec is careful about this.**

- `spatial_reciprocity` (the flagship) is **ecological**: with P = 0 a defector
  in a defector interior earns literally nothing and starves against the basic
  living cost L. Absolute income against a survival threshold.
- `donation_game_threshold` is **evolutionary**: Ohtsuki's b/c > k, about
  relative fitness in a Moran process under weak selection.

They point the same way, which makes them easy to blur. Never let one borrow the
other's justification.

---

# PART 2 — OPENING A FRESH DESIGN SESSION (Claude.ai, here)

## The opening message to paste

> This is the M11a Phase A prompt-drafting session. Attached is the handoff
> brief; it is authoritative and supersedes anything your memory tells you about
> this project, including milestone state and DECISIONS numbering. Project
> knowledge is current through DECISIONS #111 and the committed M11a spec.
>
> Read `docs/specs/M11a-population-structure-spec.md` in full before drafting —
> particularly Design 0, Design 2, Design 3, the Parameters table's Phase A
> rows, the phase plan's Phase A entry, and the VT-1 task. Then draft the
> Phase A prompt for Claude Code.

Attach: this brief. Ensure project knowledge holds the current spec and
`DECISIONS.md` (both changed in the docs pass — refresh them).

## The house rules a fresh instance must follow

**Delivery.** Every suggested change to code or docs is delivered as a **single,
complete, clearly labelled cut-and-paste prompt block for Claude Code** — never
as edits to make by hand, never split across prose. Every prompt ends with a
one-line **"Action required:"** statement. Prompts run long; if one would exceed
roughly 50,000 characters, **split it and say where the seam falls and why**.

**Claude Code never commits.** At every milestone or phase completion it
presents a summary, a file list, and a suggested commit message. Yoav commits.

**Explanation register.** Full prose reasoning at an undergraduate game-theory
level. Concrete worked examples with actual arithmetic. Jargon unpacked on first
use. **Every acronym or initialism spelled out the first time it appears in each
response** — including technical and project-internal ones.

**Fresh reads over memory.** Read the actual repository documents at session
start rather than relying on recalled content.

**Decisions carry rationale, and rejected alternatives get named.** Open
questions are distinguished from settled ones. Risks are named specifically
rather than gestured at.

## What Phase A's prompt must contain

Phase A is **the structure module wired to nothing**. Its defining property: no
engine imports it, so every existing run is untouched by construction and
byte-identity is trivially true. The phase is judged purely on whether the
abstraction is right.

Scope, from the spec:

- `pdsim/core/structure.py` — the `Site` record (id, neighbour set, capacity,
  optional coordinate); the `Structure` abstraction; `WellMixedStructure`;
  `LatticeStructure`.
- Distance as a **structure-supplied** method: Chebyshev for `moore`, Manhattan
  for `von_neumann`.
- `sites_within()` and `kernel_weights()` — pure and RNG-free — plus the
  `neighbourhood_sample()` primitive, with the signature the spec pins.
- **`site_capacity` as a plain field pinned at 1**, with its validator. Not a
  registry parameter (Design 12).
- Registry: **the geometry block only** — `kind`, `rows`, `cols`,
  `neighbourhood_shape`, `boundary` — plus `StructureConfig`, the most-square
  derived default, and its validators.
- **The ascending-site-id ordering rule** applied to candidate construction
  before any draw.

Tests: degree counts under torus versus bounded (interior 8/4; corner 3/2 under
`bounded`; uniform under `torus`); Moore versus von Neumann neighbour sets at
radius 1 **and** radius 2; most-square factorisation including the prime-N 1×N
line; distance symmetry and the triangle inequality; the four kernel corners
from #105.

**VT-1 runs first, before anything else in the phase.**

**Carry the one-line header fix** (Part 3, item 1) at the head of the prompt.

**Remember `python -m pdsim.gendocs`** — Phase A adds registry entries, so
`docs/PARAMETERS.md` is regenerated and staged with them, or a pytest drift test
fails.

---

# PART 3 — CARRIED ITEMS

## 1. Header fix (do this in Phase A's prompt)

The spec's top-of-file companion-explainer pointer says **two** claims gate the
explainer; the Out-of-scope bullet now lists **four**. Both are individually
true — the #103 pair genuinely gates it, and items 3–4 arrived with #111 — but
the asymmetry is visible to a sequential reader.

**Fix:** reword the header pointer to say the explainer is gated by the
verification items listed in the Out-of-scope section, so the count lives in
exactly one place and cannot drift again. One line, no count stated in the
header.

## 2. Design 7 duplication (watch, no action)

Design 7 says the b = 5 / c = 1 walkthrough "belongs in the explainer and is out
of scope for the spec", while Edit 3a put much of that arithmetic into the
scenario's fourth requirement.

**Not a contradiction.** Design 7 was scoping the *breeder localisation*
rationale (what k counts); Edit 3a is a *precondition on the payoff matrix*
(whether b and c exist at all). Same numbers, different claims. And a scenario
must be self-justifying at the point where it sets four specific payoff values.

**Action: none.** But when the explainer is written, check the two do not drift
into saying subtly different things.

## 3. Phase E's opening task

Phase E **opens** by inspecting `helpers.greying` and reporting whether its rule
form admits **conjunctions**. `placement_contest`'s three-way gate (sync **and**
lattice **and** `energy_economy`) needs one. Prompt 1A confirmed the return shape
`(disabled, note)` and the #101 forward lookahead but **not** the conjunction
question.

## 4. `helpers.greying` has two branches

The synchronous and asynchronous paths are separate code — the async branch
delegates early to `_async_greying`. **Every `structure.*` rule needs a defined
answer on both sides**, even where that answer is "greyed, because async never
reads it." `dynamics.boundary_order` is the sharp case: its entire content is
"live under sync, greyed under async", which is a statement about both branches
at once.

## 5. The `random` enum collides — a trap for the Phase E audit

`random` appears **twice** in the seventeen enum values: once as an
`initial_layout` value, once as a `placement_contest` value. The arithmetic is
correct, but the audit must not deduplicate — that would tick one and leave the
other unexplained. **The two meanings are entirely different**: as a layout it
means *shuffle the agents over the grid*; as a contest it means *one permutation
over the admitted birth set, so energy decides eligibility rather than who wins
a contested cell*. Copy-pasted help text would be actively wrong.

## 6. `AGENTS_COLUMNS` is a fixed tuple (Phase B)

The conditionally-present `site_id` column means the writer must vary its column
set by run type and the loader must stay presence-driven (#100(b)). Small, but a
**change** rather than a pure addition — budget it.

## 7. `matcher.py`'s stale docstring (Phase D)

The module docstring justifies the `Matcher` ABC (Abstract Base Class — the
Python interface class that `RoundRobin`, `RandomK` and `SpatialKernel` all
implement) taking full `Agent` objects on the grounds that "SpatialKernel will
need `agent.position`". That continuous-coordinate plan was dropped by #104: an
agent's location is its occupancy of a site. **The signature needs no change;
only the stated reason is obsolete.** Scheduled for Phase D because that is when
someone implementing `SpatialKernel` would otherwise read it and go hunting for
an attribute that does not exist.

## 8. Phase C may want a mid-phase reset

Flagged in the spec so it is planned rather than discovered in a handback.
Phase C is the riskiest phase — it amends a sequence #80 declares frozen, its
gate failures are silent in one direction, and it turns two orderings into three.

---

# PART 4 — OPENING A FRESH CLAUDE CODE SESSION

Claude Code sessions are **driven by the prompt drafted here**, so there is no
separate "design brief" to paste. What a fresh Claude Code session needs is the
standing context that every prompt assumes.

## Standing rules (these live in `CLAUDE.md`; a fresh session should re-read it)

1. **Never commit.** Present a summary, the file list to stage, and a suggested
   commit message. Yoav commits.
2. **Never edit files outside the prompt's stated scope.** If a needed change
   falls outside, **report it; do not act**.
3. **Same seed, same run.** Any change to random-number-generator consumption is
   a breaking change requiring a DECISIONS entry.
4. **Specs are frozen historical records.** Deviations become **new** DECISIONS
   entries, never retro-edits.
5. **`python -m pdsim.gendocs`** is rerun in any phase touching the registry,
   and the regenerated `docs/PARAMETERS.md` is staged with it.
6. **End every session with `DOCS CHANGED: [files]` or `DOCS UNCHANGED`**, so
   Yoav knows what to refresh in project knowledge.
7. **Report contradictions rather than silently reconciling them.** This has
   caught three real issues across the M11a spec prompts; it works.

## The session-opening message, if starting cold mid-milestone

> Read `CLAUDE.md`, `docs/DESIGN.md` §2.12, `docs/DECISIONS.md` #103–#111,
> `docs/specs/M11a-population-structure-spec.md` in full, and `WIP.md`. M11a's
> spec is complete and committed at `Status: draft`; no M11a code exists yet.
> Then wait for the phase prompt.

## The end-of-phase ritual

Every phase closes with: the summary, the file list, the suggested commit
message, the `DOCS CHANGED` line, the verification-task answer if that phase
carried one, and **any contradiction found but not acted on**.

---

# PART 5 — WHAT COMES AFTER M11a's PHASES

- **The M11a companion explainer** — see the schedule note below.
- **The payoff/parameter calibration guide** — see the schedule note below.
- **M11b** — agent movement, the `MovementRule` ABC, the walk radius/decay pair,
  the movement schedule, the mouse layout painter, and the user-interface
  simplification (the `run.mode` tab split, collapse-with-summary, and
  novice/advanced disclosure). M11a carries the **enabling piece**: the greying
  map built as a predicate table.
- **M12** — tag-based ethnocentrism. Inherits two explicit hand-offs: the
  localisation of synchronous imitation's `SelectionRule` (declined for M11a on
  scope grounds, Design 7), and #110's rolling `imitation_adopter` checkpoint.
- **M19** — geographic structures: irregular site sets, per-site capacity above
  1, co-residency semantics, map rendering. Carries an explicit ROADMAP **task**
  line to register `site_capacity` and remove M11a's pinned-at-1 validator.
