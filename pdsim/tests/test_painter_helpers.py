"""Tests for the Streamlit-free Layout painter helpers (M11b Phase E4).

DECISIONS #186 R12: a mouse stroke cannot be driven headlessly — Streamlit's
selection state "cannot be programmatically changed or set through Session
State" and its test harness models no plotly element — so everything a
stroke DOES is pinned here on the pure functions: the selection → site-id
translation on synthetic selection dictionaries of the documented schema,
the stroke as a pure transformation of the cells, undo, the derived counts,
the file-name rules, the save, and the hand-off gate. No Streamlit import
anywhere — that is the point of the helper layer (DECISIONS #38).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pdsim.core import layouts
from pdsim.core.layouts import PAINTER_COMMENT_LINE, format_layout_file, parse_layout_file
from pdsim.core.strategies import all_strategies
from pdsim.ui import painter_helpers as ph

AC = "always_cooperate"
AD = "always_defect"
TFT = "tit_for_tat"

ISLAND_TEXT = (
    "kind: lattice_grid\nrows: 4\ncols: 6\n\n"
    f"{AD} {AD} {AD} {AD} {AD} {AD}\n"
    f"{AD} {TFT} {TFT} {TFT} {AD} {AD}\n"
    f"{AD} {TFT} {TFT} {TFT} {AD} {AD}\n"
    f"{AD} {AD} {AD} {AD} {AD} {AD}\n"
)
"""The island example as whitespace text: 24 agents, 18 defectors, 6 TFT."""


def _painted(draft: ph.LayoutDraft) -> int:
    """The painted-agent count, through the layout-file arithmetic.

    Args:
        draft: The draft to count.

    Returns:
        ``occupied_count`` of the draft viewed as a layout file.
    """
    return ph.draft_layout_file(draft).occupied_count


class TestDraftSeeds:
    """blank / from-layout / from-placements / resize."""

    def test_blank_draft_is_empty_clean_and_unsaved(self) -> None:
        """A new grid has every cell empty and nothing to undo or hand off."""
        draft = ph.blank_draft(6, 8)
        assert (draft.rows, draft.cols, draft.site_count) == (6, 8, 48)
        assert draft.cells == [None] * 48
        assert draft.saved_as is None
        assert draft.dirty is False
        assert draft.undo_cells is None
        assert _painted(draft) == 0

    def test_blank_draft_refuses_a_zero_dimension(self) -> None:
        """A grid needs at least one row and one column."""
        with pytest.raises(ValueError, match="at least 1 row"):
            ph.blank_draft(0, 5)
        with pytest.raises(ValueError, match="at least 1 row"):
            ph.blank_draft(5, 0)

    def test_draft_from_layout_copies_the_cells(self) -> None:
        """A parsed file's cells land in the draft in row-major order."""
        layout = parse_layout_file(ISLAND_TEXT)
        draft = ph.draft_from_layout(layout)
        assert (draft.rows, draft.cols) == (4, 6)
        assert draft.cells == list(layout.cells)
        assert draft.cells[7] == TFT  # row 1, col 1 — the island's corner
        assert _painted(draft) == 24
        assert draft.saved_as is None  # the caller knows the file's name

    def test_draft_from_placements_paints_the_given_sites(self) -> None:
        """The founding-view shape: site id → name; absent ids stay empty."""
        draft = ph.draft_from_placements(2, 3, {0: AC, 5: AD})
        assert draft.cells == [AC, None, None, None, None, AD]
        with pytest.raises(ValueError, match="outside"):
            ph.draft_from_placements(2, 3, {6: AC})

    def test_resize_keeps_the_top_left_overlap_and_pads_growth(self) -> None:
        """Shrinking drops cells outside the new size; growing adds empty ones."""
        cells: list[str | None] = ["a", "b", "c", "d", "e", "f"]  # 2 × 3
        assert ph.resized_cells(cells, 2, 3, 3, 2) == ["a", "b", "d", "e", None, None]
        assert ph.resized_cells(cells, 2, 3, 1, 4) == ["a", "b", "c", None]
        assert ph.resized_cells(cells, 2, 3, 2, 3) == cells
        draft = ph.LayoutDraft(rows=2, cols=3, cells=list(cells))
        ph.resize_draft(draft, 3, 2)
        assert (draft.rows, draft.cols) == (3, 2)
        assert draft.cells == ["a", "b", "d", "e", None, None]

    def test_resize_to_the_same_shape_changes_nothing(self) -> None:
        """A no-op resize leaves the draft clean, its undo and cache intact."""
        draft = ph.blank_draft(2, 3)
        draft.undo_cells = [None] * 6
        draft.figure_cache = object()
        ph.resize_draft(draft, 2, 3)
        assert draft.dirty is False
        assert draft.undo_cells is not None
        assert draft.figure_cache is not None

    def test_resize_clears_undo_marks_dirty_and_invalidates_the_cache(self) -> None:
        """A real resize cannot be undone across shapes and needs a new figure."""
        draft = ph.blank_draft(2, 3)
        ph.apply_brush(draft, [0], AC)
        draft.figure_cache = object()
        ph.resize_draft(draft, 3, 3)
        assert draft.undo_cells is None
        assert draft.dirty is True
        assert draft.figure_cache is None
        with pytest.raises(ValueError, match="at least 1 row"):
            ph.resize_draft(draft, 0, 3)


class TestSelectionTranslation:
    """``cells_from_selection`` on synthetic selection dictionaries (#186 R12)."""

    def test_a_single_point(self) -> None:
        """One clicked marker → one site id."""
        selection = {"points": [{"curve_number": 0, "point_index": 7, "x": 1, "y": 1}]}
        assert ph.cells_from_selection(selection, 24) == (7,)

    def test_a_box_selection_comes_back_ascending_and_deduplicated(self) -> None:
        """A rectangle's points list, in any order, with repeats."""
        points = [{"curve_number": 0, "point_index": index} for index in (9, 3, 8, 3, 2)]
        assert ph.cells_from_selection({"points": points}, 24) == (2, 3, 8, 9)

    def test_legend_trace_entries_are_dropped(self) -> None:
        """Only curve 0 — the cells trace — counts; a legend trace never paints."""
        points = [
            {"curve_number": 1, "point_index": 0},
            {"curve_number": 0, "point_index": 4},
            {"point_index": 5},  # curve_number absent: treated as the cells trace
        ]
        assert ph.cells_from_selection({"points": points}, 24) == (4, 5)

    def test_out_of_range_and_malformed_indices_are_dropped(self) -> None:
        """Indices outside [0, site_count) and non-integers never reach the stroke."""
        points = [
            {"curve_number": 0, "point_index": -1},
            {"curve_number": 0, "point_index": 24},
            {"curve_number": 0, "point_index": 23},
            {"curve_number": 0, "point_index": "3"},
            {"curve_number": 0, "point_index": True},
            {"curve_number": 0},
        ]
        assert ph.cells_from_selection({"points": points}, 24) == (23,)

    def test_empty_and_absent_selections_yield_nothing(self) -> None:
        """No selection, an empty points list, or a mapping without points."""
        assert ph.cells_from_selection(None, 24) == ()
        assert ph.cells_from_selection({}, 24) == ()
        assert ph.cells_from_selection({"points": []}, 24) == ()
        assert ph.cells_from_selection({"box": [{"x": [0, 1], "y": [0, 1]}]}, 24) == ()


class TestTools:
    """The "Tool" radio's reading of a completed drag (DECISIONS #188).

    A plotly chart inside Streamlit reports a finished drag, never mouse
    motion, so the Draw tool's brush stroke is the lasso PATH rasterised
    over the cells it crossed; the Rectangle and Lasso tools take the
    enclosed points. All pure, all pinned here.
    """

    def test_dragmode_for_each_tool(self) -> None:
        """Draw and Lasso are freehand drags; Rectangle is a box; Draw is the default."""
        assert ph.TOOL_OPTIONS[0] == ph.TOOL_DRAW
        assert ph.dragmode_for_tool(ph.TOOL_DRAW) == "lasso"
        assert ph.dragmode_for_tool(ph.TOOL_LASSO) == "lasso"
        assert ph.dragmode_for_tool(ph.TOOL_RECTANGLE) == "select"
        with pytest.raises(ValueError, match="Unknown painter tool"):
            ph.dragmode_for_tool("Pan")

    def test_a_horizontal_stroke_paints_every_cell_it_crosses(self) -> None:
        """Row 1 from x = 0.1 to x = 4.9 on a 3 × 6 grid crosses columns 0 to 5."""
        assert ph.cells_along_path([0.1, 4.9], [1.0, 1.0], 3, 6) == (6, 7, 8, 9, 10, 11)

    def test_a_diagonal_stroke_hits_exactly_the_diagonal(self) -> None:
        """(0, 0) to (3, 3) on 4 × 4: the four diagonal cells, nothing else."""
        assert ph.cells_along_path([0, 3], [0, 3], 4, 4) == (0, 5, 10, 15)

    def test_a_fast_stroke_with_far_apart_vertices_leaves_no_gaps(self) -> None:
        """Two vertices six rows apart: the sampling fills every row between."""
        assert ph.cells_along_path([0, 0], [0, 5], 6, 1) == (0, 1, 2, 3, 4, 5)

    def test_a_dab_paints_one_cell(self) -> None:
        """A press with a tiny nudge inside cell (1, 2) paints that cell only."""
        assert ph.cells_along_path([2.1, 2.2], [1.05, 1.1], 4, 6) == (8,)

    def test_the_closing_segment_is_not_walked(self) -> None:
        """An L-shaped stroke is a stroke, not the triangle it would enclose."""
        cells = ph.cells_along_path([0, 0, 3], [0, 3, 3], 4, 4)
        assert set(cells) == {0, 4, 8, 12, 13, 14, 15}  # down column 0, then along row 3
        assert 5 not in cells and 10 not in cells  # the diagonal stays unpainted

    def test_samples_outside_the_grid_are_dropped(self) -> None:
        """Off-grid samples never map to a cell; an empty path paints nothing."""
        assert ph.cells_along_path([-3.0, -1.0], [0.0, 0.0], 2, 2) == ()
        assert ph.cells_along_path([-1.0, 1.0], [0.0, 0.0], 2, 2) == (0, 1)
        assert ph.cells_along_path([], [], 2, 2) == ()
        with pytest.raises(ValueError, match="as many x as y"):
            ph.cells_along_path([0], [], 2, 2)

    def test_lasso_paths_reads_the_selection_schema(self) -> None:
        """The `lasso` entries' x/y lists; malformed entries are skipped."""
        selection = {
            "points": [],
            "lasso": [
                {"xref": "x", "yref": "y", "x": [0, 1], "y": [0, 0]},
                {"x": [1], "y": []},
                "junk",
                {"x": ["a"], "y": [1]},
            ],
        }
        assert ph.lasso_paths(selection) == [([0.0, 1.0], [0.0, 0.0])]
        assert ph.lasso_paths(None) == []
        assert ph.lasso_paths({}) == []
        assert ph.lasso_paths({"lasso": []}) == []

    def test_cells_for_tool_reads_a_drag_per_tool(self) -> None:
        """Draw takes the path; Lasso and Rectangle take the enclosed points."""
        lasso_drag = {
            "points": [{"curve_number": 0, "point_index": 9}],
            "lasso": [{"x": [0, 3], "y": [0, 0]}],
        }
        assert ph.cells_for_tool(ph.TOOL_DRAW, lasso_drag, 3, 4) == (0, 1, 2, 3)
        assert ph.cells_for_tool(ph.TOOL_LASSO, lasso_drag, 3, 4) == (9,)
        box_drag = {
            "points": [{"curve_number": 0, "point_index": index} for index in (4, 5)],
            "box": [{"x": [0, 1], "y": [1, 1]}],
        }
        assert ph.cells_for_tool(ph.TOOL_RECTANGLE, box_drag, 3, 4) == (4, 5)
        assert ph.cells_for_tool(ph.TOOL_DRAW, box_drag, 3, 4) == (4, 5)  # no path: fall back
        assert ph.cells_for_tool(ph.TOOL_DRAW, None, 3, 4) == ()
        with pytest.raises(ValueError, match="Unknown painter tool"):
            ph.cells_for_tool("Pan", lasso_drag, 3, 4)


class TestStrokes:
    """The stroke as a pure transformation; apply / undo / fill / clear."""

    def test_stroke_is_pure(self) -> None:
        """The input cells are untouched; a new list comes back."""
        cells: list[str | None] = [None, AC, None]
        after = ph.stroke(cells, [0, 1], AD)
        assert after == [AD, AD, None]
        assert cells == [None, AC, None]

    def test_apply_brush_counts_only_real_changes(self) -> None:
        """Painting 3 empty cells changes 3; the same stroke again changes 0."""
        draft = ph.blank_draft(2, 3)
        assert ph.apply_brush(draft, [0, 1, 2], AD) == 3
        assert draft.dirty is True
        assert draft.undo_cells == [None] * 6
        assert ph.apply_brush(draft, [0, 1, 2], AD) == 0  # a no-op stroke
        assert draft.undo_cells == [None] * 6  # the undo level is not consumed
        assert ph.apply_brush(draft, [6, 7], AD) == 0  # out of range: ignored

    def test_occupied_cells_are_overwritten(self) -> None:
        """It is a painter: every selected cell takes the brush (#186 R9)."""
        draft = ph.blank_draft(1, 3)
        ph.apply_brush(draft, [0, 1, 2], AD)
        assert ph.apply_brush(draft, [1], TFT) == 1
        assert draft.cells == [AD, TFT, AD]

    def test_the_eraser_empties_cells(self) -> None:
        """Brush None paints empty."""
        draft = ph.blank_draft(1, 3)
        ph.apply_brush(draft, [0, 1, 2], AD)
        assert ph.apply_brush(draft, [0, 2], None) == 2
        assert draft.cells == [None, AD, None]
        assert _painted(draft) == 1

    def test_undo_restores_one_level_only(self) -> None:
        """Undo brings back the cells before the last stroke; a second undo does nothing."""
        draft = ph.blank_draft(1, 3)
        ph.apply_brush(draft, [0], AC)
        ph.apply_brush(draft, [1], AD)
        assert ph.undo_stroke(draft) is True
        assert draft.cells == [AC, None, None]
        assert draft.undo_cells is None
        assert ph.undo_stroke(draft) is False  # nothing left to undo
        assert draft.cells == [AC, None, None]

    def test_undo_with_nothing_to_undo_changes_nothing(self) -> None:
        """A fresh draft has no undo level."""
        draft = ph.blank_draft(1, 3)
        assert ph.undo_stroke(draft) is False
        assert draft.cells == [None] * 3
        assert draft.dirty is False

    def test_fill_and_clear_are_undoable_strokes(self) -> None:
        """Fill → every cell painted; clear → none; undo → the fill returns."""
        draft = ph.blank_draft(6, 8)
        assert ph.fill_all(draft, TFT) == 48
        assert _painted(draft) == 48
        assert ph.clear_all(draft) == 48
        assert _painted(draft) == 0
        assert ph.undo_stroke(draft) is True
        assert _painted(draft) == 48
        assert ph.fill_all(draft, None) == 48  # the eraser fills with empty

    def test_every_mutation_invalidates_the_figure_cache(self) -> None:
        """The rebuild cache (#187): reset by every change, kept by a no-op."""
        draft = ph.blank_draft(2, 2)
        draft.figure_cache = object()
        assert ph.apply_brush(draft, [], AC) == 0
        assert draft.figure_cache is not None  # a no-op stroke keeps the figure
        ph.apply_brush(draft, [0], AC)
        assert draft.figure_cache is None
        draft.figure_cache = object()
        ph.undo_stroke(draft)
        assert draft.figure_cache is None
        draft.figure_cache = object()
        ph.fill_all(draft, AD)
        assert draft.figure_cache is None
        draft.figure_cache = object()
        ph.clear_all(draft)
        assert draft.figure_cache is None


class TestDerivedCounts:
    """Counts through the layout-file dataclass; brush labels; the caption."""

    def test_draft_layout_file_reuses_the_layout_file_arithmetic(self) -> None:
        """occupied_count and strategy_counts come from LayoutFile, not a copy."""
        draft = ph.draft_from_layout(parse_layout_file(ISLAND_TEXT))
        layout = ph.draft_layout_file(draft)
        assert layout.kind == layouts.LAYOUT_FILE_KIND
        assert (layout.rows, layout.cols) == (4, 6)
        assert layout.occupied_count == 24
        assert layout.strategy_counts() == {AD: 18, TFT: 6}
        assert layout.positions == ()  # never parsed from text

    def test_counts_caption_uses_display_names_in_registry_order(self) -> None:
        """The island reads 'Always Defect 18, Tit for Tat 6'; a blank grid reads ''."""
        draft = ph.draft_from_layout(parse_layout_file(ISLAND_TEXT))
        assert ph.counts_caption(draft) == "Always Defect 18, Tit for Tat 6"
        assert ph.counts_caption(ph.blank_draft(2, 2)) == ""

    def test_brush_options_are_the_registry_plus_the_eraser(self) -> None:
        """Display names in registry order, then the eraser; labels map back."""
        options = ph.brush_options()
        assert options == [*(info.display_name for info in all_strategies()), ph.ERASER_LABEL]
        for info in all_strategies():
            assert ph.brush_from_label(info.display_name) == info.name
        assert ph.brush_from_label(ph.ERASER_LABEL) is None
        assert ph.brush_from_label(None) is None
        with pytest.raises(ValueError, match="Unknown brush"):
            ph.brush_from_label("Not a strategy")


class TestTemplateNames:
    """The `.txt` listing, the suffix rule, and the save-name rules (#186 R5)."""

    def test_normalise_appends_txt_only_without_a_suffix(self) -> None:
        """'my_painting' → 'my_painting.txt'; names with a suffix are unchanged."""
        assert ph.normalise_template_name("my_painting") == "my_painting.txt"
        assert ph.normalise_template_name("my_painting.txt") == "my_painting.txt"
        assert ph.normalise_template_name("notes.md") == "notes.md"

    def test_blank_and_path_like_names_are_refused(self) -> None:
        """A bare name is required — the #122 rule in reverse."""
        assert ph.template_name_problem("", exists=False, replace=False) is not None
        assert ph.template_name_problem("   ", exists=False, replace=False) is not None
        for bad in ("sub/dir.txt", "sub\\dir.txt", "C:\\abs\\file.txt", "/abs/file.txt", "..", "."):
            problem = ph.template_name_problem(bad, exists=False, replace=False)
            assert problem is not None, bad
            assert "bare file name" in problem

    @pytest.mark.parametrize("shipped", ph.SHIPPED_TEMPLATES)
    def test_each_protected_example_is_refused(self, shipped: str) -> None:
        """The shipped examples cannot be overwritten — whatever the letter case."""
        for variant in (shipped, shipped.removesuffix(".txt"), shipped.upper()):
            problem = ph.template_name_problem(variant, exists=True, replace=True)
            assert problem is not None, variant
            assert "shipped examples" in problem

    def test_an_existing_file_needs_the_replace_checkbox(self) -> None:
        """Exists without replace → refused naming the checkbox; with it → allowed."""
        problem = ph.template_name_problem("mine", exists=True, replace=False)
        assert problem is not None
        assert "Replace the existing file" in problem
        assert ph.template_name_problem("mine", exists=True, replace=True) is None
        assert ph.template_name_problem("mine", exists=False, replace=False) is None
        assert ph.template_name_problem("mine.txt", exists=False, replace=False) is None

    def test_template_names_lists_only_txt_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sorted .txt names of the templates folder, read at call time."""
        monkeypatch.setattr(layouts, "GRID_TEMPLATES_DIR", tmp_path / "missing")
        assert ph.template_names() == []
        folder = tmp_path / "templates"
        folder.mkdir()
        for name in ("b.txt", "a.txt", "README.md", "notes.TXT", "z.yaml"):
            (folder / name).write_text("x", encoding="utf-8")
        (folder / "sub.txt").mkdir()  # a folder, even with the suffix, is not a file
        monkeypatch.setattr(layouts, "GRID_TEMPLATES_DIR", folder)
        assert ph.template_names() == ["a.txt", "b.txt", "notes.TXT"]


class TestSaveAndHandoff:
    """`save_draft` writes exactly the formatter's text; the hand-off gate."""

    def test_save_writes_exactly_the_formatter_text_with_lf_endings(self, tmp_path: Path) -> None:
        """Byte for byte the formatter's output, LF only, comment line first."""
        draft = ph.draft_from_layout(parse_layout_file(ISLAND_TEXT))
        ph.apply_brush(draft, [0], None)  # dirty it first
        path = ph.save_draft(draft, tmp_path, "  my_island ")
        assert path == tmp_path / "my_island.txt"
        expected = format_layout_file(ph.draft_layout_file(draft), comment=True)
        raw = path.read_bytes()
        assert raw == expected.encode("utf-8")
        assert b"\r" not in raw
        assert raw.startswith(PAINTER_COMMENT_LINE.encode("utf-8") + b"\n")
        assert draft.saved_as == "my_island.txt"
        assert draft.dirty is False
        # And it reads back through the one parser as the same picture.
        reread = layouts.read_layout_file(path)
        assert reread.cells == tuple(draft.cells)

    def test_save_can_omit_the_comment_line(self, tmp_path: Path) -> None:
        """comment=False writes the bare header first."""
        draft = ph.blank_draft(1, 2)
        path = ph.save_draft(draft, tmp_path, "bare", comment=False)
        assert path.read_text(encoding="utf-8") == "kind: lattice_grid\nrows: 1\ncols: 2\n\n. .\n"

    def test_handoff_problem_covers_every_gate(self) -> None:
        """No draft; unsaved; changed since saving; fewer than two agents; then live."""
        assert ph.handoff_problem(None) is not None
        draft = ph.blank_draft(4, 6)
        problem = ph.handoff_problem(draft)
        assert problem is not None
        assert "Save the layout first" in problem
        draft.saved_as = "zero.txt"  # saved with zero agents: the count gate
        problem = ph.handoff_problem(draft)
        assert problem is not None
        assert "at least two agents" in problem
        ph.apply_brush(draft, [0], TFT)  # one agent, and now dirty
        problem = ph.handoff_problem(draft)
        assert problem is not None
        assert "changed since it was saved" in problem
        draft.dirty = False  # as a save would leave it
        problem = ph.handoff_problem(draft)
        assert problem is not None
        assert "at least two agents" in problem
        assert "places 1" in problem
        ph.apply_brush(draft, [1], AD)
        draft.dirty = False
        assert ph.handoff_problem(draft) is None


class TestShippedTemplatesProtection:
    """#186 amendment (b): the protected tuple matches the examples on disk."""

    def test_every_shipped_example_on_disk_is_protected_and_vice_versa(self) -> None:
        """No example_*.txt may exist unprotected; no protected name may be missing."""
        on_disk = {path.name for path in Path("grid_templates").glob("example_*.txt")}
        assert on_disk == set(ph.SHIPPED_TEMPLATES)
        for name in ph.SHIPPED_TEMPLATES:
            assert (Path("grid_templates") / name).is_file(), name
