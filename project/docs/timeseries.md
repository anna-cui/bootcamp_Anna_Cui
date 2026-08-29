# Time series forecasting - what the drift's own history is worth

**Stage 10b.** Companion to `src/timeseries.py` and
`notebooks/modeling_timeseries.ipynb`.

Figures from the `20260828-1756` cleaned prices: 624 model-ready fund-days after windows
and the 21-day target, split at 2026-06-01 into 498 training and 126 test rows.

**The short version.** A correctly built time-series pipeline, on correctly built causal
features, with a time-aware split and selection made on cross-validation, forecasts 3%
better than assuming nothing changes, and 26% worse than Stage 10a. The machinery is
right and the result is thin, and both halves of that are the finding.

---

## 1. The track, and why classification is unavailable

The Stage 10b instructions allow classification or time series, with regression already
committed in Stage 10a. Time series is chosen.

**Classification is not available on this data.** Stage 08 found the flag green on all
753 fund-days, so a classifier at the 3pp policy threshold has **zero positive cases** and
cannot be fitted. At 2pp there are 6 positives out of 753, 0.8%, and a model answering
"no" every time scores 99.2% accuracy. That is a real property of the monitor, not a
limitation of method, and it is why the question here is "how far" rather than "will it
breach".

---

## 2. The features, and the one line that makes them causal

Eleven features across all six families the sheet lists: `lag_1/5/21`,
`roll_mean_5/21`, `roll_std_5/21`, `roll_min_21`, `roll_max_21`, `momentum_21`,
`zscore_21`.

**Every rolling statistic is shifted by one after its window.** A rolling mean at row *t*
includes row *t*; using it to predict row *t* means using a number that did not exist when
the prediction was needed. The notebook demonstrates this rather than asserting it: the
causal column at row *t* is exactly the leaky column at row *t-1*.

The leaky version is not obviously wrong when you read it. It is a rolling mean, it looks
like a smoother, and every value is a real number computed from real data. The only thing
wrong with it is *when* it was available.

Everything is grouped by fund. A `.rolling(21)` on the long panel as delivered would
average across VTI, VXUS and BND without raising an error.

Stage 09's `assert_no_lookahead` is run against the Stage 10b builder and passes on all
eleven features across 528 overlapping rows.

---

## 3. The most expensive mistake available at this stage

Features were built on **absolute** drift, matching the target. Building the identical
eleven features on **signed** drift, with the same pipeline, the same split and the same
estimator:

| Features built on | test RMSE | test R² |
|---|---|---|
| absolute drift (correct) | 0.286 | +0.538 |
| **signed drift (wrong space)** | **0.741** | **-2.11** |
| predicting a constant | 0.519 | -0.52 |

The wrong-space model is **worse than predicting a constant**, by a wide margin.

The reason: BND's drift sits negative and VXUS's positive. A linear model handed signed
lags and asked for an absolute target has to represent |y| from inputs whose sign differs
by fund, and it extrapolates disastrously on a test period where the signs are more
extreme.

**No amount of pipeline hygiene rescues a model pointed at the wrong quantity.** That is
worth more than the modelling result below, and it is why `make_lag_features` takes the
source column as an explicit argument rather than defaulting silently.

---

## 4. The Pipeline, and what its guarantee is actually worth

`Pipeline([('scaler', StandardScaler()), ('model', Ridge())])`, built by
`timeseries.build_pipeline` so it is repo code rather than a notebook cell. That is the
Stage 10b requirement, and the point of it is that train-only fitting becomes a property
of the project instead of something to remember.

Stage 10a deliberately did not scale, because fitting a scaler before the split fits it on
rows the test set will contain, and Stage 09's look-ahead audit cannot catch that: it
happens *after* the features are built.

**Measured, the leak costs 0.00001 RMSE.**

The interesting part is why, because it is not that the leaked statistics were similar.
`lag_1` centres at 0.629 on training rows and 0.690 across all rows, a 10% difference,
because the test period runs higher. The leaked information is genuinely different and the
forecast does not move.

Standardising is an affine transformation, and a linear model absorbs an affine change of
its inputs into its coefficients almost exactly. Ridge's penalty applies to the scaled
coefficients, so a trace survives, and that trace is the 0.00001.

**So the Pipeline here is a correctness guarantee that costs nothing, not a performance
trick.** Swap the estimator for a tree ensemble or anything distance-based and the same
leak stops being free, with no change to how the code is written. Making it structural is
what stops that from being a future surprise.

Where it does bite is cross-validation: the scaler is refitted inside every fold, and
fitting it once outside the loop would leak each validation block into the training of its
own fold, repeatedly.

---

## 5. Walk-forward cross-validation, and the spread as the result

`TimeSeriesSplit` trains on a prefix and validates on the block immediately after it,
never training on data that comes after what it validates.

Five folds on `lag_1 + zscore_21`:

| fold | train rows | validate rows | RMSE |
|---|---|---|---|
| 1 | 83 | 83 | 0.401 |
| 2 | 166 | 83 | 0.428 |
| 3 | 249 | 83 | 0.540 |
| 4 | 332 | 83 | 0.656 |
| 5 | 415 | 83 | 0.347 |

Mean 0.475, standard deviation **0.110**. Nearly a factor of two between best and worst.

Fold count changes the picture: 3 folds give sd 0.049, 5 give 0.110, 8 give 0.187. More
folds means smaller training prefixes, and the first of eight trains on under four
effective observations.

**The spread is the result, not a nuisance.** It is Stage 10a's effective sample size
problem seen from another angle: with roughly 24 independent observations, which 80% of
the window a model trains on genuinely changes what it learns. A single train/test number
hides that entirely, and any comparison between models has to survive this much noise
before it means anything.

---

## 6. Selection, done on cross-validation rather than on the test set

| Feature set | k | CV RMSE | CV sd | test RMSE | test R² |
|---|---|---|---|---|---|
| **lag_1 only** | **1** | **0.4666** | **0.107** | 0.2857 | 0.538 |
| lag_1 + lag_5 | 2 | 0.4739 | 0.099 | 0.2833 | 0.545 |
| lag_1 + zscore_21 | 2 | 0.4745 | 0.110 | **0.2732** | **0.577** |
| lag_1 + roll_mean_21 | 2 | 0.4915 | 0.089 | 0.2740 | 0.575 |
| lag_1 + momentum_21 | 2 | 0.5025 | 0.087 | 0.2882 | 0.530 |
| lag_1 + mean_21 + std_21 | 3 | 0.6114 | 0.335 | 0.3724 | 0.215 |
| all 11 features | 11 | 0.7463 | 0.545 | 0.4087 | 0.054 |

**CV and the test set agree on the ranking.** That agreement is the evidence that running
CV was worth it: it would have rejected the eleven-feature model without anyone touching
the test data. Fold instability also rises with model size, from sd 0.107 at one feature
to 0.545 at eleven.

**The selection is `lag_1` alone.** On the test set `lag_1 + zscore_21` is better by 0.013
RMSE, which is about a tenth of the fold standard deviation of 0.110. The two are
indistinguishable, and preferring the simpler one is the disciplined call. Chasing the
0.013 would be selecting on the test set and reporting the result as though it were
validation.

---

## 7. Results

| Predictor | MAE | RMSE | R² |
|---|---|---|---|
| pipeline, `lag_1` | **0.2390** | **0.2857** | 0.538 |
| pipeline, all 11 features | 0.3226 | 0.4087 | 0.054 |
| persistence, no model | 0.2392 | 0.2947 | 0.508 |
| train mean, a flat line | 0.4024 | 0.5187 | -0.524 |
| signed-space features | 0.5112 | 0.7405 | -2.105 |

**3.1% better than persistence.** In the monitor's units, a typical miss of 0.24pp against
a 3pp amber threshold and a worst observed drift of 2.23pp, so roughly a tenth of the
range that matters.

**Stage 10a reached 0.211pp**, 26% better than this, using no lags at all.

---

## 8. The finding that matters most

**The prescribed time-series feature family adds almost nothing on this series.** Lags,
rolling means, rolling standard deviations, extremes, momentum and z-scores are the
standard toolkit. Here they recover the naive baseline and little more, and every addition
past the first feature either fails to help or actively hurts.

**Stage 09's engineered features beat all of them.** The features carrying signal came
from *domain reasoning* rather than from the series' own history: drift as a fraction of
its fund's target, the rolling slope of the trend, realized volatility, and the fund
identity. On this problem Stage 09's approach outperforms Stage 10b's, and saying so is
more useful than presenting a 3% gain as a success.

**What Stage 10b does add is discipline.** A Pipeline that makes train-only fitting
structural, a walk-forward split that never trains on the future, and a selection made on
cross-validation. Stage 10a's numbers were produced without any of that, which is exactly
why Stage 11 should re-check them under it.

---

## 9. Assumptions, and which of them break

| Assumption | Status |
|---|---|
| Observations are independent | **False, badly.** A 21-day forward target makes consecutive rows share 20 of 21 days. Stage 10a measured Durbin-Watson at 0.107 to 0.151 and put the effective sample near 24. Every fold swing in section 5 is that shortage. |
| The relationship is stable over time | Untested and probably false. One trending year; Stage 08 found a near-deterministic ratchet rather than a stationary process. |
| Errors have constant variance | False. Residuals grow with the prediction, matching Stage 10a's 1.16 spread ratio. |
| Features are available when the prediction is made | **True, and tested** rather than assumed. |
| The drift's own past predicts its future | Weakly true, and almost entirely through `lag_1`. Everything beyond that is noise at this sample size. |

---

## 10. Handoff to Stage 11

Evaluation under uncertainty. Three things this stage sets up:

1. **Bootstrap the intervals Stage 10a could not honestly quote.** With ~24 effective
   observations, a block bootstrap that respects the overlap is the right tool.
2. **Compare scenarios.** The wrong-space result in section 3 is one scenario comparison
   already; the others are Gaussian versus fat-tailed errors, and the pp versus relative
   unit question Stage 09 left with the principal.
3. **Test subgroup heterogeneity.** The fold-to-fold spread is the first evidence that
   the three funds may be different enough to need separate treatment rather than one
   pooled model with fund dummies.
