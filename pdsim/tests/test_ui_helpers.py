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


class TestGreying:
    """Mode- and matcher-aware widget greying (the #34 pattern, plus #57)."""

    def test_dynamics_parameters_grey_out_in_tournament_mode(self) -> None:
        """Selection/mutation widgets disable with an explanatory note."""
        disabled, note = helpers.greying("dynamics.selection_beta", {"run.mode": "tournament"})
        assert disabled
        assert "tournament" in note

    def test_dynamics_parameters_stay_active_in_evolution_mode(self) -> None:
        """Evolution mode uses every dynamics parameter."""
        assert helpers.greying("dynamics.selection_beta", {"run.mode": "evolution"}) == (False, "")

    def test_tournament_cycles_grey_out_in_evolution_mode(self) -> None:
        """The inverse case: cycles matter only to tournaments."""
        disabled, note = helpers.greying("run.tournament_cycles", {"run.mode": "evolution"})
        assert disabled
        assert "tournament" in note

    def test_opponents_per_agent_greys_out_under_round_robin(self) -> None:
        """The k widget disables when the MATCHER says round_robin (#57)."""
        values = {"run.mode": "evolution", "matching.matcher": "round_robin"}
        disabled, note = helpers.greying("matching.opponents_per_agent", values)
        assert disabled
        assert "random_k" in note

    def test_opponents_per_agent_active_under_random_k(self) -> None:
        """Choosing random_k un-greys k immediately."""
        values = {"run.mode": "evolution", "matching.matcher": "random_k"}
        assert helpers.greying("matching.opponents_per_agent", values) == (False, "")

    def test_matcher_greying_is_keyed_off_the_matcher_not_the_mode(self) -> None:
        """Tournament mode does not grey k — only the matcher choice does."""
        values = {"run.mode": "tournament", "matching.matcher": "random_k"}
        disabled, _ = helpers.greying("matching.opponents_per_agent", values)
        assert not disabled

    def test_unrelated_parameters_never_grey(self) -> None:
        """Widgets outside the ignored sets are always active."""
        assert helpers.greying("game.payoff_reward", {"run.mode": "tournament"}) == (False, "")

    def test_rule_parameters_grey_unless_their_rule_is_selected(self) -> None:
        """Each selection rule's parameter keys off the rule widget (#63)."""
        values = {"run.mode": "evolution", "dynamics.selection_rule": "fermi"}
        for key, owner in [
            ("dynamics.selection_tournament_k", "tournament_k"),
            ("dynamics.selection_elite_fraction", "truncation"),
            ("dynamics.selection_threshold_multiplier", "threshold_cloning"),
        ]:
            disabled, note = helpers.greying(key, values)
            assert disabled
            assert owner in note
            active = {**values, "dynamics.selection_rule": owner}
            assert helpers.greying(key, active) == (False, "")

    def test_beta_greys_under_non_fermi_rules(self) -> None:
        """β is fermi's parameter; other rules never read it (#63)."""
        values = {"run.mode": "evolution", "dynamics.selection_rule": "proportional"}
        disabled, note = helpers.greying("dynamics.selection_beta", values)
        assert disabled
        assert "fermi" in note
        fermi = {**values, "dynamics.selection_rule": "fermi"}
        assert helpers.greying("dynamics.selection_beta", fermi) == (False, "")

    def test_accounting_parameters_grey_unless_their_choice_is_selected(self) -> None:
        """W and λ key off the score-accounting widget (#64)."""
        values = {"run.mode": "evolution", "dynamics.score_accounting": "per_generation"}
        for key, owner in [
            ("dynamics.accounting_window", "sliding_window"),
            ("dynamics.accounting_discount", "exponential_discount"),
        ]:
            disabled, note = helpers.greying(key, values)
            assert disabled
            assert owner in note
            active = {**values, "dynamics.score_accounting": owner}
            assert helpers.greying(key, active) == (False, "")

    def test_tournament_mode_greys_all_new_dynamics_parameters(self) -> None:
        """The whole dynamics section — accounting included — is inert (#34)."""
        values = {
            "run.mode": "tournament",
            "dynamics.selection_rule": "tournament_k",
            "dynamics.score_accounting": "sliding_window",
        }
        for key in [
            "dynamics.selection_tournament_k",
            "dynamics.score_accounting",
            "dynamics.accounting_window",
        ]:
            disabled, note = helpers.greying(key, values)
            assert disabled
            assert "tournament mode" in note


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
