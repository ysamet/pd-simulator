"""Tests for the M10b Phase A async engine core (spec Designs 0, 2a, 5, 8, 9).

Covers the V6 RNG golden-master (a fixed seed reproduces an async run
byte-for-byte, plus a pinned trace so a mis-pinned draw order fails loudly),
the V7 synchronous regression (sync streams gain nothing), the Option B
seam contracts (two orderings, place-before-pay), the breeding refractory,
the event-time ledger, and the #81 lone-survivor corner in event-time.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest
from pydantic import ValidationError

from pdsim.config.experiment import ExperimentConfig
from pdsim.core import async_dynamics as async_module
from pdsim.core.async_dynamics import AsyncDynamics
from pdsim.core.engine import run
from pdsim.core.events import (
    BirthEvent,
    DeathEvent,
    GenerationFinished,
    ImitationEvent,
    RunFinished,
)
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
