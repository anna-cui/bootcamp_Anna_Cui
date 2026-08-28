# Outlier Definition, Assumptions and Risks

**Project:** Portfolio Drift Monitor · **Stage:** 07 · **Window:** 251 trading days, 753 fund-days
**Code:** `src/outliers.py` · **Evidence:** `data/processed/drift_profile_*.csv`, `threshold_sensitivity_*.csv`, `return_outliers_*.csv`

## Two definitions, deliberately kept apart

This monitor has two places something can be called an outlier, and they are different problems with different correct responses.

| | Input side | Output side |
|---|---|---|
| **What it is** | A price that looks wrong | A drift day worth acting on |
| **Judged on** | Daily returns, per fund | Drift in percentage points |
| **Rule** | IQR (k=1.5) and z-score (3.0) | `AMBER_PP = 3.0`, `RED_PP = 5.0` |
| **Correct response** | Investigate, then keep or repair | Tell the decision owner |
| **A false positive costs** | Wasted attention | An unnecessary trade |
| **A false negative costs** | Manufactured drift in the report | A portfolio left off-target |

Conflating them is how a drift report ends up confidently wrong: a broken close flows straight into the weights and manufactures drift that never happened.

## Input side: are the prices trustworthy?

Returns are judged **within each fund separately**. Pooling would be wrong — BND's ordinary day is a fraction of VXUS's, so one shared fence would flag routine equity moves while missing a genuinely broken bond quote.

**Result: 24 of 753 fund-days (3.2%) flagged by IQR, 11 (1.5%) by z-score.** The z-score flags are a strict subset of the IQR flags.

| Fund | IQR flags | z flags |
|---|---|---|
| BND | 3 | 1 |
| VTI | 8 | 4 |
| VXUS | 13 | 6 |

**No prices were removed.** Two pieces of evidence say these are market days, not data faults:

1. **They cluster across funds.** Ten of the 24 flagged fund-days fall on just five dates — 2025-10-10, 2026-03-20, 2026-03-31, 2026-04-08, 2026-06-05 — and on every one of them the funds moved *in the same direction*. A bad tick hits one feed for one fund. A market day moves everything at once.
2. **The magnitudes are ordinary for the asset.** The largest flagged move is VXUS at +4.1%; the largest BND move is −0.80%. Neither is remarkable for its fund. BND's appearance in this list at all is a demonstration that the fences are per-fund: a 0.7% day is genuinely unusual *for a bond fund*, and would be invisible inside an equity-scaled threshold.

A price is dropped only when there is reason to believe it is wrong. "It was large" is not that reason.

## Output side: where drift actually lives

| Fund | median | p90 | p99 | worst |
|---|---|---|---|---|
| BND | 0.634 | 1.480 | 1.750 | **1.769** |
| VTI | 0.343 | 0.956 | 1.435 | **1.553** |
| VXUS | 0.923 | 1.534 | 2.158 | **2.233** |
| **All** | 0.552 | 1.430 | 1.945 | **2.233** |

Against those numbers, the thresholds currently in force:

| threshold (pp) | fund-days fired | % of fund-days | funds involved | |
|---|---|---|---|---|
| 0.5 | 395 | 52.46 | 3 | |
| 1.0 | 220 | 29.22 | 3 | |
| 1.5 | 52 | 6.91 | 3 | |
| 2.0 | 6 | 0.80 | 1 | |
| 2.5 | 0 | 0.00 | 0 | |
| **3.0** | **0** | **0.00** | **0** | **← amber** |
| 4.0 | 0 | 0.00 | 0 | |
| **5.0** | **0** | **0.00** | **0** | **← red** |

**Neither threshold has ever fired.** Amber sits 34% above the worst drift the year produced; red is 2.2× it. The monitor has returned 100% green for 753 consecutive fund-days.

## The alarm has been tested

A monitor that has never fired and a monitor that is broken produce identical output: silence. Before reading anything into a quiet year, the pipeline injects synthetic drift and confirms the flag responds:

| injected | expected | result |
|---|---|---|
| +6.0pp | red | red ✓ |
| −5.5pp | red | red ✓ |
| +3.5pp | amber | amber ✓ |
| +0.4pp | green | green ✓ |

The −5.5pp case is there on purpose: the rule must be symmetric in sign, since a fund can drift below its target as easily as above. These run as `assert` statements inside `project_pipeline.ipynb`, so a regression in `flag_drift` fails the pipeline rather than silently disarming the monitor.

**This converts a year of silence from unknown into evidence.** The monitor is not broken. The portfolio simply never drifted far enough to trip it.

## Decisions

**The 3pp and 5pp thresholds stay where they are.** The tempting move after a year of green is to lower them until something lights up. That is tuning the policy to flatter the output. The thresholds encode what the firm principal considers worth *acting on* — a trade has costs, and a rebalance triggered by a 2pp deviation may cost more than the deviation does. No amount of quiet data changes that judgement. What the sweep earns is the right to state the position: the lines are high relative to this window, that is deliberate, and here is the number.

**A 2.0pp "watch" level is proposed, for reporting only.** A report that says green 100% of the time gives Dana nothing to look at and no way to tell a working monitor from a stalled one. At 2.0pp, six fund-days a year would be marked — roughly one every two months, all VXUS. That is frequent enough to be informative and rare enough to mean something. It would carry **no action requirement**: it says "this is the largest drift we have seen," not "do something." (For comparison: a 1.5pp line would mark 52 fund-days, about 7%, which starts to be noise.)

**Nothing is deleted anywhere.** Both sides flag rather than filter, and the flags travel with the data as columns. The person reading the report decides.

## Assumptions, and what breaks if they are wrong

| # | Assumption | If wrong |
|---|---|---|
| 1 | The five multi-fund dates are market moves, not feed errors | Real bad ticks are sitting in the weights, and drift is overstated on those days |
| 2 | One year is representative enough to say the thresholds are high | 2025-26 was unusually calm; the lines may be correctly placed for a normal year and we have simply not seen one |
| 3 | Drift measured in percentage points is the right unit for all three funds | See below — this is the weakest assumption here |
| 4 | Daily closes are the right sampling frequency | Intraday drift could exceed the daily figure and never be seen |
| 5 | The target weights themselves are correct | Everything above measures deviation from a number nobody has re-examined |

### The unit problem (assumption 3)

A single percentage-point threshold treats all three funds as equivalent, and they are not:

| Fund | target | worst drift | drift **relative to target** |
|---|---|---|---|
| BND | 10% | 1.769pp | **17.7%** |
| VXUS | 30% | 2.233pp | 7.4% |
| VTI | 60% | 1.553pp | 2.6% |

In absolute terms BND looks like the calmest fund. In relative terms it is by far the most off-target — nearly a fifth away from its intended allocation — and the pp rule is *least* sensitive to exactly the fund where a given pp move matters most. A 1.77pp drift on a 10% sleeve is a materially different portfolio; the same 1.77pp on the 60% sleeve is rounding.

This is not fixed here, because changing the unit changes the policy and that is the principal's call. It is the first thing to raise.

## Risks, ranked by cost

**Discarding a real event is the expensive error.** If a genuine market shock were filtered as a "bad price," the monitor would understate volatility and drift precisely when it matters. In a risk tool, that failure mode defeats the purpose of the tool. This is why the input side flags and never deletes.

**A permanently-green monitor decays into wallpaper.** The subtler risk is human: a report that never says anything stops being read. By the time it does fire, nobody is looking. The watch tier and the committed stress test are both aimed at this — one gives the report something to say, the other proves it can still shout.

**One calm year is thin evidence.** Every conclusion here rests on 251 trading days in which nothing much happened. The honest statement is not "the thresholds are too high" but "the thresholds were never approached in this window, and here is by how much."

## What was not tested

- Whether the two funds' outliers coincide *statistically* rather than just on five eyeballed dates.
- A rolling or per-regime threshold instead of a whole-sample one — which matters for something meant to run daily.
- A median/MAD rule, which would sidestep the sigma-inflation problem that makes z-score thresholds unresponsive.
- Drift measured relative to target rather than in absolute percentage points (assumption 3).

Any of these would be a reasonable next step, and the third and fourth are the ones I would do first.