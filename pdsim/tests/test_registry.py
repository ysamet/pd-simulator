"""Tests for the Parameter Registry (``pdsim/config/registry.py``).

Covers spec well-formedness, value validation for every parameter kind, and
the registry's guarantees (unique keys, helpful lookup errors, and — because
the platform is novice-first — that every parameter actually explains itself).
"""

import pytest

from pdsim.config import registry
from pdsim.config.registry import ParameterSpec


def _spec(**overrides: object) -> ParameterSpec:
    """Build a throwaway valid spec, overriding selected fields.

    Args:
        **overrides: ParameterSpec fields to replace in the baseline.

    Returns:
        A ParameterSpec that is valid unless an override breaks it.
    """
    fields: dict = {
        "key": "test.example",
        "kind": "float",
        "default": 0.5,
        "minimum": 0.0,
        "maximum": 1.0,
        "label": "Example",
        "section": "Test",
        "description": "A throwaway parameter used only in tests.",
    }
    fields.update(overrides)
    return ParameterSpec(**fields)


class TestParameterSpecWellFormedness:
    """A malformed spec must fail at construction, not at use."""

    def test_malformed_key_rejected(self) -> None:
        """Keys must be dotted lowercase paths."""
        with pytest.raises(ValueError, match="dotted lowercase"):
            _spec(key="NoDots")

    def test_empty_description_rejected(self) -> None:
        """Hard rule 3: a parameter without an explanation is a bug."""
        with pytest.raises(ValueError, match="no description"):
            _spec(description="   ")

    def test_choice_kind_requires_choices(self) -> None:
        """A 'choice' parameter must declare its options."""
        with pytest.raises(ValueError, match="choices"):
            _spec(kind="choice", default="a", minimum=None, maximum=None)

    def test_choices_forbidden_on_numeric_kind(self) -> None:
        """Only 'choice' parameters may declare choices."""
        with pytest.raises(ValueError, match="only 'choice'"):
            _spec(choices=("a", "b"))

    def test_bounds_forbidden_on_bool(self) -> None:
        """Bounds make no sense for true/false parameters."""
        with pytest.raises(ValueError, match="numbers only"):
            _spec(kind="bool", default=True, minimum=0.0)

    def test_invalid_default_rejected(self) -> None:
        """The default must satisfy the spec's own rules."""
        with pytest.raises(ValueError, match="at most"):
            _spec(default=2.0)  # above maximum=1.0


class TestValueValidation:
    """ParameterSpec.validate() across kinds, bounds, and edge cases."""

    def test_float_accepts_int_and_widens(self) -> None:
        """YAML often parses '5' as int; float parameters must accept it."""
        assert _spec().validate(1) == 1.0
        assert isinstance(_spec().validate(1), float)

    def test_int_rejects_float(self) -> None:
        """Whole-number parameters must not silently truncate floats."""
        spec = _spec(kind="int", default=5, minimum=1, maximum=10)
        with pytest.raises(ValueError, match="whole number"):
            spec.validate(2.5)

    def test_numeric_kinds_reject_bool(self) -> None:
        """Python's bool subclasses int; True must not pass as the number 1."""
        spec = _spec(kind="int", default=5, minimum=1, maximum=10)
        with pytest.raises(ValueError, match=r"whole number|number"):
            spec.validate(True)

    def test_bool_rejects_non_bool(self) -> None:
        """Truthiness is not enough: 1 is not an accepted bool value."""
        spec = _spec(kind="bool", default=True, minimum=None, maximum=None)
        with pytest.raises(ValueError, match="true or false"):
            spec.validate(1)

    def test_minimum_enforced(self) -> None:
        """Values below the inclusive lower bound are rejected."""
        with pytest.raises(ValueError, match="at least"):
            _spec().validate(-0.1)

    def test_inclusive_maximum_allows_boundary(self) -> None:
        """An inclusive maximum accepts the boundary value itself."""
        assert _spec().validate(1.0) == 1.0

    def test_exclusive_maximum_rejects_boundary(self) -> None:
        """continuation_probability-style bounds must reject the maximum itself."""
        spec = _spec(maximum_exclusive=True, default=0.5)
        with pytest.raises(ValueError, match="strictly below"):
            spec.validate(1.0)

    def test_choice_membership_enforced(self) -> None:
        """A choice value outside the declared options is rejected."""
        spec = _spec(kind="choice", default="a", choices=("a", "b"), minimum=None, maximum=None)
        assert spec.validate("b") == "b"
        with pytest.raises(ValueError, match="must be one of"):
            spec.validate("c")

    def test_nullable_accepts_none(self) -> None:
        """Nullable parameters (e.g. memory depth) accept None as 'unlimited'."""
        spec = _spec(nullable=True)
        assert spec.validate(None) is None

    def test_non_nullable_rejects_none(self) -> None:
        """None must not slip into parameters that don't declare nullable."""
        with pytest.raises(ValueError, match="null"):
            _spec().validate(None)


class TestRegistry:
    """The registry's global guarantees."""

    def test_duplicate_key_rejected(self) -> None:
        """Registering the same key twice is always a bug."""
        existing = registry.get_spec("run.seed")
        with pytest.raises(ValueError, match="already registered"):
            registry.register(existing)

    def test_unknown_key_lookup_is_helpful(self) -> None:
        """A typo'd key should fail with the known keys in the message."""
        with pytest.raises(KeyError, match=r"run\.seed"):
            registry.get_spec("run.sead")

    def test_validate_value_convenience(self) -> None:
        """validate_value composes lookup + validation."""
        assert registry.validate_value("dynamics.mutation_rate", 0.5) == 0.5
        with pytest.raises(ValueError, match="at most"):
            registry.validate_value("dynamics.mutation_rate", 1.5)

    def test_every_default_passes_its_own_validation(self) -> None:
        """Each registered default must satisfy its own spec."""
        for spec in registry.all_specs():
            spec.validate(spec.default)  # raises on failure

    def test_every_spec_is_novice_documented(self) -> None:
        """Novice-first rule: every parameter carries a real explanation."""
        for spec in registry.all_specs():
            assert len(spec.description.split()) >= 8, f"{spec.key} description too thin"
            assert spec.label.strip(), f"{spec.key} has no label"
            assert spec.section.strip(), f"{spec.key} has no section"

    def test_expected_v1_parameters_present(self) -> None:
        """The v1 engine parameters from docs/DESIGN.md §2 are all registered."""
        expected = {
            "game.payoff_temptation",
            "game.payoff_reward",
            "game.payoff_punishment",
            "game.payoff_sucker",
            "game.enforce_pd_ordering",
            "game.enforce_alternation_constraint",
            "matching.matcher",
            "match.length_mode",
            "match.rounds_per_match",
            "match.continuation_probability",
            "match.noise_epsilon",
            "population.size",
            "population.memory_depth",
            "dynamics.generations",
            "dynamics.selection_rule",
            "dynamics.selection_beta",
            "dynamics.mutation_rate",
            "run.seed",
        }
        registered = {spec.key for spec in registry.all_specs()}
        assert expected <= registered
