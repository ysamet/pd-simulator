"""Tests for the Strategy Registry and roster auto-discovery (DECISIONS #25).

Covers: the seven v1 strategies are discovered by importing the package,
lookup and error ergonomics, ``StrategyInfo`` well-formedness, the
``create_strategy`` factory, and the novice-documentation guarantees that
mirror the Parameter Registry's.
"""

from __future__ import annotations

import pytest

from pdsim.config.registry import get_spec
from pdsim.core.strategies import (
    StrategyInfo,
    all_strategies,
    all_strategy_names,
    create_strategy,
    get_strategy_info,
    register_strategy,
    strategy_name_of,
)
from pdsim.core.strategies.generous_tit_for_tat import GenerousTitForTat
from pdsim.core.strategies.pavlov import Pavlov
from pdsim.core.strategies.random_strategy import Random
from pdsim.core.strategies.tit_for_tat import TitForTat
from pdsim.core.strategy import Strategy
from pdsim.tests.stub_strategies import StubAlwaysCooperate

V1_ROSTER = {
    "always_cooperate",
    "always_defect",
    "generous_tit_for_tat",
    "grim_trigger",
    "pavlov",
    "random",
    "tit_for_tat",
}


class TestDiscovery:
    """Importing the package must populate the full roster."""

    def test_all_seven_v1_strategies_registered(self) -> None:
        """The roster contains exactly the DESIGN §2.3 strategy set."""
        assert set(all_strategy_names()) == V1_ROSTER

    def test_lookup_returns_the_right_class(self) -> None:
        """get_strategy_info wires machine names to their classes."""
        assert get_strategy_info("tit_for_tat").factory is TitForTat
        assert get_strategy_info("pavlov").factory is Pavlov

    def test_all_strategies_matches_names(self) -> None:
        """The two roster views agree with each other."""
        assert tuple(info.name for info in all_strategies()) == all_strategy_names()

    def test_unknown_name_lists_known_ones(self) -> None:
        """A typo'd lookup names the valid strategies (typo ergonomics)."""
        with pytest.raises(KeyError, match="tit_for_tat"):
            get_strategy_info("tit_for_tot")

    def test_duplicate_registration_rejected(self) -> None:
        """Re-registering an existing machine name is always a bug."""
        with pytest.raises(ValueError, match="already registered"):
            register_strategy(get_strategy_info("pavlov"))

    def test_strategy_name_of_reverses_create_strategy(self) -> None:
        """An instance can be traced back to its machine name."""
        assert strategy_name_of(create_strategy("pavlov")) == "pavlov"
        assert strategy_name_of(TitForTat()) == "tit_for_tat"

    def test_strategy_name_of_rejects_unregistered_classes(self) -> None:
        """Test stubs and other outsiders have no machine name."""
        with pytest.raises(KeyError, match="not a registered strategy class"):
            strategy_name_of(StubAlwaysCooperate())


class TestStrategyInfoWellFormedness:
    """StrategyInfo validates its own declaration at construction.

    These infos are constructed but never registered, keeping the module
    dict pristine (same convention as the Parameter Registry tests).
    """

    def test_bad_machine_name_rejected(self) -> None:
        """Machine names must be lowercase tokens (persistence surface)."""
        with pytest.raises(ValueError, match="lowercase token"):
            StrategyInfo(
                name="TitForTat",
                display_name="Bad Name",
                description="A throwaway declaration used only in this test.",
                factory=StubAlwaysCooperate,
            )

    def test_blank_description_rejected(self) -> None:
        """A strategy without an explanation violates hard rule 3's mirror."""
        with pytest.raises(ValueError, match="no description"):
            StrategyInfo(
                name="nameless",
                display_name="Nameless",
                description="   ",
                factory=StubAlwaysCooperate,
            )

    def test_foreign_parameter_key_rejected(self) -> None:
        """Parameter keys must live under the strategy's own namespace."""
        foreign_spec = get_spec("strategy.random.cooperation_probability")
        with pytest.raises(ValueError, match="must start with"):
            StrategyInfo(
                name="impostor",
                display_name="Impostor",
                description="A throwaway declaration used only in this test.",
                factory=StubAlwaysCooperate,
                params=(foreign_spec,),
            )

    def test_param_names_are_last_key_segments(self) -> None:
        """The constructor-keyword mapping is the final dotted segment."""
        assert get_strategy_info("random").param_names() == ("cooperation_probability",)
        assert get_strategy_info("generous_tit_for_tat").param_names() == ("generosity",)
        assert get_strategy_info("tit_for_tat").param_names() == ()


class TestCreateStrategy:
    """The factory the engine (M4 mutation) and UI (M6) construct through."""

    @pytest.mark.parametrize("name", sorted(V1_ROSTER))
    def test_builds_every_registered_strategy(self, name: str) -> None:
        """Every roster entry constructs with defaults into a Strategy."""
        assert isinstance(create_strategy(name), Strategy)

    def test_override_takes_effect(self) -> None:
        """A parameter override reaches the constructed instance."""
        strategy = create_strategy("random", cooperation_probability=0.9)
        assert isinstance(strategy, Random)
        assert strategy.cooperation_probability == 0.9

    def test_defaults_used_when_no_override(self) -> None:
        """Omitted parameters fall back to their registry defaults."""
        strategy = create_strategy("generous_tit_for_tat")
        assert isinstance(strategy, GenerousTitForTat)
        assert strategy.generosity == get_spec("strategy.generous_tit_for_tat.generosity").default

    def test_unknown_parameter_rejected_with_valid_list(self) -> None:
        """Wrong parameter names fail loudly, naming the valid ones."""
        with pytest.raises(ValueError, match="cooperation_probability"):
            create_strategy("random", generosity=0.5)

    def test_parameterless_strategy_rejects_any_parameter(self) -> None:
        """Strategies without parameters accept no overrides at all."""
        with pytest.raises(ValueError, match="no parameters"):
            create_strategy("grim_trigger", generosity=0.5)

    def test_out_of_range_override_rejected(self) -> None:
        """Value validation flows through the parameter's registry spec."""
        with pytest.raises(ValueError, match="at most"):
            create_strategy("generous_tit_for_tat", generosity=2.0)

    def test_unknown_strategy_name_rejected(self) -> None:
        """Unknown machine names raise the roster-listing KeyError."""
        with pytest.raises(KeyError, match="Registered strategies"):
            create_strategy("telepathy")


class TestRosterDocumentation:
    """Novice-first guarantees, mirroring the Parameter Registry tests."""

    def test_every_strategy_is_novice_documented(self) -> None:
        """Every roster entry has a real description and display name."""
        for info in all_strategies():
            assert len(info.description.split()) >= 8, f"{info.name} description too thin"
            assert info.display_name.strip(), f"{info.name} has no display name"

    def test_every_factory_is_a_strategy_subclass(self) -> None:
        """The factory contract: every entry constructs a Strategy."""
        for info in all_strategies():
            assert issubclass(info.factory, Strategy), info.name

    def test_strategy_parameters_live_in_the_parameter_registry(self) -> None:
        """Strategy params are ordinary registry entries (hard rule 3)."""
        for info in all_strategies():
            for spec in info.params:
                assert get_spec(spec.key) is spec
