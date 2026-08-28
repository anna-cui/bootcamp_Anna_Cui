"""Outlier detection and handling - Stage 07 (Outliers, Risk, Assumptions).

Every function here returns something NEW; nothing is modified in place, so the
original series is always available for the before/after comparisons that this
stage is actually about.

Five improvements over the starter implementations, each of which the starter
notebook explicitly invites:

1. **Empty input is rejected.** The starter versions silently return an empty
   mask, which downstream code happily treats as "no outliers found" - a wrong
   answer that looks like a right one.
2. **NaN behaviour is stated and enforced.** Missing is not the same as extreme.
   NaN never counts as an outlier here; handling missing data was Stage 06's job
   and doing it again silently would hide which step made the decision.
3. **`ddof=0` is explained rather than just used.** See the note in
   `detect_outliers_zscore`.
4. **Parameters are validated.** A negative `k` or `threshold` silently inverts
   the test and flags every ordinary point instead of the extreme ones.
5. **`winsorize_series` checks that `lower` sits below `upper`.** Reversed
   quantiles make `Series.clip` return a constant series with no error at all.
"""

import numpy as np
import pandas as pd


def _validate_series(series, name="series"):
    """Reject inputs no outlier rule can meaningfully be applied to."""
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    if len(series) == 0:
        raise ValueError(f"{name} is empty - there is nothing to test")
    if series.notna().sum() == 0:
        raise ValueError(f"{name} is entirely missing - no outliers are definable")
    if not pd.api.types.is_numeric_dtype(series):
        raise TypeError(f"{name} must be numeric, got dtype {series.dtype}")
    return series


def detect_outliers_iqr(series, k=1.5):
    """Flag values outside [Q1 - k*IQR, Q3 + k*IQR].

    This is a *rank-based* rule: quartiles do not move when a value gets more
    extreme, only when it crosses a quartile. That makes IQR robust to the very
    points it is trying to find - unlike the z-score rule below, whose own
    yardstick is stretched by the outliers.

    Assumptions
    -----------
    - The middle half of the data is representative of "normal".
    - The distribution is unimodal enough that quartiles summarise it. On a
      bimodal series this rule flags the gap between modes, not the tails.
    - k=1.5 is Tukey's convention, not a law. On roughly normal data it flags
      about 0.7% of points; on heavy-tailed financial returns it flags many
      more, because fat tails are the normal state of affairs, not an error.

    Parameters
    ----------
    series : pd.Series
        Numeric values to test.
    k : float, default 1.5
        Fence width in IQR units. Larger k is more permissive.

    Returns
    -------
    pd.Series of bool
        True where the value is outside the fences. **NaN yields False** - a
        missing value is not an extreme value, and conflating the two hides
        which cleaning step made the decision.
    """
    series = _validate_series(series)
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")

    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - k * iqr
    upper = q3 + k * iqr

    flags = (series < lower) | (series > upper)
    return flags.fillna(False).astype(bool)


def detect_outliers_zscore(series, threshold=3.0):
    """Flag values whose distance from the mean exceeds `threshold` std devs.

    **Why ddof=0.** The population standard deviation is used because this is a
    description of the sample in hand, not an inference about a wider
    population: "how unusual is this point among the points I have". With
    ddof=1 the divisor is n-1 and every z shrinks slightly, which changes counts
    near the boundary. Either is defensible; what is not defensible is leaving
    it unstated, since the two disagree on borderline points.

    **The trap this rule carries.** The mean and the standard deviation are both
    computed from data that includes the outliers. A few large shocks inflate
    sigma, which widens the threshold, which can stop those same shocks from
    being flagged - classic *masking*. The symptom is a rule that stops
    responding to its own parameter: if flag counts are identical at
    threshold=2.0 and threshold=3.5, sigma is being driven by the extremes and
    this rule is not really measuring anything. Prefer the IQR rule, or a
    median/MAD variant, when that happens.

    Assumptions
    -----------
    - Roughly normal, unimodal data - the 3-sigma intuition comes from the
      normal distribution and does not transfer to heavy tails.
    - No strong trend or regime shift. A series that steps up halfway through
      has a mean that describes neither half.

    Parameters
    ----------
    series : pd.Series
        Numeric values to test.
    threshold : float, default 3.0
        Absolute z-score above which a point is flagged.

    Returns
    -------
    pd.Series of bool
        True where |z| > threshold. **NaN yields False**, as above.
    """
    series = _validate_series(series)
    if threshold <= 0:
        raise ValueError(f"threshold must be positive, got {threshold}")

    mu = series.mean()
    sigma = series.std(ddof=0)
    if sigma == 0 or np.isnan(sigma):
        # A constant series has no spread; nothing can be unusual within it.
        return pd.Series(False, index=series.index)

    z = (series - mu) / sigma
    return (z.abs() > threshold).fillna(False).astype(bool)


def winsorize_series(series, lower=0.05, upper=0.95):
    """Clip values to the given quantiles instead of deleting them.

    Winsorizing keeps every row - it caps extremes rather than removing them, so
    the sample size and any date index stay intact. That is its advantage over
    filtering, and it is why it suits time series where deleting a row leaves a
    hole.

    **The trap it carries.** Winsorizing one column of a relationship while
    leaving the other alone compresses one axis and not the other, which biases
    any fitted slope. If you winsorize a predictor for a regression, winsorize
    the response too - or do not winsorize at all. The homework notebook
    demonstrates this: clipping only x drives the fitted slope from 0.61 to
    1.47 against a true value of 0.6.

    Assumptions
    -----------
    - The extreme values are contaminated in *magnitude* but still belong in the
      sample - worth keeping at a capped value rather than discarding.
    - The chosen quantiles bracket the honest data. Clipping at 5/95 always
      moves about 10% of the points, whether or not anything is wrong with them.

    Parameters
    ----------
    series : pd.Series
        Numeric values to clip.
    lower, upper : float
        Quantiles in [0, 1] with lower < upper.

    Returns
    -------
    pd.Series
        A copy with values clipped to the quantile bounds. NaN stays NaN.
    """
    series = _validate_series(series)
    if not 0 <= lower < upper <= 1:
        raise ValueError(
            f"need 0 <= lower < upper <= 1, got lower={lower}, upper={upper}"
        )

    lo = series.quantile(lower)
    hi = series.quantile(upper)
    return series.clip(lower=lo, upper=hi)


def outlier_report(series, k=1.5, threshold=3.0):
    """Summarise what each rule flags, so the two can be compared at a glance.

    Returns
    -------
    pd.DataFrame
        One row per method, with the bounds it used, how many points it flagged
        and what share of the series that is. Built for the sensitivity tables
        this stage asks for - and reused by the project pipeline.
    """
    series = _validate_series(series)

    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    iqr_flags = detect_outliers_iqr(series, k=k)

    mu, sigma = series.mean(), series.std(ddof=0)
    z_flags = detect_outliers_zscore(series, threshold=threshold)

    return pd.DataFrame(
        {
            "lower_bound": [q1 - k * iqr, mu - threshold * sigma],
            "upper_bound": [q3 + k * iqr, mu + threshold * sigma],
            "n_flagged": [int(iqr_flags.sum()), int(z_flags.sum())],
            "pct_flagged": [
                round(100 * iqr_flags.mean(), 2),
                round(100 * z_flags.mean(), 2),
            ],
        },
        index=[f"iqr (k={k})", f"zscore (threshold={threshold})"],
    )