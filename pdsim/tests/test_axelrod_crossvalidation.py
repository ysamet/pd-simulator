"""Cross-validation of the v1 roster against the ``axelrod`` library.

``docs/DESIGN.md`` §7 names the open-source `axelrod` library — the reference
implementation of hundreds of PD strategies — as the correctness oracle for
our seven v1 strategies: we drive full matches through *both* engines and
require identical move transcripts, round by round (DECISIONS #27).

Scope notes:

* axelrod is a **dev-only** dependency (it drags in matplotlib/pandas/dask);
  nothing outside this test module imports it, so the headless-engine rule
  is untouched. If it is not installed, this whole module skips and the rest
  of the suite is unaffected.
* Comparisons are noise-free and fixed-length: transcript equality is only
  meaningful for deterministic play, so the stochastic strategies are
  cross-validated at their deterministic extremes (p, g ∈ {0, 1}), where
  each is exactly an alias of a deterministic strategy. Interior-probability
  behavior is covered by the seeded checks in ``test_strategies.py`` — the
  two libraries' random streams differ by design.
* Both engines use the same default payoffs: axelrod's default game is
  (R, P, S, T) = (3, 1, 0, 5), identical to our registry defaults.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from pdsim.config.experiment import GameConfig, MatchConfig
from pdsim.core.agent import Agent
from pdsim.core.game import PrisonersDilemma
from pdsim.core.match import Match, MatchResult
from pdsim.core.strategies import create_strategy
from pdsim.core.strategy import Strategy
from pdsim.tests.stub_strategies import StubCycler

# pytest.importorskip: if the oracle is missing (or broken on this Python),
# skip the module instead of erroring — the main suite must stand alone.
axl = pytest.importorskip("axelrod")

TURNS = 30
"""Rounds per cross-validated match — long enough to expose retaliation
cycles, lock-ins, and recovery patterns."""

# Our machine name → the axelrod player class implementing the same strategy.
DETERMINISTIC = {
    "always_cooperate": axl.Cooperator,
    "always_defect": axl.Defector,
    "tit_for_tat": axl.TitForTat,
    "grim_trigger": axl.Grudger,
    "pavlov": axl.WinStayLoseShift,
}

# Every unordered pairing of the five deterministic strategies, self-play
# included: 15 matches, each compared transcript-for-transcript.
PAIRINGS = list(itertools.combinations_with_replacement(sorted(DETERMINISTIC), 2))

# Stochastic strategies at their deterministic extremes: each is an exact
# alias of a deterministic player, so transcripts must again be identical.
EXTREME_ALIASES = {
    "random_p0": (("random", {"cooperation_probability": 0.0}), axl.Defector),
    "random_p1": (("random", {"cooperation_probability": 1.0}), axl.Cooperator),
    "gtft_g0": (("generous_tit_for_tat", {"generosity": 0.0}), axl.TitForTat),
    "gtft_g1": (("generous_tit_for_tat", {"generosity": 1.0}), axl.Cooperator),
}


def _our_match(strategy_a: Strategy, strategy_b: Strategy) -> MatchResult:
    """Play one fixed-length noise-free match in *our* engine.

    Args:
        strategy_a: Strategy for agent 0.
        strategy_b: Strategy for agent 1.

    Returns:
        The finished match transcript. The seed is irrelevant for the
        deterministic play compared here, but the engine contract still
        requires a seeded generator (hard rule 5).
    """
    agent_a = Agent(agent_id=0, strategy=strategy_a)
    agent_b = Agent(agent_id=1, strategy=strategy_b)
    match = Match(
        PrisonersDilemma(GameConfig()),
        MatchConfig(rounds_per_match=TURNS),
        np.random.default_rng(0),
    )
    return match.play(agent_a, agent_b)


def _our_transcript(strategy_a: Strategy, strategy_b: Strategy) -> tuple[str, str]:
    """Return both sides' moves from our engine as ``"CCD..."`` strings.

    Args:
        strategy_a: Strategy for agent 0.
        strategy_b: Strategy for agent 1.

    Returns:
        Move strings ``(side_a, side_b)``, one character per round.
    """
    result = _our_match(strategy_a, strategy_b)
    side_a = "".join(record.actions[0].value for record in result.rounds)
    side_b = "".join(record.actions[1].value for record in result.rounds)
    return side_a, side_b


def _axelrod_transcript(player_a: object, player_b: object) -> tuple[str, str]:
    """Return both sides' moves from the axelrod engine as strings.

    Args:
        player_a: An axelrod player instance.
        player_b: An axelrod player instance.

    Returns:
        Move strings ``(side_a, side_b)``; ``str()`` of an axelrod action
        is ``"C"``/``"D"``, matching our ``Action`` values.
    """
    moves = axl.Match((player_a, player_b), turns=TURNS).play()
    side_a = "".join(str(move_a) for move_a, _ in moves)
    side_b = "".join(str(move_b) for _, move_b in moves)
    return side_a, side_b


class TestDeterministicTranscripts:
    """The five deterministic strategies, engine vs engine."""

    @pytest.mark.parametrize(("name_a", "name_b"), PAIRINGS)
    def test_all_pairings_play_identical_matches(self, name_a: str, name_b: str) -> None:
        """Every pairing (self-play included) must transcript-match."""
        ours = _our_transcript(create_strategy(name_a), create_strategy(name_b))
        theirs = _axelrod_transcript(DETERMINISTIC[name_a](), DETERMINISTIC[name_b]())
        assert ours == theirs

    def test_payoff_totals_agree_with_the_oracle(self) -> None:
        """Bonus engine check: total scores match axelrod's final_score."""
        result = _our_match(create_strategy("tit_for_tat"), create_strategy("always_defect"))
        oracle = axl.Match((axl.TitForTat(), axl.Defector()), turns=TURNS)
        oracle.play()
        score_a, score_b = oracle.final_score()
        assert result.total_payoffs == {0: float(score_a), 1: float(score_b)}


class TestProbeSequences:
    """Scripted opponents expose reactions self-play never produces.

    A cycler forces asymmetric histories — e.g. Pavlov against alternation,
    GrimTrigger's exact trigger round — that mutual play between nice
    strategies would never reach.
    """

    @pytest.mark.parametrize("cycle", ["CCD", "CD"])
    @pytest.mark.parametrize("name", sorted(DETERMINISTIC))
    def test_responses_to_scripted_opponents_match(self, name: str, cycle: str) -> None:
        """Each strategy's answer to a scripted pattern must match."""
        ours = _our_transcript(create_strategy(name), StubCycler(cycle))
        theirs = _axelrod_transcript(DETERMINISTIC[name](), axl.Cycler(cycle))
        assert ours == theirs


class TestStochasticExtremes:
    """Random(p) and GTFT(g) at p, g ∈ {0, 1} are deterministic aliases."""

    @pytest.mark.parametrize("opponent", sorted(DETERMINISTIC))
    @pytest.mark.parametrize("alias", sorted(EXTREME_ALIASES))
    def test_extremes_behave_as_their_aliases(self, alias: str, opponent: str) -> None:
        """Each extreme, against each deterministic opponent, matches."""
        (our_name, params), axl_alias = EXTREME_ALIASES[alias]
        ours = _our_transcript(create_strategy(our_name, **params), create_strategy(opponent))
        theirs = _axelrod_transcript(axl_alias(), DETERMINISTIC[opponent]())
        assert ours == theirs


class TestParameterDefaults:
    """Our registry defaults line up with the oracle's."""

    def test_gtft_default_generosity_matches_the_oracle(self) -> None:
        """Our g = 1/3 equals axelrod GTFT's payoff-derived default.

        axelrod computes min(1 - (T-R)/(R-S), (R-P)/(T-P)) after seeing the
        game; at standard payoffs that is 1/3 (up to floating-point
        rounding — hence ``approx``).
        """
        oracle = axl.GTFT()
        axl.Match((oracle, axl.Cooperator()), turns=2).play()  # lets it derive p
        ours = create_strategy("generous_tit_for_tat")
        assert ours.generosity == pytest.approx(oracle.p)
