"""Selection rules: how the next generation is chosen (``docs/DESIGN.md`` §2.7).

A :class:`SelectionRule` answers one question per next-generation slot: *which
current-generation agent's strategy fills this slot?* It works purely on the
score list — it never sees agents or strategies — which keeps it trivially
reusable by the future vectorized backend (§3.1). The scores it receives are
the EFFECTIVE scores supplied by score accounting
(:mod:`pdsim.core.accounting`, M9a) — raw per-generation scores under the
default accounting.

Five rules ship as of M9a. Each rule's RNG contract is part of the design —
a pinned seeded-history contract; changing one is a breaking change requiring
a new DECISIONS entry:

* **fermi** (v1, DECISIONS #32): per slot, exactly three draws in fixed
  order — incumbent index, model index, adoption coin — *unconditionally*,
  so the random stream is independent of β and of the scores.
* **proportional**, **tournament_k**, **truncation**, **threshold_cloning**
  (M9a, DECISIONS #63): draw orders and tie-breaks documented per class
  below. Tie-breaks are always deterministic, never a random draw;
  threshold_cloning's draw count is data-conditional (the #26 precedent).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Sequence

import numpy as np

from pdsim.config.experiment import DynamicsConfig


class SelectionRule(ABC):
    """Chooses, per next-generation slot, a parent from the current one."""

    @abstractmethod
    def select_parents(self, scores: Sequence[float], rng: np.random.Generator) -> tuple[int, ...]:
        """Pick a parent index for every next-generation slot.

        All slots are decided against the *same* scored population — the
        choices are applied simultaneously by the caller, so no slot's
        outcome can feed back into another's (synchronous generations,
        DESIGN §2.7).

        Args:
            scores: End-of-generation score of every current agent, in
                agent order.
            rng: The run's seeded random generator.

        Returns:
            One index into ``scores`` per slot, ``len(scores)`` in total —
            the agent whose strategy the slot inherits.
        """


def _logistic(x: float) -> float:
    """Numerically stable logistic function 1 / (1 + e^(-x)).

    The naive formula overflows for large negative ``x`` (``math.exp(709)``
    is already infinity), which a big β times a big score gap can easily
    produce. Branching on the sign keeps every ``exp`` argument ≤ 0, where
    the worst case is a harmless underflow to 0.0.

    Args:
        x: Any real number.

    Returns:
        The logistic of ``x``, in [0, 1]; exactly 0.5 at ``x = 0``.
    """
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


class FermiSelection(SelectionRule):
    """Pairwise-comparison selection with the Fermi rule (DESIGN §2.7).

    Per slot: sample an incumbent A and a model B (uniformly, with
    replacement — A and B may even be the same agent, in which case the
    outcome is A either way). A adopts B's strategy with probability
    ``1 / (1 + exp(-β * (s_B - s_A)))``.

    β is the selection-intensity knob: at 0 the probability is always 1/2 —
    scores are ignored and strategies spread by pure drift; the larger β,
    the more deterministically higher scorers get copied.
    """

    def __init__(self, config: DynamicsConfig) -> None:
        """Create a Fermi selection rule.

        Args:
            config: The dynamics section of an experiment config; only
                ``selection_beta`` is read (a validated frozen model crosses
                the boundary, per DECISIONS #24).
        """
        self._beta = config.selection_beta

    def select_parents(self, scores: Sequence[float], rng: np.random.Generator) -> tuple[int, ...]:
        """Run one Fermi comparison per slot (see class docstring).

        Args:
            scores: End-of-generation score of every current agent.
            rng: The run's seeded random generator; consumes exactly three
                draws per slot, in the documented order (DECISIONS #32).

        Returns:
            One parent index per slot, ``len(scores)`` in total.
        """
        n = len(scores)
        parents: list[int] = []
        for _ in range(n):
            # Fixed draw order (DECISIONS #32): incumbent, model, adoption.
            incumbent = int(rng.integers(n))
            model = int(rng.integers(n))
            adopt = _logistic(self._beta * (scores[model] - scores[incumbent]))
            parents.append(model if rng.random() < adopt else incumbent)
        return tuple(parents)


class ProportionalSelection(SelectionRule):
    """Fitness-proportional (roulette-wheel) selection — DECISIONS #63.

    Every agent gets a draw weight ``w_i = s_i - min(s)``: how far its
    effective score sits above the generation's worst. The shift is
    mandatory — scores can be negative, and roulette weights cannot. A
    consequence worth knowing: the worst-scoring agent has weight 0 and is
    never drawn (unless all scores are equal). When all scores are equal,
    every weight is 0 and the draw falls back to uniform.

    RNG contract: per slot, in slot order, exactly one weighted index draw
    (``rng.choice`` over the population with the normalized weights, or
    uniform under the fallback) — always N draws.
    """

    def __init__(self, config: DynamicsConfig) -> None:
        """Create a proportional selection rule.

        Args:
            config: The dynamics section of an experiment config; this rule
                has no parameters of its own, but the constructor keeps the
                factory's uniform shape (DECISIONS #24).
        """

    def select_parents(self, scores: Sequence[float], rng: np.random.Generator) -> tuple[int, ...]:
        """Draw one score-weighted parent per slot (see class docstring).

        Args:
            scores: Effective score of every current agent, in agent order.
            rng: The run's seeded random generator; consumes exactly one
                draw per slot.

        Returns:
            One parent index per slot, ``len(scores)`` in total.
        """
        n = len(scores)
        floor = min(scores)
        weights = [score - floor for score in scores]
        total = sum(weights)
        # All scores equal -> all weights 0 -> uniform fallback (p=None
        # means uniform for rng.choice).
        probabilities = [weight / total for weight in weights] if total > 0 else None
        return tuple(int(rng.choice(n, p=probabilities)) for _ in range(n))


class TournamentKSelection(SelectionRule):
    """Tournament selection: k candidates per slot, best one wins — #63.

    Not related to the tournament RUN MODE (which has no selection at all);
    "tournament selection" is this rule's traditional name in the genetic
    algorithms literature, kept under the machine name ``tournament_k`` to
    avoid colliding with ``run.mode``.

    RNG contract: per slot, in slot order, exactly one without-replacement
    draw of k candidate indices (``rng.choice(n, size=k, replace=False)``
    over the population in agent-id order). The winner is the candidate
    with the highest effective score; ties are broken by the earliest
    position in the drawn array (deterministic — no extra draw).
    """

    def __init__(self, config: DynamicsConfig) -> None:
        """Create a tournament selection rule.

        Args:
            config: The dynamics section of an experiment config; reads
                ``selection_tournament_k``.
        """
        self._k = config.selection_tournament_k

    def select_parents(self, scores: Sequence[float], rng: np.random.Generator) -> tuple[int, ...]:
        """Run one k-candidate contest per slot (see class docstring).

        Args:
            scores: Effective score of every current agent, in agent order.
            rng: The run's seeded random generator; consumes exactly one
                k-sized draw per slot.

        Returns:
            One parent index per slot, ``len(scores)`` in total.

        Raises:
            ValueError: If k exceeds the population size (defensive —
                config validation enforces this for engine runs).
        """
        n = len(scores)
        if self._k > n:
            raise ValueError(
                f"tournament_k needs {self._k} candidates per slot, but the "
                f"population only has {n} agents."
            )
        parents: list[int] = []
        for _ in range(n):
            candidates = rng.choice(n, size=self._k, replace=False)
            # Strictly-greater comparison = earliest drawn position wins ties.
            best = int(candidates[0])
            for candidate in candidates[1:]:
                if scores[int(candidate)] > scores[best]:
                    best = int(candidate)
            parents.append(best)
        return tuple(parents)


class TruncationSelection(SelectionRule):
    """Elitist (truncation) selection: parents come from the top q — #63.

    The elite set holds ``elite_count = max(1, floor(q * N))`` agents: the
    highest effective scorers, with boundary ties broken by lower agent id
    (deterministic). The elite list is ordered by (score descending, agent
    id ascending).

    RNG contract: per slot, in slot order, exactly one uniform draw of an
    index into that elite list — always N draws.
    """

    def __init__(self, config: DynamicsConfig) -> None:
        """Create a truncation selection rule.

        Args:
            config: The dynamics section of an experiment config; reads
                ``selection_elite_fraction``.
        """
        self._fraction = config.selection_elite_fraction

    def select_parents(self, scores: Sequence[float], rng: np.random.Generator) -> tuple[int, ...]:
        """Draw every slot's parent uniformly from the elite set.

        Args:
            scores: Effective score of every current agent, in agent order.
            rng: The run's seeded random generator; consumes exactly one
                draw per slot.

        Returns:
            One parent index per slot, ``len(scores)`` in total.
        """
        n = len(scores)
        elite_count = max(1, math.floor(self._fraction * n))
        # Sort key (-score, id): highest scores first, boundary ties to the
        # lower agent id — fully deterministic elite membership and order.
        elite = sorted(range(n), key=lambda i: (-scores[i], i))[:elite_count]
        return tuple(int(elite[int(rng.integers(elite_count))]) for _ in range(n))


class ThresholdCloningSelection(SelectionRule):
    """Threshold cloning: clear the bar and keep your strategy — #63.

    The survivor set holds every agent whose effective score is at least
    ``θ x mean effective score``. If no one clears the bar (possible e.g.
    when θ > 1), the survivor set falls back to all agents tied at the
    maximum score. Surviving slots keep their own strategy; every other
    slot becomes a copy of a uniformly drawn survivor.

    RNG contract: surviving slots consume NO draw; each non-surviving slot,
    in slot order, consumes exactly one uniform draw of an index into the
    survivor list (ascending agent-id order). The draw count is therefore
    data-conditional — a deterministic function of the scores, which is the
    #26 precedent (GTFT's conditional draw), not a reproducibility hazard.
    """

    def __init__(self, config: DynamicsConfig) -> None:
        """Create a threshold-cloning selection rule.

        Args:
            config: The dynamics section of an experiment config; reads
                ``selection_threshold_multiplier``.
        """
        self._multiplier = config.selection_threshold_multiplier

    def select_parents(self, scores: Sequence[float], rng: np.random.Generator) -> tuple[int, ...]:
        """Keep survivors in place; refill the rest from the survivor set.

        Args:
            scores: Effective score of every current agent, in agent order.
            rng: The run's seeded random generator; consumes one draw per
                NON-surviving slot only.

        Returns:
            One parent index per slot (a surviving slot's parent is itself).
        """
        n = len(scores)
        threshold = self._multiplier * (sum(scores) / n)
        survivors = [i for i in range(n) if scores[i] >= threshold]
        if not survivors:
            best = max(scores)
            survivors = [i for i in range(n) if scores[i] == best]
        surviving = set(survivors)
        parents: list[int] = []
        for slot in range(n):
            if slot in surviving:
                parents.append(slot)  # keeps its strategy — no draw
            else:
                parents.append(int(survivors[int(rng.integers(len(survivors)))]))
        return tuple(parents)


def build_selection_rule(config: DynamicsConfig) -> SelectionRule:
    """Construct the selection rule named by a validated config.

    Maps the registry choice string (``dynamics.selection_rule``) to a class,
    mirroring :func:`pdsim.core.matcher.build_matcher`.

    Args:
        config: The dynamics section of an experiment config.

    Returns:
        A ready-to-use :class:`SelectionRule`.

    Raises:
        ValueError: If the name is unknown (defensive — the registry's
            choices should have caught it already).
    """
    rules: dict[str, type[SelectionRule]] = {
        "fermi": FermiSelection,
        "proportional": ProportionalSelection,
        "tournament_k": TournamentKSelection,
        "truncation": TruncationSelection,
        "threshold_cloning": ThresholdCloningSelection,
    }
    try:
        return rules[config.selection_rule](config)
    except KeyError:
        raise ValueError(
            f"Unknown selection rule {config.selection_rule!r}; known rules: {sorted(rules)}"
        ) from None
