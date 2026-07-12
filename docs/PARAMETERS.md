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

Number of agents in the population. It stays constant across generations: selection always produces exactly this many agents. Practical note for v1: a few hundred agents is the comfortable limit for live visualization.

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
