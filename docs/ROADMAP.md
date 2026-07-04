# ROADMAP.md

## v1 — Pairwise evolutionary PD with live web UI

Milestone order (each lands with tests + docs):

1. **Skeleton + registry.** Repo scaffold, `pyproject.toml`, ruff, pytest;
   Parameter Registry; `ExperimentConfig` (pydantic) + YAML load/save.
   ✅ M1 landed 2026-07-03, 38 tests passing.
2. **Core game loop.** `Game` ABC + PrisonersDilemma (payoff validation toggles);
   `Strategy` ABC + history views; Agent; Match (fixed rounds + continuation-prob w;
   execution noise ε); RoundRobin matcher.
   ✅ M2 landed 2026-07-03, 70 tests passing.
3. **Strategy roster.** The seven v1 strategies with decision-table tests and
   `axelrod` cross-validation.
   ✅ M3 landed 2026-07-04, 200 tests passing.
4. **Evolutionary dynamics.** Synchronous generations; Fermi selection (β);
   strategy-switch mutation (μ); seeded RNG discipline; golden validation tests.
   ✅ M4 landed 2026-07-04, 237 tests passing.
5. **GUI foundations** (rescoped — see DECISIONS #33). Run modes
   (evolution/tournament); typed event stream with observer-side granularity;
   Scenario Registry with five curated presets.
   ✅ M5 landed 2026-07-04, 270 tests passing.
6. **Streamlit UI.** Scenario dropdown (registry-driven); registry-generated
   parameter panel with novice tooltips; mode-aware charts (stacked-area
   composition + score trajectories in evolution; cumulative standings in
   tournament) with ignored-parameter greying; live updates with granularity
   (round/match/generation) + playback speed; run launcher. No results browser
   yet.
   ✅ M6 landed 2026-07-04, 303 tests passing.
7. **Persistence + CLI.** Run folders (config + seed + parquet + summary);
   runs index; headless CLI (`python -m pdsim.run`); results browser in the UI.
8. **Polish.** `docs/PARAMETERS.md` generation; README quick start; RandomK matcher
   if not already landed.

Out of scope for v1 (but nothing may block them): everything below.

## v2 — Growth, group games, reciprocity machinery

- **Score-as-energy population growth:** reproduction cost T, offspring stake,
  per-round living cost, death at score ≤ 0, carrying capacity K; asynchronous
  (Moran-style) event mode.
- **Additional selection rules:** fitness-proportional, tournament(k),
  truncation/elitist, threshold cloning.
- **Score accounting options:** cumulative, sliding window, exponential discounting.
- **Parameter-perturbation mutation** (Gaussian noise on continuous strategy
  parameters → genuine strategy evolution).
- **Public Goods Game + variants:** threshold/step-level, volunteer's dilemma,
  n-player snowdrift; group-size parameter.
- **Reciprocity machinery for group games:** public reputation, targeted peer
  punishment (costly fines), exclusion.
- **Vectorized NumPy engine backend** for populations in the thousands.

## v3+ — Geography and real-world scenario modeling

- Spatial layer: `Agent.position`, SpatialKernel matcher (distance-weighted
  interaction), configurable initial dispersion.
- Real geographies: countries/states/municipalities (GeoJSON), map visualizations
  of population composition and spread.
- Scenario modeling toolkit for societal/geopolitical conflicts (asymmetric payoffs,
  alliances/sanctions as mechanics, heterogeneous endowments).
- Richer dashboard (Dash or FastAPI+React) replacing Streamlit if needed.
- Batch experiment sweeps operated via Claude Cowork (YAML-driven).
