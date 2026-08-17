# M11b — Agent movement, encounter mode, calibration + advisories, and the parameter-panel redesign

**Status: frozen** (created 2026-08-17, Phase 0). This spec is a frozen
historical record (#62): deviations during implementation become new
DECISIONS entries, never retro-edits of this file beyond this status line.

## Purpose

M11b completes the M11 population-structure milestone (#103 split): agents
gain the ability to relocate; the encounter-doubling artifact gains a
switch; the Economy calibration learns the asynchronous clock; the advisory
mechanism ships with A1–A3; and the parameter panel is redesigned per the
tabs decision (#158) plus the disclosure and live-run rulings of this
milestone's design session. The #159 admission-quota question is resolved
here, explicitly before M12, as #159 requires.

## Design rulings

All rulings made 2026-08-17 in the M11b design session; full rationale and
alternatives live in DECISIONS #164–#170. Summary, binding on every phase:

1. **Feasibility-aware admission (#164, resolves #159).** The synchronous
   economy's capacity gate admits only parents with at least one empty site
   within birth reach. Hardwired — no compatibility parameter. A #80/#99
   breaking change: the affected sync-lattice positive goldens are
   re-recorded ONCE, in Phase A, under Phase A's DECISIONS entry, with the
   full #133(d) technique. That is the milestone's entire re-recording
   budget; every later phase holds zero re-recordings.
2. **Movement schedule (#165, resolves the #103 open item).** Async:
   movement is a step INSIDE the focal activation, never a new event type —
   the one-event-one-activation correspondence and Δt = 1/N(t) are
   untouched. Sync: movement is the FINAL step of the demographic boundary,
   after deaths and births. Both clocks: move-then-play — matches are
   always played from post-movement positions; generation 0's matches are
   played from the founding layout as dealt or painted; newborns are
   eligible to move in the same boundary, one uniform rule. Movement
   contention is resolved by one permutation over the movers (#107/#133
   pattern), never by wealth.
3. **Movement parameters (#165).** `movement.rate` (per-agent per-period
   move probability, default 0), `movement.radius`, `movement.decay` (the
   third reach-kernel pair, #105). All movement draws are gated on
   rate > 0 (#80/#99 active-flag idiom): a movement-off config consumes
   zero additional random draws, so every pre-existing golden — including
   Phase A's fresh ones — passes untouched. A move attempt with no empty
   site in walk reach fails in place and is counted (blocked moves).
   Movement energy cost is a NAMED FUTURE OPTION, out of scope (below).
4. **`matching.encounter_mode`** ∈ {`per_initiator`, `per_pair`}, default
   `per_initiator` (#166). Spatial-only: live only while
   `matching.spatial_interaction` is on; the well-mixed matchers are
   untouched (future extension recorded). Implementation contract: partner
   draws are made exactly as today — identical random-number consumption —
   and deduplication is applied to the resulting pair list before matches
   are played; the knob changes which matches run, never how randomness is
   consumed, so the default is byte-identical trivially. Greyed under the
   asynchronous clock, with a greying-table entry and help text (async is
   per-initiator by construction).
5. **Disclosure (#167, completes #158).** Registry entries gain a boolean
   `advanced` flag (single source of truth, hard rule 3). The panel
   renders each section's advanced parameters inside a labelled,
   collapsed-but-present expander. Grey-never-hide holds inside the
   expander. Orthogonal to the mode tabs. Flagging criterion: the default
   is the canonical choice AND changing it presupposes a mechanism the
   novice tooltips don't assume. Candidate initial list (owner confirms at
   the Phase E2 prompt): `birth_decay`, `interaction_decay`,
   `movement.decay`, `dynamics.boundary_order`,
   `structure.placement_contest`, `matching.encounter_mode`,
   `match.continuation_probability`, the selection-rule internals.
6. **Live-run display continuity (#168).** The four display toggles
   (update granularity, playback delay, score view, time scope) become
   changeable mid-run without stopping the run: the run loop is
   restructured so engine state survives in session memory and each script
   pass advances the engine, repaints with current toggle values, and
   schedules the next pass. Display-side only — no engine, registry, or
   draw changes. Implementation must REPORT (Rule 7) which toggles govern
   paint cadence versus recording resolution; the granularity toggle's
   mid-run wording is the owner's call on that report.
7. **Async calibration (#169, resolves the #154 held question).** The
   Economy panel's spatial branch extends to the asynchronous clock, GATED
   on Phase D's measurement confirming matches per agent per
   generation-equivalent ≈ 2 × min(k, degree) within sampling noise. On
   confirmation the #154 pin is retired with a replacement pin; on
   disagreement, report and hold.
8. **A2 amended (#170).** Triggers gain `matching.spatial_interaction`,
   `matching.encounter_mode`, `matching.interaction_radius`; explicitly
   exclude `movement.rate` and `interaction_decay`. (Executed in Phase 0.)

## New parameters (registered in their owning phases)

| Key | Phase | Default | Notes |
|---|---|---|---|
| `movement.rate` | B | 0 | per-agent per-period probability |
| `movement.radius` | B | (spec'd at Phase B, kernel pair) | walk support radius |
| `movement.decay` | B | (spec'd at Phase B, kernel pair) | walk decay β |
| `matching.encounter_mode` | C | `per_initiator` | spatial-only; greys under async |

Plus the registry `advanced` metadata flag (Phase E2) — a registry FIELD,
not a parameter.

## Phase plan

One phase per fresh conversation (▲ reset at each boundary); one commit per
phase after design-layer GO; each phase's prompt arrives from the design
layer.

- **Phase A — feasibility-aware admission.** Implement #164 in the
  synchronous economy's birth step, gated lattice-active so well-mixed
  runs stay byte-identical. Redefine the blocked-parents metric (blocked =
  lost to placement contention only) and add an infeasible-parents count,
  with help text updated (#133(c) single-source discipline). Re-run
  `the_filling_grid` headlessly on its shipped seed, observe the endgame,
  and rewrite the scenario's description and things-to-try to what is
  actually observed (arithmetic, not predictions, #152). Re-record the
  affected sync-lattice positive goldens under this phase's DECISIONS
  entry with the full #133(d) technique; all negatives and async goldens
  must pass unchanged. DESIGN §2.12's birth-step text amended.
- **Phase B — movement.** `pdsim` gains the `MovementRule` abstract base
  class (#46) with one implementation: the kernel-weighted random walk
  over `movement.radius`/`movement.decay`, consuming the #156 cached
  reach. Registry entries per the table; sync boundary's final step with
  the mover permutation; async in-activation step; blocked-moves counting
  and readout; draw-gating per ruling 3 with counting-wrapper no-draw pins
  proving movement-off consumes zero draws. New positive golden(s) for a
  movement-on configuration, recorded (not re-recorded) under this phase's
  entry. DESIGN §2.12 gains the movement mechanism.
- **Phase C — `encounter_mode`.** Registry entry, pair-list deduplication
  after draws, the async greying-table entry and help text, tests pinning
  default byte-identity and per_pair's halved match counts. The bench
  gains a `per_pair` column beside the #156 structure grid — the first
  real test of #156's held hypothesis (re-met pairs' history copies as the
  Moore cost excess); report the measured verdict honestly, tune nothing.
- **Phase D — calibration + advisories.** (1) The measurement task:
  instrument an asynchronous spatial run and count matches per agent per
  generation-equivalent; compare to 2 × min(k, degree); report. (2) On
  confirmation, extend `spatial_calibration_active` / the spatial branch
  to the async clock, retire the #154 pin with a replacement, and mark the
  async figure "expected" in the fine print. (3) Implement the advisory
  mechanism as a predicate table (ADVISORIES.md pattern) and ship A1–A3 as
  callers of `spatial_income_arithmetic`, which gains the encounter-mode
  branch (2× vs 1×); A3's message is mode-conditional.
- **Phase E — the user-interface batch**, as sub-prompts:
  - **E1** — the #158 tab split (evolution | tournament) and
    collapse-with-summary, built as a second renderer over the #141
    `STRUCTURE_GREYING` predicate table.
  - **E2** — the `advanced` registry flag and the per-section advanced
    expander; the owner confirms the flag list in the E2 prompt.
  - **E3** — live-run display continuity per ruling 6, including the
    Rule 7 toggle-classification report.
  - **E4** — the mouse layout painter: a UI tool that WRITES #109 layout
    files which configs reference; the engine only ever reads data
    (rules 4 and 8). Validated paint → save → load → run → re-run
    identical.
  - **E5** — close-out: the movement validation scenario
    `the_restless_frontier` (clustered `patches` founding whose clusters
    visibly erode as `movement.rate` rises — movement as a measured
    mixing dial against M11a's natal-locality baseline; exact
    configuration and worked arithmetic finalised in the E5 prompt per
    #36/#151 conventions), the docs-obligations sweep, ROADMAP/CLAUDE.md
    close-out, and the completion DECISIONS entry.

## Golden-master strategy

Phase A holds the milestone's ONLY re-recording, logged in its own entry.
Phase B adds new movement-on positives and no-draw pins. Phases C–E:
zero re-recordings, zero new goldens except where a phase's entry records
otherwise. Any collision outside this budget is a Rule 7 stop.

## Bench

Phase C's `per_pair` column is this milestone's standing-priority
performance examination (#156's actionable lever). Output stays
environment-specific and uncommitted; numbers live in the DECISIONS entry
and handback.

## Validation (written at spec time; app-first, #42/#61)

- **V1 (A):** load `the_filling_grid`, run. Expect: the ~265-of-400
  permanent freeze does not persist; "Blocked parents" no longer equals
  site count − population persistently; the new infeasible-parents readout
  is visible with a (?). The observed endgame is what the rewritten text
  states.
- **V2 (B):** load `spatial_reciprocity`, set `movement.rate` to 0.5,
  run. Expect: clusters visibly erode/drift relative to the rate-0
  baseline; blocked-moves readout visible. At rate 0, confirm a re-run of
  the unmodified flagship is unchanged.
- **V3 (C):** flagship, switch `encounter_mode` to `per_pair`. Expect:
  Economy calibration shows 4 matches (was 8) and halved incomes. Switch
  the clock to asynchronous: the widget greys with the explanatory (?).
- **V4 (D):** flagship — set living cost to 0: A1 caution appears; set it
  at/above all-C income: A1 caution. Change `interaction_radius`: A2
  inline caution at the widget. With k ≥ degree: A3 info beside the
  spatial toggle. Load `donation_game_threshold` (asynchronous): its
  Economy readout now shows the expected 2 × 4 = 8 matches, not
  N − 1 = 99. The measurement task itself is inherently headless (CLI
  acceptable).
- **V5 (E):** E1 — two mode tabs; tournament tab carries no structure/
  dynamics/demography (total-fork, #158); inert sections collapse with
  summaries. E2 — advanced expanders collapsed by default, open on click,
  greying live inside. E3 — start a run, flip time scope and score view
  mid-run: the run continues and the chart re-renders; flip granularity
  and observe the behaviour the E3 report established. E4 — paint a
  layout, save, run a config referencing it, confirm the painted
  arrangement founds the run and a re-run is identical. E5 — load
  `the_restless_frontier` and confirm its description's arithmetic
  against the observed run.

## Out of scope

- **Movement energy cost** — named future option (#165): a ledger charge
  per move; adds a calibration surface A1/A2 must learn; deliberately not
  in M11b.
- **`encounter_mode` for well-mixed matchers** — future extension (#166).
- **`admission_ranking` ∈ {wealth, random}** — M12 scoping's question,
  handed off by #164 (Hammond–Axelrod's reproduction order is random;
  wealth still ranks feasible parents at tight K).
- **Success-driven / walk-away movement rules** — future `MovementRule`
  implementations.
- **The M11b explainer** — separate effort behind a design-layer
  literature verification pass (movement/migration literature verified in
  the design chat before any explainer content is drafted).
- **Everything M19** (irregular sites, capacity > 1, co-residency, maps).

## Docs obligations

Numbering continues from #170. Per phase: the build decisions and any
deviations as new DECISIONS entries; DESIGN §2.12 amendments (A: admission;
B: movement) in the same session as the code; `python -m pdsim.gendocs`
after every registry change; ROADMAP M11b status lines at each phase
landing; the E5 close-out entry, docs sweep, and CLAUDE.md update.
ADVISORIES.md was amended in Phase 0 (#170) and needs no further edit
unless Phase D's implementation forces one (Rule 7 if so).
