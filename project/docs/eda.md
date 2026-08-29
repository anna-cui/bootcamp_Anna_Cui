# Exploratory Data Analysis - what the drift data actually looks like

**Stage 08.** Companion to `notebooks/eda.ipynb`, which holds the plots and the code.
This file holds the conclusions, so they can be read without running anything.

Window: 2025-08-29 to 2026-08-28. 251 trading days, three funds, 753 fund-days.
Source: `data/processed/prices_clean_*.parquet`, produced by Stage 06 from a yfinance
pull.

---

## 1. The headline: the drift is a trend, not noise

Stage 07 established that neither threshold has ever fired. Over 753 fund-days the flag
was green 100% of the time, amber (3pp) sits 34% above the worst drift the year produced
and red (5pp) is 2.2 times it.

A flag count cannot say why. There are two explanations and they call for opposite
responses:

- the drift is stationary noise centred well below the line, in which case the threshold
  is set too high for the process and is worth arguing about;
- the drift is a trend that has not arrived yet, in which case the threshold is fine and
  the observation window is too short.

Fitting drift against time separates them.

| Fund | current drift (pp) | rate (pp/yr) | corr with time | r-squared | years to amber | years to red |
|---|---|---|---|---|---|---|
| BND | -1.705 | -1.688 | -0.929 | 0.863 | 0.77 | 1.95 |
| VXUS | +1.145 | +1.345 | +0.643 | 0.413 | 1.38 | 2.87 |
| VTI | +0.560 | +0.343 | +0.175 | 0.031 | 7.11 | 12.93 |

BND's drift is 86% explained by a straight line in time. This is the second explanation,
clearly. The mechanism is visible in the cumulative returns over the window: VTI +19.2%,
VXUS +22.6%, BND -2.0%. A portfolio bought at 60/30/10 and left alone drifts away from
its bond target at a rate set by that spread, in one direction, without oscillating back.

**So the alarm is not broken and the threshold is not obviously wrong. The monitor has
been shown one year of a phenomenon that operates on a multi-year timescale, and on
current rates the first amber lands inside the next reporting year.**

That is the sentence this stage adds to Stage 07's null result.

### The caveat, stated plainly

The projection is a linear extrapolation. It assumes the equity-over-bond spread
persists, which it will not do indefinitely; mean reversion pushes the amber dates out.
It is a way to size the problem, not a date to schedule a trade against. What survives
the caveat is the qualitative point: the drift has a direction, so silence now does not
imply silence later.

### What follows operationally

Dana, the client-service associate who receives the report, has seen a year of unbroken
green. The first amber should not be the first time anyone explains to her what an amber
means. Two changes are proposed rather than made, because both are the principal's call:

1. Put the drift rate and the projected crossing in the report as a standing line, so the
   trend is visible before the threshold is.
2. Reconsider the 2.0pp watch tier proposed in `docs/outliers.md`. Under the trend
   reading it stops being a way to make a quiet report look busier and becomes an early
   warning with a known lead time.

Neither is implemented. Changing what the monitor reports is a policy decision.

---

## 2. The date axis is business-daily, and that is a trap for Stage 09

| Check | Result |
|---|---|
| rows on the daily axis | 251, sorted, no duplicates |
| missing against a **calendar**-day grid | 114 |
| missing against a **business**-day grid | 10 |
| the ten | 2025-09-01, 2025-11-27, 2025-12-25, 2026-01-01, 2026-01-19, 2026-02-16, 2026-04-03, 2026-05-25, 2026-06-19, 2026-07-03 |
| gaps between consecutive rows | 1 day x195, 2 x3, 3 x45 (weekends), 4 x7 (holiday weekends) |

All ten absent business days are US market holidays. There is no data-quality problem
here. There is a units problem, and it is the kind that produces plausible numbers rather
than an error:

- a 7-row rolling mean spans 9 calendar days on average and 11 across a holiday weekend;
- `shift(1)` means the previous trading day, which is three calendar days back every
  Monday;
- reindexing onto `freq='D'` to "make the axis regular" inserts 114 empty rows and
  dilutes every rolling statistic, silently.

**Rule for Stage 09:** build lags and rolling windows on the existing business-day index,
label them in trading days, and do not reindex to a calendar frequency. The check is
enforced by an assertion in `project_pipeline.ipynb`, so a future change that breaks the
axis fails the run instead of producing quiet nonsense.

Note that a long frame reports 502 duplicate dates by design, one row per fund. The check
runs on a one-row-per-date frame.

---

## 3. Distributions and correlations

### Returns

| Fund | ann. vol (%) | skew | excess kurtosis |
|---|---|---|---|
| VTI | 13.07 | -0.22 | 1.12 |
| VXUS | 17.00 | -0.12 | 2.01 |
| BND | 3.91 | -0.28 | 0.07 |

Excess kurtosis is measured against a normal distribution, where the value is 0. VXUS at
2.0 has visibly heavier tails than normal, which is exactly the region a 3-sigma z-score
cutoff assumes it knows. BND at 0.07 is the one fund where a z-score would behave. This
is the evidence behind Stage 07 making the IQR rule primary and the z-score a
cross-check, and it was not available when that decision was made.

Returns are near-symmetric and contain negatives, so no log transform. The skew worth
acting on in this project is in the price level, not the return.

### Correlations: one real matrix, one structural one

Daily returns: VTI-VXUS **0.82**, VXUS-BND 0.46, VTI-BND 0.34.

0.82 means one fund explains 67% of the other's daily variance. Two features that close
to each other produce unstable coefficients in a linear model, so Stage 09 uses one of
them or replaces the pair with a spread. BND at 0.34 is carrying genuinely different
information, which is the argument for holding it.

The drift correlation matrix is negative on every pair, and it means nothing. Weights sum
to one, so deviations from a fixed target sum to zero (verified: the three drift columns
sum to within 2e-14 of zero on every row), so the columns are forced to move against each
other whatever the market does. Reading it as evidence of diversification would be a real
error, and a heatmap makes it an easy one, because both matrices look equally like
results.

### The categorical profile

`ticker` is 251 / 251 / 251 exactly, which is a passing test rather than a curiosity:
Stage 06's `drop_incomplete_days` guarantees it, so an imbalance would mean the cleaner
had been skipped.

`flag` is 100% green. `flag_columns` reports it as a dominant category at 100%, which
means it is a constant wearing a disguise. It stays a reporting column and never becomes
a model feature.

---

## 4. What Stage 08 changed, and what it deliberately did not

**No data was altered, dropped or imputed.** That is the correct outcome for an EDA stage
and is stated rather than implied.

**Nothing about the thresholds was changed.** Stage 07 decided to leave amber and red at
3pp and 5pp on the grounds that they encode what is worth acting on. Stage 08 strengthens
that decision rather than reopening it: the reason nothing fires is a short window, not a
badly placed line.

**The pp-versus-relative unit problem is still open.** BND's worst drift of 1.769pp is
17.7% of its 10% target; VTI's 1.553pp is 2.6% of its 60% target. The single pp rule is
least sensitive where a given move matters most. Named in `docs/outliers.md`, unchanged
here, still a decision for the principal.

---

## 5. The handoff to Stage 09

Build, in priority order:

1. **First difference of drift**, and rolling 21-day and 63-day drift slope. The level is
   dominated by a trend, so a lagged level is nearly as good a predictor of tomorrow as
   today's value and adds nothing.
2. **Equity-minus-bond return spread.** This is the mechanism actually producing the
   drift, so it is the feature with a causal story rather than a correlation.
3. **21-day realized volatility per fund.** The rolling vol plot shows real clustering
   (VTI 6% to 21%, VXUS 8% to 29%), so this is signal rather than decoration.

Do not build:

- **calendar features** (month, day of week). There is no seasonality in this series; the
  weekday means of daily drift change are all within 0.03pp of zero.
- **both VTI and VXUS** as separate inputs to a linear model, at 0.82.

## 6. The handoff to Stage 10b

Split chronologically, and expect the score to look worse than the model deserves.
Training on the first 80% trains on the low-drift half and tests on the high-drift half,
so the test set is out of distribution by construction. A random split would score much
better and would be leakage, because a trend makes neighbouring days nearly identical.

The split stays chronological. The write-up reports the drift range of each side next to
the score, so the number is read with the reason it is what it is.
