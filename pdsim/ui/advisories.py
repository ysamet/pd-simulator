"""Streamlit-free advisory rules: the M11b warning batch A1–A3 (#170/#176).

An advisory is a derived readout whose output is a WARNING rather than a
number, built on the same predicate-table pattern as the M11a greying map
(#141): :data:`ADVISORY_RULES` is a table of rules — key, severity,
surface, predicate — evaluated in one place
(:func:`evaluate_advisories`), with the app rendering whatever fires at
each surface. Every rule is a pure function of (current widget values,
loaded widget values): no session history, no previous-render state — the
loaded baseline (#176 R5) is what makes A2 a change DETECTOR rather than
a one-repaint flash.

The module lives beside :mod:`pdsim.ui.economy_helpers` (the #38/#48
Streamlit-free helper discipline): every branch is unit-testable without
Streamlit, and ``app.py`` only renders.

The batch (docs/ADVISORIES.md, as amended by #170 and #176):

* **A1** — living cost outside the survival window (caution; Economy
  panel, beside the calibration readout). Gate: :func:`~pdsim.ui.
  economy_helpers.economy_active` (#176 R4). Fires when the basic living
  cost is at or below the all-defector income, or at or above the
  all-cooperator income (#176 R1 — both bounds INCLUSIVE for the
  advisory, which is exactly why the printed window is strict).
* **A2** — an income-multiplying parameter changed without recalibration
  (caution; inline at the changed widget). Gate: the same R4 predicate.
  Fires per trigger key while its current value differs from the LOADED
  value (#176 R5).
* **A3** — spatial interaction with k at or above the reachable
  neighbourhood size (info; beside the spatial-interaction toggle).
  Gate: the engine's ACTUAL spatial gate — evolution AND lattice AND
  toggle (#176 R7, the #137(b)/#141(c) predicate) — never the toggle
  alone. The degree is the R6 radius-aware reach size, and the message
  is encounter-mode- and clock-conditional (#175's ripple; #176 R3).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import NamedTuple

from pydantic import ValidationError

from pdsim.config.experiment import interior_reach_size, resolve_lattice_dimensions
from pdsim.config.registry import ParamValue
from pdsim.core.strategies import all_strategies
from pdsim.ui import helpers
from pdsim.ui.economy_helpers import CalibrationReport, calibration_report, economy_active

# Intra-package reuse of the engine-gate predicate (the async_dynamics /
# _CooperationTally precedent): the underscore marks it internal to the UI
# layer, not to helpers.py — A3 must gate on EXACTLY the engine's spatial
# gate (#176 R7), and growing a second copy here could drift from it.
from pdsim.ui.helpers import _spatial_sampling_active

ECONOMY_PANEL_SURFACE = "economy_panel"
"""The A1 surface: the Economy panel, beside the calibration readout.

Widget-anchored advisories use the widget's registry key as their surface;
A1 belongs to a panel, not a widget, so it gets a named pseudo-surface —
the ``population.composition`` pseudo-key idiom (#141)."""


class Advisory(NamedTuple):
    """One fired advisory, ready for the panel to render.

    Attributes:
        key: The advisory's id in docs/ADVISORIES.md (``"A1"``…``"A3"``).
        severity: ``"info"`` or ``"caution"`` — decides the render style.
        surface: Where it appears — a widget's registry key, or
            :data:`ECONOMY_PANEL_SURFACE`.
        message: The text the user sees.
    """

    key: str
    severity: str
    surface: str
    message: str


AdvisoryPredicate = Callable[[Mapping[str, ParamValue], Mapping[str, ParamValue]], str | None]
"""One rule's answer: the message when it fires, ``None`` when silent.

Both arguments are widget-value mappings keyed by registry key: the
CURRENT values (with the app's lookahead) and the LOADED baseline —
what the last scenario/config load wrote into the widgets (#176 R5).
"""


class AdvisoryRule(NamedTuple):
    """One row of the advisory table (the #141 predicate-table pattern).

    Attributes:
        key: The advisory's id in docs/ADVISORIES.md.
        severity: ``"info"`` or ``"caution"``.
        surface: Where a firing renders (see :class:`Advisory`).
        predicate: The pure rule — ``(values, loaded_values)`` → message
            or ``None``.
    """

    key: str
    severity: str
    surface: str
    predicate: AdvisoryPredicate


A1_MESSAGE = (
    "The metabolic filter is switched off — at or below the all-defector "
    "income, defectors never starve; at or above the all-cooperator "
    "income, even a population of pure cooperators cannot pay its bills."
)
"""A1's message (docs/ADVISORIES.md, first clause per #176 R1)."""

A2_MESSAGE = (
    "This change rescales every agent's income (it may raise or lower it). "
    "Recompute the survival window before trusting the living cost."
)
"""A2's message (docs/ADVISORIES.md, as reworded by #178 R8 — the old
"multiplies" implied income only ever goes up)."""

A2_TRIGGER_KEYS = (
    "matching.matcher",
    "matching.opponents_per_agent",
    "match.rounds_per_match",
    "match.continuation_probability",
    "structure.neighbourhood_shape",
    "structure.kind",
    "matching.spatial_interaction",
    "matching.encounter_mode",
    # ADVISORIES.md and #170 name this trigger "matching.interaction_radius";
    # the parameter is REGISTERED as structure.interaction_radius (it renders
    # in the Structure section) — the registry key is the single identifier a
    # parameter has everywhere, so the table uses it (#177's Rule 7 report).
    "structure.interaction_radius",
)
"""A2's nine trigger keys (#170's amended list; `movement.rate` and
`interaction_decay` deliberately excluded — see #170 for reasons)."""


def _calibration_for(values: Mapping[str, ParamValue]) -> CalibrationReport | None:
    """Derive the calibration report from widget values alone (A1's input).

    A1's predicate must be a pure function of the value mappings (the
    table's signature), but :func:`calibration_report` consumes a
    VALIDATED config — so this helper assembles one from the values with
    two stand-ins for the inputs the calibration arithmetic never reads:
    a one-strategy composition (the mix enters no income figure) and the
    ``random`` initial layout (the arrangement enters none either, and
    the from-file layout validators would otherwise demand a file whose
    composition matches the stand-in). Every value the arithmetic DOES
    read — payoffs, matching, match length, structure geometry, the
    ledger — is the user's own. An invalid panel returns ``None`` and the
    advisory stays silent, exactly as the panel's own readout waits for a
    valid configuration.

    Args:
        values: The current widget values (with the app's lookahead).

    Returns:
        The report, or ``None`` while the values do not assemble.
    """
    size = values.get("population.size")
    if not isinstance(size, int) or size < 1:
        return None
    strategies = all_strategies()
    if not strategies:
        return None
    stand_in_mix = {strategies[0].name: size}
    neutral = dict(values)
    neutral["structure.initial_layout"] = "random"
    neutral["structure.layout_file"] = None
    try:
        config = helpers.build_config(neutral, stand_in_mix)
    except ValidationError:
        return None
    return calibration_report(config)


def _a1_living_cost(
    values: Mapping[str, ParamValue], loaded_values: Mapping[str, ParamValue]
) -> str | None:
    """A1: the living cost sits outside the survival window (#176 R1).

    Fires when ``basic_living_cost`` ≤ the all-D income (inclusive — at
    the bound a defector nets exactly zero and never starves) or ≥ the
    all-C income (inclusive — at the bound a pure cooperator nets zero
    and cannot fund reproduction's overheads). The incomes come from
    :func:`calibration_report`, which branches to the spatial arithmetic
    exactly when the spatial gate holds (#154/#176), so the advisory and
    the readout beside it can never disagree.

    Args:
        values: Current widget values (with the app's lookahead).
        loaded_values: The loaded baseline (unused; the signature is the
            table's).

    Returns:
        :data:`A1_MESSAGE` when the filter is off, else ``None``.
    """
    if not economy_active(values):
        return None
    report = _calibration_for(values)
    if report is None:
        return None
    if report.living_cost <= report.all_d_income or report.living_cost >= report.all_c_income:
        return A1_MESSAGE
    return None


def _a2_rule(key: str) -> AdvisoryPredicate:
    """Build A2's per-key predicate: changed-since-load detection (#176 R5).

    A factory (one closure per trigger key) rather than nine hand-written
    functions — the same rule at nine surfaces. The baseline is the
    LOADED scenario's values: loading writes a fresh baseline, so loading
    clears every A2 by construction. A key absent from the baseline has
    nothing to differ from and stays silent (never guess a baseline).

    Args:
        key: The trigger key this closure watches.

    Returns:
        The predicate for one :class:`AdvisoryRule` row.
    """

    def predicate(
        values: Mapping[str, ParamValue], loaded_values: Mapping[str, ParamValue]
    ) -> str | None:
        if not economy_active(values):
            return None
        if key not in loaded_values:
            return None
        if values.get(key) == loaded_values[key]:
            return None
        return A2_MESSAGE

    return predicate


def _a3_message(values: Mapping[str, ParamValue]) -> str:
    """A3's mode-conditional message (#175's ripple; #176 R3).

    Under the asynchronous clock the encounter mode is per-initiator by
    construction and the figure is an expectation, so the message always
    carries the per-initiator arithmetic phrased as expected — a stranded
    ``per_pair`` widget value never reaches it (the same forcing the
    calibration report applies).

    Args:
        values: Current widget values (with the app's lookahead).

    Returns:
        The message variant for the current clock and encounter mode.
    """
    if values.get("dynamics.time_model") == "asynchronous":
        return (
            "Every agent is expected to play all its reachable neighbours "
            "and be drawn in by each of them per generation-equivalent, so "
            "matches per agent is expected to be roughly twice the degree "
            "— income is doubled relative to a naive reading."
        )
    if values.get("matching.encounter_mode") == "per_pair":
        return (
            "Every agent plays all its reachable neighbours, and encounter "
            "mode 'per_pair' collapses the duplicate pairs — each pair "
            "meets once, so matches per agent roughly equals the degree."
        )
    return (
        "Every agent plays all its neighbours and is played by all of "
        "them, so matches per agent is roughly twice the degree — income "
        "is doubled relative to a naive reading."
    )


def _a3_full_neighbourhood(
    values: Mapping[str, ParamValue], loaded_values: Mapping[str, ParamValue]
) -> str | None:
    """A3: k reaches the whole neighbourhood, so the budget is the geometry.

    Gate (#176 R7): the engine's ACTUAL spatial gate — evolution AND
    lattice AND toggle — never the toggle alone, which is false under
    ``well_mixed`` (a greyed checkbox keeps its value) and under
    tournament. Fires when k ≥ the R6 radius-aware reach size
    (:func:`interior_reach_size`): every reachable neighbour is then
    played, and the interaction budget is set by the grid's geometry
    rather than by k.

    Args:
        values: Current widget values (with the app's lookahead).
        loaded_values: The loaded baseline (unused; the signature is the
            table's).

    Returns:
        The mode-conditional message when k covers the neighbourhood,
        else ``None``.
    """
    if not _spatial_sampling_active(values):
        return None
    shape = values.get("structure.neighbourhood_shape")
    k = values.get("matching.opponents_per_agent")
    radius = values.get("structure.interaction_radius")
    if not isinstance(shape, str) or not isinstance(k, int):
        return None
    if radius is not None and not isinstance(radius, int):
        return None
    site_count = None
    size = values.get("population.size")
    if isinstance(size, int) and size >= 1:
        rows = values.get("structure.rows")
        cols = values.get("structure.cols")
        resolved_rows, resolved_cols = resolve_lattice_dimensions(
            rows if isinstance(rows, int) else None,
            cols if isinstance(cols, int) else None,
            size,
        )
        site_count = resolved_rows * resolved_cols
    if radius is None and site_count is None:
        return None  # unlimited reach with no grid size yet — cannot judge
    if k < interior_reach_size(shape, radius, site_count):
        return None
    return _a3_message(values)


ADVISORY_RULES: tuple[AdvisoryRule, ...] = (
    AdvisoryRule("A1", "caution", ECONOMY_PANEL_SURFACE, _a1_living_cost),
    *(AdvisoryRule("A2", "caution", key, _a2_rule(key)) for key in A2_TRIGGER_KEYS),
    AdvisoryRule("A3", "info", "matching.spatial_interaction", _a3_full_neighbourhood),
)
"""The advisory table (ADVISORIES.md's M11b batch): A1, A2 × nine trigger
surfaces, A3 — evaluated in one place by :func:`evaluate_advisories`."""


def evaluate_advisories(
    values: Mapping[str, ParamValue], loaded_values: Mapping[str, ParamValue]
) -> tuple[Advisory, ...]:
    """Evaluate every advisory rule — the table's one evaluation point.

    Args:
        values: Current widget values (with the app's lookahead).
        loaded_values: The loaded baseline (#176 R5) — what the last
            scenario/config load wrote into the widgets.

    Returns:
        The fired advisories, in table order.
    """
    fired: list[Advisory] = []
    for rule in ADVISORY_RULES:
        message = rule.predicate(values, loaded_values)
        if message is not None:
            fired.append(Advisory(rule.key, rule.severity, rule.surface, message))
    return tuple(fired)


def advisories_for_surface(
    surface: str,
    values: Mapping[str, ParamValue],
    loaded_values: Mapping[str, ParamValue],
) -> tuple[Advisory, ...]:
    """The fired advisories anchored at one surface (the app's per-seam call).

    Args:
        surface: A widget's registry key, or
            :data:`ECONOMY_PANEL_SURFACE`.
        values: Current widget values (with the app's lookahead).
        loaded_values: The loaded baseline (#176 R5).

    Returns:
        The fired advisories whose surface matches, in table order.
    """
    return tuple(
        advisory
        for advisory in evaluate_advisories(values, loaded_values)
        if advisory.surface == surface
    )
