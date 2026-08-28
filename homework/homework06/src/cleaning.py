"""Reusable cleaning helpers - Stage 06 (Data Preprocessing).

Design rules that apply to every function in this module:

1. Nothing is modified in place. Each function copies its input and returns a
   NEW DataFrame, so the original stays available for before/after comparison.
2. Numeric-only operations refuse non-numeric columns loudly (TypeError)
   instead of silently doing nothing.
3. Every choice that could change a result - which columns, which threshold,
   which scaler - is an explicit argument with a documented default.
"""

import numpy as np
import pandas as pd


def _resolve_numeric(df, columns=None):
    """Return the list of numeric columns to operate on.

    columns=None  -> every numeric column in the frame.
    columns=list  -> exactly those, after checking they exist AND are numeric.
    """
    if columns is None:
        return list(df.select_dtypes(include="number").columns)

    columns = list(columns)
    absent = [c for c in columns if c not in df.columns]
    if absent:
        raise KeyError(f"columns not found in DataFrame: {absent}")
    non_numeric = [c for c in columns if not pd.api.types.is_numeric_dtype(df[c])]
    if non_numeric:
        raise TypeError(
            f"these columns are not numeric, so this operation is undefined "
            f"for them: {non_numeric}"
        )
    return columns


def fill_missing_median(df, columns=None):
    """Fill missing values in numeric columns with that column's median.

    Why median and not mean: the median is not dragged around by a single
    extreme value, so on a small or skewed sample it is the safer default.

    Assumption this encodes: the values are missing at random, so a
    middle-of-the-distribution guess is better than throwing the row away.
    If a value is missing BECAUSE it is extreme (income missing only for the
    very rich), median filling actively hides that pattern - use drop_missing
    or an explicit missingness flag instead.

    Parameters
    ----------
    df : pd.DataFrame
    columns : list[str] or None
        Numeric columns to fill. None means every numeric column.

    Returns
    -------
    pd.DataFrame
        A copy with the chosen columns filled. Non-numeric columns are
        untouched - a median of city names is not a thing.
    """
    out = df.copy()
    for col in _resolve_numeric(out, columns):
        out[col] = out[col].fillna(out[col].median())
    return out


def drop_missing(df, columns=None, threshold=None, axis="rows"):
    """Drop rows or columns based on how much data they are missing.

    Three mutually exclusive modes, checked in this order:

    1. columns=[...]  -> drop any ROW that is missing a value in those columns.
       Use when a field is required (you cannot model a row with no target).
    2. threshold=f    -> keep rows (or columns, see `axis`) that have at least
       fraction `f` of their values present. threshold=0.5 keeps anything at
       least half populated.
    3. neither        -> drop every row containing any missing value at all.
       The blunt option; listed last because it is the most destructive.

    Parameters
    ----------
    df : pd.DataFrame
    columns : list[str] or None
        Required fields. Rows missing any of them are dropped.
    threshold : float or None
        Fraction in (0, 1]. Minimum share of values that must be present.
    axis : {'rows', 'columns'}
        Only used with `threshold`. 'rows' judges each row against the number
        of columns; 'columns' judges each column against the number of rows.

    Returns
    -------
    pd.DataFrame
        A copy with the offending rows or columns removed.
    """
    out = df.copy()

    if columns is not None:
        absent = [c for c in columns if c not in out.columns]
        if absent:
            raise KeyError(f"columns not found in DataFrame: {absent}")
        return out.dropna(subset=list(columns))

    if threshold is not None:
        if not 0 < threshold <= 1:
            raise ValueError("threshold must be a fraction in (0, 1]")
        if axis == "rows":
            return out.dropna(axis=0, thresh=int(np.ceil(threshold * out.shape[1])))
        if axis == "columns":
            return out.dropna(axis=1, thresh=int(np.ceil(threshold * out.shape[0])))
        raise ValueError("axis must be 'rows' or 'columns'")

    return out.dropna()


def normalize_data(df, columns=None, method="minmax"):
    """Put numeric columns on a common scale.

    method='minmax'   -> (x - min) / (max - min), giving a 0-1 range.
                         Use when you want bounded values and the min/max are
                         meaningful. Sensitive to outliers: one extreme value
                         squashes everything else toward 0.
    method='standard' -> (x - mean) / std, giving mean 0 and std 1.
                         Use when the spread matters more than the bounds.

    Both match scikit-learn's MinMaxScaler / StandardScaler (std uses ddof=0),
    but are written in plain pandas so this module has no sklearn dependency.

    A constant column has no spread to divide by; rather than produce inf or
    NaN, it is mapped to all zeros and that is what sklearn does too.

    IMPORTANT: scaling is fit on the data you pass in. If you later split into
    train/test, fit on train only - otherwise test statistics leak into the
    scaling and your evaluation is optimistic.

    Parameters
    ----------
    df : pd.DataFrame
    columns : list[str] or None
        Numeric columns to scale. None means every numeric column.
    method : {'minmax', 'standard'}

    Returns
    -------
    pd.DataFrame
        A copy with the chosen columns rescaled in place. Missing values stay
        missing - scale after you have decided how to handle them.
    """
    out = df.copy()
    cols = _resolve_numeric(out, columns)

    for col in cols:
        s = out[col].astype(float)
        if method == "minmax":
            lo, hi = s.min(), s.max()
            spread = hi - lo
            out[col] = 0.0 if spread == 0 else (s - lo) / spread
        elif method == "standard":
            mu, sd = s.mean(), s.std(ddof=0)
            out[col] = 0.0 if sd == 0 else (s - mu) / sd
        else:
            raise ValueError("method must be 'minmax' or 'standard'")
    return out
