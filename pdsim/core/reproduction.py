"""Reproduction: turning parent picks into offspring strategies (``docs/DESIGN.md`` §2.7).

v1 ships **strategy-switch mutation**: with probability μ a newly produced
agent ignores the strategy it was supposed to copy and instead adopts a
uniformly random strategy from the roster. μ = 0 means perfect cloning;
μ > 0 keeps "extinct" strategies able to reappear, which produces the
theoretically expected cooperation cycles.

Two documented consequences (DECISIONS #32):

* The mutation roster is the **full registered roster**, not just the
  strategies in the initial composition — mutation can introduce a strategy
  the run did not start with. This is why ``strategy_params`` may name
  strategies outside the composition (DECISIONS #30).
* Copying is instance *sharing*: strategies are stateless pure functions
  (DECISIONS #21), so offspring can safely hold the very same strategy
  object as the parent — the flyweight option noted in DECISIONS #25. (A
  functional-programming payoff: immutable/stateless things never need
  defensive copies.)

v2's parameter-perturbation mutation (Gaussian noise on continuous strategy
parameters) will plug in beside this class per §6.1.
"""

from __future__ import annotations

import numpy as np

from pdsim.config.experiment import ExperimentConfig
from pdsim.core.strategies import all_strategy_names, create_strategy
from pdsim.core.strategy import Strategy


class StrategySwitchReproduction:
    """Produces each next-generation slot's strategy: inherit or mutate.

    RNG contract (DECISIONS #32, mirroring the noise rule in #23): when
    μ = 0 the generator is never touched, so mutation-free runs consume the
    random stream identically whether or not mutation support exists. When
    μ > 0, each slot costs one coin draw, plus one roster-index draw only
    when the coin hits.
    """

    def __init__(self, config: ExperimentConfig) -> None:
        """Create the reproduction step for one run.

        Args:
            config: The full experiment config; reads the mutation rate
                (``dynamics.mutation_rate``) and the per-run strategy
                parameter overrides (``strategy_params``) that mutants are
                constructed with.
        """
        self._mutation_rate = config.dynamics.mutation_rate
        self._strategy_params = config.strategy_params
        # Snapshot the roster once: mutation draws index into this tuple.
        self._roster: tuple[str, ...] = all_strategy_names()

    def offspring_strategy(self, parent_strategy: Strategy, rng: np.random.Generator) -> Strategy:
        """Decide one slot's strategy: the parent's, or a random mutant.

        Args:
            parent_strategy: The strategy of the selected parent; returned
                as-is (shared, not copied — safe because strategies are
                stateless) unless mutation strikes.
            rng: The run's seeded random generator.

        Returns:
            The parent's strategy instance, or — with probability μ — a
            freshly constructed strategy drawn uniformly from the full
            roster, built with this run's ``strategy_params``.
        """
        if self._mutation_rate <= 0.0 or rng.random() >= self._mutation_rate:
            return parent_strategy
        name = self._roster[int(rng.integers(len(self._roster)))]
        return create_strategy(name, **self._strategy_params.get(name, {}))
