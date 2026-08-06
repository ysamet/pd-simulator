"""Tests for M11a Phase C: local birth (spec Designs 4, 5, 7, 9).

Written in the spec's mandated order — the traps BEFORE the code they
guard. The three groups written first (and briefly red until the engine
lands) are:

* the **counting-wrapper no-draw pins** — the testable image of Design 5's
  confinement argument: contention exists ONLY under synchronous + lattice
  + ``energy_economy``, and no test can observe "contention cannot arise
  here" directly — only that zero contest draws were consumed;
* the **three-orderings fixture** — admission order (energy desc, id asc),
  iteration order (parent-id asc), and the contest permutation must never
  collapse into each other. The named bug this pins against: applying the
  permutation to a list that has ALREADY been energy-sorted, which turns a
  ``random`` contest quietly energy-biased in exactly the way #107
  rejected. The fixture makes all three orders differ pairwise and asserts
  that disagreement inside itself, so it cannot silently degenerate;
* the **positive control** — one permutation call per generation whenever
  the three-way gate holds, proving the wrapper can see the draw at all.

The rest of the module accompanies the Phase C implementation: occupancy
going live (death frees a site, birth occupies one, a newborn's site is
real from birth), the blocked-parent semantics (no stake, stays eligible,
counted), ``boundary_order``, and the async amendments (the ``variable_n``
placement insertion; the localised ``fixed_n`` breeder/victim draws with
the R = 1 Ohtsuki reduction).
"""

from __future__ import annotations

import numpy as np
import pytest

from pdsim.config.experiment import ExperimentConfig
from pdsim.core import engine
from pdsim.core.async_dynamics import AsyncDynamics
from pdsim.core.dynamics import EconomyDynamics, PopulationDynamics
from pdsim.core.events import GenerationFinished
from pdsim.core.structure import kernel_weights, sites_within
from pdsim.tests.counting_rng import CountingGenerator

AC = "always_cooperate"
AD = "always_defect"
TFT = "tit_for_tat"


# ---------------------------------------------------------------------------
# Config builders
# ---------------------------------------------------------------------------


def _sync_economy_config(kind: str = "lattice", **overrides: object) -> ExperimentConfig:
    """Build the orderings fixture: 5 founders on a sparse 6x6 grid.

    The grid is deliberately larger than the population (36 sites for 5
    agents) with unlimited birth reach, so every admitted parent can place
    and the iteration order is fully visible in the newborns' ids.

    Args:
        kind: ``"lattice"`` or ``"well_mixed"`` (the gate-off control).
        **overrides: Extra ``dynamics`` fields (e.g. ``placement_contest``
            lives under ``structure`` — pass ``structure_overrides``).

    Returns:
        A validated sync economy config, seed 42.
    """
    structure: dict[str, object] = {"kind": kind}
    if kind == "lattice":
        structure.update({"rows": 6, "cols": 6, "initial_layout": "stripes"})
    structure.update(overrides.pop("structure_overrides", {}))  # type: ignore[arg-type]
    dynamics: dict[str, object] = {
        "generations": 3,
        "reproduction_mode": "energy_economy",
        "mutation_rate": 0.0,
        "reproduction_threshold": 500.0,
        "offspring_stake": 100.0,
        "basic_living_cost": 0.0,
        "carrying_capacity": 9,
    }
    dynamics.update(overrides)
    return ExperimentConfig.model_validate(
        {
            "seed": 42,
            "population": {"size": 5, "composition": {AC: 3, AD: 2}},
            "match": {"length_mode": "fixed", "rounds_per_match": 2},
            "structure": structure,
            "dynamics": dynamics,
        }
    )


ORDERING_ENERGIES = {0: 700.0, 1: 900.0, 2: 650.0, 3: 800.0, 4: 1000.0}
"""Hand-set energies for the three-orderings fixture (ids 0-4).

With ``carrying_capacity = 9`` and 5 living agents there are 4 slots, so
admission takes the richest four — ids {0, 1, 3, 4}, dropping id 2 — and
the three orders over that set are:

* admission (energy desc, id asc): ``[4, 1, 3, 0]``
* parent-id ascending:             ``[0, 1, 3, 4]``
* the contest permutation at the fixture's seed 0 — ``[2, 0, 1, 3]`` over
  the id-ordered base — giving ``[3, 0, 1, 4]``.
"""


def _orderings_dynamics(config: ExperimentConfig) -> EconomyDynamics:
    """Build an EconomyDynamics with the fixture energies hand-set.

    Args:
        config: A 5-founder economy config from :func:`_sync_economy_config`.

    Returns:
        The dynamics, its generator repositioned to a fresh seed-0 stream so
        the birth phase's first draw is exactly ``permutation`` under
        ``default_rng(0)``.
    """
    dynamics = EconomyDynamics(config, np.random.default_rng(config.seed))
    for agent in dynamics._population:
        agent.energy = ORDERING_ENERGIES[agent.agent_id]
    dynamics._rng = np.random.default_rng(0)
    return dynamics


def _observed_iteration(dynamics: EconomyDynamics) -> list[int]:
    """Run one birth phase and read the iteration order off the child ids.

    Passport ids are assigned in iteration order (amended #80 step 6), so
    sorting the newborns by id recovers the order their parents were
    processed in.

    Args:
        dynamics: A prepared economy dynamics.

    Returns:
        The parents' ids, in the order they were iterated.
    """
    newborns = dynamics._birth_phase(list(dynamics._population))
    ordered = sorted(newborns, key=lambda agent: agent.agent_id)
    return [agent.parent_id for agent in ordered]


# ---------------------------------------------------------------------------
# The counting wrapper itself
# ---------------------------------------------------------------------------


class TestCountingGenerator:
    """The wrapper must record faithfully and change nothing."""

    def test_calls_are_recorded_and_results_untouched(self) -> None:
        """Wrapped and bare generators at one seed produce identical values."""
        counted = CountingGenerator(np.random.default_rng(9))
        twin = np.random.default_rng(9)
        assert counted.random() == twin.random()
        assert list(counted.permutation(5)) == list(twin.permutation(5))
        assert counted.integers(10) == twin.integers(10)
        assert counted.count("random") == 1
        assert counted.count("permutation") == 1
        assert counted.count("integers") == 1
        assert [name for name, _, _ in counted.calls] == ["random", "permutation", "integers"]

    def test_non_callable_attributes_pass_through(self) -> None:
        """State access works, so stream-position checks stay possible."""
        counted = CountingGenerator(np.random.default_rng(9))
        assert counted.bit_generator.state == np.random.default_rng(9).bit_generator.state


# ---------------------------------------------------------------------------
# The no-draw pins (Design 5's confinement, via its draw-consumption shadow)
# ---------------------------------------------------------------------------


def _count_run(config: ExperimentConfig) -> CountingGenerator:
    """Run a config to completion on a counting generator.

    Args:
        config: Any evolution-mode config. Lattice configs must use a
            DETERMINISTIC layout — the ``random`` layout's founding draw is
            itself a ``permutation`` call and would muddy the count.

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


class TestNoDrawPins:
    """Zero contest-permutation draws anywhere outside sync+lattice+economy."""

    def test_sync_well_mixed_economy_consumes_no_permutation(self) -> None:
        """The gate is off without a lattice — well-mixed streams stay pinned."""
        counted = _count_run(_sync_economy_config(kind="well_mixed"))
        assert counted.count("permutation") == 0

    def test_sync_imitation_with_a_lattice_consumes_no_permutation(self) -> None:
        """Imitation has no births, so there is nothing to contend for."""
        config = ExperimentConfig.model_validate(
            {
                "seed": 5,
                "population": {"size": 9, "composition": {TFT: 5, AD: 4}},
                "match": {"length_mode": "fixed", "rounds_per_match": 2},
                "structure": {"kind": "lattice", "rows": 3, "cols": 3, "initial_layout": "stripes"},
                "dynamics": {"generations": 3, "mutation_rate": 0.1},
            }
        )
        counted = _count_run(config)
        assert counted.count("permutation") == 0

    @pytest.mark.parametrize("async_population", ["variable_n", "fixed_n"])
    def test_async_with_a_lattice_consumes_no_permutation(self, async_population: str) -> None:
        """Async resolves one event at a time: no two births ever contend."""
        dynamics: dict[str, object] = {
            "generations": 3,
            "time_model": "asynchronous",
            "async_population": async_population,
            "mutation_rate": 0.0,
        }
        size = 9 if async_population == "fixed_n" else 8
        composition = {TFT: 5, AD: 4} if async_population == "fixed_n" else {TFT: 4, AD: 4}
        structure: dict[str, object] = {
            "kind": "lattice",
            "rows": 3,
            "cols": 3,
            "initial_layout": "stripes",
        }
        if async_population == "variable_n":
            dynamics.update(
                {
                    "reproduction_threshold": 60.0,
                    "offspring_stake": 50.0,
                    "basic_living_cost": 25.0,
                    "carrying_capacity": 9,
                }
            )
        config = ExperimentConfig.model_validate(
            {
                "seed": 5,
                "population": {"size": size, "composition": composition},
                "matching": {"matcher": "random_k", "opponents_per_agent": 2},
                "match": {"length_mode": "fixed", "rounds_per_match": 3},
                "structure": structure,
                "dynamics": dynamics,
            }
        )
        counted = _count_run(config)
        assert counted.count("permutation") == 0

    def test_positive_control_sync_lattice_economy_draws_one_per_generation(self) -> None:
        """The wrapper CAN see the draw: one permutation per boundary under the gate.

        Without this, every zero above would also pass with a wrapper that
        records nothing.
        """
        config = _sync_economy_config(kind="lattice")
        counted = _count_run(config)
        assert counted.count("permutation") == config.dynamics.generations


# ---------------------------------------------------------------------------
# The three orderings (Design 9; the #107 trap)
# ---------------------------------------------------------------------------


class TestThreeOrderings:
    """Admission, iteration, and the contest permutation never conflate."""

    def _expected_orders(self) -> tuple[list[int], list[int], list[int]]:
        """Compute the three orders over the admitted set, and check they differ.

        Returns:
            ``(energy_order, id_order, permutation_order)`` as parent-id
            lists. Raises through the assertions if the fixture has
            degenerated into agreement anywhere.
        """
        energy_order = [4, 1, 3, 0]
        id_order = [0, 1, 3, 4]
        permutation = list(np.random.default_rng(0).permutation(4))
        permutation_order = [id_order[int(i)] for i in permutation]
        assert energy_order != id_order
        assert permutation_order != energy_order
        assert permutation_order != id_order
        return energy_order, id_order, permutation_order

    def test_random_contest_follows_the_permutation_alone(self) -> None:
        """Under ``placement_contest = random`` the permutation decides.

        The permutation is applied to the ID-ORDERED base (Defining
        principle 5: every list is id-ordered before a draw touches it) —
        NOT to the energy-sorted admission list. Permuting the energy-sorted
        list is the named #107 bug: the same index draw would produce a
        different, quietly energy-anchored order.
        """
        _, _, permutation_order = self._expected_orders()
        dynamics = _orderings_dynamics(_sync_economy_config(kind="lattice"))
        assert _observed_iteration(dynamics) == permutation_order

    def test_energy_priority_iterates_energy_descending(self) -> None:
        """Under ``energy_priority`` the richest places first."""
        energy_order, _, _ = self._expected_orders()
        config = _sync_economy_config(
            kind="lattice", structure_overrides={"placement_contest": "energy_priority"}
        )
        dynamics = _orderings_dynamics(config)
        assert _observed_iteration(dynamics) == energy_order

    def test_gate_off_iterates_parent_id_ascending(self) -> None:
        """Well-mixed: today's #80 contract, untouched."""
        _, id_order, _ = self._expected_orders()
        dynamics = _orderings_dynamics(_sync_economy_config(kind="well_mixed"))
        assert _observed_iteration(dynamics) == id_order

    def test_energy_priority_still_draws_the_permutation(self) -> None:
        """The draw is gated on the THREE-WAY conjunction, not on the contest choice.

        Spec Design 9's inventory gates the insertion on sync + lattice +
        ``energy_economy`` alone, so switching ``placement_contest`` can
        never shift the stream (the #80 active-flag idiom, applied to a
        choice widget).
        """
        config = _sync_economy_config(
            kind="lattice", structure_overrides={"placement_contest": "energy_priority"}
        )
        dynamics = _orderings_dynamics(config)
        counted = CountingGenerator(np.random.default_rng(0))
        dynamics._rng = counted  # type: ignore[assignment]
        dynamics._birth_phase(list(dynamics._population))
        assert counted.count("permutation") == 1


# ---------------------------------------------------------------------------
# Occupancy goes live (Design 4; #120(c)'s gap closed)
# ---------------------------------------------------------------------------


def _stripes_config(**dynamics_overrides: object) -> ExperimentConfig:
    """A 3x3 bounded lattice economy with 8 founders and one empty site.

    Under ``stripes`` with {AC: 4, AD: 4} the deal is deterministic: agents
    0-3 (AC) sit on sites 0-3, agents 4-7 (AD) on sites 4-7, and site 8 —
    the bottom-right corner — is empty. ``bounded`` keeps corner
    neighbourhoods small, which is what the walled-in fixtures need.

    Args:
        **dynamics_overrides: Extra dynamics fields.

    Returns:
        A validated sync economy config, seed 42.
    """
    dynamics: dict[str, object] = {
        "generations": 3,
        "reproduction_mode": "energy_economy",
        "mutation_rate": 0.0,
        "reproduction_threshold": 500.0,
        "offspring_stake": 100.0,
        "basic_living_cost": 0.0,
        "carrying_capacity": 9,
    }
    dynamics.update(dynamics_overrides)
    return ExperimentConfig.model_validate(
        {
            "seed": 42,
            "population": {"size": 8, "composition": {AC: 4, AD: 4}},
            "match": {"length_mode": "fixed", "rounds_per_match": 2},
            "structure": {
                "kind": "lattice",
                "rows": 3,
                "cols": 3,
                "boundary": "bounded",
                "initial_layout": "stripes",
                "birth_radius": 1,
            },
            "dynamics": dynamics,
        }
    )


class TestOccupancyGoesLive:
    """Death frees a site, birth occupies one, newborn sites are real."""

    def test_the_occupancy_always_maps_exactly_the_living(self) -> None:
        """After every generation: one site per living agent, no leaks.

        The fixture churns in both directions — rich founders breed at
        generation 0, and a heavy living cost then starves the population
        to extinction — so sites are claimed AND reclaimed along the way.
        """
        config = _sync_economy_config(
            kind="lattice", generations=6, initial_energy=800.0, basic_living_cost=250.0
        )
        dynamics = EconomyDynamics(config, np.random.default_rng(config.seed))
        births = deaths = 0
        previous = len(dynamics.population)
        for _ in dynamics.run():
            occupancy = dynamics.occupancy
            assert occupancy is not None
            living = {agent.agent_id for agent in dynamics.population}
            assert set(occupancy.sites_by_agent()) == living
            assert len(occupancy) == len(living)
            births += max(0, len(dynamics.population) - previous)
            deaths += max(0, previous - len(dynamics.population))
            previous = len(dynamics.population)
        assert births > 0 and deaths > 0  # both directions actually exercised

    def test_newborn_snapshots_carry_real_sites(self) -> None:
        """#120(c)'s honest gap is closed: a site id from the moment of birth."""
        config = _sync_economy_config(kind="lattice", generations=3, initial_energy=600.0)
        newborn_sites = [
            snapshot.site_id
            for event in engine.run(config)
            if isinstance(event, GenerationFinished)
            for snapshot in event.agents
            if snapshot.parent_id is not None
        ]
        assert newborn_sites  # the fixture breeds
        assert all(site is not None for site in newborn_sites)

    def test_every_period_placement_is_exclusive(self) -> None:
        """No two living agents ever share a site (capacity 1, Design 12)."""
        config = _sync_economy_config(
            kind="lattice", generations=6, initial_energy=800.0, basic_living_cost=250.0
        )
        for event in engine.run(config):
            if isinstance(event, GenerationFinished):
                sites = [s.site_id for s in event.agents if s.site_id is not None]
                assert len(sites) == len(set(sites)) == len(event.agents)


# ---------------------------------------------------------------------------
# The blocked parent (Design 4: cleared the global gate, failed the local one)
# ---------------------------------------------------------------------------


class TestBlockedParents:
    """No stake, stays eligible, counted — the place-before-pay branch live."""

    def _prepared(self, rich_agent_id: int) -> EconomyDynamics:
        """Build the stripes fixture with exactly one θ-eligible parent.

        Args:
            rich_agent_id: The one agent set above threshold. Agent 0 sits
                on site 0 (a bounded corner whose neighbours 1, 3, 4 are
                all occupied — walled in); agent 7 sits on site 7, adjacent
                to the one empty site 8.

        Returns:
            The dynamics, energies hand-set, generator repositioned.
        """
        dynamics = EconomyDynamics(_stripes_config(), np.random.default_rng(42))
        for agent in dynamics._population:
            agent.energy = 1000.0 if agent.agent_id == rich_agent_id else 100.0
        dynamics._rng = np.random.default_rng(1)
        return dynamics

    def test_a_walled_in_parent_pays_nothing_and_is_counted(self) -> None:
        """Blocked: no newborn, no stake, the counter moves."""
        dynamics = self._prepared(rich_agent_id=0)
        newborns = dynamics._birth_phase(list(dynamics._population))
        assert newborns == []
        assert dynamics._blocked_parents == 1
        walled_in = next(a for a in dynamics.population if a.agent_id == 0)
        assert walled_in.energy == 1000.0  # not a unit of stake left it

    def test_a_blocked_parent_stays_eligible_and_breeds_once_room_opens(self) -> None:
        """Blocked is a delay, not a verdict: free a neighbour and it breeds."""
        dynamics = self._prepared(rich_agent_id=0)
        dynamics._birth_phase(list(dynamics._population))
        occupancy = dynamics.occupancy
        assert occupancy is not None
        # A neighbour of the walled-in parent dies; its site frees up.
        victim = next(a for a in dynamics._population if a.agent_id == 1)
        occupancy.remove_agent(victim.agent_id)
        living = [a for a in dynamics._population if a.agent_id != 1]
        newborns = dynamics._birth_phase(living)
        assert [n.parent_id for n in newborns] == [0]
        assert occupancy.site_of(newborns[0].agent_id) == 1  # the freed site

    def test_a_parent_with_reach_places_into_the_empty_site(self) -> None:
        """The unblocked control: the only in-reach empty site is taken."""
        dynamics = self._prepared(rich_agent_id=7)
        newborns = dynamics._birth_phase(list(dynamics._population))
        assert [n.parent_id for n in newborns] == [7]
        assert dynamics._blocked_parents == 0
        occupancy = dynamics.occupancy
        assert occupancy is not None
        assert occupancy.site_of(newborns[0].agent_id) == 8
        parent = next(a for a in dynamics.population if a.agent_id == 7)
        assert parent.energy == 900.0  # stake paid on success

    def test_blocked_counts_reach_the_event_stream(self) -> None:
        """The readout's channel: report → GenerationFinished.blocked_parents.

        Under von Neumann the richest founder — the first AlwaysDefect,
        agent 4, sitting on the CENTRE site 4 of the stripes deal — has
        neighbours 1, 3, 5, 7, all occupied, while the one empty site (8)
        sits outside its reach. Every generation the single free seat under
        K = 9 admits exactly that agent, and every generation it is
        blocked; the count must ride the event stream to the app.
        """
        config = ExperimentConfig.model_validate(
            {
                "seed": 42,
                "population": {"size": 8, "composition": {AC: 4, AD: 4}},
                "match": {"length_mode": "fixed", "rounds_per_match": 2},
                "structure": {
                    "kind": "lattice",
                    "rows": 3,
                    "cols": 3,
                    "neighbourhood_shape": "von_neumann",
                    "boundary": "bounded",
                    "initial_layout": "stripes",
                    "birth_radius": 1,
                },
                "dynamics": {
                    "generations": 3,
                    "reproduction_mode": "energy_economy",
                    "mutation_rate": 0.0,
                    "initial_energy": 1000.0,
                    "reproduction_threshold": 500.0,
                    "offspring_stake": 100.0,
                    "basic_living_cost": 0.0,
                    "carrying_capacity": 9,
                },
            }
        )
        events = [e for e in engine.run(config) if isinstance(e, GenerationFinished)]
        assert events
        assert all(event.blocked_parents == 1 for event in events)

    def test_well_mixed_streams_report_zero_blocked(self) -> None:
        """The new field stays inert off-lattice (the goldens' companion pin)."""
        config = _sync_economy_config(kind="well_mixed")
        for event in engine.run(config):
            if isinstance(event, GenerationFinished):
                assert event.blocked_parents == 0


# ---------------------------------------------------------------------------
# boundary_order (Design 5; VT-4's two effects, pinned deterministically)
# ---------------------------------------------------------------------------


def _boundary_order_config(order: str, **dynamics_overrides: object) -> ExperimentConfig:
    """A well-mixed economy fixture whose deaths are deterministic.

    6 founders (3 AC, 3 AD), one round per match, round-robin: each AC
    earns exactly 6 and each AD exactly 17 per generation, so hand-set
    energies make deaths (insolvency) and eligibility (θ) exact.

    Args:
        order: ``"death_first"`` or ``"birth_first"``.
        **dynamics_overrides: Extra dynamics fields.

    Returns:
        A validated config, seed 42.
    """
    dynamics: dict[str, object] = {
        "generations": 1,
        "reproduction_mode": "energy_economy",
        "boundary_order": order,
        "mutation_rate": 0.0,
        "reproduction_threshold": 500.0,
        "offspring_stake": 100.0,
        "basic_living_cost": 0.0,
        "carrying_capacity": 8,
    }
    dynamics.update(dynamics_overrides)
    return ExperimentConfig.model_validate(
        {
            "seed": 42,
            "population": {"size": 6, "composition": {AC: 3, AD: 3}},
            "match": {"length_mode": "fixed", "rounds_per_match": 1},
            "dynamics": dynamics,
        }
    )


ENTRY_ENERGIES = {0: -16.0, 1: 594.0, 2: 594.0, 3: 583.0, 4: -22.0, 5: 83.0}
"""Hand-set pre-step energies for the boundary-order fixture (ids 0-5).

Post-update (score income: AC = 6, AD = 17): id 0 → −10 (dies, insolvency),
id 1 → 600, id 2 → 600, id 3 → 600, id 4 → −5 (dies), id 5 → 100. Three
parents clear θ = 500. With K = 8: death_first has 4 survivors → 4 slots →
all 3 admitted; birth_first rations against the 6 pre-death living → 2
slots → only 2 admitted. The worked VT-4 arithmetic, at test size.
"""


def _run_one_boundary(order: str) -> tuple[int, int]:
    """Play one generation and count its births and final population.

    Args:
        order: ``"death_first"`` or ``"birth_first"``.

    Returns:
        ``(newborns, post-boundary population size)``.
    """
    dynamics = EconomyDynamics(_boundary_order_config(order), np.random.default_rng(42))
    for agent in dynamics._population:
        agent.energy = ENTRY_ENERGIES[agent.agent_id]
    report = dynamics.step()
    newborns = sum(1 for s in report.agents if s.parent_id is not None)
    return newborns, len(report.agents)


class TestBoundaryOrder:
    """`death_first` is #80 untouched; `birth_first` is H-A's order."""

    def test_birth_first_rations_against_the_pre_death_population(self) -> None:
        """VT-4's slots effect, exact: 3 births vs 2 at one boundary.

        Same config, same seed, mortality off — so the pre-death ration is
        the ONLY divergence channel (V4's first validation pass, as a
        test).
        """
        death_first_births, death_first_size = _run_one_boundary("death_first")
        birth_first_births, birth_first_size = _run_one_boundary("birth_first")
        assert death_first_births == 3
        assert birth_first_births == 2
        assert death_first_size == 4 + 3  # survivors + births
        assert birth_first_size == 4 + 2

    def test_newborns_face_the_reaper_in_their_birth_round(self) -> None:
        """H-A's exposure, at the deterministic corner: base_hazard = 1.

        With certain death for everyone, the two orders differ in exactly
        one observable: whether anyone was BORN before the cull. Under
        ``birth_first`` the births run first — two children exist, briefly
        — and then the whole merged population, newborns included, dies:
        children who died the round they were born. Under ``death_first``
        the parents are dead before the birth phase, so no child ever
        exists. Both runs end empty; the passport counter tells them
        apart.
        """

        def extinct_after_births(order: str) -> tuple[int, int]:
            config = _boundary_order_config(order, base_hazard=1.0, carrying_capacity=8)
            dynamics = EconomyDynamics(config, np.random.default_rng(42))
            for agent in dynamics._population:
                agent.energy = ENTRY_ENERGIES[agent.agent_id]
            report = dynamics.step()
            return len(report.agents), dynamics._next_id

        assert extinct_after_births("birth_first") == (0, 8)  # 2 born, all died
        assert extinct_after_births("death_first") == (0, 6)  # nobody ever born

    def test_newborn_coins_are_drawn_under_birth_first(self) -> None:
        """The stream itself shows the exposure: living + newborn coins."""
        config = _boundary_order_config("birth_first", base_hazard=0.5)
        counted = CountingGenerator(np.random.default_rng(42))
        dynamics = EconomyDynamics(config, counted)  # type: ignore[arg-type]
        for agent in dynamics._population:
            agent.energy = ENTRY_ENERGIES[agent.agent_id]
        before = counted.count("random")
        dynamics.step()
        # Match phase consumes no rng.random (deterministic strategies, no
        # noise); the death phase draws one coin per living agent PLUS one
        # per newborn: 6 living + 2 admitted births = 8 coins.
        assert counted.count("random") - before == 8

    def test_death_first_remains_the_frozen_sequence(self) -> None:
        """The default replays identically, boundary for boundary.

        The negative goldens pin the frozen #80 stream globally; this is
        the same fact at fixture grain.
        """
        first = _run_one_boundary("death_first")
        second = _run_one_boundary("death_first")
        assert first == second


# ---------------------------------------------------------------------------
# The async amendments (Design 7 / amended #99)
# ---------------------------------------------------------------------------


def _async_lattice_config(**dynamics_overrides: object) -> ExperimentConfig:
    """A 3x3 bounded-lattice async variable_n config, stripes founding.

    Args:
        **dynamics_overrides: Extra dynamics fields.

    Returns:
        A validated config, seed 42, 8 founders, site 8 empty.
    """
    dynamics: dict[str, object] = {
        "generations": 2,
        "time_model": "asynchronous",
        "mutation_rate": 0.0,
        "reproduction_threshold": 500.0,
        "offspring_stake": 100.0,
        "basic_living_cost": 0.0,
        "carrying_capacity": 9,
    }
    dynamics.update(dynamics_overrides)
    return ExperimentConfig.model_validate(
        {
            "seed": 42,
            "population": {"size": 8, "composition": {AC: 4, AD: 4}},
            "matching": {"matcher": "random_k", "opponents_per_agent": 2},
            "match": {"length_mode": "fixed", "rounds_per_match": 2},
            "structure": {
                "kind": "lattice",
                "rows": 3,
                "cols": 3,
                "boundary": "bounded",
                "initial_layout": "stripes",
                "birth_radius": 1,
            },
            "dynamics": dynamics,
        }
    )


class TestAsyncVariableNPlacement:
    """The same kernel draw, the same blocked semantics, one event at a time."""

    def _prepared(self, rich_agent_id: int) -> AsyncDynamics:
        """Build the async fixture with one θ-eligible, refractory-clear parent.

        Args:
            rich_agent_id: The one agent set above threshold (agent 0 is
                walled in on site 0; agent 7 neighbours the empty site 8).

        Returns:
            The dynamics, clock advanced past every refractory.
        """
        dynamics = AsyncDynamics(_async_lattice_config(), np.random.default_rng(42))
        for agent in dynamics._population:
            agent.energy = 1000.0 if agent.agent_id == rich_agent_id else 100.0
        dynamics._time = 5.0
        dynamics._rng = np.random.default_rng(1)
        return dynamics

    def test_a_walled_in_parent_is_blocked_with_anchor_untouched(self) -> None:
        """No stake, no birth, refractory anchor NOT reset, counted."""
        dynamics = self._prepared(rich_agent_id=0)
        anchor_before = dynamics._breeding_anchor[0]
        dynamics._births()
        assert len(dynamics.population) == 8  # nobody born
        blocked = next(a for a in dynamics.population if a.agent_id == 0)
        assert blocked.energy == 1000.0
        assert dynamics._breeding_anchor[0] == anchor_before
        assert dynamics._window_blocked == 1

    def test_a_parent_with_reach_places_and_occupies(self) -> None:
        """The unblocked control: newborn on site 8, stake paid, anchor set."""
        dynamics = self._prepared(rich_agent_id=7)
        dynamics._births()
        assert len(dynamics.population) == 9
        newborn = max(dynamics.population, key=lambda a: a.agent_id)
        assert newborn.parent_id == 7
        occupancy = dynamics._occupancy
        assert occupancy is not None
        assert occupancy.site_of(newborn.agent_id) == 8
        assert dynamics._breeding_anchor[7] == dynamics._time

    def test_async_deaths_vacate_sites(self) -> None:
        """A full run keeps occupancy equal to the living set, always."""
        config = _async_lattice_config(basic_living_cost=40.0)
        dynamics = AsyncDynamics(config, np.random.default_rng(config.seed))
        for _ in dynamics.run():
            occupancy = dynamics._occupancy
            assert occupancy is not None
            assert set(occupancy.sites_by_agent()) == {
                agent.agent_id for agent in dynamics.population
            }


def _fixed_n_lattice_dynamics(death_rule: str = "pure_random") -> AsyncDynamics:
    """Build a 3x3 torus von Neumann fixed_n dynamics at R = 1.

    Args:
        death_rule: ``fixed_n_death_rule``.

    Returns:
        The dynamics, 9 agents on 9 sites (full occupancy, validated).
    """
    config = ExperimentConfig.model_validate(
        {
            "seed": 42,
            "population": {"size": 9, "composition": {AC: 5, AD: 4}},
            "matching": {"matcher": "random_k", "opponents_per_agent": 2},
            "match": {"length_mode": "fixed", "rounds_per_match": 2},
            "structure": {
                "kind": "lattice",
                "rows": 3,
                "cols": 3,
                "neighbourhood_shape": "von_neumann",
                "initial_layout": "stripes",
                "birth_radius": 1,
            },
            "dynamics": {
                "generations": 2,
                "time_model": "asynchronous",
                "async_population": "fixed_n",
                "moran_rule": "death_birth",
                "fixed_n_death_rule": death_rule,
                "mutation_rate": 0.0,
            },
        }
    )
    return AsyncDynamics(config, np.random.default_rng(config.seed))


class TestFixedNLocalisation:
    """Design 7: the breeder/victim localise; R = 1 recovers Ohtsuki exactly."""

    def test_breeder_draw_at_r1_is_exactly_fitness_proportional(self) -> None:
        """The MULTIPLY fork's promised corner, pinned draw-for-draw.

        At R = 1 every candidate sits at distance 1, so the kernel factors
        are equal and cancel out of the normalisation: the engine's
        localised draw must select the SAME agent, seed for seed, as a
        plain #63 shifted-fitness roulette over the neighbour set (with
        the shift's standing consequence — the poorest neighbour has
        weight 0 and is never drawn).
        """
        dynamics = _fixed_n_lattice_dynamics()
        energies = {
            0: 50.0,
            1: 200.0,
            2: 90.0,
            3: 400.0,
            4: 130.0,
            5: 260.0,
            6: 75.0,
            7: 310.0,
            8: 180.0,
        }
        for agent in dynamics._population:
            agent.energy = energies[agent.agent_id]
        occupancy = dynamics._occupancy
        assert occupancy is not None
        structure = occupancy.structure
        freed_site = 4  # the centre; von Neumann neighbours: 1, 3, 5, 7
        victim_id = occupancy.vacate(freed_site)
        neighbour_sites = sites_within(structure, freed_site, 1)
        assert neighbour_sites == (1, 3, 5, 7)
        # The kernel factors really are all equal at R = 1.
        assert len(set(kernel_weights(structure, freed_site, neighbour_sites, 0.7))) == 1
        by_id = {agent.agent_id: agent for agent in dynamics._population}
        occupants = [by_id[occupancy.agent_at(site)] for site in neighbour_sites]
        floor = min(agent.energy for agent in occupants)
        for seed in range(20):
            dynamics._rng = np.random.default_rng(seed)
            winner = dynamics._localised_breeder(freed_site)
            # Reference: the #63 roulette over the same candidates — the
            # zero-weight (poorest) candidate drops from the pool exactly
            # as neighbourhood_sample's drawable filter does.
            pool = [
                s for s, a in zip(neighbour_sites, occupants, strict=True) if a.energy - floor > 0
            ]
            weights = np.array(
                [by_id[occupancy.agent_at(s)].energy - floor for s in pool], dtype=float
            )
            reference_rng = np.random.default_rng(seed)
            expected_site = reference_rng.choice(
                pool, size=1, replace=False, p=weights / weights.sum()
            )[0]
            assert occupancy.agent_at(int(expected_site)) == winner.agent_id
        # Restore the fixture invariant (the vacated victim), for hygiene.
        occupancy.occupy(freed_site, victim_id)

    def test_birth_death_victim_is_always_a_lattice_neighbour(self) -> None:
        """The victim localises to the breeder's neighbourhood, never beyond."""
        for seed in range(10):
            dynamics = _fixed_n_lattice_dynamics()
            for agent in dynamics._population:
                agent.energy = 100.0 + agent.agent_id  # distinct, all drawable
            dynamics._rng = np.random.default_rng(seed)
            occupancy = dynamics._occupancy
            assert occupancy is not None
            structure = occupancy.structure
            breeder = dynamics._population[0]
            breeder_site = occupancy.site_of(breeder.agent_id)
            assert breeder_site is not None
            victim = dynamics._localised_victim(breeder)
            victim_site = occupancy.site_of(victim.agent_id)
            assert victim_site in structure.neighbours(breeder_site)

    def test_energy_decides_picks_the_poorest_neighbour_without_a_draw(self) -> None:
        """The deterministic death rule localises deterministically."""
        dynamics = _fixed_n_lattice_dynamics(death_rule="energy_decides")
        for agent in dynamics._population:
            agent.energy = 100.0 + agent.agent_id
        counted = CountingGenerator(np.random.default_rng(3))
        dynamics._rng = counted  # type: ignore[assignment]
        occupancy = dynamics._occupancy
        assert occupancy is not None
        breeder = dynamics._population[4]  # site 4: neighbours 1, 3, 5, 7
        victim = dynamics._localised_victim(breeder)
        assert victim.agent_id == 1  # the poorest of agents 1, 3, 5, 7
        assert counted.calls == []  # no draw — the #80 active-flag idiom

    def test_site_recycling_keeps_the_grid_full(self) -> None:
        """A fixed_n lattice run stays at full occupancy through replacements."""
        dynamics = _fixed_n_lattice_dynamics()
        for _ in dynamics.run():
            occupancy = dynamics._occupancy
            assert occupancy is not None
            assert len(occupancy) == 9
            assert set(occupancy.sites_by_agent()) == {
                agent.agent_id for agent in dynamics.population
            }
