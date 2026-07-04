"""Selection rules: how the next generation is chosen (``docs/DESIGN.md`` §2.7).

A :class:`SelectionRule` answers one question per next-generation slot: *which
current-generation agent's strategy fills this slot?* It works purely on the
score list — it never sees agents or strategies — which keeps it trivially
reusable by the future vectorized backend (§3.1) and keeps the interface open
for v2's additional rules (proportional, tournament(k), truncation; §6.1).

v1 ships **Fermi (pairwise-comparison)** selection. Its RNG contract is part
of the design (DECISIONS #32): per slot, exactly three draws in fixed order —
incumbent index, model index, adoption coin — *unconditionally*, so the random
stream is independent of β and of the scores.
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
    rules: dict[str, type[SelectionRule]] = {"fermi": FermiSelection}
    try:
        return rules[config.selection_rule](config)
    except KeyError:
        raise ValueError(
            f"Unknown selection rule {config.selection_rule!r}; known rules: {sorted(rules)}"
        ) from None
