# M11a — Phase B: occupancy, founding layouts, the grid renderer, persistence

You are Claude Code working in the pdsim repository. This prompt implements
**Phase B** of milestone M11a, exactly as the frozen specification defines it.
It was drafted in the design layer against the spec, DECISIONS #103–#115,
CLAUDE.md, and the current PARAMETERS.md; where this prompt and the spec ever
appear to disagree, **the spec wins** — stop and report the discrepancy rather
than improvising.

## 0. Session start — do these before writing any code

1. **Check for `docs/WIP.md`.** Phase A ended at a scheduled ▲ reset, so a
   phase-boundary baton may be waiting. Read it, absorb it, delete it once
   absorbed.
2. **Read, in full:**
   - `docs/specs/M11a-population-structure-spec.md` — the whole file,
     **including both post-freeze addenda at its end** (the VT-5/VT-6
     addendum and the phase-task ledger). The sections this phase implements
     directly: Design 0, Design 3 (topology/occupancy split), Design 8
     (layouts and the layout file), Design 10 (persistence, schema 5), the
     Parameters table (the two Phase B rows), the Phase plan's Phase B block
     and its risk reading, Design 9's RNG inventory (the founding-layout
     row), and the Validation section's V1, V2, V8.
   - `docs/DESIGN.md` §2.12, §6.3, §4, §5.
   - `docs/DECISIONS.md` #67, #78, #80, #81, #83, #89, #99, #100, and
     #103–#115 (note #112 — Phase A's micro-semantics — and #114, which
     assigns this phase a measurement task).
   - `CLAUDE.md` — hard rules, the knowledge-preservation contract, the
     end-of-session ritual, the WIP.md protocol.
   - `docs/PARAMETERS.md`, Structure section, to see exactly what Phase A
     registered.
3. **Standing rules that bind this entire session:**
   - **The spec is frozen.** Any deviation you need — anything where the spec
     is silent, wrong, or does not fit the code you find — becomes a new
     `docs/DECISIONS.md` entry (number, date, decision, rationale,
     alternatives), **never** an edit to the spec body. The only permitted
     spec edit is its `Status:` line.
   - **Never run `git commit`.** The owner commits. You end by presenting a
     summary, a file list to stage, and a suggested commit message.
   - **Validation is app-first** (#42/#61): the owner confirms this phase by
     loading the app and *seeing* the feature. Automated tests complement,
     never substitute.
   - All hard rules in CLAUDE.md apply: docstrings everywhere, type hints,
     registry as the single source of truth, headless engine, seeded
     randomness only, tests accompany features, reproducibility.

## 1. Where the milestone stands, and what this phase is

Phase A landed 2026-08-01 (#112): `pdsim/core/structure.py` exists — the
`Site` record, the `Structure` abstraction, `WellMixedStructure`,
`LatticeStructure`, `sites_within()`, `kernel_weights()`, and
`neighbourhood_sample()` — implemented and tested, imported by no engine
code. The registry carries the five-parameter geometry block (`kind`, `rows`,
`cols`, `neighbourhood_shape`, `boundary`) with the most-square derived
default and the #112 one-blank ceiling-division rule.

**Phase B gives the structure occupants and makes it visible.** Its scope,
verbatim from the spec's phase plan: the `Occupancy` object; agents acquire
sites at generation 0; all seven `initial_layout` values plus the layout-file
mechanism and its format; site id enters `AgentSnapshot`, `agents.parquet`,
and the schema version; and the grid renderer, correct at a few hundred
cells.

**The exit condition, which every design choice below serves: after Phase B,
structure exists and is visible, but NOTHING READS IT.** No matcher, no birth
logic, no death logic, no selection draw consults the structure or the
occupancy. Behaviour is unchanged; every existing well-mixed golden master
passes byte-identical (V8). Local birth is Phase C; local interaction is
Phase D; the pixel-array rendering fallback and the ≈3 px cell floor are
Phase E — build none of them here.

## 2. Deliverables

### 2.1 The `Occupancy` object (spec Design 3)

A mutable, per-run object owned by the dynamics — exactly like the population
list — kept strictly separate from the immutable `Structure`:

- site id → agent id and agent id → site id mappings, kept mutually
  consistent;
- `occupy(site_id, agent_id)`, `vacate(site_id)` (or the equivalent the
  codebase's idioms suggest — report the exact signatures you ship), and
  `empty_sites_within(structure, origin, radius)`;
- exclusivity enforced: a site holds at most one agent (capacity is pinned at
  1 in M11a; the check reads `occupants < capacity` so M19's capacity knob is
  a parameter change, not a seam migration);
- lives where the dynamics can own it. `Structure` remains a pure value with
  no simulation state inside it — that split is what makes the Phase E
  precomputation possible and is the difference between M19 writing a builder
  and M19 writing an engine. Do not blur it.

In Phase B the occupancy is written once, at founding, and then only read (by
the renderer and the recorder). Births and deaths do not yet touch it —
`vacate()` and the mutation path exist and are tested, but no engine event
calls them until Phase C.

### 2.2 Founding: agents acquire sites at generation 0

When `structure.kind = lattice`, population construction assigns every
founding agent a site. Constraints, all from spec Design 8:

- **Composition is authoritative; layout decides arrangement only.** #67's
  resolved exact integer counts per strategy are the deck; the layout deals
  that deck onto sites. There is no divisibility problem because nothing is
  being divided.
- **Deal order is ascending strategy machine name** — #67's tie-break
  convention, reused so the project has one ordering rule, not two.
- **When N < site count** (possible under the economy and under async
  `variable_n`; impossible under `fixed_n` once Phase C adds its validator):
  `random` scatters over the whole grid; the five patterned layouts use a
  centred contiguous footprint of N sites with the pattern dealt inside it;
  `central_block` is definitionally its own footprint.
- Well-mixed runs do none of this: the well-mixed path must not route
  through structure code at all (spec principle 1).

### 2.3 The seven `initial_layout` values (spec Design 8)

The six algorithmic layouts are one engine — walk the sites in a traversal
order, deal strategies from the resolved counts — differing only in traversal
and dealing discipline. Implement them exactly as Design 8 specifies:

- `stripes` — row-major sweep, run-length dealing; stripe boundaries fall
  where the counts fall (a "stripe" can be a fragment of a row — the help
  text says so).
- `blocks` — run-length dealing along a boustrophedon sweep over sub-blocks;
  no new parameter, degrades gracefully at any count.
- `checkerboard` — round-robin dealing over strategies that still have agents
  left; maximal interleaving is the purpose (the anti-cluster baseline,
  #109), not chessboard appearance.
- `patches` — one RNG-placed seed site per strategy, then multi-source growth
  outward with each strategy's quota as its budget; deterministic given the
  seeds, RNG enters only at seed placement.
- `random` — shuffle the whole deck over the footprint (whole grid, per 2.2).
- `central_block` — a centred rectangle sized to N, the rest empty; the
  filling regime (#109).
- `from_file` — see 2.4.

Layouts must be deterministic functions of (config, seed): identical config
and seed reproduce the identical founding arrangement.

### 2.4 The layout-file mechanism (spec Design 8)

- **Format:** plain text; header lines `kind: lattice_grid`, `rows:`,
  `cols:`; body a character grid, one token per cell — a strategy machine
  name or `.` for an empty site. The `kind:` discriminator ships from day one
  so M19's `site_map` variant is additive.
- **Validators:** header dimensions must match the resolved `structure.rows`
  / `structure.cols`; every non-`.` token must be a registered strategy;
  **reject a layout file combined with a swept composition axis** (a sweep
  varying composition while a file pins every cell is incoherent — error at
  spec validation, not silent override).
- **The file wins on composition.** A layout file names a strategy per cell,
  so its counts *are* the composition; the composition widgets' values are
  superseded (their greying treatment: see 2.5).
- **The recorder copies the layout file into the run folder** — a
  `config.yaml` referencing an external path violates hard rule 8 the moment
  that file moves. The run folder must be self-contained.

### 2.5 Registry additions

Register exactly two parameters, per the spec's Parameters table:

- `structure.initial_layout` — choice of the seven values above, default
  `random`;
- `structure.layout_file` — string, nullable, blank default; meaningful only
  under `initial_layout = from_file` (the same idiom as
  `match.length_mode = continuation` making `continuation_probability` live).

Both carry plain-language, mechanism-explaining descriptions, and **every one
of the seven enum values gets its own individual explanation** (§12 rule —
`stripes`' fragment-of-a-row caveat, `checkerboard`'s
generalise-by-purpose reading, `patches`' RNG-only-at-seeds property, and
`central_block`'s filling-regime purpose all belong in that text). The full
greying map as a predicate table is Phase E; for these two widgets (and the
composition widgets under `from_file`), apply the same interim treatment
Phase A gave the geometry block — inspect what Phase A actually did and match
it, and state in your handback what that treatment was. Rerun
`python -m pdsim.gendocs` and stage the regenerated `docs/PARAMETERS.md` —
the drift test fails while it is stale.

### 2.6 Persistence: site id and schema 5 (spec Design 10)

- `AgentSnapshot` gains `site_id: int | None`. The snapshot is the render
  state.
- **Site id is a single column on `agents.parquet`, present when the run has
  structure and absent otherwise** (#83's honest-presence rule). No sibling
  table, no widened `timeseries.parquet`, nothing NaN-filled.
- The spec flags the one refactor this hides: **`AGENTS_COLUMNS` is
  currently a fixed tuple**, so the writer must vary its column set by run
  type and the loader must stay presence-driven (#100(b)). Budget it as a
  change, not an addition.
- `SCHEMA_VERSION = 5`, written by **any lattice run**. Existing constants
  untouched: well-mixed sync imitation still writes 2, well-mixed sync
  economy 3, well-mixed async 4. The loader accepts 1–5 and rejects above.
  The loader stays presence-driven, not version-driven — a sync-economy
  lattice run writes 5 without event-time files, and #100(b)'s
  missing-file-equals-empty-shape contract already makes that coherent.
- **The sync-imitation + lattice conditional is resolved by VT-2 (section
  3.1).** Implement the persistence of that configuration only after running
  VT-2, per the branch instruction there.

### 2.7 The grid renderer

The renderer lands in this phase, not Phase E, on app-first grounds: there is
no honest way to validate a layout except to look at it. Requirements:

- Renders the lattice with **exactly square cells**, one cell per site, each
  occupied cell coloured by its occupant's strategy (reuse the app's existing
  strategy colour mapping if one exists — report if it does not), empty sites
  visibly empty.
- **Correct at a few hundred cells.** Do not build the pixel-array fallback
  or the ≈3 px size floor — Phase E.
- Reports the **site count** (V1's derived readout). Use the Phase A pure
  resolver (`resolve_lattice_dimensions`, per #112) so the displayed number
  cannot drift from the validator's arithmetic — do not duplicate the
  resolution logic in UI code.
- Reads occupancy via `AgentSnapshot.site_id` where snapshots exist; under
  sync imitation (snapshots empty by design) the live renderer reads the
  in-memory occupancy directly, per Design 10's nothing-to-persist branch.
- Appears when `structure.kind = lattice`; placed per DESIGN §6.3's intent
  and the app's existing layout conventions. Hard rule 4 stands: nothing
  under `pdsim/core/`, `pdsim/config/`, or `pdsim/io/` imports UI code — the
  renderer consumes the event stream / snapshots, never the reverse.

## 3. Verification tasks in this phase

Three tasks. Each produces a finding that must appear in (a) your
end-of-session handback **and** (b) a tracked doc — a `docs/DECISIONS.md`
entry, numbering continuing from the file's current tail (#115 at drafting
time; verify before numbering). WIP.md may duplicate but never solely carry
them.

### 3.1 VT-2 — does synchronous imitation preserve agent ids?

*Question:* under synchronous imitation reproduction, does a `SelectionRule`
replace strategies on the existing agents (ids preserved), or produce a
fresh cohort with new ids?

*Why it matters:* it decides Design 10's persistence branch for
sync-imitation + lattice. **Ids preserved** ⇒ nobody is born or dies,
occupancy never changes after founding, is fully determined by the config,
and re-running reproduces it — **nothing to persist**; the live renderer
holds occupancy in memory. **Ids not preserved** ⇒ occupancy is re-derived
each generation and needs a dense `occupancy.parquet` sibling (period,
agent_id, site_id) on the #100(b) pattern — not a widened `agents.parquet`,
which would NaN-fill energy and age for every imitation run (#47c forbids).

*Instruction, per the spec's phase plan:* the expected answer
(ids preserved — #89(c)'s "an id must mean one creature forever") is already
evidenced. **Verify it against the running code** (inspect the
`SelectionRule` implementations and confirm at runtime — a short scripted
check of id sets across an imitation generation is enough), then **implement
only the nothing-to-persist branch**. If the runtime behaviour diverges from
the evidence, **stop and report rather than switching branches
unilaterally** — the second branch exists in the spec so the situation is
understood, not so you take it alone.

### 3.2 VT-3 — what the async `fixed_n` breeder draw reads

*Question:* does the asynchronous `fixed_n` fitness-proportional breeder
draw read current-period payoff or accumulated energy, and does any
selection-intensity parameter temper it?

*Evidenced expectation (spec, `donation_game_threshold` section):*
accumulated energy through the #63 non-negative shift
(`w_i = e_i − min(e)`), with no intensity knob. Confirm by inspecting the
draw's implementation; report exactly what it reads and whether any
intensity parameter exists anywhere on that path.

*What the answer is for:* the weak-selection caveat wording in the
`donation_game_threshold` scenario text — which is **Phase E**, so this task
changes no shipped text now. Note for your report: DECISIONS #114 has
**softened** the spec's frozen second-order claim ("effective selection
strengthens over time" does not follow from the shift idiom — the spec body
is frozen and stands uncorrected; #114 is the deviation record). Word your
finding in #114's terms, not the spec's.

### 3.3 The #114 measurement — the shifted-weight spread

Assigned to this phase by the spec's post-freeze phase-task ledger. This is
the empirical half of the claim #114 softened: whether the spread of shifted
weights keeps widening super-linearly once divergence is established is an
empirical question, not an arithmetic one.

*Instruction:* instrument a well-mixed async `fixed_n` run (structure is not
read in Phase B, so well-mixed is the right rig) and log the shifted-weight
spread — define spread as `max(e) − min(e)`, i.e. the maximum shifted weight;
also record the standard deviation of the shifted weights for completeness —
at **three points** spaced across the run, chosen after the initial
all-weights-zero phase has passed (at run start every agent holds identical
energy, so the spread begins at exactly zero — #114). Report the three
(elapsed generation-equivalents, spread) pairs and your reading of whether
growth is faster than linear. The instrumentation is temporary — it does not
ship; the numbers go to the design layer via the handback and the DECISIONS
entry, where the calibration guide's wording depends on them.

## 4. Random-number-generator and byte-identity obligations

- **One new draw enters in this phase**, per Design 9's inventory: the
  founding-layout draw — once per run, at population construction, **before
  generation 0**, outside the per-generation order entirely. Gate: lattice
  **and** a layout that actually consumes randomness (`random`'s shuffle;
  `patches`' seed placement). Deterministic layouts (`stripes`, `blocks`,
  `checkerboard`, `central_block`, `from_file`) consume nothing — the
  #80/#99 active-flag idiom: a draw exists only when its governing flag
  makes it meaningful.
- All randomness flows from the single injected `numpy` `Generator` (hard
  rule 5). No unseeded calls anywhere.
- **Well-mixed runs consume zero new draws and produce byte-identical
  output** — events, stream, persisted folders. Run the existing well-mixed
  golden/regression suite (V8) and report the result explicitly.
- A cheap invariant worth pinning because it operationalises the exit
  condition: a lattice run with a **deterministic** layout differs from the
  same-seed well-mixed run only in its persisted site ids and schema
  version — the event stream is identical, because nothing reads structure
  yet and no draw was consumed. A lattice run with `random` layout consumes
  exactly one founding shuffle and nothing else new.

## 5. Tests

pytest, accompanying the features (hard rule 7). Cover at least:

- **Occupancy:** mutual consistency of the two mappings; exclusivity
  (occupying an occupied site is an error); `vacate` round-trip;
  `empty_sites_within` against a hand-computed fixture.
- **Layouts:** for each of the six algorithmic layouts — counts conserved
  exactly (the dealt deck equals the #67-resolved composition); deal order
  ascending machine name; determinism under a fixed seed; the two-equal-
  strategies checkerboard reproduces the literal checkerboard; `stripes`
  run-lengths equal the counts; `central_block` footprint is the centred
  rectangle; footprint rules when N < site count (scatter for `random`,
  centred contiguous block for the patterned five).
- **Layout file:** parse round-trip; each validator rejects what it should
  (dimension mismatch, unregistered token, file + swept composition axis);
  the recorder copies the file into the run folder.
- **Persistence:** `site_id` column present on lattice runs, absent on
  well-mixed (honest presence); schema constant 5 written by a lattice run,
  existing constants untouched; loader accepts 1–5, rejects 6; loader
  round-trip on a lattice economy run.
- **Byte-identity:** the existing well-mixed suite green and byte-identical;
  the deterministic-layout invariant from section 4 if cheap to pin.

Renderer correctness is validated by eye in the app (section 6) — do not
attempt to screenshot-test it.

## 6. App-first validation — what the owner will do

With the venv active (`.venv\Scripts\Activate.ps1`), launch
`streamlit run pdsim/ui/app.py`. Give the owner these steps, refined to match
the widgets you actually shipped:

- **V1 — structure exists and is visible.** Set `structure.kind = lattice`
  with a population around 400 (auto-resolves 20×20); run; the grid renders,
  cells are exactly square, and the site count readout shows 400.
- **V2 — layouts.** With two strategies at equal counts, walk
  `structure.initial_layout` through all seven values and *see* each
  arrangement: literal checkerboard under `checkerboard`; contiguous runs
  under `stripes` and `blocks`; irregular clusters under `patches`; scatter
  under `random`; a centred filled rectangle with an empty frame under
  `central_block`; and a hand-written small layout file rendered exactly as
  authored under `from_file`.
- A behavioural non-event worth stating to the owner: charts and outcomes
  are unchanged from well-mixed — nothing reads the structure yet, and that
  is this phase's exit condition, not a defect.

## 7. Docs obligations

- **DECISIONS entries** (append-only, numbering from the current tail):
  VT-2's confirmed answer and the branch implemented; VT-3's confirmed
  answer worded per #114; the #114 measurement's three data points and
  reading; and any deviation from the spec this session required, each with
  rationale and alternatives. One consolidated Phase B entry or several — 
  your judgment — but every finding must land in the file.
- **Spec status line only**: update to record Phase B implemented with the
  new DECISIONS numbers. No other spec edit of any kind.
- **`docs/PARAMETERS.md`** regenerated via `python -m pdsim.gendocs` and
  staged.
- **`CLAUDE.md` "Current phase"** updated: Phase B landed, next up Phase C
  (local birth — the riskiest phase, per the spec's risk reading).
- **`docs/DESIGN.md`**: update only if a designed interface changed or a new
  mechanism is absent from it (CLAUDE.md's triggers); report either way.

## 8. End of session

Phase B ends at a scheduled ▲ reset. In order:

1. Re-check CLAUDE.md's doc-update triggers; make any missing updates now.
2. **Write `docs/WIP.md` as the phase-boundary baton**: phase state,
   staged-awaiting-commit status, and Phase C's entry point — including the
   tasks Phase C carries (VT-4; the stake-plus-overhead validation fix from
   the phase-task ledger; the blocked-parents Economy-panel readout; the
   Design 9 RNG amendments and golden masters). WIP.md duplicates tracked
   docs; it carries nothing solely.
3. **Present the commit handoff** — you never commit: (a) a summary of what
   was done, (b) the exact file list to stage (never including WIP.md),
   (c) a suggested commit message.
4. **Report** `DOCS CHANGED: [files]` (or `DOCS UNCHANGED`), calling out the
   new DECISIONS entry numbers so the design layer can spot the delta.
5. Include in the handback: the VT-2 and VT-3 answers, the #114 measurement
   numbers, the V8 byte-identity result, what interim greying treatment you
   matched, and the exact `Occupancy` signatures shipped.

Action required: implement M11a Phase B exactly as specified above — Occupancy, founding via all seven layouts plus the layout file, the two registry entries with regenerated PARAMETERS.md, site-id persistence with schema 5, and the grid renderer; run VT-2, VT-3, and the #114 measurement and record their findings in DECISIONS; verify well-mixed byte-identity; then stop at the phase boundary with the WIP.md baton, the commit handoff, and the DOCS CHANGED report — and do not commit.
