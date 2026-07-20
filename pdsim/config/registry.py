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

ParamKind = Literal["int", "float", "bool", "choice"]
"""The kinds of parameter the registry understands.

``Literal`` (new concept) restricts a value to an exact set of constants — a
lightweight enum that type checkers and validators can reason about.
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
            "opponents instead, so big populations stay fast. Distance-based "
            "matching arrives with the geographic layer in a later version."
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
        default=200,
        minimum=1,
        label="Carrying capacity (K)",
        section="Dynamics",
        description=(
            "The most agents the world can hold, in the energy economy. Births "
            "only fill seats left below this cap — at capacity, nobody new gets "
            "in until deaths free room, and the richest would-be parents are "
            "admitted first. It is the well-mixed model's stand-in for physical "
            "room; once the population gets a spatial structure (a later "
            "milestone), capacity may instead emerge from the number of sites."
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
            "with the worse-scoring of the two players considering a switch "
            "to the better-scoring one's strategy — the bigger the score gap, "
            "the likelier the switch, tuned by the same selection intensity "
            "the Fermi rule uses. Nothing else changes hands: nobody is born "
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
