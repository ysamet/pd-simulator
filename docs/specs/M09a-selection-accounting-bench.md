Status: implemented (see DECISIONS #63, #64; convention entry #62)

# M9a — Selection rules, score accounting, benchmark rider

Context: v1 complete (M8, 382 tests). M9 is split: M9a (this spec) and M9b
(cooperation-rate recording per DECISIONS #60, separate spec/session). Read
DECISIONS #9, #26, #31, #32, #34, #44, #57, #58 and DESIGN §2.7 before
implementing.

## Task 1 — four new SelectionRule implementations

All plug into the existing SelectionRule ABC (pdsim/core/selection.py), selected
via the registry choice dynamics.selection_rule. These semantics are PINNED
seeded-history contracts (the #23/#32/#57 pattern): log them in DECISIONS (one
entry for all four is fine), including draw order, tie-breaks, edge cases. Any
future change is breaking and requires a new entry. Data-conditional draw counts
are acceptable where noted (the #26 precedent); tie-breaks are always
deterministic, never a random draw.

All rules keep #32's frame: all N slot decisions are made against the same scored
population and applied simultaneously; the mutation phase runs identically after
every rule; Fermi is untouched. The score each rule consumes is the EFFECTIVE
score supplied by score accounting (Task 2).

1. proportional — fitness-proportional (roulette). Weights w_i = s_i − min(s)
   (scores can be negative; the shift is mandatory). All-zero weights (all scores
   equal) ⇒ uniform fallback. Per slot, in slot order: exactly one weighted index
   draw; the slot adopts that agent's strategy. Always N draws.

2. tournament_k — tournament selection. Machine name deliberately NOT
   "tournament" (must not collide with run.mode="tournament"; the registry
   description must disambiguate the two in plain language). New registry
   parameter dynamics.selection_tournament_k (int ≥ 2), cross-parameter validated
   k ≤ N with a plain-language error (#57 precedent). Per slot, in slot order:
   one without-replacement draw of k candidate indices (rng.choice over the
   population in agent-id order, size=k, replace=False); winner = highest
   effective score among candidates; ties broken by earliest position in the
   drawn array. The slot adopts the winner's strategy.

3. truncation — elitist. New registry parameter
   dynamics.selection_elite_fraction (float q, 0 < q ≤ 1). elite_count =
   max(1, floor(q·N)); elite set = top elite_count by effective score, boundary
   ties broken by lower agent id. Per slot, in slot order: one uniform draw from
   the elite set.

4. threshold_cloning. New registry parameter
   dynamics.selection_threshold_multiplier (float θ ≥ 0, default 1.0, upper
   bound 10). Survivor set = agents with effective score ≥ θ · mean effective
   score; if empty (possible when θ > 1), survivor set = all agents tied at the
   maximum. Slots whose incumbent is a survivor KEEP their strategy and consume
   no draw; each non-survivor slot, in slot order, consumes one uniform draw
   from the survivor set and adopts that survivor's strategy. Data-conditional
   draw count — cite the #26 precedent in the DECISIONS entry.

UI: new rules' parameters greyed unless their rule is selected — extend
ui/helpers.greying (#57 pattern, keyed off the selection-rule widget's current
value), unit-tested Streamlit-free. All new registry entries get novice-first
descriptions; regenerate docs/PARAMETERS.md (drift test enforces).

Tests: decision-style unit tests per rule with hand-constructed score vectors,
covering at least: negative scores under proportional; all-equal scores;
truncation boundary ties; threshold_cloning empty-survivor fallback;
tournament_k with k = N. Plus per-rule seeded-stability tests (same config +
seed ⇒ identical composition trajectory), cross-parameter validation tests,
greying tests.

## Task 2 — ScoreAccounting options

DESIGN §2.7/§6.1 name the ScoreAccounting seam. If the ABC exists, implement
against it; if it exists only as prose, create it now (align §2.7's wording
with what you build; log the interface decision).

PINNED semantics (log as a DECISIONS entry, including the rejected alternative):

- Accounting maintains per-slot state and supplies the EFFECTIVE score selection
  consumes. Everything else unchanged: raw per-generation scores, the #31
  resets, event payloads, charts, persistence. Accounting is invisible outside
  the selection phase in M9. (Surfacing effective scores in events/charts is a
  possible later addition — note, don't build.)
- Accounting state belongs to the AGENT SLOT and survives strategy switches
  from selection or mutation. Rationale: models fitness inertia of the lineage
  occupying the slot; reset-on-switch is ill-defined (copying your own strategy
  from a same-strategy model is not a detectable switch). Rejected alternative:
  reset accounting state on strategy change.
- Rules (registry choice dynamics.score_accounting):
  - per_generation (default): effective = this generation's raw score. Exactly
    current behavior.
  - sliding_window: new registry parameter dynamics.accounting_window (int
    W ≥ 1). Effective = MEAN of the last min(W, generations so far) raw
    generation scores, current included. Mean, not sum: keeps scale comparable
    across W values and during warmup (β interacts with score scale). W = 1 ≡
    per_generation.
  - exponential_discount: new registry parameter dynamics.accounting_discount
    (float λ, 0 ≤ λ < 1). effective(t) = (1−λ)·raw(t) + λ·effective(t−1);
    effective(0) = raw(0). EMA form is scale-stable; λ = 0 ≡ per_generation.
- Greying (#34): W greyed unless sliding_window; λ greyed unless
  exponential_discount; the accounting choice and its parameters greyed
  entirely in tournament mode — ignored-but-valid, never a validation error.
- RNG: accounting consumes zero draws. With per_generation selected, every
  seeded v1 run is byte-identical to before this change — regression test
  pinning a known seeded trajectory required.

Tests: hand-computed sequences for both rules (warmup; W = 1 and λ = 0
equivalences); slot-carry under strategy switch; tournament-mode
ignored-parameter behavior; the v1-equivalence regression test.

## Task 3 — benchmark rider

New top-level pdsim/bench.py, runnable as python -m pdsim.bench (#48 convention;
imports config/core only — no UI, no plotting). Purpose (#58): make the
vectorization trigger empirical. Defaults: grid of N in {50, 100, 200, 400} ×
matcher in {round_robin, random_k(k=5)}, evolution mode, fixed 50-round matches,
default roster mix, 3 generations per cell with the first discarded as warmup;
report median wall-clock seconds per generation per cell as a plain stdout
table; --out PATH writes CSV. Grid overridable via CLI flags. Output is
environment-specific and never committed (gitignore any default output
location). Document the command in CLAUDE.md's Commands section; add one
sentence to DESIGN §3.1 naming the rider as the vectorization-trigger data
source.

## Validation

*(Section added at spec time per the DECISIONS #61/#62 convention; it was not
part of the drafted spec text.)*

With the venv active, launch the app: `streamlit run pdsim/ui/app.py`.

1. **Selection rules in the app.** Load **Drift vs Meritocracy**. In the
   Dynamics expander, open the Selection rule selectbox — it should list all
   five rules with tooltips. Confirm the greying dance: with `fermi` selected,
   β is active and the three new parameters (tournament size k, elite
   fraction, threshold multiplier) are greyed with explanatory tooltips; pick
   `tournament_k` and watch k un-grey (and β grey out); same pattern for
   `truncation` → elite fraction and `threshold_cloning` → threshold
   multiplier. Run the scenario once under `truncation` with elite fraction
   0.2: the composition chart should sort sharply toward the winners much
   faster than the β = 0.001 Fermi baseline — an elitist rule is strong
   selection regardless of β.
2. **Score accounting in the app.** Still in Dynamics: the Score accounting
   selectbox shows three options; window W is greyed unless
   `sliding_window`, discount λ greyed unless `exponential_discount`. Load
   **Noise Breaks the Grim**, set accounting to `sliding_window` with W = 5,
   and run: the run completes normally and charts render (accounting changes
   selection pressure, not the charts' meaning). Switch Run mode to
   tournament: the whole Dynamics section, accounting included, greys out.
3. **Reproducibility.** Run any scenario twice with the same seed under a
   non-default rule (e.g. `proportional`) — identical charts both times.
4. **Benchmark rider (inherently headless — CLI is the right venue).** Run
   `python -m pdsim.bench --sizes 50,100 --generations 3` and confirm a
   table of seconds-per-generation appears with one row per (N, matcher)
   cell, random_k rows faster than round_robin at equal N. `--out bench.csv`
   writes the same rows as CSV.
