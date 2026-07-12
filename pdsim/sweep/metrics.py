"""Outcome Metrics Registry — named functions that score a finished run.

The **fourth** instance of the project's registry idiom (DESIGN §5, after the
Parameter, Strategy, and Scenario registries; DECISIONS #69): immutable
declarations in one module-level dict, written only at import time. Each metric
is named, described in plain language (mandatory — hard rule 3's mirror), and
computed from a *loaded* run (:class:`~pdsim.io.results.LoadedRun`).

Metrics are **pure post-processing over recorded runs** (DECISIONS #47/#59):
``compute`` reads the reconstructed ``timeseries`` and ``config`` — never raw
parquet — so a metric written today works retroactively on any recording and
inherits schema-compatibility handling for free (schema-1 runs simply lack
cooperation data, and the cooperation metrics return ``None`` there — #65).

A functional-programming note (a learning thread of this project): a metric is
a *pure function* of a run — same run in, same number out, no side effects. The
registry stores these functions as data (``OutcomeMetricInfo.compute``), exactly
as the Strategy Registry stores strategy classes as ``factory``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Import only for type checkers — avoids a runtime import cycle and keeps
    # metric compute functions free to be pickled into sweep workers.
    from pdsim.io.results import LoadedRun

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
"""Metric machine names follow the registry-idiom convention (lowercase token)."""

MetricValue = float | None
"""What a metric returns: a number, or ``None`` for "not applicable / undefined"."""


@dataclass(frozen=True, slots=True)
class MetricParam:
    """One parameter a metric accepts (a lightweight spec — the UI is M9.5b).

    Not a full :class:`~pdsim.config.registry.ParameterSpec`: metric params are
    call-time arguments in a SweepSpec, not tunable simulation knobs, so they
    carry only what documentation and basic validation need.

    Attributes:
        name: Keyword name, e.g. ``"strategy"`` or ``"threshold"``.
        kind: Plain-language type hint, e.g. ``"strategy"``, ``"float"``,
            ``"int"``.
        description: Plain-language explanation (mandatory).
        default: Optional default; ``None`` means the param is required.
    """

    name: str
    kind: str
    description: str
    default: float | int | str | None = None


@dataclass(frozen=True, slots=True)
class OutcomeMetricInfo:
    """Complete declaration of one outcome metric.

    Attributes:
        name: Machine name used in a SweepSpec's ``metrics`` list.
        display_name: Human-readable name for charts and docs.
        description: Plain-language "what does this measure?" text
            (mandatory — hard rule 3's mirror).
        params: The metric's call-time parameters, in declaration order.
        compute: The metric function: ``(run, **params) -> float | None``.
    """

    name: str
    display_name: str
    description: str
    compute: Callable[..., MetricValue]
    params: tuple[MetricParam, ...] = ()

    def __post_init__(self) -> None:
        """Check that the declaration is well-formed (fail fast at import).

        Raises:
            ValueError: If the machine name is malformed or the description
                is empty.
        """
        if not _NAME_PATTERN.match(self.name):
            raise ValueError(
                f"Outcome metric name {self.name!r} must be a lowercase token like 'final_share'."
            )
        if not self.description.strip():
            raise ValueError(f"Outcome metric {self.name!r} has no description — hard rule 3.")

    def param_names(self) -> tuple[str, ...]:
        """Return the metric's parameter names, in declaration order.

        Returns:
            The keyword names ``compute`` accepts.
        """
        return tuple(param.name for param in self.params)


_METRICS: dict[str, OutcomeMetricInfo] = {}


def register_metric(info: OutcomeMetricInfo) -> OutcomeMetricInfo:
    """Add a metric to the registry.

    Args:
        info: The fully-declared metric.

    Returns:
        The same info (the registry idiom's convention).

    Raises:
        ValueError: If a metric with the same machine name is already
            registered — duplicate declarations are always a bug.
    """
    if info.name in _METRICS:
        raise ValueError(
            f"Outcome metric {info.name!r} is already registered; names must be unique."
        )
    _METRICS[info.name] = info
    return info


def get_metric(name: str) -> OutcomeMetricInfo:
    """Look up a metric by machine name.

    Args:
        name: Machine name, e.g. ``"final_share"``.

    Returns:
        The registered :class:`OutcomeMetricInfo`.

    Raises:
        KeyError: If no metric with this name exists (the message lists the
            registered names).
    """
    try:
        return _METRICS[name]
    except KeyError:
        known = ", ".join(sorted(_METRICS))
        raise KeyError(f"Unknown outcome metric {name!r}. Registered metrics: {known}") from None


def all_metrics() -> tuple[OutcomeMetricInfo, ...]:
    """Return every registered metric, in registration (= display) order.

    Returns:
        An immutable snapshot of the registry.
    """
    return tuple(_METRICS.values())


# ---------------------------------------------------------------------------
# Small helpers shared by the seed metrics. Each reads the loaded run's
# reconstructed series (never raw parquet), so metrics are retroactive (#47).
# ---------------------------------------------------------------------------


def _size(run: LoadedRun) -> int:
    """Return the population size of a loaded run.

    Args:
        run: The loaded run.

    Returns:
        ``config.population.size``.
    """
    return run.config.population.size


def _counts(run: LoadedRun, strategy: str) -> list[int]:
    """Return a strategy's per-period agent counts (0 if it never appeared).

    Args:
        run: The loaded run.
        strategy: Strategy machine name.

    Returns:
        One count per period, aligned with ``timeseries.periods``; an
        all-zero list if the strategy is absent from the run.
    """
    _check_strategy(run, strategy)
    series = run.timeseries.composition.get(strategy)
    if series is None:
        return [0] * len(run.timeseries.periods)
    return list(series)


def _check_strategy(run: LoadedRun, strategy: str) -> None:
    """Validate a strategy-param name against the run's roster at compute time.

    Args:
        run: The loaded run.
        strategy: The strategy machine name a metric was asked about.

    Raises:
        ValueError: If the name is not a registered strategy — a plain
            message, since metric params come from user-authored SweepSpecs.
    """
    from pdsim.core.strategies import all_strategy_names

    if strategy not in all_strategy_names():
        valid = ", ".join(sorted(all_strategy_names()))
        raise ValueError(
            f"metric asked about unknown strategy {strategy!r}. Valid strategies: {valid}."
        )


# ---------------------------------------------------------------------------
# The seed metric set (DECISIONS #69). Share-based metrics divide agent counts
# by the population size; the cooperation metrics read the overall series (#65).
# ---------------------------------------------------------------------------


def _final_share(run: LoadedRun, strategy: str) -> MetricValue:
    """Final share of the population held by a strategy.

    Args:
        run: The loaded run.
        strategy: Strategy machine name.

    Returns:
        ``count[-1] / N`` (0.0 if the strategy never appeared or there are
        no periods).
    """
    counts = _counts(run, strategy)
    if not counts:
        return 0.0
    return counts[-1] / _size(run)


def _fixation_flag(run: LoadedRun, strategy: str) -> MetricValue:
    """Whether a strategy ever reached the whole population.

    Args:
        run: The loaded run.
        strategy: Strategy machine name.

    Returns:
        1.0 if ``count == N`` in any period, else 0.0.
    """
    size = _size(run)
    return 1.0 if any(count == size for count in _counts(run, strategy)) else 0.0


def _time_to_fixation(run: LoadedRun, strategy: str) -> MetricValue:
    """Period index at which a strategy first reached fixation.

    Paired with :func:`_fixation_censored`: a run that never fixes reports
    ``time = periods_completed`` and ``censored = 1`` (survival-analysis
    encoding, no sentinels — companion §3.4).

    Args:
        run: The loaded run.
        strategy: Strategy machine name.

    Returns:
        The 0-based index of the first fixation period, or the number of
        periods completed if fixation never occurred.
    """
    size = _size(run)
    counts = _counts(run, strategy)
    for index, count in enumerate(counts):
        if count == size:
            return float(index)
    return float(len(counts))


def _fixation_censored(run: LoadedRun, strategy: str) -> MetricValue:
    """The censoring flag paired with :func:`_time_to_fixation`.

    Args:
        run: The loaded run.
        strategy: Strategy machine name.

    Returns:
        1.0 if the strategy never fixed (the fixation time is censored),
        else 0.0.
    """
    return 1.0 - _fixation_flag(run, strategy)


def _mean_share_last_k(run: LoadedRun, strategy: str, k: int) -> MetricValue:
    """Mean population share over the last k periods.

    Args:
        run: The loaded run.
        strategy: Strategy machine name.
        k: Number of trailing periods to average (clamped to what exists).

    Returns:
        Mean of ``count / N`` over the last ``min(k, periods)`` periods, or
        ``None`` if there are no periods.
    """
    counts = _counts(run, strategy)
    if not counts:
        return None
    window = counts[-int(k) :] if k >= 1 else counts
    size = _size(run)
    return sum(count / size for count in window) / len(window)


def _ever_exceeded(run: LoadedRun, strategy: str, threshold: float) -> MetricValue:
    """Whether a strategy's share ever reached a threshold (quasi-fixation).

    Args:
        run: The loaded run.
        strategy: Strategy machine name.
        threshold: Share in [0, 1] the strategy must reach.

    Returns:
        1.0 if ``count / N >= threshold`` in any period, else 0.0.
    """
    size = _size(run)
    return 1.0 if any(count / size >= threshold for count in _counts(run, strategy)) else 0.0


def _held_above_for(run: LoadedRun, strategy: str, threshold: float, k: int) -> MetricValue:
    """Whether a strategy held above a threshold for k consecutive periods.

    Args:
        run: The loaded run.
        strategy: Strategy machine name.
        threshold: Share in [0, 1].
        k: Required run length of consecutive periods at or above threshold.

    Returns:
        1.0 if some window of ``k`` consecutive periods all had
        ``count / N >= threshold``, else 0.0.
    """
    size = _size(run)
    streak = 0
    for count in _counts(run, strategy):
        streak = streak + 1 if count / size >= threshold else 0
        if streak >= k:
            return 1.0
    return 0.0


def _cooperation_series(run: LoadedRun) -> list[float]:
    """Return the run's non-None overall cooperation rates.

    Args:
        run: The loaded run.

    Returns:
        The overall cooperation series with ``None`` gaps dropped; empty for
        schema-1 runs (recorded before cooperation existed, #65).
    """
    return [rate for rate in run.timeseries.cooperation_overall if rate is not None]


def _min_cooperation(run: LoadedRun) -> MetricValue:
    """The lowest overall cooperation rate the run reached.

    Args:
        run: The loaded run.

    Returns:
        The minimum of the overall cooperation series, or ``None`` when the
        series is empty (schema-1 run — the collapse metrics #65 enabled).
    """
    series = _cooperation_series(run)
    return min(series) if series else None


def _final_cooperation(run: LoadedRun) -> MetricValue:
    """The final overall cooperation rate.

    Args:
        run: The loaded run.

    Returns:
        The last overall cooperation rate, or ``None`` for a schema-1 run.
    """
    series = _cooperation_series(run)
    return series[-1] if series else None


_STRATEGY_PARAM = MetricParam("strategy", "strategy", "The strategy machine name to measure.")

register_metric(
    OutcomeMetricInfo(
        name="final_share",
        display_name="Final share",
        description=(
            "The fraction of the population the strategy holds at the end of the run "
            "(its final count divided by the population size). 0 means it died out; "
            "1 means it took over completely."
        ),
        compute=_final_share,
        params=(_STRATEGY_PARAM,),
    )
)

register_metric(
    OutcomeMetricInfo(
        name="fixation_flag",
        display_name="Reached fixation",
        description=(
            "1 if the strategy ever grew to the entire population at any point in "
            "the run, otherwise 0. 'Fixation' is reaching 100% — the classic "
            "take-over event."
        ),
        compute=_fixation_flag,
        params=(_STRATEGY_PARAM,),
    )
)

register_metric(
    OutcomeMetricInfo(
        name="time_to_fixation",
        display_name="Time to fixation",
        description=(
            "The generation (or cycle) at which the strategy first reached the whole "
            "population. If it never did, this reports the number of periods the run "
            "lasted — pair it with 'fixation_censored' to tell the two cases apart "
            "(the run simply ended first; fixation might still have happened later)."
        ),
        compute=_time_to_fixation,
        params=(_STRATEGY_PARAM,),
    )
)

register_metric(
    OutcomeMetricInfo(
        name="fixation_censored",
        display_name="Fixation censored",
        description=(
            "1 if the strategy never reached fixation during the run (so its "
            "'time_to_fixation' is a lower bound, not the true time), otherwise 0. "
            "This is the survival-analysis 'censored' flag — it keeps runs that "
            "ended early honest instead of pretending fixation never happens."
        ),
        compute=_fixation_censored,
        params=(_STRATEGY_PARAM,),
    )
)

register_metric(
    OutcomeMetricInfo(
        name="mean_share_last_k",
        display_name="Mean share (last k periods)",
        description=(
            "The strategy's average population share over the final k generations "
            "(or cycles). A smoother 'where did it end up' measure than the single "
            "final share — useful when the population wobbles near the end."
        ),
        compute=_mean_share_last_k,
        params=(
            _STRATEGY_PARAM,
            MetricParam("k", "int", "How many trailing periods to average.", default=10),
        ),
    )
)

register_metric(
    OutcomeMetricInfo(
        name="ever_exceeded",
        display_name="Ever exceeded threshold",
        description=(
            "1 if the strategy's share ever reached the given threshold (a fraction "
            "between 0 and 1) at any point, otherwise 0. A 'quasi-fixation' measure: "
            "when mutation keeps a population from ever being perfectly pure, "
            "'reached 90%' is often the honest question rather than 'reached 100%'."
        ),
        compute=_ever_exceeded,
        params=(
            _STRATEGY_PARAM,
            MetricParam("threshold", "float", "Share (0-1) the strategy must reach.", default=0.9),
        ),
    )
)

register_metric(
    OutcomeMetricInfo(
        name="held_above_for",
        display_name="Held above threshold for k periods",
        description=(
            "1 if the strategy's share stayed at or above the threshold for at least "
            "k consecutive generations (or cycles) somewhere in the run, otherwise 0. "
            "A staying-power measure: it rewards durable dominance, not a one-period "
            "spike."
        ),
        compute=_held_above_for,
        params=(
            _STRATEGY_PARAM,
            MetricParam("threshold", "float", "Share (0-1) to stay at or above.", default=0.9),
            MetricParam("k", "int", "Required run of consecutive periods.", default=5),
        ),
    )
)

register_metric(
    OutcomeMetricInfo(
        name="min_cooperation",
        display_name="Minimum cooperation rate",
        description=(
            "The lowest overall cooperation rate the population reached at any point "
            "(0 = everyone defecting, 1 = everyone cooperating). Catches a "
            "cooperation collapse even if the population recovers afterwards. Not "
            "available for runs recorded before cooperation tracking existed."
        ),
        compute=_min_cooperation,
    )
)

register_metric(
    OutcomeMetricInfo(
        name="final_cooperation",
        display_name="Final cooperation rate",
        description=(
            "The overall cooperation rate at the end of the run (0 = everyone "
            "defecting, 1 = everyone cooperating). Not available for runs recorded "
            "before cooperation tracking existed."
        ),
        compute=_final_cooperation,
    )
)
