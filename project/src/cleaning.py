"""Cleaning helpers for the Portfolio Drift Monitor - Stage 06.

These are deliberately NOT the same rules as `homework/homework06/src/cleaning.py`.
That module cleans a cross-section: seven unrelated people, where one person's
income tells you nothing about the next person's, so the median of the column is
the best stand-in for a blank.

This module cleans a time series, where the opposite is true. Yesterday's close
is by far the best estimate of a close that did not arrive, and the median of a
year of prices is not a plausible price for any particular day - it would drag a
December observation back toward the middle of the year and quietly invent a move
that never happened. Reusing the homework's median rule here would be the wrong
answer arrived at by copying, so the difference is spelled out rather than left
for a reader to notice.

Design rules, same as everywhere else in this project:

1. Nothing is modified in place. Every function copies and returns a new frame.
2. Anything that changes a number is reported, not done silently. `clean_prices`
   returns a log of what it touched alongside the cleaned frame.
3. Every judgement call - the fill limit, which duplicate wins - is an explicit
   argument with a documented default.
"""

import numpy as np
import pandas as pd


def missingness_report(df):
    """Per-column dtype, missing count and share. The input to every decision below."""
    return pd.DataFrame({
        "dtype": df.dtypes.astype(str),
        "missing": df.isna().sum(),
        "missing_pct": (df.isna().mean() * 100).round(2),
    })


def coerce_types(df, date_col="date", numeric_cols=("close",)):
    """Force `date_col` to datetime and `numeric_cols` to numeric.

    A CSV round trip is the reason this exists. Stage 05 established that CSV is
    text and forgets dtypes: the raw file on disk stores `2025-08-29` and
    `318.20001220703125` as strings, and pandas' guess at re-read time is a guess.
    Sorting a date column that is really text sorts lexicographically, which is
    right for ISO dates by luck and wrong for every other format.

    Coercion errors become NaT/NaN here rather than raising, because a single
    unparseable row should be visible in the missingness report and handled by the
    dropping rules below - not stop the pipeline at import time. `parse_dates` in
    src/utils.py takes the strict line for the cases that should be fatal.

    Returns
    -------
    (pd.DataFrame, dict)
        The coerced copy, and a count of values that failed to parse per column.
    """
    out = df.copy()
    failures = {}

    if date_col in out.columns:
        before = out[date_col].notna().sum()
        out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
        failures[date_col] = int(before - out[date_col].notna().sum())

    for col in numeric_cols:
        if col in out.columns:
            before = out[col].notna().sum()
            out[col] = pd.to_numeric(out[col], errors="coerce")
            failures[col] = int(before - out[col].notna().sum())

    return out, failures


def drop_duplicate_quotes(df, keys=("date", "ticker"), keep="last"):
    """Remove repeated (date, ticker) observations.

    Two rows for the same fund on the same day is not extra information, it is a
    contradiction, and a pivot on a duplicated key raises rather than picking one.

    `keep='last'` because when a vendor sends the same day twice the later row is
    the correction. That is an assumption about the vendor, not a fact: with a
    source that appends corrections at the top it would be exactly backwards.

    Returns
    -------
    (pd.DataFrame, int)
        The de-duplicated copy and the number of rows removed.
    """
    out = df.copy()
    keys = list(keys)
    removed = int(out.duplicated(subset=keys, keep=keep).sum())
    return out.drop_duplicates(subset=keys, keep=keep), removed


def fill_missing_closes(df, group="ticker", col="close", limit=3):
    """Forward-fill missing closes within each fund, up to `limit` days.

    Why forward fill: an absent close means the observation did not arrive, not
    that the asset had no value. The last traded price is the standard stand-in -
    it is how a stale holding is marked in a NAV - and it is the only fill that
    cannot invent a move the market did not make.

    Why a limit: forward filling across a long hole draws a flat line through it.
    A flat line is not neutral. It reads as zero volatility and zero drift for the
    whole gap, which is a stronger claim than the data supports and one that flows
    straight into the drift report. Three days covers a long weekend plus a holiday;
    anything longer is a gap that should be visible, so it stays missing and gets
    dropped by `drop_incomplete_days`.

    Sorting by date first is not optional. Forward fill walks the frame in row
    order, so on an unsorted frame it propagates prices backwards in time.

    Returns
    -------
    (pd.DataFrame, int)
        The filled copy and the number of cells actually filled.
    """
    out = df.copy().sort_values([group, "date"]).reset_index(drop=True)
    before = int(out[col].isna().sum())
    out[col] = out.groupby(group)[col].ffill(limit=limit)
    filled = before - int(out[col].isna().sum())
    return out.sort_values(["date", group]).reset_index(drop=True), filled


def drop_incomplete_days(df, tickers, date_col="date", group="ticker"):
    """Drop any date that does not have a close for every fund.

    This is the rule that matters most and the one with no honest alternative. A
    weight is a share of a total. If BND is missing on a Tuesday, the weights
    computed from VTI and VXUS alone still sum to 1 - over the wrong basket. The
    result is not missing, it is *wrong*, and it looks entirely reasonable: VTI
    would read about 67% against a 60% target and fire a 7pp red flag caused by a
    gap in the data rather than by any move in the market.

    Dropping the day is expensive and honest. Filling it is cheap and invents a
    portfolio that did not exist.

    Returns
    -------
    (pd.DataFrame, list)
        The filtered copy and the dates that were dropped.
    """
    out = df.copy()
    complete = (out.dropna(subset=["close"])
                   .groupby(date_col)[group]
                   .nunique()
                   .eq(len(tickers)))
    good_dates = complete[complete].index
    dropped = [d for d in out[date_col].dropna().unique() if d not in set(good_dates)]
    return out[out[date_col].isin(good_dates)].reset_index(drop=True), sorted(dropped)


def clean_prices(df, tickers, fill_limit=3, keep="last"):
    """Run the full cleaning sequence on a long price frame.

    The order is deliberate and a different order gives different numbers:

    1. **Coerce types** - nothing below can be trusted until `date` is a real
       datetime and `close` is a real float. Sorting and filling both depend on it.
    2. **Sort by (date, ticker)** - forward fill walks row order, so an unsorted
       frame fills backwards through time.
    3. **Drop duplicate (date, ticker)** - before filling, so a duplicate cannot be
       used as the source of a fill for its own twin.
    4. **Drop non-positive prices** - a close of zero or less is not a cheap fund,
       it is a broken record. Converted to missing so the fill rules can see it.
    5. **Forward fill, with a limit** - short gaps only.
    6. **Drop incomplete days** - last, because a day that was incomplete in step 1
       may have been repaired by step 5, and dropping it earlier would throw away
       a day that the fill could have saved.

    Returns
    -------
    (pd.DataFrame, dict)
        The cleaned frame and a log of every change, for printing in the notebook.
    """
    log = {"rows_in": len(df)}

    out, failures = coerce_types(df)
    log["unparseable_values"] = failures

    out = out.sort_values(["date", "ticker"]).reset_index(drop=True)

    out, dupes = drop_duplicate_quotes(out, keep=keep)
    log["duplicate_rows_removed"] = dupes

    bad_price = out["close"].notna() & (out["close"] <= 0)
    log["non_positive_prices"] = int(bad_price.sum())
    out.loc[bad_price, "close"] = np.nan

    log["missing_closes_before_fill"] = int(out["close"].isna().sum())
    out, filled = fill_missing_closes(out, limit=fill_limit)
    log["closes_forward_filled"] = filled

    out, dropped_dates = drop_incomplete_days(out, tickers)
    log["incomplete_days_dropped"] = len(dropped_dates)
    log["dropped_dates"] = [pd.Timestamp(d).date().isoformat() for d in dropped_dates]

    out = out.dropna(subset=["close"]).reset_index(drop=True)
    log["rows_out"] = len(out)
    log["rows_removed"] = log["rows_in"] - log["rows_out"]
    return out, log
