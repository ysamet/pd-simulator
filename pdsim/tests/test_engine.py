"""Tests for the engine's typed event stream (``pdsim/core/engine.py``).

Covers: event counts and ordering at each granularity, the
granularity-changes-nothing guarantee (identical simulation results for the
same seed — DECISIONS #35), mode-appropriate period events, the
tournament-mode ignores-dynamics-parameters guarantee (#34), and payload
sanity for the fine-grained events.
"""

from __future__ import annotations

import pytest

from pdsim.config.experiment import ExperimentConfig
from pdsim.core import engine
from pdsim.core.events import (
    CycleFinished,
    GenerationFinished,
    MatchFinished,
    RoundPlayed,
    RunFinished,
)

N_AGENTS = 4
N_PAIRS = 6  # C(4, 2) round-robin pairings
ROUNDS = 3
GENERATIONS = 2


def _evolution_config(**dynamics_overrides: float) -> ExperimentConfig:
    """Build a small evolution-mode config for event tests.

    Args:
        **dynamics_overrides: Extra dynamics fields (e.g. a beta override).

    Returns:
        A validated config: 4 agents, 3-round matches, 2 generations.
    """
    return ExperimentConfig.model_validate(
        {
            "population": {
                "size": N_AGENTS,
                "composition": {"tit_for_tat": 2, "always_defect": 2},
            },
            "match": {"length_mode": "fixed", "rounds_per_match": ROUNDS},
            "dynamics": {"generations": GENERATIONS, **dynamics_overrides},
        }
    )


def _tournament_config(**dynamics_overrides: float) -> ExperimentConfig:
    """Build a small tournament-mode config for event tests.

    Args:
        **dynamics_overrides: Dynamics fields that tournament mode must
            ignore (DECISIONS #34).

    Returns:
        A validated config: 4 agents, 3-round matches, 2 cycles.
    """
    return ExperimentConfig.model_validate(
        {
            "mode": "tournament",
            "tournament_cycles": 2,
            "population": {
                "size": N_AGENTS,
                "composition": {"tit_for_tat": 2, "always_defect": 2},
            },
            "match": {"length_mode": "fixed", "rounds_per_match": ROUNDS},
            "dynamics": dict(dynamics_overrides),
        }
    )


def _counts(events: list[object]) -> dict[str, int]:
    """Count events by type name.

    Args:
        events: A collected event stream.

    Returns:
        Mapping of event class name to occurrence count.
    """
    counts: dict[str, int] = {}
    for event in events:
        name = type(event).__name__
        counts[name] = counts.get(name, 0) + 1
    return counts


class TestGranularityCounts:
    """Each granularity emits its level and everything coarser."""

    def test_generation_granularity_emits_period_events_only(self) -> None:
        """Default granularity: one GenerationFinished per generation + RunFinished."""
        events = list(engine.run(_evolution_config()))
        assert _counts(events) == {"GenerationFinished": GENERATIONS, "RunFinished": 1}
        assert [e.index for e in events if isinstance(e, GenerationFinished)] == [0, 1]

    def test_period_events_carry_exact_rounds_played(self) -> None:
        """DECISIONS #44: each strategy's agent-rounds for the period.

        Fixed mode, 4 agents: every agent plays 3 opponents x 3 rounds = 9
        rounds, so each 2-agent strategy logs 18 agent-rounds.
        """
        events = list(engine.run(_evolution_config()))
        first = next(e for e in events if isinstance(e, GenerationFinished))
        assert first.rounds_played == {"tit_for_tat": 18, "always_defect": 18}

    def test_match_granularity_adds_match_events(self) -> None:
        """One MatchFinished per pairing per generation, plus the coarser events."""
        events = list(engine.run(_evolution_config(), granularity="match"))
        assert _counts(events) == {
            "MatchFinished": N_PAIRS * GENERATIONS,
            "GenerationFinished": GENERATIONS,
            "RunFinished": 1,
        }

    def test_round_granularity_adds_round_events(self) -> None:
        """One RoundPlayed per round of every match, plus everything coarser."""
        events = list(engine.run(_evolution_config(), granularity="round"))
        assert _counts(events) == {
            "RoundPlayed": ROUNDS * N_PAIRS * GENERATIONS,
            "MatchFinished": N_PAIRS * GENERATIONS,
            "GenerationFinished": GENERATIONS,
            "RunFinished": 1,
        }

    def test_unknown_granularity_rejected(self) -> None:
        """A typo'd granularity fails loudly before the run starts."""
        with pytest.raises(ValueError, match="granularity"):
            list(engine.run(_evolution_config(), granularity="epoch"))  # type: ignore[arg-type]


class TestOrdering:
    """Events arrive in play order, closed by exactly one RunFinished."""

    def test_run_finished_is_always_last_and_unique(self) -> None:
        """Every stream ends with its single RunFinished."""
        for granularity in ("round", "match", "generation"):
            events = list(engine.run(_evolution_config(), granularity=granularity))
            assert isinstance(events[-1], RunFinished)
            assert sum(isinstance(e, RunFinished) for e in events) == 1

    def test_rounds_precede_their_match_which_precede_the_generation(self) -> None:
        """Within a match: its rounds, then MatchFinished; then the period event."""
        events = list(engine.run(_evolution_config(), granularity="round"))
        round_index = 0
        for event in events:
            if isinstance(event, RoundPlayed):
                assert event.round_index == round_index
                round_index += 1
            elif isinstance(event, MatchFinished):
                assert round_index == ROUNDS  # all of this match's rounds arrived
                round_index = 0

    def test_round_payloads_are_coherent(self) -> None:
        """RoundPlayed carries both participants' actions and payoffs."""
        events = list(engine.run(_evolution_config(), granularity="round"))
        first = next(e for e in events if isinstance(e, RoundPlayed))
        assert set(first.actions) == set(first.agent_ids)
        assert set(first.payoffs) == set(first.agent_ids)


class TestGranularityChangesNothing:
    """DECISIONS #35: granularity is an observer concern, never a model one."""

    def test_identical_results_at_every_granularity(self) -> None:
        """Same seed → identical period events and final summary at all levels."""
        streams = {
            granularity: list(engine.run(_evolution_config(mutation_rate=0.2), granularity))
            for granularity in ("round", "match", "generation")
        }
        finals = {g: events[-1] for g, events in streams.items()}
        assert finals["round"] == finals["match"] == finals["generation"]
        periods = {
            g: [e for e in events if isinstance(e, GenerationFinished)]
            for g, events in streams.items()
        }
        assert periods["round"] == periods["match"] == periods["generation"]


class TestRandomKStreams:
    """random_k emits well-formed streams in both modes (DECISIONS #57)."""

    K = 2

    def _with_random_k(self, config: ExperimentConfig) -> ExperimentConfig:
        """Return a copy of a config that matches via random_k.

        Args:
            config: Any validated experiment config.

        Returns:
            The same experiment with the matching section swapped.
        """
        data = config.model_dump()
        data["matching"] = {"matcher": "random_k", "opponents_per_agent": self.K}
        return ExperimentConfig.model_validate(data)

    def test_evolution_stream_is_well_formed(self) -> None:
        """N·k matches per generation; period events and the closer intact."""
        events = list(engine.run(self._with_random_k(_evolution_config()), granularity="match"))
        assert _counts(events) == {
            "MatchFinished": N_AGENTS * self.K * GENERATIONS,
            "GenerationFinished": GENERATIONS,
            "RunFinished": 1,
        }
        assert isinstance(events[-1], RunFinished)

    def test_tournament_stream_is_well_formed(self) -> None:
        """One random_k pass per cycle: N·k matches each, cumulative reports."""
        events = list(engine.run(self._with_random_k(_tournament_config()), granularity="match"))
        assert _counts(events) == {
            "MatchFinished": N_AGENTS * self.K * 2,
            "CycleFinished": 2,
            "RunFinished": 1,
        }
        assert isinstance(events[-1], RunFinished)


class TestModes:
    """Each mode emits its own period event, never the other's."""

    def test_evolution_never_emits_cycle_events(self) -> None:
        """Evolution runs report generations, not cycles."""
        events = list(engine.run(_evolution_config(), granularity="round"))
        assert not any(isinstance(e, CycleFinished) for e in events)
        assert events[-1].mode == "evolution"
        assert events[-1].total_scores is None

    def test_tournament_never_emits_generation_events(self) -> None:
        """Tournament runs report cycles, not generations."""
        events = list(engine.run(_tournament_config(), granularity="round"))
        assert not any(isinstance(e, GenerationFinished) for e in events)
        assert sum(isinstance(e, CycleFinished) for e in events) == 2
        assert events[-1].mode == "tournament"
        assert events[-1].total_scores is not None

    def test_tournament_ignores_dynamics_parameters(self) -> None:
        """DECISIONS #34: selection/mutation settings have zero effect.

        Two tournament runs that differ only in beta and mu must produce
        byte-identical event streams — those parameters are valid in the
        config but never consulted (and consume no RNG draws).
        """
        stream_a = list(engine.run(_tournament_config(), granularity="round"))
        stream_b = list(
            engine.run(
                _tournament_config(selection_beta=99.0, mutation_rate=0.9),
                granularity="round",
            )
        )
        assert stream_a == stream_b
