"""The sweep/search layer: run families of experiments, summarise the family.

A *sweep* runs not one simulation but a controlled family of them — one base
configuration varied along one or more axes (a composition axis, parameter
grids, seed lists) — and summarises the family as a table and a metric-vs-axis
curve. Its founding purpose is invasion-threshold questions (see
``docs/explainers/M9.5-sweeps-and-invasion.md``); the design is scoped in
DECISIONS #59 and built in #66-#71.

**Defining principle (#59):** this layer consumes only configs and recorded run
folders. It touches no engine semantics — it is a config *generator* plus
post-processing over recorded runs. Every configuration it produces is a
first-class, fully-validated :class:`~pdsim.config.experiment.ExperimentConfig`
that could have been written by hand, and every member run is independently
reproducible from its own ``config.yaml`` (hard rule 8).

This is an **orchestration-tier** subpackage (like ``run.py`` / ``bench.py`` /
``gendocs.py``, DECISIONS #48): it may import ``config``, ``core``, ``io``, and
``viz``, but stays **free of Streamlit** so the future Sweep tab (M9.5b) can
import from it. Run a sweep with ``python -m pdsim.sweep <spec.yaml>``.
"""

from __future__ import annotations

from pdsim.sweep.metrics import (
    OutcomeMetricInfo,
    all_metrics,
    get_metric,
    register_metric,
)
from pdsim.sweep.spec import (
    CompositionAxis,
    MemberPlan,
    MetricRef,
    ParameterAxis,
    SweepSpec,
    expand,
    load_sweep_spec,
    resolve_composition,
    sweep_validation_messages,
)

__all__ = [
    "CompositionAxis",
    "MemberPlan",
    "MetricRef",
    "OutcomeMetricInfo",
    "ParameterAxis",
    "SweepSpec",
    "all_metrics",
    "expand",
    "get_metric",
    "load_sweep_spec",
    "register_metric",
    "resolve_composition",
    "sweep_validation_messages",
]
