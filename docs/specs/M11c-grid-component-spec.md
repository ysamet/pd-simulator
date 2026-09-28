# M11c — The grid component and smooth live display

**Status: in progress (frozen 2026-09-25 — DECISIONS #190, #194; stage one sub-prompt 1.1 built 2026-09-26 — #195, #196).**
This spec is frozen intent (#62): deviations during implementation become new DECISIONS entries, never retro-edits beyond this status line. Rationale and rejected alternatives live in DECISIONS #190 (the display-architecture rulings) and #194 (this spec's rulings R1–R25); this file is the binding summary.

## Purpose

Two owner reports, one cause (#190(a)): on live runs the whole page shudders and the charts blink every generation, and the Layout painter paints only on release. Streamlit re-executes the whole script per pass — ≈ 190 ms of page work beyond the engine (#184(a)(viii)) — and `plotly_chart` hashes the figure into its element id, so a changed figure is torn down and remounted (#184(a)(vii)). M11c fixes both inside Streamlit: (1) a KEYED custom component — an HTML canvas plus one JavaScript file served from a folder inside the package, no build toolchain — that keeps its identity across reruns and redraws in place, owning the pixels for live display and for painting under the held pointer, with zoom and pan; (2) a TIMER-DRIVEN fragment confining the per-generation pass to the run area. Neither makes the engine faster; both make a run smooth to watch. Stages (#190 R4/R5): ONE — the live-run grid and the painter on the component, zoom and pan, the "too fine to paint" refusal lifted, the fragment; TWO — the founding preview and the Results browser on the same component (one grid renderer over four surfaces); THREE — streaming time-series charts in the component. Migration off Streamlit stays parked behind the trigger: a measured live run still unfollowable after stages one AND three, or the M19 map goal needing what an embedded iframe cannot give (#190 R2 as read by #194(a)(f5)).

## Design

### 1. One component and its files
- Declared once as `pdsim_grid_canvas` from the absolute path of `pdsim/ui/frontend/grid_canvas/` (`index.html` and `grid_canvas.js`; no `__init__.py`, no build step). `pdsim/ui/grid_canvas.py` is the only module importing Streamlit for it (the declaration and one call function); `pdsim/ui/grid_canvas_helpers.py` is Streamlit-free (palette, byte encoder, the two surfaces' argument builders, the timer-interval and work-budget functions); the stroke applier lives in `pdsim/ui/painter_helpers.py` beside `apply_brush`.
- Two modes, one code path: `view` (the Run lab's run-area grid, during and after a run; stage two adds the preview and the browser) and `paint` (the Layout painter). Keys: `live_grid`, `painter_canvas`.
- Keyed identity keeps the iframe alive across reruns (`key_as_main_identity={"name","url"}`; E4 handback Part 3 finding 2). `streamlit>=1.58` stays; a Streamlit upgrade re-runs the Validation checklist.

### 2. Python → page (every render; #194 R1)
- `cells`: the WHOLE grid, one byte per site in row-major site order; 0 = empty, i = the strategy's registry position + 1. A binary argument if 1.1's Task 0 confirms 1.58 delivers bytes arguments to the iframe as binary; otherwise base64 text. 500 × 500 = 250,000 bytes (≈ 244 KB; ≈ 333 KB as base64).
- JSON arguments: `rows`, `cols`; `palette` (`strategy_colors()` in registry order; index 0 is drawn from the theme, §4); `names` (display names, same order); `key_entries` (paint: all strategies + Empty; view: the run's strategies + Empty); `mode`; `border_min_px` (= `charts.BORDER_MIN_SIDE_PX`, one home); `version` (a live run's period index; the draft's revision counter, bumped by every mutation) so the page skips identical frames; `debug` (§4); in paint mode `tool`, `brush` (palette index) and `applied` (the last applied {mount, stroke}).
- A live run sends once per pass; the painter only when the draft changes — never on timer ticks. Never diffs; revisit only per #194(d)(i).

### 3. Page → Python (paint mode only; #194 R2)
- On pointer release, one value: `{"mount": <random string chosen at page load>, "stroke": <increasing integer>, "brush": <palette index>, "sites": [<site ids painted, in order>]}`. View mode sends nothing.
- Received through the component's `on_change` callback if 1.58 accepts one (1.1 Task 0); otherwise de-duplicated on (mount, stroke), because a component returns its last value on every rerun.
- `painter_helpers.apply_component_stroke(...)`, pure: refuses the whole stroke with a staged note on an out-of-range site or an unknown brush (a bug, not user error), de-duplicates, calls `apply_brush`, records (mount, stroke) on the draft as applied. Undo, fill, clear, readouts, save and hand-off are untouched. The brush applied is the one the page painted with.

### 4. The page's obligations (`grid_canvas.js`)
- Protocol: post `{type: "streamlit:componentReady", apiVersion: 1}` before anything else; handle `streamlit:render` (args, theme); send values with `streamlit:setComponentValue`; size with `streamlit:setFrameHeight`.
- Drawing: one pixel per site into an off-screen image, scaled onto the canvas with smoothing off, at device-pixel resolution; the image rebuilt only when `version`, dimensions or palette change; grid lines only where a cell is ≥ `border_min_px` on screen, only within view; empty sites in the theme's secondary background colour, the canvas background in the theme's background colour; the colour key drawn below the canvas from `key_entries`; hover "row r, col c — <name>" or "— empty", 1-based.
- View: opens fitted and centred; the wheel zooms about the pointer; in-canvas "+", "−", "Fit"; zoom from fit to 64 px per cell; canvas height capped at ≈ 600 px; zoom and pan survive reruns and reset to Fit only when rows or cols change; a ResizeObserver redraws on width change and tolerates zero width (a hidden tab).
- Tools (paint mode): Draw — the cell under the pointer takes the brush IMMEDIATELY on press and on every move, a grid line walked between successive positions (no gaps); a still click paints one cell. Rectangle — a rubber band while dragging, the enclosed cells on release; a click paints one cell. Lasso — an outline while dragging, on release the cells whose centre lies inside. Pan — a drag moves the view. In view mode a drag always pans. Pointer events with pointer capture; `touch-action: none` on the canvas.
- Overlay: strokes not yet acknowledged by `applied` are kept and repainted over incoming cells, so a stroke begun before the previous one is acknowledged is never clobbered.
- Debug: with `?grid_debug=1` in the app's address (read in Python via `st.query_params`, passed as `debug`) the page shows its last frame time.

### 5. The fragment and the timer (#190 R2; #194 R9–R12)
- Boundary: inside — the live grid component, the run-area readouts, the progress line, the chart slots; outside — the controls row ("Update granularity", "Playback delay (s)", "Score view", "Time scope", "Run", "Stop", "Record this run") and everything else.
- The timer is on only while a run is live: each full-script pass registers the fragment with `run_every` = the interval during a run and without it otherwise. The end-of-`main` sleep-and-`st.rerun` retires.
- Interval = max("Playback delay (s)", `LIVE_TICK_FLOOR_S` = 0.05 s). Guard: at most one advance per interval, measured from the START of the previous advance; a tick inside the window only repaints. Pre-authorised branch (1.2 Task 0): if a tick arriving during a running pass interrupts it or queues without bound, the pass self-paces — a pass longer than the interval requests one full rerun re-registering the interval at 1.25 × its measured time, and again only when later passes differ from that by more than 50%.
- Work per pass — one pure function of (idle gap, interval, delay): one period at any delay above zero; at a delay of exactly zero (the slider already reaches 0: 0 to 1.0 s in 0.05 s steps, default 0.05), periods until 0.05 s of engine time is spent, at least one; after browser throttling — an idle gap since the previous pass ENDED greater than both twice the interval and 0.5 s — up to min(gap − interval, 1 s) of engine time.
- Run-ending: finish, Stop, crash and Streamlit's own Stop each end by requesting ONE full-script rerun (timer off; Run, the final summary, the Results browser's newest-run selection (#189) and any error note repainted). A tick that finds no live run repaints the last display.
- Mid-run contract (#183 R4 unchanged): Stop is a full pass whose fragment body checks the flag first and discards exactly as today (#53, #183 R5); a panel edit, scenario load, mode switch or painter stroke is a full pass that advances one period and re-arms the timer; other app tabs keep the run advancing; the #94 chart throttle (`LIVE_REDRAW_MIN_SECONDS`) stays until stage three while the grid redraws every pass.

### 6. Testing policy (#190 R6; #194 R13, R14)
- Pinned as pure functions: the byte encoder and both argument builders; the stroke applier; the interval and work-budget functions.
- The whole-loop app tests stay APP-LEVEL: one shared helper repeats full-script `at.run()` passes (each executes the fragment body, so advances one period) until the run ends, capped at periods + 2. Assertions unchanged; the one-call chain reliance and the `streamlit.rerun` monkeypatches retire; every affected test is named in 1.2's build entry with its new form. Fallback if a full pass does not execute the fragment body under AppTest: #190 R2's direct-call plan, the lost assertions listed.
- Tripwires: the folder exists inside the package with both files; `grid_canvas.js` contains the four protocol message types and `apiVersion: 1`.
- The drawing, the gestures and the timer are tested by the Validation checklist; Playwright stays deferred.

## Stage one — four build sub-prompts

Each runs in a fresh session; the design layer drafts each against this committed spec; each ends with the DOCS CHANGED report and `python -m pdsim.export_docs`.

**1.1 — the component in view mode on the Run lab's run-area grid, under today's full-script loop.** Task 0: (a) whether bytes arguments reach the iframe as binary (the frontend bundle); (b) whether the component call accepts `on_change`, and when its callback runs; (c) what AppTest's element tree holds for a component call — if its arguments are inspectable, app tests read them; (d) re-confirm the "Playback delay (s)" slider still runs 0–1.0 s, step 0.05, default 0.05 (§5's zero-delay budget needs 0 reachable); (e) whether 1.58 ships a second component API (recorded only); (f) the live grid's current code path and data source (`_live_grid_figure`, key `live_grid_0`); (g) the #194 R21 audit; (h) the #194 R22 search; (i) the Performance baselines. Build: the folder, `grid_canvas.js` (§4 without the paint tools), the wrapper, the helpers, the run-area grid moved onto the component with its plotly path retired, the tripwires, the wheel check (`python -m pip wheel . --no-deps -w <temp dir>`, listed, not committed), carry-outs #194 R21 and R22. DESIGN §4.1 item 5's grid sentence. Checklist C1–C7.

**1.2 — the timer-driven fragment.** Task 0: (a) a full-script AppTest pass executes a `run_every` fragment's body; (b) registering per full pass with an interval or none changes or stops the browser's timer (source; the checklist confirms); (c) what happens to a tick arriving during a running fragment pass → §5's branch; (d) whether the timer fires while its tab is hidden (source; C14 confirms); (e) what Streamlit's own Stop does to the timer; (f) every whole-loop test by function name. Build: §5 and §6's test helper. DESIGN §4.1 item 4 (its "not a fragment" sentence) and item 5. Checklist C8–C17.

**1.3 — the painter on the component.** Task 0: (a) every consumer of `paint_canvas`, `paint_cell_side`, `dragmode_for_tool`, `cells_from_selection`, `cells_along_path`, `lasso_paths`, `cells_for_tool`, `PAINTER_TOO_FINE_NOTE`, `EMPTY_CELL_COLOR`, `LayoutDraft.figure_cache`; (b) the tests that find the painter canvas by key; (c) the draft encoder at 500 × 500 → the Performance cache tripwire. Build: paint mode (§3, §4), the "Tool" radio gains "Pan (drag to move the view)", the "too fine to paint" refusal lifted (the painter stops consulting `pixel_array_active`; the 1–500 cap stays), the plotly painter and its helpers retired with replacement tests. DESIGN §4.1 item 6, §2.12 (the rendering contract and the large-grid sentence), §6.3. Checklist C18–C28.

**1.4 — stage-one close-out.** The design note (below); DESIGN §3's module tree (including its pre-existing omissions: `painter_helpers`, `sweep_helpers`, `advisories`, `export_docs`, four tabs) and §6.4 (the parked-migration trigger replaces "when maps and heavy interactivity arrive"); the owner's checklist results recorded; ROADMAP's stage-one landing line; CLAUDE.md (current phase; validation-precision: the painter's canvas for every grid, the Pan tool, `?grid_debug=1`); this spec's status line.

## Stage two — the founding preview and the Results browser (its own design session)
Invariants: one grid renderer over four surfaces when it lands; whole-state messages; the testing policy; no engine or golden change. Open questions: what replaces the ninth §12 readout "Pixel-array rendering" (#145(c), #190 R4); the #149 small-cell trigger's and 320 px width's tests; whether `grid_chart`'s grid path retires or stays for export; how the browser's Founding | Final selector (#146) feeds the component; the empty-cell look on read-only surfaces.

## Stage three — streaming charts (its own design session)
Invariants: one point per line per generation appended in JavaScript; a toggle flip asks Python for the full series once, then streams (#190 R5). Open questions: the message shape and how a series resets (a new run, a toggle flip); axes and legends in JavaScript; whether "Score view" and "Time scope" move into the component; the event-time axis (#101); the cooperation and economy charts; the post-run and browser charts; retiring the #94 throttle.

## Golden masters and engine
Display-only: zero re-recordings and zero new goldens in every stage; nothing under `pdsim/core/` or `pdsim/io/` changes; `pdsim/config/` changes only the #194 R21 scenario dicts, at values identical to those already resolved. A golden failure is a stop, never a re-record.

## Performance (the standing examination; #194 R17)
Measured and recorded in each build entry and the design note. 1.1 — encoder time and payload at 500 × 500 (synthetic full occupancy); per-pass cost before and after on a tiny Custom run and "Cooperation Survives in Clusters" (baseline #184(a)(viii): 166–226 ms per pass, engine ≈ 35 ms per generation). 1.2 — the fragment pass there (expected ≈ engine + a few ms). 1.3 — stroke round trip at 50 × 50 and 500 × 500; a whole-grid lasso at 500 × 500 (≈ 250,000 ids, ≈ 1.7 MB JSON); the draft encoder. The owner — frame time at 500 × 500 (C7, C28), target under 16 ms. Tripwires: encoder above ≈ 20 ms at 500 × 500 → cache the bytes on the draft, reset by every mutation (pre-authorised); a fragment pass more than 50 ms above the engine → stop and report, no tuning. Diffs or compression are reconsidered only per #194(d)(i).

## Design note (written in 1.4)
`docs/design-notes/M11c-grid-component-design-note.md`, from the as-built code and measurements, for a reader new to web front ends: (1) the two reports and their one cause; (2) how Streamlit draws a page — reruns and element identity — with the plotly remount as the worked example; (3) the component: the iframe, its four messages, keyed identity; (4) drawing: the off-screen image and the zoom-and-pan arithmetic worked through (500 columns in 700 px = 1.4 px per cell; eight ×1.25 steps ≈ 8.3 px, where grid lines appear); (5) painting: mount and stroke identity, the overlay, a timeline of two quick strokes; (6) the fragment: what runs when, the run-ending rerun, the interval, guard and work budget, background tabs; (7) testing: what pytest pins, the checklist, why no browser automation yet; (8) the measured numbers; (9) portability and the migration trigger; (10) what stages two and three change (sections added as they land).

## Validation (app-first, #42/#61; written at spec time)
Paths come from the record (CLAUDE.md's validation-precision paragraph, #184(a)(iii), #187, #188, #192(a)(ix)) and were label-checked against `pdsim/ui/app.py` when this file was written (#194 BUILD NOTE); each sub-prompt's handback gives its own full, verified walkthrough. The component is the project's first code pytest does not exercise (#190 R6): this checklist IS its test. Run the items a sub-prompt enables after its handback and report failures by C-number; failures become validation-feedback fixes (#180, #188). Launch with `streamlit run pdsim/ui/app.py` after `.venv\Scripts\Activate.ps1`.

After 1.1 — the run-area grid (view mode):
- C1 "Run lab" tab → the Scenario dropdown at the top of the page → "Cooperation Survives in Clusters"; leave "Generations" (in the "Dynamics" section, which starts expanded) at 100; click "Run". The grid updates in place every generation and never blanks or flashes.
- C2 During that run, turn the mouse wheel over the grid: it zooms about the pointer and stays zoomed while generations advance.
- C3 Drag on the grid: it pans. The in-grid "Fit" restores the whole grid; "+" and "−" step the zoom.
- C4 Hover a cell: "row r, col c — <strategy name>" or "— empty", counted from 1.
- C5 Streamlit's own menu (⋮, top right) → Settings → the Dark theme: the grid's background, empty cells and colour key follow; strategy colours are unchanged.
- C6 Mid-run, open the "Results browser" tab for ten seconds and return: the grid has the right size and shows the current generation.
- C7 Open the app at `http://localhost:8501/?grid_debug=1` and set up a 500 × 500 lattice run (1.1's handback gives the exact widget steps): the grid shows a frame time — note it.

After 1.2 — the fragment:
- C8 Repeat C1: nothing outside the run area flashes per generation (the charts may still rebuild up to twice a second until stage three).
- C9 Count the generations shown over ten seconds at the default "Playback delay (s)"; note the number.
- C10 Mid-run, set "Playback delay (s)" to 1.0: one generation per second. Set it to 0: as fast as the engine allows.
- C11 Mid-run, change any value in the parameter panel: the run continues unaffected; the change applies to the next Run.
- C12 Mid-run, click "Stop": the run stops within a moment, the charts stay marked "stopped early", "Run" is clickable again, and a recording (if "Record this run" was ticked) is discarded.
- C13 Tick "Record this run" and let a run finish: "Run" is clickable again, the final summary appears, and "Results browser" → "Open a run" shows the new run.
- C14 Set "Generations" to 2000, run, open the "Layout painter" tab for 30 seconds, return: the run advanced meanwhile.
- C15 The same long run: switch to another browser tab (or cover the window) for six minutes, return; note the generation reached against six minutes at C9's rate.
- C16 Mid-run, if Streamlit's own "Stop" appears at the top right, click it: the run ends without a kept folder and nothing advances afterwards.
- C17 Load "Async: Imitation Only", set "Playback delay (s)" to 0, run: it finishes in seconds, not minutes.

After 1.3 — the Layout painter:
- C18 "Layout painter" tab → "Rows" 20, "Columns" 20 → "New blank grid"; "Tool" = "Draw (drag to paint)", any "Brush"; press and drag: each cell changes colour the moment the pointer reaches it, before release.
- C19 A fast diagonal drag leaves no gaps.
- C20 A single still click paints exactly one cell.
- C21 "Brush" = "Empty (eraser)" with Draw: cells clear under the pointer as it moves.
- C22 "Rectangle (drag a box)" and "Lasso (enclose an area)": an outline follows the drag; the enclosed cells fill on release.
- C23 Two strokes in quick succession: both survive.
- C24 "Undo last stroke" undoes exactly the last stroke; "Painted agents" and "Empty cells" track every stroke.
- C25 "Tool" = "Pan (drag to move the view)": dragging moves the view; the wheel zooms under every tool; changing "Brush" keeps the zoom and position.
- C26 "Rows" 500, "Columns" 500 → "New blank grid": the canvas appears (no "too fine to paint" sentence). Zoom in, paint one cell, type a new name under "Layout file name", click "Save layout", then "Use this layout in the Run lab"; in the Run lab tick "Record this run" and click "Run": the founding grid shows the painted cell; re-running the recorded config gives identical results (1.3's handback gives the re-run steps).
- C27 "Load into painter" with a same-size file: the view is kept; change "Rows" or "Columns" and click "Resize grid": the view refits.
- C28 With `?grid_debug=1`, pan the 500 × 500 canvas: frame time under 16 ms.

## Out of scope
Stages two and three's builds (their own design sessions); browser automation (Playwright); migration off Streamlit (parked); raising the 500 × 500 cap; engine speed; everything M19 (irregular sites, capacity above 1, maps); the M11b explainer's movement/migration literature pass with its sanity check of the movement mechanism (#194 R24 — a separate design session); the nullable-number "no limit" wording (#194 R25).

## Docs obligations
Numbering continues from #195: each sub-prompt appends its build record (Task 0 findings, as-built, deviations, tests, measurements). DESIGN is amended in the sub-prompt that changes the behaviour (1.1: §4.1 item 5's grid sentence; 1.2: §4.1 items 4 and 5; 1.3: §4.1 item 6, §2.12 twice, §6.3; 1.4: §3, §6.4). ROADMAP: a landing line per sub-prompt. CLAUDE.md: the current-phase paragraph each time; the validation-precision paragraph in 1.3/1.4. This spec: status line only (1.1 → "in progress"; "implemented" when stage three lands). The design note in 1.4. `python -m pdsim.gendocs` only if the R21 edits move generated text (the drift test says). Every handback ends: run `python -m pdsim.export_docs` and upload the files it lists.
