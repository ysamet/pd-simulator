"""Tests for occupancy, founding layouts, and the layout file (M11a Phase B).

The phase's exit condition is the thing most worth pinning: structure exists
and is VISIBLE, and nothing reads it. So alongside the layout arithmetic
these tests assert the negative — a well-mixed run builds no structure and
consumes no randomness, and a lattice run with a deterministic layout leaves
the event stream exactly where it was.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pdsim.config.experiment import ExperimentConfig
from pdsim.core import engine
from pdsim.core.dynamics import build_initial_population
from pdsim.core.events import GenerationFinished
from pdsim.core.layouts import (
    LAYOUT_CHOICES,
    STOCHASTIC_LAYOUTS,
    deal_layout,
    found_population,
    founding_view,
    layout_consumes_rng,
    parse_layout_file,
    validate_layout_file,
)
from pdsim.core.occupancy import Occupancy
from pdsim.core.strategies import strategy_name_of
from pdsim.core.structure import LatticeStructure

AC = "always_cooperate"
AD = "always_defect"


def _lattice(
    rows: int = 4, cols: int = 4, shape: str = "moore", boundary: str = "torus"
) -> LatticeStructure:
    """Build a lattice for a test.

    Args:
        rows: Row count.
        cols: Column count.
        shape: Neighbourhood shape.
        boundary: Boundary rule.

    Returns:
        The structure.
    """
    return LatticeStructure(rows=rows, cols=cols, neighbourhood_shape=shape, boundary=boundary)


def _config(**structure: object) -> ExperimentConfig:
    """Build a tiny lattice config.

    Args:
        **structure: Overrides for the ``structure`` section.

    Returns:
        A validated config with 16 agents, half cooperators, half defectors.
    """
    section = {"kind": "lattice", "rows": 4, "cols": 4}
    section.update(structure)
    return ExperimentConfig.model_validate(
        {
            "mode": "evolution",
            "seed": 7,
            "population": {"size": 16, "composition": {AC: 8, AD: 8}},
            "match": {"length_mode": "fixed", "rounds_per_match": 2},
            "structure": section,
            "dynamics": {"generations": 3},
        }
    )


class TestOccupancy:
    """The mutable site → agent bookkeeping (spec Design 3)."""

    def test_the_two_mappings_stay_consistent(self) -> None:
        """Occupying writes both directions; vacating clears both."""
        occupancy = Occupancy(_lattice())
        occupancy.occupy(5, 42)
        assert occupancy.agent_at(5) == 42
        assert occupancy.site_of(42) == 5
        assert occupancy.sites_by_agent() == {42: 5}
        assert occupancy.vacate(5) == 42
        assert occupancy.agent_at(5) is None
        assert occupancy.site_of(42) is None

    def test_a_site_holds_at_most_one_agent(self) -> None:
        """Exclusivity is enforced, not assumed (capacity is pinned at 1)."""
        occupancy = Occupancy(_lattice())
        occupancy.occupy(0, 1)
        with pytest.raises(ValueError, match="already holds"):
            occupancy.occupy(0, 2)

    def test_an_agent_occupies_at_most_one_site(self) -> None:
        """Agents do not move in M11a, so double placement is a bug, not a move."""
        occupancy = Occupancy(_lattice())
        occupancy.occupy(0, 1)
        with pytest.raises(ValueError, match="already occupies"):
            occupancy.occupy(1, 1)

    def test_remove_agent_is_the_death_side_inverse(self) -> None:
        """Deaths know the agent; placement knows the site. Both work."""
        occupancy = Occupancy(_lattice())
        occupancy.occupy(9, 3)
        assert occupancy.remove_agent(3) == 9
        assert occupancy.empty_sites() == frozenset(range(16))

    def test_vacating_an_empty_site_raises(self) -> None:
        """A silent no-op here would let the two mappings drift apart."""
        occupancy = Occupancy(_lattice())
        with pytest.raises(KeyError, match="already empty"):
            occupancy.vacate(0)

    def test_empty_sites_within_against_a_hand_computed_fixture(self) -> None:
        """Radius-1 emptiness on a 4x4 von Neumann torus, computed by hand.

        Site 5 sits at (1, 1); its von Neumann neighbours are (0,1)=1,
        (2,1)=9, (1,0)=4 and (1,2)=6. Filling 4 and 9 leaves 1 and 6.
        """
        structure = _lattice(shape="von_neumann")
        occupancy = Occupancy(structure)
        occupancy.occupy(4, 100)
        occupancy.occupy(9, 101)
        assert occupancy.empty_sites_within(5, 1) == (1, 6)

    def test_isolated_agents_finds_the_lone_one(self) -> None:
        """The Design 8 guard: an agent with no occupied neighbour."""
        structure = _lattice(shape="von_neumann", boundary="bounded")
        occupancy = Occupancy(structure)
        occupancy.occupy(0, 1)  # (0,0)
        occupancy.occupy(1, 2)  # (0,1) — adjacent to site 0
        occupancy.occupy(15, 3)  # (3,3) — nobody near
        assert occupancy.isolated_agents() == (3,)


class TestLayoutDealing:
    """The six algorithmic layouts (spec Design 8)."""

    @pytest.mark.parametrize("layout", sorted(set(LAYOUT_CHOICES) - {"from_file"}))
    def test_counts_are_conserved_exactly(self, layout: str) -> None:
        """The dealt deck equals the #67-resolved composition, every layout."""
        structure = _lattice()
        counts = {AC: 6, AD: 10}
        placement = deal_layout(structure, counts, layout, np.random.default_rng(3))
        dealt: dict[str, int] = {}
        for name in placement.values():
            dealt[name] = dealt.get(name, 0) + 1
        assert dealt == counts

    @pytest.mark.parametrize("layout", sorted(set(LAYOUT_CHOICES) - {"from_file"}))
    def test_layouts_are_deterministic_under_a_fixed_seed(self, layout: str) -> None:
        """Same config, same seed, same arrangement — for stochastic ones too."""
        structure = _lattice()
        counts = {AC: 8, AD: 8}
        first = deal_layout(structure, counts, layout, np.random.default_rng(11))
        second = deal_layout(structure, counts, layout, np.random.default_rng(11))
        assert first == second

    def test_deal_order_is_ascending_machine_name(self) -> None:
        """#67's tie-break, reused: `always_cooperate` is dealt before `always_defect`."""
        structure = _lattice()
        placement = deal_layout(structure, {AD: 8, AC: 8}, "stripes", np.random.default_rng(0))
        assert placement[0] == AC
        assert placement[15] == AD

    def test_stripes_run_lengths_equal_the_counts(self) -> None:
        """Each strategy's whole count is one consecutive run, row-major."""
        structure = _lattice()
        placement = deal_layout(structure, {AC: 5, AD: 11}, "stripes", np.random.default_rng(0))
        ordered = [placement[site_id] for site_id in sorted(placement)]
        assert ordered == [AC] * 5 + [AD] * 11

    def test_two_equal_strategies_make_a_literal_checkerboard(self) -> None:
        """The spec's acceptance test for `checkerboard` (spec Design 8)."""
        structure = _lattice()
        placement = deal_layout(structure, {AC: 8, AD: 8}, "checkerboard", np.random.default_rng(0))
        for site_id, name in placement.items():
            row, col = divmod(site_id, 4)
            expected = AC if (row + col) % 2 == 0 else AD
            assert name == expected, f"site {site_id} ({row},{col}) holds {name}"

    def test_checkerboard_generalises_by_purpose_not_appearance(self) -> None:
        """Four unequal strategies still interleave; nothing crashes or under-deals."""
        structure = _lattice()
        counts = {AC: 7, AD: 5, "tit_for_tat": 3, "grim_trigger": 1}
        placement = deal_layout(structure, counts, "checkerboard", np.random.default_rng(0))
        assert len(placement) == 16

    def test_blocks_is_compact_in_two_dimensions(self) -> None:
        """A `blocks` run spans fewer rows than the same run under `stripes`.

        The property that distinguishes the two layouts: tiles keep a run
        chunky, where a row-major sweep smears it across whole rows.
        """
        structure = _lattice(rows=4, cols=4)
        counts = {AC: 4, AD: 12}
        blocks = deal_layout(structure, counts, "blocks", np.random.default_rng(0))
        stripes = deal_layout(structure, counts, "stripes", np.random.default_rng(0))
        block_cols = {site_id % 4 for site_id, name in blocks.items() if name == AC}
        stripe_cols = {site_id % 4 for site_id, name in stripes.items() if name == AC}
        assert len(block_cols) < len(stripe_cols)

    def test_central_block_footprint_is_centred(self) -> None:
        """The filling regime: a centred rectangle, the rest of the world empty."""
        structure = _lattice(rows=5, cols=5)
        placement = deal_layout(structure, {AC: 9}, "central_block", np.random.default_rng(0))
        assert sorted(placement) == [6, 7, 8, 11, 12, 13, 16, 17, 18]

    def test_random_scatters_over_the_whole_grid(self) -> None:
        """`random` means random: it does not confine itself to a centred block."""
        structure = _lattice(rows=6, cols=6)
        placement = deal_layout(structure, {AC: 6}, "random", np.random.default_rng(5))
        centred = {14, 15, 20, 21, 22, 28}
        assert set(placement) != centred

    def test_patterned_layouts_use_a_centred_footprint_when_sparse(self) -> None:
        """The patterned five stay contiguous when N is below the site count."""
        structure = _lattice(rows=5, cols=5)
        placement = deal_layout(structure, {AC: 4, AD: 5}, "stripes", np.random.default_rng(0))
        assert sorted(placement) == [6, 7, 8, 11, 12, 13, 16, 17, 18]

    def test_patches_consume_rng_only_at_the_seeds(self) -> None:
        """Growth is deterministic: two different seeds move the patches, not the sizes."""
        structure = _lattice(rows=6, cols=6)
        counts = {AC: 18, AD: 18}
        first = deal_layout(structure, counts, "patches", np.random.default_rng(1))
        second = deal_layout(structure, counts, "patches", np.random.default_rng(2))
        assert first != second
        for placement in (first, second):
            tally: dict[str, int] = {}
            for name in placement.values():
                tally[name] = tally.get(name, 0) + 1
            assert tally == counts

    def test_more_agents_than_sites_is_refused(self) -> None:
        """Every site holds at most one agent; the error says so."""
        with pytest.raises(ValueError, match="cannot be placed"):
            deal_layout(_lattice(rows=2, cols=2), {AC: 5}, "random", np.random.default_rng(0))


class TestLayoutFile:
    """Parsing, validating, and using a hand-authored layout (spec Design 8)."""

    TEXT = f"kind: lattice_grid\nrows: 2\ncols: 3\n\n{AD} {AD} .\n{AC} .   {AC}\n"

    def test_parse_round_trip(self) -> None:
        """Header and body come back exactly as written, `.` meaning empty."""
        layout = parse_layout_file(self.TEXT)
        assert (layout.kind, layout.rows, layout.cols) == ("lattice_grid", 2, 3)
        assert layout.cells == (AD, AD, None, AC, None, AC)
        assert layout.occupied_count == 4
        assert layout.strategy_counts() == {AC: 2, AD: 2}

    def test_comments_and_blank_lines_are_ignored(self) -> None:
        """A hand-authored file can be annotated."""
        layout = parse_layout_file("# a note\n" + self.TEXT + "\n# trailing\n")
        assert layout.occupied_count == 4

    def test_a_missing_header_line_is_reported(self) -> None:
        """The message names the missing key and shows the expected shape."""
        with pytest.raises(ValueError, match="missing its 'cols' header"):
            parse_layout_file("kind: lattice_grid\nrows: 2\n\n. .\n")

    def test_an_unknown_kind_is_refused(self) -> None:
        """The discriminator ships from day one so M19's variant is additive."""
        with pytest.raises(ValueError, match="site_map"):
            parse_layout_file("kind: site_map\nrows: 1\ncols: 1\n\n.\n")

    def test_a_wrong_cell_count_is_reported(self) -> None:
        """Every cell needs a token — silence here would shift the whole grid."""
        with pytest.raises(ValueError, match="body"):
            parse_layout_file("kind: lattice_grid\nrows: 2\ncols: 3\n\n. . .\n")

    def test_dimension_mismatch_is_rejected(self) -> None:
        """Validator 1: the header must match the run's resolved grid."""
        layout = parse_layout_file(self.TEXT)
        with pytest.raises(ValueError, match="2x3 but this run's grid is 4x4"):
            validate_layout_file(
                layout, rows=4, cols=4, known_strategies=frozenset({AC, AD}), population_size=4
            )

    def test_unregistered_token_is_rejected(self) -> None:
        """Validator 2: every non-'.' token must be a registered strategy."""
        layout = parse_layout_file(self.TEXT.replace(AC, "wishful_thinking"))
        with pytest.raises(ValueError, match="wishful_thinking"):
            validate_layout_file(
                layout, rows=2, cols=3, known_strategies=frozenset({AC, AD}), population_size=4
            )

    def test_population_size_mismatch_is_rejected(self) -> None:
        """The file decides WHICH strategy each agent has; N must still agree."""
        layout = parse_layout_file(self.TEXT)
        with pytest.raises(ValueError, match=r"places 4 agents but population\.size is 6"):
            validate_layout_file(
                layout, rows=2, cols=3, known_strategies=frozenset({AC, AD}), population_size=6
            )

    def test_the_file_wins_on_composition(self, tmp_path: Path) -> None:
        """A file whose mix contradicts the widgets overrides them (Design 8)."""
        text = "kind: lattice_grid\nrows: 2\ncols: 2\n\n" + f"{AD} {AD}\n{AD} {AC}\n"
        path = tmp_path / "painted.txt"
        path.write_text(text, encoding="utf-8")
        config = ExperimentConfig.model_validate(
            {
                "mode": "evolution",
                "seed": 1,
                # The widgets say two of each; the file says three defectors.
                "population": {"size": 4, "composition": {AC: 2, AD: 2}},
                "structure": {
                    "kind": "lattice",
                    "rows": 2,
                    "cols": 2,
                    "initial_layout": "from_file",
                    "layout_file": str(path),
                },
                "dynamics": {"generations": 1},
            }
        )
        view = founding_view(config)
        assert view is not None
        assert view.placements == {0: AD, 1: AD, 2: AD, 3: AC}

    def test_from_file_without_a_path_is_a_config_error(self) -> None:
        """Only the missing-path direction can silently run the wrong experiment."""
        with pytest.raises(ValueError, match="layout_file"):
            ExperimentConfig.model_validate(
                {
                    "mode": "evolution",
                    "population": {"size": 4, "composition": {AC: 4}},
                    "structure": {"kind": "lattice", "initial_layout": "from_file"},
                }
            )

    def test_a_missing_file_names_the_resolved_path(self, tmp_path: Path) -> None:
        """The common failure is a relative path resolving somewhere unexpected."""
        config = ExperimentConfig.model_validate(
            {
                "mode": "evolution",
                "population": {"size": 4, "composition": {AC: 4}},
                "structure": {
                    "kind": "lattice",
                    "rows": 2,
                    "cols": 2,
                    "initial_layout": "from_file",
                    "layout_file": str(tmp_path / "nope.txt"),
                },
            }
        )
        with pytest.raises(FileNotFoundError, match=r"nope\.txt"):
            founding_view(config)


class TestFounding:
    """Agents acquiring sites at generation 0."""

    def test_every_founder_gets_a_site(self) -> None:
        """N agents, N distinct sites, both mappings complete."""
        config = _config()
        agents = build_initial_population(config)
        occupancy = found_population(config, agents, np.random.default_rng(config.seed))
        assert occupancy is not None
        assert len(occupancy) == 16
        assert len(set(occupancy.sites_by_agent().values())) == 16

    def test_founding_view_matches_what_the_engine_founds(self) -> None:
        """The panel's preview and the engine's placement cannot drift apart.

        Both replay the same first draw from the same seed — the property the
        renderer depends on for imitation runs, which persist no sites at all.
        """
        config = _config(initial_layout="patches")
        view = founding_view(config)
        events = [e for e in engine.run(config) if isinstance(e, GenerationFinished)]
        assert view is not None
        assert events  # the run happened
        agents = build_initial_population(config)
        occupancy = found_population(config, agents, np.random.default_rng(config.seed))
        assert occupancy is not None
        by_id = {agent.agent_id: agent for agent in agents}
        engine_placement = {
            site: strategy_name_of(by_id[agent_id].strategy)
            for agent_id, site in occupancy.sites_by_agent().items()
        }
        assert view.placements == engine_placement

    def test_the_view_reports_the_site_count_and_occupancy(self) -> None:
        """V1's derived readout, computed from the same resolver the run uses."""
        config = _config()
        view = founding_view(config)
        assert view is not None
        assert (view.rows, view.cols, view.site_count) == (4, 4, 16)
        assert view.occupied == 16
        assert view.occupancy_fraction == 1.0

    def test_a_tournament_has_no_structure(self) -> None:
        """Nothing is born and nothing dies, so space has nothing to do."""
        config = ExperimentConfig.model_validate(
            {
                "mode": "tournament",
                "population": {"size": 4, "composition": {AC: 2, AD: 2}},
                "structure": {"kind": "lattice", "rows": 2, "cols": 2},
            }
        )
        assert founding_view(config) is None


class TestWellMixedIsUntouched:
    """Defining principle 1, asserted directly (this replaces Phase A's guard)."""

    def test_a_well_mixed_run_builds_no_occupancy(self) -> None:
        """The well-mixed path does not route through structure code at all."""
        config = ExperimentConfig.model_validate(
            {
                "mode": "evolution",
                "seed": 3,
                "population": {"size": 6, "composition": {AC: 3, AD: 3}},
                "dynamics": {"generations": 2},
            }
        )
        agents = build_initial_population(config)
        assert found_population(config, agents, np.random.default_rng(1)) is None
        assert founding_view(config) is None

    def test_a_well_mixed_run_consumes_no_founding_draw(self) -> None:
        """The gate, stated as a stream property rather than an output one.

        A spurious draw would shift everything downstream — but only if
        something downstream consumed randomness. Comparing the generator's
        state directly catches it either way.
        """
        config = ExperimentConfig.model_validate(
            {
                "mode": "evolution",
                "population": {"size": 6, "composition": {AC: 3, AD: 3}},
            }
        )
        rng = np.random.default_rng(99)
        before = rng.bit_generator.state
        found_population(config, build_initial_population(config), rng)
        assert rng.bit_generator.state == before

    @pytest.mark.parametrize("layout", sorted(set(LAYOUT_CHOICES) - STOCHASTIC_LAYOUTS))
    def test_deterministic_layouts_consume_no_draw_either(self, layout: str) -> None:
        """The active-flag idiom: a draw exists only where it means something."""
        assert not layout_consumes_rng("lattice", layout)

    @pytest.mark.parametrize("layout", sorted(STOCHASTIC_LAYOUTS))
    def test_stochastic_layouts_declare_their_draw(self, layout: str) -> None:
        """`random` shuffles and `patches` seeds; both are gated on the lattice."""
        assert layout_consumes_rng("lattice", layout)
        assert not layout_consumes_rng("well_mixed", layout)

    def test_a_deterministic_lattice_run_matches_the_well_mixed_stream(self) -> None:
        """The exit condition, as an executable assertion.

        Nothing reads the structure yet, and a deterministic layout consumes
        no randomness — so a lattice run and a well-mixed run at the same
        seed must produce the same composition trajectory. When Phase C
        wires local birth, this test is expected to start failing and should
        be retired then, not weakened now.
        """

        def trajectory(kind: str) -> list[dict[str, int]]:
            config = ExperimentConfig.model_validate(
                {
                    "mode": "evolution",
                    "seed": 5,
                    "population": {"size": 16, "composition": {AC: 8, AD: 8}},
                    "match": {"length_mode": "fixed", "rounds_per_match": 3},
                    "structure": {"kind": kind, "rows": 4, "cols": 4, "initial_layout": "stripes"},
                    "dynamics": {"generations": 4, "mutation_rate": 0.1},
                }
            )
            return [
                event.composition
                for event in engine.run(config)
                if isinstance(event, GenerationFinished)
            ]

        assert trajectory("lattice") == trajectory("well_mixed")
