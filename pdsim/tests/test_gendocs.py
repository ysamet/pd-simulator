"""Tests for the parameter-doc generator (``pdsim/gendocs.py``, DECISIONS #56).

The centerpiece is the **drift test**: ``docs/PARAMETERS.md`` is a committed
file, and this suite regenerates it in memory and compares — so a stale
committed copy is a failing test, exactly like a missing registry entry.
"""

from __future__ import annotations

from pathlib import Path

from pdsim.config.registry import all_specs
from pdsim.config.scenarios import all_scenarios
from pdsim.core.strategies import all_strategies
from pdsim.gendocs import (
    DEFAULT_OUTPUT,
    generate_parameters_markdown,
    write_parameters_doc,
)


class TestDrift:
    """The committed document must match a fresh regeneration exactly."""

    def test_committed_parameters_doc_is_current(self) -> None:
        """docs/PARAMETERS.md equals the in-memory regeneration, byte for byte.

        (Line endings are normalized by the text read, so the comparison is
        insensitive to git's platform checkout behavior — everything else
        must match exactly.)
        """
        committed = DEFAULT_OUTPUT.read_text(encoding="utf-8")
        assert committed == generate_parameters_markdown(), (
            "docs/PARAMETERS.md is stale (the registries changed since it was "
            "generated). Regenerate it with `python -m pdsim.gendocs` and stage "
            "the result."
        )

    def test_generation_is_deterministic(self) -> None:
        """Two regenerations in one process are identical (no timestamps etc.)."""
        assert generate_parameters_markdown() == generate_parameters_markdown()


class TestContent:
    """The document must actually cover the registries it claims to."""

    def test_header_declares_the_file_generated(self) -> None:
        """The do-not-hand-edit warning and the regeneration command lead."""
        document = generate_parameters_markdown()
        assert "GENERATED FILE" in document
        assert "python -m pdsim.gendocs" in document

    def test_every_registered_parameter_appears(self) -> None:
        """Each Parameter Registry key shows up (strategy keys included)."""
        document = generate_parameters_markdown()
        for spec in all_specs():
            assert f"`{spec.key}`" in document, f"{spec.key} missing from PARAMETERS.md"

    def test_every_strategy_and_scenario_appears(self) -> None:
        """Roster and scenario entries are all present, by both names."""
        document = generate_parameters_markdown()
        for info in all_strategies():
            assert f"{info.display_name} (`{info.name}`)" in document
        for scenario in all_scenarios():
            assert f"{scenario.display_name} (`{scenario.name}`)" in document

    def test_descriptions_come_from_the_registries(self) -> None:
        """Spot-check: registry description text lands in the document verbatim."""
        document = generate_parameters_markdown()
        assert all_specs()[0].description in document
        assert all_strategies()[0].description in document
        assert all_scenarios()[0].things_to_try in document


class TestWriter:
    """The file-writing entry point behind ``python -m pdsim.gendocs``."""

    def test_write_round_trips_through_disk(self, tmp_path: Path) -> None:
        """What is written (LF-normalized) is exactly what was generated."""
        target = write_parameters_doc(tmp_path / "PARAMETERS.md")
        assert target.read_text(encoding="utf-8") == generate_parameters_markdown()


DISCLOSURE_BULLET = (
    "- **Disclosure:** advanced setting — the app folds it under "
    '"Advanced settings" in its section; its default is the canonical choice'
)
"""The verbatim mark a flagged entry carries (M11b Phase E2, DECISIONS #181 R6)."""


def _entry_block(document: str, key: str) -> str:
    """Cut one parameter's block out of the generated document.

    Args:
        document: The generated markdown.
        key: The registry key whose ``####`` block to return.

    Returns:
        The text from that entry's heading up to the next ``####`` heading.
    """
    _, after = document.split(f"#### `{key}`", maxsplit=1)
    return after.split("####", maxsplit=1)[0]


class TestDisclosureMark:
    """Flagged entries carry the Disclosure bullet; unflagged ones do not."""

    def test_flagged_entry_carries_the_bullet(self) -> None:
        """An advanced key's block holds the verbatim bullet in its metadata list."""
        document = generate_parameters_markdown()
        block = _entry_block(document, "dynamics.boundary_order")
        assert DISCLOSURE_BULLET in block
        # In the metadata list — after the Default line, before the prose.
        assert block.index("- **Default:**") < block.index(DISCLOSURE_BULLET)

    def test_unflagged_entry_carries_no_bullet(self) -> None:
        """An everyday key (the default rule's own dial) is unmarked."""
        document = generate_parameters_markdown()
        assert DISCLOSURE_BULLET not in _entry_block(document, "dynamics.selection_beta")
        assert DISCLOSURE_BULLET not in _entry_block(document, "match.continuation_probability")

    def test_bullet_count_equals_the_flagged_count(self) -> None:
        """Exactly one bullet per flagged registry entry, no more."""
        document = generate_parameters_markdown()
        flagged = sum(1 for spec in all_specs() if spec.advanced)
        assert document.count(DISCLOSURE_BULLET) == flagged == 16
