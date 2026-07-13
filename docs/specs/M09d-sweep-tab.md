Status: implemented (see DECISIONS #72-#74)

# M9.5b — The Sweep tab: author, launch, and monitor sweeps from the app

Companion documents: `docs/specs/M09c-sweep-layer.md` (the headless core this
tab drives) and `docs/explainers/M9.5-sweeps-and-invasion.md` §4 (the frozen
intent: "authoring, tweaking, and launching a sweep *from within the app* …
the *execution* stays headless either way"). Read DECISIONS #59 and #66–#71
first. This milestone builds **no new engine or sweep-core code** — M9.5a
delivered all of that. It is a UI-only milestone plus a Streamlit-free helper
module and its tests.

## Frozen scope

**IN scope for M9.5b:**

- A third Streamlit tab, **"Sweep"**, that authors the COMPLETE SweepSpec
  surface (name, base scenario/config, one composition axis, N parameter
  axes, seeds, N metrics), validates it through the ONE shared path
  `pdsim.sweep.spec.sweep_validation_messages`, launches the runner as a
  detached subprocess, and monitors it via a manual "Refresh status" button
  reading the sweep's own `sweep_status.json` — plus the single headline
  metric-vs-axis chart once `sweep_summary.parquet` exists.

**OUT of scope for M9.5b** (deferred to a dedicated follow-on "sweep
browser" increment already parked on the ROADMAP): member-run drilldown from
the tab, multi-sweep interactive browsing, multi-curve overlays,
summary-table filtering, side-by-side member comparison. The tab stops at
status + one headline chart. The existing Results browser is NOT wired to
scan `sweeps/<name>/runs/`.

## Defining principles

1. **The tab changes NOTHING about execution.** Launch is literally "write
   the YAML the user could have written by hand, then run the command they
   could have typed": `subprocess.Popen([sys.executable, "-m",
   "pdsim.sweep", <spec-path>, "--out", <out-dir>])`. A sweep launched from
   the tab is therefore resumable, inspectable, and killable by the
   identical means as one launched from a terminal. (DECISIONS #59: the
   sweep layer is a config generator; the tab is a config *author* on top
   of it.)

2. **ONE validation path** (the #38/#48 reuse rule). The tab calls
   `sweep_validation_messages(spec)` — never a reimplemented copy.
   Structural errors from building the pydantic models are surfaced with
   the SAME plain-message extraction the Run lab uses
   (`helpers.validation_messages` works on any pydantic `ValidationError`).

3. **Logic lives in a Streamlit-free, tested module; the tab is a thin
   rendering shell** (the existing `helpers.build_config` /
   `validation_messages` split, applied again). No branch worth testing may
   live inside a function that imports streamlit.

4. **`sweep_status.json` is the app-poll surface it was designed to be
   (#70).** The tab reads it; it NEVER writes it. The runner subprocess
   remains its sole writer.

## Task 0 — new Streamlit-free helper module: `pdsim/ui/sweep_helpers.py`

Importable WITHOUT streamlit (like `pdsim/ui/helpers.py`; asserted by a
subprocess import test). Holds every piece of tab logic worth testing:

- `parse_int_list(text) -> list[int]` — comma/space-separated ints;
  plain-language `ValueError` on a bad token; empty text → `[]`.
- `build_range(start, stop, step) -> list[int]` — inclusive-of-start range
  for the counts/seeds convenience builders (stop included when the step
  lands on it); plain error on non-positive step or `stop < start`.
- `parse_value_list(key, text) -> list[ParamValue]` — parse a parameter
  axis's text field by the registry spec's kind (int/float/bool/choice);
  plain error naming the bad token. (Companion to
  `validate_parameter_values`; parsing is a branch worth testing, so it
  lives here, not in the tab.)
- `validate_parameter_values(key, values) -> list[str]` — run each value
  through `pdsim.config.registry.validate_value(key, value)`, collecting
  plain messages (belt-and-braces before `sweep_validation_messages`, so
  per-axis errors show next to their widget).
- `build_sweep_spec(fields) -> SweepSpec` — plain dict of authored values
  (name; base_kind + base_scenario/base_path; optional composition dict
  with vary/counts/fixed/fill; list of parameter-axis dicts {key, values};
  seeds; list of metric dicts {metric, **params}) → the SweepSpec model
  family. Raises pydantic `ValidationError` on structural problems (caller
  extracts messages via `helpers.validation_messages`).
- `base_population_size(fields) -> int | None` — the base config's
  population size for the live composition preview (`None` when the base
  cannot be loaded — the preview just doesn't render).
- `authored_spec_path(out_dir, name) -> Path` and
  `write_authored_spec(spec, path) -> Path` — persist the authored spec to
  a real, inspectable file the spawned CLI reads:
  `<out_dir>/<name>.authored.yaml`, via `pdsim.sweep.spec.save_sweep_spec`.
  A NAMED file, not a tempfile, so the user can re-launch it from the CLI
  (reproducibility ethos). The runner's own verbatim copy into
  `sweeps/<name>/sweep_spec.yaml` remains the canonical record.
- `launch_log_path(out_dir, name) -> Path` — `<out_dir>/<name>.launch.log`,
  the subprocess's stdout/stderr target (exists from launch time).
- `build_launch_command(spec_path, out_dir) -> list[str]` — the exact argv
  `[sys.executable, "-m", "pdsim.sweep", str(spec_path), "--out",
  str(out_dir)]`. Pure and unit-testable; the tab passes it to
  `subprocess.Popen`.
- `sweep_folder_exists(out_dir, name) -> bool` — whether `sweeps/<name>/`
  already exists (drives the resume-awareness notice).
- `read_sweep_status(out_dir, name) -> dict | None` — load
  `sweep_status.json` if present, else `None`; a mid-write/corrupt read
  also returns `None` (the user just refreshes again).
- `status_rows(status) -> list[dict]` — the compact per-index table
  (run_index, status, folder, error), sorted by run_index.
- `list_sweep_names(out_dir) -> list[str]` — existing sweep folder names,
  newest first (for the monitor selectbox); `[]` when the dir is missing.
- `read_sweep_summary_meta(out_dir, name) -> dict | None` — load
  `sweep_summary.json` if present; rejects a newer `schema_version` with a
  plain `ValueError` (the #47 guard, honored on read).
- `metric_display_labels(meta) -> dict[str, str]` — summary metric column →
  the metric's registry display name (for the chart's y-label).

**Two tiny additions to `pdsim/sweep/spec.py`** (not new sweep-core
*mechanism* — one bug fix and one refactor, both in service of the reuse
rule):

- `sweep_spec_yaml(spec) -> str` — the YAML text of a spec;
  `save_sweep_spec` now writes this same string, so the tab's YAML preview
  and download share the one serialization path.
- `sweep_validation_messages` gains the **name rule**: `_NAME_PATTERN` was
  defined in M9.5a ("safe lowercase token") but never wired to a check —
  dormant dead code. It now yields a plain message for a malformed name, so
  the CLI and the tab both get it from the shared path.

Every function gets direct unit tests in `pdsim/tests/test_sweep_ui.py`
(new): parse_int_list good/bad; build_range good/bad; build_sweep_spec
producing a valid spec that round-trips through
`sweep_validation_messages == []` for the tft_invasion shape (and expands
to 90 members), and a malformed shape raising `ValidationError`;
authored_spec_path/write_authored_spec writing a file that
`load_sweep_spec` reads back equal; build_launch_command's exact argv;
read_sweep_status on a hand-written status file and on an absent one
(`None`).

## Task 1 — the Sweep tab authoring UI (`pdsim/ui/app.py`)

Add `_sweep_tab()` and call it from `main()` as a THIRD tab:

    tab_lab, tab_browser, tab_sweep = st.tabs(
        ["Run lab", "Results browser", "Sweep"])

A module constant mirrors `RUNS_DIR`: `SWEEPS_DIR =
Path(os.environ.get("PDSIM_SWEEPS_DIR", "sweeps"))` (the env override
exists for tests, the #49 idiom). `_sweep_tab` authors the full surface,
top to bottom; every branch worth testing delegates to `sweep_helpers`.
Reuse the existing registries exactly as the Run lab does:
`all_scenarios` (config.scenarios), `all_strategies` (core.strategies),
`helpers.panel_specs()` for parameter keys, `all_metrics`/`get_metric`
(sweep.metrics).

Sections:

- **(a) Name** — text input for the sweep name (safe lowercase token; the
  SweepSpec name rule in the shared validator flags violations).
- **(b) Base** — radio {"From a scenario", "From a config file"}. Scenario
  → selectbox over `all_scenarios()` display names, mapped to
  `base_scenario` (the machine name). Config file → text input for a path
  → `base`. Mirrors `_scenario_area`'s selectbox idiom.
- **(c) Composition axis** — an "Include a composition axis" checkbox gates
  an expander. Inside: `vary` (selectbox over strategy machine names);
  `counts` (text input parsed by `parse_int_list`, PLUS a start/stop/step
  range builder whose "Fill counts" button writes `build_range(...)` into
  the counts field via session state); **bucket assignment** for the
  REMAINING strategies — one row per strategy with a bucket radio
  {none, fixed, fill} and a value field (an int count for "fixed", a
  percentage for "fill"). This makes the three-bucket disjointness
  STRUCTURAL — a strategy can be in at most one bucket by construction, so
  the "buckets disjoint" rule is impossible to violate from the UI.
  Live preview (pedagogical, cheap, and it exercises the real engine
  code): when counts and buckets are well-formed, call
  `pdsim.sweep.spec.resolve_composition(size, vary, max(counts), fixed,
  fill)` and show the resolved integer composition at the LARGEST count as
  a caption (the arithmetic the explainer §4 preview tool shows). Show the
  running fill-percentage sum and warn when ≠ 100.
- **(d) Parameter axes** — an "Add parameter axis" pattern backed by a list
  in session state. Each axis: a selectbox over `helpers.panel_specs()`
  keys (minus `run.seed` — seeds are their own first-class axis, and a
  `run.seed` parameter axis would be silently overwritten by the seed
  loop) + a text input for its values (parsed via `parse_value_list`,
  validated via `validate_parameter_values`, per-axis plain errors shown
  next to the widget). A remove button per axis.
- **(e) Seeds** — text input (`parse_int_list`) plus a range-builder
  convenience (start, count → `build_range(start, start + count − 1, 1)`).
- **(f) Metrics** — multiselect over `all_metrics()` display names; for
  EACH selected metric, render its declared `MetricParam`s (a strategy
  selectbox for a `"strategy"` param; number inputs for int/float params
  such as `threshold`/`k`); build one MetricRef-shaped dict each.
- **(g) Validate + expansion size** — on every render, attempt
  `sweep_helpers.build_sweep_spec(fields)`; on pydantic `ValidationError`
  show each `helpers.validation_messages(err)` line via `st.error`. If it
  builds, run `sweep_validation_messages(spec)` and show any messages via
  `st.error`. When the spec is clean, show `len(expand(spec))` as "This
  sweep expands to N member runs." (expectation-setting before a long
  job). Offer the authored YAML in an expander (`sweep_spec_yaml`) and an
  `st.download_button` for it.
- **(h) Launch** — a "Launch sweep" button, disabled unless validation is
  clean. When the authored name already has a `sweeps/<name>/` folder,
  show an `st.info` that launching will RESUME it (finished members
  skipped, per #70) — the true runner behaviour, surfaced rather than
  hidden. On click: `write_authored_spec(spec, authored_spec_path(...))`;
  then `subprocess.Popen(build_launch_command(spec_path, SWEEPS_DIR))`
  with stdout/stderr redirected to the launch log (a file under
  `SWEEPS_DIR` that exists at launch time). Record the launched name in
  session state (the monitor defaults to it). Do NOT block the script
  thread; do NOT run `run_sweep` in-process.

## Task 2 — the monitor surface (same tab, below authoring)

A "Monitor" section:

- A selectbox over existing `sweeps/<name>/` folder names (defaulting to
  the just-launched name from session state) — so a finished sweep's
  status and headline chart can be re-opened without a full browser. This
  is deliberately NOT a comprehensive browser: no member drilldown, no
  overlays, no filtering.
- A manual "Refresh status" button (no auto-refresh timer, no add-on
  dependency — a job measured in minutes; the click is honest and
  dependency-free).
- Render `read_sweep_status(...)`: completed / total / failed / running,
  started_at / updated_at, and the compact per-index table (run_index,
  status, folder, error) via `st.dataframe`.
- The launch log (when the tab launched this sweep) in an expander.
- If `sweeps/<name>/sweep_summary.parquet` exists: load it (pandas) and
  render the single headline chart with the EXISTING pure builder
  `pdsim.viz.charts.sweep_metric_chart(summary_frame, axis_column,
  metric_column, metric_label=...)`. Axis and metric columns come from
  `sweep_summary.json` (`axis_columns` / `metric_columns`, #70);
  selectboxes choose which axis and which metric to plot. The builder is
  reused as-is — no new chart function.
- A caption noting member run folders live under `sweeps/<name>/runs/` and
  that rich per-member and cross-sweep browsing arrives in the follow-on
  increment.

## Task 3 — docs

- `ROADMAP.md`: mark M9.5b landed under the M9.5 block, pointing at this
  spec; note the comprehensive sweep browser remains the deferred
  follow-on.
- `CLAUDE.md`: note that the Sweep tab authors and launches sweeps
  (execution stays headless via a spawned `python -m pdsim.sweep`).
- New DECISIONS entries (#72–#74): (i) the detached-subprocess launch model
  and why in-process / threaded launch were rejected; (ii) the structural
  three-bucket UI; (iii) authoring the complete SweepSpec surface in v1
  while deferring the comprehensive sweep browser to a named follow-on.
- No PARAMETERS.md change expected (no new registry entries).

## Validation

APP-FIRST (M9.5a deferred app validation to here). With the venv active
and `streamlit run pdsim/ui/app.py`:

1. Open the **Sweep** tab. Author a sweep that reproduces
   `examples/sweeps/tft_invasion.yaml`: name it (e.g. `tft_invasion_app`),
   base = scenario *Reciprocity Takes Over*, composition vary =
   `tit_for_tat`, counts = `2,4,6,8,10,12,14,16,20` (use the range builder
   then edit, or type the list), fill = `always_defect` 100%, seeds 1–10
   (range builder: start 1, count 10), metrics `final_share(tit_for_tat)`,
   `time_to_fixation(tit_for_tat)`, `fixation_flag(tit_for_tat)`. Confirm
   the live composition preview shows the resolved integers at the largest
   count, and the "expands to N member runs" line reads **90** (9 counts ×
   10 seeds).
2. Break it on purpose: set fill to 90%. Confirm the tab shows the SAME
   plain sentence `sweep_validation_messages` produces at the CLI, and
   Launch is disabled. Restore to 100%.
3. Launch. Confirm `sweeps/tft_invasion_app/` appears with
   `sweep_spec.yaml` and the authored spec file, and the subprocess runs
   headlessly (the app stays responsive — you can keep interacting). Click
   "Refresh status" a few times and watch completed climb to 90 with
   failed 0.
4. When finished, confirm `sweep_summary.parquet` is present and the
   headline metric-vs-axis chart renders in the Monitor: mean
   `final_share` vs invader count rising from ≈0 toward ≈1 with a
   replicate-spread band (the invasion threshold, explainer §1.4).
5. Cross-check headless equivalence: confirm the authored
   `sweep_spec.yaml` is accepted verbatim by the CLI — `python -m
   pdsim.sweep sweeps/tft_invasion_app/sweep_spec.yaml --out sweeps
   --resume` reports all members already done (identical spec → resume,
   nothing re-runs).
6. Resume-awareness: re-open the tab, author the same NAME again, and
   confirm the info notice that launching will resume the existing sweep.
7. Open one member folder's config standalone (`python -m pdsim.run
   sweeps/tft_invasion_app/runs/<one>/config.yaml`) — it reproduces (hard
   rule 8; the tab authored nothing that weakens per-member
   reproducibility).

Automated tests (`pdsim/tests/test_sweep_ui.py`) complement, never
replace, the above: every `sweep_helpers` function per Task 0, including
the tft_invasion-shape `build_sweep_spec` round-tripping to an empty
`sweep_validation_messages`, a malformed shape raising `ValidationError`,
and `build_launch_command`'s exact argv. The streamlit-importing tab
function stays out of the unit tests (it is a thin shell over tested
helpers); the existing AppTest smoke tests cover that the three-tab app
still renders.
