"""Tests for the Streamlit-free UI helpers (``pdsim/ui/helpers.py``).

Covers: the config → widget-values → config round trip, panel spec
selection, the "Custom" default composition, strategy-parameter collection,
and readable validation messages. No Streamlit import anywhere — that is
the point of the helper layer (DECISIONS #38).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pdsim.config.scenarios import get_scenario_info
from pdsim.ui import helpers


class TestPanelSpecs:
    """Which registry entries the generated panel renders."""

    def test_strategy_parameters_are_excluded(self) -> None:
        """strategy.* specs render in their own expander, not the panel."""
        keys = [spec.key for spec in helpers.panel_specs()]
        assert not any(key.startswith("strategy.") for key in keys)
        assert "dynamics.selection_beta" in keys
        assert "run.mode" in keys


class TestConfigRoundTrip:
    """Scenario loading and config assembly must be exact inverses."""

    @pytest.mark.parametrize("name", ["classic_tournament", "defectors_paradise"])
    def test_widget_values_round_trip_scenarios(self, name: str) -> None:
        """Config -> widget values -> config reproduces the scenario."""
        original = get_scenario_info(name).config
        rebuilt = helpers.build_config(
            helpers.widget_values_from_config(original),
            original.population.composition,
            original.strategy_params,
        )
        assert rebuilt == original

    def test_zero_counts_are_dropped(self) -> None:
        """UI mix widgets allow 0; configs require >= 1 — zeros vanish."""
        values = helpers.default_widget_values()
        values["population.size"] = 4
        config = helpers.build_config(values, {"tit_for_tat": 2, "always_defect": 2, "pavlov": 0})
        assert config.population.composition == {"tit_for_tat": 2, "always_defect": 2}

    def test_validation_errors_surface(self) -> None:
        """A bad mix raises pydantic's error for the UI to render."""
        values = helpers.default_widget_values()
        with pytest.raises(ValidationError):
            helpers.build_config(values, {"tit_for_tat": 3})  # size defaults to 100


class TestDefaultComposition:
    """The 'Custom' starting mix (DECISIONS #40)."""

    def test_even_split_with_remainder_to_earliest(self) -> None:
        """100 agents over 7 strategies: two 15s, five 14s, sum exact."""
        names = ["a", "b", "c", "d", "e", "f", "g"]
        mix = helpers.default_composition(100, names)
        assert sum(mix.values()) == 100
        assert mix["a"] == 15 and mix["b"] == 15 and mix["c"] == 14

    def test_small_sizes_leave_zero_counts(self) -> None:
        """Fewer agents than strategies: trailing names get 0 (droppable)."""
        mix = helpers.default_composition(4, ["a", "b", "c", "d", "e", "f", "g"])
        assert sum(mix.values()) == 4
        assert mix == {"a": 1, "b": 1, "c": 1, "d": 1, "e": 0, "f": 0, "g": 0}


class TestStrategyParams:
    """Only non-default overrides enter the config (DECISIONS #41)."""

    def test_untouched_values_produce_no_overrides(self) -> None:
        """Defaults in -> empty overrides out (config stays clean)."""
        defaults = {
            "strategy.random.cooperation_probability": 0.5,
            "strategy.generous_tit_for_tat.generosity": 1 / 3,
        }
        assert helpers.collect_strategy_params(defaults) == {}

    def test_changed_values_are_collected_by_strategy(self) -> None:
        """A changed value lands under its strategy's machine name."""
        overrides = helpers.collect_strategy_params(
            {"strategy.random.cooperation_probability": 0.9}
        )
        assert overrides == {"random": {"cooperation_probability": 0.9}}


class TestValidationMessages:
    """pydantic errors become plain sentences for st.error."""

    def test_registry_message_survives_without_framing(self) -> None:
        """The registry's user-facing text comes through cleanly."""
        values = helpers.default_widget_values()
        values["dynamics.mutation_rate"] = 1.5
        try:
            helpers.build_config(values, {"tit_for_tat": 100})
        except ValidationError as error:
            messages = helpers.validation_messages(error)
        assert any("at most" in message for message in messages)
        assert not any(message.startswith("Value error") for message in messages)
