"""Scenario Registry — curated, ready-to-run experiment presets.

The third instance of the project's registry idiom (after the Parameter
Registry and the Strategy Registry): immutable declarations in one
module-level dict, written only at import time. Each scenario is a complete,
validated :class:`~pdsim.config.experiment.ExperimentConfig` plus the
novice-facing story around it — what question it explores and what to try
changing. The UI's scenario dropdown (M6) reads this registry; "Custom" is a
UI concept (start from any scenario, then edit), not a registry entry.

One scenario = one config (DECISIONS #36). Comparative questions ("re-run
with a different β and compare") live in the ``things_to_try`` text for now;
a run-both-and-compare mechanism is a possible future UI feature.

This module is also the designated future home of the v3 real-world scenario
presets (DESIGN §6.3): geographic/geopolitical setups will register here
exactly like the seed scenarios below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pdsim.config.experiment import ExperimentConfig

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
"""Scenario machine names follow the strategy-registry convention."""


@dataclass(frozen=True, slots=True)
class ScenarioInfo:
    """Complete declaration of one curated scenario.

    Attributes:
        name: Machine name, e.g. ``"classic_tournament"``.
        display_name: Human-readable name for the UI dropdown.
        description: Novice-friendly "what question does this explore?"
            text. Mandatory — mirrors hard rule 3.
        config: The complete, validated experiment configuration. Frozen
            like every config: the UI copies it into the parameter panel
            rather than editing it.
        things_to_try: Concrete parameter tweaks worth experimenting with,
            written for a non-expert.
    """

    name: str
    display_name: str
    description: str
    config: ExperimentConfig
    things_to_try: str

    def __post_init__(self) -> None:
        """Check that the declaration is well-formed (fail fast at import).

        Raises:
            ValueError: If the machine name is malformed or either
                novice-facing text is missing.
        """
        if not _NAME_PATTERN.match(self.name):
            raise ValueError(
                f"Scenario machine name {self.name!r} must be a lowercase token "
                "like 'classic_tournament'."
            )
        if not self.description.strip():
            raise ValueError(f"Scenario {self.name!r} has no description — hard rule 3's mirror.")
        if not self.things_to_try.strip():
            raise ValueError(f"Scenario {self.name!r} has no things_to_try note.")


_SCENARIOS: dict[str, ScenarioInfo] = {}


def register_scenario(info: ScenarioInfo) -> ScenarioInfo:
    """Add a scenario to the registry.

    Args:
        info: The fully-declared scenario.

    Returns:
        The same info (the registry idiom's convention).

    Raises:
        ValueError: If a scenario with the same machine name exists.
    """
    if info.name in _SCENARIOS:
        raise ValueError(f"Scenario {info.name!r} is already registered; names must be unique.")
    _SCENARIOS[info.name] = info
    return info


def get_scenario_info(name: str) -> ScenarioInfo:
    """Look up a scenario by machine name.

    Args:
        name: Machine name, e.g. ``"noise_breaks_the_grim"``.

    Returns:
        The registered :class:`ScenarioInfo`.

    Raises:
        KeyError: If no scenario with this name exists (the message lists
            the registered names).
    """
    try:
        return _SCENARIOS[name]
    except KeyError:
        known = ", ".join(sorted(_SCENARIOS))
        raise KeyError(f"Unknown scenario {name!r}. Registered scenarios: {known}") from None


def all_scenarios() -> tuple[ScenarioInfo, ...]:
    """Return every registered scenario, in registration (= display) order.

    Returns:
        An immutable snapshot of the registry.
    """
    return tuple(_SCENARIOS.values())


def all_scenario_names() -> tuple[str, ...]:
    """Return every registered machine name, in registration order.

    Returns:
        The names the UI dropdown and lookups may use.
    """
    return tuple(_SCENARIOS)


# ---------------------------------------------------------------------------
# The five v1 seed scenarios. Sizes are tuned to run live in the GUI within
# seconds while still showing each phenomenon clearly.
# ---------------------------------------------------------------------------

register_scenario(
    ScenarioInfo(
        name="classic_tournament",
        display_name="The Classic Tournament",
        description=(
            "Axelrod's original question: which strategy wins a round-robin "
            "tournament? All seven strategies field three agents each and play "
            "repeated matches — nothing evolves, the scores just accumulate. "
            "Watch whether niceness or exploitation pays over the long haul."
        ),
        config=ExperimentConfig.model_validate(
            {
                "mode": "tournament",
                "tournament_cycles": 10,
                "seed": 42,
                "population": {
                    "size": 21,
                    "composition": {
                        "always_cooperate": 3,
                        "always_defect": 3,
                        "generous_tit_for_tat": 3,
                        "grim_trigger": 3,
                        "pavlov": 3,
                        "random": 3,
                        "tit_for_tat": 3,
                    },
                },
                "match": {"length_mode": "fixed", "rounds_per_match": 20},
            }
        ),
        things_to_try=(
            "Add execution noise (try 0.05) and watch Grim Trigger tumble down the "
            "standings. Shorten the matches to 5 rounds — with less future to "
            "protect, defection starts paying."
        ),
    )
)

register_scenario(
    ScenarioInfo(
        name="reciprocity_takes_over",
        display_name="Reciprocity Takes Over",
        description=(
            "Can cooperation win in a population of defectors and coin-flippers? "
            "Tit for Tat, Always Defect, and Random start in equal numbers under "
            "evolution. The classic result: reciprocity invades and takes over — "
            "and afterwards, mutation-injected cooperative cousins drift in "
            "neutrally, because everyone is already cooperating."
        ),
        config=ExperimentConfig.model_validate(
            {
                "seed": 42,
                "population": {
                    "size": 24,
                    "composition": {"tit_for_tat": 8, "always_defect": 8, "random": 8},
                },
                "match": {"length_mode": "fixed", "rounds_per_match": 20},
                "dynamics": {
                    "generations": 30,
                    "selection_beta": 0.02,
                    "mutation_rate": 0.02,
                },
            }
        ),
        things_to_try=(
            "Set the mutation rate to 0 and the takeover becomes permanent — no "
            "drifting newcomers. Cut the rounds per match to 5 and watch Tit for "
            "Tat struggle: reciprocity needs repetition to pay off."
        ),
    )
)

register_scenario(
    ScenarioInfo(
        name="noise_breaks_the_grim",
        display_name="Noise Breaks the Grim",
        description=(
            "Which reciprocal strategies survive a trembling hand? With a 5% "
            "chance that any action flips by accident, one slip poisons Grim "
            "Trigger's relationships forever, while forgiving reciprocators "
            "(Generous Tit for Tat, Pavlov) can repair the damage. Evolution "
            "decides who copes."
        ),
        config=ExperimentConfig.model_validate(
            {
                "seed": 7,
                "population": {
                    "size": 24,
                    "composition": {
                        "grim_trigger": 9,
                        "tit_for_tat": 5,
                        "generous_tit_for_tat": 5,
                        "pavlov": 5,
                    },
                },
                "match": {
                    "length_mode": "fixed",
                    "rounds_per_match": 30,
                    "noise_epsilon": 0.05,
                },
                "dynamics": {
                    "generations": 40,
                    "selection_beta": 0.02,
                    "mutation_rate": 0.02,
                },
            }
        ),
        things_to_try=(
            "Set the noise to 0 and Grim Trigger is suddenly a fine citizen — the "
            "whole drama is noise-driven. Crank the noise to 0.2 and see whether "
            "even the forgivers can hold cooperation together."
        ),
    )
)

register_scenario(
    ScenarioInfo(
        name="drift_vs_meritocracy",
        display_name="Drift vs Meritocracy",
        description=(
            "What does selection intensity actually do? With β = 0.001, scores "
            "barely matter: strategies rise and fall by luck (neutral drift), "
            "and even strong performers can vanish by chance. This is the "
            "control experiment for every other scenario."
        ),
        config=ExperimentConfig.model_validate(
            {
                "seed": 11,
                "population": {
                    "size": 21,
                    "composition": {
                        "always_cooperate": 3,
                        "always_defect": 3,
                        "generous_tit_for_tat": 3,
                        "grim_trigger": 3,
                        "pavlov": 3,
                        "random": 3,
                        "tit_for_tat": 3,
                    },
                },
                "match": {"length_mode": "fixed", "rounds_per_match": 20},
                "dynamics": {
                    "generations": 50,
                    "selection_beta": 0.001,
                    "mutation_rate": 0.01,
                },
            }
        ),
        things_to_try=(
            "Re-run with selection intensity 0.5 and compare: the same starting "
            "mix now sorts sharply by score instead of wandering. That contrast — "
            "not either run alone — is the lesson."
        ),
    )
)

register_scenario(
    ScenarioInfo(
        name="defectors_paradise",
        display_name="Defectors' Paradise",
        description=(
            "Can a small band of reciprocators invade a world of defectors? "
            "Twenty Always Defect agents and just four Tit for Tats, but the "
            "matches are long (high continuation probability — a long 'shadow of "
            "the future') and selection is strong. Cooperation among the few can "
            "out-earn universal betrayal."
        ),
        config=ExperimentConfig.model_validate(
            {
                "seed": 5,
                "population": {
                    "size": 24,
                    "composition": {"always_defect": 20, "tit_for_tat": 4},
                },
                "match": {"length_mode": "continuation", "continuation_probability": 0.98},
                "dynamics": {
                    "generations": 30,
                    "selection_beta": 0.1,
                    "mutation_rate": 0.005,
                },
            }
        ),
        things_to_try=(
            "Lower the continuation probability to 0.5 (short matches) and the "
            "invasion fails — the shadow of the future is the whole story. Try 2 "
            "Tit for Tats instead of 4: is there a critical cluster size?"
        ),
    )
)

# The M10a energy-economy scenario. The numbers are a worked calibration
# (see the spec and docs/explainers/M10-growth-economy-explainer.md):
# random_k with k=5 gives ≈ 2k = 10 matches/agent × 10 rounds = 100 rounds;
# all-C income = 300, all-D income = 100, and the living cost of 200 sits at
# the midpoint of that window — cooperators net +100/generation, defectors
# net −100 and are extinct by generation 5.

register_scenario(
    ScenarioInfo(
        name="the_growth_economy",
        display_name="The Growth Economy",
        description=(
            "What happens when survival costs energy and playing earns it? "
            "Agents pay a living bill every generation, breed when they can "
            "afford the stake, and die when their energy runs out — nobody "
            "copies anyone. Cooperators generate more energy per interaction "
            "than defectors do, so the same bill that cooperators shrug off "
            "can drive defectors extinct, while the population itself grows "
            "toward its carrying capacity."
        ),
        config=ExperimentConfig.model_validate(
            {
                "seed": 42,
                "population": {
                    "size": 40,
                    "composition": {"tit_for_tat": 20, "always_defect": 20},
                },
                "matching": {"matcher": "random_k", "opponents_per_agent": 5},
                "match": {"length_mode": "fixed", "rounds_per_match": 10},
                "dynamics": {
                    "generations": 60,
                    "reproduction_mode": "energy_economy",
                    "reproduction_threshold": 500.0,
                    "offspring_stake": 400.0,
                    "basic_living_cost": 200.0,
                    "carrying_capacity": 200,
                    "mutation_rate": 0.0,
                },
            }
        ),
        things_to_try=(
            "Set the basic living cost to 320 (above the all-cooperator income "
            "of 300) and EVERYONE dies — the survival window is real. Set it "
            "to 80 (below the all-defector income of 100) and even defectors "
            "grow, because the filter is switched off. Switch the composition "
            "to 40 Always Defect and watch the population collapse over "
            "generations 4 to 6 — not all at once: every defector is on the "
            "same average trajectory, so they all approach zero energy "
            "together, and who actually crosses first is decided by "
            "participation luck, since under random_k some agents get drawn "
            "into more matches than others. Set the max age to 20 and watch "
            "the mean-age chart settle. Set the capital return rate to 0.05 "
            "and watch the escape velocity appear in the Economy panel."
        ),
    )
)

# ---------------------------------------------------------------------------
# The four M10b event-time scenarios (spec Validation V1/V2/V3/V5). Sizes are
# tuned to run live in the GUI while showing each phenomenon; the Moran pair
# uses the textbook corner (sigma = 0, L = 0, pure_random deaths) so what you
# watch is the update rule itself, not the economy.
# ---------------------------------------------------------------------------

register_scenario(
    ScenarioInfo(
        name="async_death_birth_fixation",
        display_name="Async: Death-Birth Fixation",
        description=(
            "What does evolution look like when time has no generations? "
            "Here the clock ticks one event at a time: an agent is drawn, "
            "plays its matches, and then one randomly chosen agent dies and "
            "the rest compete — weighted by accumulated energy — to fill "
            "the empty seat (the classic Moran death-birth update). The "
            "population count is pinned, so the only thing that can change "
            "is WHO the population is: watch one strategy drift and drive "
            "toward complete fixation while the total height of the "
            "composition chart never moves. The x-axis is "
            "generation-equivalents: N events, one population's worth of "
            "activity, per unit."
        ),
        config=ExperimentConfig.model_validate(
            {
                "seed": 21,
                "population": {
                    "size": 24,
                    "composition": {"tit_for_tat": 12, "always_defect": 12},
                },
                "matching": {"matcher": "random_k", "opponents_per_agent": 4},
                "match": {"length_mode": "fixed", "rounds_per_match": 8},
                "dynamics": {
                    "generations": 50,
                    "time_model": "asynchronous",
                    "async_population": "fixed_n",
                    "moran_rule": "death_birth",
                    "fixed_n_death_rule": "pure_random",
                    "offspring_stake": 0.0,
                    "basic_living_cost": 0.0,
                    "mutation_rate": 0.0,
                },
            }
        ),
        things_to_try=(
            "Switch the Moran rule to birth_death — now the breeder is "
            "chosen first and its offspring replaces someone else; the two "
            "orders differ subtly in who is at risk. Switch the death rule "
            "to energy_decides and the reaper stops being blind: the "
            "lowest-energy agent always dies, so newborns (who start at "
            "the stake, here 0) live dangerously. Set the mutation rate to "
            "0.01 and fixation stops being forever — the lost strategy "
            "keeps reappearing."
        ),
    )
)

register_scenario(
    ScenarioInfo(
        name="imitation_overlay_only",
        display_name="Async: Imitation Only",
        description=(
            "Can a population change what it plays without anyone being "
            "born or dying? This run switches every demographic channel "
            "off — the breeding threshold is unreachable, the living cost "
            "is zero, and there is no age limit — and turns ON the "
            "imitation overlay: after each match, one of the two players "
            "(picked by a fair coin, regardless of score) considers "
            "copying the other's strategy, and the better the other "
            "scored IN THAT MATCH, the likelier the copy. Watch strategy "
            "shares move while the population count stays perfectly flat — "
            "and watch WHICH WAY and HOW FAST they move: defection sweeps "
            "the population within a couple of generation-equivalents. In "
            "any mixed match the defector out-earns the very reciprocator "
            "it is exploiting, so copying match winners favours Always "
            "Defect even though reciprocators earn more from each other — "
            "and because copying happens per MATCH, minds change on the "
            "interaction timescale, far faster than any demographic "
            "takeover. The run records per event, so you see every single "
            "step of the sweep."
        ),
        config=ExperimentConfig.model_validate(
            {
                "seed": 8,
                "population": {
                    "size": 20,
                    "composition": {"tit_for_tat": 10, "always_defect": 10},
                },
                "matching": {"matcher": "random_k", "opponents_per_agent": 4},
                "match": {"length_mode": "fixed", "rounds_per_match": 8},
                "dynamics": {
                    "generations": 6,
                    "time_model": "asynchronous",
                    "async_population": "variable_n",
                    "imitation_overlay": True,
                    "selection_beta": 0.2,
                    "reproduction_threshold": 1e9,
                    "offspring_stake": 0.0,
                    "basic_living_cost": 0.0,
                    "mutation_rate": 0.0,
                },
                "output": {"recording_cadence": "per_event"},
            }
        ),
        things_to_try=(
            "Set the selection intensity to 0 and the copying becomes a "
            "pure coin flip — neutral drift, which still churns just as "
            "fast but with no direction: try a few seeds and either "
            "strategy can sweep. Crank it to 10 and the takeover is "
            "nearly one-way. Compare with The Growth Economy, where the "
            "SAME strategies compete demographically and cooperators win "
            "— the two channels reward different things. Check the "
            "recorded run in the Results browser: total agents born "
            "equals the twenty founders; only minds changed."
        ),
    )
)

register_scenario(
    ScenarioInfo(
        name="moran_random_mix",
        display_name="Async: Mixed Moran Rules",
        description=(
            "What lies between the two classic Moran updates? Each event "
            "here rolls a weighted coin: 80% of events run birth-death "
            "(pick a breeder by energy, its offspring replaces a random "
            "other) and 20% run death-birth (a random agent dies, the "
            "rest compete for the seat). With only 24 agents any single "
            "run is a fixation GAMBLE — higher earners are favoured to "
            "take over, not guaranteed to — and the rule mixture shifts "
            "the odds. This seed happens to fixate Always Defect: an "
            "early lucky streak snowballs, which is exactly what finite-"
            "population drift means."
        ),
        config=ExperimentConfig.model_validate(
            {
                "seed": 21,
                "population": {
                    "size": 24,
                    "composition": {"tit_for_tat": 12, "always_defect": 12},
                },
                "matching": {"matcher": "random_k", "opponents_per_agent": 4},
                "match": {"length_mode": "fixed", "rounds_per_match": 8},
                "dynamics": {
                    "generations": 50,
                    "time_model": "asynchronous",
                    "async_population": "fixed_n",
                    "moran_rule": "random",
                    "moran_weight_birth_death": 0.8,
                    "moran_weight_death_birth": 0.2,
                    "fixed_n_death_rule": "pure_random",
                    "offspring_stake": 0.0,
                    "basic_living_cost": 0.0,
                    "mutation_rate": 0.0,
                },
            }
        ),
        things_to_try=(
            "Set the weights to 1/0 (pure birth-death), then 0/1 (pure "
            "death-birth), and run each across a few seeds — single runs "
            "are gambles, so it is the SPREAD of outcomes the mixture "
            "sits between, not any one trajectory. Switch the death rule "
            "to energy_decides and the gamble largely disappears: the "
            "reaper targets the poorest, so the higher earners fixate far "
            "more reliably. In this well-mixed world the rules differ "
            "only mechanically; when population structure arrives (M11), "
            "death-birth is the update under which neighbourhoods can "
            "favour cooperation."
        ),
    )
)

register_scenario(
    ScenarioInfo(
        name="sync_vs_async_economy",
        display_name="Async: The Growth Economy in Event Time",
        description=(
            "The Growth Economy again — same costs, same stakes, same "
            "carrying capacity — but with the generation dissolved: births "
            "fire the moment a parent clears the threshold, deaths fire "
            "the moment energy runs out, and the clock advances 1/N per "
            "event. The population still grows from 40 toward the "
            "carrying capacity of 200 as defectors go extinct, on a "
            "comparable x-axis (generation-equivalents carry the same "
            "per-agent interaction budget as generations). Flip the time "
            "model back to synchronous and compare: the same growth "
            "story, told by two different clocks."
        ),
        config=ExperimentConfig.model_validate(
            {
                "seed": 42,
                "population": {
                    "size": 40,
                    "composition": {"tit_for_tat": 20, "always_defect": 20},
                },
                "matching": {"matcher": "random_k", "opponents_per_agent": 5},
                "match": {"length_mode": "fixed", "rounds_per_match": 10},
                "dynamics": {
                    "generations": 60,
                    "time_model": "asynchronous",
                    "async_population": "variable_n",
                    "reproduction_mode": "energy_economy",
                    "reproduction_threshold": 500.0,
                    "offspring_stake": 400.0,
                    "basic_living_cost": 200.0,
                    "carrying_capacity": 200,
                    "mutation_rate": 0.0,
                },
            }
        ),
        things_to_try=(
            "Flip the time model to synchronous and run again: both runs "
            "grow from 40 toward K = 200 and the Economy panel's survival "
            "window applies to both — but they are NOT identical runs, "
            "and should not be: event time compounds interest continuously "
            "over income that arrives mid-period, where the generational "
            "clock applies it once at each boundary. Switch the recording "
            "cadence to per_event to see every single birth and death at "
            "full resolution (bigger files, denser charts)."
        ),
    )
)

# ---------------------------------------------------------------------------
# The four M11a population-structure scenarios (spec Validation; DECISIONS
# #151, with three things-to-try rewordings recorded in #152). Every override
# of a registry default is deliberate and its reason is carried in the
# scenario text itself; the worked arithmetic is written so a novice can
# reproduce every number in the description from the settings shown.
# ---------------------------------------------------------------------------

register_scenario(
    ScenarioInfo(
        name="spatial_reciprocity",
        display_name="Cooperation Survives in Clusters",
        description=(
            "Can cooperation survive on pure geography, with no reciprocity "
            "at all? Two hundred agents — half Always Cooperate, half Always "
            "Defect — live on a 20 × 20 torus of 400 sites, so the world "
            "starts half empty and clusters have room to breathe (left "
            "blank, the grid would auto-size to exactly 200 sites — a full "
            "world with no room). Reproduction is the energy economy rather "
            "than copying because the story is ECOLOGICAL survival: agents "
            "live or die on absolute income measured against a survival "
            "bill. The founding layout is 'patches' — contiguous clusters "
            "from generation 0, dealt inside a centred 200-site blob — so "
            "the interior-versus-edge arithmetic below is on screen "
            "immediately. Spatial interaction is on with the von Neumann "
            "neighbourhood (4 orthogonal neighbours — fewer neighbours "
            "means stronger viscosity, the setting most likely to let "
            "clusters win), the torus keeps every site at exactly 4 "
            "neighbours (which is what makes the interior arithmetic "
            "exact), the opponents-per-agent count of 5 simply clamps to "
            "the 4 neighbours that exist (play-all-your-neighbours), and "
            "children land right next to their parents (birth radius 1). "
            "Matches last ONE round, so matches and rounds are the same "
            "number and every figure below is per generation. The income "
            "rates: each adjacent pair meets twice per generation (each "
            "side initiates one match — measured in this engine, exactly), "
            "so with T = 5, R = 3, P = 0, S = −1 a cooperator earns +6 per "
            "cooperating neighbour (2 × R) and −2 per defecting neighbour "
            "(2 × S), while a defector earns +10 per cooperating neighbour "
            "(2 × T) and 0 per defecting neighbour (2 × P). P is set to 0 — "
            "overriding the default 1 — because the scenario's whole claim "
            "is that a defector interior earns NOTHING against the living "
            "cost; and S = −1 keeps the strict T > R > P > S ordering legal "
            "with P at 0, and makes cluster edges actively bleed energy "
            "rather than merely fail to earn it. An agent with all four "
            "neighbour sites occupied plays exactly 8 matches per "
            "generation (4 it initiates + 4 it is drawn into): an interior "
            "cooperator earns 8 × 3 = 24, an interior defector 8 × 0 = 0, "
            "so the survival window is 0 ≤ L < 24 and the living cost of "
            "12 sits at its midpoint. At L = 12 a cooperator with n "
            "cooperating neighbours (all four sites occupied) earns "
            "8n − 8: interiors net +12, flat cluster edges (n = 3) net +4, "
            "corners (n = 2) net −4 — compact clusters thrive, ragged "
            "edges erode. A defector touching one cooperator earns 10 and "
            "nets −2: it starves, slowly; only a defector hugging two or "
            "more cooperators profits, so frontier parasitism is present "
            "but contained. (Agents on the blob's rim have empty neighbour "
            "sites, play fewer matches, and earn proportionally less — the "
            "formulas above are the full-occupancy cases.) The ledger "
            "paces the drama: interior defectors fall 12 per generation "
            "from their starting 40 and die during generation 4; interior "
            "cooperators rise 12 per generation, first breed at generation "
            "2 (64 ≥ the threshold of 60), pay the 40-point stake to the "
            "child, and settle into a three-generation breeding rhythm. "
            "Mutation is 0 so no copying-rule mutant can seed a defector "
            "inside a cooperator cluster and muddy that arithmetic, and "
            "100 generations is plenty: defector interiors die by about "
            "generation 4, and the edge dynamics play out over tens of "
            "generations. One guard, because it is easy to blur: this "
            "scenario does NOT rest on the b/c > k threshold. Its story is "
            "ecological — absolute income against a survival threshold, "
            "with P = 0 meaning a defector interior earns nothing — while "
            "b/c > k concerns relative fitness in a Moran process under "
            "weak selection, and that is 'The b/c > k Threshold' "
            "scenario's story. The two arguments happen to point the same "
            "way and must never be conflated; this matrix is not even "
            "additive (T − R = 2 against P − S = 1), so 'b/c' is not "
            "defined here — the additivity readout beside the payoff "
            "widgets says so."
        ),
        config=ExperimentConfig.model_validate(
            {
                "seed": 42,
                "population": {
                    "size": 200,
                    "composition": {"always_cooperate": 100, "always_defect": 100},
                },
                "game": {
                    "payoff_temptation": 5.0,
                    "payoff_reward": 3.0,
                    "payoff_punishment": 0.0,
                    "payoff_sucker": -1.0,
                },
                "matching": {"spatial_interaction": True, "opponents_per_agent": 5},
                "match": {"length_mode": "fixed", "rounds_per_match": 1},
                "structure": {
                    "kind": "lattice",
                    "rows": 20,
                    "cols": 20,
                    "neighbourhood_shape": "von_neumann",
                    "boundary": "torus",
                    "initial_layout": "patches",
                },
                "dynamics": {
                    "generations": 100,
                    "reproduction_mode": "energy_economy",
                    "reproduction_threshold": 60.0,
                    "offspring_stake": 40.0,
                    "basic_living_cost": 12.0,
                    "mutation_rate": 0.0,
                },
            }
        ),
        things_to_try=(
            "First, the well-mixed comparison — in this order: turn Spatial "
            "interaction OFF first, then switch the world structure to "
            "well_mixed, then set the matching scheme to random_k (the "
            "opponents-per-agent count is already 5). The order matters: "
            "under well_mixed the spatial toggle greys out with its value "
            "stranded, and a stranded-on toggle fails validation — switch "
            "it off while it is still editable. The matcher matters too: "
            "the default round-robin at 200 agents would give every agent "
            "199 matches, income two orders of magnitude above L = 12, and "
            "the filter would simply be off. With random_k at k = 5 the "
            "arithmetic stays on the spatial run's scale: about 2k = 10 "
            "matches, so a cooperator meeting the average 50/50 mix earns "
            "about 5 × 3 + 5 × (−1) = 10 and nets −2 against L = 12, "
            "starving slowly, while a defector earns about "
            "5 × 5 + 5 × 0 = 25 and nets +13, breeding freely. Always "
            "Defect takes everything — and then, with the cooperators "
            "gone, all-defector income is 0 against L = 12 and the whole "
            "population collapses. Without a grid to cluster on, "
            "cooperation dies first and everyone follows: the tragedy "
            "completes. Second, the Moore switch, as arithmetic rather "
            "than prediction: the naive reading says von Neumann means 4 "
            "matches; the measured truth is 8; Moore at k ≥ 8 (raise "
            "Opponents per agent to 8 to play all eight neighbours) gives "
            "16 by the same arithmetic. Against the naive reading that is "
            "a FOUR-fold income change (16 vs 4); against the actual it "
            "is two-fold (16 vs 8). At L = 12 the Moore all-cooperator "
            "interior income of 48 sits far above the cost and the "
            "metabolic filter loosens dramatically — the window becomes "
            "0 ≤ L < 48 with L sitting in its lower quarter. Whether "
            "clusters struggle under the weaker viscosity is then "
            "something to watch, not something promised: recompute the "
            "window before trusting any living cost after this switch."
        ),
    )
)

register_scenario(
    ScenarioInfo(
        name="donation_game_threshold",
        display_name="The b/c > k Threshold",
        description=(
            "The closest this platform can come to a textbook replication: "
            "the death-birth rule on a lattice, where theory (Ohtsuki and "
            "colleagues) says cooperation is favoured when the "
            "benefit-to-cost ratio of helping exceeds the number of "
            "neighbours — b/c > k. One hundred agents fill a 10 × 10 torus "
            "exactly (the fixed-size Moran mode requires one agent per "
            "site), half Always Cooperate and half Always Defect, "
            "scattered at random; the neighbourhood is von Neumann, so "
            "k = 4 — the case that CLEARS the b/c = 5 threshold, which is "
            "why the default view shows cooperation succeeding — and "
            "Opponents per agent is 4, exact play-all at the von Neumann "
            "degree. Four settings are load-bearing, and each deserves its "
            "reason. (1) ONE round per match, with only these two "
            "strategies: the threshold is derived for one-shot games, so "
            "noise, memory depth, and every reciprocity parameter are "
            "inert here — that is where the seven-strategy roster went; at "
            "one round Tit for Tat would just cooperate and be "
            "indistinguishable from Always Cooperate anyway. (2) The "
            "fixed-N death rule is pure_random, NOT the default "
            "energy_decides: this death-birth process kills a RANDOM "
            "individual, whose neighbours then compete by fitness for the "
            "empty site. The default makes the death deterministic — a "
            "plausible-looking run that is not the model being replicated. "
            "(3) The honesty caveat: in this engine the competition for "
            "the empty seat reads each candidate's ACCUMULATED lifetime "
            "energy, with no selection-intensity dial, so the "
            "weak-selection limit in which b/c > k is derived cannot be "
            "approached here. Selection begins at exactly zero (every "
            "founder holds identical energy, so the draw starts uniform) "
            "and strengthens from nothing — and because fitness reads a "
            "lifetime stock rather than a current flow, the draw partly "
            "selects for AGE rather than strategy. Measured in this "
            "engine across 20 seeds per shape, the mean final cooperator "
            "share was 0.596 under von Neumann against 0.569 under Moore "
            "— inside sampling noise, with NO visible reversal. The "
            "threshold is a calibration compass, not a prediction. "
            "(4) Additivity — the payoffs T = 5, R = 4, P = 0, S = −1 are "
            "not arbitrary: read the cost of cooperating off the matrix "
            "twice and you get T − R = 1 against a cooperator and "
            "P − S = 1 against a defector — the same number, c = 1 — and "
            "the benefit falls out symmetrically (T − P = 5 = R − S, so "
            "b = 5), making b/c = 5 unambiguous. The registered default "
            "payoffs (5, 3, 1, 0) FAIL that test: a perfectly valid "
            "Prisoner's Dilemma that is simply not a donation game, under "
            "which 'b/c' is not a well-defined quantity at all. And "
            "additivity with P = 0 forces the negative sucker payoff — "
            "S = −1 is not a stylistic choice. Mutation is 0 so fixation, "
            "when it comes, is permanent and readable; 150 "
            "generation-equivalents is the horizon the in-engine "
            "measurement used. One last honesty note: the shipped seed is "
            "one on which cooperation happens to win. At this selection "
            "strength any single run is a fixation gamble (the 20-seed "
            "measurement above is the honest picture), so try other seeds "
            "and expect either outcome."
        ),
        config=ExperimentConfig.model_validate(
            {
                "seed": 4,
                "population": {
                    "size": 100,
                    "composition": {"always_cooperate": 50, "always_defect": 50},
                },
                "game": {
                    "payoff_temptation": 5.0,
                    "payoff_reward": 4.0,
                    "payoff_punishment": 0.0,
                    "payoff_sucker": -1.0,
                },
                "matching": {"spatial_interaction": True, "opponents_per_agent": 4},
                "match": {"length_mode": "fixed", "rounds_per_match": 1},
                "structure": {
                    "kind": "lattice",
                    "rows": 10,
                    "cols": 10,
                    "neighbourhood_shape": "von_neumann",
                    "boundary": "torus",
                    "initial_layout": "random",
                },
                "dynamics": {
                    "generations": 150,
                    "time_model": "asynchronous",
                    "async_population": "fixed_n",
                    "moran_rule": "death_birth",
                    "fixed_n_death_rule": "pure_random",
                    "mutation_rate": 0.0,
                },
            }
        ),
        things_to_try=(
            "Switch the neighbourhood shape to moore and re-run. Theory "
            "predicts a reversal — k = 8 exceeds b/c = 5 and fails the "
            "threshold that k = 4 clears — so state that prediction, run "
            "it, and expect very little visible change. The gap between "
            "the prediction and the observation IS the weak-selection "
            "lesson: this engine's selection is far from the limit in "
            "which the threshold is derived, and the compass points where "
            "the prediction cannot. Second warning: the payoffs are live "
            "widgets, and the threshold only applies while T − R = P − S "
            "holds — the additivity readout beside the payoff widgets "
            "says when it no longer does."
        ),
    )
)

register_scenario(
    ScenarioInfo(
        name="the_drifting_frontier",
        display_name="The Drifting Frontier",
        description=(
            "What does a population look like when it CANNOT fill its "
            "world? 120 agents — Tit for Tat, Always Cooperate, and Always "
            "Defect, forty each — found as patches on a 20 × 20 grid of "
            "400 sites, with the carrying capacity set to 240: 60% of the "
            "site count, so 160 sites' worth of slack is always in play. "
            "This is the growth economy's own calibration, moved onto a "
            "lattice: random_k matching with k = 5 gives each agent about "
            "2k = 10 matches per generation, 10 rounds per match makes "
            "100 rounds, so all-cooperator income is 100 × 3 = 300 and "
            "all-defector income is 100 × 1 = 100 — the survival window "
            "is 100 ≤ L < 300, and the living cost of 200 sits at its "
            "midpoint (a cooperator-pair economy nets +100 per "
            "generation; an all-defect economy −100). Spatial interaction "
            "is deliberately OFF: local birth WITHOUT local interaction "
            "is a legitimate configuration in its own right, and this "
            "scenario demonstrates the separability — children land "
            "within radius 1 of their parents (the birth kernel is the "
            "active spatial mechanism here) while everyone still plays "
            "everyone, which is also what keeps the window arithmetic "
            "above honestly aspatial. The churn comes from a 5% base "
            "hazard with the senescence factor pinned at 1 (age never "
            "matters — the hazard is a flat coin every generation), so "
            "the mean lifetime is 20 generations and deaths land ANYWHERE "
            "on the grid. The story to watch: deaths free sites anywhere, "
            "births fill sites only next to parents, and the 160-site "
            "slack means the occupied region drifts, clusters, and "
            "migrates across the world rather than filling it. Mutation "
            "is 0, keeping the three-way composition clean, and 200 "
            "generations is ten full population turnovers — drift is "
            "slow. Compare the Founding and Final grid views in the "
            "results browser to see how far the region wandered."
        ),
        config=ExperimentConfig.model_validate(
            {
                "seed": 7,
                "population": {
                    "size": 120,
                    "composition": {
                        "tit_for_tat": 40,
                        "always_cooperate": 40,
                        "always_defect": 40,
                    },
                },
                "game": {
                    "payoff_temptation": 5.0,
                    "payoff_reward": 3.0,
                    "payoff_punishment": 1.0,
                    "payoff_sucker": 0.0,
                },
                "matching": {
                    "spatial_interaction": False,
                    "matcher": "random_k",
                    "opponents_per_agent": 5,
                },
                "match": {"length_mode": "fixed", "rounds_per_match": 10},
                "structure": {
                    "kind": "lattice",
                    "rows": 20,
                    "cols": 20,
                    "initial_layout": "patches",
                    "birth_radius": 1,
                    "birth_decay": 0.0,
                },
                "dynamics": {
                    "generations": 200,
                    "reproduction_mode": "energy_economy",
                    "reproduction_threshold": 500.0,
                    "offspring_stake": 400.0,
                    "basic_living_cost": 200.0,
                    "carrying_capacity": 240,
                    "base_hazard": 0.05,
                    "senescence_factor": 1.0,
                    "mutation_rate": 0.0,
                },
            }
        ),
        things_to_try=(
            "Clear the carrying capacity (leave it blank): on a lattice, "
            "blank resolves to the site count — 400 — and the slack "
            "vanishes: the grid fills and the drift stops. Then try the "
            "recalibration drill, in two steps: turn Spatial interaction "
            "ON and RECOMPUTE the window before trusting the living cost. "
            "First, at the default Moore shape: matches per agent is "
            "about 2 × min(5, 8) = 10 — the window happens NOT to move. "
            "That is the drill working, not failing: sometimes its answer "
            "is 'no change', and you only know by running it. Second, "
            "switch the shape to von Neumann: min(5, 4) = 4, so 8 "
            "matches, 80 rounds — the window is now 80 ≤ L < 240 and the "
            "living cost of 200 sits near its top: all-cooperator pairs "
            "net +40 where they netted +100, and all-defect nets −120."
        ),
    )
)

register_scenario(
    ScenarioInfo(
        name="the_filling_grid",
        display_name="The Filling Grid",
        description=(
            "Sixty agents — half Always Cooperate, half Always Defect — "
            "start packed into a centred 6 × 10 rectangle (the most-square "
            "rectangle holding 60) with 340 empty sites around them: the "
            "FILLING regime, a population expanding into empty space (the "
            "early-run setting Kaznatcheev & Shultz's result concerns, "
            "and the reason the central_block layout exists). The "
            "carrying capacity is left blank and resolves to the site "
            "count, 400, so the grid itself is the only cap. Spatial "
            "interaction is on at the default Moore neighbourhood — kept "
            "deliberately, as the contrast with the flagship's von "
            "Neumann — with Opponents per agent at 8 (play-all at the "
            "Moore degree) and 10 rounds per match. The payoffs stay at "
            "the defaults (5, 3, 1, 0), and P = 1 is the deliberate "
            "anti-flagship choice: a saturated defector interior earns "
            "16 matches × 10 rounds × 1 = 160 per generation and never "
            "starves. During the fill, frontier agents with few "
            "neighbours earn little — a cooperator pair alone on the "
            "edge plays 2 matches × 10 rounds × 3 = 60 and nets +20 "
            "against the living cost of 40 — while an all-cooperator "
            "interior plays 16 × 10 = 160 rounds, earns 480, and nets "
            "+440, breeding nearly every generation against the 50-point "
            "gap between the 150-point stake and the 200-point "
            "threshold. Free space means everyone who can pay expands, "
            "and cooperation's share can rise early. At saturation, "
            "though, the metabolic filter is OFF for interiors — the "
            "saturated interior window is 160 ≤ L < 480 and L = 40 sits "
            "BELOW it, so even a solid defector block clears its bills. "
            "The only agents who can starve are cooperators whose "
            "occupied neighbours are ALL defectors: a cooperator earns "
            "60 per cooperating neighbour and 0 per defecting one, so a "
            "single cooperator contact clears the 40-point bill and zero "
            "contacts means income 0 < 40. That is the grinding "
            "mechanism, stated as mechanism rather than metaphor: "
            "defectors encircle a boundary cooperator, it starves, they "
            "breed into the grave, and the front advances one cell at a "
            "time — which is why the fall is slow. RISE THEN FALL is the "
            "expected observable here, not cooperation winning; 300 "
            "generations gives the slow half room to be visible."
        ),
        config=ExperimentConfig.model_validate(
            {
                "seed": 11,
                "population": {
                    "size": 60,
                    "composition": {"always_cooperate": 30, "always_defect": 30},
                },
                "game": {
                    "payoff_temptation": 5.0,
                    "payoff_reward": 3.0,
                    "payoff_punishment": 1.0,
                    "payoff_sucker": 0.0,
                },
                "matching": {"spatial_interaction": True, "opponents_per_agent": 8},
                "match": {"length_mode": "fixed", "rounds_per_match": 10},
                "structure": {
                    "kind": "lattice",
                    "rows": 20,
                    "cols": 20,
                    "neighbourhood_shape": "moore",
                    "initial_layout": "central_block",
                },
                "dynamics": {
                    "generations": 300,
                    "reproduction_mode": "energy_economy",
                    "reproduction_threshold": 200.0,
                    "offspring_stake": 150.0,
                    "basic_living_cost": 40.0,
                    "mutation_rate": 0.0,
                },
            }
        ),
        things_to_try=(
            "Switch the punishment payoff P to 0 and re-derive before "
            "running: the saturated defector interior now earns "
            "16 × 10 × 0 = 0 against L = 40 and starves — the flagship's "
            "mechanism switched on inside the filling world — and the "
            "endgame changes character, from grind to "
            "collapse-and-recolonise. Recompute the window whenever you "
            "touch a payoff: this one change moves the all-defector "
            "bound from 160 to 0."
        ),
    )
)
