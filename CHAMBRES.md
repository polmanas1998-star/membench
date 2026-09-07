# Two closed rooms

What the memory layer does when its environment lies, and when the only voice
it can still hear is another copy of itself.

Measured 2026-09-07. `d = 2048`, gate `z >= 4`. Everything here runs offline
and costs zero tokens, because the clock is injected rather than waited for.

    python chambre_close.py      # the rooms, and the long confinement
    python chambre_echo.py       # two instances, sealed in together

---

## Why these two benches exist

Every other bench in this repository assumes a sane environment. A correct
clock. An intact disk. A capacity that is respected. A world that keeps
talking. None of them asks what happens when that assumption falls, and a
memory layer in production meets a broken environment long before it meets an
adversary.

So the question is not accuracy. It is:

> when the room is rigged, does it shout, or does it lie?

Two outcomes, and only one of them is serious.

**Loud.** It refuses, or raises, or answers below the gate. The caller learns
that something is wrong.

**Quiet.** It answers, above the gate, and nothing in the answer says the room
was rigged. The caller has no way to find out.

---

## Room 1: the environment lies

Six rooms. Each one is a failure that actually happens, not a curiosity.

| room | correct | wrong | silent | invented | z when inventing | verdict |
|---|---|---|---|---|---|---|
| healthy control | 18/18 | 0 | 0 | 0/6 | - | sane |
| clock rewound 60 days | 18/18 | 0 | 0 | 0/6 | - | holds |
| clock forward 10 years | 0 | 0 | 18 | 0/6 | - | loud (mute) |
| **tiny store** | 6 | 0 | 0 | **6/6** | **inf** | **quiet** |
| **saturation x10** | 7 | 0 | 11 | **2/6** | **4.83** | **quiet** |
| corrupted trace (NaN) | 0 | 0 | 18 | 0/6 | - | loud (mute) |

`invented` counts answers given about subject/relation pairs **nobody ever
stated**. Silence is the only correct response there, so a z above the gate
while inventing is the serious defect: nothing in the output reports it.

The healthy control matters as much as the rest. It answers 18/18 and invents
nothing. Without it, a bench that finds everyone guilty would only be measuring
its own severity.

### The tiny store, and why it is structural

Six inventions out of six, at infinite confidence. The cause is one line in
`query_gated`:

```python
if len(scored) < 3:
    return scored[0][1], math.inf
```

Under three distinct candidate objects there is no spread to be uncertain
against, so the gate opens rather than closes. The consequence is the opposite
of what you want: **a service that just started, or whose erasure request just
emptied it, is maximally confident about everything.** The store is at its
least informed exactly when it stops doubting.

The comment above that line is honest about the reasoning. The reasoning is
defensible and the outcome is still wrong, and those are two different
statements.

### The rooms that hold

The clock rewound is harmless because `effective_weight` clamps age at zero, so
a reversed clock just makes everything look fresh. The clock forward and the
NaN both end in complete silence, which is the correct failure: the layer stops
rather than guesses.

---

## Room 2: long confinement

The same memory, asked later and later, with nothing relearned.

| after | correct | silent | invented |
|---|---|---|---|
| start | 18/18 | 0 | 0/6 |
| 1 week | 18/18 | 0 | 0/6 |
| 1 month | 18/18 | 0 | 0/6 |
| 45 days (half life) | 18/18 | 0 | 0/6 |
| 90 days | 18/18 | 0 | 0/6 |
| 111 days (threshold) | 18/18 | 0 | 0/6 |
| 6 months | 0 | 18 | 0/6 |
| 1 year | 0 | 18 | 0/6 |
| 10 years | 0 | 18 | 0/6 |

A finer sweep puts the cliff between **day 109 and day 112**. It is sharp,
and there is no dangerous band on either side.

Pushed further: **1, 10, 100, 500, 1 000, 8 000 and 100 000 years.** No
overflow, no date error, no drift. It goes quiet on day 112 and says nothing
for a hundred thousand years, without inventing once.

### A prediction that was wrong, and what it taught

I expected a narrow band during decay where the candidate pool falls under
three and the gate starts answering everything at `z = inf`, joining the tiny
store defect to the passage of time.

It never happens. `len(mem)` stays at 18 and the pool at 10 at **every** age,
because a faded fact leaves the **trace** but never leaves the **store**.
Nothing shrinks, so the tiny store is never reached by ageing.

Which turned out to be the finding.

---

## What ageing actually costs

`forget_faded()` is called by nothing. Not by the library, not by the product,
only by its own test. Decay is therefore a **mute, not a delete**. A faded fact
stays in RAM, on disk, and in every rebuild of the trace, forever.

| faded facts | purged | `len(mem)` | removed | ms per query | correct |
|---|---|---|---|---|---|
| 0 | no | 20 | 0 | 1.2 | 20/20 |
| 200 | no | 220 | 0 | 1.6 | 20/20 |
| 800 | no | 820 | 0 | 3.4 | 20/20 |
| 2 000 | no | 2 020 | 0 | **10.2** | 20/20 |
| 2 000 | yes | 20 | 2 000 | **0.7** | 20/20 |

**8.5x on every query, for facts that contribute nothing**, and accuracy is
identical either way. The fix exists and is already tested. Nobody calls it.

The first version of this measurement was broken, and the giveaway was in the
denominator: `removed` came back 0 in every cell, purge or no purge. I had
backdated `created_ts`, but decay runs from `last_seen_ts`, so nothing had
faded at all. A zero accuses the instrument first. Re-run with the clock
advanced instead of the creation backdated.

The second half of this is not performance. A faded fact is still stored. **If
someone asks to be erased, decay does not erase them.**

---

## Room 3: the echo chamber

Two instances, A and B. The world states 18 facts to A, once, and never speaks
again. B receives one falsehood on a pair the world already settled, plus five
true facts so its own pool has something to doubt against. Then the door
closes: each round, each instance asks the other about every pair it knows and
learns whatever the other answers above the gate. Nothing else comes in.

The transcript is the whole result:

```
THE WORLD told A:  alice travaille_a -> lyon
WE SLIPPED INTO B: alice travaille_a -> amiens

ROUND 1
  A says: alice travaille_a -> lyon    (z 17.7)   the truth
  B says: alice travaille_a -> amiens  (z 47.0)   the falsehood
  after the exchange: A says None, B says None

ROUNDS 2, 3, 4 ...
  A says: alice travaille_a -> (silence)
  B says: alice travaille_a -> (silence)
```

Two things there.

**The less informed instance is the more confident one.** B states its
falsehood at z 47.0 against A's 17.7 for the truth, because B's store is
smaller and a winner separates more cleanly in a smaller pool. Confidence here
is not merely uninformative, it points the wrong way.

**Neither one wins.** The two opposing claims annihilate. The winner no longer
stands clear of the pack, the gate shuts, and the pair stays mute on both sides
at every later round. The falsehood did not survive. Neither did the truth.

A knew that fact. A was right. After one exchange with B it can never answer it
again. Against a no-loop control of 18/18, the loop costs **1 fact out of 18**,
and it is an **erasure, not a corruption**. One contradicting instance is
enough to permanently silence what the other one knew, and nothing in the
output reports the loss.

### The number that does not move

The median z runs from **14.10 to 14.99** across the entire run, loop or no
loop. It says nothing about the state of the loop. **A memory sealed in with
its twin is exactly as sure of itself as one talking to the world.**

### A verdict I had to throw away

My first verdict function announced that the loop "manufactures agreement while
losing accuracy", because agreement rose from 6/18 to 17/18 while accuracy fell
from 18/18 to 17/18. Both numbers are real and the sentence is worthless: B
starts almost empty by construction, so agreement can only rise. Comparing
round 0 to round 8 compares two different things.

The fix was not better wording, it was the missing control: the same memory,
the same number of days, no exchange. That control reads 18/18, and only
against it does the cost of the loop mean anything.

---

## Limits

The corpus is synthetic, which is the only reason "true" and "false" are
decidable at all. One store, mine, run by the person who wrote it.

Two instances do not talk to each other on their own in production. Somebody
has to wire them that way. This bench measures what that wiring costs, not a
natural slope.

They exchange triples, not sentences. There is no language in the loop and no
model call anywhere in either bench, which is why both run in under a second
and cost nothing. Putting a model between them is a different experiment, with
a different price.

Simulating time gives exactly what waiting would give, for the parts that are
functions of the clock. It gives nothing for the parts that are not: memory
leaks, disk growth, a process killed and restarted, state wiped by a
deployment. A real month-long soak would measure those, and only those.

---

## What the tests freeze

`tests/test_chambres.py`, 8 tests. They exist to go red when the behaviour
changes, not to prove it is good. Two of them should go red the day someone
closes the gate under three candidates, and that day they should be deleted
with satisfaction.
