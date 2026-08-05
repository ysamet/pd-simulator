# Calibrating Payoffs and the Energy Ledger

> A practical guide to choosing the four Prisoner's Dilemma payoffs and the seven
> energy-ledger quantities when you are modelling a real situation in pdsim.
>
> Written for a reader who is comfortable with arithmetic and algebra but has
> never taken a game theory course. Every symbol is defined, every acronym is
> spelled out, and every number is worked rather than asserted.

---

## §0 — What this is, and when you don't need it

pdsim asks you for four payoff numbers and, if you switch on the energy economy, seven more numbers describing what it costs to live and what it costs to reproduce. Nothing in the interface tells you the most important fact about those first four numbers:

**What a payoff number *means* depends on a setting somewhere else in the panel.**

Under one setting, the payoffs are a comparison — only the gaps between them matter, and the absolute sizes are yours to choose freely. Under another setting, the very same numbers become literal income, measured against a literal survival bill, and every one of them matters absolutely. A pair of payoff matrices that produce identical simulations in the first case can produce a thriving population and a dead one in the second.

This guide is about that difference and everything that follows from it.

### What this guide is not

It does not log decisions — `DECISIONS.md` does that. It is not the authority on default values or allowed ranges — `PARAMETERS.md` is, and it is generated directly from the code, so it cannot drift. It is not the deeper derivation of the energy economy — `docs/explainers/M10-growth-economy-explainer.md` is, and this guide cross-references it rather than repeating it.

### When you can stop reading

Two situations make the whole calibration question disappear.

**If the run mode is Tournament**, nothing evolves. A fixed cast of agents plays repeated matches and the scores simply accumulate, exactly like Robert Axelrod's original computer tournaments. Payoffs are a scoreboard. Pick any numbers satisfying the constraints in §2 and move on.

**If reproduction is by imitation and your selection rule is rank-based** — that is, `tournament_k` or `truncation` — then the rule only ever asks "who scored higher?" and never "by how much?". Any change to the payoffs that preserves the ordering of scores changes nothing at all. §3 explains why.

Everything else in this guide is for people who have switched on the energy economy, or who are using a selection rule that reads score *differences* rather than score *rankings*.

---

## §1 — Two regimes, and the one table worth memorising

pdsim offers two ways for a population to change over time.

**Imitation.** The population size never changes. Each slot in the next generation copies some current agent's strategy, and who gets copied depends on scores. Nobody is born, nobody dies, nobody eats. This is cultural transmission: strategies spread by being adopted.

**The energy economy.** Agents hold a stock of energy. They earn it by playing, pay it out every generation simply to stay alive, and have offspring when they can afford to. Nobody copies anyone. An agent whose earnings cannot cover its bills slides toward zero energy and dies. This is demographic transmission: strategies spread by their carriers out-surviving everyone else.

Now consider two ways of changing a payoff matrix that leave the *strategic* content untouched.

**A shift** adds the same constant to all four payoffs. Turning (5, 3, 1, 0) into (9, 7, 5, 4) is a shift by 4.

**A scaling** multiplies all four payoffs by the same positive constant. Turning (5, 3, 1, 0) into (50, 30, 10, 0) is a scaling by 10.

Neither operation changes which action is better in any situation. Both leave every strategic conclusion intact. You would expect both to be free. Here is what actually happens.

| | **Shift** (add a constant to all four payoffs) | **Scaling** (multiply all four payoffs) |
|---|---|---|
| **Imitation** | Free — *but only if every agent plays the same number of rounds* | **Not free.** Multiplying payoffs by 10 is the same experiment as multiplying the selection intensity by 10 |
| **Energy economy** | **Not free.** Payoffs become income that accumulates over however many rounds an agent plays, and zero energy is an absolute point where agents die | Free — *provided you multiply the whole ledger by the same factor* |

Each regime is immune to exactly one of the two operations. And in both regimes it is the opposite one from what intuition suggests.

The rest of this guide is that table, unpacked.

### The practical licence hidden in the bottom-right cell

Because the energy economy is exactly scale-invariant, **only ratios matter there.** Income relative to the living cost. The offspring stake relative to net income. The reproduction threshold relative to the stake. The absolute size of the numbers is yours to choose for readability — you can work in units of 1 or units of 1,000 and get identical dynamics.

The one way to lose this licence is to scale the payoffs and forget one of the ledger quantities. §6 lists all seven so you can check them off.

---

## §2 — The constraint structure: what makes a Prisoner's Dilemma

### §2.1 — The ordering, and the two facts that create the dilemma

Two players each choose to cooperate or defect. Four outcomes, four payoffs:

> **T > R > P > S**

- **T** — the *temptation* payoff. What you earn by defecting while the other player cooperates.
- **R** — the *reward* payoff. What each player earns when both cooperate.
- **P** — the *punishment* payoff. What each player earns when both defect.
- **S** — the *sucker* payoff. What you earn by cooperating while the other player defects.

pdsim's defaults are T = 5, R = 3, P = 1, S = 0. These are not arbitrary: they are the illustrative values from the 1981 paper in *Science* by Robert Axelrod and William Hamilton that established the modern study of cooperation, and they remain the field's common reference point.

Two facts follow from the ordering, and together they are the dilemma.

**Fact one: defection is better whatever the other player does.** If the other cooperates, you can take R by cooperating or T by defecting — and T > R, so defect. If the other defects, you can take S by cooperating or P by defecting — and P > S, so defect again. On the defaults: against a cooperator, 5 beats 3; against a defector, 1 beats 0. Whatever happens, defecting pays more.

**Fact two: if both follow that logic, both do worse.** Two defectors each collect P = 1. Two cooperators would each have collected R = 3. Individually rational choices produce a collectively worse outcome. That is the dilemma.

**Real-life anchor.** Two firms have a quiet agreement to hold prices high. Holding the price while your rival holds theirs is the reward. Undercutting while they hold is the temptation — you capture their customers. Holding while they undercut leaves you the sucker. Both undercutting is the punishment: a price war that leaves both worse off than the agreement would have.

### §2.2 — Why steady cooperation must beat taking turns

There is a second condition, easy to overlook and enforced by pdsim's second validation toggle:

> **2R > T + S**

- **R**, **T**, **S** — as defined in §2.1.

Read it as a comparison over two rounds. Two players who both cooperate twice collect R + R each. Two players who take turns exploiting each other — you defect while I cooperate, then I defect while you cooperate — collect T once and S once each, so T + S. The condition says steady cooperation must pay more than alternating exploitation.

**Worked, on the defaults.** 2R = 2 × 3 = 6. T + S = 5 + 0 = 5. Six beats five, so the condition holds, with a margin of 1.

**Worked, violated.** Take T = 7, R = 3, P = 1, S = 0. The ordering still holds — 7 > 3 > 1 > 0 — so this still looks like a Prisoner's Dilemma. But 2R = 6 while T + S = 7. Now two players who coordinate on "you cheat me this round, I cheat you next round" collect 7 apiece over two rounds, against the 6 they would get from cooperating steadily. The best joint strategy has become organised mutual exploitation, and the game is no longer about cooperation in any recognisable sense.

Axelrod and Hamilton state this rationale themselves in their 1981 paper, in a note attached to the payoff definition: the condition is there specifically to rule out alternating exploitation being better for both players than mutual cooperation.

**Real-life anchor.** Two neighbouring territories can trade steadily, or they can alternate raids — you raid me this season, I raid you next. If the loot from a successful raid is large enough relative to the gains from trade, alternating raids beats trading, and what looks like a cooperation problem is really a raiding schedule.

### §2.3 — The two toggles, and when to switch them off

pdsim enforces both conditions by default, through `game.enforce_pd_ordering` and `game.enforce_alternation_constraint`. Switching either off is legitimate — it lets you explore neighbouring games. If the punishment payoff drops below the sucker payoff, so that mutual defection is the worst outcome for both, you have the game usually called Chicken or Hawk–Dove. If the reward payoff rises above the temptation, so that cooperating against a cooperator is the best outcome available, you have a Stag Hunt.

**One recognised case deserves its own name.** Setting the punishment payoff equal to the sucker payoff — most commonly both at zero — gives what the literature calls the *weak Prisoner's Dilemma*. It fails the strict ordering, because punishment must exceed sucker, but it is a deliberate and widely used simplification: with reward fixed at 1 and both of the others at 0, the entire matrix collapses to a single free parameter, the temptation. Martin Nowak and Robert May used exactly this matrix in their 1992 *Nature* paper on spatial games, the paper that first showed cooperators surviving by clustering on a grid. The 2007 *Physics Reports* survey of evolutionary games on graphs by György Szabó and Gábor Fáth gives the configuration its name and records Nowak and May's finding that the weak version behaves the same way qualitatively as the strict version, at least when the cost of being exploited is small.

If you want this configuration in pdsim, you must switch off the ordering toggle. Do it deliberately, and be aware of the side effect: the toggle protects everything else you subsequently edit, so with it off you can silently produce a matrix that is not a social dilemma at all.

**An honest warning about switching either toggle off.** The energy economy's income arithmetic keeps computing regardless. You will still get a survival window, still get a calibration readout, still get numbers. But the language attached to those numbers — "cooperators out-earn defectors," "the filter selects for cooperation" — stops meaning what it says, because in a Stag Hunt or a Chicken game the strategies are not related the way the words assume. The numbers remain correct; the story attached to them does not.

### §2.4 — Additivity: when "benefit" and "cost" actually exist

There is a third condition, which pdsim does *not* enforce, and which decides whether one of the most useful results in the field applies to your matrix at all.

> **T − R = P − S**

- **T**, **R**, **P**, **S** — as defined in §2.1.

This is called *additivity*, or sometimes *equal gains from switching*. To see what it means, read the cost of cooperating off the matrix twice.

Against a cooperator, you could have had T and you took R instead, so cooperating cost you **T − R**. Against a defector, you could have had P and you took S instead, so cooperating cost you **P − S**. Additivity says those two numbers are the same — that cooperating costs you a fixed amount regardless of what the other player does.

**The donation game.** The natural situation where this holds is one where cooperating means paying a fixed cost so that someone else receives a fixed benefit, and defecting means paying nothing and providing nothing. Write **c** for the cost to the donor and **b** for the benefit to the recipient. Then:

> **T = b,  R = b − c,  P = 0,  S = −c**

- **b** — the benefit received when the other player cooperates
- **c** — the cost paid when you cooperate

Check it: T − R = b − (b − c) = c, and P − S = 0 − (−c) = c. Same number. Cooperating costs c either way.

**Real-life anchor.** You cover a colleague's shift. It costs you an evening; it saves them a crisis. The cost to you is the same evening whether or not they would have covered for you. That fixed-cost, fixed-benefit structure is exactly a donation game.

**pdsim's defaults are not additive.** T − R = 5 − 3 = 2, while P − S = 1 − 0 = 1. Two does not equal one. The defaults are a perfectly valid Prisoner's Dilemma — the ordering holds and the alternation condition holds — but they are not a donation game.

**And the consequence is sharper than "the donation-game results don't apply."** With a non-additive matrix, the quantity "benefit divided by cost" is not merely inapplicable, it is **undefined**. There are two defensible readings of the benefit and two of the cost:

- benefit could be T − P = 5 − 1 = 4, or R − S = 3 − 0 = 3
- cost could be T − R = 2, or P − S = 1

which gives four possible ratios: 4 ÷ 2 = 2.0, 4 ÷ 1 = 4.0, 3 ÷ 2 = 1.5, 3 ÷ 1 = 3.0. Against a threshold of 4 (see §2.5), two of these clear it and two fail. A user could "predict" either outcome simply by choosing a definition. That is the signature of a malformed question, not a hard one.

pdsim reports this for you. A derived readout inspects your four live payoff values and tells you either "additive: b = …, c = …, b/c = …" or "not additive — this matrix has no well-defined benefit-to-cost ratio," with the reason.

**Recipe: building an additive matrix.** Choose the punishment payoff P and the cost c. Then:

> **S = P − c,  T = P + b,  R = P + b − c**

- **P** — the punishment payoff, which you may set anywhere, including 0
- **c** — the cost of cooperating
- **b** — the benefit conferred by cooperating

**Worked, keeping every payoff non-negative.** Take P = 1, c = 1, b = 5. Then S = 1 − 1 = 0, T = 1 + 5 = 6, R = 1 + 5 − 1 = 5. The matrix is **(T = 6, R = 5, P = 1, S = 0)**.

Check all three conditions. Ordering: 6 > 5 > 1 > 0 ✓. Alternation: 2R = 10, T + S = 6, and 10 > 6 ✓. Additivity: T − R = 1 and P − S = 1 ✓. And the benefit reads consistently: T − P = 5 and R − S = 5 ✓. So c = 1, b = 5, and the ratio is 5, unambiguously.

Note for later: this matrix is exactly the `donation_game_threshold` scenario's matrix (5, 4, 0, −1) with 1 added to every cell. Under imitation those two are the same experiment. Under the energy economy they are not. §3.7 works through why, and it is the single most important example in this guide.

### §2.5 — When your matrix is not additive: the structure coefficient

If your matrix fails additivity, there is still a usable test — it just isn't a ratio.

A 2009 paper in the *Journal of Theoretical Biology* by Corina Tarnita, Hisashi Ohtsuki, Tibor Antal, Feng Fu and Martin Nowak proved that for a very wide range of population structures, whether cooperation is favoured comes down to a single number summarising the structure. Their condition, translated into the payoff names used here:

> **σR + S > T + σP**

- **σ** (sigma) — the *structure coefficient*: one number capturing how much the population's structure helps players of the same strategy find each other. σ = 1 means structure gives no help at all; σ > 1 means it does.
- **T**, **R**, **P**, **S** — as defined in §2.1.

Read it as a weighted comparison. The left side is what cooperation gets, with the "cooperator meets cooperator" outcome weighted up by σ. The right side is what defection gets, with "defector meets defector" weighted up the same way. Structure helps cooperation precisely by making like meet like more often, and σ measures how much.

The paper notes that σ = 1 is exactly the standard risk-dominance condition from classical game theory, and that when σ exceeds 1 the diagonal entries of the matrix — the two "both players did the same thing" outcomes — matter more than the off-diagonal ones. That is the sense in which structure helps.

**The value of σ for a grid.** For a regular graph where every site has exactly k neighbours:

> **σ = ((k + 1) × N − 4k) / ((k − 1) × N)**

- **k** — the number of neighbours each site has (4 for von Neumann, 8 for Moore)
- **N** — the population size

For very large N this simplifies to the more familiar (k + 1) / (k − 1), but pdsim runs modest populations and the difference is real:

| Lattice | N | σ, four neighbours |
|---|---|---|
| 6 × 6 | 36 | (5 × 36 − 16) ÷ (3 × 36) = 164 ÷ 108 = **1.52** |
| 10 × 10 | 100 | (500 − 16) ÷ 300 = 484 ÷ 300 = **1.61** |
| 20 × 20 | 400 | (2000 − 16) ÷ 1200 = 1984 ÷ 1200 = **1.65** |
| very large | ∞ | 5 ÷ 3 = **1.67** |

Small lattices are measurably less friendly to cooperation than the textbook figure suggests. pdsim's default population is 100.

**Worked, on pdsim's defaults.** Four neighbours, large population, so σ = 5/3 ≈ 1.67. Left side: σR + S = (5/3 × 3) + 0 = 5. Right side: T + σP = 5 + (5/3 × 1) = 5 + 1.67 = 6.67. Five is less than 6.67, so cooperation is **not** favoured. One clear answer, where the ratio test in §2.4 gave four contradictory ones.

**Two caveats that must travel with this formula.**

*First: it does not cover birth-death updating.* The proof assumes that one half of each replacement event — either who is born or who dies — happens independently of payoff. Death-birth updating satisfies this, because the dying agent is chosen at random. Birth-death updating does not, and the authors say so explicitly: the condition is still expected to hold there, but it needs a different proof they had not yet given. Since pdsim offers both under `dynamics.moran_rule`, check which one you are running. §7.3 has more, and it is worse than a technicality.

*Second: it is an approximation on a grid.* The underlying derivation uses a technique formulated for graphs without closed loops. A square lattice is full of loops — any four adjacent sites form one. The original authors state that discrepancy between the formula and actual simulations on looped graphs is expected. Treat σ as a compass, not a prediction.

---

## §3 — Under imitation, the numbers barely matter (with two exceptions)

### §3.1 — The claim, stated precisely

Under imitation dynamics, what drives the simulation is not any agent's score but the *comparison* between scores. So any change to the payoffs that leaves all the relevant comparisons intact leaves the simulation intact.

That claim has a solid theoretical foundation. The 2003 survey "Evolutionary game dynamics" by Josef Hofbauer and Karl Sigmund, published in the *Bulletin of the American Mathematical Society*, establishes three relevant results. Adding a constant to a whole column of the payoff matrix does not affect the replicator equation — the standard continuous-time model of strategies spreading in proportion to how well they do. The same holds for adding any function uniformly to all payoff functions. And, most usefully here, every imitation rule in a broad family reduces to the replicator equation up to a change in velocity — same trajectory, different clock.

But "leaves the relevant comparisons intact" is doing real work in that sentence, and pdsim gives you five different selection rules that compare in different ways. Two of them have exceptions.

### §3.2 — Shift, worked

Add 4 to every cell. The defaults (5, 3, 1, 0) become (9, 7, 5, 4).

An agent that plays 100 rounds now earns an extra 4 in each round, so an extra 400 in total. If every agent plays 100 rounds, every agent gains exactly 400. Every score rises by 400. Every *difference* between two scores is unchanged, because both scores moved by the same amount.

A rule that reads differences sees nothing at all. The simulation is identical.

### §3.3 — Scaling is not free: it is the selection-intensity dial in disguise

pdsim's default selection rule is `fermi`, named after the physicist Enrico Fermi because it borrows a formula from statistical physics. It repeatedly picks two agents and has the first copy the second's strategy with a probability that grows with:

> **β × (s_B − s_A)**

- **β** (beta) — the selection intensity, set by `dynamics.selection_beta`. At 0, scores are ignored entirely and strategies spread by pure luck. The larger it is, the more reliably higher scorers get copied.
- **s_A** — the first agent's score
- **s_B** — the second agent's score

The rule only ever sees that **product**. Now multiply every payoff by 10. Every score multiplies by 10. Every difference multiplies by 10. So the product β × (difference) multiplies by 10 — which is exactly what would have happened if you had left the payoffs alone and changed β from 1 to 10.

**Scaling the payoff matrix by a factor is identical to multiplying the selection intensity by the same factor.**

This is a real trap. Someone who rewrites (5, 3, 1, 0) as (50, 30, 10, 0) because round numbers look tidier, and leaves β at its default of 1.0, has silently switched from moderate selection to ferocious selection. Their cooperators will now sweep or vanish far more decisively, and they will conclude something about cooperation when what changed was the strength of selection.

The dynamics are fully recoverable: divide β by the same factor. But only if you know to.

*(This equivalence is derived from pdsim's own selection rule, not taken from the literature. The two lines of algebra above are the whole argument.)*

### §3.4 — Shift-invariance holds only when everyone plays the same amount

§3.2 assumed every agent plays 100 rounds. Under `round_robin` matching that is true — every pair plays exactly once, so everyone plays the same number of matches. Under `random_k` it is not.

Under `random_k`, each agent *initiates* a fixed number of matches, but is also *drawn into* matches by others, and how many times you get drawn is a matter of luck. Some agents play more than others.

**Worked.** Rounds per match is 10. Agent A ends up in 8 matches, so 80 rounds. Agent B ends up in 12 matches, so 120 rounds. Now add 4 to every payoff cell. Agent A gains 4 × 80 = 320. Agent B gains 4 × 120 = 480.

The gap between them has widened by 160 — in favour of the agent who happened to be drawn more often. Under a rule that reads score differences, that is a systematic reward for participation luck rather than for strategy. The shift did not cancel.

This also sharpens a note in the project's own records. A workaround was once considered of adding 1 to all four payoffs to avoid a negative number, on the grounds that it preserves every best response and so leaves the strategic structure intact. That is true about best responses. It is not true about the selection dynamics under `random_k`. The workaround was never needed, so this is a note for the record rather than a live problem — but the principle stands.

### §3.5 — What each of the five selection rules is immune to

| Selection rule | Immune to a shift? | Immune to scaling? |
|---|---|---|
| `fermi` | Yes, when participation is equal (§3.4) | **No** — equivalent to rescaling β (§3.3) |
| `proportional` | Yes | Yes |
| `tournament_k` | Yes | Yes |
| `truncation` | Yes | Yes |
| `threshold_cloning` | **Only at the default multiplier of 1.0** | Yes |

Three of these are quick. `proportional` (roulette-wheel selection) weights each agent by how far its score sits above the generation's lowest, then draws in proportion — the subtraction removes any constant, and the proportion removes any factor, so it is immune to both. `tournament_k` and `truncation` are rank-based: one holds a mini-contest and takes the best scorer, the other copies only from the top slice. Neither ever looks at *how much* better, only *which is better*, so any change that preserves the ordering of scores changes nothing.

**`threshold_cloning` is the interesting one.** It keeps every agent scoring at or above a bar, and replaces the rest with copies of the survivors. The bar sits at a multiplier times the generation's mean score. Agent *i* survives when:

> **s_i ≥ m × μ**

- **s_i** — agent *i*'s score
- **m** — the multiplier, set by `dynamics.selection_threshold_multiplier`, default 1.0
- **μ** (mu) — the generation's mean score

Now add a constant *a* to every payoff, which raises every individual score by *a* and therefore raises the mean by *a* too. The survival test becomes s_i + a ≥ m × (μ + a), which rearranges to:

> **s_i ≥ m × μ + (m − 1) × a**

At m = 1 the second term vanishes and the shift cancels exactly — the bar moves in lockstep with the field, and the same agents survive.

At m = 1.2 it does not. Add 100 to every score: individual scores rise by 100, but the bar rises by 1.2 × 100 = 120. The bar has moved 20 points *relative to the field*. Same population, same play, different survivors — from a change that altered nothing strategic whatsoever.

*(This table is derived from the behaviour documented in the parameter registry, which is authoritative for what each rule is meant to do. The `threshold_cloning` row in particular is a claim about arithmetic; it has been verified against the implementation — the survival bar is computed as multiplier × generation mean (VT-5, answered in the M11a spec's post-freeze addendum).)*

### §3.6 — Practical upshot for imitation runs

Spend your effort on the *ordering* of the payoffs and on the *ratios* between the gaps. Do not spend it on the levels. But if you rescale the payoffs, rescale the selection intensity inversely — or you have changed the experiment without meaning to.

### §3.7 — The example the whole guide turns on

Compare two matrices:

- **(T = 5, R = 3, P = 0, S = −1)** — pdsim's flagship spatial scenario
- **(T = 6, R = 4, P = 1, S = 0)** — the same thing with 1 added to every cell

Start with what does *not* differ. Both have T − R = 2 and P − S = 1. **A shift can never change whether a matrix is additive**, because both of those differences are themselves shift-invariant. Both matrices preserve every best response. Under imitation with equal participation, they are the same experiment, and §3.2 proves it.

Now put them into the energy economy, at the flagship's settings: a grid with four neighbours per site, one round per match, and roughly 8 matches per agent per generation (§4.2 derives that 8).

| | (5, 3, 0, −1) | (6, 4, 1, 0) |
|---|---|---|
| Defector surrounded by defectors | 8 × 0 = **0** | 8 × 1 = **8** |
| Cooperator inside a cooperator cluster | 8 × 3 = **24** | 8 × 4 = **32** |
| Cooperator at a cluster edge, per defector neighbour | **−1** | **0** |

The flagship scenario's entire claim is that a defector surrounded by other defectors earns **nothing** and starves against the living cost. At P = 1 it earns 8 per generation, and whether it starves now depends entirely on where you put the living cost. If 8 clears the bill, nobody starves, cooperator clusters gain no relative advantage, and the scenario demonstrates nothing at all while still producing a plausible-looking run.

**A transformation that is provably free under imitation destroys the mechanism under the energy economy.** That is §1's table, on your own flagship, in one worked example.

**And the sucker payoff is a genuine modelling choice, not a formality.** At S = −1 a cooperator meeting a defector actively loses energy. At S = 0 it merely fails to gain any. Ask which describes your situation: **does being exploited cost you something, or does it merely fail to pay you?** If cooperating means handing over a real resource — a donation, a covered shift, a share of the harvest — then being met with defection is a net loss and the sucker payoff should be negative. If cooperating means offering a trade the other party declines to reciprocate, you have lost the opportunity but not the goods, and zero is right. On a grid this decides whether cluster edges bleed energy or merely fail to earn it, which decides how heavily clusters are penalised for having a perimeter at all.

---

## §4 — Under the energy economy, the numbers are income

### §4.1 — The ledger, and the income identity

Once `dynamics.reproduction_mode` is set to `energy_economy`, each agent carries a running energy balance updated every generation:

> **e ← e × (1 + r) + score − L − c × m**

- **e** — the agent's energy stock, carried from one generation to the next
- **r** — the capital return rate; interest earned on carried-over energy
- **score** — total Prisoner's Dilemma payoff earned this generation
- **L** — the basic living cost; a flat bill every agent pays for existing
- **c** — the engagement cost; paid once per match taken part in
- **m** — the number of matches this agent actually played this generation

The payoffs enter through `score`, and `score` is built like this:

> **score = (payoff per round) × (rounds per match) × (matches per agent)**

Three multipliers. Only the first of them looks like a payoff setting. The other two live in the Matching and Match sections of the parameter panel and are labelled as though they were about pacing or thoroughness. They are not: **they multiply every agent's income.**

**Real-life anchor.** The living cost is a firm's fixed operating overhead — rent, salaries, insurance. It falls due whether or not you traded well this quarter. Clear it and you continue; fail to clear it repeatedly and you close.

### §4.2 — The matcher multiplier, in three regimes

**`round_robin` — every pair plays exactly once.**

Matches per agent = N − 1, where N is the population size. Income therefore scales with N.

In a growth economy this is a serious problem, because the population grows by design. As it grows, every agent plays more matches and earns more, so the whole survival window drifts upward. A living cost you carefully placed at the midpoint when the population was 40 is sitting near the bottom by the time it reaches 200. The model decalibrates itself, without you touching anything, purely by doing what you built it to do.

**`random_k` — each agent starts matches against a few random opponents.**

Each agent *initiates* k matches. It is also *drawn* by others: each of the other N − 1 agents picks k opponents out of N − 1 candidates, so the chance any particular one picks you is k ÷ (N − 1), and there are N − 1 of them, giving k expected draws. So:

> **matches per agent ≈ 2k**

- **k** — opponents per agent, set by `matching.opponents_per_agent`

Notice that N cancelled. The interaction budget is bounded regardless of population size, which is why `random_k` is the growth economy's natural matcher — the window stays put while the population moves. The M10 explainer works this through in full.

**Spatial interaction on — the same phenomenon, with geometry in place of k.**

When `matching.spatial_interaction` is switched on, the matcher dropdown greys out and partners come from within reach on the grid. The doubling from `random_k` carries straight over, and this is the part most likely to be misread:

> **matches per agent ≈ 2 × min(k, degree)**

- **k** — opponents per agent, as above
- **degree** — the number of neighbours a site actually has (4 under von Neumann, 8 under Moore, fewer at the edge of a bounded grid)

Every agent initiates a match against each neighbour — that is *degree* matches. But each of those neighbours is also busy initiating against *its* neighbours, and you are one of them, so you get drawn in *degree* more times. Four neighbours means roughly **eight** matches, not four. Eight neighbours means roughly **sixteen**, not eight.

pdsim does not remove these duplicates, and that is deliberate rather than accidental: the same behaviour is already present in `random_k`, and inheriting it unchanged keeps income statistics comparable between the spatial and non-spatial cases. But it means the neighbourhood shape dropdown is an income multiplier, which is not how anyone reads a setting called "neighbourhood shape."

### §4.3 — Choosing the neighbourhood shape

The two standard choices on a square grid are named after the mathematicians who introduced them. **Von Neumann** counts the four orthogonal neighbours — up, down, left, right. **Moore** counts all eight surrounding cells, diagonals included.

Switching between them does four things at once:

| | von Neumann (k = 4) | Moore (k = 8) |
|---|---|---|
| Cooperation threshold from §2.5 | benefit ÷ cost > 4 | benefit ÷ cost > 8 |
| Structure coefficient σ, large population | 5 ÷ 3 = 1.67 | 9 ÷ 7 = 1.29 |
| Matches per agent per generation | ≈ 8 | ≈ 16 |
| Runtime | baseline | roughly double |

Cooperation needs twice the benefit-to-cost ratio under Moore, structure helps it substantially less, income doubles against an unchanged living cost, and the run takes twice as long. Four consequences, one dropdown. **This is never a small change.**

**The honest way to choose is to ask what "adjacent" means in the thing you are modelling: is a diagonal neighbour as easy to reach as an orthogonal one?**

Choose **von Neumann** when contact runs along channels. Settlements strung along a river or canal. A street grid where diagonally-facing buildings share no boundary and you must walk around the corner. Agricultural plots that share edges. Administrative districts that share borders. Supply chains with fixed links. Also choose it when you want the strongest available clustering effect — which is why pdsim's flagship spatial scenario uses it.

Choose **Moore** when the terrain is open and a diagonal step costs nothing extra. Grazing land. Open sea. A plain. Air routes. A social network with no geographic constraint at all. Also choose it deliberately when you want a *harder* test: if cooperation survives at eight neighbours, the result is more robust.

### §4.4 — How often should two neighbours actually meet?

§4.2 established that a neighbouring pair currently meets **twice** per generation, because each of the two starts one match. Nothing about the world being modelled makes that so — it falls out of the fact that matches are indexed by whoever initiated them.

For many real situations, one encounter per pair per period is the natural unit. When scattered groups occasionally run into one another, the encounter is an event that happens to the *pair*; it is circumstance, not each side independently deciding to seek the other out. Doubling it is a modelling claim, and at present pdsim is making that claim on your behalf.

Two further points, neither obvious:

**Two matches of one round each are not the same as one match of two rounds**, even though the round count agrees. Reciprocal strategies open every match by cooperating, so match boundaries reset first-move behaviour. And when match length is set by continuation probability rather than a fixed count, the length is drawn once per match, so doubling the match count doubles the number of draws.

**The doubling is invisible on exactly the half of the flagship where you would look for it**, because 8 × 0 and 4 × 0 are both zero. Only the cooperator side shows it.

A configurable encounter mode is on the roadmap for a later milestone. Until it lands, use the ≈ 2 × degree figure and know that it is a choice rather than a fact.

### §4.5 — The survival window

Two reference points matter, and both are computable from your settings before you run anything.

> **all-C income = (rounds per agent per generation) × R**
>
> **all-D income = (rounds per agent per generation) × P**

- **all-C income** — what an agent earns per generation in a population where everyone cooperates
- **all-D income** — what an agent earns per generation where everyone defects
- **R**, **P** — the reward and punishment payoffs

The regime where behaviour decides survival is:

> **all-D income ≤ L < all-C income**

- **L** — the basic living cost

Below the window, even defectors pay their bills and the filter is switched off. Above it, even a world of perfect cooperators cannot pay, and everything dies. Only inside the window does how you play decide whether you live.

**Worked, for `the_growth_economy` scenario.** `random_k` with k = 5, and 10 rounds per match.

- Matches per agent = 2 × 5 = 10.
- Rounds per agent per generation = 10 × 10 = **100**.
- all-C income = 100 × 3 = **300**. all-D income = 100 × 1 = **100**.
- Window: 100 ≤ L < 300. Midpoint: **L = 200**.
- A cooperator nets 300 − 200 = **+100** per generation. A defector nets 100 − 200 = **−100**. Symmetric, and exactly what the app's calibration readout will tell you.

The M10 explainer derives all of this in more detail, including an important caution: this arithmetic tells you when the *average* agent dies, not when the *population* does. Under `random_k` real incomes are spread around the average, so a collapse smears across two or three generations rather than happening at once.

### §4.6 — The recalibration drill

Start from that baseline — window 100 to 300, living cost 200, comfortably inside. Now change exactly one thing at a time.

**Rounds per match, 10 → 50.** Rounds per agent = 10 × 50 = 500. Window becomes 500 ≤ L < 1500. Your living cost of 200 is now *below* the window: the filter is off and everyone grows, defectors included.

**Opponents per agent, 5 → 2.** Matches = 2 × 2 = 4, rounds = 40. Window becomes 40 ≤ L < 120. Your 200 is now *above* the window: nobody can pay, and the entire population dies.

**Matcher, `random_k` → `round_robin`, at 40 agents.** Matches = 39, rounds = 390. Window becomes 390 ≤ L < 1170 — and it keeps moving as the population grows.

**Neighbourhood shape, Moore → von Neumann**, with spatial interaction on, one round per match, and the flagship's punishment of 0. Under Moore: 16 rounds, all-C income 16 × 3 = 48, window 0 ≤ L < 48. Under von Neumann: 8 rounds, all-C income 24, window 0 ≤ L < 24. A living cost of 30 sits inside the window under Moore and *above* it under von Neumann. Same payoffs, same cost, one dropdown — and in one case cooperators thrive while in the other everybody dies.

**The rule: never move the matcher, the opponents-per-agent count, the rounds per match, the continuation probability, the neighbourhood shape, or the world structure without recomputing the window.**

On continuation probability specifically: when match length is probabilistic rather than fixed, use

> **expected rounds per match = 1 ÷ (1 − w)**

- **w** — the continuation probability, set by `match.continuation_probability`

At w = 0.98 that is 1 ÷ 0.02 = 50 rounds. So switching from fixed 10-round matches to continuation at 0.98 multiplies every income by five.

### §4.7 — The shift is not free here either

§3.2 showed that adding 4 to every payoff is free under imitation. Under the economy, at 100 rounds per generation, adding just 1 to every cell adds 100 to every agent's income — half the entire living cost in the worked example above.

That is §1's table again. The transformation that costs nothing in one regime is a major recalibration in the other.

---

## §5 — Reproduction: the two gates, and what actually limits births

### §5.1 — The threshold and the stake

Two quantities govern reproduction.

> **eligible if e ≥ θ, then pay σ + overhead**

- **e** — the agent's energy at the generation boundary
- **θ** (theta) — the reproduction threshold, set by `dynamics.reproduction_threshold`. This is *eligibility*: the bar you must clear to be allowed a child.
- **σ** (sigma) — the offspring stake, set by `dynamics.offspring_stake`. This is the endowment handed to the newborn, paid out of the parent's stock. Reproduction transfers wealth; it does not create it.
- **overhead** — the reproduction overhead, set by `dynamics.reproduction_overhead`. Extra energy burned by the act itself, which simply disappears.

**Real-life anchor.** The threshold is the capital a household needs before it can support a child. The stake is what the child leaves home with. The overhead is what the process consumes and nobody receives.

**How often can an agent breed?** In a well-mixed world:

> **breeding interval = σ ÷ (net income per generation)**

- **σ** — the offspring stake
- **net income per generation** — income minus all costs

On the defaults, σ = 400 and a cooperator nets +100, so a cooperator can afford a child roughly every four generations. Note also that pdsim allows **one birth per agent per generation regardless of wealth**: an agent holding five times the threshold still has one child. The dynastic advantage runs through breeding *frequency*, not through endowment size.

### §5.2 — A warning the validator does not currently give you

pdsim checks that the stake does not exceed the threshold, and the documentation explains that check as guaranteeing a parent always survives its own reproduction. With the defaults it works: an agent at exactly 500 pays out 400 and keeps 100.

But the parent pays **stake plus overhead**, and the check only looks at the stake.

**Worked.** Threshold 500, stake 400, overhead 150. A parent sitting at exactly 500 pays out 550 and ends the generation at **−50**. The stated guarantee has failed.

And it fails quietly. The order of events at each boundary is: update energy, apply age-related deaths, remove anyone with negative energy, then process births. Insolvency is checked *before* births happen, so a parent that drives itself negative does not die on the spot — it carries the negative balance into the next generation and dies at the *following* boundary. From the outside it looks like an agent that reproduced successfully and then mysteriously died a generation later.

**Set your threshold to at least the stake plus the overhead:**

> **θ ≥ σ + overhead**

### §5.3 — The two gates

Under a spatial structure, becoming a parent requires clearing **two** independent gates.

**The capacity gate** asks whether the world is under its carrying capacity. When seats are scarce they are rationed by energy priority — the richest eligible parents are admitted first.

**The placement gate** asks whether there is an empty site within reach of the parent on the grid.

**Clearing one is not clearing the other, in both directions.** A parent can win a seat under the capacity cap and still find every neighbouring site occupied. A parent with an empty site right next door can still be turned away because the world is at capacity.

Crucially, pdsim checks placement *before* charging the stake. A parent that cannot place a child pays **nothing** and stays eligible next generation.

### §5.4 — The blocked parent is not a bug

The consequence is the single thing in the spatial layer most likely to be misread.

**A parent walled in by occupied neighbours pays nothing, stays eligible, and keeps accumulating energy indefinitely.** You will see agents sitting at five times the reproduction threshold, doing nothing. On a dashboard that reads as a defect. It is not. Being unable to spend reproductive wealth because the neighbourhood is full is the entire content of what population biologists call *viscosity* — and viscosity is precisely what spatial structure is for.

The app reports **blocked parents this generation** in the Economy panel so you can see the mechanism rather than infer it.

**Real-life anchor.** A prosperous farming family with the capital for another household and no land next door. The money is real; the constraint is geographic.

### §5.5 — The payload: under structure, geometry sets the birth rate, not θ

This is the section's real point, and it changes how you should think about the threshold and the stake on a lattice.

**Well-mixed arithmetic.** σ = 400, cooperator nets +100 per generation, so a birth every 4 generations. The stake sets the pace.

**Saturated lattice arithmetic.** Suppose a von Neumann agent's four neighbouring sites are all occupied, and each occupant dies with probability 0.02 per generation. The chance that at least one of the four frees up in a given generation is approximately 4 × 0.02 = 0.08, so the expected wait is 1 ÷ 0.08 = **12.5 generations**.

The threshold-and-stake formula says four generations. Geometry says twelve and a half. **Geometry binds, and it binds by a factor of three.**

So a threshold you carefully tuned in a well-mixed run will produce a completely different demography on a lattice with nothing else changed. On a saturated grid, lowering the stake to speed up breeding accomplishes nothing at all — you are not waiting for money, you are waiting for a vacancy.

### §5.6 — Setting the threshold and the stake

Think of it as choosing between a **ramp** and a **rhythm**.

A large stake relative to the threshold gives children a long runway but drains parents hard, producing infrequent well-provisioned births. A small stake gives frequent births with short runways — offspring that must earn quickly or die. The constraint σ ≤ θ (and, per §5.2, σ + overhead ≤ θ) is what stops reproduction from being suicidal.

Two corners worth knowing. At σ = 0 the newborn starts at nothing and reproduction is free — this is the textbook configuration used for replicating published results, and it has a side effect covered in §7.2. As σ approaches θ, a parent is stripped back to nearly nothing at every birth and the population becomes a series of near-identical fresh starts.

`dynamics.initial_energy` sets what the founding generation starts with, and leaving it blank means "same as the offspring stake" — founders begin life exactly like newborns. Raising it buys a longer runway before the economics bite, which mostly changes how long a doomed population takes to die rather than whether it does.

---

## §6 — The remaining ledger quantities

### §6.1 — Engagement cost

> **engagement charge = c × m**

- **c** — the engagement cost, set by `dynamics.engagement_cost`
- **m** — matches this agent actually played

Note it is per **match**, not per round. That is deliberate: tying it to rounds would make match-length settings silently economic, so that turning up the rounds to give reciprocity more room to work would also change everyone's cost structure. Keeping it per match makes it survival-neutral for an agent that plays nothing.

But it inherits the same matcher multiplier as income. Under `round_robin` at 40 agents an agent plays 39 matches; under `random_k` at k = 5 it plays about 10. The same engagement cost is roughly four times the charge in the first case.

**Real-life anchor.** A per-deal transaction cost — legal fees, brokerage, the time to negotiate. Dealmaking itself is not free.

### §6.2 — Reproduction overhead

The only quantity in the ledger where energy leaves the system entirely. The stake reaches the child; the overhead simply vanishes. It defaults to zero, and §5.2 explains the trap when it does not.

### §6.3 — Capital return rate, and the rentier

> **e\* = costs ÷ r**

- **e\*** — the *escape velocity*: the energy stock above which returns alone cover all bills, forever
- **costs** — total per-generation costs, principally the living cost plus any engagement charges
- **r** — the capital return rate, set by `dynamics.capital_return_rate`

**Worked.** Living cost 200, no engagement cost, r = 0.05. Escape velocity is 200 ÷ 0.05 = **4000**. Against a reproduction threshold of 500, that leaves a long band — from 500 up to 4000 — where agents can breed but are not yet self-sustaining on returns alone.

Above escape velocity, an agent pays its bills from interest regardless of how it plays. **The metabolic filter has been switched off for the wealthy without being switched off in the parameter panel.** This is why the rate defaults to zero and why the app surfaces the escape velocity figure for you.

**Real-life anchor.** Endowment income. Above a certain principal, performance stops mattering.

### §6.4 — The scale-invariance checklist

§1 promised that the economy is exactly scale-invariant. To use that licence, multiply **all** of the following by the same positive factor, and nothing else:

the four payoffs (T, R, P, S) · the basic living cost · the reproduction threshold · the offspring stake · the initial energy · the engagement cost · the reproduction overhead

Leave alone: the capital return rate (a dimensionless ratio), the carrying capacity (a head count), and everything to do with age and mortality (which never sees energy).

Miss one and the invariance is gone.

---

## §7 — Three worked exhibits

### §7.1 — The flagship: starvation, not relative fitness

The `spatial_reciprocity` scenario asks the oldest question in spatial game theory: can cooperators survive by clustering? Its settings are a grid with von Neumann neighbourhoods, local interaction and local birth at radius 1, only unconditional cooperators and unconditional defectors on the roster, one round per match, and a payoff matrix of **T = 5, R = 3, P = 0, S = −1**.

Three of those numbers override the registry defaults, and each override is load-bearing.

**Punishment set to 0.** The scenario's whole mechanism is that a defector surrounded by other defectors earns *nothing* and starves. At the default punishment of 1, with eight Moore neighbours, such a defector earns 8 per generation — which may well clear the living cost, in which case nobody starves, cooperator clusters gain no advantage, and the scenario silently demonstrates nothing while still producing a plausible-looking run.

**Von Neumann rather than Moore.** Fewer neighbours means stronger clustering and an easier time for cooperation, which is what you want from a scenario designed to show the effect exists.

**Sucker set to −1.** This keeps the matrix legal: with punishment at 0 and sucker at its default of 0 the two would be equal, and the strict ordering requires punishment to exceed sucker. It also makes cluster edges cost something, which sharpens the pressure to cluster.

**One conceptual guard, because it is easy to blur.** This scenario does **not** rest on the neighbour-count threshold from §2.5. Its story is **ecological** — absolute income measured against a survival bill, with a defector interior earning nothing. The threshold from §2.5 is about **relative fitness among competitors under weak selection**, which is a different scenario's story. The two arguments happen to point the same way. They are not the same argument, and conflating them will lead you to the wrong conclusion about which settings matter.

### §7.2 — Accumulation artifacts, and how to mitigate them

In the fixed-population asynchronous mode, when it is time for someone to reproduce, the parent is drawn with probability proportional to a fitness weight:

> **w_i = e_i − min(e)**

- **w_i** — agent *i*'s fitness weight
- **e_i** — agent *i*'s accumulated energy stock
- **min(e)** — the lowest energy stock in the population

There is no selection-intensity dial on this at all. It is raw proportional selection on an accumulated **stock**, not a per-generation **flow**, and that produces four distinct artifacts.

**Artifact one: selection starts at exactly zero.** At the beginning of a run every agent holds identical energy, so every weight after subtraction is zero, a uniform-random fallback fires, and the parent draw is perfectly neutral — pure luck, with no fitness content whatsoever. Selection then climbs as stocks diverge. *Mitigation: none required, but do not read early trajectories as selective. They are drift.*

How far does the climb go? This was measured rather than left open (DECISIONS #117, 2026-08-03): over 7,200 breeder draws in a 300-generation-equivalent run, the spread of the shifted weights reaches a plateau within the first quarter of the run and wanders around it thereafter — spread divided by elapsed time *falls* roughly fourfold across the run, and the strongest agent's actual draw probability drifts slightly *down*, not up. The same picture holds in all three variants tested: the textbook corner, mutation at 0.01, and a 2% capital return (the compounding channel). So the honest summary is that selection strengthens *from zero* in a run's opening stretch and then stops strengthening; a claim that effective selection keeps strengthening as a run ages is contradicted by measurement, not merely unsupported by the algebra. The measurement's own limits: one seed, one population size, one matcher, one death rule — enough to refute "strengthens over time", not enough to say where the plateau sits as the parameters move.

**Artifact two: the draw partly selects for age rather than strategy.** The population turns over, and an incumbent has simply had longer to accumulate than a newborn. In the textbook configuration where the offspring stake is zero, a newborn's weight sits at or near the bottom and it effectively **cannot reproduce** until it has accumulated. Being old is an advantage independent of playing well. *Mitigation: set the offspring stake near the population's typical working energy so newborns are not automatically bottom-ranked — at the cost of departing from the textbook corner. Or keep runs short relative to the divergence timescale. Or accept it and report it, which is the honest option when replicating a published result that itself uses a stake of zero.*

The project's own scenario text already notes the mirror image on the death side: when the reaper targets the poorest, newborns live dangerously.

**Artifact three: blocked parents become privileged.** Per §5.4, a walled-in parent pays nothing and accumulates without limit. Its energy then dominates **both** this fitness draw **and** the energy-priority rationing at the capacity gate. So *being stuck* turns into *being favoured* the moment a seat opens nearby. *Mitigation: watch the blocked-parents readout. A run with many long-blocked parents is one where birth priority is measuring immobility rather than performance.*

**Artifact four: the rentier**, per §6.3. *Mitigation: leave the capital return rate at zero, or watch the escape-velocity readout.*

**And one thing that is not an artifact but will save you an afternoon: the living cost has no effect on selection in the fixed-population mode at all.** Every agent pays the same bill, so it shifts every energy balance by the same amount, and subtracting the lowest removes uniform shifts exactly. Do not tune it there.

**The general principle.** Prefer a **flow** to a **stock** wherever pdsim offers you the choice. Under imitation it does: `dynamics.score_accounting` offers per-generation scoring (a pure flow), a sliding window, and an exponential discount. Under the energy economy it does not — fitness is the stock, by construction — so every mitigation above is indirect.

**A note on the weak-selection limit.** The threshold in §2.5 is derived for *weak selection*: the regime where payoff differences barely register in the dynamics. The published models make that explicit. Ohtsuki and colleagues write fitness as (1 − w) + w × payoff, where w tunes selection intensity, with w = 1 meaning strong selection and w much less than 1 meaning weak. Tarnita and colleagues write effective payoff as 1 + δ × payoff, with the weak-selection limit being δ → 0.

pdsim's fixed-population breeder draw has **no such parameter**. We cannot approach the limit in which the threshold was derived. Treat §2.5 as a **calibration compass, not a prediction** — a way to see which direction a change pushes, not a forecast of what will happen.

### §7.3 — Under birth-death updating, cooperation cannot win

pdsim's `dynamics.moran_rule` offers three orderings for each replacement event in the fixed-population mode. Under **death-birth**, an agent dies first and the survivors compete to fill the empty seat. Under **birth-death**, a parent is chosen first and its offspring displaces someone else. Under **random**, a weighted coin decides per event.

The Supplementary Information to Ohtsuki and colleagues' 2006 paper works out all three, and the result for birth-death is unambiguous: defectors are favoured over cooperators for **any** choice of benefit and cost with benefit greater than cost. Selection never favours cooperators under birth-death updating.

So if you set birth-death and expect to see cooperation survive by clustering, you will see cooperation lose, every time, at every benefit-to-cost ratio. **That is the model behaving correctly**, not a bug and not a badly chosen living cost. Under the `random` mixture the effect is diluted in proportion to the weights.

Note also that the structure-coefficient result in §2.5 explicitly excludes birth-death from its proof, for the related reason that neither the birth step nor the death step is independent of payoff there.

**If you are investigating cooperation on a structure, use death-birth.** It is pdsim's default for exactly this reason.

---

## §8 — A calibration procedure

1. **Identify the regime.** Tournament mode, or imitation with a rank-based rule? Then payoffs are nearly free — check §2 and stop.
2. **Check the three constraints.** Ordering (§2.1). No-alternation (§2.2). Additivity (§2.4), which is not enforced but decides whether "benefit over cost" means anything for your matrix.
3. **If imitation:** set payoffs for readability. But if you rescale them, rescale the selection intensity inversely (§3.3). And if you are on `random_k`, remember that shifts do not fully cancel (§3.4).
4. **If the energy economy: compute matches per agent.** N − 1 under round-robin; ≈ 2k under `random_k`; ≈ 2 × min(k, degree) with spatial interaction on (§4.2).
5. **Compute rounds per agent per generation:** matches × rounds per match, converting continuation probability to expected rounds via 1 ÷ (1 − w) (§4.6).
6. **Compute the survival window** and place the living cost inside it (§4.5).
7. **Set the threshold and the stake** against net income, respecting θ ≥ σ + overhead (§5.2, §5.6).
8. **If a spatial structure is on, re-check the birth rate against geometry** rather than against the stake (§5.5).
9. **If the capital return rate is above zero, compute escape velocity** and decide whether a rentier class is part of your model (§6.3).
10. **Re-run this whole procedure** whenever you change the matcher, the opponents-per-agent count, the rounds per match, the continuation probability, the neighbourhood shape, or the world structure. Every one of them silently multiplies income.

---

## §9 — Quick reference

The third column is this table's purpose.

| Quantity | Units | Compared against | What silently rescales it |
|---|---|---|---|
| Temptation, Reward, Punishment, Sucker | payoff per round | each other (imitation); the living cost (economy) | rounds per match; matches per agent; the matcher; the neighbourhood shape |
| Selection intensity (β) | dimensionless | the score difference it multiplies | **any scaling of the payoffs** |
| Basic living cost (L) | energy per generation | all-C and all-D income | anything that changes rounds per agent |
| Reproduction threshold (θ) | energy stock | the agent's balance; must be ≥ stake + overhead | net income per generation; on a lattice, site turnover |
| Offspring stake (σ) | energy per birth | net income (sets breeding interval) | net income; the threshold |
| Initial energy | energy stock | the living cost (sets the runway) | defaults to the stake if left blank |
| Engagement cost | energy per match | income | **matches per agent** — the same multiplier as income |
| Reproduction overhead | energy per birth | the threshold minus the stake | nothing; but it breaks the survival guarantee if ignored |
| Capital return rate (r) | dimensionless | escape velocity = costs ÷ r | nothing — it is a ratio and survives any scaling |
| Opponents per agent (k) | count | the neighbourhood degree, which clamps it | the neighbourhood shape |
| Neighbourhood shape | 4 or 8 neighbours | the cooperation threshold and σ | nothing — but it changes four things at once |

---

## References

**Axelrod, R. & Hamilton, W. D. (1981).** The evolution of cooperation. *Science* 211(4489), 1390–1396. DOI: 10.1126/science.7466396. — The paper that established the modern framework. Source of the T > R > P > S and 2R > T + S conditions (Figure 1 caption), the rationale for the second condition (note 17), and the illustrative values 5, 3, 1, 0 that pdsim uses as defaults.

**Hofbauer, J. & Sigmund, K. (2003).** Evolutionary game dynamics. *Bulletin of the American Mathematical Society* 40(4), 479–519. — Survey of the mathematics of strategies spreading in populations. Source of the invariance results in §3.1: column-constant invariance of the replicator equation, invariance under adding a function to all payoff functions, and the reduction of aggregate-monotonic imitation dynamics to replicator dynamics up to a change in velocity.

**Hofbauer, J. & Sigmund, K. (1998).** *Evolutionary Games and Population Dynamics.* Cambridge University Press. — The standard book-length treatment. Listed for orientation; no claim here rests on it.

**Nowak, M. A. & May, R. M. (1992).** Evolutionary games and spatial chaos. *Nature* 359, 826–829. DOI: 10.1038/359826a0. — The paper that first showed cooperators surviving by clustering on a grid, using the single-free-parameter matrix discussed in §2.3.

**Ohtsuki, H., Hauert, C., Lieberman, E. & Nowak, M. A. (2006).** A simple rule for the evolution of cooperation on graphs and social networks. *Nature* 441, 502–505. DOI: 10.1038/nature04605. — Source of the benefit-over-cost-exceeds-neighbour-count threshold, the donation-game matrix, the explicit selection-intensity parameter quoted in §7.2, and the birth-death result in §7.3.

**Szabó, G. & Fáth, G. (2007).** Evolutionary games on graphs. *Physics Reports* 446(4–6), 97–216. — Comprehensive survey. Source of the "weak Prisoner's Dilemma" naming in §2.3 and the finding that the weak version behaves qualitatively like the strict one for small cost.

**Tarnita, C. E., Ohtsuki, H., Antal, T., Fu, F. & Nowak, M. A. (2009).** Strategy selection in structured populations. *Journal of Theoretical Biology* 259(3), 570–581. DOI: 10.1016/j.jtbi.2009.03.035. — Source of the structure coefficient in §2.5, its values for regular graphs and finite populations, the risk-dominance interpretation, and the scope limit excluding birth-death updating.

### Derived, not cited

Three claims in this guide come from pdsim's own arithmetic rather than from published work, and are labelled as such where they appear: the equivalence between scaling payoffs and rescaling the selection intensity (§3.3); the selection-rule invariance table (§3.5), which is derived from documented behaviour; and the shift-dependence of `threshold_cloning` at multipliers other than 1.0 (§3.5).

### Terminology note

"Additivity" and "equal gains from switching" are both used in the literature for the condition in §2.4. This guide uses them interchangeably and attributes neither to a specific originating paper.
