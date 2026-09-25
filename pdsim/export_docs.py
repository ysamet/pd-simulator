"""Assemble the Claude.ai project-knowledge upload set (DECISIONS #193).

Usage (with the project venv active)::

    python -m pdsim.export_docs

Project knowledge on the Claude.ai side is a FLAT list of files; the
repository is not. ``grid_templates/README.md`` collides with the root
``README.md``, so before this command existed the owner renamed the copy by
hand at every upload — and the refresh after each build was a manual walk
over the handback's DOCS CHANGED list. This command does both jobs:

1. It copies the upload set — defined in :func:`upload_set` and nowhere
   else — into ``exports/project-files/`` under fixed, collision-free
   names (:func:`export_name`), clearing the folder first so it always
   holds exactly the current set.
2. It compares the copies' content hashes against the previous export's
   ``.manifest.json`` and prints three lists — Changed (re-upload), New
   (upload), Removed (delete from project knowledge) — then the folder's
   absolute path.

The folder is git-ignored (``exports/`` in ``.gitignore``); the manifest is
a dotfile the owner does not upload. Nothing outside ``exports/`` is ever
written. Like ``gendocs.py`` this module lives at the package top level: it
is a repository tool, not part of the engine, and per hard rule 4 it imports
no UI or plotting code.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
"""The repository root — the folder holding ``CLAUDE.md`` and ``pdsim/``."""

EXPORT_SUBDIR = Path("exports") / "project-files"
"""Where the upload set lands, relative to the repository root (#193 R4)."""

MANIFEST_NAME = ".manifest.json"
"""The dotfile recording each exported name's content hash (#193 R4)."""

DOCS_DIR = "docs"
"""The folder whose ``*.md`` files are exported recursively under bare names."""

ROOT_FILES: tuple[str, ...] = ("CLAUDE.md", "README.md")
"""Repository-root files in the upload set (#193 R2)."""

EXTRA_FILES: tuple[str, ...] = ("grid_templates/README.md",)
"""Files outside ``docs/`` and the root that are in the upload set (#193 R2)."""

EXCLUDED_FILES: frozenset[str] = frozenset({"docs/WIP.md"})
"""Files under ``docs/`` that are NEVER uploaded: the session baton (#193 R2)."""


class DuplicateExportNameError(ValueError):
    """Two files in the upload set would export under the same name.

    Raised before anything is written, so a refusal leaves the previous
    export untouched (#193 R3: a name must never change between exports, so
    a collision is fixed in the repository, never papered over here).
    """


def export_name(path: Path | str, repo_root: Path | str) -> str:
    """Name a repository file for the flat project-knowledge list (#193 R3).

    A pure function of the path alone — it never touches the filesystem, so
    the same path always yields the same name. The three cases:

    * a file at the repository root keeps its name (``README.md``);
    * a file anywhere under ``docs/`` keeps its bare filename
      (``docs/specs/M09a-….md`` → ``M09a-….md``) — :func:`export_names`
      refuses to run if two such files share a name;
    * any other file is named ``<parent folder>-<filename>``
      (``grid_templates/README.md`` → ``grid_templates-README.md``).

    Args:
        path: The file to name — either relative to ``repo_root`` or an
            absolute path underneath it.
        repo_root: The repository root the path is taken relative to.

    Returns:
        The filename the copy gets in ``exports/project-files/``.

    Raises:
        ValueError: If ``path`` is the root itself or lies outside it.
    """
    relative = Path(path)
    if relative.is_absolute():
        relative = relative.relative_to(Path(repo_root))
    parts = relative.parts
    if not parts:
        raise ValueError("export_name needs a file path, not the repository root")
    if len(parts) == 1:
        return relative.name
    if parts[0] == DOCS_DIR:
        return relative.name
    return f"{relative.parent.name}-{relative.name}"


def upload_set(repo_root: Path | str) -> list[Path]:
    """List the files that make up the project-knowledge upload set (#193 R2).

    This function is the ONE definition of the set: ``CLAUDE.md``, the root
    ``README.md``, every ``*.md`` under ``docs/`` recursively except
    ``docs/WIP.md``, and ``grid_templates/README.md``.

    Args:
        repo_root: The repository root to read from.

    Returns:
        Absolute paths, sorted by their repository-relative path so the
        order is the same on every platform.

    Raises:
        FileNotFoundError: If one of the fixed files is missing — a broken
            checkout, reported rather than silently exported without it.
    """
    root = Path(repo_root)
    files: list[Path] = [root / name for name in ROOT_FILES]
    # Path.rglob is the RECURSIVE glob: "*.md" alone would list only the
    # folder's own files, rglob walks every subfolder too (specs/, explainers/,
    # design-notes/, and any folder added later).
    files.extend(path for path in (root / DOCS_DIR).rglob("*.md") if path.is_file())
    files.extend(root / name for name in EXTRA_FILES)
    excluded = {root / name for name in EXCLUDED_FILES}
    files = [path for path in files if path not in excluded]
    missing = [path for path in files if not path.is_file()]
    if missing:
        names = ", ".join(path.relative_to(root).as_posix() for path in missing)
        raise FileNotFoundError(f"upload set incomplete — missing: {names}")
    return sorted(files, key=lambda path: path.relative_to(root).as_posix().lower())


def export_names(files: Iterable[Path], repo_root: Path | str) -> dict[str, Path]:
    """Map every file to its export name, refusing on any collision (#193 R3).

    Args:
        files: The upload set (see :func:`upload_set`).
        repo_root: The repository root the paths are taken relative to.

    Returns:
        ``{export name: source path}`` in the order the files were given.

    Raises:
        DuplicateExportNameError: If two files would share a name. The
            ruling names the ``docs/`` case (two files with one bare
            filename); the check covers the whole set, which includes it.
    """
    mapping: dict[str, Path] = {}
    for path in files:
        name = export_name(path, repo_root)
        if name in mapping:
            raise DuplicateExportNameError(
                f"{path} and {mapping[name]} would both export as {name!r}; "
                "rename one in the repository (#193 R3 keeps export names fixed)"
            )
        mapping[name] = path
    return mapping


def content_hash(data: bytes) -> str:
    """Fingerprint a file's bytes so a later run can tell whether it changed.

    Args:
        data: The file's complete contents.

    Returns:
        The SHA-256 digest as 64 hexadecimal characters.
    """
    # hashlib.sha256 turns any bytes into a fixed-length "digest": the same
    # bytes always give the same digest, and a one-character edit gives a
    # completely different one. Comparing digests is therefore a cheap,
    # exact way to ask "is this file byte-for-byte what it was last time?"
    # without keeping the old copy around.
    return hashlib.sha256(data).hexdigest()


def read_manifest(path: Path) -> dict[str, str]:
    """Load the previous export's ``{export name: hash}`` record, if any.

    Args:
        path: The manifest file (``exports/project-files/.manifest.json``).

    Returns:
        The recorded hashes, or an empty mapping on the first run.
    """
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(name): str(digest) for name, digest in data.items()}


def compare_manifests(
    previous: Mapping[str, str], current: Mapping[str, str]
) -> tuple[list[str], list[str], list[str]]:
    """Split the export names into the three lists the owner acts on (#193 R4).

    Args:
        previous: The last export's ``{name: hash}`` (empty on the first run).
        current: This export's ``{name: hash}``.

    Returns:
        ``(changed, new, removed)`` — names present in both with a different
        hash (re-upload), names only in ``current`` (upload), and names only
        in ``previous`` (delete from project knowledge) — each sorted
        case-insensitively.
    """
    changed = [name for name in current if name in previous and previous[name] != current[name]]
    new = [name for name in current if name not in previous]
    removed = [name for name in previous if name not in current]
    return (
        sorted(changed, key=str.lower),
        sorted(new, key=str.lower),
        sorted(removed, key=str.lower),
    )


@dataclass(frozen=True)
class ExportReport:
    """What one run of the export produced — the data behind the printout.

    Attributes:
        destination: The absolute path of ``exports/project-files/``.
        names: Every export name written this run, sorted case-insensitively.
        changed: Names whose contents differ from the previous export.
        new: Names the previous export did not have.
        removed: Names the previous export had that no longer exist.
    """

    destination: Path
    names: list[str]
    changed: list[str]
    new: list[str]
    removed: list[str]


def _clear_folder(folder: Path) -> None:
    """Empty a folder in place (files and subfolders), keeping the folder itself.

    Emptying rather than deleting-and-recreating keeps the folder's identity
    stable for anything watching it (a file explorer window, OneDrive).

    Args:
        folder: The folder to empty; created if it does not exist.
    """
    folder.mkdir(parents=True, exist_ok=True)
    for entry in folder.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def run_export(repo_root: Path | str) -> ExportReport:
    """Rewrite ``exports/project-files/`` and report what changed (#193 R4).

    The naming pass runs first, so a duplicate-name refusal leaves the
    previous export exactly as it was. The previous manifest is read before
    the folder is cleared (clearing deletes it), every source file is copied
    byte for byte under its export name, and the new manifest is written
    last.

    Args:
        repo_root: The repository root to export from; the destination is
            ``<repo_root>/exports/project-files/``.

    Returns:
        The :class:`ExportReport` for this run.

    Raises:
        DuplicateExportNameError: Two files would share an export name.
        FileNotFoundError: A fixed member of the upload set is missing.
    """
    root = Path(repo_root)
    mapping = export_names(upload_set(root), root)
    destination = root / EXPORT_SUBDIR
    manifest_path = destination / MANIFEST_NAME
    previous = read_manifest(manifest_path)
    _clear_folder(destination)
    current: dict[str, str] = {}
    for name, source in mapping.items():
        data = source.read_bytes()
        (destination / name).write_bytes(data)
        current[name] = content_hash(data)
    # Sorted keys and LF line endings keep the manifest byte-stable between
    # runs that export identical content.
    manifest_path.write_text(
        json.dumps(dict(sorted(current.items())), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    changed, new, removed = compare_manifests(previous, current)
    return ExportReport(
        destination=destination.resolve(),
        names=sorted(current, key=str.lower),
        changed=changed,
        new=new,
        removed=removed,
    )


def format_report(report: ExportReport) -> str:
    """Render a report as the text ``python -m pdsim.export_docs`` prints.

    Args:
        report: The result of :func:`run_export`.

    Returns:
        The three named lists (each showing ``(none)`` when empty), then the
        export folder's absolute path on the last line.
    """
    lines = [f"Project-knowledge upload set: {len(report.names)} files exported."]
    sections = (
        ("Changed (re-upload)", report.changed),
        ("New (upload)", report.new),
        ("Removed (delete from project knowledge)", report.removed),
    )
    for title, names in sections:
        lines += ["", f"{title}: {len(names)}"]
        lines += [f"  {name}" for name in names] or ["  (none)"]
    lines += ["", "Export folder (upload from here):", str(report.destination)]
    return "\n".join(lines)


def main() -> int:
    """Run the export as a command.

    Returns:
        Process exit code: 0 after a successful export, 1 when the script
        refused to run (duplicate export name or a missing fixed file) — in
        which case the previous export is left untouched.
    """
    try:
        report = run_export(REPO_ROOT)
    except (DuplicateExportNameError, FileNotFoundError) as error:
        print(f"export_docs refused to run: {error}", file=sys.stderr)
        return 1
    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
