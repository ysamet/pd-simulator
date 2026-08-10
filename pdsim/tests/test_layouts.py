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
from pydantic import ValidationError

from pdsim.config.experiment import ExperimentConfig
from pdsim.core import engine
from pdsim.core.dynamics import build_initial_population
from pdsim.core.events import GenerationFinished
from pdsim.core.layouts import (
    LAYOUT_CHOICES,
    STOCHASTIC_LAYOUTS,
    deal_layout,
    found_occupancy,
    found_population,
    founding_view,
    layout_consumes_rng,
    parse_layout_file,
    read_layout_file,
    resolve_layout_path,
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

    def test_central_block_is_a_true_rectangle_at_non_square_n(self) -> None:
        """N=10 on 5x5: a centred 2x5 rectangle, not the blob-with-a-knob (#125).

        The generic centred footprint for 10 is the 3x3 ball plus one stray
        cell at the ring's lowest id — which is what `stripes` gets, and
        what `central_block` wrongly got before the fix.
        """
        structure = _lattice(rows=5, cols=5)
        counts = {AC: 5, AD: 5}
        block = deal_layout(structure, counts, "central_block", np.random.default_rng(0))
        assert sorted(block) == list(range(5, 15))  # rows 1-2, all five columns
        stripes = deal_layout(structure, counts, "stripes", np.random.default_rng(0))
        assert block != stripes

    def test_central_block_differs_from_stripes_on_an_oversized_grid(self) -> None:
        """The V2 walk's missing contrast: N=60 on 20x20 (#125).

        `central_block` is the centred 6x10 rectangle; `stripes` bands the
        generic centred blob. Before the fix the two were one code path and
        identical in every configuration.
        """
        structure = _lattice(rows=20, cols=20)
        counts = {AC: 30, AD: 30}
        block = deal_layout(structure, counts, "central_block", np.random.default_rng(0))
        rows = {site // 20 for site in block}
        cols = {site % 20 for site in block}
        assert rows == set(range(7, 13)) and cols == set(range(5, 15))
        assert block != deal_layout(structure, counts, "stripes", np.random.default_rng(0))

    def test_central_block_orientation_follows_the_grid(self) -> None:
        """A wide grid gets a wide block: N=12 on 3x10 is 3x4, not 4x3."""
        structure = _lattice(rows=3, cols=10)
        block = deal_layout(structure, {AC: 12}, "central_block", np.random.default_rng(0))
        rows = {site // 10 for site in block}
        cols = {site % 10 for site in block}
        assert rows == {0, 1, 2} and cols == {3, 4, 5, 6}

    def test_central_block_prime_n_makes_a_centred_line(self) -> None:
        """A prime population's only rectangle is 1xN.

        The same reading the grid's own auto-sizing gives prime populations.
        """
        structure = _lattice(rows=5, cols=5)
        block = deal_layout(structure, {AC: 5}, "central_block", np.random.default_rng(0))
        assert sorted(block) == [10, 11, 12, 13, 14]  # the middle row

    def test_central_block_falls_back_when_no_rectangle_fits(self) -> None:
        """A prime N wider than both grid dimensions: the blob, not an error."""
        structure = _lattice(rows=3, cols=3)
        counts = {AC: 3, AD: 4}
        block = deal_layout(structure, counts, "central_block", np.random.default_rng(0))
        stripes = deal_layout(structure, counts, "stripes", np.random.default_rng(0))
        assert len(block) == 7
        assert sorted(block) == sorted(stripes)  # same footprint, by design

    def test_the_blob_can_coincide_with_the_rectangle_and_that_is_not_a_bug(self) -> None:
        """N=30 on 12x12: stripes and central_block are IDENTICAL — correctly.

        The generic centred blob is built ring by ring with lowest-id ties
        filling from the top, and at this N the 30 nearest cells complete
        exactly the 5x6 rectangle rows 3-7 x cols 3-8 — the very rectangle
        `central_block` computes as 30's most-square factor pair. Whenever
        the blob happens to be a rectangle, the two layouts coincide, and
        that is a property of the footprints, not a regression of #125.
        Pinned so the next person who trips over such a case (twice now:
        100 on 20x20, 30 on 12x12) finds the explanation in the suite.
        """
        structure = _lattice(rows=12, cols=12)
        counts = {AC: 15, AD: 15}
        block = deal_layout(structure, counts, "central_block", np.random.default_rng(1))
        stripes = deal_layout(structure, counts, "stripes", np.random.default_rng(1))
        assert block == stripes
        assert sorted({site // 12 for site in block}) == [3, 4, 5, 6, 7]
        assert sorted({site % 12 for site in block}) == [3, 4, 5, 6, 7, 8]

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

    def test_the_file_wins_on_composition_at_the_founding_seam(self) -> None:
        """The engine's file-wins overwrite, tested at its own level (Design 8).

        Since #126, a CONFIG whose composition disagrees with its file never
        validates, so this defence-in-depth seam is unreachable through the
        app — but it still protects programmatically built inputs, where the
        deal must follow the file, not the agents' built-with strategies.
        """
        text = "kind: lattice_grid\nrows: 2\ncols: 2\n\n" + f"{AD} {AD}\n{AD} {AC}\n"
        layout = parse_layout_file(text)
        structure = _lattice(rows=2, cols=2)
        config = ExperimentConfig.model_validate(
            {
                "mode": "evolution",
                "population": {"size": 4, "composition": {AC: 2, AD: 2}},
                "dynamics": {"generations": 1},
            }
        )
        agents = build_initial_population(config)  # built as two of each
        occupancy = found_occupancy(
            structure,
            agents,
            {AC: 2, AD: 2},
            "from_file",
            np.random.default_rng(0),
            layout,
        )
        placements = {
            site: strategy_name_of(next(a for a in agents if a.agent_id == agent_id).strategy)
            for agent_id, site in occupancy.sites_by_agent().items()
        }
        assert placements == {0: AD, 1: AD, 2: AD, 3: AC}

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
        """The common failure is a relative path resolving somewhere unexpected.

        Since #126 this fails at CONFIG VALIDATION — as a ValidationError the
        app and CLI render as a plain sentence — not at founding time.
        """
        with pytest.raises(ValidationError, match=r"nope\.txt"):
            ExperimentConfig.model_validate(
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

    def test_replay_matches_the_engine_under_the_sync_economy(self) -> None:
        """Design 9's founding position, pinned for the economy path (#121).

        The renderer replays founding from (config, seed); that is exact
        only if no draw precedes founding in the engine. The imitation pin
        above established it for one mode — the flagship and the drifting
        frontier are ECONOMY runs, so the property must hold there too.
        The engine's placement is read off the persisted surface (founder
        snapshots' site ids), which also exercises the site_id path.
        """
        config = ExperimentConfig.model_validate(
            {
                "mode": "evolution",
                "seed": 13,
                "population": {"size": 12, "composition": {AC: 6, AD: 6}},
                "match": {"length_mode": "fixed", "rounds_per_match": 2},
                "structure": {"kind": "lattice", "rows": 4, "cols": 4, "initial_layout": "random"},
                "dynamics": {
                    "reproduction_mode": "energy_economy",
                    "generations": 2,
                    "mutation_rate": 0.0,
                    "reproduction_threshold": 1000.0,
                    "offspring_stake": 100.0,
                    "initial_energy": 100.0,
                    "basic_living_cost": 0.0,
                    "carrying_capacity": 16,
                },
            }
        )
        view = founding_view(config)
        assert view is not None
        first = next(e for e in engine.run(config) if isinstance(e, GenerationFinished))
        founders = [s for s in first.agents if s.parent_id is None]
        assert founders and all(s.site_id is not None for s in founders)
        for snapshot in founders:
            assert view.placements[snapshot.site_id] == snapshot.strategy

    def test_replay_matches_the_engine_under_the_async_clock(self) -> None:
        """The same pin for the asynchronous path (`donation_game_threshold`'s mode)."""
        config = ExperimentConfig.model_validate(
            {
                "mode": "evolution",
                "seed": 21,
                "population": {"size": 9, "composition": {AC: 5, AD: 4}},
                "matching": {"matcher": "random_k", "opponents_per_agent": 3},
                "match": {"length_mode": "fixed", "rounds_per_match": 2},
                "structure": {"kind": "lattice", "rows": 3, "cols": 3, "initial_layout": "patches"},
                "dynamics": {
                    "time_model": "asynchronous",
                    "async_population": "fixed_n",
                    "moran_rule": "death_birth",
                    "fixed_n_death_rule": "pure_random",
                    "generations": 2,
                    "mutation_rate": 0.0,
                    "offspring_stake": 0.0,
                    "basic_living_cost": 0.0,
                },
            }
        )
        view = founding_view(config)
        assert view is not None
        first = next(e for e in engine.run(config) if isinstance(e, GenerationFinished))
        # fixed_n replaces agents as it goes; the surviving FOUNDERS still
        # carry their founding sites, and under a mutation-free run their
        # strategies are exactly what the deal put there. Newborns carry
        # sites too since Phase C, but theirs are recycled seats, not
        # founding ones — so the replay pin reads founders only.
        founders = [s for s in first.agents if s.site_id is not None and s.parent_id is None]
        assert founders
        for snapshot in founders:
            assert view.placements[snapshot.site_id] == snapshot.strategy


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

    # RETIRED (M11a Phase C): test_a_deterministic_lattice_run_matches_the_
    # well_mixed_stream pinned the Phase B exit condition — "nothing reads
    # the structure", asserted as a lattice run matching its well-mixed
    # twin. That claim is false in general since local birth landed (an
    # economy lattice run draws placement kernels), and true only in the
    # imitation corner the fixture happened to use — where it is now
    # asserted more sharply by the no-draw pin (test_local_birth.py:
    # sync imitation + lattice consumes zero contest draws) and by the
    # Phase C golden masters (test_golden_masters.py), which seal the
    # well-mixed streams byte-for-byte instead of comparing trajectories.


class TestCommaSeparator:
    """The comma-separated body style (DECISIONS #123)."""

    WHITESPACE = f"kind: lattice_grid\nrows: 2\ncols: 3\n\n{AD} {AD} .\n{AC} . {AC}\n"
    COMMA = f"kind: lattice_grid\nrows: 2\ncols: 3\n\n{AD}, {AD}, .\n{AC},  . , {AC}\n"

    def test_a_comma_file_parses_identically_to_its_whitespace_twin(self) -> None:
        """Same cells, same counts — the separator is presentation only."""
        whitespace = parse_layout_file(self.WHITESPACE)
        comma = parse_layout_file(self.COMMA)
        assert comma.cells == whitespace.cells
        assert comma.strategy_counts() == whitespace.strategy_counts()
        assert (comma.rows, comma.cols) == (whitespace.rows, whitespace.cols)

    def test_one_comma_puts_the_whole_body_in_comma_mode(self) -> None:
        """Mixed-separator files are impossible by construction.

        A whitespace-looking line inside a comma-mode file is ONE token per
        line (commas are the only separator), so the cell count comes up
        short — the file is rejected rather than half-reinterpreted.
        """
        mixed = f"kind: lattice_grid\nrows: 2\ncols: 3\n\n{AD}, {AD}, .\n{AC} . {AC}\n"
        with pytest.raises(ValueError, match="6 cells but its body holds 4"):
            parse_layout_file(mixed)

    def test_an_empty_field_between_commas_is_an_error(self) -> None:
        """A bare gap must not silently mean 'empty' — that masks typos."""
        text = f"kind: lattice_grid\nrows: 2\ncols: 3\n\n{AD}, , .\n{AC}, ., {AC}\n"
        with pytest.raises(ValueError, match=r"empty field on line 5 \(cell 2\)"):
            parse_layout_file(text)

    def test_a_trailing_comma_is_an_error_too(self) -> None:
        """The blank token it produces gets the same treatment."""
        text = f"kind: lattice_grid\nrows: 1\ncols: 2\n\n{AD}, {AD},\n"
        with pytest.raises(ValueError, match=r"Write '\.' for an empty site"):
            parse_layout_file(text)

    def test_the_dot_stays_the_empty_token_in_comma_mode(self) -> None:
        """`.` means empty in both styles."""
        layout = parse_layout_file(self.COMMA)
        assert layout.cells[2] is None
        assert layout.cells[4] is None

    def test_an_unregistered_token_error_names_line_cell_and_valid_names(self) -> None:
        """The #122 surfacing: the error is a map, not a shrug."""
        text = f"kind: lattice_grid\nrows: 2\ncols: 2\n\n{AD} {AD}\ntit_for_tta {AC}\n"
        layout = parse_layout_file(text)
        with pytest.raises(ValueError) as excinfo:
            validate_layout_file(
                layout,
                rows=2,
                cols=2,
                known_strategies=frozenset({AC, AD, "tit_for_tat"}),
                population_size=4,
            )
        message = str(excinfo.value)
        assert "'tit_for_tta' (line 6, cell 1)" in message
        assert "tit_for_tat" in message  # the valid names are listed


class TestGridTemplates:
    """The shipped templates and the bare-name resolution rule (#122)."""

    def test_both_shipped_examples_parse_and_use_registered_names(self) -> None:
        """The README's examples must never rot against the registry."""
        from pdsim.core.strategies import all_strategy_names

        known = frozenset(all_strategy_names())
        for name, agents in (("example_quadrants.txt", 18), ("example_island.txt", 24)):
            layout = read_layout_file(Path("grid_templates") / name)
            validate_layout_file(
                layout, rows=4, cols=6, known_strategies=known, population_size=agents
            )
            assert layout.occupied_count == agents

    def test_a_bare_name_resolves_against_grid_templates(self) -> None:
        """No separator means 'a template' — the #122 rule."""
        resolved = resolve_layout_path("example_island.txt")
        assert resolved == Path("grid_templates") / "example_island.txt"
        assert resolved.is_file()

    def test_a_path_with_a_separator_is_used_as_given(self, tmp_path: Path) -> None:
        """Only bare names get the template lookup."""
        target = tmp_path / "mine.txt"
        target.write_text("x", encoding="utf-8")
        assert resolve_layout_path(str(target)) == target

    def test_the_beside_config_copy_outranks_a_same_named_template(self, tmp_path: Path) -> None:
        """A recorded folder's own copy outranks the template directory.

        Otherwise an old run could silently read a same-named template
        written later (hard rule 8).
        """
        (tmp_path / "example_island.txt").write_text("the folder's copy", encoding="utf-8")
        resolved = resolve_layout_path("example_island.txt", config_dir=tmp_path)
        assert resolved == tmp_path / "example_island.txt"

    def test_a_bare_template_run_founds_from_the_template(self) -> None:
        """End to end: bare name in the config, arrangement from the file."""
        config = ExperimentConfig.model_validate(
            {
                "mode": "evolution",
                "seed": 1,
                "population": {
                    "size": 24,
                    # The island's true mix — #126 requires the composition
                    # to EQUAL the file's implied one.
                    "composition": {"always_defect": 18, "tit_for_tat": 6},
                },
                "structure": {
                    "kind": "lattice",
                    "rows": 4,
                    "cols": 6,
                    "initial_layout": "from_file",
                    "layout_file": "example_island.txt",
                },
                "dynamics": {"generations": 1},
            }
        )
        view = founding_view(config)
        assert view is not None
        assert view.occupied == 24
        assert view.placements[7] == "tit_for_tat"  # island interior
        assert view.placements[0] == "always_defect"  # the sea


class TestConfigTimeLayoutValidation:
    """Every layout-file check fires at config validation (#126, Design 8).

    Before #126 these checks lived at founding time inside the engine, so a
    mistake surfaced in the app as a raw traceback. Now they are pydantic
    validators: the app's Run button and the CLI both render them as plain
    sentences, and Run is blocked while a from-file disagreement stands.
    """

    GOOD = "kind: lattice_grid\nrows: 2\ncols: 2\n\n" + f"{AC} {AC}\n{AD} {AD}\n"

    @staticmethod
    def _config_data(tmp_path: Path, text: str) -> dict[str, object]:
        """Build raw config data around a scratch layout file.

        Args:
            tmp_path: pytest's per-test directory.
            text: Layout-file contents.

        Returns:
            A dict ready for ``ExperimentConfig.model_validate``, matching
            the file (two cooperators, two defectors on a 2x2 grid).
        """
        path = tmp_path / "scratch.txt"
        path.write_text(text, encoding="utf-8")
        return {
            "mode": "evolution",
            "seed": 1,
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

    def test_a_matching_config_validates_and_founds(self, tmp_path: Path) -> None:
        """The clean path: file and widgets agree, the run is buildable."""
        config = ExperimentConfig.model_validate(self._config_data(tmp_path, self.GOOD))
        view = founding_view(config)
        assert view is not None
        assert view.occupied == 4

    def test_an_unresolvable_path_is_a_validation_error(self, tmp_path: Path) -> None:
        """Missing file: a ValidationError naming the path — nothing escapes raw."""
        data = self._config_data(tmp_path, self.GOOD)
        data["structure"]["layout_file"] = str(tmp_path / "gone.txt")  # type: ignore[index]
        with pytest.raises(ValidationError, match=r"gone\.txt"):
            ExperimentConfig.model_validate(data)

    def test_a_parse_failure_is_a_validation_error(self, tmp_path: Path) -> None:
        """A malformed header fails at validation with the parser's message."""
        broken = "kind: lattice_grid\nrows: 2\n\n. .\n. .\n"  # no cols line
        with pytest.raises(ValidationError, match="missing its 'cols' header"):
            ExperimentConfig.model_validate(self._config_data(tmp_path, broken))

    def test_the_defect_state_dimension_mismatch_fails_at_validation(self) -> None:
        """The exact observed defect: 12x12 pinned dims, the 4x6 island file.

        Before #126 this raised a raw ValueError from founding inside
        `PopulationDynamics.__init__` — a traceback in the app window. Now
        it is a ValidationError at config time, which the app's Run handler
        and the CLI already render as plain sentences; the engine is never
        constructed.
        """
        data = {
            "mode": "evolution",
            "seed": 1,
            "population": {"size": 24, "composition": {AD: 18, "tit_for_tat": 6}},
            "structure": {
                "kind": "lattice",
                "rows": 12,
                "cols": 12,
                "initial_layout": "from_file",
                "layout_file": "example_island.txt",
            },
            "dynamics": {"generations": 1},
        }
        with pytest.raises(ValidationError, match="4x6 but this run's grid is 12x12"):
            ExperimentConfig.model_validate(data)

    def test_an_unregistered_token_fails_with_its_position(self, tmp_path: Path) -> None:
        """Token, line, cell, and the valid names — the #122 error content."""
        typo = self.GOOD.replace(AD, "always_defcet")
        with pytest.raises(ValidationError, match=r"'always_defcet' \(line 6, cell 1\)"):
            ExperimentConfig.model_validate(self._config_data(tmp_path, typo))

    def test_fewer_than_two_agents_fails_at_validation(self, tmp_path: Path) -> None:
        """A near-empty file cannot found a run."""
        sparse = "kind: lattice_grid\nrows: 2\ncols: 2\n\n" + f"{AC} .\n. .\n"
        data = self._config_data(tmp_path, sparse)
        data["population"] = {"size": 2, "composition": {AC: 2}}
        with pytest.raises(ValidationError, match="at least 2"):
            ExperimentConfig.model_validate(data)

    @pytest.mark.parametrize(
        ("size", "composition"),
        [
            (4, {AC: 1, AD: 3}),  # same size, different mixture
            (6, {AC: 3, AD: 3}),  # different size, same ratio
            (4, {AC: 2, "tit_for_tat": 2}),  # different strategy set
        ],
    )
    def test_composition_disagreement_fails_and_points_at_populate(
        self, tmp_path: Path, size: int, composition: dict[str, int]
    ) -> None:
        """Size-only, mixture-only, or both: one message, naming both sides.

        This is the guard that keeps config.yaml honest (hard rule 8): a
        from-file run can never record a composition other than the one
        that actually runs. The message points at the one-click fix.
        """
        data = self._config_data(tmp_path, self.GOOD)
        data["population"] = {"size": size, "composition": composition}
        with pytest.raises(ValidationError, match="Populate the Population section from the file"):
            ExperimentConfig.model_validate(data)

    def test_ignored_layouts_are_never_validation_errors(self, tmp_path: Path) -> None:
        """#34's rule: the checks run only where the file is consumed."""
        data = self._config_data(tmp_path, self.GOOD)
        data["structure"]["layout_file"] = str(tmp_path / "gone.txt")  # type: ignore[index]
        # A generated layout ignores the stale path entirely...
        data["structure"]["initial_layout"] = "random"  # type: ignore[index]
        ExperimentConfig.model_validate(data)
        # ...and tournament mode ignores structure altogether.
        data["structure"]["initial_layout"] = "from_file"  # type: ignore[index]
        data["mode"] = "tournament"
        data["tournament_cycles"] = 1
        ExperimentConfig.model_validate(data)

    def test_a_recorded_folder_still_reloads_its_own_copy(self, tmp_path: Path) -> None:
        """load_config resolves beside-config BEFORE validating (#126).

        A recorded folder stores its layout copy under a bare name; the
        validator reads the file, so resolution must happen on the raw data
        first — otherwise every recorded from-file folder would fail to
        reload.
        """
        import yaml

        from pdsim.config.experiment import load_config

        (tmp_path / "layout.txt").write_text(self.GOOD, encoding="utf-8")
        data = self._config_data(tmp_path, self.GOOD)
        data["structure"]["layout_file"] = "layout.txt"  # type: ignore[index]
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        reloaded = load_config(config_path)
        assert Path(reloaded.structure.layout_file or "") == tmp_path / "layout.txt"
