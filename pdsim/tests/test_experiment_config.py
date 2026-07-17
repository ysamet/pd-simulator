"""Tests for ExperimentConfig and YAML load/save (``pdsim/config/experiment.py``).

Covers: registry-driven defaults, payoff-shape validation, composition rules,
strictness against unknown keys, immutability, and YAML round-tripping.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from pdsim.config import ExperimentConfig, get_spec, load_config, save_config
from pdsim.config.experiment import GameConfig, PopulationConfig

# Machine names from the strategy registry (pdsim/core/strategies/) —
# composition names are validated against the registered roster.
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

    def test_unknown_strategy_name_rejected(self) -> None:
        """Names are validated against the strategy registry (DECISIONS #25)."""
        with pytest.raises(ValidationError, match="unknown strategy name"):
            PopulationConfig(size=100, composition={"tit_for_tot": 100})

    def test_unknown_name_error_lists_the_valid_roster(self) -> None:
        """The error message must teach the user the valid names."""
        with pytest.raises(ValidationError, match="pavlov"):
            PopulationConfig(size=100, composition={"telepathy": 100})


class TestMatchingValidation:
    """The random_k cross-parameter check (DECISIONS #57)."""

    def test_random_k_accepts_k_up_to_n_minus_one(self) -> None:
        """The exhaustive edge case k = N - 1 must validate."""
        cfg = _minimal_config(matching={"matcher": "random_k", "opponents_per_agent": 99})
        assert cfg.matching.opponents_per_agent == 99

    def test_random_k_rejects_k_beyond_the_population(self) -> None:
        """Beyond N - 1 opponents, a plain-language cross-parameter error."""
        with pytest.raises(ValidationError, match="only 99 possible"):
            _minimal_config(matching={"matcher": "random_k", "opponents_per_agent": 100})

    def test_k_is_ignored_under_round_robin(self) -> None:
        """The #34 ignored-parameter pattern: oversized k is fine when unused.

        Valid, no effect, no RNG consumed — so configs can switch matchers
        without surgery and the UI greys k out instead of hiding it.
        """
        cfg = _minimal_config(matching={"matcher": "round_robin", "opponents_per_agent": 5000})
        assert cfg.matching.opponents_per_agent == 5000

    def test_random_k_config_round_trips(self, tmp_path: Path) -> None:
        """Matching fields survive YAML save/load exactly (hard rule 8)."""
        cfg = _minimal_config(matching={"matcher": "random_k", "opponents_per_agent": 7})
        assert load_config(save_config(cfg, tmp_path / "rk.yaml")) == cfg


class TestSelectionValidation:
    """The tournament_k cross-parameter check (DECISIONS #63)."""

    def test_tournament_k_accepts_k_up_to_n(self) -> None:
        """The exhaustive edge case k = N must validate."""
        cfg = _minimal_config(
            dynamics={"selection_rule": "tournament_k", "selection_tournament_k": 100}
        )
        assert cfg.dynamics.selection_tournament_k == 100

    def test_tournament_k_rejects_k_beyond_the_population(self) -> None:
        """Beyond N candidates, a plain-language cross-parameter error."""
        with pytest.raises(ValidationError, match="only has 100 agents"):
            _minimal_config(
                dynamics={"selection_rule": "tournament_k", "selection_tournament_k": 101}
            )

    def test_k_is_ignored_under_other_rules(self) -> None:
        """The #34 ignored-parameter pattern: oversized k is fine when unused."""
        cfg = _minimal_config(dynamics={"selection_tournament_k": 5000})
        assert cfg.dynamics.selection_rule == "fermi"
        assert cfg.dynamics.selection_tournament_k == 5000

    def test_k_is_ignored_in_tournament_mode(self) -> None:
        """In tournament mode ALL dynamics parameters are inert (#34).

        Even an oversized tournament_k under the tournament_k rule passes:
        nothing in the dynamics section is consumed there.
        """
        cfg = _minimal_config(
            mode="tournament",
            dynamics={"selection_rule": "tournament_k", "selection_tournament_k": 5000},
        )
        assert cfg.mode == "tournament"

    def test_elite_fraction_must_be_above_zero(self) -> None:
        """An elite fraction of 0 is rejected by the minimum_exclusive bound."""
        with pytest.raises(ValidationError, match="strictly above"):
            _minimal_config(dynamics={"selection_elite_fraction": 0.0})

    def test_accounting_discount_must_stay_below_one(self) -> None:
        """λ = 1 would mean new scores never matter."""
        with pytest.raises(ValidationError, match="strictly below"):
            _minimal_config(dynamics={"accounting_discount": 1.0})

    def test_new_dynamics_config_round_trips(self, tmp_path: Path) -> None:
        """M9a fields survive YAML save/load exactly (hard rule 8)."""
        cfg = _minimal_config(
            dynamics={
                "selection_rule": "truncation",
                "selection_elite_fraction": 0.25,
                "score_accounting": "exponential_discount",
                "accounting_discount": 0.75,
            }
        )
        assert load_config(save_config(cfg, tmp_path / "m9a.yaml")) == cfg


class TestRunMode:
    """The run-mode fields (DECISIONS #34)."""

    def test_default_mode_is_evolution(self) -> None:
        """Untouched configs run the evolutionary loop."""
        cfg = _minimal_config()
        assert cfg.mode == "evolution"
        assert cfg.tournament_cycles == get_spec("run.tournament_cycles").default

    def test_tournament_mode_accepted_with_dynamics_settings(self) -> None:
        """Dynamics settings stay valid in tournament mode (DECISIONS #34).

        Ignored rather than rejected, so configs can switch modes without
        surgery and the UI can simply grey these parameters out.
        """
        cfg = _minimal_config(mode="tournament", dynamics={"selection_beta": 5.0})
        assert cfg.mode == "tournament"
        assert cfg.dynamics.selection_beta == 5.0

    def test_unknown_mode_rejected(self) -> None:
        """Only the two registered modes exist."""
        with pytest.raises(ValidationError, match="must be one of"):
            _minimal_config(mode="battle_royale")

    def test_tournament_cycles_must_be_positive(self) -> None:
        """Zero cycles would mean an empty run."""
        with pytest.raises(ValidationError, match="at least"):
            _minimal_config(tournament_cycles=0)

    def test_tournament_config_round_trips(self, tmp_path: Path) -> None:
        """Mode fields survive YAML save/load exactly (hard rule 8)."""
        cfg = _minimal_config(mode="tournament", tournament_cycles=7)
        assert load_config(save_config(cfg, tmp_path / "t.yaml")) == cfg


class TestStrategyParams:
    """Per-run strategy parameter overrides (DECISIONS #30)."""

    def test_defaults_to_no_overrides(self) -> None:
        """Omitting the section means registry defaults everywhere."""
        assert _minimal_config().strategy_params == {}

    def test_valid_override_accepted(self) -> None:
        """A well-formed override is stored as given."""
        cfg = _minimal_config(strategy_params={"random": {"cooperation_probability": 0.9}})
        assert cfg.strategy_params == {"random": {"cooperation_probability": 0.9}}

    def test_strategy_absent_from_composition_is_allowed(self) -> None:
        """Params for a non-composition strategy are legal (DECISIONS #30).

        A no-op for the initial population — but mutation may still
        introduce that strategy mid-run, and then these values apply.
        """
        cfg = _minimal_config(
            strategy_params={"generous_tit_for_tat": {"generosity": 0.5}},
        )
        assert "generous_tit_for_tat" not in cfg.population.composition
        assert cfg.strategy_params["generous_tit_for_tat"] == {"generosity": 0.5}

    def test_unknown_strategy_rejected(self) -> None:
        """Overrides for a strategy that doesn't exist fail loudly."""
        with pytest.raises(ValidationError, match="unknown strategy"):
            _minimal_config(strategy_params={"telepathy": {"power": 1.0}})

    def test_unknown_parameter_rejected(self) -> None:
        """Overrides must name parameters the strategy actually declares."""
        with pytest.raises(ValidationError, match="cooperation_probability"):
            _minimal_config(strategy_params={"random": {"generosity": 0.5}})

    def test_parameterless_strategy_rejects_overrides(self) -> None:
        """A strategy without parameters accepts no overrides at all."""
        with pytest.raises(ValidationError, match="no parameters"):
            _minimal_config(strategy_params={"tit_for_tat": {"generosity": 0.5}})

    def test_out_of_range_value_rejected(self) -> None:
        """Override values validate against their registry specs."""
        with pytest.raises(ValidationError, match="at most"):
            _minimal_config(strategy_params={"random": {"cooperation_probability": 2.0}})


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
            strategy_params={"random": {"cooperation_probability": 0.25}},
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


class TestEconomyConfig:
    """M10a: the derived defaults and the two economy cross-field checks."""

    def test_resolve_initial_energy(self) -> None:
        """None means 'same as the offspring stake'; numbers pass through."""
        from pdsim.config.experiment import resolve_initial_energy

        assert resolve_initial_energy(None, 400.0) == 400.0
        assert resolve_initial_energy(250.0, 400.0) == 250.0
        assert resolve_initial_energy(0.0, 400.0) == 0.0  # explicit zero is not auto

    def test_resolve_senescence_factor(self) -> None:
        """The auto rule and its worked example (0.01, 20 → 1.2589…)."""
        from pdsim.config.experiment import resolve_senescence_factor

        assert resolve_senescence_factor(None, 0.01, 20) == pytest.approx(1.2589, abs=1e-4)
        assert resolve_senescence_factor(None, 0.0, 20) == 1.0  # no hazard: nothing to calibrate
        assert resolve_senescence_factor(None, 0.01, 0) == 1.0  # no cap: nothing to calibrate
        assert resolve_senescence_factor(1.6, 0.01, 20) == 1.6  # explicit override passes through

    def test_derived_defaults_resolve_at_construction(self) -> None:
        """A config never holds None for the two auto fields."""
        cfg = _minimal_config()
        assert cfg.dynamics.initial_energy == 400.0  # the default stake
        assert cfg.dynamics.senescence_factor == 1.0

    def test_auto_follows_the_configured_stake_and_mortality(self) -> None:
        """The resolver reads sibling raw inputs, not just registry defaults."""
        cfg = _minimal_config(
            dynamics={
                "reproduction_mode": "energy_economy",
                "offspring_stake": 250.0,
                "reproduction_threshold": 300.0,
                "base_hazard": 0.01,
                "max_age": 20,
            }
        )
        assert cfg.dynamics.initial_energy == 250.0
        assert cfg.dynamics.senescence_factor == pytest.approx(1.2589, abs=1e-4)

    def test_saved_yaml_holds_plain_numbers(self, tmp_path: Path) -> None:
        """Hard rule 8: the auto rule can never change a stored run."""
        cfg = _minimal_config()
        path = save_config(cfg, tmp_path / "config.yaml")
        text = path.read_text(encoding="utf-8")
        assert "initial_energy: 400.0" in text
        assert "senescence_factor: 1.0" in text
        assert load_config(path) == cfg

    def test_stake_above_threshold_rejected_in_economy_mode(self) -> None:
        """σ > θ would make reproduction suicidal — a plain-message error."""
        with pytest.raises(ValidationError, match="offspring_stake"):
            _minimal_config(
                dynamics={
                    "reproduction_mode": "energy_economy",
                    "offspring_stake": 600.0,
                    "reproduction_threshold": 500.0,
                }
            )

    def test_stake_above_threshold_ignored_under_imitation(self) -> None:
        """#34: ignored parameters are never validation errors."""
        cfg = _minimal_config(dynamics={"offspring_stake": 600.0, "reproduction_threshold": 500.0})
        assert cfg.dynamics.reproduction_mode == "imitation"

    def test_capacity_below_population_rejected_in_economy_mode(self) -> None:
        """Generation 0 must not already exceed K."""
        with pytest.raises(ValidationError, match="carrying_capacity"):
            _minimal_config(
                dynamics={"reproduction_mode": "energy_economy", "carrying_capacity": 50}
            )

    def test_capacity_below_population_ignored_under_imitation(self) -> None:
        """Pre-M10a configs (N > default K) must keep loading (hard rule 8)."""
        cfg = _minimal_config(
            population={
                "size": 300,
                "composition": {"tit_for_tat": 150, "always_defect": 150},
            }
        )
        assert cfg.dynamics.carrying_capacity == 200  # < N, and that is fine here
