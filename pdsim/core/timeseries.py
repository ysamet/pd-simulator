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

from pdsim.core.events import CycleFinished, Event, GenerationFinished, RunFinished


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
        elif isinstance(event, CycleFinished):
            self.periods.append(event.index)
            self._append(self.composition, event.composition, fill=0)
            self._append(self.mean_scores, event.mean_scores, fill=None)
            self._append(self.total_scores, event.total_scores, fill=None)
            per_round = {
                name: (total / event.rounds_played[name] if event.rounds_played.get(name) else None)
                for name, total in event.total_scores.items()
            }
            self._append(self.mean_scores_per_round, per_round, fill=None)
        elif isinstance(event, RunFinished):
            self.final = event

    def strategy_names(self) -> tuple[str, ...]:
        """Return every strategy seen so far, in first-appearance order.

        Returns:
            Machine names, stable across the run (dicts keep insertion
            order).
        """
        return tuple(self.composition)

    def _append(
        self,
        series: dict[str, list],
        values: dict[str, int] | dict[str, float] | dict[str, float | None],
        fill: int | float | None,
    ) -> None:
        """Append one period's values, keeping all series aligned.

        Args:
            series: The per-strategy series to extend.
            values: This period's value per strategy machine name.
            fill: Backfill/absence value (0 for counts, None for scores).
        """
        n_previous = len(self.periods) - 1  # periods already includes this one
        for name in values:
            if name not in series:
                series[name] = [fill] * n_previous  # newcomer: backfill history
        for name, column in series.items():
            column.append(values.get(name, fill))
