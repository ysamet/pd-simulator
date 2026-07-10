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
   ✅ M7 landed 2026-07-06, 347 tests passing.
8. **Polish.** `docs/PARAMETERS.md` generation; README quick start; RandomK matcher
   if not already landed.
   ✅ M8 landed 2026-07-07, 382 tests passing — **v1 complete**: PARAMETERS.md
   is a committed generated artifact with a drift test (`python -m
   pdsim.gendocs`, DECISIONS #56); RandomK shipped (DECISIONS #57).

Out of scope for v1 (but nothing may block them): everything below.

## v2 — Economy-first: growth, sweeps, tags, group games

Milestone spine (DECISIONS #58): **M9 → M9.5 → M10 → M12 → M11 → M13 → M14**.
M12 deliberately runs *before* M11: the owner's research program targets
tag-based/ethnocentrism dynamics, and tags come after M10 so they are built
variable-N-aware from birth.

- **M9 — Selection rules, score accounting, cooperation recording.**
  Fitness-proportional, tournament(k), truncation/elitist, and
  threshold-cloning selection rules; sliding-window and exponentially
  discounted score accounting — all plug-ins to the existing ABCs. Plus
  pairwise cooperation-rate recording at strategy-pair resolution
  (schema_version bump; DECISIONS #60) and a benchmark rider capturing
  wall-clock per generation across N × matcher, so the vectorization
  trigger becomes data.
  ✅ M9a (part 1 of 2) landed 2026-07-08: the four selection rules
  (DECISIONS #63), the ScoreAccounting seam with sliding-window and
  exponential-discount options (DECISIONS #64), and the benchmark rider
  (`python -m pdsim.bench`) — spec:
  `docs/specs/M09a-selection-accounting-bench.md`; 440 tests passing.
  ✅ M9b landed 2026-07-09 — **M9 complete**: pairwise cooperation-rate
  recording at strategy-pair resolution, cooperation chart + pair-matrix
  table, `cooperation.parquet`, schema_version 2 with loaders accepting
  both schemas (DECISIONS #65; spec
  `docs/specs/M09b-cooperation-recording.md`); 457 tests passing.
- **M9.5 — Sweep/search layer** (DECISIONS #59). SweepSpec YAML config
  families (base config + parameter/composition/seed axes), a parallel
  batch runner (`python -m pdsim.sweep`, multiprocessing across runs), the
  **Outcome Metrics Registry** (fourth registry-idiom instance: final
  share, fixation with censoring semantics, quasi-fixation variants,
  cooperation-collapse metrics — pure post-processing over recorded runs),
  and `sweeps/<name>/` persistence with a per-run summary parquet and a
  metric-vs-axis chart. First research program: invasion thresholds.
- **M10 — Score-as-energy growth economy.** Reproduction cost T, offspring
  stake, per-round living cost, death at score ≤ 0, carrying capacity K;
  asynchronous (Moran-style) event mode. Possible split: synchronous
  growth first, async/Moran second. Chat-designed first: offspring score
  policy, death semantics, birth/death RNG order (seeded-history contract
  extending #32), selection under energy-driven reproduction, matchers
  under variable N, event/schema changes (DECISIONS #58).
- **M12 (before M11) — Agent attributes + attribute-conditional
  strategies.** Generic attributes mapping with visibility and inheritance
  policies; strategies conditioning on an opponent's visible tags (Riolo
  tags; Hammond & Axelrod ethnocentrism — richer with the v3 spatial
  layer). See DESIGN §6.5, DECISIONS #46/#58.
- **M11 — Parameter-perturbation mutation** (Gaussian noise on continuous
  strategy parameters → genuine strategy evolution), plus the
  variant-identity machinery it requires (resolves the #30 deferral).
- **M13 — Public Goods Game + variants:** threshold/step-level, volunteer's
  dilemma, n-player snowdrift; group-size parameter; group matching.
- **M14 — Reciprocity machinery for group games:** public reputation,
  targeted peer punishment (costly fines), exclusion — designed against
  M12's visible-attributes surface (reputation is nearly a dynamic public
  attribute).

**Unscheduled, empirically triggered:** the **vectorized NumPy engine
backend** for populations in the thousands — paired with sampling matchers
(RandomK shipped in v1/M8, SpatialKernel in v3) to reach thousands of agents
at interactive speed (see DESIGN §3.1). It is deliberately NOT on the spine:
it lands when actual experiments/sweeps show the sampling matchers cannot
buy the needed scale (M9's benchmark rider supplies the data; DECISIONS #58).

## v3+ — Geography and real-world scenario modeling

- Spatial layer: `Agent.position`, SpatialKernel matcher (distance-weighted
  interaction), configurable initial dispersion.
- Agent movement over time: `MovementRule` ABC (random walk, drift toward
  similar neighbors, post-interaction relocation) on a configurable schedule,
  feeding SpatialKernel matching; movement is population dynamics, not a
  strategy decision (DESIGN §6.3, DECISIONS #46).
- Real geographies: countries/states/municipalities (GeoJSON), map visualizations
  of population composition and spread.
- Scenario modeling toolkit for societal/geopolitical conflicts (asymmetric payoffs,
  alliances/sanctions as mechanics, heterogeneous endowments).
- Richer dashboard (Dash or FastAPI+React) replacing Streamlit if needed.
- Sweep operation story. The sweep *capability* itself is v2/M9.5
  (DECISIONS #59); what remains for v3+ is only how it is operated at
  scale: scheduled, Cowork-driven experiment campaigns, plus the deferred
  search increments (adaptive threshold bisection, sweep browsing in the UI).
