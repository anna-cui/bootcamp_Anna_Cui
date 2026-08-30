"""The analysis as something another program can call - Stage 13.

Stages 06 to 12 built the monitor as a sequence of notebook cells. A notebook is a fine
place to *decide* things and a bad place to *serve* them: it cannot be called, it re-runs
work that has not changed, and the reasoning is interleaved with the computation so
neither can be reused without the other. This module is the same analysis with the
decisions taken out and the computation left behind.

**The equivalence requirement drives the design.** The project instructions say to keep
the original cells and check that the extracted functions reproduce them. So every
function here is written to match the notebook exactly rather than to improve on it, and
`notebooks/productization.ipynb` asserts the match to machine precision. A refactor that
quietly changes a number is worse than no refactor, because the change enters the app
where nobody is watching for it.

**What the pickle has to carry, and why it is not just the coefficients.** Stage 11
established that the monitor publishes a *prediction interval*, and Stage 12 that the
interval is the part Dana actually needs. A prediction interval is built from the
distribution of the test residuals, so a saved model containing only `beta` can produce a
point forecast and nothing else. The bundle therefore carries the residuals, the feature
names, the split date and the fit metadata alongside the coefficients. A pickle that
cannot reproduce the published number is not a saved model, it is half of one.

**`get_bundle` prefers the saved model over refitting**, which is what the instructions
ask for. That is a real decision with a real risk: a stale pickle against fresh prices
gives a forecast that looks current and is not. So the bundle records the date range it
was fitted on, `describe_bundle` prints it, and the API returns it on `/health`. The
staleness is made visible rather than prevented, because refusing to serve a stale model
would take the monitor down exactly when someone needs a number.

Nothing here modifies its input, matching every other module in `src/`.
"""

import io
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from . import evaluation as ev
from . import features as fe
from . import modeling as md
from . import reporting as rp
from .utils import AMBER_PP, RED_PP, TARGET_WEIGHTS

MODEL_PATH = Path("model/model.pkl")

# The Stage 12 specification. Five features, six parameters. Stage 10a's variant sweep
# chose it and Stage 12's bias work confirmed it: MAE 0.176 against the 11-parameter
# model's 0.192, on a target carrying about 24 independent observations.
SERVICE_FEATURES = ["abs_drift", "abs_drift_rel", "drift_chg_1", "drift_chg_5",
                    "drift_slope_21"]
HORIZON = 21
BUNDLE_VERSION = 1


# --- building and persisting the model ------------------------------------

def build_matrix(prices, target_weights=None, horizon=HORIZON):
    """Prices to the modelling frame, exactly as the pipeline does it."""
    weights = target_weights or TARGET_WEIGHTS
    frame = prices.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    return fe.build_feature_matrix(frame, weights, prices_raw=frame, horizon=horizon)


def build_bundle(prices, target_weights=None, horizon=HORIZON, test_frac=0.2,
                 features=None):
    """Fit the published model and return everything needed to serve it.

    The ordering (`sort_values(['date', 'ticker'])`, `reset_index(drop=True)`) is copied
    from the notebook rather than tidied, because `chronological_split` cuts on dates and
    the residual vector is positional. A different sort gives a different residual order,
    which gives different bootstrap blocks, which gives a different interval.
    """
    weights = target_weights or TARGET_WEIGHTS
    feats = list(features or SERVICE_FEATURES)
    target = f"y_absdrift_fwd_{horizon}"

    matrix = build_matrix(prices, weights, horizon)
    data = (matrix[["date", "ticker"] + fe.MODEL_FEATURES + [target]]
            .dropna().sort_values(["date", "ticker"]).reset_index(drop=True))
    train, test, cut = md.chronological_split(data, test_frac=test_frac)

    fit = md.fit_ols(train[feats].to_numpy(), train[target].to_numpy(), feats)
    resid = test[target].to_numpy() - md.predict_ols(fit["beta"], test[feats].to_numpy())

    per_fund_bias = {t: float(resid[(test["ticker"] == t).to_numpy()].mean())
                     for t in sorted(test["ticker"].unique())}

    return {
        "version": BUNDLE_VERSION,
        "beta": fit["beta"],
        "features": feats,
        "target": target,
        "horizon": horizon,
        "target_weights": dict(weights),
        # Residuals are not diagnostics here, they are an input. The published
        # prediction interval is built from their percentiles.
        "residuals": resid,
        "test_dates": test["date"].to_numpy(),
        "test_tickers": test["ticker"].to_numpy(),
        "per_fund_bias": per_fund_bias,
        "cut_date": pd.Timestamp(cut),
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "n_test_dates": int(test["date"].nunique()),
        "data_start": pd.Timestamp(data["date"].min()),
        "data_end": pd.Timestamp(data["date"].max()),
        "mae": float(ev.mae(resid)),
        "rmse": float(ev.rmse(resid)),
        "bias": float(ev.bias(resid)),
        "fitted_at": datetime.now().isoformat(timespec="seconds"),
    }


def save_bundle(bundle, path=MODEL_PATH, overwrite=True):
    """Write the bundle to disk, creating the directory first.

    `joblib` will not create a missing directory and fails with `FileNotFoundError`,
    which is the trap the homework sheet calls out. `overwrite=False` is offered
    because the instructions ask for the option, not because refusing is usually right.
    """
    p = Path(path)
    if p.exists() and not overwrite:
        raise FileExistsError(f"{p} exists and overwrite=False")
    p.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, p)
    return p


def load_bundle(path=MODEL_PATH):
    """Read a bundle back, refusing one written by a different layout."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"no saved model at {p}. Run build_bundle then save_bundle.")
    bundle = joblib.load(p)
    if bundle.get("version") != BUNDLE_VERSION:
        raise ValueError(
            f"{p} was written by bundle version {bundle.get('version')}, this code "
            f"expects {BUNDLE_VERSION}. Refit rather than trusting the mismatch.")
    return bundle


def get_bundle(prices=None, path=MODEL_PATH, refit=False, **kwargs):
    """Use the saved model if there is one, otherwise fit and save. Returns (bundle, source).

    This is the "use a saved model, if it exists, rather than running it anew" option
    from the instructions. `refit=True` forces a fresh fit and overwrites, which is what
    the pipeline does after pulling new prices.
    """
    p = Path(path)
    if not refit and p.exists():
        return load_bundle(p), "loaded"
    if prices is None:
        raise ValueError("no saved model and no prices given, so nothing can be fitted")
    bundle = build_bundle(prices, **kwargs)
    save_bundle(bundle, p)
    return bundle, "fitted"


def describe_bundle(bundle):
    """One-line provenance, so a stale model is visible rather than silent."""
    return (f"{len(bundle['features'])} features, {len(bundle['beta'])} parameters | "
            f"fitted {bundle['fitted_at']} on "
            f"{bundle['data_start'].date()} to {bundle['data_end'].date()} | "
            f"cut {bundle['cut_date'].date()} | "
            f"MAE {bundle['mae']:.4f}pp")


# --- serving --------------------------------------------------------------

def predict_rows(bundle, rows):
    """Predict for one or more feature rows, in the bundle's own feature order."""
    X = np.atleast_2d(np.asarray(rows, dtype=float))
    if X.shape[1] != len(bundle["features"]):
        raise ValueError(f"expected {len(bundle['features'])} features "
                         f"({', '.join(bundle['features'])}), got {X.shape[1]}")
    return md.predict_ols(bundle["beta"], X)


def latest_rows(matrix, features=None):
    """The most recent complete observation per fund, ready to predict from."""
    feats = list(features or SERVICE_FEATURES)
    latest = (matrix.dropna(subset=feats).sort_values("date")
              .groupby("ticker").tail(1).sort_values("ticker"))
    return latest


def forecast(bundle, matrix, level=0.95):
    """Point forecast plus prediction interval for each fund's latest observation.

    The interval comes from the residual percentiles carried in the bundle, which is
    why the bundle carries them. This is the number the monitor publishes.
    """
    latest = latest_rows(matrix, bundle["features"])
    point = predict_rows(bundle, latest[bundle["features"]].to_numpy())
    out = ev.prediction_interval(point, bundle["residuals"], level=level)
    out.insert(0, "ticker", latest["ticker"].to_numpy())
    out["as_of"] = latest["date"].to_numpy()
    return out


def monitor(bundle, matrix, amber=AMBER_PP, red=RED_PP, level=0.95):
    """The stakeholder table: one row per fund, bands, and an action.

    `amber` and `red` are arguments rather than constants so the API can expose them.
    Stage 07 left the threshold open and Stage 12 closed the *unit* question but not the
    *level* one, so letting the principal ask "what would 2pp look like" is the one place
    a caller should be able to change the analysis.
    """
    fc = forecast(bundle, matrix, level=level)
    latest = latest_rows(matrix, bundle["features"])
    return rp.monitor_table(fc, latest["abs_drift"].to_numpy(), fc["ticker"].to_numpy(),
                            per_fund_bias=bundle["per_fund_bias"], amber=amber, red=red)


def plot_forecast_png(bundle, matrix, amber=AMBER_PP, level=0.95, dpi=110):
    """The Stage 12 chart as PNG bytes, for the API's /plot route.

    Returns bytes rather than writing a file or calling `plt.show`, so the same function
    serves an HTTP response, a notebook and a report without three variants of it.
    Uses the Agg backend and closes the figure, because a long-running server that leaks
    figures runs out of memory eventually.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"VTI": "#1f4e79", "VXUS": "#c77b30", "BND": "#4a7c59"}
    hist = matrix[["date", "ticker", "abs_drift"]].dropna()
    fc = forecast(bundle, matrix, level=level)
    last = hist["date"].max()
    ahead = last + pd.Timedelta(days=int(bundle["horizon"] * 7 / 5))

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ymax = max(amber + 0.4, float(fc["hi"].max()) + 0.6)
    ax.set_ylim(0, ymax)
    ax.set_xlim(hist["date"].min(), ahead + pd.Timedelta(days=10))
    ax.axhspan(amber, ymax, color="#f0ad4e", alpha=0.16)
    ax.axhline(amber, color="#f0ad4e", lw=1.2, ls="--")
    ax.text(ahead, amber + 0.09, "amber: review with principal  ", color="#a06a12",
            fontsize=9, va="bottom", ha="right")

    for t in rp.DISPLAY_ORDER:
        s = hist[hist["ticker"] == t]
        if s.empty:
            continue
        ax.plot(s["date"], s["abs_drift"], color=colors.get(t, "#555555"), lw=1.5, label=t)
        row = fc[fc["ticker"] == t].iloc[0]
        ax.plot([last, ahead], [s["abs_drift"].iloc[-1], row["point"]],
                color=colors.get(t, "#555555"), lw=1.2, ls=":")
        ax.vlines(ahead, row["lo"], row["hi"], color=colors.get(t, "#555555"),
                  lw=6, alpha=0.35)
        ax.plot(ahead, row["point"], "o", color=colors.get(t, "#555555"), ms=7,
                markeredgecolor="white", markeredgewidth=1.2)

    ax.axvline(last, color="grey", lw=0.9, ls="--")
    ax.set_title(f"Portfolio drift and the {bundle['horizon']}-day projection\n"
                 f"bars are {int(level * 100)}% prediction intervals, "
                 f"amber at {amber:.1f}pp", loc="left")
    ax.set_ylabel("absolute drift from target (percentage points)")
    ax.legend(title="fund", loc="upper left", frameon=True)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def run_full_analysis(prices=None, matrix=None, bundle=None, amber=AMBER_PP,
                      red=RED_PP, level=0.95, path=MODEL_PATH, refit=False):
    """The whole chain in one call, returning what a caller needs and nothing else.

    Accepts a prebuilt `matrix` or `bundle` so the API can serve repeated requests
    without redoing the feature build, and falls back to constructing them when called
    cold. This is the function `/run_full_analysis` wraps.
    """
    if bundle is None:
        bundle, source = get_bundle(prices, path=path, refit=refit)
    else:
        source = "provided"
    if matrix is None:
        if prices is None:
            raise ValueError("need prices or a prebuilt matrix")
        matrix = build_matrix(prices, bundle["target_weights"], bundle["horizon"])

    table = monitor(bundle, matrix, amber=amber, red=red, level=level)
    worst = float(table["upper_95_pp"].max())
    return {
        "model_source": source,
        "model": describe_bundle(bundle),
        "as_of": str(pd.Timestamp(matrix["date"].max()).date()),
        "thresholds": {"amber_pp": float(amber), "red_pp": float(red)},
        "level": float(level),
        "monitor": table,
        "worst_case_pp": worst,
        "any_action_needed": bool((table["worst_case_band"] != "green").any()),
        "headline": (
            f"No fund needs attention: the widest {int(level * 100)}% upper bound is "
            f"{worst:.2f}pp against an amber line of {amber:.1f}pp."
            if not bool((table["worst_case_band"] != "green").any()) else
            f"Review needed: {', '.join(table.loc[table['worst_case_band'] != 'green', 'fund'])} "
            f"can reach {worst:.2f}pp against an amber line of {amber:.1f}pp."),
    }
