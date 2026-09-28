"""The grid component's Python side (M11c sub-prompt 1.1; spec §1, §2, §6; DECISIONS #194–#196).

Two groups. The pure helpers of :mod:`pdsim.ui.grid_canvas_helpers` — the
byte encoder, palette, names, the live colour-key rule, the frame version
and the view-mode argument dict — pinned as plain functions (#190 R6, #194
R13). Then the tripwires (#194 R14, R16): the page's folder ships inside the
package with both files, the page speaks the four protocol messages, the
helpers stay Streamlit-free, and only ``ui/grid_canvas.py`` declares the
component. The drawing itself, the gestures and the theme are the spec's
Validation checklist's — pytest cannot see inside the iframe.
"""

from __future__ import annotations

import ast
import importlib.resources
from pathlib import Path

import pytest

from pdsim.config.experiment import ExperimentConfig
from pdsim.config.scenarios import get_scenario_info
from pdsim.core.events import AgentSnapshot
from pdsim.core.strategies import all_strategies
from pdsim.ui import grid_canvas_helpers as gch
from pdsim.viz import charts

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
"""The ``pdsim`` package folder."""


def _code(name: str) -> int:
    """A strategy's cell byte, derived independently: registry position + 1.

    Args:
        name: Strategy machine name.

    Returns:
        Its position in the registry, plus one.
    """
    return [info.name for info in all_strategies()].index(name) + 1


def _config(composition: dict[str, int], mutation_rate: float) -> ExperimentConfig:
    """A small evolution config with the given founders and mutation rate.

    Args:
        composition: Strategy machine name → founding count (sums to 10).
        mutation_rate: ``dynamics.mutation_rate``.

    Returns:
        The validated config.
    """
    return ExperimentConfig.model_validate(
        {
            "population": {"size": 10, "composition": composition},
            "dynamics": {"mutation_rate": mutation_rate},
        }
    )


class TestEncoder:
    """``encode_cells``: one byte per site, row-major, 0 empty, position + 1 (#194 R1)."""

    def test_exact_bytes_on_a_hand_built_grid(self) -> None:
        """2 × 3: sites 0, 4 and 5 occupied; every other byte 0."""
        placements = {0: "always_defect", 4: "always_cooperate", 5: "tit_for_tat"}
        encoded = gch.encode_cells(2, 3, placements)
        assert isinstance(encoded, bytes)
        assert list(encoded) == [
            _code("always_defect"),
            0,
            0,
            0,
            _code("always_cooperate"),
            _code("tit_for_tat"),
        ]

    def test_row_major_site_order(self) -> None:
        """Site id = row × cols + col: the last cell of row 0 is byte cols − 1."""
        encoded = gch.encode_cells(3, 4, {3: "pavlov", 4: "random"})
        assert encoded[3] == _code("pavlov")  # row 0, col 3
        assert encoded[4] == _code("random")  # row 1, col 0
        assert len(encoded) == 12

    def test_empty_grid_is_all_zeros(self) -> None:
        """No placements: rows × cols zero bytes."""
        assert gch.encode_cells(5, 7, {}) == bytes(35)

    def test_codes_are_registry_positions_plus_one(self) -> None:
        """Every registered strategy encodes as its own position + 1."""
        names = [info.name for info in all_strategies()]
        placements = dict(enumerate(names))
        encoded = gch.encode_cells(1, len(names), placements)
        assert list(encoded) == list(range(1, len(names) + 1))
        assert gch.strategy_codes() == {name: i + 1 for i, name in enumerate(names)}

    def test_unknown_strategy_is_refused(self) -> None:
        """A name the registry does not know is a bug, not a colour."""
        with pytest.raises(ValueError, match="Unknown strategy 'no_such_strategy'"):
            gch.encode_cells(2, 2, {0: "no_such_strategy"})

    @pytest.mark.parametrize("site", [4, 99, -1])
    def test_site_outside_the_grid_is_refused(self, site: int) -> None:
        """The wrong-length refusal: a placement that cannot belong to a 2 × 2 grid."""
        with pytest.raises(ValueError, match="outside the 2 × 2 grid"):
            gch.encode_cells(2, 2, {site: "always_cooperate"})

    @pytest.mark.parametrize(("rows", "cols"), [(0, 3), (3, 0), (-1, 2)])
    def test_non_positive_dimensions_are_refused(self, rows: int, cols: int) -> None:
        """A grid needs at least one row and one column."""
        with pytest.raises(ValueError, match="at least one row and one column"):
            gch.encode_cells(rows, cols, {})

    def test_placements_from_snapshots_skip_siteless_agents(self) -> None:
        """The snapshot is the render state; an agent without a site is not drawn."""
        snapshots = (
            AgentSnapshot(
                agent_id=1, parent_id=None, age=0, energy=1.0, strategy="pavlov", site_id=7
            ),
            AgentSnapshot(
                agent_id=2, parent_id=None, age=0, energy=1.0, strategy="random", site_id=None
            ),
        )
        assert gch.placements_from_snapshots(snapshots) == {7: "pavlov"}


class TestPaletteAndNames:
    """``grid_palette`` / ``grid_names``: index 0 empty, then the registry, in order."""

    def test_palette(self) -> None:
        """[None] + the one stable per-strategy mapping, in registry order (#37)."""
        palette = gch.grid_palette()
        assert len(palette) == len(all_strategies()) + 1
        assert palette[0] is None
        assert palette[1:] == list(charts.strategy_colors().values())
        assert palette[1:] == [charts.strategy_colors()[info.name] for info in all_strategies()]

    def test_names(self) -> None:
        """The word Empty, then display names aligned with the palette."""
        names = gch.grid_names()
        assert len(names) == len(gch.grid_palette())
        assert names[0] == "Empty"
        assert names[1:] == [info.display_name for info in all_strategies()]


class TestLiveKeyEntries:
    """``live_key_entries``: what the run CAN contain, registry order, Empty last (#195 F4)."""

    def test_no_mutation_lists_the_founders_in_registry_order(self) -> None:
        """At μ = 0 only founders can ever appear, listed in registry order."""
        config = _config({"tit_for_tat": 4, "always_cooperate": 6}, 0.0)
        assert gch.live_key_entries(config) == [
            _code("always_cooperate"),
            _code("tit_for_tat"),
            0,
        ]

    def test_mutation_lists_every_registered_strategy(self) -> None:
        """Above μ = 0 a mutant can be any registered strategy."""
        config = _config({"tit_for_tat": 4, "always_cooperate": 6}, 0.01)
        assert gch.live_key_entries(config) == [*range(1, len(all_strategies()) + 1), 0]

    def test_the_flagship_key(self) -> None:
        """Cooperation Survives in Clusters: Always Cooperate, Always Defect, Empty."""
        config = get_scenario_info("spatial_reciprocity").config
        assert gch.live_key_entries(config) == [
            _code("always_cooperate"),
            _code("always_defect"),
            0,
        ]


class TestVersionAndArgs:
    """``frame_version`` (#195 F3) and the view-mode argument dict (spec §2)."""

    def test_frame_version(self) -> None:
        """The text run:period — the run number keeps runs' frames apart."""
        assert gch.frame_version(3, 17) == "3:17"
        assert gch.frame_version(1, 0) != gch.frame_version(2, 0)

    def test_live_grid_args(self) -> None:
        """Every key present with its value; one home for the border threshold."""
        placements = {0: "always_cooperate", 5: "always_defect"}
        args = gch.live_grid_args(
            2, 3, placements, key_entries=(1, 2, 0), version="4:9", debug=True
        )
        assert set(args) == {
            "cells",
            "rows",
            "cols",
            "palette",
            "names",
            "key_entries",
            "mode",
            "border_min_px",
            "version",
            "debug",
        }
        assert args["cells"] == gch.encode_cells(2, 3, placements)
        assert args["rows"] == 2
        assert args["cols"] == 3
        assert args["palette"] == gch.grid_palette()
        assert args["names"] == gch.grid_names()
        assert args["key_entries"] == [1, 2, 0]
        assert args["mode"] == "view"
        assert args["border_min_px"] == charts.BORDER_MIN_SIDE_PX
        assert args["version"] == "4:9"
        assert args["debug"] is True

    def test_debug_defaults_off(self) -> None:
        """No ``?grid_debug=1``: no frame-time line."""
        args = gch.live_grid_args(1, 1, {}, key_entries=(0,), version="1:0")
        assert args["debug"] is False

    def test_no_argument_collides_with_the_calls_own_parameters(self) -> None:
        """``default``, ``key``, ``on_change`` and ``tab_index`` belong to the call (Task 0 (a))."""
        args = gch.live_grid_args(1, 1, {}, key_entries=(0,), version="1:0")
        assert not set(args) & {"default", "key", "on_change", "tab_index", "height"}


class TestTripwires:
    """Packaging and protocol tripwires (#194 R14, R16)."""

    def _folder(self) -> Path:
        """The page's folder, found through the installed package.

        Returns:
            ``pdsim/ui/frontend/grid_canvas`` as a filesystem path.
        """
        folder = importlib.resources.files("pdsim.ui") / "frontend" / "grid_canvas"
        return Path(str(folder))

    def test_folder_ships_inside_the_package_with_both_files(self) -> None:
        """Both files, and no ``__init__.py`` — it is static content, not a module."""
        folder = self._folder()
        assert folder.is_dir()
        assert (folder / "index.html").is_file()
        assert (folder / "grid_canvas.js").is_file()
        assert not (folder / "__init__.py").exists()

    def test_page_speaks_the_protocol(self) -> None:
        """The four message types, API version 1, and the key the app requires."""
        script = (self._folder() / "grid_canvas.js").read_text(encoding="utf-8")
        for token in (
            "streamlit:componentReady",
            "apiVersion: 1",
            "streamlit:render",
            "streamlit:setComponentValue",
            "streamlit:setFrameHeight",
            # 1.58's frontend drops any message without this key (#196).
            "isStreamlitMessage",
        ):
            assert token in script, token

    def test_page_loads_its_script_and_nothing_external(self) -> None:
        """index.html loads grid_canvas.js; neither file reaches the network."""
        folder = self._folder()
        page = (folder / "index.html").read_text(encoding="utf-8")
        script = (folder / "grid_canvas.js").read_text(encoding="utf-8")
        assert '<script src="grid_canvas.js"></script>' in page
        for text in (page, script):
            assert "http://" not in text
            assert "https://" not in text

    def test_helpers_import_no_streamlit(self) -> None:
        """``grid_canvas_helpers`` is pure: no Streamlit import anywhere in it."""
        source = (PACKAGE_ROOT / "ui" / "grid_canvas_helpers.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                assert not any(alias.name.startswith("streamlit") for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("streamlit")

    def test_only_grid_canvas_declares_the_component(self) -> None:
        """Exactly one module calls ``declare_component``: ``ui/grid_canvas.py``."""
        declaring = []
        for path in sorted(PACKAGE_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                    if name == "declare_component":
                        declaring.append(path.relative_to(PACKAGE_ROOT).as_posix())
        assert declaring == ["ui/grid_canvas.py"]
