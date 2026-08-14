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

#### `matching.spatial_interaction` — Spatial interaction

- **Type:** true/false
- **Allowed values:** true or false
- **Default:** `false`

Whether agents play their NEIGHBOURS instead of the whole population. Off — the default — is exactly today's behaviour: the matching scheme below picks partners from the entire population, and distance plays no part. On: each agent's partners are sampled from within the interaction radius by the reach kernel (see the Structure section), and the matching scheme is NOT consulted — round-robin has no local analogue (there is no 'every pair plays once' inside overlapping neighbourhoods), and the population-wide schemes are just this kernel with unlimited radius. Instead, 'Opponents per agent' (k) does the work: set k at or above the neighbourhood size to PLAY ALL YOUR NEIGHBOURS (the classic Hammond–Axelrod convention), and k simply CLAMPS to the neighbours that actually exist rather than erroring — a corner cell with 3 neighbours on a bounded Moore grid plays 3 matches at k = 8, which is geometry, not a misconfiguration. One counting fact worth knowing: partners are drawn per agent WITHOUT checking who already drew whom, so A can pick B while B picks A and the pair meets twice. At k at-or-above the neighbourhood size each agent therefore plays roughly TWICE its neighbour count in matches per generation (its own, plus being drawn by each neighbour) — income is about double a naive reading. Requires the lattice world structure: in a well-mixed world there is no distance to sample within.

*Learn more:* Playing only your neighbours is what makes clustering matter: cooperators inside a cluster keep cooperation's benefits among themselves — spatial reciprocity, the mechanism this milestone exists for.

#### `matching.matcher` — Matching scheme

- **Type:** choice
- **Allowed values:** one of: `round_robin`, `random_k`
- **Default:** `round_robin`

How opponents are paired up each generation (or tournament cycle). 'round_robin' means every agent plays every other agent exactly once — thorough, but the match count grows with the SQUARE of the population. 'random_k' means each agent starts matches against a few randomly drawn opponents instead, so big populations stay fast. While 'Spatial interaction' (above) is on, this scheme is NOT consulted — partners come from the grid via the reach kernel instead, and the widget greys to say so.

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

### Structure

#### `structure.kind` — World structure

- **Type:** choice
- **Allowed values:** one of: `well_mixed`, `lattice`
- **Default:** `well_mixed`

The shape of the world the population lives in. 'well_mixed': the classic aspatial world of every earlier version — there are no places, every agent can meet every other, and distance does not exist. 'lattice': the population lives on a rectangular grid of sites, each site holding at most one agent; who an agent plays and where its newborn children are placed become LOCAL questions, decided by grid distance. One honest caveat, stated where the choice is made: under synchronous 'imitation' reproduction the agent a player compares its score against is still drawn from the WHOLE population even on a lattice — interaction partners and newborn placement go local, strategy imitation stays global.

*Learn more:* Putting a population on a grid is what lets cooperators survive by clustering — neighbours mostly meet neighbours, so cooperation's benefits stay among cooperators instead of leaking to everyone.

#### `structure.rows` — Lattice rows

- **Type:** whole number
- **Allowed values:** at least 1; may be empty (= off/unlimited)
- **Default:** empty (no limit)

Number of rows in the lattice grid. Leave empty for automatic sizing: the grid becomes the most-square rectangle whose cell count exactly equals the population size (400 agents give a 20 x 20 grid; 60 give 6 x 10). A PRIME population size can only factorise as a single line of cells (101 gives 1 x 101) — a legitimate one-dimensional world, not a bug. If you set only one dimension, the other resolves to the smallest count that fits the whole population. Ignored under the 'well_mixed' structure.

#### `structure.cols` — Lattice columns

- **Type:** whole number
- **Allowed values:** at least 1; may be empty (= off/unlimited)
- **Default:** empty (no limit)

Number of columns in the lattice grid. Leave empty for automatic sizing: the grid becomes the most-square rectangle whose cell count exactly equals the population size (400 agents give a 20 x 20 grid; 60 give 6 x 10). A PRIME population size can only factorise as a single line of cells (101 gives 1 x 101) — a legitimate one-dimensional world, not a bug. If you set only one dimension, the other resolves to the smallest count that fits the whole population. Ignored under the 'well_mixed' structure.

#### `structure.neighbourhood_shape` — Neighbourhood shape

- **Type:** choice
- **Allowed values:** one of: `moore`, `von_neumann`
- **Default:** `moore`

Which cells count as a cell's neighbours — and, with that, what DISTANCE means on the grid, because the shape IS the distance metric. 'moore': the 8 surrounding cells are neighbours; a diagonal step counts as distance 1, so distance is the LARGER of the row and column differences (Chebyshev distance). 'von_neumann': only the 4 orthogonal cells (up, down, left, right) are neighbours; a diagonal step costs 2, because distance is the row difference PLUS the column difference (Manhattan distance). This one choice governs birth reach and interaction reach TOGETHER: every 'how far away is that site' in the world is measured with the metric chosen here, never per feature.

*Learn more:* The two classic cellular-automaton neighbourhoods, named after Edward F. Moore and John von Neumann.

#### `structure.boundary` — Grid boundary

- **Type:** choice
- **Allowed values:** one of: `torus`, `bounded`
- **Default:** `torus`

What happens at the edge of the grid. 'torus': the world wraps around — the left edge is adjacent to the right edge and the top to the bottom, so there is no rim and every cell has exactly the same number of neighbours. 'bounded': the grid has hard edges — corner and edge cells have FEWER neighbours than interior cells (a corner keeps 3 of Moore's 8, or 2 of von Neumann's 4). The default is 'torus' because uniform degree removes an edge artifact: how easily cooperation survives depends on how many neighbours a cell has, so on a bounded grid the corners become spuriously friendly to cooperation — an effect of the map's edge, not a finding about the model. Choose 'bounded' deliberately when a hard edge is itself part of what you want to model (a coastline, a walled world).

#### `structure.initial_layout` — Initial layout

- **Type:** choice
- **Allowed values:** one of: `random`, `checkerboard`, `stripes`, `blocks`, `patches`, `central_block`, `from_file`
- **Default:** `random`

How the starting population is ARRANGED on the grid. It decides arrangement only — how many agents of each strategy there are is already fixed by the population mix, and the layout simply deals that fixed deck onto cells. This choice matters enormously on a lattice: whether cooperators start clustered together or scattered among defectors can decide whether cooperation survives at all. 'random': agents are scattered over the whole grid in random order — the closest spatial analogue of the classic well-mixed world, and the honest baseline. 'checkerboard': strategies are dealt one cell at a time in rotation, so agents are interleaved as thoroughly as the counts allow — with two equal-sized strategies this is the literal chessboard, and with four unequal ones it is still the maximum-mixing arrangement. This is the ANTI-CLUSTER baseline: if cooperation survives here, it is not surviving by clustering. 'stripes': each strategy's whole count is dealt as one consecutive run along a row-by-row sweep, giving broad bands. Because the run ends where the COUNT ends rather than where a row ends, a 'stripe' can be a fragment of a row — that is the arrangement working as intended, not a glitch. 'blocks': the same consecutive-run dealing, but along a tile-by-tile sweep, so each strategy occupies a chunky two-dimensional region instead of horizontal bands. 'patches': one randomly placed seed cell per strategy, with each patch then growing outward until its quota is used up — the most natural irregular clusters. Only the seed placement is random; the growth is fixed. 'central_block': the population fills a centred rectangle — the most-square rectangle holding exactly the population count (a prime-sized population makes a single line) — and the rest of the grid is left EMPTY: the expanding-frontier setup, where what you are watching is a population growing into empty space. NOTE: with the grid dimensions left on automatic the world holds exactly as many sites as agents, so the rectangle IS the whole grid and the picture is identical to 'stripes' — set Lattice rows and columns larger than the population to see the empty frame. 'from_file': read the exact arrangement, cell by cell, from a layout file you wrote (see the layout file parameter). Its tokens are strategy MACHINE NAMES exactly as registered — the app lists the current spellings beside the layout file box, and the grid_templates folder ships worked examples. Ignored under the 'well_mixed' structure.

*Learn more:* Starting arrangement is a genuine experimental variable in spatial game theory, not a cosmetic one: the classic result that cooperators survive by clustering is a statement about arrangement, so comparing 'patches' against 'checkerboard' at identical composition isolates exactly that effect.

#### `structure.layout_file` — Layout file

- **Type:** text
- **Allowed values:** any text; may be empty (= off)
- **Default:** empty (no limit)

The layout file that paints the starting world cell by cell. Read only when the initial layout is 'from_file'; leave it empty otherwise. A BARE FILENAME (no slash or backslash) is looked up in the project's grid_templates folder, which ships with a README and worked examples; a value containing a path separator, or an absolute path, is used exactly as given. The file is a picture of the grid: a short header of 'kind: lattice_grid', 'rows:' and 'cols:' lines, then one line per grid row, one token per cell — separated by spaces, or by commas (if any grid line contains a comma, the whole file is read comma-separated). A token is either a strategy's MACHINE NAME spelled exactly as registered (such as 'always_defect' — the app lists the current names beside this box) or a full stop '.' for a cell left empty; in the comma style an empty field between commas is an error, not an empty cell. The file's row and column counts must match the grid's, and it must place exactly as many agents as the population size — but WHICH strategy sits in each cell is entirely the file's decision, so the population-mix widgets no longer control the arrangement or the mixture. When the Population section disagrees with the file, the app points out the difference and offers to fill the section in from the file with one click, so nothing needs retyping. A copy of the file is saved into the run folder, so a recorded run can always be re-run even if the original file later moves or changes.

#### `structure.birth_radius` — Birth radius (R)

- **Type:** whole number
- **Allowed values:** at least 1; may be empty (= off/unlimited)
- **Default:** `1`

How far from its parent a newborn can be placed, in grid distance (the neighbourhood shape above decides what distance means). At birth, the empty sites within this radius of the parent are the candidate homes; if EVERY site in reach is occupied, the parent is BLOCKED this round — it pays nothing, keeps its energy, stays eligible, and simply tries again next generation (the Economy panel counts blocked parents so this reads as the mechanism it is, not as a stall). At 1 — the default — children land right next to their parents, the classic Hammond–Axelrod setting and the one that makes family clusters form. Leave empty for unlimited reach: a child can then land on any empty site on the grid. IMPORTANT under the fixed-size ('fixed_n' Moran) population mode: this radius and the decay below define WHO COMPETES to fill a freed site — the set of neighbours whose fitness contest decides the replacement — which is exactly the neighbour count k that the b/c > k cooperation threshold counts. That is why the pair stays live under 'fixed_n' even though nobody breeds freely there. Ignored under the 'well_mixed' structure.

*Learn more:* Hammond & Axelrod 2006 place offspring in the immediate neighbourhood; Ohtsuki et al. 2006 derive b/c > k, where k counts the competitors for a vacated site.

#### `structure.birth_decay` — Birth decay (β)

- **Type:** number
- **Allowed values:** 0 to 20
- **Default:** `0.0`

How steeply a newborn's placement prefers sites CLOSER to its parent, within the birth radius. This is the decay β of the reach kernel: a candidate site at distance d is weighted exp(−β·d). At 0 — the default — every empty site within the radius is equally likely; higher values keep children ever closer to home even where the radius technically allows more distance. IRRELEVANT at a birth radius of 1: all candidates then sit at the same distance, so every β gives the same behaviour. Under the fixed-size ('fixed_n' Moran) population mode this decay also weights the competition for a freed site — nearer neighbours are likelier to win it. Ignored under the 'well_mixed' structure.

#### `structure.placement_contest` — Placement contest

- **Type:** choice
- **Allowed values:** one of: `random`, `energy_priority`
- **Default:** `random`

Who places first when several parents breed at the same generation boundary — the order matters on a lattice, because an earlier parent can take the last empty site in a neighbourhood another parent wanted. 'random' — the default — shuffles the admitted parents once and lets each place in turn: reproduction order is luck (the Hammond–Axelrod convention), so wealth decides only WHO MAY BREED (via the reproduction threshold), never who wins contested ground. 'energy_priority' lets the RICHEST admitted parent place first: an advantage that COMPOUNDS spatially — a good neighbourhood raises earnings, which wins more contested cells, which acquires more good territory — a substantive modelling claim to switch on deliberately, not to inherit silently. Only matters under a synchronous energy-economy run on a lattice; everywhere else births never contend (an asynchronous run resolves one birth at a time, and a well-mixed world has no cells to contest).

#### `structure.interaction_radius` — Interaction radius (R)

- **Type:** whole number
- **Allowed values:** at least 1; may be empty (= off/unlimited)
- **Default:** `1`

How far away a potential match PARTNER can be, in grid distance (the neighbourhood shape above decides what distance means). This is the hard edge of 'who is reachable as a partner': agents beyond it are simply never met. At 1 — the default — partners come from the immediate neighbourhood only, the classic Hammond–Axelrod setting. Leave empty for unlimited reach: every agent on the grid is then a candidate, with only the decay below expressing locality. Only consulted while 'Spatial interaction' (in the Matching section) is on; ignored otherwise, and ignored under the 'well_mixed' structure.

#### `structure.interaction_decay` — Interaction decay (β)

- **Type:** number
- **Allowed values:** 0 to 20
- **Default:** `0.0`

How steeply partner choice prefers CLOSER agents, within the interaction radius. This is the decay β of the reach kernel: a candidate at distance d is weighted exp(−β·d). At 0 — the default — every reachable agent is equally likely (a uniform disc); higher values make distant partners reachable but increasingly unlikely. IRRELEVANT at an interaction radius of 1: all candidates then sit at the same distance, so every β gives the same behaviour. Only consulted while 'Spatial interaction' (in the Matching section) is on; ignored otherwise, and ignored under the 'well_mixed' structure.

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
- **Allowed values:** at least 1; may be empty (= off/unlimited)
- **Default:** empty (no limit)

The most agents the world can hold, in the energy economy. Births only fill seats left below this cap — at capacity, nobody new gets in until deaths free room, and the richest would-be parents are admitted first. Leave blank for automatic: on a lattice the capacity becomes the NUMBER OF GRID SITES (the grid decides — the zero-effort spatial setting), while in a well-mixed world, where there is no grid to decide, blank falls back to the standard 200. On a lattice an explicit value BELOW the site count leaves deliberate slack — the population then parks below a full grid, and the occupied region can drift, cluster, and migrate as births and deaths reshape it. The capacity can never exceed the site count: the grid is the outer bound, this cap an optional tighter one.

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

#### `dynamics.boundary_order` — Boundary order

- **Type:** choice
- **Allowed values:** one of: `death_first`, `birth_first`
- **Default:** `death_first`

The order of deaths and births at each synchronous generation boundary. 'death_first' — the default, and this platform's behaviour in every earlier version — applies deaths first, then lets survivors breed into the room the deaths freed. 'birth_first' is Hammond & Axelrod's period order: reproduction runs first, then the death phase. Two real consequences, both pushing the population DOWN relative to 'death_first'. (1) Births are rationed against the PRE-death population: free seats under the carrying capacity are counted before the dead have vacated theirs, so FEWER births are admitted — with capacity 200, 180 alive and 20 deaths, death-first admits 40 births where birth-first admits only 20. That is a different demographic regime, not a phase offset, and it is present even without a lattice. (2) Newborns go through the death phase in their own birth round — the age-mortality coin included — so a child can die the very round it was born. A 'birth_first' run sitting at a visibly lower population is correct, not broken. On a lattice the choice additionally decides WHICH sites are empty when children are placed: deaths-first lets newborns fill the interior graves the dead just left, while births-first offers only the cells that were already empty — the frontier. Only read under the synchronous time model.

*Learn more:* Hammond & Axelrod 2006 run immigration → interaction → reproduction → death; their ethnocentrism result lives on the frontier this ordering creates.

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

### Async: Death-Birth Fixation (`async_death_birth_fixation`)

What does evolution look like when time has no generations? Here the clock ticks one event at a time: an agent is drawn, plays its matches, and then one randomly chosen agent dies and the rest compete — weighted by accumulated energy — to fill the empty seat (the classic Moran death-birth update). The population count is pinned, so the only thing that can change is WHO the population is: watch one strategy drift and drive toward complete fixation while the total height of the composition chart never moves. The x-axis is generation-equivalents: N events, one population's worth of activity, per unit.

**Things to try:** Switch the Moran rule to birth_death — now the breeder is chosen first and its offspring replaces someone else; the two orders differ subtly in who is at risk. Switch the death rule to energy_decides and the reaper stops being blind: the lowest-energy agent always dies, so newborns (who start at the stake, here 0) live dangerously. Set the mutation rate to 0.01 and fixation stops being forever — the lost strategy keeps reappearing.

### Async: Imitation Only (`imitation_overlay_only`)

Can a population change what it plays without anyone being born or dying? This run switches every demographic channel off — the breeding threshold is unreachable, the living cost is zero, and there is no age limit — and turns ON the imitation overlay: after each match, one of the two players (picked by a fair coin, regardless of score) considers copying the other's strategy, and the better the other scored IN THAT MATCH, the likelier the copy. Watch strategy shares move while the population count stays perfectly flat — and watch WHICH WAY and HOW FAST they move: defection sweeps the population within a couple of generation-equivalents. In any mixed match the defector out-earns the very reciprocator it is exploiting, so copying match winners favours Always Defect even though reciprocators earn more from each other — and because copying happens per MATCH, minds change on the interaction timescale, far faster than any demographic takeover. The run records per event, so you see every single step of the sweep.

**Things to try:** Set the selection intensity to 0 and the copying becomes a pure coin flip — neutral drift, which still churns just as fast but with no direction: try a few seeds and either strategy can sweep. Crank it to 10 and the takeover is nearly one-way. Compare with The Growth Economy, where the SAME strategies compete demographically and cooperators win — the two channels reward different things. Check the recorded run in the Results browser: total agents born equals the twenty founders; only minds changed.

### Async: Mixed Moran Rules (`moran_random_mix`)

What lies between the two classic Moran updates? Each event here rolls a weighted coin: 80% of events run birth-death (pick a breeder by energy, its offspring replaces a random other) and 20% run death-birth (a random agent dies, the rest compete for the seat). With only 24 agents any single run is a fixation GAMBLE — higher earners are favoured to take over, not guaranteed to — and the rule mixture shifts the odds. This seed happens to fixate Always Defect: an early lucky streak snowballs, which is exactly what finite-population drift means.

**Things to try:** Set the weights to 1/0 (pure birth-death), then 0/1 (pure death-birth), and run each across a few seeds — single runs are gambles, so it is the SPREAD of outcomes the mixture sits between, not any one trajectory. Switch the death rule to energy_decides and the gamble largely disappears: the reaper targets the poorest, so the higher earners fixate far more reliably. In this well-mixed world the rules differ only mechanically; when population structure arrives (M11), death-birth is the update under which neighbourhoods can favour cooperation.

### Async: The Growth Economy in Event Time (`sync_vs_async_economy`)

The Growth Economy again — same costs, same stakes, same carrying capacity — but with the generation dissolved: births fire the moment a parent clears the threshold, deaths fire the moment energy runs out, and the clock advances 1/N per event. The population still grows from 40 toward the carrying capacity of 200 as defectors go extinct, on a comparable x-axis (generation-equivalents carry the same per-agent interaction budget as generations). Flip the time model back to synchronous and compare: the same growth story, told by two different clocks.

**Things to try:** Flip the time model to synchronous and run again: both runs grow from 40 toward K = 200 and the Economy panel's survival window applies to both — but they are NOT identical runs, and should not be: event time compounds interest continuously over income that arrives mid-period, where the generational clock applies it once at each boundary. Switch the recording cadence to per_event to see every single birth and death at full resolution (bigger files, denser charts).

### Cooperation Survives in Clusters (`spatial_reciprocity`)

Can cooperation survive on pure geography, with no reciprocity at all? Two hundred agents — half Always Cooperate, half Always Defect — live on a 20 × 20 torus of 400 sites, so the world starts half empty and clusters have room to breathe (left blank, the grid would auto-size to exactly 200 sites — a full world with no room). Reproduction is the energy economy rather than copying because the story is ECOLOGICAL survival: agents live or die on absolute income measured against a survival bill. The founding layout is 'patches' — contiguous clusters from generation 0, dealt inside a centred 200-site blob — so the interior-versus-edge arithmetic below is on screen immediately. Spatial interaction is on with the von Neumann neighbourhood (4 orthogonal neighbours — fewer neighbours means stronger viscosity, the setting most likely to let clusters win), the torus keeps every site at exactly 4 neighbours (which is what makes the interior arithmetic exact), the opponents-per-agent count of 5 simply clamps to the 4 neighbours that exist (play-all-your-neighbours), and children land right next to their parents (birth radius 1). Matches last ONE round, so matches and rounds are the same number and every figure below is per generation. The income rates: each adjacent pair meets twice per generation (each side initiates one match — measured in this engine, exactly), so with T = 5, R = 3, P = 0, S = −1 a cooperator earns +6 per cooperating neighbour (2 × R) and −2 per defecting neighbour (2 × S), while a defector earns +10 per cooperating neighbour (2 × T) and 0 per defecting neighbour (2 × P). P is set to 0 — overriding the default 1 — because the scenario's whole claim is that a defector interior earns NOTHING against the living cost; and S = −1 keeps the strict T > R > P > S ordering legal with P at 0, and makes cluster edges actively bleed energy rather than merely fail to earn it. An agent with all four neighbour sites occupied plays exactly 8 matches per generation (4 it initiates + 4 it is drawn into): an interior cooperator earns 8 × 3 = 24, an interior defector 8 × 0 = 0, so the survival window is 0 ≤ L < 24 and the living cost of 12 sits at its midpoint. At L = 12 a cooperator with n cooperating neighbours (all four sites occupied) earns 8n − 8: interiors net +12, flat cluster edges (n = 3) net +4, corners (n = 2) net −4 — compact clusters thrive, ragged edges erode. A defector touching one cooperator earns 10 and nets −2: it starves, slowly; only a defector hugging two or more cooperators profits, so frontier parasitism is present but contained. (Agents on the blob's rim have empty neighbour sites, play fewer matches, and earn proportionally less — the formulas above are the full-occupancy cases.) The ledger paces the drama: interior defectors fall 12 per generation from their starting 40 and die during generation 4; interior cooperators rise 12 per generation, first breed at generation 2 (64 ≥ the threshold of 60), pay the 40-point stake to the child, and settle into a three-generation breeding rhythm. Mutation is 0 so no copying-rule mutant can seed a defector inside a cooperator cluster and muddy that arithmetic, and 100 generations is plenty: defector interiors die by about generation 4, and the edge dynamics play out over tens of generations. One guard, because it is easy to blur: this scenario does NOT rest on the b/c > k threshold. Its story is ecological — absolute income against a survival threshold, with P = 0 meaning a defector interior earns nothing — while b/c > k concerns relative fitness in a Moran process under weak selection, and that is 'The b/c > k Threshold' scenario's story. The two arguments happen to point the same way and must never be conflated; this matrix is not even additive (T − R = 2 against P − S = 1), so 'b/c' is not defined here — the additivity readout beside the payoff widgets says so.

**Things to try:** First, the well-mixed comparison — in this order: turn Spatial interaction OFF first, then switch the world structure to well_mixed, then set the matching scheme to random_k (the opponents-per-agent count is already 5). The order matters: under well_mixed the spatial toggle greys out with its value stranded, and a stranded-on toggle fails validation — switch it off while it is still editable. The matcher matters too: the default round-robin at 200 agents would give every agent 199 matches, income two orders of magnitude above L = 12, and the filter would simply be off. With random_k at k = 5 the arithmetic stays on the spatial run's scale: about 2k = 10 matches, so a cooperator meeting the average 50/50 mix earns about 5 × 3 + 5 × (−1) = 10 and nets −2 against L = 12, starving slowly, while a defector earns about 5 × 5 + 5 × 0 = 25 and nets +13, breeding freely. Always Defect takes everything — and then, with the cooperators gone, all-defector income is 0 against L = 12 and the whole population collapses. Without a grid to cluster on, cooperation dies first and everyone follows: the tragedy completes. Second, the Moore switch, as arithmetic rather than prediction: the naive reading says von Neumann means 4 matches; the measured truth is 8; Moore at k ≥ 8 (raise Opponents per agent to 8 to play all eight neighbours) gives 16 by the same arithmetic. Against the naive reading that is a FOUR-fold income change (16 vs 4); against the actual it is two-fold (16 vs 8). At L = 12 the Moore all-cooperator interior income of 48 sits far above the cost and the metabolic filter loosens dramatically — the window becomes 0 ≤ L < 48 with L sitting in its lower quarter. Whether clusters struggle under the weaker viscosity is then something to watch, not something promised: recompute the window before trusting any living cost after this switch.

### The b/c > k Threshold (`donation_game_threshold`)

The closest this platform can come to a textbook replication: the death-birth rule on a lattice, where theory (Ohtsuki and colleagues) says cooperation is favoured when the benefit-to-cost ratio of helping exceeds the number of neighbours — b/c > k. One hundred agents fill a 10 × 10 torus exactly (the fixed-size Moran mode requires one agent per site), half Always Cooperate and half Always Defect, scattered at random; the neighbourhood is von Neumann, so k = 4 — the case that CLEARS the b/c = 5 threshold, which is why the default view shows cooperation succeeding — and Opponents per agent is 4, exact play-all at the von Neumann degree. Four settings are load-bearing, and each deserves its reason. (1) ONE round per match, with only these two strategies: the threshold is derived for one-shot games, so noise, memory depth, and every reciprocity parameter are inert here — that is where the seven-strategy roster went; at one round Tit for Tat would just cooperate and be indistinguishable from Always Cooperate anyway. (2) The fixed-N death rule is pure_random, NOT the default energy_decides: this death-birth process kills a RANDOM individual, whose neighbours then compete by fitness for the empty site. The default makes the death deterministic — a plausible-looking run that is not the model being replicated. (3) The honesty caveat: in this engine the competition for the empty seat reads each candidate's ACCUMULATED lifetime energy, with no selection-intensity dial, so the weak-selection limit in which b/c > k is derived cannot be approached here. Selection begins at exactly zero (every founder holds identical energy, so the draw starts uniform) and strengthens from nothing — and because fitness reads a lifetime stock rather than a current flow, the draw partly selects for AGE rather than strategy. Measured in this engine across 20 seeds per shape, the mean final cooperator share was 0.596 under von Neumann against 0.569 under Moore — inside sampling noise, with NO visible reversal. The threshold is a calibration compass, not a prediction. (4) Additivity — the payoffs T = 5, R = 4, P = 0, S = −1 are not arbitrary: read the cost of cooperating off the matrix twice and you get T − R = 1 against a cooperator and P − S = 1 against a defector — the same number, c = 1 — and the benefit falls out symmetrically (T − P = 5 = R − S, so b = 5), making b/c = 5 unambiguous. The registered default payoffs (5, 3, 1, 0) FAIL that test: a perfectly valid Prisoner's Dilemma that is simply not a donation game, under which 'b/c' is not a well-defined quantity at all. And additivity with P = 0 forces the negative sucker payoff — S = −1 is not a stylistic choice. Mutation is 0 so fixation, when it comes, is permanent and readable; 150 generation-equivalents is the horizon the in-engine measurement used. One last honesty note: the shipped seed is one on which cooperation happens to win. At this selection strength any single run is a fixation gamble (the 20-seed measurement above is the honest picture), so try other seeds and expect either outcome.

**Things to try:** Switch the neighbourhood shape to moore and re-run. Theory predicts a reversal — k = 8 exceeds b/c = 5 and fails the threshold that k = 4 clears — so state that prediction, run it, and expect very little visible change. The gap between the prediction and the observation IS the weak-selection lesson: this engine's selection is far from the limit in which the threshold is derived, and the compass points where the prediction cannot. Second warning: the payoffs are live widgets, and the threshold only applies while T − R = P − S holds — the additivity readout beside the payoff widgets says when it no longer does.

### The Drifting Frontier (`the_drifting_frontier`)

What does a population look like when it CANNOT fill its world? 120 agents — Tit for Tat, Always Cooperate, and Always Defect, forty each — found as patches on a 20 × 20 grid of 400 sites, with the carrying capacity set to 240: 60% of the site count, so 160 sites' worth of slack is always in play. This is the growth economy's own calibration, moved onto a lattice: random_k matching with k = 5 gives each agent about 2k = 10 matches per generation, 10 rounds per match makes 100 rounds, so all-cooperator income is 100 × 3 = 300 and all-defector income is 100 × 1 = 100 — the survival window is 100 ≤ L < 300, and the living cost of 200 sits at its midpoint (a cooperator-pair economy nets +100 per generation; an all-defect economy −100). Spatial interaction is deliberately OFF: local birth WITHOUT local interaction is a legitimate configuration in its own right, and this scenario demonstrates the separability — children land within radius 1 of their parents (the birth kernel is the active spatial mechanism here) while everyone still plays everyone, which is also what keeps the window arithmetic above honestly aspatial. The churn comes from a 5% base hazard with the senescence factor pinned at 1 (age never matters — the hazard is a flat coin every generation), so the mean lifetime is 20 generations and deaths land ANYWHERE on the grid. The story to watch: deaths free sites anywhere, births fill sites only next to parents, and the 160-site slack means the occupied region drifts, clusters, and migrates across the world rather than filling it. Mutation is 0, keeping the three-way composition clean, and 200 generations is ten full population turnovers — drift is slow. Compare the Founding and Final grid views in the results browser to see how far the region wandered.

**Things to try:** Clear the carrying capacity (leave it blank): on a lattice, blank resolves to the site count — 400 — and the slack vanishes: the grid fills and the drift stops. Then try the recalibration drill, in two steps: turn Spatial interaction ON and RECOMPUTE the window before trusting the living cost. First, at the default Moore shape: matches per agent is about 2 × min(5, 8) = 10 — the window happens NOT to move. That is the drill working, not failing: sometimes its answer is 'no change', and you only know by running it. Second, switch the shape to von Neumann: min(5, 4) = 4, so 8 matches, 80 rounds — the window is now 80 ≤ L < 240 and the living cost of 200 sits near its top: all-cooperator pairs net +40 where they netted +100, and all-defect nets −120.

### The Filling Grid (`the_filling_grid`)

Sixty agents — half Always Cooperate, half Always Defect — start packed into a centred 6 × 10 rectangle (the most-square rectangle holding 60) with 340 empty sites around them: the FILLING regime, a population expanding into empty space (the early-run setting Kaznatcheev & Shultz's result concerns, and the reason the central_block layout exists). The carrying capacity is left blank and resolves to the site count, 400, so the grid itself is the only cap. Spatial interaction is on at the default Moore neighbourhood — kept deliberately, as the contrast with the flagship's von Neumann — with Opponents per agent at 8 (play-all at the Moore degree) and 10 rounds per match. The payoffs stay at the defaults (5, 3, 1, 0), and P = 1 is the deliberate anti-flagship choice: a saturated defector interior earns 16 matches × 10 rounds × 1 = 160 per generation and never starves. During the fill, frontier agents with few neighbours earn little — a cooperator pair alone on the edge plays 2 matches × 10 rounds × 3 = 60 and nets +20 against the living cost of 40 — while an all-cooperator interior plays 16 × 10 = 160 rounds, earns 480, and nets +440, breeding nearly every generation against the 50-point gap between the 150-point stake and the 200-point threshold. Free space means everyone who can pay expands, and cooperation's share can rise early. But on the shipped seed saturation never arrives, and what actually happens is the scenario's real lesson: RISE, THEN FREEZE. Reproduction here has two gates, and a parent must clear both — clearing one is not clearing the other. The first gate is global admission: births only fill seats left under the carrying capacity, and when seats are scarce the RICHEST eligible parents are admitted first. The second gate is local placement: an admitted parent must find an empty site within reach (Moore radius 1) to put the child in — and a parent that fails placement pays nothing and stays eligible, and richer, next generation. At population scale the two gates deadlock: the richest parents are the all-cooperator interior (earning 480 per generation, compounding), and interior agents are precisely the ones with no empty site in reach — so they consume the entire admission quota and then fail placement, every generation, while the poorer frontier parents, every one of them above the breeding threshold and beside an empty site, never rank inside the quota. Growth stops around 265 of the 400 sites with zero deaths and near-zero births: a genuine standstill, not a slowdown. See the signature yourself in the Economy panel: from about generation 6 onward, 'Blocked parents this generation' equals EXACTLY 400 minus the population, every generation — the whole admission quota, spent on parents who cannot place. (Had the grid filled, the expected endgame was a slow grind — a saturated defector interior earns 160 against the living cost of 40 and never starves, so only fully-encircled cooperators could die, one cell at a time — but the freeze arrives first.) 300 generations gives the rise room to complete and the freeze room to prove it is permanent.

**Things to try:** Switch the punishment payoff P to 0 — after first unticking 'Enforce PD payoff ordering (T > R > P > S)' in the Game section, because the sucker payoff here is 0, so P = 0 ties P and S and the strict-ordering check would reject it — and re-derive before running: a defector whose occupied neighbours are all defectors now earns 16 × 10 × 0 = 0 against the living cost of 40, and starves. Dead defectors free interior sites — and freed interior sites are exactly what the frozen world lacks, so the freeze MAY break and the fill resume. That is arithmetic, not a promise: whether enough defectors sit in all-defector pockets to matter is something to watch, not something guaranteed. And recompute the survival window whenever you touch a payoff — this one change moves the all-defector income bound from 160 to 0.

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
