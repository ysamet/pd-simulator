"""Tests for the Outcome Metrics Registry (``pdsim/sweep/metrics.py``, #69).

Each metric is exercised on a synthesized :class:`~pdsim.io.results.LoadedRun`
with a hand-controlled composition trajectory, so the expected value is
computable by eye — including both censoring cases, a never-appeared strategy,
and a schema-1 (no cooperation) run.
"""

from __future__ import annotations

import pytest

from pdsim.config.experiment import ExperimentConfig
from pdsim.core.events import GenerationFinished, RunFinished
from pdsim.core.timeseries import RunTimeseries
from pdsim.io.results import LoadedRun
from pdsim.sweep.metrics import all_metrics, get_metric, register_metric


def _run(
    compositions: list[dict[str, int]],
    size: int,
    *,
    cooperation: list[float] | None = None,
) -> LoadedRun:
    """Synthesize a LoadedRun with a given composition trajectory.

    Args:
        compositions: One composition dict per period.
        size: Population size N.
        cooperation: Optional per-period overall cooperation rate; omit for a
            schema-1 run (no cooperation series).

    Returns:
        A LoadedRun the metrics can read.
    """
    # A valid base config (its composition need only sum to size).
    config = ExperimentConfig.model_validate(
        {"population": {"size": size, "composition": {"tit_for_tat": size}}}
    )
    series = RunTimeseries(mode="evolution")
    for index, composition in enumerate(compositions):
        coop_table = {}
        if cooperation is not None:
            # One synthetic self-pair carrying the overall rate for that period.
            coop_table = {("tit_for_tat", "tit_for_tat"): (cooperation[index], 10)}
        series.add(
            GenerationFinished(
                index=index,
                composition=composition,
                mean_scores={name: 1.0 for name in composition},
                rounds_played={name: 1 for name in composition},
                cooperation=coop_table,
            )
        )
    series.add(
        RunFinished(
            mode="evolution",
            completed=len(compositions),
            composition=compositions[-1],
            mean_scores={name: 1.0 for name in compositions[-1]},
            total_scores=None,
        )
    )
    return LoadedRun(config=config, timeseries=series, summary={})


def _compute(name: str, run: LoadedRun, **params: object) -> float | None:
    """Run a registered metric by name.

    Args:
        name: Metric machine name.
        run: The loaded run.
        **params: Metric params.

    Returns:
        The metric value.
    """
    return get_metric(name).compute(run, **params)


class TestShareMetrics:
    """final_share / fixation_flag / mean_share_last_k / thresholds."""

    def test_final_share(self) -> None:
        """Final count / N."""
        run = _run(
            [{"tit_for_tat": 2, "always_defect": 8}, {"tit_for_tat": 5, "always_defect": 5}], 10
        )
        assert _compute("final_share", run, strategy="tit_for_tat") == 0.5

    def test_final_share_never_appeared_is_zero(self) -> None:
        """A strategy absent from the whole run scores 0.0, not an error."""
        run = _run([{"always_defect": 10}], 10)
        assert _compute("final_share", run, strategy="tit_for_tat") == 0.0

    def test_fixation_flag_true_and_false(self) -> None:
        """1.0 iff the strategy ever hit the whole population."""
        fixed = _run([{"tit_for_tat": 4, "always_defect": 6}, {"tit_for_tat": 10}], 10)
        never = _run(
            [{"tit_for_tat": 4, "always_defect": 6}, {"tit_for_tat": 6, "always_defect": 4}], 10
        )
        assert _compute("fixation_flag", fixed, strategy="tit_for_tat") == 1.0
        assert _compute("fixation_flag", never, strategy="tit_for_tat") == 0.0

    def test_mean_share_last_k(self) -> None:
        """Average share over the trailing k periods."""
        run = _run(
            [
                {"tit_for_tat": 2, "always_defect": 8},
                {"tit_for_tat": 4, "always_defect": 6},
                {"tit_for_tat": 6, "always_defect": 4},
            ],
            10,
        )
        # Last 2 periods: shares 0.4 and 0.6 -> mean 0.5.
        assert _compute("mean_share_last_k", run, strategy="tit_for_tat", k=2) == pytest.approx(0.5)

    def test_ever_exceeded(self) -> None:
        """Quasi-fixation: reached the threshold at any period."""
        run = _run(
            [{"tit_for_tat": 5, "always_defect": 5}, {"tit_for_tat": 9, "always_defect": 1}], 10
        )
        assert _compute("ever_exceeded", run, strategy="tit_for_tat", threshold=0.9) == 1.0
        assert _compute("ever_exceeded", run, strategy="tit_for_tat", threshold=0.95) == 0.0

    def test_held_above_for(self) -> None:
        """Staying power: k consecutive periods at or above the threshold."""
        run = _run(
            [
                {"tit_for_tat": 9, "always_defect": 1},
                {"tit_for_tat": 5, "always_defect": 5},
                {"tit_for_tat": 9, "always_defect": 1},
                {"tit_for_tat": 9, "always_defect": 1},
            ],
            10,
        )
        # A run of 2 at/above 0.9 exists (periods 2 and 3), but not 3.
        assert _compute("held_above_for", run, strategy="tit_for_tat", threshold=0.9, k=2) == 1.0
        assert _compute("held_above_for", run, strategy="tit_for_tat", threshold=0.9, k=3) == 0.0


class TestFixationTimeAndCensoring:
    """The two-column survival encoding (companion §3.4)."""

    def test_fixed_run_reports_first_period_uncensored(self) -> None:
        """Time = first fixation index; censored = 0."""
        run = _run(
            [{"tit_for_tat": 4, "always_defect": 6}, {"tit_for_tat": 10}, {"tit_for_tat": 10}], 10
        )
        assert _compute("time_to_fixation", run, strategy="tit_for_tat") == 1.0
        assert _compute("fixation_censored", run, strategy="tit_for_tat") == 0.0

    def test_never_fixed_run_reports_length_censored(self) -> None:
        """Time = periods completed; censored = 1 (it might fix later)."""
        run = _run(
            [{"tit_for_tat": 2, "always_defect": 8}, {"tit_for_tat": 3, "always_defect": 7}], 10
        )
        assert _compute("time_to_fixation", run, strategy="tit_for_tat") == 2.0  # 2 periods
        assert _compute("fixation_censored", run, strategy="tit_for_tat") == 1.0


class TestCooperationMetrics:
    """min/final cooperation, incl. the schema-1 None path (#65)."""

    def test_min_and_final_cooperation(self) -> None:
        """Read the overall cooperation series."""
        run = _run(
            [{"tit_for_tat": 10}, {"tit_for_tat": 10}, {"tit_for_tat": 10}],
            10,
            cooperation=[0.9, 0.3, 0.7],
        )
        assert _compute("min_cooperation", run) == pytest.approx(0.3)
        assert _compute("final_cooperation", run) == pytest.approx(0.7)

    def test_schema_1_run_returns_none(self) -> None:
        """A run with no cooperation series yields None (renders as a gap)."""
        run = _run([{"tit_for_tat": 10}], 10)  # cooperation omitted
        assert _compute("min_cooperation", run) is None
        assert _compute("final_cooperation", run) is None


class TestUnknownStrategy:
    """Strategy-param names are checked at compute time with a plain error."""

    def test_unknown_strategy_raises_plainly(self) -> None:
        """An unregistered strategy name is a clear ValueError."""
        run = _run([{"tit_for_tat": 10}], 10)
        with pytest.raises(ValueError, match="unknown strategy"):
            _compute("final_share", run, strategy="telepathy")


class TestRegistry:
    """The fourth registry's guarantees."""

    def test_every_metric_is_documented(self) -> None:
        """Novice-first rule: each metric has a real description and names."""
        for metric in all_metrics():
            assert len(metric.description.split()) >= 8, f"{metric.name} description too thin"
            assert metric.display_name.strip()

    def test_duplicate_registration_rejected(self) -> None:
        """Re-registering an existing name is always a bug."""
        with pytest.raises(ValueError, match="already registered"):
            register_metric(get_metric("final_share"))

    def test_unknown_metric_lookup_is_helpful(self) -> None:
        """A typo lists the registered names."""
        with pytest.raises(KeyError, match="final_share"):
            get_metric("finl_share")
