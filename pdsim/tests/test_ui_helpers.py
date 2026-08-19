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
from pdsim.core.events import AgentSnapshot, GenerationFinished
from pdsim.core.timeseries import RunTimeseries
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


class TestFinalOccupancy:
    """The results browser's presence test for its Founding | Final selector.

    M11a Phase E2 (#136's deferred half, DECISIONS #146): presence-driven,
    never mode-driven — the answer comes from the recorded snapshots alone.
    """

    @staticmethod
    def _series(periods: list[tuple[AgentSnapshot, ...]]) -> RunTimeseries:
        """Assemble a timeseries carrying the given per-period snapshots.

        Args:
            periods: One snapshot tuple per generation.

        Returns:
            An evolution-mode series with matching minimal aggregates.
        """
        timeseries = RunTimeseries(mode="evolution")
        for index, agents in enumerate(periods):
            counts: dict[str, int] = {}
            for snapshot in agents:
                counts[snapshot.strategy] = counts.get(snapshot.strategy, 0) + 1
            timeseries.add(
                GenerationFinished(
                    index=index,
                    composition=counts,
                    mean_scores={name: 1.0 for name in counts},
                    rounds_played={name: 1 for name in counts},
                    agents=agents,
                )
            )
        return timeseries

    def test_snapshots_with_site_ids_yield_the_last_periods_map(self) -> None:
        """Present → the LAST period's site → strategy pairs, exactly."""
        early = (
            AgentSnapshot(0, None, 1, 10.0, "always_defect", site_id=0),
            AgentSnapshot(1, None, 1, 10.0, "tit_for_tat", site_id=1),
        )
        late = (
            AgentSnapshot(0, None, 2, 20.0, "always_defect", site_id=0),
            AgentSnapshot(2, 0, 0, 5.0, "always_defect", site_id=3),
        )
        placements = helpers.final_occupancy(self._series([early, late]))
        assert placements == {0: "always_defect", 3: "always_defect"}

    def test_no_snapshots_at_all_yields_none(self) -> None:
        """Imitation-shaped data (#116: nothing persisted) → founding only."""
        timeseries = RunTimeseries(mode="evolution")
        assert helpers.final_occupancy(timeseries) is None

    def test_snapshots_without_site_ids_yield_none(self) -> None:
        """A schema ≤ 4 economy recording (site_id absent) behaves as today."""
        agents = (
            AgentSnapshot(0, None, 1, 10.0, "always_defect"),
            AgentSnapshot(1, None, 1, 10.0, "tit_for_tat"),
        )
        assert helpers.final_occupancy(self._series([agents])) is None

    def test_an_extinct_final_period_yields_an_empty_map_not_none(self) -> None:
        """Earlier periods carried sites; the run ended with nobody alive.

        The empty mapping (not None) keeps the selector available: an empty
        world IS the run's final occupancy, and hiding it would misreport
        what happened.
        """
        alive = (AgentSnapshot(0, None, 1, 10.0, "always_defect", site_id=4),)
        assert helpers.final_occupancy(self._series([alive, ()])) == {}


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

        N = 400 with K = 200: the FULL config fails validation under
        `energy_economy` (K >= N is checked exactly there), and that
        failure once took the preview down with it. The preview config must
        build anyway, because the grid never reads the dynamics section.
        (#121's session hit this with K's then-DEFAULT of 200; since Phase
        C a blank K auto-resolves to the site count, so the defect state
        now needs the same 200 set explicitly — the pin is unchanged in
        substance.)
        """
        values = helpers.default_widget_values()
        values["run.mode"] = "evolution"
        values["structure.kind"] = "lattice"
        values["population.size"] = 400
        values["dynamics.reproduction_mode"] = "energy_economy"
        values["dynamics.carrying_capacity"] = 200
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


class TestStructureGreyingTable:
    """M11a Phase E: the ONE predicate table, consumed by BOTH branches (#141).

    The spec's Design 11 map made executable: a completeness test for the
    two-branch obligation, then cell pins for every load-bearing rule.
    """

    SYNC: ClassVar[dict[str, object]] = {
        "run.mode": "evolution",
        "dynamics.time_model": "synchronous",
    }
    ASYNC: ClassVar[dict[str, object]] = {
        "run.mode": "evolution",
        "dynamics.time_model": "asynchronous",
    }

    def test_every_named_key_has_a_defined_answer_in_both_branches(self) -> None:
        """The two-branch obligation, executable (spec Design 11).

        Every ``structure.*`` registry key plus the four named
        matching/dynamics keys must carry an explicit answer in BOTH table
        columns — even where that answer is "greyed, because async never
        reads it" — and each answer must evaluate on a bare mapping.
        """
        from pdsim.config.registry import all_specs

        named = [
            *(spec.key for spec in all_specs() if spec.key.startswith("structure.")),
            # M11b Phase B (#172): the movement trio joins the table.
            *(spec.key for spec in all_specs() if spec.key.startswith("movement.")),
            "matching.spatial_interaction",
            "matching.matcher",
            "matching.opponents_per_agent",
            "dynamics.boundary_order",
        ]
        assert named  # the registry must actually contribute structure keys
        for key in named:
            assert key in helpers.STRUCTURE_GREYING, key
            rule = helpers.STRUCTURE_GREYING[key]
            for answer in (rule.sync({}), rule.asynchronous({})):
                assert answer is None or isinstance(answer, str), key

    def test_opponents_per_agent_answers_live_in_both_branches(self) -> None:
        """Item 9's assertion: k stays live always — the #81 clamp idiom."""
        rule = helpers.STRUCTURE_GREYING["matching.opponents_per_agent"]
        spatial = {"structure.kind": "lattice", "matching.spatial_interaction": True}
        for values in ({}, spatial):
            assert rule.sync(values) is None
            assert rule.asynchronous(values) is None

    def test_kind_is_the_gate_and_never_greys(self) -> None:
        """structure.kind stays live in both branches, both worlds."""
        for base in (self.SYNC, self.ASYNC):
            for kind in ("well_mixed", "lattice"):
                values = {**base, "structure.kind": kind}
                assert helpers.greying("structure.kind", values) == (False, ""), (base, kind)

    def test_well_mixed_greys_every_other_structure_widget_in_both_branches(self) -> None:
        """The map's base rule: no geometry, nothing for these to act on."""
        for base in (self.SYNC, self.ASYNC):
            values = {**base, "structure.kind": "well_mixed"}
            for key in (
                "structure.rows",
                "structure.cols",
                "structure.neighbourhood_shape",
                "structure.boundary",
                "structure.initial_layout",
                "structure.layout_file",
                "structure.birth_radius",
                "structure.birth_decay",
                "structure.placement_contest",
                "structure.interaction_radius",
                "structure.interaction_decay",
            ):
                disabled, note = helpers.greying(key, values)
                assert disabled, (base, key)
                assert note, (base, key)

    def test_layout_file_needs_lattice_and_from_file(self) -> None:
        """The `continuation_probability` idiom, in both branches."""
        for base in (self.SYNC, self.ASYNC):
            live = {
                **base,
                "structure.kind": "lattice",
                "structure.initial_layout": "from_file",
            }
            assert helpers.greying("structure.layout_file", live) == (False, "")
            other_layout = {**live, "structure.initial_layout": "random"}
            disabled, note = helpers.greying("structure.layout_file", other_layout)
            assert disabled
            assert "from_file" in note

    def test_birth_pair_stays_live_on_a_lattice_in_every_mode(self) -> None:
        """The spec's emphatic cell: the naive reading is BACKWARDS.

        Under async fixed_n the birth kernel defines the competition set
        for a freed site — the k that b/c > k counts (#132) — so the pair
        must NOT grey there; nor under sync imitation (the spec's map greys
        the pair only under well_mixed).
        """
        modes = [
            {**self.ASYNC, "dynamics.async_population": "fixed_n"},
            {**self.ASYNC, "dynamics.async_population": "variable_n"},
            {**self.SYNC, "dynamics.reproduction_mode": "energy_economy"},
            {**self.SYNC, "dynamics.reproduction_mode": "imitation"},
        ]
        for base in modes:
            values = {**base, "structure.kind": "lattice"}
            for key in ("structure.birth_radius", "structure.birth_decay"):
                assert helpers.greying(key, values) == (False, ""), (base, key)

    def test_placement_contest_three_way_conjunction(self) -> None:
        """All eight combinations of (synchronous, lattice, energy_economy).

        Exactly one cell is live — sync AND lattice AND economy (#107) —
        and each greyed cell's note names its actual cause.
        """
        for synchronous in (True, False):
            for lattice in (True, False):
                for economy in (True, False):
                    values = {
                        **(self.SYNC if synchronous else self.ASYNC),
                        "structure.kind": "lattice" if lattice else "well_mixed",
                        "dynamics.reproduction_mode": (
                            "energy_economy" if economy else "imitation"
                        ),
                    }
                    disabled, note = helpers.greying("structure.placement_contest", values)
                    cell = (synchronous, lattice, economy)
                    if synchronous and lattice and economy:
                        assert (disabled, note) == (False, ""), cell
                    else:
                        assert disabled, cell
                        if not lattice:
                            assert "cells to contest" in note or "well-mixed" in note, cell
                        elif not synchronous:
                            assert "asynchronous" in note or "fixed_n" in note.lower(), cell
                        else:
                            assert "imitation" in note, cell

    def test_placement_contest_async_notes_name_the_specific_cause(self) -> None:
        """fixed_n gets the freed-site note; variable_n the not-consulted note.

        The variable_n note was reworded clock-honest at M11b Phase B
        (#171(f2)/#172): several births CAN resolve in one async event, in
        ascending id order — the old "one birth at a time" clause was false.
        """
        fixed = {
            **self.ASYNC,
            "structure.kind": "lattice",
            "dynamics.async_population": "fixed_n",
        }
        _, note = helpers.greying("structure.placement_contest", fixed)
        assert "freed site" in note
        variable = {**fixed, "dynamics.async_population": "variable_n"}
        _, note = helpers.greying("structure.placement_contest", variable)
        assert "ascending agent-id order" in note
        assert "one birth at a time" not in note

    def test_interaction_radii_disjunction_names_the_holding_condition(self) -> None:
        """Three greyed causes, one live cell — in BOTH branches (#137(c))."""
        for base in (self.SYNC, self.ASYNC):
            for key in ("structure.interaction_radius", "structure.interaction_decay"):
                live = {
                    **base,
                    "structure.kind": "lattice",
                    "matching.spatial_interaction": True,
                }
                assert helpers.greying(key, live) == (False, ""), (base, key)
                toggle_off = {**live, "matching.spatial_interaction": False}
                disabled, note = helpers.greying(key, toggle_off)
                assert disabled and "Spatial interaction" in note, (base, key)
                for toggle in (True, False):
                    well_mixed = {
                        **base,
                        "structure.kind": "well_mixed",
                        "matching.spatial_interaction": toggle,
                    }
                    disabled, note = helpers.greying(key, well_mixed)
                    assert disabled and "lattice" in note, (base, key, toggle)

    def test_spatial_toggle_greys_under_well_mixed_in_both_branches(self) -> None:
        """The forward-pointing rule (#141): the toggle renders ABOVE kind."""
        for base in (self.SYNC, self.ASYNC):
            well_mixed = {**base, "structure.kind": "well_mixed"}
            disabled, note = helpers.greying("matching.spatial_interaction", well_mixed)
            assert disabled
            assert "lattice" in note
            lattice = {**base, "structure.kind": "lattice"}
            assert helpers.greying("matching.spatial_interaction", lattice) == (False, "")

    def test_matcher_greys_while_spatial_sampling_is_active_sync(self) -> None:
        """Discharges #137(a)'s interim state: toggle on → matcher unconsulted."""
        values = {
            **self.SYNC,
            "structure.kind": "lattice",
            "matching.spatial_interaction": True,
        }
        disabled, note = helpers.greying("matching.matcher", values)
        assert disabled
        assert "not consulted" in note
        off = {**values, "matching.spatial_interaction": False}
        assert helpers.greying("matching.matcher", off) == (False, "")

    def test_matcher_stays_live_under_tournament_whatever_the_toggle_says(self) -> None:
        """Tournament keeps build_matcher (#137(b)) — the mode guard is real."""
        values = {
            "run.mode": "tournament",
            "structure.kind": "lattice",
            "matching.spatial_interaction": True,
        }
        assert helpers.greying("matching.matcher", values) == (False, "")

    def test_async_matcher_note_knows_about_spatial_interaction(self) -> None:
        """The Phase D imprecision, corrected: partners are not always uniform."""
        values = {**self.ASYNC, "structure.kind": "lattice"}
        disabled, note = helpers.greying("matching.matcher", values)
        assert disabled
        assert "Spatial interaction" in note

    def test_k_stays_live_under_active_spatial_sampling(self) -> None:
        """A (greyed) round_robin matcher must not grey k while spatial is on."""
        values = {
            **self.SYNC,
            "structure.kind": "lattice",
            "matching.spatial_interaction": True,
            "matching.matcher": "round_robin",
        }
        assert helpers.greying("matching.opponents_per_agent", values) == (False, "")
        off = {**values, "matching.spatial_interaction": False}
        disabled, note = helpers.greying("matching.opponents_per_agent", off)
        assert disabled
        assert "round-robin" in note

    def test_boundary_order_is_live_under_every_synchronous_mode(self) -> None:
        """#131's cell: live under ALL sync runs (VT-4's slots rationing)."""
        for reproduction in ("imitation", "energy_economy"):
            for kind in ("well_mixed", "lattice"):
                values = {
                    **self.SYNC,
                    "dynamics.reproduction_mode": reproduction,
                    "structure.kind": kind,
                }
                assert helpers.greying("dynamics.boundary_order", values) == (False, ""), (
                    reproduction,
                    kind,
                )

    def test_boundary_order_greys_under_async_with_the_no_boundary_note(self) -> None:
        """The sharp two-branch case: its whole content is sync-vs-async."""
        for kind in ("well_mixed", "lattice"):
            values = {**self.ASYNC, "structure.kind": kind}
            disabled, note = helpers.greying("dynamics.boundary_order", values)
            assert disabled, kind
            assert "generation boundary" in note

    def test_composition_greys_under_from_file_on_both_clocks(self) -> None:
        """Spec Design 8 consequence 1 / #124's end-state: the file decides."""
        for base in (self.SYNC, self.ASYNC):
            values = {
                **base,
                "structure.kind": "lattice",
                "structure.initial_layout": "from_file",
            }
            disabled, note = helpers.greying("population.composition", values)
            assert disabled, base
            assert "Populate" in note

    def test_composition_stays_live_outside_the_from_file_cell(self) -> None:
        """Any other layout, a well-mixed world, or tournament: fully live."""
        for values in (
            {**self.SYNC, "structure.kind": "lattice", "structure.initial_layout": "random"},
            {**self.SYNC, "structure.kind": "well_mixed", "structure.initial_layout": "from_file"},
            {
                "run.mode": "tournament",
                "structure.kind": "lattice",
                "structure.initial_layout": "from_file",
            },
        ):
            assert helpers.greying("population.composition", values) == (False, ""), values

    def test_population_size_has_no_table_row_and_stays_live(self) -> None:
        """Spec Design 11: size stays live and validated, even under from_file."""
        assert "population.size" not in helpers.STRUCTURE_GREYING
        values = {
            **self.SYNC,
            "structure.kind": "lattice",
            "structure.initial_layout": "from_file",
        }
        assert helpers.greying("population.size", values) == (False, "")

    def test_capacity_and_size_rules_are_unamended(self) -> None:
        """Item 11: K and N keep their existing greying exactly."""
        economy = {
            **self.SYNC,
            "structure.kind": "lattice",
            "dynamics.reproduction_mode": "energy_economy",
        }
        assert helpers.greying("dynamics.carrying_capacity", economy) == (False, "")
        imitation = {**economy, "dynamics.reproduction_mode": "imitation"}
        disabled, note = helpers.greying("dynamics.carrying_capacity", imitation)
        assert disabled
        assert "IGNORED under imitation" in note

    def test_structure_greys_wholesale_under_tournament(self) -> None:
        """Item 13's fix: #120(a) made visible — the widgets say so too now."""
        values = {"run.mode": "tournament", "structure.kind": "lattice"}
        for key in (
            "structure.kind",
            "structure.rows",
            "structure.initial_layout",
            "structure.birth_radius",
            "structure.placement_contest",
            "structure.interaction_radius",
            "matching.spatial_interaction",
            "dynamics.boundary_order",
        ):
            disabled, note = helpers.greying(key, values)
            assert disabled, key
            assert "tournament mode" in note, key


class TestMovementGreying:
    """M11b Phase B (#165/#172): the movement trio greys where the gate cannot hold.

    Grey under well_mixed (both branches), under sync imitation, under async
    fixed_n, and in tournament mode; live under the sync lattice economy and
    under async variable_n on a lattice. The rate is a VALUE, not a liveness
    condition: at rate 0 the widgets stay live (that is how movement is
    switched on).
    """

    TRIO: ClassVar[tuple[str, ...]] = ("movement.rate", "movement.radius", "movement.decay")
    SYNC: ClassVar[dict[str, object]] = {
        "run.mode": "evolution",
        "dynamics.time_model": "synchronous",
    }
    ASYNC: ClassVar[dict[str, object]] = {
        "run.mode": "evolution",
        "dynamics.time_model": "asynchronous",
    }

    def test_well_mixed_greys_the_trio_in_both_branches(self) -> None:
        """No geometry, nowhere to move — the note says so."""
        for base in (self.SYNC, self.ASYNC):
            values = {**base, "structure.kind": "well_mixed"}
            for key in self.TRIO:
                disabled, note = helpers.greying(key, values)
                assert disabled, (base, key)
                assert "nowhere to move" in note

    def test_sync_imitation_greys_the_trio_with_the_no_boundary_note(self) -> None:
        """Imitation has no demographic boundary to host the movement step."""
        values = {
            **self.SYNC,
            "structure.kind": "lattice",
            "dynamics.reproduction_mode": "imitation",
        }
        for key in self.TRIO:
            disabled, note = helpers.greying(key, values)
            assert disabled, key
            assert "demographic boundary" in note

    def test_sync_lattice_economy_keeps_the_trio_live_even_at_rate_zero(self) -> None:
        """Live under the gate; rate 0 is a value (movement off), not a greying cause."""
        values = {
            **self.SYNC,
            "structure.kind": "lattice",
            "dynamics.reproduction_mode": "energy_economy",
            "movement.rate": 0.0,
        }
        for key in self.TRIO:
            assert helpers.greying(key, values) == (False, ""), key

    def test_async_fixed_n_greys_the_trio_with_the_full_grid_note(self) -> None:
        """fixed_n's grid is full by construction — every move would be blocked."""
        values = {
            **self.ASYNC,
            "structure.kind": "lattice",
            "dynamics.async_population": "fixed_n",
        }
        for key in self.TRIO:
            disabled, note = helpers.greying(key, values)
            assert disabled, key
            assert "completely full" in note

    def test_async_variable_n_on_a_lattice_keeps_the_trio_live(self) -> None:
        """The async half of the gate: variable_n + lattice."""
        values = {
            **self.ASYNC,
            "structure.kind": "lattice",
            "dynamics.async_population": "variable_n",
        }
        for key in self.TRIO:
            assert helpers.greying(key, values) == (False, ""), key

    def test_tournament_greys_the_trio_wholesale(self) -> None:
        """Nothing is born, dies, or moves in a tournament."""
        values = {"run.mode": "tournament", "structure.kind": "lattice"}
        for key in self.TRIO:
            disabled, note = helpers.greying(key, values)
            assert disabled, key
            assert "tournament" in note

    def test_movement_notes_never_say_infeasible(self) -> None:
        """The vocabulary rule holds in the greying notes too."""
        for base in (self.SYNC, self.ASYNC):
            for kind in ("well_mixed", "lattice"):
                for mode in ("imitation", "energy_economy"):
                    for population in ("variable_n", "fixed_n"):
                        values = {
                            **base,
                            "structure.kind": kind,
                            "dynamics.reproduction_mode": mode,
                            "dynamics.async_population": population,
                        }
                        for key in self.TRIO:
                            _, note = helpers.greying(key, values)
                            assert "infeasible" not in note.lower()
