# CLAUDE CODE PROMPT — M10a reconciliation (recovers the truncated tail)

> Copy everything below the line into Claude Code as a single prompt.
> Small and self-contained: it assumes M10a is staged and complete.

---

Follow-up to M10a. Your report was right on every count, including the
truncation: the prompt was 55,236 characters against a 50,000-character limit, so
it was cut two lines into **#76** and you lost the whole DECISIONS cluster, the
closing ritual, and the action line. Reconstructing #76–#84 from the spec's own
logging obligations was the right call. Here is the lost tail.

**Do not renumber or rewrite #76–#84.** They are coherent and the docs already
reference them. This is an **audit-and-append** pass.

## Task 1 — audit the DECISIONS cluster, then append what is missing

Below is the intended cluster as originally written. Most of its substance also
lived in the spec body (which survived inside the 50k), so much of it should
already be present in your #76–#84. **Read your #76–#84, check each item below
against them, and report a short coverage table** (item → covered by #NN, or
MISSING).

Then **append new sequential entries from #85** for anything genuinely missing.
Merge freely — do not manufacture nine entries to match a list. **Report the
final numbers.**

The intended content:

1. **Milestone renumbering.** Carries the table. States explicitly that it
   supersedes the **numbering** — *not* the substance or the rationale — of
   **#58** and **#75**. Append-only: **#58 and #75 are NOT retro-edited.** (The
   "numbering only, not substance" nuance and the explicit no-retro-edit
   instruction lived only in the lost tail — check it survived.)
2. **M10 splits into M10a (synchronous) / M10b (async).** Energy is a distinct
   paradigm that **replaces** imitation; the SelectionRule and ScoreAccounting
   families grey out (#34). **This ties off #64's deferred `cumulative`
   accounting**: energy *is* that cumulative stock, but repurposed — accounting
   produces "effective scores selection reads", energy is "a stock reproduction
   spends". Different jobs → replace, don't compose. So #64's `cumulative` option
   should be marked resolved-by-replacement rather than left open. Rejected:
   one-milestone-both-modes; async-first. *(The #64 tie-off was tail-only —
   most likely MISSING.)*
3. **The open-flow ledger** (named sources / sinks / transfers) and the two
   additive cost components. **`engagement_cost` is per-MATCH, not per-round** —
   a deliberate deviation from DESIGN §6.1's phrasing. Per-round would couple
   cost to `rounds_per_match` and continuation probability `w`, making
   match-length knobs silently *economic*; under `w` it would inherit a random
   match length, entangling a cost with RNG. **Rejected: coupling the two costs
   by a ratio** — the units don't work (energy/generation vs energy/match needs a
   match count, but N changes every generation by design), and it breaks M9.5
   axis independence. *(The rejected-ratio rationale was tail-only; it also
   appears in explainer §5.)*
4. **Offspring policy**: stake transfer, σ ≤ θ, one birth per agent per
   generation, `initial_energy` defaults to σ. **Rejected: fixed endowment
   (independent of σ); zero endowment (folded in as the σ = 0 corner); binary
   fission (parent splits its balance in half).** *(Rejected alternatives were
   tail-only — likely MISSING.)*
5. **Death at `e < 0`** (strict, not `<= 0`) and the M10a per-generation draw
   sequence, extending #32. **Death-before-birth is a plain design preference
   and deviates from Hammond–Axelrod's birth-before-death period order** — named
   honestly, *not* justified as "spatially correct for M11".
6. **`capital_return_rate`**; escape velocity `e* = costs / r`; capital return
   combined with highest-energy-first admission produces **structurally permanent
   dynasty** — named as a *mechanism*, not buried as a footnote. It cannot
   compound a debt (death at `e < 0` runs every generation, so every living agent
   enters every generation at `e ≥ 0`).
7. **`carrying_capacity`**: aspatial-specific scope (a lattice gets capacity free
   from site occupancy; K is the well-mixed model paying cash for it);
   deterministic RNG-free highest-energy-first admission, chosen over a random
   lottery which would inject fresh RNG into the birth phase for no scientific
   gain; placement and admission isolated in two named free functions (no
   speculative ABC — hard rule 6); check-placement-then-pay-σ.
8. **The mortality trio** and the registry's **first derived defaults** (`None` +
   `nullable` as the sentinel, reusing the `population.memory_depth` precedent
   rather than an `"auto"` string); resolved in a `mode="before"` validator
   because the models are `frozen=True`; warn-don't-forbid on effective max age.
9. **Founder age staggering** (automatic, no parameter).
10. **Passport ids** (never reused, monotonic) + `parent_id` lineage;
    `total_agents_born` / `population_final`. Rejected: id reuse ("hotel-room
    splicing" — stitching together the histories of unrelated creatures who
    happened to occupy the same slot).
11. **The variable-N `random_k` contract**: clamp to `min(k, N−1)`; verified
    no-op at N ≥ k+1 so no existing seeded run changes; the lone-survivor corner;
    id-sorted iteration over a non-contiguous id set; extinction ends the run.
    Rejected: error; skip.
12. **Per-agent snapshot** on `GenerationFinished`, economy-only, post-boundary
    carried-forward grain (with its named cost: an agent that earned, bred and
    died within one boundary has its gross earnings absent from the snapshot);
    population size derived not carried; **no explicit birth/death events**
    (deferred to M10b, where async event-time makes per-event ordering
    meaningful).
13. **`schema_version` 3** + the `agents.parquet` sibling; loaders accept
    {1, 2, 3}; imitation runs still write 2. Rejected: widening
    `timeseries.parquet` with energy columns (#47c's no-empty-columns rule).
14. **The calibration readout ships IN M10a** — app-first validation is not
    honest without it.
15. **The per-generation engagement tally** (matches *and* rounds), and why
    `agent.rounds_played` must not feed #44's denominator in economy mode.
16. **Per-opponent histories persist across generations** in economy mode;
    score-only reset. Amends the **scope** of #31 and #22, follows the #34
    tournament precedent. Names: GrimTrigger is lifetime-grim; the `view_of`
    O(length²) copy becomes quadratic in run length under round_robin;
    `memory_depth` is the bound; readout warns rather than forbids. Rejected:
    per-generation reset.

Also confirm these two, which your report says you already logged, are present
with their rationale intact:

- The **all-defector extinction at generation 6** deviation (participation luck
  under random_k vs the spec's mean-field trace).
- The **two economy validators conditioned on `energy_economy` mode**. Your
  reasoning here was correct and caught a real defect in the spec: an
  unconditional `K >= population.size` check would refuse to load a pre-M10a
  config with `population.size = 300` against the ignored default `K = 200`,
  breaking hard rule 8. Make sure the entry records *that* as the rationale —
  it is the load-bearing part.

## Task 2 — the all-defector trace: fix the live text, keep the numbers

Your generation-6 finding was independently reproduced at the design layer and
matches your series exactly: `40 → 40 → 40 → 40 → 21 → 1 → 0`, extinct at
boundary 6.

The mechanism is worth recording precisely, because it is more interesting than
"the spec was off by one". At **boundary 4 the mean-field defector energy is
exactly 0.0** — the measured population mean at that boundary is 0.0 and the
minimum is 0.0. The scenario therefore sits on a **knife edge**: at boundary 4,
death (`e < 0`, strict) is decided by participation luck *alone*, which is why it
splits the population almost exactly in half (21 of 40) instead of killing
everyone at once.

**Do not re-tune the scenario to make the collapse crisp.** The smear across
boundaries 4–6 is not noise obscuring the result — it **is** participation luck
under `random_k` (#44/#57), appearing in the economy exactly where theory says it
should. A defector population dying on a precise schedule would be the
*suspicious* outcome. The calibration (L = 200 at the window midpoint, ±100
symmetric) stays.

So: **fix the text, not the numbers.**

- **`docs/DECISIONS.md`** — the deviation entry should name the knife edge
  explicitly: mean-field energy hits exactly 0.0 at boundary 4, so luck alone
  decides that boundary, and the extinction generation is therefore
  seed-sensitive (the scenario pins seed 42, so *it* is reproducible).
- **`pdsim/config/scenarios.py`** — check `the_growth_economy`'s
  `things_to_try`. If it says the all-defector population dies "at generation 5",
  that is **live, user-facing, and wrong**. Rephrase to describe the real
  behaviour and teach the mechanism, e.g.: *"switch the composition to 40 Always
  Defect and watch the population collapse over generations 4 to 6 — not all at
  once. Every defector is on the same average trajectory, so they all approach
  zero energy together; who actually crosses first is decided by participation
  luck, since under random_k some agents get drawn into more matches than
  others."* Keep it novice-readable.
- **`docs/specs/M10a-growth-economy.md`** — **frozen** (#62). Its mean-field
  trace and its "extinct at generation 5" stay as written; the DECISIONS entry is
  the record. Do not retro-edit it.
- **`docs/explainers/M10-growth-economy-explainer.md`** — add two or three
  sentences to §4 (Calibration) noting that a mean-field trace tells you *when*
  the average agent dies, not when the population does; under `random_k`,
  participation luck spreads a synchronized collapse over two or three
  generations, and it bites hardest exactly where the mean-field trajectory
  passes through zero. Match the existing voice: plain language, worked numbers.

## Task 3 — the bench's missing generations term

Your bench result is the interesting one, and it needs one more measurement
before it goes into the docs.

You measured economy overhead at **~5–10% under random_k** but **~50% under
round_robin**, and attributed the gap to persistent-history growth rather than
the boundary. That attribution is almost certainly right — but **the ~50% figure
is a function of how many generations the bench ran**, and the current cost model
in DESIGN §3.1 (`s/gen ≈ 7.5 µs × N × k × rounds`) has **no generations term at
all**. Under `energy_economy` + `round_robin` + unbounded `memory_depth`, it now
needs one.

The theory gives a sharp, falsifiable prediction. `view_of` copies the visible
history every round. Under round_robin every pair meets every generation, so at
generation G a history is ≈ `rounds × (G−1)` long, and the per-match copy cost is
≈ `rounds² × (G−1) + rounds²/2` against `rounds²/2` at G = 1 — a ratio of
**≈ 2G − 1**. Averaged over a run of `Ggens`, the copy component therefore scales
**linearly with `Ggens`**, while the base cost stays flat.

**The measurement:** run the economy bench under **round_robin** at two
generation counts — e.g. `generations = 20` and `generations = 100` — holding N,
k and rounds fixed, and report **s/gen** for each. Repeat each (the #65 noise
rule). Then do the same under **random_k**.

- **Prediction to test:** s/gen **rises with `Ggens` under round_robin** (if the
  copy component is ~0.5× base at 20 generations, expect roughly **2–3× the
  s/gen** at 100), and stays **flat under random_k**, where a specific opponent
  recurs with probability only ≈ `k/(N−1)` per generation so histories never grow.
- **If confirmed:** DESIGN §3.1 must say so explicitly — the cost model holds
  per-generation for imitation and for economy+random_k, but under
  economy+round_robin with unbounded memory the per-generation cost grows with
  the generation index, so a long round_robin economy run is superlinear in
  `generations`. Name `memory_depth` as the bound and point at the readout's
  memory-growth note.
- **If contradicted** — s/gen flat under round_robin too — then the ~50% is *not*
  history growth and the attribution in your report is wrong. Say so plainly and
  log it; that would mean the boundary bookkeeping is more expensive than
  expected under round_robin and is worth a look.

Either way this is a **measurement, not a refactor**. The vectorization trigger
stays **M18, review-at**. Bench output is environment-specific and is **never
committed**.

## Task 4 — finish

`ruff check . && ruff format .` and `pytest`. Then the usual ritual: `DOCS
CHANGED: <list>` with the new DECISIONS numbers called out, the coverage table
from Task 1, the Task 3 bench numbers, and (a) a summary, (b) files to stage,
(c) a suggested commit message. **Do not run `git commit`.**

Action required: paste this into Claude Code, then perform the git commit yourself once it reports the DECISIONS coverage table and presents the file list.
