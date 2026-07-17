Status: implemented (see DECISIONS #76-#84)

# M10a — Score-as-energy growth economy (synchronous generational)

Companion explainer: `docs/explainers/M10-growth-economy-explainer.md` (the
science, the worked arithmetic, and the literature grounding — read it for the
*why*). This spec is the *what* and *how*.

Read DECISIONS #20, #22, #23, #31, #32, #34, #35, #38, #44, #47, #48, #57, #61,
#62, #63, #64, #65 and DESIGN §2.7/§3.1/§4/§5/§8 first.

This is **M10 part a** — the energy economy on the *existing generational
clock*. The asynchronous / Moran-style event time-model is **M10b**, a separate
later spec. Nothing here dissolves the generation as the unit of time.

## Frozen scope

**M10a delivers the entire variable-N invariant.** The generation stays the unit
of time; population size is constant *within* a generation and changes only *at
the boundary*, where all births and deaths are computed against one frozen
end-of-generation snapshot and applied simultaneously.

**Energy REPLACES imitation.** `energy_economy` is a distinct evolutionary
paradigm — *birth-death dynamics*, not a modification of v1's *imitation
dynamics* (Fermi copying). In `energy_economy` mode the whole SelectionRule
family and the ScoreAccounting family **grey out** via the #34
ignored-but-valid pattern. Differential survival *is* the selection.

In scope: the energy ledger, the two cost components, stake-transfer
reproduction, the mortality trio, carrying capacity with deterministic
admission, passport ids with `parent_id` lineage, the variable-N `random_k`
contract, the per-agent snapshot, `schema_version` 3 + `agents.parquet`, the
calibration readout, the Economy panel, three economy charts, one scenario.

Out of scope (named, not built): async/Moran event time (M10b); population
structure and local birth (M11); tags (M12); taxation, redistribution,
immigration, inheritance beyond the 100%-tax corner (M15); explicit
birth/death events (M10b); vectorization (M18).

## Defining principles

1. **The generation stays atomic.** All births and deaths at one boundary,
   against one frozen snapshot. No mid-boundary feedback.
2. **The imitation path stays byte-identical.** Every change is additive or
   economy-mode-only. An `imitation` run under M10a code must reproduce its
   pre-M10a seeded trajectory exactly, and must still write `schema_version`
   ≤ 2. This is testable and is pinned by a regression test.
3. **Raw, not derived** (#47). Population size is `sum(composition.values())` —
   it is never carried in a payload or written to a table.
4. **Everything id-ordered is sorted by `agent_id`, explicitly.** Deaths make
   ids non-contiguous; list position is never a proxy for id.
5. **Well-mixed is a real mode, not a stub** — it is the fully-connected corner
   that M11 will generalise.

## Task 0 — verify first (do this before writing any code)

Two claims the design layer could not confirm from `docs/` alone. Verify each
against the code, then proceed. Report what you found.

**0a — per-agent match count at the energy-update step.** The `− engagement_cost
× matches_played` term needs a per-agent *match* count.

*Expected finding:* it does not exist. `Agent.rounds_played` is a property
summing `len(history.my_moves)` across `_histories` — that is **rounds**, not
matches. `len(agent._histories)` counts *distinct opponents met*, which is also
not the match count: `RandomK`'s own docstring states a pair may play twice in
one generation (A drawing B and B drawing A), so distinct-opponents undercounts.

*Fallback (implement this if the expected finding holds):* build a
**per-generation tally** keyed by passport id, fed one finished match at a time
during the match phase, recording for **both** participants `matches_played += 1`
and `rounds_played += result.n_rounds`. A fresh tally each generation. Mirror the
`_CooperationTally` shape and location in `pdsim/core/dynamics.py`. It is **pure
bookkeeping: it consumes no RNG and never influences the simulation.** Implement
it in `EconomyDynamics` only, so the imitation path stays untouched (principle 2).

**Why the tally must count rounds as well as matches.** `engagement_cost` needs
the match count. But because per-opponent histories now **persist** across
generations in economy mode (Task 3), `Agent.rounds_played` — a property derived
from `_histories` — becomes a **lifetime** count there, and can no longer serve as
#44's per-generation denominator. `EconomyDynamics` must therefore build its
`GenerationReport.rounds_played` from **this tally**, never from
`agent.rounds_played`. Getting this wrong is **silent**: nothing raises, the
per-round score view simply decays as agents age. Pin it with a test — an agent
alive for three generations must report *this* generation's rounds, not its
life's.

**0b — the birth loop's home.** Confirm that `PopulationDynamics.step()` in
`pdsim/core/dynamics.py` is the generation boundary, and that the new
`EconomyDynamics.step()` is therefore its sibling. The
placement-check-before-σ ordering and the admission-order-vs-id-order split
(Task 5) must both be enforced there, in one place.

## Task 1 — Parameter Registry (`pdsim/config/registry.py`)

Twelve new parameters, section `"Dynamics"`. Every one carries a plain-language
`description` written for someone who does not know game theory (hard rule 3).

**Registration ORDER matters.** The app renders widgets in registry order and
`greying()` keys off values already gathered this script run, so
`dynamics.reproduction_mode` must be registered **immediately after
`dynamics.generations` and BEFORE `dynamics.selection_rule`**. The remaining
eleven follow the accounting parameters, at the end of the Dynamics block.

| Key | kind | default | notes |
|---|---|---|---|
| `dynamics.reproduction_mode` | choice | `"imitation"` | choices `("imitation", "energy_economy")` |
| `dynamics.reproduction_threshold` | float | `500.0` | θ; min 0.0 |
| `dynamics.offspring_stake` | float | `400.0` | σ; min 0.0 |
| `dynamics.initial_energy` | float | `None` | **nullable = auto → σ**; min 0.0 |
| `dynamics.basic_living_cost` | float | `200.0` | min 0.0 |
| `dynamics.engagement_cost` | float | `0.0` | min 0.0 |
| `dynamics.reproduction_overhead` | float | `0.0` | min 0.0 |
| `dynamics.capital_return_rate` | float | `0.0` | min 0.0 |
| `dynamics.carrying_capacity` | int | `200` | K; min 1 |
| `dynamics.base_hazard` | float | `0.0` | min 0.0, max 1.0 |
| `dynamics.senescence_factor` | float | `None` | **nullable = auto**; min 0.0, `minimum_exclusive=True` |
| `dynamics.max_age` | int | `0` | 0 = no cap; min 0 |

**The two `None` defaults are the registry's first DERIVED defaults** — new
machinery. Use `nullable=True` with `default=None` meaning "auto", following the
existing `population.memory_depth` precedent (nullable float/int whose `None`
means something specific) rather than inventing a `"auto"` string sentinel in a
float field. The design freeze said "a sentinel (e.g. `"auto"`)"; `None` +
`nullable` is that sentinel, chosen to reuse machinery that already exists. Log
this refinement in DECISIONS.

Descriptions must explain the *mechanism*, not just the name. Required content:

- `reproduction_mode`: **each enum value gets its own explanation** (§12 rule).
  `imitation` = the classic setting: population size never changes; each slot in
  the next generation copies a parent's strategy, chosen by the selection rule.
  `energy_economy` = agents hold a stock of energy; they earn it by playing, pay
  it to stay alive, and reproduce when they can afford to — nobody copies
  anyone, and the population grows and shrinks. Switching to `energy_economy`
  makes the selection rule and score accounting settings inert.
- `initial_energy`: "Leave blank for 'same as the offspring stake' — founders
  then start life exactly like newborns."
- `senescence_factor`: "Leave blank for 'auto', which picks the value that makes
  the death chance reach exactly 1.0 at the maximum age."
- `capital_return_rate`: name the rentier consequence in one sentence.
- `carrying_capacity`: name that it is the well-mixed model's stand-in for
  physical room (K's scope is **aspatial-specific**, not universal — under M11
  capacity may become emergent from site count).

Also **update `population.size`'s description**: it is the *starting* population
size; in `energy_economy` mode the population changes from generation to
generation.

Run `python -m pdsim.gendocs` and stage `docs/PARAMETERS.md` (a pytest drift
test fails while it is stale).

## Task 2 — config layer (`pdsim/config/experiment.py`)

Add the twelve fields to `DynamicsConfig` (mapped in `_registry_keys`, built
with `_registry_field`), with full docstring attribute entries.

**The derived-default resolver.** `_RegistryBackedModel` sets
`model_config = ConfigDict(extra="forbid", frozen=True)` — a `mode="after"`
validator therefore **cannot** assign to a field. Use a
`@model_validator(mode="before")` on `DynamicsConfig` that rewrites the raw
input mapping. Because `mode="before"` runs *before* defaults are filled, treat
an **absent key and an explicit `None` identically**; read any input it needs
(e.g. `offspring_stake`) from the mapping, falling back to
`registry.get_spec(...).default`.

The arithmetic lives in **pure, unit-tested free functions** (never in a
validator body, never in UI):

```
resolve_initial_energy(initial_energy, offspring_stake) -> float
    None -> offspring_stake; otherwise unchanged.

resolve_senescence_factor(senescence_factor, base_hazard, max_age) -> float
    None and base_hazard > 0 and max_age > 0 -> (1 / base_hazard) ** (1 / max_age)
    None otherwise                           -> 1.0
    not None                                 -> unchanged.
```

`save_config` uses `config.model_dump(mode="json")`, so resolving in
`mode="before"` means **the stored `config.yaml` holds a plain number** — hard
rule 8 (re-run an old config) is preserved and the auto rule can never
retroactively change an existing run.

New cross-field validators:

- **On `DynamicsConfig`**: `offspring_stake <= reproduction_threshold` (σ ≤ θ
  guarantees a parent survives its own reproduction). Plain message naming both
  values.
- **On `ExperimentConfig`** (it spans two sections, like
  `_check_matching_fits_population`): `carrying_capacity >= population.size` —
  otherwise generation 0 already exceeds capacity. Plain message.

`_check_matching_fits_population` (k ≤ N−1) **stays exactly as it is**: it
guards generation 0. It does not and cannot guard a generation where deaths have
shrunk N below k+1 — that is Task 4's job.

## Task 3 — `Agent` gains energy, age, and lineage (`pdsim/core/agent.py`)

Three new attributes with inert defaults, so the imitation path is untouched:

```
energy: float = 0.0
age: int = 0
parent_id: AgentId | None = None
```

Add them as optional keyword arguments to `__init__` with those defaults, and
document each in the class docstring. **Do not touch `reset_for_new_generation`,
`score`, `rounds_played`, `view_of`, `decide`, or `record_round`.**

**Per-opponent histories PERSIST across generations in economy mode.** A
surviving agent remembers every passport id it has ever played, for its whole
life. #31's rationale for clearing them — "under selection the neighbors'
strategies change, so a remembered relationship would be memory of a different
agent" — is **selection-specific and dissolves here**: nobody's strategy is
overwritten, ids are never reused, and agent 7 next generation IS the same agent
7. This matches the blessed precedent in `TournamentDynamics` (#34), where a
fixed cast accumulates histories across cycles and "GrimTrigger stays grim in
cycle 2 about a betrayal from cycle 1" is documented as *intended* direct
reciprocity, not an accident. An economy agent is a persistent creature; its
memory persists too.

This requires **splitting the reset** (see Task 5b step 8):

- **Score still resets every generation** — non-negotiable: step 3's energy
  update consumes that generation's `raw_score`.
- **Histories do not reset** for carried-forward agents. Newborns are fresh
  `Agent` objects and start empty by construction.

Add a score-only reset — e.g. `reset_score_for_new_generation()` — **beside**
`reset_for_new_generation()`. **Do not modify `reset_for_new_generation()`
itself**: `PopulationDynamics` and its byte-identity guarantee (principle 2)
depend on it exactly as it is.

Three consequences, all intended, all named in DECISIONS:

- **`HistoryView.round_number` becomes lifetime-cumulative** against a given
  opponent in economy mode. #22's "cumulative within one generation only" is now
  mode-dependent — amend its **scope**, do not overturn it. A strategy testing
  `round_number == 0` to detect a first meeting now detects a first meeting
  *ever* — once per run, not once per generation.
- **GrimTrigger becomes lifetime-grim.** A betrayal at generation 3 is still
  punished at generation 200. This is the largest behavioural consequence of
  persistence, and it is exactly #34's tournament semantics.
- **`Agent.rounds_played` becomes a lifetime count** in economy mode — see Task
  0a for the per-generation tally that must replace it there.

**The cost, named honestly.** `Agent.view_of` copies the visible history into
fresh tuples every round — the O(length²) hotspot the `Agent` docstring already
flags. Wiping histories bounded that at the match length; persistence unbounds
it. `memory_depth` is the existing bound (it caps what strategies see, so it caps
the copy). Task 10's readout warns rather than forbids.

## Task 4 — the variable-N `random_k` contract (`pdsim/core/matcher.py`)

In `RandomK.pairings`:

- **Delete the `ValueError` raise** for `k > len(agents) - 1`.
- **Clamp the draw**: `size=min(self._k, len(others))`, one draw per initiator,
  still `replace=False`, still in the order `agents` is given.

Rejected alternatives, for the docstring: **error** — a valid config must not
crash because the population got small mid-run; a metabolic filter is *supposed*
to be able to shrink a population, that is the science. **Skip** (initiate 0
matches when `N−1 < k`) — a discontinuous cliff: at `N−1 = k+1` you play k, one
death later you play 0, with no mechanism motivating the jump.

**Why the clamp is safe against the #57 seeded-history contract:** at every
N ≥ k+1 — the only regime the fixed-N engine could ever occupy —
`min(k, N−1) = k`, so the clamp is a **literal no-op** and every existing seeded
`random_k` run stays byte-identical. The new behaviour activates only in the
N < k+1 regime the old engine could never reach. This is not a breaking change
to an existing contract; it is a definition of previously-undefined territory.
Pin it with a regression test.

Verified corner behaviour (do not re-derive, but do test):

- **N = 2**: `others` has 1 entry, `size=min(k,1)=1` — each agent plays the one
  other.
- **N = 1**: `others` is empty, `size=min(k,0)=0`. `rng.choice(0, size=0,
  replace=False)` returns an empty array **without raising** and **consumes no
  RNG**. The lone survivor plays 0 matches, earns 0 payoff, still pays
  `basic_living_cost`, and dies at `e < 0` at the next boundary unless
  `capital_return_rate > 0` clears the bill. **This is the frozen, intended
  thermodynamics of "a population of one under a metabolic bill"** — not a bug.
- **N = 0**: extinction; the run ends (Task 7).

`RoundRobin` needs **no change**: `itertools.combinations` is already
set-size-agnostic. The only consequence of variable N is that income scales with
N under round-robin — the self-decalibration the calibration readout surfaces
(Task 10) and the explainer owns. That is a calibration fact, not a correctness
one.

## Task 5 — the economy boundary

### 5a — pure helpers: new module `pdsim/core/economy.py`

Headless (hard rule 4), no UI imports, every function pure and unit-tested.

```
energy_update(carried_in, raw_score, matches_played, dynamics) -> float
    carried_in * (1 + capital_return_rate)
      + raw_score
      - basic_living_cost
      - engagement_cost * matches_played

mortality_probability(age, dynamics) -> float
    if max_age > 0 and age >= max_age: 1.0
    else: min(1.0, base_hazard * senescence_factor ** age)

age_mortality_active(dynamics) -> bool
    base_hazard > 0 or senescence_factor != 1.0 or max_age > 0

admit_births(eligible, slots) -> list[Agent]        # the CAPACITY gate
    sort by (energy DESC, agent_id ASC); return the first `slots`.
    Deterministic and RNG-FREE — a deliberate choice over a random lottery,
    which would inject fresh RNG into the birth phase for no scientific gain.

place_offspring(population, parent) -> bool          # the STRUCTURAL gate
    well_mixed: append nothing, return True, always.
    Named NOW so M11 can swap in a neighbourhood-aware body without touching
    the birth loop. No speculative ABC (hard rule 6: M11 updates DESIGN first).

staggered_founder_ages(n, max_age) -> list[int]
    max_age > 0: [i % max_age for i in range(n)]; else [0] * n.
```

**Founder age staggering** is automatic, with no parameter, and applies only
when age-mortality is active **and** `max_age > 0`. A fixed-lifespan population
at a steady birth rate has a uniform age distribution in equilibrium, so
staggering starts the run at demographic steady state instead of a colony-ship
moment where the entire founding cohort dies at once at generation `max_age`.
(Synchronized cohort: a future option.)

### 5b — `EconomyDynamics` in `pdsim/core/dynamics.py`

A **new class beside** `PopulationDynamics`, not a branch inside it (Fork 2:
distinct paradigm; and it keeps `PopulationDynamics` byte-identical). It yields
the same `GenerationReport` type. It reuses `Match`, `build_matcher`, and
`StrategySwitchReproduction.offspring_strategy` unchanged. It **never**
constructs a SelectionRule or a ScoreAccounting.

Construction: build founders with `build_initial_population(config)` (unchanged),
then decorate them — `energy = initial_energy`, `parent_id = None`, ages from
`staggered_founder_ages(...)` when age-mortality is active. Own a monotonic
`self._next_id = len(founders)`.

**Invariant: `self._population` is ALWAYS in ascending `agent_id` order.** Sort
explicitly at the boundary rather than trusting insertion order. Deaths make ids
non-contiguous (id 5 dies; 4 and 6 remain), so "ascending id order over the
current living set" is **not** `0..N−1`. Any code that reaches for a list index
as a proxy for id silently corrupts the draw order the moment a death opens a
gap.

**`step()` — this IS the M10a step-4 RNG contract, extending #32:**

1. **Match phase** — unchanged (#23 per-round order). Feed the cooperation
   tally (#65) and the new per-agent `matches_played` tally (Task 0a).
2. **Build the `GenerationReport`** from the population **as it played**, before
   any death or birth: `composition`, raw `mean_scores`, `rounds_played`,
   `cooperation`. **Per-strategy fields keep their existing meaning** —
   `mean_scores` stays the raw PD score (it is what the calibration window is
   about, and it is comparable across modes); `rounds_played` stays
   per-strategy agent-rounds. Energy is **additive, not a replacement**.
3. **Energy update** — deterministic, every living agent:
   `e ← energy_update(e_carried_in, raw_score, matches_played[id], dynamics)`.
   This produces the single frozen snapshot deaths and births read.
4. **Mortality sub-phase** — **only if `age_mortality_active(dynamics)`**: one
   coin per living agent, in **ascending agent-id order**, `rng.random() <
   mortality_probability(age, dynamics)` → dies. **Exactly one coin per living
   agent, unconditionally, whenever age-mortality is active — including in the
   deterministic corners (p = 0.0 or p = 1.0).** The stream then depends only on
   the *active* flag and the population size, never on individual hazard values.
5. **Insolvency deaths** — deterministic: remove every agent with `e < 0`.
   **Strictly negative, not `e <= 0`**: an agent that just qualified and paid σ
   can land at exactly 0; under strict-negative it survives empty-handed to earn
   again, so reproduction is not suicidal at the margin.
6. **Births** — deterministic threshold + capacity admission:
   - `eligible` = survivors with `e >= θ`, in ascending id order.
   - `slots = max(0, carrying_capacity - len(survivors))`.
   - `admitted = admit_births(eligible, slots)` — **energy-priority order**.
   - **then re-sort `admitted` by `agent_id` ascending**, and for each parent in
     that order: `if place_offspring(population, parent):` pay
     `σ + reproduction_overhead`, assign `self._next_id` (post-increment),
     construct the child (`energy = σ`, `age = 0`, `parent_id = parent.agent_id`,
     empty per-opponent history), then take the μ-mutation draw via
     `offspring_strategy(parent.strategy, rng)`.
   - **One birth per agent per generation**, even if `e ≥ 2θ`. Consequence: the
     dynastic channel runs through *breeding frequency*, not offspring
     endowment.

   **TWO ORDERINGS, kept separate — the spec pins this.** Admission decides *the
   set* by energy-priority `(energy desc, id asc)`. Id-assignment and mutation
   then iterate *that set* in **parent-id order**, because that is the
   RNG-reproducibility contract. Conflating them (e.g. assigning ids in energy
   order) would silently change every seeded economy run.

   **Check placement → THEN pay σ. Never pay-then-place.** In M10a
   `place_offspring` never returns False, so it is invisible — but writing it
   backwards bequeaths M11 the exact bug where a blocked parent is charged for a
   child never born. Write the test now: stub a `place_offspring` returning
   False and assert σ is untouched. M11 inherits a guarantee, not a hope.
7. **Age increment** — survivors `age += 1`; newborns stay at 0.
8. **Reset — score only.** `reset_score_for_new_generation()` on every
   carried-forward agent (newborns are already at 0). **Per-opponent histories
   are NOT cleared** (Task 3). Never call `reset_for_new_generation()` here.
9. **Snapshot** — build `agents: tuple[AgentSnapshot, ...]` from the
   **post-boundary carried-forward population**: the exact set entering
   generation G+1, each with age-entering-next-generation and net energy carried
   forward — precisely what G+1's step-3 reads as `e_carried_in`. Attach it to
   the `GenerationReport` built in step 2 and return.

**Death-before-birth (frozen).** The cull frees room, then survivors breed into
it — an at-capacity, Moran-like regime. **This is a plain design preference, and
it deviates from Hammond–Axelrod**, whose period order is immigration →
interaction → reproduction → death (birth *before* death). In a steady cycle the
difference largely rotates out, but two real differences remain: in H-A a newborn
can die in the period it was born, and the first period differs. Do **not**
justify the order as "spatially correct for M11" — the canonical spatial model
does the opposite. Name the deviation honestly in DECISIONS. Rejected:
fully-simultaneous no-ordering (ambiguous at capacity).

**Snapshot grain — the known, accepted cost.** An agent that earned, bred, and
died of old age within the same boundary has its gross earnings absent from the
snapshot. Nothing essential is lost: those earnings still flow into that
generation's per-strategy `mean_score`, and its child's `parent_id` records the
reproduction. Only the exact energy-at-moment-of-reproduction is unrecoverable.
The alternative — snapshotting the pre-cull scored population — preserves that
detail but does not match `e_carried_in` and is the wrong grain for the energy
and age charts.

**Only RNG in the whole birth/death/mortality machinery:** mortality coins
(step 4, conditional) and mutation draws (step 6, conditional), both id-ordered.
With age-mortality off and μ = 0, the match phase is byte-identical to the
fixed-N engine. **Any change to this order is a breaking change → new DECISIONS
entry.**

## Task 6 — events (`pdsim/core/events.py`)

New frozen value type, beside the others:

```python
@dataclass(frozen=True, slots=True)
class AgentSnapshot:
    agent_id: AgentId
    parent_id: AgentId | None
    age: int
    energy: float
    strategy: str          # machine name
```

`GenerationFinished` gains **one** optional field:

```python
agents: tuple[AgentSnapshot, ...] = ()
```

Populated **only** in `energy_economy` mode; empty in imitation mode. Empty there
keeps imitation payloads byte-identical to today, which is what keeps the
schema-guard story clean (Task 9). `CycleFinished` gains nothing — a tournament
has no economy.

`GenerationReport` in `dynamics.py` gains the mirror field
`agents: tuple[AgentSnapshot, ...] = ()`, importing `AgentSnapshot` from
`events.py` (no cycle: `events` imports only from `game`).

**Rejected — explicit birth/death events.** Any id present at G but not G−1 was
born at G (`parent_id` names its parent); any id present at G−1 but not G died
during G. The snapshot sequence reconstructs the entire birth/death record by
diff. Adding them would duplicate truth (#47) and complicate the observer-only
granularity model (#35) for no gain, because in the synchronous model all births
and deaths happen at one atomic boundary. Explicit birth/death events belong to
**M10b**, where async event-time makes per-event ordering meaningful.

**Rejected — a population-size payload field.** `N(G) =
sum(composition.values())`, and `composition` is already in every
`GenerationFinished` (#47 raw-not-derived). Better: the existing stacked-area
composition chart **already is** the population-growth chart — its total height
grows, for free.

## Task 7 — the engine ends a run at extinction (`pdsim/core/engine.py`)

`_run_evolution` currently loops `for _ in range(config.dynamics.generations)`
and closes with `RunFinished(completed=config.dynamics.generations)` — a
hard-coded count that is **wrong the moment a run can end early**.

- Dispatch on `config.dynamics.reproduction_mode`: `PopulationDynamics` for
  `"imitation"`, `EconomyDynamics` for `"energy_economy"`. Tournament mode is
  untouched (`reproduction_mode` is ignored there — it joins
  `IGNORED_IN_TOURNAMENT`).
- Count generations actually played; pass that count to `RunFinished.completed`.
- After yielding a `GenerationFinished`, **break if the population is empty**
  (extinction). The run ends; this is a legitimate outcome, not an error.
- `_headline` in `pdsim/io/results.py` must handle an **empty final
  composition** ("population extinct at generation N") without raising.
- `RunFinished.composition` / `mean_scores` are then empty dicts. Confirm
  `RunTimeseries`, the run card, the charts, and the sweep metrics all survive
  an extinct run; fix what does not.

Guard the imitation path: `completed` must still equal
`config.dynamics.generations` for every imitation run (population never empties).

## Task 8 — `RunTimeseries` (`pdsim/core/timeseries.py`)

- Fold `event.agents` into a per-period accumulator (empty tuple → nothing
  recorded), exactly mirroring how `_fold_cooperation` handles schema-1 events
  with no cooperation data.
- Add a **derived** `population_size` series: `sum(composition.values())` per
  period. Derived, never stored (#47).
- Add derived per-strategy mean-energy and mean-age series computed from the
  snapshots, for the charts.

## Task 9 — persistence: `schema_version` 3 (`pdsim/io/results.py`)

A pure application of the #47/#65 pattern — invent nothing.

- `SCHEMA_VERSION = 3`. Update the module docstring's History line: `3 = M10a
  adds agents.parquet, total_agents_born, and population_final`.
- **New sibling table `agents.parquet`** — the filename the module docstring
  already reserves. Columns: `period`, `agent_id`, `parent_id`, `age`, `energy`,
  `strategy`. `parent_id` is a **nullable integer** (pandas `Int64`); founders
  are `<NA>`. **No `born_this_period` flag** — derivable by diff
  (raw-not-derived).
- Written **only** when snapshots exist. An `imitation` run under M10a code
  writes **no** `agents.parquet` and therefore `schema_version` **2** — the
  version number tracks the presence of per-agent data, which is the honest
  thing for it to track. Only `energy_economy` runs write 3.
- `timeseries.parquet` and `cooperation.parquet` are **untouched** — their
  per-strategy grain is unchanged. **Rejected: widening `timeseries.parquet`
  with energy columns** — it would write NaN-filled columns for every imitation
  run, which the "no empty columns today" rule (#47c) exists precisely to
  forbid. A separate sibling is the established shape.
- `summary.json` gains **`total_agents_born`** (the largest passport id ever
  issued — it drops out of the id contract for free) and **`population_final`**
  (the size of the last snapshot). Both are `None` for imitation runs. Both are
  derivable but belong in the summary as the natural headline numbers of a
  growth economy. Note that the existing `population_size` field is
  config-derived and therefore means **initial** size — leave it alone and say
  so in the docstring.
- **Loader compatibility, exactly per #65:** `load_run` accepts **1, 2, and 3**;
  rejects > 3 with the existing message. A schema-1 or schema-2 folder simply has
  no `agents.parquet` and renders without the energy/age/population views — no
  migration, no error, no empty columns. Read `agents.parquet` with the same
  "missing file → empty mapping" shape as `_read_cooperation`, group by period,
  and feed the snapshots back through `GenerationFinished` so every derived view
  is recomputed by the exact same code the live run used.

## Task 10 — the calibration readout

New **Streamlit-free** module `pdsim/ui/economy_helpers.py`, mirroring
`pdsim/ui/sweep_helpers.py` (the #38/#48 helper pattern). Pure config → numbers,
fully unit-tested, importable by non-UI callers.

This is close to load-bearing, not a nicety: app-first validation ("set up an
economy, observe growth") is impossible to do honestly if the person cannot see
where the survival window is.

```
calibration_report(config) -> CalibrationReport   # a frozen dataclass
```

Derived straight from the config:

- **expected matches per agent** — `N − 1` under round_robin; `≈ 2k` under
  random_k (each agent initiates k and is drawn ≈ k times).
- **expected rounds per match** — `rounds_per_match` (fixed), or `1 / (1 − w)`
  (continuation mode).
- **all-C income** = matches × rounds × R. **all-D income** = matches × rounds
  × P. **total cost** at that participation = `basic_living_cost +
  engagement_cost × matches`.
- **the verdict line**: "a cooperator nets +X per generation, a defector nets
  −Y per generation".
- **the window**: `all-D income ≤ L < all-C income`, with an explicit
  in-window / out-of-window verdict.
- when `capital_return_rate > 0`: **escape velocity `e* = total_cost /
  capital_return_rate`** — above `e*` an agent is self-sustaining regardless of
  behaviour, pays its bills from returns on capital, and clears θ forever. It is
  immune to the metabolic filter the whole experiment rests on. Surface it
  whenever r > 0.
- when `max_age > 0`: **generations-to-θ** from `initial_energy` at the
  cooperator's net rate, compared against lifetime; **expected offspring count**;
  and the **effective-max-age** note.
- **Warn, don't forbid**: if an explicit `senescence_factor` makes the effective
  maximum age fall below `max_age`, allow it and surface a soft note
  ("effective maximum age ≈ 15, below max_age 20"). Someone may legitimately
  want a population where nobody reaches the cap.
- **The memory-growth note** — the second warn-don't-forbid, same idiom.
  Histories persist (Task 3), and `view_of` copies the whole visible history
  every round (the documented O(length²) hotspot), so the copy cost now grows
  with the *relationship*, not the match.

  Under **round_robin** every pair meets every generation, so a history reaches
  `rounds_per_match × generations` moves and per-match cost grows **linearly with
  generation** — total cost **quadratic in run length**. Worked, at N=100, 50
  rounds: per-match copy cost is ≈ 2 × 50 × 50(G−1) ≈ 5000(G−1) element-copies at
  generation G, against the ≈ 2550 within-match ramp (50×51/2 × 2) at generation
  1 — **≈ 390× slower per match at G = 200**, ≈ 200× over the run. Under
  **random_k** a specific opponent recurs with probability ≈ k/(N−1) per
  generation, histories stay short, and the cliff barely bites.

  So: when `reproduction_mode == "energy_economy"` **and**
  `population.memory_depth is None`, report the projected worst-case history
  length (`rounds_per_match × generations` under round_robin) and name
  `memory_depth` as the bound. Do **not** forbid it — 30 generations under
  random_k needs no bound; 500 under round_robin very much does.

Under **round_robin, income scales with N**, so any fixed L decalibrates itself
as the population grows — the window moves. Under **random_k the interaction
budget is bounded (≈ 2k) independent of N**, so the window stays put. The
readout must state which regime it is in; the explainer owns the argument.

## Task 11 — the app (`pdsim/ui/app.py`, `pdsim/ui/helpers.py`)

**Greying (#34, in `helpers.greying`)** — extend, do not restructure:

- add `dynamics.reproduction_mode` to `IGNORED_IN_TOURNAMENT`;
- define `_ECONOMY_PARAMS` (the eleven economy knobs) and `_IMITATION_PARAMS`
  (the five selection keys + the three accounting keys);
- when `dynamics.reproduction_mode == "energy_economy"`: grey every
  `_IMITATION_PARAMS` key — "NOTE: this parameter exists but is IGNORED in the
  energy economy — nobody copies anyone; differential survival *is* the
  selection.";
- when `dynamics.reproduction_mode == "imitation"`: grey every
  `_ECONOMY_PARAMS` key — "NOTE: this parameter is only read in the energy
  economy — IGNORED under imitation dynamics.";
- the coarse `reproduction_mode` check runs **before** the existing
  `_RULE_PARAMS` / `_ACCOUNTING_PARAMS` checks.

**The Economy panel**: render the `CalibrationReport` in the Dynamics expander,
directly under the economy widgets, and **only** when
`reproduction_mode == "energy_economy"`. Verdict line first, then the window,
then the conditional readouts.

**The (?) checklist — §12's spec rule, verifiable not aspirational.** Registry
parameters get their tooltip free. These do **not**, and each needs an inline
(?) whose text is drawn from a **single described source** so app text and docs
cannot drift. Tick every box:

- [ ] enum value `imitation`
- [ ] enum value `energy_economy`
- [ ] concept: **energy** (a stock, not a score)
- [ ] concept: **admission** (who gets in when the population is at capacity)
- [ ] concept: **estate destruction on death** (the 100% inheritance-tax corner)
- [ ] concept: **passport id / parent_id** (ids are never reused)
- [ ] readout: **expected matches per agent**
- [ ] readout: **all-C income** and **all-D income**
- [ ] readout: **the window**
- [ ] readout: **escape velocity `e*`**
- [ ] readout: **generations-to-θ** and **expected offspring count**
- [ ] readout: **effective max age**

## Task 12 — charts (`pdsim/viz/charts.py`)

Three new figures, all economy-only, all rendered only when snapshots exist, all
matching the existing `_line_chart` / `strategy_colors` house style:

- `population_chart(timeseries)` — total N per period, with a dashed
  `carrying_capacity` reference line. (The stacked composition chart already
  shows growth; this makes N vs K legible, which is the point of the K story.)
- `mean_energy_chart(timeseries)` — mean energy per strategy per period.
- `mean_age_chart(timeseries)` — mean age per strategy per period.

Add them to `export_run_charts` when snapshots exist. Render them in the live
run lab and the results browser next to the existing charts. A schema-1/2 run
shows none of them and must not error.

## Task 13 — the scenario (`pdsim/config/scenarios.py`)

One new scenario, `the_growth_economy`, tuned so the default *actually grows* —
the numbers below are the worked calibration, not assertions.

```
seed: 42
population: size 40, composition {tit_for_tat: 20, always_defect: 20}
matching: matcher random_k, opponents_per_agent 5
match: length_mode fixed, rounds_per_match 10
dynamics:
  generations 60
  reproduction_mode energy_economy
  reproduction_threshold 500.0
  offspring_stake 400.0
  basic_living_cost 200.0
  carrying_capacity 200
  mutation_rate 0.0
```

**The arithmetic** (game defaults T=5, R=3, P=1, S=0; `initial_energy` resolves
to σ = 400):

- expected matches per agent = 2k = **10**; expected rounds per agent =
  2k × r = **100**.
- all-C income = 100 × 3 = **300**. all-D income = 100 × 1 = **100**.
- window: `100 ≤ L < 300`; midpoint **L = 200** ← `basic_living_cost`.
- a cooperator nets **+100**/generation; a defector nets **−100**/generation.
- **Founder cooperator trace** (all-C): e₀ = 400 → gen 1: 400 + 300 − 200 = 500
  ≥ θ → breeds, pays σ → 100 (child born at 400). Then 200 → 300 → 400 → 500 at
  gen 5 → breeds → 100. **Steady breeding interval = σ / net = 400 / 100 = 4
  generations.**
- **Founder defector trace** (all-D): e₀ = 400 → 300 → 200 → 100 → 0 → **−100 at
  generation 5 → dead. The all-D population goes extinct at generation 5.**

`description` (novice-friendly, "what question does this explore?"): what
happens when survival costs energy and playing earns it — cooperators generate
more energy per interaction than defectors do, so the same bill that cooperators
shrug off can drive defectors extinct.

`things_to_try`: set `basic_living_cost` to 320 (above all-C income) and
*everyone* dies — the window is real; set it to 80 (below all-D income) and
even defectors grow, because the filter is switched off; switch the composition
to 40 `always_defect` and watch the population die at generation 5; set
`max_age` to 20 and watch the mortality curve; set `capital_return_rate` to 0.05
and watch escape velocity appear in the readout.

## Task 14 — re-run the bench under the economy

M10a obligation from the vectorization verdict: variable N plus
energy/mortality/birth bookkeeping change the cost profile. Re-run
`python -m pdsim.bench` under `energy_economy` at a couple of N values and
report the numbers against the validated cost model
`s/gen ≈ 7.5 µs × N × k × rounds`. M9b-Task-5 discipline; **#65's noise warning
applies — repeat before trusting a delta.** Bench output is
environment-specific and is **never committed**. If the profile has changed
materially, log it in DECISIONS; the vectorization trigger stays **M18,
review-at** unless the machine contradicts the extrapolation.

## Task 15 — docs

- **`docs/DESIGN.md`**: a new §2.10 (or the right neighbour) describing the
  economy paradigm, the ledger, and the M10a boundary sequence; §4 gains
  `AgentSnapshot` and the `GenerationFinished.agents` field; §8 gains
  `agents.parquet` and `schema_version` 3. **Correct §3.1**: its "N≥1000 → too
  slow" is true only for **round_robin at 50 rounds** — state the envelope *per
  matcher*, cite the cost model, and note that large-N is a headless/sweep
  product while live visualisation stays in the low hundreds (#10 — a rendering
  limit, not an engine limit). Update the §6 cross-references to the new
  milestone numbers.
- **`docs/ROADMAP.md`**: rewrite to the new spine, and add a top **"Renumbering
  note"** section reproducing the table below and pointing at the DECISIONS
  entry.
- **`CLAUDE.md`**: update the *Current phase* line to the new spine.
- **`docs/PARAMETERS.md`**: regenerate via `python -m pdsim.gendocs`.
- **`docs/explainers/M10-growth-economy-explainer.md`**: the companion explainer
  arrives as a separate prompt — create the file only if that prompt has already
  landed; otherwise leave the spec's pointer dangling and say so in your report.

**The renumbering table** (execution order = numeric order, no gaps):

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

Spine: **M10 → M11 → M12 → M13 → M14 → M15 → M16 → M17 → M18.** The old #58
M12-before-M11 "deliberate swap" **dissolves** — the numbers now match the
order. Tags keeps its M12 label (this spares cross-reference churn). Population
structure is placed *before* the sweep browser by **#75's own logic**: the
browser is a read-only view over run data, and structure changes what run data
exists, so it is built after structure and is structure-aware from birth.

## Validation

APP-FIRST (#42/#61). With the venv active (`.venv\Scripts\Activate.ps1`), launch
`streamlit run pdsim/ui/app.py`.

1. **The economy grows.** Load the **The Growth Economy** scenario. Before
   running, read the **Economy panel** in the Dynamics expander: it must show
   ≈10 matches/agent, all-C income **300**, all-D income **100**, the window
   **100 ≤ L < 300** with L = 200 **inside** it, and the verdict "a cooperator
   nets +100 per generation, a defector nets −100 per generation". Run it. The
   composition chart's total height **rises** from 40 and flattens at the
   `carrying_capacity` line of **200**; the new **population chart** shows N
   climbing to K and plateauing against the dashed K line; Always Defect is
   squeezed out. The run card reports `total_agents_born` and
   `population_final = 200`.
2. **The window is real.** Same scenario; set **Basic living cost** to **320**.
   The panel's verdict flips to "a cooperator nets −20 per generation" and the
   window line reports L **above** the window. Run it: the population **dies
   out**, the run **ends early** at extinction, and the run card says so rather
   than erroring. Then set it to **80**: the panel reports L **below** the
   window, and both strategies grow — the filter is switched off.
3. **Defectors starve.** Same scenario; set the composition to **40 Always
   Defect**. Run it: the population is **extinct at generation 5**, exactly the
   trace in Task 13.
4. **The selection family greys out.** With **Reproduction mode** =
   `energy_economy`, confirm Selection rule, β, and Score accounting are all
   **greyed with an explanatory note, never hidden** (#34). Switch to
   `imitation`: the economy knobs grey instead, and the Economy panel
   disappears. Hover the (?) on **Reproduction mode** and confirm **both** enum
   values are explained.
5. **Mortality.** Same scenario; set **Max age** to **20**, leave
   **Senescence factor** blank, and set **Base hazard** to **0.01**. The panel
   reports the resolved factor ≈ **1.2589** and a generations-to-θ line. Run it:
   the **mean age chart** appears and settles rather than sawtoothing (founder
   staggering); the population still reaches K. Now type **1.6** into Senescence
   factor: the panel shows the soft **effective-max-age** note and the run is
   still allowed.
6. **Escape velocity.** Set **Capital return rate** to **0.05**: the panel gains
   an escape-velocity line (`e* = 200 / 0.05 = 4000`). Run it and watch the
   **mean energy chart** — the rentier threshold is visible as runaway
   accumulation.
7. **Reproducibility and the schema guard.** Re-run scenario 1 — byte-identical
   charts. Open the run folder: it holds **`agents.parquet`** and
   `summary.json` with **`schema_version: 3`**. In the **Results browser**, open
   an **old pre-M10a run**: it loads fine, renders without the energy / age /
   population charts, and does not error (#65 backward compatibility). Run any
   **imitation** scenario (e.g. **Reciprocity Takes Over**) under M10a code: it
   writes **no** `agents.parquet` and `schema_version: 2`, and its trajectory is
   **unchanged** from before this milestone.
8. **Config validation.** Set **Offspring stake** above **Reproduction
   threshold**: a plain-sentence validation message names both values and the
   run is blocked. Set **Carrying capacity** below the population size: likewise.
9. **Memory persists across generations.** Same scenario; set the composition to
   **20 Grim Trigger / 20 Always Defect**, **Matching scheme** to `round_robin`,
   **Carrying capacity** to **40**, and **Generations** to **5**. (K = N means
   `slots = 0`, so no births — the population is frozen at the 40 founders and the
   observable is exact rather than diluted by newborns opening with C.) The
   Economy panel shows the **memory-growth note** naming `memory_depth`. Run it
   and read the **cooperation chart**: Grim Trigger's cooperation rate against
   Always Defect is **≈ 0.1 in generation 1** — it opens with C once per 10-round
   match, gets defected on, and defects for the remaining 9 rounds — and **≈ 0.0
   from generation 2 onward**, because the grudge survived the boundary. Now
   switch **Reproduction mode** to `imitation`: the rate returns to ≈ 0.1 *every*
   generation, because the imitation path still clears histories (#31,
   unchanged). That contrast is the whole decision, visible in one chart.

CLI validation is legitimate only for the inherently headless obligation:
`python -m pdsim.bench` (Task 14).

Automated tests complement — never substitute for — the above:

- `resolve_initial_energy` / `resolve_senescence_factor` worked examples,
  including the exact `base_hazard = 0.01, max_age = 20 → 1.2589…` case, both
  `None` branches, and the explicit-override passthrough; the resolved value is
  what `save_config` writes.
- `energy_update`, `mortality_probability`, `age_mortality_active`,
  `staggered_founder_ages` — decision-table style.
- `admit_births`: energy-priority order, the `(energy desc, id asc)` tie-break,
  `slots = 0`, `slots > len(eligible)`.
- **`place_offspring` returning False never charges σ** (stub it; M11's
  inherited guarantee).
- **The two orderings are distinct**: a case where energy order ≠ parent-id
  order proves ids are assigned in id order, not energy order.
- **The `random_k` clamp is a no-op at N ≥ k+1** — byte-identical draws vs. the
  pre-clamp code; plus the N=2, N=1 (zero-size draw, no RNG consumed), and N=0
  corners.
- **A run with a mid-run death reproduces byte-for-byte** (the golden test for
  id-ordered iteration over a non-contiguous id set).
- **Histories persist in economy mode**: an agent meeting the same passport id in
  generations 1 and 2 sees a generation-2 `round_number` that *includes*
  generation 1's rounds; GrimTrigger punishes at generation 2 a betrayal from
  generation 1. Plus the mirror: `PopulationDynamics` still clears histories every
  generation, unchanged.
- **`rounds_played` is per-generation, not lifetime** — for an agent alive
  several generations, `GenerationReport.rounds_played` reports this generation
  only. This is the silent-decay trap from Task 0a; it fails loudly here or
  nowhere.
- **Newborns start with empty histories** and no inherited relationships.
- **The imitation path is byte-identical** to its pre-M10a seeded trajectory,
  and still writes `schema_version` 2 with no `agents.parquet`.
- Extinction: the run ends early, `RunFinished.completed` is the true count,
  `_headline` survives an empty composition, the run card and sweep metrics
  survive an extinct run.
- Schema guard: a schema-3 folder round-trips; schema 1 and 2 still load;
  schema 4 is rejected.
- σ ≤ θ and K ≥ population.size validators; `calibration_report` worked
  examples for both matchers, both length modes, and the r > 0 / max_age > 0
  branches.
- The existing golden validation tests (DESIGN §7) stay green.
