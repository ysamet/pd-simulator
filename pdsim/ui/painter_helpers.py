"""Streamlit-free helpers behind the Layout painter tab (M11b Phase E4).

The same split as :mod:`pdsim.ui.helpers` and :mod:`pdsim.ui.sweep_helpers`
(DECISIONS #38): every branch worth testing lives here, importable without
Streamlit, and the tab function in ``app.py`` stays a thin rendering shell.

**What the painter is.** A UI TOOL that WRITES layout files — the very files
a config's ``structure.layout_file`` references and the engine reads at
founding (DECISIONS #109; DESIGN §2.12). The engine only ever reads data:
it never learns a mouse was involved (hard rule 4), and a recorded run
re-runs from its config alone because the recorder copies the file into the
run folder (hard rule 8). Nothing here touches a draw, a config default, or
a validator; the one core addition the painter needed is the pure text
formatter :func:`pdsim.core.layouts.format_layout_file`, so the layout-file
FORMAT keeps a single home (#186 R5).

**Grid-size-agnostic on purpose** (#186 R3's forward note). The
:class:`LayoutDraft` and every function below speak only of rows, columns,
and cells — never of pixels. The mouse canvas the app draws today
(:func:`pdsim.viz.charts.paint_canvas`) is ONE renderer over the draft, kept
within the regime where cells are large enough to click; M19's large-grid
editing surface — a zoomed viewport with region tools over the pixel-array
regime, or a map-shaped site set — is a SECOND renderer over this same
draft and this same save path, with no engine implication.

**The functional-programming thread.** A stroke is a pure transformation
of the cells: :func:`stroke` takes a sequence of cells and returns a NEW
list with the brush applied to the chosen indices, leaving its input
untouched. The mutable :class:`LayoutDraft` is a thin holder around that
pure core — :func:`apply_brush` calls :func:`stroke`, compares before and
after, and only then commits (recording the undo snapshot). Keeping the
transformation pure is what makes undo a one-liner and the stroke testable
without any UI: the same idea as strategies-as-composable-functions, one
level up.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pdsim.core import layouts
from pdsim.core.layouts import LAYOUT_FILE_KIND, LayoutFile, format_layout_file
from pdsim.core.strategies import all_strategies

SHIPPED_TEMPLATES: tuple[str, ...] = (
    "example_quadrants.txt",
    "example_island.txt",
    "example_template_20x20.txt",
)
"""The layout files that ship with the repository and may never be overwritten.

The painter refuses these names on save (#186 R5). A test pins that every
``example_*.txt`` actually present in ``grid_templates/`` appears here, so a
later shipped example cannot be overwritten silently because nobody added it
(#186 amendment b). The third entry is the owner's 20 × 20 sample, renamed
from ``Grid_Layout_Template.md`` in Phase E4 (#186 OC2).
"""

ERASER_LABEL = "Empty (eraser)"
"""The brush option that paints empty cells — the radio's last entry (#186 R8)."""

MAX_PAINTER_DIMENSION = 500
"""Upper bound of the painter's Rows / Columns boxes (#186 R7).

Generous on purpose: the canvas itself refuses what cannot be painted by
mouse through :func:`pdsim.viz.charts.paint_cell_side` (#186 R3), so this
bound only keeps the number boxes sane.
"""

TOOL_DRAW = "Draw (drag to paint)"
"""The brush stroke: every cell the pointer passes over takes the brush (#188)."""

TOOL_RECTANGLE = "Rectangle (drag a box)"
"""The box: every cell inside the dragged rectangle takes the brush."""

TOOL_LASSO = "Lasso (enclose an area)"
"""The enclosure: every cell inside the drawn shape takes the brush."""

TOOL_OPTIONS: tuple[str, ...] = (TOOL_DRAW, TOOL_RECTANGLE, TOOL_LASSO)
"""The "Tool" radio's options, in display order; the first is the default.

The owner's in-session ruling of DECISIONS #188, replacing the "pan tool,
then click" single-cell path of #186: a plotly chart inside Streamlit can
report only a COMPLETED drag (a box or a lasso), never mouse motion or a
plain click on a scatter marker — Streamlit's click handler acts only on
hierarchical charts, and click-to-select exists only in the pan drag mode,
whose toolbar button plotly hides under fixed-range axes. So all three
tools are drags; what differs is how the app reads the drag back.
"""

STROKE_STEP = 0.25
"""Sampling step along a Draw stroke, in cell units (a quarter of a cell).

The lasso path comes back as vertices in data coordinates — a column index
and a row index per vertex, fractional. Walking each segment at quarter-cell
steps and rounding every sample to its cell visits every cell the segment
crosses, so a fast stroke leaves no gaps.
"""


@dataclass
class LayoutDraft:
    """The painting in progress, kept in app state between script passes.

    A mutable ``@dataclass`` like :class:`~pdsim.ui.helpers.LiveRun` (the
    holder pattern of M11b Phase E3): the fields stay assignable, which a
    draft that changes with every stroke needs. Session state keeps the
    reference; nothing is pickled.

    Attributes:
        rows: Grid rows.
        cols: Grid columns.
        cells: One entry per site in row-major order (``id = row * cols +
            col``, matching the layout file and the lattice) — a strategy
            machine name, or ``None`` for an empty site.
        saved_as: The bare file name the draft was last saved under (or
            loaded from), or ``None`` while it has never been saved.
        dirty: Whether the cells changed since the last save or load — the
            hand-off gate reads it (#186 R6, amendment d).
        undo_cells: The cells as they were before the last effective stroke
            (one level of undo, #186 R9), or ``None`` when there is nothing
            to undo.
        figure_cache: The app's built canvas figure for the CURRENT cells,
            or ``None`` when it must be rebuilt. Every mutation below resets
            it — the pre-authorised rebuild cache of #186 R12, measured and
            adopted in #187 — and the app fills it. Typed loosely so this
            module stays free of any plotting import; it is never compared.
    """

    rows: int
    cols: int
    cells: list[str | None]
    saved_as: str | None = None
    dirty: bool = False
    undo_cells: list[str | None] | None = None
    figure_cache: object | None = field(default=None, repr=False, compare=False)

    @property
    def site_count(self) -> int:
        """How many cells the grid has.

        Returns:
            ``rows × cols``.
        """
        return self.rows * self.cols


def _check_dimensions(rows: int, cols: int) -> None:
    """Refuse a grid without at least one row and one column.

    Args:
        rows: Grid rows.
        cols: Grid columns.

    Raises:
        ValueError: If either dimension is below 1.
    """
    if rows < 1 or cols < 1:
        raise ValueError(f"A grid needs at least 1 row and 1 column, got {rows}x{cols}.")


def blank_draft(rows: int, cols: int) -> LayoutDraft:
    """Start an empty grid.

    Args:
        rows: Grid rows.
        cols: Grid columns.

    Returns:
        A draft with every cell empty, unsaved and clean.

    Raises:
        ValueError: If either dimension is below 1.
    """
    _check_dimensions(rows, cols)
    return LayoutDraft(rows=rows, cols=cols, cells=[None] * (rows * cols))


def draft_from_layout(layout: LayoutFile) -> LayoutDraft:
    """Start from a parsed layout file.

    Args:
        layout: The parsed file (its cells are already row-major).

    Returns:
        A draft holding the file's cells; ``saved_as`` is left for the
        caller, which knows the file's name.
    """
    return LayoutDraft(rows=layout.rows, cols=layout.cols, cells=list(layout.cells))


def draft_from_placements(rows: int, cols: int, placements: Mapping[int, str]) -> LayoutDraft:
    """Start from a founding arrangement (site id → strategy machine name).

    The shape :func:`pdsim.core.layouts.founding_view` produces, so the Run
    lab's founding preview can seed the painter (#186 R7).

    Args:
        rows: Grid rows.
        cols: Grid columns.
        placements: Occupied sites only; absent ids are empty cells.

    Returns:
        A draft with the placements painted in.

    Raises:
        ValueError: If a dimension is below 1 or a site id is outside the grid.
    """
    _check_dimensions(rows, cols)
    cells: list[str | None] = [None] * (rows * cols)
    for site_id, name in placements.items():
        if not 0 <= site_id < rows * cols:
            raise ValueError(f"Site id {site_id} lies outside a {rows}x{cols} grid.")
        cells[site_id] = name
    return LayoutDraft(rows=rows, cols=cols, cells=cells)


def resized_cells(
    cells: Sequence[str | None], rows: int, cols: int, new_rows: int, new_cols: int
) -> list[str | None]:
    """The pure core of :func:`resize_draft`: re-shape a cell list.

    The top-left overlap is kept cell for cell; growth is padded with empty
    cells; cells outside the new size are dropped.

    Args:
        cells: The current cells, row-major over ``rows × cols``.
        rows: Current rows.
        cols: Current columns.
        new_rows: Target rows.
        new_cols: Target columns.

    Returns:
        A new list, row-major over ``new_rows × new_cols``.
    """
    resized: list[str | None] = [None] * (new_rows * new_cols)
    for row in range(min(rows, new_rows)):
        for col in range(min(cols, new_cols)):
            resized[row * new_cols + col] = cells[row * cols + col]
    return resized


def resize_draft(draft: LayoutDraft, rows: int, cols: int) -> None:
    """Re-shape a draft in place, keeping the top-left overlap (#186 R7).

    Never implicit: the app calls this only from its explicit "Resize grid"
    button, because a resize can discard painted cells. The undo snapshot is
    cleared — it has the old shape and could not be restored onto the new one.

    Args:
        draft: The draft to re-shape.
        rows: Target rows.
        cols: Target columns.

    Raises:
        ValueError: If either dimension is below 1.
    """
    _check_dimensions(rows, cols)
    if (rows, cols) == (draft.rows, draft.cols):
        return
    draft.cells = resized_cells(draft.cells, draft.rows, draft.cols, rows, cols)
    draft.rows = rows
    draft.cols = cols
    draft.undo_cells = None
    draft.dirty = True
    draft.figure_cache = None


def cells_from_selection(
    selection: Mapping[str, object] | None, site_count: int
) -> tuple[int, ...]:
    """Translate a plotly selection into site ids — the stroke's input.

    Pure, and pinned on synthetic selection dictionaries (#186 R12): a mouse
    stroke cannot be driven headlessly — Streamlit's own docstring says
    selection state "cannot be programmatically changed or set through
    Session State", and its test harness models no plotly element — so this
    translation is the part a test CAN reach. The canvas draws its cells as
    ONE scatter trace in row-major site order (#186 R2), which is what makes
    ``point_index`` the site id; legend-only traces come after it, so only
    entries on curve 0 count.

    Args:
        selection: Streamlit's ``PlotlySelectionState`` — a mapping with a
            ``points`` sequence of per-point mappings — or ``None``.
        site_count: ``rows × cols``; indices outside ``[0, site_count)``
            are dropped.

    Returns:
        The selected site ids, de-duplicated and ascending; empty when the
        selection is missing, has no ``points``, or holds nothing usable.
    """
    if not selection:
        return ()
    points = selection.get("points")
    if not points:
        return ()
    chosen: set[int] = set()
    for point in points:
        curve = point.get("curve_number", 0)
        if curve not in (0, None):
            continue
        index = point.get("point_index")
        # bool is an int subclass; a True here would be a schema surprise,
        # not a site id.
        if isinstance(index, bool) or not isinstance(index, int):
            continue
        if 0 <= index < site_count:
            chosen.add(index)
    return tuple(sorted(chosen))


def stroke(
    cells: Sequence[str | None], targets: Iterable[int], brush: str | None
) -> list[str | None]:
    """Apply a brush to some cells — a PURE transformation (the FP thread).

    The input is never modified; a new list comes back. Every targeted cell
    takes the brush, occupied cells included — it is a painter, not a fill
    of empty space (#186 R9).

    Args:
        cells: The current cells.
        targets: Site ids to paint (already within range).
        brush: A strategy machine name, or ``None`` for the eraser.

    Returns:
        The cells after the stroke.
    """
    painted = list(cells)
    for index in targets:
        painted[index] = brush
    return painted


def dragmode_for_tool(tool: str) -> str:
    """The plotly drag mode the canvas needs for a tool.

    Args:
        tool: One of :data:`TOOL_OPTIONS`.

    Returns:
        ``"lasso"`` for the Draw and Lasso tools (both are freehand drags —
        the app reads the drag back differently), ``"select"`` for the
        Rectangle tool.

    Raises:
        ValueError: If the tool is unknown — a silent default would paint
            with the wrong gesture.
    """
    if tool in (TOOL_DRAW, TOOL_LASSO):
        return "lasso"
    if tool == TOOL_RECTANGLE:
        return "select"
    raise ValueError(f"Unknown painter tool {tool!r}; expected one of {TOOL_OPTIONS}.")


def cells_along_path(
    xs: Sequence[float], ys: Sequence[float], rows: int, cols: int
) -> tuple[int, ...]:
    """Every cell a freehand path passes through — the Draw tool's brush stroke.

    Pure (the FP thread again: a polyline in, a set of site ids out). The
    path is the lasso's vertex list in data coordinates, where cell
    ``(row, col)`` is centred at ``x = col``, ``y = row`` and spans half a
    cell each way. Each segment is sampled every :data:`STROKE_STEP` cell
    units (endpoints included) and every sample is rounded to its cell;
    the lasso's closing segment (last vertex back to the first) is NOT part
    of the vertex list and is deliberately not walked — a brush stroke is
    the path the pointer took, not the shape it enclosed. Samples outside
    the grid are dropped.

    Args:
        xs: The vertices' x coordinates (column axis).
        ys: The vertices' y coordinates (row axis), same length.
        rows: Grid rows.
        cols: Grid columns.

    Returns:
        The crossed site ids, de-duplicated and ascending; empty for an
        empty path or one entirely outside the grid.

    Raises:
        ValueError: If the two coordinate sequences differ in length.
    """
    if len(xs) != len(ys):
        raise ValueError(f"A path needs as many x as y values, got {len(xs)} and {len(ys)}.")
    chosen: set[int] = set()

    def visit(x: float, y: float) -> None:
        """Add the cell under one sample, if it lies on the grid."""
        col = math.floor(x + 0.5)  # nearest integer, ties rounding up (not banker's)
        row = math.floor(y + 0.5)
        if 0 <= row < rows and 0 <= col < cols:
            chosen.add(row * cols + col)

    points = [(float(x), float(y)) for x, y in zip(xs, ys, strict=True)]
    if not points:
        return ()
    x0, y0 = points[0]
    visit(x0, y0)
    for x1, y1 in points[1:]:
        steps = max(1, math.ceil(max(abs(x1 - x0), abs(y1 - y0)) / STROKE_STEP))
        for i in range(1, steps + 1):
            fraction = i / steps
            visit(x0 + (x1 - x0) * fraction, y0 + (y1 - y0) * fraction)
        x0, y0 = x1, y1
    return tuple(sorted(chosen))


def lasso_paths(selection: Mapping[str, object] | None) -> list[tuple[list[float], list[float]]]:
    """The freehand paths a plotly selection carries, as coordinate lists.

    Streamlit's selection state lists lasso shapes under ``lasso`` — one
    mapping per shape with ``x`` and ``y`` vertex lists in data coordinates
    (its frontend parses the SVG path of plotly's selection shape). Entries
    without both lists, or with mismatched lengths, are skipped.

    Args:
        selection: Streamlit's ``PlotlySelectionState`` mapping, or ``None``.

    Returns:
        ``(xs, ys)`` per lasso shape, in order; empty when there is none.
    """
    if not selection:
        return []
    entries = selection.get("lasso")
    paths: list[tuple[list[float], list[float]]] = []
    for entry in entries or ():
        xs = entry.get("x") if isinstance(entry, Mapping) else None
        ys = entry.get("y") if isinstance(entry, Mapping) else None
        if not xs or not ys or len(xs) != len(ys):
            continue
        try:
            paths.append(([float(x) for x in xs], [float(y) for y in ys]))
        except (TypeError, ValueError):
            continue
    return paths


def cells_for_tool(
    tool: str, selection: Mapping[str, object] | None, rows: int, cols: int
) -> tuple[int, ...]:
    """Translate one completed drag into the cells a tool paints (#188).

    The Draw tool reads the drag as a STROKE: the lasso path's vertices,
    rasterised by :func:`cells_along_path`, whatever the shape encloses. The
    Rectangle and Lasso tools read it as an ENCLOSURE: the points plotly
    reports inside the box or the shape, through
    :func:`cells_from_selection`. A Draw drag that carries no path (which
    plotly does not produce, but the schema allows) falls back to the
    enclosed points rather than painting nothing.

    Args:
        tool: One of :data:`TOOL_OPTIONS`.
        selection: Streamlit's ``PlotlySelectionState`` mapping, or ``None``.
        rows: Grid rows.
        cols: Grid columns.

    Returns:
        The site ids to paint, de-duplicated and ascending.

    Raises:
        ValueError: If the tool is unknown.
    """
    if tool == TOOL_DRAW:
        chosen: set[int] = set()
        for xs, ys in lasso_paths(selection):
            chosen.update(cells_along_path(xs, ys, rows, cols))
        if chosen:
            return tuple(sorted(chosen))
        return cells_from_selection(selection, rows * cols)
    if tool in (TOOL_RECTANGLE, TOOL_LASSO):
        return cells_from_selection(selection, rows * cols)
    raise ValueError(f"Unknown painter tool {tool!r}; expected one of {TOOL_OPTIONS}.")


def apply_brush(draft: LayoutDraft, cells: Iterable[int], brush: str | None) -> int:
    """Paint the given cells with the brush; report how many actually changed.

    Commits only when something changed: the undo snapshot is recorded and
    ``dirty`` set exactly then, so a no-op stroke (the same brush over cells
    that already carry it) leaves the draft — and its undo level — alone.

    Args:
        draft: The draft to paint.
        cells: Site ids to paint; ids outside the grid are ignored.
        brush: A strategy machine name, or ``None`` for the eraser.

    Returns:
        The number of cells whose content changed.
    """
    targets = [index for index in cells if 0 <= index < draft.site_count]
    after = stroke(draft.cells, targets, brush)
    changed = sum(1 for before, now in zip(draft.cells, after, strict=True) if before != now)
    if changed:
        draft.undo_cells = list(draft.cells)
        draft.cells = after
        draft.dirty = True
        draft.figure_cache = None
    return changed


def undo_stroke(draft: LayoutDraft) -> bool:
    """Restore the cells from before the last effective stroke (one level).

    One level only (#186 R9): the snapshot is consumed, so a second press
    does nothing — the stroke before the last one cannot be recovered.

    Args:
        draft: The draft to restore.

    Returns:
        True when a stroke was undone; False when there was nothing to undo.
    """
    if draft.undo_cells is None:
        return False
    draft.cells = draft.undo_cells
    draft.undo_cells = None
    draft.dirty = True
    draft.figure_cache = None
    return True


def fill_all(draft: LayoutDraft, brush: str | None) -> int:
    """Paint every cell with the brush (undoable like any stroke).

    Args:
        draft: The draft to paint.
        brush: A strategy machine name, or ``None`` for the eraser.

    Returns:
        The number of cells whose content changed.
    """
    return apply_brush(draft, range(draft.site_count), brush)


def clear_all(draft: LayoutDraft) -> int:
    """Empty every cell (undoable like any stroke).

    Args:
        draft: The draft to clear.

    Returns:
        The number of cells whose content changed.
    """
    return apply_brush(draft, range(draft.site_count), None)


def draft_layout_file(draft: LayoutDraft) -> LayoutFile:
    """View the draft as a :class:`~pdsim.core.layouts.LayoutFile`.

    This is how the painter derives its counts: ``occupied_count`` and
    ``strategy_counts()`` are REUSED from the layout-file dataclass, never
    re-implemented here (#186 R4), so the painter's "Painted agents" and the
    population the hand-off sets come from one arithmetic.

    Args:
        draft: The draft to view.

    Returns:
        A layout-file value with the draft's cells (no file positions — it
        was never parsed from text).
    """
    return LayoutFile(
        kind=LAYOUT_FILE_KIND, rows=draft.rows, cols=draft.cols, cells=tuple(draft.cells)
    )


def counts_caption(draft: LayoutDraft) -> str:
    """The per-strategy counts as one line, display names in registry order.

    Registry order is the app's display convention (the brush radio, the
    canvas legend, and the Population section all use it), so the caption
    reads in the same order the owner sees everywhere else.

    Args:
        draft: The draft to count.

    Returns:
        ``"Tit for Tat 18, Always Defect 6"`` style text, or ``""`` when no
        cell is painted.
    """
    counts = draft_layout_file(draft).strategy_counts()
    parts = [
        f"{info.display_name} {counts[info.name]}"
        for info in all_strategies()
        if info.name in counts
    ]
    return ", ".join(parts)


def brush_options() -> list[str]:
    """The brush radio's options: display names in registry order, then the eraser.

    Returns:
        The labels, never a hardcoded list (#186 R8) — a newly registered
        strategy appears as a brush with zero UI edits.
    """
    return [*(info.display_name for info in all_strategies()), ERASER_LABEL]


def brush_from_label(label: str | None) -> str | None:
    """Map a brush radio label back to the brush the stroke applies.

    Args:
        label: A display name from :func:`brush_options`, or the eraser label.

    Returns:
        The strategy machine name, or ``None`` for the eraser (also for a
        missing label — the radio has not rendered yet).

    Raises:
        ValueError: If the label names no registered strategy — a silent
            fallback to the eraser would paint the wrong thing.
    """
    if label is None or label == ERASER_LABEL:
        return None
    for info in all_strategies():
        if info.display_name == label:
            return info.name
    raise ValueError(f"Unknown brush {label!r}; expected one of {brush_options()}.")


def template_names() -> list[str]:
    """The layout files the painter can load: ``.txt`` files in the templates folder.

    Read at call time from :data:`pdsim.core.layouts.GRID_TEMPLATES_DIR` (so a
    test can redirect the folder), listing ``.txt`` files ONLY — the README
    states the rule; anything else in the folder (the README itself) is not a
    layout to offer.

    Returns:
        The bare file names, sorted; empty when the folder does not exist.
    """
    directory = layouts.GRID_TEMPLATES_DIR
    if not directory.is_dir():
        return []
    return sorted(
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".txt"
    )


def normalise_template_name(name: str) -> str:
    """Give a typed file name its ``.txt`` suffix when it has no suffix at all.

    Args:
        name: What the owner typed (whitespace already stripped by callers).

    Returns:
        ``"my_painting"`` → ``"my_painting.txt"``; a name that already has a
        suffix (``"my_painting.txt"``, ``"notes.md"``) is returned unchanged.
    """
    return name if Path(name).suffix else f"{name}.txt"


def template_name_problem(name: str, *, exists: bool, replace: bool) -> str | None:
    """Why a save under this name is refused, or ``None`` when it is allowed.

    The #122 bare-name rule in reverse: a layout file is saved into the
    templates folder under a bare name, which is exactly what the Run lab's
    "Layout file" box looks up. The shipped examples are protected (#186
    R5); an existing file needs the explicit replace checkbox. The
    protection check ignores letter case because Windows file systems do —
    ``Example_Island.txt`` would overwrite ``example_island.txt`` there.

    Args:
        name: What the owner typed.
        exists: Whether a file under the normalised name already exists.
        replace: Whether the "Replace the existing file" checkbox is ticked.

    Returns:
        A plain-language sentence naming the problem and the fix, or ``None``.
    """
    stripped = name.strip()
    if not stripped:
        return "Give the layout a file name before saving."
    if (
        "/" in stripped
        or "\\" in stripped
        or Path(stripped).is_absolute()
        or Path(stripped).name != stripped
        or not any(character.isalnum() for character in stripped)
    ):
        return (
            "Use a bare file name with letters or digits and no folder or path "
            "separator — layouts are saved into the grid_templates folder, and a bare "
            "name is exactly what the Run lab's Layout file box looks up."
        )
    normalised = normalise_template_name(stripped)
    if normalised.lower() in {shipped.lower() for shipped in SHIPPED_TEMPLATES}:
        return (
            f"'{normalised}' is one of the shipped examples and cannot be overwritten — "
            "choose another name."
        )
    if exists and not replace:
        return (
            f"A file named '{normalised}' already exists in the grid_templates folder — "
            "tick 'Replace the existing file' to overwrite it, or choose another name."
        )
    return None


def save_draft(draft: LayoutDraft, directory: Path, name: str, *, comment: bool = True) -> Path:
    """Write the draft as a layout file and mark the draft saved.

    The text is exactly :func:`pdsim.core.layouts.format_layout_file` of
    :func:`draft_layout_file`, written with LF line endings on every
    platform (the repository's convention) so identical paintings are
    identical bytes wherever they are saved. Callers run
    :func:`template_name_problem` first; this function does not re-check.

    Args:
        draft: The draft to save.
        directory: The folder to write into (the app passes
            :data:`pdsim.core.layouts.GRID_TEMPLATES_DIR`).
        name: The typed name; :func:`normalise_template_name` is applied.
        comment: Whether the file opens with the fixed painter comment line
            (the app passes True; the parser skips ``#`` lines).

    Returns:
        The written path.
    """
    normalised = normalise_template_name(name.strip())
    path = Path(directory) / normalised
    path.parent.mkdir(parents=True, exist_ok=True)
    text = format_layout_file(draft_layout_file(draft), comment=comment)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    draft.saved_as = normalised
    draft.dirty = False
    return path


def handoff_problem(draft: LayoutDraft | None) -> str | None:
    """Why the hand-off to the Run lab is disabled, or ``None`` when it is live.

    The gate of #186 R6, amendment (d): the Run lab's config must reference a
    FILE (hard rule 8), that file must be what the canvas shows, and the
    config validator refuses a layout placing fewer than two agents (#126).

    Args:
        draft: The current draft, or ``None`` before any grid exists.

    Returns:
        The reason shown beside the greyed button, or ``None``.
    """
    if draft is None:
        return "Start a grid first — there is nothing to hand off yet."
    if draft.saved_as is None:
        return (
            "Save the layout first — the Run lab references a FILE, so an unsaved "
            "painting has nothing to point at."
        )
    if draft.dirty:
        return (
            f"The painting has changed since it was saved as '{draft.saved_as}' — save it "
            "again (or undo the change) before handing it off."
        )
    painted = draft_layout_file(draft).occupied_count
    if painted < 2:
        return (
            f"A layout must place at least two agents before it can found a run; this one "
            f"places {painted}."
        )
    return None
