"""Helper utilities for Stage 03."""

from datetime import datetime


def log_call(func):
    """Print a timestamped line each time the wrapped function runs."""
    def wrapper(*args, **kwargs):
        print(f"[{datetime.now()}] Function '{func.__name__}' called.")
        return func(*args, **kwargs)
    return wrapper


@log_call
def get_summary_stats(df):
    """Return descriptive statistics for the numeric columns of `df`."""
    return df.describe()


@log_call
def summarize_by_group(df, group_col, value_col):
    """Aggregate `value_col` within each level of `group_col`.

    Returns count, mean, median, std, min and max as a tidy DataFrame with
    `group_col` as an ordinary column rather than the index, so the result can
    be written straight to CSV.

    Assumptions
    -----------
    - `group_col` is categorical with a manageable number of levels.
    - `value_col` is numeric; non-numeric input raises rather than coercing.
    """
    if value_col not in df.select_dtypes("number").columns:
        raise TypeError(f"{value_col!r} is not numeric")
    return (df.groupby(group_col)[value_col]
              .agg(["count", "mean", "median", "std", "min", "max"])
              .reset_index())
