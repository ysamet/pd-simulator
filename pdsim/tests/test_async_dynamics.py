"""Tests for the M10b async engine (spec Designs 0, 2, 2a, 3, 5, 8, 9).

Phase A: the V6 RNG golden-master (a fixed seed reproduces an async run
byte-for-byte, plus a pinned trace so a mis-pinned draw order fails loudly),
the V7 synchronous regression (sync streams gain nothing), the Option B
seam contracts (two orderings, place-before-pay), the breeding refractory,
the event-time ledger, and the #81 lone-survivor corner in event-time.

Phase B: the fixed_n Moran engine (the moran-random golden master pinning
the rule roll's first-draw position, the death-rule semantics, the #63
fitness-shift idiom, place-before-pay in the fixed_n path, the legal
negative parent), variable_n's mortality trio in event-time (birthday
hazard coins, the deterministic age cap, founder staggering via negative
birth_time), and the #34 validator gates the new parameters brought.

Phase C: the imitation overlay (spec Design 4) — the unconditional
per-match coin and its Design 8 step-3 position, the no-event-on-no-op
rule, the lower-total (then lower-id) adopter, immediacy inside a bundle,
the cultural/demographic split V2 makes visible, and the overlay's
off-by-default silence that keeps both golden masters valid.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest
from pydantic import ValidationError

from pdsim.config.experiment import ExperimentConfig
from pdsim.core import async_dynamics as async_module
from pdsim.core.agent import Agent
from pdsim.core.async_dynamics import AsyncDynamics
from pdsim.core.engine import run
from pdsim.core.events import (
    BirthEvent,
    DeathEvent,
    GenerationFinished,
    ImitationEvent,
    RunFinished,
)
from pdsim.core.match import MatchResult
from pdsim.core.strategies import create_strategy, strategy_name_of
from pdsim.core.timeseries import RunTimeseries


def _config(**dynamics_overrides: object) -> ExperimentConfig:
    """Build a small asynchronous experiment (10 agents, k = 2, 4 rounds).

    Args:
        **dynamics_overrides: Dynamics field values to override.

    Returns:
        A validated async config (seed 7) — the golden-master fixture.
    """
    data: dict[str, object] = {
        "generations": 4,
        "time_model": "asynchronous",
        "reproduction_threshold": 60.0,
        "offspring_stake": 50.0,
        "basic_living_cost": 25.0,
        "carrying_capacity": 30,
        "mutation_rate": 0.0,
    }
    data.update(dynamics_overrides)
    return ExperimentConfig.model_validate(
        {
            "seed": 7,
            "population": {
                "size": 10,
                "composition": {"tit_for_tat": 5, "always_defect": 5},
            },
            "matching": {"matcher": "random_k", "opponents_per_agent": 2},
            "match": {"length_mode": "fixed", "rounds_per_match": 4},
            "dynamics": data,
        }
    )


# ---------------------------------------------------------------------------
# V6 — the RNG golden-master
# ---------------------------------------------------------------------------


def test_async_stream_is_reproducible() -> None:
    """Same config + seed → byte-identical event streams (hard rule 5)."""
    config = _config()
    assert list(run(config)) == list(run(config))


def test_async_golden_trace() -> None:
    """The pinned seed-7 trace: any draw-order change fails loudly here.

    The values were captured from the frozen Phase A contract (spec Design
    8). They pin the composition trajectory, every birth (with lineage and
    timestamp), and every death — a mis-pinned focal/partner/μ draw or a
    reordered demographic step cannot reproduce them.
    """
    expected_compositions = [
        (0, {"tit_for_tat": 5, "always_defect": 7}, 1.0),
        (1, {"tit_for_tat": 5, "always_defect": 7}, 2.038462),
        (2, {"tit_for_tat": 4, "always_defect": 8}, 3.053114),
        (3, {"tit_for_tat": 3, "always_defect": 6}, 4.066245),
    ]
    expected_births = [
        (10, 7, 1.0),
        (11, 9, 1.0),
        (12, 5, 1.083333),
        (13, 12, 2.121795),
        (14, 10, 2.371795),
        (15, 8, 2.75641),
    ]
    expected_deaths = [
        (9, "insolvency", 1.621795),
        (7, "insolvency", 2.121795),
        (12, "insolvency", 2.899267),
        (4, "insolvency", 3.053114),
        (3, "insolvency", 3.553114),
        (10, "insolvency", 3.644023),
        (11, "insolvency", 3.844023),
    ]
    compositions = []
    births = []
    deaths = []
    final = None
    for event in run(_config()):
        if isinstance(event, GenerationFinished):
            compositions.append(
                (event.index, dict(event.composition), round(event.gen_equiv_time, 6))
            )
        elif isinstance(event, BirthEvent):
            births.append((event.agent_id, event.parent_id, round(event.gen_equiv_time, 6)))
        elif isinstance(event, DeathEvent):
            deaths.append((event.agent_id, event.cause, round(event.gen_equiv_time, 6)))
        elif isinstance(event, RunFinished):
            final = event
    assert compositions == expected_compositions
    assert births == expected_births
    assert deaths == expected_deaths
    assert final is not None
    assert final.completed == 4
    assert final.composition == {"tit_for_tat": 3, "always_defect": 6}


def test_granularity_is_observer_only_in_async() -> None:
    """#35 extends to async: granularity never changes period payloads."""
    coarse = [e for e in run(_config()) if isinstance(e, GenerationFinished)]
    fine = [e for e in run(_config(), granularity="match") if isinstance(e, GenerationFinished)]
    assert coarse == fine


# ---------------------------------------------------------------------------
# V7 — the synchronous paths gain nothing
# ---------------------------------------------------------------------------


def _sync_config(reproduction_mode: str) -> ExperimentConfig:
    """Build a small synchronous config in the given reproduction mode.

    Args:
        reproduction_mode: ``"imitation"`` or ``"energy_economy"``.

    Returns:
        A validated synchronous config (seed 11).
    """
    return ExperimentConfig.model_validate(
        {
            "seed": 11,
            "population": {
                "size": 6,
                "composition": {"tit_for_tat": 3, "always_defect": 3},
            },
            "match": {"length_mode": "fixed", "rounds_per_match": 2},
            "dynamics": {
                "generations": 3,
                "reproduction_mode": reproduction_mode,
                "mutation_rate": 0.0,
                "carrying_capacity": 50,
            },
        }
    )


@pytest.mark.parametrize("reproduction_mode", ["imitation", "energy_economy"])
def test_sync_streams_emit_no_async_events(reproduction_mode: str) -> None:
    """Sync runs emit no demographic events and no clock stamps (V7)."""
    for event in run(_sync_config(reproduction_mode)):
        assert not isinstance(event, BirthEvent | DeathEvent | ImitationEvent)
        if isinstance(event, GenerationFinished):
            assert event.gen_equiv_time is None


# ---------------------------------------------------------------------------
# The Option B seam contracts (spec Design 9)
# ---------------------------------------------------------------------------


def test_ids_assigned_in_parent_id_order_not_energy_order() -> None:
    """The #80 two-orderings pin, in event-time.

    Admission is by energy priority, but passport ids (and μ draws) follow
    ascending PARENT id.
    """
    dynamics = AsyncDynamics(_config(), np.random.default_rng(0))
    dynamics._population = dynamics._population[:2]
    poor, rich = dynamics._population
    poor.energy = 500.0
    rich.energy = 900.0
    dynamics._time = 5.0  # refractory long clear for both founders
    dynamics._births()
    births = [e for e in dynamics._pending if isinstance(e, BirthEvent)]
    # Energy order is (rich, poor) = (id 1, id 0); id assignment must run in
    # parent-id order regardless: first new id to parent 0, next to parent 1.
    assert [(e.agent_id, e.parent_id) for e in births] == [(10, 0), (11, 1)]
    assert poor.energy == 500.0 - 50.0
    assert rich.energy == 900.0 - 50.0


def test_place_before_pay(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blocked placement never charges σ (M11's inherited guarantee)."""
    monkeypatch.setattr(async_module, "place_offspring", lambda population, parent: False)
    dynamics = AsyncDynamics(_config(), np.random.default_rng(0))
    parent = dynamics._population[0]
    parent.energy = 900.0
    dynamics._time = 5.0
    next_id_before = dynamics._next_id
    dynamics._births()
    assert parent.energy == 900.0
    assert dynamics._pending == []
    assert dynamics._next_id == next_id_before


# ---------------------------------------------------------------------------
# The event-time ledger and refractory (spec Design 2a)
# ---------------------------------------------------------------------------


def test_breeding_refractory_one_birth_per_generation_equivalent() -> None:
    """A rich parent breeds at most once per unit of event-time.

    The event-time image of #80's one-birth-per-generation rule.
    """
    config = ExperimentConfig.model_validate(
        {
            "seed": 3,
            "population": {"size": 4, "composition": {"tit_for_tat": 4}},
            "matching": {"matcher": "random_k", "opponents_per_agent": 1},
            "match": {"length_mode": "fixed", "rounds_per_match": 2},
            "dynamics": {
                "generations": 3,
                "time_model": "asynchronous",
                "reproduction_threshold": 100.0,
                "offspring_stake": 100.0,
                "initial_energy": 1000.0,
                "basic_living_cost": 0.0,
                "carrying_capacity": 100,
                "mutation_rate": 0.0,
            },
        }
    )
    births_by_parent: dict[int, list[float]] = {}
    for event in run(config):
        if isinstance(event, BirthEvent):
            births_by_parent.setdefault(event.parent_id, []).append(event.gen_equiv_time)
    assert births_by_parent, "rich founders must breed"
    for times in births_by_parent.values():
        # Founders anchor at t = 0, so nothing breeds before t ≈ 1 — and
        # after each birth the anchor moves, so consecutive gaps are ≥ 1.
        assert times[0] >= 1.0 - 1e-6
        for earlier, later in itertools.pairwise(times):
            assert later - earlier >= 1.0 - 1e-6


def test_accrual_sweep_ledger_arithmetic() -> None:
    """``e ← e·(1+r)^Δt − L·Δt`` — the Design 2a conversion, exactly."""
    dynamics = AsyncDynamics(
        _config(capital_return_rate=0.05, basic_living_cost=10.0),
        np.random.default_rng(0),
    )
    agent = dynamics._population[0]
    agent.energy = 100.0
    dynamics._accrue(0.5)
    assert agent.energy == pytest.approx(100.0 * 1.05**0.5 - 5.0)


def test_lone_survivor_event_consumes_no_rng() -> None:
    """The #81 corner in event-time: at N = 1 an event draws nothing.

    No focal, no partners, no match — but the clock still advances a full
    generation-equivalent and the living cost still bites.
    """
    dynamics = AsyncDynamics(_config(), np.random.default_rng(0))
    survivor = dynamics._population[0]
    dynamics._population = [survivor]
    for agent_id in list(dynamics._birth_time):
        if agent_id != survivor.agent_id:
            del dynamics._birth_time[agent_id]
            del dynamics._breeding_anchor[agent_id]
    survivor.energy = 30.0
    state_before = dynamics._rng.bit_generator.state
    report = dynamics._step_event(None)
    assert dynamics._rng.bit_generator.state == state_before
    assert dynamics.time == pytest.approx(1.0)
    # e ← 30·(1+0)^1 − 25·1 = 5: earned nothing, still paid the bill.
    assert survivor.energy == pytest.approx(5.0)
    assert report is not None  # crossing t = 1.0 emits the first period


# ---------------------------------------------------------------------------
# The clock, periods, and extinction (spec Designs 5 and 2)
# ---------------------------------------------------------------------------


def test_constant_population_clock_and_period_count() -> None:
    """With demographics inert, N events = one period at each integer."""
    config = _config(
        reproduction_threshold=1e9,
        offspring_stake=0.0,
        basic_living_cost=0.0,
        generations=3,
    )
    periods = [e for e in run(config) if isinstance(e, GenerationFinished)]
    assert [p.index for p in periods] == [0, 1, 2]
    for index, period in enumerate(periods):
        assert period.gen_equiv_time == pytest.approx(index + 1.0, abs=1e-6)
        assert sum(period.composition.values()) == 10
        assert set(period.mean_scores) <= set(period.composition)


def test_extinction_ends_async_run_early() -> None:
    """Insolvency wipes everyone → the run closes with #82 semantics."""
    config = ExperimentConfig.model_validate(
        {
            "seed": 5,
            "population": {"size": 4, "composition": {"always_defect": 4}},
            "matching": {"matcher": "random_k", "opponents_per_agent": 1},
            "match": {"length_mode": "fixed", "rounds_per_match": 2},
            "dynamics": {
                "generations": 10,
                "time_model": "asynchronous",
                "reproduction_threshold": 500.0,
                "offspring_stake": 400.0,
                "initial_energy": 50.0,
                "basic_living_cost": 100.0,
                "carrying_capacity": 100,
                "mutation_rate": 0.0,
            },
        }
    )
    events = list(run(config))
    final = events[-1]
    assert isinstance(final, RunFinished)
    assert final.composition == {}
    assert final.completed < 10
    deaths = [e for e in events if isinstance(e, DeathEvent)]
    assert len(deaths) == 4
    last_period = [e for e in events if isinstance(e, GenerationFinished)][-1]
    assert last_period.composition == {}
    assert last_period.agents == ()


def test_async_stream_feeds_run_timeseries() -> None:
    """Every async event folds into RunTimeseries without error.

    The mean_scores ⊆ composition key guarantee is what the accumulator's
    per-round arithmetic expects.
    """
    timeseries = RunTimeseries(mode="evolution")
    for event in run(_config()):
        timeseries.add(event)
    assert len(timeseries.periods) == 4
    assert timeseries.final is not None


# ---------------------------------------------------------------------------
# Config validation (#34: validate exactly what is consumed)
# ---------------------------------------------------------------------------


def test_async_consumes_k_regardless_of_matcher() -> None:
    """Under async, k is checked even with round_robin selected."""
    with pytest.raises(ValidationError, match="opponents"):
        ExperimentConfig.model_validate(
            {
                "population": {"size": 4, "composition": {"tit_for_tat": 4}},
                "matching": {"matcher": "round_robin", "opponents_per_agent": 9},
                "dynamics": {"time_model": "asynchronous"},
            }
        )
    # Synchronous round_robin still ignores k entirely (#34, unchanged).
    ExperimentConfig.model_validate(
        {
            "population": {"size": 4, "composition": {"tit_for_tat": 4}},
            "matching": {"matcher": "round_robin", "opponents_per_agent": 9},
        }
    )


def test_async_consumes_stake_threshold_and_capacity() -> None:
    """σ ≤ θ and K ≥ N are enforced under async.

    Even with imitation selected as the (ignored) reproduction mode — the
    async demographics consume both parameters regardless.
    """
    with pytest.raises(ValidationError, match="stake"):
        ExperimentConfig.model_validate(
            {
                "population": {"size": 4, "composition": {"tit_for_tat": 4}},
                "dynamics": {
                    "time_model": "asynchronous",
                    "offspring_stake": 600.0,
                    "reproduction_threshold": 500.0,
                },
            }
        )
    with pytest.raises(ValidationError, match="capacity"):
        ExperimentConfig.model_validate(
            {
                "population": {"size": 4, "composition": {"tit_for_tat": 4}},
                "matching": {"matcher": "random_k", "opponents_per_agent": 2},
                "dynamics": {"time_model": "asynchronous", "carrying_capacity": 2},
            }
        )
    # Synchronous imitation still ignores both (#34, unchanged).
    ExperimentConfig.model_validate(
        {
            "population": {"size": 4, "composition": {"tit_for_tat": 4}},
            "dynamics": {"offspring_stake": 600.0, "reproduction_threshold": 500.0},
        }
    )


# ---------------------------------------------------------------------------
# Phase B — the fixed_n Moran engine (spec Design 3)
# ---------------------------------------------------------------------------


def _moran_config(**dynamics_overrides: object) -> ExperimentConfig:
    """Build a small fixed_n Moran experiment (6 agents, k = 2, 4 rounds).

    Args:
        **dynamics_overrides: Dynamics field values to override.

    Returns:
        A validated async fixed_n config (seed 13) — the moran golden-master
        fixture.
    """
    data: dict[str, object] = {
        "generations": 2,
        "time_model": "asynchronous",
        "async_population": "fixed_n",
        "offspring_stake": 50.0,
        "reproduction_threshold": 60.0,
        "initial_energy": 100.0,
        "basic_living_cost": 10.0,
        "mutation_rate": 0.0,
    }
    data.update(dynamics_overrides)
    return ExperimentConfig.model_validate(
        {
            "seed": 13,
            "population": {
                "size": 6,
                "composition": {"tit_for_tat": 3, "always_defect": 3},
            },
            "matching": {"matcher": "random_k", "opponents_per_agent": 2},
            "match": {"length_mode": "fixed", "rounds_per_match": 4},
            "dynamics": data,
        }
    )


def test_moran_random_golden_trace() -> None:
    """The pinned moran-random master (V6, spec Design 8 fixed_n branch).

    ``moran_rule = "random"`` with weights 0.8/0.2, ``pure_random`` deaths,
    and μ = 0.1 — so the trace pins the rule roll's FIRST-draw position,
    the death/breeder draw order of both branches, and the μ draw's place
    at the tail. Values captured from the frozen Phase B contract; a
    mis-pinned or reordered draw cannot reproduce them.
    """
    config = _moran_config(
        moran_rule="random",
        moran_weight_birth_death=0.8,
        moran_weight_death_birth=0.2,
        fixed_n_death_rule="pure_random",
        mutation_rate=0.1,
    )
    expected_compositions = [
        (0, {"tit_for_tat": 3, "always_defect": 3}, 1.0),
        (1, {"tit_for_tat": 5, "always_defect": 1}, 2.0),
    ]
    expected_births = [
        (6, 3, "always_defect", 0.166667),
        (7, 4, "always_defect", 0.333333),
        (8, 3, "always_defect", 0.5),
        (9, 1, "tit_for_tat", 0.666667),
        (10, 9, "tit_for_tat", 0.833333),
        (11, 3, "always_defect", 1.0),
        (12, 10, "generous_tit_for_tat", 1.166667),
        (13, 10, "tit_for_tat", 1.333333),
        (14, 7, "always_defect", 1.5),
        (15, 2, "tit_for_tat", 1.666667),
        (16, 2, "tit_for_tat", 1.833333),
        (17, 16, "tit_for_tat", 2.0),
    ]
    expected_deaths = [
        (5, "random_moran", 0.166667),
        (0, "random_moran", 0.333333),
        (6, "replacement", 0.5),
        (8, "replacement", 0.666667),
        (4, "replacement", 0.833333),
        (1, "replacement", 1.0),
        (11, "replacement", 1.166667),
        (12, "replacement", 1.333333),
        (10, "replacement", 1.5),
        (14, "replacement", 1.666667),
        (9, "replacement", 1.833333),
        (3, "replacement", 2.0),
    ]
    compositions = []
    births = []
    deaths = []
    final = None
    for event in run(config):
        if isinstance(event, GenerationFinished):
            compositions.append(
                (event.index, dict(event.composition), round(event.gen_equiv_time, 6))
            )
        elif isinstance(event, BirthEvent):
            births.append(
                (event.agent_id, event.parent_id, event.strategy, round(event.gen_equiv_time, 6))
            )
        elif isinstance(event, DeathEvent):
            deaths.append((event.agent_id, event.cause, round(event.gen_equiv_time, 6)))
        elif isinstance(event, RunFinished):
            final = event
    assert compositions == expected_compositions
    assert births == expected_births
    assert deaths == expected_deaths
    assert final is not None
    assert final.completed == 2
    assert final.composition == {"tit_for_tat": 5, "always_defect": 1}
    # And the stream reproduces byte-for-byte (hard rule 5).
    assert list(run(config)) == list(run(config))


@pytest.mark.parametrize(
    ("moran_rule", "expected_cause"),
    [("death_birth", "random_moran"), ("birth_death", "replacement")],
)
def test_fixed_n_pins_population_and_causes(moran_rule: str, expected_cause: str) -> None:
    """N stays pinned, one replacement per event, causes name the slot.

    Every period's composition sums to the starting size, every death
    carries the rule's slot cause, every birth is ``"moran"``, and the run
    completes its full horizon — no extinction in fixed_n (spec Design 2).
    """
    config = _moran_config(moran_rule=moran_rule)
    births = 0
    deaths = 0
    final = None
    for event in run(config):
        if isinstance(event, GenerationFinished):
            assert sum(event.composition.values()) == 6
        elif isinstance(event, BirthEvent):
            births += 1
            assert event.cause == "moran"
        elif isinstance(event, DeathEvent):
            deaths += 1
            assert event.cause == expected_cause
        elif isinstance(event, RunFinished):
            final = event
    # 6 agents × 2 generation-equivalents = 12 events, one replacement each.
    assert births == deaths == 12
    assert final is not None
    assert final.completed == 2
    assert sum(final.composition.values()) == 6


def test_rule_roll_first_and_only_when_random() -> None:
    """The Design 8 fixed_n draw order, pinned by exact stream replay.

    With equal energies (uniform breeder fallback), ``energy_decides``
    deaths (no draw), and μ = 0, a ``death_birth`` step consumes exactly
    one ``choice(N-1)`` — and flipping the rule to ``"random"`` prepends
    exactly one ``random()`` roll (weights 0/1 make the roll always land
    on death_birth, so the rest of the stream is identical).
    """
    for rule_overrides, replay_roll in [
        ({"moran_rule": "death_birth"}, False),
        (
            {
                "moran_rule": "random",
                "moran_weight_birth_death": 0.0,
                "moran_weight_death_birth": 1.0,
            },
            True,
        ),
    ]:
        config = _moran_config(fixed_n_death_rule="energy_decides", **rule_overrides)
        dynamics = AsyncDynamics(config, np.random.default_rng(21))
        for agent in dynamics._population:
            agent.energy = 100.0
        state_before = dynamics._rng.bit_generator.state
        dynamics._moran_step()
        replay = np.random.default_rng(21)
        replay.bit_generator.state = state_before
        if replay_roll:
            replay.random()  # the rule roll — the FIRST demographic draw
        replay.choice(5)  # the breeder draw over the 5 remaining candidates
        assert dynamics._rng.bit_generator.state == replay.bit_generator.state
        # energy_decides on all-equal energies: tie to the lowest id.
        deaths = [e for e in dynamics._pending if isinstance(e, DeathEvent)]
        assert [(e.agent_id, e.cause) for e in deaths] == [(0, "random_moran")]


def test_energy_decides_picks_poorest_tie_to_lowest_id() -> None:
    """The deterministic death slot: lowest energy, ties to lowest id."""
    dynamics = AsyncDynamics(
        _moran_config(moran_rule="death_birth", fixed_n_death_rule="energy_decides"),
        np.random.default_rng(0),
    )
    energies = [50.0, 20.0, 20.0, 90.0, 90.0, 90.0]
    for agent, energy in zip(dynamics._population, energies, strict=True):
        agent.energy = energy
    dynamics._moran_step()
    deaths = [e for e in dynamics._pending if isinstance(e, DeathEvent)]
    assert [(e.agent_id, e.cause) for e in deaths] == [(1, "random_moran")]


def test_proportional_parent_shift_and_fallback() -> None:
    """The #63 fitness idiom: shifted weights, worst never drawn.

    With two candidates the poorer one carries weight 0 and the richer is
    drawn with certainty — including when both balances are negative (the
    shift absorbs them). All-equal energies fall back to a uniform draw
    that still lands on a candidate.
    """
    dynamics = AsyncDynamics(_moran_config(), np.random.default_rng(4))
    poor, rich = dynamics._population[0], dynamics._population[1]
    for energies in [(5.0, 10.0), (-10.0, -5.0)]:
        poor.energy, rich.energy = energies
        for _ in range(10):
            assert dynamics._proportional_parent([poor, rich]) is rich
    poor.energy = rich.energy = 7.0
    assert dynamics._proportional_parent([poor, rich]) in (poor, rich)


def test_fixed_n_place_before_pay(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blocked placement never charges σ — the seam holds in fixed_n too."""
    monkeypatch.setattr(async_module, "place_offspring", lambda population, parent: False)
    dynamics = AsyncDynamics(
        _moran_config(moran_rule="death_birth", fixed_n_death_rule="energy_decides"),
        np.random.default_rng(0),
    )
    next_id_before = dynamics._next_id
    dynamics._moran_step()
    assert all(agent.energy == 100.0 for agent in dynamics._population)
    assert not any(isinstance(e, BirthEvent) for e in dynamics._pending)
    assert dynamics._next_id == next_id_before


def test_fixed_n_parent_may_go_negative_and_relaxed_gates() -> None:
    """A stake-driven negative balance is legal in fixed_n (spec Design 3).

    σ > θ and K < N are both accepted under fixed_n (the Phase B validator
    refinement — neither θ nor K is consumed), the parent that pays σ from
    a smaller balance goes negative and SURVIVES (no insolvency death in
    fixed_n), and every death in a full run carries a Moran slot cause.
    """
    config = ExperimentConfig.model_validate(
        {
            "seed": 2,
            "population": {"size": 2, "composition": {"tit_for_tat": 1, "always_defect": 1}},
            "matching": {"matcher": "random_k", "opponents_per_agent": 1},
            "match": {"length_mode": "fixed", "rounds_per_match": 2},
            "dynamics": {
                "generations": 2,
                "time_model": "asynchronous",
                "async_population": "fixed_n",
                "moran_rule": "birth_death",  # the breeder survives its stake
                "offspring_stake": 500.0,
                "reproduction_threshold": 100.0,  # σ > θ: legal in fixed_n
                "carrying_capacity": 1,  # K < N: ignored in fixed_n
                "initial_energy": 100.0,
                "basic_living_cost": 0.0,
                "mutation_rate": 0.0,
            },
        }
    )
    dynamics = AsyncDynamics(config, np.random.default_rng(config.seed))
    dynamics._step_event(None)
    # One replacement happened; whoever bred paid σ = 500 from ≈ 100 + match
    # income and is still standing at a negative balance.
    assert len(dynamics._population) == 2
    assert any(agent.energy < 0 for agent in dynamics._population)
    for event in run(config):
        if isinstance(event, DeathEvent):
            assert event.cause in ("random_moran", "replacement")


# ---------------------------------------------------------------------------
# Phase B — variable_n's mortality trio in event-time (spec Design 2a)
# ---------------------------------------------------------------------------


def _mortality_config(**dynamics_overrides: object) -> ExperimentConfig:
    """Build a small variable_n config with births/insolvency switched off.

    Four tit-for-tat founders, k = 1, zero living cost, unreachable θ — so
    the only demographics left are whatever mortality settings the
    overrides switch on.

    Args:
        **dynamics_overrides: Dynamics field values to override.

    Returns:
        A validated async variable_n config (seed 5).
    """
    data: dict[str, object] = {
        "generations": 5,
        "time_model": "asynchronous",
        "reproduction_threshold": 1e9,
        "offspring_stake": 0.0,
        "basic_living_cost": 0.0,
        "carrying_capacity": 100,
        "mutation_rate": 0.0,
    }
    data.update(dynamics_overrides)
    return ExperimentConfig.model_validate(
        {
            "seed": 5,
            "population": {"size": 4, "composition": {"tit_for_tat": 4}},
            "matching": {"matcher": "random_k", "opponents_per_agent": 1},
            "match": {"length_mode": "fixed", "rounds_per_match": 2},
            "dynamics": data,
        }
    )


def test_birthday_hazard_certain_death() -> None:
    """At base_hazard = 1, every founder dies at its first birthday.

    The birthday-coin conversion: the coin for crossing birthday 1 prices
    p(0) = 1, so all four founders (unstaggered — no age cap) die at the
    event that crosses t = 1, cause ``"age"``, and the run goes extinct.
    """
    config = _mortality_config(base_hazard=1.0)
    deaths = []
    final = None
    for event in run(config):
        if isinstance(event, DeathEvent):
            deaths.append((event.agent_id, event.cause, round(event.gen_equiv_time, 6)))
        elif isinstance(event, RunFinished):
            final = event
    assert deaths == [(i, "age", 1.0) for i in range(4)]
    assert final is not None
    assert final.composition == {}


def test_age_cap_deterministic_with_staggered_founders() -> None:
    """The max_age cap fires the moment an age reaches it — no coin needed.

    With base_hazard = 0 and max_age = 3, the hazard coins are drawn (the
    active flag is on) but never kill; founders are staggered to ages
    [0, 1, 2, 0] via negative birth times, so they die of the cap in
    stagger order at exactly t = 3 − s each — including id 2, which
    survives its p(2) = 0 birthday coin at t = 1 and dies of the cap in
    the same event.
    """
    config = _mortality_config(max_age=3)
    deaths = []
    for event in run(config):
        if isinstance(event, DeathEvent):
            deaths.append((event.agent_id, event.cause, round(event.gen_equiv_time, 6)))
    assert deaths == [
        (2, "age", 1.0),
        (1, "age", 2.0),
        (0, "age", 3.0),
        (3, "age", 3.0),
    ]


def test_birthday_coin_consumed_even_at_p_zero() -> None:
    """The #80 active-flag idiom in event-time: the coin is unconditional.

    A lone survivor's event draws nothing for matches (N = 1), but with
    age-mortality active its birthday crossing costs exactly one
    ``rng.random()`` — even at hazard 0, where the coin cannot kill.
    """
    dynamics = AsyncDynamics(_config(max_age=50), np.random.default_rng(0))
    survivor = dynamics._population[0]  # stagger 0: birth_time 0, age 0
    dynamics._population = [survivor]
    for agent_id in list(dynamics._birth_time):
        if agent_id != survivor.agent_id:
            del dynamics._birth_time[agent_id]
            del dynamics._breeding_anchor[agent_id]
    survivor.energy = 40.0  # below θ = 60: no birth muddies the count
    state_before = dynamics._rng.bit_generator.state
    dynamics._step_event(None)
    replay = np.random.default_rng(0)
    replay.bit_generator.state = state_before
    replay.random()  # the one birthday coin (crossing age 1, p(0) = 0)
    assert dynamics._rng.bit_generator.state == replay.bit_generator.state
    assert dynamics._population == [survivor]  # the coin spared it


def test_founder_staggering_only_when_mortality_active() -> None:
    """Staggering keys off the active flag, and anchors stay at t = 0.

    With max_age set, founder birth times go negative in stagger order
    (ages start at the demographic steady state); with mortality off they
    all start at 0 — the Phase A behaviour, untouched. Breeding-refractory
    anchors stay at 0 either way (staggering is an AGE construct).
    """
    staggered = AsyncDynamics(_mortality_config(max_age=3), np.random.default_rng(0))
    birth_times = [staggered._birth_time[a.agent_id] for a in staggered._population]
    assert birth_times == [0.0, -1.0, -2.0, 0.0]
    assert [a.age for a in staggered._population] == [0, 1, 2, 0]
    assert all(anchor == 0.0 for anchor in staggered._breeding_anchor.values())
    plain = AsyncDynamics(_mortality_config(), np.random.default_rng(0))
    assert all(t == 0.0 for t in plain._birth_time.values())
    assert [a.age for a in plain._population] == [0, 0, 0, 0]


# ---------------------------------------------------------------------------
# Phase B — the new validator gates (#34: validate exactly what is consumed)
# ---------------------------------------------------------------------------


def test_moran_weights_both_zero_rejected_only_when_consumed() -> None:
    """The weight pair rejects both-zero exactly when the roll can happen."""

    def build(**settings: object) -> dict[str, object]:
        dynamics: dict[str, object] = {
            "time_model": "asynchronous",
            "async_population": "fixed_n",
            "moran_rule": "random",
            "moran_weight_birth_death": 0.0,
            "moran_weight_death_birth": 0.0,
        }
        mode = settings.pop("mode", "evolution")
        dynamics.update(settings)
        return {
            "mode": mode,
            "population": {"size": 4, "composition": {"tit_for_tat": 4}},
            "matching": {"matcher": "random_k", "opponents_per_agent": 2},
            "dynamics": dynamics,
        }

    with pytest.raises(ValidationError, match="nothing to roll"):
        ExperimentConfig.model_validate(build())
    # Not consumed: a fixed rule, the variable_n engine, the synchronous
    # clock, or tournament mode — all valid (#34).
    ExperimentConfig.model_validate(build(moran_rule="death_birth"))
    ExperimentConfig.model_validate(build(async_population="variable_n"))
    ExperimentConfig.model_validate(build(time_model="synchronous"))
    ExperimentConfig.model_validate(build(mode="tournament"))


# ---------------------------------------------------------------------------
# Phase C — the imitation overlay (spec Design 4, draw order Design 8 step 3)
# ---------------------------------------------------------------------------


def _imitation_config(
    composition: dict[str, int] | None = None, **dynamics_overrides: object
) -> ExperimentConfig:
    """Build an async config whose ONLY dynamics is the imitation overlay.

    Six agents, k = 2, 4 fixed rounds, no noise — and demographics switched
    off from every side (unreachable θ, zero living cost, mortality off, K
    far above N), so nobody is born and nobody dies. What remains is the
    cultural channel alone: the V2 configuration, in test form.

    Args:
        composition: Starting strategy mix; defaults to six tit-for-tats
            (a homogeneous population, where every copy is a no-op).
        **dynamics_overrides: Dynamics field values to override.

    Returns:
        A validated async config with the overlay ON (seed 11).
    """
    data: dict[str, object] = {
        "generations": 3,
        "time_model": "asynchronous",
        "imitation_overlay": True,
        "reproduction_threshold": 1e9,
        "offspring_stake": 0.0,
        "basic_living_cost": 0.0,
        "carrying_capacity": 100,
        "mutation_rate": 0.0,
    }
    data.update(dynamics_overrides)
    return ExperimentConfig.model_validate(
        {
            "seed": 11,
            "population": {"size": 6, "composition": composition or {"tit_for_tat": 6}},
            "matching": {"matcher": "random_k", "opponents_per_agent": 2},
            "match": {"length_mode": "fixed", "rounds_per_match": 4},
            "dynamics": data,
        }
    )


def _tied_match(agent_a: Agent, agent_b: Agent) -> MatchResult:
    """Fabricate a finished match both participants tied in.

    Args:
        agent_a: One participant.
        agent_b: The other.

    Returns:
        A transcript-free :class:`MatchResult` with equal totals — the
        exact-tie corner the lower-id tie-break governs.
    """
    return MatchResult(
        agent_ids=(agent_a.agent_id, agent_b.agent_id),
        total_payoffs={agent_a.agent_id: 12.0, agent_b.agent_id: 12.0},
        rounds=(),
    )


def test_imitation_coin_is_one_unconditional_draw_per_match() -> None:
    """Design 8 step 3, pinned by exact stream replay.

    A homogeneous population makes every copy a no-op — and the coins are
    drawn anyway (the #80 active-flag idiom: the stream depends on the
    flag and the match schedule, never on strategy states). With
    deterministic strategies, no noise, fixed rounds and no demographics,
    one event's ENTIRE draw list is: the focal draw, the partner draw, and
    exactly k adoption coins, in that order.
    """
    dynamics = AsyncDynamics(_imitation_config(), np.random.default_rng(3))
    state_before = dynamics._rng.bit_generator.state
    dynamics._step_event(None)
    replay = np.random.default_rng(3)
    replay.bit_generator.state = state_before
    replay.integers(6)  # the focal draw
    replay.choice(5, size=2, replace=False)  # the partner draw (k = 2)
    replay.random()  # match 1's adoption coin
    replay.random()  # match 2's adoption coin
    assert dynamics._rng.bit_generator.state == replay.bit_generator.state
    # Every copy was a no-op, so the coins produced no events at all.
    assert dynamics._pending == []


def test_overlay_off_draws_no_coin() -> None:
    """Off by default, silent by default — what keeps the masters valid.

    The same event with the overlay off consumes the focal and partner
    draws and nothing else, so the Phase A and Phase B golden traces
    (which run with the overlay off) cannot shift.
    """
    dynamics = AsyncDynamics(_imitation_config(imitation_overlay=False), np.random.default_rng(3))
    state_before = dynamics._rng.bit_generator.state
    dynamics._step_event(None)
    replay = np.random.default_rng(3)
    replay.bit_generator.state = state_before
    replay.integers(6)
    replay.choice(5, size=2, replace=False)
    assert dynamics._rng.bit_generator.state == replay.bit_generator.state


def test_adopter_is_the_lower_scorer_not_the_lower_id() -> None:
    """Score, not identity, decides who considers switching.

    The lower-id agent wins the match by a wide margin, so at a high β the
    coin lands with near-certainty on the HIGHER-id agent adopting — the
    reverse of what an id-based rule would produce.
    """
    dynamics = AsyncDynamics(
        _imitation_config({"tit_for_tat": 3, "always_defect": 3}, selection_beta=10.0),
        np.random.default_rng(0),
    )
    winner = dynamics._population[0]
    loser = dynamics._population[5]
    winner.strategy = create_strategy("always_defect")
    loser.strategy = create_strategy("tit_for_tat")
    result = MatchResult(
        agent_ids=(winner.agent_id, loser.agent_id),
        total_payoffs={winner.agent_id: 20.0, loser.agent_id: 1.0},
        rounds=(),
    )
    dynamics._imitate(result, winner, loser)
    assert strategy_name_of(loser.strategy) == "always_defect"
    assert strategy_name_of(winner.strategy) == "always_defect"  # untouched
    events = [e for e in dynamics._pending if isinstance(e, ImitationEvent)]
    assert [(e.agent_id, e.from_strategy, e.to_strategy, e.source_agent_id) for e in events] == [
        (5, "tit_for_tat", "always_defect", 0)
    ]


def test_exact_tie_makes_the_lower_id_the_adopter() -> None:
    """The tie-break is deterministic (principle 5), never a second draw.

    On an exact score tie the gap is 0, so the coin is a fair one — but
    only ever for the LOWER-id agent: over many tied matches the higher-id
    agent never changes strategy, whichever argument position it occupies.
    """
    dynamics = AsyncDynamics(
        _imitation_config({"tit_for_tat": 3, "always_defect": 3}),
        np.random.default_rng(1),
    )
    low, high = dynamics._population[0], dynamics._population[5]
    result = _tied_match(low, high)
    adoptions = 0
    for _ in range(50):
        low.strategy = create_strategy("tit_for_tat")
        high.strategy = create_strategy("always_defect")
        # Argument order deliberately reversed: the rule reads totals and
        # ids, not who was focal.
        dynamics._imitate(result, high, low)
        assert strategy_name_of(high.strategy) == "always_defect"
        if strategy_name_of(low.strategy) == "always_defect":
            adoptions += 1
    # A fair coin at gap 0: both outcomes occur (and the count is pinned by
    # the seed, so this is deterministic, not flaky).
    assert 0 < adoptions < 50


def test_no_event_when_the_copy_changes_nothing() -> None:
    """The coin is the RNG contract; the event is not (spec Design 4).

    Two agents already playing the same strategy still spend a coin, and
    still emit nothing — a no-op copy is not an :class:`ImitationEvent`.
    """
    dynamics = AsyncDynamics(_imitation_config(selection_beta=10.0), np.random.default_rng(2))
    first, second = dynamics._population[0], dynamics._population[1]
    result = MatchResult(
        agent_ids=(first.agent_id, second.agent_id),
        total_payoffs={first.agent_id: 20.0, second.agent_id: 1.0},
        rounds=(),
    )
    state_before = dynamics._rng.bit_generator.state
    dynamics._imitate(result, first, second)
    replay = np.random.default_rng(2)
    replay.bit_generator.state = state_before
    replay.random()  # the coin was spent even though the copy is a no-op
    assert dynamics._rng.bit_generator.state == replay.bit_generator.state
    assert dynamics._pending == []


def test_adopted_strategy_plays_in_the_next_match_of_the_bundle() -> None:
    """Immediacy — what asynchrony means (spec Design 0).

    A strategy copied after one match is what plays in the next match of
    the same focal bundle: the cooperator adopts always-defect after
    losing match 1, and match 2 against a second defector is therefore
    mutual defection, not exploitation.
    """
    dynamics = AsyncDynamics(
        _imitation_config(
            {"always_cooperate": 1, "always_defect": 5},
            selection_beta=10.0,
        ),
        np.random.default_rng(0),
    )
    focal = dynamics._population[0]
    first, second = dynamics._population[1], dynamics._population[2]
    assert strategy_name_of(focal.strategy) == "always_cooperate"
    result = dynamics._match.play(focal, first)
    dynamics._imitate(result, focal, first)
    assert strategy_name_of(focal.strategy) == "always_defect"
    # The very next match of the bundle is played by the NEW strategy.
    second_result = dynamics._match.play(focal, second)
    assert second_result.total_payoffs[focal.agent_id] == pytest.approx(
        second_result.total_payoffs[second.agent_id]
    )
    assert all(record.actions[focal.agent_id].name == "DEFECT" for record in second_result.rounds)


def test_v2_shares_move_while_the_population_stays_flat() -> None:
    """V2's cultural/demographic split, in engine terms.

    With demographics switched off entirely, an overlay run changes WHAT
    the population plays without changing WHO it is: strategy shares move,
    the head-count never does, and not a single birth or death event is
    emitted (so a run's ``total_agents_born`` stays at the founder count).
    """
    config = _imitation_config({"tit_for_tat": 3, "always_defect": 3}, selection_beta=5.0)
    compositions = []
    imitations = 0
    for event in run(config):
        if isinstance(event, GenerationFinished):
            compositions.append(dict(event.composition))
        elif isinstance(event, ImitationEvent):
            imitations += 1
            assert event.from_strategy != event.to_strategy
        elif isinstance(event, (BirthEvent, DeathEvent)):
            pytest.fail(f"the overlay is not demographic, but emitted {event!r}")
    assert imitations > 0
    assert all(sum(c.values()) == 6 for c in compositions)
    # The mix actually moved off its starting 3/3 at some point.
    assert any(c != {"tit_for_tat": 3, "always_defect": 3} for c in compositions)


def test_overlay_layers_on_fixed_n_too() -> None:
    """Both channels at once: Moran demography plus cultural copying.

    The overlay is not a fourth Moran rule — it rides on top of one, so a
    fixed_n run emits its replacements AND its imitations, with N pinned
    throughout (spec Design 4).
    """
    config = _moran_config(imitation_overlay=True, selection_beta=5.0, moran_rule="death_birth")
    births = deaths = imitations = 0
    for event in run(config):
        if isinstance(event, GenerationFinished):
            assert sum(event.composition.values()) == 6
        elif isinstance(event, BirthEvent):
            births += 1
        elif isinstance(event, DeathEvent):
            deaths += 1
        elif isinstance(event, ImitationEvent):
            imitations += 1
    assert births == deaths == 12
    assert imitations > 0


def test_overlay_run_is_reproducible() -> None:
    """Same config + seed → byte-identical streams, overlay included."""
    config = _imitation_config({"tit_for_tat": 3, "always_defect": 3}, selection_beta=5.0)
    assert list(run(config)) == list(run(config))
