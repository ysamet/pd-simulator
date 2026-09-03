"""Streamlit-free economy helpers: the calibration readout (M10a Task 10).

The Economy panel's arithmetic, kept out of ``app.py`` so every branch is
unit-testable without Streamlit (the #38/#48 helper pattern, exactly like
``sweep_helpers.py``). Pure config → numbers: :func:`calibration_report`
derives, straight from an ``ExperimentConfig``, where the survival window
lies and what the configured economy will actually do — which is what makes
app-first validation of an economy honest ("set up an economy, observe
growth" is impossible to judge if you cannot see the window).

``ECONOMY_HELP`` is the single source for the panel's inline (?) texts, so
the app's wording and the docs cannot drift apart (the spec's §12 rule).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import NamedTuple

from pdsim.config.experiment import ExperimentConfig, effective_neighbour_count
from pdsim.config.registry import ParamValue
from pdsim.core.economy import age_mortality_active
from pdsim.core.movement import movement_active

ECONOMY_HELP: dict[str, str] = {
    "energy": (
        "Energy is a STOCK, not a score: an agent owns it across generations, "
        "earns it by playing, pays it to stay alive, and spends it on children. "
        "The per-generation score still exists (it is the income line of the "
        "ledger) but resets every generation; energy is what accumulates."
    ),
    "admission": (
        "When more agents qualify to breed than the carrying capacity has free "
        "seats, admission is by energy priority: the richest eligible parents "
        "get the seats (ties broken by lower id). Deterministic on purpose — "
        "no lottery, no extra randomness in the birth phase. On a lattice "
        "under the synchronous clock only FEASIBLE parents are ranked at all "
        "— those with at least one empty site within their birth radius — so "
        "a seat never goes to a parent who has nowhere to put the child (see "
        "the infeasible-parents readout)."
    ),
    "estate_destruction": (
        "When an agent dies, its remaining energy vanishes — nothing is "
        "inherited or redistributed. This is the 100% inheritance-tax corner "
        "of the design; other estate policies (inheritance, redistribution) "
        "are a later milestone."
    ),
    "passport_id": (
        "Every agent gets a lifetime passport id at birth, and ids are NEVER "
        "reused — agent 7 next generation is the same creature as agent 7 this "
        "generation. Each newborn records its parent's id, so the whole family "
        "tree is reconstructible from the recorded snapshots."
    ),
    "expected_matches": (
        "How many matches one agent is expected to play per generation: N − 1 "
        "under round_robin (everyone meets everyone), ≈ 2k under random_k "
        "(each agent starts k matches and is drawn into ≈ k more), and "
        "2 × the effective neighbour count while spatial interaction is on "
        "(each agent starts a match with every reachable neighbour and is "
        "drawn into as many in return). With encounter mode 'per_pair' the "
        "duplicate pairs are collapsed after the draws, so the spatial "
        "figure is 1 × the effective neighbour count instead — each "
        "neighbouring pair plays at most once per generation. Under the "
        "asynchronous clock the spatial figure is an EXPECTED value per "
        "generation-equivalent — each agent is activated once on average "
        "and drawn in by each activated neighbour — where the synchronous "
        "count is exact."
    ),
    "income": (
        "The two income extremes per generation: what an agent earns if every "
        "round of every match ends in mutual cooperation (all-C, at the reward "
        "payoff R) versus mutual defection (all-D, at the punishment payoff P). "
        "Real agents earn somewhere in between."
    ),
    "window": (
        "The survival window: with the total per-generation cost above the "
        "all-D income but below the all-C income, cooperators can pay "
        "their bills and defectors cannot — the metabolic filter is switched "
        "on. At or below the all-D income even defectors pay their bills "
        "(at the bound exactly, a defector nets zero and never starves — "
        "which is why the window's lower bound is strict); at or above the "
        "all-C income everyone starves."
    ),
    "escape_velocity": (
        "With a capital return rate above zero, an agent whose energy stock "
        "exceeds e* = total cost ÷ return rate pays its bills from interest "
        "alone — it is self-sustaining regardless of how it plays, immune to "
        "the metabolic filter the experiment rests on, and clears the "
        "breeding bar forever. Watch the mean-energy chart for runaway "
        "accumulation once anyone crosses it."
    ),
    "generations_to_threshold": (
        "How many generations a founder needs, earning at the all-C "
        "cooperator's net rate, to first reach the reproduction threshold — "
        "and roughly how many children it can afford in a lifetime capped by "
        "the maximum age (first breed, then one child every stake ÷ net-rate "
        "generations)."
    ),
    "effective_max_age": (
        "The age at which the death chance actually reaches certainty. With "
        "the senescence factor on auto this is exactly the configured max "
        "age; an explicitly steeper factor can bring it BELOW the cap, in "
        "which case nobody ever reaches the cap — allowed, just worth "
        "knowing."
    ),
    "blocked_parents": (
        "A BLOCKED parent won a free seat under the carrying capacity but "
        "found no empty site within its birth radius when its turn came to "
        "place the child — so it paid nothing, keeps its energy, stays "
        "eligible, and simply tries again. What that means depends on the "
        "clock. Under the SYNCHRONOUS economy every seated parent had an "
        "empty site in reach when seats were handed out (only feasible "
        "parents are ranked), so a blocked parent here LOST A PLACEMENT "
        "CONTEST: an earlier-placed parent took the last empty site within "
        "its reach this generation — rare, and self-healing next generation. "
        "Under the ASYNCHRONOUS clock there is no feasibility filter and no "
        "shuffled contest step, so blocked keeps its original, undivided "
        "meaning: no empty "
        "site was in reach at that birth event, whether the neighbourhood "
        "was simply full or an earlier birth in the same event took the last "
        "site. Under that clock the number is a PER-EVENT tally summed over "
        "the recording window — a parent that stays walled in is "
        "re-attempted, and re-counted, at every event of the window (about "
        "N events per generation-equivalent), so it counts blocked ATTEMPTS, "
        "not distinct parents, and one stuck parent shows up roughly N times "
        "per generation-equivalent. Either way, an agent sitting at several times the breeding "
        "bar and not breeding is CORRECT, not stuck: being unable to spend "
        "reproductive wealth because the neighbourhood is full is exactly "
        "what spatial viscosity means, and it is the mechanism that lets "
        "clusters keep their shape."
    ),
    "infeasible_parents": (
        "An INFEASIBLE parent holds enough energy to breed but has NO empty "
        "site within its birth radius, so under the synchronous economy it "
        "is not ranked for a seat at all this generation — the seats go to "
        "parents who can actually place a child (K decides how many, the "
        "birth radius decides where). It pays nothing, keeps its energy, "
        "stays eligible, and is re-assessed every generation against the "
        "changing occupancy. The count is ALL such parents, not just the "
        "ones who would have won a seat: on a completely full grid every "
        "eligible parent is infeasible — that is what saturation looks like "
        "in this readout. Under the asynchronous clock this readout does not "
        "apply (there is no feasibility filter there; such parents show up "
        "as blocked instead)."
    ),
    "blocked_moves": (
        "A BLOCKED MOVE is a move attempt that found NO empty site within "
        "the movement radius of the agent's current position, so the agent "
        "stayed where it was. Each agent attempts a move with probability "
        "'Movement rate' — at the end of each generation's demographic "
        "boundary under the synchronous clock, or when it is activated as "
        "the focal agent under the asynchronous clock — and a successful "
        "move relocates it to one empty site within reach (an agent never "
        "moves onto an occupied site, and never 'moves' to its own). One "
        "count covers every way an attempt can fail: the agent may be "
        "walled in by neighbours, or — under the synchronous clock, where "
        "the period's movers are shuffled once and moved in turn — an "
        "earlier mover may have taken the last empty site in its reach "
        "(and freed its own origin for later movers, so chains can form). "
        "A blocked agent simply tries again whenever its next attempt "
        "comes; nothing is paid and nothing else changes. Many blocked "
        "moves on a crowded grid are what crowding LOOKS like in this "
        "readout, not a stall: on a completely full grid every attempt "
        "is blocked. Movement is free (no energy cost) and blind to "
        "strategy."
    ),
}
"""The single source for the Economy panel's inline (?) explainer texts."""


SPATIAL_FINE_PRINT = (
    "The figure is the fully-occupied, uniform-degree case — an agent in "
    "the interior of a full grid; edge agents on a bounded grid, and agents "
    "beside empty sites, play fewer matches and earn less."
)
"""The spatial calibration's fine print, in one sentence (DECISIONS #154).

The single source (the §12 discipline) for the caveat the spatial readout
must carry: the 2 × effective-neighbour-count figure describes an interior
agent on a full grid, and every other agent earns less than it says.
"""


def _spatial_regime_note(encounter_mode: str, asynchronous: bool = False) -> str:
    """The spatial branch's regime caption: bounded budget, plus the fine print.

    Mode-conditional since M11b Phase C (#174(a)): the caption states the
    multiplier the arithmetic actually used — 2 × the effective neighbour
    count under ``"per_initiator"``, 1 × under ``"per_pair"`` — so the
    Economy panel's fine print can never contradict the figure beside it
    (#34). The per-initiator sentence is the pre-Phase-C text, verbatim.
    Clock-aware since M11b Phase D (#169/#176): under the asynchronous
    clock the figure is marked EXPECTED where the synchronous figure was
    exact — activation order is random, so the per-window count varies
    agent to agent around it (the Phase D measurement's per-agent spread
    is exactly this variation; the population mean was exact).

    Args:
        encounter_mode: The encounter mode the ARITHMETIC used —
            ``"per_initiator"`` or ``"per_pair"`` (under the asynchronous
            clock the caller forces ``"per_initiator"``, ruling R3 of
            #176, so a stranded widget value never reaches this note).
        asynchronous: Whether the configured clock is asynchronous.

    Returns:
        The caption for :attr:`CalibrationReport.regime_note`, ending with
        :data:`SPATIAL_FINE_PRINT`.
    """
    if encounter_mode == "per_pair":
        budget = (
            "1 × the effective neighbour count (encounter mode 'per_pair' "
            "collapses duplicate pairs after the draws)"
        )
    else:
        budget = "2 × the effective neighbour count"
    if asynchronous:
        budget += (
            ", as an EXPECTED figure per generation-equivalent under the "
            "asynchronous clock (activation order is random, so individual "
            "agents scatter around it)"
        )
    return (
        "Under spatial interaction the interaction budget is set by the grid's "
        f"geometry — {budget} — no matter how large the "
        "population grows, so this window stays put for the whole run. " + SPATIAL_FINE_PRINT
    )


def _expected_rounds(
    length_mode: str, rounds_per_match: int, continuation_probability: float
) -> float:
    """Expected rounds per match — the one place both arithmetics compute it.

    Args:
        length_mode: ``"fixed"`` (exact round count) or ``"continuation"``
            (coin-flip after each round).
        rounds_per_match: The fixed round count (read under ``"fixed"``).
        continuation_probability: w, the keep-playing chance (read under
            ``"continuation"``; the expected match length is 1 / (1 − w)).

    Returns:
        The expected number of rounds one match lasts.
    """
    if length_mode == "fixed":
        return float(rounds_per_match)
    return 1.0 / (1.0 - continuation_probability)


class SpatialIncome(NamedTuple):
    """The spatial branch's worked income arithmetic (DECISIONS #154).

    Attributes:
        matches_per_agent: 2 × the effective neighbour count under
            ``encounter_mode = "per_initiator"`` — each agent starts a
            match with every reachable neighbour and is drawn into as many
            in return (the calibration guide §4.2's third regime, measured
            exactly in #139) — or 1 × it under ``"per_pair"``, where the
            duplicate pairs are collapsed after the draws (M11b Phase C,
            #166/#174(a)).
        rounds_per_agent: Matches × expected rounds per match.
        all_c_income: Per-generation income if every round is mutual
            cooperation (rounds per agent × R).
        all_d_income: Per-generation income if every round is mutual
            defection (rounds per agent × P).
        window_low: The survival window's lower bound (= all-D income).
        window_high: The survival window's upper bound (= all-C income);
            the window is ``window_low < cost < window_high`` — BOTH
            bounds strict since M11b Phase D (#176 R1): at cost exactly
            equal to the all-D income a defector nets zero and never
            starves, so the boundary point defeats the filter.
    """

    matches_per_agent: float
    rounds_per_agent: float
    all_c_income: float
    all_d_income: float
    window_low: float
    window_high: float


def spatial_income_arithmetic(
    *,
    neighbourhood_shape: str,
    boundary: str,
    opponents_per_agent: int,
    length_mode: str,
    rounds_per_match: int,
    continuation_probability: float,
    payoff_reward: float,
    payoff_punishment: float,
    encounter_mode: str = "per_initiator",
    interaction_radius: int | None = 1,
    site_count: int | None = None,
) -> SpatialIncome:
    """The spatial survival-window arithmetic, as a pure paint-time function.

    Matches per agent = 2 × :func:`~pdsim.config.experiment.
    effective_neighbour_count` (reused, not re-derived — DECISIONS #141(e)):
    an interior agent initiates a match against each of its min(k, degree)
    reachable neighbours and is drawn into as many in return (§4.2 of the
    calibration guide; measured exactly in #139) — or 1 × it under
    ``encounter_mode = "per_pair"``, where the duplicate pairs are
    collapsed after the draws (M11b Phase C, the #174(a) display branch).
    Everything downstream — rounds per agent, the two income extremes, the
    window bounds — follows the same shape as the aspatial calibration
    branches. The figure is the fully-occupied, uniform-degree case
    (:data:`SPATIAL_FINE_PRINT` states it; any readout showing these
    numbers must carry that sentence).

    Registry-value inputs only, deliberately (DECISIONS #154): the M11b
    advisories A1 and A2 trigger on exactly these quantities, so this
    function is shaped for them to CALL rather than re-derive.

    Args:
        neighbourhood_shape: ``"moore"`` (8 neighbours) or ``"von_neumann"``
            (4 neighbours) — ``structure.neighbourhood_shape``.
        boundary: ``"torus"`` or ``"bounded"`` — ``structure.boundary``
            (documented in :func:`effective_neighbour_count` as not moving
            the interior number).
        opponents_per_agent: The configured k —
            ``matching.opponents_per_agent``.
        length_mode: ``match.length_mode`` (``"fixed"`` or
            ``"continuation"``).
        rounds_per_match: ``match.rounds_per_match`` (read under
            ``"fixed"``).
        continuation_probability: ``match.continuation_probability`` (read
            under ``"continuation"``; expected length 1 / (1 − w)).
        payoff_reward: R — ``game.payoff_reward``.
        payoff_punishment: P — ``game.payoff_punishment``.
        encounter_mode: ``matching.encounter_mode`` —
            ``"per_initiator"`` (the 2× default) or ``"per_pair"`` (1×).
        interaction_radius: ``structure.interaction_radius`` — the
            interaction kernel's support radius (``None`` = unlimited),
            passed through to the radius-aware
            :func:`effective_neighbour_count` (#176 R6). Defaults to 1,
            the registry default.
        site_count: The grid's site count (rows × cols), required for the
            unlimited-radius case and a truthful ceiling otherwise.

    Returns:
        The full :class:`SpatialIncome` arithmetic.
    """
    multiplier = 1.0 if encounter_mode == "per_pair" else 2.0
    matches = multiplier * effective_neighbour_count(
        neighbourhood_shape,
        boundary,
        opponents_per_agent,
        interaction_radius,
        site_count,
    )
    rounds_per_agent = matches * _expected_rounds(
        length_mode, rounds_per_match, continuation_probability
    )
    all_c = rounds_per_agent * payoff_reward
    all_d = rounds_per_agent * payoff_punishment
    return SpatialIncome(
        matches_per_agent=matches,
        rounds_per_agent=rounds_per_agent,
        all_c_income=all_c,
        all_d_income=all_d,
        window_low=all_d,
        window_high=all_c,
    )


def spatial_calibration_active(config: ExperimentConfig) -> bool:
    """Whether the calibration report should use the spatial branch (#154).

    Mirrors the engine's own gate as #141(c) sharpened it — an EVOLUTION
    run on a LATTICE with the spatial-interaction toggle on — not the
    toggle alone: with the toggle stranded on under ``well_mixed`` (a
    greyed checkbox keeps its value) or under tournament, the configured
    matcher genuinely IS consulted, and the aspatial arithmetic remains the
    correct report there. The synchronous-clock conjunct #154 held this
    predicate to was RETIRED in M11b Phase D (#169's gate, discharged by
    the #177 measurement): asynchronous spatial runs measured EXACTLY
    2 × min(k, degree) matches per agent per generation-equivalent as the
    population mean, every window, on the fixed_n configuration where the
    prediction is exact — so both clocks now share the spatial branch,
    with the async figure marked "expected" in the fine print (activation
    order is random; individuals scatter around the exact mean).

    Args:
        config: The experiment being calibrated.

    Returns:
        True when the spatial arithmetic describes the configured run.
    """
    return (
        config.mode == "evolution"
        and config.structure.kind == "lattice"
        and config.matching.spatial_interaction
    )


def economy_active(values: Mapping[str, ParamValue]) -> bool:
    """Whether the energy ledger actually filters anyone (#176 R4).

    The ONE shared gate for advisories A1 and A2: evolution mode AND
    ((synchronous AND ``reproduction_mode = energy_economy``) OR
    (asynchronous AND ``async_population = variable_n``)). Each excluded
    corner would make a "metabolic filter" warning describe a filter that
    does not exist: under the asynchronous clock the reproduction-mode
    widget is inert (#154) and ``async_population`` chooses the paradigm
    instead; under ``fixed_n`` the living cost is never charged (no
    insolvency deaths — the Moran replacement is the only demography);
    under tournament the economy is ignored wholesale.

    Takes the WIDGET-VALUE mapping (with the app's lookahead), not a
    config, because A2 must fire at paint time while the panel may not
    even assemble into a valid config yet — the same signature shape as
    the greying predicates (#141).

    Args:
        values: Widget values keyed by registry key (plus ``run.mode``).

    Returns:
        True when the configured run charges the living cost and kills the
        insolvent — the regime the survival-window advisories describe.
    """
    if values.get("run.mode") != "evolution":
        return False
    if values.get("dynamics.time_model") == "asynchronous":
        return values.get("dynamics.async_population") == "variable_n"
    return values.get("dynamics.reproduction_mode") == "energy_economy"


def economy_inactive_summary(values: Mapping[str, ParamValue]) -> tuple[str, str]:
    """The collapsed Economy panel's summary label and explanation (#178 R9).

    Consulted exactly when :func:`economy_active` is False on the
    evolution tab, and names the cause the way the collapsed sections do
    (#178 R5): under the asynchronous clock the inactive corner is
    ``fixed_n`` — the living cost is never charged there, the Moran
    replacement being the only demography — and under the synchronous
    clock it is ``imitation`` reproduction, where nobody pays a living
    cost or starves. Tournament never reaches this label: the whole
    Dynamics section is hidden on that tab (#178 R3).

    Args:
        values: Widget values keyed by registry key (plus ``run.mode``).

    Returns:
        ``(summary label, one-line explanation)`` for the collapsed
        panel — no readout; the calibration would describe a filter
        that is not running.
    """
    if values.get("dynamics.time_model") == "asynchronous":
        return (
            "Economy — inactive under fixed_n (living cost not charged)",
            "Under the fixed-size ('fixed_n' Moran) population the living "
            "cost is never charged and nobody starves — the Moran "
            "replacement is the only demography, so there is no survival "
            "window to calibrate. Switch 'Async population' to "
            "'variable_n' to run the economy in event time.",
        )
    return (
        "Economy — inactive under imitation",
        "Under 'imitation' reproduction nobody pays the living cost or "
        "starves — agents copy strategies instead of breeding and dying, "
        "so there is no survival window to calibrate. Switch "
        "'Reproduction mode' to 'energy_economy' to run the economy.",
    )


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """Everything the Economy panel shows, derived straight from a config.

    Attributes:
        matcher: The CONFIGURED matching scheme. While ``spatial`` is True
            it is greyed and unconsulted (#141(c)) — the numbers then come
            from the grid's geometry, not from it.
        expected_matches: Matches one agent is expected to play per
            generation (N − 1 round-robin; ≈ 2k random_k; 2 × the
            effective neighbour count under spatial interaction, #154).
        expected_rounds_per_match: Fixed round count, or 1 / (1 − w) in
            continuation mode.
        all_c_income: Per-generation income if every round is mutual
            cooperation (matches × rounds × R).
        all_d_income: Per-generation income if every round is mutual
            defection (matches × rounds × P).
        living_cost: The configured basic living cost L.
        total_cost: The full per-generation bill at the expected
            participation: L + engagement_cost × matches (equals L when
            engagement is free).
        cooperator_net: all-C income − total cost (the verdict line's +X).
        defector_net: all-D income − total cost (the verdict line's −Y).
        window_verdict: Where the total cost sits relative to the survival
            window ``all-D < cost < all-C`` (both bounds strict, #176 R1)
            — ``"inside"``, ``"below"`` (even defectors grow; the lower
            bound itself counts as below), or ``"above"`` (everyone
            starves).
        regime_note: Whether this window stays put as N changes: it does
            under random_k (bounded interaction budget) and does NOT under
            round-robin (income scales with N, so the window moves).
        escape_velocity: e* = total_cost / capital_return_rate when r > 0,
            else ``None``.
        senescence_factor: The RESOLVED factor, shown whenever age
            mortality is active (``None`` otherwise) — this is where a
            blank "auto" input becomes a visible number.
        effective_max_age: The age at which the death chance reaches 1.0
            (``None`` when nothing age-related is configured).
        effective_max_age_note: The warn-don't-forbid soft note when an
            explicit senescence factor drops the effective maximum age
            below the configured cap; ``None`` otherwise.
        generations_to_threshold: Generations a founder needs at the
            cooperator's net rate to first reach θ (when max_age > 0 and
            the net is positive; ``None`` otherwise).
        expected_offspring: Rough lifetime child count at the cooperator's
            net rate under the age cap (when max_age > 0).
        memory_note: The second warn-don't-forbid note: histories persist
            in the economy, so with unlimited ``memory_depth`` the history
            copy cost grows with relationship length — named with the
            projected worst case; ``None`` when a bound is set or the mode
            is imitation.
        spatial: Whether the spatial branch produced the matches figure —
            True exactly on the engine's own gate as #154 mirrors it
            (evolution on a lattice with spatial interaction on; BOTH
            clocks since M11b Phase D, #169's gate discharged by the #177
            measurement); the ``regime_note`` then carries
            :data:`SPATIAL_FINE_PRINT`, marked "expected" under the
            asynchronous clock.
    """

    matcher: str
    expected_matches: float
    expected_rounds_per_match: float
    all_c_income: float
    all_d_income: float
    living_cost: float
    total_cost: float
    cooperator_net: float
    defector_net: float
    window_verdict: str
    regime_note: str
    escape_velocity: float | None
    senescence_factor: float | None
    effective_max_age: float | None
    effective_max_age_note: str | None
    generations_to_threshold: float | None
    expected_offspring: float | None
    memory_note: str | None
    spatial: bool


def calibration_report(config: ExperimentConfig) -> CalibrationReport:
    """Derive the Economy panel's numbers from a validated config.

    Pure and deterministic: same config in, same report out — no RNG, no
    simulation, just the worked arithmetic of the explainer
    (`docs/explainers/M10-growth-economy-explainer.md`).

    Args:
        config: The experiment to calibrate (normally one whose
            ``dynamics.reproduction_mode`` is ``"energy_economy"`` — the
            arithmetic is well-defined regardless).

    Returns:
        The full :class:`CalibrationReport`.
    """
    dynamics = config.dynamics
    n = config.population.size
    spatial = spatial_calibration_active(config)
    asynchronous = dynamics.time_model == "asynchronous"
    if spatial:
        # The spatial branch (#154): while partners genuinely come from the
        # grid, the greyed matcher's arithmetic would describe a mechanism
        # that is not running — the figures come from the geometry instead.
        # Under the asynchronous clock the encounter mode is FORCED to
        # per_initiator (#176 R3): the async loop never deduplicates
        # (#175(a)), so honouring a stranded per_pair widget value would
        # print 4 where the engine plays 8 — the #34 falsehood #174(a)
        # exists to prevent.
        encounter_mode = "per_initiator" if asynchronous else config.matching.encounter_mode
        # A validated lattice config stores resolved dimensions (the
        # before-validator, hard rule 8); the guard mirrors the model's own
        # defensive checks rather than assuming.
        site_count = (
            config.structure.rows * config.structure.cols
            if config.structure.rows is not None and config.structure.cols is not None
            else None
        )
        arithmetic = spatial_income_arithmetic(
            neighbourhood_shape=config.structure.neighbourhood_shape,
            boundary=config.structure.boundary,
            opponents_per_agent=config.matching.opponents_per_agent,
            length_mode=config.match.length_mode,
            rounds_per_match=config.match.rounds_per_match,
            continuation_probability=config.match.continuation_probability,
            payoff_reward=config.game.payoff_reward,
            payoff_punishment=config.game.payoff_punishment,
            encounter_mode=encounter_mode,
            interaction_radius=config.structure.interaction_radius,
            site_count=site_count,
        )
        matches = arithmetic.matches_per_agent
        regime_note = _spatial_regime_note(encounter_mode, asynchronous)
    elif config.matching.matcher == "round_robin":
        matches = float(n - 1)
        regime_note = (
            "Under round_robin, income scales with the population size: as N "
            "grows every agent plays more matches, so this window MOVES — a "
            "living cost calibrated for the founders drifts out of (or into) "
            "the window as the population grows."
        )
    else:
        matches = 2.0 * config.matching.opponents_per_agent
        regime_note = (
            "Under random_k the interaction budget is bounded (≈ 2k matches "
            "per agent) no matter how large the population grows, so this "
            "window stays put for the whole run."
        )
    rounds = _expected_rounds(
        config.match.length_mode,
        config.match.rounds_per_match,
        config.match.continuation_probability,
    )

    all_c = matches * rounds * config.game.payoff_reward
    all_d = matches * rounds * config.game.payoff_punishment
    total_cost = dynamics.basic_living_cost + dynamics.engagement_cost * matches
    if total_cost >= all_c:
        verdict = "above"
    elif total_cost <= all_d:
        # The lower bound is STRICT (#176 R1): at cost exactly equal to the
        # all-D income a defector nets zero and never starves, so the
        # boundary point itself sits below the window, filter off.
        verdict = "below"
    else:
        verdict = "inside"

    escape = total_cost / dynamics.capital_return_rate if dynamics.capital_return_rate > 0 else None

    mortality_on = age_mortality_active(dynamics)
    factor = dynamics.senescence_factor if mortality_on else None
    effective: float | None = None
    if dynamics.base_hazard > 0 and dynamics.senescence_factor > 1:
        # The age where base_hazard × factor^age first reaches 1.
        effective = math.log(1.0 / dynamics.base_hazard) / math.log(dynamics.senescence_factor)
        if dynamics.max_age > 0:
            effective = min(effective, float(dynamics.max_age))
    elif dynamics.max_age > 0:
        effective = float(dynamics.max_age)  # the cap is the only certainty
    age_note = None
    if dynamics.max_age > 0 and effective is not None and effective < dynamics.max_age - 1e-9:
        age_note = (
            f"Effective maximum age ≈ {effective:.1f}, below the configured max "
            f"age {dynamics.max_age} — the death chance reaches certainty before "
            "the cap, so nobody will actually reach it. Allowed; just know that "
            "the senescence curve, not the cap, is doing the killing."
        )

    coop_net = all_c - total_cost
    to_threshold: float | None = None
    offspring: float | None = None
    if dynamics.max_age > 0:
        if coop_net > 0:
            to_threshold = max(
                0.0, (dynamics.reproduction_threshold - dynamics.initial_energy) / coop_net
            )
            # A rough lifetime schedule at the cooperator's net rate: first
            # breed once θ is reached (never before the first boundary),
            # then one child every ceil((σ + overhead) / net) generations.
            first = max(1, math.ceil(to_threshold))
            interval = max(
                1,
                math.ceil((dynamics.offspring_stake + dynamics.reproduction_overhead) / coop_net),
            )
            if dynamics.max_age < first:
                offspring = 0.0
            else:
                offspring = 1.0 + (dynamics.max_age - first) // interval
        else:
            offspring = 0.0

    memory_note = None
    if dynamics.reproduction_mode == "energy_economy" and config.population.memory_depth is None:
        if spatial:
            # The E4b audit fix: the note used to branch on the CONFIGURED
            # matcher here too, attributing the growth to a mechanism that is
            # not running — and the random_k wording ("recurs only
            # occasionally") is the opposite of the lattice truth, where
            # neighbours are fixed and an adjacent pair meets twice per
            # generation (#139), doubling round_robin's per-pair growth rate.
            # Mode-aware since M11b Phase C (#174(a)'s never-false rule):
            # under 'per_pair' the pair meets once and the worst case halves.
            # Under the asynchronous clock the stranded widget value is
            # FORCED to per_initiator (#176 R3), same as the arithmetic —
            # the async loop never deduplicates (#175(a)).
            per_pair = not asynchronous and config.matching.encounter_mode == "per_pair"
            meetings = 1 if per_pair else 2
            worst = meetings * rounds * dynamics.generations
            frequency = "once" if per_pair else "twice"
            memory_note = (
                "Histories persist for an agent's whole life and memory depth "
                "is unlimited: under spatial interaction an agent's "
                f"neighbours are FIXED, so a neighbouring pair meets {frequency} "
                f"every generation and one relationship can reach ≈ {worst:,.0f} "
                f"recorded moves by generation {dynamics.generations}, with "
                "the per-round history copy growing alongside (cost quadratic "
                "in run length). Set the population memory depth to bound it."
            )
        elif config.matching.matcher == "round_robin":
            worst = rounds * dynamics.generations
            memory_note = (
                "Histories persist for an agent's whole life and memory depth "
                "is unlimited: under round_robin every pair meets every "
                f"generation, so one relationship can reach ≈ {worst:,.0f} "
                f"recorded moves by generation {dynamics.generations}, and the "
                "per-round history copy grows with it (cost quadratic in run "
                "length). Set the population memory depth to bound it."
            )
        else:
            memory_note = (
                "Histories persist for an agent's whole life and memory depth "
                "is unlimited. Under random_k a given opponent recurs only "
                "occasionally, so relationships stay short and this rarely "
                "matters — but for very long runs the population memory depth "
                "is the bound."
            )

    return CalibrationReport(
        matcher=config.matching.matcher,
        expected_matches=matches,
        expected_rounds_per_match=rounds,
        all_c_income=all_c,
        all_d_income=all_d,
        living_cost=dynamics.basic_living_cost,
        total_cost=total_cost,
        cooperator_net=coop_net,
        defector_net=all_d - total_cost,
        window_verdict=verdict,
        regime_note=regime_note,
        escape_velocity=escape,
        senescence_factor=factor,
        effective_max_age=effective,
        effective_max_age_note=age_note,
        generations_to_threshold=to_threshold,
        expected_offspring=offspring,
        memory_note=memory_note,
        spatial=spatial,
    )


def chart_carrying_capacity(config: ExperimentConfig) -> float | None:
    """The K reference line the population chart should draw, if any.

    Args:
        config: The run's config.

    Returns:
        ``dynamics.carrying_capacity`` for an energy-economy evolution run;
        ``None`` for every other run (no line — K is not consumed there).
    """
    if config.mode == "evolution" and config.dynamics.reproduction_mode == "energy_economy":
        return float(config.dynamics.carrying_capacity)
    return None


def blocked_parents_visible(config: ExperimentConfig) -> bool:
    """Whether the blocked-parents readout applies to this run (M11a Phase C).

    Blocked parents exist exactly where the LOCAL placement gate exists:
    an evolution run on a lattice whose birth machinery is θ-driven — the
    synchronous energy economy, or the asynchronous ``variable_n`` mode.
    ``fixed_n`` never blocks (the freed seat always exists), imitation
    never births, and a well-mixed world never refuses a placement.

    Args:
        config: The run's config.

    Returns:
        True when the readout should be shown.
    """
    if config.mode != "evolution" or config.structure.kind != "lattice":
        return False
    dynamics = config.dynamics
    if dynamics.time_model == "asynchronous":
        return dynamics.async_population == "variable_n"
    return dynamics.reproduction_mode == "energy_economy"


def infeasible_parents_visible(config: ExperimentConfig) -> bool:
    """Whether the infeasible-parents readout applies to this run (M11b Phase A).

    The feasibility filter runs under the three-way gate ONLY — synchronous
    clock + lattice + ``energy_economy`` (#164) — so the readout is shown
    exactly there. The asynchronous clock never populates the field
    (DECISIONS #171, ruling R1: its blocked count stays undivided), so it
    is hidden rather than shown as a permanent zero.

    Args:
        config: The run's config.

    Returns:
        True when the readout should be shown.
    """
    if config.mode != "evolution" or config.structure.kind != "lattice":
        return False
    dynamics = config.dynamics
    if dynamics.time_model == "asynchronous":
        return False
    return dynamics.reproduction_mode == "energy_economy"


def blocked_parents_metric(blocked: list[int]) -> tuple[int, int] | None:
    """The numbers behind the live blocked-parents readout (Design 4, #89(e)).

    A parent walled in at five times the breeding bar, paying nothing and
    accumulating, is CORRECT viscosity — but it reads as a bug unless the
    app says "blocked: no site in reach". Streamlit-free so the arithmetic
    is unit-testable; the explanation itself lives in
    ``ECONOMY_HELP["blocked_parents"]`` (the §12 single-source rule).

    Args:
        blocked: The per-period blocked-parent counts so far (the
            timeseries' live series).

    Returns:
        ``(latest period's count, run total)``, or ``None`` before any
        period has finished.
    """
    if not blocked:
        return None
    return blocked[-1], sum(blocked)


def blocked_moves_visible(config: ExperimentConfig) -> bool:
    """Whether the blocked-moves readout applies to this run (M11b Phase B).

    Shown exactly where movement is ACTIVE — the engine's own gate
    (:func:`~pdsim.core.movement.movement_active`): lattice + energy
    economy (synchronous ``energy_economy`` or asynchronous ``variable_n``)
    AND ``movement.rate > 0``. At rate 0 movement is off and no attempt
    ever happens, so the readout is hidden rather than shown as a permanent
    zero (the ``infeasible_parents_visible`` pattern).

    Args:
        config: The run's config.

    Returns:
        True when the readout should be shown.
    """
    return movement_active(config)


def blocked_moves_metric(blocked: list[int]) -> tuple[int, int] | None:
    """The numbers behind the live blocked-moves readout (M11b Phase B).

    The same shape as :func:`blocked_parents_metric` — the three metrics sit
    side by side in the Economy panel and are read the same way. The
    explanation lives in ``ECONOMY_HELP["blocked_moves"]`` (the §12
    single-source rule).

    Args:
        blocked: The per-period blocked-move counts so far (the
            timeseries' live series).

    Returns:
        ``(latest period's count, run total)``, or ``None`` before any
        period has finished.
    """
    if not blocked:
        return None
    return blocked[-1], sum(blocked)


def infeasible_parents_metric(infeasible: list[int]) -> tuple[int, int] | None:
    """The numbers behind the live infeasible-parents readout (M11b Phase A).

    The same shape as :func:`blocked_parents_metric` — the two metrics sit
    side by side in the Economy panel and are read the same way. The
    explanation lives in ``ECONOMY_HELP["infeasible_parents"]`` (the §12
    single-source rule).

    Args:
        infeasible: The per-period infeasible-parent counts so far (the
            timeseries' live series).

    Returns:
        ``(latest period's count, run total)``, or ``None`` before any
        period has finished.
    """
    if not infeasible:
        return None
    return infeasible[-1], sum(infeasible)
