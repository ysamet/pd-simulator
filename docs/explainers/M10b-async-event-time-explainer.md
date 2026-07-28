# M10b — Asynchronous time: the Moran-style event-time model

*A companion explainer. It stands on its own: a reader who is comfortable with a
little arithmetic but who has never opened the M10a explainer should be able to
follow it from a cold start. The spec (`docs/specs/M10b-async-event-time-spec.md`)
records the frozen build intent; this document explains what the milestone does,
why the design choices are what they are, and where the underlying science comes
from. It is written against the **final, shipped** M10b — where implementation
refined or superseded the spec (most importantly the imitation adopter rule), the
text follows the implementation and names the DECISIONS entry that governs it.*

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
cohort. Time becomes a *sequence of individual events*: this one agent plays and
then breeds; that one is charged its living costs and goes insolvent; a third
copies a partner's strategy mid-way through its own run of matches — one at a
time, in a definite order. Nobody steps in unison. The population is more like a
city than a marching band: births, deaths, and conversions happen continuously and
singly, never all at once.

That sounds like a small bookkeeping change. It is not. It reaches into a decision
that the synchronous model never had to make explicit — *at what moment, and by
what rule, is each individual birth evaluated?* — and that question turns out to
collide with a change a **later** milestone (M11, which adds spatial structure)
will make. Section 8 is about that collision and how the design sidesteps it. But
first, the science the async clock is built on, and the anatomy of a single event.

### A worked contrast: the boundary sort versus the event stream

Suppose the population can hold at most `K = 4` agents, and at some point two of
them run out of resources and die.

**Synchronously**, that is easy to resolve. At the boundary you stop the world.
Two slots are now open (`slots = K − survivors = 4 − 2 = 2`). You look at *everyone
eligible to reproduce* — say four agents with energies `{50, 40, 30, 20}` — sort
them, and admit the top two (50 and 40). The word "global" is doing real work here:
because there is one frozen instant and a known slot count, ranking the *whole*
population at once is natural and cheap.

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
old. In 1958 the statistician P. A. P. Moran described a population model in which
births happen one after another, and each birth is paid for by the death of an
existing individual. That coupling is the heart of what we now call the **Moran
process**:

> Repeat forever: pick one individual to **reproduce**, and one individual to
> **die**. The newborn takes the dead one's place. Population size never changes.

Because exactly one birth is paired with exactly one death at every step, the
population is pinned at a constant size `N`. This is the purest possible "event
time" — the population never grows or shrinks, it only *turns over*, one
replacement at a time, and evolution is the slow drift of the population's
composition as fitter types are picked to reproduce slightly more often.

M10b takes this idea seriously enough to ship it as a mode (`fixed_n`, §7), but it
does **not** adopt the Moran replacement as the definition of an event. The reason
is the subject of the next section, and it is one of the most consequential design
choices in the milestone.

---

## 3. What one event actually is — and what a generation-equivalent means

### An event is a turn, not a replacement

In the textbook Moran process an event *is* a replacement: somebody breeds,
somebody dies, nothing else happens. That definition is only available if
demography is the only thing going on. This platform's main research line is the
**energy economy** (§6), in which agents earn, spend, save, starve and breed on
their own schedules — and in which the vast majority of moments contain no birth
and no death at all. If "event" meant "replacement", the economy would have almost
no events to run on.

So M10b pins a different, and more standard-for-agent-based-models, definition —
the **random asynchronous update**:

> **One event = one focal activation.** A **focal agent** is drawn uniformly at
> random from the living population. It plays **k matches** (`k =
> matching.opponents_per_agent`) against distinct partners drawn uniformly from
> everyone else. Then the consequences fire: match income and per-match costs
> land, the time-based ledger accrues, the demographic step runs, and — if the
> cultural overlay is on — the imitation rolls resolve.

Two things follow immediately, and both matter.

**Effects are immediate.** That is what asynchrony *means*. If the imitation
overlay flips the focal's strategy after match 2 of its bundle, the focal plays
match 3 as the new strategy (DECISIONS #98d). If a death trigger evaluates true,
the agent dies at that moment, not at some later boundary. There is no staging
area, no "apply at end of tick."

**The population that carried the event is the population that is measured.**
`N(t)` is read at event start; an event that ends in three deaths still belongs to
the `N` that began it. `N = 0` never starts an event, because extinction has
already ended the run.

### The generation-equivalent: N turns, not N replacements

If the generation no longer exists, what goes on the horizontal axis of a chart?
The raw unit of async time is one event, but one event is a tiny amount of change
compared to a synchronous generation. In a population of `N = 50`, a single
synchronous generation involves all fifty agents living, playing, and being
judged. A single event involves *one* focal — about 1/50th of that much activity.

So async time is measured in **generation-equivalents**, defined by turns:

> One generation-equivalent is the stretch of event time over which **every agent
> has been the focal once, on average**. Each event advances the clock by
> `Δt = 1/N(t)`; one generation-equivalent completes when the running sum of those
> increments reaches 1.

Note carefully what this is *not*. It is not "the time for every agent to be
replaced once" — that is the Moran reading, and it would be wrong here, because in
the economy most events replace nobody. It is "the time for every agent to have
had its turn." In the `fixed_n` Moran mode the two readings happen to coincide
(every event is exactly one replacement, so N events really is one full turnover),
which is why the convention is also exactly the textbook one there. In
`variable_n` the turn-based reading is the only one that survives, and it
self-adjusts as the population grows and shrinks, because `N(t)` is re-read every
event.

This is a **fixed reporting convention, not a tunable knob** (spec Design 5).
There is only one scientifically standard mapping; letting a user pick a
non-standard one would make their own sync and async runs incomparable for no
gain. It consumes no randomness and changes nothing inside the simulation — it
changes only the label on the x-axis and the stamp on each recorded event.

### Why the k-match bundle: keeping async calibrated against sync `random_k`

Here is the part that is easy to get wrong, and that the design deliberately gets
right. The generation-equivalent makes sync and async runs comparable in **time**.
Making them comparable in **income** takes a second, independent decision: how
many matches a focal plays when activated. M10b's answer is *k of them*, the same
`k` a synchronous `random_k` generation uses — and the reason is arithmetic.

Take `N = 50` agents and `k = 3`.

**Synchronous `random_k`, one generation.** Every agent initiates `k = 3` matches,
so the generation contains `50 × 3 = 150` matches. Each match seats two players,
so there are `150 × 2 = 300` match participations, spread over 50 agents:

    300 participations ÷ 50 agents = 6 matches per agent = 2k

Each agent plays about `2k = 6` matches per generation — `k` as an initiator, and
about `k` more as somebody else's randomly drawn partner.

**Asynchronous, one generation-equivalent.** That is `N = 50` events. Each event is
one focal playing `k = 3` matches, so again `50 × 3 = 150` matches, `300`
participations, `6` per agent. **Identical.**

**Now suppose an event were a single match instead of a bundle.** Fifty events
would produce 50 matches, 100 participations, `100 ÷ 50 = 2` matches per agent —
*one third* of the synchronous budget, and in general a factor of `k` short.

That factor of `k` would be silent and destructive. Every economy parameter in
M10a is tuned against an agent's income over one generation: the basic living cost
`L` is deliberately set *between* the all-defector and all-cooperator incomes so
that cooperation becomes a survival matter, and the app's Economy panel prints
exactly where that survival window lies. Cut income to a third while leaving `L`
where it is, and every population starves — not because asynchrony favours
starvation, but because the bookkeeping quietly changed the meaning of `L`. The
V5 validation scenario (`sync_vs_async_economy`) exists to show this *not*
happening: the same economy grows from 40 toward `K = 200` under both clocks, and
the Economy panel's window readout applies unchanged to both.

One small consequence, pinned rather than papered over: because partners are drawn
uniformly, a given pair can meet more than once inside one generation-equivalent —
the same pair-recurrence that synchronous `random_k` already has, at roughly
`2k/(N−1)`. The bundle matches sync's budget *because* it inherits sync's sampling
quirks, not in spite of them.

### The one-agent corner

At `N = 1` there is no partner to draw. The lone survivor plays no matches,
consumes no partner randomness, still pays its living costs in the accrual sweep,
and — absent capital returns — slides toward insolvency. This is the intended
thermodynamics of "a population of one under a metabolic bill", carried over from
M10a and pinned by test, not an edge case that was overlooked.

---

## 4. Update rules: who reproduces, who dies

The bare Moran process says "pick one to reproduce and one to die" but leaves open
*how* you pick. The two classical choices, and a mixture of them, are M10b's
first user-facing demographic toggle — `moran_rule`. It applies in `fixed_n` mode
only (§7 explains why).

**Death-birth (DB).** First choose an individual to die. That leaves an empty slot.
Then the survivors compete to reproduce into it, with a chance **proportional to
fitness**: a fitter agent is more likely to win the vacancy. Death picks the
*slot*; fitness picks the *winner*.

**Birth-death (BD).** The other order. First choose an individual to reproduce,
with a chance **proportional to fitness** — the fittest are most likely to breed.
Then the offspring replaces one of the *others*, chosen by the death rule below
(the breeder cannot replace itself). Fitness picks the *breeder*; the death rule
picks the *victim*.

**Random.** A per-event mixture of the two. On each event, before anything else
demographic happens, the engine flips a weighted coin to decide whether *this*
event uses BD or DB, then proceeds accordingly. The weights are two ordinary
parameters (`moran_weight_birth_death` and `moran_weight_death_birth`, defaults
0.5 / 0.5, normalised at use), so "uniform mix" is just the default and you can
dial the blend.

### How "proportional to fitness" is actually computed

Energies can be negative in this platform, and you cannot spin a roulette wheel
with negative slice widths. So fitness weights use the **shift idiom**: for each
candidate `i`, the weight is

    w_i = e_i − min(e over the candidate set)

If every weight comes out zero (all candidates hold identical energy), the draw
falls back to uniform. One worked case: candidates holding `{900, 700, 400}` give
`min = 400` and weights `{500, 300, 0}` — the poorest candidate cannot win the
slot, and the richest is 500/800 = 62.5% likely to. Candidates holding
`{100, −100, −300}` give `min = −300` and weights `{400, 200, 0}` — negative
balances are absorbed without special-casing. This is the same shift the
synchronous proportional selection rule already used; reusing it, rather than
inventing an async variant, is what keeps the two clocks' selection semantics
honest.

### Why the order is not cosmetic

It is tempting to assume BD and DB are two spellings of the same thing. They are
not — and the difference is exactly the kind of thing this platform exists to
study. On a *structured* population (agents arranged on a graph, interacting only
with neighbours), Ohtsuki, Hauert, Lieberman and Nowak showed in 2006 that the
update rule decides whether cooperation can survive at all. Writing `b` for the
benefit a cooperator confers, `c` for the cost it pays, and `k` for the number of
neighbours each agent has:

- Under **death-birth** updating, cooperation is favoured when `b/c > k`.
  Structure can *rescue* cooperation.
- Under **birth-death** updating, no such rescue exists on a regular graph —
  defection prevails regardless of structure.
- Under **imitation** updating (a close cousin — see §5), the threshold shifts to
  `b/c > k + 2`. Imitation is harder on cooperation than death-birth because the
  agent being updated has its *own* payoff in the comparison, and a defector on
  the edge of a cooperator cluster is precisely the agent doing well.

Later work found that raising the *fraction* of death-birth events monotonically
improves cooperation's prospects, at least under weak selection. That is why the
default `moran_rule` is **death_birth**: it points the platform at the regime
where cooperation has a fighting chance, which is the whole research programme's
target.

One honest caveat, stated up front: that `b/c > k` result *requires the graph*. In
M10b's world there is no graph yet — everyone is everyone else's potential partner
(well-mixed). So in M10b the three rules differ **mechanically** (they really do
pick breeders and victims differently, and reproducible runs diverge under each)
but the cooperation-promoting *result* does not yet bite. M10b builds the
`moran_rule` machinery; **M11**, which adds the graph, is what makes it
scientifically potent. Sequencing the seam before the payoff is deliberate, and
the app's tooltip beside the toggle says exactly this rather than implying a
result the model cannot yet deliver.

### The fixed-N death rule

Whichever Moran rule fires, something has to fill its *death slot* — under DB, who
dies; under BD, which other agent the offspring displaces. `fixed_n_death_rule`
offers two flavours:

- **pure_random** — one uniform draw; death is independent of energy, exactly as
  in the textbook process. This is the setting for reproducing published Moran
  results, and part of the textbook corner in §7.
- **energy_decides** (the default) — the lowest-energy candidate dies, ties broken
  by lowest id. Deterministic; it consumes no randomness at all. This imports an
  economic flavour into the otherwise-textbook model: survival still depends on how
  well you have been doing, but the population count does not float.

A naming subtlety worth knowing when you read a run's `deaths.parquet`: the
recorded `cause` names the **slot**, not the selection rule — `random_moran` for
the death-birth death slot and `replacement` for the birth-death victim slot, even
when `energy_decides` filled that slot deterministically. The run's stored config
records which rule was actually in force (DECISIONS #97b).

---

## 5. Imitation is a different animal: the cultural channel

There is a third classical way for strategies to spread, and it is **not** a third
Moran rule — treating it as one was a tempting mistake the design deliberately
avoids. The reason is worth spelling out, because it is a genuine conceptual split,
not a plumbing detail.

Birth-death and death-birth are **demographic**: they change *who exists*. A birth
adds an agent to the world; a death removes one. **Imitation** is **cultural**: it
changes *what an existing agent plays*, while that agent keeps living — same
identity, same energy, same age, same match histories. Nobody is born, nobody dies;
a mind changes.

### A worked contrast: cast-change versus mind-change

Take four agents: A (cooperator), B (defector), C (cooperator), D (defector).

- A **death-birth event**: D is chosen to die; the survivors compete for its slot;
  A wins and a fresh cooperator is born there. The population is now {A, B, C, A′}.
  *One agent died, one was born — the cast changed.*
- An **imitation event**: B and C play a match, and afterwards B adopts C's
  strategy. The population is still {A, B, C, D} — the very same four agents, same
  energies, same ages — but B is now a cooperator. *Nobody was born or died; a
  behaviour changed.*

These are not two ways of doing the same job, and you might well want both
happening in one run — strategies spreading *both* by out-breeding *and* by
conversion. A single "pick one rule" radio button cannot express that; two
independent channels can. So imitation is its own switch, `imitation_overlay`
(a checkbox, default off), layerable on top of **either** async population mode.
When it is on, it fires on a different **trigger** than births and deaths do: not
on a vacancy, but on a *completed match*.

### The rule that shipped: symmetric adopter choice (DECISIONS #93)

This is the one place where the shipped model differs from the frozen spec text,
and the difference is scientifically load-bearing rather than cosmetic, so it is
worth working through carefully.

After each completed match, with the overlay on, the engine draws **two coins**:

1. **The adopter coin.** Of the two agents who just played, one is chosen by a
   **fair coin** to be the potential **adopter**; the other is the **model**.
   Score plays no part in this choice.
2. **The Fermi coin.** The adopter copies the model's strategy with probability

       P(adopter copies model) = 1 / (1 + e^(−β · (model_score − adopter_score)))

   where the scores are the two participants' totals from the match just played,
   and `β` is `dynamics.selection_beta`, the same selection-intensity dial the
   synchronous engine already uses.

Both coins are drawn **unconditionally** whenever the overlay is on — even when
both participants already play the same strategy, in which case the copy is a
no-op. This is the platform's standing "active-flag" discipline: the random number
stream must depend only on which *flags* are set, never on the *state* the agents
happen to be in, or a fixed seed would stop reproducing a run the moment a
strategy distribution shifted. A no-op spends its two coins and emits no
`ImitationEvent`; the coins, not the events, are the reproducibility contract
(DECISIONS #98c, #99).

### Why symmetric, and what `β` really controls

The parameter `β` is an **inverse temperature**, borrowed from statistical physics
by Traulsen, Nowak and Pacheco. It controls how sharply the copy depends on the
score gap. Work an example: adopter scored 3, model scored 5, `β = 1`, so the gap
is `+2`:

    P = 1 / (1 + e^(−1 × 2)) = 1 / (1 + 0.1353) = 0.881

The adopter copies the better-scoring model about 88% of the time. Raise `β` and
that climbs toward certainty; lower it toward 0 and it falls back to a coin flip.
In the limit of very large `β` the rule becomes a step function — always copy the
better scorer — which is the "imitation dynamics" extreme in the literature.

Now put the two coins together for that same pair — scores 3 and 5, `β = 1`:

- With probability ½ the **3-scorer** is the adopter. It copies the 5-scorer with
  probability `1/(1 + e^(−2)) = 0.881`.
- With probability ½ the **5-scorer** is the adopter. It copies the 3-scorer with
  probability `1/(1 + e^(+2)) = 1/8.389 = 0.119`. **Downhill copies are
  possible.**

So per match:

    P(the better strategy spreads) = ½ × 0.8808 = 0.4404
    P(the worse strategy spreads)  = ½ × 0.1192 = 0.0596
    -------------------------------------------------------
    P(some copy happens)                         = 0.5000
    Net drift toward the better scorer           = 0.3808

Two facts fall straight out of that arithmetic, and both are worth internalising.

**First: the total copy rate is exactly ½ per match, for every `β` and every score
gap.** This is not a coincidence of the numbers chosen. Writing `σ(x)` for the
logistic function, the two branches sum to `½·σ(βΔ) + ½·σ(−βΔ) = ½·(σ(βΔ) + 1 −
σ(βΔ)) = ½`. So **`β` sets the *bias* of a fair per-match coin, not the *rate* of
copying.** Cranking `β` up does not make culture spread faster; it makes each of
the same number of copies more reliably point uphill. This has a practical
consequence the V2 scenario had to be retuned around (DECISIONS #101c): cultural
turnover runs on the *match* timescale at any `β`, so an overlay-only run can
sweep the population within a couple of generation-equivalents.

**Second: at `β = 0` the exponent vanishes, both branches equal ½, and the rule
becomes pure neutral drift** — strategies spread by luck alone, with no
directional pull whatsoever. This is the property that motivated the change.

The originally specified rule was **asymmetric**: the adopter was forced to be the
*lower*-scoring participant, so every copy pointed uphill and the higher scorer
never adopted. Under that rule `β = 0` gives `P = ½` of a copy that is *still*
directed from winner to loser — fitness-blind in *intensity* but still
fitness-*directed*. Neutral drift is unreachable at any `β`, because the direction
is hardwired. Meanwhile the synchronous engine has always used the symmetric form
(it samples an incumbent A and a model B, and A adopts B with `1/(1 + e^(−β(s_B −
s_A)))`, with A's own score irrelevant to whether it was picked). The same
parameter `β` therefore meant two different things on the two clocks — most
visibly at `β = 0`, neutral under sync and residually selective under async.

Since a central purpose of shipping both clocks is to **compare** them, a `β`
sweep run under each would have compared two different rules under one label, and
part of a pure rule artifact would have been read as a time-model effect. Phase E
reconciled async to the symmetric rule; `selection_beta` now means one thing
everywhere, and `β = 0` is true neutral drift on both clocks.

It is worth noting that the symmetric shape is also the shape the graph literature
uses: in Ohtsuki et al.'s imitation updating, the individual who reassesses its
strategy is chosen *at random*, and only then does fitness govern what it adopts.
Choosing the adopter by score is a different dynamic, not a neutral implementation
detail.

### The asymmetric rule is deferred, not discarded

"Imitate whoever did better than you" is a legitimate and well-studied dynamic in
its own right, not a mistake to be swept up. It is **backlogged with an explicit
review checkpoint** (DECISIONS #93B): the intended shape is a labelled parameter,
`dynamics.imitation_adopter ∈ {symmetric, imitate_better}`, defaulting to
symmetric and governing *both* time models. It was not built during M10b because
exposing it also reaches into the stable synchronous selection path — scope
deliberately not reopened mid-milestone. The checkpoint fires at **M12 scoping**
(tags and Hammond–Axelrod ethnocentrism), which is the first milestone where the
distinction may be load-bearing: ethnocentrism is precisely a story about how
behaviour spreads within and across group boundaries, and imitate-the-better
versus symmetric drift-plus-selection can push in-group and out-group cooperation
differently. A "not yet" answer at M12 is an entirely acceptable outcome; the
checkpoint only guarantees the question gets asked on schedule.

### A finding the overlay produced, worth flagging

Validation turned up something the spec had not anticipated, and the shipped
scenario now teaches it (DECISIONS #101c-i). With the overlay on, imitation tends
to spread **defection** — because in any mixed match the defector out-earns the
very reciprocator it is exploiting, so copying match winners favours unconditional
defection even though reciprocators earn more when playing *each other*. The
cultural channel and the demographic channel can therefore disagree about
cooperation in the very same run. That is not a bug in the overlay; it is a
concrete illustration of why the two channels were separated in the first place.

---

## 6. The ledger in event time: costs, interest, and the compounding grain

The platform carries a **resource economy**, and it runs in **both** async modes.
A brief standalone sketch, since it is what makes async time more than a
rearrangement of the Moran process.

Each agent holds a stock of energy. Playing earns energy — and because cooperation
returns more jointly than mutual defection does, *cooperators generate more energy
per interaction than defectors do*. Living costs energy: a **basic living cost**
`L` is charged simply for existing (default 200 per generation), and an optional
**engagement cost** is charged per match played. An agent that reaches the
**reproduction threshold** `θ` (default 500) can afford a child, paying an
**offspring stake** `σ` (default 400) out of its own stock into the newborn's,
plus any **reproduction overhead** that simply burns. An agent whose stock goes
strictly negative is **insolvent** and dies. A **carrying capacity** `K` caps how
many agents the world can hold. An optional **capital return rate** `r` (default
0) pays interest on carried energy. The upshot is that the same metabolic bill a
thriving cooperator shrugs off can drive defectors extinct, and population size
becomes an *outcome you measure* rather than a fixed input.

Every one of those terms was defined **per generation boundary**. Async time has
no boundaries, so each one had to be converted. The conversion is spec Design 2a,
and it is mostly mechanical — with one term that genuinely cannot convert cleanly,
which the rest of this section is about.

### The accrual sweep

Match income and engagement costs land at **match completion** — the moment the
match ends, credited to both participants. That part is easy: those were always
per-match quantities.

Time-based quantities are different, because "per generation" now has to mean "per
unit of the generation-equivalent clock". Once per event, the engine runs an
**accrual sweep** over every living agent in ascending id order, applying

    e ← e · (1 + r)^Δt  −  L · Δt

with `Δt = 1/N(t)` the event's clock advance. The sweep consumes no randomness and
is pure bookkeeping. Its cost is `O(N)` per event, hence `O(N²)` per
generation-equivalent — which sounds alarming until you notice that each event
already plays `k` matches of many rounds each. The Phase-E benchmark measured the
whole async loop at roughly **6–11% overhead** over the synchronous economy at
equal `N`, with scaling still linear in `N` (DECISIONS #102). The sweep is
bookkeeping-cheap, exactly as the design predicted.

### The compounding grain: where the two clocks stop agreeing exactly

The living cost converts cleanly. The interest does not, and the spec names this
honestly rather than hiding it.

**Synchronously**, interest is applied **once per boundary**, and it applies to
the balance *carried in* — income earned during the generation is folded in
afterwards:

    e_new = e_carried_in × (1 + r)  +  income  −  L  −  engagement costs

**Asynchronously**, interest compounds `(1 + r)^Δt` at every event, applied to
whatever balance exists *at that moment* — which includes income that already
arrived earlier in the same generation-equivalent.

The consequence, stated precisely: **the two clocks agree exactly on a static
balance, and only on a static balance.** Three worked cases make this concrete.
Take `N = 4` (so `Δt = 0.25` and four events make one generation-equivalent) and
an agent starting at `e = 1000`.

**Case 1 — static balance, `r = 10%`.** No income, no costs.

The per-event factor is `(1.10)^0.25 = 1.0241137`. Four events:

    1000 × 1.0241137⁴ = 1000 × 1.10 = 1100.00

Synchronously: `1000 × 1.10 = 1100.00`. **Exactly equal** — this is the whole
content of "compounds to exactly (1+r) per generation-equivalent", and it is true
by construction: `((1+r)^(1/N))^N = (1+r)`.

**Case 2 — `r = 0` (the default), with income and costs.** Say the agent earns 100
per event (400 over the generation-equivalent) and `L = 200`.

Async: interest multiplies by 1, and the living charges sum to
`L × ΣΔt = 200 × 1 = 200` exactly. Final balance `1000 + 400 − 200 = 1200.00`.
Sync: `1000 × 1 + 400 − 200 = 1200.00`. **Exactly equal again.** With interest
switched off, *when* money moves does not matter, only how much — so the default
configuration has no divergence at all.

**Case 3 — `r = 10%`, with the same income and costs.** Now timing bites.

Sync: `1000 × 1.10 + 400 − 200 = 1100 + 400 − 200 = 1300.00`

Async, event by event (income lands, then the sweep multiplies and charges
`L·Δt = 50`):

| Event | + income | × 1.0241137 | − 50 |
|---|---|---|---|
| 1 | 1100.00 | 1126.53 | 1076.53 |
| 2 | 1176.53 | 1204.90 | 1154.90 |
| 3 | 1254.90 | 1285.16 | 1235.16 |
| 4 | 1335.16 | 1367.35 | **1317.35** |

Async finishes at **1317.35** against sync's **1300.00** — a gap of **+17.35**, or
about 1.3% of the balance. And the gap decomposes exactly into its two causes:

- **Income earns interest earlier (+24.70).** The four payments of 100 compound for
  four, three, two and one quarter-steps respectively:
  `100 × (m⁴ + m³ + m² + m) = 100 × 4.24702 = 424.70`, against sync's flat 400.
- **Costs are paid earlier (−7.35).** Money removed early stops compounding:
  `50 × (m³ + m² + m + 1) = 50 × 4.14702 = 207.35` of final-balance impact,
  against sync's flat 200.

`424.70 − 400 = +24.70`; `207.35 − 200 = −7.35`; net `+17.35`. ✓

**This is inherent to event time, not a bug.** There is no ordering of operations
that makes a continuously-compounding clock agree with a once-per-boundary clock
about money that arrives mid-period, because the two models genuinely disagree
about when that money starts earning. The comparability tests pin it that way:
they assert the *same growth story* across the clocks and deliberately do **not**
assert byte-identity (DECISIONS #96d). If you want the clocks to agree to the
penny, set `r = 0` — which the default already does, and which the textbook corner
in §7 requires anyway.

One further difference survives even at `r = 0`, and it is a modelling difference
rather than an arithmetic one: async evaluates insolvency at **every** demographic
step, so an agent whose balance dips below zero mid-period dies there, where a
synchronous agent would have been rescued by income arriving later in the same
generation. Same totals, different survival. That is a real property of
asynchronous time, and worth remembering when a defector population collapses
faster on the async clock than the per-generation arithmetic would suggest.

### The breeding refractory period

One more conversion needed care. Synchronously, an agent could have at most one
child per generation — a hard cap the boundary enforced for free. In event time
that cap has no natural home: a parent sitting at `e ≥ 2θ` would pay `σ`, still
hold `≥ θ`, and be immediately eligible again, burst-breeding several children
inside a single generation-equivalent.

That is not a small quantitative difference; it *reroutes* how dynasties work.
Under the one-child cap, a wealthy lineage's advantage runs through **breeding
frequency** — you breed every generation instead of every third. Under
burst-breeding it would run through **stock size** — accumulate enough and convert
it into offspring all at once. The platform had already considered and rejected
the stock-size channel.

So event time gets an explicit **refractory period of 1.0 time units**: a parent
must wait a full generation-equivalent after a birth before breeding again
(founders' clocks anchored at `t = 0`). Like the generation-equivalent itself,
this is a fixed convention rather than a knob — it exists to preserve a decision
already made, not to open a new one (DECISIONS #96a).

Ages convert the same way: an agent's age is `t − birth_time` measured in
generation-equivalents, and mortality's per-boundary coin becomes one coin per
**integer birthday**, priced identically — so an async agent draws the same
lifetime sequence of hazard coins a synchronous agent would. Founders staggered to
different starting ages simply get negative birth times, so a staggered population
still begins at its demographic steady state (DECISIONS #96b, #96c).

---

## 7. Variable-N versus fixed-N — and the exact textbook-Moran corner

Recall from §6 that the economy has **already decoupled birth from death**. A
death is triggered by insolvency or age; a birth is triggered, independently, by an
agent clearing `θ` with a slot free under `K`. They no longer arrive as the coupled
pair that *defines* the Moran process. This is why "birth-death versus death-birth"
is intrinsically a **fixed-N** concept: the crisp BD/DB distinction comes from *one
birth balancing one death*, and once births and deaths fire independently, the
coupling — and the distinction that rode on it — is gone.

So M10b's asynchronous clock runs in one of two modes (`async_population`):

- **`variable_n`** (the default) — the economy's own decoupled, largely
  deterministic demographic rules run in event time. Births fire when agents clear
  `θ` with the refractory clear; deaths fire on insolvency or age; `N` floats
  between extinction and `K`. Here `moran_rule` and `fixed_n_death_rule` simply do
  not apply — the economy *is* the demographic engine. This carries the M10a
  resource economy forward into continuous time, which is the platform's research
  through-line.
- **`fixed_n`** — the Moran process: size pinned, every event ending in exactly
  one replacement, governed by `moran_rule` and `fixed_n_death_rule` from §4.
  There are no insolvency deaths, no age deaths, no `θ` births, and no extinction;
  `carrying_capacity` is ignored outright. This is the clean comparison model.

The imitation overlay (§5) is available in **both**.

A structural note that follows from the coupling: `fixed_n` never calls the
capacity-admission seam at all, because a Moran replacement vacates the very seat
it fills — there is no capacity question to ask. It *does* still call the
placement seam before the parent pays its stake, which matters for §8 (DECISIONS
#97d).

### The textbook corner, precisely

`fixed_n` is the mode you would use to reproduce a published Moran result, but the
defaults are not textbook — they are economy-flavoured. The exact corner is:

| Setting | Value | Why it is required |
|---|---|---|
| `async_population` | `fixed_n` | The one-birth-one-death coupling exists only here. Under `variable_n` there is no Moran process to reproduce. |
| `fixed_n_death_rule` | `pure_random` | Textbook Moran death is **independent of fitness** — one uniform draw. The default `energy_decides` aims the reaper at the poorest agent, which is a different (and deliberately economic) process. |
| `offspring_stake` σ | `0` | With σ > 0, birth **transfers capital**: the parent's balance drops and the newborn starts endowed, so a lineage's wealth becomes heritable and breeding feeds back on the breeder's own fitness. The textbook process has no analogue for either. At σ = 0 nothing is transferred and a newborn starts from nothing. |
| `capital_return_rate` r | `0` (already the default) | Interest is **multiplicative**, so it amplifies existing differences and creates rentiers — agents whose holdings alone pay their bills regardless of how they play. Textbook fitness comes from play, not from capital. Zeroing `r` also collapses the §6 compounding divergence to nothing. |

Note what is *not* on that list: the basic living cost `L`. It can stay at its
default, because of the shift idiom from §4. Since the accrual sweep charges every
living agent the *same* `L·Δt` at the *same* event, it moves every balance by the
same amount, and the fitness weight `w_i = e_i − min(e)` depends only on
differences. Worked: energies `{900, 700, 400}` give weights `{500, 300, 0}`;
charge everyone 200 to get `{700, 500, 200}` and the weights are `{500, 300, 0}`
again — identical. Unlike `r`, `L` cannot amplify inequality, because it is a flat
per-capita charge rather than a proportional one.

**Two honest residues**, so nobody is surprised when the numbers do not line up
with a paper:

1. *`L`'s cancellation is exact among agents that have been alive over the same
   span, not across cohorts.* An agent born halfway through a run has been charged
   half as much `L` as a founder, so with `L > 0` a young agent sits higher
   relative to an old one than it would with `L = 0`. In a pinned-`N` run with no
   age deaths this only starts to matter once replacement births accumulate. Set
   `L = 0` if you want the residue gone entirely.
2. *Fitness here is a stock, not a flow.* Textbook frequency-dependent Moran
   models usually take fitness from the payoff earned in the **current** round.
   This platform's `fixed_n` fitness is the agent's **accumulated ledger balance** —
   its whole earning history, not its latest one. That is a deliberate consequence
   of running one ledger across both modes, and it makes `fixed_n` a Moran process
   *with memory*. For qualitative comparisons it behaves as you would expect; for
   quantitative reproduction of a published fixation probability, it is the
   difference to reach for first.

---

## 8. The seam: why a time change collides with a space change

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
  fires, the event loop itself scans the whole population, ranks by energy, and
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
  implement "candidate set = whole population, rule = energy priority, placement =
  anywhere," producing numbers identical to Option A. But the loop never encodes
  that. When M11 arrives, it swaps only the *implementations* of those two
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

## 9. Recording, comparability, and reproducibility

Four practical consequences of moving to event time.

**Explicit birth/death/imitation events.** Because per-event ordering is now
meaningful, asynchronous runs emit explicit typed events — a birth event (with the
newborn's identity, parent, strategy, starting energy and cause), a death event
(with its cause: insolvency, age, replacement, or the Moran death slot), and an
imitation event (who copied whom, from which strategy to which). Each carries the
index of the event that produced it and its `gen_equiv_time` stamp. Within one
event, deaths are recorded before the births they pair with — the seat empties,
then fills — and the ordering is now load-bearing, because the persistence loader
re-interleaves the three event tables by relying on it. The synchronous path is
unchanged: it emits none of these, so old synchronous runs produce byte-identical
output (DECISIONS #97f, #100c).

**Recording cadence is a knob** (unlike the time-mapping convention of §3, which is
fixed). In event time you can record on *every* event — maximum resolution, but
`N` times more points per generation-equivalent, larger files, and the
chart-rendering ceiling arriving fast — or downsample to one snapshot per
generation-equivalent (comparable to synchronous runs, sane file sizes), or one
every `m` events. This is a genuine resolution-versus-cost trade with no single
right answer, so it is exposed as `recording_cadence`, defaulting to one snapshot
per generation-equivalent. It is an *observer* control and is pinned by test never
to influence the simulation — same config and seed at different cadences produce
identical state trajectories. It lives in the config anyway (unlike other observer
settings) because it decides what the persisted record *contains*, and what a run
recorded is part of reproducing it.

**Charts plot the clock, not the period index.** Whenever a run carries
`gen_equiv_time` stamps, every chart's x-axis is the generation-equivalent clock,
labelled as such. This matters under the non-default cadences: recorded periods
are then *not* equally spaced in time, so plotting against the period index would
visibly distort trajectories. Synchronous and tournament runs keep their period
axis untouched (DECISIONS #101b).

**Reproducibility.** A fixed seed must reproduce an async run exactly, which means
the order in which random draws are consumed *within* each event is pinned: focal
draw → partner draw → per-match round draws (each match followed, when the overlay
is on, by its two adoption coins) → the randomness-free accrual sweep → the
mode-specific demographic draws → randomness-free recording. Draws exist only when
their governing flag makes them meaningful. In particular, when `moran_rule =
random`, the rule-selection coin is the **first** demographic draw of every event
and is spent *only* when the random rule is active — so a `death_birth` run and a
`random` run share an identical stream except for that one extra coin. Golden-master
tests lock the whole ordering down; a mis-pinned rule roll cannot reproduce the
pinned trace.

One reporting subtlety worth knowing when reading async output: async period
reports describe the living population **at the recording point**, where sync
reports describe the population **as it played**. A strategy that went extinct
before a recording point therefore drops out of that period's mean scores (its
earnings survive in the pair-keyed cooperation table), and an extinct run's final
partial period shows an empty composition while still carrying its closing deaths
and clock stamp (DECISIONS #96e).

---

## 10. Where this milestone's ideas come from

**Moran (1958) is where event time comes from.** The one-birth-one-death
replacement process — population pinned, evolution as slow turnover — is Moran's,
and it is the direct ancestor of M10b's `fixed_n` mode. His framing of a population
that changes by single replacements rather than whole generations is precisely the
dissolution of the generation that this milestone implements. M10b's departure —
defining an event as a focal *turn* rather than a *replacement* (§3) — is what lets
the same clock also carry an economy in which most moments contain no replacement
at all.

**Lieberman, Hauert & Nowak (2005) is where the process meets structure — and it
is the hook forward to M11.** They set the Moran process on a graph and showed that
population *structure* changes evolutionary outcomes: some structures amplify
selection, others suppress it. M10b runs the process well-mixed; M11 puts it on the
graph, at which point this line of work becomes directly relevant.

**Ohtsuki, Hauert, Lieberman & Nowak (2006) is why the update rule is a first-class
toggle.** Their result — cooperation favoured under death-birth updating when
`b/c > k`, never under birth-death, and under imitation when `b/c > k + 2` — is the
reason BD, DB and imitation are treated as scientifically distinct choices rather
than implementation trivia, and the reason death-birth is the default. Their
imitation rule is also the shape M10b's overlay follows after the #93
reconciliation: the individual who reassesses is chosen at random, and only then
does payoff govern what it adopts.

**Traulsen, Nowak & Pacheco (2006, 2007) is where the imitation overlay's mechanism
comes from.** Their pairwise-comparison rule adopts the Fermi function from
statistical mechanics, with an inverse temperature controlling selection intensity,
giving a single framework that spans everything from random drift to imitation
dynamics. The overlay's `β` is that dial — and §5's arithmetic shows exactly what
it does and does not control on this platform.

**Hammond & Axelrod (2006) is where this is all heading (M12).** Their ethnocentrism
model — agents carry tags and cooperate preferentially with their own kind — is the
research target the whole spine is built toward. The event time of M10b and the
spatial structure of M11 are the substrate on which M12's tag-based
in-group/out-group dynamics will run, and M12 scoping also carries the imitation
adopter checkpoint from §5.

**Nowak (2006) tells us which question M10b is asking.** Of the five mechanisms he
catalogues for the evolution of cooperation, M10b's machinery sits closest to
*network reciprocity* — cooperation sustained by who-interacts-with-whom — which is
exactly the mechanism death-birth updating on a graph switches on. M10b lays the
event-time groundwork; the network arrives next door.

---

## 11. What M10b deliberately does NOT model

- **Space.** No lattice, no neighbourhoods, no placement radius. Everyone is
  well-mixed. That is M11, and §8 explains why M10b is carefully built to leave the
  spatial seam untouched.
- **Tags / ethnocentrism.** No in-group/out-group conditioning of behaviour. That is
  M12, for which M10b (event time) and M11 (structure) are the substrate.
- **A non-standard time mapping.** Generation-equivalents are a fixed convention,
  not a knob (§3) — as is the 1.0-unit breeding refractory (§6).
- **A choice of imitation adopter rule.** The symmetric rule is the only one
  shipped; `imitate_better` is backlogged with a review checkpoint at M12 (§5).
- **Fitness-blind demographics in the economy.** In `variable_n` the economy's
  resource rules — not a Moran coin — decide births and deaths; the Moran update
  rules apply only to the `fixed_n` comparison mode (§7).
- **Exact sync/async ledger identity under interest.** By design and by test: the
  clocks agree exactly at `r = 0` and on static balances, and diverge in a fully
  characterised way otherwise (§6).

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

*Note on provenance: every reference above was verified against the publisher
record or the paper itself. Re-verified during this revision pass: Traulsen, Nowak
& Pacheco (2006) against the Physical Review E record (vol. 74, 011909, published
17 July 2006), whose abstract is the source of the "unified framework from random
drift to imitation dynamics" characterisation of the inverse-temperature dial in
§5; Traulsen, Pacheco & Nowak (2007) against ScienceDirect and PubMed (vol. 246,
issue 3, pp. 522–529; PMID 17292423) — the earlier "confirm on fetch" hedge on this
DOI is now discharged; and Ohtsuki et al. (2006) including the `b/c > k + 2`
imitation threshold, checked against the paper's own supplementary material, which
also supplies the definition of imitation updating (a randomly chosen individual
reassesses, then imitates proportional to fitness) cited in §5 and §10. Moran
(1958) was verified in the original literature pass via Cambridge Core (vol. 54,
pp. 60–71); Lieberman–Hauert–Nowak (2005) via its Nature record; Hammond & Axelrod
(2006) and Nowak (2006) carry over verified from the M10 literature pass. The Fermi
copy-probability form `P = 1/(1 + e^(−β·Δ))` matches the pairwise-comparison
literature.*
