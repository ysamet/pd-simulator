# M11a — Population structure: spatial reciprocity, the constraint structure of the Prisoner's Dilemma, and the b/c > k threshold

*A companion explainer to the M11a milestone (spec:
`docs/specs/M11a-population-structure-spec.md`, status implemented; DECISIONS
#111–#161). It is written for a reader who is just starting game theory: every
symbol is defined, every piece of jargon is unpacked where it first appears,
and every number is worked so that it can be reproduced by hand. Where the
calibration guide (`docs/explainers/calibration-guide.md`) already treats a
topic in full, this document states the headline result and points there
rather than deriving it a second time. Every literature claim traces to a
reference in §9, all of which were verified against publisher records or
author-institutional deposits during the M11a literature verification pass
(2026-08-14, DECISIONS #161). It is written against the final, shipped M11a:
where the milestone measured something that differs from what a textbook
would predict, the text reports the measurement and names the DECISIONS entry
that records it.*

---

## 1. What M11a builds, and why a shape matters

Before M11a, the population in pdsim was a list. Any agent could meet any
other agent, could breed into a vacancy anywhere, and could be replaced by
anyone; the question "where is this agent?" had no answer because there was
no *where*. M11a gives the world a **shape**, and the shape is built out of
one idea.

**A site is an exclusive container.** A site holds at most one agent, and an
agent occupies exactly one site. (The engine carries a `site_capacity` field
so that a later milestone can relax this, but in M11a it is pinned at 1 —
DECISIONS #135.) The population is then a **graph of sites**: a collection of
sites together with a relation saying which sites are *adjacent* to which. It
is deliberately not "a rectangle". The rectangular lattice — `structure.kind
= lattice`, with `structure.rows` and `structure.cols` — is *one builder*
that produces a graph of sites; the core engine never reasons about rows and
columns, only about sites, adjacency, and a **distance** the structure
supplies. This matters because a later milestone (M19) will build irregular,
geographic site sets from the same abstraction; nothing in M11a will need to
change for it (DECISIONS #103, #104).

Two settings decide what "adjacent" and "distance" mean on the lattice, and
because they recur throughout this document each is worth its own sentence.
The **von Neumann neighbourhood** (named for the mathematician John von
Neumann) is the four sites that share an edge with a given site — up, down,
left, right — and its distance is the *Manhattan* distance, the sum of the
row difference and the column difference, as a taxi drives on a street grid.
The **Moore neighbourhood** (named for the mathematician Edward Moore) is the
eight sites that share an edge *or a corner* — the four von Neumann sites
plus the four diagonals — and its distance is the *Chebyshev* distance, the
larger of the row difference and the column difference, as a chess king
moves. Under both, the neighbours are exactly the sites at distance 1. The
number of neighbours a site has is called its **degree**, and it will be
written *k* from §4 on: k = 4 under von Neumann, k = 8 under Moore. The
third setting, `structure.boundary`, chooses between a **torus** — the top
row is adjacent to the bottom row and the left column to the right, so the
grid wraps around like the surface of a doughnut and *every* site has
exactly the same degree — and a **bounded** grid with genuine edges and
corners, where edge sites have fewer neighbours. Most of the arithmetic in
this document assumes a torus, because that is what makes "every interior
agent earns exactly this much" an exact statement rather than an
approximation.

**The well-mixed world is a corner of the same abstraction, not a separate
program.** `structure.kind = well_mixed` is the pre-M11a engine, and it is
recovered as the graph in which every site is adjacent to every other and
distance never matters. This is not a figure of speech: the well-mixed path
is *byte-identical* to the engine as it was before the milestone — same
events, same random-number stream, same saved folders on every seeded run —
and that identity is pinned by four negative golden-master tests (spec
Design 9). The point of building it this way is that a spatial experiment
and its aspatial control are the same engine with one setting changed, so
whatever differs between them is attributable to the structure and to
nothing else.

**Local birth and local interaction are two independent dials.** With sites
in place, two things can become local. **Local birth** — a child is placed
in an empty site within reach of its parent rather than "somewhere" —
is governed by `structure.birth_radius` and `structure.birth_decay`.
**Local interaction** — you play your neighbours rather than anyone — is
switched on by `matching.spatial_interaction` and shaped by
`structure.interaction_radius` and `structure.interaction_decay`. Each is a
legitimate configuration on its own. Children can land beside their parents
while everyone still plays everyone (this is exactly what the registered
scenario `the_drifting_frontier` does, deliberately, with spatial
interaction switched off), or agents can play only their neighbours while
newborns land anywhere. Neither configuration is even *expressible* until
the sites exist, which is why the structure and the two localities ship in
one milestone; but they ship with independent switches, and that is what
lets the first spatial experiments say *which* locality did the work.

**One reach kernel, parameterised twice.** Both localities answer the same
question — "given an origin site, which other sites are candidates, and how
much should closer ones be preferred?" — and pdsim answers it with one
functional form. The weight given to a site at distance *d* from the origin
is proportional to

> exp(−β·d) for d ≤ R, and zero beyond,

where **R** is a *support radius* — the hard edge beyond which a site is
simply not a candidate — and **β** (beta) is a *decay* — how steeply
preference falls with distance inside that edge. Two parameters, because
they answer two different questions: R answers "who is reachable at all?",
β answers "among the reachable, how much does closer matter?". As a worked
example, R = 3 with β = 0.5 gives sites at distances 1, 2 and 3 relative
weights of exp(−0.5) ≈ 0.61, exp(−1.0) ≈ 0.37 and exp(−1.5) ≈ 0.22 each,
and nothing at all to a site at distance 4. Four corners of this
two-parameter family recover four familiar worlds (DECISIONS #105):
**R = 1** is the Hammond–Axelrod rule of §7 exactly — children land in, and
partners come from, the immediate neighbourhood, and β is irrelevant
because every candidate sits at the same distance; **β = 0 with R = n** is a
uniform disc, every site within n equally likely; **large β with R = n** is
steeply viscous — distant sites remain reachable but very unlikely, locality
as a strong preference rather than a wall; and **R → ∞ with β = 0** is the
well-mixed world again, arrived at from inside the spatial abstraction by
parameters rather than by a branch. In the engine there is a single function,
`neighbourhood_sample`, that enumerates the sites within R of an origin,
filters them to an eligible set, weights them by exp(−β·d), and draws
without replacement; every place that needs "sites near here" — placing a
child, choosing a partner, choosing who competes for a vacancy — is a call
to that one function with a different eligible set (spec Design 2).

**Viscosity**, finally, is the word this document will use for the property
all of this creates. A population is *viscous* to the extent that it is hard
for lineages and interactions to mix across the space — hard for a family
line to spread far from where it began, hard for two agents at opposite ends
of the grid ever to meet. A well-mixed population has viscosity zero. A
lattice with both radii at 1 is highly viscous, and the fewer neighbours a
site has, the more viscous it is, because a lineage can only advance along
its neighbour links. This one property is the reason the shape matters at
all, and §2 says why.

## 2. Spatial reciprocity: how clustering rescues cooperation

Consider first why cooperation fails in a well-mixed world, using the
numbers the flagship scenario's own things-to-try comparison uses. Two
hundred agents, half unconditional cooperators — the strategy Always
Cooperate, written AllC from here on — and half unconditional defectors —
Always Defect, AllD — with the payoffs T = 5, R = 3, P = 0, S = −1 (defined
properly in §3; for now, R is what two cooperators each earn, T is what a
defector earns from a cooperator, S is what that cooperator earns from the
defector, and P is what two defectors each earn), matches of one round,
and a living cost of 12 energy units per generation that every agent must
pay or die. Under the aspatial `random_k` matcher with k = 5, each agent
plays about ten matches per generation (five it starts, and about five it
is drawn into by others — the calibration guide, §4.2, works this out).
Meeting the population's average 50/50 mix, a cooperator earns roughly
5 × 3 + 5 × (−1) = 10 and nets −2 against the living cost; a defector earns
roughly 5 × 5 + 5 × 0 = 25 and nets +13. The cooperator's kindness is
dissipated across the whole population, and defectors free-ride on it from
anywhere. AllD takes everything — and then, with the cooperators gone,
all-defector income is 0 against a bill of 12 and the whole population
collapses. Nothing about that is subtle: a cooperator has no way to direct
its benefits towards other cooperators.

On a lattice it does. If children are born beside their parents and agents
play only their neighbours, then a cooperator inside a cluster of
cooperators earns the reward payoff R from every neighbour it plays, and a
defector sitting in a defector interior earns only the punishment payoff P
from everyone around it. Cooperators who cluster keep the benefits of
cooperation among themselves. That is **spatial reciprocity**: not
reciprocity in the sense of remembering and repaying — these agents have no
memory at all — but reciprocity produced by geometry, because the agents you
help are the agents who help you, for the sole reason that they are next to
you. Martin Nowak and Robert May (1992) were the first to show cooperators
surviving by clustering on a grid, in a spatial game with no memory and no
strategy more elaborate than "always cooperate" and "always defect"; the
calibration guide, §2.3, discusses the deliberately simplified payoff
matrix they used. Nowak and May's simulation used a different update rule
from anything in pdsim, but their picture is the one to hold in mind
throughout: cooperators survive as clusters, and the interior of a cluster
is a safe place to be a cooperator.

Here is where the platform's own measurement replaces the picture with a
number. How many matches does an agent on the lattice actually play per
generation? A naive reading says four under von Neumann — one against each
neighbour. The engine says **exactly eight**, and it is worth understanding
why rather than trusting it. With spatial interaction on, the
`opponents_per_agent` count is clamped to the neighbours that exist, so on
a fully occupied torus every agent *initiates* one match against each of its
four von Neumann neighbours: four matches. But each of those four
neighbours is doing the same, and it counts you among *its* four, so you are
*drawn into* four more matches that you did not initiate. pdsim does not
remove these duplicates — the same pair meets twice per generation, once
initiated by each side — because that is how the aspatial `random_k` matcher
already behaves and inheriting the rule unchanged keeps the two cases
comparable. Four plus four is eight, and on a torus with full occupancy the
degree is uniform, so there is no variance at all. This was *measured*, not
derived: a temporary probe on a fully occupied 10 × 10 torus under von
Neumann, both kernels at radius 1, found the minimum, mean and maximum
matches per agent all equal to 8.00 in every generation, at two different
values of the opponents-per-agent setting (DECISIONS #139); the equality is
now pinned by a permanent test asserting that every adjacent pair meets
exactly twice and every agent plays exactly eight. Moore doubles it: eight
neighbours, sixteen matches. The consequence for the cluster picture is
that a cluster-interior cooperator's income is **8R, not 4R**, and the
neighbourhood-shape setting is, among other things, an income multiplier.

With that number, the flagship scenario `spatial_reciprocity` can be worked
by hand — and the reader is encouraged to load it and check. Its matrix is
T = 5, R = 3, P = 0, S = −1, one round per match, so every figure below is
income per generation. Each adjacent pair meets twice, so a cooperator earns
2 × 3 = +6 per cooperating neighbour and 2 × (−1) = −2 per defecting
neighbour, while a defector earns 2 × 5 = +10 per cooperating neighbour and
2 × 0 = 0 per defecting one. An interior cooperator with four cooperating
neighbours therefore earns 8 × 3 = 24; an interior defector earns 8 × 0 = 0.
The living cost L must sit strictly between those two incomes for the
economy to be a filter at all — 0 ≤ L < 24 is the *survival window* — and
the scenario places L = 12 at its midpoint. A cooperator with all four
neighbour sites occupied, n of them by cooperators, then earns
6n − 2(4 − n) = 8n − 8 and nets 8n − 20 against the bill: an interior
(n = 4) nets +12, a flat cluster edge (n = 3) nets +4, and a cluster corner
(n = 2) nets −4. Compact clusters thrive; ragged edges erode. A defector
touching exactly one cooperator earns 10 and nets −2 — it starves, slowly —
and only a defector hugging two or more cooperators profits, so parasitism
at the frontier is present but contained. Two of these four payoffs are
overrides of the registry defaults, and both are load-bearing: **P is set to
0** so that a defector interior earns *nothing* against the living cost
(at the default P = 1 with eight Moore neighbours a defector in a solid
block would earn 16 per generation, which may well clear the bill, in which
case nobody starves and the scenario silently demonstrates nothing), and
**S is set to −1** because with P at 0 the strict ordering of §3 needs S
below it, and because it makes cluster edges actively bleed energy rather
than merely fail to earn it (DECISIONS #111, #115).

Notice what kind of argument this is. The flagship's story is
**ecological**: absolute income measured against a survival bill, with
agents living or dying on whether their neighbourhood feeds them. It says
nothing about *relative* fitness, and its matrix — as §3 will show — is not
of the special kind under which the famous b/c > k rule of §4 is even
defined. That the two arguments point the same way is a coincidence of this
scenario, not an identity between them; §6 returns to the distinction,
because it is the easiest thing in this whole subject to blur.

## 3. What makes a Prisoner's Dilemma: the full constraint structure on T, R, P, S

The Prisoner's Dilemma (PD) is a two-player game in which each player
either cooperates or defects, and four payoffs describe every outcome. In
the notation the field has used since Robert Axelrod and William Hamilton's
1981 paper in *Science*, and pdsim uses in its Parameter Registry:

- **T**, the *temptation*: what you earn by defecting while the other
  player cooperates;
- **R**, the *reward*: what each earns when both cooperate;
- **P**, the *punishment*: what each earns when both defect;
- **S**, the *sucker's payoff*: what you earn by cooperating while the
  other defects.

pdsim's registered defaults are T = 5, R = 3, P = 1, S = 0 — Axelrod and
Hamilton's own illustrative values, and the field's common reference point.
Three layers of constraint sit on these four numbers. The first two make
the game a Prisoner's Dilemma; the third decides whether a particular family
of results applies to it at all. The calibration guide, §2.1–§2.4, treats
all three at greater length; this section states each, works it on the
defaults, and says what goes wrong without it.

### 3.1 The ordering: T > R > P > S

Each inequality rules out a different way of not being a dilemma. **T > R**
says that defecting against a cooperator pays more than cooperating with
one — the temptation is real. Without it, cooperating against a cooperator
would be the best thing that can happen to you, and the problem would be
one of coordination rather than of temptation. **P > S** says that
defecting against a defector pays more than cooperating with one. Without
it, being the sucker would be no worse than mutual defection, and the game
would be the one usually called Chicken or Hawk–Dove, where the last thing
you want is for both players to defect. Together, T > R and P > S say that
*defection is better whatever the other player does*: on the defaults,
against a cooperator 5 beats 3, and against a defector 1 beats 0. The middle
inequality, **R > P**, says that mutual cooperation is nevertheless better
for both than mutual defection: two cooperators collect 3 each where two
defectors collect 1 each. Individually rational choices produce a
collectively worse outcome, and that is the dilemma. pdsim enforces the
ordering by default through `game.enforce_pd_ordering`; the guide's §2.3
explains when switching it off is legitimate.

### 3.2 The alternation condition: 2R > T + S

The ordering alone is not enough, and Axelrod and Hamilton's 1981 paper
states the second condition and its rationale in a note attached to the
payoff definition. Read it as a comparison over two rounds. Two players who
cooperate steadily collect R + R each. Two players who *take turns
exploiting each other* — you defect while I cooperate, then I defect while
you cooperate — collect T once and S once each. The condition says steady
cooperation must pay more than alternating exploitation. On the defaults,
2R = 6 against T + S = 5, so it holds with a margin of 1.

What goes wrong without it is instructive. Take T = 7, R = 3, P = 1, S = 0.
The ordering still holds — 7 > 3 > 1 > 0 — so this still looks like a
Prisoner's Dilemma. But 2R = 6 while T + S = 7. Two players who agree
"you cheat me this round, I cheat you next" collect 7 apiece over two
rounds against the 6 they would get from cooperating steadily. The best
joint strategy is now organised mutual exploitation, and the game is no
longer about cooperation in any recognisable sense. pdsim enforces this
condition through `game.enforce_alternation_constraint`.

### 3.3 Additivity: T − R = P − S, and the donation game

The third condition pdsim does *not* enforce, and it decides whether the
central result of §4 applies to your matrix at all. To see what it says,
read the cost of cooperating off the matrix twice. Against a cooperator you
could have had T and you took R, so cooperating cost you **T − R**. Against
a defector you could have had P and you took S, so cooperating cost you
**P − S**. **Additivity** — also called *equal gains from switching*; the
guide's terminology note explains that both names are in use — is the
statement that these two numbers are the same: cooperating costs you a
fixed amount regardless of what the other player does.

The natural situation in which this holds is the **donation game**.
Cooperating means paying a cost *c* so that the other player receives a
benefit *b*; defecting means paying nothing and providing nothing. Then
T = b (you receive the benefit and pay nothing), R = b − c (you receive it
and pay), P = 0 (nothing changes hands), S = −c (you pay and receive
nothing). Check it: T − R = b − (b − c) = c, and P − S = 0 − (−c) = c. The
same number, by construction — and the benefit reads off consistently too,
T − P = b and R − S = b.

**pdsim's defaults fail additivity.** T − R = 5 − 3 = 2, while
P − S = 1 − 0 = 1; two does not equal one. The defaults are a perfectly
valid Prisoner's Dilemma — both conditions above hold — that is simply not
a donation game. And the consequence is sharper than "the donation-game
results don't apply": under a non-additive matrix, the ratio "b/c" is
**undefined**. There are two defensible readings of the benefit
(T − P = 4, or R − S = 3) and two of the cost (T − R = 2, or P − S = 1),
giving four defensible ratios: 4 ÷ 2 = 2.0, 4 ÷ 1 = 4.0, 3 ÷ 2 = 1.5,
3 ÷ 1 = 3.0. Against the von Neumann threshold of §4, k = 4, two of these
clear it and two fail — so a user could "predict" either outcome simply by
choosing a definition. That is the signature of a malformed question, not
a hard one (DECISIONS #111).

The registered scenario `donation_game_threshold` therefore uses
**T = 5, R = 4, P = 0, S = −1**. Check: T − R = 1 and P − S = 1, so c = 1;
T − P = 5 and R − S = 5, so b = 5; b/c = 5, unambiguously. And notice that
additivity with P = 0 *forces* the sucker payoff negative: S = P − c = −1
is not a stylistic choice but the only value that keeps the matrix
additive with the punishment at zero. (This is why the platform's payoff
parameters admit negative values at all.) The guide's §2.4 gives a recipe
for building additive matrices with every payoff non-negative if that is
what you need — (6, 5, 1, 0) is the same donation game shifted up by one.

The app carries a live guard for this. Among the derived readouts beside
the payoff widgets, the **additivity readout** inspects the four live
payoff values and reports either "additive: b = 5, c = 1, b/c = 5" or "not
additive — the b/c > k threshold does not apply", with the one-line reason
that cooperating costs a different amount against a cooperator than against
a defector. Because the payoffs are live sliders, a user can nudge one and
silently destroy the thing being demonstrated; the readout is what says so.

## 4. The Ohtsuki threshold: what b/c > k claims, and why k appears at all

The best-known result about cooperation on a graph is the "simple rule" of
Hisashi Ohtsuki, Christoph Hauert, Erez Lieberman and Martin Nowak, published
in *Nature* in 2006. Stated plainly: on a regular graph where every
individual has exactly *k* neighbours, natural selection favours cooperation
if and only if the benefit-to-cost ratio of helping exceeds the number of
neighbours —

> **b/c > k.**

"Favours" has a precise meaning here. A single cooperator introduced into a
population of defectors either takes over the whole population (reaches
*fixation*) or disappears. Under no selection at all it would take over
with probability 1/N, N being the population size, since it is one of N
equally lucky individuals. Cooperation is *favoured* when a cooperator's
fixation probability exceeds that neutral 1/N.

The rule is compact enough to memorise and easy enough to misapply, so
here is the assumption set it rests on, verified against the paper and its
Supplementary Information (SI) rather than reconstructed:

- **Donation-game payoffs.** Cooperators pay c so that each neighbour
  receives b; the matrix is exactly the additive one of §3.3.
- **One-shot interactions.** Each individual plays each of its k neighbours
  once, and its payoff is the *sum* of those k one-shot games. There is no
  repetition anywhere in the derivation — no memory, no reciprocity, no
  Tit for Tat.
- **Death-birth updating.** In each step a *random* individual dies; its
  k neighbours then compete for the vacated site, and one of them places a
  copy of itself there with probability proportional to its fitness.
- **Fitness (1 − w) + w × payoff, with weak selection.** The parameter w
  tunes selection intensity: w = 1 is strong selection (fitness is payoff),
  w ≪ 1 is *weak* selection, where payoff differences barely register.
  The rule is derived in the weak-selection limit.
- **Large population, N ≫ k.**
- **Pair approximation on loop-free graphs.** The mathematical technique
  is formulated for Bethe lattices — infinite trees, graphs with no closed
  loops — and the authors themselves state that discrepancy on graphs full
  of loops, such as square lattices, is expected. A square lattice is
  nothing but loops (any four mutually adjacent sites form one), so the
  rule is an approximation there, and known to be.

**Why k appears at all.** The most illuminating fact about the rule is that
the threshold is not some fixed number but the *degree of the graph*, and
the reason is the death-birth step: k counts the **competitors for the
vacated site**. When an individual dies, the individuals who contest the
empty seat are precisely its k neighbours, so a strategy's success depends
on how it fares in a k-way contest among neighbours — and the benefit a
cooperator's neighbourhood generates for it must outweigh the cost of
helping, spread over those k contestants.

The heart of the derivation, in words an undergraduate can hold on to, is
this. Under death-birth updating on a graph, like tends to sit beside like,
because offspring are placed next to their parents. The pair approximation
tracks how much: it shows the dynamics settling quickly into a state in
which an individual competing for a vacated site has, among its k − 1
*other* neighbours (all of its neighbours except the vacant site itself),
on average **one more** neighbour of its own strategy than a competitor of
the opposite strategy has — the paper's slow-manifold correlation result,
in its own notation q(same|same) − q(same|other) = 1/(k − 1), which times
the k − 1 other neighbours gives exactly one. A cooperator, in other words,
is guaranteed on average one ally that a defector in the same position
lacks. That ally is worth b (the benefit the ally donates). Being a
cooperator costs c to each of k neighbours, hence c·k. The extra ally pays
for the cooperator's costs when b > c·k, that is, when b/c > k. That
sentence is not the proof — SI §1 of the paper is the proof, for
death-birth, with the rule at SI §1.5 — but it is why the rule looks the
way it does.

Two siblings come from the same source, and both matter to pdsim. Under
**imitation updating** — a random individual is chosen and *copies* a
strategy in proportion to fitness rather than dying and being replaced —
the rule shifts to **b/c > k + 2** (SI §2). And under **birth-death
updating** — an individual is first chosen to
reproduce with probability proportional to fitness, and its offspring then
replaces a random neighbour — SI §3, titled "'Birth-death' (BD) updating",
proves that a defector's fixation probability exceeds 1/N which exceeds a
cooperator's for **any** b > c > 0: selection never favours cooperators
under birth-death, at any benefit-to-cost ratio. The calibration guide's
§7.3 states this and draws the practical conclusion — investigate spatial
reciprocity under death-birth, which is pdsim's default — and the
platform's advisories backlog (`docs/ADVISORIES.md`, item A4, an in-app
warning queued for a later milestone) points at that same SI §3; the
pinpoint was checked in the verification pass and is correct as shipped.

**The design consequence, worked** (DECISIONS #103). Choose b = 5 and
c = 1. The donation-game matrix is T = 5, R = 4, P = 0, S = −1, additive
by construction, b/c = 5. Under the von Neumann neighbourhood k = 4, and
5 > 4: the rule says cooperation is favoured. Under Moore k = 8, and
5 < 8: the rule says it is not. Same grid, same payoffs, same population —
opposite prediction from one enum flip. This is the configuration
`donation_game_threshold` packages, and it ships under von Neumann so that
the default view is the case the rule says should succeed.

How pdsim maps onto the assumption set is worth stating exactly, because
the gap is the subject of §6. `dynamics.moran_rule = death_birth` with
`fixed_n_death_rule = pure_random` is the right shape: a random individual
dies, and — under a lattice, since M11a — the competition for the vacated
site is drawn from the dead agent's neighbourhood through the birth kernel
rather than from the whole population; at radius 1 every candidate sits at
distance 1, the kernel factors cancel, and the draw is exactly
fitness-proportional over the neighbours (DECISIONS #132). One round per
match with only AllC and AllD on the roster makes the interactions
one-shot. What differs is *what fitness is* — and that is §6(a).

## 5. The generalisation: when the matrix is not additive

The rule of §4 needs b and c to exist, and §3.3 showed that they do not
exist for a non-additive matrix such as pdsim's defaults. Corina Tarnita,
Hisashi Ohtsuki, Tibor Antal, Feng Fu and Martin Nowak (2009), in the
*Journal of Theoretical Biology*, proved that for a very wide class of
population structures the question "is cooperation favoured?" nevertheless
comes down to a single number, the **structure coefficient σ** (sigma),
and one inequality. In pdsim's payoff names,

> **σR + S > T + σP.**

Read it as a weighted comparison: the left side is what cooperation earns,
with the "cooperator meets cooperator" outcome weighted up by σ; the right
side is what defection earns, with "defector meets defector" weighted up
the same way. Two facts about σ give it its meaning, both from the paper.
**σ = 1** turns the inequality into R + S > T + P, which is exactly the
classical *risk-dominance* condition of game theory — the structureless
case. **σ > 1** means the diagonal outcomes — the two "both players did the
same thing" cells, R and P — weigh more than the off-diagonal ones, and
that is precisely the sense in which population structure helps
cooperation: it makes like meet like more often. The paper writes effective
payoff as 1 + δ × payoff and takes the weak-selection limit δ → 0, the same
regime as §4 in different notation.

**The value of σ for a grid.** For death-birth updating on a regular graph
of degree k, in a large population with low mutation, the paper gives
(its equation 17)

> **σ = (k + 1) / (k − 1),**

and it is careful about where the value comes from: it credits Ohtsuki and
colleagues' 2006 online material, equation 24, via the relation
σ = ((b/c)* + 1) / ((b/c)* − 1), where (b/c)* is the critical ratio at
which cooperation becomes favoured. The reader can confirm that the two
results are the same statement in two vocabularies. Substitute the
donation-game matrix into the σ inequality: σ(b − c) − c > b, so
b(σ − 1) > c(σ + 1), so b/c > (σ + 1)/(σ − 1); with σ = (k + 1)/(k − 1)
the right-hand side is ((k + 1) + (k − 1)) / ((k + 1) − (k − 1)) = 2k/2 = k.
The σ condition collapses to b/c > k exactly when the matrix is additive,
which is what a generalisation should do. For a finite population the paper
refines the value (its equation 18) to

> **σ = ((k + 1)·N − 4k) / ((k − 1)·N),**

which tends to (k + 1)/(k − 1) as N grows and is measurably smaller for the
modest populations pdsim runs: at k = 4, a 6 × 6 lattice gives 1.52, a
10 × 10 gives 1.61, a 20 × 20 gives 1.65, and the infinite-population value
is 5/3 ≈ 1.67 (the calibration guide's §2.5 tabulates these; the numbers
here are its numbers). Small lattices are less friendly to cooperation than
the textbook figure suggests. The paper also gives σ = (N − 2)/N for a
finite well-mixed population — below 1, so finite mixing is slightly
*hostile* to the diagonal.

**Worked, on the defaults.** Four neighbours, large N, σ = 5/3. Left side:
(5/3) × 3 + 0 = 5. Right side: 5 + (5/3) × 1 ≈ 6.67. Five is less than
6.67, so cooperation is not favoured — one clear answer where §3.3's ratio
test gave four contradictory ones. And, as a further illustration of the
guard at the end of §2: apply the same test to the flagship's matrix
(5, 3, 0, −1). Left side: (5/3) × 3 + (−1) = 4. Right side: 5 + 0 = 5. Not
favoured either — and yet the flagship shows cooperator clusters thriving.
There is no contradiction, because the σ test answers a question the
flagship is not asking: it concerns the fixation of a mutant in a
weak-selection Moran process, while the flagship is an ecology of absolute
incomes against a bill.

**The scope limit, carried in spirit from the paper.** The proof requires
that *either* the birth step *or* the death step be independent of payoff.
Death-birth qualifies (the dying individual is chosen at random). Birth-death
does not, and the authors say so explicitly: they expect the σ condition to
hold there too, but it needs a different proof they had not given. And the
second caveat of §4 travels with σ as well: the derivation is a pair
approximation, formulated for loop-free graphs, so on a square lattice σ is
a compass, not a prediction. The calibration guide, §2.5, works all of this
out in full and carries both caveats; nothing here should be read as
differing from it.

## 6. Two honesty caveats, and what we actually measured

Everything in §4 and §5 is derived under assumptions, and pdsim satisfies
some of them and not others. Two caveats therefore travel with the
threshold wherever it appears in this platform, and both are worded
consistently across the scenario texts, the calibration guide and this
document.

**(a) One-shot weak selection versus this engine's strong selection.** The
published rule assumes fitness (1 − w) + w × payoff with w tuned towards
zero. pdsim's fixed-population breeder draw has **no such parameter**. When
a vacancy opens, each candidate's weight is its **accumulated energy**
shifted by the poorest candidate's — w_i = e_i − min(e) — with no
selection-intensity dial anywhere on that path (DECISIONS #117); the
calibration guide, §7.2, is the full account. Two consequences follow, and
they are the consequences the platform states rather than stronger ones it
once conjectured. First, selection begins at *exactly zero*: at the start of
a run every founder holds identical energy, every shifted weight is zero,
a uniform fallback fires, and the draw is neutral, with no fitness content
whatsoever. Selection then strengthens *from nothing* as stocks diverge —
and a measurement over 7,200 breeder draws found that the spread of the
shifted weights reaches a plateau early and wanders around it thereafter,
rather than growing without bound (DECISIONS #114, #117). Second, because
fitness reads a lifetime **stock** rather than a per-generation **flow**,
the draw partly selects for **age** rather than strategy: an incumbent has
had longer to accumulate than a newborn, and at the textbook offspring stake
of zero a newborn effectively cannot breed until it has accumulated. So we
cannot approach the w → 0 (or δ → 0) limit in which the threshold was
derived; selection in this engine starts at zero and is otherwise strong.
The one-shot half of the assumption set, by contrast, *is* satisfied by the
threshold scenario, which sets one round per match with only AllC and AllD
on the roster precisely so that no repetition or reciprocity enters —
noise, memory depth and every reciprocity parameter are inert there, and
the scenario text says so.

**(b) The threshold is a calibration compass, not a prediction.** This is
the phrase the platform uses everywhere, and it is not a hedge but a
measured finding. Before the scenario shipped, the prescribed configuration
was run by hand: the donation matrix (5, 4, 0, −1), one round per match,
AllC and AllD only, asynchronous `fixed_n` with N = 100 on a 10 × 10 torus,
`death_birth` with the `pure_random` reaper, both kernels at radius 1,
spatial interaction on, random founding layout, no mutation, 150
generation-equivalents — under von Neumann (k = 4, which b/c = 5 clears)
and under Moore (k = 8, which it fails). A single seed pair was ambiguous,
so **twenty seeds per shape** were run. Von Neumann: AllC fixed in 11 of 20
runs, AllD in 8, one still coexisting at the horizon, mean final cooperator
share **0.596**. Moore: AllC fixed in 10 of 20, AllD in 7, three
coexisting, mean final share **0.569** (DECISIONS #140). Directionally von
Neumann sits a hair above Moore, but the separation — one seed in twenty —
is well inside sampling noise. There was **no visible b/c > k reversal** at
this configuration, and nothing was tuned to force the textbook picture.
The honest reading is the one the scenario's things-to-try teaches: state
the prediction, switch to Moore, run it, and expect very little visible
change — the gap between the prediction and the observation *is* the
weak-selection lesson (DECISIONS #152). Drift plus strong selection washes
the k-dependence out at these settings; the compass still points where the
prediction cannot.

Two further honesty facts belong here. The default seed of
`donation_game_threshold` was **curated**: a twelve-seed check during the
scenario's validation split six–six between AllC fixing and AllD fixing,
and because the scenario's frozen intent is that the default view shows
cooperation succeeding, a cooperation-fixing seed ships — with a sentence
in the scenario text saying so plainly (DECISIONS #151). The default view is
therefore not typical; at this selection strength any single run is a
fixation gamble, and the twenty-seed measurement above is the honest
picture. And the conceptual guard of §2 must be restated in its final form:
the flagship `spatial_reciprocity` is an **ecological** story — absolute
income against a survival bill, with a non-additive matrix under which
"b/c" is not defined at all — while b/c > k concerns **relative fitness in
a Moran process under weak selection**, which is `donation_game_threshold`'s
story and only that scenario's. The two arguments happen to point the same
way. They are not the same argument (DECISIONS #111, #151).

## 7. The lineage: Hammond–Axelrod and Kaznatcheev–Shultz

M11a exists to prepare the ground for M12's replication of Ross Hammond and
Robert Axelrod's 2006 model of ethnocentrism, and both that model and its
most important follow-up are now on verified footing.

**Hammond and Axelrod (2006).** The stage is a 50 × 50 lattice with — in
the paper's own words — "wraparound borders so that every site has exactly
four neighboring sites": a **torus** with **von Neumann** geometry, stated
in the model section and again in the appendix. Each agent has a *potential
to reproduce* (PTR), reset to a base value of 12% every period. Agents play
one-shot Prisoner's Dilemma donations with each of their four neighbours:
giving help costs the giver one percentage point of PTR (1%) and adds three
to the receiver (3%). Then each agent, in random order, gets one chance to
reproduce with probability equal to its PTR, cloning a child into an
adjacent empty site if one exists — local reproduction, exactly M11a's
birth kernel at R = 1. Every agent then faces a flat 10% chance of dying,
and one random immigrant arrives per period. Mutation is 0.5% per trait,
and the standard run is 2,000 periods. In the standard case, roughly 76% of
agents end up *ethnocentric* — cooperating with their own colour tag and
defecting against others — and roughly 74% of interactions are
cooperative. The paper's robustness checks halve and double the cost, the
number of colours, the mutation rate, the immigration rate, the lattice
size and the run length, and ethnocentrism survives all of it. What they
never do is remove the lattice. It is not a parameter; it is the stage. The
M10 explainer says why that matters for the *order* of pdsim's milestones —
tags without a lattice have no regions, no borders and no interior to
defend — and M11a's job was to build the stage.

**Kaznatcheev and Shultz (2011).** The follow-up pulled the two ingredients
of that model apart and found something more interesting than "space
matters". On the same 50 × 50 torus with four adjacent neighbours,
holding the cost c = 0.01 fixed and varying the benefit b, they compared the
full model with a version that keeps local child-placement but has *no
tags at all*. Their result is in their title — *ethnocentrism maintains
cooperation, but keeping one's children close fuels it* — and its timing is
the point. Local child-placement without tags does about as well as the
standard model **up to around 300 cycles**, which is the figure the M10
explainer quotes. That number is where the world population *saturates* —
"at about 300 cycles, on average", a timing the paper attributes to earlier
work by Shultz, Hartshorn and Kaznatcheev (2009) — and it is where the
ethnocentric strategies pull ahead of the *humanitarians*, their term for
agents who cooperate with everyone regardless of tag. After
saturation, expanding clusters collide, and only then do tags become
critical, because only then is there a border to defend. One nuance
travels with the result: the effect of tags in *maintaining* cooperation is
strongest in competitive environments where the benefit-to-cost ratio is
low; at their b/c = 4 the no-tag decay disappears altogether. The
conclusion, as the M10 explainer put it: **viscosity creates cooperation;
tags preserve it once space runs out.** That is the scientific reason
population structure (M11) precedes tags (M12) in this platform, and it is
also the reason the registered scenario `the_filling_grid` — a small block
of agents expanding into an empty grid — is described as the Kaznatcheev
and Shultz regime.

## 8. What the platform measured that the papers could not

Three findings from the milestone are worth setting beside the literature,
because each is a measurement of *this* engine rather than a result carried
over from a paper.

**Exactly eight matches per agent per generation.** As §2 reported, on a
fully occupied von Neumann torus every agent plays exactly 8 matches per
generation — 4 initiated and 4 received — with no variance, at any
opponents-per-agent setting of 4 or more; Moore gives 16 by the same
arithmetic. The measurement (DECISIONS #139) also confirmed that the engine
does not deduplicate: an engine that did would have shown 4. The number is
what the flagship's living cost and the Economy panel's spatial calibration
branch (DECISIONS #154) are built on.

**No visible reversal at strong selection.** As §6 reported in full, the
b/c > k configuration run at twenty seeds per shape gave 0.596 against
0.569 — inside sampling noise, no reversal (DECISIONS #140). Ohtsuki and
colleagues could not have measured this because their model *has* the
weak-selection dial and uses it; this engine does not, and the honest
finding is what a strong-selection stock-fitness engine does with the same
configuration.

**The Filling Grid freeze, and an open question.** `the_filling_grid`
starts sixty agents — thirty AllC, thirty AllD — packed into a centred
6 × 10 rectangle on a 20 × 20 lattice, with 340 empty sites around them and
the carrying capacity resolving to the site count, 400. It uses the Moore
neighbourhood, ten rounds per match, the default payoffs (5, 3, 1, 0), and
a living cost of 40 — deliberately the anti-flagship configuration, in
which a saturated defector interior earns 16 × 10 × 1 = 160 per generation
and never starves. On the shipped seed the fill happens as designed (sixty
agents become roughly 250 by generation 5, and cooperation's share rises
from 0.50 to about 0.61), and then growth **stops**, at roughly 265 of the
400 sites, with zero deaths and near-zero births for the rest of the
300-generation run. The mechanism, diagnosed from the event stream, is an
interaction of three separately-designed rules: births are admitted only up
to the free-seat count under the carrying capacity, and when seats are
scarce the *richest* eligible parents are admitted first; an admitted
parent must then find an empty site within its birth kernel — Moore
radius 1 — and a parent that cannot pays nothing and stays eligible, but its
admission slot is spent for that generation. The richest parents are the
all-cooperator *interior*, earning 480 per generation, which is exactly the
cohort with no empty site in reach; the poorer frontier parents, every one
above the breeding threshold and beside an empty site, never rank inside
the quota. The signature is verifiable in the app's Economy panel: from
about generation 6 onward, 'Blocked parents this generation' equals
**exactly** 400 minus the population, every generation (DECISIONS #153).
The scenario's things-to-try invites the reader to switch P to 0 — after
first unticking 'Enforce PD payoff ordering (T > R > P > S)', because this
scenario ships S = 0 and P = 0 would tie them — and rederive: all-defector
pockets then earn 16 × 10 × 0 = 0 against the bill of 40 and starve,
freeing interior sites. That was run, once, headlessly (DECISIONS #155),
and the honest report is that the freeze broke only *transiently*:
sixty-eight defectors starved in punctuated waves, cooperation's share climbed to
about 0.91, the freed sites were refilled — and then, once every surviving
defector held at least one cooperator contact, deaths went to zero, births
to near-zero, and the population sat flat at **235 of 400**, thirty sites
*below* the original freeze. The deadlock is indifferent to the payoffs; it
is a property of the admission mechanism itself.

Whether the global quota should be consumed by *admission*, as it is today,
or by *successful placement* — equivalently, whether unfilled quota should
roll to the next-richest eligible parent, or whether admission should see
placement feasibility at all — is logged as **OPEN QUESTION #159**,
deliberately unresolved, with a deadline of M11b at the latest and
explicitly before M12. It was not slipped into M11a because any change to it
alters the engine's random-number consumption and is therefore a breaking
change requiring its own golden masters. Why it matters is the stake named
in that entry: the Hammond–Axelrod frontier replication of §7 runs at a
carrying capacity equal to the site count, with rich interior incumbents
and poor frontier parents — precisely the configuration that starves the
frontier of admission quota — so the question must be settled before that
scenario can mean anything. This document states that the question is open,
and why; it does not resolve it, and it makes no claim about what the
filling regime's endgame will be under any rule beyond what was measured
above.

## 9. References

All entries below were verified against publisher records or
author-institutional deposits of the published versions during the M11a
literature verification pass (2026-08-14, DECISIONS #161); the four entries
marked † were the gated claims of DECISIONS #103 and #111, and the others
were already verified for the calibration guide's References, whose
annotations they reuse. Nothing else is cited in this document.

**Axelrod, R. & Hamilton, W. D. (1981).** The evolution of cooperation.
*Science* 211(4489), 1390–1396. DOI: 10.1126/science.7466396. — Source of
the T > R > P > S and 2R > T + S conditions (Figure 1 caption), the
rationale for the second condition (note 17), and the illustrative values
5, 3, 1, 0 that pdsim uses as defaults.

**Hammond, R. A. & Axelrod, R. (2006).** † The evolution of ethnocentrism.
*Journal of Conflict Resolution* 50(6), 926–936.
DOI: 10.1177/0022002706293470. — Source of the ethnocentrism model of §7:
the 50 × 50 toroidal lattice with von Neumann geometry, one-shot donations
at 1% cost and 3% benefit of a 12% base potential to reproduce, local
reproduction into adjacent empty sites, 10% death rate, one immigrant per
period, ~76% ethnocentric outcome, and the robustness table that never
removes the lattice. Verified from the authors' institutional deposit.

**Kaznatcheev, A. & Shultz, T. R. (2011).** † Ethnocentrism maintains
cooperation, but keeping one's children close fuels it. *Proceedings of the
33rd Annual Conference of the Cognitive Science Society*, 3174–3179. —
Source of the finding that local child-placement without tags matches the
full model up to around 300 cycles, of the ~300-cycle saturation timing
(which the paper attributes to Shultz, Hartshorn & Kaznatcheev 2009), of
tags becoming critical after saturation, and of the b/c-dependence of the
tags-maintain effect. Verified from the publisher-hosted full text.

**Nowak, M. A. & May, R. M. (1992).** Evolutionary games and spatial chaos.
*Nature* 359, 826–829. DOI: 10.1038/359826a0. — The paper that first showed
cooperators surviving by clustering on a grid, using the single-
free-parameter matrix discussed in the calibration guide's §2.3.

**Ohtsuki, H., Hauert, C., Lieberman, E. & Nowak, M. A. (2006).** † A simple
rule for the evolution of cooperation on graphs and social networks.
*Nature* 441, 502–505. DOI: 10.1038/nature04605. — Source of the b/c > k
threshold and its full assumption set (§4): the donation-game matrix,
one-shot summed payoffs, fitness (1 − w) + w × payoff with weak selection,
N ≫ k, pair approximation on Bethe lattices with looped-graph discrepancy
expected; death-birth derived in Supplementary Information §1 with the rule
at §1.5 via the correlation result q(same|same) − q(same|other) = 1/(k − 1);
imitation b/c > k + 2 in SI §2; and SI §3, "'Birth-death' (BD) updating",
proving cooperators are never favoured for any b > c > 0. Verified from the
full Supplementary Information (co-author Hauert's institutional reprint).

**Tarnita, C. E., Ohtsuki, H., Antal, T., Fu, F. & Nowak, M. A. (2009).** †
Strategy selection in structured populations. *Journal of Theoretical
Biology* 259(3), 570–581. DOI: 10.1016/j.jtbi.2009.03.035. — Source of the
structure coefficient and the condition σR + S > T + σP (§5), the
risk-dominance interpretation of σ = 1, the regular-graph value
σ = (k + 1)/(k − 1) (their eq. 17, credited by them to Ohtsuki et al. 2006's
online material eq. 24 via σ = ((b/c)* + 1)/((b/c)* − 1)), the finite-N
formula ((k + 1)N − 4k)/((k − 1)N) (their eq. 18), σ = (N − 2)/N for a
finite well-mixed population, and the scope limit excluding birth-death
updating from the proof. Verified from the Harvard DASH open-access deposit
carrying the publisher DOI.

*Provenance note. The four entries marked † were verified on 2026-08-14 in
the design layer against publisher records or author-institutional deposits
of the published versions, discharging the verification debt recorded in
DECISIONS #103(ii) and #111(d); DECISIONS #161 is the consolidated record,
and the calibration guide's References and `docs/ADVISORIES.md`'s A4
pinpoint were confirmed correct as shipped in the same pass. Shultz,
Hartshorn & Kaznatcheev (2009) appears in §7 only as Kaznatcheev & Shultz's
own attribution for the saturation timing and carries no entry here; it is
listed in the M10 explainer's References. Everything else in this document
that is not attributed to one of the entries above — the exactly-eight
measurement, the twenty-seed no-reversal result, the shifted-weight
plateau, and the Filling Grid freeze — is pdsim's own measurement, and each
is labelled with the DECISIONS entry that records it.*
