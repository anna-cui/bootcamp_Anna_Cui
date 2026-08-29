# Feature Engineering - what was built, and why each one exists

**Stage 09.** Companion to `src/features.py` and the Stage 09 section of
`notebooks/project_pipeline.ipynb`. Definitions for the README live in `README.md`;
this file holds the reasoning and the evidence.

Figures are from the `20260828-1756` pull: 251 trading days, three funds, 753 fund-days.

---

## 1. The target had to be invented, and the horizon is a real choice

This project is a monitor. It reports; it does not predict. So there was no target
variable to correlate features against, and one had to be defined before any feature
could be judged.

`flag` is unusable: Stage 08 found it 100% green across all 753 fund-days, so as a label
it has one class.

That leaves the drift itself, some number of days ahead. How many is not a detail:

| horizon (trading days) | corr(today's abs drift, future abs drift) | usable rows |
|---|---|---|
| 1 | **0.979** | 750 |
| 5 | 0.913 | 738 |
| 21 | **0.689** | 690 |
| 63 | 0.235 | 564 |

A one-day horizon is very nearly the feature itself. A model would score above 0.95 by
answering "the same as today" and would have learned nothing. This is Stage 08's trend
finding arriving as a modelling constraint: a trended series is trivially predictable one
step ahead, and the triviality scales with how short the step is. At 63 days VTI's
correlation goes negative and the sample is down to 564 rows.

**Chosen: absolute drift 21 trading days ahead.** Far enough that today's level explains
under half the variance pooled, and a month is enough warning for the principal to decide
whether to rebalance. The pipeline asserts both bounds, so a future pull that breaks them
forces the choice to be revisited rather than quietly becoming a worse question.

---

## 2. The eleven features, and where each came from

Not one was invented because it was easy to compute. The lineage is the deliverable.

| Feature | Origin | Pooled r | Per fund |
|---|---|---|---|
| `abs_drift` | the quantity the threshold is compared against | **+0.689** | BND +0.87, VXUS +0.66, VTI +0.27 |
| `abs_drift_rel` | Stage 07's open unit problem, sized by Stage 08 | +0.621 | identical within fund |
| `drift_chg_1` | Stage 08: build the rate, not the level | -0.010 | all under 0.06 |
| `drift_chg_5` | same, at a weekly step | -0.023 | all under 0.13 |
| `drift_slope_21` | Stage 08: BND's drift correlates with time at -0.93 | -0.108 | VTI -0.39, BND -0.24 |
| `ret_1` | the raw input the drift is built from | -0.026 | all under 0.09 |
| `vol_21` | Stage 08's volatility clustering | +0.036 | **BND +0.57, VTI -0.23** |
| `eq_bond_spread_21` | Stage 08 traced the drift to this spread | +0.054 | BND +0.27, VTI -0.17 |
| `ticker_VTI/VXUS/BND` | Stage 08's 251/251/251 categorical profile | -0.36 / +0.22 / +0.14 | n/a |

Excluded: `drift_slope_63` (24.70% missing, fails Stage 08's own gate, returns -0.001),
`ticker_target` and `ticker_label` (lose to one-hot), `close_was_filled` (constant today).

---

## 3. The unit result, which is a policy finding rather than a modelling one

Stage 07 recorded an open problem: a single percentage-point threshold treats all three
funds as equivalent, when BND's worst drift of 1.769pp is 17.7% of its 10% target and
VTI's 1.553pp is 2.6% of its 60% target. Stage 07 flagged it for the principal and
changed nothing, because changing the unit changes the policy.

Stage 09 can now attach evidence. Building the drift in both units and predicting both:

|  | target in pp | target in % of target weight |
|---|---|---|
| `abs_drift` (pp) | **0.689** | 0.523 |
| `abs_drift_rel` (relative) | 0.621 | **0.906** |

Within a single fund the two features correlate at exactly 1.000000: `drift_rel` is
`drift_pp` divided by a constant, so they are the same information. The difference is
entirely across funds, and the diagonal says each unit predicts its own future best.

**The relative formulation is substantially more predictable a month out: 0.906 against
0.689.** That is not an argument that one feature is better. It is evidence that
measuring drift relative to each fund's target is the more internally consistent
description of what this portfolio does, which is exactly the question Stage 07 left
open.

Still not changed here. It remains the principal's decision. It is simply no longer an
open question with nothing attached to it.

---

## 4. The feature that shows why one-hot encoding was necessary

`vol_21` correlates with the 21-day forward target at **+0.036 pooled**, which reads as
irrelevant, and at **+0.567 for BND** against **-0.227 for VTI**.

The pooled figure is not a weak signal. It is two opposite signals cancelling. A model
without the fund identity would see +0.036, drop volatility, and be wrong about two funds
at once.

That is the concrete payoff of the encoding choice, and the sharpest illustration in this
project of the reading's warning that correlation is a hint rather than a ranking.

### Why one-hot, and not the two alternatives

The choice is settled by one number from Stage 08's categorical profile: the split is
**251 / 251 / 251**, exactly, because Stage 06's `drop_incomplete_days` keeps only dates
with a close for every fund.

- **Frequency encoding is arithmetically a constant here.** All three funds are 33.33% of
  the rows, so the encoded column has exactly one distinct value across 753 rows. It
  carries zero information and would silently occupy a column in the design matrix. The
  homework notebook prints the distinct count rather than asserting this.
- **Label encoding invents an ordering.** It assigns integers alphabetically: BND 0,
  VTI 1, VXUS 2. A linear model reads that as an order *and* a spacing, so it would be
  told VXUS is twice VTI. Both are artifacts of the alphabet. The funds do differ in a
  real ordered way, by target weight, but that order is 0.10 / 0.60 / 0.30. The damage is
  measurable: `ticker_label` correlates with the target at 0.042, while the three one-hot
  columns correlate at -0.360, +0.217 and +0.143. Collapsing three different
  relationships onto one line averaged them away.
- **Target encoding is not used.** The reading raises it and flags the leakage risk.
  On a panel this size, replacing each fund with the mean of its own target values would
  leak the answer unless computed on the training split alone. That is a Stage 10b
  decision.

`ticker_target` (encode each fund by its policy weight, 0.60 / 0.30 / 0.10) is built and
kept as a candidate. It is a genuine ordinal carrying real domain knowledge, unlike the
label encoding. Its limitation is the mirror of its strength: constant within a fund, so
it can only help a model that pools all three.

---

## 5. `close_was_filled` - closing an item the README has carried since Stage 06

The README has said since Stage 06 that a forward-filled close carries the same dtype as
a real one, so once the cleaning log scrolls past, nothing downstream can tell an estimate
from an observation, and that an indicator was the obvious Stage 09 feature.

Built. It is derived by comparing the cleaned frame against the raw pull rather than by
reading `cleaning.py`'s internals, so it stays correct if the fill rule changes.

On this pull it flags **zero rows**, because the vendor delivered three liquid funds with
no gaps. On a deliberately damaged copy it fires on exactly the two repaired rows, which
the homework notebook demonstrates.

**Kept in the pipeline, excluded from the model.** A constant column contributes nothing
and can destabilise a matrix inversion, so it must not go into a model while it is
constant. But it costs one merge, it is verified to work, and on the day a vendor gap
appears it is the only column that can tell a model which rows are estimates. The
alternative is discovering the need for it after a bad quarter with no history of it.

---

## 6. What did not work, on the record

Stage 08's written instruction put the **first difference of drift** at the top of the
feature list, on the reasoning that a trended level makes yesterday's value nearly as good
a predictor as today's, so the information must be in the rate.

`drift_chg_1` correlates with the target at **-0.010**. That is nothing.

The reasoning was right and the implementation was too raw. A one-day change in drift is
almost entirely noise at a 21-day horizon. The signal Stage 08 was pointing at is real,
but it lives in the *smoothed* rate: `drift_slope_21` reaches -0.39 for VTI. The raw
difference is kept in the matrix and excluded from nothing, as a recorded negative result.

Recording a prediction that failed is worth more than deleting the feature and leaving no
trace that the prediction was made.

---

## 7. Leakage: the check, and the check on the check

Every feature here claims to be causal: the value at row *t* uses only rows at or before
*t*. `assert_no_lookahead` tests that instead of asserting it in a docstring. It builds
the features on the full history, builds them again on the history truncated at 70%, and
compares the overlapping rows. A causal feature is identical in both.

The audit passes on all 11 modelling features across 528 overlapping rows.

It is then run against a deliberately broken build, in which one right-aligned window is
changed to `center=True`. It fails immediately, and the message names the giveaway:
truncating the future changed *which past rows are even defined*, because a centred
21-day window needs ten rows after `t` to produce a value at `t`.

This matters because a leaked feature does not raise an error. It raises an R-squared,
and the code and output continue to look correct. `center=True` is a one-word change that
a code review reads as a smoothing preference. In Stage 10b it would produce a test score
that cannot be reproduced in production.

**One leak this audit cannot catch.** Scaling. Standardising features before the split
fits the scaler on rows Stage 10b will hold out, and it happens *after* the features are
built, so the audit never sees it. Nothing is scaled in Stage 09 for exactly that reason.
Scaling belongs inside the split.

---

## 8. Assumptions and risks

| Assumption | Risk if wrong |
|---|---|
| A 21-trading-day horizon is the right question | Chosen on autocorrelation and on what gives the principal useful warning, not on a stated business requirement. A different horizon changes which features matter. |
| 690 usable rows support 11 features | Roughly 63 rows per feature. Enough for a regularised linear model, not for anything with high capacity. Stage 10 should stay simple. |
| Correlation is a useful screen | It is linear and pairwise. `vol_21` at +0.036 pooled and +0.57 within a fund is this stage's own demonstration of the limit. |
| The trend that makes drift predictable will continue | Same caveat as Stage 08. These features describe a trending regime; a mean-reverting one would degrade all of them together. |
| Percentage points are the policy unit | Section 3 gives evidence the relative unit is more coherent. Still open, still the principal's call. |

---

## 9. Handoff to Stage 10

Use `data/processed/features_model_ready_<stamp>.parquet`: 11 features, one target,
complete rows only, 627 of 753 fund-days after windows and the forward target.

Split **chronologically**, as Stage 08 required, and expect a worse score than a random
split would give. A random split on a trended series leaks, because neighbouring days are
nearly identical.

Scale inside the split. Report the drift range of each side next to the score, so the
number is read with the reason it is what it is.
