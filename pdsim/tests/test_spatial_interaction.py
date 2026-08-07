"""Tests for M11a Phase D: local interaction (spec Designs 2, 6, 9).

The groups, in the order the spec's Phase D block lists their obligations:

* **SpatialKernel** — the thin synchronous adapter: ascending-id walk,
  partners only from within the radius, never the focal's own site, the
  #81 clamp (a bounded-Moore corner plays 3 at k = 8), and the two
  behaviours inherited from RandomK deliberately (no deduplication; clamp,
  don't raise).
* **The RNG contract** — draw unconditionally (one kernel call per focal
  agent, whether or not the neighbourhood forces the outcome) and the
  empty-eligible corner (an isolated agent plays nothing and consumes
  nothing, before any draw).
* **The async substitution** — the partner draw under lattice +
  ``spatial_interaction`` goes through the same primitive at the same
  position: partners land within the radius, and the per-method call
  sequence of a ``fixed_n`` lattice run is IDENTICAL to its well-mixed
  twin's (a substitution changes a draw's candidates, never the stream's
  shape). Toggle-off async lattice behaviour is byte-identical to Phase C
  by the pinned positive goldens in ``test_phase_c_goldens.py`` — Phase D
  re-recorded nothing.
* **The no-call assertions** — with ``spatial_interaction`` off, zero
  interaction-kernel calls occur anywhere: sync engines are watched at
  ``pdsim.core.matcher``'s primitive reference (interaction-only by
  construction), async at ``pdsim.core.async_dynamics``'s — where the
  birth/breeder kernel draws (Phase C, always ``size=1``) share the name,
  so the interaction draw is told apart by its ``size = k`` signature.
* **The validator** — spatial interaction without a lattice is a config
  error; under tournament mode the toggle is ignored (#34/#120(a)).
"""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

import pdsim.core.async_dynamics as async_dynamics_module
import pdsim.core.matcher as matcher_module
from pdsim.config.experiment import ExperimentConfig
from pdsim.core.agent import Agent
from pdsim.core.async_dynamics import AsyncDynamics
from pdsim.core.dynamics import EconomyDynamics, PopulationDynamics
from pdsim.core.match import MatchResult
from pdsim.core.matcher import SpatialKernel
from pdsim.core.occupancy import Occupancy
from pdsim.core.strategies import create_strategy
from pdsim.core.structure import LatticeStructure, neighbourhood_sample
from pdsim.tests.counting_rng import CountingGenerator

AC = "always_cooperate"
AD = "always_defect"
TFT = "tit_for_tat"


# ---------------------------------------------------------------------------
# Hand-built worlds for kernel-level tests
# ---------------------------------------------------------------------------


def _world(
    rows: int,
    cols: int,
    shape: str = "von_neumann",
    boundary: str = "torus",
    occupied: list[int] | None = None,
) -> tuple[LatticeStructure, Occupancy, list[Agent]]:
    """Build a lattice, an occupancy, and one agent per occupied site.

    Args:
        rows: Lattice rows.
        cols: Lattice columns.
        shape: Neighbourhood shape (= the metric).
        boundary: ``"torus"`` or ``"bounded"``.
        occupied: The sites to occupy, in order (agent i takes the i-th
            listed site). ``None`` fills the whole grid.

    Returns:
        The structure, the occupancy, and the agents in ascending id order.
    """
    structure = LatticeStructure(rows, cols, shape, boundary)
    occupancy = Occupancy(structure)
    strategy = create_strategy(AC)
    sites = list(range(rows * cols)) if occupied is None else occupied
    agents = []
    for agent_id, site_id in enumerate(sites):
        occupancy.occupy(site_id, agent_id)
        agents.append(Agent(agent_id=agent_id, strategy=strategy))
    return structure, occupancy, agents


def _kernel(
    occupancy: Occupancy, radius: int | None = 1, decay: float = 0.0, k: int = 4
) -> SpatialKernel:
    """Build a SpatialKernel over a hand-built world.

    Args:
        occupancy: The world's occupancy (its structure is read off it).
        radius: Interaction radius R.
        decay: Interaction decay β.
        k: Opponents per agent.

    Returns:
        The kernel adapter, ready for ``pairings``.
    """
    return SpatialKernel(
        structure=occupancy.structure, occupancy=occupancy, radius=radius, decay=decay, k=k
    )


class TestSpatialKernelPairings:
    """The thin adapter's contract: walk, radius, self-exclusion, clamp."""

    def test_focal_agents_walk_in_ascending_id_order(self) -> None:
        """Focals appear ascending even when the input sequence is reversed.

        Pairings group by focal; the walk order is the adapter's, not the
        caller's.
        """
        _, occupancy, agents = _world(3, 3)
        pairs = list(_kernel(occupancy).pairings(list(reversed(agents)), np.random.default_rng(0)))
        focal_order = []
        for focal, _ in pairs:
            if not focal_order or focal_order[-1] != focal.agent_id:
                focal_order.append(focal.agent_id)
        assert focal_order == sorted(focal_order), "focal walk must ascend"
        assert focal_order == list(range(9)), "every agent is focal exactly once"

    def test_partners_come_only_from_within_the_radius(self) -> None:
        """Every drawn partner sits within R of the focal's site."""
        structure, occupancy, agents = _world(4, 4, shape="moore")
        pairs = list(_kernel(occupancy, radius=1, k=3).pairings(agents, np.random.default_rng(1)))
        assert pairs, "a full grid must produce pairings"
        for focal, partner in pairs:
            origin = occupancy.site_of(focal.agent_id)
            target = occupancy.site_of(partner.agent_id)
            assert origin is not None and target is not None
            assert structure.distance(origin, target) <= 1

    def test_the_focal_never_draws_itself(self) -> None:
        """Eligible excludes the focal's own site, so no self-pair exists."""
        _, occupancy, agents = _world(3, 3)
        pairs = list(_kernel(occupancy, k=8).pairings(agents, np.random.default_rng(2)))
        assert all(focal.agent_id != partner.agent_id for focal, partner in pairs)

    def test_bounded_moore_corner_plays_three_at_k_eight(self) -> None:
        """The #81 clamp: 3 neighbours means 3 matches, k = 8 notwithstanding."""
        _, occupancy, agents = _world(3, 3, shape="moore", boundary="bounded")
        pairs = list(_kernel(occupancy, k=8).pairings(agents, np.random.default_rng(3)))
        initiated = {agent.agent_id: 0 for agent in agents}
        for focal, _ in pairs:
            initiated[focal.agent_id] += 1
        # Site 0 is the top-left corner (3 Moore neighbours); site 4 the
        # centre (8). Agent ids equal site ids in the full-grid world.
        assert initiated[0] == 3
        assert initiated[4] == 8

    def test_unlimited_radius_reaches_the_whole_grid(self) -> None:
        """``radius=None`` makes every other occupied site a candidate."""
        _, occupancy, agents = _world(3, 3)
        pairs = list(
            _kernel(occupancy, radius=None, k=8).pairings(agents, np.random.default_rng(4))
        )
        initiated = {agent.agent_id: 0 for agent in agents}
        for focal, _ in pairs:
            initiated[focal.agent_id] += 1
        assert all(count == 8 for count in initiated.values())


class TestDrawUnconditionally:
    """Spec Design 6's resolved fork: the call count is config-shaped."""

    @pytest.mark.parametrize("k", [2, 4, 8])
    def test_one_kernel_draw_per_focal_regardless_of_fullness(self, k: int) -> None:
        """9 focals mean 9 ``choice`` calls, whatever k is.

        At k below, at, and above the neighbourhood size — including where
        the outcome is forced and the draw is "wasted" on purpose.
        """
        _, occupancy, agents = _world(3, 3)
        counted = CountingGenerator(np.random.default_rng(5))
        list(_kernel(occupancy, k=k).pairings(agents, counted))  # type: ignore[arg-type]
        assert counted.count("choice") == 9

    def test_isolated_agents_play_nothing_and_draw_nothing(self) -> None:
        """Empty eligible set: the primitive returns () BEFORE drawing."""
        _, occupancy, agents = _world(5, 5, occupied=[0, 12])
        counted = CountingGenerator(np.random.default_rng(6))
        pairs = list(_kernel(occupancy).pairings(agents, counted))  # type: ignore[arg-type]
        assert pairs == []
        assert counted.count("choice") == 0

    def test_mixed_world_draws_only_for_connected_focals(self) -> None:
        """One isolated agent among a connected pair: two draws, not three."""
        _, occupancy, agents = _world(5, 5, occupied=[0, 1, 12])
        counted = CountingGenerator(np.random.default_rng(7))
        pairs = list(_kernel(occupancy).pairings(agents, counted))  # type: ignore[arg-type]
        assert counted.count("choice") == 2
        involved = {agent.agent_id for pair in pairs for agent in pair}
        assert involved == {0, 1}, "the isolated agent appears in no pairing"


# ---------------------------------------------------------------------------
# Engine-level: the sync no-dedup contract (and VT-6(b)'s number, pinned)
# ---------------------------------------------------------------------------


def _sync_imitation_spatial_config(**matching_overrides: object) -> ExperimentConfig:
    """A 3x3 torus von Neumann imitation run with spatial interaction on.

    Args:
        **matching_overrides: Extra ``matching`` fields (e.g. a different k).

    Returns:
        A validated config; k = 4 covers the whole von Neumann
        neighbourhood, the Hammond–Axelrod play-all-neighbours convention.
    """
    matching: dict[str, object] = {"spatial_interaction": True, "opponents_per_agent": 4}
    matching.update(matching_overrides)
    return ExperimentConfig.model_validate(
        {
            "seed": 11,
            "population": {"size": 9, "composition": {AC: 5, AD: 4}},
            "matching": matching,
            "match": {"length_mode": "fixed", "rounds_per_match": 1},
            "structure": {
                "kind": "lattice",
                "rows": 3,
                "cols": 3,
                "initial_layout": "stripes",
                "neighbourhood_shape": "von_neumann",
            },
            "dynamics": {"generations": 1, "mutation_rate": 0.0},
        }
    )


class TestNoDeduplication:
    """Inherited RandomK behaviour 1 (#57): pairs can meet twice."""

    def test_adjacent_agents_meet_exactly_twice_when_k_covers_the_neighbourhood(
        self,
    ) -> None:
        """Every adjacent pair plays exactly two matches at k = 4.

        At k = neighbourhood size every draw is forced, so A draws B AND B
        draws A, and each agent plays exactly 8 (4 initiated + 4 received)
        — the VT-6(b) arithmetic, pinned as a test.
        """
        config = _sync_imitation_spatial_config()
        dynamics = PopulationDynamics(config, np.random.default_rng(config.seed))
        matches: list[MatchResult] = []
        dynamics.step(on_match=matches.append)
        per_pair: dict[tuple[int, int], int] = {}
        per_agent: dict[int, int] = {}
        for result in matches:
            a, b = result.agent_ids
            key = (min(a, b), max(a, b))
            per_pair[key] = per_pair.get(key, 0) + 1
            for agent_id in (a, b):
                per_agent[agent_id] = per_agent.get(agent_id, 0) + 1
        assert set(per_pair.values()) == {2}, "every adjacent pair meets exactly twice"
        assert set(per_agent.values()) == {8}, "each agent plays 4 initiated + 4 received"
        assert len(matches) == 36  # 9 focals x 4 forced draws


# ---------------------------------------------------------------------------
# The async substitution
# ---------------------------------------------------------------------------


def _async_fixed_n_config(kind: str, spatial: bool, k: int = 2) -> ExperimentConfig:
    """A fixed_n Moran run — lattice or well-mixed twin, same everything else.

    Args:
        kind: ``"lattice"`` (3x3, stripes) or ``"well_mixed"``.
        spatial: The ``matching.spatial_interaction`` toggle.
        k: Opponents per agent.

    Returns:
        A validated config with deterministic strategies, one-round
        matches, no noise, and μ = 0 — so the ONLY RNG consumers are the
        focal, partner, victim, and breeder draws, and the per-method call
        sequence is fully config-shaped.
    """
    structure: dict[str, object] = {"kind": kind}
    if kind == "lattice":
        structure.update(
            {
                "rows": 3,
                "cols": 3,
                "initial_layout": "stripes",
                "neighbourhood_shape": "von_neumann",
            }
        )
    return ExperimentConfig.model_validate(
        {
            "seed": 19,
            "population": {"size": 9, "composition": {TFT: 5, AD: 4}},
            "matching": {"spatial_interaction": spatial, "opponents_per_agent": k},
            "match": {"length_mode": "fixed", "rounds_per_match": 1},
            "structure": structure,
            "dynamics": {
                "generations": 2,
                "time_model": "asynchronous",
                "async_population": "fixed_n",
                "moran_rule": "death_birth",
                "fixed_n_death_rule": "pure_random",
                "mutation_rate": 0.0,
            },
        }
    )


class TestAsyncSubstitution:
    """One primitive, same position: the partner draw localises, nothing else."""

    def test_partners_land_within_the_interaction_radius(self) -> None:
        """Every async match under the toggle joins two sites at distance ≤ 1."""
        config = _async_fixed_n_config("lattice", spatial=True, k=4)
        dynamics = AsyncDynamics(config, np.random.default_rng(config.seed))
        occupancy = dynamics._occupancy
        assert occupancy is not None
        structure = occupancy.structure
        seen = 0

        def check(result: MatchResult) -> None:
            nonlocal seen
            seen += 1
            site_a = occupancy.site_of(result.agent_ids[0])
            site_b = occupancy.site_of(result.agent_ids[1])
            assert site_a is not None and site_b is not None
            assert structure.distance(site_a, site_b) <= 1

        for _ in dynamics.run(on_match=check):
            pass
        assert seen > 0, "the run must actually play matches"

    def test_variable_n_partners_land_within_the_radius_too(self) -> None:
        """The substitution serves BOTH async population modes (one call site)."""
        config = ExperimentConfig.model_validate(
            {
                "seed": 29,
                "population": {"size": 9, "composition": {TFT: 5, AD: 4}},
                "matching": {"spatial_interaction": True, "opponents_per_agent": 3},
                "match": {"length_mode": "fixed", "rounds_per_match": 1},
                "structure": {
                    "kind": "lattice",
                    "rows": 3,
                    "cols": 3,
                    "initial_layout": "stripes",
                    "neighbourhood_shape": "von_neumann",
                },
                "dynamics": {
                    "generations": 2,
                    "time_model": "asynchronous",
                    "reproduction_threshold": 60.0,
                    "offspring_stake": 50.0,
                    "basic_living_cost": 10.0,
                    "carrying_capacity": 9,
                    "mutation_rate": 0.0,
                },
            }
        )
        dynamics = AsyncDynamics(config, np.random.default_rng(config.seed))
        occupancy = dynamics._occupancy
        assert occupancy is not None
        structure = occupancy.structure

        def check(result: MatchResult) -> None:
            site_a = occupancy.site_of(result.agent_ids[0])
            site_b = occupancy.site_of(result.agent_ids[1])
            assert site_a is not None and site_b is not None
            assert structure.distance(site_a, site_b) <= 1

        for _ in dynamics.run(on_match=check):
            pass

    def test_lattice_run_consumes_the_exact_call_sequence_of_its_well_mixed_twin(
        self,
    ) -> None:
        """Substitution, not insertion: identical per-method call sequences.

        A spatial ``fixed_n`` run's call-name sequence matches its
        well-mixed twin's — same length, same names, same order. Only
        candidate sets and weights differ, which is exactly what a
        substitution means (#99/#133 discipline).
        """
        spatial = CountingGenerator(np.random.default_rng(19))
        dynamics = AsyncDynamics(_async_fixed_n_config("lattice", spatial=True), spatial)  # type: ignore[arg-type]
        for _ in dynamics.run():
            pass
        well_mixed = CountingGenerator(np.random.default_rng(19))
        twin = AsyncDynamics(_async_fixed_n_config("well_mixed", spatial=False), well_mixed)  # type: ignore[arg-type]
        for _ in twin.run():
            pass
        spatial_names = [name for name, _, _ in spatial.calls]
        well_mixed_names = [name for name, _, _ in well_mixed.calls]
        assert spatial_names == well_mixed_names


# ---------------------------------------------------------------------------
# The no-call assertions (spec Design 9: gates hold shut)
# ---------------------------------------------------------------------------


def _record_kernel_calls(monkeypatch: pytest.MonkeyPatch, module: object) -> list[dict]:
    """Route one module's ``neighbourhood_sample`` reference through a recorder.

    Args:
        monkeypatch: pytest's patching fixture.
        module: The module whose imported reference to watch —
            ``pdsim.core.matcher`` sees ONLY interaction draws (the sync
            engines' birth draws go through ``pdsim.core.dynamics``'s own
            reference), while ``pdsim.core.async_dynamics`` also carries
            the Phase C breeder/victim/placement draws, all ``size=1``.

    Returns:
        A list the recorder appends each call's keyword arguments to.
    """
    calls: list[dict] = []

    def recording(*args: object, **kwargs: object) -> object:
        calls.append(dict(kwargs))
        return neighbourhood_sample(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(module, "neighbourhood_sample", recording)
    return calls


def _run_sync(config: ExperimentConfig) -> None:
    """Run a synchronous config to completion on its own seed.

    Args:
        config: An evolution-mode synchronous config.
    """
    rng = np.random.default_rng(config.seed)
    if config.dynamics.reproduction_mode == "energy_economy":
        dynamics: PopulationDynamics | EconomyDynamics = EconomyDynamics(config, rng)
    else:
        dynamics = PopulationDynamics(config, rng)
    for _ in dynamics.run():
        pass


class TestNoInteractionCallsWhenOff:
    """Toggle off — well-mixed AND lattice — zero interaction-kernel calls."""

    def test_sync_imitation_well_mixed_makes_no_interaction_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The classic imitation run never touches the matcher's kernel."""
        calls = _record_kernel_calls(monkeypatch, matcher_module)
        _run_sync(
            ExperimentConfig.model_validate(
                {
                    "seed": 3,
                    "population": {"size": 8, "composition": {TFT: 4, AD: 4}},
                    "match": {"length_mode": "fixed", "rounds_per_match": 2},
                    "dynamics": {"generations": 2, "mutation_rate": 0.0},
                }
            )
        )
        assert calls == []

    def test_sync_imitation_lattice_toggle_off_makes_no_interaction_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A lattice ALONE never localises interaction.

        The gate is the conjunction lattice + ``spatial_interaction``.
        """
        calls = _record_kernel_calls(monkeypatch, matcher_module)
        _run_sync(
            ExperimentConfig.model_validate(
                {
                    "seed": 3,
                    "population": {"size": 9, "composition": {TFT: 5, AD: 4}},
                    "structure": {
                        "kind": "lattice",
                        "rows": 3,
                        "cols": 3,
                        "initial_layout": "stripes",
                    },
                    "match": {"length_mode": "fixed", "rounds_per_match": 2},
                    "dynamics": {"generations": 2, "mutation_rate": 0.0},
                }
            )
        )
        assert calls == []

    def test_sync_economy_lattice_toggle_off_makes_no_interaction_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The matcher's kernel reference stays silent with the toggle off.

        Phase C's birth draws go through dynamics.py's own reference, so
        this watch point is interaction-only.
        """
        calls = _record_kernel_calls(monkeypatch, matcher_module)
        _run_sync(
            ExperimentConfig.model_validate(
                {
                    "seed": 23,
                    "population": {"size": 4, "composition": {AC: 2, AD: 2}},
                    "structure": {
                        "kind": "lattice",
                        "rows": 3,
                        "cols": 3,
                        "initial_layout": "stripes",
                    },
                    "match": {"length_mode": "fixed", "rounds_per_match": 2},
                    "dynamics": {
                        "generations": 4,
                        "reproduction_mode": "energy_economy",
                        "mutation_rate": 0.0,
                        "initial_energy": 480.0,
                        "basic_living_cost": 5.0,
                        "reproduction_threshold": 500.0,
                        "offspring_stake": 400.0,
                        "carrying_capacity": 9,
                    },
                }
            )
        )
        assert calls == []

    def test_sync_spatial_on_is_the_positive_control(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The recorder can see interaction draws at all (positive control).

        Toggle on: one call per focal per generation.
        """
        calls = _record_kernel_calls(monkeypatch, matcher_module)
        config = _sync_imitation_spatial_config()
        _run_sync(config)
        assert len(calls) == 9  # 9 focals x 1 generation

    def test_async_well_mixed_makes_no_kernel_call_at_all(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No lattice, no kernel — the async module's reference stays silent."""
        calls = _record_kernel_calls(monkeypatch, async_dynamics_module)
        config = _async_fixed_n_config("well_mixed", spatial=False)
        dynamics = AsyncDynamics(config, np.random.default_rng(config.seed))
        for _ in dynamics.run():
            pass
        assert calls == []

    def test_async_lattice_toggle_off_makes_no_interaction_sized_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No interaction-sized kernel call under a toggle-off lattice.

        A toggle-off ``fixed_n`` lattice run's kernel calls are all Phase
        C's breeder draws (``size=1``); none carries the interaction
        draw's ``size = k`` signature.
        """
        calls = _record_kernel_calls(monkeypatch, async_dynamics_module)
        config = _async_fixed_n_config("lattice", spatial=False, k=3)
        dynamics = AsyncDynamics(config, np.random.default_rng(config.seed))
        for _ in dynamics.run():
            pass
        assert calls, "Phase C's localised breeder draws must be visible"
        assert all(call.get("size") == 1 for call in calls)

    def test_async_spatial_on_is_the_positive_control(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Toggle on: interaction-sized (``size = k``) calls appear."""
        calls = _record_kernel_calls(monkeypatch, async_dynamics_module)
        config = _async_fixed_n_config("lattice", spatial=True, k=3)
        dynamics = AsyncDynamics(config, np.random.default_rng(config.seed))
        for _ in dynamics.run():
            pass
        assert any(call.get("size") == 3 for call in calls)


# ---------------------------------------------------------------------------
# The validator
# ---------------------------------------------------------------------------


class TestSpatialInteractionValidator:
    """Spatial interaction requires a lattice — at config time, in plain words."""

    def test_spatial_interaction_without_a_lattice_is_a_config_error(self) -> None:
        """The message names both settings and says why."""
        with pytest.raises(ValidationError, match=r"spatial_interaction.*structure\.kind") as info:
            ExperimentConfig.model_validate(
                {
                    "population": {"size": 4, "composition": {AC: 2, AD: 2}},
                    "matching": {"spatial_interaction": True},
                }
            )
        assert "no distance to sample within" in str(info.value)

    def test_spatial_interaction_with_a_lattice_validates(self) -> None:
        """The intended configuration passes."""
        config = ExperimentConfig.model_validate(
            {
                "population": {"size": 4, "composition": {AC: 2, AD: 2}},
                "matching": {"spatial_interaction": True},
                "structure": {"kind": "lattice", "rows": 2, "cols": 2},
            }
        )
        assert config.matching.spatial_interaction is True

    def test_tournament_mode_ignores_the_toggle(self) -> None:
        """Tournament mode never errors on the toggle.

        Structure is ignored wholesale under tournament (#120(a)); the
        toggle gets the identical treatment — ignored parameters are never
        validation errors (#34).
        """
        config = ExperimentConfig.model_validate(
            {
                "mode": "tournament",
                "population": {"size": 4, "composition": {AC: 2, AD: 2}},
                "matching": {"spatial_interaction": True},
            }
        )
        assert config.mode == "tournament"
