# ROADMAP.md

## Renumbering note (2026-07-16, DECISIONS #76)

The v2 milestone labels were renumbered when M10a landed so that **execution
order = numeric order, with no gaps**. The old #58/#75 "M12 deliberately
before M11" swap dissolves — the numbers now simply match the order. Tags
keeps its M12 label (sparing cross-reference churn); two new milestones
(population structure, economy policy) join the spine; the sweep browser and
the vectorized engine get numbers.

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

References to milestone numbers in DECISIONS entries #1-#75 use the OLD
labels; from #76 on, the NEW labels.

## v1 — Pairwise evolutionary PD with live web UI

Milestone order (each lands with tests + docs):

1. **Skeleton + registry.** Repo scaffold, `pyproject.toml`, ruff, pytest;
   Parameter Registry; `ExperimentConfig` (pydantic) + YAML load/save.
   ✅ M1 landed 2026-07-03, 38 tests passing.
2. **Core game loop.** `Game` ABC + PrisonersDilemma (payoff validation toggles);
   `Strategy` ABC + history views; Agent; Match (fixed rounds + continuation-prob w;
   execution noise ε); RoundRobin matcher.
   ✅ M2 landed 2026-07-03, 70 tests passing.
3. **Strategy roster.** The seven v1 strategies with decision-table tests and
   `axelrod` cross-validation.
   ✅ M3 landed 2026-07-04, 200 tests passing.
4. **Evolutionary dynamics.** Synchronous generations; Fermi selection (β);
   strategy-switch mutation (μ); seeded RNG discipline; golden validation tests.
   ✅ M4 landed 2026-07-04, 237 tests passing.
5. **GUI foundations** (rescoped — see DECISIONS #33). Run modes
   (evolution/tournament); typed event stream with observer-side granularity;
   Scenario Registry with five curated presets.
   ✅ M5 landed 2026-07-04, 270 tests passing.
6. **Streamlit UI.** Scenario dropdown (registry-driven); registry-generated
   parameter panel with novice tooltips; mode-aware charts (stacked-area
   composition + score trajectories in evolution; cumulative standings in
   tournament) with ignored-parameter greying; live updates with granularity
   (round/match/generation) + playback speed; run launcher. No results browser
   yet.
   ✅ M6 landed 2026-07-04, 303 tests passing.
7. **Persistence + CLI.** Run folders (config + seed + parquet + summary);
   runs index; headless CLI (`python -m pdsim.run`); results browser in the UI.
   ✅ M7 landed 2026-07-06, 347 tests passing.
8. **Polish.** `docs/PARAMETERS.md` generation; README quick start; RandomK matcher
   if not already landed.
   ✅ M8 landed 2026-07-07, 382 tests passing — **v1 complete**: PARAMETERS.md
   is a committed generated artifact with a drift test (`python -m
   pdsim.gendocs`, DECISIONS #56); RandomK shipped (DECISIONS #57).

Out of scope for v1 (but nothing may block them): everything below.

## v2 — Economy-first: growth, structure, tags, group games

Milestone spine (renumbered in DECISIONS #76; economy-first rationale in
#58/#75; M19 appended 2026-07-28 — purely additive, no renumbering, #103):
**M9 → M9.5 → M10 → M11 → M12 → M13 → M14 → M15 → M16 → M17 → M18 → M19.**
M10's variable-N invariant is the spine's load-bearing change — every
downstream milestone is built variable-N-aware from birth. Population
structure (M11) runs before the sweep browser (M13) by #75's own logic:
the browser is a read-only view over run data, and structure changes what
run data exists.

**Standing priority (owner decision 2026-08-13): performance
opportunities are examined at EVERY milestone's scoping** from here on,
and the M18 vectorization review-at can be pulled forward the moment
slowness genuinely blocks the owner's experiments — large-N runs already
strain the app. The bench (#58/#91/#102/#156) supplies the data.

- **M9 — Selection rules, score accounting, cooperation recording.**
  ✅ M9a landed 2026-07-08: four selection rules (DECISIONS #63), the
  ScoreAccounting seam (#64), and the benchmark rider (`python -m
  pdsim.bench`) — spec `docs/specs/M09a-selection-accounting-bench.md`;
  440 tests passing.
  ✅ M9b landed 2026-07-09 — **M9 complete**: pairwise cooperation-rate
  recording at strategy-pair resolution, cooperation chart + pair-matrix
  table, `cooperation.parquet`, schema_version 2 (DECISIONS #65; spec
  `docs/specs/M09b-cooperation-recording.md`); 457 tests passing.
- **M9.5 — Sweep/search layer** (DECISIONS #59).
  ✅ M9.5a (headless core) landed 2026-07-11: `pdsim/sweep/` (SweepSpec +
  three-bucket composition + Outcome Metrics Registry + parallel runner
  with resume and failure isolation), `python -m pdsim.sweep`, and the
  metric-vs-axis chart builder — spec `docs/specs/M09c-sweep-layer.md`,
  explainer `docs/explainers/M9.5-sweeps-and-invasion.md` (DECISIONS
  #66-#71); 509 tests passing.
  ✅ M9.5b (Sweep tab) landed 2026-07-13 — **M9.5 complete**: a third
  Streamlit tab authors, validates, launches (detached headless CLI), and
  monitors sweeps — spec `docs/specs/M09d-sweep-tab.md` (DECISIONS
  #72-#74); 555 tests passing.
- **M10 — Score-as-energy growth economy.**
  ✅ M10a (synchronous generational) landed 2026-07-16 (DECISIONS
  #76-#84; spec `docs/specs/M10a-growth-economy.md`, explainer
  `docs/explainers/M10-growth-economy-explainer.md`; DESIGN §2.10): the
  `energy_economy` reproduction mode — energy ledger (living cost,
  engagement cost, capital returns), stake-transfer reproduction, the
  mortality trio with staggered founders, carrying capacity with
  deterministic admission, passport-id lineage, variable N with the
  `random_k` clamp, extinction as a run ending, per-agent snapshots +
  `agents.parquet` (schema_version 3), the Economy calibration panel,
  three economy charts, and the `the_growth_economy` scenario; 645 tests
  passing.
  ✅ M10b landed 2026-07-20 (DECISIONS #93-#102) — the asynchronous /
  Moran-style event time-model: `time_model` clock choice, the focal-
  bundle event loop with the 1/N(t) generation-equivalent clock, both
  demographic engines (`variable_n` economy-in-event-time, `fixed_n`
  Moran with BD/DB/random rules), the symmetric imitation overlay,
  explicit birth/death/imitation events, recording cadence (Output
  section), schema 4 persistence, event-time chart axis, greying map,
  four validation scenarios, async bench column; 722 tests passing.
- **M11 — Population structure.** Chat-designed 2026-07-28 (hard rule 6:
  DESIGN §2.12 before code; DECISIONS #103-#110). Splits into M11a/M11b
  (#103) so natal locality gets a clean baseline before movement, and each
  change gets its own goldens.
  - **M11a — Structure, local birth, local interaction.** The
    graph-of-sites abstraction with the rectangular lattice as its first
    builder (`structure.kind`, rows/cols with a most-square derived
    default, `moore`/`von_neumann` neighbourhoods as distance metrics,
    `torus`/`bounded` boundaries, #104); the soft reach kernel (support
    radius R + decay β, #105) parameterised separately for birth and
    interaction; carrying capacity as a second cap with a site-count
    derived default (#106); placement contention + `boundary_order`
    (#107, amending #80); the `matching.spatial_interaction` toggle over
    the `neighbourhood_sample` primitive with the `SpatialKernel` sync
    adapter (#108); six initial layouts + the layout-file mechanism
    (#109); the square-cell rendering contract with pixel-array fallback
    (#109). The M10a `place_offspring` gate (the well-mixed always-True
    corner) becomes the local placement seam. Spec arrives as a separate
    prompt and must satisfy the §2.12 inline-(?) checklist obligation.

    Phase status: **A landed 2026-08-01** (#112 — the structure module,
    wired to nothing). **B landed 2026-08-03** (#116-#120 — occupancy,
    the seven founding layouts plus the layout file, schema 5's `site_id`
    column, the grid renderer; VT-2 and VT-3 answered, and #114's
    shifted-weight spread measured and found to PLATEAU rather than grow;
    follow-ups #121-#126). **C — local birth — landed 2026-08-06**
    (#127-#136): occupancy live in all three engines (death frees a
    site, birth occupies one, newborn `site_id` real from birth), the
    amended #80 birth step (contest permutation, kernel placement,
    place-before-pay live, blocked parents counted and shown live),
    `birth_radius`/`birth_decay`/`placement_contest`/`boundary_order`,
    K's site-count derived default with the K-family validators, the
    stake+overhead fix (#129), the localised `fixed_n` draws with the
    R = 1 Ohtsuki reduction (#132), VT-4 runtime-confirmed (#130), four
    negative + three positive golden masters with the counting-wrapper
    no-draw pins (#133; the fourth positive golden moved to Phase D,
    #128); 950 tests passing. **D — local interaction — landed
    2026-08-06** (#137-#140): `matching.spatial_interaction` +
    `interaction_radius`/`interaction_decay`; the `SpatialKernel`
    synchronous adapter and the async partner-draw substitution, both
    gated on lattice + toggle, both through the one Phase A primitive;
    the draw-unconditionally/empty-eligible RNG contract with new
    no-call pins; the requires-lattice validator; the matcher.py
    docstring correction; the fourth positive golden recorded (#128
    discharged, #138); VT-6(b) answered EXACTLY 8 matches per agent per
    generation (#139); V6 run by manual configuration — no visible
    b/c > k separation at strong selection, reported honestly to the
    design layer (#140); 977 tests passing, zero golden re-recordings.
    **E — polish — landed 2026-08-07 through 2026-08-14 as five
    sub-prompts**: E1 (#141-#144) — the `STRUCTURE_GREYING` predicate
    table consumed by both clock branches (tournament wholesale-grey,
    `spatial_interaction` greyed under well_mixed, composition greyed
    under `from_file`) and the first §12 paint-time readouts; E2
    (#145-#149) — the pixel-array rendering fallback with the ≈ 3 px
    cell floor in the one `grid_chart` path, the ninth §12 readout,
    the results browser's Founding | Final selector, the golden suite
    renamed `test_golden_masters.py`; E2b (#150) — the #127
    sparse-`stripes` band with the milestone's only (logged, confined)
    golden re-record; E3 (#151-#153) — the four registered scenarios
    (`spatial_reciprocity`, `donation_game_threshold`,
    `the_drifting_frontier`, `the_filling_grid`) and the E3 findings
    reported and held; E4a (#154-#155) — the Economy panel's spatial
    calibration branch and the Filling Grid's rise-then-freeze truth;
    E4b (#156-#160) — reach-kernel precomputation in the engine
    (draw-neutral, pinned three ways), the bench's five-column
    structure grid with both hypothesis verdicts, the 54-item §12
    audit (54/54 covered, one text fix), the tabs decision (#158),
    the admission-quota open question (#159), and the close-out
    (#160). **M11a complete 2026-08-14, 1059 tests passing.** The
    literature verification pass landed 2026-08-14 (all four gates
    verified true, DECISIONS #161) and the M11a explainer shipped
    2026-08-16 as `docs/explainers/M11a-population-structure-explainer.md`.

    Calibration-guide residue (DECISIONS #113–#115) folded into the
    remaining phases: Phase B measures the #114 shifted-weight spread;
    Phase C carries the ADVISORIES.md stake+overhead validation fix; Phase
    D answers VT-6(b), whose report may force design-layer corrections to
    the flagship's living cost and the guide's §4.2. Details in the spec's
    post-freeze phase-task ledger.
  - **M11b — Agent movement + layout painter.** The `MovementRule` ABC
    (#46) with its own walk radius/decay pair over the same reach kernel,
    on a configurable schedule — the schedule is the genuinely open
    design item: under async it either becomes a new event type or a step
    inside the focal activation (#103); plus the mouse layout painter
    that writes the layout files M11a's configs reference (#109).
    Movement stays population dynamics, orthogonal to strategies (#46).

    **New parameter: `matching.encounter_mode`** ∈ {`per_initiator`,
    `per_pair`}, default `per_initiator` (today's behaviour). Under the
    current no-deduplication rule inherited from `RandomK`, an unordered
    pair of neighbours meets **twice** per period, because each of the two
    independently initiates a match. That is an artefact of indexing
    matches by initiator, not a modelling claim: an encounter is an event
    that happens to a *pair*. `per_pair` deduplicates. Note that two
    matches of R rounds is not equivalent to one match of 2R rounds —
    reciprocal strategies reopen at each match boundary, and under
    continuation mode the length is drawn per match. Deferred from M11a
    deliberately: the M11a spec is frozen and Phase A is committed, and
    changing pairing semantics would alter RNG consumption and invalidate
    the golden masters Phase C depends on. Requires its own spec and a
    DECISIONS entry when picked up.

    **Advisory mechanism + advisories A1, A2, A3** (`docs/ADVISORIES.md`)
    — warning-shaped derived readouts on the same predicate-table pattern
    as the greying map. Owned here rather than earlier because where a
    warning appears is a disclosure question, so the rules and the
    parameter-panel redesign are designed together. While the panel is
    open: the asynchronous clock's Economy calibration readout still
    reports the unconsulted matcher's arithmetic (pre-existing, held
    and pinned in #154) — a candidate to fix alongside A1/A2.

    **User-interface simplification** (per the tabs decision, #158):
    the `run.mode` tab split — evolution and tournament as separate
    tabs, the one fork that passes the total-fork criterion —
    collapse-with-summary for inert sections, and novice/advanced
    disclosure taken up as its own orthogonal decision; built as a
    second renderer over the #141 `STRUCTURE_GREYING` predicate table
    (the enabling piece that already shipped).

    **Resolve the admission-quota open question (#159)** — whether the
    carrying capacity's birth quota is consumed by ADMISSION (today's
    behaviour: a wealth-ranked parent that fails local placement still
    spends a slot) or by SUCCESSFUL PLACEMENT (unfilled quota rolls to
    the next-richest eligible parent). M11b at the latest, EXPLICITLY
    BEFORE M12: the Hammond–Axelrod frontier replication runs at
    K = site count with rich interior incumbents and poor frontier
    parents, precisely the configuration #153(c)'s freeze starves. Any
    change alters RNG consumption (#80/#99) and needs its own golden
    masters.

    **Spec frozen 2026-08-17**
    (`docs/specs/M11b-movement-and-panel-spec.md`; design rulings
    DECISIONS #164–#170 — the #103 movement-schedule question and #159
    are RESOLVED; phases A–E per the spec).

    ✅ **M11b Phase A landed 2026-08-17** (DECISIONS #171): feasibility-aware
    admission in the synchronous lattice economy (`feasible_parents`, a
    zero-draw occupancy read in front of `admit_births`; the contest
    permutation mechanically untouched); the blocked/infeasible metric
    split (`infeasible_parents` LIVE-only beside `blocked_parents`, the
    Economy panel's second metric, both (?) texts clock-aware; async
    byte-untouched — ruling R1, its vocabulary a named future option;
    ruling R2's absolute infeasible count); the milestone's re-recording
    budget UNUSED — the `sync_economy_lattice` golden never admits an
    infeasible parent (demonstrated and pinned), so nothing was re-recorded
    and no pinned field list was extended; `the_filling_grid` re-run
    headlessly and its text rewritten to the observed post-#164
    trajectory; DESIGN §2.12 amended. Two Rule 7 findings held for the
    design layer: async admits a whole eligible SET per event (DESIGN's
    "one birth per event" is not what the engine does), and the golden
    file has ONE `GenerationFinished` field list for both clocks (no
    per-clock list to extend). 1073 tests passing.

    ✅ **M11b Phase B landed 2026-08-18** (DECISIONS #172): agent movement —
    `pdsim/core/movement.py` (the `MovementRule` ABC, the `KernelWalk`
    over the third reach-kernel pair `movement.radius`/`movement.decay`,
    `attempt_move` with vacate-after-draw, the one `movement_active`
    gate); the `Movement` registry section (`movement.rate` default 0 =
    off; old configs re-run identically) with its greying-table rows;
    the sync boundary's FINAL movement step (coins in ascending id →
    ONE mover permutation → walk draws, newborns eligible) and the async
    in-activation step (coin after the focal draw, move-then-play, no
    new event type); the gate lattice + energy economy (sync
    `energy_economy`, async `variable_n`; `fixed_n` excluded — full
    grid); the LIVE-only `blocked_moves` channel with the app's third
    metric; TWO movement-on goldens RECORDED (`sync_economy_lattice_movement`,
    `async_variable_n_lattice_movement`, rate 0.5) with all eight
    pre-existing pins and every counting pin untouched — zero
    re-recording; the `placement_contest` reword to the #171(f2) fact
    (registry + greying note); DESIGN §2.12 movement passage and §6.3
    rewritten to the resolved schedule. Six Rule 7 findings ruled
    in-session (the sync golden cannot produce a blocked move at any
    rate — recorded honestly with 0; the garbled permutation sentence
    read as "call iff ≥ 1 coin drawn"; module in `core/`; N = 1 async
    draws no coin; the greying note reworded; a pre-existing
    `widget_values_from_config` gap over `config.output` logged for
    E1). 1129 tests passing.
- **M12 — Agent attributes + attribute-conditional strategies.** Generic
  attributes mapping with visibility and inheritance policies; strategies
  conditioning on an opponent's visible tags (Riolo tags; Hammond &
  Axelrod ethnocentrism — richer with the v3 spatial layer). Built
  variable-N-aware on top of M10. See DESIGN §6.5, DECISIONS #46/#58.
  Plus **advisories A4 and A5** (`docs/ADVISORIES.md`): the birth-death
  cooperation warning and the payoff-scale/selection-intensity warning.
- **Imitation adopter rule — asymmetric "imitate-better" option
  (review-at M12).** The imitation mechanism currently uses the symmetric
  adopter rule in both time models (a random adopter of the pair; β = 0 is
  neutral drift; DECISIONS #93). The asymmetric "imitate-better" variant —
  the lower-scorer always the adopter, every copy uphill — is a genuine
  studied dynamic, to be exposed later as a labeled option
  (dynamics.imitation_adopter ∈ {symmetric, imitate_better}, default
  symmetric) governing both modes. Deferred out of M10b because it also
  touches the stable sync selection path. The checkpoint was EXAMINED at
  M11 scoping (2026-07-28) and NOT triggered: Ohtsuki's imitation
  updating chooses the reassessing individual at random, independently of
  payoff — an endorsement of the shipped symmetric rule, not a reason to
  fork (DECISIONS #110). It rolls to M12 scoping as originally written:
  ethnocentrism spreads strategies between in-group and out-group, where
  symmetric vs imitate-better can differ, so examine there whether M12
  needs the option as a comparison (full rationale: DECISIONS #93). Not
  triggered ⇒ roll the checkpoint to the next imitation-touching
  milestone.
- **Neighbourhood-proportional imitation (backlog, #110).** Ohtsuki's
  imitation updating picks a model proportionally over the whole
  neighbourhood, self included; our overlay is a pairwise Fermi
  comparison after a match. Reproducing the b/c > k + 2 imitation
  threshold exactly would require this as a NEW mechanism — declined for
  M11a explicitly on scope grounds (the death-birth threshold b/c > k is
  the one testable with what we have).
- **Weak-selection mode for the `fixed_n` reproduction lottery (backlog,
  owner-requested 2026-08-13; examine at M12 scoping).** An explicit
  selection-intensity dial (tickets = equal base + dial × fitness) plus
  fitness read as RECENT income rather than accumulated lifetime energy
  — the two ingredients needed to approach the weak-selection limit in
  which the b/c > k threshold is derived. Motivation: #140's
  no-visible-reversal finding (this engine's selection is far from that
  limit); reproduction dynamics reopen at M12 anyway.
- **M13 — Sweep browser.** Member-run drilldown from a sweep's summary,
  multi-sweep interactive browsing, multi-curve overlays, summary-table
  filtering, side-by-side member comparison — the affordances deferred out
  of M9.5b (#74), designed from real invasion-campaign evidence and
  structure-aware from birth (#75, #76).
- **M14 — Parameter-perturbation mutation.** Gaussian noise on continuous
  strategy parameters → genuine strategy evolution, plus the
  variant-identity machinery it requires (resolves the #30 deferral).
- **M15 — Economy policy (NEW).** Taxation, redistribution, immigration,
  and inheritance policies over the M10 energy substrate (today's corner:
  estates are destroyed on death — the 100% inheritance tax).
- **M16 — Public Goods Game + variants:** threshold/step-level, volunteer's
  dilemma, n-player snowdrift; group-size parameter; group matching.
- **M17 — Reciprocity machinery for group games:** public reputation,
  targeted peer punishment (costly fines), exclusion — designed against
  M12's visible-attributes surface (reputation is nearly a dynamic public
  attribute).
- **M18 — Vectorized NumPy engine backend (review-at).** For populations in
  the thousands — paired with sampling matchers to reach thousands of
  agents at interactive speed (DESIGN §3.1). Empirically triggered: it
  lands when experiments/sweeps show the sampling matchers cannot buy the
  needed scale (the bench supplies the data; DECISIONS #58/#65; M10a's
  re-bench kept the trigger untripped, #84).
- **M19 — Geographic structures (NEW, #103).** The second real
  implementation of M11a's structure abstraction (DESIGN §2.12 forward-
  guards, §6.3): irregular site sets from GeoJSON polygons (shared-border
  adjacency) or raster masks (cells absent outside a boundary); per-site
  capacity above 1 for varying population density — which forces the
  distance-zero kernel question and co-residency semantics (#104); map
  rendering including the mixed-occupancy colour question (likely both a
  blended and a dominant-strategy view, §6.3); centroid/Euclidean
  distance as a structure-supplied metric. Purely additive after M18 and
  needs nothing from M12-M18, so it can be pulled forward without
  renumbering pain provided M11a honours the forward-guards.
  **TASK (spec Design 12, #135): register `site_capacity` as a tunable
  registry parameter and remove M11a's pinned-at-1 validator** —
  answering the three deferred questions #135 records (the
  distance-zero kernel weight, the mixed-cell colour, and what k means
  under occupancy-dependent neighbourhood sizes) before the knob ships.

## v3+ — Real-world scenario modeling

The geographic layer itself moved into the v2 spine (DECISIONS #103):
population structure is M11a, agent movement is M11b, and real geographies
— GeoJSON/raster site sets, map rendering, geographic distance — are M19.
What remains v3+:

- Scenario modeling toolkit for societal/geopolitical conflicts (asymmetric payoffs,
  alliances/sanctions as mechanics, heterogeneous endowments) — built over
  M19's geographic structures.
- Richer dashboard (Dash or FastAPI+React) replacing Streamlit if needed.
- Sweep operation story. The sweep *capability* is v2/M9.5 and in-UI sweep
  browsing is v2/M13 (DECISIONS #59/#75/#76); what remains for v3+ is only
  how it is operated at scale: scheduled, Cowork-driven experiment
  campaigns, plus the deferred adaptive threshold-bisection search
  increment.
