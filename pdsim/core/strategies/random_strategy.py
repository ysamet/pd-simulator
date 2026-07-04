"""Random(p) — cooperates with probability p each round (``docs/DESIGN.md`` §2.3).

The module is named ``random_strategy`` (not ``random``) to avoid shadowing
Python's standard-library ``random`` module in imports and tooling; module
filenames never matter to discovery — the machine name below does.
"""

from __future__ import annotations

import numpy as np

from pdsim.config.registry import ParameterSpec, register
from pdsim.core.game import Action

# Full submodule path: the package __init__ is mid-execution during
# auto-discovery, so its re-exported names are not available yet.
from pdsim.core.strategies.registry import StrategyInfo, register_strategy
from pdsim.core.strategy import HistoryView, Strategy

# The strategy's tunable parameter lives in the Parameter Registry like any
# other knob (hard rule 3); this module keeps a handle for its constructor.
COOPERATION_PROBABILITY = register(
    ParameterSpec(
        key="strategy.random.cooperation_probability",
        kind="float",
        default=0.5,
        minimum=0.0,
        maximum=1.0,
        label="Cooperation probability (p)",
        section="Strategies",
        description=(
            "Chance that a Random agent cooperates in any given round. At 0.5 it "
            "flips a fair coin; 0 makes it always defect and 1 makes it always "
            "cooperate. The ends of the range are allowed on purpose, so you can "
            "morph Random into either unconditional strategy."
        ),
    )
)


class Random(Strategy):
    """Cooperates with a fixed probability, independent of history."""

    def __init__(self, cooperation_probability: float | None = None) -> None:
        """Create a Random(p) strategy.

        Args:
            cooperation_probability: Chance of cooperating each round;
                ``None`` means "use the registry default" — the default is
                never written here, keeping the registry the single source
                of truth (hard rule 3).

        Raises:
            ValueError: If the value violates the registry spec (outside
                [0, 1]); the spec's own message is user-facing.
        """
        raw = (
            COOPERATION_PROBABILITY.default
            if cooperation_probability is None
            else cooperation_probability
        )
        self.cooperation_probability: float = float(COOPERATION_PROBABILITY.validate(raw))

    def decide(self, view: HistoryView, rng: np.random.Generator) -> Action:
        """Draw once and cooperate if the draw lands below p.

        Exactly one RNG draw happens per decision, even at p = 0 or p = 1
        (``rng.random()`` is in [0, 1), so the extremes are still fully
        deterministic). A *fixed* draw count keeps the run's random stream —
        and therefore reproducibility — independent of the parameter value
        (DECISIONS #23).

        Args:
            view: Ignored — the decision never depends on history.
            rng: The run's seeded random generator; the only randomness
                source (hard rule 5).

        Returns:
            ``COOPERATE`` with probability p, else ``DEFECT``.
        """
        return Action.COOPERATE if rng.random() < self.cooperation_probability else Action.DEFECT


register_strategy(
    StrategyInfo(
        name="random",
        display_name="Random",
        description=(
            "Ignores the other player entirely and cooperates at random, with a "
            "tunable probability each round. Useful as a noise source and as a "
            "baseline that no reciprocity can form a relationship with."
        ),
        factory=Random,
        params=(COOPERATION_PROBABILITY,),
        learn_more=(
            "In Axelrod's tournaments RANDOM finished near the bottom — "
            "unpredictability wins no friends in repeated games."
        ),
    )
)
