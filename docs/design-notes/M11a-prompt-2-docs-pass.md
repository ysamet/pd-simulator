# CLAUDE CODE PROMPT — M11a, PROMPT 2: PRE-IMPLEMENTATION DOCUMENTATION PASS

## What this prompt does, and what it must not do

This is a **documentation-only** pass. It corrects two coherence points in the
M11a spec, adds a design finding that arrived after the spec was committed, and
records that finding as a DECISIONS entry.

**Write no code. Write no tests. Add no registry entries.** Do not run
`python -m pdsim.gendocs` (nothing here touches the registry). Do not run
`pytest` (no behaviour changes).

**Files you may edit — exactly two:**

- `docs/specs/M11a-population-structure-spec.md`
- `docs/DECISIONS.md`

Change no other file. In particular, do **not** touch `DESIGN.md`,
`ROADMAP.md`, `PARAMETERS.md`, `CLAUDE.md` or `WIP.md`.

**Why this is a separate prompt rather than a preamble to Phase A.** The spec is
the artifact every later phase references, and no code exists against it yet.
Correcting it while it is still purely a document keeps the commit history clean
and keeps the next handback unambiguous — if something looks wrong after Phase A,
it is Phase A, not a docs pass riding along with it.

## Read these first

- `docs/specs/M11a-population-structure-spec.md` in full — you are editing a
  document you wrote across two prompts, and the edits must read as one voice.
- `docs/DECISIONS.md`, at least #103–#110, for the entry format and the
  numbering. **#110 is the highest existing entry; this prompt writes #111.**
- `docs/PARAMETERS.md` §Game, for the four payoff parameters and their defaults.

## On #62 and retro-editing

The project rule is that **specs are frozen historical records** and deviations
found during implementation become **new DECISIONS entries, never retro-edits**.
That rule governs deviations discovered *while building against a spec*. It is
not engaged here: the spec is at `Status: draft`, no implementation exists
against it, and these are corrections made before the first line of code.

Two of the edits are nevertheless recorded in `DECISIONS.md` as well, because
they are genuine choices rather than clarifications, and their reasoning exists
nowhere in the repository: **Edit 4** changes a committed count (53 → 54), and
**Edit 2** overrides two live registry defaults in the flagship scenario. Both go
into **#111**.

---

# THE SIX EDITS

## Edit 1 — Attribute VT-4's evidence in the risk reading

**Where:** the Phase plan's Risk reading, sub-item **(iv-a)**.

**Problem.** Design 5 (written in Prompt 1A) hedges — "VT-4 **may** add a second,
larger effect" — while (iv-a) asserts "VT-4's answer **makes** `boundary_order`
doubly restrictive", and the Verification tasks section still presents both VT-4
branches as open. A sequential reader meets a hedge, then an assertion, then an
open question, with no explanation of the shift.

**Fix — minimal, at (iv-a) only.** Reword its opening clause so the evidence is
attributed and the hedge chain stays honest. Something of this form:

> **(iv-a) VT-4's expected answer — evidenced by code inspection during the spec
> drafting, and pending Phase C's runtime confirmation — makes `boundary_order`
> doubly restrictive, and this must be written into the help text.**

Keep every other word of (iv-a), including the worked K = 200 / 180 living / 20
deaths arithmetic and the conclusion that a `birth_first` run sitting at a
visibly lower population is correct rather than broken.

**Do not touch Design 5, and do not touch the VT-4 task entry.** Design 5's
hedge is *correct*: VT-4 is formally open until Phase C runs it, and reading
source code is evidence, not runtime verification. Add one short sentence to
(iv-a) saying exactly that, so the reader understands why the spec holds
evidence and verification apart.

## Edit 2 — Set the flagship scenario's two implied parameters explicitly

**Where:** the Validation section, the `spatial_reciprocity` scenario.

**Problem.** The scenario's description says cooperators "earn R from all four
neighbours" and defectors "earn P = 0". Both are **implications of prose that are
not stated as settings**, and both differ from the registered defaults: four
neighbours means `von_neumann`, but `neighbourhood_shape` defaults to `moore`
(eight); and the default punishment payoff is **P = 1**, not 0.

**This is not cosmetic — P = 0 is what makes the mechanism work.** The scenario's
whole claim is that a defector in a defector interior starves. Under the energy
economy that depends on whether its income clears the basic living cost L. With
P = 1 and eight neighbours, a defector in a solid defector block earns 8 per
round rather than nothing, which may well clear L — in which case it does not
starve, cooperator clusters gain no relative advantage, and the flagship
demonstrates nothing. With P = 0 it earns literally nothing and the living cost
kills it.

The neighbourhood shape pushes the same way: fewer neighbours means stronger
viscosity and an easier time for clustering, so `von_neumann` is the
configuration most likely to actually show cooperation surviving — which is what
a flagship scenario is for.

**Fix.** State both as explicit scenario settings: **`neighbourhood_shape =
von_neumann`** and **`payoff_punishment = 0`**. Keep the existing description
text as written. Add a sentence explaining **why** P = 0 is set rather than left
at its default, in the terms above: the mechanism is a defector interior earning
nothing against the living cost.

**Both overrides are recorded as decisions in #111 (see Edit 5), not treated as
clarifications of the existing prose.** The spec described the mechanism but
never stated either value as a setting, and both override a live registry
default for a specific mechanical reason. A later reader meeting them in scenario
prose alone would have no way to recover why.

**Also add a second things-to-try note:** switch `neighbourhood_shape` to `moore`
and watch the clusters struggle. This is #36-compliant — one scenario, one
configuration, comparisons live in things-to-try — and it teaches the
degree-dependence for free.

**One conceptual guard to write into the scenario text, because it is easy to
blur.** The flagship does **not** rest on the Ohtsuki mechanism. Its story is
**ecological**: absolute income measured against a survival threshold, with P = 0
meaning a defector interior earns nothing. Ohtsuki's b/c > k is about **relative
fitness in a Moran process under weak selection**, and that is
`donation_game_threshold`'s scenario, not this one. The two arguments happen to
point the same way, and the spec must never let a reader think one is the other.

## Edit 3 — Additivity: the fourth non-obvious requirement (THE MAIN EDIT)

**Where:** three places, listed below.

### The finding

The b/c > k rule is derived for the **donation game** specifically, not for a
general Prisoner's Dilemma matrix. In the donation game a cooperator pays a cost
c so the opponent receives a benefit b, and a defector pays and provides
nothing — which in matrix terms means **T = b, R = b − c, P = 0, S = −c**.

Read the cost of cooperating off that matrix twice:

- against a **cooperator**: T − R = b − (b − c) = **c**
- against a **defector**: P − S = 0 − (−c) = **c**

The same number. Cooperating costs you c **regardless of what the other player
does** — your action and theirs contribute independently to your payoff. The
benefit falls out symmetrically: T − P = **b** and R − S = **b**.

So the compliance test is: **T − R = P − S** (which defines c), and equivalently
**T − P = R − S** (which defines b). This property is called **additivity**, or
**equal gains from switching**, in the literature.

### Why this matters: our defaults fail it, and the failure is not a near miss

The registered defaults are **T = 5, R = 3, P = 1, S = 0**.

- T − R = 5 − 3 = **2**
- P − S = 1 − 0 = **1**

Not equal. Cooperating against a cooperator costs 2; cooperating against a
defector costs 1. This is a perfectly valid Prisoner's Dilemma — T > R > P > S
holds, and 2R > T + S holds (6 > 5) — it simply is **not a donation game**.

**The consequence is sharper than "the rule does not apply": with a non-additive
matrix, "b/c" is not a well-defined quantity at all.** There are two candidate
costs and two candidate benefits, giving four defensible readings:

| | c = T − R = 2 | c = P − S = 1 |
|---|---|---|
| **b = T − P = 4** | b/c = 2.0 | b/c = 4.0 |
| **b = R − S = 3** | b/c = 1.5 | b/c = 3.0 |

Four values spanning 1.5 to 4.0. Against von Neumann's k = 4, two clear the
threshold and two do not — so a user could "predict" either outcome by choosing a
definition. That is the signature of a malformed question, not a hard one.

### Why the scenario's payoffs are the way they are

Run the same test on `donation_game_threshold`'s **T = 5, R = 4, P = 0, S = −1**:

- T − R = 1 and P − S = 1, so **c = 1**
- T − P = 5 and R − S = 5, so **b = 5**

Additive, and **b/c = 5** unambiguously. The scenario design then falls straight
out: von Neumann has k = 4 and 5 > 4 **clears**; Moore has k = 8 and 5 < 8
**fails**. That is why it ships on von Neumann with a things-to-try note inviting
the reversal.

**This is also the deeper reason VT-1 mattered.** S = −1 is not a stylistic
choice — additivity with P = 0 *forces* a negative sucker payoff. Had the
registry rejected negatives, the scenario would have needed the +1 shift, whose
real cost is the one the spec already names: every agent's income moves, and the
living cost L is calibrated against income.

### The three edits

**(3a) — the scenario's requirement list.** `donation_game_threshold` currently
lists **three** non-obvious requirements (`rounds_per_match = 1` with an AllC +
AllD roster; `fixed_n_death_rule = pure_random`; the weak-selection caveat).
**Add a fourth: additivity.** State that the four payoff values are not
arbitrary — they are the only kind of matrix for which the scenario's central
claim is even meaningful — and give the T − R = P − S test with the arithmetic
above. Note that the payoff parameters are live registry values, so a user can
nudge a slider and silently destroy the thing being demonstrated.

**(3b) — the §12 concept explanation for "the b/c > k threshold".** It is
currently under-specified: explaining what b and c *are* is not enough. It must
say that b and c only **exist** when T − R = P − S, and that under a non-additive
matrix the ratio is ambiguous rather than merely inapplicable.

**(3c) — a things-to-try warning** on `donation_game_threshold`: changing the
payoffs is fine and encouraged, but the threshold only applies while
T − R = P − S holds.

**None of these changes any checklist count.** They enrich items that already
exist. The 53-item total and Design 4's "fourteen concepts" cross-reference are
untouched by Edit 3.

## Edit 4 — The additivity readout: 8 derived readouts become 9, and 53 becomes 54

**Where:** the §12 checklist's derived-readouts group, and its headline count.

**The readout.** A panel readout that inspects the four payoff values and reports
one of two things:

- when **T − R = P − S**: that the payoffs are additive, with the resolved b, the
  resolved c, and the ratio — e.g. "additive: b = 5, c = 1, b/c = 5";
- when they differ: that the payoffs are **not** additive, so the b/c > k
  threshold does not apply, with a one-line reason (cooperating costs a different
  amount against a cooperator than against a defector).

**Why it earns its place.** It makes an otherwise invisible precondition visible
at the moment the user is in a position to act on it. This is exactly the
§12 spirit — the same argument that put "blocked parents" and "zero-neighbour
agents at founding" into the Economy panel rather than leaving them as tooltips.

**Implementation shape.** It is a **pure function of four registry values**, so it
slots directly into the paint-time resolver pattern Design 11 already mandates:
a pure free function callable from both the validator and the panel. No new
machinery.

**Counts.** Derived readouts **8 → 9**; §12 checklist total **53 → 54**. Update
the group count, the headline count, and the arithmetic line so it reads
**14 + 17 + 14 + 9 = 54**. Check the arithmetic and report it in your handback.

**Placement.** Phase E, with the rest of the §12 audit.

## Edit 5 — DECISIONS #111

Write a new entry, numbered **#111**, dated **2026-07-31**, in the house format
(a bold title line stating the decision, then the reasoning, with the rejected
alternative and the consequence). It must record:

- the **finding**: b/c > k presupposes an additive (donation-game) payoff matrix,
  T − R = P − S;
- that **the project defaults T=5, R=3, P=1, S=0 fail this test** (2 ≠ 1), and
  that the failure makes b/c **ambiguous across four readings from 1.5 to 4.0**,
  not merely inapplicable — include that table or its numbers, because the
  ambiguity is the substance of the decision;
- that `donation_game_threshold`'s T=5, R=4, P=0, S=−1 **is** additive with
  b = 5, c = 1, and that this is why those values were chosen and why VT-1's
  negative-payoff question was load-bearing;
- the **decision**: additivity becomes the fourth stated requirement of the
  scenario, the §12 concept explanation carries the precondition, and a **new
  derived readout** reports additive-or-not with the resolved b/c;
- the **count change**, stated explicitly: §12 derived readouts 8 → 9, checklist
  total 53 → 54;
- the **conceptual guard**: the flagship `spatial_reciprocity` scenario does not
  depend on this at all, because its mechanism is ecological (absolute income
  against the living cost) rather than relative fitness under weak selection.

### #111 must also record the flagship's two explicit overrides (Edit 2)

The spec described `spatial_reciprocity` in prose — cooperators earning R "from
all four neighbours", defectors earning "P = 0" — but never stated either as a
**setting**, and both differ from the registered defaults (`moore`, eight
neighbours; P = 1). Edit 2 makes them explicit settings. Record that in #111 as a
**decision**, not as bookkeeping, with the reasoning for each:

- **`neighbourhood_shape = von_neumann`**, overriding the `moore` default: fewer
  neighbours means stronger viscosity and an easier time for clustering, so this
  is the configuration most likely to actually show cooperation surviving —
  which is what a flagship scenario is for.
- **`payoff_punishment = 0`**, overriding the default P = 1: the scenario's
  entire mechanism is that a defector in a defector interior earns **nothing**
  and starves against the basic living cost L. At P = 1 with eight neighbours a
  defector in a solid block earns 8 per round, which may clear L — in which case
  it does not starve, cooperator clusters gain no relative advantage, and the
  flagship demonstrates nothing.

State plainly **why this is recorded rather than treated as a clarification**:
P = 0 is not a more precise restatement of anything, it is an override of a live
registry default chosen for a specific mechanical reason, and a later reader
meeting it in scenario prose alone would have no way to recover that reason. The
same logic covers the shape override. This is the traceability the DECISIONS file
exists for.

**One thing to state carefully in the entry.** There is a known generalisation of
b/c > k to non-additive matrices via a **structure coefficient** (cooperation
favoured when σR + S > T + σP, with σ = (k+1)/(k−1) for death-birth on a regular
graph). **Record it as an unverified pointer only** — flagged for the explainer's
literature pass, not asserted as project fact. It was derived during the design
conversation by checking that it collapses correctly to b/c > k, which is a
consistency check, not a citation. Do not put the formula anywhere in the spec.

## Edit 6 — Extend the explainer's scope and its verification list

**Where:** the Out-of-scope section's explainer bullet.

**Scope.** The M11a explainer must cover, at the owner's explicit request:

- the **full constraint structure on T, R, P, S** — the Prisoner's Dilemma
  ordering T > R > P > S; the 2R > T + S condition and what goes wrong without it
  (alternating exploitation becomes the best joint strategy); and the
  **additivity condition T − R = P − S**, with the donation-game construction
  that produces it;
- the **meaning and significance of the Ohtsuki threshold** — what b/c > k
  claims, the assumptions it rests on, and **why k appears at all** (k counts the
  competitors for a vacated site).

**The literature verification list grows from two items to four.** State all four
in the bullet:

1. whether Hammond & Axelrod used **wrap-around** on their 50×50 lattice
   (UNVERIFIED, #103);
2. the Kaznatcheev & Shultz **300-period figure** quoted by the M10 explainer
   without a verification note (UNVERIFIED, #103);
3. the **structure-coefficient generalisation** — the σ formulation and whether
   σ = (k+1)/(k−1) is correctly attributed (Tarnita et al. 2009 / Nowak et al.
   2009 are the likely sources; this must be checked, not assumed);
4. the **precise assumption set** behind b/c > k — donation game, weak selection,
   large population, pair approximation on regular graphs — verified against
   Ohtsuki et al. 2006 rather than reconstructed.

Add the standing rule as a sentence: **claims derived by consistency check are
not citations**, and nothing enters an explainer until it is verified against
publisher records.

---

# YOUR OBLIGATIONS ON FINISHING

1. **Do not commit.** Present (a) a summary of the six edits, (b) the files to
   stage — exactly `docs/specs/M11a-population-structure-spec.md` and
   `docs/DECISIONS.md` — and (c) a suggested commit message.
2. **Report the §12 arithmetic**: 14 + 17 + 14 + 9 = 54. If the written lists do
   not total 54, say so rather than adjusting the headline.
3. **Confirm the spec's status line still reads exactly `Status: draft`** and
   that no section was removed.
4. **Confirm no registry entry, code, or test was touched**, and that `gendocs`
   and `pytest` were not run.
5. **Report `DOCS CHANGED: docs/specs/M11a-population-structure-spec.md,
   docs/DECISIONS.md`** and call out the new decision number **#111** explicitly,
   per the end-of-session ritual.
6. **Raise any contradiction** these edits create with text written in Prompts 1A
   or 1B — particularly anything in Design 5, Design 11's resolver discussion, or
   the Validation section that now sits oddly against Edit 2's explicit settings.
   Report; do not silently reconcile.

Action required: apply the six documentation edits above to `docs/specs/M11a-population-structure-spec.md` and `docs/DECISIONS.md`, write no code or tests or registry entries, then report the summary, the §12 arithmetic, the files to stage, the suggested commit message, and the DOCS CHANGED line with #111 called out.
