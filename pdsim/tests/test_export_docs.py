"""Tests for the project-files export script (``pdsim/export_docs.py``, DECISIONS #193).

The pins #193 R6 names: the naming rule on its three cases, the duplicate
refusal, the ``docs/WIP.md`` exclusion, and a temp-tree run producing the
expected set and the three lists across two runs. Every test builds its own
miniature repository under ``tmp_path`` — the real repository is never read
or written here.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from pdsim import export_docs
from pdsim.export_docs import (
    EXPORT_SUBDIR,
    MANIFEST_NAME,
    DuplicateExportNameError,
    compare_manifests,
    export_name,
    export_names,
    format_report,
    run_export,
    upload_set,
)

TREE: dict[str, str] = {
    "CLAUDE.md": "# conventions\n",
    "README.md": "# root readme\n",
    "docs/DESIGN.md": "# design\n",
    "docs/DECISIONS.md": "# decisions\n",
    "docs/specs/M09a-selection-accounting-bench.md": "# a spec\n",
    "docs/explainers/calibration-guide.md": "# a guide\n",
    "docs/WIP.md": "# the session baton — never uploaded\n",
    "grid_templates/README.md": "# templates readme\n",
    # Present in a real checkout but NOT in the upload set:
    "docs/notes.txt": "not markdown\n",
    "examples/README.md": "# an examples readme\n",
    "grid_templates/example_island.txt": "..X..\n",
    "pdsim/README.md": "# a package readme\n",
}
"""A miniature repository: the upload set plus the files that must be left out."""

EXPECTED_NAMES: list[str] = [
    "calibration-guide.md",
    "CLAUDE.md",
    "DECISIONS.md",
    "DESIGN.md",
    "grid_templates-README.md",
    "M09a-selection-accounting-bench.md",
    "README.md",
]
"""What the miniature repository exports, in the report's case-insensitive order."""


def _make_tree(root: Path, files: dict[str, str] | None = None) -> None:
    """Write a miniature repository under ``root``.

    Args:
        root: The folder to populate (``tmp_path`` in practice).
        files: ``{relative posix path: contents}``; defaults to :data:`TREE`.
    """
    for relative, text in (TREE if files is None else files).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def _exported(root: Path) -> list[str]:
    """List the export folder's visible files (the manifest dotfile excluded).

    Args:
        root: The miniature repository's root.

    Returns:
        Filenames sorted case-insensitively, as the report lists them.
    """
    folder = root / EXPORT_SUBDIR
    return sorted((p.name for p in folder.iterdir() if p.name != MANIFEST_NAME), key=str.lower)


def _snapshot(root: Path) -> dict[str, bytes]:
    """Capture every file outside ``exports/`` with its contents.

    Args:
        root: The miniature repository's root.

    Returns:
        ``{relative posix path: bytes}`` for everything the export must not touch.
    """
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and p.relative_to(root).parts[0] != "exports"
    }


class TestExportName:
    """R3: the pure naming rule, on its three cases."""

    ROOT = Path("C:/repo") if Path("C:/").anchor else Path("/repo")

    def test_root_file_keeps_its_name(self) -> None:
        """A repository-root file exports under its own name."""
        assert export_name(Path("README.md"), self.ROOT) == "README.md"
        assert export_name(Path("CLAUDE.md"), self.ROOT) == "CLAUDE.md"

    def test_docs_file_keeps_its_bare_filename(self) -> None:
        """Anything under docs/, however deep, drops its folders."""
        assert export_name(Path("docs/DESIGN.md"), self.ROOT) == "DESIGN.md"
        assert (
            export_name(Path("docs/specs/M09a-selection-accounting-bench.md"), self.ROOT)
            == "M09a-selection-accounting-bench.md"
        )
        assert export_name(Path("docs/a/b/c/deep.md"), self.ROOT) == "deep.md"

    def test_other_file_is_prefixed_with_its_parent_folder(self) -> None:
        """grid_templates/README.md → grid_templates-README.md (the name already in use)."""
        templates_readme = Path("grid_templates/README.md")
        assert export_name(templates_readme, self.ROOT) == "grid_templates-README.md"
        # The rule generalises: the IMMEDIATE parent folder, whatever the depth.
        assert export_name(Path("a/b/notes.md"), self.ROOT) == "b-notes.md"

    def test_absolute_and_relative_paths_agree(self) -> None:
        """The name depends only on the path's position under the root."""
        for relative in ("README.md", "docs/specs/x.md", "grid_templates/README.md"):
            assert export_name(self.ROOT / relative, self.ROOT) == export_name(
                Path(relative), self.ROOT
            )

    def test_pure_no_filesystem_needed(self) -> None:
        """Nonexistent paths are named just the same — the rule reads no file."""
        assert export_name(Path("docs/never-written.md"), self.ROOT) == "never-written.md"
        assert export_name(Path("never/written.md"), self.ROOT) == "never-written.md"

    def test_root_itself_is_refused(self) -> None:
        """The repository root is not a file and gets no name."""
        with pytest.raises(ValueError, match="repository root"):
            export_name(self.ROOT, self.ROOT)


class TestUploadSet:
    """R2: the set is CLAUDE.md, README.md, docs/**/*.md minus WIP.md, grid_templates/README.md."""

    def test_exactly_the_ruled_set(self, tmp_path: Path) -> None:
        """Every member is present; nothing outside the rule sneaks in."""
        _make_tree(tmp_path)
        relative = [p.relative_to(tmp_path).as_posix() for p in upload_set(tmp_path)]
        assert relative == [
            "CLAUDE.md",
            "docs/DECISIONS.md",
            "docs/DESIGN.md",
            "docs/explainers/calibration-guide.md",
            "docs/specs/M09a-selection-accounting-bench.md",
            "grid_templates/README.md",
            "README.md",
        ]

    def test_wip_is_excluded(self, tmp_path: Path) -> None:
        """docs/WIP.md — the session baton — is never in the set."""
        _make_tree(tmp_path)
        assert (tmp_path / "docs" / "WIP.md").is_file()
        assert all(p.name != "WIP.md" for p in upload_set(tmp_path))

    def test_non_markdown_and_outside_files_are_excluded(self, tmp_path: Path) -> None:
        """docs/notes.txt, examples/README.md, pdsim/README.md, the .txt layouts stay home."""
        _make_tree(tmp_path)
        relative = {p.relative_to(tmp_path).as_posix() for p in upload_set(tmp_path)}
        assert "docs/notes.txt" not in relative
        assert "examples/README.md" not in relative
        assert "pdsim/README.md" not in relative
        assert "grid_templates/example_island.txt" not in relative

    def test_missing_fixed_member_is_an_error(self, tmp_path: Path) -> None:
        """A checkout without grid_templates/README.md is reported, not exported around."""
        files = {k: v for k, v in TREE.items() if k != "grid_templates/README.md"}
        _make_tree(tmp_path, files)
        with pytest.raises(FileNotFoundError, match=re.escape("grid_templates/README.md")):
            upload_set(tmp_path)


class TestDuplicateRefusal:
    """R3: two docs/ files sharing a bare filename stop the script before it writes."""

    def test_export_names_refuses(self, tmp_path: Path) -> None:
        """The mapping names both offenders and the shared export name."""
        _make_tree(tmp_path)
        _make_tree(tmp_path, {"docs/specs/X.md": "one\n", "docs/explainers/X.md": "two\n"})
        with pytest.raises(DuplicateExportNameError, match=re.escape("'X.md'")):
            export_names(upload_set(tmp_path), tmp_path)

    def test_run_export_leaves_the_previous_export_untouched(self, tmp_path: Path) -> None:
        """A refusal fires before clearing: the last good export survives intact."""
        _make_tree(tmp_path)
        first = run_export(tmp_path)
        before = {p.name: p.read_bytes() for p in first.destination.iterdir()}
        _make_tree(tmp_path, {"docs/specs/X.md": "one\n", "docs/explainers/X.md": "two\n"})
        with pytest.raises(DuplicateExportNameError):
            run_export(tmp_path)
        after = {p.name: p.read_bytes() for p in first.destination.iterdir()}
        assert after == before


class TestRunExport:
    """R4/R6: the temp-tree run — the expected set and the three lists across runs."""

    def test_first_run_exports_the_set_as_all_new(self, tmp_path: Path) -> None:
        """Every ruled file lands under its export name; all New, nothing else."""
        _make_tree(tmp_path)
        report = run_export(tmp_path)
        assert report.destination == (tmp_path / EXPORT_SUBDIR).resolve()
        assert _exported(tmp_path) == EXPECTED_NAMES
        assert report.names == EXPECTED_NAMES
        assert report.new == EXPECTED_NAMES
        assert report.changed == []
        assert report.removed == []

    def test_copies_are_byte_for_byte_and_hashed(self, tmp_path: Path) -> None:
        """Each copy equals its source; the manifest holds each copy's SHA-256."""
        _make_tree(tmp_path)
        run_export(tmp_path)
        folder = tmp_path / EXPORT_SUBDIR
        manifest = json.loads((folder / MANIFEST_NAME).read_text(encoding="utf-8"))
        assert sorted(manifest, key=str.lower) == EXPECTED_NAMES
        sources = {
            "grid_templates-README.md": "grid_templates/README.md",
            "M09a-selection-accounting-bench.md": "docs/specs/M09a-selection-accounting-bench.md",
            "README.md": "README.md",
        }
        for name, source in sources.items():
            data = (tmp_path / source).read_bytes()
            assert (folder / name).read_bytes() == data
            assert manifest[name] == hashlib.sha256(data).hexdigest()

    def test_wip_never_lands_in_the_folder(self, tmp_path: Path) -> None:
        """The baton is excluded at the source; no WIP.md in the export."""
        _make_tree(tmp_path)
        run_export(tmp_path)
        assert not (tmp_path / EXPORT_SUBDIR / "WIP.md").exists()

    def test_second_run_without_edits_reports_nothing(self, tmp_path: Path) -> None:
        """Identical content → all three lists empty; the set is unchanged."""
        _make_tree(tmp_path)
        run_export(tmp_path)
        report = run_export(tmp_path)
        assert (report.changed, report.new, report.removed) == ([], [], [])
        assert _exported(tmp_path) == EXPECTED_NAMES

    def test_edit_add_and_remove_land_in_their_lists(self, tmp_path: Path) -> None:
        """One edited, one new, one deleted source → one name in each list."""
        _make_tree(tmp_path)
        run_export(tmp_path)
        (tmp_path / "docs" / "DECISIONS.md").write_text("# decisions, amended\n", encoding="utf-8")
        (tmp_path / "docs" / "specs" / "M11c-grid-component-spec.md").write_text(
            "# a new spec\n", encoding="utf-8"
        )
        (tmp_path / "docs" / "explainers" / "calibration-guide.md").unlink()
        report = run_export(tmp_path)
        assert report.changed == ["DECISIONS.md"]
        assert report.new == ["M11c-grid-component-spec.md"]
        assert report.removed == ["calibration-guide.md"]
        # The folder is cleared and rewritten: the removed file's copy is gone.
        assert "calibration-guide.md" not in _exported(tmp_path)
        assert "M11c-grid-component-spec.md" in _exported(tmp_path)

    def test_stale_files_in_the_folder_are_cleared(self, tmp_path: Path) -> None:
        """Anything left in exports/project-files/ by hand disappears on the next run."""
        _make_tree(tmp_path)
        run_export(tmp_path)
        stray = tmp_path / EXPORT_SUBDIR / "stray-note.md"
        stray.write_text("left behind\n", encoding="utf-8")
        run_export(tmp_path)
        assert not stray.exists()
        assert _exported(tmp_path) == EXPECTED_NAMES

    def test_nothing_outside_exports_is_written(self, tmp_path: Path) -> None:
        """The repository tree is read only: every other file is byte-identical after a run."""
        _make_tree(tmp_path)
        before = _snapshot(tmp_path)
        run_export(tmp_path)
        run_export(tmp_path)
        assert _snapshot(tmp_path) == before


class TestCompareManifests:
    """The three-way split is exact and case-insensitively sorted."""

    def test_split(self) -> None:
        """Changed = same name, different hash; New = only now; Removed = only before."""
        previous = {"a.md": "1", "b.md": "2", "gone.md": "3"}
        current = {"a.md": "1", "b.md": "changed", "Added.md": "4"}
        assert compare_manifests(previous, current) == (["b.md"], ["Added.md"], ["gone.md"])

    def test_first_run_is_all_new(self) -> None:
        """An empty previous manifest puts every name under New."""
        assert compare_manifests({}, {"x.md": "1", "y.md": "2"}) == ([], ["x.md", "y.md"], [])


class TestCommand:
    """``python -m pdsim.export_docs``: the printout and the exit codes."""

    def test_main_prints_the_lists_then_the_folder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """First run: every name under New, "(none)" elsewhere, the path on the last line."""
        _make_tree(tmp_path)
        monkeypatch.setattr(export_docs, "REPO_ROOT", tmp_path)
        assert export_docs.main() == 0
        out = capsys.readouterr().out
        assert "Changed (re-upload): 0\n  (none)" in out
        assert "New (upload): 7" in out
        assert "Removed (delete from project knowledge): 0\n  (none)" in out
        for name in EXPECTED_NAMES:
            assert f"  {name}\n" in out
        assert out.rstrip("\n").splitlines()[-1] == str((tmp_path / EXPORT_SUBDIR).resolve())

    def test_main_refuses_with_exit_code_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A duplicate bare filename under docs/ → message on stderr, exit 1, nothing written."""
        _make_tree(tmp_path)
        _make_tree(tmp_path, {"docs/specs/X.md": "one\n", "docs/explainers/X.md": "two\n"})
        monkeypatch.setattr(export_docs, "REPO_ROOT", tmp_path)
        assert export_docs.main() == 1
        assert "refused to run" in capsys.readouterr().err
        assert not (tmp_path / "exports").exists()

    def test_format_report_names_every_list(self) -> None:
        """The pure renderer: titles, counts, names, and the path last."""
        report = export_docs.ExportReport(
            destination=Path("somewhere"),
            names=["a.md", "b.md"],
            changed=["a.md"],
            new=["b.md"],
            removed=["c.md"],
        )
        text = format_report(report)
        assert "Changed (re-upload): 1\n  a.md" in text
        assert "New (upload): 1\n  b.md" in text
        assert "Removed (delete from project knowledge): 1\n  c.md" in text
        assert text.splitlines()[-1] == "somewhere"
