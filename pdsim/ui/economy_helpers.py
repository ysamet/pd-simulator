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
from dataclasses import dataclass
from typing import NamedTuple

from pdsim.config.experiment import ExperimentConfig, effective_neighbour_count
from pdsim.core.economy import age_mortality_active

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
        "drawn into as many in return)."
    ),
    "income": (
        "The two income extremes per generation: what an agent earns if every "
        "round of every match ends in mutual cooperation (all-C, at the reward "
        "payoff R) versus mutual defection (all-D, at the punishment payoff P). "
        "Real agents earn somewhere in between."
    ),
    "window": (
        "The survival window: with the total per-generation cost at or above "
        "the all-D income but below the all-C income, cooperators can pay "
        "their bills and defectors cannot — the metabolic filter is switched "
        "on. Below the window even defectors grow; above it everyone starves."
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
        "site. Either way, an agent sitting at several times the breeding "
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

_SPATIAL_REGIME_NOTE = (
    "Under spatial interaction the interaction budget is set by the grid's "
    "geometry — 2 × the effective neighbour count — no matter how large the "
    "population grows, so this window stays put for the whole run. " + SPATIAL_FINE_PRINT
)
"""The spatial branch's regime caption: bounded budget, plus the fine print."""


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
        matches_per_agent: 2 × the effective neighbour count — each agent
            starts a match with every reachable neighbour and is drawn into
            as many in return (the calibration guide §4.2's third regime,
            measured exactly in #139).
        rounds_per_agent: Matches × expected rounds per match.
        all_c_income: Per-generation income if every round is mutual
            cooperation (rounds per agent × R).
        all_d_income: Per-generation income if every round is mutual
            defection (rounds per agent × P).
        window_low: The survival window's lower bound (= all-D income).
        window_high: The survival window's upper bound (= all-C income);
            the window is ``window_low ≤ cost < window_high``.
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
) -> SpatialIncome:
    """The spatial survival-window arithmetic, as a pure paint-time function.

    Matches per agent = 2 × :func:`~pdsim.config.experiment.
    effective_neighbour_count` (reused, not re-derived — DECISIONS #141(e)):
    an interior agent initiates a match against each of its min(k, degree)
    reachable neighbours and is drawn into as many in return (§4.2 of the
    calibration guide; measured exactly in #139). Everything downstream —
    rounds per agent, the two income extremes, the window bounds — follows
    the same shape as the aspatial calibration branches. The figure is the
    fully-occupied, uniform-degree case (:data:`SPATIAL_FINE_PRINT` states
    it; any readout showing these numbers must carry that sentence).

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

    Returns:
        The full :class:`SpatialIncome` arithmetic.
    """
    matches = 2.0 * effective_neighbour_count(neighbourhood_shape, boundary, opponents_per_agent)
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
    correct report there. The synchronous-clock conjunct is the
    config-level equivalent of #141(c)'s table position (that cell lives in
    the greying table's SYNC column): the 2 × effective-neighbour-count
    figure was measured on the synchronous engine (#139), and the
    asynchronous clock's per-generation-equivalent match count has not been
    measured — so the async context keeps its pre-#154 report rather than
    getting a guessed formula (#154's scope clause).

    Args:
        config: The experiment being calibrated.

    Returns:
        True when the spatial arithmetic describes the configured run.
    """
    return (
        config.mode == "evolution"
        and config.dynamics.time_model == "synchronous"
        and config.structure.kind == "lattice"
        and config.matching.spatial_interaction
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
            window ``all-D ≤ cost < all-C`` — ``"inside"``, ``"below"``
            (even defectors grow), or ``"above"`` (everyone starves).
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
            (synchronous evolution on a lattice with spatial interaction
            on); the ``regime_note`` then carries
            :data:`SPATIAL_FINE_PRINT`.
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
    if spatial:
        # The spatial branch (#154): while partners genuinely come from the
        # grid, the greyed matcher's arithmetic would describe a mechanism
        # that is not running — the figures come from the geometry instead.
        arithmetic = spatial_income_arithmetic(
            neighbourhood_shape=config.structure.neighbourhood_shape,
            boundary=config.structure.boundary,
            opponents_per_agent=config.matching.opponents_per_agent,
            length_mode=config.match.length_mode,
            rounds_per_match=config.match.rounds_per_match,
            continuation_probability=config.match.continuation_probability,
            payoff_reward=config.game.payoff_reward,
            payoff_punishment=config.game.payoff_punishment,
        )
        matches = arithmetic.matches_per_agent
        regime_note = _SPATIAL_REGIME_NOTE
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
    elif total_cost < all_d:
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
            worst = 2 * rounds * dynamics.generations
            memory_note = (
                "Histories persist for an agent's whole life and memory depth "
                "is unlimited: under spatial interaction an agent's "
                "neighbours are FIXED, so a neighbouring pair meets twice "
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
