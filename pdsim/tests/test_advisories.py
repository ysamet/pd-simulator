"""Tests for the M11b advisory batch A1–A3 (``pdsim/ui/advisories.py``).

Streamlit-free by construction (the #38/#48 helper discipline): every rule
is a pure function of (current widget values, loaded widget values), so the
tests drive the predicate table directly — each rule on both sides of its
boundary, the shared R4 gate across all four clock/mode combinations plus
tournament, A2's baseline-clearing contract, and A3's three message
variants (DECISIONS #176).
"""

from __future__ import annotations

from pdsim.config.registry import ParamValue
from pdsim.config.scenarios import get_scenario_info
from pdsim.ui import helpers
from pdsim.ui.advisories import (
    A2_MESSAGE,
    A2_TRIGGER_KEYS,
    ECONOMY_PANEL_SURFACE,
    advisories_for_surface,
    evaluate_advisories,
)
from pdsim.ui.economy_helpers import economy_active


def _flagship_values(**overrides: ParamValue) -> dict[str, ParamValue]:
    """The flagship's widget values — a synchronous spatial economy baseline.

    spatial_reciprocity: evolution, lattice, spatial interaction on, k = 5
    (clamps to degree 4), L = 12 inside the window 0 < L < 24 — every
    advisory's home ground.

    Args:
        **overrides: Widget values to replace, keyed by registry key.

    Returns:
        The full widget-value mapping.
    """
    values = helpers.widget_values_from_config(get_scenario_info("spatial_reciprocity").config)
    values.update(overrides)
    return values


def _keys_fired(
    values: dict[str, ParamValue], loaded: dict[str, ParamValue]
) -> list[tuple[str, str]]:
    """The (key, surface) pairs of every fired advisory.

    Args:
        values: Current widget values.
        loaded: The loaded baseline.

    Returns:
        (advisory key, surface) per firing, in table order.
    """
    return [(a.key, a.surface) for a in evaluate_advisories(values, loaded)]


class TestEconomyActiveGate:
    """#176 R4: one shared gate, all four clock/mode combinations + tournament."""

    def test_synchronous_energy_economy_is_active(self) -> None:
        """The classic gate: evolution + sync + energy_economy."""
        assert economy_active(_flagship_values()) is True

    def test_synchronous_imitation_is_inactive(self) -> None:
        """Under imitation nobody pays the living cost into starvation."""
        values = _flagship_values(**{"dynamics.reproduction_mode": "imitation"})
        assert economy_active(values) is False

    def test_asynchronous_variable_n_is_active(self) -> None:
        """variable_n IS the economy in event time — the stranded widget is inert."""
        values = _flagship_values(
            **{
                "dynamics.time_model": "asynchronous",
                "dynamics.async_population": "variable_n",
                # The stranded reproduction_mode value must NOT matter (#154).
                "dynamics.reproduction_mode": "imitation",
            }
        )
        assert economy_active(values) is True

    def test_asynchronous_fixed_n_is_inactive(self) -> None:
        """fixed_n never charges the living cost — no insolvency deaths exist."""
        values = _flagship_values(
            **{
                "dynamics.time_model": "asynchronous",
                "dynamics.async_population": "fixed_n",
                "dynamics.reproduction_mode": "energy_economy",  # stranded, inert
            }
        )
        assert economy_active(values) is False

    def test_tournament_is_inactive(self) -> None:
        """Tournament ignores the economy wholesale (#34/#120(a))."""
        assert economy_active(_flagship_values(**{"run.mode": "tournament"})) is False


class TestA1LivingCostWindow:
    """A1 (#176 R1): inclusive bounds, both sides of each boundary."""

    def _a1_fires(self, **overrides: ParamValue) -> bool:
        values = _flagship_values(**overrides)
        return any(key == "A1" for key, _ in _keys_fired(values, values))

    def test_fires_at_the_all_defector_income(self) -> None:
        """L = all-D income = 0: inclusive — a defector nets zero, never starves."""
        assert self._a1_fires(**{"dynamics.basic_living_cost": 0.0}) is True

    def test_silent_just_above_the_all_defector_income(self) -> None:
        """L = 0.01 > all-D = 0: the filter bites, no warning."""
        assert self._a1_fires(**{"dynamics.basic_living_cost": 0.01}) is False

    def test_fires_at_the_all_cooperator_income(self) -> None:
        """L = all-C income = 24: inclusive — even pure cooperators net zero."""
        assert self._a1_fires(**{"dynamics.basic_living_cost": 24.0}) is True

    def test_silent_just_below_the_all_cooperator_income(self) -> None:
        """L = 23.9 < all-C = 24: inside the window, no warning."""
        assert self._a1_fires(**{"dynamics.basic_living_cost": 23.9}) is False

    def test_surface_and_severity(self) -> None:
        """A1 renders in the Economy panel as a caution."""
        values = _flagship_values(**{"dynamics.basic_living_cost": 0.0})
        fired = advisories_for_surface(ECONOMY_PANEL_SURFACE, values, values)
        assert [a.key for a in fired] == ["A1"]
        assert fired[0].severity == "caution"
        assert "defectors never starve" in fired[0].message

    def test_gate_silences_a1_under_async_fixed_n(self) -> None:
        """R4: fixed_n has no metabolic filter for A1 to describe."""
        assert (
            self._a1_fires(
                **{
                    "dynamics.basic_living_cost": 0.0,
                    "dynamics.time_model": "asynchronous",
                    "dynamics.async_population": "fixed_n",
                }
            )
            is False
        )

    def test_a1_works_under_the_asynchronous_variable_n_clock(self) -> None:
        """#169's point: the warning system must not be dark under async."""
        assert (
            self._a1_fires(
                **{
                    "dynamics.basic_living_cost": 0.0,
                    "dynamics.time_model": "asynchronous",
                    "dynamics.async_population": "variable_n",
                }
            )
            is True
        )

    def test_silent_while_the_panel_does_not_assemble(self) -> None:
        """An invalid configuration silences A1 — as the readout itself waits.

        K below N fails the energy economy's capacity validation, so no
        report exists to warn from.
        """
        assert (
            self._a1_fires(
                **{
                    "dynamics.basic_living_cost": 0.0,
                    "dynamics.carrying_capacity": 10,
                }
            )
            is False
        )


class TestA2ChangedSinceLoad:
    """A2 (#176 R5): a change detector against the LOADED baseline."""

    def test_every_trigger_key_fires_when_changed(self) -> None:
        """Each of the nine #170 trigger keys fires inline at its own widget."""
        loaded = _flagship_values()
        changed: dict[str, ParamValue] = {
            "matching.matcher": "random_k",
            "matching.opponents_per_agent": 6,
            "match.rounds_per_match": 2,
            "match.continuation_probability": 0.5,
            "structure.neighbourhood_shape": "moore",
            "structure.kind": "well_mixed",
            "matching.spatial_interaction": False,
            "matching.encounter_mode": "per_pair",
            "structure.interaction_radius": 2,
        }
        assert set(changed) == set(A2_TRIGGER_KEYS)
        for key, new_value in changed.items():
            values = _flagship_values(**{key: new_value})
            fired = advisories_for_surface(key, values, loaded)
            assert [a.key for a in fired if a.key == "A2"] == ["A2"], key
            a2 = next(a for a in fired if a.key == "A2")
            assert a2.severity == "caution"
            assert a2.message == A2_MESSAGE

    def test_silent_while_values_match_the_baseline(self) -> None:
        """No change, no warning — the loaded configuration is the calibration."""
        values = _flagship_values()
        assert all(key != "A2" for key, _ in _keys_fired(values, values))

    def test_loading_clears_the_advisory(self) -> None:
        """R5: loading writes a fresh baseline, so the detector resets.

        Simulated exactly as the app does it: the baseline becomes the
        loaded values, so a mapping equal to the new baseline is silent
        even though it differs from the OLD one.
        """
        old_loaded = _flagship_values()
        current = _flagship_values(**{"matching.opponents_per_agent": 7})
        assert any(key == "A2" for key, _ in _keys_fired(current, old_loaded))
        new_loaded = dict(current)  # what _load_state writes on the next load
        assert all(key != "A2" for key, _ in _keys_fired(current, new_loaded))

    def test_gate_silences_a2_outside_the_economy(self) -> None:
        """R4: the same change under imitation multiplies nobody's survival."""
        loaded = _flagship_values()
        values = _flagship_values(
            **{
                "matching.opponents_per_agent": 6,
                "dynamics.reproduction_mode": "imitation",
            }
        )
        assert all(key != "A2" for key, _ in _keys_fired(values, loaded))

    def test_a_key_missing_from_the_baseline_stays_silent(self) -> None:
        """No baseline, nothing to differ from — never guess one."""
        values = _flagship_values(**{"matching.opponents_per_agent": 6})
        assert all(key != "A2" for key, _ in _keys_fired(values, {}))


class TestA3FullNeighbourhood:
    """A3 (#176 R6/R7): the engine's gate, the radius-aware degree, 3 messages."""

    def _a3_messages(self, values: dict[str, ParamValue]) -> list[str]:
        return [
            a.message
            for a in advisories_for_surface("matching.spatial_interaction", values, values)
            if a.key == "A3"
        ]

    def test_fires_at_k_at_or_above_the_degree(self) -> None:
        """Flagship: k = 5 ≥ degree 4 — the info note appears, per-initiator."""
        messages = self._a3_messages(_flagship_values())
        assert len(messages) == 1
        assert "twice the degree" in messages[0]
        assert "expected" not in messages[0]

    def test_silent_below_the_degree(self) -> None:
        """At k = 3 < 4, k does the limiting — no note."""
        values = _flagship_values(**{"matching.opponents_per_agent": 3})
        assert self._a3_messages(values) == []

    def test_the_degree_is_radius_aware(self) -> None:
        """R6: at radius 2 the von Neumann reach is 12, so k = 5 is silent."""
        values = _flagship_values(**{"structure.interaction_radius": 2})
        assert self._a3_messages(values) == []
        values = _flagship_values(
            **{"structure.interaction_radius": 2, "matching.opponents_per_agent": 12}
        )
        assert len(self._a3_messages(values)) == 1

    def test_per_pair_variant(self) -> None:
        """#175's ripple: under per_pair each pair meets once — degree, not 2×."""
        values = _flagship_values(**{"matching.encounter_mode": "per_pair"})
        messages = self._a3_messages(values)
        assert len(messages) == 1
        assert "meets once" in messages[0]
        assert "roughly equals the degree" in messages[0]

    def test_async_variant_is_per_initiator_phrased_as_expected(self) -> None:
        """R3: under the async clock always the per-initiator wording, expected.

        Even with a stranded per_pair widget value — the async loop never
        deduplicates, so the pair wording would be false there.
        """
        for stranded_mode in ("per_initiator", "per_pair"):
            values = _flagship_values(
                **{
                    "dynamics.time_model": "asynchronous",
                    "dynamics.async_population": "variable_n",
                    "matching.encounter_mode": stranded_mode,
                }
            )
            messages = self._a3_messages(values)
            assert len(messages) == 1, stranded_mode
            assert "expected" in messages[0]
            assert "twice the degree" in messages[0]
            assert "meets once" not in messages[0]

    def test_gate_is_the_engines_not_the_toggles(self) -> None:
        """R7: a stranded-on toggle under well_mixed or tournament is silent."""
        stranded = _flagship_values(**{"structure.kind": "well_mixed"})
        assert self._a3_messages(stranded) == []
        tournament = _flagship_values(**{"run.mode": "tournament"})
        assert self._a3_messages(tournament) == []

    def test_severity_is_info(self) -> None:
        """A3 informs; it does not caution — nothing is miscalibrated."""
        values = _flagship_values()
        fired = advisories_for_surface("matching.spatial_interaction", values, values)
        a3 = next(a for a in fired if a.key == "A3")
        assert a3.severity == "info"
