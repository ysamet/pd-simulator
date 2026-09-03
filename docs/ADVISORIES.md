# Advisories backlog

Requested in-flight warnings for parameter combinations that produce known
artifacts. **Nothing is implemented directly from this file** — it is a queue.
A milestone picks up a batch.

An advisory is a derived readout whose output is a warning rather than a number,
built on the same predicate-table pattern as M11a's greying map: a list of
rules, each a pure function of registry values, evaluated in one place. No new
machinery is required.

**Mechanism ownership: M11b**, alongside the parameter-panel redesign — where a
warning appears is a disclosure question, so the two surfaces are designed
together rather than one retrofitted into the other.

## Fields

| Field | Meaning |
|---|---|
| Trigger | The condition, as a calculation over registry values |
| Message | The text the user sees |
| Severity | `info`, `caution`, or `blocking` |
| Surface | Where in the app it appears |
| Owner | The milestone that implements it |

## Queue

### A1 — Living cost outside the survival window

- **Trigger:** `basic_living_cost` at or below all-D income, or at or above all-C income (both bounds INCLUSIVE — DECISIONS #176 R1: at L exactly equal to the all-D income a defector nets zero and never starves), where those are computed from the payoffs, rounds per match, and matches per agent
- **Message:** The metabolic filter is switched off — at or below the all-defector income, defectors never starve; at or above the all-cooperator income, even a population of pure cooperators cannot pay its bills.
- **Severity:** caution
- **Surface:** Economy panel, beside the existing calibration readout
- **Owner:** M11b

Trigger and message amended per DECISIONS #176 R1 (2026-08-24), implemented in M11b Phase D; the printed calibration window's lower bound became strict in the same change.

### A2 — Income-multiplying parameter changed without recalibration

- **Trigger:** any change (relative to the LOADED scenario's values — DECISIONS #176 R5) to `matching.matcher`, `matching.opponents_per_agent`, `match.rounds_per_match`, `match.continuation_probability`, `structure.neighbourhood_shape`, `structure.kind`, `matching.spatial_interaction`, `matching.encounter_mode`, or `structure.interaction_radius` while the economy is active — evolution mode AND ((synchronous AND `reproduction_mode = energy_economy`) OR (asynchronous AND `async_population = variable_n`)) (DECISIONS #176 R4)
- **Message:** This change rescales every agent's income (it may raise or lower it). Recompute the survival window before trusting the living cost.
- **Severity:** caution
- **Surface:** inline at the changed widget
- **Owner:** M11b

Trigger list amended per DECISIONS #170 (2026-08-17): `movement.rate` and `interaction_decay` deliberately excluded — see the entry for reasons. Gate amended per DECISIONS #176 R4 (2026-08-24), implemented in M11b Phase D; the radius trigger's key corrected in the same edit to `structure.interaction_radius` — the parameter's REGISTERED key (it renders in the Structure section); #170's `matching.interaction_radius` named the same parameter by its owning concept, not its registry key (a Rule 7 report in #177). Message reworded per DECISIONS #178 R8 (2026-09-01, implemented in M11b Phase E1): the old "multiplies every agent's income" implied income only ever goes up — several triggers can lower it — so the message now says "rescales (it may raise or lower it)".

### A3 — Spatial interaction with k at or above the neighbourhood size

- **Trigger:** the engine's ACTUAL spatial gate — evolution mode AND `structure.kind = lattice` AND `matching.spatial_interaction` on (DECISIONS #176 R7, the #137(b)/#141(c) predicate; never the toggle alone, which is false under `well_mixed` or tournament) — AND `opponents_per_agent` ≥ the radius-aware reach size at (shape, `interaction_radius`) (DECISIONS #176 R6: von Neumann 2r(r+1), Moore (2r+1)² − 1, blank radius → site count − 1)
- **Message:** Every agent plays all its neighbours and is played by all of them, so matches per agent is roughly twice the degree — income is doubled relative to a naive reading. (Mode-conditional per #166/#175: under `per_pair` each pair meets once, so matches per agent roughly equals the degree; under the asynchronous clock always the per-initiator arithmetic, phrased as expected — #176 R3.)
- **Severity:** info
- **Surface:** beside the spatial interaction toggle
- **Owner:** M11b

Gate and degree amended per DECISIONS #176 R6/R7 (2026-08-24), implemented in M11b Phase D.

### A4 — Birth-death updating with a cooperation-focused roster

- **Trigger:** `moran_rule = birth_death` (or `random` with a birth-death weight above 0) AND the roster contains both unconditional cooperators and unconditional defectors AND `structure.kind = lattice`
- **Message:** Under birth-death updating, selection never favours cooperators at any benefit-to-cost ratio (Ohtsuki et al. 2006, Supplementary Information §3). Cooperation losing here is the correct result, not a calibration failure. Use death-birth to investigate spatial reciprocity.
- **Severity:** caution
- **Surface:** beside the Moran rule selector
- **Owner:** M12

### A5 — Payoff scale changed without a selection-intensity change

- **Trigger:** `reproduction_mode = imitation` AND `selection_rule = fermi` AND the payoff vector has been scaled by a factor since the scenario default, with `selection_beta` unchanged
- **Message:** Multiplying all payoffs by a factor is equivalent to multiplying the selection intensity by the same factor. Divide beta by that factor to preserve the original dynamics.
- **Severity:** info
- **Surface:** beside the selection intensity widget
- **Owner:** M12

## Not an advisory

**Status: DISCHARGED 2026-08-06 (M11a Phase C, DECISIONS #129).** The
validator now checks the sum, the message names all three quantities, and no
shipped scenario or fixture violated the tightened rule. Kept below for the
record only.

**Reproduction threshold below stake plus overhead.** This is a hard invariant
with a documented guarantee attached — the parent-survives-its-own-reproduction
property — not a judgement call. The existing validator checks
`offspring_stake <= reproduction_threshold` but the parent pays stake PLUS
overhead, so with overhead 150, stake 400 and threshold 500 a parent at exactly
threshold ends at −50 and dies at the FOLLOWING boundary (insolvency is checked
before births). **This is a validation fix, to be made when the validation
module is next touched: the check should be
`offspring_stake + reproduction_overhead <= reproduction_threshold`.**
