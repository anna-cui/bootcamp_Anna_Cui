"""Reusable helpers for the Portfolio Drift Monitor.

Every function here is pure: it takes data in, returns new data out, and never
writes to disk or mutates its argument. That makes them safe to call from any
notebook and testable without fixtures.
"""

import numpy as np
import pandas as pd

TARGET_WEIGHTS = {"VTI": 0.60, "VXUS": 0.30, "BND": 0.10}
AMBER_PP = 3.0
RED_PP = 5.0


def clean_columns(df):
    """Return `df` with column names lowercased, stripped, snake_cased."""
    out = df.copy()
    out.columns = (out.columns.astype(str)
                   .str.strip().str.lower().str.replace(r"[^\w]+", "_", regex=True)
                   .str.strip("_"))
    return out


def parse_dates(df, col="date"):
    """Coerce `col` to datetime, raising if any value fails to parse.

    Assumption: a date that will not parse is a data-quality problem, not
    something to silently turn into NaT and carry downstream.
    """
    out = df.copy()
    parsed = pd.to_datetime(out[col], errors="coerce")
    bad = parsed.isna() & out[col].notna()
    if bad.any():
        raise ValueError(f"{int(bad.sum())} unparseable date(s), e.g. {out.loc[bad, col].iloc[0]!r}")
    out[col] = parsed
    return out


def to_weights(values):
    """Convert holdings values to portfolio weights summing to 1."""
    arr = np.asarray(values, dtype=float)
    total = arr.sum()
    if total <= 0:
        raise ValueError("total portfolio value must be positive")
    return arr / total


def drift_pp(current, target):
    """Drift in PERCENTAGE POINTS: current weight minus target weight.

    Percentage points, not percent. A move from 60% to 68% is 8 pp, not 13%.
    The distinction is the whole reporting metric, so it is named in the return.
    """
    return (np.asarray(current, float) - np.asarray(target, float)) * 100.0


def flag_drift(drift, amber=AMBER_PP, red=RED_PP):
    """Map drift in pp to green / amber / red using the principal's policy.

    green  |drift| < amber
    amber  amber <= |drift| <= red   (noted, no action)
    red    |drift| > red             (escalated same day)
    """
    if not 0 < amber <= red:
        raise ValueError("require 0 < amber <= red")
    mag = np.abs(np.asarray(drift, float))
    return np.where(mag > red, "red", np.where(mag >= amber, "amber", "green"))
