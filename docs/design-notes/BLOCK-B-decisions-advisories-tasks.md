> **HOW TO USE THIS FILE.** Everything below the horizontal rule is a single
> prompt for Claude Code. Copy it as *markdown source*, not from a rendered
> preview.
>
> **Send this only after Block A2 has confirmed** the guide file is complete.

---

# PROMPT FOR CLAUDE CODE — BLOCK B of 3

This prompt makes five changes. Do not commit any of them.

Read `DECISIONS.md` first to confirm the next available entry number. The design layer believes the last entry is **#112**; if it is not, use the actual next numbers and report the discrepancy.

---

## Change 1 — Three `DECISIONS.md` entries

Append these in order, renumbering if #112 was not the last entry.

**#113 — A standalone explainer with no companion specification, and the naming that follows.** `docs/explainers/calibration-guide.md` ships without a paired spec. The companion-explainer rule assumes each explainer documents something a milestone built; this one documents behaviour that already exists across M9 through M11a, so there is nothing to specify and nothing to freeze. Two consequences recorded so a later reader does not conclude a spec was lost. First, the filename drops the milestone prefix that the explainer convention assumes and uses `calibration-guide.md` rather than a name ending `-explainer.md` — it sits in `docs/explainers/` but is a standing reference rather than a milestone companion, and the name says so. Second, this establishes the precedent for future standalone documents: a cross-cutting reference gets a descriptive filename, no spec, and a DECISIONS entry noting the deviation. Alternative rejected: writing a retrospective spec purely to satisfy the pairing rule, which would produce a document with no frozen intent, no validation section and no implementation to record — a ritual artifact rather than a record.

**#114 — VT-3's second-order claim overstates what the arithmetic supports; softened in the guide, and Phase B will measure the open half.** The M11a spec states that because the `fixed_n` breeder draw reads accumulated energy, relative differences widen as a run proceeds and effective selection strengthens over time. The first half does not follow from the shift idiom. Under `w_i = e_i − min(e)`, if agent energies diverge linearly at rates `r_i`, then `w_i(t) = (r_i − r_min) × t`, and the draw probability `w_i / Σw` has `t` in both numerator and denominator — it cancels. Subtracting the poorest normalises steady divergence away entirely. What IS demonstrable and ships in the guide: (a) selection begins at exactly zero, because at run start every agent holds identical energy, every shifted weight is zero, the uniform fallback fires, and the draw is neutral with no fitness content — so selection strengthens *from nothing*, which is a real effect but a different one; and (b) the draw partly selects for AGE rather than strategy, because an incumbent has had longer to accumulate than a newborn, and at the textbook `offspring_stake = 0` a newborn's weight sits at the bottom and it effectively cannot breed until it accumulates. Whether the spread keeps widening after divergence is established requires super-linear growth in the spread, which is plausible — richer agents breed more, and the M11a multiply-fork compounds distance weight with fitness — but is an empirical question, not an arithmetic one. **Phase B task added: log the shifted-weight spread at three points in a `fixed_n` run and report whether it grows faster than linearly.** The spec text is frozen and is NOT edited; this entry is the deviation record per the standing rule. The `donation_game_threshold` scenario text uses the softened wording. Alternative rejected: repeating the spec's wording in the guide, which would put a claim that fails five lines of algebra into user-facing scenario text.

**#115 — The flagship gains a third explicit override: `payoff_sucker = −1`.** #111(c) recorded two overrides for `spatial_reciprocity` — `neighbourhood_shape = von_neumann` and `payoff_punishment = 0`. With punishment overridden to 0 and sucker left at its registry default of 0, the configuration has punishment = sucker, which fails the strict `T > R > P > S` ordering that `game.enforce_pd_ordering` enforces by default. Three resolutions existed: also disable the ordering validator; override the sucker payoff to a negative value; or rely on the validator being lenient. DECIDED: override `payoff_sucker = −1`, giving T = 5, R = 3, P = 0, S = −1. Reasons. It keeps the scenario legal under the app's own rules, so nobody loading it meets a validation error or inherits a scenario exempt from checking. It makes the sucker payoff carry meaning rather than being a silent zero: a cooperator at a cluster edge now actively loses energy per defector neighbour, which sharpens the pressure to cluster — the mechanism the scenario exists to show. And it does not disturb #111's conceptual guard, because the matrix remains non-additive: T − R = 2 against P − S = 1, so the flagship is still emphatically not a donation game and its story is still ecological rather than Ohtsuki's. Alternative rejected: disabling the ordering validator for the flagship, which is defensible — punishment = sucker = 0 is the recognised "weak Prisoner's Dilemma" of the spatial-games literature (Nowak & May 1992; named and characterised by Szabó & Fáth 2007) — but buys a tidier matrix at the price of switching off a safety rail on the project's headline scenario, so that anything the user subsequently edits is unchecked. Second alternative rejected: relying on the validator being lenient, which is a fact about the code rather than a decision, and a rule documented as strict that behaves leniently is a defect waiting to be fixed out from under the scenario. **A verification task confirms which behaviour the validator actually has (see Change 5).**

---

## Change 2 — New file `docs/ADVISORIES.md`

Create it with exactly this content:

```markdown
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
```

---

## Change 3 — `ROADMAP.md`

Add to the M11b entry, in whatever form matches the file's existing structure:

> **New parameter: `matching.encounter_mode`** ∈ {`per_initiator`, `per_pair`}, default `per_initiator` (today's behaviour). Under the current no-deduplication rule inherited from `RandomK`, an unordered pair of neighbours meets **twice** per period, because each of the two independently initiates a match. That is an artefact of indexing matches by initiator, not a modelling claim: an encounter is an event that happens to a *pair*. `per_pair` deduplicates. Note that two matches of R rounds is not equivalent to one match of 2R rounds — reciprocal strategies reopen at each match boundary, and under continuation mode the length is drawn per match. Deferred from M11a deliberately: the M11a spec is frozen and Phase A is committed, and changing pairing semantics would alter RNG consumption and invalidate the golden masters Phase C depends on. Requires its own spec and a DECISIONS entry when picked up.

Also add to M11b: **the advisory mechanism plus advisories A1, A2 and A3 from `docs/ADVISORIES.md`.** And add to M12: **advisories A4 and A5.**

---

## Change 4 — `CLAUDE.md`: two delivery constraints

Add to whatever section covers how prompts arrive:

> **Prompt size limit.** A single prompt must stay under 50,000 characters. The
> harness truncates silently past that, marking the cut but leaving the
> receiving session with no way to recover the tail. Deliverables that would
> exceed the limit are split into numbered sub-prompts at a natural section
> boundary, each self-contained, each with its own `Action required:` line, and
> each stating explicitly where it stops so the receiving session knows the file
> is deliberately incomplete.
>
> **Markdown must arrive as source, not as rendered text.** Prompts containing
> markdown are delivered as `.md` files or inside fenced code blocks, never as
> text copied from a rendered chat view. Copying from a rendered view strips
> headings and emphasis, converts tables to tab-separated lines, and silently
> corrupts literal asterisks — an `e*` becomes an italic marker and the asterisk
> vanishes. If a received prompt shows any of these symptoms, report it and
> request re-delivery rather than writing the damaged text.

---

## Change 5 — Two verification tasks

Add these to the M11a spec's verification-task section, or to `WIP.md` if the spec section is frozen — report which you chose and why.

**VT-5 — `threshold_cloning` shift-dependence.** Read-only, no code change. In the `threshold_cloning` selection rule, is the survival bar computed as `multiplier × generation_mean`? **If yes:** the calibration guide's §3.5 table ships as written — the rule is shift-invariant only at the default multiplier of 1.0, because under a shift `a` the bar moves by `m × a` while individual scores move by `a`, leaving a relative displacement of `(m − 1) × a`. **If the implementation differs:** report the actual computation; the design layer rewrites that table row before the guide is considered final.

**VT-6 — Joint flagship verification.** Two questions, one report.

*(a) Payoff ordering validator strictness.* Does `game.enforce_pd_ordering` compare punishment against sucker strictly (`P > S`) or leniently (`P >= S`)? **If strict:** #115's override of `payoff_sucker = −1` is required and ships as decided. **If lenient:** report it — the documentation describes the rule as strict, and a rule documented one way and implemented another is a defect to be logged, not a fact to build a scenario on. #115's override stands either way.

*(b) Matches per agent under spatial interaction.* Confirm empirically — a short instrumented run is fine — how many matches each agent actually plays per generation when `spatial_interaction` is on, `structure.kind = lattice`, `neighbourhood_shape = von_neumann`, boundary `torus`, and `opponents_per_agent` ≥ 4. **Expected: ≈ 8**, because Design 6 inherits `RandomK`'s no-deduplication behaviour, so each agent initiates 4 and is drawn by 4. **If ≈ 8 confirmed:** the flagship's `basic_living_cost` must be calibrated against a cluster-interior cooperator income of ≈ 8R, not 4R, and the Moore counterfactual in the scenario's things-to-try is a four-fold income change rather than a two-fold one — both must be checked against the scenario's actual living cost before the flagship is trusted. **If ≈ 4:** the engine deduplicates after all, and Design 6's text plus the calibration guide's §4.2 both need correcting. Report the measured number either way.

---

## Reporting

When all five changes are made, report: the files changed, the DECISIONS entry numbers used, where VT-5 and VT-6 were placed, and a suggested commit message.

Do not commit.

**Action required:** Make Changes 1 through 5 exactly as specified, then report the files changed, the DECISIONS entry numbers used, the placement of VT-5 and VT-6, and a suggested commit message — without committing.
