"""RunTimeseries: folds the event stream into per-strategy time series.

The seam between the engine and everything that plots or stores results
(DECISIONS #37): the UI's charts (M6) and the recorder (M7) both consume
this one shape instead of re-deriving it from raw events. It lives in
``core`` — not ``viz`` — because it is pure data processing with no plotting
imports, so the headless recorder may use it without violating hard rule 4.

Only *period-level* events change the series: ``GenerationFinished`` and
``CycleFinished`` each append one column; ``RunFinished`` is kept for the
final summary; ``RoundPlayed``/``MatchFinished`` are ignored here (consumers
use them for progress display, not for time series).
"""

from __future__ import annotations

from pdsim.core.events import AgentSnapshot, CycleFinished, Event, GenerationFinished, RunFinished


class RunTimeseries:
    """Per-strategy series accumulated from one run's event stream.

    Strategies can appear mid-run (mutation introduces them), so every
    series is kept aligned with ``periods``: when a strategy first appears,
    its earlier values are backfilled, and known strategies absent from a
    period get a fill value (0 agents / ``None`` score — ``None`` renders
    as a gap in charts, which is the honest representation of "extinct").

    Attributes:
        mode: ``"evolution"`` or ``"tournament"`` (from the config).
        periods: Completed period indices, in order (generations or cycles).
        composition: Per-strategy agent counts, one value per period.
        mean_scores: Per-strategy mean scores, one value per period
            (that period's mean in evolution; cumulative per-agent mean in
            tournament).
        mean_scores_per_round: Per-strategy mean payoff per round, one
            value per period — total score ÷ rounds played, so it lives on
            the payoff-matrix scale (S..T; DECISIONS #44). ``None`` where a
            period carried no rounds information.
        running_mean_scores: Whole-game-so-far view (evolution only,
            DECISIONS #45): cumulative score ÷ cumulative agent-generations
            up to each period — a running average that moves gradually. A
            currently-extinct strategy's line carries forward flat (its
            whole-game average is unchanged while it sits out). Empty in
            tournament mode, whose plain series are already cumulative.
        running_mean_scores_per_round: Whole-game per-round view (evolution
            only): cumulative score ÷ cumulative rounds played.
        total_scores: Per-strategy cumulative totals, one value per period
            (tournament mode only; stays empty in evolution).
        rounds_played: Per-strategy rounds played (agent-rounds), one value
            per period, exactly as the events reported them — raw data the
            recorder persists (DECISIONS #47).
        cooperation_pairs: Cooperation rate per ordered
            (actor strategy, opponent strategy) pair, one value per period —
            raw data the recorder persists (M9b, DECISIONS #65). Empty for
            runs recorded before cooperation existed (schema 1).
        cooperation_pair_actions: Actions counted per ordered pair, one
            value per period — the weights that make aggregates exact.
        cooperation_by_strategy: Actions-weighted cooperation rate per ACTOR
            strategy (aggregated over its opponents), one value per period —
            a derived view, recomputed on load like every aggregate (#47).
        cooperation_overall: The whole population's actions-weighted
            cooperation rate, one value per period (derived view).
        agent_snapshots: Per-agent post-boundary snapshots, one tuple per
            period (M10a) — raw data the recorder persists as
            ``agents.parquet``. Entirely empty for imitation runs and
            pre-schema-3 recordings, which is how charts know to skip the
            economy figures; once an economy run has recorded data, an
            EMPTY tuple for a later period is meaningful (extinction).
        mean_energy: Mean carried-forward energy per strategy, one value
            per period — a derived view over the snapshots (#47).
        mean_age: Mean entering age per strategy, one value per period —
            a derived view over the snapshots (#47).
        final: The closing ``RunFinished`` event, once it has arrived.
    """

    def __init__(self, mode: str) -> None:
        """Create an empty accumulator.

        Args:
            mode: The run's mode, from ``config.mode`` — decides which
                period event type is expected.
        """
        self.mode = mode
        self.periods: list[int] = []
        self.composition: dict[str, list[int]] = {}
        self.mean_scores: dict[str, list[float | None]] = {}
        self.mean_scores_per_round: dict[str, list[float | None]] = {}
        self.running_mean_scores: dict[str, list[float | None]] = {}
        self.running_mean_scores_per_round: dict[str, list[float | None]] = {}
        self.total_scores: dict[str, list[float | None]] = {}
        self.rounds_played: dict[str, list[int]] = {}
        self.cooperation_pairs: dict[tuple[str, str], list[float | None]] = {}
        self.cooperation_pair_actions: dict[tuple[str, str], list[int]] = {}
        self.cooperation_by_strategy: dict[str, list[float | None]] = {}
        self.cooperation_overall: list[float | None] = []
        self.agent_snapshots: list[tuple[AgentSnapshot, ...]] = []
        self.mean_energy: dict[str, list[float | None]] = {}
        self.mean_age: dict[str, list[float | None]] = {}
        self.final: RunFinished | None = None
        # Whole-game accumulators behind the running_* series (evolution).
        self._cumulative_scores: dict[str, float] = {}
        self._cumulative_agents: dict[str, int] = {}
        self._cumulative_rounds: dict[str, int] = {}

    def add(self, event: Event) -> None:
        """Fold one event into the series (ignores fine-grained events).

        Args:
            event: Any engine event; only period events and ``RunFinished``
                have an effect.
        """
        if isinstance(event, GenerationFinished):
            self.periods.append(event.index)
            self._append(self.composition, event.composition, fill=0)
            self._append(self.mean_scores, event.mean_scores, fill=None)
            self._append(self.rounds_played, event.rounds_played, fill=0)
            # Per-strategy total = mean x count; divide by agent-rounds.
            per_round = {
                name: (
                    mean * event.composition[name] / event.rounds_played[name]
                    if event.rounds_played.get(name)
                    else None
                )
                for name, mean in event.mean_scores.items()
            }
            self._append(self.mean_scores_per_round, per_round, fill=None)
            # Whole-game running averages (DECISIONS #45): fold this
            # generation into the accumulators, then report values for
            # EVERY strategy seen so far — an extinct strategy's whole-game
            # average simply stays flat while it sits out.
            for name, mean in event.mean_scores.items():
                count = event.composition[name]
                self._cumulative_scores[name] = (
                    self._cumulative_scores.get(name, 0.0) + mean * count
                )
                self._cumulative_agents[name] = self._cumulative_agents.get(name, 0) + count
                self._cumulative_rounds[name] = self._cumulative_rounds.get(
                    name, 0
                ) + event.rounds_played.get(name, 0)
            running = {
                name: score / self._cumulative_agents[name]
                for name, score in self._cumulative_scores.items()
            }
            running_per_round = {
                name: (score / self._cumulative_rounds[name])
                if self._cumulative_rounds.get(name)
                else None
                for name, score in self._cumulative_scores.items()
            }
            self._append(self.running_mean_scores, running, fill=None)
            self._append(self.running_mean_scores_per_round, running_per_round, fill=None)
            self._fold_cooperation(event.cooperation)
            self._fold_agents(event.agents)
        elif isinstance(event, CycleFinished):
            self.periods.append(event.index)
            self._append(self.composition, event.composition, fill=0)
            self._append(self.mean_scores, event.mean_scores, fill=None)
            self._append(self.rounds_played, event.rounds_played, fill=0)
            self._append(self.total_scores, event.total_scores, fill=None)
            per_round = {
                name: (total / event.rounds_played[name] if event.rounds_played.get(name) else None)
                for name, total in event.total_scores.items()
            }
            self._append(self.mean_scores_per_round, per_round, fill=None)
            self._fold_cooperation(event.cooperation)
        elif isinstance(event, RunFinished):
            self.final = event

    def _fold_cooperation(self, cooperation: dict[tuple[str, str], tuple[float, int]]) -> None:
        """Fold one period's cooperation table into the series (M9b, #65).

        Events without cooperation data (runs recorded before schema 2)
        leave every cooperation series empty, which is how charts know to
        skip the cooperation figure entirely — no error, no gap chart.

        Args:
            cooperation: Ordered pair → (rate, actions counted); may be
                empty.
        """
        if not cooperation and not self.cooperation_overall:
            return  # a pre-cooperation run: leave the series empty
        rates = {pair: rate for pair, (rate, _actions) in cooperation.items()}
        actions = {pair: count for pair, (_rate, count) in cooperation.items()}
        self._append(self.cooperation_pairs, rates, fill=None)
        self._append(self.cooperation_pair_actions, actions, fill=0)
        # Aggregates are actions-weighted means (#60): rate x count restores
        # the cooperation count exactly, so no precision is lost.
        actor_cooperations: dict[str, float] = {}
        actor_actions: dict[str, int] = {}
        total_cooperations = 0.0
        total_actions = 0
        for (actor, _opponent), (rate, count) in cooperation.items():
            actor_cooperations[actor] = actor_cooperations.get(actor, 0.0) + rate * count
            actor_actions[actor] = actor_actions.get(actor, 0) + count
            total_cooperations += rate * count
            total_actions += count
        by_actor = {
            name: actor_cooperations[name] / actor_actions[name]
            for name in actor_actions
            if actor_actions[name]
        }
        self._append(self.cooperation_by_strategy, by_actor, fill=None)
        self.cooperation_overall.append(
            total_cooperations / total_actions if total_actions else None
        )

    def _fold_agents(self, agents: tuple[AgentSnapshot, ...]) -> None:
        """Fold one period's per-agent snapshots into the series (M10a).

        Mirrors :meth:`_fold_cooperation`'s compatibility shape: events
        without snapshots (imitation runs, pre-schema-3 recordings) leave
        every economy series empty, which is how charts know to skip the
        economy figures — no error, no gap chart. Once an economy run has
        recorded data, an empty tuple is meaningful (extinction) and still
        appends, keeping the series aligned with ``periods``.

        Args:
            agents: The period's post-boundary snapshots; may be empty.
        """
        if not agents and not self.agent_snapshots:
            return  # no per-agent data in this run: leave the series empty
        self.agent_snapshots.append(agents)
        # Derived per-strategy means (#47: recomputed, never persisted).
        counts: dict[str, int] = {}
        energy_totals: dict[str, float] = {}
        age_totals: dict[str, float] = {}
        for snapshot in agents:
            counts[snapshot.strategy] = counts.get(snapshot.strategy, 0) + 1
            energy_totals[snapshot.strategy] = (
                energy_totals.get(snapshot.strategy, 0.0) + snapshot.energy
            )
            age_totals[snapshot.strategy] = age_totals.get(snapshot.strategy, 0.0) + snapshot.age
        self._append(self.mean_energy, {n: energy_totals[n] / counts[n] for n in counts}, fill=None)
        self._append(self.mean_age, {n: age_totals[n] / counts[n] for n in counts}, fill=None)

    @property
    def population_size(self) -> list[int]:
        """Total population per period — derived, never stored (#47).

        ``N(G) = sum(composition.values())``: the raw composition already
        carries the population size, so this is a cheap recomputation
        rather than a persisted column. Under imitation it is constant;
        in the energy economy it is the growth curve.

        Returns:
            One total per period, aligned with ``periods``.
        """
        return [
            sum(series[i] for series in self.composition.values()) for i in range(len(self.periods))
        ]

    def strategy_names(self) -> tuple[str, ...]:
        """Return every strategy seen so far, in first-appearance order.

        Returns:
            Machine names, stable across the run (dicts keep insertion
            order).
        """
        return tuple(self.composition)

    def _append(
        self,
        series: dict,
        values: dict,
        fill: int | float | None,
    ) -> None:
        """Append one period's values, keeping all series aligned.

        Args:
            series: The keyed series to extend (keys are strategy machine
                names, or ordered strategy-name pairs for the cooperation
                series).
            values: This period's value per key.
            fill: Backfill/absence value (0 for counts, None for scores).
        """
        n_previous = len(self.periods) - 1  # periods already includes this one
        for name in values:
            if name not in series:
                series[name] = [fill] * n_previous  # newcomer: backfill history
        for name, column in series.items():
            column.append(values.get(name, fill))
