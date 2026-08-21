"""Tests for M11b Phase C: ``matching.encounter_mode`` (#166/#174).

The groups, following the phase prompt's test plan (T-B through T-G; T-A is
the whole suite — every golden and counting pin passing untouched):

* **The halved-match pin (T-B)** — the #139 forced-draw regime (fully
  occupied von Neumann torus, k ≥ degree), measured at k = 4 and k = 6:
  under ``per_pair`` every adjacent pair meets EXACTLY once and every agent
  plays EXACTLY min(k, degree) = 4 matches — the counterpart of #139's
  permanent ×2 test, which pins the ``per_initiator`` default and must keep
  passing unchanged (it lives in ``test_spatial_interaction.py``).
* **The survivor pin (T-C)** — deduplication keeps the FIRST occurrence in
  pair-list order; focals walk in ascending id order (#57), so in the
  forced regime every surviving match's initiator is the LOWER id of its
  pair (#174(c)) — pinned at the kernel and at the engine.
* **The cross-mode partner-draw pin (T-D)** — the #172(e) idiom: same seed,
  same config, counting wrapper — the partner-draw call log under
  ``per_pair`` is call-for-call identical to ``per_initiator``. Scope per
  #174(f): the pin covers the PARTNER DRAWS; downstream stream divergence
  (fewer matches remove their in-match draws) is the knob working, not a
  violation, so nothing past the partner draws is asserted.
* **Greying (T-E)** — the ``STRUCTURE_GREYING`` row per #174(d): sync greys
  on the engine's ACTUAL spatial gate (evolution AND lattice AND toggle),
  never the toggle alone; async always greyed with the verbatim #166(c)
  note; tournament ignored wholesale.
* **The calibration display branch (T-F, #174(a))** — the expected-matches
  figure flips 2× ↔ 1× with the mode on a fixed geometry, and the Economy
  report's fine print states the multiplier it actually used.
* **Config and round trip (T-G)** — a config without the key loads at the
  default (hard rule 8); the widget round trip carries the key.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest

from pdsim.config.experiment import ExperimentConfig, load_config, save_config
from pdsim.config.registry import get_spec
from pdsim.config.scenarios import get_scenario_info
from pdsim.core.agent import Agent
from pdsim.core.dynamics import PopulationDynamics
from pdsim.core.match import MatchResult
from pdsim.core.matcher import SpatialKernel
from pdsim.core.occupancy import Occupancy
from pdsim.core.strategies import create_strategy
from pdsim.core.structure import LatticeStructure
from pdsim.tests.counting_rng import CountingGenerator
from pdsim.ui import economy_helpers, helpers
from pdsim.ui.economy_helpers import (
    SPATIAL_FINE_PRINT,
    calibration_report,
    spatial_income_arithmetic,
)

AC = "always_cooperate"
AD = "always_defect"

# The verbatim #166(c)/#174(d) async note (the "NOTE: " prefix is the
# greying table's house formatting; the ruling's sentence rides it whole).
ASYNC_NOTE_VERBATIM = (
    "Greyed under the asynchronous clock: each async event's focal draws "
    "one partner — per-initiator by construction — and deduplicating "
    "across events would require remembering encounters through time, "
    "distorting the activation clock."
)

# The sync scope note, derived from the registry description (#174(d)).
SYNC_NOTE_VERBATIM = (
    "Live only while spatial interaction is on; the well-mixed matchers "
    "are untouched by this setting."
)


# ---------------------------------------------------------------------------
# Hand-built worlds for kernel-level tests (the test_spatial_interaction
# pattern: each test module builds its own worlds)
# ---------------------------------------------------------------------------


def _full_vn_torus(rows: int = 3, cols: int = 3) -> tuple[Occupancy, list[Agent]]:
    """Build a fully occupied von Neumann torus — the #139 forced regime.

    Args:
        rows: Lattice rows.
        cols: Lattice columns.

    Returns:
        The occupancy and the agents in ascending id order (agent i on
        site i).
    """
    structure = LatticeStructure(rows, cols, "von_neumann", "torus")
    occupancy = Occupancy(structure)
    strategy = create_strategy(AC)
    agents = []
    for site_id in range(rows * cols):
        occupancy.occupy(site_id, site_id)
        agents.append(Agent(agent_id=site_id, strategy=strategy))
    return occupancy, agents


def _kernel(occupancy: Occupancy, k: int, encounter_mode: str) -> SpatialKernel:
    """Build a SpatialKernel over a hand-built world.

    Args:
        occupancy: The world's occupancy (its structure is read off it).
        k: Opponents per agent.
        encounter_mode: ``"per_initiator"`` or ``"per_pair"``.

    Returns:
        The kernel adapter, ready for ``pairings``.
    """
    return SpatialKernel(
        structure=occupancy.structure,
        occupancy=occupancy,
        radius=1,
        decay=0.0,
        k=k,
        encounter_mode=encounter_mode,
    )


def _spatial_imitation_config(**matching_overrides: object) -> ExperimentConfig:
    """A 3x3 torus von Neumann imitation run with spatial interaction on.

    The ``test_spatial_interaction`` fixture shape (the #139 regime), with
    matching overridable so one helper serves both encounter modes.

    Args:
        **matching_overrides: Extra ``matching`` fields (k, the mode).

    Returns:
        A validated config; k = 4 covers the whole von Neumann
        neighbourhood, the forced-draw convention.
    """
    matching: dict[str, object] = {"spatial_interaction": True, "opponents_per_agent": 4}
    matching.update(matching_overrides)
    return ExperimentConfig.model_validate(
        {
            "seed": 11,
            "population": {"size": 9, "composition": {AC: 5, AD: 4}},
            "matching": matching,
            "match": {"length_mode": "fixed", "rounds_per_match": 1},
            "structure": {
                "kind": "lattice",
                "rows": 3,
                "cols": 3,
                "initial_layout": "stripes",
                "neighbourhood_shape": "von_neumann",
            },
            "dynamics": {"generations": 1, "mutation_rate": 0.0},
        }
    )


def _play_one_generation(config: ExperimentConfig) -> list[MatchResult]:
    """Play one synchronous generation and collect every match result.

    Args:
        config: A synchronous imitation config.

    Returns:
        The finished matches, in play order.
    """
    dynamics = PopulationDynamics(config, np.random.default_rng(config.seed))
    matches: list[MatchResult] = []
    dynamics.step(on_match=matches.append)
    return matches


# ---------------------------------------------------------------------------
# T-B: the halved-match pin in the #139 forced regime
# ---------------------------------------------------------------------------


class TestHalvedMatchCounts:
    """Under ``per_pair`` the #139 ×2 dissolves into exactly ×1 (#174(b))."""

    @pytest.mark.parametrize("k", [4, 6])
    def test_every_adjacent_pair_meets_exactly_once(self, k: int) -> None:
        """The forced regime at k = 4 and k = 6 (mirroring #139).

        Every adjacent pair meets EXACTLY once and every agent plays
        EXACTLY min(k, degree) = 4 matches — half of #139's 8, which its
        permanent ``per_initiator`` test continues to pin unchanged.
        """
        config = _spatial_imitation_config(encounter_mode="per_pair", opponents_per_agent=k)
        matches = _play_one_generation(config)
        per_pair: dict[tuple[int, int], int] = {}
        per_agent: dict[int, int] = {}
        for result in matches:
            a, b = result.agent_ids
            key = (min(a, b), max(a, b))
            per_pair[key] = per_pair.get(key, 0) + 1
            for agent_id in (a, b):
                per_agent[agent_id] = per_agent.get(agent_id, 0) + 1
        assert set(per_pair.values()) == {1}, "every adjacent pair meets exactly once"
        assert set(per_agent.values()) == {4}, "each agent plays min(k, degree) = 4"
        assert len(matches) == 18  # the 3x3 von Neumann torus's 18 edges
        assert len(per_pair) == 18

    def test_the_default_still_doubles(self) -> None:
        """The ``per_initiator`` default keeps the #139 behaviour exactly."""
        matches = _play_one_generation(_spatial_imitation_config())
        assert len(matches) == 36  # 9 focals x 4 forced draws, nothing dropped


# ---------------------------------------------------------------------------
# T-C: the survivor pin (#174(c))
# ---------------------------------------------------------------------------


class TestFirstOccurrenceSurvives:
    """Dedup keeps the first occurrence in pair-list order, seat intact."""

    def test_kernel_survivors_all_have_the_lower_id_initiator(self) -> None:
        """Forced regime, kernel level: focal < partner in every survivor.

        Focals walk ascending (#57's order through the adapter), so the
        lower id of each adjacent pair initiates first and its occurrence
        is the one that survives — the higher id's later duplicate drops.
        """
        occupancy, agents = _full_vn_torus()
        pairs = list(
            _kernel(occupancy, k=4, encounter_mode="per_pair").pairings(
                agents, np.random.default_rng(0)
            )
        )
        assert len(pairs) == 18
        assert all(focal.agent_id < partner.agent_id for focal, partner in pairs)

    def test_engine_survivors_keep_the_lower_id_initiator_seat(self) -> None:
        """Forced regime, engine level: the played matches carry the seat.

        ``MatchResult.agent_ids`` preserves (initiator, partner) play
        order, so the pin reads straight off the transcripts.
        """
        matches = _play_one_generation(_spatial_imitation_config(encounter_mode="per_pair"))
        assert len(matches) == 18
        assert all(result.agent_ids[0] < result.agent_ids[1] for result in matches)


# ---------------------------------------------------------------------------
# T-D: the cross-mode partner-draw pin (#166(b)/#174(f))
# ---------------------------------------------------------------------------


class TestPartnerDrawsIdenticalAcrossModes:
    """The knob changes WHICH matches run, never how randomness is consumed."""

    @pytest.mark.parametrize("k", [2, 4])
    def test_kernel_call_logs_are_identical_call_for_call(self, k: int) -> None:
        """Same seed, same world: the two modes' pairing draws are one stream.

        At k = 4 the draws are forced (every duplicate collapses); at
        k = 2 duplication is stochastic (only pairs that happened to draw
        each other collapse) — in BOTH cases the recorded call log is
        identical, because deduplication happens after all draws and
        consumes nothing.
        """
        logs = []
        for mode in ("per_initiator", "per_pair"):
            occupancy, agents = _full_vn_torus()
            counted = CountingGenerator(np.random.default_rng(23))
            list(_kernel(occupancy, k=k, encounter_mode=mode).pairings(agents, counted))  # type: ignore[arg-type]
            logs.append(counted.calls)
        assert logs[0] == logs[1]
        assert len(logs[0]) == 9  # one kernel draw per focal, both modes

    def test_engine_partner_draw_prefix_is_identical(self) -> None:
        """The generation's partner draws lead the stream, identically.

        The stripes founding is deterministic (no founding draw), so the
        match phase's 9 kernel draws are the generation's FIRST 9 calls in
        both modes — compared call-for-call. Scope per #174(f): nothing
        past the partner draws is asserted; downstream divergence is the
        knob working.
        """
        prefixes = []
        for mode in ("per_initiator", "per_pair"):
            config = _spatial_imitation_config(encounter_mode=mode)
            counted = CountingGenerator(np.random.default_rng(config.seed))
            PopulationDynamics(config, counted).step()  # type: ignore[arg-type]
            prefixes.append(counted.calls[:9])
        assert prefixes[0] == prefixes[1]
        assert all(name == "choice" for name, _, _ in prefixes[0])


# ---------------------------------------------------------------------------
# T-E: greying (#174(d))
# ---------------------------------------------------------------------------


class TestEncounterModeGreying:
    """The table row: sync on the engine's actual gate; async always greyed."""

    KEY = "matching.encounter_mode"
    SYNC: ClassVar[dict[str, object]] = {
        "run.mode": "evolution",
        "dynamics.time_model": "synchronous",
    }
    ASYNC: ClassVar[dict[str, object]] = {
        "run.mode": "evolution",
        "dynamics.time_model": "asynchronous",
    }

    def test_live_on_the_sync_spatial_gate(self) -> None:
        """Evolution AND lattice AND toggle: the widget is live."""
        values = {
            **self.SYNC,
            "structure.kind": "lattice",
            "matching.spatial_interaction": True,
        }
        assert helpers.greying(self.KEY, values) == (False, "")

    def test_live_under_both_reproduction_modes(self) -> None:
        """The gate is the ENGINE's (#137(b)): both sync loops substitute.

        Imitation and the energy economy both build the SpatialKernel, so
        the reproduction mode is deliberately NOT a conjunct.
        """
        for mode in ("imitation", "energy_economy"):
            values = {
                **self.SYNC,
                "structure.kind": "lattice",
                "matching.spatial_interaction": True,
                "dynamics.reproduction_mode": mode,
            }
            assert helpers.greying(self.KEY, values) == (False, ""), mode

    def test_toggle_off_greys_with_the_scope_note(self) -> None:
        """A lattice alone is not the gate — the toggle must be on."""
        values = {
            **self.SYNC,
            "structure.kind": "lattice",
            "matching.spatial_interaction": False,
        }
        disabled, note = helpers.greying(self.KEY, values)
        assert disabled
        assert SYNC_NOTE_VERBATIM in note

    def test_well_mixed_greys_with_the_scope_note_even_with_the_toggle_stranded_on(
        self,
    ) -> None:
        """The #141(c) precision: never the toggle alone.

        A greyed checkbox keeps its value, so the toggle can be stranded on
        under well_mixed — where the configured matcher IS consulted and
        the knob is inert.
        """
        values = {
            **self.SYNC,
            "structure.kind": "well_mixed",
            "matching.spatial_interaction": True,
        }
        disabled, note = helpers.greying(self.KEY, values)
        assert disabled
        assert SYNC_NOTE_VERBATIM in note

    def test_async_always_greyed_with_the_verbatim_note(self) -> None:
        """Per-initiator by construction — even with the full gate held."""
        for extra in (
            {},
            {"structure.kind": "lattice", "matching.spatial_interaction": True},
        ):
            disabled, note = helpers.greying(self.KEY, {**self.ASYNC, **extra})
            assert disabled, extra
            assert ASYNC_NOTE_VERBATIM in note, extra

    def test_tournament_ignores_the_widget_wholesale(self) -> None:
        """IGNORED_IN_TOURNAMENT, matching movement's #172(b) treatment."""
        values = {
            "run.mode": "tournament",
            "structure.kind": "lattice",
            "matching.spatial_interaction": True,
        }
        disabled, note = helpers.greying(self.KEY, values)
        assert disabled
        assert "tournament mode" in note

    def test_both_table_columns_answer_on_a_bare_mapping(self) -> None:
        """The two-branch obligation (#141): each cell evaluates anywhere."""
        rule = helpers.STRUCTURE_GREYING[self.KEY]
        for answer in (rule.sync({}), rule.asynchronous({})):
            assert answer is None or isinstance(answer, str)
        assert rule.asynchronous({}) is not None  # async never live


# ---------------------------------------------------------------------------
# T-F: the calibration display branch (#174(a))
# ---------------------------------------------------------------------------


def _flagship_with_mode(encounter_mode: str) -> ExperimentConfig:
    """The flagship scenario's config with the encounter mode swapped in.

    Args:
        encounter_mode: The ``matching.encounter_mode`` value to set.

    Returns:
        The modified config (``model_copy`` — no re-validation needed; the
        knob has no cross-field validator).
    """
    flagship = get_scenario_info("spatial_reciprocity").config
    return flagship.model_copy(
        update={"matching": flagship.matching.model_copy(update={"encounter_mode": encounter_mode})}
    )


class TestCalibrationDisplayBranch:
    """The expected-matches figure flips 2× ↔ 1× with the mode (#174(a))."""

    def test_pure_function_flips_on_a_fixed_geometry(self) -> None:
        """Moore torus at k = 8: 16 matches per_initiator, 8 per_pair."""
        kwargs: dict[str, object] = {
            "neighbourhood_shape": "moore",
            "boundary": "torus",
            "opponents_per_agent": 8,
            "length_mode": "fixed",
            "rounds_per_match": 1,
            "continuation_probability": 0.95,
            "payoff_reward": 3.0,
            "payoff_punishment": 1.0,
        }
        doubled = spatial_income_arithmetic(**kwargs)  # type: ignore[arg-type]
        halved = spatial_income_arithmetic(**kwargs, encounter_mode="per_pair")  # type: ignore[arg-type]
        assert doubled.matches_per_agent == 16.0
        assert halved.matches_per_agent == 8.0
        assert halved.all_c_income == doubled.all_c_income / 2
        assert halved.all_d_income == doubled.all_d_income / 2

    def test_flagship_report_shows_four_under_per_pair(self) -> None:
        """The V3 figure: 4 expected matches (was 8), incomes halved."""
        report = calibration_report(_flagship_with_mode("per_pair"))
        assert report.spatial is True
        assert report.expected_matches == 4.0
        assert report.all_c_income == 12.0  # was 24
        assert SPATIAL_FINE_PRINT in report.regime_note
        assert "1 × the effective neighbour count" in report.regime_note
        assert "per_pair" in report.regime_note

    def test_flagship_default_report_is_unchanged(self) -> None:
        """The per-initiator caption is the pre-Phase-C text, verbatim."""
        report = calibration_report(get_scenario_info("spatial_reciprocity").config)
        assert report.expected_matches == 8.0
        assert "2 × the effective neighbour count" in report.regime_note
        assert "per_pair" not in report.regime_note

    def test_memory_note_follows_the_mode(self) -> None:
        """The fixed-neighbour note halves its worst case under per_pair.

        Under the default an adjacent pair meets twice per generation
        (#139) and the flagship's worst case reads ≈ 200 recorded moves;
        under per_pair it meets once and the worst case halves to ≈ 100 —
        the #174(a) never-false rule applied to the E4b note.
        """
        default = calibration_report(get_scenario_info("spatial_reciprocity").config)
        assert default.memory_note is not None
        assert "meets twice" in default.memory_note
        assert "200" in default.memory_note
        halved = calibration_report(_flagship_with_mode("per_pair"))
        assert halved.memory_note is not None
        assert "meets once" in halved.memory_note
        assert "100" in halved.memory_note

    def test_help_text_covers_both_modes(self) -> None:
        """The (?) beside the number cannot contradict it (#154's rule)."""
        text = economy_helpers.ECONOMY_HELP["expected_matches"]
        assert "2 × the effective neighbour count" in text
        assert "per_pair" in text
        assert "1 × the effective neighbour count" in text


# ---------------------------------------------------------------------------
# T-G: config, registry, and round trip
# ---------------------------------------------------------------------------


class TestEncounterModeConfig:
    """The registry entry, hard rule 8, and the widget round trip."""

    def test_the_registry_entry(self) -> None:
        """Choice, values per_initiator | per_pair, default per_initiator."""
        spec = get_spec("matching.encounter_mode")
        assert spec.kind == "choice"
        assert spec.choices == ("per_initiator", "per_pair")
        assert spec.default == "per_initiator"
        assert spec.section == "Matching"
        # The description is the single source the greying notes derive
        # from — its scope sentence must actually be there.
        assert "collapses duplicate pairs after the draws" in spec.description
        assert "Live only while spatial interaction is on" in spec.description

    def test_the_widget_renders_last_in_the_matching_section(self) -> None:
        """Registration (= panel) order: after the spatial-interaction widgets."""
        from pdsim.config.registry import all_specs

        keys = [spec.key for spec in all_specs() if spec.section == "Matching"]
        assert keys == [
            "matching.spatial_interaction",
            "matching.matcher",
            "matching.opponents_per_agent",
            "matching.encounter_mode",
        ]

    def test_a_config_without_the_key_loads_at_the_default(self) -> None:
        """Hard rule 8: pre-M11b payloads know nothing of the knob."""
        config = ExperimentConfig.model_validate(
            {"population": {"size": 4, "composition": {AC: 2, AD: 2}}}
        )
        assert config.matching.encounter_mode == "per_initiator"

    def test_an_old_yaml_without_the_key_loads(self, tmp_path: Path) -> None:
        """A saved config with the line stripped reloads identically.

        The ``test_movement`` idiom: strip the key's line from the saved
        YAML and confirm the reload equals the original config.
        """
        config = _spatial_imitation_config()
        path = save_config(config, tmp_path / "new.yaml")
        text = path.read_text(encoding="utf-8")
        assert "encounter_mode:" in text
        stripped = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("encounter_mode:")
        )
        (tmp_path / "old.yaml").write_text(stripped, encoding="utf-8")
        reloaded = load_config(tmp_path / "old.yaml")
        assert reloaded.matching.encounter_mode == "per_initiator"
        assert reloaded == config

    def test_widget_values_round_trip_the_key(self) -> None:
        """Config → widget values → config keeps the mode."""
        original = _spatial_imitation_config(encounter_mode="per_pair")
        values = helpers.widget_values_from_config(original)
        assert values["matching.encounter_mode"] == "per_pair"
        rebuilt = helpers.build_config(
            values, original.population.composition, original.strategy_params
        )
        assert rebuilt.matching.encounter_mode == "per_pair"
        assert rebuilt == original

    def test_an_unknown_mode_is_rejected_from_the_registry(self) -> None:
        """The choice list is enforced from the registry alone (rule 3)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _spatial_imitation_config(encounter_mode="per_neighbourhood")
