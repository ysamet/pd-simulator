"""The run loops: evolution generations and fixed-cast tournaments.

Two loop classes, one per run mode (DESIGN §2.7/§2.9):

* :class:`PopulationDynamics` — evolution mode. One :meth:`~PopulationDynamics.step`
  is one synchronous generation: every pairing plays its matches,
  end-of-generation scores feed the selection rule, every next-generation
  slot is decided at once (no mid-selection feedback), mutation is applied,
  and the population is reset for the next generation.
* :class:`TournamentDynamics` — tournament mode. One step is one complete
  matcher pass ("cycle"); nothing is selected, mutated, or reset, ever.

Generation-boundary reset (DECISIONS #31): **both scores and per-opponent
histories are cleared** between generations. Under selection the neighbors'
strategies change, so a remembered relationship would be memory of a
different agent; consequently a history view's ``round_number`` is cumulative
within one generation only (#22).

RNG draw order per generation (DECISIONS #32, extending #23's match order):
    1. the match phase (matcher order; per-round draws per #23),
    2. the selection phase (per slot: incumbent, model, adoption — see
       ``selection.py``),
    3. the mutation phase (per slot: coin only when μ > 0, then a roster
       index only when the coin hits — see ``reproduction.py``).
Any change to this order changes every seeded run's history — treat it as a
breaking change requiring a DECISIONS entry.

v2 forward-compatibility (§6.1): growth/energy dynamics (variable population
size, births/deaths, carrying capacity) change *this* module's internals —
matching, match play, selection, and reproduction all stay behind their
existing interfaces.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import numpy as np

from pdsim.config.experiment import ExperimentConfig
from pdsim.core.agent import Agent
from pdsim.core.game import PrisonersDilemma
from pdsim.core.match import Match, MatchResult
from pdsim.core.matcher import build_matcher
from pdsim.core.reproduction import StrategySwitchReproduction
from pdsim.core.selection import build_selection_rule
from pdsim.core.strategies import create_strategy, strategy_name_of


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
    """

    index: int
    composition: dict[str, int]
    mean_scores: dict[str, float]
    rounds_played: dict[str, int] = field(default_factory=dict)


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
        for agent_a, agent_b in self._matcher.pairings(self._population, self._rng):
            result = self._match.play(agent_a, agent_b)
            if on_match is not None:
                on_match(result)
        report = self._report()

        # 2. Selection phase: one parent index per slot, all chosen against
        #    the same scored population (synchronous — no feedback).
        scores = [agent.score for agent in self._population]
        parents = self._selection.select_parents(scores, self._rng)

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

    def _report(self) -> GenerationReport:
        """Summarize the just-played generation by strategy.

        Returns:
            Composition counts and mean scores keyed by machine name.
        """
        counts, totals, rounds = _tally_by_strategy(self._population)
        return GenerationReport(
            index=self._generation,
            composition=counts,
            mean_scores={name: totals[name] / counts[name] for name in counts},
            rounds_played=rounds,
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
    """

    index: int
    composition: dict[str, int]
    total_scores: dict[str, float]
    mean_scores: dict[str, float]
    rounds_played: dict[str, int] = field(default_factory=dict)


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
            if on_match is not None:
                on_match(result)
        counts, totals, rounds = _tally_by_strategy(self._population)
        report = CycleReport(
            index=self._cycle,
            composition=counts,
            total_scores=totals,
            mean_scores={name: totals[name] / counts[name] for name in counts},
            rounds_played=rounds,
        )
        self._cycle += 1
        return report
