"""Parameter Registry — the single source of truth for every tunable parameter.

Every knob a user can turn — payoffs, noise, selection intensity, and so on —
is declared exactly once in this module as a :class:`ParameterSpec`. UI widgets,
hover tooltips, the generated parameter documentation, and config validation are
all derived from these declarations, which makes it structurally impossible for
a parameter to exist without a plain-language explanation (hard rule 3 in
``CLAUDE.md``; see ``docs/DESIGN.md`` §5 and DECISIONS #15).

How to add a parameter:
    1. Add one ``register(ParameterSpec(...))`` call below — or, for a
       strategy-specific parameter, in that strategy's own module.
    2. There is no step 2. Defaults, ranges, and help text live here only;
       no other module may re-declare them.

A functional-programming note (a learning thread of this project): the registry
is plain *data* — immutable ``ParameterSpec`` values held in one dict — and
validation is a *pure function* of ``(spec, value)``: same inputs, same result,
no side effects. The only mutable state is the module-level dict, written only
at import time by ``register``.
"""

# `from __future__ import annotations` makes all annotations lazily evaluated
# strings, so type hints never cost anything at runtime and can reference names
# defined later in the file.
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# Python 3.10+ union syntax: `int | float` instead of typing.Union[int, float].
ParamValue = int | float | bool | str | None
"""Every value type a registered parameter may hold."""

ParamKind = Literal["int", "float", "bool", "choice", "str"]
"""The kinds of parameter the registry understands.

``Literal`` (new concept) restricts a value to an exact set of constants — a
lightweight enum that type checkers and validators can reason about.

``"str"`` is free text, and it arrived last for a good reason: a parameter
whose value is not drawn from a declared set cannot be validated by the
registry beyond "it is a string", so it is the weakest kind here and is used
only where the value is genuinely open — a filesystem path (M11a's
``structure.layout_file``). Anything with a knowable set of values is a
``"choice"``.
"""

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
"""Keys are dotted lowercase paths, e.g. ``game.payoff_temptation``."""


# `frozen=True` makes instances immutable (assigning to a field raises), so a
# spec is a constant value that can be shared safely; `slots=True` fixes the
# set of attributes, catching typos like `spec.defualt` at runtime.
@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """Complete declaration of one tunable parameter.

    Attributes:
        key: Unique dotted identifier, e.g. ``"game.payoff_temptation"``.
        kind: Value kind — ``"int"``, ``"float"``, ``"bool"``, or ``"choice"``.
        default: Default value; must itself pass :meth:`validate`.
        label: Short human-readable name for UI widgets.
        description: Plain-language explanation written for a non-expert.
            This is mandatory and is the text users see as a tooltip.
        section: UI grouping, e.g. ``"Game"`` or ``"Dynamics"``.
        minimum: Lower bound (numeric kinds only); inclusive unless
            ``minimum_exclusive`` is set.
        maximum: Upper bound (numeric kinds only); inclusive unless
            ``maximum_exclusive`` is set.
        minimum_exclusive: If True, the value must be strictly above
            ``minimum`` (used e.g. for fractions that must stay > 0).
        maximum_exclusive: If True, the value must be strictly below
            ``maximum`` (used e.g. for probabilities that must stay < 1).
        choices: Allowed values (``"choice"`` kind only).
        nullable: If True, ``None`` is an accepted value (rendered as
            "unlimited" / "off" in the UI).
        learn_more: Optional pointer to background reading for the curious.
    """

    key: str
    kind: ParamKind
    default: ParamValue
    label: str
    description: str
    section: str
    minimum: float | None = None
    maximum: float | None = None
    minimum_exclusive: bool = False
    maximum_exclusive: bool = False
    choices: tuple[str, ...] | None = None
    nullable: bool = False
    learn_more: str | None = None

    def __post_init__(self) -> None:
        """Check that the spec itself is well-formed (fail fast at import time).

        Raises:
            ValueError: If the key is malformed, the description is missing,
                bounds/choices don't match the kind, or the default value
                fails the spec's own validation.
        """
        if not _KEY_PATTERN.match(self.key):
            raise ValueError(
                f"Parameter key {self.key!r} must be a dotted lowercase path "
                "like 'game.payoff_temptation'."
            )
        if not self.description.strip():
            raise ValueError(
                f"Parameter {self.key!r} has no description — hard rule 3 forbids this."
            )
        if self.kind == "choice":
            if not self.choices:
                raise ValueError(f"Choice parameter {self.key!r} must declare its choices.")
        elif self.choices is not None:
            raise ValueError(
                f"Parameter {self.key!r} is {self.kind!r}; only 'choice' takes choices."
            )
        has_bounds = self.minimum is not None or self.maximum is not None
        if self.kind not in ("int", "float") and has_bounds:
            raise ValueError(
                f"Parameter {self.key!r} is {self.kind!r}; bounds apply to numbers only."
            )
        if self.maximum_exclusive and self.maximum is None:
            raise ValueError(f"Parameter {self.key!r} sets maximum_exclusive without a maximum.")
        if self.minimum_exclusive and self.minimum is None:
            raise ValueError(f"Parameter {self.key!r} sets minimum_exclusive without a minimum.")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError(f"Parameter {self.key!r} has minimum > maximum.")
        # The default must satisfy the spec — validated here so a bad
        # declaration explodes at import time, not mid-experiment.
        self.validate(self.default)

    def validate(self, value: ParamValue) -> ParamValue:
        """Check a value against this spec.

        Args:
            value: The candidate value (e.g. from a YAML file or UI widget).

        Returns:
            The validated value; ints are widened to float for ``"float"``
            parameters so callers always get the declared type back.

        Raises:
            ValueError: If the value has the wrong type, is outside the
                declared bounds, or is not one of the declared choices. The
                message names the parameter and the allowed values — it is
                shown to users, so it must be self-explanatory.
        """
        if value is None:
            if self.nullable:
                return None
            raise ValueError(f"{self._name()} does not accept null/None.")

        if self.kind == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{self._name()} expects true or false, got {value!r}.")
            return value

        if self.kind == "str":
            if not isinstance(value, str):
                raise ValueError(f"{self._name()} expects text, got {value!r}.")
            # Blank text is the same statement as "unset" for a path-shaped
            # parameter, so a nullable string normalises "" to None rather
            # than carrying two spellings of empty through the whole system.
            if not value.strip() and self.nullable:
                return None
            return value

        if self.kind == "choice":
            # self.choices is guaranteed non-None here by __post_init__.
            if value not in self.choices:  # type: ignore[operator]
                allowed = ", ".join(repr(c) for c in self.choices)  # type: ignore[union-attr]
                raise ValueError(f"{self._name()} must be one of: {allowed}. Got {value!r}.")
            return value

        # Numeric kinds. Gotcha worth knowing: in Python, bool is a *subclass*
        # of int (True == 1), so `isinstance(True, int)` holds — we must reject
        # bools explicitly or `noise_epsilon: true` would sneak through as 1.
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{self._name()} expects a number, got {value!r}.")
        if self.kind == "int" and not isinstance(value, int):
            raise ValueError(f"{self._name()} expects a whole number, got {value!r}.")

        number = float(value)
        if self.minimum is not None:
            if self.minimum_exclusive and number <= self.minimum:
                raise ValueError(
                    f"{self._name()} must be strictly above {self.minimum}, got {value!r}."
                )
            if not self.minimum_exclusive and number < self.minimum:
                raise ValueError(f"{self._name()} must be at least {self.minimum}, got {value!r}.")
        if self.maximum is not None:
            if self.maximum_exclusive and number >= self.maximum:
                raise ValueError(
                    f"{self._name()} must be strictly below {self.maximum}, got {value!r}."
                )
            if not self.maximum_exclusive and number > self.maximum:
                raise ValueError(f"{self._name()} must be at most {self.maximum}, got {value!r}.")

        return float(value) if self.kind == "float" else value

    def _name(self) -> str:
        """Return the ``key (label)`` prefix used in validation error messages.

        Returns:
            A string like ``"parameter 'game.payoff_temptation' (Temptation payoff (T))"``.
        """
        return f"parameter {self.key!r} ({self.label})"


# ---------------------------------------------------------------------------
# The registry itself: one module-level dict, written only via register().
# Dicts preserve insertion order in Python, so registration order below is
# also the display order for generated UI panels and docs.
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, ParameterSpec] = {}


def register(spec: ParameterSpec) -> ParameterSpec:
    """Add a parameter spec to the registry.

    Args:
        spec: The fully-declared parameter.

    Returns:
        The same spec, so callers (e.g. strategy modules) can keep a handle:
        ``P_GENEROSITY = register(ParameterSpec(...))``.

    Raises:
        ValueError: If a spec with the same key is already registered —
            duplicate declarations are always a bug.
    """
    if spec.key in _REGISTRY:
        raise ValueError(f"Parameter {spec.key!r} is already registered; keys must be unique.")
    _REGISTRY[spec.key] = spec
    return spec


def get_spec(key: str) -> ParameterSpec:
    """Look up a parameter spec by key.

    Args:
        key: Dotted parameter key, e.g. ``"dynamics.mutation_rate"``.

    Returns:
        The registered :class:`ParameterSpec`.

    Raises:
        KeyError: If no parameter with this key exists (the message lists the
            registered keys to make typos easy to spot).
    """
    try:
        return _REGISTRY[key]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Unknown parameter key {key!r}. Registered keys: {known}") from None


def all_specs() -> tuple[ParameterSpec, ...]:
    """Return every registered spec, in registration (= display) order.

    Returns:
        An immutable snapshot of the registry's specs.
    """
    return tuple(_REGISTRY.values())


def validate_value(key: str, value: ParamValue) -> ParamValue:
    """Validate a value against the spec registered under ``key``.

    Convenience composition of :func:`get_spec` and
    :meth:`ParameterSpec.validate`.

    Args:
        key: Dotted parameter key.
        value: Candidate value.

    Returns:
        The validated (possibly type-widened) value.

    Raises:
        KeyError: If the key is unknown.
        ValueError: If the value fails validation.
    """
    return get_spec(key).validate(value)


# ---------------------------------------------------------------------------
# Game — payoff matrix and game-shape rules (docs/DESIGN.md §2.1)
# ---------------------------------------------------------------------------

register(
    ParameterSpec(
        key="game.payoff_temptation",
        kind="float",
        default=5.0,
        minimum=-100.0,
        maximum=100.0,
        label="Temptation payoff (T)",
        section="Game",
        description=(
            "Points a player earns by defecting while the other player cooperates. "
            "This is the 'temptation to cheat' — in a true Prisoner's Dilemma it is "
            "the biggest payoff in the game."
        ),
    )
)

register(
    ParameterSpec(
        key="game.payoff_reward",
        kind="float",
        default=3.0,
        minimum=-100.0,
        maximum=100.0,
        label="Reward payoff (R)",
        section="Game",
        description=(
            "Points each player earns when both cooperate — the 'reward for working "
            "together'. Whether cooperation can survive depends on how R compares to "
            "the temptation to cheat."
        ),
    )
)

register(
    ParameterSpec(
        key="game.payoff_punishment",
        kind="float",
        default=1.0,
        minimum=-100.0,
        maximum=100.0,
        label="Punishment payoff (P)",
        section="Game",
        description=(
            "Points each player earns when both defect. Mutual betrayal leaves both "
            "sides worse off than mutual cooperation would have."
        ),
    )
)

register(
    ParameterSpec(
        key="game.payoff_sucker",
        kind="float",
        default=0.0,
        minimum=-100.0,
        maximum=100.0,
        label="Sucker payoff (S)",
        section="Game",
        description=(
            "Points a player earns by cooperating while the other player defects. "
            "Being the 'sucker' is the worst outcome in a true Prisoner's Dilemma."
        ),
    )
)

register(
    ParameterSpec(
        key="game.enforce_pd_ordering",
        kind="bool",
        default=True,
        label="Enforce PD payoff ordering (T > R > P > S)",
        section="Game",
        description=(
            "Keep the payoffs in the classic Prisoner's Dilemma order: temptation > "
            "reward > punishment > sucker. Turn this off to explore neighboring games "
            "such as Chicken or Stag Hunt, where the order differs."
        ),
    )
)

register(
    ParameterSpec(
        key="game.enforce_alternation_constraint",
        kind="bool",
        default=True,
        label="Enforce no-alternation rule (2R > T + S)",
        section="Game",
        description=(
            "Require that steady mutual cooperation pays more than two players taking "
            "turns exploiting each other. Without this rule (2 x reward > temptation "
            "+ sucker), alternating betrayal becomes the best team tactic, which "
            "changes the character of the game."
        ),
    )
)

# ---------------------------------------------------------------------------
# Matching — who plays whom each generation (docs/DESIGN.md §2.4)
# ---------------------------------------------------------------------------

# `spatial_interaction` is registered FIRST, above `matcher`, deliberately
# (M11a spec Design 11): it is the gate, so `matcher` later greys off a
# sibling that rendered BEFORE it — the clean direction, needing no
# lookahead. The interaction radius and decay it governs live in the
# Structure section (their keys are fixed by the spec's Parameters table).

register(
    ParameterSpec(
        key="matching.spatial_interaction",
        kind="bool",
        default=False,
        label="Spatial interaction",
        section="Matching",
        description=(
            "Whether agents play their NEIGHBOURS instead of the whole "
            "population. Off — the default — is exactly today's behaviour: "
            "the matching scheme below picks partners from the entire "
            "population, and distance plays no part. On: each agent's "
            "partners are sampled from within the interaction radius by the "
            "reach kernel (see the Structure section), and the matching "
            "scheme is NOT consulted — round-robin has no local analogue "
            "(there is no 'every pair plays once' inside overlapping "
            "neighbourhoods), and the population-wide schemes are just this "
            "kernel with unlimited radius. Instead, 'Opponents per agent' "
            "(k) does the work: set k at or above the neighbourhood size to "
            "PLAY ALL YOUR NEIGHBOURS (the classic Hammond–Axelrod "
            "convention), and k simply CLAMPS to the neighbours that "
            "actually exist rather than erroring — a corner cell with 3 "
            "neighbours on a bounded Moore grid plays 3 matches at k = 8, "
            "which is geometry, not a misconfiguration. One counting fact "
            "worth knowing: partners are drawn per agent WITHOUT checking "
            "who already drew whom, so A can pick B while B picks A and the "
            "pair meets twice. At k at-or-above the neighbourhood size each "
            "agent therefore plays roughly TWICE its neighbour count in "
            "matches per generation (its own, plus being drawn by each "
            "neighbour) — income is about double a naive reading. Requires "
            "the lattice world structure: in a well-mixed world there is no "
            "distance to sample within."
        ),
        learn_more=(
            "Playing only your neighbours is what makes clustering matter: "
            "cooperators inside a cluster keep cooperation's benefits among "
            "themselves — spatial reciprocity, the mechanism this milestone "
            "exists for."
        ),
    )
)

register(
    ParameterSpec(
        key="matching.matcher",
        kind="choice",
        default="round_robin",
        choices=("round_robin", "random_k"),
        label="Matching scheme",
        section="Matching",
        description=(
            "How opponents are paired up each generation (or tournament cycle). "
            "'round_robin' means every agent plays every other agent exactly once — "
            "thorough, but the match count grows with the SQUARE of the population. "
            "'random_k' means each agent starts matches against a few randomly drawn "
            "opponents instead, so big populations stay fast. While 'Spatial "
            "interaction' (above) is on, this scheme is NOT consulted — partners "
            "come from the grid via the reach kernel instead, and the widget "
            "greys to say so."
        ),
        learn_more=(
            "Round-robin plays about N²/2 matches per period; random_k plays exactly "
            "N x k. Sampling who meets whom is the first lever for scaling to "
            "thousands of agents (see docs/DESIGN.md §3.1)."
        ),
    )
)

register(
    ParameterSpec(
        key="matching.opponents_per_agent",
        kind="int",
        default=5,
        minimum=1,
        maximum=9_999,
        label="Opponents per agent (k)",
        section="Matching",
        description=(
            "How many randomly drawn opponents each agent starts matches against per "
            "generation (or tournament cycle) when the matching scheme is "
            "'random_k'. Every agent initiates this many matches and can ALSO be "
            "drawn by others, so some agents play more rounds than others — part of "
            "the model, and the 'per round' score view divides that luck away. Must "
            "be smaller than the population size. Ignored under 'round_robin', "
            "where every pair plays anyway."
        ),
        learn_more=(
            "Fewer matches per period is what makes large populations affordable: "
            "N x k matches instead of round-robin's ~N²/2."
        ),
    )
)

# `encounter_mode` renders LAST in the Matching section (M11b Phase C,
# #166/#174) — after the spatial-interaction widgets it refines: the knob
# is live only while the toggle above is on, and its greying-table row
# reads the toggle backwards (no lookahead needed).

register(
    ParameterSpec(
        key="matching.encounter_mode",
        kind="choice",
        default="per_initiator",
        choices=("per_initiator", "per_pair"),
        label="Encounter mode",
        section="Matching",
        description=(
            "Under spatial interaction each agent initiates its own partner "
            "draws, so two neighbours that draw each other play twice per "
            "generation — once in each initiator seat. 'per_initiator' keeps "
            "every drawn match (the default and the historical behaviour; the "
            "doubling was measured in the engine's validation). 'per_pair' "
            "collapses duplicate pairs after the draws, so each pair plays at "
            "most once per generation. Only WHICH matches run changes — the "
            "random draws themselves are identical in both modes. Live only "
            "while spatial interaction is on; the well-mixed matchers are "
            "untouched."
        ),
    )
)

# ---------------------------------------------------------------------------
# Match — how long a match lasts, and noise (docs/DESIGN.md §2.5-2.6)
# ---------------------------------------------------------------------------

register(
    ParameterSpec(
        key="match.length_mode",
        kind="choice",
        default="fixed",
        choices=("fixed", "continuation"),
        label="Match length mode",
        section="Match",
        description=(
            "How the length of each match is decided. 'fixed' plays an exact number "
            "of rounds. 'continuation' flips a weighted coin after every round to "
            "decide whether the match continues — so players can never be sure which "
            "round is the last."
        ),
        learn_more=(
            "With a known final round, defecting at the end is 'safe', and that logic "
            "unravels backwards (backward induction). Probabilistic continuation "
            "models 'the shadow of the future' (Axelrod)."
        ),
    )
)

register(
    ParameterSpec(
        key="match.rounds_per_match",
        kind="int",
        default=50,
        minimum=1,
        maximum=10_000,
        label="Rounds per match",
        section="Match",
        description=(
            "Number of rounds in every match when the match length mode is 'fixed'. "
            "Longer matches give reciprocal strategies (like Tit for Tat) more time "
            "to build cooperation."
        ),
    )
)

register(
    ParameterSpec(
        key="match.continuation_probability",
        kind="float",
        default=0.98,
        minimum=0.0,
        maximum=1.0,
        maximum_exclusive=True,
        label="Continuation probability (w)",
        section="Match",
        description=(
            "Chance the match continues after each round when the match length mode "
            "is 'continuation'. Higher values mean longer matches on average — the "
            "expected length is 1 / (1 - w), so 0.98 gives about 50 rounds. Must be "
            "below 1, or matches would never end."
        ),
        learn_more="w is the 'shadow of the future': how much tomorrow matters today.",
    )
)

register(
    ParameterSpec(
        key="match.noise_epsilon",
        kind="float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        label="Execution noise (ε)",
        section="Match",
        description=(
            "Chance that an agent's action is accidentally flipped — it meant to "
            "cooperate but defected, or vice versa. Even a little noise punishes "
            "unforgiving strategies (Grim Trigger) and rewards forgiving ones "
            "(Generous Tit for Tat, Pavlov)."
        ),
        learn_more="Known in game theory as 'trembling hand' error.",
    )
)

# ---------------------------------------------------------------------------
# Population — size, memory (docs/DESIGN.md §2.2)
# ---------------------------------------------------------------------------

register(
    ParameterSpec(
        key="population.size",
        kind="int",
        default=100,
        minimum=2,
        maximum=10_000,
        label="Population size (N)",
        section="Population",
        description=(
            "Number of agents the run STARTS with. Under 'imitation' reproduction "
            "it stays constant across generations: selection always produces "
            "exactly this many agents. In the 'energy_economy' reproduction mode "
            "the population changes from generation to generation — this is only "
            "the founding count. Practical note: a few hundred agents is the "
            "comfortable limit for live visualization."
        ),
    )
)

register(
    ParameterSpec(
        key="population.memory_depth",
        kind="int",
        default=None,
        minimum=1,
        nullable=True,
        label="Memory depth",
        section="Population",
        description=(
            "How many past rounds against each specific opponent a strategy may "
            "remember. Leave empty for unlimited memory. This is an experimental "
            "constraint — most classic strategies only look at the previous round "
            "anyway."
        ),
    )
)

# ---------------------------------------------------------------------------
# Structure — the shape of the world (docs/DESIGN.md §2.12; M11a)
# Sits between Population and Dynamics so every auto value's source renders
# above it: N is set in Population, rows/cols auto-derive from N here, and K
# (Dynamics) will auto-derive from the site count (spec Design 11).
# ---------------------------------------------------------------------------

register(
    ParameterSpec(
        key="structure.kind",
        kind="choice",
        default="well_mixed",
        choices=("well_mixed", "lattice"),
        label="World structure",
        section="Structure",
        description=(
            "The shape of the world the population lives in. 'well_mixed': the "
            "classic aspatial world of every earlier version — there are no "
            "places, every agent can meet every other, and distance does not "
            "exist. 'lattice': the population lives on a rectangular grid of "
            "sites, each site holding at most one agent; who an agent plays and "
            "where its newborn children are placed become LOCAL questions, "
            "decided by grid distance. One honest caveat, stated where the "
            "choice is made: under synchronous 'imitation' reproduction the "
            "agent a player compares its score against is still drawn from the "
            "WHOLE population even on a lattice — interaction partners and "
            "newborn placement go local, strategy imitation stays global."
        ),
        learn_more=(
            "Putting a population on a grid is what lets cooperators survive by "
            "clustering — neighbours mostly meet neighbours, so cooperation's "
            "benefits stay among cooperators instead of leaking to everyone."
        ),
    )
)

register(
    ParameterSpec(
        key="structure.rows",
        kind="int",
        default=None,
        minimum=1,
        nullable=True,
        label="Lattice rows",
        section="Structure",
        description=(
            "Number of rows in the lattice grid. Leave empty for automatic "
            "sizing: the grid becomes the most-square rectangle whose cell "
            "count exactly equals the population size (400 agents give a "
            "20 x 20 grid; 60 give 6 x 10). A PRIME population size can only "
            "factorise as a single line of cells (101 gives 1 x 101) — a "
            "legitimate one-dimensional world, not a bug. If you set only one "
            "dimension, the other resolves to the smallest count that fits the "
            "whole population. Ignored under the 'well_mixed' structure."
        ),
    )
)

register(
    ParameterSpec(
        key="structure.cols",
        kind="int",
        default=None,
        minimum=1,
        nullable=True,
        label="Lattice columns",
        section="Structure",
        description=(
            "Number of columns in the lattice grid. Leave empty for automatic "
            "sizing: the grid becomes the most-square rectangle whose cell "
            "count exactly equals the population size (400 agents give a "
            "20 x 20 grid; 60 give 6 x 10). A PRIME population size can only "
            "factorise as a single line of cells (101 gives 1 x 101) — a "
            "legitimate one-dimensional world, not a bug. If you set only one "
            "dimension, the other resolves to the smallest count that fits the "
            "whole population. Ignored under the 'well_mixed' structure."
        ),
    )
)

register(
    ParameterSpec(
        key="structure.neighbourhood_shape",
        kind="choice",
        default="moore",
        choices=("moore", "von_neumann"),
        label="Neighbourhood shape",
        section="Structure",
        description=(
            "Which cells count as a cell's neighbours — and, with that, what "
            "DISTANCE means on the grid, because the shape IS the distance "
            "metric. 'moore': the 8 surrounding cells are neighbours; a "
            "diagonal step counts as distance 1, so distance is the LARGER of "
            "the row and column differences (Chebyshev distance). "
            "'von_neumann': only the 4 orthogonal cells (up, down, left, "
            "right) are neighbours; a diagonal step costs 2, because distance "
            "is the row difference PLUS the column difference (Manhattan "
            "distance). This one choice governs birth reach and interaction "
            "reach TOGETHER: every 'how far away is that site' in the world is "
            "measured with the metric chosen here, never per feature."
        ),
        learn_more=(
            "The two classic cellular-automaton neighbourhoods, named after "
            "Edward F. Moore and John von Neumann."
        ),
    )
)

register(
    ParameterSpec(
        key="structure.boundary",
        kind="choice",
        default="torus",
        choices=("torus", "bounded"),
        label="Grid boundary",
        section="Structure",
        description=(
            "What happens at the edge of the grid. 'torus': the world wraps "
            "around — the left edge is adjacent to the right edge and the top "
            "to the bottom, so there is no rim and every cell has exactly the "
            "same number of neighbours. 'bounded': the grid has hard edges — "
            "corner and edge cells have FEWER neighbours than interior cells "
            "(a corner keeps 3 of Moore's 8, or 2 of von Neumann's 4). The "
            "default is 'torus' because uniform degree removes an edge "
            "artifact: how easily cooperation survives depends on how many "
            "neighbours a cell has, so on a bounded grid the corners become "
            "spuriously friendly to cooperation — an effect of the map's "
            "edge, not a finding about the model. Choose 'bounded' "
            "deliberately when a hard edge is itself part of what you want to "
            "model (a coastline, a walled world)."
        ),
    )
)

register(
    ParameterSpec(
        key="structure.initial_layout",
        kind="choice",
        default="random",
        choices=(
            "random",
            "checkerboard",
            "stripes",
            "blocks",
            "patches",
            "central_block",
            "from_file",
        ),
        label="Initial layout",
        section="Structure",
        description=(
            "How the starting population is ARRANGED on the grid. It decides "
            "arrangement only — how many agents of each strategy there are is "
            "already fixed by the population mix, and the layout simply deals "
            "that fixed deck onto cells. This choice matters enormously on a "
            "lattice: whether cooperators start clustered together or "
            "scattered among defectors can decide whether cooperation survives "
            "at all. 'random': agents are scattered over the whole grid in "
            "random order — the closest spatial analogue of the classic "
            "well-mixed world, and the honest baseline. 'checkerboard': "
            "strategies are dealt one cell at a time in rotation, so agents "
            "are interleaved as thoroughly as the counts allow — with two "
            "equal-sized strategies this is the literal chessboard, and with "
            "four unequal ones it is still the maximum-mixing arrangement. "
            "This is the ANTI-CLUSTER baseline: if cooperation survives here, "
            "it is not surviving by clustering. 'stripes': each strategy's "
            "whole count is dealt as one consecutive run along a row-by-row "
            "sweep, giving broad bands. Because the run ends where the COUNT "
            "ends rather than where a row ends, a 'stripe' can be a fragment "
            "of a row — that is the arrangement working as intended, not a "
            "glitch. 'blocks': the same consecutive-run dealing, but along a "
            "tile-by-tile sweep, so each strategy occupies a chunky "
            "two-dimensional region instead of horizontal bands. 'patches': "
            "one randomly placed seed cell per strategy, with each patch then "
            "growing outward until its quota is used up — the most natural "
            "irregular clusters. Only the seed placement is random; the growth "
            "is fixed. 'central_block': the population fills a centred "
            "rectangle — the most-square rectangle holding exactly the "
            "population count (a prime-sized population makes a single line) "
            "— and the rest of the grid is left EMPTY: the expanding-frontier "
            "setup, where what you are watching is a population growing into "
            "empty space. NOTE: with the grid dimensions left on automatic "
            "the world holds exactly as many sites as agents, so the "
            "rectangle IS the whole grid and the picture is identical to "
            "'stripes' — set Lattice rows and columns larger than the "
            "population to see the empty frame. 'from_file': read the exact "
            "arrangement, cell by cell, from a layout file you wrote (see the "
            "layout file parameter). Its tokens are strategy MACHINE NAMES "
            "exactly as registered — the app lists the current spellings "
            "beside the layout file box, and the grid_templates folder ships "
            "worked examples. Ignored under the 'well_mixed' structure."
        ),
        learn_more=(
            "Starting arrangement is a genuine experimental variable in "
            "spatial game theory, not a cosmetic one: the classic result that "
            "cooperators survive by clustering is a statement about "
            "arrangement, so comparing 'patches' against 'checkerboard' at "
            "identical composition isolates exactly that effect."
        ),
    )
)

register(
    ParameterSpec(
        key="structure.layout_file",
        kind="str",
        default=None,
        nullable=True,
        label="Layout file",
        section="Structure",
        description=(
            "The layout file that paints the starting world cell by cell. "
            "Read only when the initial layout is 'from_file'; leave it empty "
            "otherwise. A BARE FILENAME (no slash or backslash) is looked up "
            "in the project's grid_templates folder, which ships with a "
            "README and worked examples; a value containing a path separator, "
            "or an absolute path, is used exactly as given. The file is a "
            "picture of the grid: a short header of 'kind: lattice_grid', "
            "'rows:' and 'cols:' lines, then one line per grid row, one token "
            "per cell — separated by spaces, or by commas (if any grid line "
            "contains a comma, the whole file is read comma-separated). A "
            "token is either a strategy's MACHINE NAME spelled exactly as "
            "registered (such as 'always_defect' — the app lists the current "
            "names beside this box) or a full stop '.' for a cell left empty; "
            "in the comma style an empty field between commas is an error, "
            "not an empty cell. The file's row and column counts must match "
            "the grid's, and it must place exactly as many agents as the "
            "population size — but WHICH strategy sits in each cell is "
            "entirely the file's decision, so the population-mix widgets no "
            "longer control the arrangement or the mixture. When the "
            "Population section disagrees with the file, the app points out "
            "the difference and offers to fill the section in from the file "
            "with one click, so nothing needs retyping. A copy of the file "
            "is saved into the run folder, so a recorded run can always be "
            "re-run even if the original file later moves or changes."
        ),
    )
)

# --- The local-birth knobs (M11a Phase C). The birth pair parameterises the
# reach kernel for newborn placement — and, under the fixed-size Moran mode,
# for the competition to fill a freed site (spec Design 7). The contest
# decides ordering where several synchronous births resolve at once.

register(
    ParameterSpec(
        key="structure.birth_radius",
        kind="int",
        default=1,
        minimum=1,
        nullable=True,
        label="Birth radius (R)",
        section="Structure",
        description=(
            "How far from its parent a newborn can be placed, in grid "
            "distance (the neighbourhood shape above decides what distance "
            "means). At birth, the empty sites within this radius of the "
            "parent are the candidate homes; if EVERY site in reach is "
            "occupied, the parent cannot breed this round — it pays "
            "nothing, keeps its energy, stays eligible, and simply tries "
            "again next generation (the Economy panel counts such parents "
            "— as INFEASIBLE under the synchronous clock, where they are "
            "not even ranked for a seat, and as BLOCKED under the "
            "asynchronous clock — so this reads as the mechanism it is, "
            "not as a stall). At 1 — the "
            "default — children land right next to their parents, the "
            "classic Hammond–Axelrod setting and the one that makes family "
            "clusters form. Leave empty for unlimited reach: a child can "
            "then land on any empty site on the grid. IMPORTANT under the "
            "fixed-size ('fixed_n' Moran) population mode: this radius and "
            "the decay below define WHO COMPETES to fill a freed site — the "
            "set of neighbours whose fitness contest decides the "
            "replacement — which is exactly the neighbour count k that the "
            "b/c > k cooperation threshold counts. That is why the pair "
            "stays live under 'fixed_n' even though nobody breeds freely "
            "there. Ignored under the 'well_mixed' structure."
        ),
        learn_more=(
            "Hammond & Axelrod 2006 place offspring in the immediate "
            "neighbourhood; Ohtsuki et al. 2006 derive b/c > k, where k "
            "counts the competitors for a vacated site."
        ),
    )
)

register(
    ParameterSpec(
        key="structure.birth_decay",
        kind="float",
        default=0.0,
        minimum=0.0,
        maximum=20.0,
        label="Birth decay (β)",
        section="Structure",
        description=(
            "How steeply a newborn's placement prefers sites CLOSER to its "
            "parent, within the birth radius. This is the decay β of the "
            "reach kernel: a candidate site at distance d is weighted "
            "exp(−β·d). At 0 — the default — every empty site within the "
            "radius is equally likely; higher values keep children ever "
            "closer to home even where the radius technically allows more "
            "distance. IRRELEVANT at a birth radius of 1: all candidates "
            "then sit at the same distance, so every β gives the same "
            "behaviour. Under the fixed-size ('fixed_n' Moran) population "
            "mode this decay also weights the competition for a freed site "
            "— nearer neighbours are likelier to win it. Ignored under the "
            "'well_mixed' structure."
        ),
    )
)

register(
    ParameterSpec(
        key="structure.placement_contest",
        kind="choice",
        default="random",
        choices=("random", "energy_priority"),
        label="Placement contest",
        section="Structure",
        description=(
            "Who places first when several parents breed at the same "
            "generation boundary — the order matters on a lattice, because "
            "an earlier parent can take the last empty site in a "
            "neighbourhood another parent wanted. 'random' — the default — "
            "shuffles the admitted parents once and lets each place in "
            "turn: reproduction order is luck (the Hammond–Axelrod "
            "convention), so wealth decides only WHO MAY BREED (via the "
            "reproduction threshold), never who wins contested ground. "
            "'energy_priority' lets the RICHEST admitted parent place "
            "first: an advantage that COMPOUNDS spatially — a good "
            "neighbourhood raises earnings, which wins more contested "
            "cells, which acquires more good territory — a substantive "
            "modelling claim to switch on deliberately, not to inherit "
            "silently. Only matters under a synchronous energy-economy run "
            "on a lattice; nowhere else is this shuffle drawn (a well-mixed "
            "world has no cells to contest). Under the asynchronous clock "
            "several births CAN resolve in one event — the whole eligible "
            "set is admitted per event and placed in ascending agent-id "
            "order, so a shared last empty site goes to the lower id; "
            "whether that should instead be one birth per event is held as "
            "an open question for M12 scoping — but this setting is not "
            "consulted there."
        ),
    )
)

# --- The local-interaction knobs (M11a Phase D). The interaction pair
# parameterises the SAME reach kernel a second time — birth and interaction
# are independent dials on the one structure (spec Design 2) — and both are
# consulted only while `matching.spatial_interaction` (the gate, in the
# Matching section) is on.

register(
    ParameterSpec(
        key="structure.interaction_radius",
        kind="int",
        default=1,
        minimum=1,
        nullable=True,
        label="Interaction radius (R)",
        section="Structure",
        description=(
            "How far away a potential match PARTNER can be, in grid distance "
            "(the neighbourhood shape above decides what distance means). "
            "This is the hard edge of 'who is reachable as a partner': "
            "agents beyond it are simply never met. At 1 — the default — "
            "partners come from the immediate neighbourhood only, the "
            "classic Hammond–Axelrod setting. Leave empty for unlimited "
            "reach: every agent on the grid is then a candidate, with only "
            "the decay below expressing locality. Only consulted while "
            "'Spatial interaction' (in the Matching section) is on; ignored "
            "otherwise, and ignored under the 'well_mixed' structure."
        ),
    )
)

register(
    ParameterSpec(
        key="structure.interaction_decay",
        kind="float",
        default=0.0,
        minimum=0.0,
        maximum=20.0,
        label="Interaction decay (β)",
        section="Structure",
        description=(
            "How steeply partner choice prefers CLOSER agents, within the "
            "interaction radius. This is the decay β of the reach kernel: a "
            "candidate at distance d is weighted exp(−β·d). At 0 — the "
            "default — every reachable agent is equally likely (a uniform "
            "disc); higher values make distant partners reachable but "
            "increasingly unlikely. IRRELEVANT at an interaction radius of "
            "1: all candidates then sit at the same distance, so every β "
            "gives the same behaviour. Only consulted while 'Spatial "
            "interaction' (in the Matching section) is on; ignored "
            "otherwise, and ignored under the 'well_mixed' structure."
        ),
    )
)

# ---------------------------------------------------------------------------
# Movement — agents relocating on the grid (docs/DESIGN.md §2.12; M11b
# Phase B, DECISIONS #165/#172). The third parameterisation of the reach
# kernel: after "where a child lands" and "who you play", "where you may
# walk to". Registered after Structure so the panel and the docs render it
# there. Every movement draw is gated on `movement.rate > 0` AND lattice +
# energy economy (sync `energy_economy`, async `variable_n`): at the default
# rate 0 — movement off — a run consumes zero additional draws and every
# pre-M11b config re-runs identically (hard rule 8).
# ---------------------------------------------------------------------------

register(
    ParameterSpec(
        key="movement.rate",
        kind="float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        label="Movement rate",
        section="Movement",
        description=(
            "How likely each agent is to attempt ONE move per period — a "
            "probability from 0 to 1. At 0 — the default — nobody ever "
            "moves: agents stay on the site they were born (or dealt) onto, "
            "exactly as before movement existed, so an older configuration "
            "re-runs identically. At 1 every agent attempts a move every "
            "period. Under the synchronous (generational) clock the "
            "attempts happen at the END of each generation's demographic "
            "boundary — after that generation's deaths and births, so "
            "movers see the freshest vacancies and every generation's "
            "matches are played from the positions the previous boundary "
            "settled (generation 0 plays from the founding layout as dealt "
            "or painted); a child born in that boundary may move in it too. "
            "Under the asynchronous (event-time) clock the attempt happens "
            "when an agent is activated as the focal of an event, "
            "immediately before it plays its matches — so the same number "
            "means the same expected moves per agent per generation(-"
            "equivalent) under both clocks. A move goes to an EMPTY site "
            "within the movement radius below (weighted by the movement "
            "decay); an agent with no empty site in reach simply stays put "
            "— the Economy panel counts such BLOCKED moves so a crowded "
            "grid reads as what it is. Movement is free (no energy cost) "
            "and blind to strategy: it is population dynamics, not a "
            "decision the strategies make. Only consulted in the ENERGY "
            "ECONOMY on a LATTICE — under 'energy_economy' reproduction on "
            "the synchronous clock, or 'variable_n' on the asynchronous "
            "clock. Ignored under 'well_mixed' (nowhere to go), under "
            "'imitation' reproduction (no demographic boundary to host the "
            "step), and under the fixed-size ('fixed_n' Moran) population "
            "(its grid is completely full by construction — every move "
            "would be blocked)."
        ),
    )
)

register(
    ParameterSpec(
        key="movement.radius",
        kind="int",
        default=1,
        minimum=1,
        nullable=True,
        label="Movement radius (R)",
        section="Movement",
        description=(
            "How far a single move can carry an agent, in grid distance (the "
            "neighbourhood shape in the Structure section decides what "
            "distance means). At a move, the EMPTY sites within this radius "
            "of the agent's current site are the candidate destinations — "
            "the agent's own site is occupied and never a candidate, so a "
            "move is always a genuine relocation. If every site in reach is "
            "occupied the move is BLOCKED: the agent stays put and tries "
            "again whenever its next attempt comes (the Economy panel "
            "counts blocked moves). At 1 — the default — an agent hops to "
            "an adjacent empty cell: the smallest, most local step, and the "
            "one that lets clusters erode gradually rather than scatter. "
            "Leave empty for unlimited reach: a mover can then land on any "
            "empty site on the grid, with only the decay below expressing "
            "locality. Only consulted while the movement rate above is "
            "positive and movement applies (energy economy on a lattice); "
            "ignored otherwise."
        ),
    )
)

register(
    ParameterSpec(
        key="movement.decay",
        kind="float",
        default=0.0,
        minimum=0.0,
        maximum=20.0,
        label="Movement decay (β)",
        section="Movement",
        description=(
            "How steeply a move prefers empty sites CLOSER to the agent's "
            "current position, within the movement radius. This is the "
            "decay β of the reach kernel: a candidate site at distance d is "
            "weighted exp(−β·d). At 0 — the default — every empty site "
            "within the radius is equally likely; higher values keep moves "
            "short even where the radius technically allows a longer jump. "
            "IRRELEVANT at a movement radius of 1: all candidates then sit "
            "at the same distance, so every β gives the same behaviour. "
            "Only consulted while the movement rate above is positive and "
            "movement applies (energy economy on a lattice); ignored "
            "otherwise."
        ),
    )
)

# ---------------------------------------------------------------------------
# Dynamics — selection and mutation (docs/DESIGN.md §2.7)
# ---------------------------------------------------------------------------

register(
    ParameterSpec(
        key="dynamics.generations",
        kind="int",
        default=200,
        minimum=1,
        maximum=100_000,
        label="Generations",
        section="Dynamics",
        description=(
            "How many generations the simulation runs. In each generation everyone "
            "plays their matches, scores are tallied, and the next generation is "
            "formed by selection and mutation."
        ),
    )
)

# Registered immediately after dynamics.generations and BEFORE the selection
# family on purpose (M10a): the app renders widgets in registry order, and the
# greying of the selection/accounting widgets keys off this widget's value —
# it must already be gathered when they render (DECISIONS #34 pattern).
register(
    ParameterSpec(
        key="dynamics.reproduction_mode",
        kind="choice",
        default="imitation",
        choices=("imitation", "energy_economy"),
        label="Reproduction mode",
        section="Dynamics",
        description=(
            "How the next generation comes to be. 'imitation' is the classic "
            "setting: the population size never changes — each slot in the next "
            "generation copies a parent's strategy, chosen by the selection rule "
            "below. 'energy_economy' replaces copying with living: agents hold a "
            "stock of energy, earn it by playing, pay it to stay alive, and "
            "reproduce when they can afford to — nobody copies anyone, the "
            "population grows and shrinks (and can even go extinct), and "
            "differential survival IS the selection. Switching to "
            "'energy_economy' makes the selection rule and score accounting "
            "settings inert (they stay visible but are ignored)."
        ),
        learn_more=(
            "The two classic families of evolutionary dynamics: imitation "
            "(cultural copying, e.g. the Fermi rule) versus birth-death dynamics "
            "(organisms with metabolisms, e.g. Epstein & Axtell's Sugarscape)."
        ),
    )
)

# Registered right after dynamics.reproduction_mode on purpose (M10b): the
# widget-order rule again — async-mode greying keys off this value, so it
# must be gathered before the widgets it greys render (DECISIONS #34).
register(
    ParameterSpec(
        key="dynamics.time_model",
        kind="choice",
        default="synchronous",
        choices=("synchronous", "asynchronous"),
        label="Time model",
        section="Dynamics",
        description=(
            "The clock the simulation runs on. 'synchronous' is the classic "
            "generational clock: everyone plays their matches, then the whole "
            "population is updated at once at the generation boundary — exactly "
            "the behaviour of every earlier version. 'asynchronous' dissolves "
            "the generation: time advances one small event at a time — one "
            "agent is activated, plays its matches, and any births or deaths "
            "happen immediately, not at a boundary. The charts then count "
            "'generation-equivalents': one activation per current member of "
            "the population, on average, adds up to one generation's worth of "
            "time, so the two clocks stay comparable. Under 'asynchronous' the "
            "reproduction mode, selection rule, and score accounting settings "
            "are ignored (an asynchronous run is always birth-death dynamics), "
            "and the matching scheme is ignored too — partners are drawn one "
            "activation at a time, using the opponents-per-agent count."
        ),
        learn_more=(
            "Whether everyone updates at once or one at a time is a classic "
            "modelling choice that can change outcomes (Huberman & Glance "
            "1993). The asynchronous clock here follows the Moran-process "
            "convention: N single-agent events make one generation."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.selection_rule",
        kind="choice",
        default="fermi",
        choices=("fermi", "proportional", "tournament_k", "truncation", "threshold_cloning"),
        label="Selection rule",
        section="Dynamics",
        description=(
            "How the next generation is chosen from the current one. 'fermi' "
            "(pairwise comparison) repeatedly picks two random agents and has the "
            "first copy the second's strategy with a probability that grows with "
            "the score difference and the selection intensity. 'proportional' "
            "(roulette wheel) draws each new agent's parent with a weight based on "
            "how far its score sits above the generation's worst. 'tournament_k' "
            "holds a mini-contest for every slot: a few randomly drawn candidates, "
            "the best scorer wins — despite the name, this has NOTHING to do with "
            "the tournament RUN MODE (which switches selection off entirely); it "
            "is simply this rule's traditional name. 'truncation' (elitist) only "
            "copies from the top slice of scorers. 'threshold_cloning' keeps every "
            "agent scoring above a threshold and replaces the rest with copies of "
            "those survivors."
        ),
        learn_more=(
            "Fermi comes from statistical physics; roulette and tournament "
            "selection from genetic algorithms; truncation from selective breeding."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.selection_beta",
        kind="float",
        default=1.0,
        minimum=0.0,
        maximum=1_000.0,
        label="Selection intensity (β)",
        section="Dynamics",
        description=(
            "How strongly scores drive selection when the selection rule is "
            "'fermi'. At 0, scores are ignored and strategies spread by pure luck "
            "(random drift). The higher the value, the more reliably "
            "higher-scoring strategies get copied. This is the main knob for "
            "sweeping between 'luck' and 'meritocracy'. Ignored under the other "
            "selection rules."
        ),
        learn_more=(
            "This is the temperature-like β in the Fermi update rule from statistical physics."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.selection_tournament_k",
        kind="int",
        default=3,
        minimum=2,
        maximum=10_000,
        label="Tournament size (k)",
        section="Dynamics",
        description=(
            "How many randomly drawn candidates compete for each next-generation "
            "slot when the selection rule is 'tournament_k'. The best scorer among "
            "the candidates wins the slot. Bigger values mean stronger selection "
            "pressure — with k equal to the whole population, the top scorer wins "
            "every slot. Cannot exceed the population size. Not related to the "
            "tournament run mode. Ignored under other selection rules."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.selection_elite_fraction",
        kind="float",
        default=0.2,
        minimum=0.0,
        minimum_exclusive=True,
        maximum=1.0,
        label="Elite fraction (q)",
        section="Dynamics",
        description=(
            "The top share of scorers that the 'truncation' selection rule copies "
            "from. At 0.2, only the best-scoring 20% of agents can be parents — "
            "every next-generation agent is a copy of someone from that elite. At "
            "least one agent always qualifies, and 1.0 means everyone does. Must "
            "be above 0. Ignored under other selection rules."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.selection_threshold_multiplier",
        kind="float",
        default=1.0,
        minimum=0.0,
        maximum=10.0,
        label="Survival threshold (x mean score)",
        section="Dynamics",
        description=(
            "The survival bar for the 'threshold_cloning' selection rule, as a "
            "multiple of the generation's mean score. Agents at or above the bar "
            "keep their strategies; everyone else becomes a copy of a random "
            "survivor. At 1.0, scoring at least average means survival; higher "
            "values are stricter (if nobody clears the bar, the top scorers "
            "survive). Ignored under other selection rules."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.mutation_rate",
        kind="float",
        default=0.01,
        minimum=0.0,
        maximum=1.0,
        label="Mutation rate (μ)",
        section="Dynamics",
        description=(
            "Chance that a newly created agent ignores the strategy it was supposed "
            "to copy and instead adopts a random strategy from the enabled roster. "
            "A small rate keeps 'extinct' strategies able to reappear; 0 means "
            "perfect copying."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.score_accounting",
        kind="choice",
        default="per_generation",
        choices=("per_generation", "sliding_window", "exponential_discount"),
        label="Score accounting",
        section="Dynamics",
        description=(
            "Which score selection looks at. 'per_generation' uses only the "
            "current generation's score — the classic setting. 'sliding_window' "
            "uses the average of the last few generations, so one lucky or unlucky "
            "generation matters less. 'exponential_discount' uses a running "
            "average in which older generations fade out gradually. Only what "
            "selection sees changes — the charts keep showing the raw "
            "per-generation scores. Ignored in tournament mode, where nothing is "
            "selected."
        ),
        learn_more=(
            "Score memory smooths selection pressure — useful under random_k "
            "matching, where per-generation scores include participation luck."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.accounting_window",
        kind="int",
        default=5,
        minimum=1,
        maximum=100_000,
        label="Accounting window (W)",
        section="Dynamics",
        description=(
            "How many recent generations are averaged when score accounting is "
            "'sliding_window'. The score selection sees is the mean of the last W "
            "generation scores (fewer while the run is younger than W). A window "
            "of 1 behaves exactly like per-generation accounting. Ignored under "
            "other accounting choices."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.accounting_discount",
        kind="float",
        default=0.5,
        minimum=0.0,
        maximum=1.0,
        maximum_exclusive=True,
        label="Accounting discount (λ)",
        section="Dynamics",
        description=(
            "How much of the past is kept when score accounting is "
            "'exponential_discount'. Each generation, the score selection sees "
            "blends the new raw score with the previous blended score — higher "
            "values remember longer. At 0 the past is forgotten entirely, exactly "
            "like per-generation accounting. Must be below 1, or new scores would "
            "never matter at all."
        ),
    )
)

# --- The energy-economy knobs (M10a). All are read ONLY when
# dynamics.reproduction_mode is "energy_economy" — valid but ignored under
# imitation (the DECISIONS #34 pattern; the UI greys them out with a note).
# Two of them (initial_energy, senescence_factor) are the registry's first
# DERIVED defaults: nullable, with None meaning "auto" — the config layer
# resolves them to plain numbers at validation time (DECISIONS #78).

register(
    ParameterSpec(
        key="dynamics.reproduction_threshold",
        kind="float",
        default=500.0,
        minimum=0.0,
        label="Reproduction threshold (θ)",
        section="Dynamics",
        description=(
            "Energy an agent must hold at the end of a generation to have a "
            "child, in the energy economy. Reaching this bar is the 'can afford "
            "a child' test; the parent then pays the offspring stake to the "
            "newborn. Must be at least the offspring stake, so a parent always "
            "survives its own reproduction."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.offspring_stake",
        kind="float",
        default=400.0,
        minimum=0.0,
        label="Offspring stake (σ)",
        section="Dynamics",
        description=(
            "Energy a newborn starts life with, paid out of its parent's stock "
            "at the moment of birth, in the energy economy. A bigger stake gives "
            "children a longer runway but drains parents more — reproduction "
            "transfers wealth, it does not create it."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.initial_energy",
        kind="float",
        default=None,
        minimum=0.0,
        nullable=True,
        label="Initial energy",
        section="Dynamics",
        description=(
            "Energy each founding agent starts the run with, in the energy "
            "economy. Leave blank for 'same as the offspring stake' — founders "
            "then start life exactly like newborns."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.basic_living_cost",
        kind="float",
        default=200.0,
        minimum=0.0,
        label="Basic living cost (L)",
        section="Dynamics",
        description=(
            "Energy every agent pays at the end of each generation simply for "
            "existing, in the energy economy. This is the metabolic bill: an "
            "agent whose play cannot cover it slides toward death. Set it "
            "between the all-defector and all-cooperator incomes to make "
            "cooperation a survival matter — the Economy panel shows exactly "
            "where that window lies."
        ),
        learn_more=(
            "The living cost is the metabolic filter: it converts 'scoring "
            "poorly' into 'starving', which is what lets defectors go extinct "
            "instead of merely being out-copied."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.engagement_cost",
        kind="float",
        default=0.0,
        minimum=0.0,
        label="Engagement cost",
        section="Dynamics",
        description=(
            "Energy an agent pays per match it takes part in, in the energy "
            "economy. At 0, playing is free and more matches are always better; "
            "above 0, every interaction has a price, so agents that get drawn "
            "into many matches also pay more."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.reproduction_overhead",
        kind="float",
        default=0.0,
        minimum=0.0,
        label="Reproduction overhead",
        section="Dynamics",
        description=(
            "Extra energy a parent burns at each birth, on top of the offspring "
            "stake, in the energy economy. The stake reaches the child; this "
            "overhead simply disappears — it is the cost of the act of "
            "reproduction itself."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.capital_return_rate",
        kind="float",
        default=0.0,
        minimum=0.0,
        label="Capital return rate (r)",
        section="Dynamics",
        description=(
            "Interest earned on energy carried between generations, in the "
            "energy economy: carried-over energy is multiplied by (1 + this "
            "rate) each generation. Above zero it creates rentiers — an agent "
            "whose stock exceeds the 'escape velocity' shown in the Economy "
            "panel pays its bills from returns alone, forever, no matter how "
            "it plays."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.carrying_capacity",
        kind="int",
        default=None,
        minimum=1,
        nullable=True,
        label="Carrying capacity (K)",
        section="Dynamics",
        description=(
            "The most agents the world can hold, in the energy economy. Births "
            "only fill seats left below this cap — at capacity, nobody new gets "
            "in until deaths free room, and the richest would-be parents are "
            "admitted first. Leave blank for automatic: on a lattice the "
            "capacity becomes the NUMBER OF GRID SITES (the grid decides — the "
            "zero-effort spatial setting), while in a well-mixed world, where "
            "there is no grid to decide, blank falls back to the standard 200. "
            "On a lattice an explicit value BELOW the site count leaves "
            "deliberate slack — the population then parks below a full grid, "
            "and the occupied region can drift, cluster, and migrate as births "
            "and deaths reshape it. The capacity can never exceed the site "
            "count: the grid is the outer bound, this cap an optional tighter "
            "one."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.base_hazard",
        kind="float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        label="Base hazard",
        section="Dynamics",
        description=(
            "Chance a brand-new agent dies of background causes at each "
            "generation boundary, in the energy economy. The chance grows with "
            "age when the senescence factor is above 1. At 0 — with no maximum "
            "age set — nobody dies of age at all; only of running out of energy."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.senescence_factor",
        kind="float",
        default=None,
        minimum=0.0,
        minimum_exclusive=True,
        nullable=True,
        label="Senescence factor",
        section="Dynamics",
        description=(
            "How steeply the death chance climbs with age, in the energy "
            "economy: each generation of age multiplies the base hazard by this "
            "factor. Leave blank for 'auto', which picks the value that makes "
            "the death chance reach exactly 1.0 at the maximum age. Values "
            "above 1 mean aging; exactly 1 means age never matters."
        ),
        learn_more=(
            "An exponentially climbing death rate is the Gompertz law of "
            "mortality — the standard first model of aging."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.max_age",
        kind="int",
        default=0,
        minimum=0,
        label="Max age",
        section="Dynamics",
        description=(
            "A hard age cap, in the energy economy: an agent that reaches this "
            "age dies at the next generation boundary, no matter what. 0 means "
            "no cap. With a cap set and the senescence factor left blank, the "
            "death chance rises smoothly to certainty exactly at this age."
        ),
    )
)

# --- The synchronous boundary order (M11a Phase C, DECISIONS #107). Live
# under ALL synchronous runs — the slots-rationing and newborn-exposure
# effects exist even well-mixed (VT-4) — and never read under async, which
# has no boundary to order.

register(
    ParameterSpec(
        key="dynamics.boundary_order",
        kind="choice",
        default="death_first",
        choices=("death_first", "birth_first"),
        label="Boundary order",
        section="Dynamics",
        description=(
            "The order of deaths and births at each synchronous generation "
            "boundary. 'death_first' — the default, and this platform's "
            "behaviour in every earlier version — applies deaths first, then "
            "lets survivors breed into the room the deaths freed. "
            "'birth_first' is Hammond & Axelrod's period order: reproduction "
            "runs first, then the death phase. Two real consequences, both "
            "pushing the population DOWN relative to 'death_first'. (1) "
            "Births are rationed against the PRE-death population: free "
            "seats under the carrying capacity are counted before the dead "
            "have vacated theirs, so FEWER births are admitted — with "
            "capacity 200, 180 alive and 20 deaths, death-first admits 40 "
            "births where birth-first admits only 20. That is a different "
            "demographic regime, not a phase offset, and it is present even "
            "without a lattice. (2) Newborns go through the death phase in "
            "their own birth round — the age-mortality coin included — so a "
            "child can die the very round it was born. A 'birth_first' run "
            "sitting at a visibly lower population is correct, not broken. "
            "On a lattice the choice additionally decides WHICH sites are "
            "empty when children are placed: deaths-first lets newborns "
            "fill the interior graves the dead just left, while "
            "births-first offers only the cells that were already empty — "
            "the frontier. Only read under the synchronous time model."
        ),
        learn_more=(
            "Hammond & Axelrod 2006 run immigration → interaction → "
            "reproduction → death; their ethnocentrism result lives on the "
            "frontier this ordering creates."
        ),
    )
)

# --- The asynchronous-mode knobs (M10b Phase B). All are read ONLY when
# dynamics.time_model is "asynchronous" — valid but ignored under the
# synchronous clock (the DECISIONS #34 pattern). Registered at the end of the
# Dynamics block, after the M10a economy params (the M10b spec's placement).

register(
    ParameterSpec(
        key="dynamics.async_population",
        kind="choice",
        default="variable_n",
        choices=("variable_n", "fixed_n"),
        label="Async population mode",
        section="Dynamics",
        description=(
            "What happens to the population size under the asynchronous time "
            "model. 'variable_n' carries the energy economy into event time: "
            "agents earn by playing, pay to stay alive, have a child the "
            "moment they can afford one (with a seat free under the carrying "
            "capacity), and die the moment their energy goes negative or old "
            "age catches them — the population grows, shrinks, and can go "
            "extinct, exactly as in the synchronous economy, just one event "
            "at a time. 'fixed_n' is the textbook Moran process: the "
            "population is pinned at its starting size and every activation "
            "ends with exactly one death paired with one birth, chosen by "
            "the Moran rule below — no insolvency deaths, no aging, no "
            "extinction, and the carrying capacity is ignored. Energy is "
            "still tracked in 'fixed_n', but it only matters as the birth "
            "half's fitness (richer agents reproduce more often) and, "
            "optionally, as the death rule's aim. Only read under the "
            "asynchronous time model."
        ),
        learn_more=(
            "The Moran process (Moran 1958) is population genetics' standard "
            "fixed-size birth-death model; 'variable_n' is this platform's "
            "energy economy running on the same event clock."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.moran_rule",
        kind="choice",
        default="death_birth",
        choices=("birth_death", "death_birth", "random"),
        label="Moran rule",
        section="Dynamics",
        description=(
            "The order of the death half and the birth half of each "
            "fixed-size replacement. 'death_birth': one agent dies first "
            "(picked by the death rule below), then the whole remaining "
            "population competes to fill the empty seat with an offspring — "
            "an agent's chance is proportional to how far its energy sits "
            "above the poorest competitor's. 'birth_death': one agent is "
            "first picked to reproduce, energy-proportionally from everyone, "
            "and its offspring then replaces one of the OTHER agents (picked "
            "by the death rule below). 'random': every activation rolls "
            "afresh between the two, using the two weights below. The order "
            "sounds like bookkeeping, but it famously changes outcomes once "
            "a population has structure. Only read under 'fixed_n'."
        ),
        learn_more=(
            "Ohtsuki et al. 2006 (Nature): under death-birth updating on a "
            "network, cooperation is favoured when benefit/cost exceeds the "
            "number of neighbours (the b/c > k rule). The structure that "
            "makes this bite arrives with a later milestone — in today's "
            "well-mixed world the rules differ only mechanically."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.moran_weight_birth_death",
        kind="float",
        default=0.5,
        minimum=0.0,
        label="Moran weight: birth-death",
        section="Dynamics",
        description=(
            "How often the 'random' Moran rule fires a birth-death "
            "replacement, as a weight against the death-birth weight below. "
            "The two are normalised at use — 0.8 here against 0.2 there "
            "means birth-death fires 80% of the time. Only read when the "
            "Moran rule is 'random'; the two weights cannot both be zero "
            "(there would be nothing to roll between)."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.moran_weight_death_birth",
        kind="float",
        default=0.5,
        minimum=0.0,
        label="Moran weight: death-birth",
        section="Dynamics",
        description=(
            "How often the 'random' Moran rule fires a death-birth "
            "replacement, as a weight against the birth-death weight above. "
            "The two are normalised at use — equal weights mean a fair coin "
            "each activation. Only read when the Moran rule is 'random'; "
            "the two weights cannot both be zero."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.fixed_n_death_rule",
        kind="choice",
        default="energy_decides",
        choices=("pure_random", "energy_decides"),
        label="Fixed-N death rule",
        section="Dynamics",
        description=(
            "How the dying agent of a fixed-size replacement is picked — the "
            "death half of whichever Moran rule fires (under 'death_birth', "
            "who dies; under 'birth_death', which other agent the offspring "
            "replaces). 'pure_random' picks uniformly at random, blind to "
            "energy — the textbook Moran process, and the setting for "
            "reproducing published results. 'energy_decides' always picks "
            "the poorest candidate (ties go to the lowest agent id): the "
            "population size stays pinned, but the economy still aims the "
            "reaper at whoever played worst. Only read under 'fixed_n'."
        ),
    )
)

register(
    ParameterSpec(
        key="dynamics.imitation_overlay",
        kind="bool",
        default=False,
        label="Imitation overlay",
        section="Dynamics",
        description=(
            "Let agents copy each other's strategies on top of whatever the "
            "population is already doing. When on, every finished match ends "
            "with one of the two players — picked by a fair coin, regardless "
            "of score — considering a switch to the other's strategy. The "
            "better the other player scored in that match, the likelier the "
            "switch (copying a WORSE scorer is possible too, just less "
            "likely), tuned by the same selection intensity the Fermi rule "
            "uses — at zero intensity the switch is a pure coin flip, "
            "exactly like the synchronous Fermi rule's neutral drift. "
            "Nothing else changes hands: nobody is born "
            "or dies, no energy moves, and the copier keeps its own identity, "
            "age, and memory of past opponents — only its playing style "
            "changes, and immediately, so a strategy picked up mid-activation "
            "is already in use for the next match. This is CULTURAL spread "
            "(who imitates whom) running alongside the DEMOGRAPHIC spread "
            "(who is born and who dies), and it can be layered on either "
            "async population mode. Only read under the asynchronous time "
            "model."
        ),
        learn_more=(
            "Pairwise-comparison imitation is the standard cultural-evolution "
            "counterpart to birth-death dynamics: strategies spread by being "
            "copied by the living rather than by out-reproducing the dead."
        ),
    )
)

# ---------------------------------------------------------------------------
# Output — what the run RECORDS, never what it simulates (M10b spec Design 6)
# ---------------------------------------------------------------------------

register(
    ParameterSpec(
        key="output.recording_cadence",
        kind="choice",
        default="per_generation_equivalent",
        choices=("per_generation_equivalent", "per_event", "every_m_events"),
        label="Recording cadence",
        section="Output",
        description=(
            "How often an asynchronous run writes a data point (a 'recording "
            "period') to its charts and saved files. This is purely an "
            "observer control: it changes what gets RECORDED, never what "
            "happens in the simulation — the same seed produces the exact "
            "same history at every cadence. 'per_generation_equivalent' "
            "records once each time the event-time clock crosses a whole "
            "number — one point per generation-equivalent, directly "
            "comparable to a synchronous run and the sanest file size. "
            "'per_event' records after every single event — maximum "
            "resolution, but files and charts grow with every event played, "
            "so expect large outputs on long runs. 'every_m_events' records "
            "after every m-th event (m is the parameter below) — the "
            "middle ground. Only read under the asynchronous time model; "
            "synchronous runs always record once per generation."
        ),
    )
)

register(
    ParameterSpec(
        key="output.recording_cadence_m",
        kind="int",
        default=1,
        minimum=1,
        maximum=1_000_000,
        label="Events per recording (m)",
        section="Output",
        description=(
            "How many events pass between recordings when the recording "
            "cadence is 'every_m_events': a data point is written after "
            "every m-th event. At 1 this is the same as recording per "
            "event; larger values thin the record out — with N agents, "
            "m = N lands close to one point per generation-equivalent. "
            "Only read when the cadence is 'every_m_events'."
        ),
    )
)

# ---------------------------------------------------------------------------
# Run control (docs/DESIGN.md §2.8)
# ---------------------------------------------------------------------------

register(
    ParameterSpec(
        key="run.mode",
        kind="choice",
        default="evolution",
        choices=("evolution", "tournament"),
        label="Run mode",
        section="Run",
        description=(
            "What kind of experiment this is. 'evolution' means strategies compete "
            "AND the population changes over generations — strategies that score "
            "well spread through selection, and mutation adds variety. 'tournament' "
            "means a fixed cast of agents plays repeated matches while we simply "
            "watch the scores accumulate — nothing evolves, like Axelrod's original "
            "computer tournaments. Selection and mutation settings are ignored in "
            "tournament mode."
        ),
        learn_more=(
            "Robert Axelrod's 1980 computer tournaments — fixed strategy line-ups, "
            "round-robin play — are where Tit for Tat first made its name."
        ),
    )
)

register(
    ParameterSpec(
        key="run.tournament_cycles",
        kind="int",
        default=20,
        minimum=1,
        maximum=100_000,
        label="Tournament cycles",
        section="Run",
        description=(
            "How many complete tournament passes to play when the run mode is "
            "'tournament'. In one cycle, every pairing produced by the matching "
            "scheme plays one match (round-robin: every pair plays once). Agents "
            "remember their opponents from earlier cycles, so relationships keep "
            "developing. Has no effect in 'evolution' mode."
        ),
    )
)

register(
    ParameterSpec(
        key="run.seed",
        kind="int",
        default=42,
        minimum=0,
        label="Random seed",
        section="Run",
        description=(
            "Starting number for the random number generator. Two runs with the same "
            "seed and the same settings produce exactly the same results — change it "
            "to get a different random history. Every run's seed is saved with its "
            "results so any experiment can be replayed."
        ),
    )
)
