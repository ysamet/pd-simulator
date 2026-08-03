# Calibration Guide — Design Session Handoff Brief

> **Status: AUTHORITATIVE for the drafting of `docs/explainers/calibration-guide.md`.**
> This document supersedes memory. Everything a fresh instance needs to produce
> Block A (the guide text) and Block B (decisions, advisories file, verification
> tasks) is recorded here. Written 2026-08-02.

---

## 0. What this session was for, and where it got to

**Purpose.** Design a standalone practical guide for setting the four Prisoner's
Dilemma payoffs (temptation, reward, punishment, sucker) plus the seven
energy-ledger quantities (basic living cost, reproduction threshold, offspring
stake, initial energy, engagement cost, reproduction overhead, capital return
rate) when modelling real-life scenarios in pdsim. Not tied to a milestone; no
companion spec.

**Deliverables, in order:**
1. Agreed outline — **DONE** (§6 below).
2. Verified citation list — **DONE** (§4 below; all verified in-session
   2026-08-02 with URLs recorded so re-verification is cheap).
3. Two cut-and-paste Claude Code prompt blocks — **Block A and Block B, NOT YET
   WRITTEN.** This is the remaining work.

**Project knowledge currency at session start:** DECISIONS through #112; M11a
Phase A committed, Phase B not started.

**Documents read fresh this session:** `PARAMETERS.md` (complete, including the
truncated middle), `DESIGN.md` §1–2, `M10a-growth-economy.md` (Task 5, the
ledger and boundary sequence), `M10-growth-economy-explainer.md` (calibration
section in full), `M10b-async-event-time-spec.md` (Designs 2, 2a, 3),
`M11a-population-structure-spec.md` (Designs 4, 5, 6, 7, the verification-task
block, the flagship and `donation_game_threshold` scenario text, Design 11
fragments), `DECISIONS.md` #111 and #112.

---

## 1. Settled decisions (ten questions, all answered by Yoav)

| # | Decision |
|---|---|
| 1 | Flagship `spatial_reciprocity` gets a **third override: sucker payoff = −1**. Matrix (T=5, R=3, P=0, S=−1). Strict ordering preserved; the ordering validator stays ON. |
| 2 | The spatial income multiplier is **2 × degree**, not degree. Findings 1 and 2 go to the implementation session as **one joint verification item**. |
| 3 | The corrected anchoring insight is adopted, with a worked example for each half. |
| 4 | VT-3's "relative differences widen" wording: **soften in the guide, log a DECISIONS entry, AND have Phase B measure it.** |
| 5 | Reproduction-cost gap: **warn in the guide AND log the validator gap separately.** Advisory process designed (see #3 below). |
| 6 | The structure-coefficient generalisation is **IN**, as a short subsection with its caveats. |
| 7 | Four load-bearing citations re-verified in-session. **Done.** |
| 8 | Weak-Prisoner's-Dilemma attribution **verified properly** (done), because the interface must still permit punishment = sucker = 0. |
| 9 | `threshold_cloning` shift-dependence gets a **read-and-report code verification task**. |
| 10 | Filename **`docs/explainers/calibration-guide.md`**; the no-specification deviation is logged as a DECISIONS entry. |

**Four follow-up decisions, also settled:**

- **Reframed central claim ADOPTED** (§2 below). This replaces the brief's
  original anchoring statement and is the guide's §1.
- **Encounter-frequency is a BACKLOG ITEM, targeted at M11b.** Parameter name
  agreed: `matching.encounter_mode`, values `per_initiator` (today) and
  `per_pair` (deduplicated). Must be logged so it is not forgotten. NOT an M11a
  change — the spec is frozen and Phase A is committed; altering pairing
  semantics would invalidate the golden masters Phase C depends on.
- **`docs/ADVISORIES.md` CONFIRMED** as the backlog queue, four fields per
  entry, seeded with six items. Batch ownership: **M11b takes the mechanism plus
  items 2, 5, 6; M12 takes items 3 and 4; item 1 is a validator, not an
  advisory.**
- **Delivery in TWO BLOCKS**, each ending with its own `Action required:` line.

**Register (Yoav's explicit instruction, updated this session):** STEM-smart
reader, no game-theory background. **Bare formulas ARE acceptable and preferred**
— but every parameter and variable must be explained in a list UNDERNEATH the
formula, never inline inside it. Every acronym and initialism spelled out on
first use. Every reference described in words before it is cited. Every number
worked, never asserted. Real-life anchors throughout.

---

## 2. The reframed central claim (the guide's §1)

Each regime is invariant to exactly one transformation, and in both cases it is
the opposite one from intuition.

|  | Shift (add constant *a* to all four payoffs) | Scale (multiply all four payoffs by *a* > 0) |
|---|---|---|
| **Imitation** | Invariant — but ONLY under equal participation | **NOT** invariant at fixed selection intensity: scaling by *a* is identical to multiplying β by *a* |
| **Energy economy** | **NOT** invariant: income accumulates over rounds played, and zero energy is an absolute point (death) | Invariant — PROVIDED the whole ledger scales with it |

**Scale-invariance of the economy, why it holds.** The ledger is
`e ← e × (1 + r) + score − L − engagement_cost × matches`. Every term except
`r` is an energy quantity and the expression is linear in all of them. Multiply
the four payoffs, L, θ, σ, initial energy, engagement cost and reproduction
overhead by the same *a* > 0 and every trajectory scales by *a*. Insolvency
tests sign (preserved by positive scaling); the reproduction test scales on both
sides; `r` is a dimensionless ratio; carrying capacity is a head count; age and
mortality never see energy. **Practical licence: only ratios matter — income
relative to L, σ relative to net income, θ relative to σ. Absolute magnitudes are
free.** The one way to lose it is to scale the payoffs and forget one ledger
term.

**Shift-non-invariance, why it fails.** Adding *a* to every payoff adds
*a* × (rounds played) to income. Compensating requires adding
*a* × (rounds per period) to L, which works only if rounds per period is uniform
across agents and constant over time. It fails under `random_k` (participation
varies agent to agent) and under `round_robin` in a growth economy (rounds per
period rises with N). Separately, zero energy is an absolute anchor.

---

## 3. Findings produced this session (all still live)

**Finding 1 — Flagship ordering.** Overriding punishment to 0 while sucker sits
at its default 0 gives punishment = sucker, which fails strict `T > R > P > S`.
RESOLVED by decision: override sucker to −1. Still needs code confirmation of
whether the validator is strict or lenient (goes into the joint verification
item).

**Finding 2 — Spatial income is 2 × degree.** M11a Design 6 deliberately
inherits `RandomK`'s no-deduplication behaviour, so each agent initiates against
each neighbour AND is drawn by each neighbour. Von Neumann (4 neighbours) →
≈ 8 matches per agent per period, not 4. Moore (8 neighbours) → ≈ 16, not 8. The
spec's flagship prose ("earns reward from all four neighbours") reads as 4. The
defector side is invisible to the error because 8 × 0 = 4 × 0.

**Finding 3 — VT-3's second-order claim fails its own arithmetic.** Under the
shift idiom `w_i = e_i − min(e)`, if energies diverge linearly at rates `r_i`
then `w_i(t) = (r_i − r_min)·t` and the draw probability
`w_i / Σw` is constant in `t` — the *t* cancels. Subtracting the poorest
normalises steady divergence away. What IS demonstrable: (a) selection starts at
exactly zero (all agents identical → all weights zero → uniform fallback fires →
the breeder draw is pure luck), and rises from there; (b) the draw partly selects
for AGE, since incumbents out-accumulate newborns regardless of strategy, and at
the textbook offspring stake of 0 a newborn effectively cannot breed until it
accumulates; (c) whether it keeps strengthening after divergence is established
requires super-linear spread growth — an empirical question, not an arithmetic
one.

**Finding 4 — Reproduction overhead breaks a documented guarantee.** The
validator checks offspring stake ≤ reproduction threshold and the documentation
says this guarantees a parent always survives its own reproduction. But the
parent pays stake PLUS overhead. With threshold 500, stake 400, overhead 150, a
parent at exactly threshold ends at −50. Quiet failure: under the #80 boundary
order (insolvency at step 5, births at step 6) it does not die immediately — it
carries the negative balance and dies at the FOLLOWING boundary.

**Finding 5 — Rule-by-rule invariance table** (derived from registry
descriptions, NOT from code — hence verification task 2):

| Selection rule | Shift | Scale |
|---|---|---|
| `fermi` | invariant (equal participation only) | **not** — equivalent to rescaling β |
| `proportional` | invariant | invariant |
| `tournament_k` | invariant (rank-based) | invariant |
| `truncation` | invariant (rank-based) | invariant |
| `threshold_cloning` | **invariant ONLY at multiplier = 1.0** | invariant |

`threshold_cloning` arithmetic: the bar is `m × mean`. Under a shift *a*, agent
*i* survives if `s_i + a ≥ m(μ + a)`, i.e. `s_i ≥ mμ + (m − 1)a`. At m = 1 the
*a* cancels. At m = 1.2, adding 100 to every score moves the bar 120 while
individual scores move 100 — the bar shifts 20 relative to the field.

**Finding 6 (NEW, from verification) — `birth_death` forecloses cooperation
entirely.** Ohtsuki's Supplementary Information §3 works out all three update
rules and reports that under birth-death updating, defectors are favoured over
cooperators for ANY choice of benefit and cost with b > c > 0 — selection never
favours cooperators. pdsim's `moran_rule` offers `birth_death`, `death_birth`
and `random`. A user setting `birth_death` and expecting spatial reciprocity will
see cooperation lose every time, correctly. The `random` mixture dilutes
proportionally. Tarnita's proof also explicitly excludes birth-death from its
assumption (i), so the structure-coefficient result carries a caveat there too.

**Finding 7 (NEW, from verification) — finite-N structure coefficient.**
Tarnita eq. (18): `σ = ((k+1)N − 4k) / ((k−1)N)`. At von Neumann (k = 4):
6×6 lattice (N=36) → 164/108 = **1.52**; 10×10 (N=100) → 484/300 = **1.61**;
20×20 (N=400) → 1984/1200 = **1.65**; limit → 5/3 = **1.67**. pdsim's default
population is 100, so the textbook value overstates the structural advantage.
Additional authors' caveat: Ohtsuki's derivation uses pair approximation
formulated for Bethe lattices (regular graphs WITHOUT loops), and the authors
state that discrepancy with simulations on graphs with loops is expected — a
square lattice is nothing but loops.

---

## 4. Verified citations (all verified in-session 2026-08-02)

URLs recorded so a fresh instance can re-verify cheaply rather than
re-discover. House rule requires in-session verification; re-fetching these
exact URLs discharges it in one call each.

**[1] Axelrod, R. & Hamilton, W. D. (1981).** The evolution of cooperation.
*Science* 211(4489), 1390–1396. DOI: 10.1126/science.7466396.
✅ FULL TEXT READ. Source: Axelrod's own institutional deposit,
`https://websites.umich.edu/~axe/research/Axelrod%20and%20Hamilton%20EC%201981.pdf`
Supports: Figure 1 caption gives T=5, R=3, P=1 and states the game is defined by
`T > R > P > S` and `R > (S + T)/2`. Note 17: the second condition exists to rule
out the possibility that alternating exploitation could be better for both than
mutual cooperation. **This settles the provenance — 1981 paper, not the 1984
book — and confirms the app's defaults are that paper's illustrative values.**

**[2] Hofbauer, J. & Sigmund, K. (2003).** Evolutionary game dynamics.
*Bulletin of the American Mathematical Society* 40(4), 479–519.
✅ FULL TEXT READ from the PUBLISHED AMS PDF. Source:
`https://www.ams.org/journals/bull/2003-40-04/S0273-0979-03-00988-1/S0273-0979-03-00988-1.pdf`
Supports three claims: §2.2(a) adding a constant to all entries in a column does
not affect the replicator equation; §3.1 for non-linear payoff functions the
dynamics is unchanged under adding a function to all payoff functions; §3.2 all
aggregate monotonic imitation dynamics reduce, through a change in velocity, to
replicator dynamics ("same trajectory, different clock").

**[3] Hofbauer & Sigmund (1998),** *Evolutionary Games and Population Dynamics*,
Cambridge University Press. Bibliographic only. No claim rests on it; listed as
the standard reference.

**[4] Ohtsuki, H., Hauert, C., Lieberman, E. & Nowak, M. A. (2006).** *Nature*
441, 502–505. DOI: 10.1038/nature04605.
✅ SUPPLEMENTARY INFORMATION READ IN FULL. Source: co-author Hauert's own
institutional reprint,
`https://personal.math.ubc.ca/~hauert/publications/reprints/ohtsuki_nature06supp.pdf`
Supports: the donation-game matrix (cooperator vs cooperator = b − c, cooperator
vs defector = −c, defector vs cooperator = b, defector vs defector = 0);
death-birth update definition; `b/c > k` for death-birth, `b/c > k + 2` for
imitation updating; **birth-death never favours cooperators (Finding 6)**; the
standard square-lattice neighbourhoods are named as von Neumann (k = 4) and
Moore (k = 8); **the explicit intensity parameter — fitness is `(1 − w) + w ×
payoff`, with w = 1 strong selection and w ≪ 1 weak selection**; results hold for
N ≫ k and weak selection; pair approximation is for Bethe lattices so
discrepancy on looped graphs is expected.

**[5] Traulsen, A., Pacheco, J. M. & Nowak, M. A. (2007).** *Journal of
Theoretical Biology* 246(3), 522–529. Publisher record and abstract only.
**DECISION: do not cite.** The β-and-scale equivalence is two lines of algebra
and ships as a project-internal derivation, explicitly labelled as such.

**[6] Nowak, M. A. & May, R. M. (1992).** Evolutionary games and spatial chaos.
*Nature* 359, 826–829. DOI: 10.1038/359826a0.
⚠️ Bibliographic verified; matrix content verified via [7], not from Nature.
**Attribution wording agreed: credit the punishment = sucker = 0 matrix to Nowak
& May 1992, and credit the "weak Prisoner's Dilemma" name and the
qualitative-equivalence finding to Szabó & Fáth 2007.**

**[7] Szabó, G. & Fáth, G. (2007).** Evolutionary games on graphs. *Physics
Reports* 446(4–6), 97–216.
✅ CONTENT READ from the authors' arXiv deposit (`arXiv:cond-mat/0607344`), not
the Elsevier version. §6.5 states Nowak and May used a rescaled matrix with
punishment 0, sucker 0, reward 1, temptation b, containing only one free
parameter. Footnote 12: the case where the sucker payoff equals zero is
sometimes called a "weak" Prisoner's Dilemma, in which not only mutual defection
but also both mixed outcomes are Nash equilibria; and Nowak and May found the
weak version has the same qualitative properties as the typical version, at
least for small cost.

**[8] Tarnita, C. E., Ohtsuki, H., Antal, T., Fu, F. & Nowak, M. A. (2009).**
Strategy selection in structured populations. *Journal of Theoretical Biology*
259(3), 570–581. DOI: 10.1016/j.jtbi.2009.03.035.
✅ FULL TEXT READ from the Harvard DASH open-access deposit carrying the
publisher DOI:
`https://dash.harvard.edu/server/api/core/bitstreams/7312037c-52ae-6bd4-e053-0100007fdf3b/content`
Supports: the condition `σa + b > c + σd` for matrix rows A, B; mapping
A = cooperate, B = defect gives a = reward, b = sucker, c = temptation,
d = punishment, hence `σR + S > T + σP`; `σ = (k+1)/(k−1)` for regular graphs of
degree k under death-birth, low mutation, large N; **`σ = ((k+1)N − 4k) /
((k−1)N)` for general N (Finding 7)**; `σ = (N−2)/N` for a finite well-mixed
population, always below 1; σ = 1 is exactly risk-dominance and σ > 1 means the
diagonal entries matter more; effective payoff `1 + δ × payoff` with δ → 0 the
weak-selection limit; **scope limit — the proof assumes constant birth rate or
constant death rate; death-birth satisfies this, birth-death on graphs
explicitly does not, and the authors say the condition is still expected to hold
there but needs a different proof.** This discharges DECISIONS #111(d)'s
unverified pointer.

**[9] Nowak, M. A. & Sigmund, K. (1990).** *Acta Applicandae Mathematicae* 20,
247–265. ❌ NOT USABLE for coining "equal gains from switching." The guide uses
"additivity" and "equal gains from switching" as standard terminology with no
attribution of origin.

---

## 5. Key arithmetic the guide must carry (pre-worked, do not re-derive)

**The no-alternation condition.** Satisfied on the defaults: 2R = 6 > T + S = 5,
margin 1. Violated at T = 7, R = 3, S = 0: two players alternating exploitation
collect 7 over two rounds each, steady cooperation collects 6 — alternation wins
and the game stops being about cooperation.

**Additivity fails on the defaults.** T − R = 5 − 3 = 2 against P − S = 1 − 0 = 1.
Not equal, so the matrix is not a donation game and "benefit over cost" is not
merely inapplicable but UNDEFINED: two candidate benefits (T − P = 4, R − S = 3)
against two candidate costs (T − R = 2, P − S = 1) give four defensible readings
— 4/2 = 2.0, 4/1 = 4.0, 3/2 = 1.5, 3/1 = 3.0 — of which two clear von Neumann's
k = 4 and two fail it.

**Recipe for building an additive matrix.** Pick punishment P and cost c, set
sucker S = P − c. Pick benefit b, set temptation T = P + b and reward
R = P + b − c. Worked all-non-negative example: P = 1, c = 1, b = 5 → S = 0,
T = 6, R = 5 → matrix **(6, 5, 1, 0)**. Checks: ordering 6 > 5 > 1 > 0 ✓;
no-alternation 2R = 10 > T + S = 6 ✓; additivity T − R = 1 = P − S ✓;
benefit T − P = 5 = R − S ✓; b/c = 5 unambiguous.

**The two-matrix worked example (the guide's centrepiece).** (5, 3, 0, −1)
versus (6, 4, 1, 0). Both have T − R = 2 and P − S = 1 — a shift never changes
additivity, because both differences are shift-invariant. Both preserve every
best response. **Identical under imitation. Two different worlds under the
economy**, at the flagship's settings (von Neumann, one round per match, ≈ 8
rounds per agent per period):

| | (5, 3, 0, −1) | (6, 4, 1, 0) |
|---|---|---|
| Defector interior income | 8 × 0 = **0** | 8 × 1 = **8** |
| Cooperator cluster interior | 8 × 3 = 24 | 8 × 4 = 32 |
| Cooperator at cluster edge, per defector neighbour | **−1** | 0 |

A transformation that is provably free under imitation destroys the flagship's
starvation mechanism under the economy. This is DECISIONS #111(c)'s reasoning as
arithmetic.

**The sucker-sign modelling question (pose, do not settle).** Does being
exploited COST you, or merely FAIL TO PAY you? Handing over a real resource — a
donation, a covered shift, a shared harvest — is a net loss, so sucker < 0.
Offering a trade the other party declines costs the opportunity but not the
goods, so sucker = 0. On a lattice this decides whether cluster edges bleed
energy or merely fail to earn it.

**Neighbourhood shape does four things at once.**

| | von Neumann (k = 4) | Moore (k = 8) |
|---|---|---|
| Ohtsuki threshold | b/c > 4 | b/c > 8 |
| Structure coefficient σ (large N) | 5/3 = 1.67 | 9/7 = 1.29 |
| Matches per agent per period | ≈ 8 | ≈ 16 |
| Runtime | baseline | roughly double |

Choosing rule: **is a diagonal neighbour as easy to reach as an orthogonal one?**
Von Neumann for channel-constrained contact — settlements along rivers or
canals, street grids where diagonal buildings share no boundary, agricultural
plots sharing edges, administrative districts sharing borders, supply chains
with fixed links; also when the strongest clustering effect is wanted (which is
why the flagship uses it). Moore for open terrain where a diagonal step costs
nothing extra — grazing land, open sea, plains, air routes, social networks with
no geographic constraint; also as a deliberately harder test.

**Structure coefficient on the defaults.** σ = 5/3, a = R = 3, b = S = 0,
c = T = 5, d = P = 1. Left side σa + b = 5 + 0 = 5. Right side c + σd =
5 + 5/3 = 6.67. Left is smaller → cooperation not favoured. A clear answer where
the ratio test gave four contradictory ones.

**Income identity.** rounds per agent per period = matches per agent × rounds per
match. Three regimes: `round_robin` → N − 1 matches, income ∝ N, self-decalibrates
in a growth economy. `random_k` → ≈ 2k matches (k initiated + k drawn; the N
cancels), bounded independent of N. `spatial_interaction` on → ≈ 2 × min(k,
degree), N-independent and geometry-determined.

**The M10a window (restate compactly, cross-reference, do NOT re-derive at
length).** `random_k` with k = 5 and 10 rounds per match: 2k = 10 matches → 100
rounds → all-cooperate income 100 × 3 = 300, all-defect income 100 × 1 = 100 →
window is 100 ≤ L < 300 → midpoint L = 200 → cooperator nets +100, defector nets
−100 per generation.

**Reproduction-cost failure, worked.** Threshold 500, stake 400, overhead 150:
parent at exactly 500 pays 550 and ends at −50. Rule for the reader:
**threshold ≥ stake + overhead.**

**Escape velocity.** `e* = costs / r`. At r = 0.05 with costs 200, e* = 4000
against a threshold of 500 — a long band where agents breed but are not yet
rentiers.

**Accumulation artifacts and mitigations (guide §7.2).** (a) Age proxy in the
fixed-population breeder draw — mitigate by setting the offspring stake near
typical working energy, or shortening runs, or reporting it. (b) Selection
starts at literally zero — early trajectories are drift, not selection.
(c) Blocked-parent wealth under structure: a walled-in parent pays nothing and
accumulates without limit, then dominates BOTH the fitness draw AND the
energy-priority birth rationing, so being stuck becomes being favoured the
moment a seat opens. (d) The rentier above escape velocity. (e) **The living
cost is not a knob in the fixed-population mode at all** — a uniform per-capita
cost shifts every balance equally and the shift idiom removes uniform shifts
exactly. General principle: **prefer a flow to a stock wherever the platform
offers the choice** — under imitation `score_accounting` does; under the economy
it does not.

---

## 6. Agreed outline for `docs/explainers/calibration-guide.md`

Estimated 900–1,100 lines. Register per §1 above: bare formulas ARE fine, with
every parameter explained in a list underneath, never inline.

**§0 — What this is, and when you don't need it.** Purpose, audience, scope.
The stopping rule: under tournament run mode nothing evolves and payoffs are a
scoreboard; under imitation with a rank-based selection rule the numbers barely
matter. Cross-reference the M10 explainer as the economy's deeper derivation and
`PARAMETERS.md` as the authority on defaults.

**§1 — Two regimes, and the invariance table.** The reframed central claim
(§2 above). This is the spine; everything after elaborates it.

**§2 — The constraint structure.**
2.1 `T > R > P > S`, the two dominance facts, worked on the defaults.
2.2 `2R > T + S`, worked satisfied and worked violated, with Axelrod &
Hamilton's own rationale.
2.3 The two app toggles; when switching them off is legitimate (Chicken, Stag
Hunt, the weak Prisoner's Dilemma properly attributed); the honest warning that
the economy's income arithmetic keeps computing while the survival-window
language stops meaning what it says.
2.4 Additivity and the donation-game construction; the four-readings arithmetic;
**the recipe and (6, 5, 1, 0)**.
2.5 The structure-coefficient generalisation — **finite-N formula as the working
one**, the (k+1)/(k−1) form as its limit, plus BOTH caveats (birth-death
excluded from the proof; pair approximation assumes no loops).

**§3 — Invariance under imitation.**
3.1 The claim stated precisely: invariant to what, at fixed what.
3.2 Shift worked (add 4 to every cell).
3.3 Scale worked as the selection-intensity equivalence (×10 payoffs at β = 1
IS β = 10 at original payoffs). Labelled a project-internal derivation.
3.4 The participation caveat under `random_k`, worked with two agents drawn 8
and 12 times.
3.5 The five-rule table (Finding 5), with the `threshold_cloning` arithmetic in
full, provenance stated.
3.6 Where the results come from — the replicator column-constant invariance and
the aggregate-monotonic reduction ("same trajectory, different clock").
3.7 **The (5,3,0,−1) vs (6,4,1,0) example lands here** and is called back in §4
and §7.

**§4 — Income under the economy.**
4.1 The income identity, three multipliers, none labelled "income."
4.2 The three-row matcher table with **2 × degree derived, not asserted**.
4.3 **The encounter-frequency question** as a modelling choice, with the
ancient-tribes framing; two matches of one round ≠ one match of two rounds
(reciprocal strategies reopen at each match boundary; continuation length is
drawn per match); pointer to the backlog entry.
4.4 The window, restated compactly with cross-reference.
4.5 The recalibration drill — change one thing at a time (rounds 10 → 50; k
5 → 2; matcher → round-robin; shape Moore → von Neumann) and watch L = 200 fall
outside the window each time.
4.6 The shift is not free here either: +1 on all four cells at 100 rounds per
period adds 100 to every income, half the living cost.

**§5 — The two gates.** θ as eligibility, σ as stake paid only on placement
success; the global capacity gate versus the local structural gate and that
clearing one is not clearing the other in both directions; the blocked parent
worked at five times threshold; **the payload — under structure, geometry not θ
is the binding constraint on birth rate**, with arithmetic both ways;
**threshold ≥ stake + overhead**.

**§6 — The remaining ledger knobs.** Engagement cost (per match not per round,
and why; it inherits the same matcher multiplier as income); reproduction
overhead (pure destruction); capital return rate and escape velocity.
Cross-reference the scale-invariance licence — these all scale together or not
at all.

**§7 — Three M11a exhibits.**
7.1 The flagship's ecological starvation, with #111's conceptual guard stated in
full (ecological, NOT the Ohtsuki mechanism; the two point the same way and must
never be conflated).
7.2 Accumulation artifacts and their mitigations.
7.3 **Why `birth_death` forecloses cooperation entirely** (Finding 6).

**§8 — The calibration procedure.** Numbered checklist, doubling as the advisory
seed list. Includes the re-run trigger list: touching matcher, opponents per
agent, rounds per match, neighbourhood shape, or world structure silently
multiplies income.

**§9 — Quick reference table.** Every quantity: units, what it is compared
against, **what silently rescales it** (that third column is the table's
purpose).

**References**, with a provenance note in the M10 explainer's house style, and
derived-not-cited items separated under their own heading.

**Real-life anchors, recurring throughout:** two firms and a price agreement
(the payoff cells); neighbouring territories choosing between alternating raids
and steady trade (the no-alternation condition); covering a colleague's shift
(benefit and cost); a firm's fixed operating overhead (living cost); household
capital before a child and the child's endowment (threshold and stake);
per-deal transaction costs (engagement cost); endowment income (capital return
rate); a prosperous family with no land next door (the blocked parent); a
village market versus a global one (matcher choice); a regulated market with a
fixed number of licences (the fixed-population mode).

---

## 7. Block B contents (the second prompt)

**Three DECISIONS entries:**
1. The no-specification deviation — a standalone explainer with no companion
   spec, deliberate, with the reasoning and the precedent it sets.
2. Softening the accumulated-energy claim — VT-3's "relative differences widen"
   overstates what the arithmetic supports; record the correct mechanisms
   (from-zero, age-proxy) and that Phase B will measure the open half.
3. The flagship's third override (sucker = −1) with its reasoning.

**One new file, `docs/ADVISORIES.md`**, four fields per entry — trigger
condition as a calculation over parameter values; message text; severity
(informational / caution / blocking); where it surfaces. Seeded with six items:

| # | Trigger | Owner |
|---|---|---|
| 1 | threshold < stake + overhead | **NOT an advisory — validator fix, logged separately** |
| 2 | Living cost outside the survival window | M11b |
| 3 | Moran rule = birth-death with a cooperation-focused roster | M12 |
| 4 | Payoff scale changed without a matching selection-intensity change | M12 |
| 5 | Matcher, opponents-per-agent, rounds, or neighbourhood shape changed without recomputing the window | M11b |
| 6 | Spatial interaction on with opponents-per-agent at or above the neighbourhood size (income silently doubles) | M11b |

Mechanism ownership: **M11b**, reusing M11a's greying-map predicate-table pattern
(a list of rules, each a pure function of parameter values, evaluated in one
place). Reasons: architectural reuse, and M11b is redesigning the parameter panel
anyway so where warnings appear is a disclosure question best answered once.

**One ROADMAP addition:** `matching.encounter_mode` targeted at M11b, values
`per_initiator` (today's behaviour) and `per_pair` (deduplicated), with the
reasoning — an encounter is an event that happens to a pair, not something each
side independently initiates; the current behaviour is an artefact of indexing
matches by initiator.

**Two verification tasks for the implementation session:**
1. **`threshold_cloning` arithmetic.** Read-only. Confirm the survival bar is
   computed as multiplier × generation mean. If yes, Finding 5's table ships as
   written. If the implementation differs, report the actual computation and the
   table row is rewritten before the guide is finalised.
2. **Joint flagship item.** (a) Is the payoff-ordering validator strict or
   lenient on punishment versus sucker? (b) Confirm the match count per agent
   under spatial interaction — is it ≈ 2 × degree as Design 6's no-deduplication
   inheritance implies? Both outcomes pre-specified: if 2 × degree, the
   flagship's living cost must be calibrated against ≈ 8R for a cluster-interior
   cooperator, not 4R, and the Moore counterfactual in things-to-try is a
   four-fold income change rather than a two-fold one; if the engine
   deduplicates after all, Design 6's text needs correcting instead.

---

## 8. House rules in force

- Claude Code NEVER commits. It presents a summary, file list, and suggested
  commit message; Yoav commits.
- Every suggested change arrives as a single, clearly labelled, complete
  cut-and-paste prompt block, ending with an explicit one-line
  `Action required:` statement.
- Contradictions are REPORTED, not reconciled.
- Specs are frozen historical records; deviations are logged in `DECISIONS.md`,
  never retro-edited into the spec.
- Literature claims are verified against publisher or author-deposit records
  before entering docs; claims derived by consistency check are NOT citations
  and must be labelled as derivations.
