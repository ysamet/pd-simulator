Status: implemented 2026-08-14 (see DECISIONS #111-#160 — Phase A 2026-08-01 #112; Phase B 2026-08-03 #116-#120; Phase C 2026-08-06 #127-#136; Phase D 2026-08-06 #137-#140; Phase E as five sub-prompts 2026-08-07..14: E1 #141-#144, E2 #145-#149, E2b #150, E3 #151-#153, E4a #154-#155, E4b #156-#160 — M11a complete; the literature verification pass discharged 2026-08-14, #161, and the companion explainer `docs/explainers/M11a-population-structure-explainer.md` shipped 2026-08-16)

# M11a — Population structure (sites, local birth, local interaction)

Companion explainer: **not yet written.** The explainer (the science — spatial
reciprocity, the Ohtsuki thresholds, the Hammond–Axelrod and Kaznatcheev &
Shultz lineage) arrives as a separate prompt that follows a literature
verification pass: it is gated by the verification items enumerated in this
spec's Out-of-scope section, none of which may enter the explainer — or any
scenario text — until checked against publisher records.

Read DESIGN §2.12 (M11a's design brief, in full), §6.3, §2.10, §3.1, §4, §5
and DECISIONS #103–#110 (the M11 design batch), plus #34, #42, #47, #57,
#61, #62, #65, #67, #78, #80, #81, #83, #89, #92, #94, #99, #100, #101,
#102 first.

Depends on: **M10a** (shipped — DECISIONS #76–#84) and **M10b** (shipped —
DECISIONS #93–#102). The scope boundary, stated up front: M11a is
**structure, local birth, and local interaction** — nothing else. Agent
movement, the `MovementRule` ABC, the walk radius/decay pair, the movement
schedule, and the mouse layout painter are all **M11b**. Irregular and
geographic site sets (GeoJSON polygons, raster masks), per-site capacity
above 1, and co-residency semantics are all **M19**. Several decisions below
exist specifically so that M11b and M19 arrive as *additions* rather than
migrations; where that is the reason for a choice, this spec says so.

## Frozen intent

M11a gives the world a **shape**. Until now every agent could meet, breed
toward, and be replaced by every other agent; the population was a list.
M11a makes it a set of **sites**, where a site is an exclusive container, an
agent occupies exactly one site, and both *who you play* and *where your
children land* are decided by how far away things are.

The default is unchanged behaviour. `structure.kind = well_mixed` is the
existing aspatial world, and it is recovered as the **degenerate
fully-connected corner of the same abstraction rather than as a separate
code path** — every site adjacent to every other, distance never mattering.
It is byte-identical to today on every existing seeded run: same events,
same RNG stream, same persisted folders. This is a pinned guarantee, not a
hope (Design 9's negative golden masters).

Three things arrive together in this milestone, and it is worth saying why
they are one milestone rather than three:

- a **structure** — which sites exist, and which sites are adjacent to
  which;
- **local birth** — a child is placed in an empty site within reach of its
  parent, rather than "somewhere";
- **local interaction** — you play your neighbours, rather than anyone.

Local birth without local interaction is a legitimate configuration (children
stay near their parents, but everyone still plays everyone), and so is local
interaction without local birth (you play your neighbours, but newborns land
anywhere). That separability is deliberate — it is the whole point of
parameterising the reach kernel twice (Design 2) — but neither configuration
is *expressible* until the structure itself exists. The structure is the
common substrate; the two localities are independent dials on top of it.
Shipping them together, with independent switches, is what makes the first
spatial experiments attributable.

The research payoff, stated plainly: this is the milestone after which
**cooperation can survive by clustering**. In a well-mixed world a
cooperator's kindness is dissipated across the whole population and
defectors free-ride on it from anywhere. On a lattice, a cooperator
surrounded by cooperators earns the reward payoff from every neighbour it
plays; a defector sitting in a defector interior earns only the punishment
payoff from everyone around it. Cooperators who cluster keep the benefits of
cooperation among themselves — that is **spatial reciprocity**, and it is
the mechanism the entire M12 ethnocentrism programme is built on top of.

## Defining principles

1. **The well-mixed path is byte-identical.** `structure.kind = well_mixed`
   is today's engine — not a re-implementation that happens to agree with
   it. Every new RNG draw this milestone introduces is gated so that it
   simply does not happen when structure is off (the #80/#99 active-flag
   idiom: a draw exists only when its governing flag makes it meaningful).
   This is pinned by negative golden masters (Design 9), not merely
   intended.

2. **Same seed, same run** (hard rule 5). Every new draw has a pinned
   position in the draw ordering and a stated gate. Any change to those
   positions or gates is a breaking change requiring a DECISIONS entry —
   the same discipline #80 and #99 established for the boundary sequence
   and the within-event order.

3. **The core abstraction is a graph of sites, never a rectangle** (#104).
   The rectangular lattice is *one builder* over that abstraction. The core
   never knows about rows and columns, and distance is a method the
   **structure** supplies rather than a constant the kernel assumes. This
   is the forward-guard that makes M19's irregular geographic site sets a
   second builder instead of a rewrite.

4. **Topology is immutable; occupancy is mutable.** `Structure` is a pure
   value derived once from the config. `Occupancy` is per-run simulation
   state owned by the dynamics. Keeping them apart is what lets the
   topology be shared, cached, and precomputed (Design 3).

5. **Everything id-ordered, explicitly** — now sites as well as agents. The
   #80 invariant extends: candidate site lists are built in ascending
   site-id order before any draw touches them. Deterministic tie-breaks are
   always (value, id ascending), never a random draw.

6. **A parent must clear both gates.** `admit_births()` is the global gate
   (is there a seat under carrying capacity), `place_offspring()` is the
   local one (is there an empty site in reach), and clearing one is not
   clearing the other. Place-before-pay (#80) becomes load-bearing for the
   first time (Design 4).

7. **One kernel, parameterised per use.** There is a single functional form
   for "reach" (Design 2); birth and interaction each get their own radius
   and decay, and M11b adds a third pair for the walk. One mechanism to
   understand, three places to tune it.

8. **Novice-legibility is a shipping requirement, not polish** (design-freeze
   §12, restated by #103). Roughly fifteen parameters arrive at once with
   this milestone. Every concept, every enum value individually (`moore` and
   `von_neumann` each need their own explanation, not merely the parameter
   that holds them), and every derived readout carries an inline explanation
   drawn from a single described source, and the spec enumerates them as a
   checklist (Prompt 1B's §12 checklist) so the obligation is verifiable
   rather than aspirational.

## Design 0 — the graph of sites

The `Site` record carries four things: an **id**, a **neighbour set**, a
**capacity**, and an **optional coordinate**. The coordinate is optional
precisely because M19's site sets may have no natural grid position — a set
of municipalities with shared-border adjacency has ids and neighbours but no
rows and columns. The lattice builder fills the coordinate in, and the
renderer uses it to draw the grid, but nothing in the core requires it to
exist. (The capacity field ships now, pinned at 1 — Design 12, Prompt 1B —
so that M19's capacity-above-1 is a parameter change rather than a migration
of the placement seam.)

`Structure` is the abstraction over sites: the set of sites, the neighbour
relation, and a `distance()` method. That is all the core ever sees.

Two builders ship in M11a:

- **`WellMixedStructure`** — the degenerate case. Every site is adjacent to
  every other site; distance never differentiates anything; this is the
  fully-connected corner of the abstraction. To be explicit about a fact
  that matters for byte-identity: **the well-mixed engine does not route
  through structure code at all in M11a** — nothing on the
  `structure.kind = well_mixed` path imports it. This builder exists to
  make the abstraction honest (the aspatial world genuinely *is* a corner
  of the same model, not a separate ontology) and to be the thing M19 and
  future work can reason against — not as a live execution path, which
  would put the byte-identity guarantee at risk for no gain.

- **`LatticeStructure`** — the rectangular builder: rows, columns, a
  neighbourhood shape, and a boundary rule (Design 1).

**Distance is structure-supplied.** `structure.neighbourhood_shape = moore`
means the structure's metric is the **Chebyshev** distance — the *larger*
of the two coordinate differences; `von_neumann` means the **Manhattan**
distance — their *sum*. Concretely, from a cell at row 2, column 3 to a
cell at row 4, column 6, the row difference is 2 and the column difference
is 3: the Chebyshev distance is max(2, 3) = 3, the Manhattan distance is
2 + 3 = 5. At radius 1 the two shapes give the familiar neighbourhoods —
Moore is the 8 surrounding cells (diagonals count as distance 1), von
Neumann is the 4 orthogonal cells (a diagonal step is distance 2):

```
Moore, d ≤ 1 (8 neighbours)      von Neumann, d ≤ 1 (4 neighbours)

    1 1 1                                . 1 .
    1 * 1                                1 * 1
    1 1 1                                . 1 .
```

The key consequence, made explicit because it is easy to miss: **the shape
*is* the metric, and the metric is handed to both kernels.** Choosing
`moore` or `von_neumann` therefore governs birth reach and interaction
reach *together* — it is one decision about what "distance" means in this
world, not a separate knob for each locality.

## Design 1 — lattice geometry and the derived defaults

**`structure.rows` / `structure.cols`.** Left blank, they resolve to the
**most-square factor pair of N** — the #78 derived-default idiom: the auto
rule runs at config validation and the stored `config.yaml` always holds
plain numbers, so the rule can never retroactively change an old run. A
population of 400 resolves to 20×20; a population of 60 resolves to 6×10.
One edge case matters enough to design for: a **prime** N factorises only
to 1×N — a single line of cells. That is a legitimate one-dimensional
lattice (rings and lines are standard objects in this literature), but a
user who typed N = 101 expecting a grid will see something that looks
broken. **The app must announce the 1×N resolution rather than let it look
like a bug.**

**`structure.boundary` ∈ {`torus`, `bounded`}, default `torus`.** A torus
wraps: the left edge is adjacent to the right edge, the top to the bottom —
the world has no rim. It is the default because **uniform degree removes an
edge artifact**: on a bounded grid a corner cell has 3 neighbours under
Moore while an interior cell has 8, and since cooperation thresholds on
graphs depend on the number of neighbours (degree), corners become
spuriously favourable to cooperation — an artifact of the map's edge, not a
fact about the model. `bounded` ships anyway, deliberately: at M19 a
coastline is a *real* hard edge, and varying degree is then the model
rather than an artifact. The degree table, concretely — these numbers are
what the Phase A tests assert:

| Shape | Boundary | Interior cell | Corner cell |
|---|---|---|---|
| Moore | `torus` | 8 | 8 (no corners exist) |
| Moore | `bounded` | 8 | 3 |
| von Neumann | `torus` | 4 | 4 (no corners exist) |
| von Neumann | `bounded` | 4 | 2 |

**Carrying capacity survives under structure as a second, tighter cap**
(#106, resolving §2.10's "K may become emergent" open line). K stays a live
parameter under a lattice, with a validator: **K ≤ site count** — the grid
is the outer bound, K an optional inner one. A blank K under a lattice
resolves to the site count (the #78 idiom again), making "the grid decides"
the zero-effort path. A K *below* the site count leaves deliberate slack —
a 20×20 grid at K = 250 runs at roughly 60 % occupancy — and in that slack
the occupied region can drift, cluster, and migrate as births and deaths
reshape it, a genuinely interesting dynamic that "capacity is purely
emergent from the grid" would foreclose. The failure mode this design must
not ship: a population parks at K with half the map empty and nothing
explaining why. The Economy panel therefore reports **both numbers** — K
and the site count — so slack is visible information rather than a
mysterious stall.

**Under `fixed_n`, N = site count exactly** (validated). Every site is
occupied at all times, so a death leaves exactly one empty site and the
newborn has nowhere else to go: **site recycling is the only possible Moran
placement.** The textbook death-birth corner is therefore *structural* —
a consequence of full occupancy — rather than a rule we impose, and no
`moran_placement` parameter needs to exist (#106).

## Design 2 — the reach kernel, and the one primitive

**One functional form** (#105). The weight over a site at distance *d* from
an origin is proportional to

> **exp(−β·d) for d ≤ R, and zero beyond,**

where **R** is a *support radius* — the hard edge beyond which a site is
simply not a candidate — and **β** a *decay* — how steeply preference falls
with distance inside that edge. Two parameters because they answer two
different questions: R answers "who is reachable at all?", β answers "among
the reachable, how much does closer matter?".

Said explicitly: this supersedes the M10b forward-note's single-temperature
phrasing (M10b spec Design 9, explainer §7), which promised "hard cutoff
recoverable as temperature → 0". That phrasing was loose: sharpening a
decay recovers *nearest-neighbours-only*, not a hard-edged disc — one
parameter cannot express both "uniform within a boundary" and "steeply
local". The M10b spec is not retro-edited (frozen-spec ritual, #62); #105
is the record, and this spec is the corrected design.

The four corners, which are exactly what the Phase A kernel tests assert:

- **R = 1** is Hammond–Axelrod exactly — children land in, and partners
  come from, the immediate neighbourhood, full stop. β is irrelevant at
  R = 1 (all candidates sit at the same distance).
- **β = 0 with R = n** is a uniform disc — every site within n equally
  likely. This is the "hard cutoff" the old forward-note was reaching for.
- **Large β with R = n** is steeply viscous — distant sites remain
  *reachable* but become very unlikely; locality as a strong preference
  rather than a wall.
- **R → ∞ with β = 0 is well-mixed**, recovered by *parameters* rather
  than by a branch — the same world the aspatial engine implements, arrived
  at from inside the spatial abstraction.

M11a parameterises the kernel twice — `structure.birth_radius` /
`structure.birth_decay` and `structure.interaction_radius` /
`structure.interaction_decay` — and M11b adds a third pair for the walk.
Two radii rather than one is what makes
local-births-with-global-interaction and
global-births-with-local-interaction **separable experiments** — the
Frozen-intent separability, delivered as parameters.

### One primitive, not four

All four call sites that need "sample sites near an origin" — synchronous
placement, synchronous interaction, the asynchronous partner draw, and the
asynchronous `fixed_n` breeder/victim draw — run the *same* algorithm:
enumerate the sites within R of an origin, filter to an eligible set,
weight by exp(−β·d), and draw without replacement. Only the eligible set
and an optional second weight differ between call sites. So there is one
function:

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

The semantics, pinned here so no call site improvises:

- **`eligible` is an explicit frozen set, not a predicate callable.** The
  caller already holds the occupancy map, so it can hand over "the empty
  sites" or "the occupied sites minus self" as data — and a set is
  trivially inspectable in a failing test, where a closure is not.
- **`radius=None` means unlimited reach**, matching the nullable parameter
  it implements.
- **`site_weights` is the optional second weight.** The combined weight on
  a site is `exp(−β·d) * site_weights[site]`. This is the hook Design 7's
  fitness-weighted breeder draw uses; every other call site leaves it
  `None`.
- **The function returns fewer than `size` sites** when fewer sites are
  eligible — the #81 clamp idiom (clamp, don't raise: a small
  neighbourhood is a fact about the world, not an error).
- **It returns an empty tuple** when no sites are eligible at all — this is
  `place_offspring`'s failure signal (Design 4).

Underneath the sampler sit two functions that are **pure and RNG-free**:
`sites_within(structure, origin, radius)` — the candidate enumeration —
and `kernel_weights(structure, origin, sites, decay)` — the exp(−β·d)
weight vector. These are what the kernel-corner tests exercise directly
(no RNG in the assertion path), and they are the surface M19's builders
must satisfy.

**Determinism rule — a rule, not advice.** The candidate list is built in
**ascending site-id order before any draw**. This is #80's "everything
id-ordered, explicitly" applied to sites instead of agents. Without it, the
draw's outcome depends on set iteration order — a reproducibility bug of
the worst kind, because it survives every test on every machine until a
Python version changes hashing or iteration behaviour, and then every
golden master breaks at once with no code diff to blame.

Record, finally, that **#103's obligation on M11a is satisfied by this
design**: `neighbourhood_sample` is the named public reach primitive #103
required, so M11b's movement rule becomes a fourth caller of an existing
function — purely additive, never reopening structure code.

## Design 3 — the topology / occupancy split

`Structure` and `Occupancy` are **separate objects**, and the reason is
architectural, not stylistic:

- **`Structure` is immutable**: the sites, the neighbour relation, the
  `distance()` method. It is derived once from the config and never changes
  during a run — which makes it shareable and cacheable without thought.
  This is the object M19 reimplements as a second builder.
- **`Occupancy` is mutable per-run state owned by the dynamics**, exactly
  like the population list: site id → agent id, agent id → site id, with
  `occupy()`, `vacate()`, and `empty_sites_within()`.

The split is what lets `LatticeStructure` be a pure value with no
simulation state inside it — and **it is the difference between M19 writing
a builder and M19 writing an engine**. If topology and occupancy lived in
one object, every new site-set shape would drag the placement and death
bookkeeping along with it.

The split is also what makes the Phase E precomputation possible. Because
topology is immutable, the candidate list for each site at each radius is a
pure function of the config — it can be built once, up front, and reused
for the whole run. And because the kernel weight depends only on distance,
one distance→weight lookup table per (R, β) pair covers every site on the
grid. Neither optimisation is *required* for correctness; both fall out of
principle 4 for free.

## Design 4 — the two gates

**`admit_births()` is the GLOBAL gate**: are we under carrying capacity,
with seats rationed by energy priority when they are scarce — the M10a
mechanism, unchanged in role. **`place_offspring()` is the LOCAL gate**: is
there an empty site within the birth kernel's reach of the parent, sampled
by `neighbourhood_sample` and contested per Design 5. **A parent must clear
both gates, and clearing one is not clearing the other**: a parent can win
a seat under K and still find every site in reach occupied; a parent with
an empty site next door can still be turned away because the world is at
capacity. (This two-gate structure is one of the concepts the §12 checklist
— Prompt 1B — requires an inline explanation for; the fourteen-item count
quoted there includes it.)

**Place-before-pay (#80) is load-bearing at last.** The M10a birth loop
checks placement *before* the parent pays the offspring stake — a check
that, until now, ran against a stub that always returned `True` (the
well-mixed world has no structure to be blocked by; the stub existed purely
so M11 could not inherit a pay-then-place bug). Under structure the branch
goes live: a parent that cannot place a child pays **no stake** and stays
eligible next period.

The behavioural consequence deserves spelling out, because it is the single
most likely thing in this milestone to be misread as a bug: a parent
**walled in by occupied neighbours pays nothing, stays eligible, and keeps
accumulating energy**. An agent sitting at five times the birth threshold
and not breeding is *correct* — being unable to spend reproductive wealth
because the neighbourhood is full is the entire content of viscosity, the
thing spatial structure is *for* — but on a dashboard it reads as a
defect ("this agent is rich, why is nothing happening?") unless the app
says so. The Economy panel therefore reports **blocked parents this
generation** — how many admitted parents failed the local gate — on the
same #89(e) logic that put the calibration readout into M10a: app-first
validation is not honest if the person watching cannot see the mechanism
that explains what they are watching. This readout is a **Phase C
deliverable**, landing with local birth itself — not a Phase E nicety.

## Design 5 — birth contention, the contest, and boundary order

This section **amends the #80 frozen boundary sequence**. #80 states that
any change to it is a breaking change requiring a DECISIONS entry; #107 is
that entry, and this section carries its reasoning into the spec. (The
precise draw-order diff lives in Design 9.)

**Contention exists only where several births resolve at one instant**:
**synchronous + structure + `energy_economy`**, and nowhere else. Async
resolves one birth per event, so no two births ever contend; `fixed_n`
never calls `admit_births` at all (#97d — the Moran replacement is its own
admission); and sync well-mixed placement never fails, so there is nothing
to contend for. State this plainly: **the correctness of this confinement
is an argument, not a test** — no test can directly observe "contention
cannot arise here", only that no contest draw happened. Which is exactly
why the excluded configurations get *no-draw assertions* (Design 9's
counting wrapper) rather than mere reproducibility checks: the assertion
"this path consumed zero contest draws" is the testable image of the
argument.

**`structure.placement_contest` ∈ {`random`, `energy_priority`}, default
`random`.** Under structure, the admitted birth set is resolved by **one
permutation, then iterate**: shuffle the admitted parents once, then let
each in turn draw a placement. This matches Hammond–Axelrod's random
reproduction order, and it keeps energy's role at *eligibility* (the θ
threshold decides who may breed) rather than at *winning a contested cell*
(wealth deciding who gets the ground). The `energy_priority` option is
retained rather than defaulted because richest-wins-contested-cell
*compounds spatially* — a good neighbourhood raises earnings, which wins
more cells, which acquires more good territory — a substantive modelling
claim someone should turn on deliberately, not inherit silently.
**Parent-id order is rejected** for the contest: on a lattice, agent id
correlates with founding position (ids are dealt in layout order at
founding), so ordering the contest by id silently becomes a *spatial*
priority rule — the exact kind of invisible bias this parameter exists to
control. The shuffle is gated by the structure flag, so well-mixed sync
runs draw no extra RNG and stay byte-identical (principle 1).

**`dynamics.boundary_order` ∈ {`death_first`, `birth_first`}, default
`death_first`.** This exposes Hammond–Axelrod's period order as an option.
`death_first` is today's #80 sequence: deaths are applied, then births
fill. `birth_first` is H-A's order: reproduction happens, then the death
phase runs. Under a lattice this is **not a phase offset but a different
model**, because it decides *which sites are empty when children are
placed*: deaths-first lets newborns fill scattered interior graves;
births-first offers them only the cells that were already empty — the
frontier — and the frontier is where the ethnocentrism mechanism lives
(M12's replication scenario will set `birth_first` explicitly, which is
why the option is built now rather than reopening the boundary a third
time). Note the failure signature: a bug here produces **plausible dynamics
rather than a crash** — a frontier that quietly behaves like an interior —
which is precisely the mechanism M12 is being built to study. Wrong here
means wrong conclusions, not error messages.

**`boundary_order` is live under ALL synchronous runs and greyed only under
async.** The naive reading is that it should also grey under well-mixed
sync ("no lattice, no placement, surely no effect") — the reasoning against
that is worth recording in full:

- #107's own text says "sync-only, greyed under async (which has no
  boundary to order)" and stops there. Greying it under well-mixed would
  add a restriction the decision did not make.
- **It is not inert under well-mixed.** Under `death_first`, deaths finish
  before any child exists, so a newborn is guaranteed to survive to the
  next generation. Under `birth_first`, the child is created and *then*
  the death phase runs, so a newborn faces the age-mortality coin
  immediately and can die in the very period it was born. That is Hammond
  & Axelrod's ordering, and it is a genuine difference in infant survival
  even with no lattice anywhere.
- #34 reserves greying for parameters consumed **nowhere**. This one is
  consumed.
- The errors are asymmetric: showing a live parameter whose effect is
  small is mild noise; greying a parameter that has an effect is **the app
  asserting something false about the user's run**.
- **VT-4 may add a second, larger well-mixed effect** — whether
  `birth_first` changes how many births are admitted, not just whether
  newborns face the reaper. See the verification tasks.

## Design 6 — local interaction

**`matching.spatial_interaction` (bool, default off)** (#108). Off: today's
behaviour — `matching.matcher` picks round-robin or random-k over the whole
population, exactly as now. On: partners are sampled from within the
interaction radius by the reach kernel, and **`matching.matcher` greys** —
round-robin has no local analogue (there is no "every pair plays once"
inside overlapping neighbourhoods), and the well-mixed matchers are the
kernel's own infinite-radius corner, so keeping the widget live would offer
a choice with no distinct meanings. A toggle rather than "structure implies
local interaction" because the two localities must stay independently
switchable (Frozen intent; #108's rationale).

**`matching.opponents_per_agent` (k) stays LIVE and does the work.** k at
or above the neighbourhood size means "play all your neighbours" — the
Hammond–Axelrod and Ohtsuki convention — so **round-robin's idea survives
the greying** even though the matcher widget does not: exhaustive local
play is just a large k. k **clamps** to the number of neighbours that
actually exist (the #81 clamp idiom — clamp, don't raise): edge cells
under `bounded` have fewer neighbours than interior cells, and M19's
irregular site sets will vary degree everywhere. Validator: spatial
interaction requires `structure.kind = lattice` (there is no radius to
sample within in a well-mixed world).

**`SpatialKernel(Matcher)` is genuinely thin.** It is the sync-side adapter
#108 describes: it holds the structure, the occupancy, the interaction
radius, the decay, and k — and `pairings()` walks agents in ascending id
order, calls `neighbourhood_sample` once per focal agent with `size = k`
and `eligible` = the occupied sites minus the focal's own, and maps the
returned sites back to agents. All sampling logic lives in the primitive;
the matcher is plumbing. (The async loop calls the same primitive directly
for its partner draw — one kernel, no duplication.)

**Two behaviours are inherited from `RandomK` deliberately** — the word
matters, because both look like defects on first reading:

1. **No deduplication.** Agent A can draw B while B draws A, so a pair can
   meet twice in one generation. This is existing `RandomK` behaviour
   (#57: duplicate pairs across initiators are allowed), and it is the
   source of the `len(agent._histories)` sharp edge already present in
   the codebase. Local sampling inherits it unchanged rather than
   introducing a new dedup rule that would silently change income
   statistics relative to the well-mixed baseline.
2. **Clamp, not error, when k exceeds the neighbourhood** — the #81 idiom
   again. A corner cell with 3 neighbours under bounded Moore plays 3
   matches at k = 8, and that is a fact about geometry, not a
   misconfiguration.

**Fork resolved — draw unconditionally.** Whenever spatial sampling is
active, the kernel draw happens **even when k ≥ neighbourhood size and the
outcome is therefore forced** (everyone in reach will be drawn). The cost
is a wasted permutation in the "play all neighbours" configuration — which
is the Hammond–Axelrod convention and therefore common. The benefit is that
**the RNG stream position is predictable from the config alone** (#80's
active-flag idiom): whether a draw happens never depends on how full a
particular neighbourhood happened to be at a particular moment. A wasted
draw costs nothing; a golden master that shifts because one cell's
neighbourhood happened to be full costs a debugging afternoon.

## Design 7 — where the breeder comes from (Open Question 1, resolved)

#106 settles where the offspring **goes** under `fixed_n` + lattice: into
the freed site, because nothing else is empty. It does **not** say where
the **breeder** comes from — and M10b draws the `fixed_n` breeder
fitness-proportionally over the **whole living population**. State the
problem before the answer: if that draw stays global under a lattice, the
number of competitors for a vacated seat is N−1 rather than the local
neighbourhood size k — and **Ohtsuki's b/c > k threshold has k in it
precisely because k counts the competitors for a vacated site**. Keep the
draws global and the Moore-versus-von-Neumann comparison scenario
demonstrates nothing: both shapes would compete globally and the
neighbourhood size would never enter the dynamics.

**DECIDED: localise the async `fixed_n` breeder and victim draws under a
lattice**, with the **birth kernel** (`birth_radius` / `birth_decay`)
supplying the candidate set — read from the **freed site's** side under
`death_birth` (its neighbours compete to fill it), and from the
**breeder's** side under `birth_death` (its offspring displaces one of its
neighbours).

**DECIDED: sync IMITATION's `SelectionRule` stays GLOBAL under a lattice
for M11a.** Making the imitation comparison partner local is a genuine
mechanism change to the stable sync selection path, and M12 needs to reopen
imitation anyway for in-group/out-group strategy spread. Record this as an
**explicit decline on scope grounds — not an omission — handed to M12**;
this is the same shape #110 used for the imitation-adopter checkpoint
(examined, not triggered, rolled forward with its rationale intact).

**Fork resolved — MULTIPLY.** The localised Moran breeder draw's weight on
a candidate is `exp(−β·d) * fitness` — the kernel's distance weight times
the fitness weight, via `neighbourhood_sample`'s `site_weights` hook
(Design 2). At R = 1 every candidate sits at the same distance, so the
distance factors are all equal and the draw reduces to **exactly**
fitness-proportional over the neighbours — **Ohtsuki's setting is recovered
as a corner, not approximated**. The existing non-negative fitness shift
(the #63 idiom: `w_i = e_i − min(e)`) applies **before** the
multiplication, and the uniform fallback triggers on the **combined**
vector — if every product is zero, the draw is uniform over the candidates,
matching the shift idiom's existing contract.

**Documentation obligation — the rationale must be reachable from the UI,
not only from the explainer.** §12's rule is that each concept's
explanation comes from a single described source, so app text and docs
cannot drift. Three places carry this design's story:

1. **`structure.kind`'s `lattice` value help** states that a lattice makes
   interaction and natal placement local, **and** that in synchronous
   imitation mode the comparison partner is still drawn from the whole
   population (the explicit decline above, visible where the user makes the
   choice).
2. **`structure.birth_radius` and `birth_decay`'s help** states that under
   `fixed_n` these define the **set of competitors for a freed site** —
   which is what the b/c > k threshold's k counts.
3. **A derived readout for effective neighbour count** gives that k a
   visible number in the app.

The long-form version — including the b = 5 / c = 1 donation-game
walkthrough — belongs in the explainer and is out of scope for this spec.

## Design 8 — initial layouts and the layout file

**The divisibility problem dissolves: arrangement is DEALING, not
PARTITIONING.** #67 has already resolved composition to exact integer
counts per strategy, and §2.12 says the layout decides **arrangement
only**. So the counts are authoritative and the arrangement bends around
them — the same philosophy as largest-remainder rounding, one layer up:
resolve the numbers first, then make the geometry serve them. There is no
"4 strategies don't divide evenly into 10 rows" problem because **nothing
is being divided** — cells are dealt from a deck whose composition is
already fixed. This is stated explicitly because it is exactly the kind of
non-problem a later reader will otherwise try to solve again.

**Five algorithmic layouts are one engine**: walk the sites in some
traversal order and deal strategies out of the resolved counts until the
counts are exhausted. What varies between layouts is only the traversal and
the dealing discipline:

- **`stripes`** — row-major sweep, **run-length** dealing: each strategy's
  whole count is dealt as one consecutive run. A strategy with 39 agents
  gets 39 consecutive cells; one with 2 agents gets 2. Stripe boundaries
  therefore fall where the **counts** fall, so a "stripe" can be a fragment
  of a row — the help text says this rather than letting it look like a
  bug.
- **`blocks`** — run-length dealing along a traversal that keeps runs
  compact in *two* dimensions; a boustrophedon (serpentine) sweep over
  sub-blocks of the grid is enough. **No new parameter** (no block-size
  knob), and it degrades gracefully at any count.
- **`checkerboard`** — **round-robin** dealing: one cell at a time, cycling
  over the strategies that still have agents left. With two equal-count
  strategies this reproduces the literal checkerboard; with four unequal
  ones it produces **maximal interleaving** — which is the purpose #109
  assigns this layout: the anti-cluster baseline. **Generalise by purpose,
  not by appearance** — the layout's job is "no strategy next to itself
  where avoidable", not "look like a chessboard".
- **`patches`** — one seed site per strategy placed by RNG, then
  multi-source growth outward, each strategy's quota its growth budget.
  Deterministic given the seeds; **RNG enters only at seed placement**.
  The most natural irregular clusters (#109).
- **`random`** — shuffle: deal the whole deck over the footprint in
  RNG order.
- **`central_block`** — a centred rectangle sized to N, with the rest of
  the grid empty. This is the **filling regime** (#109) — the
  empty-frontier world the Kaznatcheev & Shultz early-run result concerns.

**Deal order: ascending machine name** — reusing #67's tie-break
convention, so the project has **one** ordering rule for strategies rather
than two.

### When N is less than the site count

This cannot arise under `fixed_n` (N = site count, by validator). It arises
under the economy and under `variable_n` — and then every layout needs a
rule for **which sites are occupied at all**, not only what is dealt into
them. `central_block` answers this definitionally (the centred rectangle is
the footprint); the other five need a stated rule.

**DECIDED: `random` scatters over the whole grid; the patterned five use a
centred contiguous footprint** (a centred block of N sites, with the
pattern dealt inside it). Rationale: "random" should mean random — a
scattered start is the closest spatial analogue of the well-mixed baseline
— while a patterned arrangement is a statement about *contiguous* structure
and would be destroyed by scattering its cells.

**MANDATORY GUARD: the app reports the number of agents with zero occupied
neighbours at founding.** A scattered population under local interaction
can leave agents isolated; an isolated agent plays nothing, earns nothing,
and starves at the next boundary. That is *correct* — it is #81's
lone-survivor thermodynamics, locally — but it is bewildering to watch
without an explanation. The founding-isolation readout turns the hazard
into information, and it is a derived readout requiring an inline
explanation under §12 anyway.

### The layout file format

The requirements pull in opposite directions. Hand-authoring wants a
**picture** — a file you can read as a map. #104's graph-of-sites
forward-guard wants something that survives M19's irregular site sets,
where there are no rows and columns to draw.

**Resolution: one format now, versioned so the second is additive.** Plain
text. A header carrying a `kind:` line reading `lattice_grid`, plus
`rows:` and `cols:`. A body that is a character grid — one token per cell,
where a token is a strategy machine name or `.` for an empty site:

```
kind: lattice_grid
rows: 4
cols: 6

always_defect always_defect tit_for_tat tit_for_tat tit_for_tat .
always_defect always_defect tit_for_tat tit_for_tat tit_for_tat .
.             .             tit_for_tat tit_for_tat .           .
.             .             .           .           .           .
```

Validators: the header's dimensions must match the resolved
`structure.rows` and `structure.cols`, and every non-`.` token must be a
registered strategy.

M19 adds `kind: site_map` with a two-column site-id/strategy body — the
form that needs no geometry — and the reader dispatches on the header.
Additive, no rewrite — and **the discriminator ships from day one**, so
there is never a layout file in the wild without a `kind:` line for the
future reader to dispatch on.

### Two consequences, both decided explicitly

1. **A layout file specifies composition implicitly** — it names a strategy
   per cell, so its cell counts *are* a composition, and they can
   contradict the #67-resolved composition widgets. **The file wins, and
   the composition widgets grey.** Requiring the user to separately
   reproduce, in the widgets, counts they have already painted in the file
   is a trap — two sources of the same truth that can silently disagree.
   **Validator: reject a layout file combined with a swept composition
   axis** — a sweep that varies composition while a file pins every cell
   is incoherent, and the incoherence should be an error at spec
   validation, not a silent override mid-campaign.
2. **The recorder must copy the layout file into the run folder.** A
   `config.yaml` that references `layouts/my_painting.txt` by path violates
   hard rule 8 the moment that file moves or changes — the run would no
   longer re-run from its folder. Copying the file in is a two-line fix
   that makes the run folder self-contained.

## Design 9 — the RNG reproducibility contract

Open with the finding, because it is the reason this section is shorter
than feared: **most changes are SUBSTITUTIONS, not INSERTIONS** — existing
draws that change their candidate set and weights while keeping their
position and call shape — because of an asymmetry in Ohtsuki's two update
rules that maps unexpectedly well onto M10b's existing draw order:

- Under **death-birth**, a random individual dies and **its neighbours
  compete** to fill the site. The victim draw is global and uniform —
  **unchanged** from M10b. Only the breeder draw localises.
- Under **birth-death**, a breeder is chosen by fitness from the whole
  population and its offspring replaces **one of its neighbours**. The
  breeder draw is global — **unchanged**. Only the victim draw localises.

So in each rule **exactly one draw changes, it is always the second of the
two, and it changes its candidate set and weights while keeping its
position and call shape**. Neither rule gains or loses a draw. The
`moran_rule = random` rule roll keeps its pinned position as the first
demographic draw of the event (#99), untouched.

### Full inventory

Every RNG change in M11a, in one table:

| Draw | Kind | Gate |
|---|---|---|
| Founding layout | NEW (once per run, before generation 0) | lattice + non-deterministic layout |
| Sync interaction partners | SUBSTITUTION (`SpatialKernel` for `RandomK`/`RoundRobin`) | lattice + `spatial_interaction` |
| Sync contest permutation | INSERTION (one permutation over the admitted set) | sync + lattice + `energy_economy` |
| Sync placement, per parent | INSERTION (at the placement check, before σ) | lattice + births exist |
| Async partner draw | SUBSTITUTION | lattice + `spatial_interaction` |
| Async DB breeder / BD victim | SUBSTITUTION | lattice + `fixed_n` |
| Async `variable_n` placement | INSERTION (same position as sync) | lattice |

**Three insertions.** The layout draw sits **outside the per-generation
order entirely** — it happens once, at population construction, before
generation 0 — so it cannot perturb any within-generation sequence. That
leaves **two real insertions into golden-mastered orders, both inside the
birth step, both landing in Phase C**. Everything else is a substitution
behind an existing call, or brand-new gated territory.

### Amended #80 step (6), births — as a diff (since #80 is frozen)

- **CURRENT:** admission by energy priority (RNG-free) → admitted set
  iterated in ascending parent-id order → placement check → σ payment →
  passport id → μ draw.
- **AMENDED:** admission **unchanged** → **contest permutation over the
  admitted set, drawn only when the three-way gate holds** (sync + lattice
  + `energy_economy`) → iteration order is the permutation under
  `placement_contest = random`, energy-descending under `energy_priority`,
  and parent-id ascending when the gate is off → **the placement check is
  now a kernel draw that can return empty** (an empty tuple from
  `neighbourhood_sample` = the parent is blocked) → **σ payment only on
  placement success** → passport id → μ draw.

### Amended #99 within-event order, `fixed_n` — as a diff

The rule roll is **unchanged** (first demographic draw of the event, only
under `moran_rule = random`). Under `death_birth`: victim draw
**unchanged**, breeder `rng.choice` now over the **freed site's
neighbours** with the combined `exp(−β·d) × shifted-fitness` weights
(Design 7). Under `birth_death`: breeder draw **unchanged**, victim draw
now over the **breeder's neighbours**. Under `variable_n`: the placement
check inside the birth sub-step becomes a kernel draw, in the same position
the sync amendment gives it.

### Three orderings now — and how they collapse

#80 keeps **admission order** (energy descending, id ascending) separate
from **iteration order** (parent-id ascending), pinned by a test where the
two orders differ. Phase C inserts a **contest permutation** between them,
making three orderings that must not be conflated.

Name the specific bug so it cannot be rediscovered the hard way: **applying
the permutation to a list that has already been energy-sorted, and then
iterating the result** — which yields a `random` contest that is quietly
energy-biased in exactly the way #107 rejected (the shuffle of a sorted
list is only unbiased if the shuffle is applied correctly; the trap is
partial shuffles, stable re-sorts, or permuting indices into the wrong base
list). The pin needs a fixture where **all three orders differ pairwise** —
harder to build than #80's two-way case, because energy, id, and the
permutation must all disagree — and **it should be written before the code
it tests**, so the code is written against the trap rather than checked for
it afterwards.

### Golden masters

**Four negative pins first** — these are what nothing else catches: sync
imitation, sync economy, async `variable_n`, async `fixed_n`; each
well-mixed; each byte-identical to its pre-M11a event stream **and**
persisted folder. These are the executable form of principle 1.

**Four new positive goldens**: sync economy + lattice; async `fixed_n` +
lattice + `death_birth`; async `variable_n` + lattice; sync imitation +
lattice (the interaction-only case — no births, no deaths, structure
expressed purely through who plays whom).

**No-draw assertions**: no contest permutation under async, under
`fixed_n`, under sync well-mixed, or under sync imitation with a lattice —
the Design 5 confinement, asserted directly.

**Technique — adopt this, and here is why.** Byte-identical output
*usually* catches a spurious draw, because a shifted stream changes
everything downstream — but **not if the extra draw lands after the last
consequential draw of the run**, where nothing remains to be perturbed. A
**counting wrapper** around the `Generator` that records the exact sequence
of method calls turns "the output matched" into "the stream was identical",
and makes the no-draw assertions **directly expressible rather than
inferential** ("this run consumed zero permutation draws", not "this run's
output looks unshifted"). It is cheap to build, and it is the mechanism the
negative pins actually need.

## Design 10 — persistence (schema 5)

**The simplification this schema rests on: in M11a, agents never move.**
Movement is M11b. So an agent's site is fixed from birth to death, and
occupancy at any period is fully determined by founding placement plus the
birth and death record — both of which are already persisted.

- **Site id becomes a single column on `agents.parquet`**, present when the
  run has structure and absent otherwise — #83's honest-presence rule
  exactly (the file's shape reflects what the run actually produced). **No
  new sibling table, no widened `timeseries.parquet`, nothing NaN-filled.**
- **`AgentSnapshot` gains `site_id: int | None`**, as DESIGN §4 already
  specifies. This is also what the live grid renderer reads — the snapshot
  is the render state.
- **`SCHEMA_VERSION = 5`**, written when structure data is present. The
  existing constants are untouched: well-mixed sync imitation still writes
  2, well-mixed sync economy 3, well-mixed async 4, and **any** lattice run
  writes 5. The loader accepts 1–5 and rejects above.
- **State the ladder honestly so it is not read as an implication**: a sync
  economy lattice run writes 5 — a version number that *arrived* with
  event-time data the run does not have. This is already handled by
  #100(b), which makes missing-file-equals-empty-shape the **contract**
  rather than mere backward compatibility: the loader is
  **presence-driven, not version-driven**, so a monotone integer works — 
  the version gates "how new must the loader be", the files themselves say
  what the run contains.

### The conditional — resolved by VT-2

`agents.parquet` and `AgentSnapshot` exist only in economy mode; DESIGN §4
says snapshots are empty under imitation (that emptiness is what keeps
imitation payloads byte-identical to pre-M10a). So **sync imitation +
lattice has occupancy and nowhere to record it** — DESIGN §4's
"AgentSnapshot gains a site id" implicitly assumed structure + economy, and
imitation + lattice is a configuration the design edit did not consider.

**The spec specifies both branches; Phase B establishes which is live and
implements only that one** (VT-2):

- **If ids are preserved across imitation generations** (the same `Agent`
  objects carry new strategies): nobody is born, nobody dies, and occupancy
  never changes after founding. It is entirely determined by the initial
  layout, which lives in the config, and re-running reproduces it exactly.
  **Nothing to persist**; the live renderer holds occupancy in memory
  without any event carrying it.
- **If ids are not preserved** (selection produces a fresh cohort with new
  ids): occupancy is re-derived every generation and does need recording.
  Then: a **dense `occupancy.parquet` sibling** — (period, agent_id,
  site_id) — on the #100(b) sibling-table pattern. **Not** a widened
  `agents.parquet`: widening would mean null energy and age columns for
  every imitation run, which is precisely the NaN-filled-columns shape
  #47c forbids.

**Forward note for M11b — recorded now because it is cheap.** Once agents
move, occupancy becomes genuinely time-varying and is no longer derivable
from births and deaths. At that point `occupancy.parquet` becomes necessary
**regardless** of how VT-2 resolves. Recording the reasoning here means
M11b inherits it instead of rediscovering it.

## Verification tasks

These are **facts about the codebase that the design session could not
establish from the docs alone.** Each one blocks a decision; each has
**both outcomes specified in advance, so the implementer never
improvises**; and each is an explicit task in a named phase. The answer to
each is reported in that phase's handback and — where the answer changes
shipped text — written into the registry help text or scenario text as
specified below.

The full phase plan arrives in Prompt 1B; the one-line key, so the phase
names in this section resolve: **A** — the structure module, wired to
nothing. **B** — occupancy: founding, layouts, rendering, persistence.
**C** — local birth. **D** — local interaction. **E** — polish: greying,
scenarios, bench, the §12 audit.

**VT-1 — Phase A, FIRST TASK, before anything else in that phase.** Blocks
the flagship scenario. *Do the payoff registry parameters admit NEGATIVE
values?* The donation game needs T = 5, R = 4, P = 0, S = −1. If negatives
are rejected, the `donation_game_threshold` scenario is unrepresentable as
designed. The workaround — adding 1 to all four payoffs — **preserves every
best response and so leaves the strategic structure intact**, but it
changes b/c away from 5, and it shifts every agent's income under the
energy ledger, which is what the living cost is calibrated against. Report
the answer before the scenario section (Prompt 1B) is trusted.

**VT-2 — Phase B.** Decides the persistence branch in Design 10. *Under
synchronous IMITATION reproduction, does a `SelectionRule` replace
strategies on the EXISTING agents (ids preserved), or produce a FRESH
COHORT with new ids?* The expectation is ids-preserved — #89(c)'s "an id
must mean one creature forever" reads as a project-wide invariant — **but
expectation is not verification.** Both branches are specified in
Design 10; Phase B establishes which is live and implements only that one.

**VT-3 — Phase B.** Decides the wording of the weak-selection caveat.
*What does the async `fixed_n` fitness-proportional BREEDER draw actually
read — current-period payoff, or accumulated energy? And is there any
selection-intensity parameter tempering it?* Ohtsuki's b/c > k threshold
holds in the **weak-selection limit** — fitness differences almost
invisible to the dynamics. If the draw is raw-proportional with no
intensity knob, we cannot approach that limit, and the threshold is a
**calibration compass, not a prediction** (#103 already says this; VT-3
fixes how strongly it must be said). Second-order consequence to check: if
fitness reads **accumulated** energy, relative differences widen as a run
proceeds, so **effective selection strengthens over time** — a run drifts
*away* from the weak-selection limit as it ages. The
`donation_game_threshold` scenario text states the answer plainly either
way.

**VT-4 — Phase C.** Decides whether `boundary_order` has a second effect,
and therefore what its help text says. *In #80's `slots = K − survivors`,
is `survivors` computed from the APPLIED death set (post-deaths), or from
the KNOWN death set?* — deaths are deterministic given the frozen energy
snapshot, so the death set is knowable before it is applied. **If
post-deaths:** then `birth_first` under well-mixed changes **how many
births are admitted** (births are rationed against a population whose
deaths have not yet happened) — a different demographic regime, not a
phase offset — and that is the more important half of what the parameter
does, so the registry help text must say so. **If known-set:** the only
well-mixed effect is newborn exposure to the death phase, as described in
Design 5. **Write the answer into the help text either way.**

### Post-freeze addendum — VT-5 and VT-6 (added 2026-08-02)

These two tasks arrived AFTER this spec was frozen (`Status: in
progress`), delivered by the calibration-guide prompt that also produced
DECISIONS #113-#115. They are recorded here rather than in `docs/WIP.md`
because WIP.md is git-ignored and may never be the sole carrier of a
verification task or its answer (CLAUDE.md). Nothing above this heading
was edited. Neither task names a phase: VT-5 and VT-6(a) are read-only
code checks that can run in any phase, while VT-6(b) needs the
local-interaction machinery and so cannot run before Phase D.

**VT-5 — `threshold_cloning` shift-dependence.** Read-only, no code
change. In the `threshold_cloning` selection rule, is the survival bar
computed as `multiplier × generation_mean`? **If yes:** the calibration
guide's §3.5 table ships as written — the rule is shift-invariant only
at the default multiplier of 1.0, because under a shift `a` the bar
moves by `m × a` while individual scores move by `a`, leaving a relative
displacement of `(m − 1) × a`. **If the implementation differs:** report
the actual computation; the design layer rewrites that table row before
the guide is considered final.

**VT-6 — Joint flagship verification.** Two questions, one report.

*(a) Payoff ordering validator strictness.* Does
`game.enforce_pd_ordering` compare punishment against sucker strictly
(`P > S`) or leniently (`P >= S`)? **If strict:** #115's override of
`payoff_sucker = −1` is required and ships as decided. **If lenient:**
report it — the documentation describes the rule as strict, and a rule
documented one way and implemented another is a defect to be logged, not
a fact to build a scenario on. #115's override stands either way.

*(b) Matches per agent under spatial interaction.* Confirm empirically —
a short instrumented run is fine — how many matches each agent actually
plays per generation when `spatial_interaction` is on, `structure.kind =
lattice`, `neighbourhood_shape = von_neumann`, boundary `torus`, and
`opponents_per_agent` ≥ 4. **Expected: ≈ 8**, because Design 6 inherits
`RandomK`'s no-deduplication behaviour, so each agent initiates 4 and is
drawn by 4. **If ≈ 8 confirmed:** the flagship's `basic_living_cost`
must be calibrated against a cluster-interior cooperator income of ≈ 8R,
not 4R, and the Moore counterfactual in the scenario's things-to-try is
a four-fold income change rather than a two-fold one — both must be
checked against the scenario's actual living cost before the flagship is
trusted. **If ≈ 4:** the engine deduplicates after all, and Design 6's
text plus the calibration guide's §4.2 both need correcting. Report the
measured number either way.

**Answers so far (2026-08-02).** The two read-only halves were run in the
delivering session, since neither needs machinery that does not yet exist.
**VT-5: yes** — `ThresholdCloningSelection.select_parents` computes
`threshold = self._multiplier * (sum(scores) / n)`
(`pdsim/core/selection.py:302`), i.e. multiplier × generation mean, so the
calibration guide's §3.5 table ships as written; its parenthetical now
records that verification instead of flagging a pending check. **VT-6(a):
strict** — the validator tests `not (t > r > p > s)` as one chained
comparison (`pdsim/config/experiment.py:241`), so P = S raises; #115's
`payoff_sucker = −1` override is REQUIRED, not merely tidy, and the
flagship would fail validation without it. **VT-6(b) remains open** — it
needs local interaction and so cannot run before Phase D.

### Post-freeze addendum — phase-task ledger (added 2026-08-03)

Three tasks generated by the calibration-guide session (DECISIONS
#113–#115) fold into specific phases. Recorded here so each phase prompt
inherits them without a DECISIONS scan:

- **Phase B:** the #114 measurement task — log the shifted-weight spread
  at three points in a `fixed_n` run and report whether it grows faster
  than linearly. This is the empirical half of the claim #114 softened;
  the spec's frozen VT-3 wording above is superseded by #114 on this
  point.
- **Phase C:** the stake-plus-overhead validation fix — the check becomes
  `offspring_stake + reproduction_overhead <= reproduction_threshold`.
  ADVISORIES.md ("Not an advisory") schedules it for "the next time the
  validation module is touched"; Phase C touches that module for the K <=
  site-count validator, so Phase C is the carrier.
- **Phase D:** VT-6(b) above. Its measured number goes back to the design
  layer, which then checks the flagship's `basic_living_cost` and the
  calibration guide's §4.2 against it.

## Design 11 — registry shape, section order, and the greying map

### Section order

Structure sits between Population and Dynamics:

```
Game → Matching → Match → Population → STRUCTURE → Dynamics → Output → Run
```

Per #100(e), the registry's section order is inherited by the parameter panel
and by the generated `PARAMETERS.md` — deciding it once here decides it for
every consumer.

The rationale is the derived defaults. Three auto values now exist, and in
this order they resolve in reading order down the page: N is set in
Population; rows/cols auto-default from N in Structure; K auto-defaults from
the site count in Dynamics. **Each auto value's source sits above it** — by
the time a reader reaches a blank box that says "auto", everything the auto
rule reads has already scrolled past.

The accepted cost: `matching.spatial_interaction` stays in the Matching
section — the key is fixed by #108 and §2.12 — so the toggle renders four
sections above the interaction radii it governs. This was weighed rather
than overlooked: exactly one greying dependency points forward *either way*
(put the toggle in Matching and the Structure radii grey off an earlier
widget; imagine it in Structure instead and `matcher` would grey off a later
one), so #101's lookahead machinery is exercised identically and neither
placement is strictly cleaner. The registry key wins.

Within Matching: **`matching.spatial_interaction` is registered FIRST, above
`matcher`.** It is the gate, so `matcher` then greys off a sibling that
rendered *before* it — the clean direction, needing no lookahead at all.

### Radius nullability

Both radii are **nullable integers where blank means unlimited**, reusing
`population.memory_depth`'s existing "at least 1; may be empty" machinery
rather than inventing a sentinel value — the same reuse-over-invention call
#78 made for the float auto-defaults. This nullability is what makes §2.12's
"R → ∞ with β = 0 is well-mixed" **expressible as a parameter rather than as
a branch**: the infinite-reach corner is a blank box, not special-cased
code.

### The layout file is the seventh enum value

`from_file` joins the `initial_layout` dropdown, and `structure.layout_file`
is live only under it and greyed otherwise. **Rejected:** a non-empty
`layout_file` silently overriding the dropdown — that design produces the
bug report "I set the layout to checkerboard and it doesn't do anything",
with the cause sitting in a different widget the user filled in last week.
The chosen form is an idiom the app has already trained its users on:
`match.length_mode = continuation` is exactly what makes
`continuation_probability` live.

### The greying map

- Every other `structure.*` parameter greys under
  `structure.kind = well_mixed` (`kind` itself is the gate and stays live).
- `structure.layout_file` greys off `initial_layout = from_file`.
- `interaction_radius` / `interaction_decay` grey off
  `matching.spatial_interaction`.
- `matching.matcher` **greys** off `matching.spatial_interaction` (#108 —
  round-robin has no local analogue; the well-mixed matchers are the
  infinite-radius corner).
- `matching.opponents_per_agent` (k) **stays live always**, with the clamp
  explained in its help text (the #81 idiom, per #108: k does the work
  under spatial sampling).
- `carrying_capacity` stays **live** with its site-count derived default
  (#106 — K is the second cap, not a casualty of structure).
- `population.size` stays **live** and validated (N = site count under
  `fixed_n` + lattice).
- **`structure.birth_radius` / `birth_decay` STAY LIVE UNDER `fixed_n`.**
  They define the competition set for a freed site — which is the k that
  the b/c > k threshold counts (Design 7). Say it plainly, because the
  naive reading is the one a reader will arrive with: "birth parameters"
  sound irrelevant when the population is pinned and nobody breeds freely —
  and that reading is exactly backwards. Under `fixed_n` the birth kernel
  is *the* mechanism deciding who competes for every vacated seat; greying
  it would grey the heart of the Moran localisation.
- **`structure.placement_contest` is a three-way conjunction:** live only
  under synchronous **and** lattice **and** `energy_economy` (#107). This
  predicate spans Matching-adjacent, Structure, and Dynamics widgets, and
  points forward in registry order regardless of section placement.
- **`dynamics.boundary_order` is live under all synchronous runs**, greyed
  only under async — the Design 5 reasoning, now reinforced by VT-4's
  evidenced answer (the slots-rationing effect is present even under
  `well_mixed`; see the Phase C risk reading).

### `helpers.greying` has two branches — every rule must be slotted into both

Prompt 1A's inspection found that `helpers.greying` **delegates early to
`_async_greying`**: the synchronous and asynchronous paths are separate
code, and a rule added to one branch does not exist in the other. This is a
**Phase E obligation, stated with its reason**: a rule present in only one
branch produces exactly the failure #34 warns against — **the app asserting
something false about the user's run**. `dynamics.boundary_order` is the
sharp case, since its entire content is "live under sync, greyed under
async" — a statement about both branches at once, which no single-branch
edit can implement. Every `structure.*` rule needs a defined answer on both
sides, even where that answer is "greyed, because async never reads it."

### Two extensions to #101's lookahead

1. **Predicates, not single-key lookups.** `placement_contest` and the
   birth pair need a **conjunction** form — "live when A and B and C hold"
   — where the existing rules key off single widget values. Whether
   `helpers.greying`'s rule form already admits conjunctions is **not yet
   established**: Prompt 1A confirmed the return shape `(disabled, note)`
   and the #101 forward lookahead, but not the conjunction question.
   **Phase E therefore opens with an explicit task: inspect
   `helpers.greying` and report whether the rule form admits conjunctions**
   — rather than assuming either answer here.
2. **Resolvers callable at paint time.** The §12 obligation includes
   derived readouts (emergent site count, effective neighbour count).
   Displaying "auto → 10 × 10" next to blank rows/cols, or an honest K
   default beside the site count, means the panel must call the resolvers
   **with possibly-blank inputs while painting**. That is more than the
   lookahead currently does — the lookahead reads raw widget values; it
   does not run the `mode="before"` resolution logic that turns blanks into
   numbers. **The resolvers must be pure free functions callable from both
   the validator and the panel** — the M10a `resolve_initial_energy`
   pattern applied again. This is said here, in the spec, because the
   alternative is that Phase B hardcodes a display string that drifts from
   the validator's arithmetic.

### Build the greying map as a predicate table

**As data, not as conditionals scattered through panel code.** The greying
map is a table of "this parameter is inert when these conditions hold" —
so build it as that table, with the panel reading it. The payoff is one
milestone ahead: **hiding is then a second renderer over the same table**,
which makes M11b's tab/collapse work a *presentation* change rather than an
audit of scattered conditionals. This is cheap now and expensive later, and
it is the enabling piece M11a carries on behalf of M11b's user-interface
simplification (see the out-of-scope section and the docs obligations).

## Design 12 — site_capacity: the field ships, the knob does not

**`site_capacity` is NOT a registry parameter in M11a.** #104 requires the
**field** to ship, so that the placement check reads
`occupants < capacity` from day one and M19 never has to migrate the
placement seam. It does not require the **knob**. Capacity ships as a plain
field on `Site`, **pinned at 1 and validated as such**, with a constant on
the builder. Registering it would mean a panel widget with exactly one
legal value — a control that cannot be operated.

The deferral to **M19 is not on effort grounds** — one registry entry is an
afternoon — but because capacity > 1 forces three questions M11a has no
answers to:

1. **What the reach kernel does at distance zero.** Two agents sharing one
   site sit at d = 0 from each other, and exp(−β·0) = 1 — the *maximum*
   weight, for **every** β. No amount of decay could ever make a housemate
   less likely to be picked than a next-door neighbour. Allowing capacity
   > 1 without confronting this would smuggle a substantive modelling
   claim ("co-residents are always the most-preferred partners") in as an
   arithmetic side-effect.
2. **What colour a cell holding one cooperator and one defector is.** §6.3
   records this as open, and notes the trap: blending occupant colours
   softens cluster **boundaries**, and the boundary is the signal the
   whole Hammond–Axelrod story is about — which is why M19 likely wants
   both a blended and a dominant-strategy view.
3. **What k IS** when neighbourhood size becomes occupancy-dependent and
   changes every generation — which costs the b/c > k comparison its fixed
   reference point.

**The density dial M11a does have is `carrying_capacity`**: per #106, K
below the site count leaves permanent slack — a 20×20 grid at K = 250 runs
at roughly 60 % occupancy — in which the occupied region drifts, clusters,
and migrates. Density variation *across the map* is M11a-expressible;
density variation *within a cell* is what waits for M19.

**Mandatory record-keeping, in three places** — all three, so the deferral
cannot silently become a hole:

- the M11a DECISIONS entry records the pinned-at-1 field and names the
  three deferred questions;
- **ROADMAP's M19 entry gains an explicit TASK line** — "register
  `site_capacity` as a tunable registry parameter and remove M11a's
  pinned-at-1 validator" — stated as a task, not as background, so it
  cannot be read past;
- **this spec's own out-of-scope section carries it** (below).

Registering it later is **additive** — one registry entry plus removing one
validator — not a migration. #104's forward-guard is fully satisfied by the
field existing now.

## Parameters

All fourteen new knobs, in **widget order** — geometry first, then layout,
then the birth group, then the interaction group — with the phase each one
lands in:

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

Every entry carries a plain-language, mechanism-explaining description
(hard rules 1 and 3), **and every choice enum value is explained
individually** per the M10a §12 rule — the §12 checklist below is what
makes that obligation verifiable rather than aspirational. `python -m
pdsim.gendocs` is rerun in every phase that touches the registry, and the
regenerated `docs/PARAMETERS.md` is staged with it, because a pytest drift
test fails while it is stale.

## Phase plan

Five phases, matching M10b's shape. ▲ is the **proactive session-reset
marker**: a fresh Claude Code session starts at each one, because session
quality degrades before the hard context limit is reached — the reset is
scheduled rather than discovered.

**Phase A — the structure module, wired to nothing.**
`pdsim/core/structure.py`: the `Site` record (id, neighbour set, capacity,
optional coordinate); the `Structure` abstraction; `WellMixedStructure` as
the degenerate builder; `LatticeStructure` as the rectangular builder.
Distance as a structure-supplied method — Chebyshev for `moore`, Manhattan
for `von_neumann`. `sites_within()`, `kernel_weights()`, and the
`neighbourhood_sample()` primitive: implemented and tested, **called by no
engine**. The registry gets **only the geometry block** — `kind`, `rows`,
`cols`, `neighbourhood_shape`, `boundary` — plus `StructureConfig` with the
most-square derived default and its validators. **No engine imports this
module.** Every existing run is untouched *by construction*, so
byte-identity is trivially true and the phase is judged purely on whether
the abstraction is right.
Tests: degree counts under torus versus bounded (interior 8/4; corner 3/2
under `bounded`; uniform under `torus`); Moore versus von Neumann neighbour
sets at radius 1 **and** radius 2; most-square factorisation including the
prime-N 1×N line; distance symmetry and the triangle inequality; the four
kernel corners from #105 (R = 1; β = 0 with R = n; large β with R = n;
R → ∞ with β = 0).
**VT-1 runs first, before anything else in this phase.** ▲

**Phase B — occupancy: founding, layouts, rendering, persistence.**
The `Occupancy` object (Design 3). Agents acquire sites at generation 0.
All seven `initial_layout` values plus the layout-file mechanism and its
format. Site id enters `AgentSnapshot`, `agents.parquet`, and the schema
version. **And the grid renderer.**
The renderer lands **here, not in Phase E**, on app-first grounds
(#42/#61): there is no honest way to validate a layout except to look at
it. "Load the scenario, set `initial_layout = checkerboard`, see a
checkerboard" **is** the validation; a test asserting that site 0 and site
1 hold different strategies is a proxy for it. Phase B needs a renderer
that is **correct at a few hundred cells**; the pixel-array fallback and
the ≈ 3 px floor wait for Phase E.
Note the one refactor this phase hides: **`AGENTS_COLUMNS` is currently a
fixed tuple**, so the conditionally-present `site_id` column means the
writer must vary its column set by run type and the loader must stay
presence-driven (#100(b)). This is a small change, not a schema conflict —
but it is a *change* rather than a pure addition, and should be budgeted as
one.
After B, structure exists and is visible but **nothing reads it**.
Behaviour is unchanged.
**VT-2 and VT-3 run in this phase.** VT-2's expected answer (ids preserved)
is already evidenced, so Phase B implements Design 10's nothing-to-persist
branch and reports confirmation; **if the runtime behaviour diverges from
that evidence, stop and report rather than switching branches
unilaterally.** ▲

**Phase C — local birth. THE RISKIEST PHASE.**
`place_offspring` becomes structure-aware; `admit_births` keeps its
global-gate job. `birth_radius` / `birth_decay`; `placement_contest`;
`dynamics.boundary_order`. K as the second cap with the site-count derived
default and the K ≤ site-count validator; the `fixed_n` + lattice
N = site-count validator. Death frees a site, birth occupies one. The
Design 9 RNG contract amendments and their golden masters.
**VT-4 runs in this phase**, and its answer is already evidenced as the
post-deaths branch — see the risk reading below for what that costs. ▲
**This phase is also the candidate for a fifth, mid-phase reset.** Flagged
here so it is planned rather than discovered in a handback.

**Phase D — local interaction.**
`matching.spatial_interaction`; `interaction_radius` /
`interaction_decay`; the `SpatialKernel(Matcher)` synchronous adapter over
the Phase A primitive; the async loop calling the primitive directly; the
k clamp; the `spatial_interaction` requires `lattice` validator.
**Also in this phase: correct `matcher.py`'s stale module docstring.** It
currently justifies the `Matcher` abstract base class taking full `Agent`
objects on the grounds that a future `SpatialKernel` would need
`agent.position` — a continuous-coordinate plan dropped by #104. Replace
the justification with the real one: `SpatialKernel` holds the structure
and occupancy at construction, and an agent's location is its site. A
comment change with no behavioural effect, scheduled here because Phase D
is when someone implementing `SpatialKernel` would otherwise read it and go
looking for an attribute that does not exist. ▲

**Phase E — polish.**
The full greying map **built as a predicate table** (Design 11), slotted
into **both** `helpers.greying` branches; the pixel-array rendering
fallback and the size floor; the named validation scenarios; the bench
structure column; `python -m pdsim.gendocs`; and the §12 checklist audit
run **item by item against the enumerated list below, with coverage
reported**.
Phase E **opens** with the `helpers.greying` conjunction inspection
(Design 11).

### Risk reading

This sub-section is the part a resuming session most needs.

**C is riskiest — and not because it changes demography. C is riskiest
because its failures are SILENT.**

**(i) It amends a sequence #80 declares frozen, and the amendment is a
GATE.** A gate has two failure directions and they fail differently.
Drawing the contest permutation when structure is **off** breaks
byte-identity on every existing seeded run — loud, caught immediately by
the negative pins. **Not** drawing it where contention genuinely exists is
**silent**: the run completes, the numbers look plausible, and the golden
master for that configuration pins the wrong stream forever. #107 confines
contention to exactly one configuration (synchronous + structure +
`energy_economy`), and **the correctness of that confinement is an
argument, not a test**. The async and `fixed_n` exclusions therefore need
pins asserting **no draw occurs** (Design 9's counting wrapper), not merely
that the result is reproducible.

**(ii) `place_offspring` can fail for the first time.** #80 checked
placement before payment against a stub that always returned true. The
branch now goes live, and the consequence is behavioural: a parent walled
in by occupied neighbours pays nothing, stays eligible, and keeps
accumulating. Correct — it is the whole content of viscosity — but an agent
sitting at five times θ and not breeding **reads as a bug** unless the
Economy panel says "blocked: no site in reach." That readout is a **Phase C
deliverable**, on the #89(e) logic that put the calibration readout into
M10a.

**(iii) Two orderings become three, and they can silently collapse.** #80
keeps admission order (energy descending, id ascending) separate from
iteration order (parent-id ascending), pinned by a test where they differ.
Phase C inserts a contest permutation between them. **The specific bug:**
applying the permutation to a list that has **already** been energy-sorted
and then iterating the result — which yields a `random` contest that is
quietly energy-biased in exactly the way #107 rejected. The pin needs a
fixture where **all three orders differ pairwise**, harder to build than
#80's two-way case, and **it should be written before the code it tests**.

**(iv) A boundary-order bug produces PLAUSIBLE DYNAMICS, not a crash.**
Under `death_first` versus `birth_first` the set of available sites
differs — the whole content of #107. Get it wrong and you get a frontier
that behaves like an interior, which is the mechanism M12 is being built
to study.

**(iv-a) VT-4's expected answer — evidenced by code inspection during the
spec drafting, and pending Phase C's runtime confirmation — makes
`boundary_order` doubly restrictive, and this must be written into the
help text.** Design 5's hedge ("VT-4 may add a second, larger effect") and
the open VT-4 task both stand deliberately: reading source code is
evidence, not runtime verification, and the spec holds the two apart.
`slots = max(0, K − len(survivors))`
reads the **applied post-death** list. Work the arithmetic through, because
the size of the effect is the point. Take K = 200, a living population of
180 entering the boundary, and 20 deaths:

- under `death_first`, deaths land first, survivors = 160, so
  slots = 200 − 160 = **40 births admitted**;
- under `birth_first` there is no post-death list yet, so the ration is
  computed against the pre-death population:
  slots = 200 − 180 = **20 births admitted**.

`birth_first` admits roughly **half** the births in this example — and
*then* the death phase runs and those newborns face the age-mortality coin
as well. The parameter is restrictive twice over, and both effects push
population down relative to `death_first`. **A `birth_first` run sitting at
a visibly lower population is correct, not broken**, and the registry help
text must say so rather than leaving it to be rediscovered. This is a
different demographic regime, not a phase offset — and it is present
**even under `well_mixed`**, which is a second, independent reason the
Design 5 decision to keep the parameter live under all synchronous runs
was right.

**Second-riskiest is B.** Founding placement is where structure meets
#67's three-bucket composition, and a mistake there is a **systematic bias
present in every run from generation 0**. It is caught by **looking** at
the grid — the strongest argument for the renderer landing in B.

**Third is D, and its risk is well-shaped**: an additive change at the
`Matcher` seam — the extension point `RandomK` already proved in M8 under
#57 — with the async side a **substituted** partner draw rather than an
inserted one.

## The §12 checklist (54 items)

What this is, and why it is enumerated rather than described: DESIGN
§2.12's M11a spec obligation, restated by #103, requires that every new
concept, **every enum value individually**, and every derived readout
carries an inline `(?)` explanation drawn from a **single described
source**, so that app text and documentation cannot drift apart. Roughly
fifteen parameters arrive at once, and a parameter-level description
silently skips the enum values inside it — `moore` and `von_neumann` each
need their own explanation, not merely the parameter that holds them.
The groups total **14 + 17 + 14 + 9 = 54**. **Phase E runs this list item
by item as an audit pass and reports coverage.**

**14 registry parameters** — a plain-language description each.
Structurally guaranteed by DESIGN §5 (a parameter cannot exist without a
description), but listed so the checklist is complete rather than partly
implicit:

1. `structure.kind`
2. `structure.rows`
3. `structure.cols`
4. `structure.neighbourhood_shape`
5. `structure.boundary`
6. `structure.initial_layout`
7. `structure.layout_file`
8. `structure.birth_radius`
9. `structure.birth_decay`
10. `structure.placement_contest`
11. `structure.interaction_radius`
12. `structure.interaction_decay`
13. `matching.spatial_interaction`
14. `dynamics.boundary_order`

**17 enum values, each individually explained** — this is the part §12
exists for:

1. `well_mixed`
2. `lattice`
3. `moore`
4. `von_neumann`
5. `torus`
6. `bounded`
7. `random` (layout)
8. `checkerboard`
9. `stripes`
10. `blocks`
11. `patches`
12. `central_block`
13. `from_file`
14. `random` (contest)
15. `energy_priority`
16. `death_first`
17. `birth_first`

**14 concepts**, each with a `(?)` drawn from one described source:

1. site
2. exclusivity and capacity
3. neighbour and neighbourhood
4. support radius R
5. decay β
6. the reach kernel
7. viscosity
8. wrap-around, and why it equalises degree
9. degree, and why cooperation thresholds depend on it
10. the two gates, and why clearing one is not enough
11. a blocked parent
12. arrangement versus composition
13. the b/c > k threshold — the explanation must say that b and c only
    **exist** when T − R = P − S (additivity), and that under a
    non-additive matrix the ratio is ambiguous rather than merely
    inapplicable
14. spatial reciprocity

**9 derived readouts**, each with a `(?)` **and a visible number**:

1. emergent site count
2. resolved rows × cols when blank
3. resolved K when blank, shown alongside site count (#106's both-numbers
   guard)
4. effective neighbour count after the clamp — the k the threshold
   compares against
5. occupancy as a fraction
6. agents with zero occupied neighbours at founding
7. blocked parents this generation
8. whether pixel-array rendering is active
9. payoff additivity — inspects the four payoff values and reports either
   that they are additive, with the resolved b, the resolved c, and the
   ratio ("additive: b = 5, c = 1, b/c = 5"), or that they are **not**
   additive, so the b/c > k threshold does not apply, with the one-line
   reason (cooperating costs a different amount against a cooperator than
   against a defector)

The additivity readout earns its place on exactly the §12 spirit that put
blocked parents and the founding-isolation count into the Economy panel:
it makes an otherwise invisible precondition visible at the moment the
user is in a position to act on it. Its implementation shape is a **pure
function of four registry values**, slotting directly into the paint-time
resolver pattern Design 11 already mandates — a pure free function
callable from both the validator and the panel, no new machinery. It lands
in **Phase E**, with the rest of the §12 audit.

**Two of those readouts are more than tooltips and belong in the Economy
panel**, not only in help text:

- **blocked parents** — stops a correct behaviour reading as a bug (risk
  reading (ii));
- **zero-neighbour agents at founding** — the guard on `random` scattering
  under a sparse population (Design 8).

## Validation

APP-FIRST (#42/#61). With the virtual environment active
(`.venv\Scripts\Activate.ps1`), launch `streamlit run pdsim/ui/app.py`.
Automated tests **complement, never substitute**.

- **V1 (app) — structure exists and is visible.** The lattice renders,
  cells are exactly square, and the site count is reported. *Phase B.*
- **V2 (app) — layouts.** Walk `initial_layout` through all seven values
  and see each arrangement. *Phase B.*
- **V3 (app) — viscosity.** Cooperator clusters survive where they would
  be wiped out well-mixed. *Phases C + D.*
- **V4 (app) — `boundary_order`.** Same configuration, `death_first`
  versus `birth_first`, divergent outcome. **Run this in two passes,
  because VT-4 established two independent effects and one run cannot tell
  them apart.** First pass with **age-mortality off**: the newborn-exposure
  channel is silenced, so any divergence is the slots rationing alone, and
  the `birth_first` population should sit visibly lower per the risk
  reading's worked example. Second pass with mortality on: both channels
  live, and the divergence is larger. *Phase C.*
- **V5 (app) — the drifting frontier.** K below site count; the occupied
  region migrates. *Phase C.*
- **V6 (app) — the b/c > k threshold.** von Neumann clears, Moore fails.
  *Phase D.*
- **V7 (command line, headless) — golden masters, positive and negative.**
  *Phase C.*
- **V8 (command line, headless) — byte-identity regression** on four
  well-mixed configurations. *Every phase.*

### Four new registered scenarios

**`spatial_reciprocity` / "Cooperation Survives in Clusters" — THE
FLAGSHIP.** Synchronous `energy_economy`, lattice, local interaction and
local birth at R = 1, roster AllC and AllD only, one round per match —
with two **explicit scenario settings** that override registry defaults:
**`neighbourhood_shape = von_neumann`** and **`payoff_punishment = 0`**
(both recorded as decisions in #111). Cooperators in a cluster earn R from
all four neighbours; defectors in a defector interior earn P = 0 from
everyone and starve under the living cost. P = 0 is *set*, not left at its
default of 1, because it is what makes the mechanism work: the scenario's
whole claim is that a defector interior earns **nothing** against the
basic living cost L — at P = 1 with eight Moore neighbours, a defector in
a solid defector block earns 8 per round, which may well clear L, in which
case nobody starves, cooperator clusters gain no relative advantage, and
the flagship demonstrates nothing. The shape override pushes the same way:
fewer neighbours means stronger viscosity and an easier time for
clustering, so von Neumann is the configuration most likely to actually
show cooperation surviving — which is what a flagship scenario is for.

One conceptual guard, written here because it is easy to blur: this
scenario does **not** rest on the Ohtsuki mechanism. Its story is
**ecological** — absolute income measured against a survival threshold,
with P = 0 meaning a defector interior earns nothing. Ohtsuki's b/c > k is
about **relative fitness in a Moran process under weak selection**, and
that is `donation_game_threshold`'s scenario, not this one. The two
arguments happen to point the same way; the spec must never let a reader
think one is the other.

Things-to-try: switch `structure.kind` back to `well_mixed` and watch AllD
take everything; and switch `neighbourhood_shape` to `moore` and watch the
clusters struggle — degree-dependence taught for free, #36-compliant (one
scenario, one configuration; comparisons live in things-to-try).

**`donation_game_threshold` / "The b/c > k Threshold"** — the Ohtsuki
replication attempt. **Unblocked by VT-1**: payoff parameters admit
negatives, so T = 5, R = 4, P = 0, S = −1 ships as designed and b/c = 5 is
intact. Four non-obvious requirements, each of which the scenario text
must explain rather than merely set:

- **`rounds_per_match = 1`, roster AllC + AllD only.** Ohtsuki's threshold
  is derived for **one-shot** games; with 50 rounds and TitForTat in the
  roster the threshold does not apply, and at one round TitForTat
  cooperates and is indistinguishable from AllC anyway. Consequence:
  noise, memory depth, and every reciprocity parameter are **inert here**
  — the scenario text says so, rather than leaving a novice wondering
  where the seven-strategy roster went.
- **`fixed_n_death_rule = pure_random`, NOT the default.** Ohtsuki's
  death-birth is: a random individual dies, then its neighbours compete by
  fitness. The M10b default `energy_decides` makes the death
  deterministic. Getting this wrong yields a plausible run that is not the
  model being replicated.
- **The weak-selection honesty caveat, worded per VT-3's now-known
  answer.** The breeder draw reads **accumulated energy** through #63's
  shift with **no selection-intensity parameter**, so we cannot approach
  the weak-selection limit in which b/c > k is derived. State two things
  plainly: the threshold is a **calibration compass, not a prediction**;
  and because fitness reads a **stock rather than a flow**, relative
  differences widen as a run proceeds, so **effective selection
  strengthens over time**. This wording is contingent on Phase B's VT-3
  confirmation.
- **Additivity: T − R = P − S — the payoff values are not arbitrary.** The
  b/c > k rule is derived for the **donation game** specifically, not for
  a general Prisoner's Dilemma matrix: a cooperator pays a cost c so the
  opponent receives a benefit b, a defector pays and provides nothing —
  in matrix terms T = b, R = b − c, P = 0, S = −c. Read the cost of
  cooperating off that matrix twice: against a cooperator,
  T − R = b − (b − c) = c; against a defector, P − S = 0 − (−c) = c. The
  same number — cooperating costs c **regardless of what the other player
  does** — and the benefit falls out symmetrically (T − P = b and
  R − S = b). This property is called **additivity**, or "equal gains from
  switching". The scenario's T = 5, R = 4, P = 0, S = −1 passes the test:
  T − R = 1 = P − S, so c = 1; T − P = 5 = R − S, so b = 5; **b/c = 5
  unambiguously** — and the design falls straight out (von Neumann's
  k = 4 clears, Moore's k = 8 fails). The registered defaults T = 5,
  R = 3, P = 1, S = 0 **fail** it: T − R = 2 against P − S = 1 — a
  perfectly valid Prisoner's Dilemma (T > R > P > S holds; 2R > T + S
  holds, 6 > 5) that simply is **not a donation game**, under which "b/c"
  is not a well-defined quantity at all: two candidate benefits
  (T − P = 4, R − S = 3) against two candidate costs (T − R = 2,
  P − S = 1) give four defensible readings — 2.0, 4.0, 1.5, 3.0 — of
  which two clear k = 4 and two do not, so a user could "predict" either
  outcome by choosing a definition. That is the signature of a malformed
  question, not a hard one. This is also the deeper reason VT-1 mattered:
  additivity with P = 0 *forces* a negative sucker payoff, so S = −1 is
  not a stylistic choice. And the payoff parameters are live registry
  values, so a user can nudge a slider and silently destroy the thing
  being demonstrated — which is what the things-to-try warning below and
  the §12 additivity readout are for.

Ships as **von Neumann** — the case that **clears** the threshold, so the
default view shows cooperation succeeding. #36 says one scenario = one
configuration and comparative questions live in the things-to-try text, so
the things-to-try note says: switch `neighbourhood_shape` to `moore` and
re-run, **predicting the reversal before doing it**. Two scenarios
differing in one enum value would duplicate the mechanism things-to-try
exists for. A second things-to-try warning: changing the payoffs is fine
and encouraged — but the threshold only applies while **T − R = P − S**
holds, and the additivity readout will say when it no longer does.

**`the_drifting_frontier` / "The Drifting Frontier"** — K at roughly 60 %
of site count, so #106's slack is live and the occupied region clusters
and migrates rather than filling the grid.

**`the_filling_grid` / "The Filling Grid"** — `central_block` layout,
growth economy, expansion into empty space. The Kaznatcheev & Shultz
regime, and the reason #109 shipped that layout.

### Bench: the structure column

**Yes, and it tests a falsifiable claim** (#91/#102 discipline, not
decoration).

Local interaction **reduces** match-phase work: k clamps to the
neighbourhood — 4 or 8 at R = 1, against round-robin's N − 1. The
interesting cost is the **kernel draws**, where the naive implementation
scales badly: enumerating sites within radius R is O(R²), and at R = 10
under Moore that is 440 sites enumerated, distance-computed, and weighted,
once per focal per event.

**The fix is precomputation**, available because of Design 3's
topology/occupancy split. Topology is immutable, so the candidate list for
each site at each radius is a pure function of the configuration and can
be built once. Weights are cacheable more cheaply still: weight depends
only on **distance**, so **one distance→weight lookup table per (R, β)
pair** covers every site on the grid. Per-draw cost then scales with
neighbourhood size rather than with enumeration. Memory stays modest —
10,000 sites at 440 neighbours each is a few million integers.

**Two hypotheses, stated so the measurement can fail:**

1. cost is **flat in R** once the cache is warm;
2. the lattice column sits **at or below `random_k`** at equal k.

If (1) fails, the cache is not working. If (2) fails, the kernel draw is
more expensive than the matches it replaces — a surprise worth chasing.

Grid: N × {`round_robin`, `random_k`, `lattice_vn_r1`, `lattice_moore_r1`,
`lattice_moore_r5`}. Measured at **Phase E**. **Rendering cost stays out**
— that is #94's wall-clock throttling on a separate axis, and the bench
measures the engine. Output remains environment-specific and uncommitted.

## Out of scope

- **`site_capacity` above 1** — the field ships pinned at 1 (Design 12);
  the knob is M19, and ROADMAP's M19 entry carries it as an explicit task
  line.
- **The M11a explainer.** A separate prompt, after a literature
  verification pass. Its scope, at the owner's explicit request, covers
  two things beyond the milestone's own mechanisms: the **full constraint
  structure on T, R, P, S** — the Prisoner's Dilemma ordering
  T > R > P > S; the 2R > T + S condition and what goes wrong without it
  (alternating exploitation becomes the best joint strategy); and the
  **additivity condition T − R = P − S**, with the donation-game
  construction that produces it — and the **meaning and significance of
  the Ohtsuki threshold**: what b/c > k claims, the assumptions it rests
  on, and **why k appears at all** (k counts the competitors for a vacated
  site). Four claims must be checked against publisher records before they
  enter it:
  1. whether Hammond & Axelrod used **wrap-around** on their 50×50 lattice
     (UNVERIFIED, #103);
  2. the Kaznatcheev & Shultz **300-period figure** quoted by the M10
     explainer without a verification note of its own (UNVERIFIED, #103);
  3. the **structure-coefficient generalisation** of the threshold to
     non-additive matrices — the σ formulation and whether
     σ = (k+1)/(k−1) is correctly attributed (Tarnita et al. 2009 / Nowak
     et al. 2009 are the likely sources; this must be checked, not
     assumed — see #111);
  4. the **precise assumption set** behind b/c > k — donation game, weak
     selection, large population, pair approximation on regular graphs —
     verified against Ohtsuki et al. 2006 rather than reconstructed.
  The standing rule: **claims derived by consistency check are not
  citations**, and nothing enters an explainer until it is verified
  against publisher records. Note that the `neighbourhood_shape` default
  is `moore` by the owner's call, **so the Hammond–Axelrod wrap-around
  verification no longer gates the default** — but it still gates the
  explainer and M12's replication scenario.
- **The user-interface tab / collapse / novice-advanced implementation.**
  That is M11b, deliberately **not** beside the riskiest phase in this
  milestone: a panel rewrite landing next to Phase C would make any
  regression ambiguous between "structure broke something" and "the panel
  rewrite broke something." What M11a carries is the **enabling piece** —
  the greying map as a predicate table (Design 11) — plus the DECISIONS
  entry recording the decision (docs obligations, below).
- **Everything M11b**: agent movement, the `MovementRule` abstract base
  class, the walk radius/decay pair, the movement schedule, the mouse
  layout painter.
- **Irregular and geographic site sets, and co-residency semantics** —
  M19.

## Docs obligations

Numbering continues from **#110**. Specs are frozen historical records
(#62): deviations during implementation become **new DECISIONS entries,
never retro-edits** of this file beyond its status line.

**DECISIONS entries the M11a work must produce:**

- the build decisions carried by this spec, as implementation proceeds,
  and wherever a deviation from it occurs;
- **Open Question 1's resolution** (Design 7) — the localisation of the
  async `fixed_n` breeder/victim draws, with the sync-imitation
  global-selection decline recorded **explicitly on scope grounds** and
  handed to M12;
- the **`site_capacity` pinned-at-1 field** and its three deferred
  questions (Design 12);
- **the tabs decision, recorded even though nothing is built.** This one
  is written out at length here because it is the piece most likely to be
  lost — a decision about UI work that M11a deliberately does not do:
  - the `run.mode` tab split — evolution and tournament as separate tabs
    is the one clean fork the panel has;
  - **the total-fork criterion** — hide a parameter only where **every**
    parameter on the far side of the fork is genuinely ignored, with no
    exceptions and no partial cases. The reason: a **greyed** widget says
    "this exists and does nothing here", while a **hidden** one says
    "this is irrelevant here" — and if the second claim is ever wrong,
    the user cannot see the parameter that is affecting their run;
  - **why `time_model` FAILS that criterion**: `selection_beta` follows
    the imitation **overlay**, not the mode (#101's carve-out), and the
    ledger knobs — L, engagement, r, σ — apply under the synchronous
    economy **and** both asynchronous population modes. Dynamics has a
    shared core with two mode-specific wings, not a clean cut;
  - **why `reproduction_mode` fails it too**: the same shared-ledger
    problem, plus async `variable_n` **being** the economy under a
    different clock;
  - **collapse-with-summary** as the treatment for inert sections — a
    collapsed section that names itself and its state, rather than
    hiding;
  - **novice/advanced disclosure as a separate, orthogonal axis**
    deserving its own decision.

**ROADMAP amendments:**

- **M19's entry** gains the explicit `site_capacity` registration
  **task** line (Design 12's wording);
- **M11b's entry** gains the user-interface simplification line (tab
  split + collapse + novice/advanced), alongside the layout painter.
