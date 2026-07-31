# CLAUDE CODE PROMPT — M11a, PROMPT 1A: CREATE THE SPEC (PART 1 OF 2)

## What this prompt does, and what it must not do

**Create exactly one file: `docs/specs/M11a-population-structure-spec.md`.**

Write **no code**. Add **no registry entries**. Write **no tests**. Change **no
other file** — not `DESIGN.md`, not `DECISIONS.md`, not `ROADMAP.md`, not
`PARAMETERS.md`, not `CLAUDE.md`. Do not run `python -m pdsim.gendocs` (nothing
in this prompt touches the registry). Do not run `pytest` (nothing changed).

This is **part 1 of 2** of the spec. This prompt carries the spec's model and
machinery: the status header, Frozen intent, Defining principles, Design 0
through Design 10, and the four verification tasks.

**Prompt 1B** (a separate prompt, after I review your handback) appends the
parameter surface and everything that verifies it: Design 11 (registry shape,
section order and the greying map), Design 12 (`site_capacity` pinned at 1),
the Parameters table, the Phase plan with its risk reading, the §12 checklist,
the Validation section with its scenarios and bench, the out-of-scope section,
and the docs obligations.

Because the spec is being written in two passes, **the file must not be able to
masquerade as complete**. Its status line and its closing stub are specified
below and are mandatory.

## Read these first — do not rely on recall

- `docs/DESIGN.md` §2.12 in full (this is M11a's design brief), plus §6.3,
  §2.10, §3.1, §4, §5.
- `docs/DECISIONS.md` #103–#110 in full, plus #34, #42, #47, #57, #61, #62,
  #65, #67, #78, #80, #81, #83, #89, #92, #94, #99, #100, #101, #102.
- `docs/specs/M10b-async-event-time-spec.md` — **its structure is the model for
  this spec.** Match its shape: a status line, a companion-explainer pointer, a
  read-first list, `## Frozen intent`, `## Defining principles` as a numbered
  list, numbered `## Design N — <title>` sections, a `## Parameters` table, and
  (in Prompt 1B) a phase plan with reset markers and a Validation section
  written at spec time.
- `docs/ROADMAP.md`'s M11a, M11b and M19 entries.
- `CLAUDE.md` — the hard rules, and the design-layer documentation contract.

## The register this spec is written in

The project owner is re-entering programming and is a novice at game theory.
Specs in this project are also read by external advisors who see **only** the
`docs/` files and never the code (CLAUDE.md's knowledge-preservation contract).

So: full prose reasoning, not terse shorthand. Unpack jargon on first use.
Where a decision had a live alternative, **state the alternative and why it
lost** — the rationale is the content, not decoration around it. Where a number
or a mechanism is easier shown than described, show it (a worked degree count,
a small grid sketch in a fenced block). Do not compress the rationale to save
space; this spec is allowed to be long, and it will be longer than M10b's.

**Everything below is FROZEN.** It was settled in a design conversation on
2026-07-30 that is not yet reflected in `docs/`. Write it into the spec as
settled design. Do not re-derive it, do not re-open it, and do not substitute
your own judgement for it. If you believe something below is wrong or
internally inconsistent, **write the spec as specified and raise the concern in
your handback** — do not silently correct it.

Two forward-pointers that matter for how you word things: **M11b** is agent
movement plus the mouse layout painter, and **M19** is geographic structures
(irregular site sets from GeoJSON or rasters). Several decisions below exist
specifically to make those two additive rather than migrations, and the spec
should say so where that is the reason.

---

# THE SPEC CONTENT

Write the file with the sections below, in this order.

## Status line and header

The first line of the file, exactly:

```
Status: draft — INCOMPLETE, awaiting Prompt 1B (registry shape and greying map, site_capacity, parameters table, phase plan, §12 checklist, validation, scenarios, bench, out-of-scope, docs obligations)
```

Then the title `# M11a — Population structure (sites, local birth, local
interaction)`.

Then a companion-explainer pointer, worded to record that the explainer does
**not** yet exist: it is a separate prompt that follows a literature
verification pass, and two claims flagged UNVERIFIED in #103 gate it — whether
Hammond & Axelrod used wrap-around on their 50×50 lattice, and the Kaznatcheev
& Shultz 300-period figure that the M10 explainer currently quotes without a
verification note of its own.

Then a read-first list naming the DESIGN sections and DECISIONS entries listed
above, in the M10b spec's style.

Then a "Depends on" line: M10a (#76–#84) and M10b (#93–#102), both shipped.
State the scope boundary explicitly — M11a is structure, local birth and local
interaction; **movement, the `MovementRule` ABC, the walk radius/decay pair,
the movement schedule and the mouse painter are M11b**; irregular and
geographic site sets, per-site capacity above 1, and co-residency semantics are
**M19**.

## `## Frozen intent`

M11a gives the world a **shape**. Until now every agent could meet, breed
toward, and be replaced by every other agent; the population was a list.
M11a makes it a set of **sites**, where a site is an exclusive container, an
agent occupies exactly one, and both who you play and where your children land
are decided by how far away things are.

The default is unchanged behaviour: `structure.kind = well_mixed` is the
existing aspatial world, recovered as the **degenerate fully-connected corner
of the same abstraction rather than as a separate code path**, and byte-identical
to today on every existing seeded run.

Three things arrive together and the spec should say why they are one milestone
rather than three: a **structure** (which sites exist and which are adjacent),
**local birth** (a child is placed in an empty site within reach of its
parent), and **local interaction** (you play your neighbours). Local birth
without local interaction, and local interaction without local birth, are both
legitimate configurations — that separability is the point of parameterising
the reach kernel twice — but the *structure* has to exist before either is
expressible.

State the research payoff plainly: this is the milestone after which
**cooperation can survive by clustering**. A cooperator surrounded by
cooperators earns the reward payoff from every neighbour; a defector in a
defector interior earns the punishment payoff from everyone. That is spatial
reciprocity, and it is the mechanism the whole M12 ethnocentrism programme is
built on top of.

## `## Defining principles`

Write these as a numbered list, each with a sentence or two of justification.

1. **The well-mixed path is byte-identical.** `structure.kind = well_mixed` is
   today's engine. Every new RNG draw is gated so that it does not happen when
   structure is off (the #80/#99 active-flag idiom). This is pinned by negative
   golden masters, not merely intended.
2. **Same seed, same run** (hard rule 5). Every new draw has a pinned position
   in the ordering and a stated gate. Any change to those is a breaking change
   requiring a DECISIONS entry.
3. **The core abstraction is a graph of sites, never a rectangle** (#104). The
   rectangular lattice is *one builder* over that abstraction. The core never
   knows about rows and columns, and distance is a method the **structure**
   supplies rather than a constant the kernel assumes. This is the forward-guard
   that makes M19 a second builder instead of a rewrite.
4. **Topology is immutable; occupancy is mutable.** `Structure` is a pure value
   derived once from the config. `Occupancy` is per-run simulation state owned
   by the dynamics. Keeping them apart is what lets the topology be shared,
   cached and precomputed.
5. **Everything id-ordered, explicitly** — now sites as well as agents. The #80
   invariant extends: candidate site lists are built in ascending site-id order
   before any draw. Deterministic tie-breaks are always (value, id ascending),
   never a random draw.
6. **A parent must clear both gates.** `admit_births()` is the global gate,
   `place_offspring()` is the local one, and clearing one is not clearing the
   other. Place-before-pay (#80) becomes load-bearing for the first time.
7. **One kernel, parameterised per use.** There is a single functional form for
   reach; birth and interaction each get their own radius and decay, and M11b
   adds a third pair for the walk.
8. **Novice-legibility is a shipping requirement, not polish** (design-freeze
   §12, restated by #103). Roughly fifteen parameters arrive at once. Every
   concept, every enum value individually, and every derived readout carries an
   inline explanation drawn from a single described source, and the spec
   enumerates them as a checklist so the obligation is verifiable rather than
   aspirational.

## `## Design 0 — the graph of sites`

The `Site` record: an **id**, a **neighbour set**, a **capacity**, and an
**optional coordinate**. The coordinate is optional precisely because M19's
site sets may have no natural grid position; the lattice builder fills it, and
the renderer uses it, but nothing in the core requires it.

`Structure` is the abstraction: the set of sites, the neighbour relation, and a
`distance()` method.

Two builders ship:

- **`WellMixedStructure`** — the degenerate case. Every site is adjacent to
  every other; this is the fully-connected corner. Write down explicitly that
  the well-mixed engine does not route through structure code at all in M11a
  (nothing imports it on that path), so this builder exists to make the
  abstraction honest and to be the thing M19 and future work can reason
  against — not as a live execution path that would jeopardise byte-identity.
- **`LatticeStructure`** — the rectangular builder: rows, columns, a
  neighbourhood shape and a boundary rule.

**Distance is structure-supplied.** `neighbourhood_shape = moore` means the
**Chebyshev** distance (the larger of the two coordinate differences);
`von_neumann` means the **Manhattan** distance (their sum). Explain both with a
worked example, and make the key consequence explicit: because the shape *is*
the metric, and the metric is handed to **both** kernels, `neighbourhood_shape`
governs birth reach and interaction reach together rather than being a separate
knob for each.

## `## Design 1 — lattice geometry and the derived defaults`

**`structure.rows` / `structure.cols`.** Blank resolves to the **most-square
factor pair of N** — the #78 derived-default idiom. Note the edge case that
matters: a prime N factorises to a 1×N line, which is a legitimate
one-dimensional lattice but one **the app must announce rather than let look
like a bug**.

**`structure.boundary` ∈ {`torus`, `bounded`}, default `torus`.** Torus wraps:
the left edge is adjacent to the right, the top to the bottom. It is the
default because **uniform degree removes an edge artifact** — on a bounded grid
a corner cell has 3 neighbours under Moore and an interior cell has 8, and
since cooperation thresholds on graphs depend on degree, corners become
spuriously favourable to cooperation. `bounded` ships anyway because at M19 a
coastline is a real hard edge and varying degree is then the model rather than
an artifact.

Give the degree table concretely, since it is what the Phase A tests assert:
under Moore, interior 8 and corner 3 when `bounded`, uniform 8 under `torus`;
under von Neumann, interior 4 and corner 2 when `bounded`, uniform 4 under
`torus`.

**Carrying capacity survives under structure as a second, tighter cap** (#106,
resolving §2.10's "may become emergent" open line). Validator: **K ≤ site
count**. A blank K under a lattice resolves to the site count (the #78 idiom
again), making "the grid decides" the zero-effort path. A K *below* site count
leaves deliberate slack — a 20×20 grid at K = 250 runs at roughly 60 %
occupancy — in which the occupied region can drift, cluster and migrate. The
Economy panel must report **both numbers** so that slack is visible rather than
reading as a mysterious stall.

**Under `fixed_n`, N = site count exactly** (validated). Every site is
occupied, so a death leaves exactly one empty site and the newborn has nowhere
else to go: **site recycling is the only possible Moran placement**, which
makes the textbook death-birth corner structural rather than a rule we impose.

## `## Design 2 — the reach kernel, and the one primitive`

**One functional form** (#105). The weight over a site at distance *d* is
proportional to **exp(−β·d) for d ≤ R, and zero beyond**, where **R** is a
*support radius* and **β** a *decay*. Say explicitly that this supersedes the
M10b forward-note's single-temperature phrasing (M10b spec Design 9, explainer
§7), which was loose: sharpening a decay recovers nearest-neighbours-only, not
a hard-edged disc.

Give the four corners, since they are what the Phase A kernel tests assert:

- **R = 1** is Hammond–Axelrod exactly.
- **β = 0 with R = n** is a uniform disc — the "hard cutoff" the old note
  reached for.
- **large β with R = n** is steeply viscous, with distant sites still reachable
  but very unlikely.
- **R → ∞ with β = 0 is well-mixed**, recovered by *parameters* rather than by
  a branch.

M11a parameterises the kernel twice — `birth_radius`/`birth_decay` and
`interaction_radius`/`interaction_decay` — and M11b adds a third pair for the
walk. Two radii rather than one is what makes local-births-with-global-interaction
and global-births-with-local-interaction **separable experiments**.

### One primitive, not four

All four call sites — sync placement, sync interaction, the async partner draw,
and the async `fixed_n` breeder/victim draw — run the *same* algorithm:
enumerate the sites within R of an origin, filter to an eligible set, weight by
exp(−β·d), and draw without replacement. Only the eligible set and an optional
second weight vary. So there is one function:

```python
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
```

Pin the semantics in the spec:

- **`eligible` is an explicit frozen set, not a predicate callable.** The caller
  already holds the occupancy map, and a set is trivially inspectable in a
  failing test where a closure is not.
- **`radius=None` means unlimited reach**, matching the nullable parameter.
- **`site_weights` is the optional second weight.** The combined weight on a
  site is `exp(−β·d) * site_weights[site]`.
- **Returns fewer than `size`** when fewer sites are eligible (the #81 clamp
  idiom).
- **Returns an empty tuple** when none are eligible — this is
  `place_offspring`'s failure signal.

Underneath sit two functions that are **pure and RNG-free**:
`sites_within(structure, origin, radius)` and
`kernel_weights(structure, origin, sites, decay)`. These are what the
kernel-corner tests exercise directly, and they are the surface M19 must
satisfy.

**Determinism rule — state this as a rule, not as advice.** The candidate list
is built in **ascending site-id order before any draw**. This is #80's
"everything id-ordered, explicitly" applied to sites instead of agents. Without
it the draw depends on set iteration order, which is a reproducibility bug that
survives every test until a Python version changes.

Record that **#103's obligation is satisfied**: `neighbourhood_sample` is the
named public function, so M11b's movement is purely additive and never reopens
structure code.

## `## Design 3 — the topology / occupancy split`

These are **separate objects**, and the spec should say why that is
architectural rather than stylistic.

- **`Structure` is immutable**: sites, neighbours, `distance()`. Derived once
  from the config; shareable and cacheable. This is what M19 reimplements as a
  second builder.
- **`Occupancy` is mutable per-run state owned by the dynamics**, exactly like
  the population list: site → agent id, agent id → site, with `occupy()`,
  `vacate()`, and `empty_sites_within()`.

The split is what lets `LatticeStructure` be a pure value with no simulation
state in it, and **it is the difference between M19 writing a builder and M19
writing an engine**. It is also what makes the Phase E precomputation possible:
because topology is immutable, the candidate list for each site at each radius
is a pure function of the config and can be built once, and because weight
depends only on distance, one distance→weight lookup table per (R, β) pair
covers every site on the grid.

## `## Design 4 — the two gates`

**`admit_births()` is the GLOBAL gate**: are we under carrying capacity,
rationed by energy priority when seats are scarce. **`place_offspring()` is the
LOCAL gate**: is there an empty site in reach, sampled by the birth kernel and
contested per Design 5. **A parent must clear both, and clearing one is not
clearing the other** — this is one of the fourteen concepts §12 requires an
explanation for.

**Place-before-pay (#80) is load-bearing at last.** A parent that cannot place a
child pays **no stake** and stays eligible next period. Until now this branch
was checked against a stub that always returned true; under structure it goes
live.

Spell out the behavioural consequence, because it is the single most likely
thing to be misread as a bug: a parent **walled in by occupied neighbours pays
nothing, stays eligible, and keeps accumulating energy**. An agent sitting at
five times the birth threshold and not breeding is *correct* — it is the whole
content of viscosity — but it reads as a defect unless the app says so. The
Economy panel therefore reports **blocked parents this generation**, on the
#89(e) logic that put the calibration readout into M10a. Mark this as a **Phase
C deliverable**, not a Phase E nicety.

## `## Design 5 — birth contention, the contest, and boundary order`

This section **amends the #80 frozen sequence**; write it as an amendment and
carry #107's reasoning.

**Contention exists only where several births resolve at one instant**:
**synchronous + structure + `energy_economy`**, and nowhere else. Async resolves
one birth per event; `fixed_n` never calls `admit_births` (#97d); sync
well-mixed placement never fails. State plainly that **the correctness of this
confinement is an argument, not a test** — which is why the exclusions get
no-draw assertions rather than mere reproducibility checks.

**`structure.placement_contest` ∈ {`random`, `energy_priority`}, default
`random`.** Under structure the admitted birth set is resolved by **one
permutation, then iterate** — matching Hammond–Axelrod's random reproduction
order, and keeping energy's role at *eligibility* (the θ threshold) rather than
at *winning a contested cell*. **Parent-id order is rejected**: on a lattice,
id correlates with founding position, so ordering by id silently becomes a
spatial priority rule. The shuffle is gated by the structure flag, so
well-mixed sync runs draw no extra RNG and stay byte-identical.

**`dynamics.boundary_order` ∈ {`death_first`, `birth_first`}, default
`death_first`.** This exposes Hammond–Axelrod's period order as an option.
Under a lattice it is **not a phase offset but a different model**, because it
decides whether newborns fill scattered interior graves (deaths first) or only
frontier cells (births first) — and the frontier is where the ethnocentrism
mechanism lives. A bug here produces **plausible dynamics rather than a crash**:
a frontier that behaves like an interior, which is precisely the mechanism M12
is being built to study.

**`boundary_order` is live under ALL synchronous runs and greyed only under
async.** Write the reasoning in, because the naive reading is that it should
grey under well-mixed:

- #107's own text says "sync-only, greyed under async" and stops there. Greying
  it under well-mixed would add a restriction the decision did not make.
- **It is not inert under well-mixed.** Under `death_first`, deaths finish
  before any child exists, so a newborn is guaranteed to survive to the next
  generation. Under `birth_first`, the child is created and *then* the death
  phase runs, so a newborn faces the age-mortality coin immediately and can die
  in the period it was born in. That is Hammond & Axelrod's ordering and a
  genuine difference in infant survival.
- #34 reserves greying for parameters consumed **nowhere**.
- The errors are asymmetric: showing a parameter whose effect is small is mild
  noise, whereas greying one that has an effect is **the app asserting
  something false about the user's run**.
- **VT-4 may add a second, larger effect** — see the verification tasks section.

## `## Design 6 — local interaction`

**`matching.spatial_interaction` (bool, default off)** (#108). Off: today's
behaviour, with `matching.matcher` picking round-robin or random-k over the
whole population. On: partners are sampled from within the interaction radius
by the reach kernel, and **`matching.matcher` greys** — round-robin has no local
analogue, and the well-mixed matchers are the infinite-radius corner.

**`matching.opponents_per_agent` (k) stays LIVE and does the work.** k at or
above the neighbourhood size means "play all neighbours", which is the
Hammond–Axelrod and Ohtsuki convention — so **round-robin's idea survives the
greying** even though the matcher does not. k **clamps** to the number of
neighbours that actually exist (the #81 clamp idiom): edge cells under
`bounded`, and irregular site sets at M19. Validator: spatial interaction
requires `structure.kind = lattice`.

**`SpatialKernel(Matcher)` is genuinely thin.** It holds the structure, the
occupancy, the radius, the decay and k. `pairings()` walks agents in ascending
id, calls `neighbourhood_sample` once per focal with `size = k` and `eligible`
= occupied sites minus self, and maps sites back to agents.

**Two behaviours are inherited deliberately from `RandomK`** — say "deliberately"
in the spec, because both look like defects on first reading:

1. **No deduplication.** A can draw B while B draws A, so a pair can meet twice
   in one generation. This is existing `RandomK` behaviour and it is the source
   of the `len(agent._histories)` sharp edge already in the codebase.
2. **Clamp, not error**, when k exceeds the neighbourhood.

**Fork resolved — draw unconditionally.** Whenever spatial sampling is active,
the draw happens **even when k ≥ neighbourhood size and the outcome is forced**.
The cost is a wasted permutation in the "play all neighbours" configuration,
which is the H-A convention and therefore common. The benefit is that **the
stream position is predictable from the config alone** (#80's active-flag
idiom). A wasted draw costs nothing; a golden master that shifts when a
neighbourhood happens to be full costs a debugging afternoon.

## `## Design 7 — where the breeder comes from (Open Question 1, resolved)`

#106 settles where the offspring **goes** under `fixed_n` + lattice. It does
**not** say where the **breeder** comes from, and M10b draws the `fixed_n`
breeder fitness-proportionally over the **whole living population**. State the
problem before the answer: if that stays global under a lattice, the number of
competitors for a seat is N−1 rather than k — and **Ohtsuki's b/c > k threshold
has k in it precisely because k counts the competitors for a vacated site**.
Keep the draws global and the Moore-versus-von-Neumann scenario demonstrates
nothing.

**DECIDED: localise the async `fixed_n` breeder and victim draws under a
lattice**, with the **birth kernel** supplying the candidate set — read from the
**freed site's** side under `death_birth`, and from the **breeder's** side under
`birth_death`.

**DECIDED: sync IMITATION's `SelectionRule` stays GLOBAL under a lattice for
M11a.** Record this as an **explicit decline on scope grounds — not an omission
— and hand it to M12**, which needs in-group/out-group strategy spread anyway.
This is the shape #110 used for the imitation-adopter checkpoint.

**Fork resolved — MULTIPLY.** The Moran breeder draw's weight is
`exp(−β·d) * fitness`. At R = 1 all distance factors are equal and it reduces to
**exactly** fitness-proportional, so **Ohtsuki is recovered as a corner rather
than approximated**. The existing non-negative fitness shift applies **before**
the multiplication, and the uniform fallback triggers on the **combined**
vector.

**Documentation obligation — the rationale must be reachable from the UI, not
only from the explainer.** §12's rule is that each concept's explanation comes
from a single described source, so app text and docs cannot drift. Three places:

1. **`structure.kind`'s `lattice` value** states that a lattice makes
   interaction and natal placement local, **and** that in synchronous imitation
   mode the comparison partner is still drawn from the whole population.
2. **`structure.birth_radius` and `birth_decay`** state that under `fixed_n`
   these define the **set of competitors for a freed site**, which is what the
   b/c > k threshold's k counts.
3. **A derived readout for effective neighbour count** gives that k a visible
   number.

The long-form version, including the b = 5 / c = 1 walkthrough, belongs in the
explainer and is out of scope for the spec.

## `## Design 8 — initial layouts and the layout file`

**The divisibility problem dissolves: arrangement is DEALING, not
PARTITIONING.** #67 has already resolved composition to exact integer counts,
and §2.12 says the layout decides **arrangement only**. So the counts are
authoritative and the arrangement bends around them — the same philosophy as
largest-remainder rounding, one layer up. There is no "4 strategies don't
divide into 10 rows" problem because **nothing is being divided**. Say this
explicitly; it is the kind of thing a later reader will otherwise try to solve
again.

**Five algorithmic layouts are one engine**: walk the sites in some traversal
order and deal strategies out of the resolved counts until they are exhausted.
What varies is the traversal and the dealing discipline.

- **`stripes`** — row-major sweep, **run-length** dealing. A strategy with 39
  agents gets 39 consecutive cells; one with 2 agents gets 2. Stripe boundaries
  fall where the **counts** fall, so a "stripe" can be a fragment of a row. Say
  this in the help text rather than letting it look like a bug.
- **`blocks`** — run-length dealing along a traversal that keeps runs compact in
  two dimensions; a boustrophedon sweep over sub-blocks is enough. **No new
  parameter**, and it degrades gracefully at any count.
- **`checkerboard`** — **round-robin** dealing: one cell at a time, cycling over
  the strategies that still have agents left. With two equal-count strategies
  this reproduces the literal checkerboard; with four unequal ones it produces
  **maximal interleaving**, which is the purpose #109 assigns it — the
  anti-cluster baseline. **Generalise by purpose, not by appearance.**
- **`patches`** — one seed site per strategy placed by RNG, then multi-source
  growth outward with each strategy's quota as its budget. Deterministic given
  the seeds; **RNG enters only at seed placement**.
- **`random`** — shuffle.
- **`central_block`** — a centred rectangle sized to N, with the rest of the
  grid empty. This is the **filling regime** (#109).

**Deal order: ascending machine name**, reusing #67's tie-break convention so
there is **one** ordering rule in the project rather than two.

### When N is less than the site count

This cannot arise under `fixed_n` (N = site count by validator). It arises under
the economy and under `variable_n`. Then every layout needs a rule for **which
sites are occupied**, not only what is in them. `central_block` answers this
definitionally; the other five need a stated rule.

**DECIDED: `random` scatters over the whole grid; the patterned five use a
centred contiguous footprint.** Rationale: "random" should mean random, and a
scattered start is the closest thing to the well-mixed baseline.

**MANDATORY GUARD: the app reports the number of agents with zero occupied
neighbours at founding.** A scattered population under local interaction can
leave agents isolated; an isolated agent plays nothing, earns nothing, and
starves at the next boundary — correct by #81's lone-survivor logic, but
bewildering to watch. This turns the hazard into information, and it is a
derived readout requiring an inline explanation under §12 anyway.

### The layout file format

The requirements pull in opposite directions: hand-authoring wants a **picture**,
while #104's graph-of-sites forward-guard wants something that survives M19's
irregular site sets, where there are no rows and columns to draw.

**Resolution: one format now, versioned so the second is additive.** Plain text.
A header carrying a `kind:` line reading `lattice_grid`, plus `rows:` and
`cols:`. A body that is a character grid, one token per cell — strategy machine
names, or `.` for an empty site.

Validators: the header's dimensions must match the resolved `structure.rows` and
`structure.cols`, and every token must be a registered strategy.

M19 adds `kind: site_map` with a two-column site-id/strategy body, and the
reader dispatches on the header. Additive, no rewrite — and **the discriminator
ships from day one**, so there is never a file in the wild without one.

### Two consequences, both decided explicitly

1. **A layout file specifies composition implicitly** (it names a strategy per
   cell), so it can contradict the resolved #67 composition. **The file wins,
   and the composition widgets grey.** Requiring the user to separately
   reproduce counts they have already painted is a trap. **Validator: reject a
   layout file combined with a swept composition axis** — those two are
   incoherent together.
2. **The recorder must copy the layout file into the run folder.** A
   `config.yaml` referencing `layouts/my_painting.txt` violates hard rule 8 the
   moment that file moves. It is a two-line fix and it makes the run folder
   self-contained.

## `## Design 9 — the RNG reproducibility contract`

Open with **the finding**, because it is the reason this section is shorter than
feared: **most changes are SUBSTITUTIONS, not INSERTIONS**, because of an
asymmetry in Ohtsuki's two update rules that maps unexpectedly well onto M10b's
existing draw order.

- Under **death-birth**, a random individual dies and **its neighbours compete**.
  The victim draw is global and uniform — **unchanged** from M10b. Only the
  breeder draw localises.
- Under **birth-death**, a breeder is chosen by fitness from the whole
  population and the offspring replaces **one of its neighbours**. The breeder
  draw is global — **unchanged**. Only the victim draw localises.

So in each rule **exactly one draw changes, it is always the second of the two,
and it changes its candidate set and weights while keeping its position and call
shape**. Neither rule gains or loses a draw. The `moran_rule = random` roll keeps
its pinned position as the first demographic draw of the event, untouched.

### Full inventory

Present as a table with three columns — draw, kind, gate:

| Draw | Kind | Gate |
|---|---|---|
| Founding layout | NEW (once per run, before generation 0) | lattice + non-deterministic layout |
| Sync interaction partners | SUBSTITUTION (`SpatialKernel` for `RandomK`/`RoundRobin`) | lattice + `spatial_interaction` |
| Sync contest permutation | INSERTION (one permutation over the admitted set) | sync + lattice + `energy_economy` |
| Sync placement, per parent | INSERTION (at the placement check, before σ) | lattice + births exist |
| Async partner draw | SUBSTITUTION | lattice + `spatial_interaction` |
| Async DB breeder / BD victim | SUBSTITUTION | lattice + `fixed_n` |
| Async `variable_n` placement | INSERTION (same position as sync) | lattice |

**Three insertions.** The layout one sits **outside the per-generation order
entirely** (it happens at population construction), so it cannot perturb any
within-generation sequence. That leaves **two real insertions into
golden-mastered orders, both inside the birth step, both in Phase C**.

### Amended #80 step (6), births — as a DIFF, since #80 is frozen

- **CURRENT:** admission by energy priority (RNG-free) → admitted set iterated in
  ascending parent-id order → placement check → σ payment → passport id → μ draw.
- **AMENDED:** admission **unchanged** → **contest permutation over the admitted
  set, when the three-way gate holds** → iteration order is the permutation
  under `random`, energy-descending under `energy_priority`, and parent-id
  ascending when the gate is off → **placement check is now a kernel draw that
  can return empty** → **σ payment only on success** → passport id → μ draw.

### Amended #99 within-event order, `fixed_n` — as a DIFF

Rule roll **unchanged**. Under `death_birth`: victim draw **unchanged**, breeder
`rng.choice` now over the **freed site's neighbours** with combined weights.
Under `birth_death`: breeder draw **unchanged**, victim draw now over the
**breeder's neighbours**. Under `variable_n`: the placement check inside the
birth sub-step becomes a kernel draw.

### Three orderings now — and how they collapse

#80 keeps **admission order** (energy descending, id ascending) separate from
**iteration order** (parent-id ascending), pinned by a test where the two
differ. Phase C inserts a **contest permutation** between them, making three.

Name the specific bug so it cannot be rediscovered the hard way: **applying the
permutation to a list that has already been energy-sorted, and then iterating
it** — which yields a `random` contest that is quietly energy-biased in exactly
the way #107 rejected. The pin needs a fixture where **all three orders differ
pairwise**, which is harder to build than #80's two-way case, and **it should be
written before the code it tests**.

### Golden masters

**Four negative pins first** — these are what nothing else catches: sync
imitation, sync economy, async `variable_n`, async `fixed_n`; each well-mixed;
each byte-identical to its pre-M11a event stream **and** persisted folder.

**Four new positive goldens**: sync economy + lattice; async `fixed_n` + lattice
+ `death_birth`; async `variable_n` + lattice; sync imitation + lattice (the
interaction-only case).

**No-draw assertions**: no contest permutation under async, under `fixed_n`,
under sync well-mixed, or under sync imitation with a lattice.

**Technique — adopt this, and say why.** Byte-identical output *usually* catches
a spurious draw, because a shifted stream changes everything downstream — but
**not if the extra draw lands after the last consequential one**. A **counting
wrapper** around the `Generator` that records the exact sequence of method calls
turns "the output matched" into "the stream was identical", and makes the
no-draw assertions **directly expressible rather than inferential**. It is cheap,
and it is the mechanism the negative pins actually need.

## `## Design 10 — persistence (schema 5)`

**The simplification: in M11a agents never move.** Movement is M11b. So an
agent's site is fixed from birth to death, and occupancy at any period is fully
determined by founding placement plus the birth and death record — both already
persisted.

- **Site id becomes a single column on `agents.parquet`**, present when the run
  has structure and absent otherwise (#83's honest-presence rule exactly). **No
  new sibling table, no widened `timeseries.parquet`, nothing NaN-filled.**
- **`AgentSnapshot` gains `site_id: int | None`**, as DESIGN §4 already
  specifies. This is also what the live grid renderer reads.
- **`SCHEMA_VERSION = 5`**, written when structure data is present. Existing
  constants are untouched: well-mixed sync imitation still writes 2, well-mixed
  sync economy 3, well-mixed async 4, and **any** lattice run writes 5. The
  loader accepts 1–5 and rejects above.
- **State this in the spec so the ladder is not read as an implication:** a sync
  economy lattice run writes 5, a number that arrived with event-time data it
  does not have. This is already handled by #100(b), which makes
  missing-file-equals-empty-shape the **contract** rather than mere backward
  compatibility. The loader is **presence-driven, not version-driven**, so a
  monotone integer works.

### The conditional — resolved by VT-2

`agents.parquet` and `AgentSnapshot` exist only in economy mode; §4 says
snapshots are empty under imitation. So **sync imitation + lattice has occupancy
and nowhere to record it**. DESIGN §4's "AgentSnapshot gains a site id"
implicitly assumes structure + economy; imitation + lattice is a configuration
the design edit did not consider.

**The spec specifies both branches; Phase B establishes which is live.**

- **If ids are preserved across imitation generations:** nobody is born, nobody
  dies, and occupancy never changes after founding. It is entirely determined by
  the initial layout, which lives in the config, and re-running reproduces it
  exactly. **Nothing to persist**; the live renderer holds occupancy without any
  event carrying it.
- **If ids are not preserved:** occupancy is re-derived every generation and does
  need recording. Then: a **dense `occupancy.parquet` sibling** (period,
  agent_id, site_id) on the #100(b) pattern. **Not** a widened `agents.parquet`
  — widening would mean null energy and age columns for every imitation run,
  which is precisely what #47c forbids.

**Forward note for M11b — record it now, it is cheap.** Once agents move,
occupancy becomes genuinely time-varying and is no longer derivable from births
and deaths. That is when `occupancy.parquet` becomes necessary **regardless** of
how VT-2 resolves. Recording this here means M11b inherits the reasoning instead
of rediscovering it.

## `## Verification tasks`

Open with what these are: **facts about the codebase that the design session
could not establish from the docs alone.** Each one blocks a decision. Each has
**both outcomes specified in advance so the implementer never improvises**, and
each is an explicit task in a named phase. State that the answer is reported in
the handback for that phase and, where the answer changes shipped text, written
into the help text or scenario text as specified.

The full phase plan arrives in Prompt 1B; include this one-line key here so the
phase names in this section resolve. **A** — the structure module, wired to
nothing. **B** — occupancy: founding, layouts, rendering, persistence. **C** —
local birth. **D** — local interaction. **E** — polish: greying, scenarios,
bench, the §12 audit.

**VT-1 — Phase A, FIRST TASK, before anything else in that phase.** Blocks the
flagship scenario. *Do the payoff registry parameters admit NEGATIVE values?*
The donation game needs T = 5, R = 4, P = 0, S = −1. If negatives are rejected,
`donation_game_threshold` is unrepresentable as designed. The workaround —
adding 1 to all four payoffs — **preserves every best response and so leaves the
strategic structure intact**, but it changes b/c away from 5 and it shifts every
agent's income under the energy ledger, which is what the living cost is
calibrated against. Report the answer before the scenario section is trusted.

**VT-2 — Phase B.** Decides the persistence branch in Design 10. *Under
synchronous IMITATION reproduction, does a `SelectionRule` replace strategies on
the EXISTING agents (ids preserved), or produce a FRESH COHORT with new ids?*
The expectation is ids-preserved — #89(c)'s "an id must mean one creature
forever" reads as a project-wide invariant — **but expectation is not
verification.** Both branches are specified in Design 10; Phase B establishes
which is live and implements only that one.

**VT-3 — Phase B.** Decides the wording of the weak-selection caveat. *What does
the async `fixed_n` fitness-proportional BREEDER draw actually read — current-period
payoff, or accumulated energy? And is there any selection-intensity parameter
tempering it?* Ohtsuki's b/c > k threshold holds in the **weak-selection limit**.
If the draw is raw-proportional with no intensity knob, we cannot approach that
limit and the threshold is a **calibration compass, not a prediction** (#103
already says this; VT-3 fixes how strongly it must be said). Second-order: if
fitness reads **accumulated** energy, relative differences widen as a run
proceeds, so **effective selection strengthens over time**. The
`donation_game_threshold` scenario text states the answer plainly.

**VT-4 — Phase C.** Decides whether `boundary_order` has a second effect, and
therefore what its help text says. *In #80's `slots = K − survivors`, is
`survivors` computed from the APPLIED death set (post-deaths), or from the KNOWN
death set?* — deaths are deterministic given the frozen energy snapshot, so the
set is knowable before it is applied. **If post-deaths:** then `birth_first`
under well-mixed changes **how many births are admitted** — a different
demographic regime, not a phase offset — and that is the more important half of
what the parameter does, so the registry help text must say so. **If
known-set:** the only well-mixed effect is newborn exposure to the death phase,
as described in Design 5. **Write the answer into the help text either way.**

## Closing stub — mandatory

End the file with a section headed `## Sections still to be written (Prompt 1B)`
listing, as a bullet list: **Design 11** — registry shape, section order and the
greying map; **Design 12** — `site_capacity` pinned at 1 and deferred to M19;
the **Parameters** table; the **Phase plan** with reset markers and its risk
reading; the **§12 checklist** as an enumerated audit list; the **Validation**
section (V1–V8) written at spec time; the four registered **scenarios**; the
**bench** structure column and its two falsifiable hypotheses; the
**out-of-scope** section; and the **docs obligations** (DECISIONS entries and
ROADMAP amendments).

Do not attempt to write any of these yourself, and do not leave placeholder
headings for them beyond this single list.

---

# YOUR OBLIGATIONS ON FINISHING

1. **Do not commit.** Present (a) a summary of what you wrote, (b) the list of
   files to stage — which should be exactly
   `docs/specs/M11a-population-structure-spec.md` — and (c) a suggested commit
   message. I perform the commit.
2. **Report the file's character count.** I am tracking spec size against
   M10b's 33,015 characters.
3. **Report `DOCS CHANGED: docs/specs/M11a-population-structure-spec.md`** per
   the end-of-session ritual. No DECISIONS entries are created by this prompt;
   say so explicitly.
4. **Raise, in your handback, anything you found in the code or docs that
   contradicts the design above** — especially anything touching #80's frozen
   birth sequence, #99's within-event order, `helpers.greying`'s rule form, the
   `agents.parquet` schema, or the existing `Matcher` ABC's signature. Do not
   act on it; report it. This is exactly the kind of finding the verification
   tasks exist to catch, and finding one early is a good outcome.
5. If any instruction above was ambiguous enough that you had to choose, **say
   which choice you made and why**, rather than leaving it implicit in the file.

Action required: create `docs/specs/M11a-population-structure-spec.md` with the sections specified above, write no code or tests or registry entries, then report the summary, the character count, the files to stage, the suggested commit message, and the DOCS CHANGED line.
