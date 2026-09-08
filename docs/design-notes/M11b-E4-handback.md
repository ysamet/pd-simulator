# M11b Phase E4 — combined handback for the design chat

**Written 2026-09-07 by the implementation layer.** Three things in one
document: (1) Phase E4 — the mouse layout painter — as built against the
design layer's rulings (DECISIONS #186) with its build record (#187);
(2) the validation-feedback fix that followed, the "Draw" tool (#188);
(3) the owner's further request — cells painted the moment the held
pointer touches them — with what that would require, as VERIFIED
FINDINGS ONLY: no rulings and no draft prompt, since scoping is the design
layer's job (CLAUDE.md). Part 4 is the repository state and the commit
instructions. Everything here is also in the tracked docs (DECISIONS
#186–#188, DESIGN §2.12/§4.1/§6.3, ROADMAP, the spec's status line,
PARAMETERS.md, `grid_templates/README.md`); this file only gathers it.

---

## Part 1 — Phase E4 as built (DECISIONS #186 rulings, #187 build record)

### What the owner gets

A fourth top-level tab, **"Layout painter"**, second in the strip after
"Run lab". On it the owner starts a grid three ways — "New blank grid"
from "Rows" and "Columns" boxes (each 1–500), "Load into painter" over the
`.txt` files of the `grid_templates/` folder, or "Start from the Run lab's
founding preview" — chooses a **Tool** (Part 2) and a **Brush** (the
registered strategies' display names plus "Empty (eraser)"), and paints on
a canvas of square cells. "Undo last stroke" (one level), "Fill all",
"Clear all". Readouts with (?) explanations: "Sites", "Painted agents",
"Empty cells", "Saved as", plus a per-strategy caption. "Save layout"
writes an ordinary layout file into `grid_templates/` under the bare name
typed into "Layout file name" (`.txt` added when there is no extension),
opening with the fixed comment line `# written by the pdsim layout
painter`; the three shipped examples are protected, an existing file needs
"Replace the existing file" ticked. "Use this layout in the Run lab" sets
the Run lab to an evolution run on a lattice of the painting's size with
"Initial layout" `from_file` naming the saved file, and fills the
Population section in from the painting — enabled only while the canvas
matches a saved file that places at least two agents, the reason shown
beside the button otherwise. The engine is untouched: it reads a FILE
exactly as before.

### How it is built

- `pdsim/core/layouts.py` — `format_layout_file(layout, *, comment=False)`
  and `PAINTER_COMMENT_LINE`: the format's WRITE side beside the parser,
  touches no filesystem, called by no engine, config, or io path (pinned).
  The parser already skipped `#` lines (its `if not line or
  line.startswith("#"): continue` branch), so the comment branch of
  amendment (c) was built.
- `pdsim/ui/painter_helpers.py` (new, Streamlit-free) — the mutable,
  grid-size-agnostic `LayoutDraft` (rows, cols, cells, `saved_as`,
  `dirty`, one-level `undo_cells`, `figure_cache`) and pure functions:
  seeds (`blank_draft`, `draft_from_layout`, `draft_from_placements`),
  `resize_draft` (top-left overlap kept), `cells_from_selection`,
  `stroke` (the pure core — the functional-programming thread),
  `apply_brush` (counts real changes; records undo and sets dirty only
  then), `undo_stroke`, `fill_all`, `clear_all`, `draft_layout_file`
  (so `occupied_count` and `strategy_counts` are REUSED from
  `LayoutFile`), `counts_caption`, `brush_options` / `brush_from_label`,
  `template_names` (`.txt` only, read at call time), the save-name rules
  (`normalise_template_name`, `template_name_problem` — protected names
  compared case-insensitively because Windows file systems are),
  `save_draft` (UTF-8, LF), `handoff_problem`, and the protected tuple
  `SHIPPED_TEMPLATES` (three entries — see OC2 below).
- `pdsim/viz/charts.py` — `paint_cell_side` (None exactly when the
  EXISTING `pixel_array_active` predicate is true: no second threshold)
  and `paint_canvas`: the project's first INPUT figure, one scatter of
  square markers in row-major site order so a selection's point index IS
  the site id, empty sites in `EMPTY_CELL_COLOR`, legend-only traces after
  the cells trace, both axes fixed-range, explicit width and height with
  the width never below the existing 320 px floor (60 × 5 sits exactly at
  320 — the amendment (a) pin), hover "row r, col c — name | empty"
  numbered from 1 like the parser's messages. Plotly's heatmap and image
  traces have no selection support (`go.Heatmap(selectedpoints=…)`
  raises), which is why the read-only `grid_chart` cannot be the click
  surface — a recorded departure from the one-renderer discipline.
- `pdsim/ui/app.py` — the tab, `PAINTER_HELP` (every widget and readout
  has a (?)), the callbacks (seeds, stroke, undo/fill/clear, resize, the
  hand-off writing `run.mode`, `structure.kind`, `structure.rows#limit` /
  `#value`, the columns pair, `structure.initial_layout`,
  `structure.layout_file`, and the population through the EXISTING
  populate path), and the ONE change to the parameter panel: its
  lookahead block factored into `_panel_lookahead(specs)` so the
  "founding preview" seed reads the same forward values the panel does.
  Every editing control renders on every pass, greyed without a grid
  (never hidden); the canvas appears once a grid exists and is coarse
  enough to paint, else a sentence says so.
- Registry: two help-text sentences pointing at the tab (`PARAMETERS.md`
  regenerated). `pyproject.toml`: `streamlit>=1.58` (the floor was already
  false). OC2: `grid_templates/Grid_Layout_Template.md` renamed on disk to
  `grid_templates/example_template_20x20.txt`, content untouched, now a
  third loadable, protected example (400 agents on 20 × 20).

### Task 0 facts that decided things

Streamlit 1.58.0, plotly 6.8.0. Streamlit's own docstring: selection
state "cannot be programmatically changed or set through Session State",
and its test harness models no plotly element — so the stroke → cells
translation is pinned on synthetic selection dictionaries and the gestures
are owner-validated. The limit-widget keys the hand-off writes are
`structure.rows#limit` (bool) / `structure.rows#value` (int) and the
columns pair; a number input refuses an out-of-range session-state value,
so the painter's own boxes are written by callbacks only within [1, 500].
The frontend bundle keeps a figure's own drag mode and forces click-mode
to `event` under a select or lasso drag tool. Per-pass cost baseline
before the tab: 99 ms on the rerun chain, 191 ms pass by pass.

### Measurement and the cache

With the tab present and no cache, a blank 10 × 10 draft added about 50–70
ms per pass and a filled 50 × 50 draft about 105–115 ms — building the
2,500-marker figure cost 72 ms (serialisation only 1–5 ms). The
pre-authorised rebuild cache was built: `LayoutDraft.figure_cache`, reset
by every mutation and filled by the tab. With it, a same-session
comparison gave 124/238 ms without the tab, 123/230 with a blank 10 × 10
draft, 123/231 with a filled 50 × 50 draft (chain / pass-by-pass median):
inside run-to-run noise.

### Rule 7 findings (#187 part c), in plain words

- f1 — the measurement above; cache adopted.
- f2 — the recorder copies the layout file into the run folder with a
  text write that turns LF into CRLF on Windows, so the recorded copy is
  not byte-identical to the saved painting there; the parser reads both
  identically and the headless re-run matches. The test compares after
  normalising line endings. HELD: a one-line byte copy in the io layer
  would make the ruled byte-for-byte pin literal.
- f3 — `width="content"` is not inspectable headlessly (it travels on a
  part of the element the harness does not expose); the explicit width
  and height inside the figure are pinned instead.
- f4 — loading a recorded config resolves the bare `layout.txt` to an
  absolute path beside the config; the pin reads the raw YAML.
- f5 — the "Existing layout file" list catches up one pass after a save.
- f6 — the hand-off leaves the Scenario dropdown as it was, so a run
  recorded straight after it carries the previously loaded scenario's
  label in the results index. HELD: whether the hand-off should set the
  dropdown to "Custom".
- f7 — browser-only behaviour routed to the walkthrough (superseded in
  part by Part 2).
- f8 — the shipped-examples test parametrised over the three examples.

Zero re-recordings, zero new goldens; 1,255 → 1,323 tests.

---

## Part 2 — The "Draw" tool: validation feedback and the owner's ruling (DECISIONS #188)

### What the owner saw

Walkthrough step 2 asked for single cells via "the pan tool in the chart's
toolbar, then click". The toolbar showed only download, box select, lasso,
and fullscreen — no pan tool.

### Findings, verified in the installed 1.58 frontend bundle

1. Plotly builds the zoom/pan toolbar group only when NOT every axis is
   fixed-range (``g&&!D||x ? F=[`zoom2d`,`pan2d`] : …``, D = all axes
   fixed). The canvas ruling requires both axes fixed-range. Two
   requirements of one ruling that plotly cannot satisfy together.
2. A plain click on a scatter marker reaches no handler in any drag mode
   but pan: Streamlit's click handler sets a selection only for points
   carrying `id` and `parent` (sunburst-style charts) and returns for a
   scatter point; under the select and lasso tools Streamlit forces
   click-mode to `event`, so plotly's own click-to-select never runs;
   only the pan drag mode has `event+select`, and pan is what finding 1
   hides.
3. Plotly lowers its drag threshold to one pixel under the select and
   lasso tools, so a press with the slightest nudge already counts as a
   drag; a perfectly still click is a click, which nothing consumes.
4. Streamlit's selection handler forwards the lasso shape's path parsed
   into vertex lists in data coordinates (a fractional column and row per
   vertex) alongside the enclosed points — the drawn PATH itself reaches
   Python.
5. A plotly chart in Streamlit reports a COMPLETED drag only, never mouse
   motion.
6. Plotly's full toolbar override (`config.modeBarButtons`, resolving
   button names) is reachable through Streamlit's `config=` and could have
   restored the pan button — rejected by the ruling below.

### The owner's ruling (in-session, 2026-09-07)

No pan tool — "we would need a pan capability only if there is also a
zoom capability", and a painter has none. Instead a "draw" mode: press on
a cell and drag; every cell the pointer passes over takes the brush until
the button is released; no two-click combination.

### As built

A **"Tool"** radio above "Brush": "Draw (drag to paint)" (default),
"Rectangle (drag a box)", "Lasso (enclose an area)". The tool sets the
figure's own drag mode (lasso / select / lasso), so it survives the canvas
redraw after each stroke. The Draw tool rasterises the lasso PATH —
`cells_along_path`, sampling each segment every quarter cell, rounding
each sample to its cell, dropping off-grid samples, and deliberately NOT
walking the lasso's closing segment (a stroke is the path the pointer
took, not the shape it enclosed); the Rectangle and Lasso tools take the
enclosed points. `paint_canvas` gained a `dragmode` argument that accepts
only `select` and `lasso`. The one limitation, stated in the tool's help
text: the cells paint on release, and a perfectly still click paints
nothing — nudge as you press to paint one cell. Tests 1,323 → 1,334.
The pan-tool sentences of #186 R2/R7 are superseded by #188; everything
else in #186 stands. The design layer may re-open the in-session ruling.

---

## Part 3 — The further request: live painting while the button is held

### The request

In the Draw tool, cells should change colour the moment the held pointer
touches them, not only when the button is released.

### Why the current canvas cannot do it (verified)

The canvas is Streamlit's built-in plotly chart. Every visible change is a
change to the figure, and the figure lives in Python: a cell can only
change colour after a full round trip — browser event, Streamlit server,
script rerun (about 0.2 s per pass, measured), new figure, browser
redraw. The component forwards only a completed selection on mouse-up
(Part 2, finding 5) and has no hook for custom JavaScript. Even if it
forwarded in-progress events, each would rerun the script and redraw the
chart element, which interrupts the drag: `plotly_chart` registers with
`key_as_main_identity=False` and hashes the figure spec into the element
id, so a figure whose colours changed is a NEW element to the browser
(#184(a)(vii); #185 finding F5). Live painting therefore has to happen in
the browser, in JavaScript, with the result sent to Python afterwards.

### What a custom component requires — verified against the installed Streamlit 1.58.0

Every fact below was read from the installed package or its frontend
bundle in this session; nothing is from memory.

1. **The API.** `streamlit.components.v1.declare_component(name, path=None,
   url=None)` — "the path to serve the component's frontend files from;
   the path should be absolute". Streamlit serves the folder itself, so a
   hand-written `index.html` plus one JavaScript file inside the package
   (for example `pdsim/ui/paint_component/`) is a complete component: no
   Node toolchain, no build step, no new Python dependency. Calling the
   declared component in the script places an iframe and returns the
   value the iframe last sent. (`st.components.v1.html` is the one-way
   sibling — it cannot send a value back.)
2. **Identity: no remount per stroke.** A KEYED component keeps its iframe
   across reruns whatever its arguments do:
   `compute_and_register_element_id("component_instance", user_key=key,
   key_as_main_identity={"name", "url"}, …)` with the source comment
   "Ensure that the component identity is kept stable when key is
   provided; only the name and url are whitelisted to result in a new
   identity". This is the opposite of the plotly chart's behaviour and is
   what makes a flicker-free canvas possible: after a stroke Python
   re-sends the cells as arguments and the same iframe simply redraws.
3. **The protocol** (frontend `ComponentInstance.DsmFJHtV.js`), four
   message types over `window.postMessage`:
   - the iframe must first post `{type: "streamlit:componentReady",
     apiVersion: 1}` — any other version is reported as an error, and a
     value sent before it is dropped with a warning;
   - Streamlit posts `{type: "streamlit:render", args, dfs, disabled,
     theme}` on every script run, where `args` are the keyword arguments
     of the component call (JSON), and `theme` carries the active theme's
     colours plus the body font — dark mode comes for free;
   - the iframe posts `{type: "streamlit:setComponentValue", value,
     dataType}` (JSON by default; "dataframe" and "bytes" are the special
     kinds) — this is a widget value change, so it reruns the script and
     the component call returns the value;
   - the iframe posts `{type: "streamlit:setFrameHeight", height}` to size
     itself.
   A vanilla-JavaScript implementation of these four messages is a few
   dozen lines; the rest of the file is the painting itself.
4. **The painting** (JavaScript, an HTML `<canvas>` with the 2D context):
   draw `rows × cols` squares from the cells and colours received in
   `args`; on pointer-down, pointer-move while pressed, and pointer-up,
   hit-test the pointer to a cell and paint it immediately — walking a
   line between consecutive pointer positions so a fast stroke leaves no
   gaps; rectangle (two corners) and lasso (a polygon, point-in-polygon per
   cell centre) are small additions; hover text (row, column, content) is
   a mouse-move hit-test; the colour key can stay a Streamlit element
   below the canvas or be drawn in the same JavaScript. Pointer events
   cover mouse and touch alike.
5. **The round trip.** On pointer-up the iframe sends the stroke — the
   changed site ids with the brush, or the whole cell array — and Python
   applies it through the EXISTING pure helper (`apply_brush`), so undo,
   fill, clear, the readouts, save, and hand-off are untouched. One rerun
   per stroke (about 0.2 s), during which the browser already shows the
   painted cells. Two details the JavaScript must handle: the render that
   echoes the stroke back must not clobber a NEW stroke already in
   progress (ignore or merge incoming cells while the button is held), and
   the payload should be a diff rather than the whole grid once grids are
   large.
6. **What the test harness reaches.** `streamlit/testing/v1/element_tree.py`
   models no component element (no `component_instance`), so a stroke on
   the component cannot be driven headlessly — the same position as today
   — while the Python side (applying a returned stroke to the draft, the
   arguments the component is called with) is pure and pinnable. The
   JavaScript itself would be the project's first code that pytest does
   not exercise: a walkthrough checklist is its test.
7. **Packaging.** The build backend is hatchling with `[tool.hatch.build.
   targets.wheel] packages = ["pdsim"]`, which ships every file under the
   package directory, so a static component folder inside `pdsim/ui/`
   needs no extra configuration — to be confirmed by listing a built
   wheel when the component lands.
8. **Hard rules.** Untouched by construction: the component is UI only,
   writes the same layout file through the same formatter, and the engine
   still reads a FILE (rules 4 and 8). The registry gains no parameter.

### Design considerations the design layer would rule on (questions, not proposals)

- Whether the component REPLACES the plotly canvas (one renderer over the
  draft, as #186 R3 frames it) or sits beside it as the Draw surface with
  plotly kept for rectangle and lasso.
- The sync cadence (on release only, or throttled during the drag) and
  the payload shape (changed ids plus brush, or the full cell list).
- Whether the "too fine to paint" limit (#186 R3) is lifted by the
  component's own zoom and pan — an HTML canvas draws hundreds of
  thousands of cells without strain, which is exactly the large-grid
  editing surface reserved for M19 (geographic structures) in #186 R3's
  forward note. In the owner's words, pan is meaningful only once there
  is zoom.
- Where hover text and the colour key live (JavaScript or Streamlit
  elements), and how the theme colours from the render message are used.
- How the JavaScript is validated and kept from rotting: a manual
  checklist in the spec's Validation section, and whether any browser
  automation is worth adding.
- Where it sits in the plan: the E5 close-out (which already carries
  #177(f3)/(f4), #181's async well-mixed calibration branch, #182(f4) and
  (f7), #187 f2 and f6), or its own phase — it is milestone-scale (a new
  UI technology for the project and a replacement of a ruled canvas).

---

## Part 4 — Repository state and commit instructions

**Tests:** 1,334 passing (baseline before E4: 1,255). Ruff clean. Zero
golden re-recordings, zero new goldens. Working copies are LF (the
renamed sample keeps its original CRLF bytes; git normalises it).

**Validation status:** walkthrough steps 1 and 2 were exercised (the
rectangles painted; step 2 has been rewritten for the Draw tool);
steps 2 (Draw/Lasso gestures) and 3–11 remain for the owner.

**Files to stage** (nothing is staged; the owner commits):

```
CLAUDE.md
docs/DECISIONS.md
docs/DESIGN.md
docs/PARAMETERS.md
docs/ROADMAP.md
docs/design-notes/M11b-E4-handback.md            (new: this file)
docs/design-notes/M11b-E4-painter-prompt-draft.md
docs/specs/M11b-movement-and-panel-spec.md
grid_templates/Grid_Layout_Template.md            (deleted)
grid_templates/example_template_20x20.txt         (added: the renamed sample)
grid_templates/README.md
pdsim/config/registry.py
pdsim/core/layouts.py
pdsim/ui/app.py
pdsim/ui/painter_helpers.py                       (new)
pdsim/viz/charts.py
pdsim/tests/test_app.py
pdsim/tests/test_charts.py
pdsim/tests/test_layouts.py
pdsim/tests/test_painter_helpers.py               (new)
pyproject.toml
```

Not to stage: `docs/WIP.md` (git-ignored hand-off note for the next
session) and the paintings the owner's validation created under
`grid_templates/` (`my_first_painting.txt`, `test1.txt`, `lonely.txt` if
present) unless the owner wants to keep them.

**Suggested commit message:**

```
feat(ui): M11b E4 mouse layout painter — "Layout painter" tab, input canvas with Draw/Rectangle/Lasso tools, painter_helpers, format_layout_file (#186/#187/#188)

Fourth top-level tab, second in the strip. charts.paint_canvas: one
scatter of square markers in row-major site order (point index = site
id), fixed-range axes, width never below 320 px, rendered exactly where
pixel_array_active is false. A "Tool" radio sets the canvas's drag mode:
Draw rasterises the lasso path as a brush stroke (every cell the pointer
crossed, painted on release), Rectangle and Lasso take the enclosed
cells; no pan tool (#188 — plotly hides pan under fixed axes and a plain
click reaches no handler). Streamlit-free ui/painter_helpers.py with the
grid-size-agnostic LayoutDraft (stroke as a pure transformation,
one-level undo, fill, clear, resize, figure cache reset on every
mutation). layouts.format_layout_file as the format's write side (one
fixed comment line). Saves into grid_templates/ under bare names; three
protected examples (Grid_Layout_Template.md renamed to
example_template_20x20.txt). Hand-off callback through the existing
populate path, enabled only for a saved, unchanged draft placing at
least two agents. Three seeds via the factored _panel_lookahead. Two
registry help sentences, PARAMETERS.md regenerated, streamlit>=1.58.
Zero re-recordings, zero new goldens; 1334 tests.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

**DOCS CHANGED** (to refresh in the Claude.ai project knowledge):
`docs/DECISIONS.md` (new entries #186, #187, #188), `docs/DESIGN.md`,
`docs/ROADMAP.md`, `docs/PARAMETERS.md`,
`docs/specs/M11b-movement-and-panel-spec.md`,
`docs/design-notes/M11b-E4-painter-prompt-draft.md`,
`docs/design-notes/M11b-E4-handback.md`, plus `CLAUDE.md` and
`grid_templates/README.md`.

**Next per ROADMAP:** Phase E5 close-out, carrying the held items listed
in CLAUDE.md's current-phase paragraph, plus — for the design layer to
place — the live-painting component of Part 3.
