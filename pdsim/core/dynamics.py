"""The run loops: evolution generations, the energy economy, and tournaments.

Three loop classes (DESIGN §2.7/§2.9/§2.10):

* :class:`PopulationDynamics` — evolution mode, ``"imitation"`` reproduction.
  One :meth:`~PopulationDynamics.step` is one synchronous generation: every
  pairing plays its matches, end-of-generation scores feed the selection
  rule, every next-generation slot is decided at once (no mid-selection
  feedback), mutation is applied, and the population is reset for the next
  generation.
* :class:`EconomyDynamics` — evolution mode, ``"energy_economy"``
  reproduction (M10a). A distinct paradigm, not a branch inside
  ``PopulationDynamics``: birth-death dynamics, where differential survival
  IS the selection — no SelectionRule, no ScoreAccounting, variable
  population size, and per-opponent histories that persist for an agent's
  whole life.
* :class:`TournamentDynamics` — tournament mode. One step is one complete
  matcher pass ("cycle"); nothing is selected, mutated, or reset, ever.

Generation-boundary reset (DECISIONS #31): under imitation, **both scores
and per-opponent histories are cleared** between generations — under
selection the neighbors' strategies change, so a remembered relationship
would be memory of a different agent; consequently a history view's
``round_number`` is cumulative within one generation only (#22). In the
energy economy that rationale dissolves (nobody's strategy is overwritten
and ids are never reused), so **only scores reset; histories persist for an
agent's lifetime** — #22's scope is per-mode, and the precedent is the
tournament's cross-cycle memory (#34). See DECISIONS #79.

RNG draw order per generation, imitation (DECISIONS #32, extending #23's
match order):
    1. the match phase (matcher order; per-round draws per #23),
    2. the selection phase (per slot: incumbent, model, adoption — see
       ``selection.py``),
    3. the mutation phase (per slot: coin only when μ > 0, then a roster
       index only when the coin hits — see ``reproduction.py``).

RNG draw order per generation, energy economy (M10a, DECISIONS #80):
    1. the match phase — identical to the above,
    2. the mortality sub-phase — ONLY when age-mortality is active: exactly
       one coin per living agent, in ascending agent-id order,
       unconditionally (even at p = 0.0 or 1.0),
    3. the birth phase — one μ-mutation draw per admitted parent, in
       ascending PARENT-id order (coin only when μ > 0, roster index only
       when it hits, per ``reproduction.py``).
Everything else at the boundary (energy update, insolvency deaths, capacity
admission, placement) is deterministic and consumes no RNG. With
age-mortality off and μ = 0, an economy generation consumes exactly the
match-phase draws.

Any change to either order changes every seeded run's history — treat it as
a breaking change requiring a DECISIONS entry.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import numpy as np

from pdsim.config.experiment import ExperimentConfig
from pdsim.core.accounting import build_score_accounting
from pdsim.core.agent import Agent
from pdsim.core.economy import (
    admit_births,
    age_mortality_active,
    energy_update,
    mortality_probability,
    place_offspring,
    staggered_founder_ages,
)
from pdsim.core.events import AgentSnapshot, DemographicEvent
from pdsim.core.game import Action, AgentId, PrisonersDilemma
from pdsim.core.match import Match, MatchResult
from pdsim.core.matcher import build_matcher
from pdsim.core.reproduction import StrategySwitchReproduction
from pdsim.core.selection import build_selection_rule
from pdsim.core.strategies import create_strategy, strategy_name_of

CooperationTable = dict[tuple[str, str], tuple[float, int]]
"""Per (actor strategy, opponent strategy): (cooperation rate, actions counted).

The M9b observability payload (DECISIONS #60/#65): the rate is cooperations ÷
actions over *executed* actions (#20), and carrying the action count alongside
makes every aggregate (per-strategy, whole population) exactly recomputable by
actions-weighted averaging.
"""


class _CooperationTally:
    """Counts executed-action cooperation per ordered strategy pair (#65).

    Fed one :class:`MatchResult` at a time during the match phase; each round
    contributes TWO actor records — one per participant, each attributed to
    the (its strategy, opponent's strategy) ordered pair. Pure bookkeeping:
    consumes no RNG draws and never influences the simulation.
    """

    def __init__(self) -> None:
        """Create an empty tally."""
        self._actions: dict[tuple[str, str], int] = {}
        self._cooperations: dict[tuple[str, str], int] = {}

    def record(self, result: MatchResult, names: dict[AgentId, str]) -> None:
        """Fold one finished match into the counts.

        Args:
            result: The match transcript (executed actions, #20).
            names: Strategy machine name per agent id, fixed for the phase.
        """
        id_a, id_b = result.agent_ids
        pair_a = (names[id_a], names[id_b])
        pair_b = (names[id_b], names[id_a])
        self._actions[pair_a] = self._actions.get(pair_a, 0) + result.n_rounds
        self._actions[pair_b] = self._actions.get(pair_b, 0) + result.n_rounds
        coop_a = coop_b = 0
        for record in result.rounds:
            if record.actions[id_a] is Action.COOPERATE:
                coop_a += 1
            if record.actions[id_b] is Action.COOPERATE:
                coop_b += 1
        self._cooperations[pair_a] = self._cooperations.get(pair_a, 0) + coop_a
        self._cooperations[pair_b] = self._cooperations.get(pair_b, 0) + coop_b

    def table(self) -> CooperationTable:
        """Return the current rates-and-counts table.

        Returns:
            Ordered pair → (cooperation rate, actions counted); only pairs
            that actually played appear.
        """
        return {
            pair: (self._cooperations.get(pair, 0) / count, count)
            for pair, count in self._actions.items()
        }


@dataclass(frozen=True, slots=True)
class GenerationReport:
    """What one completed generation looked like, for consumers.

    This is the per-generation payload that milestone 5's
    ``GenerationFinished`` event will carry (DESIGN §4): composition and
    score statistics of the generation *as it played*, before selection
    replaced it.

    Attributes:
        index: 0-based generation number.
        composition: Agent count per strategy machine name, for the
            population that played this generation.
        mean_scores: Mean end-of-generation score per strategy machine name
            (same keys as ``composition``).
        rounds_played: Rounds played per strategy this generation, summed
            over its agents ("agent-rounds") — the exact denominator for a
            per-round score view, whatever the match-length mode
            (DECISIONS #44).
        cooperation: Executed-action cooperation per ordered strategy pair,
            THIS generation only (per-generation counts, matching this
            event's per-generation character — DECISIONS #65).
        agents: Per-agent snapshots of the POST-boundary population (M10a)
            — the exact set entering the next generation, with carried
            energy and entering age. Populated only by
            :class:`EconomyDynamics`; always empty under imitation. In
            asynchronous reports (M10b) these snapshot the living
            population at the recording point.
        gen_equiv_time: The generation-equivalent clock at this recording
            point (M10b) — ``None`` in every synchronous report.
        demographic_events: The explicit birth/death/imitation events of
            this recording period, in occurrence order (M10b) — the engine
            flushes them into the stream immediately before this period's
            ``GenerationFinished``. Always empty in synchronous reports.
    """

    index: int
    composition: dict[str, int]
    mean_scores: dict[str, float]
    rounds_played: dict[str, int] = field(default_factory=dict)
    cooperation: CooperationTable = field(default_factory=dict)
    agents: tuple[AgentSnapshot, ...] = ()
    gen_equiv_time: float | None = None
    demographic_events: tuple[DemographicEvent, ...] = ()


def build_initial_population(config: ExperimentConfig) -> list[Agent]:
    """Create generation 0 from the config's composition.

    Agents are created in the composition's declaration order and numbered
    0..N-1, so a config fully determines the initial population layout
    (hard rule 8). All agents of one strategy share a single instance —
    strategies are stateless (DECISIONS #21), so sharing is safe (the
    flyweight option noted in #25).

    Args:
        config: The full experiment config; reads the composition, the
            memory-depth cap, and the per-run ``strategy_params`` that
            initial strategies are constructed with.

    Returns:
        The generation-0 agents, in id order.
    """
    agents: list[Agent] = []
    for name, count in config.population.composition.items():
        strategy = create_strategy(name, **config.strategy_params.get(name, {}))
        for _ in range(count):
            agents.append(
                Agent(
                    agent_id=len(agents),
                    strategy=strategy,
                    memory_depth=config.population.memory_depth,
                )
            )
    return agents


class PopulationDynamics:
    """Runs the synchronous-generations evolutionary loop for one experiment.

    Wires together the pieces built in earlier milestones — game, match
    runner, matcher, selection rule, reproduction — and owns the only piece
    of cross-generation state: the population itself.
    """

    def __init__(self, config: ExperimentConfig, rng: np.random.Generator) -> None:
        """Set up a run: build collaborators and the initial population.

        Args:
            config: The complete, validated experiment description.
            rng: The run's single seeded random generator (hard rule 5).
                Milestone 5's engine owns creating it from ``config.seed``.
        """
        self._config = config
        self._rng = rng
        self._match = Match(PrisonersDilemma(config.game), config.match, rng)
        self._matcher = build_matcher(config.matching)
        self._selection = build_selection_rule(config.dynamics)
        self._accounting = build_score_accounting(config.dynamics)
        self._reproduction = StrategySwitchReproduction(config)
        self._population = build_initial_population(config)
        self._generation = 0

    @property
    def population(self) -> tuple[Agent, ...]:
        """The current population, in agent-id order.

        Returns:
            An immutable snapshot (the agents themselves are live objects).
        """
        return tuple(self._population)

    def run(self) -> Iterator[GenerationReport]:
        """Play the configured number of generations, reporting each one.

        A generator (lazy, like ``Matcher.pairings``) so consumers — the
        CLI, milestone 5's event stream, the live UI — can react after
        every generation instead of waiting for the whole run.

        Yields:
            One :class:`GenerationReport` per generation, in order.
        """
        for _ in range(self._config.dynamics.generations):
            yield self.step()

    def step(self, on_match: Callable[[MatchResult], None] | None = None) -> GenerationReport:
        """Advance exactly one generation (see the module docstring's order).

        Args:
            on_match: Optional observer called with each finished match's
                result, in play order. Purely a read-only hook — the engine
                uses it to emit match/round events (DESIGN §4); it never
                influences the simulation.

        Returns:
            The report for the generation that just played — its composition
            and score statistics are captured *before* selection replaces
            the population.
        """
        # 1. Match phase: every pairing the matcher produces plays once.
        #    Scores and per-opponent histories accumulate on the agents.
        #    Cooperation bookkeeping (#65) tallies executed actions on the
        #    side — a fresh tally per generation, so rates are
        #    per-generation like everything else in the report.
        names = {a.agent_id: strategy_name_of(a.strategy) for a in self._population}
        tally = _CooperationTally()
        for agent_a, agent_b in self._matcher.pairings(self._population, self._rng):
            result = self._match.play(agent_a, agent_b)
            tally.record(result, names)
            if on_match is not None:
                on_match(result)
        report = self._report(tally.table())

        # 2. Selection phase: one parent index per slot, all chosen against
        #    the same scored population (synchronous — no feedback). What
        #    selection sees is the EFFECTIVE score: raw per-generation
        #    scores folded through the accounting rule (M9a; identity under
        #    the default per_generation accounting). Reports and events
        #    keep the raw scores — accounting is selection-only (#64).
        scores = [agent.score for agent in self._population]
        effective = self._accounting.effective_scores(scores)
        parents = self._selection.select_parents(effective, self._rng)

        # 3. Mutation phase: each slot inherits its parent's strategy or,
        #    with probability μ, a random mutant. Computed for ALL slots
        #    before anything is applied, so every decision reads the old
        #    generation only.
        offspring = [
            self._reproduction.offspring_strategy(self._population[parent].strategy, self._rng)
            for parent in parents
        ]

        # 4. Reset: the same Agent objects become the next generation —
        #    new strategies in, scores and histories wiped (DECISIONS #31).
        for agent, strategy in zip(self._population, offspring, strict=True):
            agent.strategy = strategy
            agent.reset_for_new_generation()

        self._generation += 1
        return report

    def _report(self, cooperation: CooperationTable) -> GenerationReport:
        """Summarize the just-played generation by strategy.

        Args:
            cooperation: This generation's cooperation table (#65).

        Returns:
            Composition counts and mean scores keyed by machine name.
        """
        counts, totals, rounds = _tally_by_strategy(self._population)
        return GenerationReport(
            index=self._generation,
            composition=counts,
            mean_scores={name: totals[name] / counts[name] for name in counts},
            rounds_played=rounds,
            cooperation=cooperation,
        )


def _tally_by_strategy(
    population: list[Agent],
) -> tuple[dict[str, int], dict[str, float], dict[str, int]]:
    """Count agents, sum scores, and sum rounds played per strategy.

    Args:
        population: The agents to tally.

    Returns:
        Three dicts with identical keys: agent counts, score totals, and
        rounds-played totals (agent-rounds).
    """
    counts: dict[str, int] = {}
    totals: dict[str, float] = {}
    rounds: dict[str, int] = {}
    for agent in population:
        name = strategy_name_of(agent.strategy)
        counts[name] = counts.get(name, 0) + 1
        totals[name] = totals.get(name, 0.0) + agent.score
        rounds[name] = rounds.get(name, 0) + agent.rounds_played
    return counts, totals, rounds


class _EngagementTally:
    """Per-generation match and round counts per agent (M10a, spec Task 0a).

    The energy update's ``engagement_cost × matches_played`` term needs a
    per-agent MATCH count, and nothing on the agent provides one:
    ``Agent.rounds_played`` counts rounds (and becomes a lifetime figure once
    histories persist), and counting distinct opponents undercounts because a
    pair can play twice in one generation (A drawing B and B drawing A,
    DECISIONS #57). So the economy loop tallies matches — and rounds, which
    replace ``agent.rounds_played`` as the #44 per-generation denominator —
    one finished match at a time, fresh each generation. Pure bookkeeping:
    consumes no RNG and never influences the simulation.
    """

    def __init__(self) -> None:
        """Create an empty tally."""
        self._matches: dict[AgentId, int] = {}
        self._rounds: dict[AgentId, int] = {}

    def record(self, result: MatchResult) -> None:
        """Fold one finished match into both participants' counts.

        Args:
            result: The match transcript.
        """
        for agent_id in result.agent_ids:
            self._matches[agent_id] = self._matches.get(agent_id, 0) + 1
            self._rounds[agent_id] = self._rounds.get(agent_id, 0) + result.n_rounds

    def matches(self, agent_id: AgentId) -> int:
        """Matches an agent took part in this generation.

        Args:
            agent_id: The agent's passport id.

        Returns:
            Initiated + drawn matches (0 if it never played).
        """
        return self._matches.get(agent_id, 0)

    def rounds(self, agent_id: AgentId) -> int:
        """Rounds an agent played this generation.

        Args:
            agent_id: The agent's passport id.

        Returns:
            The per-generation round count (0 if it never played) — the
            #44 denominator; never read ``agent.rounds_played`` here, which
            is a lifetime count under persistent histories.
        """
        return self._rounds.get(agent_id, 0)


class EconomyDynamics:
    """Runs the energy-economy loop (M10a, DESIGN §2.10).

    Birth-death dynamics on the existing generational clock: a sibling of
    :class:`PopulationDynamics`, not a branch inside it — the
    energy economy is a distinct evolutionary paradigm (differential
    survival IS the selection), and keeping it separate keeps the imitation
    path byte-identical. It reuses ``Match``, ``build_matcher``, and
    ``StrategySwitchReproduction.offspring_strategy`` unchanged, and never
    constructs a SelectionRule or ScoreAccounting. It yields the same
    :class:`GenerationReport` type, with the per-agent ``agents`` snapshot
    populated.

    Invariant: ``self._population`` is ALWAYS in ascending ``agent_id``
    order. Deaths make ids non-contiguous (id 5 dies; 4 and 6 remain), so
    "ascending id order over the living set" is NOT ``0..N−1`` and list
    position is never a proxy for id — the boundary sorts explicitly rather
    than trusting insertion order.
    """

    def __init__(self, config: ExperimentConfig, rng: np.random.Generator) -> None:
        """Set up a run: collaborators, founders, and the passport counter.

        Founders come from ``build_initial_population`` unchanged, then get
        their economy decoration: ``initial_energy`` (a resolved plain
        number by config time), no parent, and — when age-mortality is
        active — staggered ages so the run starts at demographic steady
        state instead of a synchronized cohort.

        Args:
            config: The complete, validated experiment description.
            rng: The run's single seeded random generator (hard rule 5).
        """
        self._config = config
        self._rng = rng
        self._match = Match(PrisonersDilemma(config.game), config.match, rng)
        self._matcher = build_matcher(config.matching)
        self._reproduction = StrategySwitchReproduction(config)
        founders = build_initial_population(config)
        dynamics = config.dynamics
        ages = (
            staggered_founder_ages(len(founders), dynamics.max_age)
            if age_mortality_active(dynamics)
            else [0] * len(founders)
        )
        for agent, age in zip(founders, ages, strict=True):
            agent.energy = dynamics.initial_energy
            agent.age = age
            agent.parent_id = None
        self._population = founders
        # Monotonic passport counter: ids are never reused, so lineage and
        # the id-ordered RNG contract stay exact across deaths.
        self._next_id = len(founders)
        self._generation = 0

    @property
    def population(self) -> tuple[Agent, ...]:
        """The current population, in ascending agent-id order.

        Returns:
            An immutable snapshot (the agents themselves are live objects);
            empty after extinction.
        """
        return tuple(self._population)

    def run(self) -> Iterator[GenerationReport]:
        """Play up to the configured number of generations, reporting each.

        Ends early at extinction — a legitimate outcome of a metabolic
        filter, not an error.

        Yields:
            One :class:`GenerationReport` per generation played, in order.
        """
        for _ in range(self._config.dynamics.generations):
            yield self.step()
            if not self._population:
                break

    def step(self, on_match: Callable[[MatchResult], None] | None = None) -> GenerationReport:
        """Advance exactly one generation (the M10a boundary sequence).

        The nine steps, in the frozen order (see the module docstring's
        economy RNG contract): match phase → report-as-played → energy
        update → age mortality → insolvency deaths → births (capacity
        admission, then id-ordered stakes/ids/mutation) → age increment →
        score-only reset → post-boundary snapshot. Deaths happen before
        births (the cull frees room, survivors breed into it — a deliberate
        deviation from Hammond–Axelrod's birth-before-death period order,
        DECISIONS #80).

        Args:
            on_match: Optional read-only observer called with each finished
                match's result, in play order (the engine's event hook).

        Returns:
            The report for the generation that just played — per-strategy
            fields describe the population AS IT PLAYED (before any death
            or birth); ``agents`` snapshots the post-boundary population
            entering the next generation.
        """
        dynamics = self._config.dynamics

        # 1. Match phase — identical to the imitation loop (#23 order),
        #    plus the per-agent engagement tally (spec Task 0a).
        names = {a.agent_id: strategy_name_of(a.strategy) for a in self._population}
        cooperation = _CooperationTally()
        engagement = _EngagementTally()
        for agent_a, agent_b in self._matcher.pairings(self._population, self._rng):
            result = self._match.play(agent_a, agent_b)
            cooperation.record(result, names)
            engagement.record(result)
            if on_match is not None:
                on_match(result)

        # 2. Report the population as it played, BEFORE any death or birth.
        #    rounds_played comes from the per-generation tally — never from
        #    agent.rounds_played, which is a lifetime count now that
        #    histories persist (the silent-decay trap, spec Task 0a).
        counts: dict[str, int] = {}
        totals: dict[str, float] = {}
        rounds: dict[str, int] = {}
        for agent in self._population:
            name = names[agent.agent_id]
            counts[name] = counts.get(name, 0) + 1
            totals[name] = totals.get(name, 0.0) + agent.score
            rounds[name] = rounds.get(name, 0) + engagement.rounds(agent.agent_id)
        mean_scores = {name: totals[name] / counts[name] for name in counts}

        # 3. Energy update — deterministic, every living agent. This is the
        #    single frozen snapshot deaths and births read.
        for agent in self._population:
            agent.energy = energy_update(
                agent.energy, agent.score, engagement.matches(agent.agent_id), dynamics
            )

        # 4. Age mortality — one coin per living agent in ascending id
        #    order, unconditionally, whenever the sub-phase is active (even
        #    at p = 0.0 or 1.0): the RNG stream depends only on the active
        #    flag and the population size, never on hazard values.
        survivors = list(self._population)
        if age_mortality_active(dynamics):
            survivors = []
            for agent in self._population:  # ascending id order — the invariant
                dies = self._rng.random() < mortality_probability(agent.age, dynamics)
                if not dies:
                    survivors.append(agent)

        # 5. Insolvency deaths — deterministic; STRICTLY negative. An agent
        #    that just paid its stake can sit at exactly 0 and survives
        #    empty-handed to earn again — reproduction is not suicidal at
        #    the margin.
        survivors = [agent for agent in survivors if agent.energy >= 0]

        # 6. Births — threshold, then the two gates. TWO DISTINCT ORDERINGS:
        #    admit_births decides THE SET by energy priority (energy desc,
        #    id asc); the loop below then iterates that set in ascending
        #    PARENT-id order, because id order is the RNG-reproducibility
        #    contract for the mutation draws. One birth per parent per
        #    generation, even at e ≥ 2θ.
        eligible = [a for a in survivors if a.energy >= dynamics.reproduction_threshold]
        slots = max(0, dynamics.carrying_capacity - len(survivors))
        admitted = admit_births(eligible, slots)
        newborns: list[Agent] = []
        for parent in sorted(admitted, key=lambda agent: agent.agent_id):
            # Placement BEFORE payment: place_offspring never fails in the
            # well-mixed M10a world, but pay-then-place would bequeath M11
            # the bug where a blocked parent is charged for a child never
            # born.
            if not place_offspring(survivors, parent):
                continue
            parent.energy -= dynamics.offspring_stake + dynamics.reproduction_overhead
            child_id = self._next_id
            self._next_id += 1
            newborns.append(
                Agent(
                    agent_id=child_id,
                    strategy=self._reproduction.offspring_strategy(parent.strategy, self._rng),
                    memory_depth=self._config.population.memory_depth,
                    energy=dynamics.offspring_stake,
                    age=0,
                    parent_id=parent.agent_id,
                )
            )

        # 7. Age increment — survivors only; newborns enter at 0.
        for agent in survivors:
            agent.age += 1

        # 8. Reset — SCORE ONLY. Histories persist for an agent's lifetime
        #    (DECISIONS #79); never call reset_for_new_generation() here.
        for agent in survivors:
            agent.reset_score_for_new_generation()

        # The invariant, enforced explicitly: ascending id order. Survivors
        # are already ascending and newborn ids all exceed theirs, but the
        # boundary sorts rather than trusting insertion order.
        self._population = sorted(survivors + newborns, key=lambda agent: agent.agent_id)

        # 9. Snapshot the post-boundary population — the exact set entering
        #    the next generation, with the energy its next update reads as
        #    carried-in and the age it enters at.
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
            index=self._generation,
            composition=counts,
            mean_scores=mean_scores,
            rounds_played=rounds,
            cooperation=cooperation.table(),
            agents=agents,
        )
        self._generation += 1
        return report


@dataclass(frozen=True, slots=True)
class CycleReport:
    """What one completed tournament cycle looks like, for consumers.

    The per-cycle payload behind milestone 5's ``CycleFinished`` event:
    tournament charts plot cumulative and mean score per strategy over time.

    Attributes:
        index: 0-based cycle number.
        composition: Agent count per strategy machine name — constant across
            the whole run, since nothing evolves in a tournament.
        total_scores: Cumulative score per strategy: summed over its agents
            and over ALL cycles so far (scores never reset in a tournament).
        mean_scores: Cumulative mean score per agent, per strategy
            (``total_scores[name] / composition[name]``).
        rounds_played: Cumulative rounds played per strategy, summed over
            its agents — cumulative like the scores, since nothing resets
            in a tournament (DECISIONS #44).
        cooperation: Executed-action cooperation per ordered strategy pair,
            CUMULATIVE over all cycles so far — cumulative like everything
            else in this event (DECISIONS #65).
    """

    index: int
    composition: dict[str, int]
    total_scores: dict[str, float]
    mean_scores: dict[str, float]
    rounds_played: dict[str, int] = field(default_factory=dict)
    cooperation: CooperationTable = field(default_factory=dict)


class TournamentDynamics:
    """Runs the fixed-cast tournament loop (run mode ``"tournament"``).

    Axelrod-style: the initial agents keep their strategies for the entire
    run. One step is one **cycle** — a complete matcher pass (round-robin:
    every pair plays one match). There is no selection, no mutation, and no
    reset: scores and per-opponent histories accumulate across the whole
    run, so with respect to the history-view semantics a tournament behaves
    as one long generation — ``round_number`` is cumulative across cycles.
    That is the intended direct-reciprocity behavior, not an accident
    (DECISIONS #34): GrimTrigger stays grim in cycle 2 about a betrayal
    from cycle 1.

    Selection/mutation/generation settings in the config are ignored here
    (valid but without effect). RNG contract: the #23 match-phase draw
    order, repeated per cycle — no selection or mutation phases exist, so a
    tournament consumes only match-phase draws.
    """

    def __init__(self, config: ExperimentConfig, rng: np.random.Generator) -> None:
        """Set up a tournament: collaborators plus the fixed cast.

        Args:
            config: The complete, validated experiment description
                (``mode`` itself is not consulted — the engine dispatches).
            rng: The run's single seeded random generator (hard rule 5).
        """
        self._config = config
        self._rng = rng
        self._match = Match(PrisonersDilemma(config.game), config.match, rng)
        self._matcher = build_matcher(config.matching)
        self._population = build_initial_population(config)
        self._cycle = 0
        # Cooperation counts accumulate across the WHOLE run (#65): a
        # tournament is one long generation, so one tally lives here rather
        # than one per cycle.
        self._cooperation = _CooperationTally()
        self._names = {a.agent_id: strategy_name_of(a.strategy) for a in self._population}

    @property
    def population(self) -> tuple[Agent, ...]:
        """The cast, in agent-id order (the same agents for the whole run).

        Returns:
            An immutable snapshot (the agents themselves are live objects).
        """
        return tuple(self._population)

    def run(self) -> Iterator[CycleReport]:
        """Play the configured number of cycles, reporting each one.

        Yields:
            One :class:`CycleReport` per cycle, in order.
        """
        for _ in range(self._config.tournament_cycles):
            yield self.step()

    def step(self, on_match: Callable[[MatchResult], None] | None = None) -> CycleReport:
        """Play exactly one cycle: a full matcher pass, nothing else.

        Args:
            on_match: Optional observer called with each finished match's
                result, in play order (read-only; used by the engine to
                emit match/round events).

        Returns:
            The cumulative standings after this cycle.
        """
        for agent_a, agent_b in self._matcher.pairings(self._population, self._rng):
            result = self._match.play(agent_a, agent_b)
            self._cooperation.record(result, self._names)
            if on_match is not None:
                on_match(result)
        counts, totals, rounds = _tally_by_strategy(self._population)
        report = CycleReport(
            index=self._cycle,
            composition=counts,
            total_scores=totals,
            mean_scores={name: totals[name] / counts[name] for name in counts},
            rounds_played=rounds,
            cooperation=self._cooperation.table(),
        )
        self._cycle += 1
        return report
