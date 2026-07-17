"""Tests for the M10a energy economy: pure helpers and EconomyDynamics.

The worked fixture used throughout: 2 AlwaysCooperate (ids 0, 1) + 2
AlwaysDefect (ids 2, 3) under round-robin, 2 rounds per match, default
payoffs (T=5, R=3, P=1, S=0). Per generation that gives every agent 3
matches / 6 rounds and raw scores of exactly 6 (each AC: 6 + 0 + 0) and 22
(each AD: 10 + 10 + 2) — small enough to hand-check every energy ledger.
"""

from __future__ import annotations

import numpy as np
import pytest

from pdsim.config.experiment import DynamicsConfig, ExperimentConfig
from pdsim.core import dynamics as dynamics_module
from pdsim.core.agent import Agent
from pdsim.core.dynamics import EconomyDynamics, PopulationDynamics
from pdsim.core.economy import (
    admit_births,
    age_mortality_active,
    energy_update,
    mortality_probability,
    place_offspring,
    staggered_founder_ages,
)
from pdsim.tests.stub_strategies import StubAlwaysCooperate


def _dynamics(**overrides: object) -> DynamicsConfig:
    """Build an economy DynamicsConfig with test-friendly defaults.

    Args:
        **overrides: Field values to override.

    Returns:
        A validated config in ``energy_economy`` mode.
    """
    data: dict[str, object] = {"reproduction_mode": "energy_economy", "mutation_rate": 0.0}
    data.update(overrides)
    return DynamicsConfig.model_validate(data)


def _config(**dynamics_overrides: object) -> ExperimentConfig:
    """Build the worked 2 AC + 2 AD round-robin economy experiment.

    Args:
        **dynamics_overrides: Dynamics field values to override.

    Returns:
        A validated economy config (2 rounds/match, seed 42).
    """
    data: dict[str, object] = {
        "reproduction_mode": "energy_economy",
        "mutation_rate": 0.0,
        "generations": 5,
        "carrying_capacity": 200,
    }
    data.update(dynamics_overrides)
    return ExperimentConfig.model_validate(
        {
            "seed": 42,
            "population": {
                "size": 4,
                "composition": {"always_cooperate": 2, "always_defect": 2},
            },
            "match": {"length_mode": "fixed", "rounds_per_match": 2},
            "dynamics": data,
        }
    )


def _agent(agent_id: int, energy: float) -> Agent:
    """Build a bare agent with an energy stock (for the pure-helper tests).

    Args:
        agent_id: The agent's id.
        energy: The agent's energy.

    Returns:
        The agent.
    """
    return Agent(agent_id=agent_id, strategy=StubAlwaysCooperate(), energy=energy)


class TestEnergyUpdate:
    """The ledger: returns on capital + income − living − engagement."""

    def test_plain_ledger(self) -> None:
        """No returns, no engagement: carried + score − living cost."""
        d = _dynamics(basic_living_cost=200.0)
        assert energy_update(400.0, 300.0, 10, d) == 500.0

    def test_engagement_cost_scales_with_matches(self) -> None:
        """Each match played costs the engagement fee."""
        d = _dynamics(basic_living_cost=0.0, engagement_cost=2.5)
        assert energy_update(100.0, 0.0, 4, d) == 90.0

    def test_capital_return_applies_to_carried_energy_only(self) -> None:
        """Interest is paid on the carried stock, not on this generation's income."""
        d = _dynamics(basic_living_cost=0.0, capital_return_rate=0.1)
        assert energy_update(1000.0, 50.0, 0, d) == pytest.approx(1150.0)

    def test_result_may_go_negative(self) -> None:
        """The ledger itself never clamps — insolvency is the boundary's job."""
        d = _dynamics(basic_living_cost=200.0)
        assert energy_update(50.0, 100.0, 0, d) == -50.0


class TestMortality:
    """The mortality trio: hard cap, Gompertz-style climb, active gate."""

    def test_age_cap_is_certain_death(self) -> None:
        """At or beyond max_age the probability is exactly 1."""
        d = _dynamics(max_age=20, base_hazard=0.01)
        assert mortality_probability(20, d) == 1.0
        assert mortality_probability(25, d) == 1.0

    def test_hazard_climbs_geometrically(self) -> None:
        """Below the cap: base_hazard × factor^age, capped at 1."""
        d = _dynamics(base_hazard=0.1, senescence_factor=2.0)
        assert mortality_probability(0, d) == pytest.approx(0.1)
        assert mortality_probability(3, d) == pytest.approx(0.8)
        assert mortality_probability(10, d) == 1.0  # capped

    def test_auto_factor_reaches_certainty_exactly_at_max_age(self) -> None:
        """The resolved auto factor hits p = 1 at max_age (spec worked case).

        The hazard curve h·f^age meets the hard cap smoothly: with the auto
        factor, h·f^max_age is exactly 1 — the cap fires where the curve
        would have anyway.
        """
        d = _dynamics(base_hazard=0.01, max_age=20)
        assert d.senescence_factor == pytest.approx(1.2589, abs=1e-4)
        assert 0.01 * d.senescence_factor**20 == pytest.approx(1.0)
        assert mortality_probability(19, d) == pytest.approx(0.794, abs=1e-3)
        assert mortality_probability(20, d) == 1.0

    def test_active_gate(self) -> None:
        """Any of the trio switches the mortality sub-phase on."""
        assert not age_mortality_active(_dynamics())
        assert age_mortality_active(_dynamics(base_hazard=0.1))
        assert age_mortality_active(_dynamics(senescence_factor=1.5))
        assert age_mortality_active(_dynamics(max_age=10))


class TestAdmitBirths:
    """The capacity gate: energy priority, deterministic, RNG-free."""

    def test_energy_priority_order(self) -> None:
        """Richest first; the id breaks ties."""
        eligible = [_agent(0, 500.0), _agent(1, 900.0), _agent(2, 700.0)]
        admitted = admit_births(eligible, slots=2)
        assert [a.agent_id for a in admitted] == [1, 2]

    def test_tie_breaks_by_ascending_id(self) -> None:
        """(energy desc, id asc): equal energy admits the lower id first."""
        eligible = [_agent(5, 500.0), _agent(3, 500.0), _agent(4, 500.0)]
        admitted = admit_births(eligible, slots=2)
        assert [a.agent_id for a in admitted] == [3, 4]

    def test_zero_slots_admits_nobody(self) -> None:
        """At capacity, no births."""
        assert admit_births([_agent(0, 999.0)], slots=0) == []

    def test_more_slots_than_eligible_admits_everyone(self) -> None:
        """Slots beyond the eligible set are simply unused."""
        eligible = [_agent(0, 500.0), _agent(1, 600.0)]
        assert len(admit_births(eligible, slots=10)) == 2


class TestPlacementAndAges:
    """The structural gate and founder staggering."""

    def test_place_offspring_always_succeeds_in_well_mixed(self) -> None:
        """M10a's fully-connected corner: placement never fails."""
        assert place_offspring([], _agent(0, 0.0)) is True

    def test_staggered_ages_cycle_up_to_max_age(self) -> None:
        """Founders get 0..max_age−1 repeating (demographic steady state)."""
        assert staggered_founder_ages(5, max_age=3) == [0, 1, 2, 0, 1]

    def test_no_cap_means_no_staggering(self) -> None:
        """Without an age cap everyone starts at 0."""
        assert staggered_founder_ages(4, max_age=0) == [0, 0, 0, 0]


class TestEconomyBoundary:
    """EconomyDynamics.step(): the nine-step boundary on the worked fixture."""

    def test_report_describes_population_as_played(self) -> None:
        """Composition, raw mean scores, and per-generation rounds."""
        dyn = EconomyDynamics(_config(), np.random.default_rng(42))
        report = dyn.step()
        assert report.composition == {"always_cooperate": 2, "always_defect": 2}
        assert report.mean_scores == {"always_cooperate": 6.0, "always_defect": 22.0}
        assert report.rounds_played == {"always_cooperate": 12, "always_defect": 12}

    def test_energy_ledger_applied_per_agent(self) -> None:
        """The ledger per agent: 400 + score − 200 → AC at 206, AD at 222."""
        dyn = EconomyDynamics(_config(basic_living_cost=200.0), np.random.default_rng(42))
        report = dyn.step()
        by_id = {snap.agent_id: snap for snap in report.agents}
        assert by_id[0].energy == pytest.approx(206.0)  # 400 + 6 − 200
        assert by_id[2].energy == pytest.approx(222.0)  # 400 + 22 − 200

    def test_insolvency_is_strictly_negative(self) -> None:
        """Ending at exactly 0 survives; below 0 dies.

        With initial_energy 0 and living cost 6, the AC founders (score 6)
        land at exactly 0 and live; with cost 7 they land at −1 and die.
        """
        at_zero = EconomyDynamics(
            _config(initial_energy=0.0, basic_living_cost=6.0, reproduction_threshold=10_000.0),
            np.random.default_rng(42),
        )
        report = at_zero.step()
        assert {s.agent_id for s in report.agents} == {0, 1, 2, 3}

        below_zero = EconomyDynamics(
            _config(initial_energy=0.0, basic_living_cost=7.0, reproduction_threshold=10_000.0),
            np.random.default_rng(42),
        )
        report = below_zero.step()
        assert {s.agent_id for s in report.agents} == {2, 3}  # only the ADs (score 22)

    def test_birth_transfers_the_stake_and_records_lineage(self) -> None:
        """A parent above θ pays σ; the child starts at σ with the parent's id.

        With initial 480 and zero living cost, the AC founders end at 486 <
        θ = 500 while the ADs end at 502 ≥ θ — exactly the two AD births.
        """
        dyn = EconomyDynamics(
            _config(
                initial_energy=480.0,
                basic_living_cost=0.0,
                reproduction_threshold=500.0,
                offspring_stake=400.0,
            ),
            np.random.default_rng(42),
        )
        report = dyn.step()
        by_id = {snap.agent_id: snap for snap in report.agents}
        assert set(by_id) == {0, 1, 2, 3, 4, 5}
        assert by_id[2].energy == pytest.approx(102.0)  # 502 − 400
        assert by_id[4].parent_id == 2  # children in parent-id order
        assert by_id[5].parent_id == 3
        assert by_id[4].energy == pytest.approx(400.0)
        assert by_id[4].age == 0
        assert by_id[4].strategy == "always_defect"

    def test_one_birth_per_parent_even_when_very_rich(self) -> None:
        """Even at e ≥ 2θ, a parent gets exactly one child per generation."""
        dyn = EconomyDynamics(
            _config(
                initial_energy=2000.0,
                basic_living_cost=0.0,
                reproduction_threshold=500.0,
                offspring_stake=400.0,
            ),
            np.random.default_rng(42),
        )
        report = dyn.step()
        assert len(report.agents) == 8  # 4 founders + exactly 4 children

    def test_reproduction_overhead_burns_extra_energy(self) -> None:
        """The parent pays σ + overhead; the child still receives only σ."""
        dyn = EconomyDynamics(
            _config(
                initial_energy=480.0,
                basic_living_cost=0.0,
                reproduction_threshold=500.0,
                offspring_stake=400.0,
                reproduction_overhead=50.0,
            ),
            np.random.default_rng(42),
        )
        report = dyn.step()
        by_id = {snap.agent_id: snap for snap in report.agents}
        assert by_id[2].energy == pytest.approx(52.0)  # 502 − 400 − 50
        assert by_id[4].energy == pytest.approx(400.0)

    def test_capacity_admits_the_richest_eligible_parents(self) -> None:
        """Free seats = K − survivors; energy priority decides the admitted set.

        K = 5 leaves one free seat; all four founders clear θ, and the AD
        founders are richer — the single seat goes to the richest (both ADs
        tie at 422; the lower id, 2, wins the tie-break).
        """
        dyn = EconomyDynamics(
            _config(
                initial_energy=600.0,
                basic_living_cost=200.0,
                reproduction_threshold=300.0,
                offspring_stake=300.0,
                carrying_capacity=5,
            ),
            np.random.default_rng(42),
        )
        report = dyn.step()
        newborns = [snap for snap in report.agents if snap.parent_id is not None]
        assert len(newborns) == 1
        assert newborns[0].parent_id == 2

    def test_ids_are_assigned_in_parent_id_order_not_energy_order(self) -> None:
        """The two orderings are distinct (the spec's RNG contract).

        Admission ranks the AD founders (ids 2, 3) ABOVE the AC founders
        (ids 0, 1) by energy — yet the first new passport id goes to parent
        0, because id assignment iterates the admitted set in parent-id
        order, never in energy order.
        """
        dyn = EconomyDynamics(
            _config(
                initial_energy=600.0,
                basic_living_cost=0.0,
                reproduction_threshold=500.0,
                offspring_stake=400.0,
            ),
            np.random.default_rng(42),
        )
        report = dyn.step()
        children = {snap.agent_id: snap.parent_id for snap in report.agents if snap.age == 0}
        assert children == {4: 0, 5: 1, 6: 2, 7: 3}

    def test_placement_is_checked_before_the_stake_is_paid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A blocked parent is never charged (M11's inherited guarantee)."""
        monkeypatch.setattr(dynamics_module, "place_offspring", lambda population, parent: False)
        dyn = EconomyDynamics(
            _config(
                initial_energy=600.0,
                basic_living_cost=0.0,
                reproduction_threshold=500.0,
                offspring_stake=400.0,
            ),
            np.random.default_rng(42),
        )
        report = dyn.step()
        assert len(report.agents) == 4  # no child was ever born
        by_id = {snap.agent_id: snap for snap in report.agents}
        assert by_id[0].energy == pytest.approx(606.0)  # σ untouched

    def test_ages_increment_for_survivors_only(self) -> None:
        """Survivors age by one; newborns enter at 0."""
        dyn = EconomyDynamics(
            _config(initial_energy=600.0, basic_living_cost=0.0), np.random.default_rng(42)
        )
        report = dyn.step()
        founders = [snap for snap in report.agents if snap.parent_id is None]
        assert all(snap.age == 1 for snap in founders)

    def test_max_age_cap_kills_on_schedule(self) -> None:
        """With max_age = 1 and no reproduction, everyone dies at boundary 2.

        Founders (staggered to age 0) survive the first boundary at age 0,
        enter generation 2 at age 1 = max_age, and die with certainty —
        extinction without a single energy death.
        """
        dyn = EconomyDynamics(
            _config(
                max_age=1,
                initial_energy=10_000.0,
                basic_living_cost=0.0,
                reproduction_threshold=100_000.0,
            ),
            np.random.default_rng(42),
        )
        first = dyn.step()
        assert len(first.agents) == 4
        second = dyn.step()
        assert second.agents == ()
        assert dyn.population == ()

    def test_snapshot_matches_the_live_population(self) -> None:
        """The snapshot IS the post-boundary population, id-ordered."""
        dyn = EconomyDynamics(_config(), np.random.default_rng(42))
        report = dyn.step()
        assert [snap.agent_id for snap in report.agents] == [
            agent.agent_id for agent in dyn.population
        ]
        ids = [snap.agent_id for snap in report.agents]
        assert ids == sorted(ids)
        for snap, agent in zip(report.agents, dyn.population, strict=True):
            assert snap.energy == agent.energy
            assert snap.age == agent.age


class TestPersistentHistories:
    """Task 3: memory persists for an agent's lifetime in economy mode."""

    def test_round_number_accumulates_across_generations(self) -> None:
        """Meeting the same passport id next generation continues the story."""
        config = _config(reproduction_threshold=100_000.0)  # no births: founders only
        dyn = EconomyDynamics(config, np.random.default_rng(42))
        dyn.step()
        agent_zero = next(a for a in dyn.population if a.agent_id == 0)
        assert agent_zero.view_of(1).round_number == 2  # generation 1's match
        dyn.step()
        assert agent_zero.view_of(1).round_number == 4  # + generation 2's match

    def test_grim_trigger_holds_a_lifetime_grudge(self) -> None:
        """A betrayal in generation 1 is still punished in generation 2.

        Grim vs AlwaysDefect, 3 rounds/match: generation 1 opens with one C
        (1/3 cooperation); generation 2 opens already grim (0/3) because
        the grudge survived the boundary.
        """
        config = ExperimentConfig.model_validate(
            {
                "seed": 42,
                "population": {
                    "size": 2,
                    "composition": {"grim_trigger": 1, "always_defect": 1},
                },
                "match": {"length_mode": "fixed", "rounds_per_match": 3},
                "dynamics": {
                    "reproduction_mode": "energy_economy",
                    "mutation_rate": 0.0,
                    "generations": 2,
                    "reproduction_threshold": 100_000.0,
                    "basic_living_cost": 0.0,
                },
            }
        )
        dyn = EconomyDynamics(config, np.random.default_rng(42))
        first = dyn.step()
        second = dyn.step()
        assert first.cooperation[("grim_trigger", "always_defect")][0] == pytest.approx(1 / 3)
        assert second.cooperation[("grim_trigger", "always_defect")][0] == 0.0

    def test_imitation_path_still_clears_histories(self) -> None:
        """The mirror: PopulationDynamics resets both score and memory (#31)."""
        config = ExperimentConfig.model_validate(
            {
                "seed": 42,
                "population": {
                    "size": 2,
                    "composition": {"grim_trigger": 1, "always_defect": 1},
                },
                "match": {"length_mode": "fixed", "rounds_per_match": 3},
                "dynamics": {"generations": 2, "mutation_rate": 0.0},
            }
        )
        dyn = PopulationDynamics(config, np.random.default_rng(42))
        dyn.step()
        # The boundary wiped everything: no scores, no remembered rounds.
        for agent in dyn.population:
            assert agent.score == 0.0
            assert agent.rounds_played == 0
            assert agent.view_of(1 - agent.agent_id).round_number == 0

    def test_rounds_played_is_per_generation_not_lifetime(self) -> None:
        """The silent-decay trap (spec Task 0a): it fails loudly here.

        An agent alive for three generations must report THIS generation's
        rounds — the same 12 per strategy every generation, not 12/24/36.
        """
        dyn = EconomyDynamics(_config(reproduction_threshold=100_000.0), np.random.default_rng(42))
        for _ in range(3):
            report = dyn.step()
            assert report.rounds_played == {"always_cooperate": 12, "always_defect": 12}

    def test_newborns_start_with_empty_histories(self) -> None:
        """A child inherits a strategy, never its parent's relationships."""
        dyn = EconomyDynamics(
            _config(initial_energy=600.0, basic_living_cost=0.0), np.random.default_rng(42)
        )
        dyn.step()
        newborns = [a for a in dyn.population if a.parent_id is not None]
        assert newborns
        for child in newborns:
            assert child.view_of(child.parent_id).round_number == 0
            assert child.rounds_played == 0


class TestReproducibility:
    """Seeded determinism across the full boundary machinery."""

    def test_run_with_mid_run_deaths_reproduces_exactly(self) -> None:
        """The golden test for id-ordered iteration over gappy ids.

        random_k + age mortality + births: deaths open id gaps, and the
        whole trajectory must still replay byte-for-byte from the seed.
        """
        config = ExperimentConfig.model_validate(
            {
                "seed": 7,
                "population": {
                    "size": 10,
                    "composition": {"tit_for_tat": 5, "always_defect": 5},
                },
                "matching": {"matcher": "random_k", "opponents_per_agent": 3},
                "match": {"length_mode": "fixed", "rounds_per_match": 5},
                "dynamics": {
                    "reproduction_mode": "energy_economy",
                    "mutation_rate": 0.1,
                    "generations": 8,
                    "reproduction_threshold": 150.0,
                    "offspring_stake": 100.0,
                    "initial_energy": 120.0,
                    "basic_living_cost": 60.0,
                    "carrying_capacity": 30,
                    "base_hazard": 0.05,
                    "max_age": 6,
                },
            }
        )

        def trajectory() -> list[tuple[tuple[int, ...], tuple[float, ...]]]:
            dyn = EconomyDynamics(config, np.random.default_rng(config.seed))
            out = []
            for report in dyn.run():
                out.append(
                    (
                        tuple(s.agent_id for s in report.agents),
                        tuple(s.energy for s in report.agents),
                    )
                )
            return out

        first, second = trajectory(), trajectory()
        assert first == second
        # And deaths actually happened (ids went non-contiguous), so the
        # test exercises what it claims to.
        all_ids = [ids for ids, _ in first if ids]
        assert any(ids != tuple(range(ids[0], ids[0] + len(ids))) for ids in all_ids)
