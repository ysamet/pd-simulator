# M10 — The growth economy

*Companion explainer to `docs/specs/M10a-growth-economy.md`. The spec is the
what and the how. This is the why, the science, and where the ideas come from.*

*Written for someone who has just met game theory. Every piece of jargon is
unpacked the first time it appears, and every claim about numbers is worked out
in full rather than asserted.*

---

## 1. Two paradigms: copying versus living

Up to now, pdsim has evolved its population by **imitation**. At the end of each
generation every agent has a score, and the next generation is built by asking,
for each of the N slots, "whose strategy does this slot copy?" The Fermi rule
answers probabilistically: a slot is more likely to copy a high-scoring agent
than a low-scoring one. Nobody is born and nobody dies. The population is a fixed
number of chairs, and what changes is which strategy is sitting in each chair.

That is a perfectly respectable model of cultural evolution — it is how ideas
spread. It is also, if you look at it squarely, a little strange as a model of
*life*. The agents are immortal. A losing strategy does not starve; it is
overwritten, from the outside, by a bookkeeping step. Nothing an agent earns is
ever *kept*.

M10 introduces the other paradigm: **birth-death dynamics**. Each agent holds a
stock of **energy**. It earns energy by playing the Prisoner's Dilemma. It pays
energy simply for existing. If its energy runs out, it dies — really dies,
removed from the population. If its energy climbs high enough, it pays some of
that energy to produce a child, which inherits its strategy. Nobody copies
anyone. **Differential survival is the selection.** The population is no longer a
fixed number of chairs: it grows, it shrinks, and it can go extinct.

This is why M10 is described as energy **replacing** imitation rather than
composing with it. In `energy_economy` mode the entire selection-rule family —
Fermi, proportional, tournament-k, truncation, threshold-cloning — and its
intensity parameter β become inert. They are not deleted from the interface; they
are **greyed out with a note explaining why**, because a parameter that silently
does nothing is worse than one that visibly does nothing. There is no selection
rule in an economy. There is only whether you can pay your bills.

There is a second, more strategic reason for this choice. The research programme
this platform is being built toward is **tag-based ethnocentrism** — the
Hammond–Axelrod model (M12). That model is birth-death. Building the economy as a
*replacement* for imitation, rather than as a modification of it, puts M10 on
M12's rails from the start rather than requiring a paradigm change later.

### Persistent creatures have persistent memories

One consequence of the switch is easy to miss, and it is worth naming because it
changes how the strategies behave.

In the imitation paradigm, agents are chairs. The creature in chair 7 next
generation is *not* the creature that was there last generation — it is a fresh
occupant that happens to have copied somebody's strategy. That is exactly why v1
wipes every agent's per-opponent memory at each generation boundary: a remembered
relationship would be a memory of somebody else entirely.

In the economy, that reasoning evaporates. Agent 7 survives **as agent 7**. Its
id is a passport, never reused, and nobody overwrites its strategy. So its
memories persist too. A Grim Trigger agent betrayed at generation 3 is still
refusing to cooperate with that specific opponent at generation 200. Direct
reciprocity stops being a within-generation phenomenon and becomes a **lifetime**
one.

This is not a new invention. It is exactly what pdsim's tournament mode has
always done, where a fixed cast accumulates grudges across cycles and a grim
agent's long memory is documented as the intended behaviour rather than an
accident. The economy simply earns the same treatment, by making its agents
genuinely persistent for the first time in evolution mode.

It has a price, and it is better to know about it before you hit it. The engine
hands each strategy a **copy** of its visible history with an opponent, once per
round. When histories were wiped every generation, that copy was bounded by the
match length — 50 moves, say. Now it grows with the whole relationship. Under
round-robin, where every pair meets every single generation, a history reaches
`rounds_per_match × generations` moves, and copying all of it every round makes
the total work grow with the **square** of the run length. Under `random_k` the
same two agents rarely meet twice, so histories stay short and the problem barely
appears — another quiet point in that matcher's favour.

The `memory_depth` parameter is the bound: cap how far back a strategy is allowed
to see, and the copying cost is capped with it. The calibration readout tells you
when you are running unbounded, rather than refusing to let you.

### What "the generation stays the unit of time" means

M10 comes in two parts, and it is worth being clear about the split. **M10a**
— what this milestone actually builds — keeps the existing generational clock.
Every agent still plays its matches; then, at the **boundary** between one
generation and the next, all the energy bookkeeping happens at once: everyone's
energy is updated against one frozen snapshot, then deaths are applied, then
births. Population size is constant *within* a generation and changes only *at*
the boundary.

**M10b** — deferred to its own milestone — dissolves the generation entirely in
favour of an asynchronous, event-based clock in the style of the Moran process,
where one birth and one death happen at a time. That is the genuinely
invariant-dissolving change, and it is quarantined so it can be designed against
a working variable-population engine rather than at the same time as one.

---

## 2. Why cooperation becomes thermodynamic

Here is the observation the whole milestone rests on. Look at the standard
Prisoner's Dilemma payoffs pdsim uses by default:

| | Opponent cooperates | Opponent defects |
|---|---|---|
| **You cooperate** | R = 3 | S = 0 |
| **You defect** | T = 5 | P = 1 |

Now ask a question nobody usually asks of this table: **how much total value does
each outcome create?**

- Both cooperate: 3 + 3 = **6**.
- One defects, one cooperates: 5 + 0 = **5**.
- Both defect: 1 + 1 = **2**.

Mutual cooperation is strongly **positive-sum** — the interaction creates six
units of value out of nothing. Mutual defection is nearly **zero-sum**: two
agents interact and almost nothing is produced. A defector is not just taking a
larger slice. A population of defectors is baking a much smaller cake.

In the imitation paradigm this is invisible, because scores are only ever
compared *relative to each other*. If everyone earns very little, the Fermi rule
still faithfully picks the least-bad performer, and the population sails on. The
absolute size of the pie has no consequence whatsoever.

Give agents a **metabolic bill** — a fixed amount of energy they must pay each
generation simply to exist — and the absolute size of the pie suddenly matters
enormously.

### The worked filter

Take four agents playing round-robin (every pair plays once), one round per
match. Each agent plays 3 matches.

- **All cooperators**: every match is C-vs-C, so every match pays 3. Income =
  3 × 3 = **9 per agent per generation**.
- **All defectors**: every match is D-vs-D, so every match pays 1. Income =
  3 × 1 = **3 per agent per generation**.

Now set the living cost to L = 4 and watch what happens:

- A cooperator nets 9 − 4 = **+5** per generation. It accumulates, crosses the
  reproduction threshold, and breeds.
- A defector nets 3 − 4 = **−1** per generation. Starting from an energy of 5:
  5 → 4 → 3 → 2 → 1 → 0 → dead.

**Anywhere between 3 and 9, the same cost that cooperators shrug off drives
defectors extinct.** Not because defection loses the game — it doesn't — but
because a world of defectors does not produce enough to pay its own upkeep. This
is Garrett Hardin's **tragedy of the commons** (1968) made thermodynamically
literal: the defectors win the game and lose the world.

### The honest caveat, stated up front

**This does not repeal the Prisoner's Dilemma.** It is important not to oversell
what just happened, and the arithmetic above quietly assumed something enormous:
that the population is *uniform*.

In a **mixed** population, a defector meeting a cooperator collects T = 5 while
the cooperator collects S = 0. The defector still out-earns its neighbour,
locally, in every direct encounter. Defection can still invade a population of
cooperators, exactly as it always could. Nothing about adding an energy stock
changes the payoff table or the strategic logic sitting on top of it.

What the economy adds is a **second, ecological layer beneath the game**. As
defectors displace cooperators, the total energy produced per agent slides from
about 9 toward about 3, and the same fixed bill that was comfortable at 9 becomes
lethal at 3. The population that defection wins is a population that cannot feed
itself.

Whether that actually *rescues* cooperation is a genuinely open question, and the
answer is: **not by itself**. It depends on **structure** — on cooperators being
able to find each other and cluster, so that a pocket of high energy production
can exist and grow faster than the defector regions eating into it. Structure is
M11 (population structure and local reproduction) and M12 (tags). **M10's job is
to build the ledger those experiments will be run on**, not to settle the
question.

---

## 3. The ledger: an open flow, not a conserved quantity

A natural first instinct when designing an economy is to conserve energy — a
fixed pool that circulates. That instinct is wrong here, and it is worth
understanding why.

A **closed** economy can do exactly two things: stall, or go extinct. Energy
sloshes between agents, or it drains away, and the system has no capacity to grow
in response to good behaviour. But growth in response to good behaviour is the
entire phenomenon we want to study. So M10's economy is an **open flow with named
sources and sinks**. Every unit of energy has a documented origin and a
documented destination.

**Sources — energy enters the system:**

- **Payoffs.** Energy earned by playing. This is the scientific heart of the
  design: because mutual cooperation is positive-sum (6) and mutual defection is
  nearly zero-sum (2), cooperation literally *creates more energy per
  interaction*. This is the tap that behaviour controls.
- **Capital return.** A return proportional to the balance an agent carries into
  the generation. **Default 0**, and deliberately behaviour-**independent** —
  more on why that matters in §5.

**Sinks — energy leaves the system:**

- **Basic living cost** — the flat metabolic bill.
- **Engagement cost** — the per-match cost of doing business. Default 0.
- **Reproduction overhead** — an optional extra the parent pays *beyond* the
  child's stake. Default 0.
- **Estate destruction on death** — when an agent dies, whatever energy it was
  holding is **destroyed**. This is not an oversight. It is the 100%
  inheritance-tax corner of a dial M15 will open, taken deliberately as a *named
  position*.

**Transfers — energy moves between agents, conserved:**

- **The offspring stake** — energy the parent hands to the child. Nothing is
  created or destroyed; it changes owner.

That estate-destruction sink has a consequence worth pausing on, because it is
doing real work. When a wealthy agent dies of old age, its entire positive
balance **vanishes from the system**. This puts a hard ceiling on accumulation:
an agent can compound its wealth for at most one lifespan's worth of generations,
and then everything resets. This is `max_age` doing its job against runaway
accumulation, and we will meet the problem it solves in §5.

---

## 4. Calibration: the window, and why a cost has no meaning on its own

Here is the single most important practical fact about running an economy
experiment, and the reason M10a ships a **calibration readout** in the app rather
than leaving you to guess:

> **A living-cost number is meaningless on its own.**

"Basic living cost = 200" tells you nothing. It only means something *relative to
income* — and income depends on the payoff matrix, on how many rounds each match
runs, and on how many matches each agent plays. Change any of those and the same
cost number means something completely different.

### The window

There are exactly two reference points that matter, and both are computable
straight from the config before you run anything:

- **all-D income** — what an agent earns per generation in a population where
  everyone defects. Every round pays P.
- **all-C income** — what an agent earns per generation in a population where
  everyone cooperates. Every round pays R.

The interesting regime — the one where the metabolic filter is switched on — is:

> **all-D income ≤ L < all-C income**

Set L **below** the window and even defectors can pay their bills; the filter is
off and everything grows. Set L **above** the window and even a world of perfect
cooperators cannot pay its bills; everything dies. **Only inside the window does
behaviour decide survival.** The calibration readout draws this bracket for you
and tells you whether your L is inside it.

### Working it out, in full

Take the settings of the `the_growth_economy` scenario: `random_k` matching with
k = 5, and 10 rounds per match.

**Step 1 — how many matches does an agent play?** Under `random_k`, each agent
*initiates* k = 5 matches. But it is also *drawn* by other agents. Each of the
other N − 1 agents picks 5 opponents out of N − 1 candidates, so the chance any
one of them picks you is 5/(N − 1), and there are N − 1 of them:

> expected times drawn = (N − 1) × 5/(N − 1) = **5**

So expected matches per agent = 5 initiated + 5 drawn = **2k = 10**.

Notice what just happened: **the N cancelled.** Under `random_k` an agent's
interaction budget is ≈ 2k *regardless of population size*.

**Step 2 — how many rounds?** 10 matches × 10 rounds = **100 rounds per agent per
generation**.

**Step 3 — the two incomes.**

- all-C income = 100 rounds × R = 100 × 3 = **300**
- all-D income = 100 rounds × P = 100 × 1 = **100**

**Step 4 — the window is `100 ≤ L < 300`.** Take the midpoint: **L = 200**.

**Step 5 — the verdict.** A cooperator nets 300 − 200 = **+100** per generation.
A defector nets 100 − 200 = **−100** per generation. Pleasingly symmetric, and
exactly what the readout will tell you.

One caution about arithmetic like this: a mean-field trace tells you when the
*average* agent dies, not when the *population* does. Under `random_k` an
agent's actual match count wobbles around 2k — some agents get drawn into more
matches than others — so real incomes are spread around the 100-per-generation
average, and a "synchronized" collapse smears out over two or three
generations. It bites hardest exactly where the mean trajectory passes through
zero: an all-defector population starting at 400 sits at *precisely* 0.0 energy
at the fourth boundary, so at that boundary participation luck alone decides
who lives — with the default seed, 19 of 40 die there, most of the rest at the
next boundary, and one straggler hangs on to generation 6. The window is doing
its job on schedule; the schedule just belongs to the average, not to any
individual.

### Self-decalibration, and why `random_k` is the economy's natural matcher

Now run the same exercise under **round-robin**, where every pair plays exactly
once. Each agent plays N − 1 matches. Income therefore **scales with N**.

That is a serious problem in a growth economy, and it is worth seeing why. The
population *grows by design*. As N rises, every agent plays more matches and
earns more, so all-C and all-D income both climb — **the window moves**. A cost
you carefully placed at the midpoint at N = 40 is sitting near the bottom of the
window at N = 200, and the filter you tuned has quietly switched itself off. The
model decalibrates itself, without you touching a thing, purely because it did
the thing you built it to do.

Under `random_k`, the interaction budget is bounded at ≈ 2k independent of N, so
the window **stays put** while the population grows. **This is why `random_k` is
the economy's natural matcher**, and it is the setting the default economy
scenario ships with.

There is a nice convergence here: the performance evidence reaches the same
conclusion by a completely different route. Round-robin plays N(N−1)/2 matches
per generation — quadratic in N — while `random_k` plays N·k, which is linear.
Measured on this project's own benchmark, at N = 1000 round-robin costs about 180
seconds per generation against `random_k`'s 1.8. The wall was never the engine;
it was round-robin's N².

### Escape velocity, the three-knob scale story

Two more readouts you will meet:

**Escape velocity** appears whenever `capital_return_rate` (call it r) is above
zero. It is the balance at which your returns alone cover your bills:

> e* = total cost / r

Above e*, an agent is self-sustaining **regardless of its behaviour**. It pays
its living cost out of returns on capital, stays above the reproduction
threshold forever, and breeds forever. It is **immune to the metabolic filter the
entire experiment rests on**. This is not a bug — it is a real economic
phenomenon, deliberately modelled — but it needs to be visible, so the readout
surfaces it whenever r > 0.

**The scale story is three multiplicative knobs**: N, k, and rounds. The measured
cost model is roughly `seconds/generation ≈ 7.5 µs × N × k × rounds`, and it holds
within about 4% across a 20-fold change in N. Two of those three knobs — k and
rounds — are **scientific choices**, not just performance dials: k sets how
connected the world is, and rounds sets how much room reciprocity has to operate.
You cannot turn them down for speed without changing the biology.

---

## 5. Every parameter: what it models, and what it can't

### θ — `reproduction_threshold`: the capital bar

The energy an agent must hold before it is *allowed* to reproduce. This is a
**capital requirement**: you cannot start a family until you have accumulated
enough to be worth something. Raising θ makes the economy harder to enter and
slows growth; lowering it lets agents breed almost as soon as they earn.

### σ — `offspring_stake`: the inheritance dial

The energy the parent hands to the child. The child starts life holding exactly
σ; the parent's balance drops by exactly σ. **Constraint: σ ≤ θ**, which
guarantees a parent survives its own reproduction — it cannot spend itself to
death making a child.

σ is the **inheritance dial**, and its two corners are worth naming:

- **σ → θ**: a child is born already at (or near) the bar. Dynasties. The child
  breeds almost immediately; wealth compounds through the lineage.
- **σ = 0**: children are born with nothing and must earn their way from scratch.
  Every generation starts equal.

σ also sets the **breeding rhythm**, in a way that is easy to miss. After
reproducing, a parent must re-earn σ before it can breed again. So:

> steady-state breeding interval = σ / (net income per generation)

In the default scenario, σ = 400 and a cooperator nets +100, so a cooperator
breeds **every 4 generations**. Note that θ does *not* appear in that formula —
θ only sets the initial ramp; σ sets the rhythm forever after.

`initial_energy` defaults to σ, so founders start life **exactly like newborns**.
That is one fewer free number to reason about.

### One birth per agent per generation

Even if an agent is holding 5θ, it produces **one** child per generation. This
matches Hammond–Axelrod (one reproduction chance per agent per period) and bounds
the birth phase.

The consequence is worth stating because it is a real modelling commitment: **the
dynastic channel runs through breeding *frequency*, not offspring endowment.** σ
is fixed, so a rich parent's children are born no richer than a poor parent's —
there are just more of them, more often. Turning on real inheritance (M15) is
what would change that.

### The flat/engagement split — the marginality dial

Two cost components, each meaning exactly one thing, combined additively:

- **`basic_living_cost`** — flat, per agent, per generation. The cost of
  *existing*. Paid even if you interact with nobody.
- **`engagement_cost`** — per **match** played. The cost of *doing business*.
  Default 0.

> energy change = − basic_living_cost − engagement_cost × matches_played

Set `engagement_cost` to 0 and you have a pure **existence** model. Set
`basic_living_cost` to 0 and you have a pure **transaction** model. Both are
corners of one design.

**Why per-match and not per-round?** Because a per-round cost would couple the
cost to `rounds_per_match` and to the continuation probability w — which would
make match-length knobs *silently economic*. Turn up the rounds to give
reciprocity more room and you would have quietly raised everyone's bills,
confounding the experiment. Under continuation mode it would be worse: match
length is random, so the cost would inherit that randomness. Per-match keeps the
cost orthogonal to the match-length knobs.

**Why two components rather than one ratio?** Because together they form a
continuous **marginality dial**. Under `random_k`, participation varies — some
agents get drawn a lot, some barely at all. A flat cost makes being
under-connected a **survival threat** (you pay whether or not anyone plays with
you). A per-match cost makes it **survival-neutral** (no matches, no bill). The
mix between them sets how harshly the world treats the poorly-connected — which
is exactly the dial that will govern whether **immigrants**, or a small community
entering an established population, face a brutal survival gradient or a soft
landing. That is a scientific question, and it deserves two independent knobs.

*(A ratio coupling the two was considered and rejected: the units don't work.
`basic_living_cost` is energy per generation, `engagement_cost` is energy per
match, and converting between them needs a match count — but N changes every
generation by design, so any fixed ratio either silently re-tunes itself as the
population grows or is a fiction after generation 1.)*

### `capital_return_rate` — wealth without behaviour

A multiplicative return on the balance an agent carries **into** the generation:

> e ← e_carried_in × (1 + r) + payoffs − costs

**Default 0.** This is the one place M10 deliberately couples **wealth to
earning** — everywhere else, what you earn depends only on how you play. It is
added in the open, switched off by default, because it is a real economic
mechanism worth being able to study, not because the model needs it.

Two things follow, and both are named honestly rather than buried:

**It cannot compound a debt.** Because death at `e < 0` is applied every single
generation, every living agent enters every generation with e ≥ 0. There is no
negative balance for interest to act on.

**It creates the rentier.** Above escape velocity e* = costs / r, an agent never
has to play well again. And combined with the at-capacity admission rule below,
it produces something stronger, which the design names as a **mechanism** rather
than a footnote: **structurally permanent dynasty**. Admission at capacity is
highest-energy-first; capital return makes the rich richer; so the rich are
admitted first, forever. `max_age` is the only thing that breaks it — a dead
rentier's estate is destroyed.

### K — `carrying_capacity` — and the admission rule

A hard cap on population size. When the population is at capacity, births compete
for the available slots, and admission is **highest-parent-energy-first, ties
broken by agent id**. This is deterministic and **RNG-free** — a deliberate
choice over a random lottery, which would inject fresh randomness into the birth
phase for no scientific gain.

**K's scope is aspatial-specific, not universal — and this matters.** In a
lattice model there is no capacity parameter at all: capacity is *implicit*,
because a site holds one agent and an offspring can only be born if an adjacent
site is empty. K is the well-mixed model **paying cash for something a lattice
provides for free**. Under M11, capacity may dissolve into emergent site-counting.

And K is **not a safety rail**. §7 explains why it is the single most
scientifically load-bearing knob in the milestone.

### The mortality trio

> p(age) = base_hazard × senescence_factor ^ age

clamped to 1.0, and forced to 1.0 at `max_age`.

- **`base_hazard`** — the death probability of a newborn; the flat,
  age-independent risk. Default 0.
- **`senescence_factor`** — the factor by which each additional generation of age
  multiplies your risk. Default **auto** (see §7).
- **`max_age`** — a hard cap where p = 1.0. Default 0, meaning no cap.

Three corners are recoverable, and each is a recognisable model in its own right:

- `senescence_factor = 1.0` → a **flat, constant death chance** at every age.
  This is literally Hammond–Axelrod's assumption.
- `base_hazard = 0, senescence_factor = 1.0, max_age = 20` → **deterministic
  death at 20**; only insolvency kills you earlier.
- All neutral → the **immortal-unless-insolvent** economy. This is the M10
  default: out of the box, the only thing that kills you is running out of money.

**Founder age staggering** happens automatically, with no parameter, whenever
age-mortality is active: founders are seeded with uniform staggered ages across
0…max_age−1. Without it, the entire founding cohort would hit `max_age` on the
same generation and die simultaneously — a colony-ship moment. A fixed-lifespan
population at a steady birth rate has a uniform age distribution in equilibrium,
so staggering simply starts the run where it would have settled anyway.

### What the economy deliberately does NOT model

**Wealth does not buy an advantage in a match.** A rich agent and a poor agent
playing the same strategy get identical payoffs. This is a deliberate
non-feature: it keeps the payoff matrix the *only* thing that determines what an
interaction produces, so the energy layer stays cleanly beneath the game rather
than tangled into it. `capital_return_rate` is the single, deliberate exception —
and that is exactly why it is off by default and why escape velocity is surfaced
whenever it is on.

---

## 6. Designed for, not built

These are the things M10a deliberately makes *reachable* without building them.
Naming them is how we make sure today's decisions don't foreclose them.

- **Taxation and redistribution (M15).** The ledger's shape — named sources,
  sinks, and transfers — is exactly what a fiscal policy needs. A tax is a sink;
  redistribution is a transfer. M10a ships neither, but it ships the vocabulary.
- **Inheritance (M15).** M10a ships the **100% inheritance-tax corner**: the
  estate is destroyed. M15 opens the dial, riding the `parent_id` lineage M10a
  lays down. Ids are **passports** — never reused, monotonically issued, each
  agent recording its parent — so lineage is real and per-agent charts are
  honest. (Reusing ids would mean "hotel-room splicing": stitching together the
  histories of unrelated creatures who happened to occupy the same slot.)
- **Immigration (M15).** Exogenous arrivals. M10a makes this a one-line
  operation, because a population that can already grow and shrink has nothing
  left to learn about a newcomer appearing. The **marginality dial** (§5) is
  already the knob that decides whether immigrants face a hard survival gradient
  or a soft landing.
- **Proselytizing religion**, via two distinct channels. The **demographic**
  channel — differential fertility between groups — is reachable with M10 + M12
  in the near term. The **conversion** channel is a separate future
  **horizontal-transmission** mechanism. Note the pleasing accident:
  conversion *is* imitation — the very mechanism M10 removed from reproduction —
  so "energy replaces imitation" left clean room for it to return later as its
  own thing.
- **Density-dependent living cost.** Living cost rising as N approaches K — a
  *soft* logistic capacity instead of M10a's hard cap. Designed for, not built.

---

## 7. Where this milestone's ideas come from

M10 does not invent the idea of giving simulated creatures an energy budget and
letting the budget decide who lives. That idea has a canonical ancestor, and the
growth economy is best understood as a deliberate recombination of two well-known
models that were built for different purposes.

### Sugarscape is where the energy comes from

**Sugarscape** (Epstein & Axtell, 1996) places agents on a grid strewn with
"sugar," a resource that regrows over time. Each agent is born with a
**metabolism** — a fixed amount of sugar it burns every turn simply for being
alive — and a store of sugar it has gathered. The rule that makes the whole thing
go is brutally simple: when an agent's store runs out, it is removed from the
simulation. It also dies on reaching its individually-assigned maximum age.

Both death channels, insolvency and old age, appear in M10 unchanged in spirit:
our `basic_living_cost` is Sugarscape's metabolism, our death-at-`e < 0` is its
death-at-zero-sugar, and our `max_age` is its maximum age.

Two further Sugarscape rules matter for where M10 is heading. Its **inheritance
rule** says that when an agent dies, its wealth is divided equally among its
living children. M10a deliberately ships the **opposite corner** — the estate is
destroyed, a 100% inheritance tax — and M15 is where the rest of that dial gets
built. Its **credit rule** lets agents lend sugar at an interest rate for a fixed
term, which is the nearest ancestor of our `capital_return_rate`, though ours is
simpler: a return on your own balance rather than a loan between two agents.

One thing Sugarscape does **not** have is a tax system, and this explainer will
not claim otherwise. Redistribution is genuinely new territory for M15.

There is also a **methodological debt** worth naming. Joseph Kehoe's formal
specification of Sugarscape (2016) exists because the original rules were
ambiguous enough that different implementations disagreed with each other. Kehoe
found, for instance, that the book never states exactly *when* in a turn the
metabolic cost is deducted — it could sit in the movement rule or anywhere else
applied every turn, and the choice is invisible in the prose but changes results.
This is precisely the failure mode pdsim's frozen per-generation RNG draw order
(DECISIONS #32, extended by M10a) is designed to prevent. When we insist that
mortality coins are drawn in ascending agent-id order, before insolvency, before
births, we are not being fussy. **We are refusing to be Sugarscape.**

### Hammond & Axelrod is where the birth-death dynamics come from — but NOT the energy

This is worth being precise about, because it is easy to get backwards.

In the **Hammond–Axelrod** model (2006), each agent has a **potential to
reproduce** (PTR). At the start of every period, every agent's PTR is **reset to
a base value of 12%**. Agents then play one-move Prisoner's Dilemmas with their
four lattice neighbours; giving help costs 1 percentage point of your own PTR,
receiving help adds 3. Then each agent, in random order, gets one chance to
reproduce with probability equal to its PTR, cloning a child into an adjacent
empty site if one exists. Finally every agent faces a flat 10% chance of dying.

Notice what PTR is: **a flow, not a stock.** It is wiped clean every period. An
H-A agent **cannot get rich**. It cannot save. Its history buys it nothing beyond
the current period. An agent showered with donations for 50 periods enters period
51 at exactly 0.12 — identical to a newborn.

That is a deliberate simplification on their part, and it is exactly the thing
M10 changes. **Our energy persists**, which is what makes θ (a capital bar), σ (an
inheritance dial), and `capital_return_rate` (compounding) even *expressible*.
None of them has an H-A counterpart. So the honest summary is:

> **H-A gives M10 its skeleton** — birth-death instead of imitation, one birth per
> agent per period, a flat death chance, offspring that need somewhere to go —
> **and Sugarscape gives M10 its bloodstream.**

Three M10 design choices are nonetheless directly grounded in H-A. **First**, one
birth per agent per generation even when an agent could afford several: H-A gives
each agent exactly one reproduction chance per period, and we match it.
**Second**, the flat-hazard corner of our mortality model
(`senescence_factor = 1.0`) is literally H-A's constant 10% death chance —
setting that one parameter reproduces their assumption exactly. **Third**,
carrying capacity is a stand-in for space. In H-A there is no capacity parameter
at all; capacity is implicit, because a lattice site holds one agent and an
offspring is only born if an adjacent site is empty. Sugarscape works the same
way. Our `carrying_capacity` is the well-mixed model paying cash for something a
lattice provides for free — which is why K is scoped as aspatial-specific and may
dissolve into emergent site-counting under M11.

**One deviation, named honestly.** H-A's period order is immigration →
interaction → reproduction → death: **birth before death**. M10a freezes **death
before birth** — the cull frees room, then survivors breed into it, an
at-capacity Moran-like regime. In a steady cycle the difference largely rotates
out, but two real differences remain: in H-A a newborn can die in the period it
was born, and the first period differs. M10a's choice is a plain design
preference, not a claim about spatial correctness.

### Why local reproduction is M11's job and not M12's

It is tempting to think that **tags** alone — telling agents apart by an
arbitrary marker and letting them condition behaviour on it — would reproduce
H-A's headline result, in which about 76% of agents end up ethnocentric. They
would not, and the reason is worth understanding because it shapes our whole
milestone order.

H-A's mechanism is **regional**. Agents of the same colour cluster because
children are born next to their parents, so a neighbourhood tends to share a tag.
An ethnocentric agent inside such a cluster receives **help from behind** — from
the same-coloured neighbours on its interior side — while an egoist of a
different colour on the far side of the boundary receives nothing from its own
kind, because egoists do not help each other either. So the ethnocentric region
**out-breeds** the egoist region at the border and expands into it.

Strip away the lattice and that story has no referents: no regions, no borders, no
interior, no correlation between an agent's tag and its neighbour's. Hammond and
Axelrod's own robustness checks halve and double nearly every parameter — cost,
number of colours, mutation, immigration, lattice size, run length — and
ethnocentrism survives all of it. **They never test removing the lattice. It is
not a parameter. It is the stage.**

Later work pulled the two ingredients apart and found something more interesting
than "space matters." Kaznatcheev and Shultz (2011) titled their result
precisely: *ethnocentrism maintains cooperation, but keeping one's children close
fuels it*. The two mechanisms operate at **different times in the same run**. For
roughly the first 300 periods — while the lattice is still filling up — local
child placement **with no tags at all** performs about as well as the full model.
Tags contribute almost nothing. Then the world **saturates**, expanding clusters
of cooperators collide with clusters of egoists, and only at that point do tags
become critical — because only then is there a border to defend.

So the causal order is: **viscosity creates cooperation; tags preserve it once
space runs out.** This is why pdsim builds population structure (M11) before tags
(M12). Tags built first would be maintenance machinery with nothing yet to
maintain.

There is a genuinely nice convergence here worth saying out loud. The milestone
renumbering put structure before tags on purely *organisational* grounds (a
read-only view should be built after the thing it views). The *science* says the
same thing for an entirely different reason. When two independent arguments land
on the same order, that order is probably right.

### K is a regime switch, not a safety rail

That last finding tells us something important about M10 itself. "The world
saturates and the dynamic changes" is, in our vocabulary, **the population hits
K**.

Carrying capacity is therefore **not a safety rail to stop runaway growth**. It
is **the switch that flips the system from a growth regime into a competition
regime**, and the at-capacity admission rule decides who wins that competition.
That is why M10a takes admission seriously enough to isolate it in its own
function, and why the combination of `capital_return_rate` with
highest-energy-first admission is named as a **mechanism** (structurally permanent
dynasty) rather than buried as a footnote.

### Gompertz is where the ageing curve comes from

Benjamin Gompertz (1825) was a working actuary trying to price annuities, and his
contribution was to notice that the mass of mortality data collapses into a
strikingly simple form: **the death rate at age x rises roughly exponentially with
age**. Write it as μ(x) = α·e^(βx) and you have the Gompertz law.

M10's mortality is exactly this in discrete form:

> p(age) = base_hazard × senescence_factor ^ age

where `base_hazard` plays α (the risk facing a newborn) and `senescence_factor`
plays e^β (the factor by which each additional year multiplies your risk).

**Work the arithmetic to see what the auto default does.** Suppose
`base_hazard` = 0.01 — a newborn has a 1% chance of dying each generation — and
`max_age` = 20. The auto rule sets:

> senescence_factor = (1 / 0.01)^(1/20) = 100^0.05 ≈ **1.2589**

So risk climbs 25.89% per year of age:

- at age 0: 0.01 = **1%**
- at age 10: 0.01 × 1.2589¹⁰ ≈ **10%**
- at age 20: 0.01 × 1.2589²⁰ = 0.01 × 100 = **exactly 1.0**

The stochastic curve arrives at certainty **precisely where the hard cap sits**,
instead of the cap chopping off a curve that was still saying "you have a 40%
chance of seeing next year." That agreement is the whole point of the derived
default.

**The honest caveat**, which Gompertz's modern commentators (Kirkwood, 2015) are
direct about: the idea that this constitutes a *universal law* of mortality has
given way to recognising that other patterns exist — across species, and notably
in advanced old age, where real death rates tend to **plateau** rather than
continue climbing. Our model has no plateau. `max_age` is a guillotine, not a
biology. This is a modelling convenience and we should say so.

### Nowak tells us which question M10 is asking

Nowak's survey (2006) identifies **five mechanisms** by which cooperation can
evolve despite natural selection opposing it: kin selection, direct reciprocity,
indirect reciprocity, network reciprocity, and group selection. It is a useful map
for locating pdsim:

- **v1's iterated Prisoner's Dilemma with memory is squarely direct
  reciprocity** — Tit-for-Tat works because you meet the same opponent again.
- **H-A deliberately abandons that** by using a one-move game: there is no repeat
  encounter, so reciprocity is off the table by construction, and cooperation must
  be rescued by something else.
- **M11's lattice is network reciprocity.**
- **M12's tags are a form of kin recognition without kinship**, adjacent to kin
  selection.

**M10 itself is not on this map, and that is the point worth making to a
newcomer.** The growth economy is **not a sixth mechanism** for rescuing
cooperation. It does not repeal the Prisoner's Dilemma: in a mixed population, a
defector meeting a cooperator still collects 5 while the cooperator collects 0, so
defectors still out-earn locally and can still invade. What the economy adds is an
**ecological layer beneath the game** — as defectors displace cooperators, total
energy production per agent collapses from about 9 toward about 3, so the same
metabolic bill that cooperators shrug off starts killing defectors. It is Hardin's
tragedy of the commons made thermodynamically literal: **the defectors win the
game and lose the world.**

Whether that actually rescues cooperation depends on structure — and structure is
M11 and M12, not M10. **M10's job is to build the ledger those experiments will be
run on.**

---

## References

Epstein, J. M., & Axtell, R. L. (1996). *Growing Artificial Societies: Social
Science from the Bottom Up.* Brookings Institution Press / MIT Press.
ISBN 0-262-55025-3.

Gompertz, B. (1825). On the nature of the function expressive of the law of human
mortality, and on a new mode of determining the value of life contingencies.
*Philosophical Transactions of the Royal Society of London*, 115, 513–583.
DOI: 10.1098/rstl.1825.0026.

Hammond, R. A., & Axelrod, R. (2006). The evolution of ethnocentrism. *Journal of
Conflict Resolution*, 50(6), 926–936. DOI: 10.1177/0022002706293470.

Hammond, R. A., & Axelrod, R. (2006). Evolution of contingent altruism when
cooperation is expensive. *Theoretical Population Biology*, 69(3), 333–338.

Hardin, G. (1968). The tragedy of the commons. *Science*, 162, 1243–1248.

Kaznatcheev, A., & Shultz, T. R. (2011). Ethnocentrism maintains cooperation, but
keeping one's children close fuels it. *Proceedings of the 33rd Annual Conference
of the Cognitive Science Society*, 3174–3179.

Kehoe, J. (2016). *The Specification of Sugarscape.* arXiv:1505.06012v3 [cs.MA].

Kirkwood, T. B. L. (2015). Deciphering death: a commentary on Gompertz (1825).
*Philosophical Transactions of the Royal Society B*, 370(1666), 20140379.

Nowak, M. A. (2006). Five rules for the evolution of cooperation. *Science*,
314(5805), 1560–1563. DOI: 10.1126/science.1133755.

Nowak, M. A., & May, R. M. (1992). Evolutionary games and spatial chaos.
*Nature*, 359, 826–829.

Riolo, R. L., Cohen, M. D., & Axelrod, R. (2001). Evolution of cooperation
without reciprocity. *Nature*, 414, 441–443.

Shultz, T. R., Hartshorn, M., & Kaznatcheev, A. (2009). Why is ethnocentrism more
common than humanitarianism? *Proceedings of the 31st Annual Conference of the
Cognitive Science Society*, 2100–2105.

*Note on provenance: Riolo et al., Hardin, and Nowak & May are verified via the
reference lists of the peer-reviewed papers fetched during the M10 literature
pass (Hammond & Axelrod 2006 and Nowak 2006 cite them with full volume and page),
rather than independently by DOI. Moran (1958) is deliberately absent — it belongs
to M10b's explainer. The Verhulst / Pearl & Reed logistic tradition
(density-dependent living cost) and Greenwood's natal-dispersal work (M11's birth
radius) are likewise deferred to the milestones that build them.*
