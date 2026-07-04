"""Demo: a round-robin tournament with today's engine (Milestone 2).

What this IS: four agents, each holding a strategy, play one repeated
Prisoner's Dilemma match against every other agent (round-robin), with
match length drawn from a continuation probability and a little execution
noise. Final scores show who did well in this social environment.

What this is NOT yet: an *evolutionary* simulation. Nothing reproduces,
mutates, or dies — that arrives with Milestone 4, and the polished
strategy roster (real TitForTat, Pavlov, ...) with Milestone 3. Until
then this demo borrows the stub strategies from the test suite.

Run it from the repo root with the virtualenv active:

    python examples/tournament_demo.py

Things to try (edit the constants below and re-run):
    * SEED — same seed, same tournament; new seed, new history.
    * NOISE_EPSILON — raise to 0.1 and watch grim_window's score drop:
      one trembling hand and it never forgives (that's the point of ε).
    * CONTINUATION_PROBABILITY — closer to 1.0 means longer matches,
      which favors the reciprocators over always_defect.
"""

from __future__ import annotations

import numpy as np

from pdsim.config.experiment import GameConfig, MatchConfig, MatchingConfig
from pdsim.core import Agent, Match, PrisonersDilemma, build_matcher
from pdsim.tests.stub_strategies import (
    StubAlwaysCooperate,
    StubAlwaysDefect,
    StubGrimWindow,
    StubMirror,
)

SEED = 42
NOISE_EPSILON = 0.02
CONTINUATION_PROBABILITY = 0.95  # expected match length: 1/(1-w) = 20 rounds


def main() -> None:
    """Play one round-robin tournament and print the standings."""
    rng = np.random.default_rng(SEED)

    roster = {
        "mirror (tit-for-tat-like)": StubMirror(),
        "always_cooperate": StubAlwaysCooperate(),
        "always_defect": StubAlwaysDefect(),
        "grim_window": StubGrimWindow(),
    }
    agents = [Agent(agent_id=i, strategy=strategy) for i, strategy in enumerate(roster.values())]
    names = dict(enumerate(roster.keys()))

    match = Match(
        game=PrisonersDilemma(GameConfig()),
        config=MatchConfig(
            length_mode="continuation",
            continuation_probability=CONTINUATION_PROBABILITY,
            noise_epsilon=NOISE_EPSILON,
        ),
        rng=rng,
    )

    print(
        f"Round-robin tournament, seed={SEED}, eps={NOISE_EPSILON}, w={CONTINUATION_PROBABILITY}\n"
    )
    matcher = build_matcher(MatchingConfig())
    for agent_a, agent_b in matcher.pairings(agents, rng):
        result = match.play(agent_a, agent_b)
        print(
            f"  {names[agent_a.agent_id]:>25} vs {names[agent_b.agent_id]:<25}"
            f" {result.n_rounds:3d} rounds ->"
            f" {result.total_payoffs[agent_a.agent_id]:6.1f} : "
            f"{result.total_payoffs[agent_b.agent_id]:6.1f}"
        )

    print("\nFinal standings:")
    for agent in sorted(agents, key=lambda a: a.score, reverse=True):
        print(f"  {names[agent.agent_id]:>25}: {agent.score:7.1f}")


if __name__ == "__main__":
    main()
