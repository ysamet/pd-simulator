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

from pdsim.config.experiment import ExperimentConfig
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
        "no lottery, no extra randomness in the birth phase."
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
        "(each agent starts k matches and is drawn into ≈ k more)."
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
}
"""The single source for the Economy panel's inline (?) explainer texts."""


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """Everything the Economy panel shows, derived straight from a config.

    Attributes:
        matcher: The matching scheme the numbers assume.
        expected_matches: Matches one agent is expected to play per
            generation (N − 1 round-robin; ≈ 2k random_k).
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
    if config.matching.matcher == "round_robin":
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
    if config.match.length_mode == "fixed":
        rounds = float(config.match.rounds_per_match)
    else:
        rounds = 1.0 / (1.0 - config.match.continuation_probability)

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
        if config.matching.matcher == "round_robin":
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
