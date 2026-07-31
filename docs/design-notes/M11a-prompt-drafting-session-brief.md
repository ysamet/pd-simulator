M11a — draft the Claude Code prompts.
Design-layer conversation. The output is six Claude Code prompts, not code.

WHAT THIS IS

The M11a design session is COMPLETE. Everything in DESIGN §2.12 and DECISIONS
#103-#110 settled the MODEL; a follow-on design conversation (2026-07-30)
settled the BUILD — phase plan, registry shape, greying map, the reach
primitive's signature, the RNG contract, layouts, persistence, scenarios,
bench, and the §12 checklist.

CRITICAL: none of that follow-on session is in the docs yet. The docs in
project knowledge are current through #110 and no further. This brief IS the
record of the build decisions. Treat every "FROZEN" item below as settled —
they are to be written INTO the spec, not re-derived.

Your job is to draft the prompts. Nothing here is open for redesign.

CORRECTIONS TO ANYTHING YOUR MEMORY TELLS YOU

Check the docs before relying on recall.

  1. M9.5 is COMPLETE (M9.5a 2026-07-11, M9.5b 2026-07-13, DECISIONS #66-#74).
     M10 is COMPLETE, both halves (M10a #76-#84, M10b #93-#102, 722 tests).

  2. M11 is next and it SPLIT. M11a = structure, local birth, local
     interaction. M11b = agent movement + the mouse layout painter (#103).

  3. M19 (geographic structures) is a new milestone at the end of the spine.
     Purely additive, no renumbering. Spine: M10 → M11 → M12 → M13 → M14 →
     M15 → M16 → M17 → M18 → M19.

  4. The #93B imitation-adopter checkpoint was examined at M11 scoping and
     rolled to M12 with a reason on the record (#110). Do not re-open it.

READ FIRST

DESIGN §2.12 (the whole thing — M11a's design brief), §6.3, §2.10, §3.1, §4,
§5; DECISIONS #103-#110 in full, plus #34, #67, #78, #80, #81, #83, #89, #99,
#100, #101, #102; the M10b spec (docs/specs/M10b-async-event-time-spec.md) —
its Design 8/9/10 and its Phase plan are the structural model for M11a's
spec; ROADMAP's M11a/M11b/M19 entries; CLAUDE.md's hard rules and the
delivery rules.

================================================================================
PART 1 — THE FOUR VERIFICATION TASKS
================================================================================

These are facts about the codebase the design session could not establish from
the docs alone. Each blocks a decision. Each must appear IN THE SPEC as an
explicit task in the named phase, with both outcomes specified so the
implementer never improvises.

  VT-1 (PHASE A, FIRST TASK — blocks the flagship scenario)
  Do the payoff registry parameters admit NEGATIVE values? The donation game
  needs T=5, R=4, P=0, S=-1. If negatives are rejected, `donation_game_
  threshold` is unrepresentable as designed. The workaround — adding 1 to all
  four payoffs — preserves every best response and so leaves the strategic
  structure intact, but it changes b/c away from 5 and it shifts every agent's
  income under the energy ledger, which is what the living cost is calibrated
  against. Report the answer before the scenario section is trusted.

  VT-2 (PHASE B — decides the persistence branch)
  Under synchronous IMITATION reproduction, does a SelectionRule replace
  strategies ON THE EXISTING AGENTS (ids preserved), or produce a FRESH COHORT
  with new ids? See PART 8 for the two branches. Expectation is ids-preserved
  (#89(c)'s "an id must mean one creature forever" reads as a project-wide
  invariant), but expectation is not verification.

  VT-3 (PHASE B — decides the weak-selection caveat's wording)
  What does the async `fixed_n` fitness-proportional BREEDER draw actually
  read — current-period payoff, or accumulated energy? And is there any
  selection-intensity parameter tempering it? Ohtsuki's b/c > k threshold
  holds in the WEAK-SELECTION limit. If the draw is raw-proportional with no
  intensity knob, we cannot approach that limit and the threshold is a
  calibration compass, not a prediction (#103 already says this — VT-3 fixes
  how strongly). Second-order: if fitness reads ACCUMULATED energy, relative
  differences widen as a run proceeds, so effective selection strengthens over
  time. The `donation_game_threshold` scenario text states the answer plainly.

  VT-4 (PHASE C — decides whether boundary_order has a second effect)
  In #80's `slots = K - survivors`, is `survivors` computed from the APPLIED
  death set (post-deaths) or from the KNOWN death set (deaths are
  deterministic given the frozen energy snapshot, so the set is knowable
  before it is applied)? If post-deaths, then `birth_first` under well-mixed
  changes how many births are admitted — a different demographic regime, not a
  phase offset — and that is the more important half of what the parameter
  does, so the registry help text must say so. If known-set, the only
  well-mixed effect is newborn exposure to the death phase. Write the answer
  into the help text either way.

================================================================================
PART 2 — PHASE PLAN (FROZEN)
================================================================================

SIX PROMPTS. Prompt 1 creates the spec and stops — no code, no registry
entries, no tests. Prompts 2-6 are Phases A-E, one prompt each.

Rationale for the split: M10b's spec file is 33,000 characters. M11a's will be
larger (14 parameters vs 9; more concepts needing prose; the §12 checklist as
a spec section). Spec-plus-Phase-A cannot fit under 50,000 characters without
trimming, and trimming is the M10a failure mode. This is the split rather than
the trim.

  PHASE A — the structure module, wired to nothing.
    `pdsim/core/structure.py`: the `Site` record (id, neighbour set, capacity,
    optional coordinate); the `Structure` abstraction; `WellMixedStructure` as
    the degenerate builder; `LatticeStructure` as the rectangular builder.
    Distance as a structure-supplied method — Chebyshev for `moore`, Manhattan
    for `von_neumann`. `sites_within()`, `kernel_weights()`, and the
    `neighbourhood_sample()` primitive: implemented and tested, called by no
    engine. Registry gets ONLY the geometry block — `kind`, `rows`, `cols`,
    `neighbourhood_shape`, `boundary` — plus `StructureConfig` with the
    most-square derived default and its validators.
    No engine imports this. Every existing run is untouched by construction,
    so byte-identity is trivially true and the phase is judged purely on
    whether the abstraction is right.
    Tests: degree counts under torus vs bounded (interior 8/4; corner 3/2
    under `bounded`; uniform under `torus`); Moore vs von Neumann neighbour
    sets at radius 1 AND 2; most-square factorisation including the prime-N
    1xN line; distance symmetry and the triangle inequality; the four kernel
    corners from #105 (R=1; beta=0 with R=n; large beta with R=n; R->inf with
    beta=0).
    VT-1 runs first, before anything else in this phase.
    RESET

  PHASE B — occupancy: founding, layouts, rendering, persistence.
    The `Occupancy` object (see PART 5). Agents acquire sites at generation 0.
    All seven `initial_layout` values plus the layout-file mechanism and its
    format. Site id enters `AgentSnapshot`, `agents.parquet`, and the schema
    version. AND the grid renderer.
    The renderer lands HERE, not in Phase E, on app-first grounds (#42/#61):
    there is no honest way to validate a layout except to look at it. "Load
    the scenario, set `initial_layout = checkerboard`, see a checkerboard" IS
    the validation; a test asserting site 0 and site 1 hold different
    strategies is a proxy for it. Phase B needs a renderer that is CORRECT at
    a few hundred cells; the pixel-array fallback and the ~3px floor wait for
    Phase E.
    After B, structure exists and is visible but nothing reads it. Behaviour
    is unchanged.
    VT-2 and VT-3 run in this phase.
    RESET

  PHASE C — local birth. THE RISKIEST PHASE.
    `place_offspring` becomes structure-aware; `admit_births` keeps its
    global-gate job. `birth_radius` / `birth_decay`; `placement_contest`;
    `dynamics.boundary_order`. K as the second cap with the site-count derived
    default and the K <= site-count validator; the `fixed_n` + lattice
    N = site-count validator. Death frees a site, birth occupies one. The RNG
    contract amendments (PART 7) and their golden masters.
    VT-4 runs in this phase.
    RESET — and this phase is the candidate for a FIFTH, mid-phase reset. Flag
    that to the owner when drafting the Phase C prompt rather than discovering
    it in a handback.

  PHASE D — local interaction.
    `matching.spatial_interaction`; `interaction_radius` / `interaction_decay`;
    the `SpatialKernel(Matcher)` sync adapter over the Phase A primitive; the
    async loop calling the primitive directly; the k clamp; the
    `spatial_interaction` requires `lattice` validator.
    RESET

  PHASE E — polish.
    The full greying map BUILT AS A PREDICATE TABLE (PART 4); the pixel-array
    rendering fallback and the size floor; the named validation scenarios; the
    bench structure column; `python -m pdsim.gendocs`; the §12 checklist audit
    run item-by-item against the enumerated list with coverage reported.

RISK READING (write this into the spec's phase plan section)

  C is riskiest, and not because it changes demography. C is riskiest because
  its failures are SILENT.

  (i) It amends a sequence #80 declares frozen, and the amendment is a GATE.
      A gate has two failure directions and they fail differently. Drawing the
      contest permutation when structure is OFF breaks byte-identity on every
      existing seeded run — loud, caught immediately. NOT drawing it where
      contention genuinely exists is silent: the run completes, the numbers
      look plausible, and the golden master for that configuration pins the
      wrong stream forever. #107 confines contention to exactly one
      configuration (synchronous + structure + `energy_economy`) and the
      correctness of that confinement is an ARGUMENT, not a test. The async
      and `fixed_n` exclusions need pins asserting NO DRAW OCCURS, not merely
      that the result is reproducible.

  (ii) `place_offspring` can fail for the first time. #80 checked placement
      before payment against a stub that always returned true. The branch now
      goes live, and the consequence is behavioural: a parent walled in by
      occupied neighbours pays nothing, stays eligible, and keeps
      accumulating. Correct — it is the whole content of viscosity — but an
      agent sitting at 5*theta and not breeding READS AS A BUG unless the
      Economy panel says "blocked: no site in reach." Treat that readout as a
      Phase C deliverable, on the #89(e) logic that put the calibration
      readout in M10a.

  (iii) Two orderings become three and they can silently collapse. #80 keeps
      admission order (energy desc, id asc) separate from iteration order
      (parent-id asc), pinned by a test where they differ. C inserts a contest
      permutation between them. The specific bug: applying the permutation to
      a list that has ALREADY been energy-sorted and then iterating it — which
      yields a `random` contest that is quietly energy-biased in exactly the
      way #107 rejected. The pin needs a fixture where all three orders differ
      PAIRWISE, harder to build than #80's two-way case, and it should be
      written before the code it tests.

  (iv) A boundary-order bug produces PLAUSIBLE DYNAMICS, not a crash. Under
      `death_first` vs `birth_first` the set of available sites differs — the
      whole content of #107. Get it wrong and you get a frontier that behaves
      like an interior, which is the mechanism M12 is being built to study.

  Second-riskiest is B: founding placement is where structure meets #67's
  three-bucket composition, and a mistake there is a systematic bias present
  in every run from generation 0. It is caught by LOOKING at the grid — the
  strongest argument for the renderer landing in B.

  Third is D, and its risk is well-shaped: an additive change at the `Matcher`
  seam, the extension point RandomK already proved in M8 under #57, with the
  async side a SUBSTITUTED partner draw rather than an inserted one.

================================================================================
PART 3 — REGISTRY SHAPE (FROZEN)
================================================================================

SECTION ORDER. Structure sits BETWEEN POPULATION AND DYNAMICS:

  Game -> Matching -> Match -> Population -> STRUCTURE -> Dynamics -> Output -> Run

Per #100(e) this order is inherited by the panel and by PARAMETERS.md.
Rationale: the three derived defaults then resolve in reading order down the
page — N in Population, rows/cols auto-defaulting from N in Structure, K
auto-defaulting from site count in Dynamics. Each auto value's source sits
above it. Accepted cost: `matching.spatial_interaction` stays in Matching (the
key is fixed by #108 and §2.12), so the toggle renders four sections above the
radii it governs. Exactly one greying dependency points forward either way, so
#101's lookahead is exercised identically.

WITHIN MATCHING: register `matching.spatial_interaction` FIRST, above
`matcher`. It is the gate, so `matcher` then greys off a sibling that rendered
before it — the clean direction.

THE 14 PARAMETERS (widget order: geometry, layout, birth group, interaction
group):

  structure.kind              choice, default `well_mixed`
                              {`well_mixed`, `lattice`} — the gate
  structure.rows              int, nullable, default blank (auto), >= 1
                              auto -> most-square factor pair of N (#78 idiom)
  structure.cols              int, nullable, default blank (auto), >= 1
                              same
  structure.neighbourhood_shape  choice, default `moore`
                              {`moore`, `von_neumann`} — the distance metric
                              handed to BOTH kernels
  structure.boundary          choice, default `torus`
                              {`torus`, `bounded`}
  structure.initial_layout    choice, default `random`
                              {`random`, `checkerboard`, `stripes`, `blocks`,
                               `patches`, `central_block`, `from_file`}
                              — SEVEN values; see PART 6
  structure.layout_file       str, nullable, default blank
                              live only when initial_layout = `from_file`
  structure.birth_radius      int, nullable, default 1, >= 1
                              blank = unlimited reach. R=1 is Hammond-Axelrod
  structure.birth_decay       float, default 0.0, range 0.0-20.0
                              beta; irrelevant at R=1
  structure.placement_contest choice, default `random`
                              {`random`, `energy_priority`}
  structure.interaction_radius int, nullable, default 1, >= 1
                              blank = unlimited reach
  structure.interaction_decay float, default 0.0, range 0.0-20.0
  matching.spatial_interaction bool, default off  [MATCHING section, FIRST]
  dynamics.boundary_order     choice, default `death_first`
                              {`death_first`, `birth_first`}  [DYNAMICS section]

RADIUS NULLABILITY: nullable int, blank = unlimited, reusing
`population.memory_depth`'s existing "at least 1; may be empty" machinery
rather than inventing a sentinel. This is what makes §2.12's "R -> inf with
beta = 0 is well-mixed" expressible as a PARAMETER rather than a branch.

LAYOUT FILE = SEVENTH ENUM VALUE. `from_file` joins the `initial_layout`
dropdown; `layout_file` is live only then and greyed otherwise. Rejected: a
non-empty `layout_file` silently overriding the dropdown — that produces a bug
report about a layout setting that "doesn't do anything." The chosen form is
the idiom the app already uses (`match.length_mode = continuation` is what
makes `continuation_probability` live).

site_capacity: NOT A REGISTRY PARAMETER IN M11a.
  #104 requires the FIELD to ship so placement checks `occupants < capacity`.
  It does not require the KNOB. Capacity ships as a plain field on `Site`,
  pinned at 1 and validated as such, with a constant on the builder.
  Registering it would mean a panel widget with exactly one legal value.
  Deferred to M19 not on effort grounds but because capacity > 1 forces three
  questions M11a has no answers to: (1) what the reach kernel does at distance
  zero — two agents in one site would have weight exp(-beta*0) = 1, the
  maximum, for EVERY beta, so no amount of decay could make a housemate less
  likely to be picked than a next-door neighbour, which is a substantive
  modelling claim smuggled in as an arithmetic side-effect; (2) what colour a
  cell holding one cooperator and one defector is — §6.3 records this as open,
  and notes blending softens cluster BOUNDARIES, which is the signal the
  Hammond-Axelrod story is about; (3) what k IS when neighbourhood size
  becomes occupancy-dependent and changes every generation, which costs the
  b/c > k comparison its fixed reference point.
  The density dial M11a DOES have is `carrying_capacity`: per #106, K below
  site count leaves permanent slack (a 20x20 grid at K=250 runs at ~60%
  occupancy) in which the occupied region drifts, clusters and migrates.
  MANDATORY RECORD-KEEPING — three places:
    - the M11a DECISIONS entry records the pinned-at-1 field and names the
      three deferred questions;
    - ROADMAP's M19 entry gains an EXPLICIT TASK line: "register
      `site_capacity` as a tunable registry parameter and remove M11a's
      pinned-at-1 validator" — stated as a task, not as background, so it
      cannot be read past;
    - the spec's own out-of-scope section carries it.
  Registering it later is ADDITIVE (one registry entry + removing one
  validator), not a migration. #104's forward-guard is fully satisfied by the
  field existing now.

================================================================================
PART 4 — GREYING MAP (FROZEN)
================================================================================

  - all `structure.*` grey under `structure.kind = well_mixed`
  - `structure.layout_file` off `initial_layout = from_file`
  - `interaction_radius` / `interaction_decay` off `matching.spatial_interaction`
  - `matching.matcher` GREYS off `matching.spatial_interaction` (#108)
  - `matching.opponents_per_agent` (k) STAYS LIVE ALWAYS, with the clamp
    explained in its help text (#81 idiom, #108)
  - `carrying_capacity` stays LIVE with its site-count derived default (#106)
  - `population.size` stays LIVE and validated (N = site count under fixed_n +
    lattice)
  - `structure.birth_radius` / `birth_decay` STAY LIVE UNDER `fixed_n` — they
    define the competition set for a freed site, which is the k the b/c > k
    threshold counts. This is a consequence of PART 5's Open Question 1 and it
    reverses the naive reading that birth parameters are irrelevant when
    population is pinned.
  - `structure.placement_contest` is a THREE-WAY CONJUNCTION: live only under
    synchronous AND lattice AND `energy_economy` (#107). This predicate spans
    Matching-adjacent, Structure, and Dynamics and points forward regardless
    of section placement.
  - `dynamics.boundary_order` is LIVE UNDER ALL SYNCHRONOUS RUNS, greyed only
    under async. See Open Question 2 below.

OPEN QUESTION 2 — RESOLVED. boundary_order live under all sync.
  Reasoning to write into the spec: #107's own text says "sync-only, greyed
  under async" and stops there — greying under well-mixed would add a
  restriction the decision did not make. The parameter is NOT inert under
  well-mixed: under `death_first`, deaths finish before any child exists, so a
  newborn is guaranteed to survive to the next generation; under
  `birth_first`, the child is created and THEN the death phase runs, so a
  newborn faces the age-mortality coin immediately and can die in the period
  it was born in. That is Hammond & Axelrod's ordering and a genuine
  difference in infant survival. #34 reserves greying for parameters consumed
  NOWHERE. And the errors are asymmetric: showing a parameter whose effect is
  small is mild noise; greying one that has an effect is the app asserting
  something false about the user's run. VT-4 may add a second, larger effect.

TWO EXTENSIONS TO #101'S LOOKAHEAD

  (1) PREDICATES, NOT SINGLE-KEY LOOKUPS. `placement_contest` and the birth
      pair need a conjunction form. Whether `helpers.greying`'s rule form
      already admits conjunctions is not establishable from the docs — make
      "inspect `helpers.greying` and report whether the rule form admits
      conjunctions" an explicit EARLY TASK in the Phase E prompt rather than
      assuming either way.

  (2) RESOLVERS CALLABLE AT PAINT TIME. The §12 obligation includes derived
      readouts (emergent site count, effective neighbour count). Displaying
      "auto -> 10 x 10" next to blank rows/cols, or an honest K default, means
      the panel must call the resolvers with possibly-blank inputs WHILE
      PAINTING. That is more than the lookahead currently does — it reads raw
      widget values, it does not run the `mode="before"` resolution logic.
      Make those resolvers PURE FREE FUNCTIONS callable from both the
      validator and the panel: the M10a `resolve_initial_energy` pattern
      applied again. Say this in the spec or Phase B will hardcode a display
      string that drifts.

BUILD THE GREYING MAP AS A PREDICATE TABLE (DATA), NOT AS CONDITIONALS
SCATTERED THROUGH PANEL CODE. It is a table of "this parameter is inert when
these conditions hold." Hiding is then a second renderer over the same table,
which makes M11b's tab work a PRESENTATION change rather than an audit. This
is cheap now and expensive later.

================================================================================
PART 5 — THE REACH PRIMITIVE (FROZEN)
================================================================================

TOPOLOGY / OCCUPANCY SPLIT. These must be separate objects.
  `Structure` is IMMUTABLE: sites, neighbours, `distance()`. Derived once from
  the config, shareable, cacheable. This is what M19 reimplements as a second
  builder.
  `Occupancy` is MUTABLE per-run state owned by the dynamics, exactly like the
  population list: site -> agent id, agent id -> site, `occupy()`, `vacate()`,
  `empty_sites_within()`.
  This split is what lets `LatticeStructure` be a pure value with no
  simulation state in it, and it is the difference between M19 writing a
  BUILDER and M19 writing an ENGINE. It also makes PART 9's precomputation
  possible.

ONE PRIMITIVE, NOT FOUR. All four call sites run the same algorithm —
enumerate sites within R of an origin, filter to an eligible set, weight by
exp(-beta*d), draw without replacement. Only the eligible set and an optional
second weight vary.

    def neighbourhood_sample(
        structure: Structure,
        origin: SiteId,
        *,
        radius: int | None,
        decay: float,
        size: int,
        rng: np.random.Generator,
        eligible: frozenset[SiteId],
        site_weights: Mapping[SiteId, float] | None = None,
    ) -> tuple[SiteId, ...]:

  - `eligible` is an explicit FROZEN SET, not a predicate callable: the caller
    already holds the occupancy map, and a set is trivially inspectable in a
    failing test where a closure is not.
  - `radius=None` means unlimited reach, matching the nullable parameter.
  - `site_weights` is the optional second weight; combined weight on a site is
    exp(-beta*d) * site_weights[site].
  - Returns FEWER than `size` when fewer are eligible (#81 clamp idiom).
  - Returns an EMPTY TUPLE when none are eligible — this is
    `place_offspring`'s failure signal.

  Underneath, both pure and RNG-free: `sites_within(structure, origin, radius)`
  and `kernel_weights(structure, origin, sites, decay)`. These are what the
  kernel-corner tests exercise directly and the surface M19 must satisfy.

  DETERMINISM RULE: the candidate list is built in ASCENDING SITE-ID ORDER
  before any draw. #80's "everything id-ordered, explicitly" applied to sites
  instead of agents. Without it the draw depends on set iteration order — a
  reproducibility bug that survives every test until a Python version changes.

#103's obligation is satisfied: `neighbourhood_sample` is the NAMED PUBLIC
FUNCTION, so M11b's movement is purely additive and never reopens structure
code.

SpatialKernel(Matcher) — genuinely thin.
  Holds structure, occupancy, radius, decay, k. `pairings()` walks agents in
  ascending id, calls the primitive once per focal with `size=k` and
  `eligible` = occupied sites minus self, maps sites back to agents.
  TWO BEHAVIOURS INHERITED DELIBERATELY FROM RandomK: (1) NO DEDUPLICATION —
  A can draw B while B draws A, so a pair can meet twice in a generation; this
  is existing RandomK behaviour and the source of the `len(agent._histories)`
  sharp edge already in the codebase. (2) CLAMP, NOT ERROR, when k exceeds the
  neighbourhood.

FORK 1 — RESOLVED: DRAW UNCONDITIONALLY whenever spatial sampling is active,
even when k >= neighbourhood size and the outcome is forced. Cost: a wasted
permutation in the "play all neighbours" configuration, which is the H-A
convention and therefore common. Benefit: the stream position is predictable
from the config alone (#80's active-flag idiom). A wasted draw costs nothing;
a golden that shifts when a neighbourhood happens to be full costs a debugging
afternoon.

FORK 2 — RESOLVED: MULTIPLY. The Moran breeder draw's weight is
exp(-beta*d) * fitness. At R=1 all distance factors are equal and it reduces
to EXACTLY fitness-proportional, so Ohtsuki is recovered as a CORNER rather
than approximated. The existing non-negative fitness shift applies BEFORE the
multiplication; the uniform fallback triggers on the COMBINED vector.

OPEN QUESTION 1 — RESOLVED AS OPTION 2. Structure localises the async fixed_n
selection draws; sync imitation's selection stays global.

  Why this was a question: #106 settles where the offspring GOES under fixed_n
  + lattice (every site occupied, a death frees exactly one site, so site
  recycling is forced). It does NOT say where the BREEDER comes from. M10b
  draws the fixed_n breeder fitness-proportionally over the WHOLE living
  population. If that stays global under a lattice, the number of competitors
  for a seat is N-1, not k — and Ohtsuki's b/c > k threshold has k in it
  precisely BECAUSE k counts the competitors for a vacated site. Keep the
  draws global and the Moore-vs-von-Neumann scenario shows nothing.

  DECIDED: localise the async `fixed_n` breeder and victim draws under a
  lattice, with the BIRTH KERNEL supplying the candidate set — read from the
  freed site's side under `death_birth`, from the breeder's side under
  `birth_death`.

  DECIDED: sync IMITATION's SelectionRule stays GLOBAL under a lattice for
  M11a. Recorded as an EXPLICIT DECLINE on scope grounds (not by omission),
  handed to M12 — which needs in-group/out-group strategy spread anyway. This
  is the shape #110 used.

  DOCUMENTATION OBLIGATION — the rationale must be reachable from the UI, not
  only from the explainer. §12's rule is that each concept's explanation comes
  from a SINGLE DESCRIBED SOURCE so app text and docs cannot drift. Three
  places:
    - `structure.kind`'s `lattice` value states that a lattice makes
      interaction and natal placement local, AND that in synchronous imitation
      mode the comparison partner stays drawn from the whole population;
    - `structure.birth_radius` and `birth_decay` state that under `fixed_n`
      these define the SET OF COMPETITORS for a freed site, which is what the
      b/c > k threshold's k counts;
    - a derived readout for EFFECTIVE NEIGHBOUR COUNT gives that k a visible
      number.
  The long-form version, including the b=5 / c=1 walkthrough, goes in the
  explainer (out of scope here — see PART 11).

================================================================================
PART 6 — LAYOUTS AND THE LAYOUT FILE (FROZEN)
================================================================================

THE DIVISIBILITY PROBLEM DISSOLVES: arrangement is DEALING, not PARTITIONING.
#67 has already resolved composition to exact integer counts, and §2.12 says
the layout decides ARRANGEMENT ONLY. So the counts are authoritative and the
arrangement bends around them — the same philosophy as largest-remainder
rounding, one layer up. There is no "4 strategies don't divide into 10 rows"
problem because nothing is being divided.

FIVE ALGORITHMIC LAYOUTS ARE ONE ENGINE: walk the sites in some traversal
order, deal strategies out of the resolved counts until exhausted. What varies
is the traversal and the dealing discipline.

  `stripes`       row-major sweep, RUN-LENGTH dealing. A strategy with 39
                  agents gets 39 consecutive cells; one with 2 agents gets 2.
                  Stripe boundaries fall where the COUNTS fall, so a "stripe"
                  can be a fragment of a row. Say this in the help text rather
                  than let it look like a bug.
  `blocks`        run-length dealing along a traversal that keeps runs compact
                  in two dimensions — a boustrophedon sweep over sub-blocks is
                  enough. No new parameter; degrades gracefully at any count.
  `checkerboard`  ROUND-ROBIN dealing: one cell at a time, cycling over the
                  strategies that still have agents left. With two equal-count
                  strategies this reproduces the literal checkerboard; with
                  four unequal ones it produces MAXIMAL INTERLEAVING, which is
                  the PURPOSE #109 assigns it ("the anti-cluster baseline").
                  Generalise by purpose, not by appearance.
  `patches`       one seed site per strategy placed by RNG, then multi-source
                  growth outward with each strategy's quota as its budget.
                  Deterministic given the seeds — RNG enters only at seed
                  placement.
  `random`        shuffle.
  `central_block` centred rectangle sized to N; the rest of the grid empty.
                  The FILLING regime (#109).

  DEAL ORDER: ascending machine name — reusing #67's tie-break convention so
  there is ONE ordering rule in the project rather than two.

WHEN N < SITE COUNT. Cannot arise under `fixed_n` (N = site count by
validator). Arises under the economy and under `variable_n`. Then every layout
needs a rule for WHICH sites are occupied, not just what is in them.
`central_block` answers this definitionally. The other five need a stated rule.
  DECIDED: `random` SCATTERS over the whole grid; the patterned five use a
  CENTRED CONTIGUOUS FOOTPRINT. Rationale: "random" should mean random, and a
  scattered start is the closest thing to the well-mixed baseline.
  MANDATORY GUARD: the app reports the NUMBER OF AGENTS WITH ZERO OCCUPIED
  NEIGHBOURS AT FOUNDING. A scattered population under local interaction can
  leave agents isolated; an isolated agent plays nothing, earns nothing, and
  starves at the next boundary — correct by #81's lone-survivor logic, but
  bewildering to watch. This turns the hazard into information. It is also a
  derived readout requiring a (?) under §12 anyway.

THE LAYOUT FILE FORMAT. Requirements pull opposite ways: hand-authoring wants
a PICTURE; #104's graph-of-sites forward-guard wants something that survives
M19's irregular site sets, where there are no rows and columns to draw.
  RESOLUTION: ONE FORMAT NOW, VERSIONED SO THE SECOND IS ADDITIVE.
  Plain text. Header: a `kind:` line reading `lattice_grid`, plus `rows:` and
  `cols:`. Body: a character grid, one token per cell — strategy machine names
  or `.` for empty.
  Validators: the header's dimensions must match the resolved `structure.rows`
  / `structure.cols`; every token must be a registered strategy.
  M19 adds `kind: site_map` with a two-column site-id/strategy body; the
  reader dispatches on the header. Additive, no rewrite — and the
  DISCRIMINATOR SHIPS FROM DAY ONE so there is never a file in the wild
  without one.

TWO CONSEQUENCES, BOTH DECIDED EXPLICITLY:
  (1) A layout file specifies composition IMPLICITLY (it names a strategy per
      cell), so it can contradict the resolved #67 composition. THE FILE WINS
      and the composition widgets grey. Requiring the user to separately
      reproduce counts they have already painted is a trap. VALIDATOR: reject
      a layout file combined with a SWEPT COMPOSITION AXIS — those two are
      incoherent together.
  (2) THE RECORDER MUST COPY THE LAYOUT FILE INTO THE RUN FOLDER. A
      `config.yaml` referencing `layouts/my_painting.txt` violates hard rule 8
      the moment that file moves. Two-line fix; makes the run folder
      self-contained.

================================================================================
PART 7 — THE RNG CONTRACT (FROZEN)
================================================================================

THE FINDING: most changes are SUBSTITUTIONS, NOT INSERTIONS, because of an
asymmetry in Ohtsuki's two update rules that maps unexpectedly well onto
M10b's existing draw order.

  Under DEATH-BIRTH: a random individual dies and ITS NEIGHBOURS compete. The
  victim draw is global and uniform — UNCHANGED from M10b. Only the breeder
  draw localises.
  Under BIRTH-DEATH: a breeder is chosen by fitness from the whole population
  and the offspring replaces ONE OF ITS NEIGHBOURS. The breeder draw is global
  — UNCHANGED. Only the victim draw localises.

  So in each rule EXACTLY ONE draw changes, it is always the SECOND of the
  two, and it changes its candidate set and weights while KEEPING ITS POSITION
  AND CALL SHAPE. Neither rule gains or loses a draw. The `moran_rule =
  random` roll keeps its pinned position as the first demographic draw of the
  event, untouched.

FULL INVENTORY

  Founding layout            NEW (once per run, before generation 0)
                             gate: lattice + non-deterministic layout
  Sync interaction partners  SUBSTITUTION (SpatialKernel for RandomK/RoundRobin)
                             gate: lattice + spatial_interaction
  Sync contest permutation   INSERTION (one permutation over the admitted set)
                             gate: sync + lattice + energy_economy
  Sync placement, per parent INSERTION (at the placement check, before sigma)
                             gate: lattice + births exist
  Async partner draw         SUBSTITUTION
                             gate: lattice + spatial_interaction
  Async DB breeder /
    BD victim                SUBSTITUTION
                             gate: lattice + fixed_n
  Async variable_n placement INSERTION (same position as sync)
                             gate: lattice

  Three insertions. The layout one sits OUTSIDE the per-generation order
  entirely (it happens at population construction), so it cannot perturb any
  within-generation sequence. That leaves TWO real insertions into
  golden-mastered orders, both inside the birth step, both Phase C.

AMENDED #80 STEP (6), BIRTHS — as a DIFF, since #80 is frozen:
  CURRENT: admission by energy priority (RNG-free) -> admitted set iterated in
  ascending parent-id order -> placement check -> sigma payment -> passport id
  -> mu draw.
  AMENDED: admission UNCHANGED -> CONTEST PERMUTATION over the admitted set,
  when the three-way gate holds -> iteration order is the permutation under
  `random`, energy-desc under `energy_priority`, and parent-id ascending when
  the gate is off -> placement check NOW A KERNEL DRAW THAT CAN RETURN EMPTY
  -> sigma payment ONLY ON SUCCESS -> passport id -> mu draw.

AMENDED #99 WITHIN-EVENT ORDER, fixed_n — as a DIFF:
  Rule roll UNCHANGED. Under `death_birth`: victim draw UNCHANGED, breeder
  `rng.choice` now over the FREED SITE'S NEIGHBOURS with combined weights.
  Under `birth_death`: breeder draw UNCHANGED, victim draw now over the
  BREEDER'S NEIGHBOURS. Under `variable_n`: the placement check inside the
  birth sub-step becomes a kernel draw.

THREE ORDERINGS NOW. See the risk reading in PART 2 (iii) for the collapse bug
and the pairwise-differing fixture.

GOLDEN MASTERS
  FOUR NEGATIVE PINS FIRST — these are what nothing else catches: sync
  imitation, sync economy, async `variable_n`, async `fixed_n`; each
  well-mixed; each byte-identical to its pre-M11a event stream AND persisted
  folder.
  FOUR NEW POSITIVE GOLDENS: sync economy + lattice; async `fixed_n` + lattice
  + `death_birth`; async `variable_n` + lattice; sync imitation + lattice (the
  interaction-only case).
  NO-DRAW ASSERTIONS: no contest permutation under async, under `fixed_n`,
  under sync well-mixed, or under sync imitation with a lattice.

  TECHNIQUE — adopt this. Byte-identical output USUALLY catches a spurious
  draw, because a shifted stream changes everything downstream — but NOT if
  the extra draw lands after the last consequential one. A COUNTING WRAPPER
  around the `Generator` that records the exact sequence of method calls turns
  "the output matched" into "the stream was identical," and makes the no-draw
  assertions DIRECTLY EXPRESSIBLE rather than inferential. Cheap, and it is
  the mechanism the negative pins actually need.

================================================================================
PART 8 — PERSISTENCE (FROZEN, WITH ONE CONDITIONAL)
================================================================================

THE SIMPLIFICATION: IN M11a AGENTS NEVER MOVE. Movement is M11b. So an agent's
site is fixed from birth to death, and occupancy at any period is fully
determined by founding placement plus the birth and death record — both
already persisted.

  - Site id becomes a SINGLE COLUMN on `agents.parquet`, present when the run
    has structure, absent otherwise (#83's honest-presence rule exactly). NO
    new sibling table, NO widened `timeseries.parquet`, nothing NaN-filled.
  - `AgentSnapshot` gains `site_id: int | None`, as DESIGN §4 already
    specifies. This is also what the live grid renderer reads.
  - SCHEMA_VERSION = 5, written when structure data is present. Existing
    constants untouched: well-mixed sync imitation still writes 2, well-mixed
    sync economy 3, well-mixed async 4, ANY lattice run 5. Loader accepts 1-5,
    rejects above.
  - STATE THIS IN THE SPEC so the ladder is not read as implication: a sync
    economy lattice run writes 5, a number that arrived with event-time data
    it does not have. This is already handled by #100(b), which makes
    missing-file-equals-empty-shape the CONTRACT rather than mere backward
    compatibility. The loader is PRESENCE-DRIVEN, not version-driven, so a
    monotone integer works.

THE CONDITIONAL — resolved by VT-2.
  `agents.parquet` and `AgentSnapshot` exist only in economy mode; §4 says
  snapshots are empty under imitation. So SYNC IMITATION + LATTICE has
  occupancy and nowhere to record it. DESIGN §4's "AgentSnapshot gains a site
  id" implicitly assumes structure + economy; imitation + lattice is a
  configuration the design edit did not consider.
    IF ids are preserved across imitation generations: nobody is born, nobody
    dies, occupancy never changes after founding. It is entirely determined by
    the initial layout, which lives in the config, and re-running reproduces
    it exactly. NOTHING TO PERSIST; the live renderer holds occupancy without
    any event carrying it.
    IF ids are NOT preserved: occupancy is re-derived every generation and
    does need recording. Then: a DENSE `occupancy.parquet` sibling (period,
    agent_id, site_id) on the #100(b) pattern. NOT a widened `agents.parquet`
    — widening would mean null energy and age columns for every imitation run,
    which is precisely what #47c forbids.
  THE SPEC SPECIFIES BOTH BRANCHES. Phase B establishes which.

FORWARD NOTE FOR M11b (record it now, it is cheap): once agents move,
occupancy becomes genuinely time-varying and is no longer derivable from
births and deaths. That is when `occupancy.parquet` becomes necessary
REGARDLESS of how VT-2 resolves. Recording this in the M11a spec means M11b
inherits the reasoning instead of rediscovering it.

================================================================================
PART 9 — VALIDATION AND BENCH (FROZEN)
================================================================================

APP-FIRST per #42/#61. With the venv active (`.venv\Scripts\Activate.ps1`),
launch `streamlit run pdsim/ui/app.py`.

  V1  Structure exists and is visible — lattice renders, cells square, site
      count reported.                                            PHASE B
  V2  Layouts — walk `initial_layout` through all seven values,
      see each arrangement.                                      PHASE B
  V3  Viscosity — cooperator clusters survive where they would be
      wiped out well-mixed.                                      PHASE C+D
  V4  `boundary_order` — same config, `death_first` vs
      `birth_first`, divergent outcome.                          PHASE C
  V5  The drifting frontier — K below site count, occupied region
      migrates.                                                  PHASE C
  V6  The b/c > k threshold — von Neumann clears, Moore fails.    PHASE D
  V7  Golden masters, positive and negative (CLI).               PHASE C
  V8  Byte-identity regression on four well-mixed configs (CLI).  EVERY PHASE

FOUR NEW REGISTERED SCENARIOS

  `spatial_reciprocity` / "Cooperation Survives in Clusters" — THE FLAGSHIP.
    Sync `energy_economy`, lattice, local interaction and local birth at R=1,
    roster AllC and AllD only, one round per match. Cooperators in a cluster
    earn R from all four neighbours; defectors in a defector interior earn
    P=0 from everyone and starve under the living cost. Things-to-try: switch
    `structure.kind` back to `well_mixed` and watch AllD take everything.

  `donation_game_threshold` / "The b/c > k Threshold" — the Ohtsuki
    replication attempt. THREE NON-OBVIOUS REQUIREMENTS:
      - `rounds_per_match = 1`, roster AllC + AllD only. Ohtsuki's threshold
        is derived for ONE-SHOT games; with 50 rounds and TitForTat in the
        roster the threshold does not apply, and at one round TFT cooperates
        and is indistinguishable from AllC anyway. Consequence: noise, memory
        depth, and every reciprocity parameter are INERT here — the scenario
        text says so rather than leaving a novice wondering where the
        seven-strategy roster went.
      - `fixed_n_death_rule = pure_random`, NOT the default. Ohtsuki's
        death-birth is: a random individual dies, then its neighbours compete
        by fitness. The M10b default `energy_decides` makes the death
        deterministic. Getting this wrong yields a plausible run that is not
        the model being replicated.
      - The WEAK-SELECTION honesty caveat, worded per VT-3.
    Ships as VON NEUMANN — the case that CLEARS the threshold, so the default
    view shows cooperation succeeding. #36 says one scenario = one config and
    comparative questions live in the things-to-try text, so the things-to-try
    note says: switch `neighbourhood_shape` to `moore` and re-run, predicting
    the reversal before doing it. TWO scenarios differing in one enum value
    would duplicate the mechanism things-to-try exists for.
    BLOCKED BY VT-1.

  `the_drifting_frontier` / "The Drifting Frontier" — K at roughly 60% of site
    count, so #106's slack is live and the occupied region clusters and
    migrates rather than filling the grid.

  `the_filling_grid` / "The Filling Grid" — `central_block` layout, growth
    economy, expansion into empty space. The Kaznatcheev & Shultz regime, and
    the reason #109 shipped that layout.

BENCH STRUCTURE COLUMN — YES, and it tests a FALSIFIABLE CLAIM (#91/#102
discipline, not decoration).

  Local interaction REDUCES match-phase work (k clamps to the neighbourhood —
  4 or 8 at R=1, against round-robin's N-1). The interesting cost is the
  KERNEL DRAWS, where the naive implementation scales badly: enumerating sites
  within radius R is O(R^2) — at R=10 under Moore that is 440 sites
  enumerated, distance-computed and weighted, once per focal per event.
  THE FIX IS PRECOMPUTATION, available because of PART 5's topology/occupancy
  split. Topology is immutable, so the candidate list for each site at each
  radius is a pure function of the config and can be built once. Weights are
  cacheable more cheaply still: weight depends only on DISTANCE, so ONE
  distance->weight lookup table per (R, beta) pair covers every site on the
  grid. Per-draw cost then scales with neighbourhood size rather than with
  enumeration. Memory stays modest — 10,000 sites at 440 neighbours each is a
  few million integers.
  TWO HYPOTHESES, stated in the spec so the measurement CAN FAIL:
    (1) cost is FLAT IN R once the cache is warm;
    (2) the lattice column sits AT OR BELOW `random_k` at equal k.
  If (1) fails, the cache is not working. If (2) fails, the kernel draw is
  more expensive than the matches it replaces — a surprise worth chasing.
  Grid: N x {`round_robin`, `random_k`, `lattice_vn_r1`, `lattice_moore_r1`,
  `lattice_moore_r5`}. Measured at Phase E. Rendering cost stays OUT — that is
  #94's wall-clock throttling on a separate axis; the bench measures the
  engine. Output remains environment-specific and uncommitted.

================================================================================
PART 10 — THE §12 CHECKLIST (53 ITEMS)
================================================================================

The spec must contain this as an EXPLICIT ENUMERATED CHECKLIST so it is
verifiable, not aspirational (#103 makes this a spec obligation). Phase E runs
it as an audit pass, item by item, and REPORTS COVERAGE.

14 REGISTRY PARAMETERS (plain-language description each — structurally
guaranteed by DESIGN §5, but listed so the checklist is complete rather than
partly implicit): structure.kind, rows, cols, neighbourhood_shape, boundary,
initial_layout, layout_file, birth_radius, birth_decay, placement_contest,
interaction_radius, interaction_decay, matching.spatial_interaction,
dynamics.boundary_order.

17 ENUM VALUES, EACH INDIVIDUALLY EXPLAINED — this is the part §12 exists for,
since a parameter-level description silently skips it: well_mixed, lattice;
moore, von_neumann; torus, bounded; random, checkerboard, stripes, blocks,
patches, central_block, from_file; random, energy_priority; death_first,
birth_first.

14 CONCEPTS, each with a (?) drawn from ONE described source: site;
exclusivity and capacity; neighbour and neighbourhood; support radius R;
decay beta; the reach kernel; viscosity; wrap-around and why it equalises
degree; degree, and why cooperation thresholds depend on it; the two gates and
why clearing one is not enough; a blocked parent; arrangement versus
composition; the b/c > k threshold; spatial reciprocity.

8 DERIVED READOUTS, each with a (?) AND a visible number: emergent site count;
resolved rows x cols when blank; resolved K when blank, shown alongside site
count (#106's both-numbers guard); effective neighbour count after the clamp —
the k the threshold compares against; occupancy as a fraction; agents with
zero occupied neighbours at founding; blocked parents this generation; whether
pixel-array rendering is active.

TWO OF THOSE READOUTS ARE MORE THAN TOOLTIPS and belong in the ECONOMY PANEL,
not only in help text:
  - BLOCKED PARENTS — stops a correct behaviour reading as a bug (PART 2 (ii)).
  - ZERO-NEIGHBOUR AGENTS AT FOUNDING — the guard on `random` scattering under
    a sparse population (PART 6).

================================================================================
PART 11 — DOCS OBLIGATIONS AND SCOPE
================================================================================

DECISIONS ENTRIES THE M11a WORK MUST PRODUCE (numbering continues from #110):
  - the build decisions in this brief, as the spec's implementation proceeds
    and wherever a deviation occurs (specs are FROZEN historical records —
    deviations become NEW DECISIONS entries, never retro-edits, #62);
  - Open Question 1's resolution, with the sync-imitation global-selection
    decline recorded EXPLICITLY on scope grounds and handed to M12;
  - the `site_capacity` pinned-at-1 field and its three deferred questions;
  - THE TABS DECISION, recorded even though nothing is built: the `run.mode`
    tab split; the TOTAL-FORK CRITERION (hide only where every parameter on
    the far side is genuinely ignored, with no exceptions and no partial
    cases — because a greyed widget says "this exists and does nothing here"
    while a hidden one says "this is irrelevant here," and if that is ever
    wrong the user cannot see the parameter affecting their run); why
    `time_model` FAILS that criterion (`selection_beta` follows the imitation
    OVERLAY not the mode — #101's carve-out — and the ledger knobs L,
    engagement, r, sigma apply under sync economy AND both async population
    modes, so Dynamics has a shared core with two mode-specific wings, not a
    clean cut); why `reproduction_mode` fails it (same shared-ledger problem,
    plus async `variable_n` BEING the economy under a different clock);
    collapse-with-summary as the treatment for inert sections; and
    novice/advanced disclosure as a SEPARATE ORTHOGONAL axis deserving its own
    decision.

ROADMAP:
  - M19's entry gains the explicit `site_capacity` registration TASK line;
  - M11b's entry gains the UI simplification line (tab split + collapse +
    novice/advanced), alongside the layout painter.

NOT IN SCOPE FOR THIS CONVERSATION:
  - THE M11a EXPLAINER. Separate prompt, after a literature verification pass.
    Two claims are flagged UNVERIFIED in #103 and must be checked against
    publisher records before they enter it: whether Hammond & Axelrod used
    WRAP-AROUND on their 50x50 lattice, and the Kaznatcheev & Shultz
    300-PERIOD FIGURE the M10 explainer currently quotes without a
    verification note of its own. Do not fold the explainer into any spec or
    phase prompt.
    (Note: the `neighbourhood_shape` default is `moore` by the owner's call,
    so the H-A wrap-around verification no longer gates the default — but it
    still gates the explainer and M12's replication scenario.)
  - The UI tab / collapse / novice-advanced IMPLEMENTATION. That is M11b, next
    to the layout painter, deliberately NOT beside the riskiest phase in this
    milestone — a panel rewrite landing next to Phase C would make any
    regression ambiguous between "structure broke something" and "the panel
    rewrite broke something." What M11a carries is the ENABLING piece: the
    greying map as a predicate table, plus the DECISIONS entry.
  - Anything M11b: movement, the MovementRule ABC, the walk radius/decay pair,
    the movement schedule, the mouse painter.
  - Re-opening #110, or anything in DESIGN §2.12 / DECISIONS #103-#110.

================================================================================
PART 12 — HOW TO PROCEED
================================================================================

  1. Read the docs listed under READ FIRST. Do not rely on recall.

  2. Draft PROMPT 1 — spec creation ONLY. It instructs Claude Code to create
     `docs/specs/M11a-population-structure-spec.md` and nothing else: no code,
     no registry entries, no tests. The spec follows the M10b spec's
     structure — status header, Frozen intent, Defining principles, numbered
     Design sections, a Parameters table, the Phase plan with reset markers,
     and a Validation section WRITTEN AT SPEC TIME — and it carries everything
     in PARTS 2-10 of this brief, plus the four verification tasks from PART 1
     placed in their named phases with both outcomes specified.
     MUST BE UNDER ~50,000 CHARACTERS. If it will not fit, SPLIT IT AND TELL
     ME THE SPLIT — do not trim content. The M10a session lost a DECISIONS
     cluster to truncation.

  3. Deliver it as a SINGLE, CLEARLY LABELLED, COMPLETE CUT-AND-PASTE PROMPT.
     Never as edits for me to make by hand. Never split across prose. End with
     an explicit one-line "Action required:" statement.

  4. I paste it to Claude Code, then paste the handback here. You review it:
     identify the invariants to verify, flag watch items, and give an explicit
     GO / NO-GO before the next prompt.

  5. Then PROMPT 2 (Phase A), same delivery rules, same review cycle. Then B,
     C, D, E. Reset the conversation at each phase boundary.

  6. Claude Code NEVER commits. At every milestone completion it presents (a)
     a summary of what was done, (b) the list of files to stage, and (c) a
     suggested commit message. I perform the commit.

  7. Every implementation prompt ends with APP-FIRST validation instructions
     (#42/#61): the venv-activation reminder, a NAMED scenario to load, the
     SPECIFIC widgets to touch, and the OBSERVABLE outcome that confirms it
     works. CLI validation only for inherently headless features (the golden
     masters, the bench). Automated tests COMPLEMENT — never substitute.

  8. Every prompt that touches the registry instructs a re-run of
     `python -m pdsim.gendocs` and staging of the result — the drift test
     fails while `docs/PARAMETERS.md` is stale.

  9. Claude Code ends every session with an explicit `DOCS CHANGED: [files]`
     or `DOCS UNCHANGED` report, with new DECISION numbers called out, so I
     know exactly which files to refresh in project knowledge.

  10. THIS CONVERSATION WILL ITSELF NEED A RESET. Expect to hand off after
      Phase C's prompt at the latest — proactive resets beat auto-compaction,
      and quality degrades before the hard context limit. Produce a WIP-style
      handoff when you judge the boundary is near, rather than waiting to be
      asked.

Start with step 2.
