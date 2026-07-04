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
