"""The asynchronous event-time run loop (M10b, spec Designs 0-5 and 8-9).

:class:`AsyncDynamics` dissolves the generation as the unit of time
(DECISIONS #85): time advances one **event** at a time, where one event is
one *focal activation* — a focal agent is drawn, plays its
``matching.opponents_per_agent`` (k) matches against uniformly drawn
partners, and the consequences fire immediately. The clock advances by
``1/N(t)`` per event (N read at event start), so N events ≈ one
**generation-equivalent** — the unit the charts, the run length
(``dynamics.generations``), and the sync-vs-async comparison all share.
The k-match bundle keeps *income* comparable too: over one
generation-equivalent each agent is focal once on average and drawn ≈ k
times — the same ≈ 2k interaction budget as a synchronous ``random_k``
generation (spec Design 0).

Phase A scope: the event loop, the clock, the event-time ledger, and
``variable_n``'s deterministic demographic core (insolvency deaths and
θ-births through the Option B seam — ``admit_births`` /
``place_offspring``, DECISIONS #89b). The mortality trio, ``fixed_n``
Moran replacement, and the imitation overlay arrive in later phases of the
M10b spec.

RNG draw order per event (spec Design 8; the reproducibility contract —
any change is a breaking change requiring a DECISIONS entry):

    1. the focal draw — one ``rng.integers(N)`` (skipped entirely at
       N = 1: no partner exists, no pair draws are consumed — the #81
       lone-survivor thermodynamics in event-time),
    2. the partner draw — one ``rng.choice(N-1, size=min(k, N-1),
       replace=False)`` over the focal's others (the RandomK idiom + #81
       clamp), skip-mapped around the focal; partners are met in drawn
       order,
    3. per match, in partner order: the #23 per-round match draws,
       unchanged,
    4. the accrual sweep and the demographic step — deterministic except
       one μ-mutation draw per admitted parent, taken in ascending
       PARENT-id order (the #80 two-orderings contract, verbatim:
       ``admit_births`` decides *the set* by energy priority; id order is
       the RNG contract),
    5. clock arithmetic, recording, and period emission — no RNG (#35).

The ledger in event-time (spec Design 2a): match income and the per-match
``engagement_cost`` are applied at match completion; ``basic_living_cost``
accrues as ``L·Δt`` and capital returns compound as ``(1+r)^Δt`` in a
per-event sweep over every living agent in ascending id order — ≈ L and
(1+r) per generation-equivalent. Insolvency stays **strictly negative**
(#80). Births need ``e ≥ θ`` AND a clear **breeding refractory period** of
1.0 time units since the parent's last birth (founders: since t = 0) — the
event-time image of #80's one-birth-per-generation rule, keeping the
dynastic channel in breeding frequency, not endowment.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import numpy as np

from pdsim.config.experiment import ExperimentConfig
from pdsim.core.agent import Agent

# Intra-package reuse of the shared per-window tally (same package, same
# maintenance boundary); the underscore marks it internal to the engine, not
# to this module.
from pdsim.core.dynamics import GenerationReport, _CooperationTally, build_initial_population
from pdsim.core.economy import admit_births, place_offspring
from pdsim.core.events import AgentSnapshot, BirthEvent, DeathEvent, DemographicEvent
from pdsim.core.game import PrisonersDilemma
from pdsim.core.match import Match, MatchResult
from pdsim.core.reproduction import StrategySwitchReproduction
from pdsim.core.strategies import strategy_name_of

_EPS = 1e-9
"""Float tolerance for clock comparisons.

The clock is a running sum of ``1/N`` terms, so integer crossings land a
hair off exact integers; every ≥-comparison against the clock allows this
slack so a boundary is never missed (or double-counted) to float noise.
"""


class AsyncDynamics:
    """Runs the asynchronous event-time loop (M10b, spec Design 0).

    A sibling of :class:`~pdsim.core.dynamics.EconomyDynamics` on a
    different clock: same ledger, same passport-id lineage, same Option B
    seam (``admit_births`` / ``place_offspring``) — but births and deaths
    fire per event instead of at a generation boundary, and the run's
    period grain is the recording cadence, not the generation.

    Invariant (M10a, unchanged): ``self._population`` is ALWAYS in
    ascending ``agent_id`` order — deaths make ids non-contiguous, so list
    position is never a proxy for id.
    """

    def __init__(self, config: ExperimentConfig, rng: np.random.Generator) -> None:
        """Set up a run: collaborators, founders, clocks, and window state.

        Args:
            config: The complete, validated experiment description.
            rng: The run's single seeded random generator (hard rule 5).
        """
        self._config = config
        self._dynamics = config.dynamics
        self._rng = rng
        self._match = Match(PrisonersDilemma(config.game), config.match, rng)
        self._reproduction = StrategySwitchReproduction(config)
        self._k = config.matching.opponents_per_agent
        founders = build_initial_population(config)
        for agent in founders:
            agent.energy = self._dynamics.initial_energy
            agent.age = 0
            agent.parent_id = None
        self._population = founders
        # Monotonic passport counter (M10a): ids are never reused.
        self._next_id = len(founders)
        # The generation-equivalent clock (spec Design 5) and event counter.
        self._time = 0.0
        self._event_index = 0
        # Per-agent event-time bookkeeping, keyed by passport id: when the
        # agent was born (ages are derived: age = floor(now - birth_time))
        # and the refractory anchor (birth, or last breeding). Founders
        # anchor at t = 0 — first eligible from t ≥ 1, like a synchronous
        # founder at boundary 1.
        self._birth_time: dict[int, float] = {a.agent_id: 0.0 for a in founders}
        self._breeding_anchor: dict[int, float] = {a.agent_id: 0.0 for a in founders}
        # Recording state: period index, next integer boundary (Phase A
        # emits at the per_generation_equivalent cadence), and the window
        # accumulators the period report is built from.
        self._period = 0
        self._next_boundary = 1.0
        self._window_payoff: dict[str, float] = {}
        self._window_rounds: dict[str, int] = {}
        self._window_cooperation = _CooperationTally()
        self._window_events = 0
        self._pending: list[DemographicEvent] = []

    @property
    def population(self) -> tuple[Agent, ...]:
        """The current population, in ascending agent-id order.

        Returns:
            An immutable snapshot (the agents themselves are live objects);
            empty after extinction.
        """
        return tuple(self._population)

    @property
    def time(self) -> float:
        """The generation-equivalent clock (spec Design 5).

        Returns:
            The running sum of ``1/N(t)`` over all events played so far.
        """
        return self._time

    def run(
        self, on_match: Callable[[MatchResult], None] | None = None
    ) -> Iterator[GenerationReport]:
        """Play events until the horizon or extinction, reporting periods.

        The run ends when the clock reaches ``dynamics.generations``
        generation-equivalents, or early at extinction (#82 — a legitimate
        outcome, not an error). A final partial period is emitted if any
        events happened after the last boundary, so the record never drops
        a tail (extinction's closing deaths always reach the stream).

        Args:
            on_match: Optional read-only observer called with each finished
                match's result, in play order (the engine's event hook).

        Yields:
            One :class:`GenerationReport` per recording period, in order —
            ``index`` is the period index, ``gen_equiv_time`` the clock at
            emission.
        """
        horizon = float(self._dynamics.generations)
        while self._population and self._time < horizon - _EPS:
            report = self._step_event(on_match)
            if report is not None:
                yield report
        if self._window_events or self._pending:
            yield self._emit_period()

    def _step_event(
        self, on_match: Callable[[MatchResult], None] | None
    ) -> GenerationReport | None:
        """Play exactly one event (see the module docstring's draw order).

        Args:
            on_match: Optional read-only match observer.

        Returns:
            A period report if this event crossed a recording boundary,
            else ``None``.
        """
        n = len(self._population)
        # Clock first (spec Design 5): Δt uses N at event start — the event
        # belongs to the population that carried it — and everything this
        # event emits is stamped with the advanced clock. Δt ≤ 1, so at
        # most one integer boundary is crossed per event.
        self._time += 1.0 / n

        # 1-3. The interaction bundle: focal draw, partner draw, matches.
        if n >= 2:
            focal_index = int(self._rng.integers(n))
            focal = self._population[focal_index]
            size = min(self._k, n - 1)
            drawn = self._rng.choice(n - 1, size=size, replace=False)
            for offset in drawn:
                # Skip-map around the focal: offsets 0..N-2 index the
                # others, uniformly, with exactly one draw array consumed.
                partner_index = int(offset) if int(offset) < focal_index else int(offset) + 1
                partner = self._population[partner_index]
                result = self._match.play(focal, partner)
                self._record_match(result, focal, partner)
                if on_match is not None:
                    on_match(result)

        # 4-5. Accrual sweep, then the demographic step (deaths, births).
        self._accrue(1.0 / n)
        self._insolvency_deaths()
        self._births()

        self._event_index += 1
        self._window_events += 1

        if self._time >= self._next_boundary - _EPS:
            self._next_boundary += 1.0
            return self._emit_period()
        return None

    def _record_match(self, result: MatchResult, focal: Agent, partner: Agent) -> None:
        """Apply one finished match's economics and window bookkeeping.

        Match income and the per-match ``engagement_cost`` land on both
        participants immediately (spec Design 2a; per-MATCH semantics, #86
        unchanged). The window accumulators are pure bookkeeping — no RNG,
        no influence on the simulation.

        Args:
            result: The match transcript.
            focal: The initiating participant.
            partner: The drawn participant.
        """
        names = {
            focal.agent_id: strategy_name_of(focal.strategy),
            partner.agent_id: strategy_name_of(partner.strategy),
        }
        self._window_cooperation.record(result, names)
        for agent in (focal, partner):
            payoff = result.total_payoffs[agent.agent_id]
            agent.energy += payoff - self._dynamics.engagement_cost
            name = names[agent.agent_id]
            self._window_payoff[name] = self._window_payoff.get(name, 0.0) + payoff
            self._window_rounds[name] = self._window_rounds.get(name, 0) + result.n_rounds

    def _accrue(self, dt: float) -> None:
        """Apply the time-based ledger terms to every living agent.

        ``e ← e·(1+r)^Δt − L·Δt`` in ascending id order (deterministic, no
        RNG): capital returns compound to exactly (1+r) per
        generation-equivalent on a static balance, and the living cost
        integrates to ≈ L. Ages are refreshed here too — an agent's age is
        the floor of its lifetime in generation-equivalents.

        Args:
            dt: This event's clock advance (1/N at event start).
        """
        growth = (1.0 + self._dynamics.capital_return_rate) ** dt
        cost = self._dynamics.basic_living_cost * dt
        for agent in self._population:
            agent.energy = agent.energy * growth - cost
            agent.age = int(self._time - self._birth_time[agent.agent_id] + _EPS)

    def _insolvency_deaths(self) -> None:
        """Remove every agent with strictly negative energy (#80 unchanged).

        Deterministic, in ascending id order, emitting one
        :class:`DeathEvent` per death into the period buffer. Strictly
        ``< 0``: a parent that just paid σ can sit at exactly 0 and
        survives empty-handed.
        """
        survivors: list[Agent] = []
        for agent in self._population:
            if agent.energy < 0:
                self._pending.append(
                    DeathEvent(
                        agent_id=agent.agent_id,
                        cause="insolvency",
                        event_index=self._event_index,
                        gen_equiv_time=self._time,
                    )
                )
                del self._birth_time[agent.agent_id]
                del self._breeding_anchor[agent.agent_id]
            else:
                survivors.append(agent)
        self._population = survivors

    def _births(self) -> None:
        """Fire every admissible birth this event (spec Design 2a).

        Eligibility is ``e ≥ θ`` plus a clear 1.0-time-unit breeding
        refractory; the capacity gate is the Option B seam —
        ``admit_births`` decides *the set* by energy priority (RNG-free),
        then the admitted set is iterated in ascending PARENT-id order for
        placement-check → σ+overhead payment → passport id → μ-mutation
        draw (the #80 two-orderings contract, verbatim; placement is
        checked BEFORE the stake is paid).
        """
        dynamics = self._dynamics
        eligible = [
            agent
            for agent in self._population
            if agent.energy >= dynamics.reproduction_threshold
            and self._time - self._breeding_anchor[agent.agent_id] >= 1.0 - _EPS
        ]
        slots = max(0, dynamics.carrying_capacity - len(self._population))
        admitted = admit_births(eligible, slots)
        newborns: list[Agent] = []
        for parent in sorted(admitted, key=lambda agent: agent.agent_id):
            if not place_offspring(self._population, parent):
                continue
            parent.energy -= dynamics.offspring_stake + dynamics.reproduction_overhead
            self._breeding_anchor[parent.agent_id] = self._time
            child_id = self._next_id
            self._next_id += 1
            strategy = self._reproduction.offspring_strategy(parent.strategy, self._rng)
            newborns.append(
                Agent(
                    agent_id=child_id,
                    strategy=strategy,
                    memory_depth=self._config.population.memory_depth,
                    energy=dynamics.offspring_stake,
                    age=0,
                    parent_id=parent.agent_id,
                )
            )
            self._birth_time[child_id] = self._time
            self._breeding_anchor[child_id] = self._time
            self._pending.append(
                BirthEvent(
                    agent_id=child_id,
                    parent_id=parent.agent_id,
                    strategy=strategy_name_of(strategy),
                    energy=dynamics.offspring_stake,
                    cause="threshold",
                    event_index=self._event_index,
                    gen_equiv_time=self._time,
                )
            )
        if newborns:
            # The invariant, enforced explicitly: ascending id order.
            self._population = sorted(self._population + newborns, key=lambda agent: agent.agent_id)

    def _emit_period(self) -> GenerationReport:
        """Build one period report from the window state, then reset it.

        The report's grain (a spec-time convention, named honestly like
        #80's snapshot grain): ``composition`` and ``agents`` describe the
        living population AT the recording point; ``mean_scores`` /
        ``rounds_played`` are the window's flows divided over / attributed
        to the strategies present at emission — window earnings of a
        strategy extinct by the recording point are dropped from
        ``mean_scores`` (they survive in the cooperation table, which is
        pair-keyed). Keeping ``mean_scores`` keys ⊆ ``composition`` keys is
        also what the existing ``RunTimeseries`` per-round arithmetic
        expects.

        Returns:
            The period report, with the buffered demographic events
            attached in occurrence order.
        """
        composition: dict[str, int] = {}
        for agent in self._population:
            name = strategy_name_of(agent.strategy)
            composition[name] = composition.get(name, 0) + 1
        mean_scores = {
            name: self._window_payoff.get(name, 0.0) / count for name, count in composition.items()
        }
        rounds = {name: self._window_rounds.get(name, 0) for name in composition}
        agents = tuple(
            AgentSnapshot(
                agent_id=agent.agent_id,
                parent_id=agent.parent_id,
                age=agent.age,
                energy=agent.energy,
                strategy=strategy_name_of(agent.strategy),
            )
            for agent in self._population
        )
        report = GenerationReport(
            index=self._period,
            composition=composition,
            mean_scores=mean_scores,
            rounds_played=rounds,
            cooperation=self._window_cooperation.table(),
            agents=agents,
            gen_equiv_time=self._time,
            demographic_events=tuple(self._pending),
        )
        self._period += 1
        self._window_payoff = {}
        self._window_rounds = {}
        self._window_cooperation = _CooperationTally()
        self._window_events = 0
        self._pending = []
        return report
