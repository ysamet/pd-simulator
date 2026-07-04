"""Headless simulation engine: game, strategies, agents, matching, matches.

Hard rule 4 (``CLAUDE.md``): nothing in this package may import UI or plotting
code. The engine communicates with the outside world only through the typed
event stream (``docs/DESIGN.md`` §4, arriving in milestone 5).

Landed in milestone 2: the core game loop (this module's re-exports).
Still to come: the strategy roster (M3), evolutionary dynamics (M4), the
engine/event stream (M5).

The most-used names are re-exported so callers can write
``from pdsim.core import Agent, Match, PrisonersDilemma``.
"""

from pdsim.core.agent import Agent
from pdsim.core.game import Action, AgentId, Game, Payoff, PrisonersDilemma
from pdsim.core.match import Match, MatchResult, RoundRecord
from pdsim.core.matcher import Matcher, RoundRobin, build_matcher
from pdsim.core.strategy import HistoryView, Strategy

__all__ = [
    "Action",
    "Agent",
    "AgentId",
    "Game",
    "HistoryView",
    "Match",
    "MatchResult",
    "Matcher",
    "Payoff",
    "PrisonersDilemma",
    "RoundRecord",
    "RoundRobin",
    "Strategy",
    "build_matcher",
]
