"""Feature engineering for the Portfolio Drift Monitor - Stage 09.

Every function here exists because Stage 08 found something specific. The
lineage matters more than the code, so it is recorded next to each one:

| Feature | Where it came from |
|---|---|
| `drift_rel` | Stage 07 named the pp-vs-relative unit problem and left it open. Stage 08 sized it: BND's worst drift is 17.7% of its target, VTI's is 2.6%. |
| `drift_chg_1` | Stage 08: the level is dominated by a trend, so build the rate. |
| `drift_slope_21/63` | Stage 08: BND's drift correlates with time at -0.93. A rolling slope is that finding as a per-row number. |
| `vol_21` | Stage 08's rolling-vol plot showed real clustering (VTI 6-21%, VXUS 8-29%). |
| `eq_bond_spread_21` | Stage 08 identified the equity-over-bond return spread as the *mechanism* producing the drift. |
| `ticker` encoding | Stage 08's categorical profile: 251/251/251 exactly. That number decides which of the three lecture encodings is usable. |
| `close_was_filled` | `README.md` names this as the obvious Stage 09 feature, unbuilt since Stage 06. |

Three rules the whole module obeys:

**Nothing modifies its input.** Every function returns a new frame, same as
`cleaning.py`, `outliers.py` and `eda.py`.

**Every window is causal.** No centred windows, no interpolation, no
`bfill`. A feature at row *t* may only see rows at or before *t*.
`assert_no_lookahead` tests that claim rather than asserting it in a comment,
because a leaked feature does not raise an error, it raises an R-squared.

**Every rolling and shifting operation runs inside a ticker group on a
date-sorted frame.** A `.rolling(21)` on the long panel as delivered would
average across funds. It would also not complain.

The axis is business-daily, as Stage 08 established, so a window of 21 means
21 *trading* days (about a calendar month) and never 21 calendar days. Nothing
here reindexes to `freq='D'`.
"""

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 251


def _sorted_panel(df, date_col="date", group="ticker"):
    """Return a date-sorted copy, or raise if the columns needed are absent."""
    for col in (date_col, group):
        if col not in df.columns:
            raise KeyError(f"column {col!r} not found")
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col])
    return out.sort_values([group, date_col]).reset_index(drop=True)


def rolling_slope(series, window, per_year=TRADING_DAYS_PER_YEAR):
    """Slope of an ordinary least squares line fitted to the last `window` rows.

    Returned in units per year rather than per row, so a value is readable
    without knowing the window: -1.7 means "falling 1.7 percentage points a
    year at the pace of the last month".

    Uses the closed form (sum of centred x times centred y, over sum of centred
    x squared) rather than `np.polyfit` inside the apply, because polyfit
    re-solves a least squares system on every one of several hundred windows.

    The window is right-aligned, which is what makes it causal: the value at
    row *t* is fitted to rows *t-window+1* through *t*.
    """
    if window < 3:
        raise ValueError("a slope needs at least 3 points to mean anything")
    x = np.arange(window, dtype=float)
    xc = x - x.mean()
    denom = (xc ** 2).sum()

    def _fit(values):
        return float((xc * (values - values.mean())).sum() / denom)

    return series.rolling(window).apply(_fit, raw=True) * per_year


def add_daily_returns(prices_long, date_col="date", group="ticker", col="close",
                      out_col="ret_1"):
    """Per-fund daily simple return.

    Grouped, because a `.pct_change()` on the long frame as delivered would
    compute BND's first return against VXUS's last price. The result would be
    a plausible-looking number rather than an error.

    `fill_method=None` is explicit: pandas used to forward-fill before
    differencing, which silently turns a gap into a zero return.
    """
    out = _sorted_panel(prices_long, date_col, group)
    out[out_col] = out.groupby(group)[col].pct_change(fill_method=None)
    return out


def volatility_feature(prices_long, window=21, date_col="date", group="ticker",
                       col="close", periods_per_year=252):
    """Rolling realized volatility, annualized, in percent.

    Stage 08's rolling-vol plot showed volatility moving in clusters rather
    than sitting at a level: VTI between 6% and 21%, VXUS between 8% and 29%.
    Clustering is what makes this a feature instead of a constant. A fund in a
    high-volatility regime covers ground faster, so its weight moves further
    per unit of time, which is the connection to drift.

    Costs `window` rows per fund at the start of the series. They stay NaN
    rather than being back-filled: a volatility estimate over four days is not
    a 21-day volatility, and pretending otherwise is the cheapest way to leak
    a bad number into a model.
    """
    out = add_daily_returns(prices_long, date_col, group, col)
    out[f"vol_{window}"] = (out.groupby(group)["ret_1"]
                               .transform(lambda s: s.rolling(window).std())
                            * np.sqrt(periods_per_year) * 100)
    return out


def drift_features(drift_long, target_weights, slope_windows=(21, 63),
                   date_col="date", group="ticker", drift_col="drift_pp"):
    """Level, relative level, rate of change, and rolling slope of the drift.

    Four features, each answering a different question:

    - `abs_drift` - how far from target, ignoring direction. This is what the
      threshold is actually compared against.
    - `drift_rel` - the same distance as a percentage *of that fund's target*.
      This is Stage 07's open unit problem expressed as a number. BND's 1.77pp
      on a 10% target and VTI's 1.55pp on a 60% target are nearly equal in
      percentage points and differ by a factor of seven in relative terms.
      Within one fund it is a constant rescale of `drift_pp` and carries the
      same information; across funds it is the only one of the two that
      compares.
    - `drift_chg_1` - the first difference. Stage 08's instruction was to build
      the rate rather than the level, because a trended level makes yesterday's
      value nearly as good a predictor as today's.
    - `drift_slope_<w>` - the trend itself, per row. Stage 08 fitted one line
      to the whole year and got -0.93 for BND. This fits the same line to a
      moving window, so the model can see the trend *steepening* rather than
      only that it exists.

    Every operation is grouped and right-aligned. The slope windows cost
    `w - 1` rows per fund; a 63-day window costs about a quarter of the data,
    which is why `feature_report` reports missingness rather than hiding it.
    """
    out = _sorted_panel(drift_long, date_col, group)
    if drift_col not in out.columns:
        raise KeyError(f"column {drift_col!r} not found")

    targets = out[group].map(target_weights)
    if targets.isna().any():
        missing = sorted(out.loc[targets.isna(), group].unique())
        raise KeyError(f"no target weight for {missing}")

    out["abs_drift"] = out[drift_col].abs()
    # drift_pp is already in percentage points; target*100 puts the denominator
    # in the same units, so the result reads as "percent of the target weight".
    out["drift_rel"] = out[drift_col] / (targets * 100) * 100
    out["abs_drift_rel"] = out["drift_rel"].abs()
    out["drift_chg_1"] = out.groupby(group)[drift_col].diff(1)
    out["drift_chg_5"] = out.groupby(group)[drift_col].diff(5)

    for window in slope_windows:
        out[f"drift_slope_{window}"] = (
            out.groupby(group)[drift_col]
               .transform(lambda s, w=window: rolling_slope(s, w))
        )
    return out


def equity_bond_spread(prices_long, target_weights, bond="BND", window=21,
                       date_col="date", group="ticker", col="close",
                       periods_per_year=252):
    """Annualized equity-minus-bond return spread over a trailing window.

    This is the mechanism, not a correlate. Stage 08 traced the drift to a
    persistent return spread: over the window the equity funds returned +19.2%
    and +22.6% against the bond fund's -2.0%, and a portfolio bought at target
    and left alone drifts at a rate set by exactly that gap. Every other
    feature here describes the drift; this one describes what is causing it.

    Portfolio-level rather than per-fund, so it takes the same value for all
    three rows on a date. That is correct and worth stating: it is a property
    of the market that day, not of a fund.

    The equity leg is weighted by the funds' targets rather than averaged, so
    it matches the portfolio actually being monitored.
    """
    out = add_daily_returns(prices_long, date_col, group, col)
    wide = out.pivot(index=date_col, columns=group, values="ret_1")

    equity = [t for t in target_weights if t != bond]
    if bond not in wide.columns:
        raise KeyError(f"bond fund {bond!r} not in the data")
    if not equity:
        raise ValueError("no equity funds to form a spread against")

    weights = np.array([target_weights[t] for t in equity], dtype=float)
    weights = weights / weights.sum()
    equity_ret = (wide[equity] * weights).sum(axis=1)

    spread = ((equity_ret.rolling(window).mean() - wide[bond].rolling(window).mean())
              * periods_per_year * 100)
    return spread.rename(f"eq_bond_spread_{window}").reset_index()


def encode_ticker(df, method="onehot", col="ticker", target_weights=None,
                  drop_first=False):
    """Encode the fund identifier. Four methods; they are not interchangeable.

    The lecture offers three, and on *this* dataset the choice is decided by a
    single number from Stage 08's categorical profile: the split is 251 / 251 /
    251, exactly, because Stage 06's `drop_incomplete_days` keeps only dates
    that have a close for every fund.

    - **frequency** - maps each fund to its share of the rows. All three shares
      are 0.3333, so the encoded column has exactly one distinct value. It is
      not a weaker encoding here, it is arithmetically a constant, and it
      carries precisely zero information. Included so the notebook can show
      that rather than assert it.
    - **label** - assigns integers in alphabetical order: BND 0, VTI 1,
      VXUS 2. A linear model reads that as an ordering and a spacing, so it
      would be told that VXUS is twice VTI and that the gap from BND to VTI
      equals the gap from VTI to VXUS. Both are artifacts of the alphabet.
    - **onehot** - three indicator columns, no invented ordering. With three
      categories the width cost is trivial. This is the one to use.
    - **target_weight** - encodes each fund by its policy target (0.60 / 0.30 /
      0.10). Not in the lecture. It is a genuine ordinal, unlike the label
      encoding, and it carries the domain knowledge that the funds differ by
      how much of the portfolio they are meant to be. Its limitation is the
      mirror of its strength: it is constant within a fund, so it can only help
      a model that pools the three.

    `drop_first` is available for one-hot but off by default: it avoids the
    dummy-variable trap for a model with an intercept, and costs interpretability
    for one without. That is a Stage 10 decision, not a Stage 09 one.
    """
    if col not in df.columns:
        raise KeyError(f"column {col!r} not found")
    out = df.copy()

    if method == "onehot":
        dummies = pd.get_dummies(out[col], prefix=col, drop_first=drop_first)
        return pd.concat([out, dummies.astype(int)], axis=1)

    if method == "label":
        levels = sorted(out[col].dropna().unique())
        out[f"{col}_label"] = out[col].map({v: i for i, v in enumerate(levels)})
        return out

    if method == "frequency":
        shares = out[col].value_counts(normalize=True)
        out[f"{col}_freq"] = out[col].map(shares)
        return out

    if method == "target_weight":
        if target_weights is None:
            raise ValueError("target_weight encoding needs target_weights")
        out[f"{col}_target"] = out[col].map(target_weights)
        if out[f"{col}_target"].isna().any():
            raise KeyError("a ticker has no target weight")
        return out

    raise ValueError(f"unknown method {method!r}; use onehot, label, "
                     "frequency or target_weight")


def flag_filled_closes(prices_clean, prices_raw, date_col="date", group="ticker",
                       col="close", out_col="close_was_filled"):
    """Mark rows whose close was forward-filled rather than observed.

    `README.md` has named this as the obvious Stage 09 feature since Stage 06,
    and the reason it matters is stated there: a forward-filled close carries
    the same dtype as a real one, so once the cleaning log scrolls past,
    nothing downstream can tell an estimate from an observation.

    Derived by comparing the cleaned frame against the raw pull rather than by
    reading `cleaning.py`'s internals, so it stays correct if the fill rule
    changes.

    On a clean vendor pull this returns all zeros, which makes it a constant
    and therefore useless as a model input *today*. It is still worth building
    and keeping in the pipeline: it costs nothing, and the day a vendor gap
    appears it is the only column that can tell the model which rows are
    estimates. `feature_report` will show it as zero-variance so nobody feeds
    a constant to a model by accident.
    """
    raw = prices_raw.copy()
    raw[date_col] = pd.to_datetime(raw[date_col])
    raw[col] = pd.to_numeric(raw[col], errors="coerce")
    observed = (raw.dropna(subset=[col])
                   .loc[:, [date_col, group]]
                   .drop_duplicates())
    observed["_observed"] = 1

    out = prices_clean.copy()
    out[date_col] = pd.to_datetime(out[date_col])
    out = out.merge(observed, on=[date_col, group], how="left")
    out[out_col] = out["_observed"].isna().astype(int)
    return out.drop(columns="_observed")


def make_forward_target(df, horizon=21, date_col="date", group="ticker",
                        col="drift_pp", absolute=True, out_col=None):
    """Shift the drift backwards to make a forward-looking target.

    `horizon` is in trading days, so 21 is about a calendar month.

    **Why not a 1-day horizon.** Today's absolute drift correlates with
    tomorrow's at 0.98 pooled and 0.99 for BND. A one-day target is very nearly
    the feature itself, so any model scores brilliantly and has learned
    nothing. At 21 days the same correlation falls to 0.69, which leaves room
    for a model to add something. That gap is Stage 08's trend finding showing
    up as a modelling constraint.

    **Why the sign is dropped by default.** The threshold is compared against
    the magnitude, so the operational question is "how far from target", not
    "in which direction".

    The last `horizon` rows of every fund necessarily have no target and stay
    NaN. They are kept rather than dropped so the frame still lines up with the
    price history; dropping them is the modelling stage's decision.
    """
    if horizon < 1:
        raise ValueError("horizon must be at least 1 trading day")
    out = _sorted_panel(df, date_col, group)
    if out_col is None:
        out_col = f"y_{'abs' if absolute else ''}drift_fwd_{horizon}"
    source = out[col].abs() if absolute else out[col]
    out[out_col] = source.groupby(out[group]).shift(-horizon)
    return out


def _safe_corr(pair, col, target_col):
    """Pearson correlation, or NaN where it is undefined rather than a warning.

    A constant column has zero standard deviation, so the correlation divides
    by zero. numpy returns a nan and prints a RuntimeWarning; a one-hot column
    inside a single-fund group hits this on every call. NaN is the honest
    answer, so it is returned directly and the warning never appears.
    """
    if len(pair) < 3:
        return np.nan
    if pair[col].nunique() < 2 or pair[target_col].nunique() < 2:
        return np.nan
    return pair[col].corr(pair[target_col])


def feature_report(df, feature_cols, target_col, group=None):
    """One row per feature: coverage, spread, and correlation with the target.

    Three columns decide whether a feature is usable at all, and they are
    reported before the correlation so a promising number on a nearly empty
    column cannot be read on its own:

    - `pct_missing` - the price of the window. Stage 08's `flag_columns` treats
      more than 20% as a column needing a decision, and that gate applies here.
    - `n_unique` - catches constants. This is the check Stage 08's helper
      misses: its near-zero-variance rule divides by the mean and skips any
      column whose mean is zero, so an all-zero column slips through.
    - `corr_with_target` - Pearson, on the rows where both are present.

    Correlation is a hint, not a ranking. A feature can be uncorrelated with
    the target on its own and still matter in combination, and a strong
    correlation on 8% of the rows is not evidence of anything.
    """
    if target_col not in df.columns:
        raise KeyError(f"target column {target_col!r} not found")

    rows = []
    for col in feature_cols:
        if col not in df.columns:
            raise KeyError(f"feature column {col!r} not found")
        series = df[col]
        pair = df[[col, target_col]].dropna()
        rows.append({
            "feature": col,
            "pct_missing": round(series.isna().mean() * 100, 2),
            "n_unique": int(series.nunique(dropna=True)),
            "mean": series.mean() if pd.api.types.is_numeric_dtype(series) else np.nan,
            "std": series.std() if pd.api.types.is_numeric_dtype(series) else np.nan,
            "n_pairs": len(pair),
            "corr_with_target": _safe_corr(pair, col, target_col),
        })
    report = pd.DataFrame(rows).set_index("feature")

    if group is not None:
        for level, part in df.groupby(group, sort=True):
            corrs = [_safe_corr(part[[col, target_col]].dropna(), col, target_col)
                     for col in feature_cols]
            report[f"corr_{level}"] = corrs

    return report.round(4)


def assert_no_lookahead(build_fn, frame, feature_cols, date_col="date",
                        cut_fraction=0.7, atol=1e-9):
    """Verify no feature at time t is changed by data after t.

    The test: build the features on the full history, then build them again on
    the history truncated at a cut date, and compare the overlapping rows. A
    causal feature is identical in both. A leaked one is not.

    This catches what a code review usually does not: a centred rolling window,
    a `bfill`, a `fillna` with a full-series mean, a scaler fitted on
    everything, a target shifted the wrong way. None of those raise an error.
    They raise an R-squared, which is why they survive until someone trusts the
    model.

    Parameters
    ----------
    build_fn : callable
        Takes a price/drift frame, returns the feature frame. Must be pure.
    frame : pd.DataFrame
        The input `build_fn` expects.
    feature_cols : list[str]
        Columns to compare. Pass features only; a forward-looking target is
        *supposed* to change when the future is truncated.

    Raises
    ------
    AssertionError
        Naming the first offending column and how far off it was.
    """
    full = build_fn(frame)
    dates = pd.to_datetime(frame[date_col]).sort_values().unique()
    cut = pd.Timestamp(dates[int(len(dates) * cut_fraction)])

    truncated = build_fn(frame[pd.to_datetime(frame[date_col]) <= cut])

    keys = [date_col] + [c for c in ("ticker",) if c in full.columns]
    left = full[pd.to_datetime(full[date_col]) <= cut].set_index(keys).sort_index()
    right = truncated.set_index(keys).sort_index()
    shared = left.index.intersection(right.index)

    if len(shared) == 0:
        raise AssertionError("no overlapping rows to compare - check the cut")

    for col in feature_cols:
        a = pd.to_numeric(left.loc[shared, col], errors="coerce")
        b = pd.to_numeric(right.loc[shared, col], errors="coerce")
        both_nan = a.isna() & b.isna()
        diff = (a - b).abs()
        worst = diff[~both_nan].max()

        n_nan_full, n_nan_cut = int(a.isna().sum()), int(b.isna().sum())
        if n_nan_full != n_nan_cut:
            raise AssertionError(
                f"look-ahead detected in {col!r}: truncating the future changed which "
                f"past rows are even defined ({n_nan_full} NaN with the full history, "
                f"{n_nan_cut} without it). A window that needs rows after t is not causal."
            )
        if pd.notna(worst) and worst > atol:
            raise AssertionError(
                f"look-ahead detected in {col!r}: truncating the future changed "
                f"{int((diff > atol).sum())} past values, worst {worst:.3g}"
            )

    return {"cut_date": cut, "rows_compared": len(shared),
            "features_checked": len(feature_cols)}


# --- project orchestration ------------------------------------------------
#
# The functions above are the homework's, unchanged. The two below wire them
# to this project's own frames so `notebooks/project_pipeline.ipynb` can build
# the whole feature matrix in one call, and so `assert_no_lookahead` has a
# single pure function to test.


def drift_panel(prices_clean, target_weights, portfolio_value=1_000_000,
                date_col="date", group="ticker", col="close"):
    """Long drift frame from a long price frame, on the project's convention.

    Buy the target allocation on day one and never rebalance, so drift is what
    the market does to a portfolio left alone. Day zero sits exactly on target
    by construction, which is asserted rather than assumed.

    Returns one row per (date, fund) with `weight`, `target_weight` and
    `drift_pp`.
    """
    tickers = list(target_weights)
    wide = prices_clean.pivot(index=date_col, columns=group, values=col)[tickers]
    if wide.isna().any().any():
        raise ValueError("the price frame has holes; clean it before building weights")

    targets = np.array([target_weights[t] for t in tickers], dtype=float)
    shares = (portfolio_value * targets) / wide.iloc[0].to_numpy()
    values = wide.to_numpy() * shares
    weights = values / values.sum(axis=1, keepdims=True)

    if not np.allclose(weights[0], targets):
        raise AssertionError("day 0 should sit exactly on target")

    weights_df = pd.DataFrame(weights, index=wide.index, columns=tickers)
    out = (weights_df.reset_index()
                     .melt(id_vars=date_col, var_name=group, value_name="weight"))
    out["target_weight"] = out[group].map(target_weights)
    out["drift_pp"] = (out["weight"] - out["target_weight"]) * 100
    return out.sort_values([date_col, group]).reset_index(drop=True)


def build_feature_matrix(prices_clean, target_weights, prices_raw=None,
                         horizon=21, slope_windows=(21, 63), vol_window=21,
                         spread_window=21, bond="BND", with_target=True):
    """Every feature in one call, from the cleaned prices alone.

    Pure by design: no globals, no mutation, and the output for any row depends
    only on rows at or before that row's date. That is what lets
    `assert_no_lookahead` test the whole build rather than one feature at a
    time. Pass `with_target=False` when testing, because a forward-looking
    target is *supposed* to change when the future is truncated.

    `prices_raw` is optional and only used for `close_was_filled`. Omit it and
    that column is not produced, rather than being produced wrong.
    """
    drift_long = drift_panel(prices_clean, target_weights)

    out = drift_features(drift_long, target_weights, slope_windows=slope_windows)

    vol = volatility_feature(prices_clean, window=vol_window)[
        ["date", "ticker", "ret_1", f"vol_{vol_window}"]]
    out = out.merge(vol, on=["date", "ticker"], how="left")

    spread = equity_bond_spread(prices_clean, target_weights, bond=bond,
                                window=spread_window)
    out = out.merge(spread, on="date", how="left")

    out = encode_ticker(out, "onehot")
    out = encode_ticker(out, "target_weight", target_weights=target_weights)

    if prices_raw is not None:
        filled = flag_filled_closes(prices_clean, prices_raw)[
            ["date", "ticker", "close_was_filled"]]
        out = out.merge(filled, on=["date", "ticker"], how="left")

    if with_target:
        out = make_forward_target(out, horizon=horizon)

    return out.sort_values(["ticker", "date"]).reset_index(drop=True)


#: The columns Stage 09 hands to Stage 10. `drift_slope_63` is excluded (24.7%
#: missing, fails Stage 08's own gate for nothing), and so are the encodings
#: that lose to one-hot and the columns that are currently constant.
MODEL_FEATURES = [
    "abs_drift", "abs_drift_rel", "drift_chg_1", "drift_chg_5",
    "drift_slope_21", "ret_1", "vol_21", "eq_bond_spread_21",
    "ticker_VTI", "ticker_VXUS", "ticker_BND",
]
