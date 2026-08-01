# CLAUDE CODE PROMPT — M11a, PROMPT 1B: COMPLETE THE SPEC (PART 2 OF 2)

## What this prompt does, and what it must not do

**Edit exactly one file: `docs/specs/M11a-population-structure-spec.md`**, which
Prompt 1A created and which currently ends with a stub headed
`## Sections still to be written (Prompt 1B)`.

Write **no code**. Add **no registry entries**. Write **no tests**. Change **no
other file** — not `DESIGN.md`, not `DECISIONS.md`, not `ROADMAP.md`, not
`PARAMETERS.md`, not `CLAUDE.md`. The DECISIONS entries and ROADMAP amendments
this milestone owes are *listed by this spec* and *written during the phases*;
none of them is written now. Do not run `python -m pdsim.gendocs` (nothing here
touches the registry). Do not run `pytest` (nothing changed).

Three mechanical steps, in order:

1. **Change the status line** — the file's first line — to exactly:
   `Status: draft`
   (Per DECISIONS #62 the ladder is `draft | in progress | implemented`.
   Implementation has not started, so `draft` is correct. The `INCOMPLETE,
   awaiting Prompt 1B` wording goes away entirely.)
2. **Delete the `## Sections still to be written (Prompt 1B)` stub** in its
   entirety.
3. **Append the sections below**, in this order, where that stub was.

Everything Prompt 1A wrote stays as it is. Do not revise Designs 0–10, the
Frozen intent, the Defining principles, or the verification tasks. If appending
these sections reveals a contradiction with what 1A wrote, **write the sections
as specified and raise the contradiction in your handback** — do not silently
reconcile.

## Read these first — do not rely on recall

- The existing `docs/specs/M11a-population-structure-spec.md` in full. You are
  continuing a document, and Designs 0–12 must read as one voice.
- `docs/specs/M10b-async-event-time-spec.md` — specifically its
  `## Parameters`, `## Phase plan (proactive session reset at each ▲)` and
  `## Validation` sections. **These are the shape to match.**
- `docs/DESIGN.md` §2.12 (the rendering contract and the M11a spec obligation
  at the end of it), §6.3, §5.
- `docs/DECISIONS.md` #34, #36, #42, #47, #61, #62, #78, #80, #81, #89, #91,
  #94, #97, #99, #100, #101, #102, #103–#110.
- `docs/ROADMAP.md`'s M11a, M11b and M19 entries.

## The register this spec is written in

Unchanged from Prompt 1A: full prose reasoning, jargon unpacked on first use,
alternatives stated along with why they lost, worked examples where a number is
clearer than a description. The project owner is a novice at game theory, and
external advisors read the `docs/` files without ever seeing the code.

**Everything below is FROZEN**, settled in the design conversation of
2026-07-30 plus the four findings reported back from Prompt 1A. Write it as
settled design. Do not re-derive it and do not substitute your own judgement.

## Four findings from Prompt 1A's handback that this spec must absorb

Your Prompt 1A inspection turned up code-level answers to all four verification
tasks and one stale comment. **The verification tasks stay open in the spec** —
reading code is evidence, not runtime verification, and the phases still
confirm them. But four consequences are now known well enough to write down,
and they are marked below at the point they apply:

- **VT-1** — payoff parameters are floats admitting −100 to +100, so negatives
  are accepted and the donation game's S = −1 is representable. The flagship
  scenario is unblocked.
- **VT-2** — sync imitation preserves agent ids (`dynamics.py:311-315`). This
  selects Design 10's **nothing-to-persist** branch, and Phase B implements
  only that branch.
- **VT-3** — the `fixed_n` breeder draw reads **accumulated energy** through
  #63's shift, with **no selection-intensity parameter**. Both second-order
  consequences fire, and the `donation_game_threshold` scenario text says so.
- **VT-4** — `slots = max(0, K − len(survivors))` reads the **applied
  post-death** list. This is the larger-effect branch; see the Phase C risk
  reading and the `boundary_order` help-text obligation below.
- **Stale comment** — `matcher.py`'s module docstring justifies the `Matcher`
  ABC (Abstract Base Class — the Python interface class that `RoundRobin`,
  `RandomK` and `SpatialKernel` all implement) taking full `Agent` objects on
  the grounds that "SpatialKernel will need `agent.position`". That
  continuous-position plan was dropped by #104: an agent's location is its
  occupancy of a site, held in `Occupancy`. The signature needs no change; only
  the stated reason is obsolete. **Cleanup is a Phase D task**, listed below.

---

# THE SECTIONS TO APPEND

## `## Design 11 — registry shape, section order, and the greying map`

### Section order

**Structure sits between Population and Dynamics:**

```
Game → Matching → Match → Population → STRUCTURE → Dynamics → Output → Run
```

Per #100(e) this order is inherited by the panel and by `PARAMETERS.md`.

**Rationale:** the three derived defaults then resolve in reading order down the
page — N in Population, rows/cols auto-defaulting from N in Structure, K
auto-defaulting from site count in Dynamics. **Each auto value's source sits
above it.**

**Accepted cost:** `matching.spatial_interaction` stays in Matching (the key is
fixed by #108 and §2.12), so the toggle renders four sections above the radii it
governs. Exactly one greying dependency points forward either way, so #101's
lookahead is exercised identically.

**Within Matching: register `matching.spatial_interaction` FIRST, above
`matcher`.** It is the gate, so `matcher` then greys off a sibling that rendered
before it — the clean direction.

### Radius nullability

Both radii are **nullable integers where blank means unlimited**, reusing
`population.memory_depth`'s existing "at least 1; may be empty" machinery rather
than inventing a sentinel value. **This is what makes §2.12's "R → ∞ with β = 0
is well-mixed" expressible as a parameter rather than as a branch.**

### The layout file is the seventh enum value

`from_file` joins the `initial_layout` dropdown, and `layout_file` is live only
then and greyed otherwise. **Rejected:** a non-empty `layout_file` silently
overriding the dropdown — that produces a bug report about a layout setting that
"doesn't do anything." The chosen form is the idiom the app already uses
(`match.length_mode = continuation` is what makes `continuation_probability`
live).

### The greying map

- All `structure.*` grey under `structure.kind = well_mixed`.
- `structure.layout_file` greys off `initial_layout = from_file`.
- `interaction_radius` / `interaction_decay` grey off
  `matching.spatial_interaction`.
- `matching.matcher` **greys** off `matching.spatial_interaction` (#108).
- `matching.opponents_per_agent` (k) **stays live always**, with the clamp
  explained in its help text (#81 idiom, #108).
- `carrying_capacity` stays **live** with its site-count derived default (#106).
- `population.size` stays **live** and validated (N = site count under `fixed_n`
  + lattice).
- **`structure.birth_radius` / `birth_decay` STAY LIVE UNDER `fixed_n`.** They
  define the competition set for a freed site, which is the k that the b/c > k
  threshold counts. This is a consequence of Design 7, and **it reverses the
  naive reading that birth parameters are irrelevant when population is
  pinned** — say so explicitly in the spec, because the naive reading is the one
  a reader will arrive with.
- **`structure.placement_contest` is a three-way conjunction:** live only under
  synchronous **and** lattice **and** `energy_economy` (#107). This predicate
  spans Matching-adjacent, Structure and Dynamics, and points forward regardless
  of section placement.
- **`dynamics.boundary_order` is live under all synchronous runs**, greyed only
  under async — with the Design 5 reasoning, now reinforced by VT-4.

### `helpers.greying` has two branches — every rule must be slotted into both

Prompt 1A's inspection found that `helpers.greying` **delegates early to
`_async_greying`**, so the synchronous and asynchronous paths are separate code.
Write this into the spec as a Phase E obligation with its reason: a rule present
in only one branch produces exactly the failure #34 warns against — **the app
asserting something false about the user's run**. `dynamics.boundary_order` is
the sharp case, since its entire content is "live under sync, greyed under
async", which is a statement about both branches at once. Every `structure.*`
rule needs a defined answer on both sides, even where that answer is "greyed,
because async never reads it."

### Two extensions to #101's lookahead

1. **Predicates, not single-key lookups.** `placement_contest` and the birth
   pair need a **conjunction** form. Whether `helpers.greying`'s rule form
   already admits conjunctions is **not yet established** — Prompt 1A confirmed
   the return shape `(disabled, note)` and the #101 forward lookahead, but not
   the conjunction question. **Phase E opens with an explicit task: inspect
   `helpers.greying` and report whether the rule form admits conjunctions**,
   rather than assuming either way.
2. **Resolvers callable at paint time.** The §12 obligation includes derived
   readouts (emergent site count, effective neighbour count). Displaying
   "auto → 10 × 10" next to blank rows/cols, or an honest K default, means the
   panel must call the resolvers **with possibly-blank inputs while painting**.
   That is more than the lookahead currently does — it reads raw widget values,
   it does not run the `mode="before"` resolution logic. **Make those resolvers
   pure free functions callable from both the validator and the panel**: the
   M10a `resolve_initial_energy` pattern applied again. Say this in the spec, or
   Phase B will hardcode a display string that drifts.

### Build the greying map as a predicate table

**As data, not as conditionals scattered through panel code.** It is a table of
"this parameter is inert when these conditions hold." **Hiding is then a second
renderer over the same table**, which makes M11b's tab work a *presentation*
change rather than an audit. This is cheap now and expensive later, and it is
the enabling piece M11a carries on behalf of M11b's user-interface
simplification.

## `## Design 12 — site_capacity: the field ships, the knob does not`

**`site_capacity` is NOT a registry parameter in M11a.** #104 requires the
**field** to ship so that placement checks `occupants < capacity`. It does not
require the **knob**. Capacity ships as a plain field on `Site`, **pinned at 1
and validated as such**, with a constant on the builder. Registering it would
mean a panel widget with exactly one legal value.

It is deferred to **M19 not on effort grounds** but because capacity > 1 forces
three questions M11a has no answers to:

1. **What the reach kernel does at distance zero.** Two agents in one site would
   have weight exp(−β·0) = 1, the maximum, for **every** β — so no amount of
   decay could make a housemate less likely to be picked than a next-door
   neighbour. That is a substantive modelling claim smuggled in as an arithmetic
   side-effect.
2. **What colour a cell holding one cooperator and one defector is.** §6.3
   records this as open, and notes that blending softens cluster **boundaries**,
   which is the signal the Hammond–Axelrod story is about.
3. **What k IS** when neighbourhood size becomes occupancy-dependent and changes
   every generation, which costs the b/c > k comparison its fixed reference
   point.

**The density dial M11a does have is `carrying_capacity`**: per #106, K below
site count leaves permanent slack (a 20×20 grid at K = 250 runs at roughly 60 %
occupancy) in which the occupied region drifts, clusters and migrates.

**Mandatory record-keeping, three places** — state all three:

- the M11a DECISIONS entry records the pinned-at-1 field and names the three
  deferred questions;
- **ROADMAP's M19 entry gains an explicit TASK line**: "register `site_capacity`
  as a tunable registry parameter and remove M11a's pinned-at-1 validator" —
  stated as a task, not as background, so it cannot be read past;
- **the spec's own out-of-scope section carries it** (written below).

Registering it later is **additive** (one registry entry plus removing one
validator), not a migration. #104's forward-guard is fully satisfied by the
field existing now.

## `## Parameters`

Introduce the table, then give it with columns **Key | kind | default | phase |
notes**, in **widget order** — geometry, layout, birth group, interaction group.
Fourteen rows.

| Key | kind | default | phase | notes |
|---|---|---|---|---|
| `structure.kind` | choice (`well_mixed`, `lattice`) | `well_mixed` | A | the gate; all other `structure.*` grey off it |
| `structure.rows` | int, nullable, ≥ 1 | blank (auto) | A | auto → most-square factor pair of N (#78 idiom) |
| `structure.cols` | int, nullable, ≥ 1 | blank (auto) | A | same |
| `structure.neighbourhood_shape` | choice (`moore`, `von_neumann`) | `moore` | A | the distance metric handed to BOTH kernels |
| `structure.boundary` | choice (`torus`, `bounded`) | `torus` | A | torus equalises degree |
| `structure.initial_layout` | choice (7 values) | `random` | B | `random`, `checkerboard`, `stripes`, `blocks`, `patches`, `central_block`, `from_file` |
| `structure.layout_file` | str, nullable | blank | B | live only when `initial_layout = from_file` |
| `structure.birth_radius` | int, nullable, ≥ 1 | 1 | C | blank = unlimited reach; R = 1 is Hammond–Axelrod |
| `structure.birth_decay` | float, 0.0–20.0 | 0.0 | C | β; irrelevant at R = 1 |
| `structure.placement_contest` | choice (`random`, `energy_priority`) | `random` | C | three-way conjunction gate (sync + lattice + `energy_economy`) |
| `structure.interaction_radius` | int, nullable, ≥ 1 | 1 | D | blank = unlimited reach |
| `structure.interaction_decay` | float, 0.0–20.0 | 0.0 | D | β |
| `matching.spatial_interaction` | bool | off | D | **Matching section, registered FIRST, above `matcher`** |
| `dynamics.boundary_order` | choice (`death_first`, `birth_first`) | `death_first` | C | **Dynamics section**; live under all sync, greyed under async |

Below the table, restate: every entry carries a plain-language,
mechanism-explaining description (hard rules 1 and 3), **and every choice enum
value is explained individually** per the M10a §12 rule — the §12 checklist
below is what makes that verifiable. `python -m pdsim.gendocs` is rerun in every
phase that touches the registry, and the regenerated `docs/PARAMETERS.md` is
staged with it, because a pytest drift test fails while it is stale.

## `## Phase plan`

Match M10b's shape: five phases, each with a reset marker. Use ▲ as the
proactive-session-reset marker, as M10b does, and open the section by saying
what the marker means — a fresh Claude Code session starts there, because
quality degrades before the hard context limit is reached.

**Phase A — the structure module, wired to nothing.**
`pdsim/core/structure.py`: the `Site` record (id, neighbour set, capacity,
optional coordinate); the `Structure` abstraction; `WellMixedStructure` as the
degenerate builder; `LatticeStructure` as the rectangular builder. Distance as a
structure-supplied method — Chebyshev for `moore`, Manhattan for `von_neumann`.
`sites_within()`, `kernel_weights()` and the `neighbourhood_sample()` primitive:
implemented and tested, **called by no engine**. The registry gets **only the
geometry block** — `kind`, `rows`, `cols`, `neighbourhood_shape`, `boundary` —
plus `StructureConfig` with the most-square derived default and its validators.
**No engine imports this module.** Every existing run is untouched by
construction, so byte-identity is trivially true and the phase is judged purely
on whether the abstraction is right.
Tests: degree counts under torus versus bounded (interior 8/4; corner 3/2 under
`bounded`; uniform under `torus`); Moore versus von Neumann neighbour sets at
radius 1 **and** radius 2; most-square factorisation including the prime-N 1×N
line; distance symmetry and the triangle inequality; the four kernel corners
from #105 (R = 1; β = 0 with R = n; large β with R = n; R → ∞ with β = 0).
**VT-1 runs first, before anything else in this phase.** ▲

**Phase B — occupancy: founding, layouts, rendering, persistence.**
The `Occupancy` object (Design 3). Agents acquire sites at generation 0. All
seven `initial_layout` values plus the layout-file mechanism and its format.
Site id enters `AgentSnapshot`, `agents.parquet` and the schema version. **And
the grid renderer.**
The renderer lands **here, not in Phase E**, on app-first grounds (#42/#61):
there is no honest way to validate a layout except to look at it. "Load the
scenario, set `initial_layout = checkerboard`, see a checkerboard" **is** the
validation; a test asserting that site 0 and site 1 hold different strategies is
a proxy for it. Phase B needs a renderer that is **correct at a few hundred
cells**; the pixel-array fallback and the ≈ 3 px floor wait for Phase E.
Note the one refactor this phase hides: **`AGENTS_COLUMNS` is currently a fixed
tuple**, so the conditionally-present `site_id` column means the writer must
vary its column set by run type and the loader must stay presence-driven
(#100(b)). This is a small change, not a schema conflict, but it is a change
rather than a pure addition and should be budgeted as one.
After B, structure exists and is visible but **nothing reads it**. Behaviour is
unchanged.
**VT-2 and VT-3 run in this phase.** VT-2's expected answer (ids preserved) is
already evidenced, so Phase B implements Design 10's nothing-to-persist branch
and reports confirmation; **if the runtime behaviour diverges from that
evidence, stop and report rather than switching branches unilaterally.** ▲

**Phase C — local birth. THE RISKIEST PHASE.**
`place_offspring` becomes structure-aware; `admit_births` keeps its global-gate
job. `birth_radius` / `birth_decay`; `placement_contest`;
`dynamics.boundary_order`. K as the second cap with the site-count derived
default and the K ≤ site-count validator; the `fixed_n` + lattice N = site-count
validator. Death frees a site, birth occupies one. The Design 9 RNG contract
amendments and their golden masters.
**VT-4 runs in this phase**, and its answer is already evidenced as the
post-deaths branch — see the risk reading below for what that costs. ▲
**This phase is also the candidate for a fifth, mid-phase reset.** It is flagged
here so it is planned rather than discovered in a handback.

**Phase D — local interaction.**
`matching.spatial_interaction`; `interaction_radius` / `interaction_decay`; the
`SpatialKernel(Matcher)` synchronous adapter over the Phase A primitive; the
async loop calling the primitive directly; the k clamp; the `spatial_interaction`
requires `lattice` validator.
**Also in this phase: correct `matcher.py`'s stale module docstring.** It
currently justifies the `Matcher` abstract base class taking full `Agent`
objects on the grounds that a future `SpatialKernel` would need
`agent.position` — a continuous-coordinate plan dropped by #104. Replace the
justification with the real one: `SpatialKernel` holds the structure and
occupancy at construction, and an agent's location is its site. This is a
comment change with no behavioural effect, scheduled here because Phase D is
when someone implementing `SpatialKernel` would otherwise read it and go looking
for an attribute that does not exist. ▲

**Phase E — polish.**
The full greying map **built as a predicate table** (Design 11), slotted into
**both** `helpers.greying` branches; the pixel-array rendering fallback and the
size floor; the named validation scenarios; the bench structure column;
`python -m pdsim.gendocs`; and the §12 checklist audit run **item by item
against the enumerated list below, with coverage reported**.
Phase E **opens** with the `helpers.greying` conjunction inspection.

### Risk reading

Write this as its own sub-section of the phase plan; it is the part a resuming
session most needs.

**C is riskiest, and not because it changes demography. C is riskiest because
its failures are SILENT.**

**(i) It amends a sequence #80 declares frozen, and the amendment is a GATE.** A
gate has two failure directions and they fail differently. Drawing the contest
permutation when structure is **off** breaks byte-identity on every existing
seeded run — loud, caught immediately. **Not** drawing it where contention
genuinely exists is **silent**: the run completes, the numbers look plausible,
and the golden master for that configuration pins the wrong stream forever.
#107 confines contention to exactly one configuration (synchronous + structure +
`energy_economy`) and **the correctness of that confinement is an argument, not
a test**. The async and `fixed_n` exclusions therefore need pins asserting **no
draw occurs**, not merely that the result is reproducible.

**(ii) `place_offspring` can fail for the first time.** #80 checked placement
before payment against a stub that always returned true. The branch now goes
live, and the consequence is behavioural: a parent walled in by occupied
neighbours pays nothing, stays eligible, and keeps accumulating. Correct — it is
the whole content of viscosity — but an agent sitting at five times θ and not
breeding **reads as a bug** unless the Economy panel says "blocked: no site in
reach." Treat that readout as a **Phase C deliverable**, on the #89(e) logic
that put the calibration readout into M10a.

**(iii) Two orderings become three and they can silently collapse.** #80 keeps
admission order (energy descending, id ascending) separate from iteration order
(parent-id ascending), pinned by a test where they differ. Phase C inserts a
contest permutation between them. **The specific bug:** applying the permutation
to a list that has **already** been energy-sorted and then iterating it — which
yields a `random` contest that is quietly energy-biased in exactly the way #107
rejected. The pin needs a fixture where **all three orders differ pairwise**,
harder to build than #80's two-way case, and **it should be written before the
code it tests**.

**(iv) A boundary-order bug produces PLAUSIBLE DYNAMICS, not a crash.** Under
`death_first` versus `birth_first` the set of available sites differs — the whole
content of #107. Get it wrong and you get a frontier that behaves like an
interior, which is the mechanism M12 is being built to study.

**(iv-a) VT-4's answer makes `boundary_order` doubly restrictive, and this must
be written into the help text.** `slots = max(0, K − len(survivors))` reads the
**applied post-death** list. Work the arithmetic through in the spec, because
the size of the effect is the point. Take K = 200, a living population of 180
entering the boundary, and 20 deaths:

- under `death_first`, deaths land first, survivors = 160, so
  slots = 200 − 160 = **40 births admitted**;
- under `birth_first` there is no post-death list yet, so the ration is computed
  against the pre-death population: slots = 200 − 180 = **20 births admitted**.

So `birth_first` admits roughly **half** the births in this example — and *then*
the death phase runs and those newborns face the age-mortality coin as well.
The parameter is restrictive twice over, and both effects push population down
relative to `death_first`. **A `birth_first` run sitting at a visibly lower
population is correct, not broken**, and the registry help text must say so
rather than leaving it to be rediscovered. This is a different demographic
regime, not a phase offset, and it is present **even under well_mixed** — which
is a second, independent reason the Design 5 decision to keep the parameter live
under all synchronous runs was right.

**Second-riskiest is B.** Founding placement is where structure meets #67's
three-bucket composition, and a mistake there is a **systematic bias present in
every run from generation 0**. It is caught by **looking** at the grid — the
strongest argument for the renderer landing in B.

**Third is D, and its risk is well-shaped**: an additive change at the `Matcher`
seam, the extension point `RandomK` already proved in M8 under #57, with the
async side a **substituted** partner draw rather than an inserted one.

## `## The §12 checklist (53 items)`

Open by saying what this is and why it is enumerated rather than described:
DESIGN §2.12's M11a spec obligation, restated by #103, requires that every new
concept, **every enum value individually**, and every derived readout carries an
inline `(?)` explanation drawn from a **single described source**, so that app
text and documentation cannot drift apart. Roughly fifteen parameters arrive at
once, and a parameter-level description silently skips the enum values inside
it. **Phase E runs this list item by item as an audit pass and reports
coverage.**

Then give the four groups as numbered lists, with the counts stated.

**14 registry parameters** — a plain-language description each. Structurally
guaranteed by DESIGN §5, but listed so the checklist is complete rather than
partly implicit: `structure.kind`, `structure.rows`, `structure.cols`,
`structure.neighbourhood_shape`, `structure.boundary`,
`structure.initial_layout`, `structure.layout_file`, `structure.birth_radius`,
`structure.birth_decay`, `structure.placement_contest`,
`structure.interaction_radius`, `structure.interaction_decay`,
`matching.spatial_interaction`, `dynamics.boundary_order`.

**17 enum values, each individually explained** — this is the part §12 exists
for: `well_mixed`, `lattice`; `moore`, `von_neumann`; `torus`, `bounded`;
`random`, `checkerboard`, `stripes`, `blocks`, `patches`, `central_block`,
`from_file`; `random`, `energy_priority`; `death_first`, `birth_first`.

**14 concepts**, each with a `(?)` drawn from one described source: site;
exclusivity and capacity; neighbour and neighbourhood; support radius R; decay
β; the reach kernel; viscosity; wrap-around and why it equalises degree; degree,
and why cooperation thresholds depend on it; the two gates and why clearing one
is not enough; a blocked parent; arrangement versus composition; the b/c > k
threshold; spatial reciprocity.

**8 derived readouts**, each with a `(?)` **and a visible number**: emergent site
count; resolved rows × cols when blank; resolved K when blank, shown alongside
site count (#106's both-numbers guard); effective neighbour count after the
clamp — the k the threshold compares against; occupancy as a fraction; agents
with zero occupied neighbours at founding; blocked parents this generation;
whether pixel-array rendering is active.

**Two of those readouts are more than tooltips and belong in the Economy panel**,
not only in help text:

- **blocked parents** — stops a correct behaviour reading as a bug (risk reading
  (ii));
- **zero-neighbour agents at founding** — the guard on `random` scattering under
  a sparse population (Design 8).

## `## Validation`

Open with the app-first rule (#42/#61): with the virtual environment active
(`.venv\Scripts\Activate.ps1`), launch `streamlit run pdsim/ui/app.py`.
Automated tests **complement, never substitute**.

- **V1 (app) — structure exists and is visible.** The lattice renders, cells are
  exactly square, and the site count is reported. *Phase B.*
- **V2 (app) — layouts.** Walk `initial_layout` through all seven values and see
  each arrangement. *Phase B.*
- **V3 (app) — viscosity.** Cooperator clusters survive where they would be
  wiped out well-mixed. *Phases C + D.*
- **V4 (app) — `boundary_order`.** Same configuration, `death_first` versus
  `birth_first`, divergent outcome. **Run this in two passes, because VT-4
  established two independent effects and one run cannot tell them apart.**
  First pass with **age-mortality off**: the newborn-exposure channel is
  silenced, so any divergence is the slots rationing alone, and the
  `birth_first` population should sit visibly lower per the risk reading's
  worked example. Second pass with mortality on: both channels live, and the
  divergence is larger. *Phase C.*
- **V5 (app) — the drifting frontier.** K below site count; the occupied region
  migrates. *Phase C.*
- **V6 (app) — the b/c > k threshold.** von Neumann clears, Moore fails.
  *Phase D.*
- **V7 (command line, headless) — golden masters, positive and negative.**
  *Phase C.*
- **V8 (command line, headless) — byte-identity regression** on four well-mixed
  configurations. *Every phase.*

### Four new registered scenarios

**`spatial_reciprocity` / "Cooperation Survives in Clusters" — THE FLAGSHIP.**
Synchronous `energy_economy`, lattice, local interaction and local birth at
R = 1, roster AllC and AllD only, one round per match. Cooperators in a cluster
earn R from all four neighbours; defectors in a defector interior earn P = 0
from everyone and starve under the living cost. Things-to-try: switch
`structure.kind` back to `well_mixed` and watch AllD take everything.

**`donation_game_threshold` / "The b/c > k Threshold"** — the Ohtsuki
replication attempt. **Unblocked by VT-1**: payoff parameters admit negatives,
so T = 5, R = 4, P = 0, S = −1 ships as designed and b/c = 5 is intact. Three
non-obvious requirements, each of which the scenario text must explain rather
than merely set:

- **`rounds_per_match = 1`, roster AllC + AllD only.** Ohtsuki's threshold is
  derived for **one-shot** games; with 50 rounds and TitForTat in the roster the
  threshold does not apply, and at one round TitForTat cooperates and is
  indistinguishable from AllC anyway. Consequence: noise, memory depth and every
  reciprocity parameter are **inert here** — the scenario text says so, rather
  than leaving a novice wondering where the seven-strategy roster went.
- **`fixed_n_death_rule = pure_random`, NOT the default.** Ohtsuki's death-birth
  is: a random individual dies, then its neighbours compete by fitness. The M10b
  default `energy_decides` makes the death deterministic. Getting this wrong
  yields a plausible run that is not the model being replicated.
- **The weak-selection honesty caveat, worded per VT-3's now-known answer.** The
  breeder draw reads **accumulated energy** through #63's shift with **no
  selection-intensity parameter**, so we cannot approach the weak-selection
  limit in which b/c > k is derived. State two things plainly: the threshold is
  a **calibration compass, not a prediction**; and because fitness reads a
  **stock rather than a flow**, relative differences widen as a run proceeds, so
  **effective selection strengthens over time**. Mark this wording as contingent
  on Phase B's VT-3 confirmation.

Ships as **von Neumann** — the case that **clears** the threshold, so the
default view shows cooperation succeeding. #36 says one scenario = one
configuration and comparative questions live in the things-to-try text, so the
things-to-try note says: switch `neighbourhood_shape` to `moore` and re-run,
**predicting the reversal before doing it**. Two scenarios differing in one enum
value would duplicate the mechanism things-to-try exists for.

**`the_drifting_frontier` / "The Drifting Frontier"** — K at roughly 60 % of site
count, so #106's slack is live and the occupied region clusters and migrates
rather than filling the grid.

**`the_filling_grid` / "The Filling Grid"** — `central_block` layout, growth
economy, expansion into empty space. The Kaznatcheev & Shultz regime, and the
reason #109 shipped that layout.

### Bench: the structure column

**Yes, and it tests a falsifiable claim** (#91/#102 discipline, not decoration).

Local interaction **reduces** match-phase work: k clamps to the neighbourhood —
4 or 8 at R = 1, against round-robin's N − 1. The interesting cost is the
**kernel draws**, where the naive implementation scales badly: enumerating sites
within radius R is O(R²), and at R = 10 under Moore that is 440 sites
enumerated, distance-computed and weighted, once per focal per event.

**The fix is precomputation**, available because of Design 3's topology/occupancy
split. Topology is immutable, so the candidate list for each site at each radius
is a pure function of the configuration and can be built once. Weights are
cacheable more cheaply still: weight depends only on **distance**, so **one
distance→weight lookup table per (R, β) pair** covers every site on the grid.
Per-draw cost then scales with neighbourhood size rather than with enumeration.
Memory stays modest — 10,000 sites at 440 neighbours each is a few million
integers.

**Two hypotheses, stated so the measurement can fail:**

1. cost is **flat in R** once the cache is warm;
2. the lattice column sits **at or below `random_k`** at equal k.

If (1) fails, the cache is not working. If (2) fails, the kernel draw is more
expensive than the matches it replaces — a surprise worth chasing.

Grid: N × {`round_robin`, `random_k`, `lattice_vn_r1`, `lattice_moore_r1`,
`lattice_moore_r5`}. Measured at **Phase E**. **Rendering cost stays out** —
that is #94's wall-clock throttling on a separate axis, and the bench measures
the engine. Output remains environment-specific and uncommitted.

## `## Out of scope`

- **`site_capacity` above 1** — the field ships pinned at 1 (Design 12); the knob
  is M19, and ROADMAP's M19 entry carries it as an explicit task line.
- **The M11a explainer.** A separate prompt, after a literature verification
  pass. Two claims are flagged UNVERIFIED in #103 and must be checked against
  publisher records before they enter it: whether Hammond & Axelrod used
  **wrap-around** on their 50×50 lattice, and the Kaznatcheev & Shultz
  **300-period figure** the M10 explainer currently quotes without a verification
  note of its own. Note that the `neighbourhood_shape` default is `moore` by the
  owner's call, **so the Hammond–Axelrod wrap-around verification no longer gates
  the default** — but it still gates the explainer and M12's replication
  scenario.
- **The user-interface tab / collapse / novice-advanced implementation.** That is
  M11b, deliberately **not** beside the riskiest phase in this milestone: a panel
  rewrite landing next to Phase C would make any regression ambiguous between
  "structure broke something" and "the panel rewrite broke something." What M11a
  carries is the **enabling piece** — the greying map as a predicate table
  (Design 11), plus the DECISIONS entry recording the decision.
- **Everything M11b**: agent movement, the `MovementRule` abstract base class,
  the walk radius/decay pair, the movement schedule, the mouse layout painter.
- **Irregular and geographic site sets, and co-residency semantics** — M19.

## `## Docs obligations`

State that numbering continues from **#110**, and that specs are frozen
historical records, so deviations during implementation become **new DECISIONS
entries, never retro-edits** (#62).

**DECISIONS entries the M11a work must produce:**

- the build decisions carried by this spec, as implementation proceeds, and
  wherever a deviation occurs;
- **Open Question 1's resolution** (Design 7), with the sync-imitation
  global-selection decline recorded **explicitly on scope grounds** and handed to
  M12;
- the **`site_capacity` pinned-at-1 field** and its three deferred questions;
- **the tabs decision, recorded even though nothing is built.** Write this one
  out at length in the spec, because it is the piece most likely to be lost:
  - the `run.mode` tab split;
  - **the total-fork criterion** — hide only where **every** parameter on the far
    side is genuinely ignored, with no exceptions and no partial cases. The
    reason is that a **greyed** widget says "this exists and does nothing here",
    while a **hidden** one says "this is irrelevant here" — and if the second
    claim is ever wrong, the user cannot see the parameter that is affecting
    their run;
  - **why `time_model` FAILS that criterion**: `selection_beta` follows the
    imitation **overlay**, not the mode (#101's carve-out), and the ledger knobs
    — L, engagement, r, σ — apply under synchronous economy **and** both
    asynchronous population modes. So Dynamics has a shared core with two
    mode-specific wings, not a clean cut;
  - **why `reproduction_mode` fails it**: the same shared-ledger problem, plus
    async `variable_n` **being** the economy under a different clock;
  - **collapse-with-summary** as the treatment for inert sections;
  - **novice/advanced disclosure as a separate, orthogonal axis** deserving its
    own decision.

**ROADMAP amendments:**

- **M19's entry** gains the explicit `site_capacity` registration **task** line;
- **M11b's entry** gains the user-interface simplification line (tab split +
  collapse + novice/advanced), alongside the layout painter.

---

# YOUR OBLIGATIONS ON FINISHING

1. **Do not commit.** Present (a) a summary of what you appended, (b) the list
   of files to stage — which should be exactly
   `docs/specs/M11a-population-structure-spec.md` — and (c) a suggested commit
   message. The owner performs the commit.
2. **Confirm the three mechanical steps**: the status line now reads exactly
   `Status: draft`; the `Sections still to be written` stub is gone; the new
   sections sit where it was.
3. **Report the file's total character count**, and confirm the spec now
   contains Designs 0 through 12, the Parameters table, the verification tasks,
   the Phase plan with its risk reading, the §12 checklist, Validation, Out of
   scope, and Docs obligations — with nothing left pending.
4. **Report `DOCS CHANGED: docs/specs/M11a-population-structure-spec.md`** per
   the end-of-session ritual, and state explicitly that **no DECISIONS entries
   were created** by this prompt.
5. **Verify the §12 checklist arithmetic in your handback**: 14 + 17 + 14 + 8 =
   53. If your written list does not total 53, say so rather than adjusting the
   headline number.
6. **Raise any contradiction** between these appended sections and what Prompt
   1A wrote — especially around Design 5's `boundary_order` reasoning versus the
   risk reading's VT-4 arithmetic, Design 10's persistence branches versus
   Phase B's instruction to implement only the ids-preserved branch, and
   Design 4's reference to "the fourteen concepts" versus the checklist's
   concept list. Report; do not silently reconcile.

Action required: apply the three mechanical steps to `docs/specs/M11a-population-structure-spec.md` and append the sections specified above, writing no code or tests or registry entries, then report the summary, the character count, the completeness confirmation, the checklist arithmetic, the files to stage, the suggested commit message, and the DOCS CHANGED line.
