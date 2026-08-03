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

- **Trigger:** `basic_living_cost` below all-D income, or at/above all-C income, where those are computed from the payoffs, rounds per match, and matches per agent
- **Message:** The metabolic filter is switched off — below the window even defectors pay their bills; at or above it, even a population of pure cooperators cannot.
- **Severity:** caution
- **Surface:** Economy panel, beside the existing calibration readout
- **Owner:** M11b

### A2 — Income-multiplying parameter changed without recalibration

- **Trigger:** any change to `matching.matcher`, `matching.opponents_per_agent`, `match.rounds_per_match`, `match.continuation_probability`, `structure.neighbourhood_shape`, or `structure.kind` while `reproduction_mode = energy_economy`
- **Message:** This change multiplies every agent's income. Recompute the survival window before trusting the living cost.
- **Severity:** caution
- **Surface:** inline at the changed widget
- **Owner:** M11b

### A3 — Spatial interaction with k at or above the neighbourhood size

- **Trigger:** `matching.spatial_interaction` is on AND `opponents_per_agent` ≥ the neighbourhood degree
- **Message:** Every agent plays all its neighbours and is played by all of them, so matches per agent is roughly twice the degree — income is doubled relative to a naive reading.
- **Severity:** info
- **Surface:** beside the spatial interaction toggle
- **Owner:** M11b

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

**Reproduction threshold below stake plus overhead.** This is a hard invariant
with a documented guarantee attached — the parent-survives-its-own-reproduction
property — not a judgement call. The existing validator checks
`offspring_stake <= reproduction_threshold` but the parent pays stake PLUS
overhead, so with overhead 150, stake 400 and threshold 500 a parent at exactly
threshold ends at −50 and dies at the FOLLOWING boundary (insolvency is checked
before births). **This is a validation fix, to be made when the validation
module is next touched: the check should be
`offspring_stake + reproduction_overhead <= reproduction_threshold`.**
