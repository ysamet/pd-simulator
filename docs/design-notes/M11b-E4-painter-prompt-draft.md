# M11b Phase E — sub-prompt E4: the mouse layout painter (DRAFT)

**RATIFIED as DECISIONS #186 on 2026-09-06; built as #187.**

**Status: DRAFT — scoped 2026-09-05 by the implementation layer, for
design-layer ratification.** DECISIONS #185 records the scoping findings
below as open design state. The design layer confirms or amends Part 2's
proposed rulings; the ratified set becomes the E4 pre-drafting DECISIONS
entry (#186, appended verbatim by the E4 build session), and Part 3 is
pasted as the E4 prompt with the design layer's amendments folded in.
Under 50,000 characters, as a single prompt must be (CLAUDE.md).

Sources read fresh when scoping: the M11b spec's Phase E paragraph, its
E4 bullet and V5's E4 sentence; DECISIONS #109, #116–#126, #143,
#145–#149, #178–#184; CLAUDE.md; `pdsim/core/layouts.py`,
`pdsim/ui/app.py`, `pdsim/ui/helpers.py`, `pdsim/viz/charts.py`,
`pdsim/io/results.py`, `grid_templates/`; the installed Streamlit 1.58.0
(Python source AND the frontend bundle `PlotlyChart.*.js`) and plotly
6.8.0. Nothing contradicts the scoping message; 1,255 tests collected.

---

## Part 1 — Scoping findings (verified 2026-09-05)

- **F1 — A mouse stroke is not headlessly drivable.** Streamlit's own
  `PlotlySelectionState` docstring: "Selection states cannot be
  programmatically changed or set through Session State"; and
  `streamlit/testing/v1/element_tree.py` models no plotly element (it
  lands as `UnknownElement`). So the #180 precedent applies: the
  stroke → cells translation is a PURE function pinned on synthetic
  selection dictionaries of the documented schema (`points[*]` with
  `point_index` and `curve_number`), the app-level pipeline pins drive
  the painter through its BUTTONS (load a file, fill, save, hand off),
  and the stroke itself is owner-validated.
- **F2 — The existing grid renderer cannot be the click surface.**
  `go.Heatmap(selectedpoints=[1])` raises `ValueError` (plotly's heatmap
  and image traces have no selection support); `go.Scatter` accepts it.
  The canvas is therefore a second figure kind — ONE `go.Scatter` of
  square markers, points in row-major site order so `point_index` IS
  the site id — a recorded departure from #145(d)'s one-renderer
  discipline, justified because the canvas is an INPUT widget: every
  read-only view (panel preview, live view, browser) stays on
  `grid_chart`, and the Run lab's founding preview of the SAVED file
  (through `founding_view`) is the truth the validation reads.
- **F3 — Frontend selection plumbing (read from the 1.58 bundle).**
  With selection on: `clickmode` becomes `event+select` when the points
  mode is enabled, else `none`; `dragmode` defaults to `pan` when the
  points mode is enabled (else `select` for box, `lasso` for lasso)
  UNLESS the figure's own layout sets `dragmode`; and whenever the
  active drag tool is `select` or `lasso`, `clickmode` is forced to
  `event` — a plain click does not select while a drag tool is active.
  Consequence: the canvas sets `dragmode="select"` so a drag paints a
  rectangle out of the box; a single cell is painted by a small drag
  over it, or by choosing the pan tool in the chart's toolbar and
  clicking; the lasso is one toolbar click away. All frontend
  behaviour is owner-validated (F1).
- **F4 — The callback form is the right one.** `on_select=<callable>`
  fires once per selection change in the pre-render window
  (`SessionState._call_callbacks`, the same window #124's populate
  button uses). The `"rerun"` form would return the SAME selection on
  every later pass until the element changes, needing a de-duplication
  signature; rejected as the primary, kept as the fallback (Part 3,
  Rule 7).
- **F5 — Element identity clears the highlight for free.**
  `plotly_chart` hashes the figure spec into its element id (#184
  (a)(vii)), so every EFFECTIVE stroke remounts the canvas and clears
  the selection; only a no-op stroke leaves plotly's dimming of
  unselected points behind — the canvas sets unselected opacity 1 so
  nothing ever dims.
- **F6 — Stale dependency floor (adjacent, pre-existing).**
  `pyproject.toml` declares `streamlit>=1.30`, while E1/E2 already rely
  on 1.58 APIs (`segmented_control(required=True)`, keyed expanders) and
  `on_select` needs ≥ 1.35.
- **F7 — `grid_templates/Grid_Layout_Template.md` (adjacent).** An
  owner-authored 20 × 20 sample committed in the Phase B fix commit
  (aa94eee) with an `.md` suffix; it parses as a valid layout (400
  cells, `kind:lattice_grid` without a space parses). Unreferenced by
  tests or docs. Proposed: the painter's file list shows `.txt` files
  only (R5); the file is left as it is unless the owner says otherwise.
- **F8 — Per-pass cost.** Every tab renders every pass, live-run passes
  included (#183 R4; #184(f9) measured the browser's share), so the
  painter's canvas is serialised on every pass of a live run. Measured
  in Task 5; a rebuild cache on the draft is pre-authorised if the
  measurement calls for it.
- **F9 — What stays untouched.** No registry PARAMETER (the painter is a
  tool), no greying-table row, no engine/config/io change beyond a pure
  text formatter in `layouts.py` that no engine path calls; zero
  re-recordings, zero new goldens.

---

## Part 2 — Proposed rulings (with alternatives)

- **R1 — Placement.** A fourth top-level tab, "Layout painter", SECOND
  in the strip: `["Run lab", "Layout painter", "Results browser",
  "Sweep"]`. The parameter panel — `_parameter_panel`,
  `_structure_panel`, the #141 table, `SECTION_GATES`, the keep-alive
  list — stays byte-untouched except for the one factoring in R7 (the
  #178 R10 discipline). Alternatives: inside the Structure section
  (rejected: an input canvas inside a two-column expander of a
  mode-gated section, needing its own persistent state anyway; the
  Sweep tab is the precedent for a tool that writes a file the run then
  consumes); last position (rejected: the painter feeds the Run lab;
  verified that no test indexes tab positions).
- **R2 — The click surface.** `charts.paint_canvas(rows, cols, cells,
  *, side_px)` — a single `go.Scatter` (markers, symbol square, size
  `side_px − 1` for a 1 px gap mirroring the heatmap's `xgap`/`ygap`),
  colours from `strategy_colors()` with empty sites in a new module
  constant `EMPTY_CELL_COLOR` (a light grey — every site must be a
  clickable point), points in row-major order (pinned), explicit
  `width`/`height` (cols × side + 40, rows × side + 60 plus legend
  room — the `grid_chart` margins), `dragmode="select"`, both axes
  `fixedrange` (no zoom on a painter), y reversed with `scaleanchor`,
  `unselected`/`selected` marker opacity 1, hover "row r, col c —
  <display name | empty>". The colour key: legend-only dummy traces
  (`x=[None]`, one per registered strategy, display names) appended
  AFTER the cells trace with a horizontal legend below the grid — the
  cells trace is trace 0, pinned, and `cells_from_selection` keeps
  only `curve_number` 0. `charts.paint_cell_side(rows, cols) -> int |
  None` gives the side (see R3). Rendered with `st.plotly_chart(fig,
  width="content", key="painter_canvas", on_select=_apply_stroke,
  selection_mode=("points", "box", "lasso"))` — `"content"` because a
  stretched canvas would break the pixel-sized markers (the #145
  `_grid_width` reasoning).
- **R3 — Paintable size.** The canvas renders exactly when
  `charts.pixel_array_active(rows, cols)` is False — the existing
  predicate reused (§12: one source), no new threshold; the side is
  then `int(_naive_cell_side(rows, cols))`, ≥ 6 px by construction.
  Otherwise the tab shows a sentence: the grid is too fine to paint by
  mouse (cells under 6 px or more than 2,500 sites); shrink it or write
  the file by hand. Alternatives: a painter-only minimum (rejected: a
  second documented threshold); scattergl (rejected: no need).
- **R4 — State and helpers.** A new Streamlit-free module
  `pdsim/ui/painter_helpers.py` (the `sweep_helpers.py` precedent)
  holds `LayoutDraft` — a mutable `@dataclass` like `LiveRun` (rows,
  cols, `cells: list[str | None]`, `saved_as: str | None`, `dirty:
  bool`, `undo_cells` for one-level undo) — and pure functions:
  `blank_draft`, `draft_from_layout(LayoutFile)`,
  `draft_from_placements(rows, cols, placements)`, `resize_draft`
  (top-left overlap kept), `cells_from_selection(selection,
  site_count)`, `apply_brush(draft, cells, brush) -> int` (changed
  count; records the undo snapshot only when something changed; sets
  dirty), `undo_stroke`, `fill_all`, `clear_all`,
  `draft_layout_file(draft) -> LayoutFile` (so `occupied_count` and
  `strategy_counts` are REUSED, never re-implemented),
  `template_names()` (sorted `.txt` names in `layouts.
  GRID_TEMPLATES_DIR`, read at call time), `normalise_template_name`
  (`.txt` appended when the name has no suffix),
  `template_name_problem(name, *, exists, replace) -> str | None`,
  `save_draft(draft, directory, name) -> Path`, and
  `SHIPPED_TEMPLATES = ("example_quadrants.txt", "example_island.txt")`.
  The draft lives under `PAINTER_DRAFT_KEY = "_layout_draft"` in
  app.py beside `LIVE_RUN_KEY` — app state, never in
  `_preserve_hidden_widget_state`. The brush is `str | None` (None =
  eraser).
- **R5 — The file.** `pdsim/core/layouts.py` gains
  `format_layout_file(layout: LayoutFile, *, comment: str | None =
  None) -> str`: an optional `#` comment line, the three header lines,
  a blank line, one whitespace-separated line per grid row, `.` for
  empty, trailing newline; round trip pinned. The core module owns the
  FORMAT (read and write) and touches no filesystem; only the app
  writes files, and a test pins that no engine module references the
  formatter — the engine still only reads data (hard rules 4 and 8).
  Save target: `layouts.GRID_TEMPLATES_DIR / name` (the #122 home,
  read at call time so tests can redirect it); refused: a blank name,
  a name with a path separator (bare names only — the #122 rule), and
  the two shipped examples; an existing file needs the "Replace the
  existing file" checkbox. No `.gitignore` change: a painting the owner
  wants to keep is committed by the owner; a recorded run is
  self-contained regardless (#120(d)). Alternative: an ignored
  `layouts/` folder (rejected: a bare name would not resolve there
  (#122), and a path-with-separator value is working-directory
  relative — the smell #122 names).
- **R6 — Hand-off.** "Use this layout in the Run lab", enabled only
  while the draft is saved and unchanged since (`saved_as` set, not
  `dirty`) — a button CALLBACK (the #124 pre-render window) writing
  `run.mode = "evolution"`, `structure.kind = "lattice"`,
  `structure.rows#limit = True` / `#value = rows`, the same for
  `cols`, `structure.initial_layout = "from_file"`,
  `structure.layout_file = <bare name>`, and the population through the
  EXISTING `_populate_from_layout_file(size, counts)` — the #143 write
  path, reused. `_loaded_values` (the A2 baseline) is NOT touched: an
  A2 caution at "World structure" after handing off from a well-mixed
  economy scenario is correct (incomes rescale on a lattice). The
  callback stages the Run lab's `_load_note` sentence. Alternative:
  hand off an unsaved draft (rejected: the config must reference a
  FILE — hard rule 8 — so saving first is the contract).
- **R7 — Seeding.** Three sources, each a button callback that writes
  the draft AND the painter's Rows/Columns widgets: "New blank grid"
  (from the Rows/Columns number inputs, default 10 × 10, minimum 1,
  maximum 500 each — R3 refuses what cannot be painted), "Load into
  painter" (the "Existing layout file" selectbox over
  `template_names()`; tokens validated against the registry via
  `validate_layout_file` — an unknown token shows the #122 sentence and
  loads nothing), and "Start from the Run lab's founding preview" —
  which needs the panel's forward values: the lookahead-building block
  of `_parameter_panel` is FACTORED into `_panel_lookahead(specs)` and
  reused unchanged (the panel's behaviour byte-identical — pinned by
  the existing suite), the composition read from the `composition.*`
  keys, then `helpers.grid_visible` → `helpers.grid_preview_config` →
  `layouts.founding_view` → `draft_from_placements`; any failure
  (tournament, well-mixed, a validation message, a missing file) is
  staged as a `_painter_note` and shown on the next pass, since a
  callback cannot render. Changing Rows/Columns with a draft present
  shows a caption and a "Resize grid" button (top-left overlap kept)
  rather than resizing implicitly.
- **R8 — Brush.** `st.radio("Brush", horizontal=True)` over the
  registered strategies' DISPLAY names in registry order plus "Empty
  (eraser)"; the callback maps the label back to the machine name
  through `all_strategies()` (never a hardcoded list). The colour key
  is the canvas legend (R2) — one palette, `strategy_colors()`.
- **R9 — Stroke semantics and readouts.** Every selected cell takes the
  brush, occupied cells included (it is a painter); "Undo last stroke"
  (one level), "Fill all", "Clear all". Readouts in the §12 style, each
  with a (?) from a `PAINTER_HELP` dict in app.py (the `STRUCTURE_HELP`
  precedent): "Sites", "Painted agents" (the population size the
  hand-off will set), "Empty cells", a per-strategy counts caption, and
  a "Saved as" status (name, or "unsaved changes").
- **R10 — Registry.** No new parameter. Two help-text sentences point
  at the tab (the `from_file` sentence of `structure.initial_layout`
  and the end of `structure.layout_file`), so `python -m pdsim.gendocs`
  runs and `PARAMETERS.md` is regenerated; the drift test guards it.
- **R11 — Dependency floor.** Raise `streamlit>=1.30` to
  `streamlit>=1.58` with a comment naming the APIs relied on
  (`segmented_control(required=True)`, keyed expanders,
  `plotly_chart(on_select=…)`); logged in the build entry. Alternative:
  leave the stale floor (the design layer's call; F6).
- **R12 — Tests** (all headless; the stroke is owner-validated per F1):
  see Task 5.
- **R13 — Docs at landing:** see Task 6.
- **R14 — Budget.** Zero re-recordings, zero new goldens; the 31 golden
  masters and every counting pin pass untouched; `layout_consumes_rng`
  untouched; ruff clean.

---

## Part 3 — The E4 prompt

**Action required:** implement M11b Phase E sub-prompt E4 — the mouse
layout painter — exactly as ruled in DECISIONS #186 (the ratified form
of Part 2 above), in one fresh session, then hand back for the owner's
app validation and commit. Do not start E5. The session starts by
checking for `docs/WIP.md` (absorb and delete if present) and by
appending #186 verbatim if the design layer has not already done so.

Standing rules restated: hard rules 1–8 of CLAUDE.md; never `git
commit`; validation is app-first with FULL verified widget paths and no
project shorthand in anything owner-facing; every deviation from a
ruling is a Rule 7 report, never a silent choice; the ▲ session reset
follows the handback.

### Task 0 — Inspection (report in the build entry's (a))

Verify against the INSTALLED versions, never from memory, and record:
(i) `streamlit.__version__`, `plotly.__version__`; (ii) the
`PlotlySelectionState` docstring sentence on session state (F1) and the
absence of a plotly element in `streamlit/testing/v1/element_tree.py`;
(iii) `go.Heatmap(selectedpoints=[1])` raising and `go.Scatter`
accepting (F2); (iv) the bundle facts of F3 — grep the Streamlit static
`PlotlyChart.*.js` for `event+select` and read the `clickmode`/
`dragmode` effect, quoting it; (v) that `register_widget` in
`elements/plotly_chart.py` passes `on_select` as the change handler and
that `SessionState._call_callbacks` runs it before the script (F4); (vi)
the `pyproject.toml` floor (F6); (vii) the seven registered strategies
with their display names, from `all_strategies()`; (viii) that no test
indexes tab positions (grep `tabs` in `pdsim/tests`); (ix) the per-pass
cost BASELINE before the tab exists — the #184(a)(viii) method (AppTest,
tiny Custom 4-agent evolution, 20 generations, chain and pass-by-pass
median). A probe app, if used, follows the #117/#130 precedent (never
shipped).

### Task 1 — The formatter (`pdsim/core/layouts.py`)

Add `format_layout_file` per R5, exported in `__all__`, with a
Google-style docstring stating that this module owns the format in both
directions, that it touches no filesystem, and that no engine path calls
it. Tests (`test_layouts.py`, a new `TestLayoutFileFormatter` class):
round trip on both shipped examples (`parse_layout_file(
format_layout_file(read_layout_file(path)))` equal in kind, rows, cols,
cells); a hand-built `LayoutFile` with empty cells and no positions;
the comment line ignored by the parser; the trailing newline; and the
rule-4 pin — the text of `dynamics.py`, `async_dynamics.py`,
`engine.py` and `structure.py` never mentions `format_layout_file`.

### Task 2 — The helpers (`pdsim/ui/painter_helpers.py`, new)

Per R4. `cells_from_selection(selection, site_count)` reads
`selection["points"]` (a sequence of mappings), keeps entries whose
`curve_number` is 0 or absent, takes integer `point_index` values in
`[0, site_count)`, and returns them de-duplicated and ascending; a
missing or empty `points` yields `()`. `save_draft` writes with
`encoding="utf-8"` and `newline="\n"`, then sets `saved_as` and clears
`dirty`. Module docstring: the painter is a UI tool that WRITES layout
files which configs reference; the engine only ever reads data (#109).
Point out the functional-programming thread where it applies (the
stroke as a pure transformation of the cells tuple). Tests
(`test_painter_helpers.py`, new): blank / from-layout / from-placements
/ resize (overlap kept, growth padded empty); `cells_from_selection` on
synthetic dictionaries — a single point, a box's points list, a
`curve_number` 1 entry dropped, out-of-range and duplicate indices, an
empty selection, a mapping without `points`; `apply_brush` counting
only real changes, occupied cells overwritten, the eraser, undo after
a stroke and undo with nothing to undo, fill and clear; the derived
counts through `draft_layout_file`; `normalise_template_name` (`.txt`
appended only when there is no suffix); `template_name_problem` for
blank, separator, absolute, shipped names, and exists-without-replace;
`template_names` listing only `.txt` files of a temporary directory;
`save_draft` writing exactly `format_layout_file(...)` with LF endings.

### Task 3 — The canvas (`pdsim/viz/charts.py`)

Per R2/R3: `EMPTY_CELL_COLOR`, `paint_cell_side`, `paint_canvas`, each
documented (the canvas is the project's first INPUT figure; say why it
is not `grid_chart`, citing F2). Tests (`test_charts.py`, a new
`TestPaintCanvas` class): `paint_cell_side` is `None` exactly when
`pixel_array_active` (49 × 49 vs 51 × 51; 200 × 10; 60 × 5 keeps a
side); trace 0 is the cells trace with `rows × cols` points and point i
at `(i % cols, i // cols)`; marker colours equal `strategy_colors()`
for occupied cells and `EMPTY_CELL_COLOR` for empty ones; the layout
carries `dragmode == "select"`, an explicit width and height, reversed
y, fixed ranges; the legend traces carry every registered display name
and no data points.

### Task 4 — The tab (`pdsim/ui/app.py`)

Per R1, R4, R6–R10: `PAINTER_DRAFT_KEY`, `PAINTER_HELP`, `_panel_
lookahead(specs)` (factored out of `_parameter_panel`, which calls it
— its behaviour byte-identical), `_painter_tab()`, the callbacks
`_new_blank_draft`, `_load_draft_from_file`, `_draft_from_preview`,
`_apply_stroke` (reads the selection under `painter_canvas`, the brush
under `painter_brush`, the draft under `PAINTER_DRAFT_KEY`), and
`_painter_handoff(name, rows, cols, size, counts)`; `main`'s tab list.
Widget labels and keys, verbatim: "Rows" `painter_rows`, "Columns"
`painter_cols`, "New blank grid" `painter_new`, "Existing layout file"
`painter_source`, "Load into painter" `painter_load`, "Start from the
Run lab's founding preview" `painter_from_preview`, "Resize grid"
`painter_resize`, "Brush" `painter_brush`, "Fill all" `painter_fill`,
"Clear all" `painter_clear`, "Undo last stroke" `painter_undo`, the
canvas `painter_canvas`, "Layout file name" `painter_file_name`,
"Replace the existing file" `painter_replace`, "Save layout"
`painter_save` (handled in the script body: writes, then `st.success`
naming the path, or `st.error` with the problem sentence), "Use this
layout in the Run lab" `painter_handoff`. Every widget and readout has
a (?) from `PAINTER_HELP` or the widget's own `help=`; the help for the
canvas states the three tools (drag a rectangle; pan tool + click for
one cell; lasso from the toolbar) so the owner is not left guessing.
Registry: the two R10 sentences; run `python -m pdsim.gendocs`.
`grid_templates/README.md`: a "Painting a layout in the app" paragraph
and the `.txt`-only listing rule. `pyproject.toml`: R11 if ratified.

### Task 5 — App tests and the measurement (`test_app.py`)

A new `TestLayoutPainter` class. Fixture discipline: `PDSIM_RUNS_DIR`
to a temporary directory (the browser tests' idiom) AND
`monkeypatch.setattr(pdsim.core.layouts, "GRID_TEMPLATES_DIR", tmp)`
with the two shipped examples copied into `tmp` — every painter path
must read the attribute at call time, so the redirect holds inside
AppTest's in-process script run. Pins: (i) the cold start renders the
tab without exception and every painter widget exists by key; (ii)
"New blank grid" at 6 × 8 → "Sites" 48, "Painted agents" 0; (iii)
"Load into painter" on `example_island.txt` → "Painted agents" 24 and
the counts caption naming 18 and 6; (iv) "Fill all" with a brush, then
"Clear all", then "Undo last stroke" → 48 / 0 / 48 on the blank grid;
(v) "Save layout" refused for a blank name, a shipped name, and an
existing name without the checkbox; accepted with the checkbox; the
written text equals `format_layout_file(draft_layout_file(draft),
comment=...)` byte for byte; (vi) the hand-off from the loaded island
saved as `island_copy.txt`: `run.mode` evolution, `structure.kind`
lattice, rows/cols 4 × 6 with the limit boxes ticked,
`structure.initial_layout` from_file, `structure.layout_file`
`island_copy.txt`, `population.size` 24 and the mix 18 / 6, the Run
lab's "Population mix OK: 24 agents." caption and the Structure
panel's "Occupied" metric reading "24 (100%)"; (vii) THE VALIDATION
PIN — after (vi), `dynamics.generations` 2, "Record this run" on, Run
(the one `run()` follows the pass chain, #184(e)): the recorded folder
holds `layout.txt` equal to the saved text byte for byte and a
`config.yaml` whose `structure.layout_file` is `layout.txt`; then the
#184(e)(ii) shape re-run identical — `python -m pdsim.run
<folder>/config.yaml` recorded into another temporary directory yields
`timeseries.parquet` and `cooperation.parquet` equal to the app's; (viii)
"Start from the Run lab's founding preview" after loading "Cooperation
Survives in Clusters" (`spatial_reciprocity`): the draft's dimensions
equal the scenario's grid and its counts equal the composition; under
the tournament tab the button stages the note and changes nothing; (ix)
a 200 × 10 blank grid shows the R3 sentence and no canvas; (x) the
panel's existing pins prove `_panel_lookahead` changed nothing. THE
MEASUREMENT: repeat Task 0 (ix) with the tab present — a blank 10 × 10
draft, then a filled 50 × 50 draft — and report the per-pass delta;
above ≈ 20 ms at 50 × 50, cache the built figure on the draft
(invalidated by every mutation) and report the cached figure.

### Task 6 — Docs (same session)

DECISIONS: #186 verbatim (if not already appended) and the build entry
#187 in the house shape — (a) Task 0 findings, (b) as-built decisions,
(c) Rule 7 findings, (d) tests and budget, (e) docs. DESIGN §2.12: the
sentence "The mouse painter that writes such files is M11b" → shipped
in Phase E4, and the painter removed from the "Still out of scope" list;
§4.1: a new item 6 for the Layout painter tab (the canvas, the three
seeds, save, hand-off, the size guard) — bullet 3's "radio" stays
untouched, held for E5 (#182(f4)); §6.3: "Still M11b: the mouse layout
painter…" → shipped. CLAUDE.md: the validation-precision paragraph
(four tabs; the painter's widgets sit directly on the tab, no
expander) and the current-phase paragraph (E4 landed; next E5).
ROADMAP: the E4 status line. The spec: status line only.
`PARAMETERS.md` regenerated. `ADVISORIES.md` untouched.

### Rule 7 tripwires

STOP and report if: any golden master fails; anything beyond the
`_panel_lookahead` factoring wants to touch `_parameter_panel`,
`_structure_panel`, the greying table, `SECTION_GATES`, or the
keep-alive list; the callback does not find the selection under
`painter_canvas` (fallback pre-authorised: the `"rerun"` form with a
de-duplication signature stored on the draft — build it, report it);
`width="content"` does not hold the explicit canvas size in AppTest's
element (report; do not switch to stretch); the measurement delta
exceeds ≈ 50 ms per pass even with the cache. Frontend behaviour that
only a browser shows — whether a plain click paints under the default
drag tool, lasso behaviour, legend placement, remount flicker per
stroke — is NOT headlessly pinnable (F1); say so plainly in the build
entry and route it to the walkthrough.

### Validation walkthrough (owner; app-first)

Activate the venv first (`.venv\Scripts\Activate.ps1` in PowerShell),
then `streamlit run pdsim/ui/app.py`.

1. Click the "Layout painter" tab (the second tab at the top of the
   page). Set "Rows" to 6 and "Columns" to 8, press "New blank grid": a
   grey 6 × 8 canvas appears with a colour key beneath it; "Sites"
   reads 48, "Painted agents" 0.
2. Under "Brush" pick "Tit for Tat". Drag a rectangle over the left
   four columns: those cells take the strategy's colour and "Painted
   agents" reads 24. Pick "Always Defect", drag over the right four
   columns: 48. Pick "Empty (eraser)", drag over the bottom row: 40.
   Press "Undo last stroke": 48 again. Then try the single-cell tools
   and report what happens: a tiny drag over one cell; the pan tool in
   the chart's toolbar followed by a click; the lasso tool.
3. Type `my_first_painting` into "Layout file name", press "Save
   layout": a green sentence names `grid_templates\my_first_painting.
   txt` and "Saved as" shows the name. Press "Save layout" again: a red
   sentence says the file exists and names the checkbox. Tick "Replace
   the existing file", press "Save layout": accepted.
4. Press "Use this layout in the Run lab", then click the "Run lab"
   tab. A green note at the top says the painting is now the founding
   layout. In the "Population" section (starts expanded) "Population
   size (N)" reads 48, "Tit for Tat" 24, "Always Defect" 24. Open the
   collapsed "Structure" expander: "World structure" lattice, "Limit
   lattice rows?" ticked with "Lattice rows" 6, "Limit lattice
   columns?" ticked with "Lattice columns" 8, "Initial layout"
   from_file, "Layout file" `my_first_painting.txt`;
   below the widgets the founding preview shows exactly the painting
   and "Occupied" reads "48 (100%)". Below the panel: "Population mix
   OK: 48 agents." The Scenario dropdown still shows whatever was
   loaded — a scenario is a starting point, not a lock.
5. In "Dynamics" (starts expanded) leave "Generations" at its value or
   set it to 20. Tick "Record this run", press "Run", let it finish.
6. Click the "Results browser" tab. "Open a run" shows the newest run;
   its grid (the founding grid — the "Grid view" selector appears only
   when the run recorded site ids) equals the painting. Note the final
   summary table's numbers.
7. Press "Load config into panel", return to the "Run lab" tab: the
   load note appears and "Layout file" now shows a path into the run
   folder ending in `layout.txt` (the recorded copy, resolved beside
   the loaded config) — expected, the recorded folder is
   self-contained. Press "Run" again with "Record this run" ticked.
   Back in the "Results browser", compare the two runs' final summary
   tables and charts: identical. Optional headless twin: `python -m
   pdsim.run runs\<the first folder>\config.yaml` records a third
   folder with the same summary.
8. In the "Layout painter", choose `my_first_painting.txt` under
   "Existing layout file", press "Load into painter": the painting
   returns. Choose `example_island.txt`, press "Load into painter":
   the island, "Painted agents" 24. In the "Run lab" load "Cooperation
   Survives in Clusters" from the Scenario dropdown, return to the
   painter and press "Start from the Run lab's founding preview": that
   scenario's founding arrangement appears at its grid size, editable.
9. Set "Rows" 200, "Columns" 10, press "New blank grid": the sentence
   about cells too fine to paint replaces the canvas.
10. Afterwards `grid_templates\my_first_painting.txt` is an untracked
    file; keep it or delete it as you like.

### Handback

(a) a summary in plain words; (b) the files to stage; (c) a suggested
commit message; the DOCS CHANGED list with the new DECISIONS numbers;
the test count against the 1,255 baseline; the measurement numbers;
every Rule 7 finding; and the walkthrough above with any label that
changed during the build corrected to what the app actually shows.
