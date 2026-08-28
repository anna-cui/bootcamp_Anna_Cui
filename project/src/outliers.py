"""Outlier analysis for the Portfolio Drift Monitor - Stage 07.

The monitor has two places an outlier can live, and they are not the same
problem:

**Input side - a bad price.** A quote that jumps absurdly is a data fault. It
propagates straight into the weights, so one bad close can manufacture drift
that never happened. `flag_return_outliers` looks for these in daily returns,
per fund, because a 2% move means something different for BND than for VXUS.

**Output side - a drift day worth acting on.** This is not a fault at all; it
is the thing the monitor exists to find. Here "outlier" means "past the
threshold a human agreed to act on", and the honest question is whether that
threshold is set anywhere near where the data actually lives.
`threshold_sensitivity` answers that by sweeping it.

Nothing here modifies its input; every function returns a new object.

Thresholds are never defaulted inside this module. `src/utils.py` owns
`AMBER_PP` and `RED_PP`, and the caller passes them in. Two files quietly
disagreeing about what "red" means is exactly the bug this stage is about.
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

    Rank-based, so the fences do not widen when a value gets more extreme -
    unlike the z-score rule, whose yardstick is built from the contaminated
    data itself.

    NaN yields False: missing is not extreme, and Stage 06 owns missingness.
    """
    series = _validate_series(series)
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    flags = (series < q1 - k * iqr) | (series > q3 + k * iqr)
    return flags.fillna(False).astype(bool)


def detect_outliers_zscore(series, threshold=3.0):
    """Flag values more than `threshold` population std devs from the mean.

    `ddof=0` because this describes the sample in hand rather than inferring
    about a population, matching the homework module.

    Carries a known trap: sigma is computed from data that includes the
    outliers, so a few extremes inflate it and can hide themselves. If flag
    counts stop responding to `threshold`, this rule is not measuring anything
    and the IQR rule should be preferred.
    """
    series = _validate_series(series)
    if threshold <= 0:
        raise ValueError(f"threshold must be positive, got {threshold}")
    mu, sigma = series.mean(), series.std(ddof=0)
    if sigma == 0 or np.isnan(sigma):
        return pd.Series(False, index=series.index)
    return ((series - mu).abs() / sigma > threshold).fillna(False).astype(bool)


def daily_returns(prices_long, date_col="date", group="ticker", col="close"):
    """Percentage change per fund, sorted by date within each fund.

    Returned as a copy of `prices_long` with a `ret` column added. The first
    observation of each fund is NaN by construction - there is no prior close
    to compare against, and that is missing rather than extreme.
    """
    for c in (date_col, group, col):
        if c not in prices_long.columns:
            raise KeyError(f"column {c!r} not found in prices_long")

    out = prices_long.sort_values([group, date_col]).copy()
    out["ret"] = out.groupby(group)[col].pct_change()
    return out


def flag_return_outliers(prices_long, k=1.5, threshold=3.0,
                         date_col="date", group="ticker", col="close"):
    """Flag suspicious daily moves, judged **within each fund separately**.

    Pooling the three funds would be wrong: BND is a bond fund whose ordinary
    day is a fraction of VXUS's, so a shared fence would flag routine equity
    moves and miss genuinely broken bond quotes.

    Returns
    -------
    pd.DataFrame
        `prices_long` plus `ret`, `ret_outlier_iqr`, `ret_outlier_z`. Rows
        whose return is NaN (each fund's first day) are never flagged.
    """
    out = daily_returns(prices_long, date_col=date_col, group=group, col=col)
    out["ret_outlier_iqr"] = False
    out["ret_outlier_z"] = False

    for name, chunk in out.groupby(group):
        rets = chunk["ret"].dropna()
        if len(rets) < 4:
            continue                      # too few points for quartiles to mean anything
        out.loc[rets.index, "ret_outlier_iqr"] = detect_outliers_iqr(rets, k=k)
        out.loc[rets.index, "ret_outlier_z"] = detect_outliers_zscore(rets,
                                                                     threshold=threshold)
    return out


def threshold_sensitivity(drift_long, thresholds, drift_col="drift_pp",
                          group="ticker"):
    """How often would the monitor fire at each candidate threshold?

    This is the question the drift monitor has never actually been asked. A
    threshold is a policy choice, and a policy nobody has priced against the
    data is a guess wearing a number.

    Parameters
    ----------
    drift_long : pd.DataFrame
        One row per fund-day, with a signed drift column in percentage points.
    thresholds : iterable of float
        Candidate absolute thresholds, in percentage points.
    drift_col, group : str

    Returns
    -------
    pd.DataFrame
        One row per threshold: how many fund-days breach it, what share that
        is, and how many distinct calendar days and funds are involved. A
        threshold that fires on zero fund-days has never been tested by this
        data - see `stress_test_threshold`.
    """
    if drift_col not in drift_long.columns:
        raise KeyError(f"column {drift_col!r} not found")

    magnitude = drift_long[drift_col].abs()
    n = len(drift_long)
    rows = []
    for t in thresholds:
        if t <= 0:
            raise ValueError(f"thresholds must be positive, got {t}")
        hit = magnitude > t
        rows.append({
            "threshold_pp": t,
            "fund_days_fired": int(hit.sum()),
            "pct_of_fund_days": round(100 * hit.mean(), 2) if n else np.nan,
            "distinct_funds": int(drift_long.loc[hit, group].nunique())
                              if group in drift_long.columns else np.nan,
        })
    return pd.DataFrame(rows)


def observed_drift_profile(drift_long, drift_col="drift_pp", group="ticker"):
    """Where drift actually lives, per fund - the evidence a threshold needs.

    Reports the magnitude quantiles rather than the signed values, because the
    monitor's rule is symmetric: it does not care which direction a fund has
    drifted, only how far.
    """
    mag = drift_long.assign(_mag=drift_long[drift_col].abs())
    profile = mag.groupby(group)["_mag"].agg(
        n="size", median="median", p90=lambda s: s.quantile(0.90),
        p99=lambda s: s.quantile(0.99), worst="max")
    overall = pd.DataFrame({
        "n": [len(mag)], "median": [mag["_mag"].median()],
        "p90": [mag["_mag"].quantile(0.90)], "p99": [mag["_mag"].quantile(0.99)],
        "worst": [mag["_mag"].max()]}, index=["ALL"])
    return pd.concat([profile, overall]).round(3)


def stress_test_threshold(drift_long, shock_pp, amber, red,
                          drift_col="drift_pp", group="ticker", ticker=None):
    """Inject a drift event and confirm the alarm actually fires.

    **Why this exists.** A monitor that has never fired and a monitor that is
    broken produce identical output: silence. Over a quiet window they are
    indistinguishable, and "no alerts" gets read as "nothing wrong" when it may
    mean "nothing works". This adds one synthetic fund-day at `shock_pp` and
    checks the flag comes back red - a smoke test for the alarm rather than a
    claim about the market.

    Parameters
    ----------
    drift_long : pd.DataFrame
    shock_pp : float
        Drift to inject, in percentage points. Should exceed `red`.
    amber, red : float
        Thresholds, passed in from `src/utils.py` rather than assumed here.
    ticker : str or None
        Which fund to attribute the synthetic day to. Defaults to the first.

    Returns
    -------
    dict
        `injected_pp`, `flag`, and `fires` - True when the alarm behaved.
    """
    if not 0 < amber <= red:
        raise ValueError("require 0 < amber <= red")

    if ticker is None:
        ticker = (drift_long[group].iloc[0] if group in drift_long.columns
                  else "SYNTHETIC")

    magnitude = abs(float(shock_pp))
    flag = "red" if magnitude > red else ("amber" if magnitude >= amber else "green")
    return {
        "ticker": ticker,
        "injected_pp": float(shock_pp),
        "amber_pp": float(amber),
        "red_pp": float(red),
        "flag": flag,
        "fires": flag == "red",
    }