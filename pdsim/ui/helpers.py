"""Streamlit-free helpers behind the app: config <-> widget-state mapping.

Everything with a branch worth testing lives here, importable without
Streamlit (DECISIONS #38): flattening a config into widget values,
assembling widget values back into a validated ``ExperimentConfig``,
choosing a default population mix, and turning pydantic errors into
plain-language strings. ``app.py`` stays presentation-only.

Widget state is a flat mapping keyed by Parameter Registry keys (e.g.
``"dynamics.selection_beta"``), which is also how the app names its
Streamlit widget keys — the registry key is the single identifier a
parameter has everywhere.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import NamedTuple

from pydantic import ValidationError

from pdsim.config.experiment import (
    ExperimentConfig,
    resolve_initial_energy,
    resolve_lattice_dimensions,
    resolve_senescence_factor,
)
from pdsim.config.registry import ParameterSpec, ParamValue, all_specs
from pdsim.core.timeseries import RunTimeseries

# Registry-key prefix -> ExperimentConfig section name. "run" is special:
# its parameters live at the top level of the config (DECISIONS #34).
_SECTIONS = ("game", "matching", "match", "population", "structure", "dynamics", "output")

IGNORED_IN_TOURNAMENT = (
    "dynamics.generations",
    "dynamics.reproduction_mode",
    "dynamics.selection_rule",
    "dynamics.selection_beta",
    "dynamics.selection_tournament_k",
    "dynamics.selection_elite_fraction",
    "dynamics.selection_threshold_multiplier",
    "dynamics.mutation_rate",
    "dynamics.score_accounting",
    "dynamics.accounting_window",
    "dynamics.accounting_discount",
    "dynamics.reproduction_threshold",
    "dynamics.offspring_stake",
    "dynamics.initial_energy",
    "dynamics.basic_living_cost",
    "dynamics.engagement_cost",
    "dynamics.reproduction_overhead",
    "dynamics.capital_return_rate",
    "dynamics.carrying_capacity",
    "dynamics.base_hazard",
    "dynamics.senescence_factor",
    "dynamics.max_age",
    "dynamics.time_model",
    "dynamics.async_population",
    "dynamics.moran_rule",
    "dynamics.moran_weight_birth_death",
    "dynamics.moran_weight_death_birth",
    "dynamics.fixed_n_death_rule",
    "dynamics.imitation_overlay",
    # M11a Phase E (#141): tournament ignores structure WHOLESALE (#120(a))
    # — nothing is born and nothing dies there, so space has nothing to do —
    # and with it the spatial-interaction toggle (the sync kernel
    # substitution exists only in the evolution engines, #137(b)) and the
    # boundary order (no generation boundary of deaths and births exists).
    # Structure landed in Phases A-D with its whole greying map deferred to
    # Phase E, which is why these joined the list only now.
    "matching.spatial_interaction",
    "structure.kind",
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
    "dynamics.boundary_order",
)
"""Parameters that exist but have no effect in tournament mode (DECISIONS #34)."""

_ECONOMY_PARAMS = (
    "dynamics.reproduction_threshold",
    "dynamics.offspring_stake",
    "dynamics.initial_energy",
    "dynamics.basic_living_cost",
    "dynamics.engagement_cost",
    "dynamics.reproduction_overhead",
    "dynamics.capital_return_rate",
    "dynamics.carrying_capacity",
    "dynamics.base_hazard",
    "dynamics.senescence_factor",
    "dynamics.max_age",
)
"""The eleven economy knobs — read only under 'energy_economy' (M10a)."""

_IMITATION_PARAMS = (
    "dynamics.selection_rule",
    "dynamics.selection_beta",
    "dynamics.selection_tournament_k",
    "dynamics.selection_elite_fraction",
    "dynamics.selection_threshold_multiplier",
    "dynamics.score_accounting",
    "dynamics.accounting_window",
    "dynamics.accounting_discount",
)
"""The selection + accounting families — inert under 'energy_economy' (M10a).

``dynamics.mutation_rate`` is deliberately NOT here: both reproduction modes
consume μ (imitation slots and economy newborns alike).
"""

_RULE_PARAMS = {
    "dynamics.selection_beta": "fermi",
    "dynamics.selection_tournament_k": "tournament_k",
    "dynamics.selection_elite_fraction": "truncation",
    "dynamics.selection_threshold_multiplier": "threshold_cloning",
}
"""Selection-rule parameter -> the one rule that reads it (DECISIONS #63)."""

_ACCOUNTING_PARAMS = {
    "dynamics.accounting_window": "sliding_window",
    "dynamics.accounting_discount": "exponential_discount",
}
"""Accounting parameter -> the one accounting choice that reads it (#64)."""

_ASYNC_KNOBS = (
    "dynamics.async_population",
    "dynamics.moran_rule",
    "dynamics.moran_weight_birth_death",
    "dynamics.moran_weight_death_birth",
    "dynamics.fixed_n_death_rule",
    "dynamics.imitation_overlay",
    "output.recording_cadence",
    "output.recording_cadence_m",
)
"""The eight M10b knobs, read only under the asynchronous time model (#34)."""

_ASYNC_INERT = (
    "dynamics.reproduction_mode",
    "dynamics.selection_rule",
    "dynamics.selection_tournament_k",
    "dynamics.selection_elite_fraction",
    "dynamics.selection_threshold_multiplier",
    "dynamics.score_accounting",
    "dynamics.accounting_window",
    "dynamics.accounting_discount",
)
"""Parameters the asynchronous time model ignores wholesale (M10b spec).

``dynamics.selection_beta`` is deliberately NOT here: the imitation
overlay consumes it in async mode, so it gets its own overlay-keyed arm
(the spec's ignored-parameter map carve-out). ``dynamics.mutation_rate``
is consumed by async
newborns, and the ledger knobs (initial energy, L, engagement, r, sigma,
overhead) run in both async modes — none of them grey here.
``matching.matcher`` moved to :data:`STRUCTURE_GREYING`'s async column
(M11a Phase E, #141) — same answer (always greyed under async), one table.
"""

_FIXED_N_PARAMS = ("dynamics.moran_rule", "dynamics.fixed_n_death_rule")
"""Moran machinery — read only when ``async_population = fixed_n``."""

_MORAN_WEIGHTS = ("dynamics.moran_weight_birth_death", "dynamics.moran_weight_death_birth")
"""The mixture weights — read only when ``moran_rule = random``."""

_VARIABLE_N_ONLY = (
    "dynamics.reproduction_threshold",
    "dynamics.carrying_capacity",
    "dynamics.base_hazard",
    "dynamics.senescence_factor",
    "dynamics.max_age",
)
"""Economy demography knobs with no fixed_n meaning (no theta births, no
carrying capacity, no age or insolvency deaths — the Moran replacement is
the only demography there)."""


# ---------------------------------------------------------------------------
# The M11a structure greying map — ONE predicate table, consumed by BOTH
# clock branches (spec Design 11; M11a Phase E, DECISIONS #141).
#
# Built as DATA, not as conditionals scattered through panel code: each row
# names a parameter and answers both branches with a liveness predicate over
# the full widget-value mapping (the #101 lookahead supplies values for
# widgets that render later, so predicates may point forward in registry
# order — `matching.spatial_interaction` greys off `structure.kind`, which
# renders four sections below it). The payoff is one milestone ahead:
# M11b's tab/collapse work becomes a second renderer over this same table.
# `grid_visible` is the table's VISIBILITY sibling — a named predicate kept
# beside the table rather than inside it, because it decides showing, not
# greying; the composition row below reuses it rather than duplicating it.
# ---------------------------------------------------------------------------

GreyingPredicate = Callable[[Mapping[str, ParamValue]], str | None]
"""One branch's answer: the greyed-state note when inert, ``None`` when live."""


class GreyingRule(NamedTuple):
    """One row of the structure greying table: an answer for EACH clock branch.

    Every row answers both branches (spec Design 11's two-branch
    obligation): :func:`greying` delegates early to :func:`_async_greying`,
    so a rule present in only one branch would simply not exist in the
    other — producing exactly the failure #34 warns against, the app
    asserting something false about the user's run.
    ``dynamics.boundary_order`` is the sharp case: its entire content is
    "live under sync, greyed under async", a statement about both branches
    at once, which no single-branch edit can implement.

    Attributes:
        sync: The synchronous-clock answer.
        asynchronous: The asynchronous-clock answer.
    """

    sync: GreyingPredicate
    asynchronous: GreyingPredicate


_NO_GEOMETRY_NOTE = (
    "NOTE: only meaningful on a lattice — a well-mixed world has no "
    "geometry for this to act on (no places, no distance). Switch 'World "
    "structure' to 'lattice' to use it."
)
"""The generic well-mixed cause, shared by every geometry-only structure widget."""

_NEEDS_LATTICE_NOTE = (
    "NOTE: needs a lattice world structure — in a well-mixed world there "
    "is no distance to sample within."
)
"""The spatial toggle's and interaction radii's well-mixed cause.

Wording from the ``matching.spatial_interaction`` registry description and
the #137(e) requires-lattice validator — the same single source (§12).
"""

_TOGGLE_OFF_NOTE = (
    "NOTE: only consulted while 'Spatial interaction' (in the Matching "
    "section) is on — switch it on to sample partners by distance."
)
"""The interaction radii's toggle-off cause (the registry description's rule)."""

_MATCHER_SPATIAL_NOTE = (
    "NOTE: not consulted while 'Spatial interaction' is on — partners come "
    "from the grid via the reach kernel, and 'Opponents per agent' (k) does "
    "the work. Switch spatial interaction off to use a matching scheme."
)
"""The sync matcher cell (#108/#137: round-robin has no local analogue)."""

_ASYNC_MATCHER_NOTE = (
    "NOTE: IGNORED under the asynchronous time model — each focal event "
    "draws its own partners (uniformly across the population, or from the "
    "grid while 'Spatial interaction' is on), consuming 'Opponents per "
    "agent' directly. Round-robin is a generation-batch concept with no "
    "event-time analogue."
)
"""The async matcher cell — reworded at Phase E (#141): the old note called
the partner draw 'uniformly (the well-mixed corner)', true only while the
spatial toggle is off (#137(c) substitutes the draw when it is on)."""

_LAYOUT_FILE_NOTE = (
    "NOTE: read only when the initial layout is 'from_file' — pick that "
    "layout to paint the world from a file, or leave this empty."
)
"""The layout-file cell (the `continuation_probability` idiom, spec Design 11)."""

_CONTEST_WELL_MIXED_NOTE = "NOTE: a well-mixed world has no cells to contest."
"""placement_contest's well-mixed cause (the registry description's wording)."""

_CONTEST_IMITATION_NOTE = (
    "NOTE: under 'imitation' reproduction there are no births to place — "
    "only a synchronous energy-economy run on a lattice reads this."
)
"""placement_contest's sync-imitation cause (#107's three-way conjunction)."""

_CONTEST_ASYNC_NOTE = (
    "NOTE: an asynchronous run resolves one birth at a time, so births "
    "never contend for ground — there is nothing to contest."
)
"""placement_contest's async cause (the registry description's wording)."""

_CONTEST_FIXED_N_NOTE = (
    "NOTE: under the fixed-size ('fixed_n' Moran) population the newborn "
    "takes exactly the freed site — there is no placement to contest."
)
"""placement_contest's async fixed_n cause (#132: no placement draw exists)."""

_BOUNDARY_ORDER_ASYNC_NOTE = (
    "NOTE: only read at a synchronous generation boundary — the "
    "asynchronous clock has no generation boundary of deaths and births "
    "to order."
)
"""boundary_order's async cell (#131: the parameter is never read there)."""

_COMPOSITION_FROM_FILE_NOTE = (
    "NOTE: set by the layout file — under 'from_file' the file decides "
    "both the arrangement and the mixture (spec Design 8: the file wins). "
    "Use the 'Populate the Population section from the file' button to "
    "bring these widgets into agreement."
)
"""The composition row's from-file cell (#124's flow is the write path)."""


def _on_a_lattice(values: Mapping[str, ParamValue]) -> bool:
    """True when the world-structure widget says lattice.

    Args:
        values: Widget values (with the app's lookahead — see
            :func:`greying`).

    Returns:
        Whether ``structure.kind`` currently reads ``"lattice"``.
    """
    return values.get("structure.kind") == "lattice"


def _spatial_sampling_active(values: Mapping[str, ParamValue]) -> bool:
    """True when partners genuinely come from the grid.

    The engine's own gate (#137(b)): an EVOLUTION run on a lattice with the
    spatial-interaction toggle on. The mode check is load-bearing —
    tournament ignores structure wholesale (#120(a)) and keeps consulting
    the configured matcher, so the matcher must never grey there.

    Args:
        values: Widget values (with the app's lookahead).

    Returns:
        Whether spatial partner sampling would actually run.
    """
    return (
        values.get("run.mode") != "tournament"
        and _on_a_lattice(values)
        and bool(values.get("matching.spatial_interaction"))
    )


def _always_live(values: Mapping[str, ParamValue]) -> str | None:
    """The always-live answer (``structure.kind`` is the gate and never greys).

    Args:
        values: Widget values (unused; the signature is the table's).

    Returns:
        Always ``None`` — live.
    """
    return None


def _geometry_only(values: Mapping[str, ParamValue]) -> str | None:
    """Grey under well-mixed, live on a lattice — the map's base rule.

    Args:
        values: Widget values (with the app's lookahead).

    Returns:
        The no-geometry note under well-mixed, else ``None``.
    """
    return None if _on_a_lattice(values) else _NO_GEOMETRY_NOTE


def _needs_lattice(values: Mapping[str, ParamValue]) -> str | None:
    """The spatial toggle's rule: grey under well-mixed, with the lattice note.

    This is the map's genuinely FORWARD-POINTING rule: the Matching section
    renders four sections above Structure, so the predicate reads
    ``structure.kind`` through the #101 lookahead (#141).

    Args:
        values: Widget values (with the app's lookahead).

    Returns:
        The needs-a-lattice note under well-mixed, else ``None``.
    """
    return None if _on_a_lattice(values) else _NEEDS_LATTICE_NOTE


def _layout_file_rule(values: Mapping[str, ParamValue]) -> str | None:
    """Live only under lattice AND ``initial_layout = from_file`` (both branches).

    Args:
        values: Widget values (with the app's lookahead).

    Returns:
        The applicable greyed note, or ``None`` when the file is consumed.
    """
    if not _on_a_lattice(values):
        return _NO_GEOMETRY_NOTE
    if values.get("structure.initial_layout") != "from_file":
        return _LAYOUT_FILE_NOTE
    return None


def _interaction_kernel_rule(values: Mapping[str, ParamValue]) -> str | None:
    """The radii's OR-shaped rule: grey under well-mixed OR toggle-off.

    Both branches share it — the async partner draw reads the pair too
    (#137(c)) — and the note names whichever condition actually holds.

    Args:
        values: Widget values (with the app's lookahead).

    Returns:
        The cause-naming note, or ``None`` under lattice with the toggle on.
    """
    if not _on_a_lattice(values):
        return _NEEDS_LATTICE_NOTE
    if not values.get("matching.spatial_interaction"):
        return _TOGGLE_OFF_NOTE
    return None


def _contest_sync(values: Mapping[str, ParamValue]) -> str | None:
    """placement_contest's sync answer: the three-way conjunction (#107).

    Live only under synchronous AND lattice AND ``energy_economy`` — the
    branch supplies "synchronous"; this predicate checks the other two,
    with the note naming the failing cause.

    Args:
        values: Widget values (with the app's lookahead).

    Returns:
        The cause-naming note, or ``None`` when contests can actually occur.
    """
    if not _on_a_lattice(values):
        return _CONTEST_WELL_MIXED_NOTE
    if values.get("dynamics.reproduction_mode") != "energy_economy":
        return _CONTEST_IMITATION_NOTE
    return None


def _contest_async(values: Mapping[str, ParamValue]) -> str | None:
    """placement_contest's async answer: always greyed, note by cause.

    Args:
        values: Widget values (with the app's lookahead).

    Returns:
        The most specific cause: no cells (well-mixed), no placement
        (fixed_n), or no contention (one birth at a time).
    """
    if not _on_a_lattice(values):
        return _CONTEST_WELL_MIXED_NOTE
    if values.get("dynamics.async_population") == "fixed_n":
        return _CONTEST_FIXED_N_NOTE
    return _CONTEST_ASYNC_NOTE


def _matcher_sync(values: Mapping[str, ParamValue]) -> str | None:
    """The matcher's sync answer: greyed while spatial sampling is active.

    Discharges #137(a)'s recorded interim state (toggle on, matcher
    rendering live but unconsulted).

    Args:
        values: Widget values (with the app's lookahead).

    Returns:
        The partners-come-from-the-grid note, or ``None``.
    """
    return _MATCHER_SPATIAL_NOTE if _spatial_sampling_active(values) else None


def _matcher_async(values: Mapping[str, ParamValue]) -> str | None:
    """The matcher's async answer: always greyed (no event-time analogue).

    Args:
        values: Widget values (unused; the signature is the table's).

    Returns:
        Always the async matcher note.
    """
    return _ASYNC_MATCHER_NOTE


def _boundary_order_async(values: Mapping[str, ParamValue]) -> str | None:
    """boundary_order's async answer: always greyed (#131 — never read).

    Args:
        values: Widget values (unused; the signature is the table's).

    Returns:
        Always the no-generation-boundary note.
    """
    return _BOUNDARY_ORDER_ASYNC_NOTE


def _composition_rule(values: Mapping[str, ParamValue]) -> str | None:
    """The composition widgets' rule: greyed while a layout file decides them.

    Reuses :func:`grid_visible` (evolution AND lattice) rather than
    duplicating its logic (#121) — under tournament the layout is ignored
    wholesale and the composition stays fully live.

    Args:
        values: Widget values (with the app's lookahead — ``initial_layout``
            points FORWARD from the Population section).

    Returns:
        The set-by-the-file note under ``from_file``, else ``None``.
    """
    if grid_visible(values) and values.get("structure.initial_layout") == "from_file":
        return _COMPOSITION_FROM_FILE_NOTE
    return None


STRUCTURE_GREYING: dict[str, GreyingRule] = {
    "structure.kind": GreyingRule(sync=_always_live, asynchronous=_always_live),
    "structure.rows": GreyingRule(sync=_geometry_only, asynchronous=_geometry_only),
    "structure.cols": GreyingRule(sync=_geometry_only, asynchronous=_geometry_only),
    "structure.neighbourhood_shape": GreyingRule(sync=_geometry_only, asynchronous=_geometry_only),
    "structure.boundary": GreyingRule(sync=_geometry_only, asynchronous=_geometry_only),
    "structure.initial_layout": GreyingRule(sync=_geometry_only, asynchronous=_geometry_only),
    "structure.layout_file": GreyingRule(sync=_layout_file_rule, asynchronous=_layout_file_rule),
    # The birth pair stays live in EVERY reproduction mode on a lattice —
    # under fixed_n the birth kernel defines the competition set for a
    # freed site, the k that b/c > k counts (#132); greying it would grey
    # the heart of the Moran localisation. The naive reading is backwards.
    "structure.birth_radius": GreyingRule(sync=_geometry_only, asynchronous=_geometry_only),
    "structure.birth_decay": GreyingRule(sync=_geometry_only, asynchronous=_geometry_only),
    "structure.placement_contest": GreyingRule(sync=_contest_sync, asynchronous=_contest_async),
    "structure.interaction_radius": GreyingRule(
        sync=_interaction_kernel_rule, asynchronous=_interaction_kernel_rule
    ),
    "structure.interaction_decay": GreyingRule(
        sync=_interaction_kernel_rule, asynchronous=_interaction_kernel_rule
    ),
    "matching.spatial_interaction": GreyingRule(sync=_needs_lattice, asynchronous=_needs_lattice),
    "matching.matcher": GreyingRule(sync=_matcher_sync, asynchronous=_matcher_async),
    # k stays live ALWAYS (#81/#108: it clamps, and it does the work under
    # spatial sampling) — the row exists so the two-branch obligation is
    # answered explicitly, not by omission. The pre-table round-robin rule
    # in `greying` still applies while spatial sampling is inactive.
    "matching.opponents_per_agent": GreyingRule(sync=_always_live, asynchronous=_always_live),
    "dynamics.boundary_order": GreyingRule(sync=_always_live, asynchronous=_boundary_order_async),
    # Not a registry key: the bespoke Population mix widgets consult the
    # table through this pseudo-key (spec Design 8 consequence 1 / #124's
    # end-state). `population.size` deliberately has NO row — it stays live
    # and validated (spec Design 11).
    "population.composition": GreyingRule(sync=_composition_rule, asynchronous=_composition_rule),
}
"""The M11a greying map (spec Design 11), one row per parameter, both branches.

Consumed by :func:`greying` (sync column) and :func:`_async_greying` (async
column); the tournament wholesale-ignore runs BEFORE either branch via
``IGNORED_IN_TOURNAMENT``, so rows never see tournament values except
through self-guarding predicates (:func:`_spatial_sampling_active`,
:func:`_composition_rule`).
"""


def greying(key: str, values: Mapping[str, ParamValue]) -> tuple[bool, str]:
    """Decide whether a panel widget is greyed out right now, and why.

    The #34 greyed-never-hidden pattern, centralized: a parameter that the
    current widget choices make irrelevant is disabled with an explanatory
    tooltip note — never removed from the panel. The cases:

    * every dynamics parameter, ignored in tournament mode;
    * ``run.tournament_cycles``, ignored in evolution mode;
    * the TIME-MODEL split (M10b): under the asynchronous clock a whole
      family of synchronous machinery is inert (see :func:`_async_greying`)
      and under the synchronous clock the eight async knobs are — this
      check runs before every mode-internal check below, so the
      clock-level note wins;
    * the M11a STRUCTURE TABLE (:data:`STRUCTURE_GREYING`, Phase E #141):
      every ``structure.*`` parameter, the spatial-interaction toggle, the
      matcher, k, the boundary order, and the composition pseudo-key answer
      BOTH clock branches from one predicate table — this function consults
      its sync column, :func:`_async_greying` its async column;
    * ``matching.opponents_per_agent``, ignored under round-robin matching
      (keyed off the matcher widget's current value, not the run mode, #57)
      — but never in async mode, where round-robin itself is inert and the
      partner draws consume k directly, and never while spatial sampling
      is active, where the (greyed) matcher is not consulted and k does
      the work (#108);
    * the COARSE reproduction-mode split (M10a): under ``energy_economy``
      the whole selection + accounting families are inert (differential
      survival IS the selection); under ``imitation`` the eleven economy
      knobs are. This check runs BEFORE the per-rule/per-accounting checks
      below, so the paradigm-level note wins over the rule-level one;
    * each selection rule's parameters, ignored unless that rule is
      selected (keyed off the selection-rule widget, #63);
    * each accounting rule's parameter, ignored unless that accounting is
      selected (keyed off the score-accounting widget, #64).

    The app renders widgets in registry order and passes the values
    gathered so far, topped up with a session-state/default LOOKAHEAD for
    widgets that render later — some M10b dependencies point forward
    (``reproduction_mode`` greys off ``time_model``, which renders after
    it; β greys off ``imitation_overlay``, registered near the end of the
    Dynamics block).

    Args:
        key: The registry key of the widget about to render.
        values: The widget values gathered so far this script run (plus
            the app's lookahead for not-yet-rendered widgets).

    Returns:
        ``(disabled, note)`` — whether to grey the widget out, and the
        tooltip line explaining why (empty when enabled).
    """
    tournament = values.get("run.mode") == "tournament"
    if key == "run.tournament_cycles" and not tournament:
        return True, "NOTE: only used in tournament mode — ignored right now."
    if key in IGNORED_IN_TOURNAMENT and tournament:
        return True, (
            "NOTE: this parameter exists but is IGNORED in tournament mode — "
            "nothing evolves there (see the run-mode help)."
        )
    asynchronous = not tournament and values.get("dynamics.time_model") == "asynchronous"
    if asynchronous:
        return _async_greying(key, values)
    if key in _ASYNC_KNOBS:
        return True, (
            "NOTE: only read under the ASYNCHRONOUS time model — IGNORED on "
            "the synchronous (generational) clock (see the time-model help)."
        )
    # The M11a structure table's SYNC column (Phase E, #141). Safe to consult
    # even under tournament: structure keys returned above via
    # IGNORED_IN_TOURNAMENT, and the remaining rows self-guard on the mode.
    rule = STRUCTURE_GREYING.get(key)
    if rule is not None:
        table_note = rule.sync(values)
        if table_note is not None:
            return True, table_note
    if (
        key == "matching.opponents_per_agent"
        and values.get("matching.matcher") == "round_robin"
        # Under active spatial sampling the (greyed) matcher is not
        # consulted and k does the work (#108) — round-robin must not
        # grey it then.
        and not _spatial_sampling_active(values)
    ):
        return True, (
            "NOTE: this parameter exists but is IGNORED under round-robin "
            "matching — every pair plays once anyway. Switch the matching "
            "scheme to 'random_k' to use it."
        )
    reproduction = values.get("dynamics.reproduction_mode")
    if key in _IMITATION_PARAMS and reproduction == "energy_economy":
        return True, (
            "NOTE: this parameter exists but is IGNORED in the energy economy "
            "— nobody copies anyone; differential survival IS the selection."
        )
    if key in _ECONOMY_PARAMS and reproduction == "imitation":
        return True, (
            "NOTE: this parameter is only read in the energy economy — "
            "IGNORED under imitation dynamics."
        )
    rule = values.get("dynamics.selection_rule")
    if key in _RULE_PARAMS and rule is not None and rule != _RULE_PARAMS[key]:
        return True, (
            f"NOTE: this parameter is only read by the {_RULE_PARAMS[key]!r} "
            "selection rule — IGNORED under the currently selected rule."
        )
    accounting = values.get("dynamics.score_accounting")
    if key in _ACCOUNTING_PARAMS and accounting not in (None, _ACCOUNTING_PARAMS[key]):
        return True, (
            f"NOTE: this parameter is only read by the {_ACCOUNTING_PARAMS[key]!r} "
            "score accounting — IGNORED under the currently selected choice."
        )
    return False, ""


def _async_greying(key: str, values: Mapping[str, ParamValue]) -> tuple[bool, str]:
    """The asynchronous-clock arm of :func:`greying` (M10b spec's map).

    Consults the M11a structure table's async column first (Phase E #141)
    — the matcher's always-greyed answer lives there now, and every
    ``structure.*`` parameter has a defined async answer, even where it is
    "greyed, because async never reads it". Then the M10b rules: under
    event time the generational machinery is inert wholesale
    (``reproduction_mode`` — the async paradigm is chosen by
    ``async_population`` instead — plus the SelectionRule family and score
    accounting; each focal event draws its own partners, consuming
    ``opponents_per_agent`` directly). Within async:
    the Moran knobs apply only under ``fixed_n``, the mixture weights only
    under ``moran_rule = random``, the economy demography knobs only under
    ``variable_n``, and β only when the imitation overlay is on — the
    carve-out that closes the Phase C authoring gap (an async config built
    from widgets could not previously reach β at all).

    Args:
        key: The registry key of the widget about to render.
        values: The widget values (with the app's lookahead — see
            :func:`greying`).

    Returns:
        ``(disabled, note)`` — as :func:`greying`.
    """
    # The M11a structure table's ASYNC column (Phase E, #141) — including
    # the matcher, whose always-greyed answer moved here from an inline
    # check so both of its branch answers live in the one table.
    rule = STRUCTURE_GREYING.get(key)
    if rule is not None:
        table_note = rule.asynchronous(values)
        if table_note is not None:
            return True, table_note
    if key == "dynamics.reproduction_mode":
        return True, (
            "NOTE: IGNORED under the asynchronous time model — the async "
            "paradigm is chosen by 'Async population' instead (variable_n "
            "= the energy economy in event time; fixed_n = Moran)."
        )
    if key in _ASYNC_INERT:
        return True, (
            "NOTE: IGNORED under the asynchronous time model — selection "
            "and score accounting are generational machinery; async "
            "selection happens through births, deaths, and (optionally) "
            "the imitation overlay."
        )
    if key == "dynamics.selection_beta":
        if values.get("dynamics.imitation_overlay"):
            return False, ""
        return True, (
            "NOTE: under the asynchronous time model this is read only by "
            "the imitation overlay — switch 'Imitation overlay' on to use "
            "it (it is the same selection intensity, on a match score gap)."
        )
    population = values.get("dynamics.async_population")
    if key in _FIXED_N_PARAMS and population != "fixed_n":
        return True, (
            "NOTE: Moran machinery — only read when 'Async population' is "
            "fixed_n. IGNORED under variable_n, where births and deaths "
            "come from the energy economy."
        )
    if key in _MORAN_WEIGHTS and (
        population != "fixed_n" or values.get("dynamics.moran_rule") != "random"
    ):
        return True, (
            "NOTE: only read when 'Moran rule' is 'random' (under fixed_n) "
            "— the weights mix birth-death and death-birth per event."
        )
    if key in _VARIABLE_N_ONLY and population == "fixed_n":
        return True, (
            "NOTE: only read under variable_n — fixed_n has no threshold "
            "births, carrying capacity, or age/insolvency deaths; the "
            "Moran replacement is its only demography."
        )
    if key == "output.recording_cadence_m" and (
        values.get("output.recording_cadence") != "every_m_events"
    ):
        return True, (
            "NOTE: only read when the recording cadence is "
            "'every_m_events' — IGNORED under the other cadences."
        )
    return False, ""


def panel_specs() -> tuple[ParameterSpec, ...]:
    """Return the specs the generated parameter panel renders.

    Everything in the Parameter Registry except strategy parameters
    (``strategy.*``), which the app renders in its own per-strategy
    expander, and ``population.composition``, which has no spec (it is a
    structural section, rendered bespoke).

    Returns:
        Specs in registration (= display) order.
    """
    return tuple(spec for spec in all_specs() if not spec.key.startswith("strategy."))


def widget_values_from_config(config: ExperimentConfig) -> dict[str, ParamValue]:
    """Flatten a config into registry-keyed widget values.

    The inverse of :func:`build_config` for every scalar parameter —
    used to load a scenario into the parameter panel.

    Args:
        config: Any validated experiment config (e.g. a scenario's).

    Returns:
        Registry key → value for every registry-backed field
        (composition and strategy_params are separate — see
        ``config.population.composition`` / ``config.strategy_params``).
    """
    models = [
        config,
        config.game,
        config.matching,
        config.match,
        config.population,
        config.structure,
        config.dynamics,
    ]
    values: dict[str, ParamValue] = {}
    for model in models:
        for field, key in type(model)._registry_keys.items():
            values[key] = getattr(model, field)
    # The two derived defaults (M10a): a validated config always holds the
    # RESOLVED plain numbers (hard rule 8), so "auto" is not stored. The
    # loss-free inverse: a stored value that equals what the auto rule
    # would produce is presented as auto (None) — re-assembling the widget
    # values resolves it straight back to the same number, so the round
    # trip is exact, and the auto widgets load unchecked as expected.
    if values["dynamics.initial_energy"] == resolve_initial_energy(
        None,
        values["dynamics.offspring_stake"],  # type: ignore[arg-type]
    ):
        values["dynamics.initial_energy"] = None
    if values["dynamics.senescence_factor"] == resolve_senescence_factor(
        None,
        values["dynamics.base_hazard"],  # type: ignore[arg-type]
        values["dynamics.max_age"],  # type: ignore[arg-type]
    ):
        values["dynamics.senescence_factor"] = None
    # Same loss-free inverse for the M11a lattice dimensions: a stored pair
    # that equals the most-square auto result is presented as auto (blank).
    if (values["structure.rows"], values["structure.cols"]) == resolve_lattice_dimensions(
        None,
        None,
        values["population.size"],  # type: ignore[arg-type]
    ):
        values["structure.rows"] = None
        values["structure.cols"] = None
    return values


def default_widget_values() -> dict[str, ParamValue]:
    """Return registry defaults for every panel parameter ("Custom" start).

    Returns:
        Registry key → default value.
    """
    return {spec.key: spec.default for spec in panel_specs()}


def default_composition(size: int, names: Sequence[str]) -> dict[str, int]:
    """Split a population size evenly across strategies ("Custom" start).

    The Parameter Registry has no composition default (an experiment must
    say what it starts with), so the UI picks the most neutral one: an even
    split, remainder going to the earliest names (DECISIONS #40).

    Args:
        size: Total number of agents to distribute.
        names: Strategy machine names, in display order.

    Returns:
        Name → count, always summing to ``size`` (some counts may be 0
        when there are more strategies than agents).
    """
    base, remainder = divmod(size, len(names))
    return {name: base + (1 if i < remainder else 0) for i, name in enumerate(names)}


def build_config(
    values: Mapping[str, ParamValue],
    composition: Mapping[str, int],
    strategy_params: Mapping[str, Mapping[str, ParamValue]] | None = None,
) -> ExperimentConfig:
    """Assemble widget state into a validated experiment config.

    Args:
        values: Registry key → widget value for every scalar parameter.
        composition: Strategy machine name → agent count from the mix
            widgets; zero counts are dropped here (configs require every
            listed strategy to have at least one agent).
        strategy_params: Optional per-strategy parameter overrides.

    Returns:
        The validated config.

    Raises:
        pydantic.ValidationError: If any value is out of range, the mix
            doesn't sum to the population size, and so on — with the
            registry's plain-language messages.
    """
    data: dict[str, object] = {section: {} for section in _SECTIONS}
    for key, value in values.items():
        prefix, field = key.split(".", maxsplit=1)
        if prefix == "run":
            data[field] = value
        else:
            data[prefix][field] = value  # type: ignore[index]
    data["population"]["composition"] = {  # type: ignore[index]
        name: count for name, count in composition.items() if count > 0
    }
    if strategy_params:
        data["strategy_params"] = {
            name: dict(params) for name, params in strategy_params.items() if params
        }
    return ExperimentConfig.model_validate(data)


def grid_visible(values: Mapping[str, ParamValue]) -> bool:
    """The grid's visibility predicate: evolution mode on a lattice.

    A NAMED predicate rather than an inline conditional, so Phase E can fold
    it into the greying/visibility predicate table unchanged (spec Design
    11). Deliberately independent of ``reproduction_mode`` and
    ``time_model``: every scenario the later phases validate by eye is a
    non-imitation configuration (the flagship and the drifting frontier are
    synchronous economy runs; `donation_game_threshold` is asynchronous),
    so a grid gated to any reproduction or clock choice would make V4-V6
    unwatchable. Tournament mode stays out: nothing is born and nothing
    dies there, so space has nothing to do (DESIGN §2.12).

    Args:
        values: Widget values keyed by registry key (plus ``run.mode``).

    Returns:
        True exactly when the founding grid should render.
    """
    return values.get("run.mode") == "evolution" and values.get("structure.kind") == "lattice"


GRID_PREVIEW_SECTIONS = ("population", "structure")
"""The config sections the founding-grid preview reads (plus mode and seed).

This tuple is the fix for a concrete defect (DECISIONS #121): the preview
once validated the ENTIRE panel, so any cross-section rule in sections the
grid never reads — K >= N is checked exactly under `energy_economy` and
async `variable_n`, and nowhere else — could hide it. The founding
arrangement is a pure function of (mode, seed, population, structure); the
preview must depend on exactly that and nothing more.
"""


def grid_preview_config(
    values: Mapping[str, ParamValue], composition: Mapping[str, int]
) -> ExperimentConfig:
    """Assemble the minimal config the founding-grid preview needs.

    Everything outside :data:`GRID_PREVIEW_SECTIONS` (plus the seed) is left
    at registry defaults, so a validation problem elsewhere in the panel — a
    carrying capacity below the population, an async k too large — can
    never take the grid down with it. Strategy parameters are omitted on
    the same reasoning: the deal reads strategy NAMES and counts, never
    their tunables, so they cannot change the picture.

    Args:
        values: Widget values keyed by registry key.
        composition: Strategy machine name → agent count.

    Returns:
        A validated config whose founding arrangement is identical to the
        full run's (same mode, seed, population, and structure).

    Raises:
        pydantic.ValidationError: Only for problems the grid genuinely has —
            a mix that does not sum to the population size, incoherent
            lattice dimensions, ``from_file`` without a file.
    """
    minimal: dict[str, ParamValue] = {
        key: value
        for key, value in values.items()
        if key.split(".", maxsplit=1)[0] in GRID_PREVIEW_SECTIONS
    }
    minimal["run.mode"] = values.get("run.mode", "evolution")
    if "run.seed" in values:
        minimal["run.seed"] = values["run.seed"]
    return build_config(minimal, composition)


def layout_population_mismatch(
    layout_file: str, size: int, composition: Mapping[str, int]
) -> tuple[int, dict[str, int]] | None:
    """Compare a layout file's implied population against the Population widgets.

    A layout file names a strategy per cell, so its cell counts ARE a
    population: a size (the occupied-cell count) and a mixture (spec
    Design 8 — the file wins on composition). This helper reads that
    population off the file so the app can offer to fill the Population
    section in from it, instead of making the user retype numbers the file
    already states (DECISIONS #124).

    Args:
        layout_file: The configured value — a bare template name or a path,
            resolved by the #122 rule.
        size: The current ``population.size`` widget value.
        composition: The current mix widgets' values (zeros included; they
            are ignored for the comparison).

    Returns:
        ``None`` when the file and the widgets agree exactly, else the
        file's ``(size, counts)`` — what the widgets would need to hold.

    Raises:
        FileNotFoundError: If the file cannot be found.
        ValueError: If the file is malformed, names unregistered strategies
            (reported with line and cell), or places fewer than two agents —
            below the smallest legal population, so no widget state could
            ever match it.
    """
    from pdsim.core.layouts import read_layout_file, resolve_layout_path, validate_layout_file
    from pdsim.core.strategies import all_strategy_names

    layout = read_layout_file(resolve_layout_path(layout_file))
    # Self-consistent dimensions and size make this run ONLY the token
    # check — the full grid/size validation belongs to founding, where the
    # run's resolved rows and cols are in play.
    validate_layout_file(
        layout,
        rows=layout.rows,
        cols=layout.cols,
        known_strategies=frozenset(all_strategy_names()),
        population_size=layout.occupied_count,
    )
    if layout.occupied_count < 2:
        raise ValueError(
            f"Layout file places {layout.occupied_count} agent(s); a run needs at "
            "least 2. Name more cells, or choose a generated layout."
        )
    file_counts = layout.strategy_counts()
    widget_counts = {name: count for name, count in composition.items() if count > 0}
    if layout.occupied_count == size and file_counts == widget_counts:
        return None
    return layout.occupied_count, file_counts


def layout_file_dimension_mismatch(values: Mapping[str, ParamValue]) -> str | None:
    """Compare a layout file's header dimensions against the resolved grid.

    The panel-side twin of the #126 config validator's dimension check, so
    the problem shows BESIDE the widgets before Run is ever pressed — the
    same pre-Run visibility the #124 composition warning already has.

    Args:
        values: Widget values keyed by registry key (``structure.rows`` /
            ``cols`` may be blank — they resolve exactly as the run would
            resolve them).

    Returns:
        A message naming both sizes and the fixes, or ``None`` when the
        dimensions agree, no file is named, or the file cannot be read (the
        panel already warns about unreadable files separately).
    """
    from pdsim.core.layouts import read_layout_file, resolve_layout_path

    layout_file = values.get("structure.layout_file")
    size = values.get("population.size")
    if not layout_file or not isinstance(size, int):
        return None
    try:
        layout = read_layout_file(resolve_layout_path(str(layout_file)))
    except (FileNotFoundError, ValueError):
        return None
    rows, cols = resolve_lattice_dimensions(
        values.get("structure.rows"),  # type: ignore[arg-type]
        values.get("structure.cols"),  # type: ignore[arg-type]
        size,
    )
    if (layout.rows, layout.cols) == (rows, cols):
        return None
    return (
        f"The layout file is {layout.rows}x{layout.cols} but this run's grid "
        f"resolves to {rows}x{cols}. Set Lattice rows to {layout.rows} and "
        f"columns to {layout.cols}, or edit the file's header to match the grid."
    )


def final_occupancy(timeseries: RunTimeseries) -> dict[int, str] | None:
    """The last recorded period's site → strategy mapping, if the data has one.

    The results browser's presence test for its Founding | Final grid
    selector (#136's deferred half; DECISIONS #146). PRESENCE-driven, never
    mode-driven (#100(b)/#120): the decision reads the recorded per-agent
    snapshots, not the config. An imitation run persists no snapshots
    (#116 — nothing moves after founding), and a schema ≤ 4 folder's
    snapshots carry no site ids; both answer ``None`` here, so the browser's
    founding-only view stands exactly as it was for them.

    Args:
        timeseries: The recorded run's accumulated series.

    Returns:
        Site id → strategy machine name from the LAST recorded period, when
        any recorded snapshot carries a real site id; ``None`` otherwise.
        The mapping can be EMPTY — a run that ended extinct has a final
        occupancy of nobody, and an empty world is the honest picture of it.
    """
    has_sites = any(
        snapshot.site_id is not None for period in timeseries.agent_snapshots for snapshot in period
    )
    if not has_sites:
        return None
    return {
        snapshot.site_id: snapshot.strategy
        for snapshot in timeseries.agent_snapshots[-1]
        if snapshot.site_id is not None
    }


def collect_strategy_params(
    values: Mapping[str, ParamValue],
) -> dict[str, dict[str, ParamValue]]:
    """Turn strategy-parameter widget values into a config override mapping.

    Only values that differ from their registry defaults are included, so
    an untouched panel produces a config with no ``strategy_params``
    section at all — the defaults stay implicit (DECISIONS #41).

    Args:
        values: ``strategy.<name>.<param>`` registry key → widget value.

    Returns:
        Strategy name → {param: value} for the changed values only.
    """
    overrides: dict[str, dict[str, ParamValue]] = {}
    for spec in all_specs():
        if not spec.key.startswith("strategy."):
            continue
        value = values.get(spec.key, spec.default)
        if value != spec.default:
            _, name, param = spec.key.split(".", maxsplit=2)
            overrides.setdefault(name, {})[param] = value
    return overrides


def validation_messages(error: ValidationError) -> list[str]:
    """Extract the plain-language messages from a pydantic error.

    The registry writes user-facing messages already; this strips
    pydantic's framing so ``st.error`` shows clean sentences.

    Args:
        error: The exception raised by config validation.

    Returns:
        One human-readable message per failed check.
    """
    messages = []
    for item in error.errors():
        message = item["msg"]
        for prefix in ("Value error, ", "Assertion error, "):
            message = message.removeprefix(prefix)
        messages.append(message)
    return messages


def should_redraw(now: float, last_redraw: float, delay: float, floor: float) -> bool:
    """Decide whether the live view redraws its charts on this period.

    The live loop accumulates data on EVERY period event, but redrawing is
    throttled to wall clock (DECISIONS #94): each redraw tears down and
    re-mounts every chart component in the browser (Streamlit requires a
    fresh element key per redraw within one script run), and fast runs —
    async event time especially — can finish periods far quicker than the
    browser can paint them, leaving the charts blank between flashes.
    Skipping a redraw leaves the PREVIOUS frame on screen untouched, which
    is exactly the smooth behavior wanted; the skipped periods' data all
    appear at the next redraw.

    Args:
        now: The current ``time.monotonic()`` reading.
        last_redraw: The ``time.monotonic()`` reading taken right after the
            previous redraw (0.0 before the first — so the first period
            always draws).
        delay: The playback-delay slider value in seconds; a larger delay
            means the owner wants a slower slideshow, so it stretches the
            throttle window too.
        floor: The minimum seconds between redraws regardless of the
            slider (the app's ``LIVE_REDRAW_MIN_SECONDS``).

    Returns:
        True when at least ``max(delay, floor)`` seconds have passed since
        the previous redraw.
    """
    return now - last_redraw >= max(delay, floor)
