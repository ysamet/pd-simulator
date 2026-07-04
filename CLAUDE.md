# CLAUDE.md — Project conventions and context

This repository is an evolutionary Prisoner's Dilemma simulation platform. Read
`docs/DESIGN.md` (model + architecture spec), `docs/ROADMAP.md` (version scoping), and
`docs/DECISIONS.md` (decision log with rationale) before making non-trivial changes.

## About the developer

The project owner is re-entering programming via Python. Prefer clear, idiomatic,
well-explained code over clever code. When introducing a new concept (decorator,
generator, ABC, vectorization trick), add a brief explanatory comment the first time
it appears. Where a design maps to functional-programming ideas (strategies as
composable functions), point it out — it's a learning thread of this project.

## Hard rules

1. **Documentation is mandatory, always.** Every module, class, function, and method
   gets a Google-style docstring. Every function parameter and return value is
   documented. Every tunable simulation parameter is documented in the Parameter
   Registry with a plain-language, novice-friendly explanation (the user of this
   platform is NOT assumed to know game theory).
2. **Type hints everywhere.** Full annotations on all public signatures.
3. **Parameter Registry is the single source of truth** (`config/registry.py`).
   Never add a tunable parameter anywhere else. UI tooltips, docs, and validation are
   generated from it. A parameter without a registry entry is a bug.
4. **Headless engine.** Nothing under `pdsim/core/`, `pdsim/config/`, or `pdsim/io/`
   may import UI or plotting code. The engine communicates via the typed event stream.
5. **Seeded randomness only.** All randomness flows from the single injected
   numpy `Generator`. Never call unseeded `random`/`np.random` module functions.
6. **Interfaces before implementations.** New mechanisms (selection rules, matchers,
   games, mutation kinds, score accounting) are added as implementations of the
   existing ABCs. If an ABC doesn't fit, update `docs/DESIGN.md` first, log the decision
   in `docs/DECISIONS.md`, then change code.
7. **Tests accompany features.** pytest; every strategy has decision-table tests;
   engine changes must keep the golden validation tests (`docs/DESIGN.md` §7) green.
8. **Reproducibility.** Every run saves complete config + seed. Never break the
   ability to re-run an old `config.yaml`.

## Style

- Python ≥ 3.11. `ruff` for lint+format (config in `pyproject.toml`). Google-style
  docstrings. Dataclasses/pydantic models for configs — no bare dicts across
  module boundaries.
- Names: strategies in `pdsim/core/strategies/`, one module each, registered via the
  strategy registry so the UI discovers them automatically.

## Commands

- Run tests: `pytest`
- Lint/format: `ruff check . && ruff format .`
- Launch UI: `streamlit run pdsim/ui/app.py`
- Headless run: `python -m pdsim.run path/to/config.yaml`

(Keep this section updated as tooling lands.)

## Cross-conversation synchronization protocol

Design discussion happens in the Claude.ai project chat; implementation happens here
in Claude Code. The sync contract, in both directions:

- Any design change agreed in chat → user brings updated `docs/DESIGN.md` /
  `docs/DECISIONS.md` text into the repo (or pastes conclusions to Claude Code, which
  updates the files).
- Any design-relevant discovery made during implementation (an interface that doesn't
  fit, a performance wall, a modeling ambiguity) → update `docs/DESIGN.md` and append to
  `docs/DECISIONS.md` in the same session, so the chat side can pick it up.
- `docs/DECISIONS.md` entries are append-only: number, date, decision, rationale,
  alternatives considered. Reversals get a new entry referencing the old one.
- End every significant Claude Code session by checking whether `docs/DESIGN.md`,
  `docs/ROADMAP.md`, or `docs/DECISIONS.md` need updates. Stale docs are bugs.

## Current phase

v1 per `docs/ROADMAP.md`: pairwise repeated PD, object-per-agent engine, Fermi selection,
strategy-switch mutation, Streamlit UI with live charts and registry-driven tooltips.
Design everything to not block the v2/v3 extensions listed in `docs/DESIGN.md` §6.
