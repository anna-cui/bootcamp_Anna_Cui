# Portfolio Drift Monitor: a summary

**Anna Cui · NYU FRE 5040 · Data through 28 August 2026**

Written for a reader with no background in statistics or programming. The technical version
is `reports/final_report.md`; the reasoning behind each choice is in `docs/`.

---

## The problem

A client's money is invested according to a plan. For every $100, the plan puts **$60 into
US shares, $30 into international shares, and $10 into bonds**.

The plan is set once, on the day the money goes in. After that nobody touches it. But the
three investments do not grow at the same speed, so the mixture quietly stops matching the
plan. If US shares have a good year and bonds have a flat one, the $60 becomes $63 and the
$10 becomes $9.60, without anyone buying or selling anything. The plan on paper still says
60/30/10; the actual portfolio no longer does.

This is called **drift**, and it matters because the plan was chosen for a reason. A
portfolio that has drifted toward shares is taking more risk than the client agreed to. The
usual fix is to sell a little of what has grown and buy a little of what has not, which
costs money and is only worth doing when the drift is large enough to matter.

So the firm needs to know two things: **how far the portfolio has drifted today**, and
**whether it is heading toward the point where someone should act**. The firm's rule is that
drift beyond **3 percentage points** deserves a conversation and beyond 5 requires action. A
percentage point here is simple: if the plan says 60% and the portfolio is at 61.5%, that is
1.5 percentage points of drift.

The people involved are the **firm's principal**, who decides whether to rebalance, and
**Dana**, a client-service associate who answers client questions, works in Excel, and does
not run computer code.

---

## What I built

Four things, in order.

**A daily record of the drift.** The system downloads each fund's closing price, works out
what the portfolio is actually worth in each, and compares that against the plan. This is
bookkeeping, but it has to be right: a missing day of prices, filled in quietly, would
corrupt everything downstream, so every filled-in price is flagged and counted.

**A forecast of where the drift is going.** Knowing next month's drift gives the principal
time to act before a threshold is crossed rather than after. The system looks at how the
drift has been moving, how volatile each fund has been, and how far apart shares and bonds
have been performing, and projects the drift **one month ahead**.

**An honest measure of how much to trust that forecast.** The hardest part of the project
and the most important. A forecast that says "1.6" is nearly useless alone, because it gives
no sense of whether the real answer might be 1.5 or might be 3. The system publishes a
**range**, calculated so the real answer should fall inside it 19 times out of 20.

**A way for people to actually use it.** A short written report for the principal, carrying
the caveats. A spreadsheet for Dana that opens with a double-click and contains no
statistical vocabulary at all, just today's drift, next month's projection, a colour, and
what to do. And a small program the firm's systems can query directly.

---

## What it found

**No fund needs attention this month, and that holds up under scrutiny.**

| Fund | Drift today | Projected in a month | Realistic range | Verdict |
|---|---|---|---|---|
| US shares | 0.56pp | 0.64pp | 0.33 to 1.04 | fine |
| International shares | 1.15pp | 0.99pp | 0.68 to 1.39 | fine |
| Bonds | 1.70pp | 1.64pp | 1.33 to 2.04 | fine |

The line that would trigger a conversation is **3 percentage points**. The worst case
anywhere in that table is 2.04, and I tested this against every assumption I had made: the
widest number any version of the analysis produced was **2.14**. There is no reasonable way
to look at this data and conclude that action is needed this month.

**The forecast is meaningfully better than doing nothing.** The obvious cheap alternative is
to assume next month's drift equals today's. The system is about **26% more accurate** than
that. It is not a large edge, and it is honest to say so, but it is a real one.

**Three findings surprised me, and two of them changed the project.**

The first was that **the effort had been going into the wrong place**. Near the end I tested
how much each of my assumptions actually moved the final answer. The choice of statistical
method, which several weeks of work had gone into, moved it by 0.10 percentage points. The
assumption that **next month will resemble the last twelve** moved it by 0.31, three times as
much. The single most valuable improvement available to this project is not a cleverer
model. It is **more history** than one year.

The second was that **a problem I had been asked to fix could not be fixed**. An earlier
stage found the system was consistently under-predicting drift for two of the three funds
and recommended a specific correction. When I tried it, the correction turned out to be
mathematically impossible in two separate ways, and more importantly it would not have
helped even if it had worked: the system is not making a mistake, the world moved between
the period it learned from and the period it was tested on. Average drift rose by 0.31
percentage points between the two. No amount of adjustment to the method fixes that. What it
calls for is publishing the size of the gap and watching it, which is what the system now
does.

The third was that **making the model simpler made it better**. Eleven inputs were less
accurate than five, and fitting each fund separately was worst of all. The reason is worth
stating: the data holds far less independent information than its size suggests. It looks
like 501 observations, but because each month-ahead forecast overlaps almost entirely with
the next, it behaves more like **24**. Twenty-four observations do not support a complicated
model, and that single number quietly constrains most decisions in the second half of the
project.

---

## What I would not rely on

**One year of data, and one calm year.** All of this rests on a single year in which nothing
dramatic happened. Nobody knows how this behaves in a market panic, because it has never
seen one. This is the largest weakness by some distance.

**The ranges are floors, not ceilings.** The honest statement is "at least this uncertain",
not "exactly this uncertain". There is not enough test data to measure uncertainty properly
at a one-month horizon, and I would rather say so than round it off.

**The bond fund is the weak point, and it is also the closest to the line.** It is the fund
the system is least accurate about and the one nearest the 3-point threshold. That is the
worst possible pairing of the three, and it is why the report recommends watching the top of
the bond fund's range rather than its central estimate.

**Nothing here has run in real conditions.** The alert has never fired, because the drift
never came close enough, so the alarm itself is untested. The handover notes tell whoever
inherits this to treat the first alert as a possible bug before treating it as a real event.

**This is coursework, not a production system.** It runs on one laptop, has no security, and
would need proper engineering before real money depended on it.

---

## What I would do next

1. **Get more history.** Five years rather than one. This is worth roughly three times more
   than any improvement to the method, and it is also the only thing that fixes the
   uncertainty ranges being floors. If only one thing on this list happens, it should be
   this one.

2. **Decide the threshold deliberately.** The 3-point line was set early and never revisited.
   The system can now answer "what would this look like at 2 points" in a second, and the
   answer is interesting: at 2 points the bond fund would need review, and it would need it
   because of the top of its range rather than its central estimate. That is a conversation
   the principal should have on purpose rather than by default.

3. **Let it run on a schedule and watch what happens.** Once a month, automatically. Most
   remaining unknowns only reveal themselves in operation, including whether the alert works.

4. **Revisit after any period of market stress.** Everything here assumes the next month
   resembles the last twelve. The first time that stops being true is the first real test.

---

## In one paragraph

The portfolio has drifted from its plan, as any unattended portfolio does, but not far, and
it is not projected to drift far enough in the next month to be worth acting on. That
conclusion survives every assumption I was able to vary. The system that produces it is
modest, honest about its limits, and more accurate than the obvious alternative by about a
quarter. Its single biggest weakness is that it has only ever seen one calm year, and the
most valuable next step is to show it more history rather than to make it cleverer.
