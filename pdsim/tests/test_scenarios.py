"""Tests for the Scenario Registry (``pdsim/config/scenarios.py``).

Covers: the five v1 seed scenarios are registered with valid configs and
novice-grade documentation, registry lookup ergonomics, and an end-to-end
smoke run of every scenario (size-reduced) through the engine's event
stream.
"""

from __future__ import annotations

import pytest

from pdsim.config.experiment import ExperimentConfig
from pdsim.config.scenarios import (
    ScenarioInfo,
    all_scenario_names,
    all_scenarios,
    get_scenario_info,
    register_scenario,
)
from pdsim.core import engine
from pdsim.core.events import CycleFinished, GenerationFinished, RunFinished

V1_SCENARIOS = {
    "classic_tournament",
    "reciprocity_takes_over",
    "noise_breaks_the_grim",
    "drift_vs_meritocracy",
    "defectors_paradise",
}


def _shrunk(config: ExperimentConfig) -> ExperimentConfig:
    """Derive a cheap variant of a scenario config for smoke tests.

    Configs are frozen, so the reduced version is built by dumping to plain
    data, shrinking, and re-validating — full validation applies, exactly
    as it would for a hand-written config.

    Args:
        config: The scenario's full-size config.

    Returns:
        A validated config with ≤2 agents per strategy, 2 generations or
        cycles, and short matches.
    """
    data = config.model_dump(mode="json")
    composition = {name: min(2, count) for name, count in data["population"]["composition"].items()}
    data["population"]["composition"] = composition
    data["population"]["size"] = sum(composition.values())
    data["dynamics"]["generations"] = 2
    data["tournament_cycles"] = 2
    if data["match"]["length_mode"] == "continuation":
        data["match"]["continuation_probability"] = 0.5
    else:
        data["match"]["rounds_per_match"] = 5
    return ExperimentConfig.model_validate(data)


class TestSeedScenarios:
    """The five curated scenarios from DESIGN §5.1."""

    def test_all_five_registered(self) -> None:
        """The registry holds exactly the v1 seed scenarios."""
        assert set(all_scenario_names()) == V1_SCENARIOS

    def test_configs_are_validated_experiment_configs(self) -> None:
        """Every scenario carries a real (already-validated) config."""
        for info in all_scenarios():
            assert isinstance(info.config, ExperimentConfig)
            assert sum(info.config.population.composition.values()) == info.config.population.size

    def test_every_scenario_is_novice_documented(self) -> None:
        """Description and things_to_try are real novice-facing prose."""
        for info in all_scenarios():
            assert len(info.description.split()) >= 8, f"{info.name} description too thin"
            assert len(info.things_to_try.split()) >= 8, f"{info.name} things_to_try too thin"
            assert info.display_name.strip(), f"{info.name} has no display name"

    def test_classic_tournament_is_tournament_mode(self) -> None:
        """Mode-specific spot checks on the two flagship scenarios."""
        assert get_scenario_info("classic_tournament").config.mode == "tournament"
        assert get_scenario_info("reciprocity_takes_over").config.mode == "evolution"


class TestRegistryMechanics:
    """The registry idiom, third instance — same ergonomics as the others."""

    def test_unknown_name_lists_known_ones(self) -> None:
        """A typo'd lookup names the valid scenarios."""
        with pytest.raises(KeyError, match="classic_tournament"):
            get_scenario_info("classic_turnament")

    def test_duplicate_registration_rejected(self) -> None:
        """Re-registering an existing machine name is always a bug."""
        with pytest.raises(ValueError, match="already registered"):
            register_scenario(get_scenario_info("drift_vs_meritocracy"))

    def test_malformed_declarations_rejected(self) -> None:
        """ScenarioInfo validates itself at construction (never registered)."""
        valid_config = get_scenario_info("classic_tournament").config
        with pytest.raises(ValueError, match="lowercase token"):
            ScenarioInfo(
                name="Bad Name",
                display_name="Bad",
                description="A throwaway declaration used only in this test.",
                config=valid_config,
                things_to_try="Nothing at all, this is a test declaration.",
            )
        with pytest.raises(ValueError, match="things_to_try"):
            ScenarioInfo(
                name="no_ideas",
                display_name="No Ideas",
                description="A throwaway declaration used only in this test.",
                config=valid_config,
                things_to_try="   ",
            )


class TestScenariosRunEndToEnd:
    """Every scenario must actually run through the engine (size-reduced)."""

    @pytest.mark.parametrize("name", sorted(V1_SCENARIOS))
    def test_scenario_smoke_run(self, name: str) -> None:
        """The event stream terminates with exactly one RunFinished."""
        config = _shrunk(get_scenario_info(name).config)
        events = list(engine.run(config))
        assert isinstance(events[-1], RunFinished)
        assert sum(isinstance(e, RunFinished) for e in events) == 1
        period_type = CycleFinished if config.mode == "tournament" else GenerationFinished
        assert sum(isinstance(e, period_type) for e in events) == 2
