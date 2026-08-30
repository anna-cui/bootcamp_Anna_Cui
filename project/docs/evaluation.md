# Evaluation and risk - what the model's numbers are actually worth

**Stage 11.** Companion to `src/evaluation.py` and `notebooks/evaluation.ipynb`.

Stage 10a fitted a model and then refused to quote a single interval from it. The reason
was specific: a 21-day forward target makes consecutive rows share 20 of their 21 days, so
501 training rows carry about 24 independent observations while every standard error the
regression reports assumes 501. This stage is the attempt to say something honest about
uncertainty anyway, and where the honest answer is "not from this much data", it says that
instead.

Seed 111, 2000 resamples, 95% level throughout. Test set: 126 fund-days over 42 dates.
Point estimates: MAE **0.1915pp**, RMSE **0.2333pp**, bias **+0.0951pp**.

---

## 1. The three results that change what the monitor publishes

1. **The prediction interval is 11 times wider than the confidence interval**, and the
   prediction interval is the one a reader of a single fund-day needs.
2. **The pooled model is systematically biased** for VTI (+0.215pp) and BND (+0.134pp),
   with bias intervals excluding zero.
3. **The test window is too short to bound its own uncertainty** at the timescale the
   target requires, so every interval here is a floor rather than a bound.

---

## 2. The block bootstrap, and why its answer is a constraint rather than a number

An ordinary bootstrap draws rows independently, which assumes they are independent. On
this panel they are not, so it repeats the error that made Stage 10a's p-values unusable.
A **moving block bootstrap** draws contiguous blocks of dates, with every fund on a date
travelling together, so the dependence survives the resampling.

The block has to be at least as long as the dependence, which for a 21-day target means 21
days. Sweeping the block length:

| block (days) | blocks per draw | distinct start positions | 95% CI | width |
|---|---|---|---|---|
| 1 (= iid) | 42 | 42 | [0.169, 0.214] | 0.044 |
| 3 | 14 | 40 | [0.161, 0.224] | 0.063 |
| **5** | 9 | 38 | **[0.163, 0.227]** | **0.064** |
| 10 | 5 | 33 | [0.180, 0.225] | 0.044 |
| 21 | 2 | 22 | [0.185, 0.217] | 0.032 |
| 42 | 1 | **1** | [0.192, 0.192] | **0.000** |

Two effects run in opposite directions. Longer blocks preserve more dependence, which
*widens* the interval. Longer blocks also leave fewer distinct starting positions, which
*narrows* it, because every replicate starts to resemble the original sample.

**The rise is the real effect: acknowledging dependence widens the honest interval by
about 45%**, from 0.044 to 0.064. **The fall is an artifact.** At block 42 there is exactly
one possible sample and the "interval" is a point.

**The block length this target requires sits inside the region where the estimator has
already degenerated.** With 42 test dates a 21-day block has 22 start positions, so
replicates overlap almost completely and the interval is narrow for the wrong reason.

So the output is a constraint. The best available interval is **MAE 0.19pp, 95%
[0.163, 0.227]** from short blocks, and it is a **lower bound** on the true uncertainty.
A 21-day block becomes usable at roughly 200 test dates, which is about five years of
data at the current split.

**A narrower interval from a longer block is not evidence that dependence is mild. It is
evidence that the sample is too short to measure it.**

---

## 3. Which interval to publish

Two questions that are easy to conflate:

| | Question | Half-width |
|---|---|---|
| **Confidence interval** | where does the true average relationship sit | **0.037pp** |
| **Prediction interval** | where will one new observation land | **0.419pp** |

A factor of **11**. The CI narrows as data accumulates; the PI barely does, because a
single future observation brings its own noise that averaging cannot remove.

**Dana reads one fund on one day.** Publishing the confidence interval to her would
understate the uncertainty by an order of magnitude. The monitor publishes the prediction
interval.

### Gaussian against empirical

| level | Gaussian PI | empirical PI | ratio |
|---|---|---|---|
| 80% | 0.274 | 0.276 | 1.01 |
| 95% | 0.419 | 0.384 | **0.91** |
| 99% | 0.551 | 0.510 | 0.93 |

**This goes the opposite way to the usual worry.** The lecture's example had fat tails, so
its empirical band was wider and normality understated the worst case. Here the empirical
band is slightly *narrower*, so the normal assumption is mildly **conservative**. The
shape numbers say why: residual excess kurtosis is **-0.18**, tails slightly thinner than
normal, and skew is -0.24.

That is the safer direction to be wrong in, and it had to be measured rather than assumed.

---

## 4. Scenario sensitivity: the unit question can be closed

Stage 07 raised whether the threshold should be written in percentage points or as a share
of each fund's target, and left it with the principal. Stage 09 found the relative
formulation more predictable. The question that actually bears on the decision is narrower:
**does the model's value depend on the unit?**

Because MAE in pp and MAE in percent-of-target are not comparable, the column that matters
is improvement over persistence *within* each unit:

| unit | features | model MAE | persistence MAE | improvement |
|---|---|---|---|---|
| pp | 11 | 0.1915 | 0.2372 | 19.2% |
| **pp** | **5** | **0.1759** | 0.2372 | **25.8%** |
| relative | 11 | 0.9610 | 1.0548 | 8.9% |
| **relative** | **5** | **0.7850** | 1.0548 | **25.6%** |

**25.8% against 25.6%. The same number.**

So the conclusion is robust to the unit, and **the principal can settle a question that has
been open since Stage 07 on operational grounds rather than modelling grounds.**

What is *not* robust is the feature count. Eleven features beat persistence by only 8.9% in
the relative unit against 25.6% for five, so Stage 10a's overfitting is worse in relative
units. If the unit does change, the smaller model matters more, not less.

---

## 5. Subgroup diagnostic: the pooled model is not fair to each fund

Stage 08 found `vol_21` correlates **+0.57 for BND and -0.23 for VTI**, so one pooled
coefficient is wrong for both in opposite directions. That damage should appear as per-fund
bias, and it does.

| Fund | n | MAE | 95% MAE CI | bias | 95% bias CI | excludes zero | bias share of MAE |
|---|---|---|---|---|---|---|---|
| VTI | 42 | 0.246 | [0.214, 0.337] | **+0.215** | [+0.169, +0.337] | **yes** | **87%** |
| BND | 42 | 0.169 | [0.096, 0.232] | **+0.134** | [+0.051, +0.223] | **yes** | **79%** |
| VXUS | 42 | 0.160 | [0.098, 0.229] | -0.063 | [-0.208, +0.027] | no | 40% |

MAE and bias are reported separately because **they fail differently**. A large MAE with
zero bias is noise, which more data fixes. A large MAE that is mostly bias is a model wrong
in a fixed direction, which more data does not fix.

**VTI and BND are both systematically under-predicted**, and for VTI 87% of the total error
is that fixed offset. VXUS is the one fund the model is unbiased about.

Block length is 10 rather than 21 for these, because a single fund's slice has a third of
the dates and a 21-day block would leave almost no distinct positions. That is a
compromise, and it is stated rather than hidden.

**The pooled model must not be reported per fund without a correction.** Two options for
Stage 12: per-fund models, or per-fund interactions. The second is cheaper and the fund
dummies already exist.

> **Amended after Stage 12.** The recommendation above was carried out and found to be
> impossible. Both options fail, and for the same reason: **`abs_drift_rel` is `abs_drift`
> divided by the target weight** (maximum discrepancy across the panel, 1.8e-15), so it is
> already `abs_drift` interacted with the fund. Adding the explicit interaction gives a
> singular design matrix, and a per-fund model cannot hold both columns at once.
>
> The deeper error is in calling this a correctable bias at all. **In-sample per-fund bias
> is zero to machine precision** for every fund, because the fund dummies force it, so no
> per-fund term fitted on the training window can see a test bias that is not in that
> window. The target itself moved **+0.31pp** between windows, and BND's moved **+0.81pp**.
> The bias is regime drift, not misspecification.
>
> Measured rather than argued: a separate model per fund spends 15 parameters against about
> 24 independent observations, scores **MAE 0.216** where the pooled 6-parameter model
> scores **0.176**, and leaves **all three** funds biased rather than two. The correction
> that does work is the smaller model plus a published offset. See `docs/reporting.md`.

---

## 6. What the monitor can now publish

Latest observation for each fund, with the **prediction** interval:

| Fund | point forecast | 95% PI | bias-corrected | amber in interval |
|---|---|---|---|---|
| VTI | 0.364 | [0.035, 0.802] | 0.579 | no |
| BND | 1.433 | [1.103, 1.870] | 1.567 | no |
| VXUS | 1.036 | [0.706, 1.473] | 0.973 | no |

**No fund is expected to need attention within the next month, and that statement survives
the uncertainty rather than depending on a point estimate.** The widest upper bound is
1.87pp against an amber line of 3pp.

This is the first forward-looking statement this project has been able to make with a
bound attached.

---

## 7. Assumptions, and what breaks if they are wrong

| Assumption | If wrong |
|---|---|
| The next month resembles the last twelve | The whole forecast fails together. One year, one trending regime, no market stress in the window. |
| 42 test dates can estimate their own uncertainty | Section 2 says they cannot at the relevant timescale. Every interval is a floor. |
| Residual spread is roughly constant | Stage 10a measured 16% more spread at higher predicted values. The interval averages across that. |
| The pooled model is right per fund | **It is not.** Section 5. |
| Persistence is the right baseline in both units | Section 4's conclusion depends on it. |

### Holds if

- volatility stays in the range of the past year, about 13% annualized for VTI, 17% for
  VXUS, 4% for BND;
- the equity-over-bond spread driving the drift persists in the same direction;
- prices keep arriving without gaps, which Stage 06 handles and `close_was_filled` monitors.

### Sensitive to

- **which fund is asked about**: VTI is 0.21pp systematically low, BND 0.13pp;
- **the feature count**: eleven overfits, and worse in relative units;
- **the length of the evaluation window**, more than to any modelling choice.

### Not sensitive to

- **the threshold unit**, 25.8% against 25.6%;
- **the normality assumption**, which is mildly conservative here.

---

## 8. Production monitoring

| Risk | What to watch |
|---|---|
| Regime change breaks the trend the model relies on | Realized volatility against the 13% / 17% / 4% band; re-estimate outside it |
| Per-fund bias grows | Rolling per-fund mean residual; alert if a bias interval moves further from zero |
| The interval is a floor, not a bound | Re-run the block sweep as the window lengthens; a 21-day block becomes usable near 200 test dates |
| Vendor gaps return | `close_was_filled`, built in Stage 09 and currently constant; alert if it stops being |

---

## 9. Handoff to Stage 12

The material for a stakeholder write-up is now in place:

1. a forecast with an interval that survives scrutiny;
2. a named, quantified bias to correct first;
3. an explicit list of what the result holds under and what it is sensitive to;
4. a monitoring plan for production;
5. a three-stage-old open question, the threshold unit, closed on the modelling side.

The one thing Stage 12 should not do is present the confidence interval. It is 11 times
narrower than the prediction interval and answers a question nobody is asking.

> **Amended after Stage 12.** Item 2 above was wrong and is corrected in section 5: the
> named bias is not correctable, and the reason it is not is more useful than the
> correction would have been. Items 1, 3, 4 and 5 held, and the instruction about the
> confidence interval was followed.
>
> Stage 12 also reordered what this list implies. Swinging each assumption against BND's
> 95% upper bound puts **regime at 0.31pp, model specification at 0.10pp, and the
> Gaussian-against-empirical question this document spends section 3 on at 0.02pp**. The
> honest reading is that Stages 09 to 11 refined the third, fourth and fifth largest
> levers, and the largest one is the length of the data window. That is the same fix
> section 2 identified for the degenerate block bootstrap, arrived at independently.
