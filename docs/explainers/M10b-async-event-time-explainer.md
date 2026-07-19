# M10b — Asynchronous time: the Moran-style event-time model

*A companion explainer. It stands on its own: a reader who is comfortable with a
little arithmetic but who has never opened the M10a explainer should be able to
follow it from a cold start. The spec (`docs/specs/M10b-async-event-time-spec.md`)
records the frozen build intent; this document explains what the milestone does,
why the design choices are what they are, and where the underlying science comes
from.*

---

## 1. What changes when you delete the generation

The whole platform simulates a population of agents playing the **Prisoner's
Dilemma** with each other, over and over, and then *evolving*: strategies that do
well become more common, strategies that do badly fade out. A strategy is just a
rule for deciding, on each encounter, whether to **cooperate** (pay a small cost
to give your partner a larger benefit) or **defect** (pay nothing, give nothing).
The dilemma's sting is that defection is individually tempting on any single
encounter, yet a population of defectors does worse than a population of
cooperators — so the interesting question is always: *under what conditions can
cooperation survive and spread?*

Every earlier milestone answered that question on a **synchronous clock**. Time
advanced in **generations**. A generation was one atomic tick with a fixed
sequence: everybody plays their matches, then — in a single frozen instant — every
agent's fate is settled together. Scores are tallied, the unfit are removed, the
fit reproduce, ages tick up. The population steps forward as one cohort, like a
marching band taking a step in unison. Because everything happens at one instant,
you can freeze the whole population, look at it all at once, and make global
decisions ("of everyone alive, these are the top scorers, they reproduce").

**M10b introduces an asynchronous clock, and this is the entire milestone.**
Asynchronous time throws away the frozen instant. There is no generation and no
cohort. Time becomes a *sequence of individual events*: this one agent dies now;
that one is born next; a third copies a neighbour's strategy after that — one at a
time, in a definite order. Nobody steps in unison. The population is more like a
city than a marching band: births, deaths, and conversions happen continuously and
singly, never all at once.

That sounds like a small bookkeeping change. It is not. It reaches into a decision
that the synchronous model never had to make explicit — *at what moment, and by
what rule, is each individual birth evaluated?* — and that question turns out to
collide with a change a **later** milestone (M11, which adds spatial structure)
will make. Most of this document is about that collision and how the design
sidesteps it. But first, the science the async clock is built on.

### A worked contrast: the boundary sort versus the event stream

Suppose the population can hold at most `K = 4` agents, and at some point two of
them run out of resources and die.

**Synchronously**, that is easy to resolve. At the boundary you stop the world.
Two slots are now open (`slots = K − survivors = 4 − 2 = 2`). You look at *everyone
eligible to reproduce* — say four agents with fitness values `{50, 40, 30, 20}` —
sort them, and admit the top two (fitness 50 and 40). The word "global" is doing
real work here: because there is one frozen instant and a known slot count, ranking
the *whole* population at once is natural and cheap.

**Asynchronously**, there is no frozen instant to sort against. Events arrive one
at a time. First: *agent X dies*, and a single slot opens. Immediately you must
answer a question the synchronous model dissolved into its batch: **who fills this
one slot, right now?** There is no batch of two to hand out; there is one opening,
and one decision. The rest of the population has not been frozen and sorted — the
next event has not even happened yet. This single-slot, single-moment decision is
the atom of asynchronous time, and everything below is about how to make it well.

---

## 2. The Moran process: one birth, one death, forever

The canonical way to run evolution one event at a time is more than sixty years
old. In 1958 the statistician P. A. P. Moran described a population model in which,
as he put it, births occur in succession and *each birth entails the death of one
parent*. That coupling is the heart of what we now call the **Moran process**:

> Repeat forever: pick one individual to **reproduce**, and one individual to
> **die**. The newborn takes the dead one's place. Population size never changes.

Because exactly one birth is paired with exactly one death at every step, the
population is pinned at a constant size `N`. This is the purest possible "event
time" — the population never grows or shrinks, it only *turns over*, one
replacement at a time, and evolution is the slow drift of the population's
composition as fitter types are picked to reproduce slightly more often.

### Time measured in events, not rounds

If a generation no longer exists, what goes on the horizontal axis of a chart? The
raw unit of async time is *one event* (one replacement). But one event is a tiny
amount of change compared to a synchronous generation. In a population of `N = 50`,
a single synchronous generation involves roughly all fifty agents living, playing,
and being judged. A single Moran event replaces *one* agent — about 1/50th of that
much turnover.

So to keep synchronous and asynchronous runs comparable, we measure async time in
**generation-equivalents**, using the standard Moran convention: one
generation-equivalent is `N` events, because after about `N` replacements every
agent has, on average, been replaced once — the same amount of turnover as one
synchronous generation. Concretely, each event advances the clock by `1 / N`.

The platform's economy lets `N` change over a run (see §5), so we use the
*instantaneous* population: each event advances the generation-equivalent clock by
`1 / N(t)`, and one generation-equivalent is complete when the running sum of those
`1 / N(t)` increments reaches 1. This is a fixed reporting convention, not a
tunable knob — there is only one scientifically standard mapping, and letting a
user pick a non-standard one would only make their own sync and async runs
incomparable. It changes nothing inside the simulation; it changes only the label
on the x-axis and the way the timeseries reports time.

---

## 3. Update rules: who reproduces, who dies

The bare Moran process says "pick one to reproduce and one to die" but leaves open
*how* you pick. The two classical choices, and a mixture of them, are M10b's first
user-facing toggle — `moran_rule`.

**Death-birth (DB).** First choose an individual to die (in the well-mixed world of
M10b, uniformly at random — each of `N` agents with probability `1/N`). That leaves
an empty slot. Then the survivors compete to reproduce into it, with a chance
**proportional to fitness**: a fitter agent is more likely to win the vacancy.
Death picks the *slot*; fitness picks the *winner*.

**Birth-death (BD).** The other order. First choose an individual to reproduce, with
a chance **proportional to fitness** — the fittest are most likely to breed. Then
the offspring replaces some *randomly chosen* other agent, fitness ignored. Fitness
picks the *breeder*; chance picks the *victim*.

**Random.** A per-event mixture of the two. On each event, before anything else, the
engine flips a weighted coin to decide whether *this* event uses BD or DB, then
proceeds accordingly. The weights are configurable (`moran_random_weights`, default
50/50), so "uniform mix" is just the default and you can dial the blend.

### Why the order is not cosmetic

It is tempting to assume BD and DB are two spellings of the same thing. They are
not — and the difference is exactly the kind of thing this platform exists to
study. On a *structured* population (agents arranged on a graph, interacting only
with neighbours), Ohtsuki, Hauert, Lieberman and Nowak proved in 2006 that the
update rule decides whether cooperation can survive at all:

- Under **death-birth** updating, cooperation is favoured when the benefit-to-cost
  ratio of cooperating exceeds the number of neighbours: `b/c > k`. Structure can
  *rescue* cooperation.
- Under **birth-death** updating, no such rescue exists on a regular graph —
  defection prevails regardless of structure.
- Under **imitation** updating (a close cousin, §4), the threshold shifts to
  `b/c > k + 2`.

Increasing the *fraction* of death-birth events, in later work, monotonically makes
cooperation more likely to evolve, at least when selection is weak. That is why the
default `moran_rule` is **death_birth**: it points the platform at the regime where
cooperation has a fighting chance, which is the whole research programme's target.

One honest caveat, stated up front: that `b/c > k` result *requires the graph*. In
M10b's world there is no graph yet — everyone is everyone else's neighbour
(well-mixed). So in M10b the three rules differ **mechanically** (they really do
pick breeders and victims differently, and reproducible runs will diverge under
each) but the cooperation-promoting *result* does not yet bite. M10b builds the
`moran_rule` machinery; **M11**, which adds the graph, is what makes it
scientifically potent. Sequencing the seam before the payoff is deliberate.

### The fixed-N death rule

The Moran process is a *fixed-N* idea — one birth, one death, size pinned. Within
that, `fixed_n_death_rule` offers two flavours:

- **pure_random** — death is independent of fitness, exactly as in the textbook
  process. This is the setting for reproducing published Moran results.
- **energy_decides** (the default) — the lowest-resource agent dies, while the count
  stays pinned. This imports an economic flavour into the otherwise-textbook model:
  survival still depends on how well you have been doing, but the population size
  does not float.

Both are coherent; the default leans toward the platform's resource-economy framing
(§5), and the tooltip beside the toggle says exactly this.

---

## 4. Imitation is a different animal: the cultural channel

There is a third classical way for strategies to spread, and it is **not** a third
Moran rule — treating it as one was a tempting mistake the design deliberately
avoids. The reason is worth spelling out, because it is a genuine conceptual split,
not a plumbing detail.

Birth-death and death-birth are **demographic**: they change *who exists*. A birth
adds an agent to the world; a death removes one. **Imitation** is **cultural**: it
changes *what an existing agent believes*, while that agent keeps living — same
identity, same resources, same age. Nobody is born, nobody dies; a mind changes.

### A worked contrast: cast-change versus mind-change

Take four agents: A (cooperator), B (defector), C (cooperator), D (defector).

- A **death-birth event**: D is chosen to die; the survivors compete for its slot;
  A wins and a fresh cooperator is born there. The population is now {A, B, C, A′}.
  *One agent died, one was born — the cast changed.*
- An **imitation event**: B and C interact, C (a cooperator) out-earned B, and B
  copies C's strategy. The population is still {A, B, C, D} — the very same four
  agents, same resources, same ages — but B is now a cooperator. *Nobody was born
  or died; a belief changed.*

These are not two ways of doing the same job, and you might well want both happening
in one run — strategies spreading *both* by out-breeding *and* by conversion. A
single "pick one rule" radio button cannot express that; two independent channels
can. So imitation is its own switch, `imitation_overlay` (default off), layered on
top of whichever demographic mode is running. When it is on, imitation fires on a
different **trigger** than births and deaths do: not on a vacancy, but on a
*completed interaction* between two agents — one agent, having played another,
may adopt the other's strategy.

### The Fermi rule, and the temperature of imitation

How likely is the copy? The platform uses the **Fermi rule**, borrowed from
statistical physics by Traulsen, Nowak and Pacheco (2006, 2007) and already used
elsewhere in the engine — so the imitation overlay reuses the existing selection
intensity `β` (`selection_beta`) rather than inventing a new knob. An agent A,
comparing its own fitness `f_A` to a partner B's fitness `f_B`, adopts B's strategy
with probability

    P(A copies B) = 1 / (1 + e^(−β·(f_B − f_A)))

The parameter `β` is an **inverse temperature** — it controls how sharply the copy
depends on the fitness gap:

- At `β = 0` the exponent vanishes and `P = 1/2` no matter who is fitter: pure
  random drift, strategies spread by luck alone.
- As `β` grows, the copy becomes increasingly reliable in the fitter agent's
  favour. Worked example: if `f_A = 3`, `f_B = 5`, and `β = 1`, then
  `P = 1 / (1 + e^(−2)) = 1 / (1 + 0.135) = 0.881` — B's strategy is copied about
  88% of the time. Raise `β` and that climbs toward certainty; lower it toward 0 and
  it falls back to a coin flip.
- In the limit of very large `β` the rule becomes a step function — always copy the
  fitter — which is the "imitation dynamics" extreme in the literature.

Traulsen and colleagues' insight was that this single temperature gives *one*
framework spanning everything from neutral drift (`β = 0`) to deterministic
imitation (`β → ∞`), which is exactly why it is the right mechanism for a knob a
user is meant to sweep.

---

## 5. Variable-N versus fixed-N: the economy meets the Moran clock

So far the population size has either been pinned (Moran) or left vague. The
platform also carries a **resource economy** — worth a brief standalone sketch,
because it is what makes the second async mode interesting.

In the economy, an agent holds a stock of energy. Playing earns energy;
*cooperators generate more energy per interaction than defectors do*. Living costs
energy — a bill is charged over time. An agent that reaches a threshold `θ` can
afford to reproduce (paying a stake to endow its child); an agent whose stock goes
negative is **insolvent** and dies. A carrying capacity `K` caps how many agents the
world can hold. The upshot is that the same living bill a thriving cooperator
shrugs off can drive defectors extinct, and the population size itself becomes an
*outcome you measure* rather than a fixed input.

Crucially, the economy has **already decoupled birth from death**. A death is
triggered by insolvency (or age); a birth is triggered, independently, by an agent
clearing `θ` with a slot free. They no longer arrive as the coupled pair that
defines the Moran process. This is why "birth-death versus death-birth" is
intrinsically a **fixed-N** concept: the crisp BD/DB distinction comes from *one
birth balancing one death*, and once the economy lets births and deaths fire
independently, that coupling — and the distinction that rode on it — is gone.

So M10b's asynchronous clock runs in one of two modes (`async_population`):

- **variable_n** (the default) — the economy's own decoupled, deterministic
  demographic rules run in event-time. Births fire when agents clear `θ`; deaths
  fire on insolvency or age; `N` floats between extinction and `K`. Here
  `moran_rule` and `fixed_n_death_rule` simply do not apply — the economy *is* the
  demographic engine. This carries the M10a resource economy forward into
  continuous time, which is the platform's research through-line.
- **fixed_n** — the textbook Moran process, size pinned, governed by `moran_rule`
  and `fixed_n_death_rule` from §3. This is the clean comparison model, the one that
  reproduces the classical results.

The imitation overlay (§4) is available in **both** modes.

---

## 6. The seam: why a time change collides with a space change

Here is the design tension that shaped the whole milestone, and it is subtle enough
to be worth stating slowly.

M10b is a **time** change. A **later** milestone, M11, is a **space** change: it
puts agents on a lattice, so that a newborn can only be placed in a cell *near* its
parent, and agents interact only with *nearby* neighbours. On its face these two
milestones touch different things — one is about *when*, the other about *where*.

But recall the atom of asynchronous time from §1: when a slot opens, you must decide
*who fills it, at this moment*. That decision — "from what set of candidates, by
what rule, does this one birth get resolved" — is **exactly** the decision M11
exists to rewrite. M11's whole job is to make "who fills this empty site" a **local**
question (only nearby agents are candidates) instead of a **global** one
(rank everyone). So the time milestone and the space milestone, despite their
different badges, reach for the *same lever*: the birth-admission decision.

That creates a fork for how M10b is built.

- **Option A — bake the admission rule into the async loop.** When a birth event
  fires, the event loop itself scans the whole population, ranks by fitness, and
  picks the breeder. Fast to write. But it hard-codes the *global, aspatial*
  assumption — "the candidate set is everyone, the rule is a global sort" — right in
  the middle of the engine's hot loop. When M11 arrives, it must reach *inside* that
  loop, tear the global scan out, replace it with "candidates = the empty site's
  neighbours," and then re-verify the entire event-ordering and reproducibility
  contract from scratch, because it just edited code in the loop's core. Worse, the
  aspatial assumption would then be hard-coded in *two* places (the old synchronous
  boundary *and* the new async loop), so M11 pays to remove it twice.

- **Option B — delegate through a seam (chosen).** The async loop, when a birth
  event fires, calls two small named functions — `admit_births(...)` (who breeds)
  and `place_offspring(...)` (where the child goes) — and stays deliberately
  *ignorant* of what they do. In M10b's aspatial world those functions happen to
  implement "candidate set = whole population, rule = fitness priority, placement =
  anywhere," producing byte-identical numbers to Option A. But the loop never
  encodes that. When M11 arrives, it swaps only the *implementations* of those two
  functions (candidate set becomes neighbours; placement becomes a specific empty
  neighbouring site) and the async loop is never reopened.

The platform chose **Option B**. This is not a choice a researcher ever sees or
flips — both options produce identical science in M10b. It is purely a question of
*where a piece of knowledge lives in the code*, and the answer that keeps M11 cheap
is "behind the seam, not in the loop." The seam was in fact carved earlier,
precisely in anticipation of this moment: the boundary logic already checks whether
a child can be *placed* before it charges the parent the reproduction stake — a
check that does nothing in a well-mixed world (there is always room) but which,
once M11's placement radius is real, prevents a "charged-for-a-child-that-was-never-
born" bug when every nearby cell is occupied.

### A forward note on radius (M11, not M10b)

M11's placement will use a **radius**: `radius = 1` lets a newborn land in any of
the eight cells immediately surrounding its parent (the Moore neighbourhood —
`(2·1+1)² − 1 = 8` cells, counting diagonals as one step); `radius = n` opens up
`(2n+1)² − 1` cells out to Chebyshev distance `n`. A parallel radius governs how far
an agent roams to find interaction partners. The intended form is a **soft
temperature kernel** — reach decays with distance, a temperature parameter sets how
fast, and a hard cutoff is recoverable as the temperature goes to zero — a spatial
cousin of the Fermi `β` above. None of this is built in M10b. It is recorded here
only so that the two seam functions (`place_offspring` and the interaction matcher)
have a documented reason to exist: they are the sockets M11 plugs radius into.

---

## 7. Recording, comparability, and reproducibility

Three practical consequences of moving to event time.

**Explicit birth/death/imitation events.** Because per-event ordering is now
meaningful, asynchronous runs emit explicit typed events — a birth event (with the
newborn's identity, parent, strategy, starting resources), a death event (with its
cause: insolvency, age, replacement, or random-Moran removal), and an imitation
event (who copied whom, from which strategy to which). The synchronous path is
unchanged: it keeps its per-generation summaries and emits none of these, so old
synchronous runs produce byte-identical output.

**Recording cadence is a knob** (unlike the time-mapping convention of §2, which is
fixed). In event time you can record a data point on *every* event — maximum
resolution, but with `N`-times more points per generation-equivalent, larger files,
and the chart-rendering ceiling arriving fast — or you can downsample to one snapshot
per generation-equivalent (comparable to synchronous runs, sane file sizes), or one
every `M` events. This is a genuine resolution-versus-cost trade with no single
right answer, so it is exposed as `recording_cadence`, defaulting to one snapshot
per generation-equivalent.

**Reproducibility.** A fixed random seed must reproduce an async run exactly, which
means the order in which random draws are consumed *within* each event is pinned. In
particular, when `moran_rule = random`, the rule-selection coin is the **first**
draw of every event, and it is spent *only* when the random rule is active — so a
death_birth run and a random run share an identical random stream except for that one
extra up-front coin. A golden-master test locks this ordering down.

---

## 8. Where this milestone's ideas come from

**Moran (1958) is where event-time comes from.** The one-birth-one-death
replacement process — population pinned, evolution as slow turnover — is Moran's,
and it is the direct ancestor of M10b's fixed-N mode. His framing of a population
that changes by single replacements rather than whole generations is precisely the
dissolution of the generation that this milestone implements.

**Lieberman, Hauert & Nowak (2005) is where the process meets structure — and it
is the hook forward to M11.** They set the Moran process on a graph and showed that
population *structure* changes evolutionary outcomes (some structures amplify
selection, others suppress it). M10b runs the process well-mixed; M11 puts it on the
graph, at which point this line of work becomes directly relevant.

**Ohtsuki, Hauert, Lieberman & Nowak (2006) is why the update rule is a first-class
toggle.** Their result — cooperation favoured under death-birth updating when
`b/c > k`, never under birth-death, and under imitation when `b/c > k + 2` — is the
reason BD, DB and IM are treated as scientifically distinct choices rather than
implementation trivia, and the reason death-birth is the default.

**Traulsen, Nowak & Pacheco (2006, 2007) is where the imitation overlay's mechanism
comes from.** Their pairwise-comparison rule, using the Fermi function with an
inverse-temperature selection intensity, gives a single dial spanning neutral drift
to deterministic imitation. The overlay's `β` is that dial.

**Hammond & Axelrod (2006) is where this is all heading (M12).** Their ethnocentrism
model — agents carry tags and cooperate preferentially with their own kind — is the
research target the whole spine is built toward. The Moran-style event time of M10b
and the spatial structure of M11 are the substrate on which M12's tag-based
in-group/out-group dynamics will run.

**Nowak (2006) tells us which question M10b is asking.** Of the five mechanisms he
catalogues for the evolution of cooperation, M10b's machinery sits closest to
*network reciprocity* — cooperation sustained by who-interacts-with-whom — which is
exactly the mechanism death-birth updating on a graph switches on. M10b lays the
event-time groundwork; the network arrives next door.

---

## 9. What M10b deliberately does NOT model

- **Space.** No lattice, no neighbourhoods, no placement radius. Everyone is
  well-mixed. That is M11, and §6 explains why M10b is carefully built to leave the
  spatial seam untouched.
- **Tags / ethnocentrism.** No in-group/out-group conditioning of behaviour. That is
  M12, for which M10b (event time) and M11 (structure) are the substrate.
- **A non-standard time mapping.** Generation-equivalents are a fixed convention, not
  a knob (§2).
- **Fitness-blind demographics in the economy.** In variable-N mode the economy's
  resource rules — not a Moran coin — decide births and deaths; the Moran update
  rules apply only to the fixed-N comparison mode (§5).

---

## References

Hammond, R. A., & Axelrod, R. (2006). The evolution of ethnocentrism. *Journal of
Conflict Resolution*, 50(6), 926–936. DOI: 10.1177/0022002706293470.

Lieberman, E., Hauert, C., & Nowak, M. A. (2005). Evolutionary dynamics on graphs.
*Nature*, 433(7023), 312–316. DOI: 10.1038/nature03204.

Moran, P. A. P. (1958). Random processes in genetics. *Mathematical Proceedings of
the Cambridge Philosophical Society*, 54(1), 60–71. DOI: 10.1017/S0305004100033193.

Nowak, M. A. (2006). Five rules for the evolution of cooperation. *Science*,
314(5805), 1560–1563. DOI: 10.1126/science.1133755.

Ohtsuki, H., Hauert, C., Lieberman, E., & Nowak, M. A. (2006). A simple rule for the
evolution of cooperation on graphs and social networks. *Nature*, 441(7092),
502–505. DOI: 10.1038/nature04605.

Traulsen, A., Nowak, M. A., & Pacheco, J. M. (2006). Stochastic dynamics of invasion
and fixation. *Physical Review E*, 74(1), 011909. DOI: 10.1103/PhysRevE.74.011909.

Traulsen, A., Pacheco, J. M., & Nowak, M. A. (2007). Pairwise comparison and
selection temperature in evolutionary game dynamics. *Journal of Theoretical
Biology*, 246(3), 522–529. DOI: 10.1016/j.jtbi.2007.01.002.

*Note on provenance: every reference above was verified during this milestone's
literature pass against the publisher record or the paper itself — Moran (1958) via
Cambridge Core / ADS (vol. 54, pp. 60–71); Lieberman–Hauert–Nowak (2005) and
Ohtsuki et al. (2006) via their Nature records; Traulsen et al. (2006) via Physical
Review E and (2007) via the Journal of Theoretical Biology reference record; and the
Fermi copy-probability form `P = 1/(1 + e^(−β·Δf))` against the pairwise-comparison
literature. Hammond & Axelrod (2006) and Nowak (2006) carry over verified from the
M10 literature pass. The Traulsen (2007) DOI is the standard JTB assignment for
volume 246, pp. 522–529; confirm on fetch if a canonical link is needed for the
bibliography.*
