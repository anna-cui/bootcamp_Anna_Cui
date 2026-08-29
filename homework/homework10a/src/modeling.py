"""Linear regression and diagnostics for the Portfolio Drift Monitor - Stage 10a.

Stage 09 handed over a feature matrix and a target. This module fits a model to
them and, more importantly, tests whether the four assumptions that make a
linear regression *interpretable* actually hold.

Two things shape every function here.

**The split is chronological, never random.** Stage 08 established the drift is
a trend. On a trended series a random split puts rows from after a test row
into the training set, so the model is asked about a regime it has already
seen. `chronological_split` is the only split function in this module, and it
splits on unique dates rather than on rows, so all three funds of a day stay on
the same side.

**No statsmodels.** Durbin-Watson, Breusch-Pagan and the coefficient standard
errors are computed here from numpy and scipy, which the project already
depends on. They are twenty lines in total, and writing them out makes it
visible that a p-value is a formula applied to residuals rather than a verdict
handed down by a library.

The diagnostics are the deliverable, not the R-squared. The reading puts it as
"story over score": the residuals are the channel through which the data says
what the model got wrong.
"""

import numpy as np
import pandas as pd
from scipy import stats

TRADING_DAYS_PER_YEAR = 251


# --- splitting -----------------------------------------------------------

def chronological_split(df, date_col="date", test_frac=0.2):
    """Split on unique dates: earliest `1 - test_frac` train, the rest test.

    Splitting on dates rather than rows matters for a long panel. A row-based
    split at 80% would cut through the middle of a day and put VTI in train and
    BND in test for the same date, which leaks the market conditions of that day
    across the boundary.

    No shuffling and no random state. Position in time *is* the split.

    Returns
    -------
    (train, test, cut_date)
    """
    if not 0 < test_frac < 1:
        raise ValueError("test_frac must be strictly between 0 and 1")
    dates = np.sort(pd.to_datetime(df[date_col]).unique())
    if len(dates) < 10:
        raise ValueError("too few distinct dates to split meaningfully")
    cut = pd.Timestamp(dates[int(len(dates) * (1 - test_frac))])
    stamps = pd.to_datetime(df[date_col])
    return df[stamps < cut].copy(), df[stamps >= cut].copy(), cut


# --- fitting -------------------------------------------------------------

def fit_ols(X, y, feature_names=None):
    """Fit OLS by least squares and return coefficients with inference.

    Returns the standard errors, t statistics and p-values as well as the
    point estimates, because the point of Stage 10a is that a coefficient
    without an interval is only half a result.

    **Those p-values are only valid if the residuals are independent.** This
    function computes them; `regression_diagnostics` is what tells you whether
    to believe them. On this project's data it says no, emphatically, and the
    two facts belong side by side.

    The design matrix must be full rank. One-hot columns for every level plus
    an intercept are collinear by construction (they sum to the intercept), so
    drop one level first. `np.linalg.lstsq` would quietly return a minimum-norm
    solution instead of complaining, so this raises.

    Returns
    -------
    dict with `coefficients` (DataFrame), `r_squared`, `adj_r_squared`,
    `residuals`, `fitted`, `n`, `k`, `sigma2`.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float).ravel()
    if feature_names is None:
        feature_names = [f"x{i}" for i in range(X.shape[1])]
    if len(feature_names) != X.shape[1]:
        raise ValueError("feature_names does not match the number of columns")

    design = np.column_stack([np.ones(len(X)), X])
    n, k = design.shape
    if n <= k:
        raise ValueError(f"{n} rows cannot fit {k} parameters")
    if np.linalg.matrix_rank(design) < k:
        raise ValueError(
            "design matrix is rank deficient - collinear columns. If you "
            "one-hot encoded every level, drop one to serve as the reference."
        )

    xtx_inv = np.linalg.inv(design.T @ design)
    beta = xtx_inv @ design.T @ y
    fitted = design @ beta
    resid = y - fitted

    dof = n - k
    sigma2 = float(resid @ resid / dof)
    se = np.sqrt(np.diag(sigma2 * xtx_inv))
    tvals = beta / se
    pvals = 2 * (1 - stats.t.cdf(np.abs(tvals), df=dof))

    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot
    adj = 1 - (1 - r2) * (n - 1) / dof

    coefficients = pd.DataFrame(
        {"coef": beta, "std_err": se, "t": tvals, "p_value": pvals},
        index=["intercept"] + list(feature_names),
    )
    return {"coefficients": coefficients, "r_squared": r2, "adj_r_squared": adj,
            "residuals": resid, "fitted": fitted, "n": n, "k": k,
            "sigma2": sigma2, "beta": beta}


def predict_ols(beta, X):
    """Apply fitted coefficients to a new design matrix (intercept first)."""
    X = np.asarray(X, dtype=float)
    return np.column_stack([np.ones(len(X)), X]) @ np.asarray(beta, dtype=float)


# --- the four assumptions ------------------------------------------------

def durbin_watson(resid):
    """Test statistic for first-order autocorrelation in residuals.

    ``sum((e_t - e_{t-1})^2) / sum(e_t^2)``

    Reads on a scale from 0 to 4: **2 means no autocorrelation**, near 0 means
    strong positive autocorrelation, near 4 strong negative. Below about 1.5 is
    conventionally a problem.

    Positive autocorrelation is the failure that matters most here, because it
    does not bias the coefficients but it does make the standard errors far too
    small, which makes p-values far too impressive.
    """
    e = np.asarray(resid, dtype=float)
    if len(e) < 3:
        raise ValueError("need at least 3 residuals")
    return float(np.sum(np.diff(e) ** 2) / np.sum(e ** 2))


def breusch_pagan(resid, X):
    """Test for heteroscedasticity: is the residual variance constant?

    Regress the squared residuals on the predictors. If the predictors explain
    any of the variance in the squared residuals, the spread of the errors
    depends on where you are in feature space, which is the definition of
    heteroscedasticity.

    ``LM = n * R^2`` from that helper regression, compared against a chi-squared
    distribution with `k` degrees of freedom.

    A small p-value says the variance is not constant. It does not say the
    problem is *large*: report the ratio of residual spread between the high-
    and low-fitted halves alongside it, because a highly significant 16%
    difference is statistically real and practically minor.
    """
    e = np.asarray(resid, dtype=float)
    X = np.asarray(X, dtype=float)
    if len(e) != len(X):
        raise ValueError("residuals and design matrix have different lengths")

    design = np.column_stack([np.ones(len(X)), X])
    if np.linalg.matrix_rank(design) < design.shape[1]:
        raise ValueError("design matrix is rank deficient - drop a collinear column")

    g = e ** 2
    beta = np.linalg.solve(design.T @ design, design.T @ g)
    fitted = design @ beta
    ss_res = float(((g - fitted) ** 2).sum())
    ss_tot = float(((g - g.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot

    n, k = len(e), X.shape[1]
    lm = n * r2
    return {"lm_stat": float(lm), "p_value": float(1 - stats.chi2.cdf(lm, k)),
            "df": k, "helper_r_squared": float(r2)}


def normality_tests(resid):
    """Shapiro-Wilk and Jarque-Bera, plus the shape numbers behind them.

    Normality is the *least* important of the four for point prediction and the
    most important for inference. Non-normal residuals do not bias the
    coefficients; they invalidate the confidence intervals and p-values built
    on them.

    Skew and excess kurtosis are reported because the tests only say "not
    normal", and with several hundred observations they say that about almost
    anything. The shape numbers say how badly, and in which direction.
    """
    e = np.asarray(resid, dtype=float)
    sw = stats.shapiro(e)
    jb = stats.jarque_bera(e)
    return {"shapiro_W": float(sw.statistic), "shapiro_p": float(sw.pvalue),
            "jarque_bera": float(jb.statistic), "jarque_bera_p": float(jb.pvalue),
            "skew": float(stats.skew(e)), "excess_kurtosis": float(stats.kurtosis(e))}


def effective_sample_size(n_rows, horizon, n_groups=1):
    """How many *independent* observations a forward-window target really has.

    A target built as "the value `horizon` steps ahead" overlaps between
    neighbouring rows: consecutive rows share `horizon - 1` of the `horizon`
    days in their windows. They are close to the same observation counted
    twice, and a regression that treats them as independent has far less
    information than its row count suggests.

    The rough correction is to divide the rows per group by the horizon. It is
    a rule of thumb rather than a theorem, and it is quoted as one, but the
    order of magnitude is what matters: it is the difference between "hundreds
    of observations" and "dozens".
    """
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    per_group = n_rows / max(n_groups, 1)
    return {"n_rows": int(n_rows), "n_groups": int(n_groups),
            "rows_per_group": float(per_group), "horizon": int(horizon),
            "effective_per_group": per_group / horizon,
            "effective_total": (per_group / horizon) * max(n_groups, 1)}


def regression_diagnostics(fit, X, group_labels=None, horizon=None):
    """Run all four assumption checks on a fitted model and return one dict.

    `group_labels` runs the independence check within each group as well as
    pooled, which matters for a panel: residuals for one fund are a time series,
    residuals for the stacked panel are three time series laid end to end and a
    pooled statistic on them is hard to read.
    """
    resid = np.asarray(fit["residuals"], dtype=float)
    fitted = np.asarray(fit["fitted"], dtype=float)

    curvature = float(np.polyfit(fitted, resid, 2)[0])

    independence = {"pooled_durbin_watson": durbin_watson(resid)}
    if group_labels is not None:
        labels = pd.Series(np.asarray(group_labels))
        by_group = {}
        for level in sorted(labels.unique()):
            mask = (labels == level).to_numpy()
            e = resid[mask]
            by_group[str(level)] = {
                "durbin_watson": durbin_watson(e),
                "lag1_autocorr": float(pd.Series(e).autocorr(1)),
            }
        independence["by_group"] = by_group

    order = np.argsort(fitted)
    low, high = np.array_split(order, 2)
    scatter = {"resid_std_low_fitted": float(resid[low].std()),
               "resid_std_high_fitted": float(resid[high].std())}
    scatter["ratio"] = scatter["resid_std_high_fitted"] / scatter["resid_std_low_fitted"]

    out = {
        "linearity": {"resid_fitted_corr": float(np.corrcoef(resid, fitted)[0, 1]),
                      "quadratic_curvature": curvature},
        "independence": independence,
        "homoscedasticity": {**breusch_pagan(resid, X), **scatter},
        "normality": normality_tests(resid),
    }
    if horizon is not None:
        n_groups = len(set(map(str, group_labels))) if group_labels is not None else 1
        out["effective_sample"] = effective_sample_size(len(resid), horizon, n_groups)
    return out


# --- evaluation ----------------------------------------------------------

def evaluate(y_true, y_pred):
    """R-squared, RMSE and MAE for one set of predictions.

    R-squared here is computed against the mean of `y_true` itself, so on a
    test set it answers "did the model beat predicting the test set's own
    mean". That is the conventional definition and it is worth stating, because
    a negative value is not a bug: it means the model did worse than a
    horizontal line.
    """
    y_true = np.asarray(y_true, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred have different lengths")
    resid = y_true - y_pred
    ss_res = float(resid @ resid)
    ss_tot = float(((y_true - y_true.mean()) ** 2).sum())
    return {"r2": 1 - ss_res / ss_tot,
            "rmse": float(np.sqrt(ss_res / len(y_true))),
            "mae": float(np.abs(resid).mean()),
            "n": len(y_true)}


def compare_baselines(train, test, target, naive_col=None):
    """Score the trivial predictors a model has to beat to be worth anything.

    Two of them:

    - **train mean** - the horizontal line. Beating it is the minimum bar and
      R-squared is defined against it.
    - **persistence** - predict that the target `horizon` days out equals the
      value it has today. On a trended series this is a *strong* baseline, and
      quoting a model's R-squared without it is how a model that has learned
      nothing but the trend gets presented as a success.
    """
    out = {"train_mean": evaluate(test[target],
                                 np.full(len(test), train[target].mean()))}
    if naive_col is not None:
        out["persistence"] = evaluate(test[target], test[naive_col])
    return out


# --- the auto-try loop ---------------------------------------------------

def auto_try(train, test, target, variants, group_col=None, horizon=None):
    """Fit several feature sets under identical conditions and rank them.

    The project instructions ask to "automate the modeling process so you can
    auto-try the model with some variations". This is that: one function, one
    split, one metric set, so the comparison between variants is a comparison
    of the variants rather than of how each one happened to be run.

    Reports train and test scores side by side on purpose. A variant whose
    train score rises while its test score falls is overfitting, and that is
    only visible when both are in the same table. On this project's data the
    polynomial variants do exactly that.

    Parameters
    ----------
    variants : dict[str, list[str]]
        Name to feature-column list. Each must be full rank with an intercept.

    Returns
    -------
    (pd.DataFrame ranked by test RMSE, dict of the fitted results by name)
    """
    if not variants:
        raise ValueError("no variants to try")

    rows, fits = [], {}
    for name, cols in variants.items():
        missing = [c for c in cols if c not in train.columns]
        if missing:
            raise KeyError(f"variant {name!r} wants missing columns {missing}")

        fit = fit_ols(train[cols].to_numpy(), train[target].to_numpy(), cols)
        pred_test = predict_ols(fit["beta"], test[cols].to_numpy())

        tr_scores = evaluate(train[target], fit["fitted"])
        te_scores = evaluate(test[target], pred_test)
        dw = durbin_watson(fit["residuals"])

        rows.append({"variant": name, "n_features": len(cols),
                     "train_r2": tr_scores["r2"], "test_r2": te_scores["r2"],
                     "train_rmse": tr_scores["rmse"], "test_rmse": te_scores["rmse"],
                     "test_mae": te_scores["mae"],
                     "overfit_gap": tr_scores["r2"] - te_scores["r2"],
                     "durbin_watson": dw})
        fits[name] = {"fit": fit, "pred_test": pred_test, "columns": list(cols)}

    table = (pd.DataFrame(rows).set_index("variant")
             .sort_values("test_rmse").round(4))
    return table, fits
