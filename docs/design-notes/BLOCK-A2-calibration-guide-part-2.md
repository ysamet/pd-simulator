> **HOW TO USE THIS FILE.** Everything below the horizontal rule is a single
> prompt for Claude Code. Copy it as *markdown source* — open this file in a
> text editor or use the raw view, not a rendered preview.
>
> **Send this only after Block A1 has confirmed** that
> `docs/explainers/calibration-guide.md` exists and ends with the line
> `Miss one and the invariance is gone.`

---

# PROMPT FOR CLAUDE CODE — BLOCK A2 of 3

## Precondition

Confirm before doing anything else that `docs/explainers/calibration-guide.md` exists and its final line is exactly:

```
Miss one and the invariance is gone.
```

If it does not, stop and report. Do not attempt to repair the file.

## The task

**Append** the content in the fenced block below to the end of `docs/explainers/calibration-guide.md`, preserving everything already there. Insert a blank line and a `---` horizontal rule between the existing final line and the new content, exactly as shown at the start of the fenced block.

Do not:

- alter any existing line in the file
- write or infer any content of your own
- do any research — every word, number, and citation below was drafted and verified in the design layer
- modify any other file
- commit

If you believe something in the text is wrong, **report it rather than correcting it**.

---

## FILE CONTENT (part 2, appended)

```markdown

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
```

---

## Reporting

When the append is complete, report:

1. The file path and its total line count.
2. Confirmation that §0 through §6.4 are unchanged.
3. Confirmation that the file now ends with the Terminology note.
4. A suggested commit message for the complete guide.

Do not commit. Do not modify any other file — the decision-log entries, advisories file, and verification tasks arrive in Block B.

**Action required:** Append the fenced content above to `docs/explainers/calibration-guide.md`, then report the four items listed without committing.
