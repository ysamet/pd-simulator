# DESIGN.md — Evolutionary Prisoner's Dilemma Simulation Platform

> Model and architecture specification. This is the authoritative reference for what the
> platform is and how it is structured. Changes to the model design are made here first,
> with rationale logged in `DECISIONS.md`. See `ROADMAP.md` for version scoping.

## 1. Vision

A simulation platform for studying how success accumulates in populations of agents
playing repeated Prisoner's Dilemma (and, later, n-player social dilemma) games under
evolutionary selection. Long-term goal: model real-world societal and geopolitical
conflict dynamics (reputation, sanctions, alliances, geography) within this framework.

Guiding principles:

1. **Every model dimension is a parameter.** All mechanisms discussed in design are
   eventually tunable from the GUI. v1 implements a subset, but every subsystem is
   built behind an interface so later options plug in without surgery.
2. **Headless engine, thin UI.** The simulation engine has zero UI dependencies. The UI
   only (a) builds an `ExperimentConfig` and (b) renders result streams. The UI layer is
   replaceable (Streamlit in v1; richer dashboard later).
3. **Novice-first explanations.** The user is not assumed to be a game-theory expert.
   Every parameter and every strategy has a plain-language explanation, maintained in a
   single Parameter Registry from which UI tooltips and documentation are generated.
4. **Reproducibility.** Every run persists its full config + RNG seed + results. Any
   experiment can be exactly re-run and compared.

## 2. Core model (v1)

### 2.1 Game: pairwise repeated Prisoner's Dilemma

- Two actions per round: **C** (cooperate) / **D** (defect).
- Payoff matrix (tunable; standard defaults): T=5 (temptation), R=3 (reward),
  P=1 (punishment), S=0 (sucker).
- Validation toggles: enforce `T > R > P > S` (PD ordering) and `2R > T + S`
  (mutual cooperation beats alternating exploitation). Both ON by default; user may
  relax them to explore neighboring games (e.g., Chicken, Stag Hunt orderings).
- The engine treats the game behind a `Game` interface (participants + actions →
  payoffs) so n-player games (Public Goods Game and variants) are v2 drop-ins.

### 2.2 Population and memory

- Population of N agents; each agent holds one strategy instance.
- **Memory:** each agent has access to its full per-opponent interaction history
  (multi-player repeated environment → built-in direct reciprocity/reputation between
  pairs). An optional `memory_depth` constraint caps how far back strategies may look.
- Agents have stable identities across a generation, so an agent meeting a repeat
  opponent can recognize it (this is what makes per-opponent memory meaningful).

### 2.3 Strategy roster (v1)

All strategies implement the `Strategy` ABC. Initial set:

| Strategy | Summary |
|---|---|
| AlwaysCooperate | Cooperates unconditionally. |
| AlwaysDefect | Defects unconditionally. |
| Random(p) | Cooperates with probability p each round. |
| TitForTat | Cooperates first; then mirrors opponent's previous move. |
| GenerousTitForTat(g) | TFT, but forgives a defection with probability g. |
| GrimTrigger | Cooperates until first opponent defection; defects forever after. |
| Pavlov (Win-Stay-Lose-Shift) | Repeats last action if it paid well (T or R); switches otherwise. |

Each strategy carries: machine name, display name, novice-friendly description,
parameter definitions (registered in the Parameter Registry), and literature notes.
This metadata lives in the **Strategy Registry**
(`pdsim/core/strategies/registry.py`): one `StrategyInfo` declaration per strategy
module, auto-discovered by importing the package (see DECISIONS #25). The v1
machine names — the identifiers configs use — are `always_cooperate`,
`always_defect`, `random`, `tit_for_tat`, `generous_tit_for_tat`, `grim_trigger`,
`pavlov`. Strategy parameters use registry keys `strategy.<machine_name>.<param>`;
defaults: Random p = 0.5, GTFT g = 1/3 (see DECISIONS #26, including Pavlov's
moves-only "win = opponent cooperated" derivation).

Per-run parameter overrides live in the optional top-level `strategy_params`
config section, mapping machine name → `{parameter: value}` — one parameter set
per strategy per run, overriding the registry defaults (DECISIONS #30).
Heterogeneous same-strategy variants in one population are a v2 concern
(parameter-perturbation mutation). A strategy may appear in `strategy_params`
without being in the composition: mutation can still introduce it mid-run, and
its configured parameters then apply.

### 2.4 Matching (who plays whom)

Behind a `Matcher` interface:

- **RoundRobin** (v1 default): every pair plays one match per generation. O(N²) matches.
- **RandomK** (v1, shipped in M8): every agent *initiates* k matches against k
  distinct opponents drawn uniformly without replacement
  (`matching.opponents_per_agent`); duplicate pairs across initiators are
  allowed, so total matches = N·k and per-agent participation varies (k
  initiated + however often the agent is drawn). Raw scores therefore include
  participation luck — deliberate: the raw total remains what selection acts
  on, and the per-round score view is the participation-normalized comparison.
  All pairings are drawn at the start of the match phase, in agent-id order;
  k ≤ N−1 is validated cross-parameter, and k is ignored (greyed in the UI)
  under round_robin. Exact semantics and RNG order: DECISIONS #57.
- **SpatialKernel** (M11a): partners sampled from within the interaction
  radius by the soft reach kernel — the sync-side adapter over the structure
  module's `neighbourhood_sample` primitive. See §2.12 and §6.3.

### 2.5 Match length

Per-match round count, two modes (both in v1, UI-selectable):

- **Fixed**: exactly `rounds_per_match` rounds.
- **Continuation probability**: after each round the match continues with probability
  `w` (expected length 1/(1−w)). Theoretically important: a known fixed horizon invites
  end-game defection by backward induction; probabilistic continuation models "the
  shadow of the future."

### 2.6 Noise

- **Execution error ε** (v1): with probability ε an agent's played action flips from
  its intended action. The classic robustness test separating brittle strategies
  (GrimTrigger) from forgiving ones (GTFT, Pavlov).
- **Perception error** (future option): an agent misreads the opponent's action.

### 2.7 Selection and reproduction (v1 dynamics package)

- **Fixed population size** N; synchronous generations (all matches played → scores
  computed → entire next generation selected at once).
- **Selection rule** behind a `SelectionRule` interface. v1 ships **Fermi
  (pairwise-comparison)**: for each next-generation slot, sample agents A (incumbent)
  and B (model); A adopts B's strategy with probability `1 / (1 + exp(-β (s_B − s_A)))`.
  All slots sample the current generation's scores and apply simultaneously; exact
  sampling and RNG-order semantics in DECISIONS #32.
  - **β = selection intensity**: 0 → pure drift (score irrelevant);
    large → near-deterministic copying of higher scorers. First-class experimental knob.
  - **Four further rules** shipped in M9a behind the same interface
    (semantics, draw orders, and tie-breaks pinned in DECISIONS #63):
    **proportional** (roulette on min-shifted weights), **tournament_k**
    (k-candidate contests per slot; k ≤ N cross-validated; unrelated to the
    tournament run mode), **truncation** (elitist: parents drawn from the
    top-q elite), and **threshold_cloning** (agents at or above θ·mean keep
    their slots; the rest are refilled from the survivor set). Every rule
    consumes the **effective** score supplied by score accounting (below);
    each rule's parameters are ignored (greyed in the UI) under other rules.
- **Mutation**: with probability **μ**, a newly produced agent receives a uniformly
  random strategy from the enabled roster instead of the copied one (strategy-switch
  mutation). In v1 the enabled roster is the **full registered roster** — mutation may
  introduce strategies absent from the initial composition; mutants are constructed
  with the run's `strategy_params` (DECISIONS #30/#32). μ=0 ⇒ perfect cloning.
  Parameter-perturbation mutation (Gaussian noise on continuous strategy parameters,
  enabling true strategy evolution) is a v2 mode behind the same reproduction interface.
- **Score accounting** (`pdsim/core/accounting.py`, M9a — DECISIONS #64): a
  `ScoreAccounting` rule folds each generation's raw scores into per-slot
  state and supplies the **effective** scores selection consumes —
  `per_generation` (default: identity, exactly the classic behavior),
  `sliding_window` (mean of the last W generations), or
  `exponential_discount` (EMA with discount λ). Accounting state belongs to
  the agent slot and survives strategy switches; it consumes no RNG draws
  and is invisible outside the selection phase — raw scores still reset
  each generation (DECISIONS #31) and remain what events, charts, and
  persistence report. Cumulative accounting stays a future option (§6.1).

### 2.8 Randomness

Single seeded RNG (numpy `Generator`) injected everywhere; seed recorded in every
run's saved config. No module may create its own unseeded RNG.

### 2.9 Run modes

Every experiment runs in one of two modes (registry: `run.mode`; DECISIONS #34):

- **evolution** (default): the full evolutionary loop of §2.7 — synchronous
  generations, selection, mutation, per-generation resets.
- **tournament**: Axelrod-style — a fixed cast of agents keeps its initial
  strategies for the entire run. Each **cycle** (`run.tournament_cycles`) is one
  complete matcher pass (round-robin: every pair plays one match). There is no
  selection, no mutation, no generation boundary, and no reset: scores and
  per-opponent histories accumulate across the ENTIRE run. With respect to the
  history-view semantics (DECISIONS #22/#31), a tournament behaves as **one long
  generation** — `round_number` is cumulative across all cycles. This is the
  intended direct-reciprocity behavior, not an accident: GrimTrigger stays grim
  in cycle 2 about a betrayal from cycle 1. RNG draw order: the match-phase
  order of DECISIONS #23, repeated per cycle — no selection or mutation phases.

Selection, mutation, and generation-count parameters are **ignored** in
tournament mode — valid in the config but without effect, NOT a validation
error — so configs can switch modes without surgery and the UI can simply grey
those parameters out (DECISIONS #34).

### 2.10 The energy economy (M10a — reproduction mode `energy_economy`)

A second evolutionary paradigm beside imitation, selected by
`dynamics.reproduction_mode` (DECISIONS #77): **birth-death dynamics**.
Agents hold a stock of **energy** — a persistent asset, unlike the
per-generation score flow — earn it by playing, pay it to exist, and spend
it on children. Differential survival IS the selection: in `energy_economy`
mode the whole SelectionRule family and ScoreAccounting are ignored (the
#34 greyed-not-hidden pattern), while mutation μ still applies to newborns.
Population size becomes **variable** — the load-bearing v2 invariant: it is
constant within a generation and changes only at the boundary. Runs can end
early at **extinction**, a legitimate outcome.

The per-agent state: `energy`, `age`, and a lifetime **passport id** with
`parent_id` lineage — ids are never reused, so the family tree is exact and
id-ordering survives death-created gaps. Per-opponent histories **persist
for an agent's whole life** (an economy agent is a persistent creature; the
#31 clearing rationale is selection-specific — DECISIONS #79); only scores
reset per generation. GrimTrigger is lifetime-grim; `memory_depth` is the
history-copy cost bound.

The boundary sequence (`EconomyDynamics.step()`, frozen in DECISIONS #80;
amended by M11a Phase C per #107 — the amendment gated so every well-mixed
run is byte-identical to its pre-M11a stream, pinned by golden masters):
match phase (unchanged) → report-as-played → **energy update**
(`e ← e·(1+r) + score − L − engagement·matches`, deterministic) → the
**death phase** (age mortality: one coin per living agent in ascending id
order, only when the mortality trio is active; then insolvency deaths,
`e < 0`, strictly negative, deterministic — each death vacates its site
on a lattice) and the **birth phase** (eligible at `e ≥ θ`; free seats
under carrying capacity K filled by energy-priority admission, RNG-free —
on a lattice ranked over the FEASIBLE eligibles only, those with an empty
site within birth reach (#164/#171, a pure occupancy read); then per
parent — in parent-id order well-mixed, in the contest order
under sync + lattice + economy (#107/#133): the placement check, which on
a lattice is one kernel draw over the empty sites within the birth
radius and can FAIL — a blocked parent pays nothing and stays eligible
(Design 4's two gates; #133) — then σ + overhead payment, passport id,
μ-draw, and site occupation; child starts at σ) — the two phases in the
order `dynamics.boundary_order` picks: `death_first` (the #80 default;
deaths free room, survivors breed into it) or `birth_first`
(Hammond–Axelrod's order: births are rationed against the pre-death
population, so fewer are admitted — VT-4, runtime-confirmed #130 — and
newborns face the death phase in their birth round, #131) → age
increment → score-only reset → per-agent snapshot of the post-boundary
population. All births and deaths are computed against one frozen
end-of-generation snapshot — the generation stays atomic. Mortality:
hazard `base_hazard × senescence_factor^age` capped at 1, plus a hard
`max_age`; founder ages are staggered to the steady-state distribution
when age-mortality is active.

Derived defaults (DECISIONS #78): `initial_energy` blank = the offspring
stake; `senescence_factor` blank = the value reaching certain death
exactly at `max_age`; `carrying_capacity` blank = the lattice's site
count, or 200 in a well-mixed world (#134). All resolve to plain numbers
at config validation, so stored `config.yaml` files never contain the
auto rule. The reproduction validator requires
`offspring_stake + reproduction_overhead ≤ reproduction_threshold`
(#129), so a parent always survives its own reproduction.

Under variable N, `random_k` clamps its draw to `min(k, N−1)` — a no-op in
every fixed-N regime, so pre-M10a seeded histories are untouched (#81); a
population of one plays nothing, still pays its bill, and starves. The
UI's **Economy panel** (`ui/economy_helpers.calibration_report`) derives
the survival window (`all-D income ≤ cost < all-C income`), escape velocity
`e* = cost / r`, and mortality/memory readouts straight from the config —
note the window is N-stable under `random_k` (bounded ≈ 2k interaction
budget) but moves with N under round-robin. Population structure and local birth
are no longer out of scope — designed in §2.12 (M11, DECISIONS
#103-#110), where this section's "K may become emergent" open line
resolves definitively: K stays live as a second cap with a site-count
derived default (#106). Still out of scope: estate policy beyond
destroy-on-death (M15). Async/Moran event time shipped in M10b — §2.11.

### 2.11 Asynchronous event time (M10b — `dynamics.time_model`)

The generation can be dissolved as the unit of time (DECISIONS #85,
#95-#102; frozen intent in `docs/specs/M10b-async-event-time-spec.md`).
**`dynamics.time_model` ∈ {`synchronous`, `asynchronous`}**, default
`synchronous` — the existing generational clock, byte-identical. Under
`asynchronous` (evolution mode only) the engine routes to
**`AsyncDynamics`** (`core/async_dynamics.py`): time advances one **focal
activation** at a time — a focal agent drawn uniformly plays
`matching.opponents_per_agent` (k) matches against uniformly drawn
distinct partners, and every consequence fires immediately (a strategy
copied after match 2 of the bundle plays in match 3; a death fires the
moment its trigger evaluates). The k-match bundle keeps async runs
comparable to sync in INCOME as well as time: over one
generation-equivalent each agent is focal once on average and drawn ≈ k
times — the same ≈ 2k interaction budget as a synchronous `random_k`
generation.

**The clock** advances Δt = 1/N(t) per event (N read at event start); one
**generation-equivalent** completes when the running sum crosses an
integer. It is pure bookkeeping — no RNG, no influence, deliberately not
a parameter; `dynamics.generations` is the run length in
generation-equivalents. Every explicit event and period record carries a
`gen_equiv_time` stamp (`None` on sync runs — the honest "this run has no
event-time clock").

**Two demographic engines** (`dynamics.async_population`, default
`variable_n`):

- **`variable_n`** — the §2.10 economy in event-time (#96): income and
  the per-match engagement cost land at match completion; `L·Δt` and
  `(1+r)^Δt` accrue in a per-event sweep (ascending id, no RNG);
  insolvency stays strictly negative; births need `e ≥ θ` AND a
  1.0-time-unit **breeding refractory** (the event-time image of #80's
  one-birth-per-generation rule); the mortality trio becomes one coin
  per agent per INTEGER birthday (same lifetime coin sequence as sync),
  with the `max_age` cap deterministic and founder staggering carried
  via negative `birth_time`. Interest-compounding grain, named honestly:
  sync applies (1+r) once per boundary, async compounds over income
  arriving mid-period — the clocks agree exactly only on a static
  balance (pinned by the V5 comparability tests: same growth story,
  never byte-identity).
- **`fixed_n`** — classic Moran (#97): N pinned, one death paired with
  one fitness-proportional birth per event, governed by
  `dynamics.moran_rule` ∈ {`birth_death`, `death_birth`, `random`} (the
  `random` mixture rolls per event against the normalised
  `moran_weight_*` pair) and `dynamics.fixed_n_death_rule` ∈
  {`pure_random`, `energy_decides`}. No insolvency/age deaths, no θ
  births, no extinction; `carrying_capacity` ignored. The ledger still
  runs — energy is Moran FITNESS (the #63 shift idiom, under which a
  uniform per-capita L cancels out of selection entirely); the textbook
  corner is the defaults + σ = 0 + `pure_random`.

**The imitation overlay** (`dynamics.imitation_overlay`, bool, default
off — #98) is a CULTURAL channel layerable on either engine: after each
completed match, one of the two participants is chosen by a fair coin as
the potential adopter (the symmetric sync-matching rule, #93) and copies
the other with probability `logistic(selection_beta · gap)` — downhill
copies possible, β = 0 true neutral drift in both clocks. Strategy-copy
only; a no-op copy spends its two coins but emits no event.

**Recording cadence** (`output.recording_cadence` ∈
{`per_generation_equivalent`, `per_event`, `every_m_events`} +
`output.recording_cadence_m` — the registry's Output section): decides
when period reports are emitted. An observer control in #35's sense
(consumes no RNG, influences nothing — pinned by test) that nevertheless
lives in the config because it decides what the persisted record
CONTAINS (hard rule 8). Sync runs ignore both parameters.

Both async engines delegate every birth to the **Option B seam** —
`admit_births()` / `place_offspring()`, place-before-pay — so M11's
local-birth rewrite swaps seam implementations without reopening the
event loop or its RNG contract. The full within-event draw order is
pinned in `async_dynamics.py`'s module docstring and golden-mastered
(seed-7 variable_n, seed-13 moran-random); any change is a breaking
change requiring a DECISIONS entry (#99). The ignored-parameter map
(which knob is inert under which mode) is implemented as UI greying with
a β carve-out — β follows the overlay in async (#101).

### 2.12 Population structure (M11 — `structure.*`)

The world becomes a set of **sites** (DECISIONS #103-#110; M11a =
structure + local birth + local interaction, M11b = movement + the layout
painter, #103). A site is an **exclusive container**: it holds at most
`site_capacity` agents, an integer field pinned at 1 and validated as such
in M11a — the field ships now so that allowing capacity > 1 at M19 is a
parameter change, not a migration of the placement seam (#104). Structure
is selected by `structure.kind` ∈ {`well_mixed`, `lattice`}, default
`well_mixed` — the existing aspatial world, byte-identical and recovered
as the degenerate fully-connected corner rather than as a separate code
path.

**The core abstraction is a graph of sites, never a rectangle** (#104). A
site carries an id, a neighbour set, a capacity, and an optional
coordinate. The rectangular lattice is ONE BUILDER over that abstraction;
the core never knows about rows and columns. Distance is a method the
STRUCTURE supplies, not a constant the kernel assumes. These three
properties are forward-guards for M19 (geographic structures): an
irregular country raster with holes, or a set of GeoJSON municipalities
with shared-border adjacency, must be a second builder requiring no core
change.

**Lattice geometry.** `structure.rows` / `structure.cols` (blank resolves
to the most-square factor pair of N — the #78 derived-default idiom; note
prime N factorises to a 1×N line, a legitimate one-dimensional lattice but
one the app must announce rather than let look like a bug);
`structure.neighbourhood_shape` ∈ {`moore`, `von_neumann`} (8 or 4
neighbours at radius 1 — implemented as the distance metric, Chebyshev or
Manhattan, that the structure hands to BOTH kernels, so it governs birth
reach and interaction reach together); `structure.boundary` ∈ {`torus`,
`bounded`}, default `torus`. Torus is the default because uniform degree
removes an edge artifact: on a bounded grid a corner cell has 3 neighbours
and an interior cell 8, and since cooperation thresholds on graphs depend
on degree, corners become spuriously favourable to cooperation. `bounded`
ships anyway because at M19 a coastline is a real hard edge and varying
degree is then the model, not a bug.

**The soft reach kernel** (#105). One functional form, separately
parameterised per use: the weight over a site at distance d is
proportional to exp(−β·d) for d ≤ R and zero beyond, where R is a
**support radius** and β a **decay**. This supersedes the M10b
forward-note's single-temperature phrasing (spec Design 9, explainer §7),
which was loose — sharpening a decay recovers nearest-neighbours-only, not
a hard-edged disc. The corners: R = 1 is Hammond–Axelrod exactly; β = 0
with R = n is a uniform disc (the "hard cutoff" the old note reached for);
large β with R = n is steeply viscous with distant sites still reachable;
R → ∞ with β = 0 is well-mixed, recovered by parameters rather than by a
branch (design-freeze §11.5). M11a parameterises the kernel twice —
`structure.birth_radius` / `structure.birth_decay` and
`structure.interaction_radius` / `structure.interaction_decay` — and M11b
adds a third pair for the walk. Two radii rather than one is what makes
local-births-with-global-interaction and
global-births-with-local-interaction separable experiments.

**The two seams keep distinct jobs.** `admit_births()` is the GLOBAL gate
— are we under carrying capacity, rationed by energy priority when seats
are scarce. Under structure (the synchronous economy on a lattice) the
global gate ranks and seats ONLY FEASIBLE parents — those with at least
one empty site within birth reach, a pure occupancy read through the reach
cache that consumes no RNG (M11b Phase A, DECISIONS #164 resolving #159,
built per #171): K decides HOW MANY, the kernel decides WHERE, and a seat
never goes to a parent who physically cannot use it. The excluded eligibles
are counted as INFEASIBLE (all of them, not merely those who would have
ranked inside the quota — #171 ruling R2). `place_offspring()` is the
LOCAL gate — is there an empty site in reach, sampled by the birth kernel
and contested per below. A parent must clear both. Place-before-pay (#80)
is load-bearing at last: a parent that cannot place a child pays NO stake
and stays eligible next period. Since #164 the only way a seated
synchronous parent fails the local gate is RESIDUAL CONTENTION — an
earlier-iterated parent took the last empty site in its reach this
boundary — accepted as rare and self-healing (next generation re-ranks
against the changed occupancy); a permanent freeze of #153(c)'s kind is
impossible, because at least one seated parent always places. The
asynchronous clock has no feasibility filter: it admits by energy alone
and its blocked count keeps the undivided pre-#164 meaning (#171 ruling
R1; unifying its vocabulary is a named future option).

**Carrying capacity survives under structure** as a second, tighter cap
(#106 — resolving §2.10's "may become emergent" open line). Validator:
K ≤ site count. Blank K under a lattice resolves to the site count (#78
idiom), making "the grid decides" the zero-effort path; a K below site
count leaves deliberate slack in which the occupied region can drift,
cluster and migrate. The Economy panel reports BOTH numbers so slack is
visible rather than a mysterious stall. Under `fixed_n`, N = site count
exactly (validated) — every site occupied, which makes site-recycling the
ONLY possible Moran placement (a death leaves exactly one empty site and
the newborn has nowhere else to go), so the textbook death-birth corner is
structural rather than a rule we impose.

**Birth contention and boundary order** (amending the #80 frozen sequence
— see DECISIONS #107). Contention exists only where several births resolve
at one instant: synchronous + structure + `energy_economy`, and nowhere
else (async resolves one birth per event; `fixed_n` never calls
`admit_births` per #97d; sync well_mixed placement never fails). [As
implemented, found in M11b Phase A and HELD for the design layer (#171,
Rule 7): the asynchronous `variable_n` engine admits the WHOLE
θ-eligible, refractory-clear set at each event and iterates it in
ascending id order, so several births CAN resolve in one event — probed on
the `async_variable_n_lattice` golden, two events fire two births each.
No contest permutation exists there; a shared last reachable site goes to
the lower id. Whether async should enforce one birth per event, or the
id-order resolution is acceptable, is an open design question; the engine
is byte-untouched.] Under structure, the admitted birth set is resolved by
`structure.placement_contest` ∈ {`random`, `energy_priority`}, default
`random` — ONE permutation then iterate, matching Hammond–Axelrod's random
reproduction order and keeping energy's role at eligibility (θ) rather
than at winning a contested cell. Parent-id order is rejected: on a
lattice, id correlates with founding position, so it silently becomes a
spatial priority rule. The shuffle is gated by the structure flag, so
well_mixed sync runs draw no extra RNG and stay byte-identical (the
#80/#99 active-flag idiom). `dynamics.boundary_order` ∈ {`death_first`,
`birth_first`}, default `death_first`, exposes H-A's period order as an
option: under a lattice the ordering is no longer a phase offset but a
different model, because it decides whether newborns fill scattered
interior graves (deaths-first) or only frontier cells (births-first) — and
the frontier is where the ethnocentrism mechanism lives. Greyed under
async, which has no boundary to order. As implemented (#131, #133): the
contest permutation is drawn whenever the three-way gate holds regardless
of the contest setting (so flipping the widget never shifts the stream),
it applies to the ID-ORDERED admitted list — never the energy-sorted
admission list — and under `birth_first` newborns go through the death
phase as full members (coin included; a survivor enters its first played
generation at age 1), with births rationed against the pre-death
population (VT-4, runtime-confirmed #130).

**Where the Moran breeder comes from under a lattice** (spec Design 7,
implemented per #132). The async `fixed_n` draws LOCALISE through the
BIRTH kernel: under `death_birth` the victim draw stays global and the
breeder is drawn from the freed site's occupied neighbours within
`birth_radius`, weighted `exp(−β·d) ×` the #63-shifted energy (shift over
the candidate set, before the multiplication; uniform fallback on the
combined vector); under `birth_death` the breeder draw stays global and
the victim localises to the breeder's neighbours (`pure_random` = one
kernel draw; `energy_decides` = poorest neighbour, deterministic). Each
is a SUBSTITUTION — same position, same single draw, changed candidates
and weights — and the newborn takes the freed site. At R = 1 the distance
factors cancel and the breeder draw is EXACTLY fitness-proportional over
the neighbours: Ohtsuki's setting recovered as a corner, which is why the
birth pair stays live under `fixed_n` — it defines the competitor set
whose size is the k in b/c > k. Synchronous IMITATION's comparison
partner stays GLOBAL under a lattice — an explicit scope-grounds decline
handed to M12, not an omission (#132).

**Local interaction** (#108). `matching.spatial_interaction` (bool,
default off). Off: today's behaviour, `matching.matcher` picks round_robin
or random_k over the whole population. On: partners are sampled from
within the interaction radius by the reach kernel, and `matching.matcher`
GREYS — round-robin has no local analogue, and the well-mixed matchers are
the infinite-radius corner. `matching.opponents_per_agent` (k) stays LIVE
and does the work: k at or above the neighbourhood size means "play all
neighbours", the H-A and Ohtsuki convention, so round-robin's IDEA
survives the greying. k clamps to the number of neighbours that actually
exist (the #81 clamp idiom) — edge cells under `bounded`, and irregular
site sets at M19. Validator: spatial interaction requires
`structure.kind = lattice`.

**Encounter mode** (M11b Phase C; DECISIONS #166 designed, #174/#175 as
built). Under spatial interaction each agent initiates its own partner
draws, so two neighbours that draw each other play twice per generation —
once in each initiator seat; at k ≥ neighbourhood size the doubling is
systematic (every adjacent pair, every generation — measured EXACTLY 8 =
2 × 4 matches per agent on a full von Neumann torus, #139).
`matching.encounter_mode` ∈ {`per_initiator` (default), `per_pair`} gives
the artifact a switch: `per_initiator` keeps every drawn match (the
historical behaviour); `per_pair` collapses duplicate UNORDERED pairs
AFTER the draws, so each pair plays at most once per generation. The
draw-identity contract (#166(b)): partner draws are made exactly the same
in both modes — same calls, same order, same random-number consumption —
and deduplication applies to the resulting pair list after ALL draws
complete and before ANY match plays, inside `SpatialKernel.pairings` (the
one place the sync pair list is built); the knob changes WHICH matches
run, never how randomness is consumed, so the default is byte-identical
trivially and downstream stream divergence under `per_pair` (dropped
matches drop their in-match draws) is the knob working (#174(f)). The
survivor is the FIRST occurrence in pair-list order, keeping its
initiator seat — focals walk in ascending id order (#57), so in the
forced-draw regime every survivor's initiator is the lower id of its pair
(#174(c), pinned). SPATIAL-ONLY: live only while
`matching.spatial_interaction` is on; the well-mixed matchers are
untouched (the `random_k` coincidental doubling is a recorded future
extension, #166(a)). GREYED under the asynchronous clock, table entry
plus help text: each async event's focal draws one partner —
per-initiator by construction — and deduplicating across events would
require remembering encounters through time, distorting the activation
clock #165 protects (#166(c)); the async loop is not touched in any way.
The Economy calibration's spatial branch reads the mode (#174(a)):
expected matches per agent = 2 × min(k, effective degree) under
`per_initiator`, 1 × under `per_pair`, with the fine print stating the
multiplier actually used — landed with the engine knob so the panel is
never false at any commit boundary.

**Agent movement** (M11b Phase B; DECISIONS #165 designed, #172 as
built). The third parameterisation of the reach kernel: `movement.rate`
(per-agent per-period move probability, default 0 = off), and the walk
pair `movement.radius` / `movement.decay` (same shape and defaults as the
birth pair: R = 1, β = 0, blank R = unlimited). The `MovementRule`
abstract base class (`core/movement.py`, the #46 seam) ships ONE
implementation, `KernelWalk`: one `neighbourhood_sample` call over the
EMPTY sites within R of the mover's CURRENT site, weighted exp(−β·d),
through the same primitive and the same #156 cached reach as every other
locality draw; success-driven and walk-away rules are future
implementations of the same interface (they will need the mover's state
as an extra input — an interface extension for the phase that builds
them). Movement is a population-dynamics concern, orthogonal to
strategies (#46). *The schedule* (#165, the #103 open item RESOLVED):
under the SYNCHRONOUS clock movement is the FINAL step of the demographic
boundary — after the death and birth phases in whichever order
`dynamics.boundary_order` ran them, immediately before the age increment
(steps 7–9 of #80 consume no RNG, so the position is draw-neutral and
"final demographic act" is unambiguous); the whole post-boundary
population is eligible, this boundary's NEWBORNS included (one uniform
rule); the next generation's matches are played from the settled
positions, and generation 0 from the founding layout as dealt or painted
(move-then-play). Under the ASYNCHRONOUS clock movement is a step INSIDE
the focal activation — focal draw, then the movement coin, then the match
bundle (partners drawn from the focal's POST-move site), then the
demographic step — never a new event type: the one-event-one-activation
correspondence and Δt = 1/N(t) are untouched, and at N = 1 the activation
is skipped along with the focal draw, so no coin is drawn either. *The
gate*: movement is live only under lattice + energy economy — sync
`energy_economy` (the `EconomyDynamics` lattice half), async `variable_n`
— and only while `movement.rate > 0`; `fixed_n` is EXCLUDED (its grid is
full by construction, N = site count, so every move would be blocked) and
sync imitation has no demographic boundary to host the step; the movement
trio greys in each excluded case with a cause-naming note
(`STRUCTURE_GREYING`), grey-never-hide. The one predicate
(`movement.movement_active`) is read by both engines at construction and
by the app's readout visibility, so the engine and the panel cannot
drift. *The RNG contract* (the #80/#99/#133 idioms applied; the second
amendment of the #80 frozen boundary sequence after #107, and the
amendment of the #99 pinned within-event order — both legal by the
active-flag idiom): every movement draw sits behind the gate, so a
movement-off or non-gated run consumes ZERO additional draws and all
eight pre-existing goldens passed untouched (observed at #172). Sync,
when active: ONE `rng.random()` coin per living agent of the
post-boundary population in ascending id order, unconditionally — even at
rate 1.0 — so the stream depends only on the flag and the population size
(#80's mortality-coin shape); then ONE `rng.permutation` over the
coin-successes (the movers), made whenever at least one coin was drawn
(a generator no-op at sizes 0 and 1, #133(a); the counting pins count
calls); then, iterating in PERMUTATION order, one walk draw per mover.
Async, when active: one coin for the focal immediately after the focal
draw; on success the walk draw; no permutation (one mover at most per
activation). *Occupancy semantics*: candidates are the sites empty AT
DRAW TIME, so the mover's own occupied origin is never a candidate — a
move is a relocation, never a possible null move; the origin is vacated
only AFTER the destination is drawn (`movement.attempt_move`, the one
function both engines call), so under the sync permutation an
earlier-permuted mover's freed origin IS available to a later mover
(chains can form) while every agent gets at most one attempt per period.
*Why a permutation over the movers* rather than id-order iteration: on a
lattice id correlates with founding position (#107), so id order would
silently hand a spatial priority to low ids whenever two movers want the
same last empty cell. *Blocked moves* (#165(c)): an attempt that finds no
empty site within walk reach fails in place — the primitive returns empty
BEFORE drawing, so a blocked mover consumes no destination RNG (the
#133(b) data-conditional shape) — and is counted as ONE undivided number,
`blocked_moves`, covering both a walled-in mover and one whose last
reachable site an earlier-permuted mover took: deliberately unlike the
birth vocabulary's blocked/infeasible split (#171), and the word
"infeasible" is kept out of every movement text so the two vocabularies
do not cross-contaminate. The count travels exactly as `blocked_parents`
does — `GenerationReport`/`GenerationFinished.blocked_moves` (additive,
default 0), populated per generation by the sync economy and per
recording window by async `variable_n`, `RunTimeseries.blocked_moves`,
a "Blocked moves this generation" live metric visible only while
movement is active (with its (?) from `ECONOMY_HELP["blocked_moves"]`) —
LIVE-only: not persisted (recorded folders byte-identical), not shown by
the results browser, and NOT in any golden's pinned field list (#171(f1):
extending a list moves a digest). Movement is FREE — a movement energy
cost is a named future option (#165) — and blind to strategy. Two
movement-on goldens (`sync_economy_lattice_movement`,
`async_variable_n_lattice_movement`: the two lattice-economy positives
plus `movement.rate = 0.5`, nothing else changed) were RECORDED, not
re-recorded, at #172; the flat sync-golden fact that a blocked move is
impossible on its 3 × 4 Moore torus (population ≤ 7 of 12, radius-1
neighbourhood of 8) is recorded there as a Rule 7 finding.

**Initial layout** (#109). `structure.initial_layout` ∈ {`random`
(default), `checkerboard`, `stripes`, `blocks`, `patches`,
`central_block`} decides ARRANGEMENT only; composition is already set by
the three-bucket model (#67). Ordered mixed → segregated: checkerboard is
the anti-cluster baseline; patches (seed points grown outward) gives the
most natural irregular clusters; central_block leaves the rest of the grid
empty and is the FILLING regime, the one Kaznatcheev & Shultz's early-run
result concerns. Plus a layout-FILE reference mechanism so a hand-authored
arrangement is DATA the engine reads (rule 8: the run must re-run from its
config; rule 4: the engine never knows a mouse was involved). The mouse
painter that writes such files is M11b.

**Layout file format** (M11a Phase B). Plain text: a header of
`kind: lattice_grid`, `rows:` and `cols:` lines, then a body of one token
per cell — a strategy machine name, or `.` for an empty site. The `kind:`
discriminator ships from day one so M19's `site_map` variant (a
site-id/strategy body, needing no geometry) is a reader dispatch rather than
a format migration. The file WINS on composition: it names a strategy per
cell, so its counts are the composition and the mix widgets no longer decide
the arrangement (the population SIZE must still agree, and a mismatch is a
validation error). A sweep that varies composition while a file pins every
cell is rejected at spec validation. The recorder copies the file into the
run folder and records the copy's name, so the folder re-runs after the
original moves (rule 8).

**Topology / occupancy split.** `Structure` (`core/structure.py`) is an
immutable value — the sites, the neighbour relation, the distance metric —
derived once from the config. `Occupancy` (`core/occupancy.py`) is mutable
per-run state owned by the dynamics: site → agent and agent → site, kept
mutually consistent, with exclusivity checked as `occupants < capacity` so
M19's per-site capacity is a parameter change rather than a migration of the
placement seam. Keeping the two apart is what lets the topology be shared,
cached, and (later) precomputed.

**Rendering contract** (#109). Cells are always exactly square: side =
min(max_width/cols, max_height/rows); the canvas takes whatever aspect the
grid has. The side is floored at ≈ 3 px, below which cells stop being
distinguishable. Past a few thousand cells the grid renders as a pixel
ARRAY, not as thousands of individual shapes, or redraw crawls — this is
where #94's wall-clock throttling starts to matter.

Structure is IGNORED in tournament mode (no births, no deaths, no
movement — nothing for space to do). Persistence gains a site id per agent
under the honest-presence rule (#83); an agent's recorded site is its
post-boundary (sync) or recording-point (async) position, so a moved agent
appears at its new site in the next snapshot. Still out of scope: per-site
capacity above 1, irregular/geographic site sets, and co-residency
semantics (all M19); the layout painter (M11b Phase E4).

**M11a spec obligation** (design-freeze §12, restated because ~15
parameters arrive at once): every new CONCEPT, every ENUM VALUE
INDIVIDUALLY (`moore` and `von_neumann` each need their own explanation,
not merely the parameter), and every DERIVED READOUT (emergent site count,
effective neighbour count) carries an inline (?) drawn from a single
described source. The spec must include an explicit checklist enumerating
them so it is verifiable, not aspirational.

## 3. Architecture

```
pdsim/
  core/
    game.py          # Game ABC; PrisonersDilemma; (v2: PublicGoodsGame)
    strategy.py      # Strategy ABC; history/memory views handed to strategies
    strategies/      # one module per strategy, auto-discovered on package import
      registry.py    #   Strategy Registry: StrategyInfo metadata + create_strategy
    agent.py         # Agent: identity, strategy instance, score, history store
    matcher.py       # Matcher ABC; RoundRobin; RandomK; SpatialKernel (M11a)
    match.py         # plays one match (length mode, noise ε) between participants
    selection.py     # SelectionRule ABC; Fermi, proportional, tournament_k,
                     #   truncation, threshold_cloning (M9a, DECISIONS #63)
    accounting.py    # ScoreAccounting ABC; per_generation, sliding_window,
                     #   exponential_discount (M9a, DECISIONS #64)
    reproduction.py  # StrategySwitchReproduction (mutation μ); (M14: perturbation)
    economy.py       # M10a pure boundary helpers: energy ledger, mortality,
                     #   capacity admission, placement gate, founder ages (§2.10)
    dynamics.py      # run loops: PopulationDynamics (imitation) + EconomyDynamics
                     #   (energy economy, M10a) + GenerationReport (evolution);
                     #   TournamentDynamics + CycleReport (tournament)
                     #   (M10b: async/Moran event time)
    events.py        # typed event dataclasses (see §4)
    engine.py        # run(config, granularity) -> Iterator[Event] (see §4)
    timeseries.py    # RunTimeseries: folds period events into chart/recorder series
  config/
    registry.py      # Parameter Registry (single source of truth; see §5)
    experiment.py    # ExperimentConfig schema (pydantic); YAML load/save; validation
    scenarios.py     # Scenario Registry: curated presets (see §5.1; v3 scenario home)
  io/
    results.py       # RunRecorder + load_run/read_index: run folders (§8)
  viz/
    charts.py        # pure builders: RunTimeseries -> plotly figures; summary rows;
                     #   HTML export seam; sweep metric-vs-axis charts (§4, §6.6, §8)
  sweep/             # sweep/search layer (M9.5a, §6.6, DECISIONS #66-#71)
    spec.py          #   SweepSpec + validation + three-bucket expansion
    metrics.py       #   Outcome Metrics Registry (4th registry idiom)
    runner.py        #   parallel runner + sweeps/<name>/ persistence
    __main__.py      #   python -m pdsim.sweep <spec.yaml>
  ui/
    app.py           # Streamlit app: Run lab + Results browser tabs (§4.1, §8)
    helpers.py       # Streamlit-free config <-> widget-state mapping (testable)
    economy_helpers.py # Streamlit-free Economy panel arithmetic: the M10a
                     #   calibration readout + single-source (?) texts (§2.10)
  run.py             # headless CLI: python -m pdsim.run (+ execute_run seam, §6.6)
  gendocs.py         # generates docs/PARAMETERS.md from the registries (§5)
  bench.py           # benchmark rider: python -m pdsim.bench (§3.1 trigger data)
  tests/             # pytest; includes validation against known results (see §7)
```

Key contracts:

- `Strategy.decide(view, rng) -> Action` where `view` exposes: my history vs this opponent,
  opponent's actions vs me, round number (optionally, later: public reputation
  info and the opponent's visible attributes — the §6.5 extension surface);
  `rng` is the injected seeded generator, so stochastic strategies stay reproducible
  (see DECISIONS #21). Strategies are stateless — pure functions of (view, rng) — and
  never see engine internals.
- `Game.play(actions: Mapping[AgentId, Action]) -> Mapping[AgentId, Payoff]` —
  arity-agnostic so PGG fits the same interface.
- `engine.run(config, granularity="generation") -> Iterator[Event]` — a
  module-level generator function: the engine **yields events** rather than
  returning a final blob (see §4). The CLI, recorder, and live UI are all just
  event consumers. `granularity` is an observer concern, never a model
  parameter (DECISIONS #35).

### 3.1 Performance strategy

- v1 engine is object-per-agent, optimized for readability and debuggability.
  The practical envelope is **per matcher** — the validated cost model is
  `s/gen ≈ 7.5 µs × N × k × rounds` (M9a bench, DECISIONS #65), where k is
  the per-agent match count (N−1 under round-robin, 2k under random_k):
  - **round_robin, 50 rounds**: N=100 → several generations/sec; N=300 →
    seconds/generation; N≥1000 → too slow. This is the only regime the old
    "N≥1000 → too slow" claim describes.
  - **random_k**: the per-agent budget is bounded by k regardless of N, so
    thousands of agents stay affordable — N=1000 at k=5, 50 rounds is on
    the order of a second per generation, not minutes.
  Large-N work is a **headless/sweep product**; live visualization stays in
  the low hundreds — a chart-rendering limit (DECISIONS #10), not an engine
  limit.
- **The generations term (M10a, measured in DECISIONS #91).** The model
  above holds *per-generation* for imitation, for tournaments, and
  asymptotically for the energy economy under random_k at large N. Under
  **`energy_economy` + round_robin with unbounded `memory_depth`** it does
  NOT: per-opponent histories persist for an agent's lifetime (#79) and
  every pair re-meets every generation, so the `view_of` history copy grows
  by ≈ `rounds` per generation and the per-generation cost rises linearly
  with the generation index — a long round_robin economy run is
  **superlinear in `generations`** (quadratic total; measured ×3.1 in
  s/gen from G=20 to G=100 at N=50 while the imitation control stayed
  flat). The growth term scales with the pair-recurrence probability — ≈ 1
  under round-robin, ≈ 2k/(N−1) under random_k — so it vanishes in exactly
  the large-N regime random_k is chosen for. `memory_depth` bounds it (it
  caps what strategies see, hence what the copy transfers), and the Economy
  panel's memory-growth note is the user-facing warning.
- **The async column (M10b, measured in DECISIONS #102).** The cost model
  carries to the event loop per GENERATION-EQUIVALENT with a ≈ 1.1×
  constant: `python -m pdsim.bench --time-model asynchronous` measured
  the async loop at ≈ 6-11% over the sync economy at equal N (N = 50 to
  400, k = 5, 50 rounds), scaling linearly in N. The O(N) per-event
  accrual sweep — O(N²) per generation-equivalent — shows up only as
  that ratio creeping from 1.08 to 1.11 across the grid: bookkeeping-
  cheap next to the k matches each event plays. Uniform partner draws
  give async random_k's pair-recurrence (≈ 2k/(N−1)), so the #91
  generations term does not bite in the benched regime.
- The performance strategy has **three independent dimensions** (DECISIONS
  #46, #59):
  1. **Faster execution/rendering of a given interaction count.** Engine side:
     the **vectorized NumPy backend** (strategies as batch state machines over
     arrays; v2, ~10–100×). UI side: headroom exists in incremental trace
     updates, series downsampling, and ultimately the §6.4 dashboard
     migration.
  2. **Fewer interactions per period**, via sampling matchers behind the
     existing `Matcher` ABC: **RandomK** (O(N·k) instead of round-robin's
     O(N²); shipped in M8 — this dimension's first implementation, DECISIONS
     #57) and **local interaction** (M11a — the `SpatialKernel` sync
     adapter over the structure module's `neighbourhood_sample` primitive,
     §2.12/#108; this dimension's second implementation).
  3. **Parallelism across runs** (DECISIONS #59; shipped in M9.5a, #70).
     Whole runs are independent, so batch experiments parallelize across
     processes — the sweep layer's `multiprocessing.Pool` runner
     (`python -m pdsim.sweep`) does exactly this. It speeds up *mass
     experiments*, not any single run, which makes sweep campaigns affordable
     before (and independently of) any vectorization.
- For large N the binding constraint is **match-phase compute, not chart
  rendering** — round-robin's O(N²) matches dominate long before plotting
  does; the first two dimensions pair to reach thousands of agents at
  interactive speed.
- The vectorization trigger is **empirical** (DECISIONS #58): the M9a
  benchmark rider, `python -m pdsim.bench`, measures median wall-clock
  seconds per generation across an N × matcher grid — that data, not
  intuition, decides when the vectorized backend gets built.
- Rule: nothing in configs, UI, or persistence may assume the object backend.

## 4. Event stream and live visualization

The engine (`pdsim/core/engine.py`) is a generator: `engine.run(config,
granularity)` yields immutable typed events (`pdsim/core/events.py`) as the run
unfolds. Five core event types (DECISIONS #35) plus the three explicit
event-time types M10b added (async runs only — see below):

- `RoundPlayed` — pair identity, round index, executed actions, payoffs.
- `MatchFinished` — pair identity, per-agent match totals, match length.
- `GenerationFinished` (evolution mode) — generation index, population
  composition (strategy → count), per-strategy mean scores, per-strategy
  rounds played (agent-rounds; the exact per-round denominator — DECISIONS
  #44), THIS generation's executed-action cooperation table per ordered
  (actor strategy, opponent strategy) pair as (rate, actions counted)
  (M9b, DECISIONS #65), and — in `energy_economy` mode only — `agents`, a
  tuple of **`AgentSnapshot`** values (agent_id, parent_id, age, energy,
  strategy) describing the POST-boundary population entering the next
  generation (M10a, §2.10). Under M11 structure, `AgentSnapshot` gains a
  site id — present exactly when the run has structure, per the
  honest-presence rule (#83). Empty under imitation, keeping those payloads
  byte-identical to pre-M10a. Births/deaths are reconstructed by diffing
  consecutive snapshots — deliberately no explicit birth/death events in
  the synchronous model (they belong to M10b's async event time, #82). No
  population-size field either: `N = sum(composition.values())` (#47).
  Extinction ends the run early: `RunFinished.completed` counts generations
  actually played, and an extinct run closes with empty composition/scores.
  Since M10b the event also carries `gen_equiv_time: float | None`
  (`None` on sync runs), and in async mode "generation" means RECORDING
  PERIOD: one `GenerationFinished` per period under the configured
  recording cadence, its composition/snapshots describing the living
  population at the recording point (#96), and `RunFinished.completed`
  counting periods (its grain follows the cadence). Since M11a Phase C it
  also carries `blocked_parents: int` — how many admitted parents failed
  the local placement gate this period (always 0 off-lattice) — a
  LIVE-only field feeding the Economy panel's readout, deliberately not
  persisted (#133). Since M11b Phase A (#164/#171) its meaning is
  clock-scoped: under the synchronous economy it counts RESIDUAL-CONTENTION
  losers only (a seated, feasible parent whose last reachable empty site an
  earlier-iterated parent took this boundary); under the asynchronous clock
  it keeps its undivided original meaning (no empty site in reach at that
  birth event). Beside it, `infeasible_parents: int` — how many
  threshold-eligible parents the feasibility filter excluded from admission
  this generation for want of an empty site in reach (all of them, so a
  full grid counts every eligible parent) — populated by the synchronous
  lattice economy ONLY, always 0 under the asynchronous clock and
  off-lattice; LIVE-only and unpersisted exactly like `blocked_parents`.
  Since M11b Phase B (#172), `blocked_moves: int` — how many move attempts
  found no empty site within walk reach this period (one undivided count;
  §2.12) — populated by the synchronous economy per generation and by
  asynchronous `variable_n` per recording window while movement is active,
  always 0 otherwise; the same LIVE-only, unpersisted, unpinned shape.
- **`BirthEvent` / `DeathEvent` / `ImitationEvent`** (M10b, async only —
  #82/#95): explicit event-time records with `event_index`,
  `gen_equiv_time`, agent identity, and cause (`threshold`/`moran` for
  births; `insolvency`/`age`/`replacement`/`random_moran` for deaths;
  from/to strategy + source for imitations). Buffered per recording
  period and flushed in OCCURRENCE ORDER immediately before that
  period's `GenerationFinished`, at every granularity. They coexist
  with snapshots without violating #47: events give exact intra-period
  timing and causes (which snapshots diff away); snapshots give the
  energy/age state between demographic events (which no event records).
  Synchronous mode emits none of these.
- `CycleFinished` (tournament mode) — cycle index, composition (constant), and
  per-strategy **cumulative** totals + per-agent mean scores + rounds played
  + the run-cumulative cooperation table (#65 — cumulative like everything
  else in this event). A distinct type from `GenerationFinished` because the
  payloads differ: a generation reports that generation's figures; a cycle
  reports run-long cumulative standings.
- `RunFinished` — always emitted, exactly once, last: mode, periods completed,
  final composition, and final scores/standings.

**Granularity** (`"round" | "match" | "generation"`, default `"generation"`) is
an argument to `engine.run` controlling the *finest* event level emitted;
coarser events are always emitted, and `RunFinished` always. In tournament mode
the "generation" level is the cycle level. Granularity is an **observer**
concern, not a model parameter — deliberately NOT in the Parameter Registry or
`ExperimentConfig`: the same config + seed produces identical simulation
results at every granularity (DECISIONS #35). Fine-granularity events are
buffered one generation/cycle at a time and arrive in play order.

Consumers:

- **Live UI** (M6): stacked-area composition + per-strategy score trajectories
  in evolution mode; cumulative/mean standings in tournament mode; user-chosen
  granularity with playback speed. Fine granularity is for small N;
  per-generation updates for large N.
- **Recorder** (`pdsim/io/results.py`): persists the raw time series to a run
  folder regardless of UI granularity (§8) — used by the CLI and the UI's
  record control.
- **Demos**: `examples/quickstart.py` (evolution) and
  `examples/tournament_demo.py` (tournament) show the consumer pattern.

All charting consumers share one intermediate shape: `RunTimeseries`
(`pdsim/core/timeseries.py`) folds period events into aligned per-strategy
series (newcomers backfilled, the extinct gap out) — including, since M9b,
the raw per-pair cooperation series plus two derived views: actions-weighted
per-actor-strategy aggregates and an overall population cooperation rate
(#65; events without cooperation data — schema-1 recordings — leave those
series empty, and charts skip the cooperation figure). It lives in `core` —
pure data processing, no plotting imports — so M7's recorder can reuse it
without touching the viz layer (DECISIONS #37). `pdsim/viz/charts.py` holds pure
builders (`RunTimeseries` in → plotly Figure out; final summaries as plain
table rows) with a per-strategy color map derived from Strategy Registry
order, stable across charts, modes, and reruns. Since M10b,
`RunTimeseries` also carries `gen_equiv_times` and `demographic_events` —
per-period lists strictly aligned with `periods` in both modes (#100) —
and the chart builders share one x-axis rule (#101): when clock stamps
exist the charts plot against the generation-equivalent CLOCK (labelled
"Generation-equivalents (event time)" — under the `per_event` /
`every_m_events` cadences periods are not equally spaced, so the period
index would distort trajectories); sync and tournament runs keep the
classic period axis, and the app shows a one-line axis explainer for
event-time runs.

### 4.1 The v1 Streamlit app (`pdsim/ui/app.py`)

Launched with `streamlit run pdsim/ui/app.py`. Layout (NetLogo-style: model on
top, parameters, live plots below):

1. **Scenario dropdown** — Scenario Registry entries by display name plus
   "Custom" (registry defaults + an even population split). Selecting loads
   the scenario's config into the widgets *once*; every widget stays editable
   (a scenario is a starting point, not a lock — DECISIONS #40) and its
   question/things-to-try text is shown.
2. **Generated parameter panel** — built from the Parameter Registry: widget
   kind from each spec (bool→checkbox, choice→selectbox, numeric→bounded
   number input, nullable→"limit?" checkbox + input), tooltips from the
   novice descriptions, one expander per registry section, widget keys =
   registry keys (DECISIONS #38). Bespoke pieces: the per-strategy
   composition inputs (names/descriptions from the Strategy Registry, live
   sum check gating Run) and a per-strategy parameter expander writing only
   non-default values into `strategy_params` (DECISIONS #41).
3. **Mode-awareness** — `run.mode` as a prominent radio; ignored parameters
   are greyed out (never hidden) with a tooltip explaining why (#34). The
   same pattern keys `matching.opponents_per_agent` off the *matcher*
   widget's current value: k is greyed while round_robin is selected (#57).
   The greying rules live in the Streamlit-free `ui/helpers.py`.
4. **Run controls** — granularity (labelled "cycle" at the coarse level in
   tournament mode), playback delay, Run (disabled while the mix ≠ size),
   Stop (session-state flag checked per event).
5. **Live charts** — placeholders redrawn only on period events; fine-grained
   events advance a progress line, batched every 200 events (DECISIONS #39);
   after the run, the final summary table and periods-elapsed message. The
   mean-score chart has two orthogonal toggles (DECISIONS #44/#45): **score
   view** — "Total" is the raw score selection acts on (scale ≈ payoff ×
   (N−1) × rounds), "Per round" divides by rounds actually played, landing on
   the payoff-matrix scale; and **time scope** — "This generation" plots each
   generation's own figure, "Whole game" plots running averages over the run
   so far (gradual movement; greyed out in tournament mode, whose scores are
   already whole-game cumulative). The last run's results persist in session
   state, so flipping any view re-renders without re-running. Below the
   chart pair, a full-width **cooperation-rate chart** (M9b, #65): overall
   population plus per-strategy actions-weighted lines, y pinned 0–1; the
   final-summary area adds the cooperation pair matrix as table rows.

Config assembly and scenario↔widget mapping live in the Streamlit-free
`pdsim/ui/helpers.py`; pydantic validation errors surface as plain sentences
via `st.error`. The seed is an ordinary, visible widget: same seed + same
settings = same charts.

## 5. Parameter Registry (novice-first explanations)

Every tunable parameter and every strategy is declared exactly once in
`config/registry.py` with: key, type, range/choices, default, display name,
**plain-language description written for a non-expert**, and (optionally) a "learn
more" note. From this registry we generate:

1. UI widgets with hover/click help text (Streamlit `help=`),
2. the auto-generated `docs/PARAMETERS.md` reference,
3. config validation (types, ranges, cross-parameter constraints).

It is structurally impossible for a parameter to exist without an explanation: the
registry entry *is* the parameter's existence.

**Parameter kinds** are `int`, `float`, `bool`, `choice`, and — since M11a
Phase B (DECISIONS #118) — `str`. `str` is free text and is deliberately the
weakest kind: a value not drawn from a declared set cannot be validated
beyond "it is a string", so anything with a knowable set of values stays a
`choice`. It exists for genuinely open values — currently only
`structure.layout_file`, a filesystem path. A nullable `str` normalises
blank text to `None`, so "unset" has one spelling rather than two.

`docs/PARAMETERS.md` (implemented in M8, DECISIONS #56) is a **committed,
generated artifact**: `python -m pdsim.gendocs` (top-level `pdsim/gendocs.py`,
no UI/plotting imports) renders the Parameter, Strategy, and Scenario
Registries into it deterministically, and a pytest drift test regenerates the
document in memory and compares it to the committed file — a stale copy is a
failing test, the registry's structural-impossibility pattern applied to the
docs. Committed rather than on-demand because of the knowledge-preservation
contract: the design chat sees only `docs/` files.

### 5.1 Scenario Registry (curated presets)

The third instance of the registry idiom (`pdsim/config/scenarios.py`, after the
Parameter and Strategy Registries). Each scenario is a frozen `ScenarioInfo`:
machine name, display name, a novice-friendly "what question does this
explore?" description, a **complete validated `ExperimentConfig`**, and a
"things to try" note with concrete tweaks to experiment with. The UI's scenario
dropdown (M6) reads this registry; "Custom" is a UI concept (start anywhere,
then edit), not a registry entry. One scenario = one config — comparative
questions live in the things-to-try text; run-both-and-compare is a possible
future UI mechanism (DECISIONS #36).

v1 ships five seed scenarios: `classic_tournament`, `reciprocity_takes_over`,
`noise_breaks_the_grim`, `drift_vs_meritocracy`, `defectors_paradise`.

This registry is also the designated future home of the v3 real-world scenario
presets (§6.3): geographic/geopolitical setups will register here exactly like
the seed scenarios.

## 6. Designed-for future extensions (build nothing that blocks these)

### 6.1 Growing populations — score-as-energy economy (M10 SHIPPED)
The synchronous half landed as **M10a** (§2.10, DECISIONS #77-#84): the energy
ledger, stake-transfer reproduction, the mortality trio, carrying capacity with
deterministic admission, passport lineage, variable N, and extinction; the
asynchronous / Moran-style event time-model landed as **M10b** (§2.11,
DECISIONS #95-#102). Still future: **M11** — population structure (designed —
§2.12: the `place_offspring` gate in `core/economy.py` becomes the local
placement seam, and K stays live as a second cap with a site-count derived
default, #106); **M15** — economy policy (taxation, redistribution,
immigration, inheritance beyond the destroy-on-death corner).

### 6.2 N-player games, reputation, punishment (M16-M17)
Public Goods Game and variants (threshold/step-level, volunteer's dilemma, n-player
snowdrift) via the arity-agnostic `Game` interface (M16). Reciprocity machinery for
group games: public reputation scores, targeted peer punishment (pay a cost to fine a
defector), exclusion (M17). These enter as engine mechanics + strategy-view extensions.

### 6.3 Spatial layer (M11a shipped design, M11b, M19)

**M11a — discrete adjacency**, per §2.12: the graph-of-sites structure,
the soft reach kernel, local birth, and local interaction. The
`SpatialKernel` matcher promised here since v1 is now M11a's reach kernel
— a thin sync-side `Matcher` adapter over the structure module's
`neighbourhood_sample` primitive (#108).

**M11b — agent movement (SHIPPED in Phase B, 2026-08-18; #165 designed,
#172 built; the full mechanism is in §2.12)**: the `MovementRule` ABC
(#46) with its own walk radius and decay pair over the same kernel family
(`movement.rate` / `movement.radius` / `movement.decay`), one shipped
implementation (`KernelWalk`), success-driven and walk-away rules as
future implementations of the same interface. The schedule is NO LONGER
OPEN — the #103 item is resolved by #165: under the asynchronous clock
movement is a step INSIDE the focal activation (in-activation WON), and
under the synchronous clock it is the final step of the demographic
boundary; both clocks move-then-play. The two alternatives were REJECTED
in #165 and are recorded there so they are not re-proposed by accident: a
separate movement EVENT TYPE (it would break the one-event-one-activation
correspondence that Δt = 1/N(t) rests on, putting a rate-dependent
correction into every axis and calibration figure), and a CADENCE
SCHEDULE (synchronized global reshuffling pulses are a modelling artifact
with no asynchronous meaning). Movement remains a **population-dynamics
concern, orthogonal to strategies** — strategies do not decide movement in
the base design (unchanged from #46). Named future option, out of M11b: a
movement energy cost (#165). Still M11b: the mouse layout painter that
writes the layout files M11a's config references (#109; Phase E4).

**M19 — geographic structures**: irregular site sets from GeoJSON polygons
(shared-border adjacency) or raster masks (cells absent outside a
boundary); per-site capacity above 1 for varying population density;
co-residency semantics (are co-residents neighbours, at what distance,
does the kernel need a value at distance 0); map rendering including the
mixed-occupancy colour question — leading candidate: blend occupant
strategy colours weighted by count, with the honest risk that blending
softens cluster BOUNDARIES, which is exactly what the Hammond–Axelrod
story is about, so M19 likely wants both a blended and a
dominant-strategy view; centroid/Euclidean distance as a
structure-supplied metric.

**Dropped: the continuous `Agent.position` plan** — not planned, not
needed (#104). A raster is the mainstream representation of gridded
geography, and continuity buys only sub-cell resolution below the scale at
which the model has content, while costing the natural notion of "full"
that makes density-dependence work.

### 6.4 GUI evolution
Streamlit v1 → richer dashboard (Dash or FastAPI+React) when maps and heavy
interactivity arrive. Safe because of the headless-engine rule (§1.2). YAML configs
remain first-class alongside the UI forever — they are the batch/scripting interface
(e.g., scheduled experiment sweeps in Claude Cowork).

### 6.5 Agent attributes and attribute-conditional strategies (M12, with v3 extensions)

Agents carry a generic **attributes mapping** (e.g. color, group membership,
location-derived tags — extensible key/value data, not hard-coded fields),
with two per-attribute policies:

- **Visibility**: which attributes an opponent's history view exposes
  (public tag vs private trait).
- **Inheritance**: what offspring receive under selection and mutation
  (copied from the parent, mutated, redrawn, ...).

Strategies may then **condition on the opponent's visible attributes** —
"cooperate with my color, defect against others" and its relatives. The
reference frame is the tag-based cooperation / ethnocentrism literature
(Riolo's tag model; Hammond & Axelrod's ethnocentrism model), which is why
this pairs naturally with v2's reciprocity machinery (§6.2) and becomes
richer still once the v3 spatial layer (§6.3) supplies location-derived tags.

Design guards effective **now** (DECISIONS #46):

1. The `Strategy` view contract's optional-extension point (§3) explicitly
   includes a visible-attributes surface, alongside the reputation extension
   already anticipated.
2. Composition, mutation, selection, and charts must not permanently assume
   **strategy is the only agent dimension** — an agent is a strategy *plus
   attributes*, and future charts may partition by either.
3. The M7 persistence schema reserves room for **per-agent attribute
   snapshots**, exactly as §6.3 already reserves spatial room (see §8).

### 6.6 Sweep/search layer and Outcome Metrics Registry (v2 — M9.5a shipped)

A batch experiment layer over the M7 substrate (scoped in DECISIONS #59;
built in #66–#71; spec `docs/specs/M09c-sweep-layer.md`, companion explainer
`docs/explainers/M9.5-sweeps-and-invasion.md`). It runs a controlled *family*
of experiments and summarises the family as a table and a metric-vs-axis
curve; its founding purpose is invasion-threshold questions. **M9.5a (the
headless core) and M9.5b (the Sweep tab) both shipped** — the execution
stays headless either way. The comprehensive **sweep browser** is **M13**
in the renumbered spine (DECISIONS #76), sequenced after population
structure (M11) so it is structure-aware from birth.

**Defining principle (#59):** the layer consumes only configs and recorded
run folders. It touches no engine semantics (no `pdsim/core/` change, no RNG
change); it is a config *generator* plus post-processing over runs. Every
member config is a fully-validated `ExperimentConfig` reproducible from its
own `config.yaml` (hard rule 8).

As-built shape:

- **Subpackage `pdsim/sweep/`** (`spec.py`, `metrics.py`, `runner.py`,
  `__main__.py`) — orchestration tier (may import config/core/io/viz),
  **Streamlit-free** so M9.5b reuses it. `python -m pdsim.sweep <spec.yaml>`.
- **`SweepSpec`** (pydantic, frozen, `extra="forbid"`): a base config
  (`base` path or `base_scenario`), an optional three-bucket `composition`
  axis, `parameters` (registry-key grids), `seeds`, and `metrics`.
  `sweep_validation_messages(spec)` is the single Streamlit-free validation
  path the CLI and the future tab share (the #38/#48 reuse pattern).
  `expand(spec)` builds the cross product in a pinned order (composition
  outermost, parameter axes in listed order, seeds innermost), fully
  validating every member before any run executes (#66).
- **Three-bucket composition** (#67): a varying invader, fixed counts, and
  percentage fills of the remainder, resolved to whole agents by the
  **largest-remainder rule** (ties broken by ascending machine name). Only
  the resolved integer composition reaches a member's `config.yaml`.
- **`execute_run` seam** (#68): the shared run→record→finalize orchestration
  (extracted from `run.py`), with `RunRecorder.append_index=False` (sweep
  members skip the shared `runs/index.csv`) and index-sorted member folder
  names. `pdsim.viz.charts` is imported lazily so sweep workers never load
  plotly.
- **Outcome Metrics Registry** (#69) — the fourth registry idiom: named,
  documented `compute(run) -> float | None` functions over the loaded
  time series (never raw parquet), so metrics apply retroactively and
  inherit schema compatibility (schema-1 runs yield `None` for cooperation
  metrics). Seed set includes fixation/censoring (a two-column survival
  encoding), quasi-fixation measures, and cooperation-collapse metrics.
  Rendered into `docs/PARAMETERS.md` and covered by the #56 drift test.
- **`sweeps/<name>/` persistence** (#70): the spec copy, one recorded run
  folder per member, a single-writer `sweep_status.json` (progress + resume;
  the parent owns all writes), a wide `sweep_summary.parquet`, a
  `sweep_summary.json` with `schema_version` (the #47 guard's fourth
  application), and metric-vs-axis chart HTML. A parallel
  `multiprocessing.Pool` runner with failure isolation (a bad member never
  kills the sweep) and resume (skip finalized members) — resume matters
  because the working copy lives under OneDrive (#51).

## 7. Validation

- Unit tests per strategy (decision tables against hand-worked histories).
- Engine-level golden tests: TFT vs AlwaysDefect known score sequences; noise-free
  TFT vs TFT = mutual cooperation; GrimTrigger collapse under ε > 0.
- Cross-validation of strategy behavior against the open-source `axelrod` Python
  library (reference implementation of hundreds of PD strategies). We build our own
  engine, but `axelrod` is the correctness oracle for v1 strategies.
- Statistical sanity checks: with β=0, strategy frequencies follow neutral drift;
  with μ>0, no strategy goes permanently extinct.

## 8. Results and persistence (implemented in M7; see DECISIONS #47-#49)

Recording is just another event-stream consumer (`pdsim/io/results.py`,
`RunRecorder`), reusing the same `RunTimeseries` accumulator as the charts.
Each recorded run is a folder `runs/<timestamp>_<slug>/` (name collisions get
`-2`, `-3` suffixes) containing:

- **`config.yaml`** — the complete config including seed; this file alone
  exactly reproduces the run (hard rule 8; `python -m pdsim.run <file>`). The
  code version (package version + best-effort git hash) is recorded as YAML
  *comments* at the top — comments survive the strict schema, extra keys
  would not. Written up front, so a *crashed* run leaves its config for
  diagnosis; an explicitly *stopped* run (UI Stop, CLI Ctrl+C) is discarded
  — folder deleted, no ghosts (DECISIONS #53).
- **`timeseries.parquet`** — RAW per-period, per-strategy rows only: period,
  strategy, agents, mean_score, total_score (tournament; NaN in evolution),
  rounds_played. Derived views (per-round means, whole-game running averages)
  are deliberately NOT persisted — they are cheap recomputations, and
  persisting them would duplicate truth (DECISIONS #47). Loading rebuilds the
  period events and refeeds a fresh `RunTimeseries`, so every derived view is
  recomputed by the same code the live run used.
- **`cooperation.parquet`** (schema 2 — M9b, DECISIONS #65) — RAW per-period,
  per-strategy-PAIR rows: period, actor_strategy, opponent_strategy,
  cooperation_rate, actions_counted. Same raw-vs-derived rule: per-strategy
  and population cooperation aggregates are recomputed on load. Rates are
  per-generation in evolution and run-cumulative in tournament (the #65
  asymmetry, mirroring the period events).
- **`agents.parquet`** (schema 3 — M10a, DECISIONS #83) — RAW per-period,
  per-AGENT snapshot rows: period, agent_id, parent_id (nullable Int64;
  founders `<NA>`), age, energy, strategy. Written ONLY when the run
  produced snapshots (energy-economy runs); no born/died flags — the
  birth/death record is derivable by diffing consecutive periods (#47).
  Per-strategy mean-energy/age series and the population-size curve are
  recomputed on load. `timeseries.parquet` and `cooperation.parquet` are
  untouched — their per-strategy grain is unchanged (widening timeseries
  with energy columns was rejected: NaN columns for every imitation run,
  which #47c forbids).
- **The event-time tables** (schema 4 — M10b, DECISIONS #100) — written
  exactly when the run produced event-time data (async runs): dense RAW
  sibling tables `births.parquet` (period, event_index, gen_equiv_time,
  agent_id, parent_id nullable Int64, strategy, energy, cause),
  `deaths.parquet` (…, agent_id, cause), `imitations.parquet` (…,
  agent_id, source_agent_id, from/to strategy), and `periods.parquet`
  (period → gen_equiv_time, the charts' clock axis) — each written only
  when it has rows; **missing file = empty shape is the contract** (a
  channel that never fired writes nothing). On load the three event
  tables re-interleave into occurrence order by a stable sort on
  `(event_index, kind)` with imitation < death < birth — exact because
  of the engine's pinned within-event ordering, which is therefore
  load-bearing (#100) — and period membership is the UNION of
  timeseries/periods/event-table periods, so an extinct run's final
  empty-composition partial period survives the round trip. Sync
  folders gain no event-time files and stay byte-identical to M10a.
- **`summary.json`** — `schema_version` (4 when event-time data exists;
  3 when per-agent data exists; an
  imitation run under M10a code still writes 2, byte-identical to pre-M10a
  recordings), run id, timestamps, code version, mode, seed, N, periods
  completed, scenario name (if any), wall-clock duration, headline outcome
  (including "population extinct at generation N"), `final_cooperation_rate`
  (schema 2), `total_agents_born` and `population_final` (schema 3; `None`
  for imitation runs — note `population_size` remains the config-derived
  INITIAL size), and the final composition/means/totals — everything a run
  card renders without opening the parquet.
- **Chart HTML exports** — written by the CLI/UI layers via
  `viz.charts.export_run_charts` (never by `pdsim/io`, hard rule 4); a run
  folder is complete without them.

A `runs/index.csv` catalogs all runs (recorder appends one row each: id,
timestamp, mode, N, periods, seed, scenario — "Custom" for custom runs —
and headline outcome; not guarded against concurrent writers in v1). **The
folders on disk are the truth**: the UI's browser lists by scanning them
(`list_runs`) and reconciles the catalog to them on every render
(`sync_index`, rewritten only when stale), so hand-deleted folders disappear
and hand-renamed ones show their new names (DECISIONS #50/#52). Runs can be
deleted (confirmation step, `delete_run`) and renamed (`rename_run`:
validated names, collision-safe, keeps `summary.json` and the index
coherent) from the browser.

**Schema guard** (§6.3/§6.5, DECISIONS #46/#47/#65/#83/#100):
`summary.json`'s
`schema_version` plus the file-naming convention — sibling tables arrive
without breaking migrations, exactly as `cooperation.parquet` did in schema 2,
`agents.parquet` in schema 3 (which still reserves room for the §6.3
spatial and §6.5 attribute snapshot columns), and the four event-time
tables in schema 4. Loaders accept 1-4 and reject folders written
by a NEWER schema version: a schema-1 folder simply
has no cooperation data and renders without the cooperation chart; a
schema-1/2 folder has no per-agent data and renders without the
population/energy/age charts; a schema ≤ 3 folder has no event-time data
and renders without the async views (#65 compatibility, applied again).

Consumers: the headless CLI (`python -m pdsim.run <config.yaml>` or
`--scenario NAME`) records every run; the UI's "Record this run" control
(default ON) records live runs; the UI's Results browser tab lists the index
and re-renders any recorded run with the full #44/#45 view toggles, and can
load a recorded config back into the parameter panel.
