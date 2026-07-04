"""Tests for ExperimentConfig and YAML load/save (``pdsim/config/experiment.py``).

Covers: registry-driven defaults, payoff-shape validation, composition rules,
strictness against unknown keys, immutability, and YAML round-tripping.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from pdsim.config import ExperimentConfig, get_spec, load_config, save_config
from pdsim.config.experiment import GameConfig, PopulationConfig

# Strategy names are not validated until the strategy registry lands
# (milestone 3), so tests use the planned v1 machine names.
_COMPOSITION = {"tit_for_tat": 60, "always_defect": 40}


def _minimal_config(**overrides: object) -> ExperimentConfig:
    """Build a valid config from registry defaults plus a population mix.

    Args:
        **overrides: Top-level ExperimentConfig fields to replace.

    Returns:
        A validated ExperimentConfig.
    """
    fields: dict = {"population": {"size": 100, "composition": dict(_COMPOSITION)}}
    fields.update(overrides)
    return ExperimentConfig.model_validate(fields)


class TestRegistryIsTheSourceOfTruth:
    """Field defaults and ranges must flow from the Parameter Registry."""

    def test_defaults_match_registry(self) -> None:
        """Spot-check that unset fields equal their registry defaults."""
        cfg = _minimal_config()
        assert cfg.seed == get_spec("run.seed").default
        assert cfg.game.payoff_temptation == get_spec("game.payoff_temptation").default
        assert cfg.match.rounds_per_match == get_spec("match.rounds_per_match").default
        assert cfg.dynamics.mutation_rate == get_spec("dynamics.mutation_rate").default
        assert cfg.population.memory_depth is None

    def test_registry_ranges_enforced_through_config(self) -> None:
        """A value violating its registry range must fail config validation."""
        with pytest.raises(ValidationError, match="at most"):
            _minimal_config(dynamics={"mutation_rate": 1.5})

    def test_registry_choices_enforced_through_config(self) -> None:
        """A value outside its registry choices must fail config validation."""
        with pytest.raises(ValidationError, match="must be one of"):
            _minimal_config(matching={"matcher": "telepathy"})

    def test_continuation_probability_must_stay_below_one(self) -> None:
        """Setting w to 1.0 would mean matches never end; the bound catches it."""
        with pytest.raises(ValidationError, match="strictly below"):
            _minimal_config(match={"continuation_probability": 1.0})


class TestGameShapeValidation:
    """The togglable T>R>P>S and 2R>T+S rules from docs/DESIGN.md §2.1."""

    def test_pd_ordering_violation_rejected(self) -> None:
        """Payoffs breaking T > R > P > S fail while the toggle is on."""
        with pytest.raises(ValidationError, match="T > R > P > S"):
            GameConfig(payoff_temptation=1.0, payoff_reward=3.0)

    def test_pd_ordering_can_be_relaxed(self) -> None:
        """Turning the toggle off legitimately allows neighboring games."""
        cfg = GameConfig(
            payoff_temptation=1.0,
            payoff_reward=3.0,
            enforce_pd_ordering=False,
            enforce_alternation_constraint=False,
        )
        assert cfg.payoff_temptation == 1.0

    def test_alternation_constraint_enforced(self) -> None:
        """Payoffs where alternating exploitation ties cooperation are rejected."""
        # T=6, S=0, R=3: 2R = T + S exactly, so the strict rule fails.
        with pytest.raises(ValidationError, match="2R > T \\+ S"):
            GameConfig(payoff_temptation=6.0)

    def test_alternation_constraint_can_be_relaxed(self) -> None:
        """The 2R > T + S rule is togglable independently of the PD ordering."""
        cfg = GameConfig(payoff_temptation=6.0, enforce_alternation_constraint=False)
        assert cfg.payoff_temptation == 6.0


class TestPopulationComposition:
    """The strategy mix must be coherent with the population size."""

    def test_counts_must_sum_to_size(self) -> None:
        """A mismatch between size and composition total is an error."""
        with pytest.raises(ValidationError, match="must match exactly"):
            PopulationConfig(size=99, composition=dict(_COMPOSITION))

    def test_composition_must_be_nonempty(self) -> None:
        """An experiment with no strategies makes no sense."""
        with pytest.raises(ValidationError, match="at least one strategy"):
            PopulationConfig(size=100, composition={})

    def test_zero_counts_rejected(self) -> None:
        """Zero-count entries must be removed, not listed."""
        with pytest.raises(ValidationError, match="at least one agent"):
            PopulationConfig(size=60, composition={"tit_for_tat": 60, "random": 0})


class TestStrictnessAndImmutability:
    """Reproducibility guards: no silent typos, no mid-run mutation."""

    def test_unknown_keys_rejected(self) -> None:
        """A typo'd key must fail loudly instead of being ignored."""
        with pytest.raises(ValidationError, match=r"extra_forbidden|Extra inputs"):
            _minimal_config(dynamics={"mutation_rte": 0.05})

    def test_configs_are_frozen(self) -> None:
        """A constructed config is a value; assignment must raise."""
        cfg = _minimal_config()
        with pytest.raises(ValidationError):
            cfg.seed = 7  # type: ignore[misc]


class TestYamlRoundTrip:
    """save_config / load_config must reproduce configs exactly (hard rule 8)."""

    def test_round_trip_preserves_config(self, tmp_path: Path) -> None:
        """Saving then loading yields an equal ExperimentConfig."""
        cfg = _minimal_config(
            seed=123,
            match={"length_mode": "continuation", "continuation_probability": 0.95},
            dynamics={"selection_beta": 2.5, "mutation_rate": 0.05},
        )
        path = save_config(cfg, tmp_path / "config.yaml")
        assert load_config(path) == cfg

    def test_load_handwritten_yaml(self, tmp_path: Path) -> None:
        """A hand-written YAML file (the batch interface) loads correctly."""
        path = tmp_path / "config.yaml"
        path.write_text(
            """
seed: 7
game:
  payoff_temptation: 5.0
  payoff_reward: 3.0
match:
  noise_epsilon: 0.02
population:
  size: 4
  composition:
    tit_for_tat: 2
    always_defect: 2
dynamics:
  generations: 10
""",
            encoding="utf-8",
        )
        cfg = load_config(path)
        assert cfg.seed == 7
        assert cfg.match.noise_epsilon == 0.02
        assert cfg.population.size == 4
        # Unspecified values still come from the registry:
        assert cfg.dynamics.selection_beta == get_spec("dynamics.selection_beta").default

    def test_non_mapping_yaml_rejected(self, tmp_path: Path) -> None:
        """A YAML file that isn't a mapping gives a clear error."""
        path = tmp_path / "bad.yaml"
        path.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_config(path)
