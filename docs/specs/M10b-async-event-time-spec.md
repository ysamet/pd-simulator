Status: in progress

# M10b — Asynchronous / Moran-style event time

Companion explainer: `docs/explainers/M10b-async-event-time-explainer.md`
(the science, the update-rule literature, and the seam rationale — read it
for the *why*; this spec is the *what* and *how*).

Read DECISIONS #32, #34, #35, #47, #57, #63, #65, #79, #80, #81, #82, #83,
#85, #86, #87, #89, #91 and DESIGN §2.10/§3.1/§4/§8 first.

Depends on: **M10a** (shipped — DECISIONS #76-#84). This is **M10 part b** —
the asynchronous / Moran-style event time-model that #85 split out of M10 and
that #82 named as the home of explicit birth/death events. Population
structure (adjacency, local birth, the SpatialKernel matcher) is **M11**, not
here; M10b stays aspatial/well-mixed throughout.

## Frozen intent

M10b dissolves the generation as the unit of time. Time advances one
individual **event** at a time: an agent is activated, plays, and the
demographic and cultural consequences fire immediately — no frozen boundary
snapshot, no atomic generation. Two async population modes ship: `variable_n`
carries the M10a energy economy into event-time (the research through-line),
and `fixed_n` is the textbook-Moran comparison mode. Imitation returns as a
separate cultural overlay channel, layerable on either mode. The synchronous
path — imitation AND the M10a economy — stays **byte-identical**: every
change is additive or async-mode-only, pinned by regression tests.

### The seam dilemma (why the architecture looks like this)

An async time model is a TIME change, but it cannot be built without deciding
the moment and manner each birth is evaluated — and that decision is exactly
what M11 (a SPACE change) will rewrite when "who fills the empty site"
becomes local. Two options were weighed:

- **Option A — the async event loop owns the admission policy** (scan the
  whole population, energy-sort, pick the breeder inline). Rejected: it
  re-hardcodes the aspatial global assumption inside the hot loop, so M11
  would have to reopen the loop and re-verify the entire async ordering/RNG
  contract just to swap in local placement.
- **Option B (CHOSEN) — the async loop delegates to `admit_births()` /
  `place_offspring()`** and stays ignorant of the candidate set and the
  admission policy. In M10b-aspatial those functions implement
  whole-population energy priority (identical numbers to Option A); M11 swaps
  only their implementations (candidate set = neighbours; placement = a
  specific empty neighbouring site) and the async loop is never reopened.

This is why #80 checks placement BEFORE paying the stake and why #89(b) named
the two free functions: the seam was carved for exactly this moment.

## Defining principles

1. **The sync path is untouched.** `time_model = "synchronous"` is the
   existing generational clock — M10a and everything before it — with
   byte-identical events, RNG streams, and persisted output (schema ≤ 3).
2. **Same seed, same run** (hard rule 5). Every async draw has a pinned
   place in the within-event order (Design 8). Any change to that order is a
   breaking change requiring a DECISIONS entry.
3. **Observer concerns never touch the simulation** (#35). The
   generation-equivalent clock and the recording cadence are bookkeeping and
   emission control; they consume no RNG and influence nothing.
4. **Raw, not derived** (#47). Explicit events and state snapshots each
   carry only what the other cannot reconstruct (see Design 7).
5. **Everything id-ordered is sorted by `agent_id`, explicitly** — the M10a
   invariant, unchanged. Deterministic tie-breaks are always (value, id asc);
   never a random draw.
6. **The seam functions stay free functions** (#89b). M10b calls them; M11
   generalises them (DESIGN first, per hard rule 6).

## Design 0 — the event anatomy (what one async event is)

The prompt-level designs (1-10 below) need a pinned definition of "an
event". **One event = one focal activation**, the literature-standard random
asynchronous update:

1. A **focal agent** is drawn uniformly from the living population.
2. The focal plays **`matching.opponents_per_agent` (k) matches** against
   distinct partners drawn uniformly from the others — the RandomK draw
   idiom, including the #81 clamp (`min(k, N−1)`; at N = 1 no partner
   exists, no match is played, and no pair draws are consumed).
3. The event's consequences fire: ledger accrual, demographic step
   (per `async_population`), imitation rolls (when the overlay is on).

**Why a k-match bundle and not a single match:** the generation-equivalent
clock (Design 5) makes sync and async runs comparable in TIME; the bundle
makes them comparable in INCOME. Over one generation-equivalent (N events)
each agent is focal once on average and drawn ≈ k times — ≈ 2k match
participations, exactly the sync `random_k` interaction budget (#44/#57). A
single-match event would cut income per generation-equivalent by a factor of
k, silently decalibrating every M10a survival window (L is tuned against 2k
matches of income); V5's sync-vs-async comparison would collapse for
economic, not scientific, reasons.

Consequences, pinned:

- `matching.opponents_per_agent` is **consumed** in async mode with its
  existing meaning. `matching.matcher` is **ignored** (#34 greyed pattern):
  round-robin is a generation-batch concept with no event-time analogue, and
  uniform partner draws ARE the well-mixed corner. M11's SpatialKernel
  matcher will take over partner selection (forward reference, Design 9).
- Effects are **immediate** — this is what asynchrony means. A strategy
  copied by the imitation overlay after match 2 of a bundle plays as the new
  strategy in match 3. A death fires the moment its trigger evaluates, not
  at a boundary.
- N(t) is read **at event start**; the event belongs to the population that
  carried it. N = 0 never starts an event (extinction already ended the
  run).

## Design 1 — time model as a clock choice

New parameter **`dynamics.time_model` ∈ {`synchronous`, `asynchronous`}**,
default `synchronous`. Synchronous = the existing generational clock (M10a
and earlier), unchanged and byte-compatible. Asynchronous = event-time as
defined in Design 0; the generation is dissolved as the unit of time.

The engine dispatches: `time_model == "asynchronous"` (evolution mode only)
routes to the new `AsyncDynamics` loop; everything else routes exactly as
today. In async mode `dynamics.reproduction_mode` is **ignored** (#34): the
async paradigm is chosen by `async_population` (Design 2), and both async
modes are birth-death paradigms — the SelectionRule family and
ScoreAccounting are ignored too (with one carve-out: `selection_beta` is
consumed by the imitation overlay, Design 4). `dynamics.generations` keeps
its name and meaning as **run length in generation-equivalents**: an async
run ends when the clock reaches `generations` (or at extinction).

## Design 2 — two async population modes

New parameter **`dynamics.async_population` ∈ {`variable_n`, `fixed_n`}**,
default `variable_n`. Applies only when `time_model = asynchronous`.

- **`variable_n`** — the M10a energy-economy demographics (#80) run in
  event-time. A death fires on insolvency or age; a birth fires when an
  agent clears θ with a slot free under K. Deaths and births are DECOUPLED
  and (hazard coins aside) DETERMINISTIC — they are the demographic engine;
  `moran_rule` and `fixed_n_death_rule` do not apply here. Extinction ends
  the run early (#82 semantics unchanged).
- **`fixed_n`** — classic Moran: the population is pinned at its initial
  size; every event ends with exactly one replacement — one death paired
  with one fitness-proportional birth — governed by `moran_rule` and
  `fixed_n_death_rule` (Design 3). No insolvency or age deaths, no θ
  births, no extinction; `carrying_capacity` is ignored.

**The ledger runs identically in both modes** (income at match completion,
time-based costs and returns in the accrual sweep — see Design 2a). In
`fixed_n` energy matters only as Moran **fitness** and as the
`energy_decides` death criterion. Two properties make this safe for the
textbook comparison: fitness weights use the shift idiom (Design 3), and a
uniform per-capita cost L shifts every balance equally — so L **cancels out
of fitness selection entirely**; and with `capital_return_rate = 0` (the
default) nothing else distorts. The pure textbook corner is therefore the
defaults plus `offspring_stake = 0` (nothing transferred at birth) and
`fixed_n_death_rule = pure_random`.

### Design 2a — the ledger in event-time (the M10a → M10b conversion)

The M10a boundary ledger (#80 step 3) converts term-by-term, with
Δt = 1/N(t) the event's clock advance (Design 5):

| M10a (per boundary) | M10b async (per event) |
|---|---|
| income: `raw_score` folded at boundary | each match's payoff credited to both participants **at match completion** |
| `engagement_cost × matches` at boundary | `engagement_cost` charged per participant **at match completion** (per-match semantics, #86 unchanged) |
| `basic_living_cost` L per generation | `L·Δt` charged to **every living agent** in the accrual sweep — ≈ L per generation-equivalent |
| `capital_return_rate`: `e·(1+r)` at boundary | `e ← e·(1+r)^Δt` in the accrual sweep — compounds to exactly (1+r) per generation-equivalent on a static balance |
| insolvency: `e < 0` at boundary | `e < 0` evaluated at every demographic step — **strictly negative**, #80 unchanged |
| eligible at `e ≥ θ`; one birth per parent per generation | eligible at `e ≥ θ` AND **refractory clear**: at least 1.0 time units since the parent's last birth (founders: since t = 0) |
| mortality coin per agent per boundary | one coin per agent per **integer birthday**: when an agent's age crosses k, one coin at `mortality_probability(k−1)` — the same lifetime coin sequence p(0), p(1), … as sync |

The **breeding refractory period of 1.0 time units** is a fixed convention,
not a knob. It is the event-time image of #80's one-birth-per-generation
rule and preserves its consequence: the dynastic channel runs through
breeding frequency, not endowment. Without it, a parent at e ≥ 2θ would
burst-breed within a single generation-equivalent (paying σ leaves it at
≥ θ, immediately eligible again), rerouting dynasty through stock size —
exactly what #80 rejected.

The accrual sweep runs once per event, over every living agent in ascending
id order, and consumes no RNG. Its cost is O(N) per event — O(N²) per
generation-equivalent — which is bookkeeping-cheap next to the k matches
each event plays; the #91 cost-model note gains an async column at the
Phase-E bench re-run.

Interest compounding grain, named honestly: sync applies (1+r) once per
boundary to the boundary balance; async compounds continuously over income
that arrives mid-period, so the two trajectories agree exactly only on a
static balance. This is inherent to event-time, not a bug; the explainer
owns the arithmetic.

Ages: an agent's age is `t − birth_time` in generation-equivalents, tracked
by the loop (founders: `birth_time = −staggered_age` via
`staggered_founder_ages`, so staggering carries over when age-mortality is
active). `AgentSnapshot.age` stays an integer — the number of completed
generation-equivalents (floor) — so the snapshot shape is unchanged.

## Design 3 — the Moran replacement rule (`fixed_n` only)

**`dynamics.moran_rule` ∈ {`birth_death`, `death_birth`, `random`}**,
default `death_birth`.

- **`death_birth`**: an agent dies (selection per `fixed_n_death_rule`); its
  neighbours — the whole remaining population, aspatially — compete to
  reproduce into the emptied slot, fitness-proportionally.
  `DeathEvent.cause = "random_moran"`.
- **`birth_death`**: an agent is chosen to reproduce fitness-proportionally
  from the whole population; its offspring replaces one of the OTHER agents
  (selection per `fixed_n_death_rule`). `DeathEvent.cause = "replacement"`.
- **`random`**: a weighted mixture of the two, rolled PER EVENT (Design 8:
  the roll is the first demographic draw and exists only when `random` is
  active).

**The weight pair is two scalar registry parameters** —
`dynamics.moran_weight_birth_death` and `dynamics.moran_weight_death_birth`,
floats ≥ 0, defaults 0.5 / 0.5 — a spec-time refinement of the design
chat's single tuple-valued knob: the Parameter Registry's kinds are scalar
(int/float/bool/choice), and two floats reuse the whole existing
widget/validation/docs machinery (the M10a `None`-sentinel precedent — reuse
machinery over inventing a kind). Weights are normalised at use
(`w_bd / (w_bd + w_db)`); a cross-field validator rejects both-zero, and
only when the pair is actually consumed (#34).

**`dynamics.fixed_n_death_rule` ∈ {`pure_random`, `energy_decides`}**,
default `energy_decides`. Governs the death-selection slot of whichever rule
fires: under `death_birth`, who dies; under `birth_death`, which neighbour
the offspring replaces. `pure_random` draws uniformly (textbook Moran —
death independent of energy, the setting for reproducing published
results); `energy_decides` picks the lowest-energy candidate
deterministically, ties to the lowest id (the economy-flavoured hybrid:
count pinned, metabolism still aims the reaper). Note the cause taxonomy
above names the mechanism's SLOT (`random_moran` = the Moran death slot),
not the selection rule — under `energy_decides` the slot is filled
deterministically; the run's config records which.

**Fitness-proportional selection** uses the #63 `ProportionalSelection`
idiom exactly: weights `w_i = e_i − min(e)` over the candidate set (energies
can be negative; roulette weights cannot), uniform fallback when all weights
are zero, one `rng.choice` draw over candidates in ascending id order.

**Births in fixed_n**: the parent pays `offspring_stake + reproduction_
overhead` unconditionally (after the `place_offspring` check — Design 9);
the newborn starts at σ with a fresh passport id, `parent_id` set, empty
histories, and the μ-mutation draw via
`StrategySwitchReproduction.offspring_strategy` (registry semantics
unchanged: μ applies to economy newborns). A parent driven negative by the
stake is legal in `fixed_n` — there is no insolvency death, and the weight
shift absorbs negative balances. σ = 0 recovers the textbook no-endowment
corner (#87's ledger-balance rationale is preserved: σ is always a
transfer, never creation).

Tooltip note (plain language, for Phase E): `death_birth` is the update
rule under which population structure can favour cooperation (the b/c > k
regime, Ohtsuki et al. 2006); the structure itself arrives at M11, so in
M10b's well-mixed world the three rules differ mechanically but that
cooperation result does not yet bite.

## Design 4 — imitation as a separate overlay channel

**`dynamics.imitation_overlay`**, bool, default off — a spec-time
refinement of the chat's `{off, on}` choice pair: a two-state switch is the
registry's `bool` kind (checkbox widget), semantics identical.

Rationale to record: birth-death and death-birth are DEMOGRAPHIC — they
change who exists, and fire on birth/death triggers. Imitation is CULTURAL —
it changes what an existing agent believes (same identity, energy, age,
histories) and fires on an INTERACTION trigger. Different trigger, different
ontological layer — so it is its own channel, layerable on top of EITHER
async population mode, and NOT a fourth Moran rule.

Mechanics, pinned: when on, after each completed match, one Fermi adoption
roll — the potential adopter is the participant with the LOWER match total
(exact tie: the lower agent id), and it copies the other's strategy with
probability `logistic(selection_beta · (winner_total − loser_total))`, the
existing Fermi rule reusing the existing `dynamics.selection_beta` (no new
β: the semantics — selection intensity on a score difference — genuinely
match). Exactly one `rng.random()` coin per completed match whenever the
overlay is on, unconditional — even when both participants already share a
strategy (the copy is a no-op but the coin is drawn: the #80 active-flag
idiom, keeping the stream independent of strategy states). Strategy-copy
ONLY: no one is born or dies, no energy/identity/age change, nothing
charged, histories untouched. An `ImitationEvent` is emitted only when the
strategy actually changes (a no-op copy is not an event; the coin, not the
event, is the RNG contract).

> **ADDENDUM (frozen-spec ritual, #62):** Superseded during Phase E — the
> async overlay uses the symmetric adopter rule; see DECISIONS #93.

## Design 5 — event-time clock and comparability (fixed convention, NOT a knob)

The x-axis for async runs is **generation-equivalents**: the clock advances
by **Δt = 1/N(t)** per event, N(t) read at event start; one
generation-equivalent completes when the running sum reaches 1. In
`fixed_n` this is exactly the textbook convention (N events = one
generation); in `variable_n` it self-adjusts as the population grows and
shrinks. The clock is pure bookkeeping — it changes nothing in the
simulation, consumes no RNG, and is deliberately NOT a parameter. It is
surfaced as an axis tooltip in the app (Phase E), and every explicit event
and period record carries its `gen_equiv_time` stamp. Sync runs leave the
stamp `None` — the honest "this run has no event-time clock".

## Design 6 — recording cadence (this IS a knob)

New registry section **Output**, two parameters:

- **`output.recording_cadence` ∈ {`per_generation_equivalent`, `per_event`,
  `every_m_events`}**, default `per_generation_equivalent` — comparable to
  sync, sane file sizes.
- **`output.recording_cadence_m`**, int ≥ 1, default 1 — applies only when
  `every_m_events` (#34 pattern).

The cadence decides when the async loop emits period-level events
(`GenerationFinished`): at each integer clock crossing, after every event,
or after every m-th event. Its placement relative to #35: like granularity
it is an OBSERVER control and must never influence the simulation (pinned
by test: same config + seed at different cadences → identical simulation
state trajectories); unlike granularity it lives in the config, because it
decides what the persisted record CONTAINS — and what a run recorded is
part of reproducing it (hard rule 8). It trades resolution against file
size and the #10 chart-rendering ceiling. Sync runs ignore both parameters
(#34). Fine-granularity (`round`/`match`) events remain governed by the
engine's `granularity` argument, orthogonally, exactly as today.

## Design 7 — explicit birth/death/imitation events (deferred here by #82)

Async time makes per-event ordering meaningful, so async mode emits three
new frozen event types (in `pdsim/core/events.py`, joining the existing
five):

- **`BirthEvent`**: `agent_id`, `parent_id`, `strategy`, `energy` (starting
  balance = σ), `cause` (`"threshold"` in variable_n, `"moran"` in
  fixed_n), `event_index`, `gen_equiv_time`.
- **`DeathEvent`**: `agent_id`, `cause`
  (`"insolvency" | "age" | "replacement" | "random_moran"`),
  `event_index`, `gen_equiv_time`.
- **`ImitationEvent`**: `agent_id`, `from_strategy`, `to_strategy`,
  `source_agent_id`, `event_index`, `gen_equiv_time`.

`event_index` is the 0-based global index of the interaction event that
produced it; `gen_equiv_time` is the clock after that event's advance.

Stream placement: explicit events are buffered per recording period and
flushed **in occurrence order immediately before that period's
`GenerationFinished`** — they are period-level truth, emitted at every
granularity (like the period events themselves; #35's granularity argument
governs only `RoundPlayed`/`MatchFinished`). SYNCHRONOUS mode emits none of
these and keeps `GenerationFinished` + the #82 snapshots byte-identical.

Coexistence with snapshots, justified against #47: async period events
still carry `agents` snapshots. Neither channel derives from the other —
explicit events give exact intra-period timing and causes (which snapshots
diff away), snapshots give the energy/age state between demographic events
(which no birth/death event records, since energy changes every event
without a demographic event firing). `GenerationFinished` additionally
gains `gen_equiv_time: float | None = None` (None under sync — the M10a
additive-field precedent). Internally, `GenerationReport` mirrors both
additions (`gen_equiv_time`, plus a `demographic_events` tuple the engine
flushes); sync reports keep the defaults.

## Design 8 — RNG reproducibility contract (extends #80)

The full within-event draw order, pinned. Draws exist ONLY when their
governing flag makes them meaningful (the #80 active-flag idiom), and every
selection over agents is over the ascending-id living population:

1. **Focal draw** — `rng.integers(N)`, an index into the id-ascending
   population. Skipped entirely at N = 1 (no partner exists; the event
   still advances the clock and runs accrual — the #81 lone-survivor
   thermodynamics in event-time).
2. **Partner draw** — one `rng.choice(N−1, size=min(k, N−1),
   replace=False)` over the focal's others (the RandomK idiom + #81 clamp),
   skip-mapped around the focal; partners are met in drawn order.
3. **Per match, in partner order**: the #23 per-round match draws
   (unchanged), then — only when `imitation_overlay` is on — exactly one
   adoption coin `rng.random()` (Design 4).
4. **Accrual sweep** — no RNG.
5. **Demographic step**:
   - `variable_n`: (a) birthday hazard coins — only when
     `age_mortality_active`, one `rng.random()` per agent whose integer age
     crossed this event, ascending id, unconditional at p = 0 or 1;
     (b) age-cap and insolvency deaths — deterministic, no RNG;
     (c) births — `admit_births` (RNG-free, energy priority), then the
     admitted set in ascending parent-id order: placement check → σ +
     overhead payment → passport id → one μ-mutation draw each (coin only
     when μ > 0, roster index only on a hit, per `reproduction.py`). The
     M10a two-orderings contract (#80) carries over verbatim.
   - `fixed_n`: (a) rule roll — only when `moran_rule = "random"`: one
     `rng.random()` against the normalised birth_death weight, the FIRST
     demographic draw of the event; (b) per the selected rule:
     `death_birth` = death draw (one `rng.integers` — only under
     `pure_random`; `energy_decides` is deterministic and draws nothing)
     → fitness-proportional breeder draw (one `rng.choice` over the
     remaining candidates) → μ-mutation draw(s); `birth_death` =
     fitness-proportional breeder draw → victim draw (uniform — only under
     `pure_random`) → μ-mutation draw(s).
6. Clock advance, recording, and period emission — no RNG (#35).

Pinned by tests: a golden-master async run (fixed seed → identical event
stream, twice, plus a hand-pinned trace prefix); a `moran_rule = "random"`
master (the rule roll's position would diverge if mis-pinned); and a
two-orderings case where energy-priority admission order ≠ parent-id order
(the #80 pin, in event-time).

## Design 9 — the Option B seam (the frozen architectural choice)

The async event loop calls **`admit_births()` / `place_offspring()`** for
every birth — variable_n capacity admission AND fixed_n slot-filling — and
never assumes the candidate set is the whole population or that admission
is a global energy sort. **Place-before-pay** (#80) is preserved
everywhere: the structural gate is checked before σ leaves the parent
(pinned by the same stub-test pattern M10a wrote).

FORWARD-REFERENCE NOTE (recorded now, built at M11): `place_offspring()`
will receive a placement RADIUS at M11 — a soft temperature kernel over the
Chebyshev/Moore neighbourhood, hard cutoff recoverable as temperature → 0 —
and the movement/interaction radius will live in the SpatialKernel matcher
(`matching.matcher`), which will also take over Design 0's partner
selection. Under a radius, `place_offspring()` can genuinely fail (all
cells within radius occupied) — the charged-for-a-child-never-born bug #80
pre-empted. M10b leaves both seams as their aspatial implementations.

## Design 10 — persistence (schema 4, the #47/#65/#83 pattern)

`SCHEMA_VERSION` becomes **4**, written exactly when the run produced
event-time data (the honest presence rule, #83): async runs write 4; sync
economy runs still write 3; sync imitation runs still write 2 — both
byte-identical to M10a output. New sibling tables, each dense, each written
only when it has rows, each read with the missing-file → empty shape:

- `births.parquet` — period, event_index, gen_equiv_time, agent_id,
  parent_id (nullable Int64), strategy, energy, cause.
- `deaths.parquet` — period, event_index, gen_equiv_time, agent_id, cause.
- `imitations.parquet` — period, event_index, gen_equiv_time, agent_id,
  source_agent_id, from_strategy, to_strategy.
- `periods.parquet` — period, gen_equiv_time (the period → clock mapping
  the charts' x-axis needs; async runs only).

`timeseries.parquet`, `cooperation.parquet`, and `agents.parquet` keep
their shapes (no widened columns — #47c). The loader accepts 1-4, rejects
> 4 with the existing message, and refeeds loaded events/snapshots through
the same `GenerationFinished`/event types the live run used, so every
derived view is recomputed by identical code (#65). A schema ≤ 3 folder
renders without the async views — no migration, no error.

Async period semantics elsewhere: `RunFinished.completed` counts
period-level events emitted (its grain follows the cadence — documented);
extinction closes the run with the #82 semantics unchanged.

## Parameters (all new knobs; registry section, kind, default, phase)

| Key | kind | default | phase | notes |
|---|---|---|---|---|
| `dynamics.time_model` | choice (`synchronous`, `asynchronous`) | `synchronous` | A | registered immediately after `dynamics.reproduction_mode` (widget-order rule, M10a Task 1) |
| `dynamics.async_population` | choice (`variable_n`, `fixed_n`) | `variable_n` | B | end of Dynamics block, after the M10a economy params |
| `dynamics.moran_rule` | choice (`birth_death`, `death_birth`, `random`) | `death_birth` | B | |
| `dynamics.moran_weight_birth_death` | float ≥ 0 | 0.5 | B | the pair refinement (Design 3) |
| `dynamics.moran_weight_death_birth` | float ≥ 0 | 0.5 | B | validator: not both 0 when consumed |
| `dynamics.fixed_n_death_rule` | choice (`pure_random`, `energy_decides`) | `energy_decides` | B | |
| `dynamics.imitation_overlay` | bool | False | C | the bool refinement (Design 4) |
| `output.recording_cadence` | choice (`per_generation_equivalent`, `per_event`, `every_m_events`) | `per_generation_equivalent` | D | new Output section + `OutputConfig` model |
| `output.recording_cadence_m` | int ≥ 1 | 1 | D | consumed only under `every_m_events` |

Every entry carries a plain-language, mechanism-explaining description
(hard rules 1/3; each choice enum value explained, per the M10a §12 rule).
`python -m pdsim.gendocs` is rerun in every phase that touches the registry.

Ignored-parameter map (#34, for Phase E greying): under `synchronous`, all
eight async knobs are greyed. Under `asynchronous`: `reproduction_mode`,
the SelectionRule family (except `selection_beta` when the overlay is on),
ScoreAccounting, and `matching.matcher` are greyed; `moran_rule` +
`fixed_n_death_rule` only apply when `fixed_n`; the weight pair only when
`moran_rule = "random"`; `carrying_capacity`, the mortality trio, and
θ/σ-as-birth-gate only when `variable_n` (the ledger knobs — L, engagement,
r, σ — apply in both async modes).

## Phase plan (proactive session reset at each ▲)

- **Phase A — async engine core.** `pdsim/core/async_dynamics.py`
  (`AsyncDynamics`): the Design 0 event loop; the Design 5 clock; the
  Design 2a ledger (accrual sweep, match-time income/engagement);
  variable_n's deterministic demographic core (insolvency deaths, θ +
  refractory births through the Option B seam) — enough demography to
  exercise births, deaths, extinction, and the seam; the three event types
  + `gen_equiv_time` on `GenerationFinished`/`GenerationReport`; the
  `dynamics.time_model` registry entry + config field + engine dispatch;
  period emission at the fixed `per_generation_equivalent` default. The
  mortality trio and everything fixed_n wait for Phase B (a Phase A golden
  master therefore runs with age-mortality off — the #80 idiom keeps it
  valid forever). V6 (as far as Phase A machinery goes) and V7 green. ▲
- **Phase B — the demographic engines completed.** fixed_n Moran:
  `async_population`, `moran_rule` (BD/DB/random + the weight pair),
  `fixed_n_death_rule`; variable_n's mortality trio in event-time (birthday
  coins, age cap, founder staggering via birth_time). V1, V3, and the
  moran-random golden master. ▲
- **Phase C — imitation overlay.** Fermi-on-match-completion, copy-only,
  reusing `selection_beta`; `ImitationEvent` emission. V2. ▲
- **Phase D — recording cadence + persistence.** The Output section +
  `OutputConfig`; schema 4, the four sibling tables, loader round-trip +
  backward compat (#47 guard). V4. ▲
- **Phase E — registry polish, UI, scenarios.** All remaining tooltips and
  conditional greying per the ignored-parameter map; the
  generation-equivalent x-axis + axis tooltip in the charts; the named
  validation scenarios; bench re-run under async (#91 discipline). V5, and
  V1-V4 re-confirmed through the app.

## Validation

APP-FIRST (#42/#61). With the venv active (`.venv\Scripts\Activate.ps1`),
launch `streamlit run pdsim/ui/app.py`.

- **V1 (app)** — scenario **`async_death_birth_fixation`**:
  `time_model = asynchronous`, `async_population = fixed_n`,
  `moran_rule = death_birth`, overlay off. Run it live: the composition
  chart shows one strategy driving toward fixation while total population
  height stays flat (N pinned); the x-axis is labelled in
  generation-equivalents.
- **V2 (app)** — scenario **`imitation_overlay_only`**:
  `imitation_overlay = on` in a configuration with no demographic turnover
  (fixed_n would still churn identities — so: variable_n with an
  unreachable θ, zero living cost, mortality off). Strategy shares MOVE
  while the population count stays flat and the run's
  `total_agents_born` equals the founder count — the cultural/demographic
  split made visible.
- **V3 (app)** — scenario **`moran_random_mix`**: `moran_rule = random`
  with non-uniform weights (e.g. 0.8/0.2); its trajectory sits between the
  pure BD and pure DB scenarios run from the same widgets.
- **V4 (app)** — on any async scenario, switch **Recording cadence**
  between `per_generation_equivalent` and `per_event`: the trace density
  changes visibly; the final composition does not (observer-only, pinned).
- **V5 (app)** — scenario **`sync_vs_async_economy`**: the M10a growth
  economy under `synchronous`, then flipped to `asynchronous`: both grow
  from 40 toward K = 200 on comparable x-axes; the Economy panel's window
  readout applies to both (the Design 0 income-parity argument, visible).
- **V6 (CLI, headless)** — the RNG golden-masters: a fixed seed reproduces
  an async run byte-for-byte (event stream compared twice, plus the pinned
  trace prefix), including under `moran_rule = random`.
- **V7 (regression)** — pre-existing synchronous runs (one imitation, one
  M10a economy) produce byte-identical event streams and persisted folders
  (schema 2 / 3) to before this milestone; the golden validation tests
  (DESIGN §7) stay green.

Automated tests complement — never substitute (#42/#61): the within-event
draw order masters (Design 8); the two-orderings pin; place-before-pay stub
(fixed_n and variable_n paths); refractory (a parent at e ≥ 2θ breeds at
most once per generation-equivalent); N = 1 event anatomy (no pair draws,
accrual still bites); clock arithmetic (Σ 1/N crossings, N read at event
start); cadence is observer-only; fitness-weight shift + uniform fallback +
energy_decides tie-breaks; imitation coin unconditional-when-on / no event
on no-op copy; schema-4 round-trip + 1-3 backward compat + reject > 4;
extinction in async; sync byte-identity.
