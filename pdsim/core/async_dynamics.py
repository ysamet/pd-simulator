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

Phase A-D scope: the event loop, the clock, the event-time ledger, the
recording cadence (``output.recording_cadence`` — spec Design 6, an
observer control deciding when period reports are emitted), and both
demographic engines — ``variable_n`` (θ-births through the Option B seam
``admit_births`` / ``place_offspring`` [DECISIONS #89b], insolvency
deaths, and the mortality trio in event-time) and ``fixed_n`` (classic
Moran replacement per spec Design 3) — plus the **imitation overlay**
(spec Design 4, adopter rule amended by DECISIONS #93): an optional
CULTURAL channel, layerable on either demographic mode, in which one of
the two participants of each finished match — chosen by a fair coin,
blind to score — may copy the other's strategy under the symmetric Fermi
rule sync selection uses. Demography answers *who exists*; imitation answers
*what the living play* — different triggers, different ontological
layers, so they are separate channels rather than one rule.

RNG draw order per event (spec Design 8; the reproducibility contract —
any change is a breaking change requiring a DECISIONS entry):

    1. the focal draw — one ``rng.integers(N)`` (skipped entirely at
       N = 1: no partner exists, no pair draws are consumed — the #81
       lone-survivor thermodynamics in event-time),
    2. the partner draw — one ``rng.choice(N-1, size=min(k, N-1),
       replace=False)`` over the focal's others (the RandomK idiom + #81
       clamp), skip-mapped around the focal; partners are met in drawn
       order,
    3. per match, in partner order: the #23 per-round match draws
       (unchanged), then — only when the imitation overlay is on — exactly
       two ``rng.random()`` draws per completed match in fixed order (#93):
       the adopter-choice coin (< ½ → the focal is the potential adopter,
       else the partner), then the adoption coin — both unconditional even
       when both participants already share a strategy,
    4. the accrual sweep — no RNG,
    5. the demographic step, per ``dynamics.async_population``:

       - ``variable_n``: (a) birthday hazard coins — only when
         age-mortality is active (the #80 active-flag idiom), one
         ``rng.random()`` per agent whose integer age crossed this event,
         in ascending id order, unconditional even at p = 0 or 1;
         (b) age-cap and insolvency deaths — deterministic, no RNG;
         (c) births — ``admit_births`` (RNG-free, energy priority), then
         one μ-mutation draw per admitted parent in ascending PARENT-id
         order (the #80 two-orderings contract, verbatim: admission
         decides *the set* by energy priority; id order is the RNG
         contract).
       - ``fixed_n``: (a) the rule roll — only when
         ``moran_rule = "random"``: one ``rng.random()`` against the
         normalised birth-death weight, the FIRST demographic draw of the
         event; (b) per the selected rule — ``death_birth``: death draw
         (one ``rng.integers`` over the living population — only under
         ``pure_random``; ``energy_decides`` is deterministic and draws
         nothing) → fitness-proportional breeder draw (one ``rng.choice``
         over the remaining candidates, the #63 shift idiom) → μ-mutation
         draw(s); ``birth_death``: fitness-proportional breeder draw over
         everyone → victim draw (one ``rng.integers`` over the others —
         only under ``pure_random``) → μ-mutation draw(s).

    6. clock arithmetic, recording, and period emission — no RNG (#35).

The ledger in event-time (spec Design 2a): match income and the per-match
``engagement_cost`` are applied at match completion; ``basic_living_cost``
accrues as ``L·Δt`` and capital returns compound as ``(1+r)^Δt`` in a
per-event sweep over every living agent in ascending id order — ≈ L and
(1+r) per generation-equivalent. Insolvency stays **strictly negative**
(#80). Births need ``e ≥ θ`` AND a clear **breeding refractory period** of
1.0 time units since the parent's last birth (founders: since t = 0) — the
event-time image of #80's one-birth-per-generation rule, keeping the
dynastic channel in breeding frequency, not endowment.

The mortality trio in event-time (spec Design 2a, Phase B): the sync
per-boundary coin becomes one coin per agent per **integer birthday** —
when an agent's age crosses k, one coin at ``mortality_probability(k−1)``,
the same lifetime coin sequence p(0), p(1), … a synchronous agent draws.
The ``max_age`` cap is deterministic in event-time: an agent whose age
reaches the cap dies that event, no coin needed (deaths fire the moment
their trigger evaluates — spec Design 0). Founder age staggering carries
over via **negative birth_time** (a founder staggered to age s is "born"
at t = −s), so a staggered population still starts at its demographic
steady state; founders' breeding-refractory anchors stay at t = 0
regardless.
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
from pdsim.core.economy import (
    admit_births,
    age_mortality_active,
    mortality_probability,
    place_offspring,
    staggered_founder_ages,
)
from pdsim.core.events import (
    AgentSnapshot,
    BirthEvent,
    DeathEvent,
    DemographicEvent,
    ImitationEvent,
)
from pdsim.core.game import PrisonersDilemma
from pdsim.core.match import Match, MatchResult
from pdsim.core.reproduction import StrategySwitchReproduction

# Intra-package reuse again (as with _CooperationTally above): the imitation
# overlay IS the Fermi rule on a match score gap, so it borrows the very same
# numerically-stable logistic FermiSelection uses rather than growing a second
# copy that could drift from it.
from pdsim.core.selection import _logistic
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
        # The demographic engine this run uses (spec Design 2), and whether
        # the mortality trio's coins are drawn at all — the #80 active-flag
        # idiom, scoped to variable_n (fixed_n has no age deaths).
        self._fixed_n = self._dynamics.async_population == "fixed_n"
        self._age_mortality = not self._fixed_n and age_mortality_active(self._dynamics)
        # The cultural channel (spec Design 4), layerable on either mode —
        # off by default, and its coin exists only when it is on (the #80
        # active-flag idiom, which is what keeps the Phase A/B golden
        # masters valid).
        self._imitation = self._dynamics.imitation_overlay
        self._beta = self._dynamics.selection_beta
        founders = build_initial_population(config)
        # Founder age staggering (M10a, in event-time): a founder staggered
        # to age s is "born" at t = -s, so its derived age starts at s and
        # its birthdays land on the same schedule as a real s-year-old.
        stagger = (
            staggered_founder_ages(len(founders), self._dynamics.max_age)
            if self._age_mortality
            else [0] * len(founders)
        )
        for agent, age in zip(founders, stagger, strict=True):
            agent.energy = self._dynamics.initial_energy
            agent.age = age
            agent.parent_id = None
        self._population = founders
        # Monotonic passport counter (M10a): ids are never reused.
        self._next_id = len(founders)
        # The generation-equivalent clock (spec Design 5) and event counter.
        self._time = 0.0
        self._event_index = 0
        # Per-agent event-time bookkeeping, keyed by passport id: when the
        # agent was born (ages are derived: age = floor(now - birth_time);
        # staggered founders have negative birth times) and the refractory
        # anchor (birth, or last breeding). Founders anchor at t = 0 even
        # when staggered — first eligible from t ≥ 1, like a synchronous
        # founder at boundary 1.
        self._birth_time: dict[int, float] = {
            agent.agent_id: -float(age) for agent, age in zip(founders, stagger, strict=True)
        }
        self._breeding_anchor: dict[int, float] = {a.agent_id: 0.0 for a in founders}
        # Recording state (spec Design 6): the cadence decides when a
        # period report is emitted — an OBSERVER control (#35): it consumes
        # no RNG and never touches the simulation, but it lives in the
        # config because it decides what the persisted record contains.
        # `_next_boundary` is the next integer clock crossing (used only
        # under per_generation_equivalent); the window accumulators below
        # are what each period report is built from.
        self._cadence = config.output.recording_cadence
        self._cadence_m = config.output.recording_cadence_m
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
            A period report if this event reached a recording point under
            ``output.recording_cadence`` (spec Design 6), else ``None``.
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
                self._imitate(result, focal, partner)
                if on_match is not None:
                    on_match(result)

        # 4-5. Accrual sweep, then the demographic step of whichever engine
        # this run uses (spec Design 2): variable_n = mortality coins,
        # age-cap/insolvency deaths, θ-births; fixed_n = one Moran
        # replacement.
        crossed = self._accrue(1.0 / n)
        if self._fixed_n:
            self._moran_step()
        else:
            self._variable_n_deaths(crossed)
            self._births()

        self._event_index += 1
        self._window_events += 1

        # 6. Period emission per the recording cadence (spec Design 6) —
        # observer-only (#35): no RNG, no influence on the simulation.
        if self._cadence == "per_event":
            return self._emit_period()
        if self._cadence == "every_m_events":
            return self._emit_period() if self._window_events >= self._cadence_m else None
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

    def _imitate(self, result: MatchResult, focal: Agent, partner: Agent) -> None:
        """Run one symmetric Fermi adoption for a finished match (Design 4).

        Spec Design 4's adopter rule as amended by DECISIONS #93. The
        overlay is CULTURAL, not demographic: it changes what an
        existing agent plays, never who exists. The adopter rule is the
        SYMMETRIC one synchronous Fermi selection uses (#93), made
        match-local: one of the two participants is chosen by a fair coin
        as the potential ADOPTER — independent of score — and the other is
        the MODEL; the adopter copies the model's strategy with the Fermi
        probability ``logistic(β·(model_total − adopter_total))``, reusing
        the existing ``dynamics.selection_beta``: the semantics — selection
        intensity on a score difference — are genuinely the Fermi rule's,
        so no second β is introduced. Downhill copies (a lower-scoring
        model) happen at probability < ½, and at β = 0 the copy is a pure
        coin flip with no score dependence at all — true neutral drift,
        exactly as in sync, so selection_beta means one thing in both time
        models.

        Two contracts worth stating plainly:

        * **The coins, not the event, are the RNG contract.** Whenever the
          overlay is on, exactly two ``rng.random()`` draws happen per
          completed match, in fixed order (Design 8 step 3, re-pinned by
          #93): the adopter-choice coin (< ½ → the focal is the potential
          adopter, else the partner), then the adoption coin — both
          unconditional, even when both participants already play the same
          strategy, where the copy is a visible no-op. That keeps the
          random stream a function of the flag and the match schedule
          alone, never of the strategy states or the scores (the #80
          active-flag idiom). A no-op copy emits NO
          :class:`ImitationEvent`.
        * **The change is immediate**, which is what asynchrony means: a
          strategy adopted after match 2 of the focal's bundle is what
          plays in match 3.

        Nothing else moves: no energy is charged or transferred, no birth
        or death fires, and identity, age, ``parent_id``, and every
        per-opponent history stay exactly as they were. Strategies are
        stateless (#21), so the adopter can safely share the source's very
        instance — the same flyweight copy reproduction does.

        Args:
            result: The finished match's transcript (its per-agent totals
                are the score gap the Fermi rule reads).
            focal: The initiating participant.
            partner: The drawn participant.
        """
        if not self._imitation:
            return
        # The adopter-choice coin: a fair flip over the pair, blind to the
        # scores (< ½ → the focal is the potential adopter).
        if self._rng.random() < 0.5:
            adopter, model = focal, partner
        else:
            adopter, model = partner, focal
        gap = result.total_payoffs[model.agent_id] - result.total_payoffs[adopter.agent_id]
        adopt = _logistic(self._beta * gap)
        if self._rng.random() >= adopt:
            return
        from_strategy = strategy_name_of(adopter.strategy)
        to_strategy = strategy_name_of(model.strategy)
        if from_strategy == to_strategy:
            return  # both coins were spent; the copy changes nothing
        adopter.strategy = model.strategy
        self._pending.append(
            ImitationEvent(
                agent_id=adopter.agent_id,
                from_strategy=from_strategy,
                to_strategy=to_strategy,
                source_agent_id=model.agent_id,
                event_index=self._event_index,
                gen_equiv_time=self._time,
            )
        )

    def _accrue(self, dt: float) -> list[Agent]:
        """Apply the time-based ledger terms to every living agent.

        ``e ← e·(1+r)^Δt − L·Δt`` in ascending id order (deterministic, no
        RNG): capital returns compound to exactly (1+r) per
        generation-equivalent on a static balance, and the living cost
        integrates to ≈ L. Ages are refreshed here too — an agent's age is
        the floor of its lifetime in generation-equivalents — and agents
        whose integer age just crossed (their "birthday") are collected for
        the mortality step. Δt ≤ 1, so at most one birthday crosses per
        agent per event.

        Args:
            dt: This event's clock advance (1/N at event start).

        Returns:
            The agents whose integer age crossed this event, in ascending
            id order (the order the birthday coins are drawn in).
        """
        growth = (1.0 + self._dynamics.capital_return_rate) ** dt
        cost = self._dynamics.basic_living_cost * dt
        crossed: list[Agent] = []
        for agent in self._population:
            agent.energy = agent.energy * growth - cost
            new_age = int(self._time - self._birth_time[agent.agent_id] + _EPS)
            if new_age > agent.age:
                crossed.append(agent)
            agent.age = new_age
        return crossed

    def _variable_n_deaths(self, birthday_crossers: list[Agent]) -> None:
        """The variable_n death step: hazard coins, age cap, insolvency.

        Spec Design 8 step 5 (variable_n), in order:

        (a) **Birthday hazard coins** — only when age-mortality is active
        (the #80 active-flag idiom): one ``rng.random()`` per agent whose
        integer age crossed this event, in ascending id order,
        unconditional even at p = 0 or 1, so the stream depends only on
        the flag and the birthday schedule, never on hazard values. The
        coin for crossing birthday k prices the year just lived —
        ``mortality_probability(k − 1)``, the same lifetime sequence
        p(0), p(1), … a synchronous agent draws (spec Design 2a).

        (b) **Age-cap and insolvency deaths** — deterministic, no RNG, in
        ascending id order. The cap fires the moment an agent's age
        reaches ``max_age`` (async deaths fire when their trigger
        evaluates, not at a boundary — so a coin-surviving agent at the
        cap still dies this event). Insolvency stays strictly ``< 0``
        (#80): a parent that just paid σ can sit at exactly 0 and
        survives empty-handed. Age takes precedence over insolvency in
        the recorded cause, mirroring the sync step order (#80 steps
        4-5). One :class:`DeathEvent` per death, into the period buffer.

        Args:
            birthday_crossers: Agents whose integer age crossed this
                event (from the accrual sweep), ascending id order.
        """
        dynamics = self._dynamics
        doomed: set[int] = set()
        if self._age_mortality:
            for agent in birthday_crossers:
                hazard = mortality_probability(agent.age - 1, dynamics)
                if self._rng.random() < hazard:
                    doomed.add(agent.agent_id)
        survivors: list[Agent] = []
        for agent in self._population:
            at_cap = dynamics.max_age > 0 and agent.age >= dynamics.max_age
            if agent.agent_id in doomed or at_cap:
                cause = "age"
            elif agent.energy < 0:
                cause = "insolvency"
            else:
                survivors.append(agent)
                continue
            self._pending.append(
                DeathEvent(
                    agent_id=agent.agent_id,
                    cause=cause,
                    event_index=self._event_index,
                    gen_equiv_time=self._time,
                )
            )
            del self._birth_time[agent.agent_id]
            del self._breeding_anchor[agent.agent_id]
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

    def _moran_step(self) -> None:
        """One fixed_n Moran replacement: one death paired with one birth.

        Spec Design 3, with the Design 8 within-event draw order. The rule
        roll — only when ``moran_rule = "random"`` (the #80 active-flag
        idiom) — is the FIRST demographic draw of the event: one
        ``rng.random()`` against the normalised birth-death weight
        ``w_bd / (w_bd + w_db)`` (the both-zero corner is rejected at
        config time whenever this roll can happen). Then:

        - ``death_birth``: the victim is selected from the whole living
          population (per ``fixed_n_death_rule``) and dies with cause
          ``"random_moran"`` (the cause names the Moran death SLOT, not
          the selection rule); the remaining population competes
          fitness-proportionally for the emptied seat.
        - ``birth_death``: the breeder is drawn fitness-proportionally
          from the whole population; its offspring replaces one of the
          OTHER agents (per ``fixed_n_death_rule``), cause
          ``"replacement"``.

        In both orders the death precedes the birth in occurrence (the
        seat empties, then fills), so the period buffer records death
        then birth. The parent may be driven negative by the stake —
        legal in fixed_n, where there is no insolvency death and the
        fitness shift absorbs negative balances (spec Design 2).
        """
        dynamics = self._dynamics
        rule = dynamics.moran_rule
        if rule == "random":
            weight_bd = dynamics.moran_weight_birth_death
            weight_db = dynamics.moran_weight_death_birth
            bd_share = weight_bd / (weight_bd + weight_db)
            rule = "birth_death" if self._rng.random() < bd_share else "death_birth"
        if rule == "death_birth":
            victim = self._select_victim(self._population)
            self._remove_agent(victim, cause="random_moran")
            parent = self._proportional_parent(self._population)
        else:
            parent = self._proportional_parent(self._population)
            others = [agent for agent in self._population if agent.agent_id != parent.agent_id]
            victim = self._select_victim(others)
            self._remove_agent(victim, cause="replacement")
        self._moran_birth(parent)

    def _select_victim(self, candidates: list[Agent]) -> Agent:
        """Pick the dying agent per ``fixed_n_death_rule`` (spec Design 3).

        ``pure_random``: one uniform ``rng.integers`` draw over the
        candidates (textbook Moran — death blind to energy).
        ``energy_decides``: the lowest-energy candidate, ties to the
        lowest id — deterministic, no draw (the #80 active-flag idiom:
        the draw exists only under the rule that needs it).

        Args:
            candidates: The agents at risk, in ascending id order (the
                whole population under death_birth; the breeder's others
                under birth_death).

        Returns:
            The agent to die.
        """
        if self._dynamics.fixed_n_death_rule == "pure_random":
            return candidates[int(self._rng.integers(len(candidates)))]
        return min(candidates, key=lambda agent: (agent.energy, agent.agent_id))

    def _proportional_parent(self, candidates: list[Agent]) -> Agent:
        """Draw the breeder fitness-proportionally — the #63 idiom, exactly.

        Weights ``w_i = e_i − min(e)`` over the candidate set (energies can
        be negative; roulette weights cannot — and a uniform per-capita
        cost L shifts every balance equally, so L cancels out of selection
        entirely). All weights zero → uniform fallback. Exactly one
        ``rng.choice`` draw over the candidates in ascending id order.

        Args:
            candidates: The competing agents, in ascending id order.

        Returns:
            The agent that reproduces.
        """
        floor = min(agent.energy for agent in candidates)
        weights = [agent.energy - floor for agent in candidates]
        total = sum(weights)
        probabilities = [weight / total for weight in weights] if total > 0 else None
        return candidates[int(self._rng.choice(len(candidates), p=probabilities))]

    def _remove_agent(self, victim: Agent, cause: str) -> None:
        """Remove one agent from the population, recording its death.

        Args:
            victim: The agent to remove.
            cause: The :class:`DeathEvent` cause (``"random_moran"`` or
                ``"replacement"`` — the fixed_n taxonomy).
        """
        self._population = [
            agent for agent in self._population if agent.agent_id != victim.agent_id
        ]
        del self._birth_time[victim.agent_id]
        del self._breeding_anchor[victim.agent_id]
        self._pending.append(
            DeathEvent(
                agent_id=victim.agent_id,
                cause=cause,
                event_index=self._event_index,
                gen_equiv_time=self._time,
            )
        )

    def _moran_birth(self, parent: Agent) -> None:
        """Fill the emptied seat with the breeder's offspring (fixed_n).

        The Option B seam holds in fixed_n too: the structural gate is
        checked BEFORE σ leaves the parent (spec Design 9 — placement can
        genuinely fail at M11, and pay-then-place would charge for a
        child never born). Then the parent pays σ + overhead
        unconditionally — even into a negative balance, legal here — and
        the newborn starts at σ with a fresh passport id, ``parent_id``
        set, empty histories, and the μ-mutation draw via the registry's
        unchanged semantics (μ applies to economy newborns).

        Args:
            parent: The breeder selected by :meth:`_proportional_parent`.
        """
        dynamics = self._dynamics
        if not place_offspring(self._population, parent):
            return
        parent.energy -= dynamics.offspring_stake + dynamics.reproduction_overhead
        child_id = self._next_id
        self._next_id += 1
        strategy = self._reproduction.offspring_strategy(parent.strategy, self._rng)
        newborn = Agent(
            agent_id=child_id,
            strategy=strategy,
            memory_depth=self._config.population.memory_depth,
            energy=dynamics.offspring_stake,
            age=0,
            parent_id=parent.agent_id,
        )
        self._birth_time[child_id] = self._time
        self._breeding_anchor[child_id] = self._time
        self._pending.append(
            BirthEvent(
                agent_id=child_id,
                parent_id=parent.agent_id,
                strategy=strategy_name_of(strategy),
                energy=dynamics.offspring_stake,
                cause="moran",
                event_index=self._event_index,
                gen_equiv_time=self._time,
            )
        )
        # The invariant, enforced explicitly: ascending id order.
        self._population = sorted([*self._population, newborn], key=lambda agent: agent.agent_id)

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
