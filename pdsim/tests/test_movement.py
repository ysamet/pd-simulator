"""Tests for M11b Phase B: agent movement (spec ruling 2/3; DECISIONS #165/#172).

Groups, in the order the phase's contract is stated:

* the **rule and the walk** — the ABC contract, destinations within reach,
  the decay weighting honoured EXACTLY (the probability vector handed to
  the draw is ∝ exp(−β·d)), and a blocked mover returning ``None`` without
  a single generator call;
* the **occupancy semantics** — the origin is never a candidate, the origin
  is vacated only after the destination is drawn, an earlier-permuted
  mover's freed origin IS available to a later one (a manufactured chain at
  a pinned seed, with its counterfactual sibling seed), and one attempt per
  agent per period;
* the **order contract** — synchronous coins in ascending id (a scripted
  coin sequence makes the order observable), and the iteration following
  the MOVER permutation alone: id order, the contract's permutation over
  the id-ordered movers, and the #107-style trap (a permutation over the
  whole population filtered to the movers) all pairwise different at a
  pinned seed;
* **newborn eligibility** — a same-boundary newborn moves at a pinned seed;
* the **counting-wrapper no-draw pins**, both clocks — rate 0 consumes zero
  movement draws on lattice-economy configs; rate > 0 on a gated-off
  config (well-mixed economy, ``fixed_n``, sync imitation) leaves the call
  log byte-identical to rate 0; a blocked mover consumes its coin but no
  destination draw; and the positive controls proving the wrapper sees the
  draws at all;
* the **blocked-moves channel** — gate-off zero, the async clock populating
  per recording window, and the readout's visibility gate.

Everything here is NEW (nothing retired): the phase's golden budget is
zero re-recordings, so every pre-existing pin stays as it was and the two
movement-on goldens land in ``test_golden_masters.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest

from pdsim.config.experiment import ExperimentConfig
from pdsim.core import engine
from pdsim.core import movement as movement_module
from pdsim.core.async_dynamics import AsyncDynamics
from pdsim.core.dynamics import EconomyDynamics, PopulationDynamics
from pdsim.core.events import GenerationFinished
from pdsim.core.movement import (
    KernelWalk,
    MovementRule,
    attempt_move,
    build_movement_rule,
    movement_active,
)
from pdsim.core.occupancy import Occupancy
from pdsim.core.structure import LatticeStructure, sites_within
from pdsim.tests.counting_rng import CountingGenerator
from pdsim.ui import economy_helpers

AC = "always_cooperate"
AD = "always_defect"
TFT = "tit_for_tat"


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _torus(rows: int, cols: int, shape: str = "moore") -> LatticeStructure:
    """Build a small torus for the direct rule tests.

    Args:
        rows: Row count.
        cols: Column count.
        shape: ``"moore"`` or ``"von_neumann"``.

    Returns:
        The lattice.
    """
    return LatticeStructure(rows=rows, cols=cols, neighbourhood_shape=shape, boundary="torus")


def _line(length: int) -> LatticeStructure:
    """Build a bounded 1 × ``length`` line — the contention fixtures' geometry.

    On a bounded line every interior site has exactly two neighbours and the
    ends one, so "the last empty site in reach" is easy to manufacture.

    Args:
        length: Number of sites.

    Returns:
        The lattice (Moore and von Neumann coincide on a line).
    """
    return LatticeStructure(rows=1, cols=length, neighbourhood_shape="moore", boundary="bounded")


def _sync_lattice_config(**overrides: object) -> ExperimentConfig:
    """A synchronous lattice economy with movement knobs from ``overrides``.

    Deterministic strategies, fixed match length, no noise, no mutation, no
    age mortality, round-robin pairing — so the ONLY ``rng.random()`` calls
    a run makes are movement coins, and the only ``permutation`` calls are
    the contest permutation (one per boundary) plus, when active, the mover
    permutation. That is what makes the no-draw pins exact rather than
    inferential.

    Args:
        **overrides: ``movement`` (a dict), ``dynamics`` extras, ``rows``,
            ``cols``, ``size``, ``composition``, ``kind``, ``time_model``,
            ``async_population``, ``reproduction_mode``, ``seed``.

    Returns:
        A validated config.
    """
    kind = overrides.pop("kind", "lattice")
    rows = overrides.pop("rows", 4)
    cols = overrides.pop("cols", 4)
    size = overrides.pop("size", 4)
    composition = overrides.pop("composition", {AC: 2, AD: 2})
    dynamics: dict[str, object] = {
        "generations": 3,
        "reproduction_mode": overrides.pop("reproduction_mode", "energy_economy"),
        "time_model": overrides.pop("time_model", "synchronous"),
        "mutation_rate": 0.0,
        "reproduction_threshold": 10_000.0,  # nobody breeds unless a test says so
        "offspring_stake": 100.0,
        "basic_living_cost": 0.0,
        "carrying_capacity": rows * cols if kind == "lattice" else 200,  # type: ignore[operator]
    }
    if "async_population" in overrides:
        dynamics["async_population"] = overrides.pop("async_population")
    dynamics.update(overrides.pop("dynamics", {}))  # type: ignore[arg-type]
    structure: dict[str, object] = {"kind": kind}
    if kind == "lattice":
        structure.update({"rows": rows, "cols": cols, "initial_layout": "stripes"})
    data: dict[str, object] = {
        "seed": overrides.pop("seed", 3),
        "population": {"size": size, "composition": composition},
        "match": {"length_mode": "fixed", "rounds_per_match": 2},
        "structure": structure,
        "dynamics": dynamics,
    }
    if dynamics["time_model"] == "asynchronous":
        # The async partner draw consumes k directly and validates k <= N - 1;
        # the synchronous fixtures keep round-robin (no matcher draws at all).
        data["matching"] = {"matcher": "random_k", "opponents_per_agent": 2}
    if "movement" in overrides:
        data["movement"] = overrides.pop("movement")
    assert not overrides, f"unused overrides: {overrides}"
    return ExperimentConfig.model_validate(data)


def _count_run(config: ExperimentConfig) -> CountingGenerator:
    """Run a config to completion on a counting generator (both clocks).

    Args:
        config: Any evolution-mode config with a deterministic layout.

    Returns:
        The wrapper, its call log covering the whole run.
    """
    counted = CountingGenerator(np.random.default_rng(config.seed))
    dynamics: PopulationDynamics | EconomyDynamics | AsyncDynamics
    if config.dynamics.time_model == "asynchronous":
        dynamics = AsyncDynamics(config, counted)  # type: ignore[arg-type]
    elif config.dynamics.reproduction_mode == "energy_economy":
        dynamics = EconomyDynamics(config, counted)  # type: ignore[arg-type]
    else:
        dynamics = PopulationDynamics(config, counted)  # type: ignore[arg-type]
    for _ in dynamics.run():
        pass
    return counted


class _RecordingRng:
    """A minimal generator double that records the ``choice`` call's inputs.

    Used for the EXACT weight assertion: the walk hands
    ``neighbourhood_sample`` a probability vector, and this double captures
    it verbatim (the counting wrapper summarises arrays away). ``choice``
    returns the FIRST pool member so the call completes.
    """

    def __init__(self) -> None:
        """Start with an empty record."""
        self.pool: list[int] | None = None
        self.p: np.ndarray | None = None

    def choice(self, pool: list[int], size: int, replace: bool, p: np.ndarray | None) -> list[int]:
        """Record the draw's inputs and return the first candidate.

        Args:
            pool: The drawable candidates.
            size: Requested count.
            replace: Ignored (recorded draws are without replacement).
            p: The probability vector, or ``None`` for uniform.

        Returns:
            The first ``size`` pool members.
        """
        self.pool = list(pool)
        self.p = None if p is None else np.array(p)
        return list(pool[:size])


class _ScriptedCoinRng:
    """A hybrid double: scripted ``random()`` coins, everything else real.

    Makes the coin ORDER observable — the scripted sequence is consumed in
    call order, so which agents become movers reveals the order the engine
    drew their coins in — while the permutation and the walk draws still
    come from a real generator at a pinned seed.
    """

    def __init__(self, coins: list[float], seed: int) -> None:
        """Set the coin script and the real generator behind it.

        Args:
            coins: The values ``random()`` returns, in call order.
            seed: Seed of the real generator serving every other call.
        """
        self._coins = list(coins)
        self._real = np.random.default_rng(seed)
        self.coins_drawn = 0

    def random(self) -> float:
        """Return the next scripted coin.

        Returns:
            The next value of the script.
        """
        value = self._coins[self.coins_drawn]
        self.coins_drawn += 1
        return value

    def __getattr__(self, name: str) -> object:
        """Forward everything else to the real generator.

        Args:
            name: The attribute (``permutation``, ``choice``, ...).

        Returns:
            The real generator's attribute.
        """
        return getattr(self._real, name)


def _place(occupancy: Occupancy, placements: dict[int, int]) -> None:
    """Rearrange an occupancy to exactly ``placements`` (agent → site).

    Args:
        occupancy: The live occupancy to rewrite.
        placements: The desired agent → site mapping.
    """
    for agent_id in list(occupancy.sites_by_agent()):
        occupancy.remove_agent(agent_id)
    for agent_id, site_id in placements.items():
        occupancy.occupy(site_id, agent_id)


def _record_attempts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int, bool]]:
    """Wrap the engines' ``attempt_move`` to log ``(agent_id, origin, moved)``.

    Both engines import the name into their own namespace, so both bindings
    are patched. The wrapper delegates to the real function — nothing about
    the run changes; it only becomes observable.

    Args:
        monkeypatch: pytest's patcher.

    Returns:
        The log, appended to as the run proceeds.
    """
    log: list[tuple[int, int, bool]] = []
    real = movement_module.attempt_move

    def recording(rule: MovementRule, agent_id: int, occupancy: Occupancy, rng: object) -> bool:
        origin = occupancy.site_of(agent_id)
        assert origin is not None
        moved = real(rule, agent_id, occupancy, rng)  # type: ignore[arg-type]
        log.append((agent_id, origin, moved))
        return moved

    import pdsim.core.async_dynamics as async_module
    import pdsim.core.dynamics as sync_module

    monkeypatch.setattr(sync_module, "attempt_move", recording)
    monkeypatch.setattr(async_module, "attempt_move", recording)
    return log


# ---------------------------------------------------------------------------
# The rule and the walk
# ---------------------------------------------------------------------------


class TestMovementRule:
    """The ABC contract and the kernel walk's basic behaviour."""

    def test_the_abc_cannot_be_instantiated_and_the_walk_is_a_rule(self) -> None:
        """#46's convention: an abstract base with one shipped implementation."""
        with pytest.raises(TypeError):
            MovementRule()  # type: ignore[abstract]
        walk = KernelWalk(radius=1, decay=0.0)
        assert isinstance(walk, MovementRule)
        assert walk.radius == 1
        assert walk.decay == 0.0

    def test_bad_parameters_fail_at_construction(self) -> None:
        """A negative radius or decay is a bug, caught before any run."""
        with pytest.raises(ValueError, match="radius"):
            KernelWalk(radius=-1, decay=0.0)
        with pytest.raises(ValueError, match="decay"):
            KernelWalk(radius=1, decay=-0.5)

    def test_build_from_config_reads_the_movement_section(self) -> None:
        """The builder hands the config's radius/decay pair to the walk."""
        config = _sync_lattice_config(movement={"rate": 0.5, "radius": 3, "decay": 1.5})
        rule = build_movement_rule(config)
        assert isinstance(rule, KernelWalk)
        assert rule.radius == 3
        assert rule.decay == 1.5

    def test_destination_is_within_reach_and_empty(self) -> None:
        """Every drawn destination lies within the radius and is empty."""
        structure = _torus(5, 5)
        occupancy = Occupancy(structure)
        # A few occupants scattered so some neighbours are taken.
        for agent_id, site_id in enumerate((0, 6, 7, 12, 18)):
            occupancy.occupy(site_id, agent_id)
        walk = KernelWalk(radius=1, decay=0.0)
        rng = np.random.default_rng(1)
        for _ in range(200):
            origin = 12  # agent 3 sits here
            destination = walk.destination(origin, occupancy, rng)
            assert destination is not None
            assert destination in sites_within(structure, origin, 1)
            assert not occupancy.is_occupied(destination)

    def test_decay_weighting_is_exactly_exp_minus_beta_d(self) -> None:
        """The probability vector handed to the draw is ∝ exp(−β·d) — exact."""
        structure = _torus(7, 7)
        occupancy = Occupancy(structure)
        origin = 24  # the centre of a 7x7 grid
        occupancy.occupy(origin, 0)
        beta = 1.3
        walk = KernelWalk(radius=2, decay=beta)
        double = _RecordingRng()
        destination = walk.destination(origin, occupancy, double)  # type: ignore[arg-type]
        assert destination is not None
        assert double.pool is not None and double.p is not None
        # Every candidate within radius 2 (24 sites on a Moore disc) is
        # empty, so the pool is the full reach in ascending id order.
        assert double.pool == list(sites_within(structure, origin, 2))
        distances = np.array([structure.distance(origin, s) for s in double.pool], dtype=float)
        expected = np.exp(-beta * distances)
        expected = expected / expected.sum()
        assert np.allclose(double.p, expected)
        # And distance 1 genuinely outweighs distance 2 by exp(β) per site.
        p_by_d = {d: double.p[distances == d][0] for d in (1.0, 2.0)}
        assert p_by_d[1.0] / p_by_d[2.0] == pytest.approx(np.exp(beta))

    def test_decay_zero_is_uniform_over_the_reachable_empties(self) -> None:
        """β = 0: every empty site within reach equally likely (a uniform disc)."""
        structure = _torus(7, 7)
        occupancy = Occupancy(structure)
        occupancy.occupy(24, 0)
        double = _RecordingRng()
        KernelWalk(radius=2, decay=0.0).destination(24, occupancy, double)  # type: ignore[arg-type]
        assert double.p is not None
        assert np.allclose(double.p, np.full(len(double.p), 1.0 / len(double.p)))

    def test_a_blocked_mover_returns_none_without_drawing(self) -> None:
        """No empty site in reach: ``None``, and NOT ONE generator call."""
        structure = _torus(3, 3)
        occupancy = Occupancy(structure)
        for site_id in range(9):  # a full grid walls everyone in
            occupancy.occupy(site_id, site_id)
        counted = CountingGenerator(np.random.default_rng(0))
        walk = KernelWalk(radius=1, decay=0.0)
        assert walk.destination(4, occupancy, counted) is None  # type: ignore[arg-type]
        assert counted.calls == []
        # Unlimited radius changes nothing on a full grid.
        assert KernelWalk(radius=None, decay=0.0).destination(4, occupancy, counted) is None  # type: ignore[arg-type]
        assert counted.calls == []


# ---------------------------------------------------------------------------
# Occupancy semantics
# ---------------------------------------------------------------------------


class TestOccupancySemantics:
    """A move is a relocation: origin never offered, vacated after the draw."""

    def test_the_origin_is_never_a_candidate(self) -> None:
        """All other sites occupied → blocked, even at unlimited radius."""
        structure = _torus(2, 2)
        occupancy = Occupancy(structure)
        for site_id in range(4):
            occupancy.occupy(site_id, site_id)
        # Free nothing: the mover's own site is the only "empty-looking"
        # site from its own point of view, and it must not be offered.
        walk = KernelWalk(radius=None, decay=0.0)
        assert walk.destination(0, occupancy, np.random.default_rng(0)) is None
        assert attempt_move(walk, 0, occupancy, np.random.default_rng(0)) is False
        assert occupancy.site_of(0) == 0

    def test_a_successful_move_vacates_the_origin_after_the_draw(self) -> None:
        """Origin empty, destination occupied by the mover, mapping updated."""
        structure = _line(3)
        occupancy = Occupancy(structure)
        occupancy.occupy(0, 7)
        walk = KernelWalk(radius=1, decay=0.0)
        moved = attempt_move(walk, 7, occupancy, np.random.default_rng(0))
        assert moved is True
        assert occupancy.site_of(7) == 1
        assert not occupancy.is_occupied(0)
        assert occupancy.agent_at(1) == 7
        assert len(occupancy) == 1

    def test_attempt_move_on_an_unplaced_agent_is_a_programming_error(self) -> None:
        """Every living agent on a lattice holds a site; a missing one raises."""
        occupancy = Occupancy(_line(3))
        with pytest.raises(KeyError):
            attempt_move(KernelWalk(1, 0.0), 99, occupancy, np.random.default_rng(0))

    def test_an_earlier_movers_origin_is_available_to_a_later_mover(self) -> None:
        """The chain, directly: B (at 1) moves to 2, then A (at 0) takes B's origin."""
        occupancy = Occupancy(_line(3))
        occupancy.occupy(0, 0)  # A
        occupancy.occupy(1, 1)  # B
        walk = KernelWalk(radius=1, decay=0.0)
        rng = np.random.default_rng(0)
        assert attempt_move(walk, 1, occupancy, rng) is True  # B → 2 (its only option)
        assert occupancy.site_of(1) == 2
        assert attempt_move(walk, 0, occupancy, rng) is True  # A → 1 (freed by B)
        assert occupancy.site_of(0) == 1

    def _chain_dynamics(self, seed: int) -> EconomyDynamics:
        """A 1 × 3 bounded line: A at 0, B at 1, site 2 empty; rate 1.0.

        Args:
            seed: The generator seed the movement phase runs under.

        Returns:
            The prepared dynamics.
        """
        config = _sync_lattice_config(
            rows=1,
            cols=3,
            size=2,
            composition={AC: 1, AD: 1},
            movement={"rate": 1.0, "radius": 1, "decay": 0.0},
        )
        # A bounded line: torus wrap would make 0 and 2 neighbours.
        data = config.model_dump()
        data["structure"]["boundary"] = "bounded"
        config = ExperimentConfig.model_validate(data)
        dynamics = EconomyDynamics(config, np.random.default_rng(seed))
        assert dynamics.occupancy is not None
        _place(dynamics.occupancy, {0: 0, 1: 1})
        dynamics._rng = np.random.default_rng(seed)
        return dynamics

    def test_the_manufactured_chain_forms_at_the_pinned_seed(self) -> None:
        """Seed 0: the mover permutation is [B, A] → B to 2, A to 1 — a chain."""
        dynamics = self._chain_dynamics(seed=0)
        # Pin the permutation the fixture relies on (two coins first).
        probe = np.random.default_rng(0)
        probe.random()
        probe.random()
        assert list(probe.permutation(2)) == [1, 0]
        dynamics._movement_phase(list(dynamics.population))
        assert dynamics.occupancy is not None
        assert dynamics.occupancy.site_of(1) == 2
        assert dynamics.occupancy.site_of(0) == 1
        assert dynamics._blocked_moves == 0

    def test_the_counterfactual_seed_blocks_a_instead(self) -> None:
        """Seed 1: permutation [A, B] → A blocked (1 taken), then B to 2."""
        dynamics = self._chain_dynamics(seed=1)
        probe = np.random.default_rng(1)
        probe.random()
        probe.random()
        assert list(probe.permutation(2)) == [0, 1]
        dynamics._movement_phase(list(dynamics.population))
        assert dynamics.occupancy is not None
        assert dynamics.occupancy.site_of(0) == 0  # stayed — blocked
        assert dynamics.occupancy.site_of(1) == 2
        assert dynamics._blocked_moves == 1

    def test_one_attempt_per_agent_per_period(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """At rate 1.0 every agent is attempted exactly once per boundary."""
        log = _record_attempts(monkeypatch)
        config = _sync_lattice_config(
            rows=4,
            cols=4,
            size=6,
            composition={AC: 3, AD: 3},
            movement={"rate": 1.0, "radius": None, "decay": 0.0},
        )
        dynamics = EconomyDynamics(config, np.random.default_rng(config.seed))
        for _ in range(3):
            log.clear()
            dynamics.step()
            attempted = sorted(agent_id for agent_id, _, _ in log)
            assert attempted == sorted(agent.agent_id for agent in dynamics.population)


# ---------------------------------------------------------------------------
# The order contract
# ---------------------------------------------------------------------------


class TestOrderContract:
    """Coins in ascending id; iteration follows the mover permutation alone."""

    def test_sync_coins_are_drawn_in_ascending_id_order(self) -> None:
        """A scripted coin sequence [miss, hit, miss, hit] makes movers {1, 3}.

        Had the coins been drawn in any other order — descending, or
        list-position after a reshuffle — a different subset would move.
        """
        config = _sync_lattice_config(
            rows=4,
            cols=4,
            size=4,
            composition={AC: 2, AD: 2},
            movement={"rate": 0.5, "radius": None, "decay": 0.0},
        )
        dynamics = EconomyDynamics(config, np.random.default_rng(config.seed))
        assert dynamics.occupancy is not None
        _place(dynamics.occupancy, {0: 0, 1: 1, 2: 2, 3: 3})
        rng = _ScriptedCoinRng(coins=[0.9, 0.1, 0.9, 0.1], seed=5)
        dynamics._rng = rng  # type: ignore[assignment]
        dynamics._movement_phase(list(dynamics.population))
        assert rng.coins_drawn == 4
        sites = dynamics.occupancy.sites_by_agent()
        assert sites[0] == 0 and sites[2] == 2  # coin misses stayed
        assert sites[1] != 1 and sites[3] != 3  # coin hits moved

    def _order_fixture(self, monkeypatch: pytest.MonkeyPatch) -> tuple[list[int], list[int]]:
        """Run one movement phase with movers {0, 1, 2} of {0, 1, 2, 3} at seed 9.

        Args:
            monkeypatch: pytest's patcher (records the iteration).

        Returns:
            ``(observed_iteration, movers_in_id_order)``.
        """
        log = _record_attempts(monkeypatch)
        config = _sync_lattice_config(
            rows=1,
            cols=5,
            size=4,
            composition={AC: 2, AD: 2},
            movement={"rate": 0.5, "radius": 1, "decay": 0.0},
        )
        dynamics = EconomyDynamics(config, np.random.default_rng(config.seed))
        assert dynamics.occupancy is not None
        _place(dynamics.occupancy, {0: 0, 1: 2, 2: 3, 3: 4})
        # Coins: hit, hit, hit, miss → movers [0, 1, 2] in id order.
        dynamics._rng = _ScriptedCoinRng(coins=[0.1, 0.1, 0.1, 0.9], seed=9)  # type: ignore[assignment]
        dynamics._movement_phase(list(dynamics.population))
        return [agent_id for agent_id, _, _ in log], [0, 1, 2]

    def test_iteration_follows_the_mover_permutation_alone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Three orders, pairwise different at seed 9; the engine follows the second.

        (1) id order over the movers — what a naive loop would do;
        (2) THE CONTRACT: one permutation over the id-ordered movers;
        (3) the #107-style trap: a permutation over the WHOLE population's
            ids, filtered to the movers (a different size, hence a
            different draw and a different order).
        """
        observed, id_order = self._order_fixture(monkeypatch)
        contract = [id_order[int(i)] for i in np.random.default_rng(9).permutation(3)]
        trap = [int(i) for i in np.random.default_rng(9).permutation(4) if int(i) in id_order]
        assert contract != id_order
        assert trap != id_order
        assert contract != trap
        assert contract == [2, 0, 1]  # the pinned seed-9 order, for the record
        assert observed == contract


# ---------------------------------------------------------------------------
# Newborn eligibility
# ---------------------------------------------------------------------------


class TestNewbornEligibility:
    """A child born in this boundary may move in it (#165: one uniform rule)."""

    def test_a_same_boundary_newborn_moves_at_the_pinned_seed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rate 1.0, unlimited radius: the newborn is attempted and relocates."""
        log = _record_attempts(monkeypatch)
        config = _sync_lattice_config(
            rows=4,
            cols=4,
            size=2,
            composition={AC: 1, AD: 1},
            dynamics={"reproduction_threshold": 50.0, "offspring_stake": 10.0},
            movement={"rate": 1.0, "radius": None, "decay": 0.0},
        )
        dynamics = EconomyDynamics(config, np.random.default_rng(config.seed))
        for agent in dynamics.population:
            agent.energy = 1000.0  # both breed at the first boundary
        first_child = dynamics._next_id
        dynamics.step()
        newborn_ids = [
            agent.agent_id for agent in dynamics.population if agent.agent_id >= first_child
        ]
        assert newborn_ids, "the fixture must actually breed"
        attempted = {agent_id: (origin, moved) for agent_id, origin, moved in log}
        for child in newborn_ids:
            assert child in attempted, "a newborn must be coin-eligible in its birth boundary"
            origin, moved = attempted[child]
            assert moved is True  # unlimited radius on a 14-empty grid never blocks
            assert dynamics.occupancy is not None
            assert dynamics.occupancy.site_of(child) != origin


# ---------------------------------------------------------------------------
# The gate and the no-draw pins (counting wrapper, both clocks)
# ---------------------------------------------------------------------------


class TestMovementGate:
    """``movement_active`` is the one predicate both engines and the app read."""

    def test_the_gate_truth_table(self) -> None:
        """Lattice + energy economy + rate > 0; fixed_n, imitation, well-mixed off."""
        on = {"rate": 0.5, "radius": 1, "decay": 0.0}
        assert movement_active(_sync_lattice_config(movement=on))
        assert movement_active(
            _sync_lattice_config(
                movement=on, time_model="asynchronous", async_population="variable_n"
            )
        )
        assert not movement_active(_sync_lattice_config())  # rate 0
        assert not movement_active(_sync_lattice_config(movement=on, kind="well_mixed"))
        assert not movement_active(
            _sync_lattice_config(
                movement=on, reproduction_mode="imitation", dynamics={"mutation_rate": 0.1}
            )
        )
        fixed = ExperimentConfig.model_validate(
            {
                "seed": 5,
                "population": {"size": 9, "composition": {TFT: 5, AD: 4}},
                "matching": {"matcher": "random_k", "opponents_per_agent": 2},
                "match": {"length_mode": "fixed", "rounds_per_match": 3},
                "structure": {"kind": "lattice", "rows": 3, "cols": 3, "initial_layout": "stripes"},
                "movement": on,
                "dynamics": {
                    "generations": 3,
                    "time_model": "asynchronous",
                    "async_population": "fixed_n",
                    "mutation_rate": 0.0,
                },
            }
        )
        assert not movement_active(fixed)
        tournament = ExperimentConfig.model_validate(
            {**_sync_lattice_config(movement=on).model_dump(), "mode": "tournament"}
        )
        assert not movement_active(tournament)


class TestNoDrawPins:
    """Zero movement draws wherever movement is off or not gated on."""

    def test_rate_zero_consumes_no_movement_draws_on_the_sync_lattice_economy(self) -> None:
        """No coins (zero ``random`` calls) and only the contest permutation."""
        config = _sync_lattice_config()
        counted = _count_run(config)
        assert counted.count("random") == 0
        assert counted.count("permutation") == config.dynamics.generations
        assert counted.count("choice") == 0

    def test_rate_zero_consumes_no_movement_draws_on_the_async_lattice_economy(self) -> None:
        """No coins at all: the async variable_n lattice draws no ``random``."""
        config = _sync_lattice_config(time_model="asynchronous", async_population="variable_n")
        counted = _count_run(config)
        assert counted.count("random") == 0

    @pytest.mark.parametrize(
        "name",
        ["well_mixed_economy", "async_fixed_n_lattice", "sync_imitation_lattice"],
    )
    def test_rate_above_zero_on_a_gated_off_config_leaves_the_call_log_identical(
        self, name: str
    ) -> None:
        """The whole call log at rate 0.5 equals the log at rate 0, call for call."""
        on = {"rate": 0.5, "radius": 1, "decay": 0.0}
        if name == "well_mixed_economy":
            off = _sync_lattice_config(
                kind="well_mixed", dynamics={"base_hazard": 0.1, "max_age": 5}
            )
            with_rate = _sync_lattice_config(
                kind="well_mixed", dynamics={"base_hazard": 0.1, "max_age": 5}, movement=on
            )
        elif name == "sync_imitation_lattice":
            off = _sync_lattice_config(
                reproduction_mode="imitation", dynamics={"mutation_rate": 0.1}
            )
            with_rate = _sync_lattice_config(
                reproduction_mode="imitation", dynamics={"mutation_rate": 0.1}, movement=on
            )
        else:
            base = {
                "seed": 5,
                "population": {"size": 9, "composition": {TFT: 5, AD: 4}},
                "matching": {"matcher": "random_k", "opponents_per_agent": 2},
                "match": {"length_mode": "fixed", "rounds_per_match": 3},
                "structure": {"kind": "lattice", "rows": 3, "cols": 3, "initial_layout": "stripes"},
                "dynamics": {
                    "generations": 3,
                    "time_model": "asynchronous",
                    "async_population": "fixed_n",
                    "moran_rule": "random",
                    "fixed_n_death_rule": "pure_random",
                    "mutation_rate": 0.05,
                },
            }
            off = ExperimentConfig.model_validate(base)
            with_rate = ExperimentConfig.model_validate({**base, "movement": on})
        assert _count_run(off).calls == _count_run(with_rate).calls
        assert _count_run(off).calls  # the log is not trivially empty

    def test_positive_control_sync_coins_and_mover_permutation(self) -> None:
        """The wrapper CAN see the draws: a coin per post-boundary agent, an extra permutation."""
        config = _sync_lattice_config(movement={"rate": 0.5, "radius": None, "decay": 0.0})
        counted = _count_run(config)
        # 4 agents, no births/deaths → 4 coins per boundary, 3 boundaries.
        assert counted.count("random") == 4 * config.dynamics.generations
        # Contest permutation + mover permutation, each once per boundary.
        assert counted.count("permutation") == 2 * config.dynamics.generations

    def test_positive_control_async_one_coin_per_activation(self) -> None:
        """One coin per event with N ≥ 2 — never more, never a permutation."""
        config = _sync_lattice_config(
            time_model="asynchronous",
            async_population="variable_n",
            movement={"rate": 0.5, "radius": None, "decay": 0.0},
        )
        counted = _count_run(config)
        # 4 agents, 3 generation-equivalents at Δt = 1/4 → 12 events, N ≥ 2 throughout.
        assert counted.count("random") == 12
        assert counted.count("permutation") == 0

    def test_a_blocked_mover_consumes_its_coin_but_no_destination_draw(self) -> None:
        """A full 3 × 3 grid at rate 1.0: nine coins per boundary, zero ``choice`` calls."""
        config = _sync_lattice_config(
            rows=3,
            cols=3,
            size=9,
            composition={AC: 5, AD: 4},
            movement={"rate": 1.0, "radius": 1, "decay": 0.0},
        )
        counted = _count_run(config)
        assert counted.count("random") == 9 * config.dynamics.generations
        assert counted.count("choice") == 0
        assert counted.count("permutation") == 2 * config.dynamics.generations
        reports = list(EconomyDynamics(config, np.random.default_rng(config.seed)).run())
        assert [report.blocked_moves for report in reports] == [9, 9, 9]

    def test_the_movement_step_at_zero_population_draws_nothing(self) -> None:
        """No living agent → no coin, no permutation (a post-extinction boundary)."""
        config = _sync_lattice_config(movement={"rate": 1.0, "radius": 1, "decay": 0.0})
        dynamics = EconomyDynamics(config, np.random.default_rng(config.seed))
        counted = CountingGenerator(np.random.default_rng(0))
        dynamics._rng = counted  # type: ignore[assignment]
        dynamics._movement_phase([])
        assert counted.calls == []


# ---------------------------------------------------------------------------
# The blocked-moves channel
# ---------------------------------------------------------------------------


class TestBlockedMovesChannel:
    """``blocked_moves`` reaches the stream, gate-off zero, async per window."""

    def test_gate_off_streams_report_zero(self) -> None:
        """Well-mixed economy and sync imitation at rate 0.5: every period 0."""
        on = {"rate": 0.5, "radius": 1, "decay": 0.0}
        for config in (
            _sync_lattice_config(kind="well_mixed", movement=on),
            _sync_lattice_config(
                reproduction_mode="imitation", dynamics={"mutation_rate": 0.1}, movement=on
            ),
        ):
            finished = [e for e in engine.run(config) if isinstance(e, GenerationFinished)]
            assert finished
            assert all(e.blocked_moves == 0 for e in finished)

    def test_rate_zero_on_a_lattice_economy_streams_zero(self) -> None:
        """Movement off: the field exists, default-valued, always 0."""
        finished = [
            e for e in engine.run(_sync_lattice_config()) if isinstance(e, GenerationFinished)
        ]
        assert all(e.blocked_moves == 0 for e in finished)

    def test_the_sync_count_reaches_the_event_stream(self) -> None:
        """The full-grid fixture's nine blocked moves per generation, on the stream."""
        config = _sync_lattice_config(
            rows=3,
            cols=3,
            size=9,
            composition={AC: 5, AD: 4},
            movement={"rate": 1.0, "radius": 1, "decay": 0.0},
        )
        finished = [e for e in engine.run(config) if isinstance(e, GenerationFinished)]
        assert [e.blocked_moves for e in finished] == [9, 9, 9]

    def test_the_async_clock_populates_per_recording_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Window totals equal the blocked attempts observed, and reset per window."""
        log = _record_attempts(monkeypatch)
        # 3 x 3 VON NEUMANN torus, 8 agents, one empty site: only the four
        # agents adjacent to the hole can move; the other four are blocked.
        config = _sync_lattice_config(
            rows=3,
            cols=3,
            size=8,
            composition={AC: 4, AD: 4},
            time_model="asynchronous",
            async_population="variable_n",
            movement={"rate": 1.0, "radius": 1, "decay": 0.0},
        )
        data = config.model_dump()
        data["structure"]["neighbourhood_shape"] = "von_neumann"
        config = ExperimentConfig.model_validate(data)
        reports = list(AsyncDynamics(config, np.random.default_rng(config.seed)).run())
        blocked_total = sum(1 for _, _, moved in log if not moved)
        assert blocked_total > 0
        assert sum(report.blocked_moves for report in reports) == blocked_total
        assert len(reports) == 3  # one per generation-equivalent
        assert any(report.blocked_moves > 0 for report in reports)

    def test_the_readout_visibility_gate(self) -> None:
        """Shown exactly where movement is active — the engine gate, verbatim."""
        on = {"rate": 0.5, "radius": 1, "decay": 0.0}
        assert economy_helpers.blocked_moves_visible(_sync_lattice_config(movement=on))
        assert economy_helpers.blocked_moves_visible(
            _sync_lattice_config(
                movement=on, time_model="asynchronous", async_population="variable_n"
            )
        )
        assert not economy_helpers.blocked_moves_visible(_sync_lattice_config())
        assert not economy_helpers.blocked_moves_visible(
            _sync_lattice_config(movement=on, kind="well_mixed")
        )
        assert not economy_helpers.blocked_moves_visible(
            _sync_lattice_config(
                movement=on, reproduction_mode="imitation", dynamics={"mutation_rate": 0.1}
            )
        )

    def test_the_metric_shape_and_help_vocabulary(self) -> None:
        """Latest/total like the sibling metrics; no 'infeasible' in movement text."""
        assert economy_helpers.blocked_moves_metric([]) is None
        assert economy_helpers.blocked_moves_metric([0, 2, 1]) == (1, 3)
        text = economy_helpers.ECONOMY_HELP["blocked_moves"]
        assert "BLOCKED MOVE" in text
        assert "infeasible" not in text.lower()

    def test_the_timeseries_mirrors_the_series(self) -> None:
        """``RunTimeseries.blocked_moves`` is aligned with periods, like blocked_parents."""
        from pdsim.core.timeseries import RunTimeseries

        config = _sync_lattice_config(
            rows=3,
            cols=3,
            size=9,
            composition={AC: 5, AD: 4},
            movement={"rate": 1.0, "radius": 1, "decay": 0.0},
        )
        series = RunTimeseries(mode=config.mode)
        for event in engine.run(config):
            series.add(event)
        assert series.blocked_moves == [9, 9, 9]
        assert len(series.blocked_moves) == len(series.periods)


# ---------------------------------------------------------------------------
# Config and registry
# ---------------------------------------------------------------------------


class TestMovementConfig:
    """The movement section: defaults, ranges, hard rule 8, round trip."""

    DEFAULTS: ClassVar[dict[str, object]] = {"rate": 0.0, "radius": 1, "decay": 0.0}

    def test_defaults_are_movement_off(self) -> None:
        """An untouched config has rate 0, radius 1, decay 0."""
        config = _sync_lattice_config()
        assert config.movement.model_dump() == self.DEFAULTS

    def test_an_old_yaml_without_a_movement_section_loads(self, tmp_path: Path) -> None:
        """Hard rule 8: a pre-M11b file has no `movement:` key and re-runs identically."""
        from pdsim.config.experiment import load_config, save_config

        config = _sync_lattice_config()
        path = save_config(config, tmp_path / "old.yaml")
        text = path.read_text(encoding="utf-8")
        assert "movement:" in text
        stripped = "\n".join(
            line
            for line in text.splitlines()
            if not line.startswith("movement:")
            and not line.startswith(("  rate:", "  radius:", "  decay:"))
        )
        (tmp_path / "older.yaml").write_text(stripped, encoding="utf-8")
        reloaded = load_config(tmp_path / "older.yaml")
        assert reloaded.movement.model_dump() == self.DEFAULTS
        assert reloaded == config

    def test_ranges_are_enforced_from_the_registry(self) -> None:
        """Rate above 1, radius 0, negative decay: all rejected."""
        from pydantic import ValidationError

        for bad in (
            {"rate": 1.5, "radius": 1, "decay": 0.0},
            {"rate": 0.5, "radius": 0, "decay": 0.0},
            {"rate": 0.5, "radius": 1, "decay": -1.0},
        ):
            with pytest.raises(ValidationError):
                _sync_lattice_config(movement=bad)

    def test_a_blank_radius_means_unlimited(self) -> None:
        """The nullable shape of the birth radius, verbatim."""
        config = _sync_lattice_config(movement={"rate": 0.5, "radius": None, "decay": 0.0})
        assert config.movement.radius is None
        assert build_movement_rule(config).radius is None  # type: ignore[attr-defined]

    def test_the_registry_section_renders_after_structure(self) -> None:
        """Registry/panel/docs order: Structure, then Movement, then Dynamics."""
        from pdsim.config.registry import all_specs

        sections: list[str] = []
        for spec in all_specs():
            if spec.section not in sections:
                sections.append(spec.section)
        assert sections.index("Structure") < sections.index("Movement") < sections.index("Dynamics")
        keys = [spec.key for spec in all_specs() if spec.section == "Movement"]
        assert keys == ["movement.rate", "movement.radius", "movement.decay"]

    def test_movement_text_never_says_infeasible(self) -> None:
        """The vocabulary rule: the birth split's word stays out of movement text."""
        from pdsim.config.registry import all_specs

        for spec in all_specs():
            if spec.key.startswith("movement."):
                assert "infeasible" not in spec.description.lower(), spec.key

    def test_widget_values_round_trip_the_movement_section(self) -> None:
        """Config → widget values → config keeps the movement knobs."""
        from pdsim.ui import helpers

        original = _sync_lattice_config(movement={"rate": 0.3, "radius": 2, "decay": 0.7})
        values = helpers.widget_values_from_config(original)
        assert values["movement.rate"] == 0.3
        assert values["movement.radius"] == 2
        assert values["movement.decay"] == 0.7
        rebuilt = helpers.build_config(
            values, original.population.composition, original.strategy_params
        )
        assert rebuilt == original
