# M10 — Design Freeze (score-as-energy growth economy)

**Status:** design record, NOT a spec. Produced in a Claude.ai design conversation.
Nothing in here has landed in `docs/` or code yet. This document is the *only*
record of the M10 scoping conversation — upload it to project knowledge before
continuing.

**What this covers:** the frozen design decisions for **M10a** (the synchronous
generational energy economy), the deferred shape of **M10b** (async/Moran) and
**M11** (population structure), the milestone renumbering, the vectorization
verdict with its measured evidence, and the remaining design work (step 5) still
to do before a spec can be written.

**How to use it:** §1–§9 are frozen. §10 is what's still open. §11 is the
literature-verification to-do. §12 is the explicit handoff plan for the next
conversation(s).

---

## 1. The two foundational forks (confirmed by the owner)

**Fork 1 — Synchronous-first split (FROZEN).**
- **M10a** = the energy economy on the *existing generational clock*. The
  generation stays the unit of time; population size is constant *within* a
  generation and changes only *at the boundary*, where all births and deaths are
  computed against one frozen end-of-generation snapshot and applied
  simultaneously. **M10a delivers the entire variable-N invariant** — the
  load-bearing change every later milestone must be built around.
- **M10b** = the asynchronous / Moran-style *event* time-model, a separate later
  increment. It dissolves the generation as the tick and gets its own spec. Not
  designed here beyond "it exists and comes second."
- Rationale: M10a is a conservative extension — preserves the #32
  synchronous-batch reproducibility contract, reuses the match phase and the
  ScoreAccounting seam untouched, generalises exactly one phase (fill-N-slots →
  apply births/deaths). The invariant-*dissolving* part (async event ordering,
  "when is energy earned in continuous time") is quarantined into M10b and
  designed against a *working* variable-N engine.
- Rejected: one-milestone-both-modes (biggest blast radius first — the mistake
  #58 rejected for games-first); async-first (front-loads the
  invariant-dissolving change onto the least-stable engine).

**Fork 2 — Energy replaces imitation (FROZEN).**
- Economy mode is a **distinct evolutionary paradigm**: *birth-death dynamics*,
  not a modification of v1's *imitation dynamics* (Fermi copying).
- In `energy_economy` mode the **SelectionRule family greys out** (Fermi,
  proportional, tournament_k, truncation, threshold_cloning) via the #34
  ignored-but-valid pattern. Selection intensity β and all rule parameters are
  **inert** in economy mode. Differential survival *is* the selection.
- Rationale: the owner's research target (Hammond–Axelrod ethnocentrism, M12) is
  birth-death, not imitation. Building the economy as "replace" puts M10 on M12's
  rails. Also ties off the #64 deferred `cumulative` accounting loose end: energy
  *is* that cumulative stock, but repurposed — accounting produces "effective
  scores selection reads"; energy is "a stock reproduction spends." Different
  jobs → replace, don't compose.

---

## 2. The economy frame: OPEN FLOW, not conserved (FROZEN)

Total system energy is an **open flow with named sources and sinks**, not a
conserved quantity. A closed economy can only stall or go extinct; it can't do
anything interesting in between.

- **Sources** (energy enters):
  - **Payoffs** — behavior-earned, from PD matches. This is the scientific heart:
    mutual cooperation is positive-sum (R+R = 3+3 = 6) while mutual defection is
    nearly zero-sum (P+P = 1+1 = 2). Cooperation *creates more energy per
    interaction*, so a metabolic bill filters behavior.
  - **Capital return** — wealth-proportional (see §6). Behavior-independent.
- **Sinks** (energy leaves):
  - basic living cost, engagement cost, reproduction overhead (§3, §5),
  - **estate destruction on death** (§7) — the 100%-inheritance-tax corner.
- **Transfers** (energy moves, conserved): **offspring stake** (§4).

**Honest caveat (must appear in the explainer):** this does NOT repeal the
Prisoner's Dilemma. In a *mixed* population a defector still exploits a
cooperator (D-vs-C pays 5/0), so defectors still locally out-earn and can invade.
What the economy adds is a second, *ecological* layer: as defectors displace
cooperators, total energy production collapses from ~9/agent toward ~3/agent, so
a defector-dominated population grows sluggishly or dies under the same living
cost — the tragedy of the commons made thermodynamically literal. Whether that
rescues cooperation depends on *structure* (→ M11, M12).

**Worked filter example** (4 agents, round-robin, 1 round/match, so 3 matches
each): all-C population earns 3×3 = 9/agent; all-D earns 3×1 = 3/agent. With flat
living cost L = 4: cooperators net +5/gen (grow), defectors net −1/gen (5→4→3→2→1→0→dead).
Anywhere 3 ≤ L < 9, the same cost that cooperators shrug off drives defectors extinct.

---

## 3. Costs: two additive components (FROZEN)

Two independent, additively-combined sinks, each meaning exactly one thing:

- **`dynamics.basic_living_cost`** — flat, per agent per generation. The cost of
  *existing* (metabolism/rent). Paid even if you interact with no one.
- **`dynamics.engagement_cost`** — per **match** the agent plays (NOT per round).
  The cost of *doing business* — overhead/exposure of an engagement.
  **Default 0.**

Energy update term: `− basic_living_cost − engagement_cost × matches_played`.

- `engagement_cost = 0` → pure existence model. `basic_living_cost = 0` → pure
  transaction model. Both pure models are corners of one design.
- **Per-match, not per-round** (deliberate deviation from DESIGN §6.1's "per-round"
  phrasing — log in DECISIONS): per-round would couple cost to `rounds_per_match`
  and continuation-probability `w`, making match-length knobs silently
  *economic* and confounding experiments. Per-match keeps the cost orthogonal to
  match-length knobs. Under continuation-prob `w`, per-round would also inherit
  the random match length → an RNG-entangled cost. Per-match avoids both.

**Rejected: coupling the two by a ratio.** The owner proposed constraining
`engagement_cost` as a configurable ratio of `basic_living_cost`. Rejected because
of a **units problem M10 itself creates**: `basic_living_cost` is energy/generation,
`engagement_cost` is energy/match; converting between them needs a match count
`m_ref` — but N changes every generation by design, so any ratio either silently
re-tunes mid-run (as N grows) or is a fiction after generation 1. Also breaks
M9.5 axis independence (two absolutes give a clean 2D sweep grid; a derived
value doesn't). The owner's actual want — *visibility/control over combined
burden* — is served by the **calibration readout** (§8), which adds information
rather than removing expressiveness.

**The marginality dial (why two components earn their keep).** Under random_k,
participation varies. Flat cost makes being under-connected a *survival threat*;
per-match cost makes it *survival-neutral*. Two components turn that fork into a
continuous dial — the same dial that governs whether *immigration* / a small
community entering under-connected faces a hard survival gradient or a soft
landing.

---

## 4. Offspring policy: stake-transfer (FROZEN)

- An agent is **eligible** to reproduce when energy ≥ **θ**
  (`dynamics.reproduction_threshold`).
- On reproducing it pays stake **σ** (`dynamics.offspring_stake`); the newborn is
  endowed with exactly σ. **σ ≤ θ** (guarantees the parent survives its own
  reproduction). Newborn starts with empty per-opponent history.
- **`dynamics.initial_energy` defaults to σ** — founders start life exactly like
  newborns (one fewer free number to reason about).
- **`dynamics.reproduction_overhead`** — optional extra the parent pays *beyond* σ
  (breeding as a metabolic cost). **Default 0.** The one clean place non-conservation
  at birth is allowed.
- **One birth per agent per generation**, even if energy ≥ several multiples of θ
  (matches H-A; bounds the birth phase). Consequence: the dynastic channel runs
  through *breeding frequency*, not offspring endowment (σ fixed → rich parents'
  children born no richer, just more of them). Turning on inheritance (M15) is
  what would change that.

**Rejected:** fixed endowment (an uncontrolled second source that swamps the
payoff source); zero endowment (folded in as σ = 0); binary fission / halving
(welds endowment to parent wealth, collapses θ and σ into one knob — noted as a
future offspring-policy option behind the same seam).

---

## 5. Death threshold & the per-generation sequence (FROZEN)

**Death at `e < 0`** (strictly negative), not `e ≤ 0`. An agent that just
qualified and paid σ can land at exactly 0; under strict-negative it survives
empty-handed to earn again, so reproduction is not suicidal at the margin.

**Per-generation draw sequence (extends #32 — this IS the step-4 RNG contract):**

1. **Match phase** — unchanged (#23 per-round order).
2. **Energy update** (deterministic; produces the single frozen snapshot deaths
   and births read):
   `e ← e_carried_in × (1 + capital_return_rate) + raw_score − basic_living_cost − engagement_cost × matches_played`
3. **Mortality sub-phase** — one mortality coin per living agent, **ascending
   agent-id order**, drawn **only if age-mortality is active**
   (`base_hazard > 0` or `senescence_factor ≠ 1.0` or `max_age > 0`). Before
   insolvency, before births.
4. **Insolvency deaths** — deterministic: remove every agent with `e < 0`.
5. **Births** — deterministic threshold (`e ≥ θ`) + capacity admission; each
   offspring assigned the next passport id in parent-id order, then the existing
   μ-mutation draws (coin, conditional roster draw) per offspring in that order.

**Death-before-birth** (frozen): the cull frees room, then survivors breed into
it — the "at K, births require deaths" Moran-like regime. *Bonus:* this is also
the spatially-correct order for M11 (deaths free lattice sites, then neighbors
reproduce into them). Rejected: fully-simultaneous no-ordering (ambiguous at
capacity).

**Only RNG in the whole birth/death/mortality machinery:** mortality coins (step
3, conditional) + mutation draws (step 5, conditional), both id-ordered. With
age-mortality off and μ = 0, the match phase is byte-identical to the fixed-N
engine. **Any change to this order is a breaking change → new DECISIONS entry.**

**Birth-step ordering discipline (M11-forward):** structure the birth as **check
placement → then pay σ**, never pay-then-place. In M10a placement never fails so
it's invisible; getting it backwards bequeaths M11 a bug where a blocked parent
is charged for a child never born.

---

## 6. Capital return / interest (FROZEN)

- **`dynamics.capital_return_rate`** — multiplicative return on the balance
  **carried into** the generation (capital held through the period), applied in
  the step-2 energy update above. **Default 0.** (Name chosen over
  `interest_rate`.)
- Applies to carried-in balance (already net of *prior*-period reproduction
  costs) — honoring "interest on residual wealth after costs," the standard way
  interest works.
- **Cannot compound a debt:** death at `e < 0` every generation means every
  living agent enters a generation at `e ≥ 0`; there's no negative balance for
  interest to act on.
- **This is the deliberate wealth→earning coupling** (previously flagged as a
  future non-feature). Added in the open, default off.
- **Escape velocity `e* = costs / r`.** Above e*, an agent is self-sustaining
  regardless of behavior (pays its bills from returns on capital, clears θ
  forever) — the *rentier threshold*. Immune to the metabolic filter the whole
  experiment rests on. Surface e* in the calibration readout whenever r > 0.
- **Interaction to name as a mechanism, not a footnote:** capital return +
  highest-energy-first at-capacity admission (§7) = **structurally permanent
  dynasty**. Keep the deterministic admission rule (RNG-free) but name this
  honestly in the explainer; note an alternative admission policy as a future knob.

---

## 7. Carrying capacity, mortality, identity (FROZEN)

### Carrying capacity
- **`dynamics.carrying_capacity` (K)** — hard cap on population size. At capacity,
  admit births **highest-parent-energy-first, ties broken by agent id**
  (deterministic, RNG-free — a deliberate choice over a random lottery, which
  would inject fresh RNG into the birth phase for no scientific gain).
- **K's scope is aspatial-specific, NOT universal.** It is the well-mixed model's
  stand-in for the physical room a lattice provides intrinsically. Under M11,
  capacity may become emergent from site count. State this scoping in spec +
  explainer.

### Mortality — rising hazard (Gompertz-shaped)
`p(age) = base_hazard × (senescence_factor ^ age)`, clamped to 1.0, forced to 1.0
at `max_age`.

- **`dynamics.base_hazard`** — death probability of a newborn (age 0); the flat,
  age-independent risk. **Default 0.**
- **`dynamics.senescence_factor`** — per-age hazard multiplier. **Default = AUTO**
  = `(1 / base_hazard) ^ (1 / max_age)` when `base_hazard > 0` AND `max_age > 0`;
  otherwise **1.0**. The auto value makes `p(max_age) = 1.0` exactly and
  `p(age) < 1.0` for all ages below it — the stochastic curve and the
  deterministic cap agree at the endpoint instead of the cap being an arbitrary
  guillotine.
- **`dynamics.max_age`** — hard cap; `p = 1.0` there. **Default 0 = no cap.**

**Corners recovered:** `senescence_factor = 1.0` → flat fixed-probability
(Hammond–Axelrod constant death chance); `base_hazard = 0, senescence_factor =
1.0` → deterministic die-at-max_age (only insolvency kills before the cap); all
neutral → the immortal-unless-insolvent economy (the M10 default).

**The auto default is the registry's FIRST derived/computed default** — new
machinery: a sentinel (e.g. `"auto"`) resolved by a Streamlit-free resolver at
config-build time into a concrete float, so the stored config holds a plain
number and validation stays simple. Own DECISIONS entry + own tests (resolver in
the testable helper, never in UI). Owner approved adding this pattern.

**Guard — warn, don't forbid:** if a user explicitly sets `senescence_factor`
high enough that effective max age < `max_age`, allow it but surface a soft note
in the calibration readout ("effective maximum age ≈ 15, below max_age 20").
Someone may legitimately want a population where nobody reaches the cap.

**Estate on death:** destroyed in M10a (age/hazard OR insolvency) — the
100%-inheritance-tax corner, a *named position* not a placeholder. M15 opens the
rest. NOTE this makes age-death a **new, large sink at high wealth** (a wealthy
agent dying of old age has its positive balance vanish) → a hard ceiling on
accumulation: compound for at most ~lifespan generations, then reset. This is
`max_age` doing its job against escape velocity.

**Founder age staggering (FROZEN):** when any age-mortality is active, seed
founders with **uniform staggered ages across 0…max_age−1 in agent-id order**,
automatically, no parameter. Rationale: a fixed-lifespan population at steady
birth rate has a uniform age distribution in equilibrium, so staggering starts
the run at demographic steady state instead of a colony-ship moment where the
whole founding cohort dies simultaneously at generation max_age. (Synchronized
cohort = future option.)

### Agent identity — passport ids (FROZEN)
- **Never reused, monotonic counter.** Newborns numbered in parent-id order.
  Every agent records **`parent_id`** (founders: none).
- Enables M15 inheritance/lineage; makes per-agent charts/persistence honest
  (no hotel-room splicing of unrelated creatures).
- **Free summary stat:** largest id ever issued = `total_agents_born`. The run
  summary surfaces **`total_agents_born`** and **`population_final`** (the natural
  headline numbers for a growth economy; drop out of the id contract for free).

---

## 8. Calibration readout — IN M10a (FROZEN)

A pure config→numbers function, **Streamlit-free and unit-tested** (the #38/#48
helper pattern), rendered in the app's Economy panel. Close to load-bearing, not
a nicety: app-first validation ("set up an economy, observe growth") is
impossible to do honestly if the person can't see where the survival window is.

Shows, derived straight from the config:
- expected matches/agent (N−1 round-robin, ≈2k random_k), expected rounds/match
  (fixed r, or 1/(1−w) continuation),
- all-C income, all-D income, total cost at that participation,
- **verdict line**: "a cooperator nets +X/generation, a defector nets −Y/generation",
- **the window** bounds (all-D income ≤ L < all-C income),
- when `capital_return_rate > 0`: **escape velocity `e* = costs / r`**,
- when `max_age > 0`: **generations-to-θ** from `initial_energy` vs lifetime;
  expected offspring count; effective-max-age warning if senescence override.

**Calibration principle (goes in explainer):** a living-cost number is meaningless
alone; it only means something relative to income, which depends on payoffs,
rounds, and matches played. Under **round-robin, income scales with N**, so any
fixed L *decalibrates itself as the population grows* (the window moves). Under
**random_k, interaction budget is bounded (≈2k) independent of N**, so the window
stays put — which is why **random_k is the economy's natural matcher** for
large/variable-N work. (Same conclusion the vectorization evidence reaches, §9.)

---

## 9. Vectorization verdict — trigger NOT fired (measured)

Bench run (`python -m pdsim.bench`, random_k, `--rounds 10 --k 8 --generations 5`):

| N | s/gen | ratio vs previous |
|---|-------|-------------------|
| 500 | 0.2894 | — |
| 1000 | 0.5847 | 2.020× |
| 2000 | 1.1888 | 2.033× |

**Linear in N** (O(N·k), as #57 predicted). **Validated cost model:**
`s/gen ≈ 7.5 µs × N × k × rounds`. Cross-check: this run → 7.3 µs/round-play;
the #65 baseline (N=100, k=5, rounds=50, 0.19 s/gen) → 7.6 µs/round-play. Holds
within ~4% across 20× N, different k, 5× rounds.

Normalized to bench defaults (k=5, rounds=50): N=1000 ≈ **1.8 s/gen** (~6 min for
200 gens); N=2000 ≈ 3.7 s/gen; N=5000 ≈ 9.4 s/gen. round_robin at N=1000 ≈ 180
s/gen (100× random_k) — **the wall was round_robin's N², not the engine.**

**Verdict:** the object-per-agent engine is not the constraint; thousands of
agents are available today, headless, via random_k. Vectorization stays **M18,
review-at**. (Would have promoted immediately had the machine contradicted the
extrapolation; it didn't.)

**Consequences to fold into M10a docs:**
- **Correct DESIGN §3.1**: its "N≥1000 → too slow" is true only for round_robin
  at 50 rounds; state the envelope *per matcher*, cite the cost model, note
  large-N is a headless/sweep product while live-viz stays low hundreds (#10 —
  a rendering limit, not an engine limit).
- The scale story is now **three multiplicative knobs (N, k, rounds)**, two of
  them scientific choices — put in the explainer's calibration section.
- **M10a obligation:** re-run the bench under the economy at a couple of N values
  (variable N + energy/mortality/birth bookkeeping change the cost profile).
  M9b-Task-5 discipline; #65's noise warning applies (repeat before trusting a
  delta).
- **Memory is unmeasured** at N=2000 × 8-core sweeps. If big-N sweeps disappoint
  despite good single-run numbers, suspect runner memory pressure — a different
  fix than vectorization.

---

## 10. Milestone renumbering (agreed in substance; to be logged)

Sequential, no gaps, execution-order = numeric-order. **New DECISIONS entry
carries this table and states it supersedes the *numbering* (not the substance or
rationale) of #58 and #75. Append-only: #58/#75 are NOT retro-edited.**

| Exec order | Milestone | OLD label | NEW label |
|---|---|---|---|
| 1 | Growth economy (M10a sync, M10b async) | M10 | **M10** |
| 2 | **Population structure — adjacency + local birth** (NEW) | — | **M11** |
| 3 | Tags / attributes | M12 | **M12** |
| 4 | Sweep browser | (unnumbered) | **M13** |
| 5 | Perturbation mutation | M11 | **M14** |
| 6 | Economy policy (tax / redistribution / immigration / inheritance) (NEW) | — | **M15** |
| 7 | Public Goods Game + group matching | M13 | **M16** |
| 8 | Reputation / punishment / exclusion | M14 | **M17** |
| 9 | Vectorized engine (review-at) | (unnumbered) | **M18** |

Spine: **M10 → M11 → M12 → M13 → M14 → M15 → M16 → M17 → M18.** The old #58
M12-before-M11 "deliberate swap" **dissolves** (numbers now match order); tags
keeps its M12 label (spares cross-reference churn). Population structure placed
*before* the sweep browser by #75's own logic: the browser is a read-only view
over run data, and structure changes what run data exists — build it after
structure so it's structure-aware from birth (the same argument #58 used to put
tags after M10).

Docs the prompt must update: ROADMAP (rewrite + a top "Renumbering note" section
reproducing the table and pointing at the DECISIONS entry), CLAUDE.md
current-phase line, DESIGN §6 cross-refs, and the M10a spec header (note the
scheme + the pinning DECISIONS entry).

---

## 11. M10a obligations toward M11 (structure) — build-nothing-that-blocks

M11 = **population structure** (Hammond–Axelrod viscosity prerequisite). Owner's
confirmed tweaks make it richer than a bare lattice:
- **(a)** structure is an *option*, default `well_mixed`, lattice one choice.
  → M10a's placement is the *first real* `well_mixed` mode, not a stub.
- **(b)** random walk (a `MovementRule`, already committed in §6.3 / #46) with a
  walk-radius parameter — understood/documented as a **viscosity dial** (radius 0
  = viscous/pure H-A, large = well-mixed).
- **(c)** birth radius = **natal dispersal**; same underlying mixing quantity from
  the natal end. (b) is adult mixing, (c) is natal mixing — mechanistically
  distinct, not independent forces.
- Keep the **hard local density-dependence** (birth blocked when neighborhood
  full) as a first-class setting (radius 0 = pure H-A); the radii *soften* it.
  This constraint is THE reason spatial ≠ well-mixed; soften it all the way and
  you've paid for a lattice and recovered the well-mixed model.

**Therefore M10a must (cheap now, expensive later):**
1. Isolate **offspring placement** in one named function (well_mixed = "join the
   population"). No speculative ABC (rule 6: M11 updates DESIGN first).
2. Isolate **capacity admission** in one named function.
3. Name **K's scope** as aspatial (§7).
4. Order birth steps **check placement → pay σ** (§5).
5. Well-mixed = degenerate structure ("everyone is everyone's neighbor"); M11
   *generalises* M10 — every M10 result stays valid as the fully-connected corner.

**Flag for the literature pass:** aspatial M12 tags alone likely will NOT
reproduce the H-A ethnocentrism result — viscosity (local reproduction) is the
mechanism, and it lives in M11, not M12. Verify against the actual model.

---

## 12. Layman-explanation requirement (spec rule, FROZEN)

- **Registry parameters:** automatic & structurally guaranteed (DESIGN §5) — every
  parameter carries a plain description; the UI (?) tooltip is generated from it.
  All economy knobs get this free.
- **Spec rule (the extension owner asked for):** every new **concept**, every
  **enum VALUE** (e.g. `energy_economy` vs `imitation` each need their own
  explanation, not just the enum parameter), and every **derived readout
  quantity** (the window, escape velocity, generations-to-θ, effective max age)
  carries an inline (?) drawn from a single described source, so app text and docs
  can't drift.
- **The M10 explainer** carries the long-form version.
- **The prompt must include an explicit checklist task** enumerating every new
  term requiring a (?), so it's verifiable not aspirational.

---

## 13. Full frozen parameter set (M10a)

All nuance knobs default to their neutral value → out-of-the-box M10 is the clean
immortal-unless-insolvent flat economy; every refinement is opt-in.

| Key | Meaning | Default |
|---|---|---|
| `dynamics.reproduction_mode` | `imitation` \| `energy_economy` (latter greys SelectionRule family) | `imitation` |
| `dynamics.reproduction_threshold` (θ) | energy bar to be eligible to reproduce | (set at spec time) |
| `dynamics.offspring_stake` (σ) | energy transferred parent→child; σ ≤ θ | (set at spec time) |
| `dynamics.initial_energy` | seed agents' starting energy | **= σ** |
| `dynamics.basic_living_cost` | flat cost per agent per generation | (see §10 open item) |
| `dynamics.engagement_cost` | cost per match played | **0** |
| `dynamics.reproduction_overhead` | extra parent pays beyond σ | **0** |
| `dynamics.capital_return_rate` | multiplicative return on carried-in balance | **0** |
| `dynamics.carrying_capacity` (K) | hard population cap | (set at spec time) |
| `dynamics.base_hazard` | age-0 death probability | **0** |
| `dynamics.senescence_factor` | per-age hazard multiplier | **auto** (→1.0 unless base_hazard>0 & max_age>0) |
| `dynamics.max_age` | hard age cap (p=1.0) | **0** (no cap) |

**Ledger:** sources = payoffs, capital return. Sinks = basic living cost,
engagement cost, reproduction overhead, estate destruction on death. Transfers =
offspring stake.

---

## 14. Open items (carry forward)

1. **`basic_living_cost` default** — compute via the window rule (midpoint of
   all-D and all-C income at the default scenario's N/matcher/rounds) rather than
   assert a literal? Needs the default scenario's actual numbers. Decide at spec
   time.
2. **Mortality parameter names** — `base_hazard` / `senescence_factor` / `max_age`
   (current) vs plainer `youth_death_chance` / `aging_factor` / `max_age`. Minor;
   owner never objected to current. Confirm at spec time.
3. **θ, σ, K sensible defaults** — set at spec time with a worked calibration so
   the default config actually grows.
4. **Renumbering table** — agreed in substance; formalize in the DECISIONS entry.
5. **M10b (async/Moran)** — entirely deferred; separate spec, separate
   conversation.

---

## 15. REMAINING DESIGN WORK — "step 5" (do this in the next conversation)

The last design piece before a spec can be written. Inputs are the frozen
decisions above + the project docs (#47 schema-guard pattern, DESIGN §4 event
payloads, #57 random_k) — NOT this conversation's argumentative memory, so it
transfers cleanly.

1. **Matchers under variable N.** random_k validation `k ≤ N−1` when N *shrinks*
   below k+1 mid-run (clamp? skip? error is wrong for a runtime condition);
   RoundRobin under variable N; RNG draw-order under a changing agent set (ids are
   passport/stable, which helps).
2. **Event-payload changes.** Period events must carry per-agent **id, parent_id,
   age, energy**; a **population-size series**; possibly explicit **birth/death
   events**. Decide granularity. `total_agents_born` / `population_final` in the
   summary.
3. **Persistence schema bump** (#47 pattern): new `schema_version`; loaders accept
   old versions backward-compatibly (a pre-economy run has no energy/age columns
   and renders without them — no migration, no error).
4. **Placement / admission function isolation** (§11 obligations 1–2) — the exact
   seam shape.
5. **Verify (don't assume): matches_played per agent** is available at the
   energy-update step. Per #44, `rounds_played` exists in period events; whether
   the *match* count is tracked per agent must be checked in code.
6. **Birth-step ordering** (check placement → pay σ) — confirm where it lives.

After step 5: the **literature verification pass** (§16), then the **M10a Claude
Code prompt** (spec-creating + implementing, app-first Validation section), then
the **companion explainer** content.

---

## 16. Literature verification to-do (territory only — NOT yet verified)

Do a real web-search verification pass in the design chat; hand Claude Code
*verified* citations. NO fabricated references. Candidates by topic:

- **Epstein & Axtell, *Sugarscape*** — agents with an energy stock, metabolism
  draining it, death at zero, emergent wealth distributions, AND taxation
  experiments. Canonical precedent for nearly everything in M10.
- **Hammond & Axelrod, ethnocentrism model** — birth-death with accumulated
  reproduction potential, lattice + local (adjacent) reproduction, immigration
  built in. Directly relevant to M11, M12, and the owner's immigration interest.
- **Moran process** — for M10b.
- **Nowak** — mechanisms for the evolution of cooperation.
- **Riolo (et al.), tags** — for M12.
- **Gompertz (1825)** — hazard rising ~exponentially with age (senescence); the
  mortality model's grounding.
- **Logistic / density-dependence tradition** — the soft-capacity ("living cost
  rises as N→K") future note.
- **Natal dispersal (ecology)** — for M11's birth-radius knob.

---

## 17. Explainer structure (committed) — `docs/explainers/M10-growth-economy.md`

Undergraduate-just-meeting-game-theory pitch; full prose, worked arithmetic,
jargon unpacked on first use. Sections:

1. **Two paradigms** — imitation vs birth-death; why the economy *replaces*
   copying; why H-A is birth-death and that puts M10 on M12's rails.
2. **Why cooperation is thermodynamic** — positive-sum vs near-zero-sum; the
   metabolic filter; the honest "doesn't repeal the PD" caveat.
3. **The open-flow ledger** — sources / sinks / transfers; where every unit goes.
4. **Calibration & the window** — the all-D/all-C bracket worked; round-robin
   self-decalibration; random_k as the natural matcher; escape velocity;
   the three-knob (N, k, rounds) scale story.
5. **Every parameter** — mechanism, what it models, what it can't: θ (capital
   bar), σ (inheritance dial: σ→θ dynastic, σ=0 from-scratch), the
   flat/engagement split (marginality dial → immigration, small communities),
   capital return (wealth-without-behavior, rentier threshold), K + admission
   (concentration engine + the interest×admission dynasty note), mortality trio.
6. **Designed-for, not built** — taxation & redistribution as sinks-and-transfers
   (M15); immigration as arrivals (M15; M10 makes it a one-line op); proselytizing
   religion via TWO channels — the *demographic* channel (differential fertility)
   is reachable with M10+M12 near-term, the *conversion* channel is a separate
   future **horizontal-transmission** mechanism distinct from reproduction (note:
   conversion *is* imitation — the mechanism removed from reproduction — so
   "energy-replaces-imitation" left clean room for it); density-dependent living
   cost as soft logistic capacity; wealth-buys-in-match-advantage as a deliberate
   non-feature (until capital_return_rate, the one coupling deliberately added).
7. **Literature grounding** — verified citations from §16.

---

## 18. Owner's downstream modeling ambitions (design pressure, don't build)

Recorded so M10a/M12 don't foreclose them:
- **Immigration** → M15 (exogenous arrivals; a population-level policy).
- **Capitalism nuances** → mostly already expressible (energy = wealth, compounds
  via reproduction; θ = capital bar; σ = inheritance; flat cost = regressive tax;
  capital_return_rate = returns on capital). Wealth-buys-in-match-advantage is a
  deliberate non-feature.
- **Taxation loopholes benefiting the rich + closing them** → M15
  (`FiscalPolicy` — the registry idiom's 5th instance: progressive/marginal/
  wealth-vs-income schedules as sinks; redistribution as transfers).
- **Proselytizing religion** → demographic channel near-term (M10+M12); conversion
  channel a separate future horizontal-transmission milestone.
- **Inheritance / kinship** → M15 (`InheritancePolicy` ABC: kinship depth, split
  rule, no-heir disposal + inheritance tax), riding the `parent_id` lineage M10a
  lays down. M10a ships the 100%-tax corner (estate destroyed).
```
