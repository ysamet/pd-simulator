"""Tests for the Scenario Registry (``pdsim/config/scenarios.py``).

Covers: the five v1 seed scenarios are registered with valid configs and
novice-grade documentation, registry lookup ergonomics, and an end-to-end
smoke run of every scenario (size-reduced) through the engine's event
stream.
"""

from __future__ import annotations

import numpy as np
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
from pdsim.core.dynamics import build_initial_population
from pdsim.core.events import CycleFinished, GenerationFinished, RunFinished
from pdsim.core.layouts import found_population
from pdsim.core.strategies.registry import strategy_name_of

V1_SCENARIOS = {
    "classic_tournament",
    "reciprocity_takes_over",
    "noise_breaks_the_grim",
    "drift_vs_meritocracy",
    "defectors_paradise",
}

ALL_SCENARIOS = V1_SCENARIOS | {
    "the_growth_economy",
    "async_death_birth_fixation",
    "imitation_overlay_only",
    "moran_random_mix",
    "sync_vs_async_economy",
    "spatial_reciprocity",
    "donation_game_threshold",
    "the_drifting_frontier",
    "the_filling_grid",
    "the_restless_frontier",
}
"""The five v1 seed scenarios, M10a's energy-economy scenario, the four
M10b event-time scenarios (spec Validation V1/V2/V3/V5), the four M11a
population-structure scenarios (DECISIONS #151), and M11b's movement
validation scenario (DECISIONS #191 R1)."""


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
    # An async fixed_n lattice run pins N to the site count, so the grid
    # must shrink with the population: 9 agents on 3 x 3 — the smallest
    # square that keeps a torus neighbourhood non-degenerate (M11a; the
    # composition is topped up cyclically to reach the 9). Larger rosters
    # would overflow 3 x 3 and fail validation loudly — revisit then.
    if (
        data["dynamics"]["time_model"] == "asynchronous"
        and data["dynamics"]["async_population"] == "fixed_n"
        and data["structure"]["kind"] == "lattice"
    ):
        data["structure"]["rows"] = 3
        data["structure"]["cols"] = 3
        names = sorted(composition)
        index = 0
        while sum(composition.values()) < 9:
            composition[names[index % len(names)]] += 1
            index += 1
        data["population"]["size"] = 9
    # random_k's k must fit the shrunk population (k ≤ N − 1 at generation 0).
    data["matching"]["opponents_per_agent"] = min(
        data["matching"]["opponents_per_agent"], data["population"]["size"] - 1
    )
    data["dynamics"]["generations"] = 2
    data["tournament_cycles"] = 2
    # Period counting below assumes one period per generation(-equivalent),
    # so a scenario's denser recording cadence (M10b Output section) is
    # reset to the default — the cadence is observer-only (#35), so the
    # smoke-run shape is otherwise unaffected.
    data["output"] = {}
    if data["match"]["length_mode"] == "continuation":
        data["match"]["continuation_probability"] = 0.5
    else:
        data["match"]["rounds_per_match"] = 5
    return ExperimentConfig.model_validate(data)


class TestSeedScenarios:
    """The five curated scenarios from DESIGN §5.1."""

    def test_all_registered(self) -> None:
        """The registry holds exactly the curated scenarios."""
        assert set(all_scenario_names()) == ALL_SCENARIOS

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


class TestRestlessFrontier:
    """The E5 movement scenario (DECISIONS #191 R1): the flagship plus one section."""

    def test_differs_from_the_flagship_only_in_movement(self) -> None:
        """Validated config to validated config, every other number is the flagship's."""
        frontier = get_scenario_info("the_restless_frontier")
        flagship = get_scenario_info("spatial_reciprocity")
        assert frontier.display_name == "The Restless Frontier"
        a = frontier.config.model_dump(mode="json")
        b = flagship.config.model_dump(mode="json")
        assert a["movement"] == {"rate": 0.5, "radius": 1, "decay": 0.0}
        assert b["movement"]["rate"] == 0.0
        del a["movement"], b["movement"]
        assert a == b
        assert a["seed"] == 42
        assert a["dynamics"]["generations"] == 100

    def test_founding_is_the_flagships_cell_for_cell(self) -> None:
        """Same seed, founding before the first movement step: generation 0 matches.

        A headless founding of each config — the engine's own
        ``build_initial_population`` then ``found_population`` on a fresh
        generator at the shared seed, the first RNG consumer of a run —
        compared site for site and strategy for strategy.
        """
        placements: dict[str, dict[int, tuple[str, object]]] = {}
        for name in ("spatial_reciprocity", "the_restless_frontier"):
            config = get_scenario_info(name).config
            founders = build_initial_population(config)
            occupancy = found_population(config, founders, np.random.default_rng(config.seed))
            assert occupancy is not None
            placements[name] = {
                agent.agent_id: (
                    strategy_name_of(agent.strategy),
                    occupancy.site_of(agent.agent_id),
                )
                for agent in founders
            }
        assert placements["spatial_reciprocity"] == placements["the_restless_frontier"]
        assert len(placements["the_restless_frontier"]) == 200
        assert len({site for _, site in placements["the_restless_frontier"].values()}) == 200

    def test_the_text_carries_the_arithmetic_and_the_direction(self) -> None:
        """The flagship's figures reused unchanged; movement stated as direction."""
        info = get_scenario_info("the_restless_frontier")
        for figure in (
            "8 matches",
            "8n − 8",
            "8n − 20",
            "+12",
            "+4",
            "−4",
            "generation 4",
            "generation 2",
            "seed, 42",
        ):
            assert figure in info.description, figure
        assert "Blocked moves this generation" in info.description
        for hint in ("Rate 0", "rate 1", "blank", "rate 0.1"):
            assert hint in info.things_to_try, hint


class TestScenariosRunEndToEnd:
    """Every scenario must actually run through the engine (size-reduced)."""

    @pytest.mark.parametrize("name", sorted(ALL_SCENARIOS))
    def test_scenario_smoke_run(self, name: str) -> None:
        """The event stream terminates with exactly one RunFinished."""
        config = _shrunk(get_scenario_info(name).config)
        events = list(engine.run(config))
        assert isinstance(events[-1], RunFinished)
        assert sum(isinstance(e, RunFinished) for e in events) == 1
        period_type = CycleFinished if config.mode == "tournament" else GenerationFinished
        assert sum(isinstance(e, period_type) for e in events) == 2
