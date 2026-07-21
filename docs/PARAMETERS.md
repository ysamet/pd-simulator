# Parameter Reference

> **GENERATED FILE — do not hand-edit.** Regenerate with
> `python -m pdsim.gendocs`. A pytest drift test compares this file to a
> fresh regeneration, so hand edits (or a stale copy) fail the suite.

Everything below is generated from the platform's registries — the Parameter
Registry (`pdsim/config/registry.py`), the Strategy Registry
(`pdsim/core/strategies/registry.py`), and the Scenario Registry
(`pdsim/config/scenarios.py`). Those registries are the single source of
truth: the same text appears as tooltips in the app, and a parameter cannot
exist without an entry here.

## Simulation parameters

Grouped by section, in the order the app's parameter panel shows them.
Strategy-specific parameters appear with their strategies further down.

### Game

#### `game.payoff_temptation` — Temptation payoff (T)

- **Type:** number
- **Allowed values:** -100 to 100
- **Default:** `5.0`

Points a player earns by defecting while the other player cooperates. This is the 'temptation to cheat' — in a true Prisoner's Dilemma it is the biggest payoff in the game.

#### `game.payoff_reward` — Reward payoff (R)

- **Type:** number
- **Allowed values:** -100 to 100
- **Default:** `3.0`

Points each player earns when both cooperate — the 'reward for working together'. Whether cooperation can survive depends on how R compares to the temptation to cheat.

#### `game.payoff_punishment` — Punishment payoff (P)

- **Type:** number
- **Allowed values:** -100 to 100
- **Default:** `1.0`

Points each player earns when both defect. Mutual betrayal leaves both sides worse off than mutual cooperation would have.

#### `game.payoff_sucker` — Sucker payoff (S)

- **Type:** number
- **Allowed values:** -100 to 100
- **Default:** `0.0`

Points a player earns by cooperating while the other player defects. Being the 'sucker' is the worst outcome in a true Prisoner's Dilemma.

#### `game.enforce_pd_ordering` — Enforce PD payoff ordering (T > R > P > S)

- **Type:** true/false
- **Allowed values:** true or false
- **Default:** `true`

Keep the payoffs in the classic Prisoner's Dilemma order: temptation > reward > punishment > sucker. Turn this off to explore neighboring games such as Chicken or Stag Hunt, where the order differs.

#### `game.enforce_alternation_constraint` — Enforce no-alternation rule (2R > T + S)

- **Type:** true/false
- **Allowed values:** true or false
- **Default:** `true`

Require that steady mutual cooperation pays more than two players taking turns exploiting each other. Without this rule (2 x reward > temptation + sucker), alternating betrayal becomes the best team tactic, which changes the character of the game.

### Matching

#### `matching.matcher` — Matching scheme

- **Type:** choice
- **Allowed values:** one of: `round_robin`, `random_k`
- **Default:** `round_robin`

How opponents are paired up each generation (or tournament cycle). 'round_robin' means every agent plays every other agent exactly once — thorough, but the match count grows with the SQUARE of the population. 'random_k' means each agent starts matches against a few randomly drawn opponents instead, so big populations stay fast. Distance-based matching arrives with the geographic layer in a later version.

*Learn more:* Round-robin plays about N²/2 matches per period; random_k plays exactly N x k. Sampling who meets whom is the first lever for scaling to thousands of agents (see docs/DESIGN.md §3.1).

#### `matching.opponents_per_agent` — Opponents per agent (k)

- **Type:** whole number
- **Allowed values:** 1 to 9999
- **Default:** `5`

How many randomly drawn opponents each agent starts matches against per generation (or tournament cycle) when the matching scheme is 'random_k'. Every agent initiates this many matches and can ALSO be drawn by others, so some agents play more rounds than others — part of the model, and the 'per round' score view divides that luck away. Must be smaller than the population size. Ignored under 'round_robin', where every pair plays anyway.

*Learn more:* Fewer matches per period is what makes large populations affordable: N x k matches instead of round-robin's ~N²/2.

### Match

#### `match.length_mode` — Match length mode

- **Type:** choice
- **Allowed values:** one of: `fixed`, `continuation`
- **Default:** `fixed`

How the length of each match is decided. 'fixed' plays an exact number of rounds. 'continuation' flips a weighted coin after every round to decide whether the match continues — so players can never be sure which round is the last.

*Learn more:* With a known final round, defecting at the end is 'safe', and that logic unravels backwards (backward induction). Probabilistic continuation models 'the shadow of the future' (Axelrod).

#### `match.rounds_per_match` — Rounds per match

- **Type:** whole number
- **Allowed values:** 1 to 10000
- **Default:** `50`

Number of rounds in every match when the match length mode is 'fixed'. Longer matches give reciprocal strategies (like Tit for Tat) more time to build cooperation.

#### `match.continuation_probability` — Continuation probability (w)

- **Type:** number
- **Allowed values:** 0 to below 1
- **Default:** `0.98`

Chance the match continues after each round when the match length mode is 'continuation'. Higher values mean longer matches on average — the expected length is 1 / (1 - w), so 0.98 gives about 50 rounds. Must be below 1, or matches would never end.

*Learn more:* w is the 'shadow of the future': how much tomorrow matters today.

#### `match.noise_epsilon` — Execution noise (ε)

- **Type:** number
- **Allowed values:** 0 to 1
- **Default:** `0.0`

Chance that an agent's action is accidentally flipped — it meant to cooperate but defected, or vice versa. Even a little noise punishes unforgiving strategies (Grim Trigger) and rewards forgiving ones (Generous Tit for Tat, Pavlov).

*Learn more:* Known in game theory as 'trembling hand' error.

### Population

#### `population.size` — Population size (N)

- **Type:** whole number
- **Allowed values:** 2 to 10000
- **Default:** `100`

Number of agents the run STARTS with. Under 'imitation' reproduction it stays constant across generations: selection always produces exactly this many agents. In the 'energy_economy' reproduction mode the population changes from generation to generation — this is only the founding count. Practical note: a few hundred agents is the comfortable limit for live visualization.

#### `population.memory_depth` — Memory depth

- **Type:** whole number
- **Allowed values:** at least 1; may be empty (= off/unlimited)
- **Default:** empty (no limit)

How many past rounds against each specific opponent a strategy may remember. Leave empty for unlimited memory. This is an experimental constraint — most classic strategies only look at the previous round anyway.

### Dynamics

#### `dynamics.generations` — Generations

- **Type:** whole number
- **Allowed values:** 1 to 100000
- **Default:** `200`

How many generations the simulation runs. In each generation everyone plays their matches, scores are tallied, and the next generation is formed by selection and mutation.

#### `dynamics.reproduction_mode` — Reproduction mode

- **Type:** choice
- **Allowed values:** one of: `imitation`, `energy_economy`
- **Default:** `imitation`

How the next generation comes to be. 'imitation' is the classic setting: the population size never changes — each slot in the next generation copies a parent's strategy, chosen by the selection rule below. 'energy_economy' replaces copying with living: agents hold a stock of energy, earn it by playing, pay it to stay alive, and reproduce when they can afford to — nobody copies anyone, the population grows and shrinks (and can even go extinct), and differential survival IS the selection. Switching to 'energy_economy' makes the selection rule and score accounting settings inert (they stay visible but are ignored).

*Learn more:* The two classic families of evolutionary dynamics: imitation (cultural copying, e.g. the Fermi rule) versus birth-death dynamics (organisms with metabolisms, e.g. Epstein & Axtell's Sugarscape).

#### `dynamics.time_model` — Time model

- **Type:** choice
- **Allowed values:** one of: `synchronous`, `asynchronous`
- **Default:** `synchronous`

The clock the simulation runs on. 'synchronous' is the classic generational clock: everyone plays their matches, then the whole population is updated at once at the generation boundary — exactly the behaviour of every earlier version. 'asynchronous' dissolves the generation: time advances one small event at a time — one agent is activated, plays its matches, and any births or deaths happen immediately, not at a boundary. The charts then count 'generation-equivalents': one activation per current member of the population, on average, adds up to one generation's worth of time, so the two clocks stay comparable. Under 'asynchronous' the reproduction mode, selection rule, and score accounting settings are ignored (an asynchronous run is always birth-death dynamics), and the matching scheme is ignored too — partners are drawn one activation at a time, using the opponents-per-agent count.

*Learn more:* Whether everyone updates at once or one at a time is a classic modelling choice that can change outcomes (Huberman & Glance 1993). The asynchronous clock here follows the Moran-process convention: N single-agent events make one generation.

#### `dynamics.selection_rule` — Selection rule

- **Type:** choice
- **Allowed values:** one of: `fermi`, `proportional`, `tournament_k`, `truncation`, `threshold_cloning`
- **Default:** `fermi`

How the next generation is chosen from the current one. 'fermi' (pairwise comparison) repeatedly picks two random agents and has the first copy the second's strategy with a probability that grows with the score difference and the selection intensity. 'proportional' (roulette wheel) draws each new agent's parent with a weight based on how far its score sits above the generation's worst. 'tournament_k' holds a mini-contest for every slot: a few randomly drawn candidates, the best scorer wins — despite the name, this has NOTHING to do with the tournament RUN MODE (which switches selection off entirely); it is simply this rule's traditional name. 'truncation' (elitist) only copies from the top slice of scorers. 'threshold_cloning' keeps every agent scoring above a threshold and replaces the rest with copies of those survivors.

*Learn more:* Fermi comes from statistical physics; roulette and tournament selection from genetic algorithms; truncation from selective breeding.

#### `dynamics.selection_beta` — Selection intensity (β)

- **Type:** number
- **Allowed values:** 0 to 1000
- **Default:** `1.0`

How strongly scores drive selection when the selection rule is 'fermi'. At 0, scores are ignored and strategies spread by pure luck (random drift). The higher the value, the more reliably higher-scoring strategies get copied. This is the main knob for sweeping between 'luck' and 'meritocracy'. Ignored under the other selection rules.

*Learn more:* This is the temperature-like β in the Fermi update rule from statistical physics.

#### `dynamics.selection_tournament_k` — Tournament size (k)

- **Type:** whole number
- **Allowed values:** 2 to 10000
- **Default:** `3`

How many randomly drawn candidates compete for each next-generation slot when the selection rule is 'tournament_k'. The best scorer among the candidates wins the slot. Bigger values mean stronger selection pressure — with k equal to the whole population, the top scorer wins every slot. Cannot exceed the population size. Not related to the tournament run mode. Ignored under other selection rules.

#### `dynamics.selection_elite_fraction` — Elite fraction (q)

- **Type:** number
- **Allowed values:** 0 to 1
- **Default:** `0.2`

The top share of scorers that the 'truncation' selection rule copies from. At 0.2, only the best-scoring 20% of agents can be parents — every next-generation agent is a copy of someone from that elite. At least one agent always qualifies, and 1.0 means everyone does. Must be above 0. Ignored under other selection rules.

#### `dynamics.selection_threshold_multiplier` — Survival threshold (x mean score)

- **Type:** number
- **Allowed values:** 0 to 10
- **Default:** `1.0`

The survival bar for the 'threshold_cloning' selection rule, as a multiple of the generation's mean score. Agents at or above the bar keep their strategies; everyone else becomes a copy of a random survivor. At 1.0, scoring at least average means survival; higher values are stricter (if nobody clears the bar, the top scorers survive). Ignored under other selection rules.

#### `dynamics.mutation_rate` — Mutation rate (μ)

- **Type:** number
- **Allowed values:** 0 to 1
- **Default:** `0.01`

Chance that a newly created agent ignores the strategy it was supposed to copy and instead adopts a random strategy from the enabled roster. A small rate keeps 'extinct' strategies able to reappear; 0 means perfect copying.

#### `dynamics.score_accounting` — Score accounting

- **Type:** choice
- **Allowed values:** one of: `per_generation`, `sliding_window`, `exponential_discount`
- **Default:** `per_generation`

Which score selection looks at. 'per_generation' uses only the current generation's score — the classic setting. 'sliding_window' uses the average of the last few generations, so one lucky or unlucky generation matters less. 'exponential_discount' uses a running average in which older generations fade out gradually. Only what selection sees changes — the charts keep showing the raw per-generation scores. Ignored in tournament mode, where nothing is selected.

*Learn more:* Score memory smooths selection pressure — useful under random_k matching, where per-generation scores include participation luck.

#### `dynamics.accounting_window` — Accounting window (W)

- **Type:** whole number
- **Allowed values:** 1 to 100000
- **Default:** `5`

How many recent generations are averaged when score accounting is 'sliding_window'. The score selection sees is the mean of the last W generation scores (fewer while the run is younger than W). A window of 1 behaves exactly like per-generation accounting. Ignored under other accounting choices.

#### `dynamics.accounting_discount` — Accounting discount (λ)

- **Type:** number
- **Allowed values:** 0 to below 1
- **Default:** `0.5`

How much of the past is kept when score accounting is 'exponential_discount'. Each generation, the score selection sees blends the new raw score with the previous blended score — higher values remember longer. At 0 the past is forgotten entirely, exactly like per-generation accounting. Must be below 1, or new scores would never matter at all.

#### `dynamics.reproduction_threshold` — Reproduction threshold (θ)

- **Type:** number
- **Allowed values:** at least 0
- **Default:** `500.0`

Energy an agent must hold at the end of a generation to have a child, in the energy economy. Reaching this bar is the 'can afford a child' test; the parent then pays the offspring stake to the newborn. Must be at least the offspring stake, so a parent always survives its own reproduction.

#### `dynamics.offspring_stake` — Offspring stake (σ)

- **Type:** number
- **Allowed values:** at least 0
- **Default:** `400.0`

Energy a newborn starts life with, paid out of its parent's stock at the moment of birth, in the energy economy. A bigger stake gives children a longer runway but drains parents more — reproduction transfers wealth, it does not create it.

#### `dynamics.initial_energy` — Initial energy

- **Type:** number
- **Allowed values:** at least 0; may be empty (= off/unlimited)
- **Default:** empty (no limit)

Energy each founding agent starts the run with, in the energy economy. Leave blank for 'same as the offspring stake' — founders then start life exactly like newborns.

#### `dynamics.basic_living_cost` — Basic living cost (L)

- **Type:** number
- **Allowed values:** at least 0
- **Default:** `200.0`

Energy every agent pays at the end of each generation simply for existing, in the energy economy. This is the metabolic bill: an agent whose play cannot cover it slides toward death. Set it between the all-defector and all-cooperator incomes to make cooperation a survival matter — the Economy panel shows exactly where that window lies.

*Learn more:* The living cost is the metabolic filter: it converts 'scoring poorly' into 'starving', which is what lets defectors go extinct instead of merely being out-copied.

#### `dynamics.engagement_cost` — Engagement cost

- **Type:** number
- **Allowed values:** at least 0
- **Default:** `0.0`

Energy an agent pays per match it takes part in, in the energy economy. At 0, playing is free and more matches are always better; above 0, every interaction has a price, so agents that get drawn into many matches also pay more.

#### `dynamics.reproduction_overhead` — Reproduction overhead

- **Type:** number
- **Allowed values:** at least 0
- **Default:** `0.0`

Extra energy a parent burns at each birth, on top of the offspring stake, in the energy economy. The stake reaches the child; this overhead simply disappears — it is the cost of the act of reproduction itself.

#### `dynamics.capital_return_rate` — Capital return rate (r)

- **Type:** number
- **Allowed values:** at least 0
- **Default:** `0.0`

Interest earned on energy carried between generations, in the energy economy: carried-over energy is multiplied by (1 + this rate) each generation. Above zero it creates rentiers — an agent whose stock exceeds the 'escape velocity' shown in the Economy panel pays its bills from returns alone, forever, no matter how it plays.

#### `dynamics.carrying_capacity` — Carrying capacity (K)

- **Type:** whole number
- **Allowed values:** at least 1
- **Default:** `200`

The most agents the world can hold, in the energy economy. Births only fill seats left below this cap — at capacity, nobody new gets in until deaths free room, and the richest would-be parents are admitted first. It is the well-mixed model's stand-in for physical room; once the population gets a spatial structure (a later milestone), capacity may instead emerge from the number of sites.

#### `dynamics.base_hazard` — Base hazard

- **Type:** number
- **Allowed values:** 0 to 1
- **Default:** `0.0`

Chance a brand-new agent dies of background causes at each generation boundary, in the energy economy. The chance grows with age when the senescence factor is above 1. At 0 — with no maximum age set — nobody dies of age at all; only of running out of energy.

#### `dynamics.senescence_factor` — Senescence factor

- **Type:** number
- **Allowed values:** at least 0; may be empty (= off/unlimited)
- **Default:** empty (no limit)

How steeply the death chance climbs with age, in the energy economy: each generation of age multiplies the base hazard by this factor. Leave blank for 'auto', which picks the value that makes the death chance reach exactly 1.0 at the maximum age. Values above 1 mean aging; exactly 1 means age never matters.

*Learn more:* An exponentially climbing death rate is the Gompertz law of mortality — the standard first model of aging.

#### `dynamics.max_age` — Max age

- **Type:** whole number
- **Allowed values:** at least 0
- **Default:** `0`

A hard age cap, in the energy economy: an agent that reaches this age dies at the next generation boundary, no matter what. 0 means no cap. With a cap set and the senescence factor left blank, the death chance rises smoothly to certainty exactly at this age.

#### `dynamics.async_population` — Async population mode

- **Type:** choice
- **Allowed values:** one of: `variable_n`, `fixed_n`
- **Default:** `variable_n`

What happens to the population size under the asynchronous time model. 'variable_n' carries the energy economy into event time: agents earn by playing, pay to stay alive, have a child the moment they can afford one (with a seat free under the carrying capacity), and die the moment their energy goes negative or old age catches them — the population grows, shrinks, and can go extinct, exactly as in the synchronous economy, just one event at a time. 'fixed_n' is the textbook Moran process: the population is pinned at its starting size and every activation ends with exactly one death paired with one birth, chosen by the Moran rule below — no insolvency deaths, no aging, no extinction, and the carrying capacity is ignored. Energy is still tracked in 'fixed_n', but it only matters as the birth half's fitness (richer agents reproduce more often) and, optionally, as the death rule's aim. Only read under the asynchronous time model.

*Learn more:* The Moran process (Moran 1958) is population genetics' standard fixed-size birth-death model; 'variable_n' is this platform's energy economy running on the same event clock.

#### `dynamics.moran_rule` — Moran rule

- **Type:** choice
- **Allowed values:** one of: `birth_death`, `death_birth`, `random`
- **Default:** `death_birth`

The order of the death half and the birth half of each fixed-size replacement. 'death_birth': one agent dies first (picked by the death rule below), then the whole remaining population competes to fill the empty seat with an offspring — an agent's chance is proportional to how far its energy sits above the poorest competitor's. 'birth_death': one agent is first picked to reproduce, energy-proportionally from everyone, and its offspring then replaces one of the OTHER agents (picked by the death rule below). 'random': every activation rolls afresh between the two, using the two weights below. The order sounds like bookkeeping, but it famously changes outcomes once a population has structure. Only read under 'fixed_n'.

*Learn more:* Ohtsuki et al. 2006 (Nature): under death-birth updating on a network, cooperation is favoured when benefit/cost exceeds the number of neighbours (the b/c > k rule). The structure that makes this bite arrives with a later milestone — in today's well-mixed world the rules differ only mechanically.

#### `dynamics.moran_weight_birth_death` — Moran weight: birth-death

- **Type:** number
- **Allowed values:** at least 0
- **Default:** `0.5`

How often the 'random' Moran rule fires a birth-death replacement, as a weight against the death-birth weight below. The two are normalised at use — 0.8 here against 0.2 there means birth-death fires 80% of the time. Only read when the Moran rule is 'random'; the two weights cannot both be zero (there would be nothing to roll between).

#### `dynamics.moran_weight_death_birth` — Moran weight: death-birth

- **Type:** number
- **Allowed values:** at least 0
- **Default:** `0.5`

How often the 'random' Moran rule fires a death-birth replacement, as a weight against the birth-death weight above. The two are normalised at use — equal weights mean a fair coin each activation. Only read when the Moran rule is 'random'; the two weights cannot both be zero.

#### `dynamics.fixed_n_death_rule` — Fixed-N death rule

- **Type:** choice
- **Allowed values:** one of: `pure_random`, `energy_decides`
- **Default:** `energy_decides`

How the dying agent of a fixed-size replacement is picked — the death half of whichever Moran rule fires (under 'death_birth', who dies; under 'birth_death', which other agent the offspring replaces). 'pure_random' picks uniformly at random, blind to energy — the textbook Moran process, and the setting for reproducing published results. 'energy_decides' always picks the poorest candidate (ties go to the lowest agent id): the population size stays pinned, but the economy still aims the reaper at whoever played worst. Only read under 'fixed_n'.

#### `dynamics.imitation_overlay` — Imitation overlay

- **Type:** true/false
- **Allowed values:** true or false
- **Default:** `false`

Let agents copy each other's strategies on top of whatever the population is already doing. When on, every finished match ends with one of the two players — picked by a fair coin, regardless of score — considering a switch to the other's strategy. The better the other player scored in that match, the likelier the switch (copying a WORSE scorer is possible too, just less likely), tuned by the same selection intensity the Fermi rule uses — at zero intensity the switch is a pure coin flip, exactly like the synchronous Fermi rule's neutral drift. Nothing else changes hands: nobody is born or dies, no energy moves, and the copier keeps its own identity, age, and memory of past opponents — only its playing style changes, and immediately, so a strategy picked up mid-activation is already in use for the next match. This is CULTURAL spread (who imitates whom) running alongside the DEMOGRAPHIC spread (who is born and who dies), and it can be layered on either async population mode. Only read under the asynchronous time model.

*Learn more:* Pairwise-comparison imitation is the standard cultural-evolution counterpart to birth-death dynamics: strategies spread by being copied by the living rather than by out-reproducing the dead.

### Output

#### `output.recording_cadence` — Recording cadence

- **Type:** choice
- **Allowed values:** one of: `per_generation_equivalent`, `per_event`, `every_m_events`
- **Default:** `per_generation_equivalent`

How often an asynchronous run writes a data point (a 'recording period') to its charts and saved files. This is purely an observer control: it changes what gets RECORDED, never what happens in the simulation — the same seed produces the exact same history at every cadence. 'per_generation_equivalent' records once each time the event-time clock crosses a whole number — one point per generation-equivalent, directly comparable to a synchronous run and the sanest file size. 'per_event' records after every single event — maximum resolution, but files and charts grow with every event played, so expect large outputs on long runs. 'every_m_events' records after every m-th event (m is the parameter below) — the middle ground. Only read under the asynchronous time model; synchronous runs always record once per generation.

#### `output.recording_cadence_m` — Events per recording (m)

- **Type:** whole number
- **Allowed values:** 1 to 1e+06
- **Default:** `1`

How many events pass between recordings when the recording cadence is 'every_m_events': a data point is written after every m-th event. At 1 this is the same as recording per event; larger values thin the record out — with N agents, m = N lands close to one point per generation-equivalent. Only read when the cadence is 'every_m_events'.

### Run

#### `run.mode` — Run mode

- **Type:** choice
- **Allowed values:** one of: `evolution`, `tournament`
- **Default:** `evolution`

What kind of experiment this is. 'evolution' means strategies compete AND the population changes over generations — strategies that score well spread through selection, and mutation adds variety. 'tournament' means a fixed cast of agents plays repeated matches while we simply watch the scores accumulate — nothing evolves, like Axelrod's original computer tournaments. Selection and mutation settings are ignored in tournament mode.

*Learn more:* Robert Axelrod's 1980 computer tournaments — fixed strategy line-ups, round-robin play — are where Tit for Tat first made its name.

#### `run.tournament_cycles` — Tournament cycles

- **Type:** whole number
- **Allowed values:** 1 to 100000
- **Default:** `20`

How many complete tournament passes to play when the run mode is 'tournament'. In one cycle, every pairing produced by the matching scheme plays one match (round-robin: every pair plays once). Agents remember their opponents from earlier cycles, so relationships keep developing. Has no effect in 'evolution' mode.

#### `run.seed` — Random seed

- **Type:** whole number
- **Allowed values:** at least 0
- **Default:** `42`

Starting number for the random number generator. Two runs with the same seed and the same settings produce exactly the same results — change it to get a different random history. Every run's seed is saved with its results so any experiment can be replayed.

## Strategy roster

Every playable strategy, in display order. The machine name in
parentheses is the identifier configs use (e.g. in
`population.composition`).

### Always Cooperate (`always_cooperate`)

Cooperates every single round, no matter what the other player does. It does wonderfully among fellow cooperators but is easy prey for anyone willing to betray it.

*Literature note:* Unconditional cooperation ('ALLC') is the standard baseline in the evolutionary game theory literature.

This strategy has no tunable parameters.

### Always Defect (`always_defect`)

Betrays every single round, no matter what the other player does. It exploits trusting opponents but earns poorly against anyone who retaliates — the benchmark that cooperation must beat.

*Literature note:* Unconditional defection ('ALLD') is the dominant strategy of the one-shot Prisoner's Dilemma.

This strategy has no tunable parameters.

### Generous Tit for Tat (`generous_tit_for_tat`)

Plays like Tit for Tat — cooperate first, then copy the other player's last move — but forgives a betrayal some of the time instead of always retaliating. That touch of mercy stops accidental defections from spiralling into endless mutual punishment.

*Literature note:* Nowak & Sigmund (1992): generosity beats strict reciprocity in noisy evolving populations.

#### `strategy.generous_tit_for_tat.generosity` — Generosity (g)

- **Type:** number
- **Allowed values:** 0 to 1
- **Default:** `0.3333333333333333`

Chance that Generous Tit for Tat forgives a betrayal and cooperates anyway instead of striking back. At 0 it behaves exactly like Tit for Tat; at 1 it never retaliates at all. The default of 1/3 is the theoretically best level of forgiveness for the standard payoff values.

*Learn more:* Nowak & Sigmund (1992) derived the optimal generosity min(1 - (T-R)/(R-S), (R-P)/(T-P)), which equals 1/3 for the standard payoffs T=5, R=3, P=1, S=0.

### Grim Trigger (`grim_trigger`)

Cooperates until the other player defects even once — then defects for the rest of the relationship, with no forgiveness ever. Its grim threat keeps honest partners honest, but a single accidental slip poisons the relationship for good.

*Literature note:* Also called 'Grudger' or the Friedman strategy (Friedman 1971), the trigger strategy behind many repeated-game folk theorems.

This strategy has no tunable parameters.

### Pavlov (Win-Stay-Lose-Shift) (`pavlov`)

Judges each round by its own result: if the round went well, it repeats its move; if it went badly, it tries the opposite. This makes it quick to re-establish cooperation after mistakes, and — unlike Tit for Tat — able to exploit players who never retaliate.

*Literature note:* Nowak & Sigmund (1993, Nature): 'Win-stay, lose-shift' outperforms Tit for Tat in noisy evolutionary simulations.

This strategy has no tunable parameters.

### Random (`random`)

Ignores the other player entirely and cooperates at random, with a tunable probability each round. Useful as a noise source and as a baseline that no reciprocity can form a relationship with.

*Literature note:* In Axelrod's tournaments RANDOM finished near the bottom — unpredictability wins no friends in repeated games.

#### `strategy.random.cooperation_probability` — Cooperation probability (p)

- **Type:** number
- **Allowed values:** 0 to 1
- **Default:** `0.5`

Chance that a Random agent cooperates in any given round. At 0.5 it flips a fair coin; 0 makes it always defect and 1 makes it always cooperate. The ends of the range are allowed on purpose, so you can morph Random into either unconditional strategy.

### Tit for Tat (`tit_for_tat`)

Starts by cooperating, then simply copies whatever the other player did last round: cooperation is answered with cooperation, betrayal with betrayal. Simple, never the first to defect, and quick to both punish and forgive.

*Literature note:* Submitted by Anatol Rapoport, Tit for Tat won both of Robert Axelrod's computer tournaments (Axelrod, 'The Evolution of Cooperation', 1984).

This strategy has no tunable parameters.

## Scenarios

Curated, ready-to-run presets from the Scenario Registry. Each is a
complete experiment configuration; in the app, pick one from the
scenario dropdown and every parameter stays editable.

### The Classic Tournament (`classic_tournament`)

Axelrod's original question: which strategy wins a round-robin tournament? All seven strategies field three agents each and play repeated matches — nothing evolves, the scores just accumulate. Watch whether niceness or exploitation pays over the long haul.

**Things to try:** Add execution noise (try 0.05) and watch Grim Trigger tumble down the standings. Shorten the matches to 5 rounds — with less future to protect, defection starts paying.

### Reciprocity Takes Over (`reciprocity_takes_over`)

Can cooperation win in a population of defectors and coin-flippers? Tit for Tat, Always Defect, and Random start in equal numbers under evolution. The classic result: reciprocity invades and takes over — and afterwards, mutation-injected cooperative cousins drift in neutrally, because everyone is already cooperating.

**Things to try:** Set the mutation rate to 0 and the takeover becomes permanent — no drifting newcomers. Cut the rounds per match to 5 and watch Tit for Tat struggle: reciprocity needs repetition to pay off.

### Noise Breaks the Grim (`noise_breaks_the_grim`)

Which reciprocal strategies survive a trembling hand? With a 5% chance that any action flips by accident, one slip poisons Grim Trigger's relationships forever, while forgiving reciprocators (Generous Tit for Tat, Pavlov) can repair the damage. Evolution decides who copes.

**Things to try:** Set the noise to 0 and Grim Trigger is suddenly a fine citizen — the whole drama is noise-driven. Crank the noise to 0.2 and see whether even the forgivers can hold cooperation together.

### Drift vs Meritocracy (`drift_vs_meritocracy`)

What does selection intensity actually do? With β = 0.001, scores barely matter: strategies rise and fall by luck (neutral drift), and even strong performers can vanish by chance. This is the control experiment for every other scenario.

**Things to try:** Re-run with selection intensity 0.5 and compare: the same starting mix now sorts sharply by score instead of wandering. That contrast — not either run alone — is the lesson.

### Defectors' Paradise (`defectors_paradise`)

Can a small band of reciprocators invade a world of defectors? Twenty Always Defect agents and just four Tit for Tats, but the matches are long (high continuation probability — a long 'shadow of the future') and selection is strong. Cooperation among the few can out-earn universal betrayal.

**Things to try:** Lower the continuation probability to 0.5 (short matches) and the invasion fails — the shadow of the future is the whole story. Try 2 Tit for Tats instead of 4: is there a critical cluster size?

### The Growth Economy (`the_growth_economy`)

What happens when survival costs energy and playing earns it? Agents pay a living bill every generation, breed when they can afford the stake, and die when their energy runs out — nobody copies anyone. Cooperators generate more energy per interaction than defectors do, so the same bill that cooperators shrug off can drive defectors extinct, while the population itself grows toward its carrying capacity.

**Things to try:** Set the basic living cost to 320 (above the all-cooperator income of 300) and EVERYONE dies — the survival window is real. Set it to 80 (below the all-defector income of 100) and even defectors grow, because the filter is switched off. Switch the composition to 40 Always Defect and watch the population collapse over generations 4 to 6 — not all at once: every defector is on the same average trajectory, so they all approach zero energy together, and who actually crosses first is decided by participation luck, since under random_k some agents get drawn into more matches than others. Set the max age to 20 and watch the mean-age chart settle. Set the capital return rate to 0.05 and watch the escape velocity appear in the Economy panel.

## Outcome metrics

Named measures the sweep layer (`python -m pdsim.sweep`) computes from a
finished run — the fourth registry, after the Parameter, Strategy, and
Scenario registries. Reference these by machine name in a sweep spec's
`metrics` list.

### Final share (`final_share`)

The fraction of the population the strategy holds at the end of the run (its final count divided by the population size). 0 means it died out; 1 means it took over completely.

- **`strategy`** (strategy) — The strategy machine name to measure.

### Reached fixation (`fixation_flag`)

1 if the strategy ever grew to the entire population at any point in the run, otherwise 0. 'Fixation' is reaching 100% — the classic take-over event.

- **`strategy`** (strategy) — The strategy machine name to measure.

### Time to fixation (`time_to_fixation`)

The generation (or cycle) at which the strategy first reached the whole population. If it never did, this reports the number of periods the run lasted — pair it with 'fixation_censored' to tell the two cases apart (the run simply ended first; fixation might still have happened later).

- **`strategy`** (strategy) — The strategy machine name to measure.

### Fixation censored (`fixation_censored`)

1 if the strategy never reached fixation during the run (so its 'time_to_fixation' is a lower bound, not the true time), otherwise 0. This is the survival-analysis 'censored' flag — it keeps runs that ended early honest instead of pretending fixation never happens.

- **`strategy`** (strategy) — The strategy machine name to measure.

### Mean share (last k periods) (`mean_share_last_k`)

The strategy's average population share over the final k generations (or cycles). A smoother 'where did it end up' measure than the single final share — useful when the population wobbles near the end.

- **`strategy`** (strategy) — The strategy machine name to measure.
- **`k`** (int) (default: `10`) — How many trailing periods to average.

### Ever exceeded threshold (`ever_exceeded`)

1 if the strategy's share ever reached the given threshold (a fraction between 0 and 1) at any point, otherwise 0. A 'quasi-fixation' measure: when mutation keeps a population from ever being perfectly pure, 'reached 90%' is often the honest question rather than 'reached 100%'.

- **`strategy`** (strategy) — The strategy machine name to measure.
- **`threshold`** (float) (default: `0.9`) — Share (0-1) the strategy must reach.

### Held above threshold for k periods (`held_above_for`)

1 if the strategy's share stayed at or above the threshold for at least k consecutive generations (or cycles) somewhere in the run, otherwise 0. A staying-power measure: it rewards durable dominance, not a one-period spike.

- **`strategy`** (strategy) — The strategy machine name to measure.
- **`threshold`** (float) (default: `0.9`) — Share (0-1) to stay at or above.
- **`k`** (int) (default: `5`) — Required run of consecutive periods.

### Minimum cooperation rate (`min_cooperation`)

The lowest overall cooperation rate the population reached at any point (0 = everyone defecting, 1 = everyone cooperating). Catches a cooperation collapse even if the population recovers afterwards. Not available for runs recorded before cooperation tracking existed.

This metric takes no parameters.

### Final cooperation rate (`final_cooperation`)

The overall cooperation rate at the end of the run (0 = everyone defecting, 1 = everyone cooperating). Not available for runs recorded before cooperation tracking existed.

This metric takes no parameters.
