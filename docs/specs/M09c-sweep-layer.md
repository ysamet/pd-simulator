Status: implemented (see DECISIONS #66-#71)

# M9.5a — Sweep/search layer: SweepSpec, parallel runner, Outcome Metrics Registry, persistence

Companion explainer: `docs/explainers/M9.5-sweeps-and-invasion.md` (the science
and the literature grounding; read it for the *why*). This spec is the *what*
and *how*. Read DECISIONS #46, #47, #48, #51, #56, #57, #58, #59, #62, #64, #65
and DESIGN §3.1/§5/§6.6/§8 first.

This is M9.5 **part a** — the headless core. The Streamlit **Sweep tab**
(authoring, tweaking, and launching a sweep from the app) is **M9.5b**, a
separate later spec. Nothing here builds UI. The sweep validation written here
is the single shared path the M9.5b tab will reuse (the #38/#48 pattern:
`ui.helpers.validation_messages` is Streamlit-free and reused by the CLI).

**Defining principle (#59):** this layer consumes only configs and recorded run
folders. It touches NO engine semantics — no `pdsim/core/` changes, no RNG draw
changes, no change to single-run behaviour. It is a config *generator* plus
post-processing over runs. Every member config is a fully-validated
`ExperimentConfig` reproducible from its own `config.yaml` (hard rule 8). The
sweep layer never weakens validation.

## Task 0 — subpackage layout

New package `pdsim/sweep/` with `__init__.py`, `spec.py`, `metrics.py`,
`runner.py`, `__main__.py`. This is an **orchestration-tier** subsystem (like
`run.py`/`bench.py`/`gendocs.py`, DECISIONS #48): it may import `config`,
`core`, `io`, and `viz`, but must stay **free of Streamlit** so M9.5b can import
from it. `python -m pdsim.sweep <spec.yaml>` runs `__main__.py`.

## Task 1 — refactor `run.py` to expose `execute_run`

Extract the run→record→finalize orchestration currently inside `main()` into a
public function:

```
execute_run(config, *, out_dir="runs", slug=None, scenario=None,
            export_charts=True, on_period=None, append_index=True) -> Path
```

- Constructs `RunRecorder(config, out_dir, slug, scenario, append_index=...)`,
  iterates `engine.run(config)` feeding `recorder.add(event)`.
- If `on_period` is not None, calls it on each `GenerationFinished`/
  `CycleFinished` (the CLI passes a printer; sweep workers pass `None`).
- On `KeyboardInterrupt`: `recorder.discard()` then re-raise (the caller decides
  the exit code — CLI keeps returning 130, DECISIONS #53).
- `recorder.finalize()`; then, only if `export_charts`, **lazily** import
  `pdsim.viz.charts` and call `export_run_charts`; return the folder.
- Make the `from pdsim.viz import charts` import **lazy** (inside the export
  branch) so importing `run.py` — and thus importing `execute_run` into sweep
  worker processes — does not pull plotly into every worker.

`main()` becomes a thin wrapper: parse → `_load` → `execute_run(...)` with an
`on_period` printer and `export_charts=True`, preserving CLI output and exit
codes (0/1/130). Existing `run.py` tests stay green.

`RunRecorder` gains `append_index: bool = True`; when False, `finalize()` skips
`_append_index` (writes parquet + cooperation + summary only). Rationale: sweep
members run in parallel and must NOT contend on a single shared
`runs/index.csv` (concurrent writers are out of scope, DECISIONS #47e). The CLI
default stays True (unchanged behaviour).

Tests: `execute_run` with `export_charts=False` writes a folder and no chart
HTML; with `append_index=False` writes no index row; `main()` behaviour and
exit codes unchanged.

## Task 2 — `SweepSpec` (`pdsim/sweep/spec.py`)

A pydantic model family mirroring `ExperimentConfig` conventions (frozen,
`extra="forbid"`, plain-language errors). Shape:

- **SweepSpec**: `name` (safe lowercase token); exactly one of `base` (path to a
  config YAML) or `base_scenario` (registered scenario name); `composition`
  (a `CompositionAxis`, optional); `parameters` (list of `ParameterAxis`,
  optional); `seeds` (non-empty list of ints); `metrics` (non-empty list of
  `MetricRef`).
- **CompositionAxis** (the three-bucket model): `vary` (one strategy machine
  name — a single varying invader in M9.5a, but model `vary` so a future set is
  a small change, per companion §3.2); `counts` (non-empty list of ints ≥ 0);
  `fixed` (dict strategy→count, default `{}`); `fill` (dict strategy→percentage,
  percentages summing to 100).
- **ParameterAxis**: `key` (a Parameter Registry key); `values` (non-empty list).
- **MetricRef**: `metric` (registered metric name) plus its metric-specific
  params (e.g. `strategy`, `threshold`, `k`).

`load_sweep_spec(path) -> SweepSpec` (YAML), mirroring `load_config`.

**Shared validation** — `sweep_validation_messages(spec) -> list[str]`, the
Streamlit-free analog of `ui.helpers.validation_messages`, so the CLI and the
M9.5b tab share ONE path. Plain-language checks:
- exactly one of `base` / `base_scenario`;
- composition buckets disjoint (`vary` not in `fixed`/`fill`; `fixed` ∩ `fill`
  empty);
- all strategy names exist in the roster;
- Σ fill percentages == 100 (int or float, with a small float tolerance);
- at the LARGEST vary count, `vary_max + Σfixed ≤ base.population.size` (else a
  plain error naming the overflow — this is where a negative fill would arise);
- if the remainder (`size − vary − Σfixed`) can exceed 0 anywhere in the sweep,
  `fill` must be non-empty;
- each ParameterAxis `key` exists in the Parameter Registry and each value
  passes `validate_value(key, value)`;
- `seeds` non-empty; `metrics` non-empty; each metric name registered and its
  params valid.

**Expansion** — `expand(spec) -> list[MemberPlan]`, where `MemberPlan` carries
`run_index` (0-based), the fully-built validated `ExperimentConfig`, and the
axis-value dict for the summary row. Expansion is the **cross product** over
composition `counts` × each ParameterAxis `values` (in listed order) × `seeds`,
in a PINNED deterministic order — composition outermost, parameters in listed
order, seeds innermost — which fixes `run_index` (document this order; it is a
reproducibility contract). For each combination: load the base (via
`load_config` or the scenario's config), dump to a mutable dict, set
`population.composition` to the resolved three-bucket integer composition
(Task 2a), apply each parameter override by its registry key's section→field
mapping (reuse the config layer's existing mapping; top-level `run.*` keys map
to top-level fields), set `seed`, then `ExperimentConfig.model_validate(dict)` —
FULL validation. Any failure is a hard error naming the `run_index` and the
offending combination, raised BEFORE any run executes (fail fast; the
"generator, never a weakener" rule).

**Task 2a — three-bucket resolution + largest-remainder** (pure, hard-tested):
`resolve_composition(size, vary, vary_count, fixed, fill) -> dict[str, int]`.
`remainder = size − vary_count − sum(fixed.values())`; if `remainder < 0` raise
(defensive — caught earlier). Allocate `remainder` across `fill` by percentage
using the **largest-remainder rule**: give each fill strategy
`floor(pct/100 · remainder)`, then hand the leftover seats one at a time to the
largest fractional parts, breaking ties by **ascending strategy machine name**
(deterministic). Merge `vary` + `fixed` + `fill` counts; drop zero-count
entries (configs require positive counts); the result sums to `size`. Tests:
the worked example N=100, vary `tit_for_tat`=2, fill 30% `always_defect` / 30%
`always_cooperate` / 40% `generous_tit_for_tat` → `always_cooperate` 30,
`always_defect` 29, `generous_tit_for_tat` 39 (the leftover seat's .4/.4 tie
breaks to `always_cooperate` by name); `remainder = 0` endpoint (fill drops
out); a non-even remainder; a single 100% fill.

## Task 3 — Outcome Metrics Registry (`pdsim/sweep/metrics.py`)

The **fourth** instance of the registry idiom (DESIGN §5; after the Parameter,
Strategy, and Scenario registries). Mirror `ScenarioInfo`:

- `OutcomeMetricInfo` (frozen dataclass, slots): `name` (token), `display_name`,
  `description` (plain-language, MANDATORY — hard rule 3's mirror), `params`
  (a lightweight tuple of param declarations: name, kind, description, optional
  default — NOT full `ParameterSpec`; the sweep UI is M9.5b), `compute`
  (callable). `register_metric` / `get_metric` / `all_metrics` mirroring the
  scenario registry (unique names; registration order = display/doc order);
  `__post_init__` validates the name pattern and a non-empty description.
- `compute(run: LoadedRun, **params) -> float | None`. Operates on the loaded
  run — `io.results.load_run` returns `LoadedRun(config, timeseries, summary)`
  — reading `timeseries.composition` / `timeseries.periods` /
  `config.population.size` and never raw parquet, so metrics apply retroactively
  to any recording and inherit schema compatibility (#47/#65). `None` means
  "not applicable / undefined" (renders as a gap). Strategy-param names are
  checked against the run's roster at compute time with a plain error.

Seed metric set:
- `final_share(strategy)` — `composition[strategy][-1] / size` (0.0 if the
  strategy never appeared).
- `fixation_flag(strategy)` — 1.0 if `composition[strategy][i] == size` for any
  period, else 0.0.
- `time_to_fixation(strategy)` — first period index with `count == size`; paired
  with `fixation_censored(strategy)` (1.0 if never fixed, else 0.0). Two-column
  survival-analysis encoding, no sentinels (companion §3.4). A run that never
  fixes reports `time = periods_completed`, `censored = 1`.
- `mean_share_last_k(strategy, k)` — mean of `count/size` over the last
  `min(k, len)` periods.
- `ever_exceeded(strategy, threshold)` — 1.0 if `count/size ≥ threshold` at any
  period (quasi-fixation; companion §3.3).
- `held_above_for(strategy, threshold, k)` — 1.0 if `count/size ≥ threshold` for
  `k` consecutive periods anywhere, else 0.0.
- `min_cooperation()` and `final_cooperation()` — over
  `timeseries.cooperation_overall`, ignoring `None`; return `None` when the
  cooperation series is empty (schema-1 runs), the collapse metrics #65 enabled.

Tests: hand-built/synthesized runs exercising each metric, including censoring
both ways, a never-appeared strategy, and an empty-cooperation (schema-1) run
→ `None`.

## Task 4 — parallel runner + persistence (`pdsim/sweep/runner.py`, `pdsim/sweep/__main__.py`)

Layout under `sweeps/<name>/` (name from the spec; `_unique`-suffixed like run
folders — reuse/mirror `io.results._unique_folder`):
- `sweep_spec.yaml` — the spec copied verbatim at START (write-up-front
  reproducibility, the #47(d) analog).
- `runs/<NNN>_<axis-slug>/` — member run folders, one per `run_index`, written
  by `RunRecorder` with `out_dir=sweeps/<name>/runs`, `append_index=False` (no
  shared-index contention), `export_charts=False` (member chart HTML is waste,
  #48). Each member's `config.yaml` makes it independently reproducible.
- `sweep_status.json` — the SINGLE-WRITER progress + resume + (future) app-poll
  file, rewritten by the PARENT on every member completion:
  `{name, total, completed, failed, running, started_at, updated_at,
  per_index: {run_index: {status: done|failed, folder, error?}}}`. Workers never
  write it — the parent owns `imap_unordered` completions, so there is no
  concurrency on it.
- `sweep_summary.parquet` — one row per `run_index`, WIDE format: `run_index`,
  `run_id` (folder name), `status`, `seed`, one column per varied axis (the
  composition axis → a column named for the vary strategy, e.g. `tit_for_tat`,
  holding its count; each ParameterAxis → a column named by its registry key),
  then one column per metric instance (e.g. `time_to_fixation[tit_for_tat]`).
  Rows sorted by `run_index` (never completion order). Written by the parent
  AFTER all members finish, by `load_run`-ing each successful member and
  computing the spec's metrics. Failed members keep their axis columns with null
  metrics and `status="failed"`.
- `sweep_summary.json` — `{schema_version: 1, name, spec, total, completed,
  failed, axis_columns, metric_columns}` — the #47 schema guard, fourth
  application; loaders reject newer versions.
- one metric-vs-axis chart HTML per (metric × primary axis) via the Task 5
  builder, written by the parent.

Runner mechanics: `multiprocessing.Pool(processes=…)` with `imap_unordered`
over member plans. The worker is a TOP-LEVEL, picklable function (Windows spawn
re-imports and pickles — no closures, no lambdas; DECISIONS #51's environment
note): it receives the member's config as a plain dict (re-validated in the
worker for spawn-safety) plus its `run_index` and target paths, calls
`execute_run(config, out_dir=<sweep>/runs, slug=…, export_charts=False,
on_period=None, append_index=False)`, and returns
`(run_index, "done", folder_name, None)`; on ANY exception it returns
`(run_index, "failed", None, short_message)` — a failing member NEVER kills the
sweep (failure isolation, #59). The parent updates `sweep_status.json` on each
completion and prints one plain line per completed member
(`[37/300] tit_for_tat=8 seed=12 → ok 4.2s` / `→ FAILED: <message>`), unless
`--quiet`.

**Resume:** before dispatching, if `sweeps/<name>/` already exists, the parent
reads `sweep_status.json` and SKIPS `run_index`es already `done` (finalized
member folder present); partial/failed indices are re-dispatched. Automatic when
the folder exists; `--resume` makes intent explicit. OneDrive makes mid-sweep
interruption likelier (#51), so resume is in scope for M9.5a.

CLI (`pdsim/sweep/__main__.py`, `python -m pdsim.sweep <spec.yaml>`): flags
`--out` (default `sweeps/`), `--processes` (default `os.cpu_count()-1`, min 1),
`--resume`, `--quiet`. Validation errors print the plain
`sweep_validation_messages` sentences (never tracebacks) and exit 1; Ctrl+C
exits 130 leaving a resumable partial (finalized members stay; status reflects
reality). Document the command in `CLAUDE.md`'s Commands section. Standing note
(#51/#59): document that for large campaigns pointing `--out` outside the
OneDrive-synced tree is advisable; do NOT hardcode a path.

## Task 5 — metric-vs-axis chart (`pdsim/viz/charts.py`)

New PURE builder `sweep_metric_chart(summary_frame, axis_column, metric_column,
*, replicate_column="seed") -> plotly Figure`: x = axis values; at each axis
value, aggregate the metric across replicate seeds → a mean line plus a shaded
band (min–max, or ±1 std) showing replicate spread (companion §4). y-label =
the metric's display name. Pure (frame in, Figure out; no Streamlit) so the
M9.5b tab reuses it. A thin `export_sweep_charts(summary_frame, folder, axes,
metrics)` writes one HTML per (metric × axis), called by the runner
(orchestration may import viz; `pdsim/io` and `pdsim/sweep` persistence code
must not — keep plotting in `viz`, invoked from the runner). Tests: the builder
returns a Figure for a small synthetic summary frame and its band reflects
replicate spread.

## Task 6 — docs generation (`pdsim/gendocs.py`)

Extend `generate_parameters_markdown()` with a new `## Outcome metrics` section
rendered from `all_metrics()` (name, display name, description, each param's
name/kind/description) in registration order — deterministic, so the existing
drift test (DECISIONS #56) covers it automatically. Regenerate
`docs/PARAMETERS.md` (`python -m pdsim.gendocs`) and stage it. No new doc
mechanism — a new section fed by the fourth registry.

## Task 7 — the canonical example

Create `examples/sweeps/tft_invasion.yaml`: a fully-commented reference sweep —
`base_scenario: reciprocity_takes_over` (or a small inline base), composition
`vary: tit_for_tat`, `counts: [2,4,6,8,10,12,14,16,20]`, `fill: {always_defect:
100}`, `seeds: [1..10]`, metrics `final_share(tit_for_tat)`,
`time_to_fixation(tit_for_tat)`, `fixation_flag(tit_for_tat)`. Sizes/generations
small enough that the whole sweep runs in a couple of minutes. This is the file
the companion doc and the Validation section point at.

## Validation

This layer is inherently headless — the runner is a batch CLI, exactly like
`python -m pdsim.bench`, so CLI validation is legitimate here (DECISIONS #61).
The APP-based validation (authoring/tweaking/launching a sweep through a
Streamlit **Sweep tab**) is **M9.5b**'s, deliberately deferred. With the venv
active:

1. `python -m pdsim.sweep examples/sweeps/tft_invasion.yaml --out sweeps`.
   Confirm plain per-member progress lines and a `sweeps/tft_invasion/` folder
   holding `sweep_spec.yaml`, `runs/` (one finalized member per count × seed),
   `sweep_status.json` (`completed == total`, `failed == 0`),
   `sweep_summary.parquet`, `sweep_summary.json` (`schema_version` 1), and a
   metric-vs-axis chart HTML.
2. Inspect `sweep_summary.parquet` (a two-line pandas snippet is fine): one row
   per `run_index` with the `tit_for_tat` count column, `seed`, `status`, and
   the metric columns. `final_share` rises from ≈0 at low invader counts toward
   ≈1 at high counts — the invasion threshold (companion §1.4).
3. Open the metric-vs-axis chart HTML: mean `final_share` vs invader count with
   a replicate-spread band.
4. Reproducibility: re-run with `--resume` — finalized members are SKIPPED;
   delete two member folders and re-run `--resume` — only those two re-run. Run
   one member's config standalone (`python -m pdsim.run
   sweeps/tft_invasion/runs/<one>/config.yaml`) — it reproduces (hard rule 8).
5. Temporarily set the fill to sum to 90% — the sweep fails
   `sweep_validation_messages` BEFORE any run executes, with a plain sentence.
6. Confirm `docs/PARAMETERS.md` gained an `Outcome metrics` section and the
   drift test passes.

Automated tests complement (never replace) the above: `resolve_composition`
worked examples incl. the tie-break and remainder=0; SweepSpec validation (each
rule) + expansion determinism + every expanded member validates; each metric
incl. censoring both ways and schema-1 `None`; `execute_run` export/append_index
flags; runner end-to-end on a tiny 2×2 sweep producing a summary parquet with
the right columns and a resumable status file; failure isolation (one bad member
→ sweep completes, row marked failed); the sweep_summary schema guard.
