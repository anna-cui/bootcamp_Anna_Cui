"""Exploratory profiling for the Portfolio Drift Monitor - Stage 08.

The homework version of this module profiled a generic DataFrame. This one is
adapted to the two frames the pipeline actually passes around:

- **a long price frame** - one row per (date, ticker) with a `close`, which is
  what `src/cleaning.clean_prices` returns.
- **a long drift frame** - one row per (date, ticker) with a `drift_pp`, which
  is what Stage 05 builds and Stage 07 analyses.

Four of the functions are general and carried over unchanged in behaviour
(`eda_summary`, `categorical_profile`, `time_axis_report`, `flag_columns`).
Two are new and specific to this project:

- `return_profile` - per-fund return statistics. A pooled profile of three
  funds mixes a bond fund with two equity funds and reports a standard
  deviation that describes neither.
- `drift_trend` - fits drift against time. Stage 07 established that the amber
  and red thresholds have never fired. This answers the follow-up question,
  which is whether that is because the drift is stationary noise sitting well
  below the line, or a trend that simply has not arrived yet. They call for
  opposite responses.

Two conventions carried over from `src/outliers.py`:

- Nothing modifies its input. Every function returns a new object.
- Thresholds are never defaulted here. `src/utils.py` owns `AMBER_PP` and
  `RED_PP`, and the caller passes them in. Two modules quietly disagreeing
  about what "red" means is exactly the bug Stage 07 was about.
"""

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, skew

TRADING_DAYS_PER_YEAR = 251


def eda_summary(df, numeric_cols=None):
    """Profile a DataFrame: shape, dtypes, missingness, numeric distribution.

    Same signature and return shape as the lecture version, with the numeric
    profile extended by the two things a mean and a standard deviation cannot
    tell you:

    - **skew** - which direction the tail runs.
    - **kurtosis** - how heavy the tails are. `scipy` reports *excess*
      kurtosis, so 0 is normal-shaped. A double-digit value is not a heavy
      tail, it is one or two points doing all the work.

    Returns
    -------
    dict with keys `shape`, `dtypes`, `missing`, `missing_pct`,
    `numeric_profile`.
    """
    if numeric_cols is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    out = {
        "shape": df.shape,
        "dtypes": df.dtypes.to_dict(),
        "missing": df.isna().sum().to_dict(),
        "missing_pct": (df.isna().mean() * 100).round(2).to_dict(),
    }

    if numeric_cols:
        profile = df[numeric_cols].describe().T
        profile["skew"] = [skew(df[c].dropna()) for c in profile.index]
        profile["kurtosis"] = [kurtosis(df[c].dropna()) for c in profile.index]
        out["numeric_profile"] = profile.round(4)
    else:
        out["numeric_profile"] = pd.DataFrame()

    return out


def categorical_profile(df, columns=None, top=10):
    """Value counts and shares for every non-numeric column.

    Counts alone hide how lopsided a split is: 900 vs 100 and 55 vs 45 both
    read as "two categories". The `pct` column is the one to look at.

    Returns
    -------
    dict[str, pd.DataFrame], one frame per column with `count` and `pct`.
    """
    if columns is None:
        columns = df.select_dtypes(exclude=["number", "datetime", "datetimetz"]).columns

    out = {}
    for col in columns:
        counts = df[col].value_counts(dropna=False)
        out[col] = pd.DataFrame({
            "count": counts,
            "pct": (counts / len(df) * 100).round(2),
        }).head(top)
    return out


def return_profile(prices_long, date_col="date", group="ticker", col="close",
                   periods_per_year=252):
    """Per-fund daily-return statistics from a long price frame.

    Reported per fund rather than pooled, because these three funds do not
    share a scale: BND's daily standard deviation is roughly a third of VTI's,
    and a pooled number describes neither.

    `excess_kurtosis` is the column that matters for Stage 07's rules. It is
    measured against a normal distribution, where the value is 0. A fund well
    above 0 has heavier tails than normal, which is precisely where a z-score
    cutoff is calibrated, so a z-score rule on that fund will mis-count.

    Returns
    -------
    pd.DataFrame indexed by fund.
    """
    df = prices_long.sort_values([group, date_col])
    rows = []
    for fund, part in df.groupby(group, sort=True):
        ret = part[col].pct_change(fill_method=None).dropna()
        if len(ret) < 2:
            continue
        rows.append({
            group: fund,
            "n": len(ret),
            "mean_pct": ret.mean() * 100,
            "std_pct": ret.std() * 100,
            "ann_vol_pct": ret.std() * np.sqrt(periods_per_year) * 100,
            "min_pct": ret.min() * 100,
            "max_pct": ret.max() * 100,
            "skew": skew(ret),
            "excess_kurtosis": kurtosis(ret),
        })
    return pd.DataFrame(rows).set_index(group).round(4)


def time_axis_report(df, date_col="date", freq="B"):
    """Check the date axis is sound before anything is built along it.

    Stage 09 computes lags and rolling windows on this axis and Stage 10b
    splits on it. Both produce plausible-looking nonsense if the rows are out
    of order, a date repeats, or there is a hole: a 7-day rolling mean that
    spans a missing week is a 7-row mean, not a 7-day one, and nothing warns
    you.

    `freq` defaults to `'B'`, not `'D'`, because this project's axis is
    business-daily. Against a calendar grid every weekend reads as a gap, which
    buries the ten genuinely absent days in 114 expected ones.

    A long frame reports duplicate dates by design, one row per fund. Pass a
    one-row-per-date frame to check for real duplicates.

    Returns
    -------
    dict with `n_rows`, `n_unique_dates`, `start`, `end`, `is_sorted`,
    `n_duplicate_dates`, `n_missing_periods`, `missing_periods`, `freq`.
    """
    if date_col not in df.columns:
        raise KeyError(f"column {date_col!r} not found")

    dates = pd.to_datetime(df[date_col])
    if len(dates) == 0:
        raise ValueError("no rows to check")

    unique = pd.DatetimeIndex(sorted(dates.unique()))
    full = pd.date_range(unique.min(), unique.max(), freq=freq)
    missing = full.difference(unique)

    return {
        "n_rows": len(dates),
        "n_unique_dates": len(unique),
        "start": unique.min(),
        "end": unique.max(),
        "is_sorted": bool(dates.is_monotonic_increasing),
        "n_duplicate_dates": int(dates.duplicated().sum()),
        "n_missing_periods": int(len(missing)),
        "missing_periods": list(missing[:25]),
        "freq": freq,
    }


def drift_trend(drift_long, amber, red, date_col="date", group="ticker",
                drift_col="drift_pp", periods_per_year=TRADING_DAYS_PER_YEAR):
    """Fit each fund's drift against time and project when it reaches the lines.

    Stage 07 established that neither threshold has ever fired over the
    observed year. That leaves two very different explanations, and a flag
    count cannot tell them apart:

    - the drift is stationary noise centred well below the line, in which case
      the threshold is set too high for the process and should be argued about;
    - the drift is a trend that has not arrived yet, in which case the
      threshold is fine and the observation window is too short.

    The correlation with time separates them. Near zero means noise. Near +/-1
    means a near-deterministic ratchet.

    `years_to_amber` and `years_to_red` are a linear extrapolation from the
    fund's *current* drift, and they are a way to size the problem, not a
    forecast. They assume the return spread producing the drift persists, which
    it will not do indefinitely. Reported as `inf` where the fit is flat or
    pointing away from the line.

    Parameters
    ----------
    drift_long : pd.DataFrame
        Long frame with `date_col`, `group` and `drift_col`.
    amber, red : float
        Thresholds in percentage points, passed in from `src.utils`.

    Returns
    -------
    pd.DataFrame indexed by fund, with the fitted rate, fit quality, current
    drift, and the projected crossings.
    """
    if not 0 < amber <= red:
        raise ValueError("require 0 < amber <= red")

    df = drift_long.sort_values([group, date_col])
    rows = []
    for fund, part in df.groupby(group, sort=True):
        series = part[drift_col].to_numpy(dtype=float)
        if len(series) < 3:
            continue
        x = np.arange(len(series))
        slope, _ = np.polyfit(x, series, 1)
        rate = slope * periods_per_year
        r = float(np.corrcoef(x, series)[0, 1])
        current = float(series[-1])

        def years_to(line):
            # Distance to whichever side of the band the fit is heading toward.
            if rate == 0:
                return np.inf
            target = line if rate > 0 else -line
            remaining = target - current
            if np.sign(remaining) != np.sign(rate):
                return 0.0          # already past it
            return abs(remaining / rate)

        rows.append({
            group: fund,
            "n_obs": len(series),
            "current_pp": current,
            "rate_pp_per_year": rate,
            "corr_with_time": r,
            "r_squared": r ** 2,
            "years_to_amber": years_to(amber),
            "years_to_red": years_to(red),
        })

    return pd.DataFrame(rows).set_index(group).round(3)


def flag_columns(df, missing_pct=20.0, dominant_pct=95.0, near_zero_var=0.01):
    """Shortlist the columns that need a decision before Stage 09.

    Three failure modes, each of which makes a column useless or dangerous as
    a feature:

    - **high missingness** - more imputed than observed values means the column
      mostly describes your filling rule, not the world.
    - **near-zero variance** - a column that barely moves cannot explain
      something that does. Measured as the coefficient of variation
      (std / |mean|), which is unit-free, so it compares a price column against
      a count column honestly.
    - **dominant category** - if one level covers nearly all rows, the column
      is a constant wearing a disguise. In this project that is not a
      hypothetical: `flag` is 100% green.

    Returns
    -------
    pd.DataFrame, one row per flagged column. Empty means nothing needs
    attention at these thresholds, which is a result, not a non-answer.
    """
    rows = []

    for col in df.columns:
        pct_missing = df[col].isna().mean() * 100
        if pct_missing > missing_pct:
            rows.append({"column": col, "issue": "high missingness",
                         "value": round(pct_missing, 2), "threshold": missing_pct})

    for col in df.select_dtypes(include=[np.number]).columns:
        s = df[col].dropna()
        if len(s) < 2 or s.mean() == 0:
            continue
        cv = abs(s.std() / s.mean())
        if cv < near_zero_var:
            rows.append({"column": col, "issue": "near-zero variance",
                         "value": round(cv, 5), "threshold": near_zero_var})

    for col in df.select_dtypes(exclude=["number", "datetime", "datetimetz"]).columns:
        if df[col].isna().all():
            continue
        share = df[col].value_counts(normalize=True).iloc[0] * 100
        if share > dominant_pct:
            rows.append({"column": col, "issue": "dominant category",
                         "value": round(share, 2), "threshold": dominant_pct})

    return pd.DataFrame(rows, columns=["column", "issue", "value", "threshold"])
