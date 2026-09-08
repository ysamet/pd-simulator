"""The Streamlit app: scenario picker, generated parameter panel, live charts.

Launch from the repo root (with the venv active):

    streamlit run pdsim/ui/app.py

This module is deliberately thin (DECISIONS #38): presentation and Streamlit
calls only. It does exactly three things with the platform — builds an
``ExperimentConfig`` from widget state, consumes the
``engine.run(config, granularity)`` event stream one period per script pass
(M11b Phase E3), and (the Sweep tab, M9.5b)
authors a ``SweepSpec`` and spawns the headless sweep CLI — via the testable
logic in :mod:`pdsim.ui.helpers`, :mod:`pdsim.ui.sweep_helpers`,
:mod:`pdsim.core.timeseries`, and :mod:`pdsim.viz.charts`.
The parameter panel is *generated* from the
Parameter Registry, so every widget's tooltip is the registry's
novice-friendly description (hard rule 3): a parameter added to the registry
appears here with zero UI edits.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

import pandas as pd
import streamlit as st
from plotly.graph_objects import Figure
from pydantic import ValidationError
from streamlit.delta_generator import DeltaGenerator
from streamlit.runtime.scriptrunner import StopException

from pdsim.config.experiment import (
    ExperimentConfig,
    effective_neighbour_count,
    payoff_additivity,
    resolve_carrying_capacity,
    resolve_lattice_dimensions,
)
from pdsim.config.registry import ParameterSpec, ParamValue
from pdsim.config.scenarios import all_scenarios
from pdsim.core import engine, layouts
from pdsim.core.strategies import all_strategies, all_strategy_names
from pdsim.core.timeseries import RunTimeseries
from pdsim.io.results import RunRecorder, delete_run, load_run, rename_run, sync_index
from pdsim.sweep.metrics import all_metrics
from pdsim.sweep.spec import (
    SweepSpec,
    expand,
    resolve_composition,
    sweep_spec_yaml,
    sweep_validation_messages,
)
from pdsim.ui import advisories, economy_helpers, helpers, painter_helpers, sweep_helpers
from pdsim.ui.economy_helpers import (
    ASYNC_EXPECTED_MATCHES_NOTE,
    ECONOMY_HELP,
    expected_matches_per_agent,
)
from pdsim.ui.helpers import ADVANCED_FOLD_HELP, LiveRun, _spatial_sampling_active
from pdsim.ui.painter_helpers import LayoutDraft
from pdsim.viz import charts

CUSTOM = "Custom"
"""The dropdown entry that starts from registry defaults (DECISIONS #36/#40)."""

TOURNAMENT_HIDDEN_SECTIONS = ("Structure", "Movement", "Dynamics")
"""The sections the tournament tab does not render (#158's total fork; #178 R3).

Hiding is per SECTION, never per key — a renderer decision layered ABOVE
the greying table, which is untouched underneath (#178 R10): the
tournament-greyed Matching keys (`spatial_interaction`,
`encounter_mode`) still render greyed with their existing notes, because
Matching as a section stays. The hidden sections' widget VALUES are
preserved across the switch and still feed the gathered config (#178
R1/R2), so a config recorded under tournament carries what the widgets
held, not registry defaults.
"""

STRUCTURE_HELP = {
    "site_count": (
        "How many cells the world has. Every cell holds at most one agent, so this "
        "is the largest population the world could ever hold. It is rows x columns, "
        "using the same arithmetic the run itself uses — so the number here and the "
        "grid you get can never disagree."
    ),
    "occupancy": (
        "How many cells currently hold an agent, and what share of the world that "
        "is. Below 100% the population has room to grow into empty space; at 100% "
        "the world is full and every birth needs somebody to die first."
    ),
    "isolated": (
        "How many agents begin with no occupied neighbouring cell. A scattered "
        "start in a sparsely filled world can strand agents this way. It matters "
        "from the milestone where agents play their neighbours: an agent with no "
        "neighbours plays nobody, earns nothing, and starves — which is the model "
        "being honest about isolation, not a fault."
    ),
    "resolved_dimensions": (
        "The grid the blank dimension boxes resolve to. Blank means automatic "
        "sizing: the most-square rectangle holding exactly the population (a "
        "prime population makes a single line). Computed by the SAME function "
        "the run itself uses, so the number shown here and the grid the run "
        "founds can never disagree."
    ),
    "resolved_capacity": (
        "The carrying capacity a blank K resolves to on this lattice: the site "
        "count — the grid decides. Shown beside the site count so both numbers "
        "are visible at once. Set K below the site count instead to leave "
        "permanent slack — empty ground for the occupied region to drift in."
    ),
    "effective_neighbours": (
        "The number of matches an interior cell actually starts per generation "
        "under spatial interaction: 'Opponents per agent' clamped to the "
        "neighbours REACHABLE within the interaction radius — at the default "
        "radius 1 that is min(k, 8) on a Moore neighbourhood and min(k, 4) on "
        "von Neumann; a larger radius enlarges the reachable set (and a blank "
        "radius reaches the whole grid), so the clamp loosens accordingly. "
        "This is the k the b/c > k cooperation threshold counts. On a "
        "bounded grid, edge and corner cells have fewer neighbours still (a "
        "corner keeps 3 of Moore's 8 at radius 1); a torus has no edges, so "
        "every cell plays exactly this number."
    ),
    "expected_matches": (
        "How many matches an interior agent on a full grid plays per "
        "generation (per generation-equivalent under the asynchronous "
        "clock). Every agent initiates min(k, neighbours) matches and is "
        "drawn into about as many by its neighbours — twice the effective "
        "neighbour count under 'per_initiator'; equal to it under "
        "'per_pair', which plays each pair once. The asynchronous clock is "
        "always per-initiator. Edge agents on a bounded grid and agents "
        "beside empty sites play fewer. The Economy panel's income "
        "arithmetic uses this same figure."
    ),
    "pixel_array": (
        "Whether the grid is currently drawn as ONE image — a pixel array, "
        "each cell one pixel block — instead of as individually bordered, "
        "individually hover-labelled cells. Two things flip it on: past a "
        "few thousand cells (above 2,500 sites here) redrawing every cell "
        "as its own bordered shape makes each refresh crawl; and on a "
        "strongly elongated grid the cells shrink toward the ~3 px floor "
        "long before the site count gets there, where the borders would eat "
        "the cells and the grid would degrade into disconnected dots. "
        "Either way the switch costs nothing you can see at that size: same "
        "colours from the same palette, same layout, just no cell borders. "
        "The large-count case is also the regime where the live view's "
        "wall-clock redraw throttling starts to matter."
    ),
}
"""Inline (?) explanations for the Structure panel's derived readouts (the §12 rule)."""

GAME_HELP = {
    "payoff_additivity": (
        "Whether the four payoffs form a DONATION GAME: cooperating costs the "
        "same amount c whoever the opponent is (T − R = P − S), with a benefit "
        "b = T − P delivered to the partner. Only then do 'b' and 'c' exist as "
        "single numbers, and only then does the b/c > k cooperation threshold "
        "apply. With a non-additive matrix the ratio is AMBIGUOUS rather than "
        "merely inapplicable — two defensible benefits (T − P, R − S) over two "
        "defensible costs (T − R, P − S) give four different readings — so "
        "asking whether b/c clears k is a malformed question there."
    ),
}
"""Inline (?) explanations for the Game panel's derived readouts (the §12 rule)."""

PROGRESS_EVERY = 200
"""Fine-grained events between progress-line refreshes (DECISIONS #39)."""

LIVE_REDRAW_MIN_SECONDS = 0.5
"""Wall-clock floor between live chart REBUILDS (DECISIONS #94, kept by #184).

Streamlit 1.58 folds a plotly figure's spec into its element id
(``plotly_chart`` registers with ``key_as_main_identity=False``), so a chart
whose data changed is a NEW element to the browser whatever key it carries:
the old component is torn down and the new one is blank until plotly has
painted it. Fast runs — async event time especially — can complete periods
faster than that paint, so the live loop rebuilds its figures at most once
per ``max(playback_delay, LIVE_REDRAW_MIN_SECONDS)`` seconds. Since the
per-pass loop (M11b Phase E3) every pass repaints, so between rebuilds a
pass re-emits the figures it built last time UNCHANGED — an identical spec
is an identical element, which the browser leaves exactly as it is. A
finishing or stopped pass, and a pass on which a display toggle flipped,
always rebuild.
"""

LIVE_RUN_KEY = "_live_run"
"""Session-state key of the :class:`~pdsim.ui.helpers.LiveRun` in progress.

App state, not widget state (DECISIONS #184): it is never re-assigned by
``_preserve_hidden_widget_state`` and no widget owns it. Present exactly
while a run is in progress; the finishing or stopping pass moves the
results into ``last_run`` (#44) and removes it.
"""

PAINTER_DRAFT_KEY = "_layout_draft"
"""Session-state key of the Layout painter's :class:`~pdsim.ui.painter_helpers.LayoutDraft`.

App state beside :data:`LIVE_RUN_KEY` (M11b Phase E4, DECISIONS #186 R4):
never re-assigned by ``_preserve_hidden_widget_state`` and owned by no
widget. Absent until the owner starts a grid; kept for the session after.
"""

PAINTER_NOTE_KEY = "_painter_note"
"""Session-state key of a sentence a painter callback stages for the next pass.

A button callback cannot render (it runs before the script), so a failed
seed — a tournament panel, a well-mixed world, an unreadable file — leaves
its explanation here and the painter tab shows it once (#186 R7).
"""

PAINTER_TOO_FINE_NOTE = (
    "This grid is too fine to paint by mouse — its cells would be under 6 pixels "
    "wide, or it has more than 2,500 sites, the same point at which the Run lab "
    "switches the grid to pixel-array rendering. Shrink the grid (fewer rows or "
    "columns), or write the layout file by hand: the grid_templates folder's "
    "README states the format."
)
"""The #186 R3 sentence shown instead of the canvas when `paint_cell_side` is None."""

PAINTER_HELP = {
    "rows": (
        "How many rows the new grid has. Only 'New blank grid' and 'Resize grid' "
        "read this box; loading a file or the Run lab's preview sets it to that "
        "grid's size."
    ),
    "cols": (
        "How many columns the new grid has. Only 'New blank grid' and 'Resize "
        "grid' read this box; loading a file or the Run lab's preview sets it to "
        "that grid's size."
    ),
    "new": (
        "Start an empty grid of the size in the Rows and Columns boxes. Any "
        "unsaved painting on the canvas is replaced — save it first if you want "
        "to keep it."
    ),
    "source": (
        "The layout files currently in the project's grid_templates folder — the "
        "same folder a bare name in the Run lab's 'Layout file' box is looked up "
        "in. Only .txt files are listed; the README there is not a layout."
    ),
    "load": (
        "Read the chosen file onto the canvas so you can edit it. Its strategy "
        "names are checked against the registry first; a file naming an unknown "
        "strategy is refused with the same message the Run lab would give."
    ),
    "confirm_delete": (
        "Tick to enable 'Delete layout file'. Deleting is the one action on this "
        "tab that cannot be undone, so it takes this explicit second step — "
        "exactly as overwriting a file needs 'Replace the existing file'."
    ),
    "delete": (
        "Remove the file chosen under 'Existing layout file' from the "
        "grid_templates folder. Only files inside that folder can be removed, and "
        "the three shipped examples never. Recorded runs are safe: every run "
        "folder carries its own copy of its layout, so a deleted file cannot break "
        "a re-run — at most a Run lab 'Layout file' box still naming it will report "
        "the file missing. If the canvas was saved as this file, the painting "
        "stays and counts as unsaved again."
    ),
    "from_preview": (
        "Copy the Run lab's founding preview onto the canvas: the arrangement the "
        "current panel settings would found at generation 0 (their seed included), "
        "ready to edit. It needs an evolution run on a lattice — a tournament or a "
        "well-mixed world has no grid to copy."
    ),
    "resize": (
        "Apply the Rows and Columns boxes to the grid on the canvas. The top-left "
        "part of the painting is kept cell for cell, new cells start empty, and "
        "cells outside the new size are dropped — which is why this never happens "
        "on its own when the boxes change."
    ),
    "tool": (
        "How a mouse gesture on the canvas chooses cells. 'Draw (drag to paint)': "
        "press the mouse button on a cell and move — every cell the pointer passes "
        "over takes the brush, and the cells are painted all at once when you "
        "release. A perfectly still click paints nothing (the chart treats it as a "
        "click, not a stroke), so nudge the mouse a little as you press to paint a "
        "single cell. 'Rectangle (drag a box)': the cells inside the box you drag. "
        "'Lasso (enclose an area)': the cells inside the shape you draw. The tool "
        "stays selected from stroke to stroke. There is no zoom on a painter, so "
        "there is no pan tool either."
    ),
    "brush": (
        "What a stroke paints: one of the registered strategies, or the eraser, "
        "which empties cells. The colours match the key under the canvas and the "
        "Run lab's charts — one palette everywhere."
    ),
    "canvas": (
        "Paint with the mouse (painted cells are overwritten, not skipped): with "
        "'Draw' press and move over the cells — a tiny nudge paints one cell; with "
        "'Rectangle' drag a box; with 'Lasso' draw around an area. Hover any cell "
        "to read its row, column, and content."
    ),
    "undo": (
        "Restore the cells as they were before the last stroke, fill, or clear. "
        "One level only: the change before that cannot be recovered."
    ),
    "fill": "Paint EVERY cell with the current brush (with the eraser this empties the grid).",
    "clear": "Empty every cell. Undoable like any stroke.",
    "sites": (
        "How many cells the grid has — rows × columns — and so the largest "
        "population this layout could ever hold."
    ),
    "painted": (
        "How many cells currently name a strategy. This IS the population size "
        "the hand-off writes into the Run lab, because a layout file decides both "
        "the arrangement and the mixture (the file wins on composition)."
    ),
    "empty": "How many cells are left empty — room the population can grow into during a run.",
    "saved_as": (
        "The file the canvas currently matches. 'not saved yet' before the first "
        "save; 'unsaved changes' once the painting differs from its file; the file "
        "name while the two agree — the state the hand-off button needs."
    ),
    "file_name": (
        "A bare file name for the painting, saved into the grid_templates folder "
        "('.txt' is added when you give no extension). The two shipped examples "
        "and the shipped 20 × 20 sample cannot be overwritten; anything else "
        "needs the 'Replace the existing file' box to be replaced."
    ),
    "replace": (
        "Allow 'Save layout' to overwrite a file of the same name that already "
        "exists in the grid_templates folder."
    ),
    "save": (
        "Write the painting as a layout file — the header, then one line per grid "
        "row, a strategy machine name or '.' per cell — exactly the format the "
        "Run lab reads and the grid_templates README describes."
    ),
    "handoff": (
        "Make this saved painting the Run lab's founding layout: the run mode is "
        "set to evolution, the world to a lattice of this grid's size, the Initial "
        "layout to 'from_file' naming this file, and the Population section is "
        "filled in from the painting's counts — the same one-click populate the "
        "Structure section offers. Available only while the canvas matches a saved "
        "file with at least two agents, because a run's config must reference a "
        "file and a run needs at least two agents."
    ),
}
"""Inline (?) explanations for the Layout painter's widgets and readouts (the §12 rule)."""

GRANULARITY_RUNNING_NOTE = (
    "NOTE: greyed while a run is in progress — the engine binds the "
    "granularity when a run starts (DECISIONS #35), so a new choice applies "
    "from the next Run."
)
"""The granularity selectbox's mid-run greying note (#183 R1; #34's pattern)."""

DISCARD_NOTE = "The interrupted run was not recorded — its partial folder was cleaned up."
"""The one interrupted-recording sentence (DECISIONS #53/#55, kept by #184)."""

RUNS_DIR = Path(os.environ.get("PDSIM_RUNS_DIR", "runs"))
"""Where recordings go; the env override exists for tests (DECISIONS #49)."""

SWEEPS_DIR = Path(os.environ.get("PDSIM_SWEEPS_DIR", "sweeps"))
"""Where the Sweep tab launches sweeps into (mirrors RUNS_DIR, DECISIONS #72)."""

GEN_EQUIV_AXIS_NOTE = (
    "⏱ Event-time run: the x-axis is **generation-equivalents** — each event "
    "advances the clock by 1/N(t), so one unit is one population's worth of "
    "events, matching a synchronous generation in both time and per-agent "
    "interaction budget (spec Design 5). Recording points need not be evenly "
    "spaced: under the per-event and every-m-events cadences the charts plot "
    "against the clock, not the period count."
)
"""The generation-equivalent axis explainer, shown for async runs (M10b)."""

st.set_page_config(page_title="pdsim — Evolutionary Prisoner's Dilemma", layout="wide")


def _help_text(spec: ParameterSpec, note: str = "") -> str:
    """Assemble a widget tooltip from a spec's registry documentation.

    Args:
        spec: The parameter being rendered.
        note: Optional extra line (e.g. the ignored-in-this-mode warning).

    Returns:
        The registry description, learn-more note, and extra note.
    """
    parts = [spec.description]
    if spec.learn_more:
        parts.append(f"Learn more: {spec.learn_more}")
    if note:
        parts.append(note)
    return "\n\n".join(parts)


def _widget(spec: ParameterSpec, *, disabled: bool = False, note: str = "") -> ParamValue:
    """Render the right widget for a ParameterSpec and return its value.

    The mapping (DECISIONS #38): bool → checkbox, choice → selectbox,
    int/float → number_input with the spec's bounds, nullable → a checkbox
    plus a number input ("Limit ...?" for nullable ints, whose None means
    unlimited; "Set ... manually?" for nullable floats, whose None means
    auto — the M10a derived defaults). Widget keys are the registry keys,
    so scenario loading can address every widget by parameter.

    Args:
        spec: The parameter to render.
        disabled: Grey the widget out (mode-awareness), never hide it.
        note: Extra tooltip line explaining why it is greyed out.

    Returns:
        The widget's current value (``None`` for an unlimited/auto
        nullable).
    """
    help_text = _help_text(spec, note)
    if spec.kind == "str":
        # Free text (M11a): a nullable string reads blank as "unset", so it
        # needs no companion checkbox — unlike the nullable number kinds,
        # where a blank box would be indistinguishable from zero.
        typed = st.text_input(spec.label, key=spec.key, help=help_text, disabled=disabled)
        stripped = str(typed).strip()
        if stripped:
            return stripped
        return None if spec.nullable else ""
    if spec.nullable and spec.kind == "int":
        limited = st.checkbox(
            f"Limit {spec.label.lower()}?",
            key=f"{spec.key}#limit",
            help=help_text,
            disabled=disabled,
        )
        value = st.number_input(
            spec.label,
            min_value=int(spec.minimum or 0),
            step=1,
            key=f"{spec.key}#value",
            help=help_text,
            disabled=disabled or not limited,
        )
        return int(value) if limited else None
    if spec.nullable:  # nullable float: None means "auto" (M10a)
        manual = st.checkbox(
            f"Set {spec.label.lower()} manually?",
            key=f"{spec.key}#limit",
            help=help_text,
            disabled=disabled,
        )
        value = st.number_input(
            spec.label,
            min_value=None if spec.minimum is None else float(spec.minimum),
            step=0.01,
            format="%.4g",
            key=f"{spec.key}#value",
            help=help_text,
            disabled=disabled or not manual,
        )
        return float(value) if manual else None
    if spec.kind == "bool":
        return bool(st.checkbox(spec.label, key=spec.key, help=help_text, disabled=disabled))
    if spec.kind == "choice":
        return st.selectbox(
            spec.label,
            options=list(spec.choices or ()),
            key=spec.key,
            help=help_text,
            disabled=disabled,
        )
    if spec.kind == "int":
        value = st.number_input(
            spec.label,
            min_value=None if spec.minimum is None else int(spec.minimum),
            max_value=None if spec.maximum is None else int(spec.maximum),
            step=1,
            key=spec.key,
            help=help_text,
            disabled=disabled,
        )
        return int(value)
    value = st.number_input(
        spec.label,
        min_value=None if spec.minimum is None else float(spec.minimum),
        max_value=None if spec.maximum is None else float(spec.maximum),
        step=0.01,
        format="%.4g",
        key=spec.key,
        help=help_text,
        disabled=disabled,
    )
    return float(value)


def _load_state(
    values: dict[str, ParamValue],
    composition: dict[str, int],
    strategy_params: dict[str, dict[str, ParamValue]],
) -> None:
    """Write a config's values into widget session state (scenario load).

    Runs before any widget is instantiated in this script run, so every
    widget picks the loaded value up as its state.

    Args:
        values: Registry key → value for the scalar parameters.
        composition: Strategy name → agent count for the mix widgets.
        strategy_params: Per-strategy overrides for the expander widgets.
    """
    for spec in helpers.panel_specs():
        value = values.get(spec.key, spec.default)
        if spec.kind == "str":
            # A text box holds "" for unset, never None — Streamlit rejects a
            # None value for text_input.
            st.session_state[spec.key] = "" if value is None else str(value)
        elif spec.nullable and spec.kind == "int":
            st.session_state[f"{spec.key}#limit"] = value is not None
            st.session_state[f"{spec.key}#value"] = (
                int(value) if value is not None else int(spec.minimum or 1)
            )
        elif spec.nullable:  # nullable float: None means "auto" (M10a)
            st.session_state[f"{spec.key}#limit"] = value is not None
            st.session_state[f"{spec.key}#value"] = (
                float(value) if value is not None else float(spec.minimum or 0.0)
            )
        else:
            st.session_state[spec.key] = value
    for info in all_strategies():
        st.session_state[f"composition.{info.name}"] = int(composition.get(info.name, 0))
        for spec in info.params:
            param = spec.key.rsplit(".", maxsplit=1)[-1]
            st.session_state[spec.key] = strategy_params.get(info.name, {}).get(param, spec.default)
    # The advisory baseline (#176 R5): retain what this load wrote, so A2
    # can detect "changed since load" as a pure function of (current,
    # loaded) values. Every load — scenario, Custom, recorded config —
    # passes through here, so loading clears the advisories by
    # construction. Display-side state only; nothing reads it but the
    # advisory rules.
    st.session_state["_loaded_values"] = {
        spec.key: values.get(spec.key, spec.default) for spec in helpers.panel_specs()
    }


def _scenario_area() -> None:
    """Render the scenario dropdown and load its config on change.

    A scenario is a starting point, not a lock (DECISIONS #40): its values
    are written into widget state exactly once, when the selection changes;
    edits afterwards are never fought, and the dropdown keeps showing the
    scenario's name.
    """
    scenarios = {info.display_name: info for info in all_scenarios()}
    choice = st.selectbox(
        "Scenario",
        options=[CUSTOM, *scenarios],
        index=1,
        key="scenario_choice",
        help=(
            "Curated, ready-to-run experiments — pick one, read its question, press "
            "Run. Every parameter stays editable: a scenario is a starting point. "
            "'Custom' starts from the documented defaults."
        ),
    )
    if st.session_state.get("_loaded_scenario") != choice:
        if choice == CUSTOM:
            values = helpers.default_widget_values()
            names = [info.name for info in all_strategies()]
            composition = helpers.default_composition(int(values["population.size"]), names)
            _load_state(values, composition, {})
        else:
            config = scenarios[choice].config
            _load_state(
                helpers.widget_values_from_config(config),
                dict(config.population.composition),
                config.strategy_params,
            )
        st.session_state["_loaded_scenario"] = choice
    if choice != CUSTOM:
        info = scenarios[choice]
        st.markdown(info.description)
        st.caption(f"**Things to try:** {info.things_to_try}")


def _advisory_captions(surface: str, values: dict[str, ParamValue]) -> None:
    """Render whatever advisories fire at one surface (M11b Phase D).

    Presentation only (the #38 split): the rules live in
    :mod:`pdsim.ui.advisories` — one predicate table, evaluated there —
    and this helper just paints what fired: ``st.warning`` for a caution,
    ``st.info`` for an info.

    Args:
        surface: A widget's registry key, or the Economy panel's
            pseudo-surface (:data:`advisories.ECONOMY_PANEL_SURFACE`).
        values: The widget values gathered so far this script run (plus
            the app's lookahead).
    """
    loaded = st.session_state.get("_loaded_values", {})
    for advisory in advisories.advisories_for_surface(surface, values, loaded):
        if advisory.severity == "caution":
            st.warning(advisory.message)
        else:
            st.info(advisory.message)


def _preserve_hidden_widget_state(specs: dict[str, ParameterSpec]) -> None:
    """Keep every panel key's session state alive across mode switches (#178 R1).

    Streamlit deletes a widget's session-state entry at the end of any
    script run in which that widget was not rendered — exactly what
    happens to the Structure, Movement, and Dynamics widgets while the
    tournament tab hides their sections (#178 R3). Re-assigning a key
    before any widget is instantiated marks it as app state for this
    run, which interrupts that cleanup (Streamlit's documented
    preservation idiom, verified in this project's Task 0 probe), so an
    evolution → tournament → evolution round trip hands every widget its
    old value back. The re-assignment never fights a user edit: the
    frontend's new value is applied at widget instantiation, after this
    runs.

    Args:
        specs: The panel's specs by registry key.
    """
    keys: list[str] = []
    for spec in specs.values():
        if spec.nullable and spec.kind in ("int", "float"):
            # Nullable numbers render as a checkbox/value widget PAIR
            # under derived keys (DECISIONS #38); both carry state.
            keys.extend((f"{spec.key}#limit", f"{spec.key}#value"))
        else:
            keys.append(spec.key)
    for key in keys:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def _panel_widget(
    spec: ParameterSpec, lookahead: dict[str, ParamValue], values: dict[str, ParamValue]
) -> None:
    """Render ONE panel widget with its greying and inline advisories.

    Factored out of the panel loop in M11b Phase E2 (#181 R4) so the
    everyday widgets and the "Advanced settings" fold share one code path
    — a folded widget greys, explains itself, and carries its inline
    advisory exactly as an everyday one does. Writes the widget's value
    into ``values`` under its registry key.

    Args:
        spec: The parameter to render.
        lookahead: The app's forward map of every panel key to what its
            widget WILL return this run (see :func:`_parameter_panel`).
        values: The values gathered so far this script run; this widget's
            value is added to it.
    """
    # Widgets render in registry order, so most values a widget's greying
    # keys off (run.mode, matching.matcher, dynamics.reproduction_mode)
    # are already gathered when it renders; the lookahead covers the
    # forward M10b dependencies (helpers.greying, DECISIONS #34).
    disabled, note = helpers.greying(spec.key, {**lookahead, **values})
    values[spec.key] = _widget(spec, disabled=disabled, note=note)
    # The advisory seam (M11b Phase D): inline warnings anchored at this
    # widget — A2 at its nine trigger keys, A3 beside the
    # spatial-interaction toggle.
    _advisory_captions(spec.key, {**lookahead, **values})


def _panel_lookahead(specs: Mapping[str, ParameterSpec]) -> dict[str, ParamValue]:
    """Map EVERY panel key to what its widget WILL return this script run.

    Forward-looking greying (M10b): some dependencies point at widgets that
    render LATER in registry order (reproduction_mode greys off time_model;
    β greys off the imitation overlay). The lookahead reads each widget's
    session-state value, or the registry default before the first
    interaction; complete coverage since E1, because the tournament tab
    gathers its hidden sections from it (#178 R2). Values actually gathered
    in a run always win over it (``{**lookahead, **values}``).

    Factored out of :func:`_parameter_panel` in M11b Phase E4 (#186 R7) so
    the Layout painter's "Start from the Run lab's founding preview" reads
    the panel's forward values through the SAME function — one lookahead,
    behaviour byte-identical, pinned by the existing suite.

    Args:
        specs: The panel's specs by registry key.

    Returns:
        Registry key → the value its widget will return this run.
    """
    lookahead: dict[str, ParamValue] = {
        key: st.session_state.get(key, spec.default)
        for key, spec in specs.items()
        if not spec.nullable
    }
    # Nullable numbers render as a checkbox/value widget PAIR, so their
    # forward value is reconstructed from that pair's session state (blank
    # until the box is ticked). The Structure readouts need one of them —
    # carrying capacity — before the Dynamics section renders (#106's
    # both-numbers guard, M11a Phase E).
    for key, spec in specs.items():
        if spec.nullable and spec.kind in ("int", "float"):
            limited = st.session_state.get(f"{key}#limit", spec.default is not None)
            lookahead[key] = st.session_state.get(f"{key}#value", spec.default) if limited else None
        elif spec.nullable and spec.kind == "str":
            # A nullable text box holds "" for unset (never None), so its
            # forward value is reconstructed the way the widget returns it
            # — blank means None. Completing the lookahead over EVERY
            # panel key is what lets the tournament tab gather hidden
            # sections from it (#178 R2).
            raw = st.session_state.get(key, spec.default)
            text = str(raw).strip() if raw is not None else ""
            lookahead[key] = text if text else None
    return lookahead


def _parameter_panel() -> tuple[dict[str, ParamValue], dict[str, int], dict[str, dict]]:
    """Render the whole generated panel; return everything a run needs.

    Returns:
        The scalar values by registry key, the composition counts, and the
        collected strategy-parameter overrides.
    """
    specs = {spec.key: spec for spec in helpers.panel_specs()}
    _preserve_hidden_widget_state(specs)
    values: dict[str, ParamValue] = {}

    # The mode strip (#178 C2): run.mode's widget IS the panel's tab
    # strip — a segmented control keyed by the registry key, so loading,
    # gathering, and the #101 lookahead read it exactly as before.
    # required=True: clicking the selected tab does nothing, so the
    # value can never deselect to None mid-session. st.tabs is NOT used
    # — run.mode must stay the single source of truth under its own key.
    mode_spec = specs["run.mode"]
    mode = st.segmented_control(
        mode_spec.label,
        options=list(mode_spec.choices or ()),
        selection_mode="single",
        required=True,
        key="run.mode",
        help=_help_text(mode_spec),
    )
    if mode is None:  # unreachable once a load has written state; belt and braces
        mode = mode_spec.default
    values["run.mode"] = mode
    col_seed, col_cycles = st.columns(2)
    with col_seed:
        values["run.seed"] = _widget(specs["run.seed"])
    with col_cycles:
        disabled, note = helpers.greying("run.tournament_cycles", values)
        values["run.tournament_cycles"] = _widget(
            specs["run.tournament_cycles"], disabled=disabled, note=note
        )

    sections: dict[str, list[ParameterSpec]] = {}
    for spec in specs.values():
        if not spec.key.startswith("run."):
            sections.setdefault(spec.section, []).append(spec)

    # Forward-looking greying (M10b): the lookahead maps EVERY panel key to
    # what its widget WILL return this run (see _panel_lookahead — factored
    # out in M11b Phase E4 so the Layout painter reads the same forward
    # values). Values actually gathered this run always win.
    lookahead = _panel_lookahead(specs)

    tournament = mode == "tournament"
    composition: dict[str, int] = {}
    for section, section_specs in sections.items():
        merged = {**lookahead, **values}
        if tournament and section in TOURNAMENT_HIDDEN_SECTIONS:
            # The #158 total fork (#178 R3): the tournament tab skips
            # these sections wholesale and gathers their PRESERVED
            # session-state values from the lookahead instead (#178
            # R1/R2) — never registry defaults — so recorded-config →
            # load → run stays a faithful round trip in both directions.
            for spec in section_specs:
                values[spec.key] = lookahead[spec.key]
            continue
        # Collapse-with-summary (#158; #178 R4/R5): an inert Structure or
        # Movement section renders collapsed under a cause-naming summary
        # label; opening it shows the greyed widgets with their notes
        # (grey-never-hide, one level down). The predicate reads the SAME
        # table column as the greying inside, so the two cannot drift.
        branch = "asynchronous" if merged.get("dynamics.time_model") == "asynchronous" else "sync"
        if helpers.section_inert(section, merged, branch):
            label = helpers.section_summary_label(section, merged, branch)
            expanded = False
        else:
            label = section
            expanded = section in ("Population", "Dynamics")
        # The stable key is load-bearing (#180): without one, an expander's
        # identity is generated from its other parameters — the label
        # included — so the inert/live label swap minted a NEW element that
        # mounted at its default and collapsed the pane under the user
        # mid-edit. With the key, identity survives the relabel and the
        # frontend keeps the pane exactly as the user left it; `expanded`
        # still applies at every genuine mount (fresh session, mode-tab
        # switch), so inert sections still START collapsed.
        with st.expander(label, expanded=expanded, key=f"section_{section}"):
            # The disclosure axis (#158/#167/#181): a section's advanced
            # keys render AFTER its everyday widgets, inside a collapsed
            # "Advanced settings" fold, through the SAME per-widget call —
            # greying, (?) text, and inline advisories included — so the
            # fold never forks the widget-rendering code.
            folded = helpers.advanced_keys(section)
            everyday = [spec for spec in section_specs if spec.key not in folded]
            columns = st.columns(2)
            for i, spec in enumerate(everyday):
                with columns[i % 2]:
                    _panel_widget(spec, lookahead, values)
            if folded:
                # The header reads the SAME merged mapping the greying
                # reads (#181 R3/R4), so the two cannot disagree within a
                # paint. The stable key is load-bearing, exactly as for
                # the section expanders (#180): the label changes on every
                # non-default edit inside the fold, and without the key
                # that relabel would mint a new element that mounts
                # collapsed — snapping the pane shut under the user
                # mid-edit. A keyed expander registers no session state
                # (#181 R5; Task 0 probe), so nothing joins the keep-alive
                # list and the fold starts collapsed at every genuine
                # mount. Streamlit 1.58's expander takes no `help=`, so the
                # fold's one explanation renders as its first line instead.
                fold_label = helpers.advanced_fold_label(section, {**lookahead, **values})
                with st.expander(fold_label, expanded=False, key=f"advanced_{section}"):
                    st.caption(ADVANCED_FOLD_HELP)
                    fold_columns = st.columns(2)
                    for i, spec in enumerate(spec for spec in section_specs if spec.key in folded):
                        with fold_columns[i % 2]:
                            _panel_widget(spec, lookahead, values)
            if section == "Game" and values.get("run.mode") == "evolution":
                # The §12 payoff-additivity readout (#111) — whether the
                # b/c > k threshold is even a well-formed question for
                # these four payoffs. Tournament mode has no births or
                # deaths for the threshold to govern, so it stays out.
                _additivity_readout(values)
            if section == "Population":
                # The composition widgets are bespoke (no registry specs),
                # so they consult the greying table through a pseudo-key:
                # under `from_file` the layout file decides the mixture and
                # the mix widgets grey (spec Design 8; #124's end-state).
                # The lookahead matters here — `initial_layout` renders in
                # the LATER Structure section.
                comp_disabled, comp_note = helpers.greying(
                    "population.composition", {**lookahead, **values}
                )
                composition = _composition_panel(disabled=comp_disabled, note=comp_note)
            if section == "Structure" and helpers.grid_visible({**lookahead, **values}):
                # The Population section renders before Structure (registry
                # order), so the composition is already gathered here — which
                # is what lets the preview be live: change the layout and the
                # arrangement redraws without running anything. The lookahead
                # supplies what has not rendered yet, the SEED above all: a
                # preview built on the default seed would show a different
                # arrangement from the one the run founds.
                _structure_panel({**lookahead, **values}, composition)
            if section == "Dynamics":
                # The Population section renders before Dynamics (registry
                # order), so the composition is already gathered here. The
                # render gate is economy_active — the #176 R4 predicate —
                # not the raw reproduction-mode widget (#178 R9, closing
                # #177(f1)): an async variable_n run with a stranded
                # imitation widget now calibrates as loaded, and the
                # inactive corners state their cause instead of the panel
                # silently vanishing.
                if economy_helpers.economy_active({**lookahead, **values}):
                    _economy_panel(values, composition)
                elif values.get("run.mode") == "evolution":
                    _economy_summary_area({**lookahead, **values})

    with st.expander("Per-strategy parameters"):
        st.caption(
            "Overrides for strategies with tunable parameters. They apply even to "
            "strategies outside the mix — mutation can still introduce them mid-run."
        )
        strategy_values: dict[str, ParamValue] = {}
        for info in all_strategies():
            for spec in info.params:
                strategy_values[spec.key] = _widget(spec)
    strategy_params = helpers.collect_strategy_params(strategy_values)

    return values, composition, strategy_params


def _composition_panel(disabled: bool = False, note: str = "") -> dict[str, int]:
    """Render the per-strategy count inputs for the initial population mix.

    Args:
        disabled: Grey every mix widget out (under ``from_file`` the layout
            file decides the mixture — the greying table's composition row,
            #34's greyed-never-hidden). The #124 Populate button still
            writes their session state: greying blocks USER edits only.
        note: The greyed-state explanation, shown as a visible caption and
            appended to each widget's tooltip.

    Returns:
        Strategy machine name → count (zeros allowed here; dropped at
        config assembly).
    """
    st.markdown("**Initial population mix** (counts must sum to the population size)")
    if disabled and note:
        st.caption(note)
    counts: dict[str, int] = {}
    columns = st.columns(4)
    for i, info in enumerate(all_strategies()):
        with columns[i % 4]:
            counts[info.name] = int(
                st.number_input(
                    info.display_name,
                    min_value=0,
                    step=1,
                    key=f"composition.{info.name}",
                    help=f"{info.description}\n\n{note}" if note else info.description,
                    disabled=disabled,
                )
            )
    return counts


def _additivity_readout(values: dict[str, ParamValue]) -> None:
    """Render the §12 payoff-additivity readout inside the Game expander (#111).

    Presentation only (the #38 split): the arithmetic is
    :func:`pdsim.config.experiment.payoff_additivity`, a pure function of
    the four payoff values on the paint-time resolver pattern, so this
    number and any future validator arithmetic cannot drift.

    Args:
        values: The widget values gathered so far this script run (the Game
            section has already rendered, so all four payoffs are present).
    """
    payoffs = tuple(
        values.get(key)
        for key in (
            "game.payoff_temptation",
            "game.payoff_reward",
            "game.payoff_punishment",
            "game.payoff_sucker",
        )
    )
    if not all(isinstance(p, int | float) for p in payoffs):
        return
    t, r, p, s = (float(x) for x in payoffs)  # type: ignore[arg-type]
    report = payoff_additivity(t, r, p, s)
    if report.additive and report.ratio is not None:
        st.metric(
            "Payoff additivity",
            f"b/c = {report.ratio:g}",
            help=GAME_HELP["payoff_additivity"],
        )
        st.caption(f"additive: b = {report.benefit:g}, c = {report.cost:g}, b/c = {report.ratio:g}")
    elif report.additive:
        st.metric(
            "Payoff additivity",
            f"b = {report.benefit:g}, c = 0",
            help=GAME_HELP["payoff_additivity"],
        )
        st.caption(
            f"additive with b = {report.benefit:g} and c = 0 — cooperating "
            "costs nothing, so the b/c > k threshold is trivially cleared."
        )
    else:
        st.metric("Payoff additivity", "not additive", help=GAME_HELP["payoff_additivity"])
        st.caption(
            "not additive — the b/c > k threshold does not apply: cooperating "
            f"costs a different amount against a cooperator (T − R = {t - r:g}) "
            f"than against a defector (P − S = {p - s:g})."
        )


def _economy_summary_area(values: dict[str, ParamValue]) -> None:
    """Render the Economy panel's collapsed-with-summary state (#178 R9).

    Shown inside the Dynamics expander exactly when
    :func:`economy_helpers.economy_active` is false on the evolution tab:
    a cause-naming summary whose toggle reveals a one-line explanation —
    no readout, because the calibration would describe a metabolic
    filter that is not running. A toggle, not a nested expander: this is
    the panel's existing in-Dynamics fold idiom (the concepts toggle),
    and Streamlit's docs advise against nesting expanders even though
    1.58 no longer forbids it.

    Args:
        values: The widget values gathered so far this script run (plus
            the app's lookahead).
    """
    st.markdown("---")
    label, explanation = economy_helpers.economy_inactive_summary(values)
    if st.toggle(label, key="economy_inactive_summary", help=explanation):
        st.caption(explanation)


def _economy_panel(values: dict[str, ParamValue], composition: dict[str, int]) -> None:
    """Render the Economy calibration readout inside the Dynamics expander.

    Presentation only (the #38 split): all arithmetic lives in the
    Streamlit-free :func:`pdsim.ui.economy_helpers.calibration_report`, and
    every inline (?) text comes from the single ``ECONOMY_HELP`` source so
    app wording and docs cannot drift. Verdict line first, then the window,
    then the conditional readouts (M10a spec Task 11).

    Args:
        values: The widget values gathered so far this script run (every
            section before Dynamics has already rendered).
        composition: The population mix gathered by the Population section.
    """
    st.markdown("---")
    st.markdown("**Economy calibration** — where the survival window lies for these settings.")
    try:
        config = helpers.build_config(values, composition)
    except ValidationError as error:
        st.info("The calibration readout appears once the configuration is valid:")
        for message in helpers.validation_messages(error):
            st.caption(f"• {message}")
        return
    report = economy_helpers.calibration_report(config)

    # The verdict line first (the spec's order), then the window.
    st.markdown(
        f"A cooperator nets **{report.cooperator_net:+g}** per generation; "
        f"a defector nets **{report.defector_net:+g}** per generation."
    )
    col_matches, col_c, col_d, col_window = st.columns(4)
    col_matches.metric(
        "Matches per agent",
        f"{report.expected_matches:g}",
        help=ECONOMY_HELP["expected_matches"],
    )
    col_c.metric("All-C income", f"{report.all_c_income:g}", help=ECONOMY_HELP["income"])
    col_d.metric("All-D income", f"{report.all_d_income:g}", help=ECONOMY_HELP["income"])
    col_window.metric(
        "Survival window",
        f"{report.all_d_income:g} < cost < {report.all_c_income:g}",
        help=ECONOMY_HELP["window"],
    )
    if report.window_verdict == "inside":
        st.markdown(
            f"Total per-generation cost **{report.total_cost:g}** is **inside** the "
            "window — cooperators can pay the bill, defectors cannot: the "
            "metabolic filter is on."
        )
    elif report.window_verdict == "above":
        st.markdown(
            f"Total per-generation cost **{report.total_cost:g}** is **above** the "
            "window — even an all-cooperator cannot pay the bill; expect the "
            "population to die out."
        )
    else:
        st.markdown(
            f"Total per-generation cost **{report.total_cost:g}** is **below** the "
            "window — even defectors profit; the metabolic filter is switched off."
        )
    # Advisory A1 (M11b Phase D, #176 R1/R4): beside the calibration
    # readout, from the same predicate table as the inline advisories.
    _advisory_captions(advisories.ECONOMY_PANEL_SURFACE, values)

    if report.escape_velocity is not None:
        st.metric(
            "Escape velocity e*",
            f"{report.escape_velocity:g}",
            help=ECONOMY_HELP["escape_velocity"],
        )
    if report.senescence_factor is not None:
        col_factor, col_eff, col_theta, col_kids = st.columns(4)
        col_factor.metric(
            "Senescence factor (resolved)",
            f"{report.senescence_factor:.4f}",
            help=(
                "The factor actually used this run — a blank 'auto' input "
                "resolves to the value that reaches certain death exactly at "
                "the max age."
            ),
        )
        if report.effective_max_age is not None:
            col_eff.metric(
                "Effective max age",
                f"{report.effective_max_age:.1f}",
                help=ECONOMY_HELP["effective_max_age"],
            )
        if report.generations_to_threshold is not None:
            col_theta.metric(
                "Generations to θ",
                f"{report.generations_to_threshold:.1f}",
                help=ECONOMY_HELP["generations_to_threshold"],
            )
        if report.expected_offspring is not None:
            col_kids.metric(
                "Expected offspring",
                f"{report.expected_offspring:g}",
                help=ECONOMY_HELP["generations_to_threshold"],
            )
    if report.effective_max_age_note:
        st.warning(report.effective_max_age_note)
    if report.memory_note:
        st.info(report.memory_note)
    st.caption(report.regime_note)
    # A toggle, not an expander — this panel lives inside the Dynamics
    # expander, and Streamlit's docs advise against nesting expanders
    # (1.58 no longer forbids it — E1's Task 0 probe — but the advice
    # stands and this is the house fold idiom).
    if st.toggle(
        "Explain the economy concepts (?)",
        key="economy_concepts",
        help="Energy, admission at capacity, estate destruction, passport ids.",
    ):
        st.markdown(f"**Energy (a stock, not a score)** — {ECONOMY_HELP['energy']}")
        st.markdown(f"**Admission at capacity** — {ECONOMY_HELP['admission']}")
        st.markdown(f"**Estate destruction on death** — {ECONOMY_HELP['estate_destruction']}")
        st.markdown(f"**Passport ids and lineage** — {ECONOMY_HELP['passport_id']}")


def _grid_width(rows: int, cols: int) -> str:
    """The ``st.plotly_chart`` width mode for a grid figure.

    When the ≈ 3 px cell floor binds, :func:`charts.grid_chart` gives the
    figure an explicit canvas size; stretching it back into the column would
    shrink the cells below the floor again, so the figure keeps its own
    (possibly scrolling) size instead (DECISIONS #145).

    Args:
        rows: Grid row count.
        cols: Grid column count.

    Returns:
        ``"content"`` when the floor binds, else ``"stretch"``.
    """
    return "content" if charts.floored_canvas(rows, cols) else "stretch"


def _grid_area(
    config: ExperimentConfig,
    key_prefix: str,
    config_dir: Path | None = None,
    resolved_capacity: int | None = None,
) -> None:
    """Draw the lattice and its derived readouts, if the run has one.

    Presentation only (the #38 split): the arrangement itself comes from
    :func:`pdsim.core.layouts.founding_view`, a pure function of the config
    and the seed, so what the panel shows and what the engine founds cannot
    drift apart.

    This is the FOUNDING arrangement — the panel preview shows generation 0,
    and the results browser shows it under its "Founding" view (its "Final"
    view draws the last recorded period's occupancy instead, #146). During a
    live economy run the run area additionally renders the CURRENT occupancy
    from the latest snapshot (Phase C: births claim sites and deaths free
    them, so the picture genuinely moves — the snapshot is the render state,
    Design 10).

    Args:
        config: The run's configuration.
        key_prefix: Distinguishes chart elements rendered by different app
            areas in the same script run.
        config_dir: Folder to resolve a relative layout file against (a
            recorded run keeps its own copy).
        resolved_capacity: The K a BLANK carrying-capacity widget resolves
            to, shown beside the site count (#106's both-numbers guard) —
            the panel passes it at paint time; the results browser and run
            area pass nothing (their configs store the resolved number).
    """
    try:
        view = layouts.founding_view(config, config_dir)
    except (FileNotFoundError, ValueError) as error:
        st.warning(f"The grid cannot be drawn: {error}")
        return
    if view is None:
        return
    st.plotly_chart(
        charts.grid_chart(view.rows, view.cols, view.placements),
        width=_grid_width(view.rows, view.cols),
        key=f"{key_prefix}_grid",
    )
    if resolved_capacity is None:
        col_sites, col_occupied, col_isolated, col_pixels = st.columns(4)
    else:
        col_sites, col_capacity, col_occupied, col_isolated, col_pixels = st.columns(5)
        col_capacity.metric(
            "Capacity K (resolved)",
            f"auto → {resolved_capacity}",
            help=STRUCTURE_HELP["resolved_capacity"],
        )
    col_sites.metric("Sites", f"{view.site_count}", help=STRUCTURE_HELP["site_count"])
    col_occupied.metric(
        "Occupied",
        f"{view.occupied} ({view.occupancy_fraction:.0%})",
        help=STRUCTURE_HELP["occupancy"],
    )
    col_isolated.metric("Isolated at founding", f"{view.isolated}", help=STRUCTURE_HELP["isolated"])
    # The ninth §12 derived readout (DECISIONS #145): the renderer's own
    # switch, read from the same predicate the renderer consults.
    col_pixels.metric(
        "Pixel-array rendering",
        "on" if charts.pixel_array_active(view.rows, view.cols) else "off",
        help=STRUCTURE_HELP["pixel_array"],
    )
    if view.isolated:
        st.caption(
            f"{view.isolated} agent(s) start with no occupied neighbour. Once local "
            "interaction arrives such an agent plays nobody and earns nothing — "
            "correct, but worth knowing you chose it."
        )


def _populate_from_layout_file(size: int, counts: dict[str, int]) -> None:
    """Write a layout file's implied population into the Population widgets.

    A button callback: Streamlit runs it at the START of the next script
    run, before any widget is instantiated, which is the one moment widget
    session state may legally be written — the same pre-render window the
    scenario loader uses (DECISIONS #124).

    Args:
        size: The file's occupied-cell count → ``population.size``.
        counts: The file's per-strategy counts → the mix widgets (registered
            strategies absent from the file are set to 0).
    """
    st.session_state["population.size"] = int(size)
    for info in all_strategies():
        st.session_state[f"composition.{info.name}"] = int(counts.get(info.name, 0))


def _structure_readouts(values: dict[str, ParamValue]) -> None:
    """Render the paint-time derived readouts above the grid preview (§12).

    Each is a pure resolver call with possibly-blank inputs (spec Design 11
    extension 2) — the SAME functions the validator runs, so the numbers
    shown and the numbers the run uses can never drift:

    * the grid a blank rows/cols pair resolves to ("auto → 10 × 10");
    * the effective neighbour count under spatial interaction — the k the
      b/c > k threshold compares against, shown while the toggle is on.

    Args:
        values: The widget values gathered so far this script run (the
            Structure section has already rendered), plus the lookahead.
    """
    size = values.get("population.size")
    if not isinstance(size, int) or size < 1:
        return
    metrics: list[tuple[str, str, str]] = []
    rows = values.get("structure.rows")
    cols = values.get("structure.cols")
    if rows is None or cols is None:
        resolved_rows, resolved_cols = resolve_lattice_dimensions(
            rows if isinstance(rows, int) else None,
            cols if isinstance(cols, int) else None,
            size,
        )
        metrics.append(
            (
                "Grid (resolved)",
                f"auto → {resolved_rows} × {resolved_cols}",
                STRUCTURE_HELP["resolved_dimensions"],
            )
        )
    if values.get("matching.spatial_interaction"):
        shape = values.get("structure.neighbourhood_shape")
        boundary = values.get("structure.boundary")
        k = values.get("matching.opponents_per_agent")
        # The interaction radius is radius-aware input since M11b Phase D
        # (#176 R6); None is a legitimate value (blank = unlimited reach).
        radius = values.get("structure.interaction_radius")
        if (
            isinstance(shape, str)
            and isinstance(boundary, str)
            and isinstance(k, int)
            and (radius is None or isinstance(radius, int))
        ):
            resolved_rows, resolved_cols = resolve_lattice_dimensions(
                rows if isinstance(rows, int) else None,
                cols if isinstance(cols, int) else None,
                size,
            )
            metrics.append(
                (
                    "Effective neighbours (k)",
                    str(
                        effective_neighbour_count(
                            shape, boundary, k, radius, resolved_rows * resolved_cols
                        )
                    ),
                    STRUCTURE_HELP["effective_neighbours"],
                )
            )
            # The matches figure (M11b Phase E2, #181 R7 — the #179(d)
            # carry-in): it belongs to structure and matching, not to the
            # economy, so it renders here wherever the ENGINE's spatial
            # gate holds — evolution AND lattice AND toggle, the same
            # predicate advisory A3 uses (#176 R7), reused not re-derived
            # — which also covers configurations the Economy panel never
            # calibrates (fixed_n, synchronous imitation on a lattice).
            # Same arithmetic as the calibration report and A1 (one
            # source), same radius/site-count pass-throughs as the
            # neighbours readout above (#177(e)). Absent, not greyed, when
            # the gate is false: a readout, not a widget.
            encounter_mode = values.get("matching.encounter_mode")
            time_model = values.get("dynamics.time_model")
            if (
                _spatial_sampling_active(values)
                and isinstance(encounter_mode, str)
                and isinstance(time_model, str)
            ):
                matches_help = STRUCTURE_HELP["expected_matches"]
                if time_model == "asynchronous":
                    # The (?) cannot contradict the number (#154's rule):
                    # under the async clock the figure is an EXPECTED one,
                    # stated in the same sentence the Economy (?) uses.
                    matches_help = f"{matches_help} {ASYNC_EXPECTED_MATCHES_NOTE}"
                metrics.append(
                    (
                        "Expected matches per agent per generation",
                        str(
                            expected_matches_per_agent(
                                shape,
                                boundary,
                                k,
                                radius,
                                resolved_rows * resolved_cols,
                                encounter_mode,
                                time_model,
                            )
                        ),
                        matches_help,
                    )
                )
    if not metrics:
        return
    columns = st.columns(max(len(metrics), 2))
    for column, (label, value, help_text) in zip(columns, metrics, strict=False):
        column.metric(label, value, help=help_text)


def _resolved_capacity_if_blank(values: dict[str, ParamValue]) -> int | None:
    """The K a blank carrying-capacity widget resolves to on this lattice.

    #106's both-numbers guard: whenever K is blank on a lattice, the panel
    shows the resolved K beside the site count. The K widget renders in the
    LATER Dynamics section, so its state arrives through the lookahead.

    Args:
        values: The widget values gathered so far, plus the lookahead.

    Returns:
        The resolved K, or ``None`` when K is set explicitly (the widget
        already shows the number) or the inputs cannot resolve yet.
    """
    if values.get("dynamics.carrying_capacity") is not None:
        return None
    size = values.get("population.size")
    if not isinstance(size, int) or size < 1:
        return None
    rows = values.get("structure.rows")
    cols = values.get("structure.cols")
    resolved_rows, resolved_cols = resolve_lattice_dimensions(
        rows if isinstance(rows, int) else None,
        cols if isinstance(cols, int) else None,
        size,
    )
    return resolve_carrying_capacity(None, resolved_rows * resolved_cols)


def _structure_panel(values: dict[str, ParamValue], composition: dict[str, int]) -> None:
    """Preview the founding arrangement from the panel's current values.

    The preview is built from ONLY the sections the founding arrangement
    reads — mode, seed, population, structure — with everything else at
    registry defaults (DECISIONS #121). Validating the whole panel here
    once hid the grid whenever an UNRELATED section failed: K >= N is
    checked exactly under `energy_economy` and async `variable_n`, so
    flipping either switch with a default K below N made the grid vanish.

    Under ``from_file`` the layout file IS a population — a size and a
    mixture — so when it disagrees with the Population section the panel
    says so and offers to fill the widgets in from the file, rather than
    leaving the user to retype numbers the file already states (#124).

    Args:
        values: Registry key → widget value gathered so far this script run.
        composition: Strategy machine name → agent count.
    """
    _structure_readouts(values)
    if values.get("structure.initial_layout") == "from_file":
        names = ", ".join(f"`{info.name}`" for info in all_strategies())
        st.caption(
            "Layout-file tokens are strategy machine names, spelled exactly as "
            f"registered: {names}. Write `.` for an empty cell. A bare filename "
            "is looked up in the `grid_templates/` folder, which ships with "
            "commented examples."
        )
        layout_file = values.get("structure.layout_file")
        if layout_file:
            try:
                mismatch = helpers.layout_population_mismatch(
                    str(layout_file), int(values.get("population.size") or 0), composition
                )
            except (FileNotFoundError, ValueError) as error:
                st.warning(f"The grid cannot be drawn: {error}")
                return
            # Dimensions get the same pre-Run visibility as the composition
            # offer (#126): Run is blocked by config validation while either
            # disagreement stands, so say so here, beside the widgets.
            dimension_message = helpers.layout_file_dimension_mismatch(values)
            if dimension_message:
                st.warning(dimension_message)
            if mismatch is not None:
                file_size, file_counts = mismatch
                file_mix = ", ".join(f"{name} {count}" for name, count in file_counts.items())
                st.warning(
                    f"The layout file describes a different population: {file_size} "
                    f"agents ({file_mix}), while the Population section currently "
                    f"says {values.get('population.size')} with a different mix. "
                    "The file decides both the arrangement AND the mixture, so "
                    "either switch Initial layout away from 'from_file' to keep "
                    "the Population section as typed, or fill it in from the file:"
                )
                st.button(
                    "Populate the Population section from the file",
                    key="populate_from_layout_file",
                    on_click=_populate_from_layout_file,
                    args=(file_size, file_counts),
                )
            if dimension_message or mismatch is not None:
                return
    try:
        config = helpers.grid_preview_config(values, composition)
    except ValidationError as error:
        # Only genuinely grid-relevant problems remain (a mix that does not
        # sum to N, incoherent dimensions, a missing layout file) — so name
        # the actual problem instead of guessing at one.
        messages = helpers.validation_messages(error)
        st.caption(f"The grid preview is waiting on: {messages[0]}")
        return
    _grid_area(config, key_prefix="panel", resolved_capacity=_resolved_capacity_if_blank(values))


def _request_stop() -> None:
    """Flag the running event loop to stop (button callback)."""
    st.session_state["stop_requested"] = True


def _economy_placeholders() -> tuple[DeltaGenerator, DeltaGenerator, DeltaGenerator]:
    """Create the three economy chart placeholders (M10a house layout).

    Returns:
        Placeholders for the population and mean-energy charts (a column
        pair) and the mean-age chart (full width below them). They stay
        blank for runs without per-agent snapshots.
    """
    col_pop, col_energy = st.columns(2)
    return col_pop.empty(), col_energy.empty(), st.empty()


def _build_figures(
    timeseries: RunTimeseries,
    per_round: bool,
    whole_game: bool,
    carrying_capacity: float | None = None,
    economy: bool = False,
) -> dict[str, Figure]:
    """Build the mode-appropriate chart figures, keyed by their role.

    The pure half of the old ``_draw_charts`` (M11b Phase E3): building is
    separated from painting so the live loop can cache what it built and
    re-emit it unchanged on passes inside the #94 throttle window.

    Args:
        timeseries: The run's accumulated series.
        per_round: Score view for the mean chart (DECISIONS #44).
        whole_game: Time scope for the mean chart (DECISIONS #45).
        carrying_capacity: K for the population chart's dashed reference
            line (config-derived; ``None`` outside the energy economy).
        economy: Whether to build the population / mean-energy / mean-age
            trio (M10a) — only built when the run carries per-agent
            snapshots (imitation runs and pre-schema-3 recordings have
            none — DECISIONS #65 again).

    Returns:
        ``left`` (composition or tournament totals), ``right`` (the mean
        chart), ``coop`` when the run has cooperation data, and the
        ``population``/``energy``/``age`` trio when asked for and present;
        empty before the first period.
    """
    figures: dict[str, Figure] = {}
    if not timeseries.periods:
        return figures
    if timeseries.mode == "tournament":
        figures["left"] = charts.total_score_chart(timeseries)
    else:
        figures["left"] = charts.composition_chart(timeseries)
    figures["right"] = charts.mean_score_chart(
        timeseries, per_round=per_round, whole_game=whole_game
    )
    if timeseries.cooperation_overall:
        figures["coop"] = charts.cooperation_chart(timeseries)
    if economy and any(timeseries.agent_snapshots):
        figures["population"] = charts.population_chart(timeseries, carrying_capacity)
        figures["energy"] = charts.mean_energy_chart(timeseries)
        figures["age"] = charts.mean_age_chart(timeseries)
    return figures


def _paint_figures(
    figures: Mapping[str, object],
    left: DeltaGenerator,
    right: DeltaGenerator,
    cooperation: DeltaGenerator,
    draw_id: int,
    key_prefix: str = "chart",
    economy: tuple[DeltaGenerator, DeltaGenerator, DeltaGenerator] | None = None,
) -> None:
    """Paint built figures into their placeholders (the Streamlit half).

    Args:
        figures: The figures by role, as :func:`_build_figures` returns
            them (typed loosely because the live holder stores them as
            plain objects).
        left: Placeholder for composition (evolution) / totals (tournament).
        right: Placeholder for the mean-score chart.
        cooperation: Full-width placeholder for the cooperation-rate chart
            (M9b); left untouched when the run carries no cooperation data.
        draw_id: Distinguishes repeated paints WITHIN one script run
            (Streamlit forbids duplicate element keys in a run); a pass of
            the live loop paints once, so it uses 0.
        key_prefix: Distinguishes chart elements rendered by different app
            areas in the same script run (live view vs results browser).
        economy: Placeholders for the population / mean-energy / mean-age
            charts (M10a); left untouched when no such figures were built.
    """
    if "left" in figures:
        left.plotly_chart(figures["left"], width="stretch", key=f"{key_prefix}_left_{draw_id}")
    if "right" in figures:
        right.plotly_chart(figures["right"], width="stretch", key=f"{key_prefix}_right_{draw_id}")
    if "coop" in figures:
        cooperation.plotly_chart(
            figures["coop"], width="stretch", key=f"{key_prefix}_coop_{draw_id}"
        )
    if economy is not None and "population" in figures:
        population, energy, age = economy
        population.plotly_chart(
            figures["population"], width="stretch", key=f"{key_prefix}_population_{draw_id}"
        )
        energy.plotly_chart(
            figures["energy"], width="stretch", key=f"{key_prefix}_energy_{draw_id}"
        )
        age.plotly_chart(figures["age"], width="stretch", key=f"{key_prefix}_age_{draw_id}")


def _draw_charts(
    timeseries: RunTimeseries,
    left: DeltaGenerator,
    right: DeltaGenerator,
    cooperation: DeltaGenerator,
    draw_id: int,
    per_round: bool,
    whole_game: bool,
    key_prefix: str = "chart",
    economy: tuple[DeltaGenerator, DeltaGenerator, DeltaGenerator] | None = None,
    carrying_capacity: float | None = None,
) -> None:
    """Build and paint the mode-appropriate charts in one step.

    The post-run view and the results browser use this; the live loop
    builds and paints separately so it can cache figures between passes.

    Args:
        timeseries: The run's accumulated series.
        left: Placeholder for composition (evolution) / totals (tournament).
        right: Placeholder for the mean-score chart.
        cooperation: Full-width placeholder for the cooperation-rate chart.
        draw_id: Element-key suffix — see :func:`_paint_figures`.
        per_round: Score view for the mean chart (DECISIONS #44).
        whole_game: Time scope for the mean chart (DECISIONS #45).
        key_prefix: Distinguishes chart elements rendered by different app
            areas in the same script run.
        economy: Placeholders for the M10a economy trio, if any.
        carrying_capacity: K for the population chart's reference line.
    """
    _paint_figures(
        _build_figures(timeseries, per_round, whole_game, carrying_capacity, economy is not None),
        left,
        right,
        cooperation,
        draw_id,
        key_prefix,
        economy,
    )


def _final_summary_area(timeseries: RunTimeseries) -> None:
    """Render the final summary table plus the cooperation pair matrix.

    Args:
        timeseries: A finished run's series (``final`` must be set).
    """
    if timeseries.final is None:
        return
    st.dataframe(charts.final_summary_rows(timeseries.final), width="stretch")
    pair_rows = charts.cooperation_pair_rows(timeseries)
    if pair_rows:
        st.caption(
            "Cooperation by strategy pair (final period; actor's rate against "
            "that opponent — the M12 in-group/out-group diagnostic in table form)."
        )
        st.dataframe(pair_rows, width="stretch")


def _start_live_run(
    config: ExperimentConfig, granularity: str, record: bool, scenario: str | None
) -> LiveRun:
    """Open a run: the engine generator, the accumulator, and the recorder.

    Nothing is computed yet — the generator runs its first period on the
    first pass (:func:`_live_pass`). The config passed in is the one the
    recorder writes (``config.yaml`` goes to disk right here, #47) and the
    one the engine consumes: FROZEN at the Run click, whatever the panel
    shows afterwards (#183 R4, hard rule 8).

    Args:
        config: The validated ExperimentConfig to run.
        granularity: Finest event level to request — bound NOW, for the
            whole run (DECISIONS #35; #183 R1).
        record: Persist this run to a run folder as it streams (#49).
        scenario: Scenario name for the recording's index row, if any.

    Returns:
        The holder the passes advance, to be kept under ``LIVE_RUN_KEY``.
    """
    recorder = RunRecorder(config, out_dir=RUNS_DIR, scenario=scenario) if record else None
    return LiveRun(
        events=engine.run(config, granularity),  # type: ignore[arg-type]
        config=config,
        mode=config.mode,
        timeseries=RunTimeseries(mode=config.mode),
        recorder=recorder,
    )


def _close_events(live: LiveRun) -> None:
    """Close the paused engine generator so its frame is released.

    Args:
        live: The run whose stream is being abandoned or has ended.
    """
    close = getattr(live.events, "close", None)
    if close is not None:
        close()


def _finish_live_run(live: LiveRun, note: str, capacity: float | None) -> None:
    """Move a finished or stopped run's results into ``last_run``; clear the holder.

    Post-run behaviour is then exactly what #44/#45 built: the next script
    run renders ``last_run`` and any view combination re-renders it
    without re-running.

    Args:
        live: The run that just finished or stopped.
        note: The results caption ("Results of the last run (seed …)").
        capacity: K for the population chart's reference line.
    """
    _close_events(live)
    st.session_state["last_run"] = {
        "timeseries": live.timeseries,
        "note": note,
        "carrying_capacity": capacity,
    }
    st.session_state.pop(LIVE_RUN_KEY, None)


def _abandon_live_run(live: LiveRun) -> None:
    """Abandon a run the script cannot continue: crash or Streamlit STOP.

    The recorder's #53 rule preserved exactly (#183 R5): an abandoned
    recording is DISCARDED, never ghosted, and the next render shows the
    one interrupted-recording sentence (staged here, in a script that is
    still alive — no dying-script write races a rerun, the #55 hazard).
    Nothing is moved into ``last_run``: the charts on screen stay until
    the next interaction, as an interrupted run's did before.

    Args:
        live: The run being abandoned.
    """
    _close_events(live)
    if live.recorder is not None:
        st.session_state["_discard_note"] = DISCARD_NOTE
        _discard_recording(live.recorder)
    st.session_state.pop(LIVE_RUN_KEY, None)


def _live_grid_figure(config: ExperimentConfig, timeseries: RunTimeseries) -> Figure | None:
    """Build the current-occupancy grid from the latest period snapshot.

    The latest snapshot IS the render state (Design 10): a lattice run with
    per-agent data redraws its occupancy as periods finish — what lets the
    drifting frontier actually be watched. Imitation runs have empty
    snapshots and keep the founding preview above instead (nothing moves,
    #116).

    Args:
        config: The run's configuration.
        timeseries: The live series (its last snapshot is drawn).

    Returns:
        The grid figure, or ``None`` when there is nothing to draw.
    """
    if config.structure.kind != "lattice" or not timeseries.agent_snapshots:
        return None
    placements = {
        snapshot.site_id: snapshot.strategy
        for snapshot in timeseries.agent_snapshots[-1]
        if snapshot.site_id is not None
    }
    if not placements or config.structure.rows is None or config.structure.cols is None:
        return None
    return charts.grid_chart(config.structure.rows, config.structure.cols, placements)


def _draw_blocked_metrics(
    config: ExperimentConfig,
    timeseries: RunTimeseries,
    blocked_note: DeltaGenerator,
    infeasible_note: DeltaGenerator,
    moves_note: DeltaGenerator,
) -> None:
    """Refresh the blocked/infeasible-parents and blocked-moves metrics.

    The blocked-parents readout (M11a Phase C, spec Design 4) is live only
    where the local placement gate exists — a lattice economy. Beside it,
    the infeasible-parents readout (M11b Phase A, #164) is live only under
    the three-way gate, where the feasibility filter runs (the async clock
    never populates it, so it stays hidden). Third, the blocked-moves
    readout (M11b Phase B, #165/#172) is live only while movement is ACTIVE
    (lattice + energy economy + a positive movement rate) — hidden, not a
    permanent zero, otherwise.

    Args:
        config: The run's configuration (decides which readouts exist).
        timeseries: The live series the counts are read from.
        blocked_note: Placeholder for the blocked-parents metric.
        infeasible_note: Placeholder for the infeasible-parents metric.
        moves_note: Placeholder for the blocked-moves metric.
    """
    numbers = economy_helpers.blocked_parents_metric(timeseries.blocked_parents)
    if economy_helpers.blocked_parents_visible(config) and numbers is not None:
        latest, total = numbers
        blocked_note.metric(
            "Blocked parents this generation",
            latest,
            delta=f"run total {total}",
            delta_color="off",
            help=ECONOMY_HELP["blocked_parents"],
        )
    infeasible = economy_helpers.infeasible_parents_metric(timeseries.infeasible_parents)
    if economy_helpers.infeasible_parents_visible(config) and infeasible is not None:
        latest, total = infeasible
        infeasible_note.metric(
            "Infeasible parents this generation",
            latest,
            delta=f"run total {total}",
            delta_color="off",
            help=ECONOMY_HELP["infeasible_parents"],
        )
    moves = economy_helpers.blocked_moves_metric(timeseries.blocked_moves)
    if economy_helpers.blocked_moves_visible(config) and moves is not None:
        latest, total = moves
        moves_note.metric(
            "Blocked moves this generation",
            latest,
            delta=f"run total {total}",
            delta_color="off",
            help=ECONOMY_HELP["blocked_moves"],
        )


def _live_pass(live: LiveRun, per_round: bool, whole_game: bool) -> None:
    """One pass of the live loop: advance one period, repaint, finish or stop.

    The run no longer lives inside one script run (M11b Phase E3, DECISIONS
    #168/#183): each script pass consumes exactly one period's events
    (#183 R3 — a generation, a cycle, or one async recording period), with
    the #39 progress caption advancing every ``PROGRESS_EVERY`` fine events
    inside the pass, then repaints every chart with the display toggles'
    CURRENT values, and :func:`_schedule_next_pass` (at the end of
    ``main``) sleeps the playback delay and reruns the script. A widget
    interaction mid-pass simply ends the pass early — the generator is
    paused, the holder is intact, and the next pass carries on — which is
    what makes the toggles switchable mid-run.

    Stop is checked ONCE per pass (#183 R4), before advancing: a stopped
    run keeps its charts, discards its recording (#53, preserved per #183
    R5), and moves into ``last_run`` flagged "stopped early". The
    finishing pass (``RunFinished`` seen) renders the summary table and the
    periods-elapsed message, finalises the recorder (staging the new folder
    as the Results browser's selection, #189 R2), and moves the results
    into ``last_run`` exactly as the in-script loop did.

    Chart rebuilds stay wall-clock throttled (#94): a pass inside the
    throttle window re-emits the figures it built last time, unchanged,
    so the browser keeps the previous frame; a toggle flip, the finishing
    pass, and the stopping pass always rebuild.

    Args:
        live: The run in progress (under ``LIVE_RUN_KEY``).
        per_round: Score view for the mean chart, as read THIS pass (#44).
        whole_game: Time scope for the mean chart, as read THIS pass (#45).
    """
    config = live.config
    timeseries = live.timeseries
    recorder = live.recorder
    period_label = "cycle" if config.mode == "tournament" else "generation"
    progress = st.empty()
    col_left, col_right = st.columns(2)
    chart_left, chart_right = col_left.empty(), col_right.empty()
    chart_coop = st.empty()  # full-width, below the pair (M9b)
    chart_economy = _economy_placeholders()  # blank outside the economy (M10a)
    blocked_col, infeasible_col, moves_col = st.columns(3)
    blocked_note = blocked_col.empty()
    infeasible_note = infeasible_col.empty()
    moves_note = moves_col.empty()
    grid_live = st.empty()
    if config.dynamics.time_model == "asynchronous":
        st.caption(GEN_EQUIV_AXIS_NOTE)
    capacity = economy_helpers.chart_carrying_capacity(config)

    stopped = bool(st.session_state.get("stop_requested"))
    period = None
    if not stopped and not live.finished:

        def _on_progress(count: int) -> None:
            """The #39 progress line, every PROGRESS_EVERY fine events."""
            progress.caption(f"... {count} match/round events so far")

        try:
            period = helpers.advance_one_period(live, _on_progress, PROGRESS_EVERY)
        except Exception:
            # A crash inside the engine or the recorder: discard the
            # partial recording (#53/#54) and let the error surface.
            _abandon_live_run(live)
            raise

    final_pass = stopped or live.finished
    view = (per_round, whole_game)
    now = time.monotonic()
    if (
        final_pass
        or view != live.view
        or helpers.should_redraw(now, live.last_redraw, live.delay, LIVE_REDRAW_MIN_SECONDS)
    ):
        live.figures = dict(_build_figures(timeseries, per_round, whole_game, capacity, True))
        grid = _live_grid_figure(config, timeseries)
        if grid is not None:
            live.figures["grid"] = grid
        live.view = view
        live.last_redraw = now
    _paint_figures(live.figures, chart_left, chart_right, chart_coop, 0, economy=chart_economy)
    grid_figure = live.figures.get("grid")
    if grid_figure is not None and config.structure.rows and config.structure.cols:
        grid_live.plotly_chart(
            grid_figure,
            width=_grid_width(config.structure.rows, config.structure.cols),
            key="live_grid_0",
        )
    _draw_blocked_metrics(config, timeseries, blocked_note, infeasible_note, moves_note)

    note = f"Results of the last run (seed {config.seed})"
    if stopped:
        st.warning("Run stopped — the charts show progress up to the stop.")
        note += " — stopped early"
        if recorder is not None:
            # Stop's recorder behaviour, preserved exactly (#53; #183 R5):
            # the partial folder is discarded and the sentence shown —
            # the failure rewrite in _discard_recording still lands here.
            st.session_state["_discard_note"] = DISCARD_NOTE
            _discard_recording(recorder)
            st.caption(st.session_state.pop("_discard_note", ""))
        _finish_live_run(live, note, capacity)
    elif live.finished:
        final = timeseries.final
        if final is not None:
            st.success(
                f"Run complete: {final.completed} {period_label}s, seed {config.seed} "
                "(same seed + same settings = same charts)."
            )
            _final_summary_area(timeseries)
            if recorder is not None:
                folder = recorder.finalize()
                charts.export_run_charts(recorder.timeseries, folder, carrying_capacity=capacity)
                st.caption(f"Recorded to {folder} — see the Results browser tab.")
                # The newest run opens itself in the Results browser (#189
                # R2): stage its folder name in the browser's own slot,
                # which the browser applies to the "Open a run" key before
                # that selectbox is instantiated — later on this very pass,
                # since the Run lab renders first in the strip (#52's route,
                # so the key keeps one writer). A stopped or unrecorded run
                # never reaches this line and leaves the selection alone.
                st.session_state["_select_run"] = folder.name
        elif recorder is not None:
            # Unreachable with the engine (every stream closes with
            # RunFinished); a recording without one must not ghost.
            _discard_recording(recorder)
        _finish_live_run(live, note, capacity)
    elif period is not None:
        progress.caption(f"{period_label} {period.index + 1} finished")


def _schedule_next_pass() -> None:
    """Sleep the playback delay, then rerun the script for the next pass.

    Called LAST in ``main`` so every tab has rendered before the pass
    ends — which is also why the Results browser and Sweep tabs keep a run
    advancing while viewed (#183 R4, accepted). A full-script rerun, not a
    fragment: the E3 probe (DECISIONS #184) found stock AppTest cannot
    request a fragment-scoped run and a fragment cannot reschedule itself
    from the full-script passes the mid-run contract requires.
    """
    live: LiveRun | None = st.session_state.get(LIVE_RUN_KEY)
    if live is None or live.finished:
        return
    if live.delay > 0:
        time.sleep(live.delay)
    st.rerun()


def _discard_recording(recorder: RunRecorder) -> None:
    """Discard a partial recording; the banner was write-ahead staged (#55).

    Usually called from a script run Streamlit has already killed (Stop /
    mid-run Run click), so the success message was staged when the run
    STARTED; only a deletion failure rewrites it (best-effort — this
    thread's session writes can race the next render).

    Args:
        recorder: The recorder whose folder should be removed.
    """
    try:
        recorder.discard()
    except OSError as error:
        st.session_state["_discard_note"] = (
            f"A stopped run's partial folder could not be removed ({error}) — "
            f"delete {recorder.folder} by hand once OneDrive/Explorer lets go."
        )


def _queue_config_load(folder: str) -> None:
    """Ask the next script run to load a recorded config (button callback).

    Args:
        folder: The run folder whose config should fill the panel.
    """
    st.session_state["_pending_load"] = folder


def _apply_pending_load() -> None:
    """Load a queued recorded config into the panel, before widgets render.

    The browser's "load into panel" button queues a folder; this runs at
    the top of the script (widget state may only be written before the
    widgets are instantiated) and reuses the scenario-loading machinery —
    the panel lands on "Custom" with the run's exact values (#49).
    """
    pending = st.session_state.pop("_pending_load", None)
    if pending is None:
        return
    loaded = load_run(Path(pending))
    _load_state(
        helpers.widget_values_from_config(loaded.config),
        dict(loaded.config.population.composition),
        loaded.config.strategy_params,
    )
    st.session_state["scenario_choice"] = CUSTOM
    st.session_state["_loaded_scenario"] = CUSTOM
    st.session_state["_load_note"] = (
        f"Loaded the config of {Path(pending).name} into the panel — press Run to "
        "reproduce it exactly, or edit it as a starting point."
    )


def _results_browser() -> None:
    """Render the results browser: index table, run charts, config loading.

    Lists the run folders that actually exist (folder truth — survives
    hand-deleted or renamed folders, DECISIONS #50) and reconstructs the
    selected run via :func:`pdsim.io.results.load_run`; the charts are the
    same pure builders the live view uses, with their own #44/#45 toggles —
    pure re-renderings of the persisted raw data.
    """
    rows = sync_index(RUNS_DIR)  # also reconciles index.csv with the folders (#52)
    if not rows:
        st.info(
            "No recorded runs yet. Turn on **Record this run** in the Run lab, or "
            "record one headlessly: `python -m pdsim.run --scenario classic_tournament`."
        )
        return
    st.dataframe(rows, width="stretch")
    run_ids = [str(row["run_id"]) for row in rows]
    # A widget's own key may only be written BEFORE the widget exists in a
    # script run, so delete/rename stage the next selection under
    # "_select_run" and we apply it here, at the top (#52). Explicit
    # assignment, not pop: Streamlit resurrects popped widget values from
    # the frontend, which left deleted names showing in the dropdown.
    staged = st.session_state.pop("_select_run", None)
    if staged in run_ids:
        st.session_state["browser_run"] = staged
    elif st.session_state.get("browser_run") not in run_ids:
        st.session_state["browser_run"] = run_ids[0]
    run_id = st.selectbox(
        "Open a run",
        options=run_ids,
        key="browser_run",
        help=(
            "Every run folder currently under runs/ (newest first); each can be "
            "reproduced from its config.yaml."
        ),
    )
    try:
        loaded = load_run(RUNS_DIR / run_id)
    except (FileNotFoundError, ValueError, OSError) as error:
        # E.g. the folder vanished between listing and loading, or a file
        # inside it is missing/corrupt — report, don't crash.
        st.error(f"Could not load {run_id}: {error}")
        return
    summary = loaded.summary
    cooperation_rate = summary.get("final_cooperation_rate")
    cooperation_note = (
        f" · cooperation {cooperation_rate:.2f}" if isinstance(cooperation_rate, float) else ""
    )
    st.caption(
        f"{summary['mode']} · N={summary['population_size']} · "
        f"{summary['periods_completed']} periods · seed {summary['seed']} · "
        f"{summary['headline']}{cooperation_note} · recorded by pdsim "
        f"{summary.get('code_version', {}).get('package', '?')}"
    )
    tournament = loaded.timeseries.mode == "tournament"
    col_view, col_scope, col_load, col_delete = st.columns([2, 2, 2, 1])
    score_view = col_view.radio(
        "Score view",
        options=["total", "per_round"],
        key="browser_score_view",
        horizontal=True,
        format_func=lambda view: "Total" if view == "total" else "Per round",
        help="Same views as the live charts — recomputed from the recorded raw data.",
    )
    scope = col_scope.radio(
        "Time scope",
        options=["generation", "whole_game"],
        key="browser_time_scope",
        horizontal=True,
        disabled=tournament,
        format_func=lambda s: "This generation" if s == "generation" else "Whole game",
        help="Greyed out for tournaments: their scores are already whole-game figures.",
    )
    col_load.button(
        "Load config into panel",
        key="browser_load",
        on_click=_queue_config_load,
        args=(str(RUNS_DIR / run_id),),
        help="Fills the Run lab panel with this run's exact config (as 'Custom').",
    )
    if col_delete.button(
        "Delete…",
        key="browser_delete",
        help="Remove this run's folder and its index entry (asks for confirmation).",
    ):
        st.session_state["_confirm_delete"] = run_id
    if st.session_state.get("_confirm_delete") == run_id:
        st.warning(
            f"Permanently delete **{run_id}**? The run folder and its index entry "
            "will be removed — this cannot be undone."
        )
        col_yes, col_no = st.columns([1, 5])
        if col_yes.button("Yes, delete", key="browser_delete_confirm", type="primary"):
            try:
                delete_run(RUNS_DIR, run_id)
            except OSError as error:
                # Windows: something briefly holds the folder (an Explorer
                # window, OneDrive sync, antivirus). Report and let the
                # user retry — never a traceback (DECISIONS #51).
                st.error(
                    f"Could not delete {run_id}: {error}. Something is still "
                    "holding the folder open — close any Explorer window "
                    "showing it, give OneDrive a moment to finish syncing, "
                    "then press 'Yes, delete' again."
                )
            else:
                st.session_state.pop("_confirm_delete", None)
                remaining = [r for r in run_ids if r != run_id]
                if remaining:
                    st.session_state["_select_run"] = remaining[0]
                st.rerun()
        if col_no.button("Cancel", key="browser_delete_cancel"):
            st.session_state.pop("_confirm_delete", None)
            st.rerun()
    with st.expander("Rename this run"):
        new_name = st.text_input(
            "New folder name",
            value=run_id,
            key=f"browser_rename#{run_id}",  # per-run key: switching runs refreshes the field
            help="Letters, digits, dots, underscores, spaces, and hyphens.",
        )
        if st.button("Apply rename", key="browser_rename_apply"):
            try:
                final_name = rename_run(RUNS_DIR, run_id, new_name)
            except (ValueError, FileExistsError, FileNotFoundError) as error:
                st.error(str(error))
            except OSError as error:
                st.error(
                    f"Could not rename {run_id}: {error}. Something is holding the "
                    "folder open — close Explorer windows / let OneDrive settle, "
                    "then try again."
                )
            else:
                st.session_state["_select_run"] = final_name
                st.rerun()
    if any(t is not None for t in loaded.timeseries.gen_equiv_times):
        st.caption(GEN_EQUIV_AXIS_NOTE)
    col_left, col_right = st.columns(2)
    _draw_charts(
        loaded.timeseries,
        col_left.empty(),
        col_right.empty(),
        st.empty(),
        0,
        score_view == "per_round",
        scope == "whole_game" and not tournament,
        key_prefix="browser",
        economy=_economy_placeholders(),
        carrying_capacity=economy_helpers.chart_carrying_capacity(loaded.config),
    )
    # A recorded lattice run carries its own layout file, so the grid is
    # resolved against the run folder rather than the working directory.
    # When the recorded data carries site ids (sync economy; async both
    # modes), the browser also offers the run's FINAL occupancy — #136's
    # deferred half — and defaults to it, because the browser answers "what
    # happened" and the final state is the answer; founding stays one click
    # away for arrangement questions (DECISIONS #146). Presence-driven,
    # never mode-driven (#100(b)/#120): imitation runs persist no snapshots
    # and schema ≤ 4 folders carry no site ids, so for them no selector
    # renders and the founding view stands unchanged.
    final_placements = helpers.final_occupancy(loaded.timeseries)
    grid_rows = loaded.config.structure.rows
    grid_cols = loaded.config.structure.cols
    if final_placements is not None and grid_rows is not None and grid_cols is not None:
        grid_view = st.radio(
            "Grid view",
            options=["Founding", "Final"],
            index=1,
            key="browser_grid_view",
            horizontal=True,
            help=(
                "'Final' draws the last recorded period's occupancy from the "
                "run's per-agent data — where births and deaths left the "
                "population. 'Founding' replays the generation-0 arrangement "
                "from the recorded config and seed."
            ),
        )
        if grid_view == "Final":
            st.plotly_chart(
                charts.grid_chart(grid_rows, grid_cols, final_placements, title="Final occupancy"),
                width=_grid_width(grid_rows, grid_cols),
                key="browser_final_grid",
            )
        else:
            _grid_area(loaded.config, key_prefix="browser", config_dir=RUNS_DIR / run_id)
    else:
        _grid_area(loaded.config, key_prefix="browser", config_dir=RUNS_DIR / run_id)
    _final_summary_area(loaded.timeseries)


class _RunControls(NamedTuple):
    """What the run-controls row returned this script run.

    Attributes:
        granularity: The finest event level the NEXT run will request.
        delay: The playback-delay slider (seconds).
        per_round: Score view — per-round when True (DECISIONS #44).
        whole_game: Time scope — whole-game when True and not greyed (#45).
        record: The "Record this run" checkbox.
        run_clicked: Whether Run was pressed this script run.
    """

    granularity: str
    delay: float
    per_round: bool
    whole_game: bool
    record: bool
    run_clicked: bool


def _toggle_values_from_state(displayed_mode: str | None) -> tuple[bool, bool, float]:
    """Read the display toggles from session state BEFORE their widgets render.

    A pass advances the engine before the run-controls row is painted, so
    the row can show the state AFTER the pass — Run re-enabled and
    granularity live the moment a run finishes or stops, with no extra
    script run. The pass therefore reads the toggles' values from session
    state, which Streamlit fills from the browser's widget states before
    the script runs (a flipped radio is already there), using the same
    defaults the widgets carry. Reading a widget's key before it renders is
    legal; only writing is not.

    Args:
        displayed_mode: The mode of the run on screen (the live run's) —
            decides whether the time scope is greyed (#183 R4).

    Returns:
        ``(per_round, whole_game, delay)`` for this pass.
    """
    per_round = st.session_state.get("score_view", "total") == "per_round"
    scope = st.session_state.get("time_scope", "generation")
    whole_game = scope == "whole_game" and not helpers.time_scope_greyed(displayed_mode)
    delay = float(st.session_state.get("playback_delay", 0.05))
    return per_round, whole_game, delay


def _run_controls(
    *, running: bool, tournament_next: bool, mix_ok: bool, displayed_mode: str | None
) -> _RunControls:
    """Render the run-controls row: the four display toggles, Record, Run, Stop.

    Args:
        running: Whether a run is in progress AFTER this pass — greys
            granularity (#183 R1) and disables Run (#183 R4).
        tournament_next: Whether the mode strip says tournament — labels
            the coarse granularity level "cycle" for the NEXT run.
        mix_ok: Whether the population mix sums to the size (the Run gate).
        displayed_mode: The mode of the run on screen, if any — the
            time-scope greying's only input (#183 R4).

    Returns:
        The row's values, including whether Run was clicked.
    """
    col_gran, col_speed, col_view, col_scope, col_run, col_stop = st.columns([2, 2, 2, 2, 1, 1])
    granularity_help = (
        "The finest event level the engine reports while running. Charts always "
        "update per generation/cycle; finer levels drive the progress line. "
        "Fine granularity is meant for small populations (DESIGN §4). "
        "Granularity never changes results — only what you watch."
    )
    if running:
        # Bound at run start (#35), so greyed mid-run with the note — the
        # #34 grey-never-hide pattern (#183 R1).
        granularity_help = f"{granularity_help}\n\n{GRANULARITY_RUNNING_NOTE}"
    granularity = col_gran.selectbox(
        "Update granularity",
        options=["generation", "match", "round"],
        key="granularity",
        format_func=lambda g: "cycle" if g == "generation" and tournament_next else g,
        disabled=running,
        help=granularity_help,
    )
    delay = col_speed.slider(
        "Playback delay (s)",
        min_value=0.0,
        max_value=1.0,
        value=0.05,
        step=0.05,
        key="playback_delay",
        help=(
            "Pause after each chart refresh, so you can watch the run unfold. "
            "Changing it mid-run takes effect from the next refresh."
        ),
    )
    score_view = col_view.radio(
        "Score view",
        options=["total", "per_round"],
        key="score_view",
        horizontal=True,
        format_func=lambda view: "Total" if view == "total" else "Per round",
        help=(
            "'Total' plots the raw score selection acts on — it grows with "
            "population size and match length (roughly payoff x (N-1) x rounds). "
            "'Per round' divides by the rounds actually played, landing on the "
            "payoff-matrix scale (0-5 with the default payoffs) so different "
            "setups compare directly. Switching mid-run re-renders the live "
            "chart as the run continues; switching after a run re-renders the "
            "last results without re-running."
        ),
    )
    record = st.checkbox(
        "Record this run",
        value=True,
        key="record_run",
        help=(
            "Save the run to a folder under runs/ as it streams: the exact config "
            "(re-runnable), the raw time series, a summary, and chart exports. "
            "Recorded runs appear in the Results browser tab. On by default — "
            "reproducibility is the platform's ethos, and the folders are small."
        ),
    )
    scope_greyed = helpers.time_scope_greyed(displayed_mode)
    scope = col_scope.radio(
        "Time scope",
        options=["generation", "whole_game"],
        key="time_scope",
        horizontal=True,
        disabled=scope_greyed,
        format_func=lambda s: "This generation" if s == "generation" else "Whole game",
        help=(
            "'This generation' plots each generation's own scores — jumpy but "
            "immediate. 'Whole game' plots the running average over the entire run "
            "so far, so lines move gradually as evidence accumulates. Greyed out "
            "while a tournament run is displayed: tournament scores never reset, "
            "so they are already whole-game figures."
        ),
    )
    # Run is disabled while a run is in progress (#183 R4) — the same idiom
    # as the composition-sum gate; parameters stay editable but inert until
    # the next Run, because the running engine consumed a config frozen at
    # the click. Stop sets a flag the NEXT pass honours.
    run_clicked = col_run.button(
        "Run", type="primary", key="run_button", disabled=not mix_ok or running
    )
    col_stop.button("Stop", key="stop_button", on_click=_request_stop)
    return _RunControls(
        granularity=str(granularity),
        delay=float(delay),
        per_round=score_view == "per_round",
        whole_game=scope == "whole_game" and not scope_greyed,
        record=bool(record),
        run_clicked=bool(run_clicked),
    )


def _run_lab() -> None:
    """Lay out the live-run experience: scenario, panel, controls, charts.

    Order of work on a pass (M11b Phase E3): the panel renders; then, if a
    run is in progress, the pass advances it and paints its charts BEFORE
    the run-controls row is painted — the row lives in a container created
    above the charts and filled afterwards, so it shows the state after the
    pass (Run re-enabled the moment a run finishes). Only the click's own
    script run paints the row before its run exists; the next pass, scheduled
    immediately, greys it (#184 f3).
    """
    _scenario_area()
    load_note = st.session_state.pop("_load_note", None)
    if load_note:
        st.success(load_note)
    discard_note = st.session_state.pop("_discard_note", None)
    if discard_note:
        st.info(discard_note)  # staged by an abandoned recorded run (#53/#184)
    values, composition, strategy_params = _parameter_panel()

    mix_total = sum(composition.values())
    size = int(values["population.size"])  # type: ignore[arg-type]
    if mix_total == size:
        st.caption(f"Population mix OK: {mix_total} agents.")
    else:
        st.warning(
            f"The population mix sums to {mix_total}, but the population size is "
            f"{size}. Adjust the counts (or the size) to enable Run."
        )

    controls_area = st.container()  # the row's position; filled after the pass
    live: LiveRun | None = st.session_state.get(LIVE_RUN_KEY)
    pass_ran = live is not None  # a finishing/stopping pass paints its own charts
    if live is not None:
        # Every pass reads the toggles fresh (#168) — from session state,
        # because the row has not rendered yet this pass.
        per_round, whole_game, delay = _toggle_values_from_state(live.mode)
        live.delay = delay
        _live_pass(live, per_round, whole_game)
        live = st.session_state.get(LIVE_RUN_KEY)  # cleared by a finishing/stopping pass

    # The run being DISPLAYED (#183 R4): the live run while one is in
    # progress, else the persisted last run, else nothing. The time-scope
    # greying keys off THIS, never off the panel's run.mode — the mode
    # strip says what the next run will be, not what is on screen.
    last = st.session_state.get("last_run")
    running = live is not None
    if live is not None:
        displayed_mode: str | None = live.mode
    elif last is not None:
        displayed_mode = last["timeseries"].mode
    else:
        displayed_mode = None
    with controls_area:
        controls = _run_controls(
            running=running,
            tournament_next=values["run.mode"] == "tournament",
            mix_ok=mix_total == size,
            displayed_mode=displayed_mode,
        )

    if controls.run_clicked and not running:
        st.session_state["stop_requested"] = False
        try:
            config = helpers.build_config(values, composition, strategy_params)
        except ValidationError as error:
            for message in helpers.validation_messages(error):
                st.error(message)
        else:
            # "Custom" is recorded as the scenario label too — a blank
            # scenario cell in the browser table read as missing data (#52).
            choice = st.session_state.get("_loaded_scenario")
            scenario = str(choice) if choice else CUSTOM
            live = _start_live_run(config, controls.granularity, controls.record, scenario)
            st.session_state[LIVE_RUN_KEY] = live
            live.delay = controls.delay
            _live_pass(live, controls.per_round, controls.whole_game)
    elif not running and not pass_ran and last is not None and not controls.run_clicked:
        timeseries = last["timeseries"]
        st.caption(f"{last['note']} — switch the score views to re-render, or press Run.")
        if any(t is not None for t in timeseries.gen_equiv_times):
            st.caption(GEN_EQUIV_AXIS_NOTE)
        col_left, col_right = st.columns(2)
        _draw_charts(
            timeseries,
            col_left.empty(),
            col_right.empty(),
            st.empty(),
            0,
            controls.per_round,
            controls.whole_game,
            economy=_economy_placeholders(),
            carrying_capacity=last.get("carrying_capacity"),
        )
        _final_summary_area(timeseries)


def _fill_range_field(target_key: str, start: int, stop: int, step: int) -> None:
    """Write a built integer range into a text field (range-builder callback).

    Button callbacks run before the next script render, so writing another
    widget's session-state value here is legal; a bad range stages a plain
    error the next render shows instead.

    Args:
        target_key: Session-state key of the text field to fill.
        start: First value of the range.
        stop: Last candidate value (inclusive when the step lands on it).
        step: Increment between values.
    """
    try:
        values = sweep_helpers.build_range(start, stop, step)
    except ValueError as error:
        st.session_state["_sweep_range_error"] = str(error)
    else:
        st.session_state[target_key] = ", ".join(str(value) for value in values)


def _add_param_axis() -> None:
    """Append a new parameter-axis row (button callback)."""
    next_id = st.session_state.get("_sweep_axis_seq", 0)
    st.session_state["_sweep_axis_seq"] = next_id + 1
    st.session_state["sweep_param_axes"] = [*st.session_state.get("sweep_param_axes", []), next_id]


def _remove_param_axis(axis_id: int) -> None:
    """Remove one parameter-axis row (button callback).

    Args:
        axis_id: The row's stable identity in the session-state list.
    """
    st.session_state["sweep_param_axes"] = [
        existing for existing in st.session_state.get("sweep_param_axes", []) if existing != axis_id
    ]


def _sweep_composition_area(fields: dict[str, object]) -> dict[str, object] | None:
    """Render the composition-axis section; return the authored axis dict.

    The three-bucket model is STRUCTURAL here (DECISIONS #73): the varying
    invader is excluded from the bucket rows, and each remaining strategy
    has ONE bucket radio — so the "buckets disjoint" rule is impossible to
    violate from the UI. A live preview shows the resolved integer
    composition at the largest count, using the real engine arithmetic
    (:func:`~pdsim.sweep.spec.resolve_composition`).

    Args:
        fields: The authored values so far (the base fields drive the
            preview's population size).

    Returns:
        ``{vary, counts, fixed, fill}``, or ``None`` when the axis is off.
    """
    include = st.checkbox(
        "Include a composition axis",
        key="sweep_comp_on",
        help=(
            "March one strategy's starting count across a range while the rest of "
            "the population keeps a constant character — the classic invasion "
            "experiment. Off = every member run keeps the base config's mix."
        ),
    )
    if not include:
        return None
    names = [info.name for info in all_strategies()]
    with st.expander("Composition axis", expanded=True):
        vary = st.selectbox(
            "Varying invader",
            options=names,
            key="sweep_vary",
            help=(
                "The strategy whose starting count the sweep marches upward. "
                "Machine names are shown because they are what the sweep YAML uses."
            ),
        )
        counts_text = st.text_input(
            "Invader counts",
            key="sweep_counts",
            help=(
                "The invader counts to try, e.g. '2, 4, 6, 8'. One member run is "
                "made per count (times every seed and parameter combination)."
            ),
        )
        col_start, col_stop, col_step, col_fill = st.columns([1, 1, 1, 1])
        start = int(
            col_start.number_input(
                "Range start", min_value=0, value=2, step=1, key="sweep_counts_start"
            )
        )
        stop = int(
            col_stop.number_input(
                "Range stop", min_value=0, value=20, step=1, key="sweep_counts_stop"
            )
        )
        step = int(
            col_step.number_input(
                "Range step", min_value=1, value=2, step=1, key="sweep_counts_step"
            )
        )
        col_fill.button(
            "Fill counts",
            key="sweep_counts_fill",
            on_click=_fill_range_field,
            args=("sweep_counts", start, stop, step),
            help="Write start..stop (step apart) into the counts field; edit freely after.",
        )
        counts: list[int] = []
        try:
            counts = sweep_helpers.parse_int_list(counts_text)
        except ValueError as error:
            st.error(str(error))
        st.markdown(
            "**Background buckets** — every other strategy is either absent "
            "(*none*), held at a constant count (*fixed*), or takes a percentage "
            "of the leftover seats (*fill*). Fill percentages must sum to 100."
        )
        fixed: dict[str, int] = {}
        fill: dict[str, float] = {}
        for info in all_strategies():
            if info.name == vary:
                continue
            col_name, col_bucket, col_value = st.columns([2, 3, 2])
            col_name.markdown(f"{info.display_name}")
            bucket = col_bucket.radio(
                f"Bucket for {info.name}",
                options=["none", "fixed", "fill"],
                key=f"sweep_bucket#{info.name}",
                horizontal=True,
                label_visibility="collapsed",
                help=info.description,
            )
            if bucket == "fixed":
                fixed[info.name] = int(
                    col_value.number_input(
                        f"Fixed count for {info.name}",
                        min_value=1,
                        value=1,
                        step=1,
                        key=f"sweep_fixed#{info.name}",
                        label_visibility="collapsed",
                        help="This many agents of the strategy, in every member run.",
                    )
                )
            elif bucket == "fill":
                fill[info.name] = float(
                    col_value.number_input(
                        f"Fill percentage for {info.name}",
                        min_value=0.0,
                        max_value=100.0,
                        value=100.0,
                        step=5.0,
                        key=f"sweep_fill#{info.name}",
                        label_visibility="collapsed",
                        help=(
                            "This strategy's share of the seats left after the "
                            "invader and the fixed counts are placed."
                        ),
                    )
                )
        if fill:
            fill_total = sum(fill.values())
            if abs(fill_total - 100) > 1e-6:
                st.warning(f"Fill percentages sum to {fill_total:g} — they must sum to 100.")
            else:
                st.caption(f"Fill percentages sum to {fill_total:g}.")
        # Live preview: the real three-bucket arithmetic at the largest count
        # (largest-remainder rounding included), so what you see is exactly
        # what the member configs get (explainer §2.2/§4).
        size = sweep_helpers.base_population_size(fields)
        if counts and size is not None:
            try:
                resolved = resolve_composition(size, vary, max(counts), fixed, fill)
            except ValueError as error:
                st.warning(str(error))
            else:
                resolved_text = ", ".join(f"{name} {count}" for name, count in resolved.items())
                st.caption(
                    f"Preview at the largest invader count ({max(counts)}): "
                    f"{resolved_text} — total {size}."
                )
    return {"vary": vary, "counts": counts, "fixed": fixed, "fill": fill}


def _sweep_parameter_axes_area() -> list[dict[str, object]]:
    """Render the add/remove parameter-axis rows; return the authored axes.

    Each axis pairs a Parameter Registry key with a list of values to try;
    the sweep runs the cross product of all axes. Values are parsed and
    checked per axis (``sweep_helpers.parse_value_list`` /
    ``validate_parameter_values``) so errors appear next to their widget.

    Returns:
        One ``{key, values}`` dict per authored axis.
    """
    st.markdown("**Parameter axes** — sweep any registry parameter over a list of values.")
    st.button(
        "Add parameter axis",
        key="sweep_add_axis",
        on_click=_add_param_axis,
        help=(
            "Each axis multiplies the sweep: 3 values on one axis and 4 on another "
            "make 12 combinations (times counts and seeds)."
        ),
    )
    # run.seed is excluded: seeds are their own first-class axis below, and a
    # run.seed parameter axis would be silently overwritten by the seed loop.
    keys = [spec.key for spec in helpers.panel_specs() if spec.key != "run.seed"]
    axes: list[dict[str, object]] = []
    for axis_id in st.session_state.get("sweep_param_axes", []):
        col_key, col_values, col_remove = st.columns([2, 3, 1])
        key = col_key.selectbox(
            "Parameter",
            options=keys,
            key=f"sweep_axis_key#{axis_id}",
            help="Any Parameter Registry key; its registry rules validate each value.",
        )
        text = col_values.text_input(
            "Values",
            key=f"sweep_axis_values#{axis_id}",
            help="Comma/space-separated values to try, e.g. '0.01, 0.1, 1.0'.",
        )
        col_remove.button(
            "Remove",
            key=f"sweep_axis_remove#{axis_id}",
            on_click=_remove_param_axis,
            args=(axis_id,),
        )
        values: list[ParamValue] = []
        try:
            values = sweep_helpers.parse_value_list(key, text)
        except ValueError as error:
            st.error(str(error))
        for message in sweep_helpers.validate_parameter_values(key, values):
            st.error(message)
        axes.append({"key": key, "values": values})
    return axes


def _sweep_metrics_area() -> list[dict[str, object]]:
    """Render the metric multiselect + per-metric params; return MetricRefs.

    Metrics come from the Outcome Metrics Registry (the fourth registry,
    DECISIONS #69), so a newly registered metric appears here with zero UI
    edits — each declared ``MetricParam`` renders by its kind (a strategy
    selectbox, or a number input).

    Returns:
        One ``{metric, **params}`` dict per selected metric.
    """
    infos = {info.display_name: info for info in all_metrics()}
    chosen = st.multiselect(
        "Metrics",
        options=list(infos),
        key="sweep_metrics",
        help=(
            "The numbers to compute from each finished member run (one summary "
            "column each). Docs: the 'Outcome metrics' section of docs/PARAMETERS.md."
        ),
    )
    strategy_names = [info.name for info in all_strategies()]
    refs: list[dict[str, object]] = []
    for display_name in chosen:
        info = infos[display_name]
        ref: dict[str, object] = {"metric": info.name}
        if info.params:
            columns = st.columns(max(3, len(info.params)))
            for i, param in enumerate(info.params):
                widget_key = f"sweep_metric#{info.name}#{param.name}"
                label = f"{param.name} — {info.display_name}"
                with columns[i % len(columns)]:
                    if param.kind == "strategy":
                        ref[param.name] = st.selectbox(
                            label, options=strategy_names, key=widget_key, help=param.description
                        )
                    elif param.kind == "int":
                        ref[param.name] = int(
                            st.number_input(
                                label,
                                min_value=1,
                                value=int(param.default or 1),
                                step=1,
                                key=widget_key,
                                help=param.description,
                            )
                        )
                    else:  # float params are shares in [0, 1] (threshold)
                        ref[param.name] = float(
                            st.number_input(
                                label,
                                min_value=0.0,
                                max_value=1.0,
                                value=float(param.default or 0.0),
                                step=0.05,
                                key=widget_key,
                                help=param.description,
                            )
                        )
        refs.append(ref)
    return refs


def _sweep_validation_area(fields: dict[str, object]) -> SweepSpec | None:
    """Validate the authored fields; render errors or the expansion size.

    ONE validation path (DECISIONS #72): structural errors surface through
    the same :func:`helpers.validation_messages` extraction the Run lab
    uses, semantic errors through the same
    :func:`~pdsim.sweep.spec.sweep_validation_messages` the CLI prints.

    Args:
        fields: The complete authored-values dict.

    Returns:
        The clean, launchable spec — or ``None`` while anything is wrong.
    """
    try:
        spec = sweep_helpers.build_sweep_spec(fields)
    except ValidationError as error:
        for message in helpers.validation_messages(error):
            st.error(message)
        return None
    messages = sweep_validation_messages(spec)
    for message in messages:
        st.error(message)
    if messages:
        return None
    try:
        member_count = len(expand(spec))
    except ValueError as error:
        st.error(str(error))
        return None
    st.success(
        f"This sweep expands to {member_count} member runs."
        + (" That is a lot — consider fewer values per axis." if member_count > 1000 else "")
    )
    yaml_text = sweep_spec_yaml(spec)
    with st.expander("Authored sweep spec (YAML)"):
        st.caption(
            "Exactly what Launch writes and the CLI reads — you could save this "
            "and run `python -m pdsim.sweep <file> --out sweeps` yourself."
        )
        st.code(yaml_text, language="yaml")
        st.download_button(
            "Download spec YAML",
            data=yaml_text,
            file_name=f"{spec.name}.yaml",
            mime="text/yaml",
            key="sweep_download",
        )
    return spec


def _sweep_launch_area(spec: SweepSpec | None) -> None:
    """Render the resume notice and the Launch button; spawn the runner.

    Launch is a DETACHED subprocess of the unchanged headless CLI
    (DECISIONS #72): the authored spec is written to a named file, then
    ``python -m pdsim.sweep <spec> --out <dir>`` is spawned with its output
    captured to a launch log. The Streamlit script thread never blocks, and
    the running sweep is inspectable/killable exactly like a terminal one.

    Args:
        spec: The validated spec, or ``None`` (button disabled).
    """
    name = str(st.session_state.get("sweep_name", "")).strip()
    if name and sweep_helpers.sweep_folder_exists(SWEEPS_DIR, name):
        st.info(
            f"A sweep named '{name}' already exists under {SWEEPS_DIR}/ — launching "
            "will RESUME it: members already finished are skipped and only missing "
            "or failed ones run. Pick a new name (or delete the folder) for a "
            "fresh sweep."
        )
    if st.button("Launch sweep", type="primary", key="sweep_launch", disabled=spec is None):
        assert spec is not None  # the button is disabled otherwise
        SWEEPS_DIR.mkdir(parents=True, exist_ok=True)
        spec_path = sweep_helpers.write_authored_spec(
            spec, sweep_helpers.authored_spec_path(SWEEPS_DIR, spec.name)
        )
        command = sweep_helpers.build_launch_command(spec_path, SWEEPS_DIR)
        log_path = sweep_helpers.launch_log_path(SWEEPS_DIR, spec.name)
        # The child inherits the log handle; closing the parent's copy right
        # after Popen is safe and keeps this script run non-blocking.
        with open(log_path, "w", encoding="utf-8") as log_handle:
            subprocess.Popen(command, stdout=log_handle, stderr=subprocess.STDOUT)
        st.session_state["_launched_sweep"] = spec.name
        st.success(
            f"Launched `{' '.join(command)}` — the app stays responsive while it "
            f"runs. Follow progress with 'Refresh status' below; output goes to "
            f"{log_path}."
        )


def _sweep_monitor_area() -> None:
    """Render the monitor: sweep picker, manual refresh, status, headline chart.

    Deliberately NOT a browser (DECISIONS #74): status plus ONE
    metric-vs-axis chart, read from the sweep's own files. The status file
    is read-only here — the runner subprocess is its sole writer (#70) —
    and refresh is a manual click (a sweep is a minutes-scale job; no
    auto-poll timer, no add-on dependency).
    """
    st.subheader("Monitor")
    names = sweep_helpers.list_sweep_names(SWEEPS_DIR)
    if not names:
        st.info(
            "No sweeps yet. Author and launch one above, or run one headlessly: "
            "`python -m pdsim.sweep examples/sweeps/tft_invasion.yaml`."
        )
        return
    # A widget's own key may only be written before it exists in a script
    # run (the #52 pattern): a just-launched sweep stages its name here.
    staged = st.session_state.pop("_launched_sweep", None)
    if staged in names:
        st.session_state["monitor_sweep"] = staged
    elif st.session_state.get("monitor_sweep") not in names:
        st.session_state["monitor_sweep"] = names[0]
    col_pick, col_refresh = st.columns([4, 1])
    name = col_pick.selectbox(
        "Sweep",
        options=names,
        key="monitor_sweep",
        help="Every sweep folder currently under sweeps/ (most recently active first).",
    )
    col_refresh.button(
        "Refresh status",
        key="monitor_refresh",
        help=(
            "Re-read this sweep's status file (the runner rewrites it after every "
            "member run). The click is the refresh — there is no auto-polling."
        ),
    )
    status = sweep_helpers.read_sweep_status(SWEEPS_DIR, name)
    if status is None:
        st.info(
            "No status file yet — the runner writes sweep_status.json once it "
            "starts. Press 'Refresh status' in a moment."
        )
    else:
        col_total, col_done, col_failed, col_left = st.columns(4)
        col_total.metric("Total members", int(status.get("total", 0)))
        col_done.metric("Completed", int(status.get("completed", 0)))
        col_failed.metric("Failed", int(status.get("failed", 0)))
        col_left.metric("Remaining", int(status.get("running", 0)))
        st.caption(
            f"Started {status.get('started_at', '?')} · last update {status.get('updated_at', '?')}"
        )
        rows = sweep_helpers.status_rows(status)
        if rows:
            st.dataframe(rows, width="stretch")
    log_path = sweep_helpers.launch_log_path(SWEEPS_DIR, name)
    if log_path.is_file():
        with st.expander("Launch log"):
            try:
                st.code(log_path.read_text(encoding="utf-8")[-4000:] or "(empty so far)")
            except OSError as error:
                st.caption(f"Could not read the launch log right now: {error}")
    parquet_path = SWEEPS_DIR / name / "sweep_summary.parquet"
    if parquet_path.is_file():
        meta = None
        try:
            meta = sweep_helpers.read_sweep_summary_meta(SWEEPS_DIR, name)
        except ValueError as error:
            st.error(str(error))
        if meta is not None:
            frame = pd.read_parquet(parquet_path)
            axis_options = [
                column for column in meta.get("axis_columns", []) if column in frame.columns
            ] or ["seed"]
            metric_options = [
                column for column in meta.get("metric_columns", []) if column in frame.columns
            ]
            if metric_options:
                col_axis, col_metric = st.columns(2)
                axis = col_axis.selectbox(
                    "Axis (x)",
                    options=axis_options,
                    key=f"monitor_axis#{name}",  # per-sweep key: switching resets cleanly
                    help="The swept quantity to put on the x-axis.",
                )
                metric = col_metric.selectbox(
                    "Metric (y)",
                    options=metric_options,
                    key=f"monitor_metric#{name}",
                    help="The outcome metric to plot (mean line + replicate-spread band).",
                )
                labels = sweep_helpers.metric_display_labels(meta)
                st.plotly_chart(
                    charts.sweep_metric_chart(frame, axis, metric, metric_label=labels.get(metric)),
                    width="stretch",
                    key=f"monitor_chart#{name}",
                )
    else:
        st.caption("The headline chart appears here once the sweep finishes.")
    st.caption(
        f"Member run folders live under {SWEEPS_DIR / name / 'runs'} — each is an "
        "ordinary, independently reproducible run folder. Rich per-member and "
        "cross-sweep browsing arrives in the follow-on sweep-browser increment."
    )


def _sweep_tab() -> None:
    """Lay out the Sweep tab: author a SweepSpec, launch it, monitor it.

    A thin rendering shell (DECISIONS #38 applied again): every branch worth
    testing lives in :mod:`pdsim.ui.sweep_helpers`. The tab authors the SAME
    ``sweep_spec.yaml`` the CLI consumes and spawns the SAME runner —
    execution stays headless (DECISIONS #72; explainer §4).
    """
    st.markdown(
        "Author a **sweep** — a whole family of runs varied along composition, "
        "parameter, and seed axes — then launch it headlessly and watch its "
        "progress. Execution is the unchanged `python -m pdsim.sweep` CLI, so a "
        "launched sweep can equally be resumed, inspected, or stopped from a "
        "terminal."
    )
    range_error = st.session_state.pop("_sweep_range_error", None)
    if range_error:
        st.error(range_error)

    fields: dict[str, object] = {}
    fields["name"] = st.text_input(
        "Sweep name",
        key="sweep_name",
        help=(
            "A safe lowercase token like 'tft_invasion_app' — it becomes the "
            "sweeps/<name>/ folder name."
        ),
    ).strip()
    base_kind = st.radio(
        "Base configuration",
        options=["From a scenario", "From a config file"],
        key="sweep_base_kind",
        horizontal=True,
        help=(
            "Every member run starts from this configuration; the axes below "
            "override its composition, parameters, and seed per member."
        ),
    )
    if base_kind == "From a scenario":
        scenarios = {info.display_name: info for info in all_scenarios()}
        choice = st.selectbox(
            "Base scenario",
            options=list(scenarios),
            key="sweep_base_scenario",
            help="A curated scenario to use as the base configuration.",
        )
        fields["base_kind"] = "scenario"
        fields["base_scenario"] = scenarios[choice].name
    else:
        fields["base_kind"] = "path"
        fields["base_path"] = st.text_input(
            "Config file path",
            key="sweep_base_path",
            help=(
                "Path to a run config YAML — e.g. the config.yaml inside any recorded run folder."
            ),
        )
    fields["composition"] = _sweep_composition_area(fields)
    fields["parameters"] = _sweep_parameter_axes_area()

    seeds_text = st.text_input(
        "Seeds",
        key="sweep_seeds",
        help=(
            "The random seeds to replicate every combination over. Invasion is a "
            "probability, not a certainty — several seeds per point estimate it "
            "(explainer §3.5)."
        ),
    )
    col_seed_start, col_seed_count, col_seed_fill = st.columns([1, 1, 1])
    seed_start = int(
        col_seed_start.number_input(
            "First seed", min_value=0, value=1, step=1, key="sweep_seed_start"
        )
    )
    seed_count = int(
        col_seed_count.number_input(
            "How many seeds", min_value=1, value=10, step=1, key="sweep_seed_count"
        )
    )
    col_seed_fill.button(
        "Fill seeds",
        key="sweep_seeds_fill",
        on_click=_fill_range_field,
        args=("sweep_seeds", seed_start, seed_start + seed_count - 1, 1),
        help="Write a consecutive seed list into the seeds field; edit freely after.",
    )
    try:
        fields["seeds"] = sweep_helpers.parse_int_list(seeds_text)
    except ValueError as error:
        st.error(str(error))
        fields["seeds"] = []

    fields["metrics"] = _sweep_metrics_area()

    st.divider()
    # A completely untouched tab shows a pointer instead of validation errors.
    authored_anything = any(
        (
            fields["name"],
            fields["composition"],
            fields["parameters"],
            fields["seeds"],
            fields["metrics"],
        )
    )
    if authored_anything:
        spec = _sweep_validation_area(fields)
    else:
        st.caption("Fill in the sections above — validation runs as you author.")
        spec = None
    _sweep_launch_area(spec)
    st.divider()
    _sweep_monitor_area()


# ---------------------------------------------------------------------------
# The Layout painter tab (M11b Phase E4, DECISIONS #186/#187).
#
# A UI TOOL that writes the layout files a config's `structure.layout_file`
# references (#109): the engine only ever reads data (hard rule 4) and a
# recorded run re-runs from its config alone (hard rule 8). Presentation only
# (#38): every branch worth testing lives in the Streamlit-free
# `pdsim.ui.painter_helpers`; the canvas figure is `charts.paint_canvas`. The
# draft is app state under PAINTER_DRAFT_KEY; every mutation is a button or
# selection CALLBACK, which Streamlit runs before the script (the #124
# pre-render window), so the pass that follows paints the changed draft.
# ---------------------------------------------------------------------------


def _stage_painter_note(text: str) -> None:
    """Leave a sentence for the painter tab to show on the next pass.

    Args:
        text: The sentence (a callback cannot render, so it stages instead).
    """
    st.session_state[PAINTER_NOTE_KEY] = text


def _painter_boxes() -> tuple[int, int]:
    """Read the painter's Rows / Columns boxes from session state.

    Returns:
        ``(rows, cols)`` as the boxes hold them (10 × 10 before first use).
    """
    return (
        int(st.session_state.get("painter_rows", 10)),
        int(st.session_state.get("painter_cols", 10)),
    )


def _set_painter_boxes(rows: int, cols: int) -> None:
    """Point the Rows / Columns boxes at a grid that was just loaded.

    Written only inside a callback (the pre-render window), and only when the
    value fits the boxes' bounds — a number input refuses an out-of-range
    session-state value at render time, and a grid above the bound cannot be
    painted anyway (#186 R3 shows its sentence instead).

    Args:
        rows: The loaded grid's rows.
        cols: The loaded grid's columns.
    """
    for key, value in (("painter_rows", rows), ("painter_cols", cols)):
        if 1 <= value <= painter_helpers.MAX_PAINTER_DIMENSION:
            st.session_state[key] = int(value)


def _new_blank_draft() -> None:
    """Start an empty grid from the Rows / Columns boxes (button callback)."""
    rows, cols = _painter_boxes()
    st.session_state[PAINTER_DRAFT_KEY] = painter_helpers.blank_draft(rows, cols)


def _load_draft_from_file() -> None:
    """Load the chosen template onto the canvas (button callback).

    Tokens are validated against the strategy registry through the SAME
    validator the Run lab and the config use, so an unknown name is refused
    with the #122 sentence (line and cell named) and nothing loads. The
    loaded draft counts as saved under its own name — the canvas matches the
    file exactly — so a shipped example can be handed off unedited.
    """
    name = st.session_state.get("painter_source")
    if not name:
        _stage_painter_note("Choose a layout file to load first.")
        return
    try:
        layout = layouts.read_layout_file(layouts.GRID_TEMPLATES_DIR / str(name))
        layouts.validate_layout_file(
            layout,
            rows=layout.rows,
            cols=layout.cols,
            known_strategies=frozenset(all_strategy_names()),
            population_size=layout.occupied_count,
        )
    except (FileNotFoundError, ValueError) as error:
        _stage_painter_note(f"Could not load {name}: {error}")
        return
    draft = painter_helpers.draft_from_layout(layout)
    draft.saved_as = str(name)
    st.session_state[PAINTER_DRAFT_KEY] = draft
    _set_painter_boxes(draft.rows, draft.cols)


def _draft_from_preview() -> None:
    """Copy the Run lab's founding preview onto the canvas (button callback).

    The panel's forward values come from :func:`_panel_lookahead` — the ONE
    lookahead the panel itself uses (#186 R7) — and the composition from the
    ``composition.*`` keys; then the same chain the Structure section's
    preview runs: ``grid_visible`` → ``grid_preview_config`` →
    ``founding_view``. Any failure (a tournament, a well-mixed world, a
    validation message, a missing layout file) is staged as a note for the
    next pass and the canvas is left as it was.
    """
    specs = {spec.key: spec for spec in helpers.panel_specs()}
    lookahead = _panel_lookahead(specs)
    if not helpers.grid_visible(lookahead):
        _stage_painter_note(
            "The Run lab has no founding preview to copy: a grid exists only for an "
            "evolution run on a lattice. Switch the Run lab's mode strip to evolution "
            "and its World structure to 'lattice', or start a blank grid here instead."
        )
        return
    composition = {
        info.name: int(st.session_state.get(f"composition.{info.name}", 0))
        for info in all_strategies()
    }
    try:
        config = helpers.grid_preview_config(lookahead, composition)
        view = layouts.founding_view(config)
    except ValidationError as error:
        _stage_painter_note(
            f"The Run lab's founding preview is waiting on: {helpers.validation_messages(error)[0]}"
        )
        return
    except (FileNotFoundError, ValueError) as error:
        _stage_painter_note(f"The Run lab's founding preview cannot be drawn: {error}")
        return
    if view is None:
        _stage_painter_note("The Run lab has no founding preview to copy right now.")
        return
    draft = painter_helpers.draft_from_placements(view.rows, view.cols, view.placements)
    st.session_state[PAINTER_DRAFT_KEY] = draft
    _set_painter_boxes(draft.rows, draft.cols)


def _resize_draft() -> None:
    """Apply the Rows / Columns boxes to the current grid (button callback)."""
    draft: LayoutDraft | None = st.session_state.get(PAINTER_DRAFT_KEY)
    if draft is None:
        return
    rows, cols = _painter_boxes()
    painter_helpers.resize_draft(draft, rows, cols)


def _current_brush() -> str | None:
    """The brush the radio currently selects, as a machine name (None = eraser).

    Returns:
        The strategy machine name, or ``None`` for the eraser.
    """
    return painter_helpers.brush_from_label(st.session_state.get("painter_brush"))


def _canvas_selection(state: object) -> Mapping[str, object] | None:
    """Pull the ``selection`` mapping out of the canvas widget's state.

    Streamlit hands the canvas's state back as a ``PlotlyState`` — a
    dictionary-like object with a ``selection`` entry that supports both key
    and attribute access; a canvas that has never been touched holds an
    empty selection.

    Args:
        state: ``st.session_state["painter_canvas"]`` as found, or ``None``.

    Returns:
        The selection mapping, or ``None`` when there is none.
    """
    if state is None:
        return None
    if isinstance(state, Mapping):
        selection = state.get("selection")
    else:
        selection = getattr(state, "selection", None)
    return selection if isinstance(selection, Mapping) else None


def _current_tool() -> str:
    """The tool the "Tool" radio currently selects (the Draw tool before it renders).

    Returns:
        One of :data:`painter_helpers.TOOL_OPTIONS`.
    """
    return str(st.session_state.get("painter_tool", painter_helpers.TOOL_DRAW))


def _apply_stroke() -> None:
    """Paint the cells one completed drag chose (the canvas's selection callback).

    Fires once per selection change, before the script (the #124 pre-render
    window), reading the selection under ``painter_canvas``, the tool under
    ``painter_tool``, the brush under ``painter_brush``, and the draft under
    :data:`PAINTER_DRAFT_KEY`. The translation from the drag to site ids is
    the pure :func:`painter_helpers.cells_for_tool` — the Draw tool
    rasterises the lasso PATH as a brush stroke, the Rectangle and Lasso
    tools take the enclosed points (#188); the stroke itself is the pure
    :func:`painter_helpers.apply_brush`. An effective stroke changes the
    figure, so the canvas remounts with a clear selection on the pass that
    follows (the figure spec is part of the element's identity, #184(a)(vii)).
    """
    draft: LayoutDraft | None = st.session_state.get(PAINTER_DRAFT_KEY)
    if draft is None:
        return
    selection = _canvas_selection(st.session_state.get("painter_canvas"))
    cells = painter_helpers.cells_for_tool(_current_tool(), selection, draft.rows, draft.cols)
    painter_helpers.apply_brush(draft, cells, _current_brush())


def _undo_stroke() -> None:
    """Undo the last effective stroke, fill, or clear (button callback)."""
    draft: LayoutDraft | None = st.session_state.get(PAINTER_DRAFT_KEY)
    if draft is not None:
        painter_helpers.undo_stroke(draft)


def _fill_all() -> None:
    """Paint every cell with the current brush (button callback)."""
    draft: LayoutDraft | None = st.session_state.get(PAINTER_DRAFT_KEY)
    if draft is not None:
        painter_helpers.fill_all(draft, _current_brush())


def _clear_all() -> None:
    """Empty every cell (button callback)."""
    draft: LayoutDraft | None = st.session_state.get(PAINTER_DRAFT_KEY)
    if draft is not None:
        painter_helpers.clear_all(draft)


def _painter_handoff(name: str, rows: int, cols: int, size: int, counts: dict[str, int]) -> None:
    """Make a saved painting the Run lab's founding layout (button callback).

    Runs in the #124 pre-render window, where widget session state may be
    written — greyed widgets included (greying blocks USER edits only).
    Writes the mode strip, the world structure, the two limit pairs under the
    keys the nullable-int widget dispatcher uses (``structure.rows#limit`` /
    ``#value`` and the columns pair — verified in this phase's Task 0), the
    initial layout and its file, then the population through the EXISTING
    :func:`_populate_from_layout_file` — #143's one write path, not a second.
    ``_loaded_values`` (the advisory baseline, #176 R5) is deliberately NOT
    touched: an A2 caution after handing off from a well-mixed economy
    scenario is correct — incomes rescale on a lattice.

    Args:
        name: The saved file's bare name (what the Layout file box looks up).
        rows: The painting's rows → "Lattice rows".
        cols: The painting's columns → "Lattice columns".
        size: The painted-agent count → "Population size (N)".
        counts: Machine name → count → the mix widgets.
    """
    st.session_state["run.mode"] = "evolution"
    st.session_state["structure.kind"] = "lattice"
    st.session_state["structure.rows#limit"] = True
    st.session_state["structure.rows#value"] = int(rows)
    st.session_state["structure.cols#limit"] = True
    st.session_state["structure.cols#value"] = int(cols)
    st.session_state["structure.initial_layout"] = "from_file"
    st.session_state["structure.layout_file"] = name
    _populate_from_layout_file(size, counts)
    st.session_state["_load_note"] = (
        f"The painting '{name}' is now the founding layout: evolution mode on a "
        f"{rows} × {cols} lattice, Initial layout 'from_file', and the Population "
        f"section filled in from the file ({size} agents). Press Run to found the run "
        "from it, or edit anything first — the painting is a starting point."
    )


def _painter_readouts(draft: LayoutDraft) -> None:
    """Render the painter's §12-style readouts with their (?) texts.

    Counts come through :func:`painter_helpers.draft_layout_file`, so
    ``occupied_count`` and ``strategy_counts`` are the layout file's own —
    the number shown as "Painted agents" IS the population size the hand-off
    writes (#186 R9).

    Args:
        draft: The current draft.
    """
    layout = painter_helpers.draft_layout_file(draft)
    if draft.dirty:
        saved_as = "unsaved changes"
    elif draft.saved_as is None:
        saved_as = "not saved yet"
    else:
        saved_as = draft.saved_as
    col_sites, col_painted, col_empty, col_saved = st.columns(4)
    col_sites.metric("Sites", f"{draft.site_count}", help=PAINTER_HELP["sites"])
    col_painted.metric("Painted agents", f"{layout.occupied_count}", help=PAINTER_HELP["painted"])
    col_empty.metric(
        "Empty cells", f"{draft.site_count - layout.occupied_count}", help=PAINTER_HELP["empty"]
    )
    col_saved.metric("Saved as", saved_as, help=PAINTER_HELP["saved_as"])
    caption = painter_helpers.counts_caption(draft)
    st.caption(f"Per strategy: {caption}." if caption else "No agents painted yet.")


def _painter_tab() -> None:
    """Lay out the Layout painter: seeds, brush and tools, canvas, readouts, save, hand-off.

    Every editing control renders whether or not a grid exists — greyed,
    never hidden (#34's pattern) — so the tab reads the same at every visit;
    the canvas itself appears once a draft exists and is small enough to
    paint (#186 R3). The readouts live in a container created BEFORE the
    save row and filled AFTER it (the #184 controls-row idiom), so the pass
    that saves already shows the file name under "Saved as".
    """
    st.markdown(
        "Paint a **starting layout** with the mouse: pick a tool and a brush, then "
        "press and drag over the canvas. The painter writes an ordinary layout file "
        "into the `grid_templates/` folder — the same file you could type by hand — "
        "and hands its name to the Run lab, whose config then references the FILE: a "
        "recorded run re-runs from its config alone, and the engine never knows a "
        "mouse was involved."
    )
    note = st.session_state.pop(PAINTER_NOTE_KEY, None)
    if note:
        st.warning(note)
    draft: LayoutDraft | None = st.session_state.get(PAINTER_DRAFT_KEY)
    has_draft = draft is not None

    # --- Seeds: a blank grid, an existing file, or the Run lab's preview.
    # The boxes' defaults travel through session state (not `value=`), so a
    # callback may point them at a loaded grid without a duplicate-default
    # warning.
    st.session_state.setdefault("painter_rows", 10)
    st.session_state.setdefault("painter_cols", 10)
    col_rows, col_cols, col_new = st.columns([1, 1, 2])
    col_rows.number_input(
        "Rows",
        min_value=1,
        max_value=painter_helpers.MAX_PAINTER_DIMENSION,
        step=1,
        key="painter_rows",
        help=PAINTER_HELP["rows"],
    )
    col_cols.number_input(
        "Columns",
        min_value=1,
        max_value=painter_helpers.MAX_PAINTER_DIMENSION,
        step=1,
        key="painter_cols",
        help=PAINTER_HELP["cols"],
    )
    col_new.button(
        "New blank grid", key="painter_new", on_click=_new_blank_draft, help=PAINTER_HELP["new"]
    )
    names = painter_helpers.template_names()
    col_source, col_load, col_preview = st.columns([2, 1, 2])
    col_source.selectbox(
        "Existing layout file",
        options=names,
        key="painter_source",
        help=PAINTER_HELP["source"],
        disabled=not names,
    )
    col_load.button(
        "Load into painter",
        key="painter_load",
        on_click=_load_draft_from_file,
        disabled=not names,
        help=PAINTER_HELP["load"],
    )
    col_preview.button(
        "Start from the Run lab's founding preview",
        key="painter_from_preview",
        on_click=_draft_from_preview,
        help=PAINTER_HELP["from_preview"],
    )

    # --- Delete (#189 R1): the file chosen above, behind a confirmation box.
    # Handled in the script body like Save, so the sentence renders in place
    # at once. The row is filled BUTTON FIRST: a widget's key may be written
    # only before that widget is instantiated in a script run, and the
    # click's own pass must untick the box after removing the file — so the
    # box is read from session state, the button rendered and handled, and
    # the box instantiated last; its column keeps it on the left whatever
    # the render order (the #184 idiom of a slot created early and filled
    # late). The button greys on the next interaction; the `and confirmed`
    # guard makes a click reaching that one render a no-op.
    col_confirm, col_delete, _ = st.columns([2, 1, 2])
    confirmed = bool(st.session_state.get("painter_confirm_delete", False))
    if (
        col_delete.button(
            "Delete layout file",
            key="painter_delete",
            disabled=not names or not confirmed,
            help=PAINTER_HELP["delete"],
        )
        and confirmed
    ):
        chosen = str(st.session_state.get("painter_source") or "")
        try:
            removed = painter_helpers.delete_template(layouts.GRID_TEMPLATES_DIR, chosen)
        except ValueError as error:
            st.error(str(error))
        except OSError as error:
            st.error(
                f"Could not delete {chosen}: {error}. Something is still holding the "
                "file open — close any window showing it, give OneDrive a moment, "
                "then try again."
            )
        else:
            if draft is not None and draft.saved_as == removed.name:
                draft.saved_as = None  # the draft is not the file (#189 R1)
            st.session_state["painter_confirm_delete"] = False
            st.success(
                f"Deleted {removed}. The file leaves the 'Existing layout file' list "
                "from the next interaction on."
            )
    col_confirm.checkbox(
        "Yes, delete this file",
        key="painter_confirm_delete",
        disabled=not names,
        help=PAINTER_HELP["confirm_delete"],
    )
    if draft is None:
        st.caption(
            "No grid yet — press 'New blank grid', 'Load into painter', or 'Start from "
            "the Run lab's founding preview' to begin."
        )
    else:
        rows_box, cols_box = _painter_boxes()
        if (rows_box, cols_box) != (draft.rows, draft.cols):
            # Never an implicit resize (#186 R7): the boxes may differ from
            # the grid; the owner applies them deliberately, or sets them back.
            st.caption(
                f"The boxes say {rows_box} × {cols_box} but the grid on the canvas is "
                f"{draft.rows} × {draft.cols}. Press 'Resize grid' to apply the boxes "
                "(the top-left part of the painting is kept; cells outside the new size "
                "are dropped), or set the boxes back."
            )
            st.button(
                "Resize grid",
                key="painter_resize",
                on_click=_resize_draft,
                help=PAINTER_HELP["resize"],
            )

    # --- Tool, brush, and the three buttons. The tool lives in the figure's
    # own drag mode, so it survives the canvas remount after every stroke.
    tool = st.radio(
        "Tool",
        options=list(painter_helpers.TOOL_OPTIONS),
        key="painter_tool",
        horizontal=True,
        disabled=not has_draft,
        help=PAINTER_HELP["tool"],
    )
    st.radio(
        "Brush",
        options=painter_helpers.brush_options(),
        key="painter_brush",
        horizontal=True,
        disabled=not has_draft,
        help=PAINTER_HELP["brush"],
    )
    col_undo, col_fill, col_clear = st.columns(3)
    col_undo.button(
        "Undo last stroke",
        key="painter_undo",
        on_click=_undo_stroke,
        disabled=draft is None or draft.undo_cells is None,
        help=PAINTER_HELP["undo"],
    )
    col_fill.button(
        "Fill all",
        key="painter_fill",
        on_click=_fill_all,
        disabled=not has_draft,
        help=PAINTER_HELP["fill"],
    )
    col_clear.button(
        "Clear all",
        key="painter_clear",
        on_click=_clear_all,
        disabled=not has_draft,
        help=PAINTER_HELP["clear"],
    )

    # --- The canvas (or the #186 R3 sentence).
    if draft is not None:
        side = charts.paint_cell_side(draft.rows, draft.cols)
        if side is None:
            st.info(PAINTER_TOO_FINE_NOTE)
        else:
            # A chart carries no help=, so the canvas's explanation — the
            # three tools — is the caption above it.
            st.caption(PAINTER_HELP["canvas"])
            # The rebuild cache (#186 R12, adopted in #187): every tab renders
            # on every pass, live-run passes included, and building the
            # 2,500-marker figure cost ≈ 70 ms per pass; the draft resets the
            # cache on every mutation, so the figure is rebuilt exactly when
            # the cells changed and re-serialised otherwise. The tool's drag
            # mode is one layout attribute, set on the cached figure each
            # pass (a no-op when unchanged) rather than a cache key (#188).
            if draft.figure_cache is None:
                draft.figure_cache = charts.paint_canvas(
                    draft.rows, draft.cols, draft.cells, side_px=side
                )
            figure: Figure = draft.figure_cache  # type: ignore[assignment]
            figure.update_layout(dragmode=painter_helpers.dragmode_for_tool(str(tool)))
            st.plotly_chart(
                figure,
                width="content",
                key="painter_canvas",
                on_select=_apply_stroke,
                selection_mode=("points", "box", "lasso"),
            )

    readouts_area = st.container()  # filled after the save row (see the docstring)

    # --- Save. Handled in the script body: the write happens here, then the
    # sentence — success naming the path, or the problem — renders at once.
    col_name, col_replace, col_save = st.columns([2, 1, 1])
    file_name = str(
        col_name.text_input(
            "Layout file name",
            key="painter_file_name",
            disabled=not has_draft,
            help=PAINTER_HELP["file_name"],
        )
    )
    replace = bool(
        col_replace.checkbox(
            "Replace the existing file",
            key="painter_replace",
            disabled=not has_draft,
            help=PAINTER_HELP["replace"],
        )
    )
    if (
        col_save.button(
            "Save layout", key="painter_save", disabled=not has_draft, help=PAINTER_HELP["save"]
        )
        and draft is not None
    ):
        directory = layouts.GRID_TEMPLATES_DIR  # read at call time (#122's home)
        typed = file_name.strip()
        exists = (
            bool(typed) and (directory / painter_helpers.normalise_template_name(typed)).is_file()
        )
        problem = painter_helpers.template_name_problem(typed, exists=exists, replace=replace)
        if problem:
            st.error(problem)
        else:
            path = painter_helpers.save_draft(draft, directory, typed)
            painted = painter_helpers.draft_layout_file(draft).occupied_count
            st.success(
                f"Saved the layout to {path}: {painted} agents on a {draft.rows} × {draft.cols} "
                "grid. 'Use this layout in the Run lab' is now live; the file joins the "
                "'Existing layout file' list from the next interaction on."
            )

    # --- Hand-off, gated per #186 R6 (amendment d); the reason sits beside it.
    problem = painter_helpers.handoff_problem(draft)
    if draft is not None:
        # Always the draft's real values, even while the button is disabled,
        # so nothing inconsistent could ever reach the panel.
        layout = painter_helpers.draft_layout_file(draft)
        handoff_args: tuple[object, ...] = (
            str(draft.saved_as or ""),
            draft.rows,
            draft.cols,
            layout.occupied_count,
            layout.strategy_counts(),
        )
    else:
        handoff_args = ("", 1, 1, 0, {})  # never called: the button is disabled
    col_handoff, col_reason = st.columns([1, 3])
    col_handoff.button(
        "Use this layout in the Run lab",
        key="painter_handoff",
        type="primary",
        disabled=problem is not None,
        on_click=_painter_handoff,
        args=handoff_args,
        help=PAINTER_HELP["handoff"],
    )
    if problem is not None:
        col_reason.caption(problem)

    with readouts_area:
        if draft is not None:
            _painter_readouts(draft)


def main() -> None:
    """Lay out the app: the Run lab, Layout painter, Results browser, and Sweep tabs.

    A live run's next pass is scheduled LAST, after every tab has rendered.
    Streamlit's own STOP — the header's Stop button, or the session
    shutting down — reaches the script as ``StopException`` at its next
    element call; a run in progress is then abandoned the way an
    interrupted script's was (recording discarded, #53/#54), instead of
    leaving an open recorder behind in session memory. A user interaction
    mid-pass is a ``RerunException`` and is deliberately NOT caught: the
    holder survives it and the next pass continues the run (#183 R4).
    """
    try:
        st.title("Evolutionary Prisoner's Dilemma Simulator")
        _apply_pending_load()
        # The Layout painter sits SECOND because it feeds the Run lab (#186
        # OC1); no test indexes tab positions.
        tab_lab, tab_painter, tab_browser, tab_sweep = st.tabs(
            ["Run lab", "Layout painter", "Results browser", "Sweep"]
        )
        with tab_lab:
            _run_lab()
        with tab_painter:
            _painter_tab()
        with tab_browser:
            _results_browser()
        with tab_sweep:
            _sweep_tab()
        _schedule_next_pass()
    except StopException:
        live: LiveRun | None = st.session_state.get(LIVE_RUN_KEY)
        if live is not None:
            _abandon_live_run(live)
        raise


main()
