"""Headless simulation engine: game, strategies, matching, dynamics, event stream.

Hard rule 4 (``CLAUDE.md``): nothing in this package may import UI or plotting
code. The engine communicates with the outside world only through the typed
event stream (``docs/DESIGN.md`` §4).

Modules land here in milestone 2+ (``docs/ROADMAP.md``).
"""
