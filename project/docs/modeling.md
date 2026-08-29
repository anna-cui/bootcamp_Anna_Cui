# Regression modeling - what was fitted, and what it may be used for

**Stage 10a.** Companion to `src/modeling.py` and `notebooks/modeling_regression.ipynb`.
That notebook is the run; this file holds the conclusions.

Figures are from the `20260828-1756` feature matrix: 627 model-ready fund-days, 2025-09-30
to 2026-07-30.

---

## 1. The track, and why the other two were rejected

The Stage 10a instructions allow regression, classification or time series, requiring at
least one across 10a and 10b.

**Regression, here.** Stage 09 built a continuous target for exactly this: absolute drift
21 trading days ahead.

**Classification was rejected on the data, not on preference.** Stage 08 found the flag is
green on all 753 fund-days. A classifier at the 3pp policy threshold would have zero
positive cases and could not be fitted at all. Dropping to 2pp gives 6 positives out of
753, which is 0.8%, and any classifier would reach 99.2% accuracy by always predicting
"no". That is a real finding about the monitor rather than a limitation of the method, and
it is the reason the operational question here is "how far", not "will it breach".

**Time series is Stage 10b**, on the same data with lag and rolling features inside a
pipeline.

---

## 2. Two decisions taken before fitting

**One dummy dropped.** Stage 09 built three one-hot fund columns and deferred `drop_first`
as "a Stage 10 decision". Three indicators sum to 1 on every row, duplicating the
intercept, so the design matrix is rank deficient: infinitely many coefficient vectors fit
equally well and standard errors are undefined. `sklearn.LinearRegression` hides this by
solving with a pseudo-inverse and returning one answer without complaint;
`modeling.fit_ols` raises instead. **BND is the reference fund**, so every `ticker_`
coefficient reads as "compared with BND".

**Chronological split, cut on dates.** Splitting on rows would put VTI in train and BND in
test on the same date, leaking that day's market conditions across the boundary. Cut at
**2026-06-01**: 501 training rows, 126 test rows.

---

## 3. Results, against the baselines that matter

| Predictor | test R² | test RMSE | test MAE |
|---|---|---|---|
| linear regression (11 params) | 0.692 | 0.233 | 0.192 |
| **persistence** (assume today's drift holds) | **0.502** | **0.296** | 0.237 |
| train mean (a flat line) | -0.533 | 0.520 | 0.404 |

The flat line scores negative because R² is defined against the *test* mean and the
training mean sits well below it. That is correct behaviour, not a bug.

**The persistence row is the honest benchmark.** It does nothing but assume today's drift
still holds in a month, and it already reaches 0.502. The model's contribution is the gap
from there: RMSE 0.233 against 0.296, an improvement of about 21%. Reporting R² 0.692
alone would present a model that has largely learned the trend as a model that has learned
something.

**RMSE in the monitor's units.** 0.233 percentage points, against a 3pp amber threshold and
a worst observed drift of 2.23pp. A typical error is about a tenth of the range the
monitor cares about.

---

## 4. A correction to Stages 08 and 09

Both stages recorded this expectation in their handoff notes:

> Split chronologically and expect the score to look worse than a random split would give,
> because a random split on a trended series leaks.

Measured:

| Split | train R² | test R² | test RMSE |
|---|---|---|---|
| chronological | 0.458 | **0.692** | **0.233** |
| random (shuffled) | 0.556 | 0.378 | 0.392 |

The chronological split scores **better**, and it also beats its own training score.

The first half of the expectation was right and the second was backwards. The reasoning
assumed "out of distribution" implies "harder". The final 20% of this window is where the
trend is most established and BND's drift is close to a straight line, so the target there
is narrower and more predictable: test range 0.305 to 1.769, train range 0.002 to 2.233. A
test score above a training score usually signals a bug; here it has a real cause.

This does **not** make a random split safe. Its optimism is real and would appear on data
where the regimes ran the other way. The narrower lesson: a chronological split does not
automatically produce a pessimistic number, and a test score that rises is something to
explain rather than to celebrate.

`docs/eda.md` and `docs/features.md` have been amended.

---

## 5. The four assumptions

| Assumption | Verdict | Evidence |
|---|---|---|
| Linearity | broadly holds | quadratic curvature of residuals on fitted **-0.032**, against a residual spread of 0.38 |
| **Independence** | **severely violated** | **Durbin-Watson 0.107 (BND), 0.114 (VXUS), 0.151 (VTI); lag-1 autocorrelation +0.92 to +0.95** |
| Homoscedasticity | violated statistically, mild practically | Breusch-Pagan LM 96.4, p = 3e-16; residual spread ratio only **1.16** |
| Normality | violated, least consequential | Shapiro-Wilk W 0.971, p = 2e-08; skew **+0.588**, excess kurtosis +0.244 |

### The one that matters

The target is absolute drift 21 trading days ahead, so **two consecutive rows share 20 of
the 21 days** in their target windows. They are very nearly the same observation counted
twice, and the residuals inherit that overlap.

The arithmetic:

```
501 training rows / 3 funds        = 167 rows per fund
167 rows per fund / 21-day horizon =   8 effective observations per fund
8 x 3 funds                        =  24 effective observations
parameters estimated               =  11
                                   ->  2.2 effective observations per parameter
```

**What this invalidates.** Positive autocorrelation does not bias coefficients. It biases
standard errors downward, badly, which inflates t statistics and shrinks p-values. Every
p-value the model reports assumes 501 independent observations against an effective 24.
The point predictions survive; the inference does not.

**Could it be fixed?** Not without changing the question. A shorter horizon reduces the
overlap, but Stage 09 showed a 1-day horizon is trivially predictable at r = 0.979.
Sampling every 21st row removes the overlap and leaves 8 rows per fund. Newey-West
standard errors would make the inference honest without fixing the information shortage.
The response taken here is to report predictions, refuse to quote a p-value, and prefer a
smaller model.

### On the other three

Homoscedasticity is the instructive one. Breusch-Pagan at p = 3e-16 is as decisive as a
test gets, and the effect is a residual standard deviation of 0.354 against 0.410, a ratio
of 1.16. With 501 rows a test detects a 16% difference easily, and detecting it is not the
same as it mattering. It is also directionally sensible: a fund that has drifted further
has more room to move. Reporting only the p-value overstates it; reporting only the ratio
hides that it is systematic.

Normality's right skew (+0.59) is expected for an absolute value bounded below at zero.

---

## 6. The variant sweep

The instructions ask to "automate the modeling process so you can auto-try the model with
some variations". `modeling.auto_try` runs each variant through one split and one metric
set, reporting train and test side by side, because overfitting is only visible when both
are in the same table.

| Variant | features | train R² | test R² | test RMSE | Durbin-Watson |
|---|---|---|---|---|---|
| `abs_drift` alone | 1 | 0.362 | 0.540 | 0.285 | 0.103 |
| **drift only** | **5** | **0.382** | **0.747** | **0.211** | 0.105 |
| no fund dummies | 8 | 0.385 | 0.728 | 0.219 | 0.110 |
| baseline | 10 | 0.458 | 0.692 | 0.233 | 0.128 |
| + `abs_drift²` | 11 | 0.492 | 0.602 | 0.265 | 0.147 |
| + squared + interaction | 12 | 0.502 | 0.494 | 0.299 | 0.159 |

Train R² climbs monotonically with every feature added, 0.362 to 0.502. Test R² peaks at
five features and falls away. Durbin-Watson drifts further from 2.0 as complexity rises.

**This is overfitting, measured rather than asserted**, and it is exactly what section 5
predicts: with about 24 effective observations, a 12-parameter model fits noise.

**The five-feature model wins on both metrics.** Stage 09 concluded that 627 rows over 11
features was "roughly 63 rows per feature, enough for a regularised linear model". That
arithmetic used the wrong numerator, and this table is the shortage seen from outside.

**The polynomial term did not help.** The mild curvature in the linearity plot was noise,
not a quadratic relationship, and a squared term absorbed it at a cost of 0.09 test R².
Worth recording as a negative result rather than replaced with a transformation that
happened to work.

Note that adding `x²` keeps this a linear regression. Linear means linear in the
coefficients, not in the predictors.

---

## 7. Coefficients

| Feature | coef | reading |
|---|---|---|
| `abs_drift` | +0.454 | A fund a percentage point further from target today is expected about 0.45pp further out in a month. Below 1, so mean reversion; well above 0, so drift persists. |
| `ticker_VXUS` | +0.538 | Against BND, VXUS runs further from target even after accounting for where it is today. Agrees with Stage 08. |
| `ticker_VTI` | +0.220 | Same, smaller. |
| `vol_21` | -0.021 | **Negative.** Higher recent volatility predicts *less* drift a month out, inverting the intuitive story. Consistent with volatility clustering followed by mean reversion, and the coefficient most likely to be an artifact of one calm year. |
| `ret_1` | -2.807 | Looks enormous, is not comparable. Daily returns have a standard deviation near 0.008, so a one-unit change is a 100% day. **Unscaled coefficients are not effect sizes.** Standardising belongs inside a pipeline fitted on train only, which is Stage 10b. |

**The p-value column cannot be quoted.** Several sit below 0.001 and the overall fit would
test as overwhelmingly significant. All of it assumes 501 independent observations against
an effective 24. As prediction the model works; as explanation it cannot support a claim
that any individual coefficient differs from zero.

---

## 8. Do I trust it, and for what purpose?

**For prediction, cautiously yes, within a narrow claim.** The five-feature variant
predicts absolute drift 21 trading days out at RMSE 0.211pp against persistence at
0.296pp, about 29% better. That is useful for **ranking** which of the three funds needs
attention next month.

**For explanation, no.** Twenty-four effective observations, 11 parameters, residuals
autocorrelated at +0.95. No coefficient supports a causal claim.

**For any statement about a specific fund crossing a specific threshold, no.** The model
predicts a magnitude, not an exceedance, and it has never seen an exceedance.

### For Dana

The report can carry a line saying which fund is drifting fastest and roughly where it
will be next month. It should not carry an error bar, and it should not promise a breach
date.

### Assumptions and risks

| Assumption | Risk if wrong |
|---|---|
| One year of daily data can support a model of a multi-year phenomenon | It cannot, for inference. This is the binding constraint on everything above. |
| The trend continues through the test period and beyond | The apparent skill is substantially the trend. A mean-reverting regime degrades it sharply. |
| Absolute drift in percentage points is the right target | Stage 09 found the relative unit predicts its own future at 0.906 against 0.689. Open with the principal. |
| Point predictions usable while inference is not | Rests on autocorrelation biasing standard errors rather than coefficients. Standard, and worth stating as an assumption rather than a fact. |

### What would change the answer

| Change | Effect |
|---|---|
| Several years of history | Attacks the binding constraint directly. Nothing else is close. |
| Newey-West or block-bootstrap standard errors | Makes inference honest without new data. Does not make it strong. |
| Ridge or lasso | Automates what the sweep found by hand. Stage 11. |
| Predicting the relative unit | 0.906 against 0.689. The principal's decision. |

---

## 9. Handoff to Stage 10b

Same data, time-aware pipeline, lag and rolling features, and the scaling this stage
deliberately avoided fitted **inside** the split. The `sklearn` Pipeline is a committed
repo requirement there, not just a notebook cell, which is what makes train-only fitting a
property of the project rather than of one execution.
