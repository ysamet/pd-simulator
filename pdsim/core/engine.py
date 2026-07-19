"""The engine: turn a config into a stream of typed events (DESIGN §3-§4).

:func:`run` is the one entry point every consumer shares. It is a
*generator*: it yields :mod:`~pdsim.core.events` values as the run unfolds,
so the CLI, the recorder (M7), and the live UI (M6) are all just ``for
event in run(config):`` loops that react to the event types they care about.

Granularity is an **observer** concern, not a model parameter (DECISIONS
#35): it controls only which events are *emitted*, never how the simulation
runs, so the same config + seed produces byte-identical results at every
granularity. That is why it is an argument to :func:`run` and deliberately
NOT in the Parameter Registry or ``ExperimentConfig``.

The engine owns turning ``config.seed`` into the run's single numpy
``Generator`` (hard rules 5 and 8). Code that drives the dynamics classes
directly (tests, notebooks) injects its own generator instead.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Literal, get_args

import numpy as np

from pdsim.config.experiment import ExperimentConfig
from pdsim.core.async_dynamics import AsyncDynamics
from pdsim.core.dynamics import EconomyDynamics, PopulationDynamics, TournamentDynamics
from pdsim.core.events import (
    CycleFinished,
    Event,
    GenerationFinished,
    MatchFinished,
    RoundPlayed,
    RunFinished,
)
from pdsim.core.match import MatchResult

Granularity = Literal["round", "match", "generation"]
"""The finest event level to emit; coarser events are always emitted.

``"generation"`` (the default, and the coarsest) also means "cycle" in
tournament mode — the period-level event of whichever mode is running.
"""


def run(config: ExperimentConfig, granularity: Granularity = "generation") -> Iterator[Event]:
    """Run one experiment, yielding events as it progresses.

    Event order: at fine granularities, each generation/cycle's
    ``RoundPlayed``/``MatchFinished`` events arrive in play order (a match's
    rounds, then its ``MatchFinished``, then the next match), followed by
    that period's ``GenerationFinished``/``CycleFinished``. A single
    ``RunFinished`` always closes the stream. Memory note: fine-granularity
    events are buffered one generation/cycle at a time, so "round" with a
    large population holds one generation's worth of round events in memory.

    Args:
        config: The complete, validated experiment description; its ``mode``
            decides which loop runs.
        granularity: Finest event level to emit — ``"round"``, ``"match"``,
            or ``"generation"`` (default; period-level events only).

    Yields:
        Typed events, finishing with exactly one :class:`RunFinished`.

    Raises:
        ValueError: If ``granularity`` is not one of the three levels.
    """
    if granularity not in get_args(Granularity):
        raise ValueError(
            f"Unknown granularity {granularity!r}; expected one of {get_args(Granularity)}."
        )
    rng = np.random.default_rng(config.seed)
    if config.mode == "tournament":
        # time_model is ignored in tournament mode (#34): a tournament has
        # no demography, so there is nothing for an event-time clock to do.
        yield from _run_tournament(config, rng, granularity)
    elif config.dynamics.time_model == "asynchronous":
        yield from _run_async(config, rng, granularity)
    else:
        yield from _run_evolution(config, rng, granularity)


def _match_events(result: MatchResult, granularity: Granularity) -> Iterator[Event]:
    """Translate one finished match into fine-grained events.

    Args:
        result: The match transcript from :class:`~pdsim.core.match.Match`.
        granularity: Decides whether per-round events are included.

    Yields:
        ``RoundPlayed`` per round (at "round" granularity), then one
        ``MatchFinished``.
    """
    if granularity == "round":
        for index, record in enumerate(result.rounds):
            yield RoundPlayed(
                agent_ids=result.agent_ids,
                round_index=index,
                actions=record.actions,
                payoffs=record.payoffs,
            )
    yield MatchFinished(
        agent_ids=result.agent_ids,
        total_payoffs=result.total_payoffs,
        n_rounds=result.n_rounds,
    )


def _run_evolution(
    config: ExperimentConfig, rng: np.random.Generator, granularity: Granularity
) -> Iterator[Event]:
    """Drive the evolution loop, emitting events per generation.

    Dispatches on ``config.dynamics.reproduction_mode`` (M10a):
    :class:`PopulationDynamics` for ``"imitation"``,
    :class:`EconomyDynamics` for ``"energy_economy"``. An economy run can
    end EARLY at extinction — a legitimate outcome of a metabolic filter,
    not an error — so ``RunFinished.completed`` counts the generations
    actually played, and an extinct run closes with empty composition and
    scores. Under imitation the population never empties, so ``completed``
    always equals ``config.dynamics.generations`` and the stream is
    byte-identical to pre-M10a runs.

    Args:
        config: The experiment description.
        rng: The run's seeded generator.
        granularity: Finest event level to emit.

    Yields:
        Match-level events (if requested), ``GenerationFinished`` per
        generation, and the closing ``RunFinished``.
    """
    dynamics: PopulationDynamics | EconomyDynamics
    if config.dynamics.reproduction_mode == "energy_economy":
        dynamics = EconomyDynamics(config, rng)
    else:
        dynamics = PopulationDynamics(config, rng)
    buffer: list[Event] = []
    on_match = None
    if granularity != "generation":

        def on_match(result: MatchResult) -> None:
            """Buffer one match's events until the generation completes."""
            buffer.extend(_match_events(result, granularity))

    # The registry guarantees generations >= 1, so `report` is always bound
    # by the time RunFinished is built.
    completed = 0
    for _ in range(config.dynamics.generations):
        report = dynamics.step(on_match=on_match)
        completed += 1
        yield from buffer
        buffer.clear()
        yield GenerationFinished(
            index=report.index,
            composition=report.composition,
            mean_scores=report.mean_scores,
            rounds_played=report.rounds_played,
            cooperation=report.cooperation,
            agents=report.agents,
        )
        if not dynamics.population:
            break  # extinction: the run ends here (economy mode only)
    extinct = not dynamics.population
    yield RunFinished(
        mode="evolution",
        completed=completed,
        composition={} if extinct else report.composition,
        mean_scores={} if extinct else report.mean_scores,
        total_scores=None,
    )


def _run_async(
    config: ExperimentConfig, rng: np.random.Generator, granularity: Granularity
) -> Iterator[Event]:
    """Drive the asynchronous event-time loop (M10b), emitting per period.

    The period grain is the recording cadence (per generation-equivalent in
    Phase A), not the generation: each period yields its buffered
    fine-grained events (if requested), then its explicit demographic
    events in occurrence order (always — they are period-level truth,
    spec Design 7), then the period's ``GenerationFinished`` with
    ``gen_equiv_time`` stamped. ``RunFinished.completed`` counts the
    period-level events emitted — its grain follows the cadence
    (documented in the M10b spec). Extinction ends the run early with the
    #82 semantics.

    Args:
        config: The experiment description.
        rng: The run's seeded generator.
        granularity: Finest event level to emit.

    Yields:
        Match-level events (if requested), demographic events,
        ``GenerationFinished`` per recording period, and the closing
        ``RunFinished``.
    """
    dynamics = AsyncDynamics(config, rng)
    buffer: list[Event] = []
    on_match = None
    if granularity != "generation":

        def on_match(result: MatchResult) -> None:
            """Buffer one match's events until the period completes."""
            buffer.extend(_match_events(result, granularity))

    completed = 0
    report = None
    for report in dynamics.run(on_match=on_match):
        completed += 1
        yield from buffer
        buffer.clear()
        yield from report.demographic_events
        yield GenerationFinished(
            index=report.index,
            composition=report.composition,
            mean_scores=report.mean_scores,
            rounds_played=report.rounds_played,
            cooperation=report.cooperation,
            agents=report.agents,
            gen_equiv_time=report.gen_equiv_time,
        )
    # At least one period always emits (generations >= 1 guarantees the
    # clock crosses 1.0 or the run went extinct with a final partial
    # period), so `report` is bound; the guard is belt-and-braces.
    extinct = not dynamics.population
    yield RunFinished(
        mode="evolution",
        completed=completed,
        composition={} if extinct or report is None else report.composition,
        mean_scores={} if extinct or report is None else report.mean_scores,
        total_scores=None,
    )


def _run_tournament(
    config: ExperimentConfig, rng: np.random.Generator, granularity: Granularity
) -> Iterator[Event]:
    """Drive the tournament loop, emitting events per cycle.

    Args:
        config: The experiment description.
        rng: The run's seeded generator.
        granularity: Finest event level to emit.

    Yields:
        Match-level events (if requested), ``CycleFinished`` per cycle, and
        the closing ``RunFinished``.
    """
    dynamics = TournamentDynamics(config, rng)
    buffer: list[Event] = []
    on_match = None
    if granularity != "generation":

        def on_match(result: MatchResult) -> None:
            """Buffer one match's events until the cycle completes."""
            buffer.extend(_match_events(result, granularity))

    for _ in range(config.tournament_cycles):
        report = dynamics.step(on_match=on_match)
        yield from buffer
        buffer.clear()
        yield CycleFinished(
            index=report.index,
            composition=report.composition,
            total_scores=report.total_scores,
            mean_scores=report.mean_scores,
            rounds_played=report.rounds_played,
            cooperation=report.cooperation,
        )
    yield RunFinished(
        mode="tournament",
        completed=config.tournament_cycles,
        composition=report.composition,
        mean_scores=report.mean_scores,
        total_scores=report.total_scores,
    )
