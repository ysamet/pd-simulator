Status: implemented (see DECISIONS #65)

# M9b — Pairwise cooperation-rate recording, schema_version 2

Context: M9a landed (selection rules, ScoreAccounting, benchmark rider — 440
tests, DECISIONS #62–#64). This spec implements DECISIONS #60 and completes M9
per docs/ROADMAP.md. Read DECISIONS #20, #34, #35, #37, #44, #47, #57, #60 and
DESIGN §4/§8 before implementing.

Hard constraint: this change is bookkeeping and observability ONLY. No RNG draw
is added, removed, or reordered anywhere (the #44 precedent). A regression test
pins a known seeded trajectory byte-identical before/after (the #64 pattern —
capture the trajectory from pre-change code first).

## Task 1 — match-phase bookkeeping

Record executed-action (#20) cooperation at strategy-pair resolution: per
period, for every ordered pair (actor strategy, opponent strategy), count
actions and cooperations. Each round contributes two actor records (one per
agent). Keys are strategy machine names. PINNED asymmetry (log in the DECISIONS
entry): evolution counts reset each generation (per-generation rates, matching
GenerationFinished's per-generation character); tournament counts accumulate
across cycles (cumulative rates, matching CycleFinished's cumulative character,
#34/#35).

## Task 2 — event payload extension

GenerationFinished and CycleFinished gain a cooperation field: mapping
(actor_strategy, opponent_strategy) → (cooperation_rate, actions_counted). Rate
plus count makes per-strategy and population aggregates exactly recomputable by
actions-weighted aggregation (#60). RunTimeseries folds these into: per-pair
series, per-actor-strategy aggregate series, and an overall population
cooperation-rate series.

## Task 3 — persistence: schema_version 2

- New sibling file cooperation.parquet in every run folder — the future that
  #47(c)'s naming convention reserved. Columns: period, actor_strategy,
  opponent_strategy, cooperation_rate, actions_counted. Raw rows only; all
  aggregates are recomputed on load (#47 raw-vs-derived rule).
- summary.json schema_version becomes 2 and gains a headline cooperation figure
  (final overall cooperation rate) for run cards. Loaders accept BOTH 1 and 2:
  a schema-1 folder simply has no cooperation data and renders without the
  cooperation chart — no error, no migration; versions > 2 are rejected as
  before. Round-trip tests for both schema versions, including loading a
  synthesized schema-1 folder.

## Task 4 — cooperation chart

New pure builder in viz/charts.py: cooperation rate over time — an overall
population line plus per-actor-strategy aggregate lines (existing strategy
color map; y-axis fixed 0–1). The full pair matrix is rendered as plain
final-summary table rows (the #37 convention), NOT a figure — a pair-matrix
heatmap is deferred (it becomes the M12 in-group/out-group diagnostic). Wire
the chart into: the live UI (redrawn on period events, both modes), the
results browser (schema-2 runs only), and viz.charts.export_run_charts.

## Task 5 — overhead check

Compare the pre-change bench output (captured before implementation) against
the same command after the change, same machine, and report the bookkeeping's
per-generation overhead in the final summary. If material (roughly >10%), say
so prominently — do not optimize speculatively.

## Validation

App-first (per DECISIONS #61), with the venv active:
streamlit run pdsim/ui/app.py

1. Load "Noise Breaks the Grim" and run. A cooperation-rate chart appears
   alongside the existing charts: an overall population line plus
   per-strategy lines, y-axis 0–1. Expected shape: cooperation degrades as
   noise poisons Grim Trigger's relationships, then recovers as forgiving
   reciprocators spread — a shape composition alone cannot show (#60's
   motivating observation).
2. Set noise to 0 on the same scenario and re-run: the cooperation lines sit
   near 1.0 once reciprocity dominates — the contrast confirms the chart is
   measuring executed actions, not composition.
3. Load "The Classic Tournament" and run: the chart renders cumulative rates
   (tournament asymmetry) — lines flatten over cycles as totals stabilize.
4. Final-summary area: the pair matrix appears as table rows (actor,
   opponent, rate, actions counted) — e.g. tit_for_tat vs always_defect
   visibly lower than tit_for_tat vs tit_for_tat.
5. Results browser: the just-recorded run re-renders WITH the cooperation
   chart; a pre-M9b run from before this change renders WITHOUT it and
   without any error — the schema-1 compatibility path.
6. Record a run and confirm its folder contains cooperation.parquet next to
   timeseries.parquet, and summary.json says schema_version 2 with a headline
   cooperation figure.

Headless (legitimately CLI): the Task 5 bench before/after comparison.
