"""Tests for the SweepSpec layer (``pdsim/sweep/spec.py``, DECISIONS #66/#67).

Covers: the largest-remainder composition resolution (worked examples incl.
the tie-break and the remainder=0 endpoint), SweepSpec validation rule by
rule, expansion determinism, and the guarantee that every expanded member is a
fully-valid config (the "generator, never a weakener" rule, #59).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pdsim.config.experiment import ExperimentConfig
from pdsim.sweep.spec import (
    SweepSpec,
    expand,
    load_sweep_spec,
    resolve_composition,
    save_sweep_spec,
    sweep_validation_messages,
)


class TestResolveComposition:
    """Three-bucket resolution + largest-remainder rounding (companion §2.2)."""

    def test_companion_worked_example(self) -> None:
        """The doc's example, including the .4/.4 tie broken by machine name."""
        result = resolve_composition(
            100,
            "tit_for_tat",
            2,
            {},
            {"always_defect": 30, "always_cooperate": 30, "generous_tit_for_tat": 40},
        )
        assert result == {
            "tit_for_tat": 2,
            "always_cooperate": 30,  # wins the leftover seat by name (< always_defect)
            "always_defect": 29,
            "generous_tit_for_tat": 39,
        }
        assert sum(result.values()) == 100

    def test_remainder_zero_drops_the_fill(self) -> None:
        """When the invader + fixed already fill N, the fill bucket vanishes."""
        result = resolve_composition(10, "tit_for_tat", 4, {"always_defect": 6}, {"random": 100})
        assert result == {"tit_for_tat": 4, "always_defect": 6}
        assert "random" not in result

    def test_non_even_remainder_sums_exactly(self) -> None:
        """An awkward split still totals N (leftover seats are handed out)."""
        result = resolve_composition(
            17, "tit_for_tat", 2, {}, {"always_defect": 33, "random": 33, "pavlov": 34}
        )
        assert sum(result.values()) == 17
        assert result["tit_for_tat"] == 2

    def test_single_full_fill_takes_the_whole_remainder(self) -> None:
        """A 100% fill gets every leftover seat."""
        result = resolve_composition(40, "tit_for_tat", 6, {}, {"always_defect": 100})
        assert result == {"tit_for_tat": 6, "always_defect": 34}

    def test_negative_remainder_raises(self) -> None:
        """Defensive: more agents than exist is a hard error (caught earlier)."""
        with pytest.raises(ValueError, match="but the population size is"):
            resolve_composition(10, "tit_for_tat", 8, {"always_defect": 5}, {"random": 100})


def _spec(**overrides: object) -> SweepSpec:
    """Build a valid baseline sweep spec, overriding selected fields.

    Args:
        **overrides: SweepSpec fields to replace.

    Returns:
        A structurally-valid SweepSpec (semantic validity depends on the
        overrides).
    """
    fields: dict = {
        "name": "test",
        "base_scenario": "reciprocity_takes_over",
        "composition": {
            "vary": "tit_for_tat",
            "counts": [2, 6],
            "fill": {"always_defect": 100},
        },
        "seeds": [1, 2],
        "metrics": [{"metric": "final_share", "strategy": "tit_for_tat"}],
    }
    fields.update(overrides)
    return SweepSpec.model_validate(fields)


class TestValidation:
    """sweep_validation_messages, rule by rule (DECISIONS #66)."""

    def test_valid_spec_has_no_messages(self) -> None:
        """A well-formed spec passes cleanly."""
        assert sweep_validation_messages(_spec()) == []

    def test_both_base_sources_rejected(self) -> None:
        """Exactly one of base / base_scenario must be given."""
        messages = sweep_validation_messages(_spec(base="x.yaml"))
        assert any("exactly one" in m for m in messages)

    def test_neither_base_source_rejected(self) -> None:
        """Zero base sources is also an error."""
        messages = sweep_validation_messages(_spec(base_scenario=None))
        assert any("exactly one" in m for m in messages)

    def test_unknown_strategy_in_composition(self) -> None:
        """Composition names are validated against the roster."""
        messages = sweep_validation_messages(
            _spec(composition={"vary": "telepathy", "counts": [1], "fill": {"always_defect": 100}})
        )
        assert any("unknown strategy" in m for m in messages)

    def test_vary_cannot_also_be_fill(self) -> None:
        """A strategy is in exactly one bucket."""
        messages = sweep_validation_messages(
            _spec(
                composition={
                    "vary": "tit_for_tat",
                    "counts": [2],
                    "fill": {"tit_for_tat": 100},
                }
            )
        )
        assert any("varying invader and cannot also" in m for m in messages)

    def test_fixed_and_fill_overlap_rejected(self) -> None:
        """A strategy cannot be both fixed and fill."""
        messages = sweep_validation_messages(
            _spec(
                composition={
                    "vary": "tit_for_tat",
                    "counts": [2],
                    "fixed": {"always_defect": 5},
                    "fill": {"always_defect": 100},
                }
            )
        )
        assert any("both 'fixed' and 'fill'" in m for m in messages)

    def test_fill_must_sum_to_100(self) -> None:
        """The headline validation step from the spec's Validation §5."""
        messages = sweep_validation_messages(
            _spec(
                composition={
                    "vary": "tit_for_tat",
                    "counts": [2],
                    "fill": {"always_defect": 90},
                }
            )
        )
        assert any("sum to 100" in m for m in messages)

    def test_invader_overflow_at_largest_count(self) -> None:
        """vary_max + sum fixed must fit the base population size."""
        messages = sweep_validation_messages(
            _spec(
                composition={
                    "vary": "tit_for_tat",
                    "counts": [2, 999],
                    "fill": {"always_defect": 100},
                }
            )
        )
        assert any("largest invader count" in m for m in messages)

    def test_empty_seats_without_fill_rejected(self) -> None:
        """Leftover seats with no fill bucket cannot be seated."""
        messages = sweep_validation_messages(
            _spec(composition={"vary": "tit_for_tat", "counts": [2]})  # no fill, no fixed
        )
        assert any("no 'fill' strategies" in m for m in messages)

    def test_unknown_parameter_key_rejected(self) -> None:
        """Parameter-axis keys must be registry keys."""
        messages = sweep_validation_messages(
            _spec(parameters=[{"key": "not.a.key", "values": [1]}])
        )
        assert any("not.a.key" in m for m in messages)

    def test_out_of_range_parameter_value_rejected(self) -> None:
        """Each parameter value validates against its registry spec."""
        messages = sweep_validation_messages(
            _spec(parameters=[{"key": "dynamics.mutation_rate", "values": [0.1, 1.5]}])
        )
        assert any("at most" in m for m in messages)

    def test_empty_seeds_and_metrics_rejected(self) -> None:
        """Both axes are required."""
        assert any("seeds" in m for m in sweep_validation_messages(_spec(seeds=[])))
        assert any("metric" in m for m in sweep_validation_messages(_spec(metrics=[])))

    def test_unknown_metric_rejected(self) -> None:
        """Metric names must be registered."""
        messages = sweep_validation_messages(_spec(metrics=[{"metric": "made_up"}]))
        assert any("made_up" in m for m in messages)

    def test_missing_required_metric_param_rejected(self) -> None:
        """final_share needs a strategy; omitting it is an error."""
        messages = sweep_validation_messages(_spec(metrics=[{"metric": "final_share"}]))
        assert any("requires parameter 'strategy'" in m for m in messages)

    def test_unknown_metric_param_rejected(self) -> None:
        """A metric rejects parameters it does not declare."""
        messages = sweep_validation_messages(
            _spec(metrics=[{"metric": "final_share", "strategy": "tit_for_tat", "bogus": 1}])
        )
        assert any("unknown parameter 'bogus'" in m for m in messages)


class TestExpansion:
    """Cross-product expansion determinism and full member validation."""

    def test_member_count_is_the_cross_product(self) -> None:
        """Counts x params x seeds, with seeds innermost."""
        spec = _spec(
            composition={
                "vary": "tit_for_tat",
                "counts": [2, 6, 10],
                "fill": {"always_defect": 100},
            },
            parameters=[{"key": "dynamics.selection_beta", "values": [0.1, 1.0]}],
            seeds=[1, 2, 3, 4],
        )
        plans = expand(spec)
        assert len(plans) == 3 * 2 * 4
        assert [p.run_index for p in plans] == list(range(24))

    def test_pinned_order_seeds_innermost(self) -> None:
        """The first members vary only by seed (composition/param outermost)."""
        spec = _spec(
            composition={"vary": "tit_for_tat", "counts": [2, 6], "fill": {"always_defect": 100}},
            seeds=[11, 22, 33],
        )
        plans = expand(spec)
        # First three members share the invader count (2) and differ by seed.
        assert [p.axis_values["seed"] for p in plans[:3]] == [11, 22, 33]
        assert all(p.axis_values["tit_for_tat"] == 2 for p in plans[:3])
        assert plans[3].axis_values["tit_for_tat"] == 6  # count advances next

    def test_every_member_is_a_valid_config(self) -> None:
        """Expansion produces fully-validated ExperimentConfigs (#59)."""
        plans = expand(_spec())
        assert all(isinstance(p.config, ExperimentConfig) for p in plans)
        # The resolved composition sums to the base population size.
        for plan in plans:
            assert sum(plan.config.population.composition.values()) == plan.config.population.size

    def test_parameter_override_reaches_the_config(self) -> None:
        """A parameter axis value lands in the member config."""
        spec = _spec(parameters=[{"key": "dynamics.selection_beta", "values": [0.25]}])
        plans = expand(spec)
        assert all(p.config.dynamics.selection_beta == 0.25 for p in plans)

    def test_run_level_parameter_override_maps_to_top_level(self) -> None:
        """A ``run.*`` key maps to a top-level config field (#38 mapping)."""
        spec = _spec(parameters=[{"key": "run.tournament_cycles", "values": [7]}])
        plans = expand(spec)
        assert all(p.config.tournament_cycles == 7 for p in plans)


class TestRoundTrip:
    """save/load round-trips a spec (the runner copies it verbatim)."""

    def test_spec_round_trips_through_yaml(self, tmp_path: Path) -> None:
        """save_sweep_spec then load_sweep_spec reproduces the spec."""
        spec = _spec(
            parameters=[{"key": "dynamics.selection_beta", "values": [0.1, 1.0]}],
            metrics=[
                {"metric": "final_share", "strategy": "tit_for_tat"},
                {"metric": "ever_exceeded", "strategy": "tit_for_tat", "threshold": 0.9},
            ],
        )
        path = save_sweep_spec(spec, tmp_path / "spec.yaml")
        assert load_sweep_spec(path) == spec
