"""Reusable profiling helpers - Stage 08 (Exploratory Data Analysis).

`eda_summary` keeps the lecture's signature and return shape so notebooks that
already call it keep working. The other three functions answer questions the
lecture version does not:

- `categorical_profile` - `.describe()` silently covers numeric columns only, so
  a categorical column can be badly lopsided and never show up in a profile.
- `time_axis_report` - a date column with gaps, duplicates or rows out of order
  makes every lag and rolling feature in Stage 09 quietly wrong. Cheaper to
  check once here than to debug there.
- `flag_columns` - the stretch goal: turns the profile into a short list of
  columns that need a decision before Stage 09, rather than a wide table
  somebody has to read.

Nothing modifies its input.
"""

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, skew


def eda_summary(df, numeric_cols=None):
    """Profile a DataFrame: shape, dtypes, missingness, numeric distribution.

    Same signature and return shape as the lecture version, with the numeric
    profile extended by the two things a mean and a standard deviation cannot
    tell you:

    - **skew** - which direction the tail runs. Positive means a long right
      tail, which usually means a log transform is worth trying in Stage 09.
    - **kurtosis** - how heavy the tails are. `scipy` reports *excess* kurtosis,
      so 0 is normal-shaped. A value in the double digits is not a heavy tail;
      it is one or two points doing all the work, and they should be identified
      by row before anything else is decided.

    Parameters
    ----------
    df : pd.DataFrame
    numeric_cols : list[str] or None
        Restrict the numeric profile. None profiles every numeric column.

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
        out["numeric_profile"] = profile.round(3)
    else:
        out["numeric_profile"] = pd.DataFrame()

    return out


def categorical_profile(df, columns=None, top=10):
    """Value counts and shares for every non-numeric column.

    Counts alone hide how lopsided a split is - 900 vs 100 and 55 vs 45 both
    read as "two categories". The `pct` column is the one to look at, and
    `dominant_pct` in `flag_columns` turns it into a yes/no.

    Returns
    -------
    dict[str, pd.DataFrame]
        One frame per column: `count` and `pct`, most common first, truncated
        to `top` rows.
    """
    if columns is None:
        columns = df.select_dtypes(exclude=[np.number, "datetime64[ns]"]).columns

    out = {}
    for col in columns:
        counts = df[col].value_counts(dropna=False)
        out[col] = pd.DataFrame({
            "count": counts,
            "pct": (counts / len(df) * 100).round(2),
        }).head(top)
    return out


def time_axis_report(df, date_col="date", freq="D"):
    """Check the date axis is sound before anything is built along it.

    Stage 09 computes lags and rolling windows on this axis and Stage 10b
    splits on it. Both produce plausible-looking nonsense if the rows are out
    of order, a date repeats, or there is a hole in the middle: a 7-day rolling
    mean that spans a missing week is a 7-row mean, not a 7-day one, and
    nothing warns you.

    Returns
    -------
    dict
        `n_rows`, `start`, `end`, `is_sorted`, `n_duplicate_dates`,
        `n_missing_periods`, and `missing_periods` (up to 20 examples).
    """
    if date_col not in df.columns:
        raise KeyError(f"column {date_col!r} not found")

    dates = pd.to_datetime(df[date_col])
    full = pd.date_range(dates.min(), dates.max(), freq=freq)
    missing = full.difference(pd.DatetimeIndex(dates.unique()))

    return {
        "n_rows": len(dates),
        "start": dates.min(),
        "end": dates.max(),
        "is_sorted": bool(dates.is_monotonic_increasing),
        "n_duplicate_dates": int(dates.duplicated().sum()),
        "n_missing_periods": int(len(missing)),
        "missing_periods": list(missing[:20]),
    }


def flag_columns(df, missing_pct=20.0, dominant_pct=95.0, near_zero_var=0.01):
    """Shortlist the columns that need a decision before Stage 09.

    Three failure modes, each of which makes a column useless or dangerous as a
    feature:

    - **high missingness** - more imputed than observed values means the column
      mostly describes your filling rule, not the world.
    - **near-zero variance** - a column that barely moves cannot explain
      something that does. Measured as the coefficient of variation
      (std / |mean|), which is unit-free, so it compares a price column against
      a count column honestly.
    - **dominant category** - if one level covers ~all rows, the column is a
      constant wearing a disguise.

    Returns
    -------
    pd.DataFrame
        One row per flagged column with the reason and the number that
        triggered it. Empty means nothing needs attention at these thresholds -
        which is a result, not a non-answer.
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

    for col in df.select_dtypes(exclude=[np.number, "datetime64[ns]"]).columns:
        if df[col].isna().all():
            continue
        share = df[col].value_counts(normalize=True).iloc[0] * 100
        if share > dominant_pct:
            rows.append({"column": col, "issue": "dominant category",
                         "value": round(share, 2), "threshold": dominant_pct})

    return pd.DataFrame(rows, columns=["column", "issue", "value", "threshold"])