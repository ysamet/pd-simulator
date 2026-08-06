"""Tests for the Streamlit-free UI helpers (``pdsim/ui/helpers.py``).

Covers: the config → widget-values → config round trip, panel spec
selection, the "Custom" default composition, strategy-parameter collection,
and readable validation messages. No Streamlit import anywhere — that is
the point of the helper layer (DECISIONS #38).
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

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


class TestEconomyGreying:
    """M10a: the coarse reproduction-mode split in the greying rules (#34)."""

    def test_selection_family_greys_out_under_the_economy(self) -> None:
        """Differential survival IS the selection — the copiers are inert."""
        values = {"run.mode": "evolution", "dynamics.reproduction_mode": "energy_economy"}
        for key in (
            "dynamics.selection_rule",
            "dynamics.selection_beta",
            "dynamics.score_accounting",
            "dynamics.accounting_window",
        ):
            disabled, note = helpers.greying(key, values)
            assert disabled, key
            assert "energy economy" in note

    def test_economy_knobs_grey_out_under_imitation(self) -> None:
        """The eleven knobs are only read in the energy economy."""
        values = {"run.mode": "evolution", "dynamics.reproduction_mode": "imitation"}
        for key in helpers._ECONOMY_PARAMS:
            disabled, note = helpers.greying(key, values)
            assert disabled, key
            assert "IGNORED under imitation" in note

    def test_mutation_rate_is_never_paradigm_greyed(self) -> None:
        """μ is consumed by BOTH modes (imitation slots, economy newborns)."""
        for mode in ("imitation", "energy_economy"):
            values = {"run.mode": "evolution", "dynamics.reproduction_mode": mode}
            disabled, _ = helpers.greying("dynamics.mutation_rate", values)
            assert not disabled, mode

    def test_paradigm_check_wins_over_the_rule_level_check(self) -> None:
        """Under the economy, β gets the paradigm note, not the fermi note."""
        values = {
            "run.mode": "evolution",
            "dynamics.reproduction_mode": "energy_economy",
            "dynamics.selection_rule": "proportional",
        }
        _, note = helpers.greying("dynamics.selection_beta", values)
        assert "energy economy" in note
        assert "fermi" not in note

    def test_everything_dynamics_greys_in_tournament_mode(self) -> None:
        """reproduction_mode and the economy knobs joined the #34 list."""
        values = {"run.mode": "tournament"}
        for key in ("dynamics.reproduction_mode", "dynamics.carrying_capacity"):
            disabled, note = helpers.greying(key, values)
            assert disabled, key
            assert "tournament" in note

    def test_economy_widgets_enabled_in_economy_mode(self) -> None:
        """The knobs are live exactly when the economy reads them."""
        values = {"run.mode": "evolution", "dynamics.reproduction_mode": "energy_economy"}
        disabled, note = helpers.greying("dynamics.carrying_capacity", values)
        assert not disabled
        assert note == ""


class TestDerivedDefaultWidgetValues:
    """M10a: resolved auto values present as blank (the resolver's inverse)."""

    def test_scenario_with_auto_values_loads_as_blank(self) -> None:
        """The growth-economy scenario stores resolved numbers, shown as auto."""
        config = get_scenario_info("the_growth_economy").config
        values = helpers.widget_values_from_config(config)
        assert values["dynamics.initial_energy"] is None  # 400 == the stake
        assert values["dynamics.senescence_factor"] is None  # 1.0 == auto

    def test_explicit_values_survive_the_round_trip(self) -> None:
        """A value the auto rule would NOT produce stays visible."""
        data = get_scenario_info("the_growth_economy").config.model_dump(mode="json")
        data["dynamics"]["initial_energy"] = 123.0
        data["dynamics"]["senescence_factor"] = 1.6
        from pdsim.config.experiment import ExperimentConfig

        config = ExperimentConfig.model_validate(data)
        values = helpers.widget_values_from_config(config)
        assert values["dynamics.initial_energy"] == 123.0
        assert values["dynamics.senescence_factor"] == 1.6

    def test_blank_values_reassemble_to_the_same_config(self) -> None:
        """The inverse mapping is loss-free: rebuild resolves right back."""
        config = get_scenario_info("the_growth_economy").config
        values = helpers.widget_values_from_config(config)
        rebuilt = helpers.build_config(values, dict(config.population.composition))
        assert rebuilt == config


class TestShouldRedraw:
    """The live view's wall-clock redraw throttle (DECISIONS #94)."""

    def test_first_period_always_draws(self) -> None:
        """last_redraw = 0.0 is the sentinel: any real clock clears it."""
        assert helpers.should_redraw(now=1000.0, last_redraw=0.0, delay=0.05, floor=0.5)

    def test_below_the_floor_skips(self) -> None:
        """Inside the window nothing is redrawn — the old frame stays up."""
        assert not helpers.should_redraw(now=1000.3, last_redraw=1000.0, delay=0.05, floor=0.5)

    def test_at_the_floor_draws(self) -> None:
        """The boundary itself redraws (>=, not >)."""
        assert helpers.should_redraw(now=1000.5, last_redraw=1000.0, delay=0.05, floor=0.5)

    def test_a_large_delay_stretches_the_window(self) -> None:
        """Slideshow mode: the slider governs once it exceeds the floor."""
        assert not helpers.should_redraw(now=1000.7, last_redraw=1000.0, delay=1.0, floor=0.5)
        assert helpers.should_redraw(now=1001.0, last_redraw=1000.0, delay=1.0, floor=0.5)

    def test_zero_delay_still_honors_the_floor(self) -> None:
        """A zero delay must not mean redraw-every-period — that is the flood."""
        assert not helpers.should_redraw(now=1000.1, last_redraw=1000.0, delay=0.0, floor=0.5)


class TestAsyncGreying:
    """M10b: the time-model split in the greying rules (spec's ignored map)."""

    SYNC: ClassVar[dict[str, str]] = {
        "run.mode": "evolution",
        "dynamics.time_model": "synchronous",
    }
    ASYNC: ClassVar[dict[str, str]] = {
        "run.mode": "evolution",
        "dynamics.time_model": "asynchronous",
    }

    def test_async_knobs_grey_under_the_synchronous_clock(self) -> None:
        """All eight M10b knobs disable on the generational clock (#34)."""
        for key in (
            "dynamics.async_population",
            "dynamics.moran_rule",
            "dynamics.moran_weight_birth_death",
            "dynamics.moran_weight_death_birth",
            "dynamics.fixed_n_death_rule",
            "dynamics.imitation_overlay",
            "output.recording_cadence",
            "output.recording_cadence_m",
        ):
            disabled, note = helpers.greying(key, self.SYNC)
            assert disabled, key
            assert "ASYNCHRONOUS" in note

    def test_generational_machinery_greys_under_async(self) -> None:
        """reproduction_mode, selection, accounting, matcher — all inert."""
        for key in (
            "dynamics.reproduction_mode",
            "dynamics.selection_rule",
            "dynamics.selection_tournament_k",
            "dynamics.selection_elite_fraction",
            "dynamics.selection_threshold_multiplier",
            "dynamics.score_accounting",
            "dynamics.accounting_window",
            "dynamics.accounting_discount",
            "matching.matcher",
        ):
            disabled, note = helpers.greying(key, self.ASYNC)
            assert disabled, key
            assert "asynchronous" in note

    def test_beta_follows_the_overlay_not_the_rule_or_mode(self) -> None:
        """The Phase C authoring gap, closed.

        Overlay ON reaches β even under energy_economy and a non-fermi
        rule — both inert in async.
        """
        off = {**self.ASYNC, "dynamics.imitation_overlay": False}
        disabled, note = helpers.greying("dynamics.selection_beta", off)
        assert disabled
        assert "overlay" in note
        on = {
            **self.ASYNC,
            "dynamics.imitation_overlay": True,
            "dynamics.reproduction_mode": "energy_economy",
            "dynamics.selection_rule": "proportional",
        }
        assert helpers.greying("dynamics.selection_beta", on) == (False, "")

    def test_opponents_per_agent_never_greys_under_async(self) -> None:
        """Async consumes k directly, whatever the matcher widget says.

        Even a stale round_robin matcher value must not grey it — the
        matcher itself is the inert one.
        """
        values = {**self.ASYNC, "matching.matcher": "round_robin"}
        assert helpers.greying("matching.opponents_per_agent", values) == (False, "")

    def test_moran_machinery_keys_off_the_population_mode(self) -> None:
        """fixed_n enables the Moran knobs; variable_n greys them."""
        fixed = {**self.ASYNC, "dynamics.async_population": "fixed_n"}
        variable = {**self.ASYNC, "dynamics.async_population": "variable_n"}
        for key in ("dynamics.moran_rule", "dynamics.fixed_n_death_rule"):
            assert helpers.greying(key, fixed) == (False, "")
            disabled, note = helpers.greying(key, variable)
            assert disabled, key
            assert "variable_n" in note

    def test_weights_need_fixed_n_and_the_random_rule(self) -> None:
        """The mixture weights are read only under moran_rule = random."""
        random_rule = {
            **self.ASYNC,
            "dynamics.async_population": "fixed_n",
            "dynamics.moran_rule": "random",
        }
        pure_rule = {**random_rule, "dynamics.moran_rule": "death_birth"}
        for key in (
            "dynamics.moran_weight_birth_death",
            "dynamics.moran_weight_death_birth",
        ):
            assert helpers.greying(key, random_rule) == (False, "")
            disabled, _ = helpers.greying(key, pure_rule)
            assert disabled, key

    def test_economy_demography_greys_under_fixed_n_but_ledger_stays(self) -> None:
        """theta/K/mortality are variable_n-only; the ledger runs in both."""
        fixed = {**self.ASYNC, "dynamics.async_population": "fixed_n"}
        for key in (
            "dynamics.reproduction_threshold",
            "dynamics.carrying_capacity",
            "dynamics.base_hazard",
            "dynamics.senescence_factor",
            "dynamics.max_age",
        ):
            disabled, note = helpers.greying(key, fixed)
            assert disabled, key
            assert "variable_n" in note
        for key in (
            "dynamics.offspring_stake",
            "dynamics.basic_living_cost",
            "dynamics.engagement_cost",
            "dynamics.capital_return_rate",
            "dynamics.reproduction_overhead",
            "dynamics.initial_energy",
            "dynamics.mutation_rate",
        ):
            assert helpers.greying(key, fixed) == (False, ""), key

    def test_cadence_m_needs_every_m_events(self) -> None:
        """The m widget keys off the cadence choice (#34 pattern)."""
        boundary = {**self.ASYNC, "output.recording_cadence": "per_generation_equivalent"}
        disabled, note = helpers.greying("output.recording_cadence_m", boundary)
        assert disabled
        assert "every_m_events" in note
        every_m = {**self.ASYNC, "output.recording_cadence": "every_m_events"}
        assert helpers.greying("output.recording_cadence_m", every_m) == (False, "")

    def test_tournament_still_wins_over_the_time_model(self) -> None:
        """A stale asynchronous time_model never un-greys tournament mode."""
        values = {"run.mode": "tournament", "dynamics.time_model": "asynchronous"}
        disabled, note = helpers.greying("dynamics.imitation_overlay", values)
        assert disabled
        assert "tournament mode" in note
        disabled, note = helpers.greying("output.recording_cadence", values)
        assert disabled
        assert "ASYNCHRONOUS" in note


class TestGridPreview:
    """The grid's visibility predicate and its minimal config (#121)."""

    def test_grid_visible_truth_table(self) -> None:
        """Evolution + lattice, nothing else consulted."""
        assert helpers.grid_visible({"run.mode": "evolution", "structure.kind": "lattice"})
        assert not helpers.grid_visible({"run.mode": "evolution", "structure.kind": "well_mixed"})
        assert not helpers.grid_visible({"run.mode": "tournament", "structure.kind": "lattice"})
        assert not helpers.grid_visible({})

    def test_visibility_ignores_reproduction_mode_and_time_model(self) -> None:
        """The defect's shape, pinned as a property.

        The two switches that hid the grid must not enter the predicate
        at all.
        """
        base = {"run.mode": "evolution", "structure.kind": "lattice"}
        for extra in (
            {"dynamics.reproduction_mode": "energy_economy"},
            {"dynamics.time_model": "asynchronous"},
            {"dynamics.reproduction_mode": "energy_economy", "dynamics.time_model": "asynchronous"},
        ):
            assert helpers.grid_visible({**base, **extra})

    def test_the_defect_itself_a_failing_section_elsewhere_cannot_hide_the_grid(self) -> None:
        """Regression pin for the observed disappearance (#121).

        N = 400 with the default K = 200: the FULL config fails validation
        under `energy_economy` (K >= N is checked exactly there), and that
        failure once took the preview down with it. The preview config must
        build anyway, because the grid never reads the dynamics section.
        """
        values = helpers.default_widget_values()
        values["run.mode"] = "evolution"
        values["structure.kind"] = "lattice"
        values["population.size"] = 400
        values["dynamics.reproduction_mode"] = "energy_economy"
        composition = {"always_cooperate": 200, "always_defect": 200}
        with pytest.raises(ValidationError):
            helpers.build_config(values, composition)  # the full panel fails...
        config = helpers.grid_preview_config(values, composition)  # ...the preview must not
        assert config.structure.kind == "lattice"
        assert config.population.size == 400

    def test_the_preview_keeps_mode_seed_population_and_structure(self) -> None:
        """Exactly the founding inputs survive; the rest are defaults."""
        values = helpers.default_widget_values()
        values["run.mode"] = "evolution"
        values["run.seed"] = 99
        values["structure.kind"] = "lattice"
        values["structure.initial_layout"] = "stripes"
        values["population.size"] = 9
        values["dynamics.selection_beta"] = 7.5  # must NOT reach the preview
        config = helpers.grid_preview_config(values, {"always_defect": 9})
        assert config.seed == 99
        assert config.structure.initial_layout == "stripes"
        assert config.dynamics.selection_beta != 7.5  # defaulted, not copied

    def test_genuinely_grid_relevant_problems_still_raise(self) -> None:
        """The preview is lenient about OTHER sections, not about its own."""
        values = helpers.default_widget_values()
        values["run.mode"] = "evolution"
        values["structure.kind"] = "lattice"
        values["population.size"] = 10
        with pytest.raises(ValidationError):
            helpers.grid_preview_config(values, {"always_defect": 7})  # mix != N


class TestLayoutPopulationMismatch:
    """The file-vs-widgets population comparison behind the populate offer (#124)."""

    TEXT = (
        "kind: lattice_grid\nrows: 2\ncols: 3\n\n"
        "always_defect always_defect .\n"
        "tit_for_tat . tit_for_tat\n"
    )

    def _write(self, tmp_path: Path, text: str | None = None) -> str:
        """Write a scratch layout file and return its path string.

        Args:
            tmp_path: pytest's per-test directory.
            text: File contents; the class fixture by default.

        Returns:
            The absolute path as a string (contains separators, so the #122
            rule uses it as given).
        """
        path = tmp_path / "scratch_layout.txt"
        path.write_text(text or self.TEXT, encoding="utf-8")
        return str(path)

    def test_agreement_returns_none(self, tmp_path: Path) -> None:
        """Matching size and mix → nothing to offer."""
        layout_file = self._write(tmp_path)
        result = helpers.layout_population_mismatch(
            layout_file, 4, {"always_defect": 2, "tit_for_tat": 2, "pavlov": 0}
        )
        assert result is None

    def test_a_size_difference_reports_the_files_population(self, tmp_path: Path) -> None:
        """The returned pair is exactly what the widgets would need to hold."""
        layout_file = self._write(tmp_path)
        result = helpers.layout_population_mismatch(layout_file, 20, {"always_defect": 20})
        assert result == (4, {"always_defect": 2, "tit_for_tat": 2})

    def test_a_mix_only_difference_still_reports(self, tmp_path: Path) -> None:
        """Same total, different mixture: the recorded config should not lie."""
        layout_file = self._write(tmp_path)
        result = helpers.layout_population_mismatch(layout_file, 4, {"always_defect": 4})
        assert result == (4, {"always_defect": 2, "tit_for_tat": 2})

    def test_an_unregistered_token_raises_with_its_position(self, tmp_path: Path) -> None:
        """The token check runs here too.

        The offer must never propose writing an unknown strategy into
        the widgets.
        """
        layout_file = self._write(tmp_path, self.TEXT.replace("tit_for_tat", "tit_for_tta"))
        with pytest.raises(ValueError, match=r"'tit_for_tta' \(line 6, cell 1\)"):
            helpers.layout_population_mismatch(layout_file, 4, {})

    def test_a_nearly_empty_file_is_refused(self, tmp_path: Path) -> None:
        """Below the smallest legal population no widget state could match."""
        text = "kind: lattice_grid\nrows: 1\ncols: 3\n\nalways_defect . .\n"
        with pytest.raises(ValueError, match="at least 2"):
            helpers.layout_population_mismatch(self._write(tmp_path, text), 1, {})

    def test_a_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        """The app shows this as the grid warning, same as founding would."""
        with pytest.raises(FileNotFoundError):
            helpers.layout_population_mismatch(str(tmp_path / "absent.txt"), 4, {})


class TestLayoutFileDimensionMismatch:
    """The panel-side dimension check behind the pre-Run warning (#126)."""

    def _values(self, tmp_path: Path, **overrides: object) -> dict[str, object]:
        """Widget values naming a 2x3 scratch layout file.

        Args:
            tmp_path: pytest's per-test directory.
            **overrides: Extra widget values merged in.

        Returns:
            A values mapping for the helper.
        """
        path = tmp_path / "scratch.txt"
        path.write_text(
            "kind: lattice_grid\nrows: 2\ncols: 3\n\n"
            "always_defect always_defect always_defect\n"
            "tit_for_tat tit_for_tat tit_for_tat\n",
            encoding="utf-8",
        )
        values: dict[str, object] = {
            "structure.layout_file": str(path),
            "structure.rows": 2,
            "structure.cols": 3,
            "population.size": 6,
        }
        values.update(overrides)
        return values

    def test_agreement_returns_none(self, tmp_path: Path) -> None:
        """Matching dimensions: nothing to warn about."""
        assert helpers.layout_file_dimension_mismatch(self._values(tmp_path)) is None

    def test_a_mismatch_names_both_sizes_and_the_fixes(self, tmp_path: Path) -> None:
        """The message mirrors the #126 validator's dimension check."""
        message = helpers.layout_file_dimension_mismatch(
            self._values(tmp_path, **{"structure.rows": 12, "structure.cols": 12})
        )
        assert message is not None
        assert "2x3" in message and "12x12" in message
        assert "Set Lattice rows to 2" in message

    def test_blank_dimensions_resolve_the_way_the_run_would(self, tmp_path: Path) -> None:
        """Auto rows/cols compare via the same resolver the engine uses.

        N=6 auto-resolves to the most-square 2x3 — matching the file, so no
        warning; at N=6 with a 3x2 file the auto pair (2x3) would mismatch.
        """
        values = self._values(tmp_path, **{"structure.rows": None, "structure.cols": None})
        assert helpers.layout_file_dimension_mismatch(values) is None

    def test_an_unreadable_file_is_someone_elses_warning(self, tmp_path: Path) -> None:
        """File problems are reported by the panel's existing warning path."""
        values = self._values(tmp_path)
        values["structure.layout_file"] = str(tmp_path / "gone.txt")
        assert helpers.layout_file_dimension_mismatch(values) is None
