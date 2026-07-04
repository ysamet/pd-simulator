"""Tests for strategy-switch mutation (``pdsim/core/reproduction.py``).

Covers: perfect cloning at μ = 0 (including the untouched-RNG guarantee),
guaranteed mutation at μ = 1, full-roster reach of mutants, construction of
mutants with the run's ``strategy_params``, and the documented draw order
(DECISIONS #32). Fixed seeds throughout — deterministic, not flaky.
"""

from __future__ import annotations

import numpy as np

from pdsim.config.experiment import ExperimentConfig
from pdsim.core.reproduction import StrategySwitchReproduction
from pdsim.core.strategies import all_strategy_names, strategy_name_of
from pdsim.core.strategies.random_strategy import Random
from pdsim.core.strategies.tit_for_tat import TitForTat


def _config(
    mutation_rate: float,
    strategy_params: dict[str, dict[str, float]] | None = None,
) -> ExperimentConfig:
    """Build a minimal experiment config for reproduction tests.

    Args:
        mutation_rate: The μ under test.
        strategy_params: Optional per-run parameter overrides.

    Returns:
        A validated config (composition content is irrelevant here).
    """
    return ExperimentConfig.model_validate(
        {
            "population": {"size": 4, "composition": {"tit_for_tat": 2, "always_defect": 2}},
            "dynamics": {"mutation_rate": mutation_rate},
            "strategy_params": strategy_params or {},
        }
    )


class TestPerfectCloning:
    """μ = 0 must be exact inheritance with zero randomness consumed."""

    def test_offspring_is_the_parent_instance(self) -> None:
        """No mutation: the very same (stateless) strategy object is shared."""
        reproduction = StrategySwitchReproduction(_config(mutation_rate=0.0))
        parent = TitForTat()
        assert reproduction.offspring_strategy(parent, np.random.default_rng(0)) is parent

    def test_rng_is_untouched_when_mu_is_zero(self) -> None:
        """DECISIONS #32: μ = 0 consumes no draws (twin-stream check)."""
        reproduction = StrategySwitchReproduction(_config(mutation_rate=0.0))
        rng_used = np.random.default_rng(9)
        rng_twin = np.random.default_rng(9)
        for _ in range(5):
            reproduction.offspring_strategy(TitForTat(), rng_used)
        assert rng_used.random() == rng_twin.random()  # streams still aligned


class TestMutation:
    """μ > 0 swaps in uniformly drawn roster strategies."""

    def test_mu_one_always_mutates(self) -> None:
        """μ = 1: the offspring is always a fresh construction."""
        reproduction = StrategySwitchReproduction(_config(mutation_rate=1.0))
        rng = np.random.default_rng(1)
        parent = TitForTat()
        offspring = [reproduction.offspring_strategy(parent, rng) for _ in range(20)]
        assert all(child is not parent for child in offspring)

    def test_mutants_cover_the_full_roster(self) -> None:
        """Mutation draws from the FULL registered roster (DECISIONS #32).

        Including strategies absent from the initial composition.
        """
        reproduction = StrategySwitchReproduction(_config(mutation_rate=1.0))
        rng = np.random.default_rng(2)
        parent = TitForTat()
        seen = {strategy_name_of(reproduction.offspring_strategy(parent, rng)) for _ in range(300)}
        assert seen == set(all_strategy_names())

    def test_intermediate_mu_mixes_clones_and_mutants(self) -> None:
        """μ = 0.5: some slots inherit, some mutate (seeded, both occur)."""
        reproduction = StrategySwitchReproduction(_config(mutation_rate=0.5))
        rng = np.random.default_rng(3)
        parent = TitForTat()
        offspring = [reproduction.offspring_strategy(parent, rng) for _ in range(200)]
        clones = sum(child is parent for child in offspring)
        assert 0 < clones < 200

    def test_mutants_are_built_with_the_runs_strategy_params(self) -> None:
        """A mutant picks up its configured parameters (DECISIONS #30).

        This is why strategy_params may name non-composition strategies.
        """
        reproduction = StrategySwitchReproduction(
            _config(mutation_rate=1.0, strategy_params={"random": {"cooperation_probability": 0.9}})
        )
        rng = np.random.default_rng(4)
        parent = TitForTat()
        randoms = [
            child
            for child in (reproduction.offspring_strategy(parent, rng) for _ in range(200))
            if isinstance(child, Random)
        ]
        assert randoms  # the roster draw certainly hit "random" in 200 tries
        assert all(child.cooperation_probability == 0.9 for child in randoms)

    def test_documented_draw_order_reproduces_mutation(self) -> None:
        """The documented draw order predicts every offspring (DECISIONS #32).

        Per slot: one coin, then a roster index only when the coin hits. A
        twin generator replaying that order must match exactly.
        """
        mu = 0.4
        reproduction = StrategySwitchReproduction(_config(mutation_rate=mu))
        roster = all_strategy_names()
        parent = TitForTat()

        rng_used = np.random.default_rng(5)
        twin = np.random.default_rng(5)
        for _ in range(50):
            child = reproduction.offspring_strategy(parent, rng_used)
            if twin.random() < mu:
                expected_name = roster[int(twin.integers(len(roster)))]
                assert child is not parent
                assert strategy_name_of(child) == expected_name
            else:
                assert child is parent
