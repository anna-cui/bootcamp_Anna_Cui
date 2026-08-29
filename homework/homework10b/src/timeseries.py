"""Lag and rolling features, and sklearn Pipelines - Stage 10b.

The Stage 10b instructions ask for code in the repo that "creates lag/rolling
features and builds a `sklearn` Pipeline". This is that code. It exists as a
module rather than as notebook cells for one reason: a Pipeline written in a
notebook is a property of that execution, while a Pipeline built by a committed
function is a property of the project.

Three rules, all inherited from earlier stages and all enforced here.

**Every window is causal, and the `.shift(1)` is the whole point.** A rolling
mean at row *t* includes row *t*. Using it to predict row *t* means using a
value you would not have had. Every rolling statistic in `make_lag_features` is
shifted by one after the window, so a feature at *t* is built only from rows up
to *t-1*.

**Features must live in the same space as the target.** This sounds obvious and
is not: building lags of *signed* drift to predict *absolute* drift scores
worse than a flat line here (test R-squared -2.12 against -0.52 for predicting
the mean). Same code, same pipeline, one wrong choice.
`make_lag_features` takes the column to build on as an argument so that choice
is explicit rather than accidental.

**Scaling belongs inside the Pipeline.** Stage 10a deliberately did not scale,
because fitting a scaler before the split fits it on rows the test set will
contain. The Stage 09 look-ahead audit cannot catch that, because it happens
after the features are built. A Pipeline fixes it structurally: `fit` on the
training fold fits the scaler on that fold only.

The axis is business-daily throughout, as Stage 08 established, so a window of
21 means 21 *trading* days and never 21 calendar days.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

DEFAULT_LAGS = (1, 5, 21)
DEFAULT_WINDOWS = (5, 21)


def make_lag_features(df, col="abs_drift", date_col="date", group="ticker",
                      lags=DEFAULT_LAGS, windows=DEFAULT_WINDOWS,
                      include_extremes=True, momentum_window=21,
                      zscore_window=21):
    """Lag, rolling, momentum and z-score features, all strictly causal.

    Produces the families the Stage 10b sheet asks for:

    - `lag_k` - the value k trading days ago. Momentum or reversal.
    - `roll_mean_w` - smoothed level, noise removed.
    - `roll_std_w` - the risk state. Stage 08 found volatility clusters, which
      is what makes this informative rather than constant.
    - `roll_min_21` / `roll_max_21` - the range recently occupied.
    - `momentum_w` - value now minus value w days before, so the direction and
      pace of travel rather than the position.
    - `zscore_w` - where the latest value sits inside its own recent
      distribution, in standard deviations. Unit-free, so it compares across
      funds whose drift lives on different scales.

    **Every rolling statistic is shifted by one after the window.** Without
    that shift the window at row *t* contains row *t*, and the model is handed
    the answer. It is one character and it is the difference between a forecast
    and a leak.

    Grouped by `group` throughout: a `.rolling()` on the long panel as
    delivered would average across funds, and it would not complain.

    Parameters
    ----------
    col : str
        The column to build features on. Choose the one the target is built
        from. See the module docstring on feature space.

    Returns
    -------
    (pd.DataFrame, list[str])
        A copy with the new columns, and the list of names created.
    """
    for c in (date_col, group, col):
        if c not in df.columns:
            raise KeyError(f"column {c!r} not found")

    out = df.sort_values([group, date_col]).reset_index(drop=True).copy()
    series = out.groupby(group)[col]
    created = []

    for k in lags:
        if k < 1:
            raise ValueError("lags must be at least 1; lag 0 is the value itself")
        name = f"lag_{k}"
        out[name] = series.shift(k)
        created.append(name)

    for w in windows:
        if w < 2:
            raise ValueError("a rolling window needs at least 2 periods")
        mean_name, std_name = f"roll_mean_{w}", f"roll_std_{w}"
        out[mean_name] = series.transform(
            lambda s, w=w: s.rolling(w).mean().shift(1))
        out[std_name] = series.transform(
            lambda s, w=w: s.rolling(w).std().shift(1))
        created += [mean_name, std_name]

    if include_extremes:
        w = max(windows)
        out[f"roll_min_{w}"] = series.transform(
            lambda s, w=w: s.rolling(w).min().shift(1))
        out[f"roll_max_{w}"] = series.transform(
            lambda s, w=w: s.rolling(w).max().shift(1))
        created += [f"roll_min_{w}", f"roll_max_{w}"]

    if momentum_window:
        w = momentum_window
        name = f"momentum_{w}"
        out[name] = series.shift(1) - series.shift(w + 1)
        created.append(name)

    if zscore_window:
        w = zscore_window
        mean_col, std_col = f"roll_mean_{w}", f"roll_std_{w}"
        if mean_col not in out.columns:
            raise ValueError(f"zscore_{w} needs windows to include {w}")
        # A zero rolling standard deviation means the series did not move at
        # all in the window. The z-score is undefined there, not infinite.
        out[f"zscore_{w}"] = ((series.shift(1) - out[mean_col])
                              / out[std_col].replace(0, np.nan))
        created.append(f"zscore_{w}")

    return out, created


def make_forecast_target(df, col="abs_drift", horizon=21, date_col="date",
                         group="ticker", out_col="y"):
    """Shift the series backwards to sit the future value on today's row.

    Features look backward, targets look forward, and the gap between them is
    what is being predicted. The last `horizon` rows of each group have no
    target and stay NaN.
    """
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    out = df.sort_values([group, date_col]).reset_index(drop=True).copy()
    out[out_col] = out.groupby(group)[col].shift(-horizon)
    return out


def build_pipeline(model=None, scale=True):
    """Preprocessing plus estimator, as one object that fits as a unit.

    This is the requirement, and the reason for it is narrow and important:
    calling `fit` on the pipeline fits the scaler **on the training rows only**.
    Scaling before the split fits it on rows the test set will contain, which
    leaks the test distribution into training. It is a small leak in level
    terms and a total one in principle.

    On this project's data that leak is worth 0.00001 RMSE. Note that this is
    not because the leaked statistics are similar: the training-only mean of
    `lag_1` is 0.629 against 0.690 over all rows, a 10% difference. It is
    because standardising is affine, and a linear model absorbs an affine
    change of its inputs into its coefficients almost exactly.

    So the Pipeline is a correctness guarantee that costs nothing, not a
    performance trick. Change the estimator to something not invariant that way
    - a tree ensemble, a distance-based method, anything with a hard
    regularisation path - and the same leak stops being free.

    Defaults to Ridge rather than plain least squares. Stage 10a found about 24
    effective observations supporting 11 parameters, and its variant sweep
    showed test scores falling as features were added. Shrinkage is the
    standard response to that, and it is the default here so a caller has to
    opt *out* of it.
    """
    if model is None:
        model = Ridge(alpha=1.0)
    steps = []
    if scale:
        steps.append(("scaler", StandardScaler()))
    steps.append(("model", model))
    return Pipeline(steps)


def evaluate_forecast(y_true, y_pred):
    """MAE, RMSE and R-squared for a forecast.

    MAE first because it is in the units of the thing being predicted and is
    the number to quote to a non-modelling reader. RMSE second because it
    punishes large misses, which is what a threshold monitor cares about.
    R-squared last, because on a shifted test distribution it is the least
    interpretable of the three.
    """
    y_true = np.asarray(y_true, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred have different lengths")
    resid = y_true - y_pred
    ss_res = float(resid @ resid)
    ss_tot = float(((y_true - y_true.mean()) ** 2).sum())
    return {"mae": float(np.abs(resid).mean()),
            "rmse": float(np.sqrt(ss_res / len(y_true))),
            "r2": 1 - ss_res / ss_tot,
            "n": len(y_true)}


def time_series_cv(pipeline, X, y, n_splits=5):
    """Walk-forward cross-validation that respects order.

    `TimeSeriesSplit` trains on a prefix and validates on the block immediately
    after it, repeatedly. Unlike k-fold it never trains on data that comes
    after what it validates on.

    Returns the per-fold scores, not just the mean, because the **spread across
    folds is the result**. On this project it grows sharply with feature count,
    which is the effective-sample-size problem showing up somewhere it can be
    seen before the test set is touched.

    Refitting the whole pipeline inside every fold is the point: the scaler is
    refitted on each training prefix rather than once on everything.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float).ravel()
    if len(X) != len(y):
        raise ValueError("X and y have different lengths")
    if n_splits < 2:
        raise ValueError("need at least 2 splits")

    from sklearn.base import clone

    rmse, r2, sizes = [], [], []
    for train_idx, val_idx in TimeSeriesSplit(n_splits=n_splits).split(X):
        fitted = clone(pipeline).fit(X[train_idx], y[train_idx])
        scores = evaluate_forecast(y[val_idx], fitted.predict(X[val_idx]))
        rmse.append(scores["rmse"])
        r2.append(scores["r2"])
        sizes.append((len(train_idx), len(val_idx)))

    return {"fold_rmse": rmse, "fold_r2": r2, "fold_sizes": sizes,
            "mean_rmse": float(np.mean(rmse)), "std_rmse": float(np.std(rmse)),
            "mean_r2": float(np.mean(r2)), "std_r2": float(np.std(r2)),
            "n_splits": n_splits}


def sweep_feature_sets(train, test, target, feature_sets, model=None,
                       n_splits=5):
    """Score several feature sets by cross-validation, then on the test set.

    The column order matters. `cv_rmse` is computed on the training data alone,
    so it is the number a selection may honestly be made on. `test_rmse` comes
    last and is a check on that selection, not an input to it. Choosing the
    feature set by its test score and then reporting that score is the most
    common way to produce a number nobody can reproduce.

    `cv_std` is reported next to `cv_rmse` because a small mean over wildly
    varying folds is not evidence of anything.
    """
    if not feature_sets:
        raise ValueError("no feature sets to sweep")

    rows = {}
    for name, cols in feature_sets.items():
        missing = [c for c in cols if c not in train.columns]
        if missing:
            raise KeyError(f"feature set {name!r} wants missing columns {missing}")

        pipe = build_pipeline(model=model)
        cv = time_series_cv(pipe, train[cols], train[target], n_splits=n_splits)
        fitted = build_pipeline(model=model).fit(train[cols], train[target])
        scores = evaluate_forecast(test[target], fitted.predict(test[cols]))

        rows[name] = {"n_features": len(cols),
                      "cv_rmse": cv["mean_rmse"], "cv_std": cv["std_rmse"],
                      "test_rmse": scores["rmse"], "test_mae": scores["mae"],
                      "test_r2": scores["r2"]}

    return (pd.DataFrame(rows).T
            .sort_values("cv_rmse")
            .astype(float)
            .round(4))


def persistence_forecast(test, lag_col="lag_1"):
    """The baseline to beat: assume the value does not change.

    On a trended series this is strong, and quoting a model's score without it
    is how a model that has learned only the trend gets presented as a success.
    `lag_1` *is* this forecast, which is why a model given `lag_1` and nothing
    else should be expected to land near it.
    """
    if lag_col not in test.columns:
        raise KeyError(f"column {lag_col!r} not found")
    return test[lag_col].to_numpy(dtype=float)
