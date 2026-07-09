"""Score accounting: which score selection consumes (``docs/DESIGN.md`` §2.7).

The ``ScoreAccounting`` seam was named in the design from day one (§2.7/§6.1)
and becomes code here (M9a, DECISIONS #64). An accounting rule sits between
the match phase and the selection phase: each generation it folds the raw
per-generation scores into its own per-slot state and returns the EFFECTIVE
scores that the :class:`~pdsim.core.selection.SelectionRule` consumes.

Everything else is untouched: agents still carry raw per-generation scores,
the generation-boundary resets (DECISIONS #31) still apply, and events,
charts, and persistence keep reporting raw scores — accounting is invisible
outside the selection phase in M9. (Surfacing effective scores in
events/charts is a possible later addition; noted, not built.)

**State belongs to the agent SLOT**, not the strategy: it survives strategy
switches from selection and mutation. This models the fitness inertia of the
lineage occupying the slot; a reset-on-switch alternative was rejected as
ill-defined — copying your own strategy from a same-strategy model is not a
detectable "switch" (DECISIONS #64).

Accounting consumes zero RNG draws, so the default (``per_generation``)
leaves every seeded v1 run byte-identical.

A functional-programming note (a learning thread of this project): the
accounting classes are the project's first *stateful* strategy objects —
each ``effective_scores`` call is a fold (reduce) step, carrying an
accumulator (the per-slot state) across generations. Contrast with the
stateless ``Strategy`` classes (#21), which are pure functions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Sequence

from pdsim.config.experiment import DynamicsConfig


class ScoreAccounting(ABC):
    """Turns raw per-generation scores into the scores selection sees."""

    @abstractmethod
    def effective_scores(self, raw_scores: Sequence[float]) -> tuple[float, ...]:
        """Fold one generation's raw scores into state; return effective ones.

        Called exactly once per generation, after the match phase and before
        the selection phase, with the raw end-of-generation score of every
        agent slot in agent-id order.

        Args:
            raw_scores: This generation's raw score per agent slot.

        Returns:
            The effective score per slot, same length and order — what the
            selection rule consumes.
        """


class PerGenerationAccounting(ScoreAccounting):
    """The classic (v1) setting: effective score = this generation's raw score."""

    def __init__(self, config: DynamicsConfig) -> None:
        """Create a per-generation accounting rule (stateless).

        Args:
            config: The dynamics section of an experiment config; nothing is
                read — the constructor keeps the factory's uniform shape
                (DECISIONS #24).
        """

    def effective_scores(self, raw_scores: Sequence[float]) -> tuple[float, ...]:
        """Return the raw scores unchanged.

        Args:
            raw_scores: This generation's raw score per agent slot.

        Returns:
            The same values, as a tuple.
        """
        return tuple(raw_scores)


class SlidingWindowAccounting(ScoreAccounting):
    """Effective score = mean of the last W raw generation scores.

    The mean (not the sum) keeps the effective-score scale comparable across
    window sizes and during warmup — β interacts with score scale, so a sum
    would silently change selection pressure with W (DECISIONS #64). During
    the first generations the window holds fewer than W entries and the mean
    is over what exists; ``W = 1`` is exactly per-generation accounting.
    """

    def __init__(self, config: DynamicsConfig) -> None:
        """Create a sliding-window accounting rule.

        Args:
            config: The dynamics section of an experiment config; reads
                ``accounting_window``.
        """
        self._window = config.accounting_window
        # One deque per agent slot, created on first use (the population
        # size is not known until the first generation reports). A deque
        # with maxlen (new concept) is a ring buffer: appending beyond
        # maxlen silently drops the oldest entry — exactly a sliding window.
        self._history: list[deque[float]] | None = None

    def effective_scores(self, raw_scores: Sequence[float]) -> tuple[float, ...]:
        """Append this generation and return each slot's window mean.

        Args:
            raw_scores: This generation's raw score per agent slot.

        Returns:
            Per slot: the mean of the last ``min(W, generations so far)``
            raw scores, the current one included.
        """
        if self._history is None:
            self._history = [deque(maxlen=self._window) for _ in raw_scores]
        for slot_history, raw in zip(self._history, raw_scores, strict=True):
            slot_history.append(raw)
        return tuple(sum(history) / len(history) for history in self._history)


class ExponentialDiscountAccounting(ScoreAccounting):
    """Effective score = exponential moving average of the raw scores.

    ``effective(t) = (1 - λ) * raw(t) + λ * effective(t - 1)``, with
    ``effective(0) = raw(0)``. The EMA form is scale-stable — a constant raw
    score is a fixed point regardless of λ — and ``λ = 0`` is exactly
    per-generation accounting (DECISIONS #64).
    """

    def __init__(self, config: DynamicsConfig) -> None:
        """Create an exponential-discount accounting rule.

        Args:
            config: The dynamics section of an experiment config; reads
                ``accounting_discount``.
        """
        self._discount = config.accounting_discount
        self._effective: list[float] | None = None

    def effective_scores(self, raw_scores: Sequence[float]) -> tuple[float, ...]:
        """Blend this generation into each slot's running average.

        Args:
            raw_scores: This generation's raw score per agent slot.

        Returns:
            Per slot: the updated exponential moving average.
        """
        if self._effective is None:
            self._effective = [float(raw) for raw in raw_scores]
        else:
            self._effective = [
                (1.0 - self._discount) * raw + self._discount * previous
                for raw, previous in zip(raw_scores, self._effective, strict=True)
            ]
        return tuple(self._effective)


def build_score_accounting(config: DynamicsConfig) -> ScoreAccounting:
    """Construct the accounting rule named by a validated config.

    Maps the registry choice string (``dynamics.score_accounting``) to a
    class, mirroring :func:`pdsim.core.selection.build_selection_rule`.

    Args:
        config: The dynamics section of an experiment config.

    Returns:
        A ready-to-use :class:`ScoreAccounting`.

    Raises:
        ValueError: If the name is unknown (defensive — the registry's
            choices should have caught it already).
    """
    rules: dict[str, type[ScoreAccounting]] = {
        "per_generation": PerGenerationAccounting,
        "sliding_window": SlidingWindowAccounting,
        "exponential_discount": ExponentialDiscountAccounting,
    }
    try:
        return rules[config.score_accounting](config)
    except KeyError:
        raise ValueError(
            f"Unknown score accounting {config.score_accounting!r}; known choices: {sorted(rules)}"
        ) from None
