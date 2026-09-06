# membench

A benchmark for memory layers that **age**, with the controls that make its
numbers mean something.

Recall is the easy half of a memory layer. This measures four things that are
rarely measured together:

| | |
|---|---|
| **retention** | a fact stated once, long ago, never repeated |
| **supersession** | a fact updated since: does the stale value come back? |
| **age** | does the answer say it is old, or serve it as fresh? |
| **absence** | a fact never stated: refuse, or invent? |

Everything is measured against the same corpus, with the base model held
constant so the memory is the only thing that varies.

```
pip install numpy
pip install git+https://github.com/polmanas1998-star/holomem
python sweep.py --seeds 8                # offline, no API key, ~1 minute
python -m pytest                         # 73 tests, offline
```

Full write-up with figures: [`membench-report.pdf`](membench-report.pdf).

## Three layers of control

Most product benchmarks have none of these. They are borrowed openly: HELM
refuses a single headline score, tau-bench scores over repeated trials rather
than one run, GPQA and ARC-AGI validate that the task is hard before reporting
who solved it.

1. **Witnesses** validate the *harness*. One arm that never answers, one that
   always guesses, one that is perfect. If those three do not return three
   distinguishable verdicts, nothing is published. In particular a precision
   computed on zero answers is `n/m`, never `1.000`, or silence wins the
   benchmark.
2. **A trivial baseline** validates that there is something to beat: always
   answer the most frequent object in the corpus.
3. **A shortcut control** validates the *task*. The same memory layer, fed a
   timeline whose objects have been randomly redistributed. If it still scores,
   the questions were answerable without memory.

## Results, 832 questions over 8 seeds

Medians across seeds. `d = 2048`. Lower is better on `stale err` and `halluc`.

> **A median hides a rare error, and this table does.** It reports the memory
> layer at `gated precision 1.000`, while the error table further down reports 2
> hallucinations out of 176 absent facts. Both come from the same 832 questions
> and they cannot both be true: an answer on a fact never stated is answered and
> not correct, so it lowers precision. The median reads 1.000 because those 2
> errors live in a minority of seeds. **Pooled over all 8 seeds, precision is
> `0.995`.** A median describes a typical seed; only a pooled rate describes the
> system.

| arm | cover | gated P | retain | stale err | age | deep ret | halluc |
|---|---|---|---|---|---|---|---|
| oracle | 0.788 | 1.000 | 1.000 | 0.000 | 1.000 | 1.000 | 0.000 |
| majority baseline | 1.000 | 0.062 | 0.071 | 0.056 | 0.000 | 0.071 | 1.000 |
| **memory layer** | 0.500 | **1.000** | **1.000** | **0.000** | 1.000 | **0.000** | **0.000** |
| layer [scrambled] | 0.524 | 0.043 | 0.036 | 0.000 | 1.000 | 0.000 | 0.000 |

Paired bootstrap over the 832 questions, 4 000 draws, 95 % intervals:

| difference in gated precision | interval |
|---|---|
| layer − scrambled twin | **+0.959 [+0.939, +0.977]** |
| layer − trivial baseline | **+0.933 [+0.915, +0.950]** |
| layer − perfect oracle | −0.005 [−0.012, **+0.000**] |

The last band touches zero: the shortfall against a perfect oracle is not
distinguishable from sampling noise at this size. That is not the same as being
perfect.

### Two repetitions of a lie beat one statement of truth

The trace is a **sum** of `bind(S, R, O)`. Nothing in that addition separates a
fact said once from a fact said twenty times, or a true one from a false one.
So the question an industrial buyer asks first is not whether poisoning is
possible, but from how many repetitions, and whether it shows.

Threat model, stated: the attacker writes to the memory on the same terms as
the legitimate source. 12 attacked pairs per point, `d = 2048`, 60 background
facts so the attacker is not fighting an empty store.

| lies told | truth returned | silence | **lie returned** | median z |
|---|---|---|---|---|
| 1 | 0.50 | 0.00 | 0.50 | 4.45 |
| 2 | 0.08 | 0.08 | **0.83** | 5.04 |
| 3 | 0.00 | 0.00 | **1.00** | 6.11 |
| 8 | 0.00 | 0.00 | **1.00** | 6.37 |
| 20 | 0.00 | 0.00 | **1.00** | 6.54 |

Two things, and the second is worse than the first.

**Silence is `0.00` almost everywhere.** A layer that went quiet under attack
would be defensible: it would degrade cleanly. It does not go quiet. It
asserts.

**The confidence score rises with the attack.** From `4.45` at one repetition to
`6.54` at twenty. The gate does not merely miss the poisoning, it **rewards**
it: repetition makes the lie sharp, and sharpness is exactly what the gate
scores. A guard that measures how clearly a memory stands out will measure a
forgery just as clearly.

Repeating the truth helps a little and not for long. Stated three times, it
survives one and two lies; past that it is a weighted vote and whoever repeats
more wins.

**This is not an implementation bug.** A superposition carries no provenance, so
a legitimately reinforced fact and a repetition attack are structurally the same
event. The fix does not live in this layer. It lives in what is allowed to write
to it. Said plainly: this memory must never be writable by an untrusted party,
and no amount of tuning the gate changes that.

Reproduce with `python poisoning.py --seeds 12`.

### The uncomfortable result

The scrambled control keeps coverage at 0.524, slightly **above** the honest
layer's 0.500. It answers just as often while being wrong 96 % of the time, and
the confidence gate does not notice.

**The gate measures internal consistency, not correctness.** Fed well-formed
false memories, the layer is exactly as confident. No internal signal fixes
this; only corroboration against something outside the trace can.

## The capacity surface, 262 080 questions

Six trace dimensions by five corpus sizes by 20 seeds, entirely offline. A
product benchmark publishes one cell; the only thing this costs is local
compute, so there is no excuse for it.

Coverage:

| d \ n | 52 | 104 | 208 | 312 | 416 |
|---|---|---|---|---|---|
| 256 | 0.240 | 0.135 | 0.053 | 0.026 | 0.019 |
| 512 | 0.375 | 0.260 | 0.132 | 0.080 | 0.048 |
| 1024 | 0.481 | 0.394 | 0.262 | 0.181 | 0.130 |
| 2048 | 0.596 | 0.505 | 0.392 | 0.317 | 0.263 |
| 4096 | **0.654** | 0.596 | 0.505 | 0.431 | 0.392 |
| 8192 | **0.654** | **0.654** | 0.599 | 0.545 | 0.500 |

![capacity surface](figures-4-capacity-surface.png)

Three things one cell could not show.

**Coverage saturates at 0.654.** At n = 52, going from d = 4096 to d = 8192 buys
nothing. That is not a capacity limit, it is the corpus: roughly a third of every
corpus is facts never stated or past the forgetting threshold, and refusing those
is the correct answer. **The ceiling is the question set, not the memory.**

**Overload makes it silent, not wrong.** At d = 256 and n = 416 coverage collapses
to 0.019 while gated precision holds at 0.764. Across the other 29 cells precision
never drops below 0.905. A store pushed past its capacity stops answering rather
than starting to lie, which is the behaviour a confidence gate is for.

**The gap to the scrambled control never falls below +0.750**, anywhere on the
surface, including the most degraded corner. The task requires memory everywhere,
not only at the operating point that suits us.

Raw cells with their ranges: [`results-capacity-surface.json`](results-capacity-surface.json).
Reproduce with `python grid.py --seeds 20`, about 26 minutes on a laptop.

## Interference costs nothing measurable

A holographic trace is a sum of `bind(S, R, O)`, queried with
`unbind(trace, bind(S, R))`. When many facts share a subject, the noise the
others pour into the answer stops being independent: it is correlated by that
shared subject. This is the worst case for this design, and it is the real one,
because people talk about themselves, one project, one machine.

Fact count held **constant** at 30, same mix, same trace length. Only the
structure changes: the same facts concentrated onto fewer and fewer subjects.
Medians over 8 seeds.

Rates pooled over 8 seeds, not median.

| relations per subject | d = 128 | d = 2048 |
|---|---|---|
| | cover / precision | cover / precision |
| 10.0 (3 subjects) | 0.237 / **1.000** | 0.642 / **1.000** |
| 6.0 (5 subjects) | 0.204 / 0.980 | 0.650 / **1.000** |
| 3.8 (8 subjects) | 0.263 / 0.984 | 0.646 / 0.994 |
| 2.5 (12 subjects) | 0.233 / **1.000** | 0.654 / 0.994 |

Precision stays between `0.980` and `1.000` throughout, with no trend against
concentration, and the gap to the scrambled twin never falls below `+0.858`.
The residual errors are the same absent-fact hallucinations found everywhere
else, not a product of interference.

**A flat result accuses the instrument first**, so the sweep was repeated at
`d = 128`, where the memory is genuinely stressed: coverage drops from 0.65 to
0.25, which proves the store is near its limit and the gate is working. The
precision still does not move.

The reading is the same as the capacity surface: **overload makes it silent,
not wrong**, and correlated noise behaves like any other noise. Below the
confidence threshold the layer refuses rather than guesses.

Scope, honestly: 30 facts, three dimensions, a 4x range of concentration. A
wider range needs a larger subject vocabulary, which this corpus does not have.
Reproduce with `python interference.py --seeds 8 --dim 128`.

## Where the errors are

Outcome by question class, 8 seeds:

| class | correct | silence | wrong | stale value | hallucinated | n |
|---|---|---|---|---|---|---|
| stable | 144 | 0 | 0 | 0 | 0 | 144 |
| reinforced | 80 | 0 | 0 | 0 | 0 | 80 |
| superseded | 112 | 32 | 0 | **0** | 0 | 144 |
| faded | 75 | 101 | 0 | 0 | 0 | 176 |
| expired | 0 | 112 | 0 | 0 | 0 | 112 |
| absent | 0 | 174 | 0 | 0 | **2** | 176 |
| **total** | **411** | **419** | **0** | **0** | **2** | **832** |

On the 368 questions the system should be able to answer: **336 correct, 0
wrong.** Silence rises monotonically with how little it is entitled to know.

This table paid for itself. The first pass showed 3 wrong answers on facts past
the forgetting threshold, a class where the layer had *zero* correct answers out
of 112. Past that line the trace no longer holds the fact; what remains is noise,
and the confidence gate scores noise the way it scores a memory. Refusing the
class outright cost no correct answer and removed three of five errors.

> A confidence gate and an age gate are not the same thing. One asks how sharp a
> memory is, the other whether it has any right to exist. A system with only the
> first is confident about its own decay products.

That sentence was briefly withdrawn and is restored. The ablation table below
confirms it in numbers: removing the age gate costs 0.7 points of precision, the
3 errors it exists to catch. The withdrawal came from taking a median across
seeds, which cannot see an error that occurs in two seeds out of eight.

## Ablation: what each guard actually buys

Four pieces, removed one at a time. `d = 2048`, 8 seeds, 832 questions per row,
**rates pooled over all seeds**, entirely offline.

| variant | removed | cover | precision | halluc | stale | deep ret |
|---|---|---|---|---|---|---|
| **complete** | nothing | 0.496 | **0.995** | 0.011 | 0.000 | 0.000 |
| no z gate | the confidence threshold | 0.865 | 0.726 | **1.000** | 0.000 | 0.000 |
| no age gate | refusal past 111 days | 0.500 | **0.988** | 0.011 | 0.000 | 0.000 |
| no decay | the 45 day half-life | 0.620 | 0.880 | 0.011 | **0.417** | 0.000 |
| no weight floor | eviction below 0.18 | 0.499 | 0.995 | 0.011 | 0.000 | 0.000 |
| eternal memory | decay **and** age gate | 0.754 | 0.901 | 0.011 | 0.417 | **0.991** |

**The z gate is the product.** Remove it and hallucination on facts never stated
goes from `0.011` to `1.000`: it invents on every single one. Everything else in
this repository is a refinement; that one line is the thing being sold.

**Decay is what makes supersession work.** Remove it and a replaced value comes
back as current `0.417` of the time. The old and the new statement then compete
forever on equal weight, and the more often the old one was said, the better it
does.

**The age gate earns 0.7 points of precision**, `0.988` to `0.995`. Exactly the
3 errors it targets: facts at 159, 192 and 242 days that the memory answered
with a z above the confidence threshold. Small, real, and it took a second
instrument to see it.

**The weight floor changes nothing measurable here.** It is a noise and cost
optimisation, not a correctness one, and this table says so rather than letting
a reader assume otherwise.

**Deep retention is a choice, and here is its price.** The last row turns
forgetting off entirely: every fact past the threshold becomes recoverable,
`deep_retention` from `0.000` to `0.991`. It costs `0.417` stale values and nine
points of precision. That is the trade this design makes, stated as a number
rather than as a preference.

### The median nearly cost a published claim

The first version of this table took the **median** of per-seed rates. The 3
errors the age gate removes live in 2 seeds out of 8, so the median of
`[1, 1, 1, 1, 1, 1, 0.98, 0.97]` is `1.000`. The table showed the age gate
changing nothing at `d = 2048`, `4096` and `8192`, and on that basis a **true**
statement in this README was withdrawn and the guard documented as dead weight.

The calibration bench, which pools every seed, found the 3 errors sitting above
the threshold and sent the claim back.

A median is blind by construction to a rare event. A rare error rate is computed
over the **total** number of questions, never by summarising rates whose
denominators differ: that gives a seed with no errors the same weight as a seed
carrying three. Both this table and `interference.py` were rewritten to pool,
and a test now fails if anyone summarises by seed again.

Reproduce with `python ablation.py --seeds 8 --dim 2048`.

## Is the confidence score meaningful?

`gate_sweep.py` answers *where to cut*. This answers a harder question: **among
the answers it does give, does the score separate the right ones from the
wrong?** A threshold can work perfectly while the score above it carries no
information at all.

Gate disconnected, `z_gate = 0`, so every answer the layer would produce is
observed, including those it normally refuses. 832 answers, 8 seeds.

| z band | n | share correct |
|---|---|---|
| [1, 2) | 82 | 0.024 |
| [2, 3) | 228 | 0.211 |
| [3, 4) | 106 | 0.632 |
| [4, 5) | 61 | 0.918 |
| [5, 6) | 51 | **1.000** |
| [6, 8) | 89 | **1.000** |
| [8, inf) | 215 | **1.000** |

Strictly monotone. **Concordance 0.956**: draw one correct and one wrong answer
at random and the correct one carries the higher z 95.6 % of the time. That is
an AUROC, so it depends on no threshold and no choice of bands. Median z is
`6.89` on correct answers, `2.25` on wrong ones.

Above the cut at `z = 4` there are exactly 5 errors in 416 answers: **3 expired
facts and 2 never stated**. The age gate removes the first three. The last two
are the 2 hallucinations in the error table, and nothing in this design catches
them, because a fact that was never stated has no age to check.

### The three uncomfortable results are one result

Read with the scrambled control and the poisoning bench, this says something
precise. **The score measures how cleanly one candidate dominates the trace.**
On an honest trace, dominance and truth coincide almost perfectly, which is the
0.956 above. On a scrambled trace, dominance survives and truth does not. Under
a repetition attack, dominance is purchasable, and the score rises as the lie is
repeated.

The gate is not weak mathematics. It is a correct measurement of the wrong thing
whenever the trace stops being trustworthy, and its validity is inherited
entirely from control over who may write to it.

Reproduce with `python calibration.py --seeds 8`.

## The gate is a dial, not a number

Saying the layer answers half the questions describes one setting. 5 seeds:

| z | coverage | gated precision | hallucination |
|---|---|---|---|
| 1.0 | 0.865 | 0.711 | 1.000 |
| 2.0 | 0.798 | 0.800 | 0.682 |
| 3.0 | 0.596 | 0.952 | 0.091 |
| **4.0** | **0.490** | **1.000** | **0.000** |
| 5.0 | 0.423 | 1.000 | 0.000 |
| 8.0 | 0.250 | 1.000 | 0.000 |

The knee is sharp. Between z = 2 and z = 4 the layer trades a third of its
coverage for two tenths of precision, and hallucination on facts never stated
falls from 0.682 to zero.

## What is lost by design

Deep retention is `0.000` and does not move at d = 1024, 2048 or 4096. A fact
leaves the trace at **111.33 days**, which is 45 × log₂(1/0.18) from the
half-life and the weight floor; measured effective weight is 0.1809 on day 111
and 0.1781 on day 112. This is decay, not capacity. On any fact older than that,
a system that simply keeps the transcript recovers everything and this one
recovers nothing.

## What the layer costs in milliseconds

Everything above measures correctness. Nothing measured time, and the service
carrying this layer runs on 512 MB and **one worker**: a second spent inside a
query is a second in which no other conversation advances. A perfect layer that
blocks the process is not deployable, and no number in this file said so.

The trace is cached and invalidated on every `learn`, which splits the cost in
two. **Cold** is what a real conversation pays: you learn, then you ask, turn
after turn, and the trace is rebuilt from the fact list each time. Warm is the
cost of a second question asked straight after the first.

Minimum over 60 trials, `d = 2048`, Windows, Python 3.11.

| facts | learn, per statement | warm query | **cold query** | trace size |
|---|---|---|---|---|
| 50 | 0.40 ms | 2.2 ms | **8.3 ms** | 32 KB |
| 100 | 0.73 ms | 3.9 ms | **10.7 ms** | 32 KB |
| 200 | 0.93 ms | 6.5 ms | **17.2 ms** | 32 KB |
| 500 | 2.39 ms | 16.2 ms | **43.3 ms** | 32 KB |
| 1000 | 4.95 ms | 33.5 ms | **87.6 ms** | 32 KB |
| 2000 | 12.51 ms | 66.3 ms | **209.6 ms** | 32 KB |

**Constant memory, linear time.** The trace stays at 32 KB whatever N is, which
is the whole promise of a superposition and this column verifies it. The clock
does not: rebuilding from the fact list is O(N), so a query costs proportionally
more as the store fills.

That tension is deliberate and documented in the library: the trace is rebuilt
rather than patched, because every weight depends on `now`, and an incrementally
maintained trace would drift away from the facts it claims to represent, in
silence. Correctness was chosen over speed. This table is the price of that
choice, stated rather than assumed.

Taking 100 ms as the point where a single worker visibly stalls: `d = 1024` and
`d = 2048` cross it at 2000 facts, `d = 4096` at 1000. For a per-user store of a
few hundred facts, the cold query stays under 50 ms and the question does not
arise. For a store of thousands, it does, and the answer is incremental
maintenance, not a bigger machine.

### The measurement was contaminated, and how that was caught

The first series was taken while a paid campaign ran in the background. At
`d = 2048` it read 250 ms at 500 facts, 924 ms at 1000, then 219 ms at 2000:
not monotone, therefore impossible for a linear cost, therefore contaminated.

Under contention every timing is inflated by a random amount that is always
**positive**; noise never cancels, it only adds. A median absorbs it without
removing it. The **minimum** over many trials keeps the run in which the machine
interfered least, and that is the estimator this bench uses.

The ratio of median to minimum is now computed for every row and printed. On a
quiet machine it sits between 1.1 and 1.5. Above 2.0 the row is labelled
contaminated and excluded from the thresholds rather than published. This repo
has paid for a timing taken under its own background load once before, at the
cost of a figure published on GitHub and on Reddit.

Reproduce with `python latency.py`.

## External validity

The corpus is synthetic: 104 generated subject-relation-object facts about a
fictional architecture practice, on a simulated timeline. That buys exact ground
truth, a known denominator for every class, and byte-for-byte reproducibility
per seed. It does **not** buy:

- **natural language** — real users state facts in prose, ambiguously, across
  turns. Every fact here arrives as a clean triple, which flatters both this
  layer and any retriever it is compared to;
- ~~**realistic fact distributions**~~ — **this limitation was wrong, and is
  withdrawn.** It claimed that "one subject carrying many interfering relations"
  was absent. Measured 06/09/2026: the vocabulary holds 12 subjects and 10
  relations, so 120 pairs, and the default mix consumes 104 of them. The corpus
  runs at 87 % of pair saturation, with **8.7 relations per subject**.
  Interference was not absent, it was near maximal, and nobody had counted it.
  What is genuinely absent is natural interference *structure*: which subjects
  attract many relations is uniform here, where a real transcript is heavy-tailed;
- ~~**a second domain**~~ — **withdrawn as a limitation, with a reason.**
  `symbol(name, dim)` derives each vector from a blake2b hash of the folded
  name, so any two distinct names are near-orthogonal whatever they mean. The
  vocabulary cannot influence a single number in this file, and a second domain
  built the same way would measure nothing. What a second domain would really
  test is a different fact *distribution*, not a different set of words, and
  that is covered by `interference.py`;
- **a second base model** — every model-side number was taken on
  `openai/gpt-oss-120b`;
- **real ageing** — time is simulated.

What it does support are statements about the layer's own arithmetic under known
conditions: precision, refusal behaviour, the shape of the confidence curve and
the location of the forgetting threshold are properties of the algorithm.
Everything comparative is a hypothesis to be re-tested on real transcripts.

## Cost per correct answer, re-taken

The earlier cost comparison was withdrawn: it used a candidate list sorted
identically in every question, so a model's position preference could not be
separated from its memory. The list is now reshuffled per question from a seed
derived from the question, identical across arms, and the numbers below are the
re-measurement rather than an amendment.

One seed, 104 questions, `openai/gpt-oss-120b`, `d = 2048`.

| arm | cover | precision | halluc | stale err | **tokens per correct answer** |
|---|---|---|---|---|---|
| **D+ layer, then model** | 0.510 | **1.000** | **0.000** | **0.000** | **1 306** |
| C retrieval top-k | 0.808 | 0.964 | 0.091 | 0.056 | 1 801 |
| A model alone | 0.000 | n/m | 0.000 | 0.000 | never correct |
| B full transcript | — | — | — | — | **did not fit in a day** |

The layer answers half as often and is right every time it does. Top-k answers
more, invents on 9 % of facts never stated, and serves a superseded value 5.6 %
of the time. Per correct answer it costs **1.38x more**.

Arm A is the witness that matters most: 133 132 tokens spent to answer nothing
correctly, because a model with no memory cannot answer a memory question. It
is what makes the task's difficulty visible rather than assumed.

### The full-transcript arm does not fit inside a day

Not a failure, a measurement. Pasting the whole transcript costs **3 483 tokens
per question**, so one seed of 104 questions needs about **362 000 tokens**. The
account's ceiling is **200 000 tokens per day**.

The campaign hit it, and the log is the clearest statement of the result
(Paris time; the log itself wrote UTC without saying so, which is its own entry
below):

    19:50  daily ceiling reached: 200 000/day, 198 839 consumed -> sleep 15 min
    20:05  200 000 consumed -> sleep 15 min
    20:20  197 917 consumed -> sleep 15 min
    20:50  199 335 consumed -> sleep 15 min

An hour of naps and no progress. The window is **rolling, not reset at
midnight**: the counter drifts between 197 917 and 200 000 instead of dropping,
so what frees up is only what falls out of the trailing window, a few hundred
tokens an hour. The whole 200 000 was spent between 19:28 and 19:45, so it
comes back at 19:45 the next day, not at any round hour.

So the honest line is not "not yet measured". It is: **on this account, a single
seed of full-context cannot be measured at all**, and that is itself the cost
statement. The other three arms together fit in one day; the fourth alone does
not fit in two.

⚠ Two accounting systems, and confusing them costs a day. The per-minute
ceiling debits `prompt + reservation`, which is what `tokens_total` reports
here. The daily ceiling debits **actual** tokens, roughly 1.7x lower. Reading a
daily budget with per-minute arithmetic overestimates consumption; reading it
the other way round underestimates it, which is the mistake made while planning
this campaign.

### The next measurement is sized before it is paid for

`cost_probe.py` now quotes the campaign before the first call, and refuses to
start when the quote does not fit:

    $ python cost_probe.py --devis
    40 questions sur 104, echantillon proportionnel, graine 1, d=2048
      genres : absent 9/22, expired 5/14, faded 8/22, reinforced 4/10,
               stable 7/18, superseded 7/18

    B historique complet       139320 jetons reserves
    D+ couche puis modele       26620 jetons reserves
    A modele seul               51204 jetons reserves
    C recherche top-k           56116 jetons reserves
    TOTAL                      273260 reserves,  156025 reels estimes
    soit 78% du plafond de 200 000 jetons/jour

The same quote at the full 104 questions reads **203 % of the day**, and the
command exits without spending anything. That arithmetic is one multiplication;
nobody did it before the campaign, and it is what a lost day actually costs.

Two other things changed, and both are ordering rather than measurement:

**The unknown arm now runs first.** The lost campaign ran D+, C, A, then B. When
the bucket empties you lose what is still ahead of you, so it lost the only
number it existed to produce and kept three arms already measured. Arms now run
B first, then the rest by increasing cost, and each one's result is written to
disk as soon as it lands.

**The reopening time is derived, not remembered.** A note said the budget
"comes back around 13:00"; it was describing a burst from the day before. The
campaign log made it worse by stamping UTC without labelling it, so `18:50` was
read as 18:50 when the clock in the room said 20:50. Two clock errors in the
same calculation, in opposite directions, and the conclusion was two hours
early. The log now stamps local time with its offset (`19:50:49+0200`), a
campaign records when it started and finished, and a run refuses to start while
the previous burst is still inside the rolling window:

      Campagne precedente terminee le 06/09 a 19:45 +0200.
      Son budget ne ressort de la fenetre glissante que le 07/09 a 19:45 +0200,
      dans 21.9 h.

    Rien n'a ete depense.

**The subsample is proportional to the corpus, not balanced across kinds.**
Equal strata would measure each kind more precisely and make the overall rates
incomparable with the 104-question run: a corpus that is 21 % absent is not
summarised by a sample that is 17 % absent. Proportional allocation with
largest-remainder rounding keeps the sample readable against the full run, which
turns the three known arms into a **control**: if D+ comes back near its 0.510
coverage, the sample is representative and B's first measurement inherits that
credibility. If it does not, the sample is what to read before the arm.

## Running it on someone else's machine

Measured 06/09/2026 on a fresh clone, no configuration: **20 failures out of
73**. Nothing was broken. `holomem` could not be imported, and every test that
needs it discovered that on its own, mid-run, with a different opaque
`ModuleNotFoundError` each time.

Twenty red lines say "this repo is broken" far louder than a README says
"install holomem first", and that verdict is reached before a reader has seen a
single number. For a public benchmark it is the one defect that costs
everything and appears before anything else.

Two fixes, one in each repository.

`holomem` is now installable: it carried no packaging at all, so the only route
was to clone it by hand and point an environment variable at the folder.

And this repo now says so once, at the top of the run, instead of failing
seventy-three times in its own words:

    holomem : ABSENT, tests de la couche sautes.
    pip install git+https://github.com/polmanas1998-star/holomem

A fresh clone with nothing installed now reads **52 passed, 21 skipped, 0
failed**. The skips are honest: they announce their reason and count separately
from success. Making them green without the library would be worse than the
twenty failures, because the repo would then be lying about what it verified.

The environment variable still works, and a sibling clone is found without it.

### The first fix was a text search, which is the wrong instrument

It marked tests by looking for `holomem` or `DermiozArm` in their source. That
took 20 failures down to 2, and stopped there: two tests reach the layer
**indirectly**, through the arm table in `long_run`, without ever writing those
words. A textual detector sees what is named, never what is reached.

It now inspects the exception actually raised, and only an `ImportError` whose
missing module is `holomem`, so a genuine failure on another dependency is
never quietly turned into a skip.

## Harness

- **40 tests, 13 mutants of 13 killed.** Two tests were decorative until
  mutation found them, including one that guarded a counter without ever
  exercising the code that sets it.
- The significance test is itself guarded by comparing an arm against **itself**
  and requiring the interval to contain zero. The first implementation failed
  that: it reported a difference of exactly zero as significant.
- The candidate list is reshuffled per question from a seed derived from the
  question, so it is decorrelated from position and identical across arms.
- An unreadable answer is counted as unreadable, never as a principled refusal.
  A reasoning model given a 48 token output budget spends all 48 thinking and
  returns an empty string, which would otherwise score as perfect calibration.
- Token counts come from the provider's own usage figures, charged as prompt
  plus reservation, which is what the per-minute ceiling actually debits.
- Deterministic corpus per seed: a result is re-runnable byte for byte.

## Layout

| file | what it does |
|---|---|
| `membench/corpus.py` | the ageing corpus and its timeline |
| `membench/scoring.py` | the metrics, and what they refuse to compute |
| `membench/arms.py` | witnesses, trivial baseline, shortcut control |
| `membench/real_arms.py` | the four arms that see a model |
| `membench/stats.py` | paired bootstrap on differences |
| `membench/providers.py` | one provider, and the ceilings it enforces |
| `sweep.py` | the offline table, multi-seed |
| `interference.py` | precision against subject concentration |
| `poisoning.py` | how many repetitions of a lie beat the truth |
| `ablation.py` | what each guard buys, measured by removing it |
| `calibration.py` | whether the confidence score separates right from wrong |
| `latency.py` | milliseconds per query, against store size |
| `cost_probe.py` | tokens per correct answer, on a sample sized to the daily ceiling |
| `gate_sweep.py` | the precision/coverage curve |
| `error_analysis.py` | outcome by question class |
| `bootstrap_report.py` | differences with intervals |
| `long_run.py` | resumable campaign that survives a daily ceiling |

MIT. Numbers are dated and carry their denominators. Anything withdrawn is named
as withdrawn rather than quietly dropped.
