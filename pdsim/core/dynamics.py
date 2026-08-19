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

The match phase's pairing draws come from the run's matcher. Under
lattice + ``matching.spatial_interaction`` (M11a Phase D — the conjunction
is the gate) the engine constructs ``SpatialKernel`` IN PLACE of the
configured matcher, a SUBSTITUTION at the same stream position: one
kernel draw per focal agent in ascending id order, made unconditionally
even when k covers the whole neighbourhood, with the primitive's
empty-eligible corner (an isolated focal) consuming no RNG. Toggle off,
the configured matcher path is byte-for-byte the pre-Phase-D one.

RNG draw order per generation, imitation (DECISIONS #32, extending #23's
match order):
    1. the match phase (matcher order; per-round draws per #23),
    2. the selection phase (per slot: incumbent, model, adoption — see
       ``selection.py``),
    3. the mutation phase (per slot: coin only when μ > 0, then a roster
       index only when the coin hits — see ``reproduction.py``).

RNG draw order per generation, energy economy (M10a DECISIONS #80, amended
by M11a Phase C per #107 — the spec's Design 9 diff):
    1. the match phase — identical to the above,
    2. the mortality sub-phase — ONLY when age-mortality is active: exactly
       one coin per living agent, in ascending agent-id order,
       unconditionally (even at p = 0.0 or 1.0),
    3. the birth phase — admission by energy priority is RNG-FREE; under
       the three-way gate it ranks ONLY the FEASIBLE eligibles (at least
       one empty site within birth reach — a pure occupancy read through
       the reach cache, zero draws; M11b Phase A, DECISIONS #164/#171),
       then:
       a. the CONTEST PERMUTATION — ONLY when the three-way gate holds
          (synchronous + lattice + ``energy_economy``): one
          ``rng.permutation`` over the admitted set, drawn regardless of
          the ``placement_contest`` setting so flipping that widget can
          never shift the stream (numpy fact, pinned by test: at admitted
          sizes 0 and 1 the call advances no generator state, but it is
          made);
       b. per admitted parent, in iteration order — the permutation under
          ``placement_contest = "random"``, energy-descending under
          ``"energy_priority"``, ascending parent id when the gate is off:
          the PLACEMENT KERNEL DRAW — only on a lattice: one draw via
          ``neighbourhood_sample`` over the empty sites within the birth
          kernel (no draw when no site is in reach — the parent is
          BLOCKED, pays nothing, and stays eligible; since #164 this can
          only be residual contention, an earlier-iterated parent having
          taken the last reachable site this boundary), then σ payment on
          success, passport id, and the μ-mutation draw (coin only when
          μ > 0, roster index only when it hits, per ``reproduction.py``),
    4. the MOVEMENT STEP (M11b Phase B, DECISIONS #165/#172 — the second
       amendment of the #80 frozen sequence after #107) — the boundary's
       FINAL demographic act, after the death and birth phases in whichever
       order ``boundary_order`` ran them, and ONLY when movement is active
       (lattice + ``energy_economy`` + ``movement.rate > 0``, the gate
       ``movement.movement_active`` decides once per run):
       a. ONE ``rng.random()`` coin per living agent of the POST-boundary
          population (survivors AND this boundary's newborns — one uniform
          rule), in ascending agent-id order, unconditionally — even at
          rate 1.0 — so the stream depends only on the flag and the
          population size (the #80 mortality-coin shape);
       b. ONE ``rng.permutation`` over the coin-successes (the movers),
          made whenever at least one coin was drawn (numpy fact, #133(a):
          at sizes 0 and 1 the call advances no generator state, but it is
          made; the counting pins count CALLS);
       c. per mover, in PERMUTATION order: the WALK DRAW — one
          ``neighbourhood_sample`` over the empty sites within the
          movement kernel of the mover's CURRENT site (the origin is
          occupied and never a candidate); an empty result means the move
          is BLOCKED (no RNG consumed — the primitive returns empty before
          drawing; counted, the mover stays put); on success the origin is
          vacated AFTER the draw and the destination occupied, so a
          later-permuted mover can take an earlier mover's vacated site.
Everything else at the boundary (energy update, insolvency deaths, capacity
admission) is deterministic and consumes no RNG. With age-mortality off,
μ = 0, no lattice, and movement off, an economy generation consumes exactly
the match-phase draws — every Phase C and Phase B(M11b) draw exists only
when its governing flag makes it meaningful (the #80/#99 active-flag idiom),
which is what keeps every well-mixed run byte-identical to its pre-M11a
stream and every movement-off lattice run byte-identical to its pre-M11b
stream (the eight golden masters, zero re-recording).

``dynamics.boundary_order`` (M11a Phase C, #107) decides which phase runs
first: ``"death_first"`` is the frozen #80 sequence above; ``"birth_first"``
is Hammond–Axelrod's period order — the birth phase runs first (its slot
ration reads the PRE-death population, so fewer births are admitted), then
the death phase, which newborns face — age-mortality coin included — in
their own birth round.

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
    feasible_parents,
    mortality_probability,
    place_offspring,
    staggered_founder_ages,
)
from pdsim.core.events import AgentSnapshot, DemographicEvent
from pdsim.core.game import Action, AgentId, PrisonersDilemma
from pdsim.core.layouts import found_population
from pdsim.core.match import Match, MatchResult
from pdsim.core.matcher import Matcher, SpatialKernel, build_matcher
from pdsim.core.movement import MovementRule, attempt_move, build_movement_rule, movement_active
from pdsim.core.occupancy import Occupancy
from pdsim.core.reproduction import StrategySwitchReproduction
from pdsim.core.selection import build_selection_rule
from pdsim.core.strategies import create_strategy, strategy_name_of
from pdsim.core.structure import SiteId, neighbourhood_sample

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
        blocked_parents: How many admitted parents failed the LOCAL gate
            this period (M11a Phase C, Design 4): they cleared the capacity
            gate but found no empty site within the birth kernel's reach at
            the moment of their placement draw, paid nothing, and stay
            eligible. Under the synchronous economy this is RESIDUAL
            CONTENTION only since M11b Phase A (#164): every seated parent
            was feasible at assessment, so a blocked one lost the last
            reachable empty site to an earlier-iterated parent. Under the
            asynchronous clock the count keeps its original, undivided
            meaning (ruling R1, #171). Always 0 without a lattice —
            well-mixed placement never fails.
        infeasible_parents: How many threshold-eligible parents (energy ≥
            θ) the feasibility filter excluded from admission this
            generation because NO empty site lay within their birth reach
            (M11b Phase A, #164; ruling R2: the absolute count of ALL
            excluded eligibles, not merely those who would have ranked
            inside the quota — on a full grid every eligible parent is
            infeasible). Synchronous economy + lattice only; always 0
            elsewhere (the asynchronous clock never populates it).
        blocked_moves: How many move attempts found NO empty site within
            walk reach this period and failed in place (M11b Phase B,
            #165(c)/#172) — ONE undivided count covering both a walled-in
            mover and one whose last reachable site an earlier-permuted
            mover took (deliberately unlike the birth vocabulary's
            blocked/infeasible split). Populated by the synchronous economy
            per generation and by asynchronous ``variable_n`` per recording
            window, exactly as ``blocked_parents`` travels; always 0 while
            movement is off or not gated on (rate 0, well-mixed, imitation,
            ``fixed_n``). LIVE-only: not persisted, not pinned by any golden.
    """

    index: int
    composition: dict[str, int]
    mean_scores: dict[str, float]
    rounds_played: dict[str, int] = field(default_factory=dict)
    cooperation: CooperationTable = field(default_factory=dict)
    agents: tuple[AgentSnapshot, ...] = ()
    gen_equiv_time: float | None = None
    demographic_events: tuple[DemographicEvent, ...] = ()
    blocked_parents: int = 0
    infeasible_parents: int = 0
    blocked_moves: int = 0


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


def _build_generation_matcher(config: ExperimentConfig, occupancy: Occupancy | None) -> Matcher:
    """Choose a synchronous run's matcher — the M11a Phase D engine seam.

    When the run has structure AND ``matching.spatial_interaction`` is on
    (the conjunction is the gate — spec Design 9's inventory; the validator
    guarantees the toggle only survives on a lattice), the
    :class:`~pdsim.core.matcher.SpatialKernel` is constructed IN PLACE of
    the configured matcher: partners then come from the interaction kernel
    and ``matching.matcher`` is not consulted (round-robin has no local
    analogue — spec Design 6). Otherwise the existing
    :func:`~pdsim.core.matcher.build_matcher` path runs untouched, which is
    what keeps every toggle-off run byte-identical (Defining principle 1).

    Args:
        config: The complete, validated experiment description.
        occupancy: The run's occupancy from founding, or ``None`` for a
            well-mixed run (which never builds a structure at all).

    Returns:
        The matcher this run's match phase should use.
    """
    if occupancy is not None and config.matching.spatial_interaction:
        return SpatialKernel(
            structure=occupancy.structure,
            occupancy=occupancy,
            radius=config.structure.interaction_radius,
            decay=config.structure.interaction_decay,
            k=config.matching.opponents_per_agent,
        )
    return build_matcher(config.matching)


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
        self._selection = build_selection_rule(config.dynamics)
        self._accounting = build_score_accounting(config.dynamics)
        self._reproduction = StrategySwitchReproduction(config)
        self._population = build_initial_population(config)
        # Founding placement (M11a Phase B): the run's FIRST draw, and only
        # on a lattice with a stochastic layout. `None` on a well-mixed run,
        # which never builds a structure at all.
        self._occupancy = found_population(config, self._population, rng)
        # The matcher is chosen AFTER founding because the Phase D seam
        # needs the occupancy (construction consumes no RNG, so the order
        # of these lines never touches the stream).
        self._matcher = _build_generation_matcher(config, self._occupancy)
        self._generation = 0

    @property
    def population(self) -> tuple[Agent, ...]:
        """The current population, in agent-id order.

        Returns:
            An immutable snapshot (the agents themselves are live objects).
        """
        return tuple(self._population)

    @property
    def occupancy(self) -> Occupancy | None:
        """Who sits where, or ``None`` for a well-mixed run.

        Under imitation nothing is born and nothing dies — VT-2 confirmed
        that a selection rule mutates the existing agents rather than
        producing a fresh cohort — so this mapping is fixed for the whole
        run, exactly as founded.

        Returns:
            The occupancy, or ``None`` when the world has no structure.
        """
        return self._occupancy

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
        # Founding placement (M11a Phase B), before any other draw. Since
        # Phase C the occupancy is LIVE: a death vacates its site, a birth
        # occupies one, and a newborn's site id is real from the moment it
        # exists (closing #120(c)'s honest gap).
        self._occupancy = found_population(config, founders, rng)
        # The matcher is chosen AFTER founding because the Phase D seam
        # needs the occupancy (construction consumes no RNG). The kernel
        # holds the LIVE occupancy, so as deaths free sites and births fill
        # them, the partner pool follows automatically.
        self._matcher = _build_generation_matcher(config, self._occupancy)
        # The Phase C birth knobs. The kernel pair and the contest are read
        # only on a lattice; without one, none of their draws exist (the
        # #80/#99 active-flag idiom).
        structure = config.structure
        self._birth_radius = structure.birth_radius
        self._birth_decay = structure.birth_decay
        self._placement_contest = structure.placement_contest
        # Blocked parents this generation (Design 4): admitted at the global
        # gate, refused at the local one — since #164 only by residual
        # contention. Infeasible parents (M11b Phase A): eligible by energy
        # but excluded from admission for want of an empty site in reach.
        # Both reset every boundary; reported so correct viscosity does not
        # read as a stall.
        self._blocked_parents = 0
        self._infeasible_parents = 0
        # Movement (M11b Phase B, #165/#172): the rule exists ONLY when the
        # gate holds — lattice + energy economy + rate > 0 — so a
        # movement-off or non-gated run has no movement object and makes
        # no movement draw (the #80/#99 active-flag idiom). Blocked moves
        # reset every boundary, like the birth counters.
        self._movement: MovementRule | None = (
            build_movement_rule(config) if movement_active(config) else None
        )
        self._movement_rate = config.movement.rate
        self._blocked_moves = 0
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

    @property
    def occupancy(self) -> Occupancy | None:
        """Who sits where right now, or ``None`` for a well-mixed run.

        Live since Phase C: deaths vacate sites and births occupy them, so
        at any moment this maps exactly the living population — every agent
        holds a site from birth to death, and since M11b Phase B may
        relocate at the boundary's movement step (the mapping follows).

        Returns:
            The occupancy, or ``None`` when the world has no structure.
        """
        return self._occupancy

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

        The nine steps (see the module docstring's economy RNG contract):
        match phase → report-as-played → energy update → the death and
        birth phases in the ``dynamics.boundary_order`` order → the
        MOVEMENT step (M11b Phase B, only when active) → age increment →
        score-only reset → post-boundary snapshot. Under the default
        ``death_first`` this is #80's frozen sequence exactly — deaths free
        room, survivors breed into it; ``birth_first`` restores
        Hammond–Axelrod's period order (M11a Phase C, #107): fewer births
        are admitted (the ration reads the pre-death population) and
        newborns face the death phase in their own birth round. Movement
        is the boundary's FINAL demographic act in either order (#165):
        movers see the freshest vacancies, this boundary's newborns are
        movement-eligible too, and the next generation's matches are
        played from the settled positions (move-then-play).

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

        # 4-6. The death and birth phases, in the configured order (M11a
        #    Phase C, #107). `death_first` is the frozen #80 sequence: the
        #    cull frees room, survivors breed into it. `birth_first` is
        #    Hammond-Axelrod's period order: births run first — their slot
        #    ration reads the PRE-death population, because the slots
        #    computation reads whatever list exists at that moment (VT-4's
        #    post-deaths branch, left deliberately as-is) — and the death
        #    phase then runs over survivors AND newborns alike, so a child
        #    faces the age-mortality coin in the round it was born.
        self._blocked_parents = 0
        self._infeasible_parents = 0
        self._blocked_moves = 0
        if dynamics.boundary_order == "birth_first":
            living = list(self._population)
            newborns = self._birth_phase(living)
            merged = sorted(living + newborns, key=lambda agent: agent.agent_id)
            survivors = self._death_phase(merged)
            next_population = list(survivors)
        else:
            survivors = self._death_phase(list(self._population))
            newborns = self._birth_phase(survivors)
            next_population = survivors + newborns

        # 6b. MOVEMENT — the boundary's FINAL demographic act (M11b Phase B,
        #    #165/#172), after deaths and births in whichever order ran
        #    them, over the whole post-boundary population (newborns
        #    included — one uniform rule). Placed here, immediately after
        #    the death/birth block and before the age increment: steps 7-9
        #    below consume no RNG, so this position and "after step 8" are
        #    the same stream — "final demographic act" is unambiguous.
        #    Only when the gate holds (`self._movement` exists): rate 0 or
        #    a non-gated config makes NO draw here.
        if self._movement is not None:
            self._movement_phase(next_population)

        # 7. Age increment — everyone who went through the death phase ages.
        #    Under death_first that is the pre-birth survivors only, so a
        #    newborn enters the next generation at age 0; under birth_first
        #    a surviving newborn has already faced the death phase and
        #    enters at age 1 — its lifetime coin sequence p(0), p(1), ...
        #    starts one boundary earlier, which is exactly the H-A exposure.
        for agent in survivors:
            agent.age += 1

        # 8. Reset — SCORE ONLY. Histories persist for an agent's lifetime
        #    (DECISIONS #79); never call reset_for_new_generation() here.
        for agent in survivors:
            agent.reset_score_for_new_generation()

        # The invariant, enforced explicitly: ascending id order. Survivors
        # are already ascending and newborn ids all exceed theirs, but the
        # boundary sorts rather than trusting insertion order.
        self._population = sorted(next_population, key=lambda agent: agent.agent_id)

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
                site_id=None
                if self._occupancy is None
                else self._occupancy.site_of(agent.agent_id),
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
            blocked_parents=self._blocked_parents,
            infeasible_parents=self._infeasible_parents,
            blocked_moves=self._blocked_moves,
        )
        self._generation += 1
        return report

    def _movement_phase(self, population: list[Agent]) -> None:
        """Run the boundary's movement step (M11b Phase B; #165/#172).

        The RNG contract, in order: ONE ``rng.random()`` coin per agent of
        the post-boundary population in ASCENDING ID ORDER, unconditionally
        (even at rate 1.0 — the #80 mortality-coin shape, so the stream
        depends only on the flag and the population size); then ONE
        ``rng.permutation`` over the coin-successes — the movers — made
        whenever at least one coin was drawn (a no-op on the generator at
        sizes 0 and 1, #133(a), but the call is made and the counting
        pins count calls); then, in PERMUTATION order, one walk draw per
        mover via :func:`~pdsim.core.movement.attempt_move`. The origin is
        vacated only AFTER the destination is drawn, so an earlier
        mover's freed site is available to a later one (chains can form);
        every agent gets at most one attempt per boundary; a mover with no
        empty site in reach is BLOCKED — no draw consumed, counted, stays
        put.

        Why a permutation over the movers rather than iterating them in id
        order: on a lattice id correlates with founding position (#107),
        so id-order iteration would silently hand a spatial priority to
        low ids whenever two movers want the same last empty cell. The
        permutation is drawn even when the movers are 0 or 1 so the call
        pattern is a function of the flag alone.

        Args:
            population: The post-boundary population — survivors plus this
                boundary's newborns (any order; sorted here by id).
        """
        assert self._movement is not None and self._occupancy is not None  # gated
        movers: list[Agent] = []
        for agent in sorted(population, key=lambda agent: agent.agent_id):
            if self._rng.random() < self._movement_rate:
                movers.append(agent)
        if not population:
            return  # no coin drawn — no success set exists, no permutation
        order = self._rng.permutation(len(movers))
        for index in order:
            moved = attempt_move(
                self._movement, movers[int(index)].agent_id, self._occupancy, self._rng
            )
            if not moved:
                self._blocked_moves += 1

    def _death_phase(self, candidates: list[Agent]) -> list[Agent]:
        """Apply the mortality coins and the insolvency cull (#80 steps 4-5).

        Age mortality first — one ``rng.random()`` coin per candidate in
        ascending id order, unconditionally, whenever the sub-phase is
        active (even at p = 0.0 or 1.0): the stream depends only on the
        active flag and the candidate count, never on hazard values. Then
        insolvency, deterministic and STRICTLY negative: an agent that just
        paid its stake can sit at exactly 0 and survives empty-handed —
        reproduction is not suicidal at the margin. Every death vacates its
        site (Phase C: the occupancy is live).

        Args:
            candidates: The agents facing the reaper, in ascending id
                order. Under ``death_first`` these are the pre-birth
                living; under ``birth_first`` they include this boundary's
                newborns, which is Hammond-Axelrod's newborn exposure.

        Returns:
            The survivors, in the same (ascending id) order.
        """
        dynamics = self._config.dynamics
        survivors = list(candidates)
        if age_mortality_active(dynamics):
            survivors = []
            for agent in candidates:  # ascending id order — the invariant
                dies = self._rng.random() < mortality_probability(agent.age, dynamics)
                if dies:
                    self._free_site(agent)
                else:
                    survivors.append(agent)
        alive: list[Agent] = []
        for agent in survivors:
            if agent.energy >= 0:
                alive.append(agent)
            else:
                self._free_site(agent)
        return alive

    def _birth_phase(self, living: list[Agent]) -> list[Agent]:
        """Run the amended #80 step 6: admission, contest, placement, birth.

        Admission — ``admit_births`` decides THE SET by energy priority,
        RNG-free. On a lattice (the three-way gate: this class is
        synchronous + ``energy_economy``, the occupancy is the lattice half)
        the set is ranked from the FEASIBLE eligibles only — those with at
        least one empty site within birth reach, a pure occupancy read that
        consumes zero draws (M11b Phase A, #164, resolving #159): K decides
        HOW MANY, the kernel decides WHERE, and a seat never goes to a
        parent who cannot use it. The excluded eligibles are counted as
        INFEASIBLE (ruling R2: all of them, whether or not they would have
        ranked inside the quota). Iteration then follows
        :meth:`_contest_order` (the permutation is UNTOUCHED mechanically —
        drawn under the gate as before, over the admitted set in id order;
        only its input set may differ, the sanctioned #164 breaking
        change), and each parent in turn faces the LOCAL gate: on a
        lattice, one kernel draw over the empty sites within the birth
        radius of its own site; an empty result means the parent is
        BLOCKED — it pays NO stake, stays eligible next period, and keeps
        accumulating (the place-before-pay branch of #80). Since #164 a
        blocked parent is always a RESIDUAL-CONTENTION loser: it was
        feasible at assessment, and an earlier-iterated parent took the
        last empty site in its reach this boundary — rare, self-healing
        (next generation re-ranks against the changed occupancy), and the
        empty-before-drawing primitive still consumes no RNG for it.
        Payment, passport id, μ-mutation draw, and site occupation follow
        only on placement success. One birth per parent per generation,
        even at e ≥ 2θ.

        Args:
            living: The population the ration is computed against — the
                post-death survivors under ``death_first``, the pre-death
                living under ``birth_first`` (the slots computation reads
                whatever list exists at that moment; VT-4). The feasibility
                filter reads the occupancy of the SAME moment — no second
                snapshot is introduced.

        Returns:
            The newborns, in iteration order (their ids ascend with it).
        """
        dynamics = self._config.dynamics
        eligible = [a for a in living if a.energy >= dynamics.reproduction_threshold]
        slots = max(0, dynamics.carrying_capacity - len(living))
        if self._occupancy is None:
            # Off the gate: the untouched #80 admission — no feasibility
            # code runs, well-mixed streams stay byte-identical.
            admitted = admit_births(eligible, slots)
        else:
            feasible = feasible_parents(eligible, self._occupancy, self._birth_radius)
            self._infeasible_parents = len(eligible) - len(feasible)
            admitted = admit_births(feasible, slots)
        newborns: list[Agent] = []
        for parent in self._contest_order(admitted):
            if self._occupancy is None:
                # The well-mixed structural gate: never fails here, kept as
                # the seam for programmatic callers (#80's stub, still the
                # defence against a pay-then-place regression).
                if not place_offspring(living, parent):
                    continue
                site_id: SiteId | None = None
            else:
                origin = self._occupancy.site_of(parent.agent_id)
                assert origin is not None  # every living agent holds a site
                drawn = neighbourhood_sample(
                    self._occupancy.structure,
                    origin,
                    radius=self._birth_radius,
                    decay=self._birth_decay,
                    size=1,
                    rng=self._rng,
                    eligible=self._occupancy.empty_sites(),
                )
                if not drawn:
                    # The local gate failed (Design 4): no empty site within
                    # reach — since #164 only because an earlier-iterated
                    # parent took the last one this boundary (residual
                    # contention). No stake leaves the parent; it stays
                    # eligible and keeps accumulating — counted so the
                    # Economy panel can say so.
                    self._blocked_parents += 1
                    continue
                site_id = drawn[0]
            parent.energy -= dynamics.offspring_stake + dynamics.reproduction_overhead
            child_id = self._next_id
            self._next_id += 1
            newborn = Agent(
                agent_id=child_id,
                strategy=self._reproduction.offspring_strategy(parent.strategy, self._rng),
                memory_depth=self._config.population.memory_depth,
                energy=dynamics.offspring_stake,
                age=0,
                parent_id=parent.agent_id,
            )
            if site_id is not None and self._occupancy is not None:
                self._occupancy.occupy(site_id, newborn.agent_id)
            newborns.append(newborn)
        return newborns

    def _contest_order(self, admitted: list[Agent]) -> list[Agent]:
        """Decide the birth-iteration order (Design 9's three orderings).

        ``admit_births`` decided THE SET (energy desc, id asc); this method
        decides the ITERATION, and the two must never conflate. Under the
        three-way gate — synchronous + lattice + ``energy_economy``; this
        class is the first and third, so the lattice is the live half — the
        CONTEST PERMUTATION is drawn unconditionally, regardless of the
        ``placement_contest`` setting: Design 9's inventory gates the
        insertion on the conjunction alone, so flipping the contest widget
        can never shift the stream (the #80 active-flag idiom). The
        permutation applies to the ID-ORDERED admitted list (Defining
        principle 5) — applying it to the energy-sorted admission list is
        the named #107 trap, a "random" contest quietly anchored to wealth.

        Args:
            admitted: The admitted parents, in admission (energy-priority)
                order.

        Returns:
            The parents in iteration order: the permutation under
            ``placement_contest = "random"``, energy-descending under
            ``"energy_priority"``, ascending parent id when the gate is
            off (the untouched #80 contract).
        """
        if self._occupancy is None:
            return sorted(admitted, key=lambda agent: agent.agent_id)
        base = sorted(admitted, key=lambda agent: agent.agent_id)
        permutation = self._rng.permutation(len(base))
        if self._placement_contest == "energy_priority":
            return list(admitted)
        return [base[int(index)] for index in permutation]

    def _free_site(self, agent: Agent) -> None:
        """Vacate a dying agent's site, if the world has sites.

        Args:
            agent: The agent that just died.
        """
        if self._occupancy is not None:
            self._occupancy.remove_agent(agent.agent_id)


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
