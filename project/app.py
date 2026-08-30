"""Portfolio Drift Monitor - HTTP API. Stage 13.

Run from the `project/` directory:

    python app.py

Serves on http://127.0.0.1:5001. Not 5000: macOS runs AirPlay Receiver there, so Flask
either fails to bind or requests reach AirPlay and come back 403. Override with
`PORT=5002 python app.py`.

Everything expensive is loaded once at import time: the prices, the feature matrix and
the model bundle. Flask imports this module once per process, so a route handler does no
setup work. Rebuilding the feature matrix per request would take seconds and would give
every caller a different answer as the rolling window moved underneath them.
"""

import os
import sys
from pathlib import Path

import pandas as pd
from flask import Flask, Response, jsonify, request

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import service as sv
from src.utils import AMBER_PP, RED_PP, read_df

PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
REPORTS = ROOT / "reports"


def _load_prices():
    """Newest cleaned parquet, falling back to the newest raw pull."""
    clean = sorted(PROC.glob("prices_clean_*.parquet"))
    if clean:
        return read_df(clean[-1]), clean[-1].name
    raw = sorted(RAW.glob("api_yfinance_*.csv"))
    if not raw:
        raise FileNotFoundError(
            "no price data. Run notebooks/project_pipeline.ipynb once to create "
            "data/processed/prices_clean_*.parquet.")
    return pd.read_csv(raw[-1]), raw[-1].name


# --- loaded ONCE, at import time ------------------------------------------
PRICES, PRICE_SOURCE = _load_prices()
BUNDLE, MODEL_SOURCE = sv.get_bundle(PRICES, path=ROOT / sv.MODEL_PATH)
MATRIX = sv.build_matrix(PRICES, BUNDLE["target_weights"], BUNDLE["horizon"])
TICKERS = sorted(BUNDLE["target_weights"])

app = Flask(__name__)

ROUTES = [
    "GET  /health",
    "POST /predict            {'features': [abs_drift, abs_drift_rel, drift_chg_1, drift_chg_5, drift_slope_21]}",
    "GET  /predict/<ticker>",
    "GET  /run_full_analysis",
    "GET  /run_full_analysis/<amber>/<red>",
    "GET  /plot",
    "GET  /monitor.csv",
]


def _number(raw, name, low=None, high=None):
    """Return (value, error). Path parameters arrive as strings and must be validated
    here rather than by a `<float:...>` converter, which would 404 on bad input instead
    of returning the JSON 400 a caller can act on."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None, f"{name} must be a number, got {raw!r}"
    if low is not None and v < low:
        return None, f"{name} must be at least {low}, got {v}"
    if high is not None and v > high:
        return None, f"{name} must be at most {high}, got {v}"
    return v, None


@app.route("/health", methods=["GET"])
def health():
    """Readiness plus provenance.

    The date range matters as much as the status. `get_bundle` prefers a saved model
    over refitting, so a pickle from last month will happily serve confident forecasts
    against this month's prices. Returning the fitted window makes that visible to the
    caller instead of hiding it.
    """
    return jsonify({
        "status": "ok",
        "model_source": MODEL_SOURCE,
        "model": sv.describe_bundle(BUNDLE),
        "features": BUNDLE["features"],
        "horizon_trading_days": BUNDLE["horizon"],
        "fitted_on": {"start": str(BUNDLE["data_start"].date()),
                      "end": str(BUNDLE["data_end"].date()),
                      "cut": str(BUNDLE["cut_date"].date())},
        "prices_through": str(pd.Timestamp(MATRIX["date"].max()).date()),
        "price_source": PRICE_SOURCE,
        "tickers": TICKERS,
        "routes": ROUTES,
    })


@app.route("/predict", methods=["POST"])
def predict_post():
    """Predict from a caller-supplied feature row."""
    payload = request.get_json(silent=True) or {}
    raw = payload.get("features")
    n = len(BUNDLE["features"])

    if raw is None:
        return jsonify({"error": f"missing 'features': send a list of {n} numbers",
                        "expected": BUNDLE["features"]}), 400
    if not isinstance(raw, (list, tuple)):
        return jsonify({"error": f"'features' must be a list, got {type(raw).__name__}",
                        "expected": BUNDLE["features"]}), 400
    if len(raw) != n:
        return jsonify({"error": f"expected exactly {n} features, got {len(raw)}",
                        "expected": BUNDLE["features"]}), 400

    values = []
    for i, v in enumerate(raw):
        if isinstance(v, bool):
            return jsonify({"error": f"feature {i} ({BUNDLE['features'][i]}) is a "
                                     f"boolean, expected a number"}), 400
        val, err = _number(v, f"feature {i} ({BUNDLE['features'][i]})")
        if err:
            return jsonify({"error": err, "expected": BUNDLE["features"]}), 400
        values.append(val)

    point = float(sv.predict_rows(BUNDLE, values)[0])
    band = sv.ev.empirical_intervals(BUNDLE["residuals"], 0.95)
    lo, hi = band["lo"], band["hi"]
    return jsonify({
        "prediction_pp": point,
        "interval_95_pp": [point + lo, point + hi],
        "band": sv.rp.traffic_light(point),
        "features": dict(zip(BUNDLE["features"], values)),
        "horizon_trading_days": BUNDLE["horizon"],
    })


@app.route("/predict/<ticker>", methods=["GET"])
def predict_ticker(ticker):
    """Projected drift for one fund, from its most recent observation.

    The path parameter is a ticker rather than raw feature values because that is the
    question a person actually has. Asking Dana to supply five engineered features over
    a URL would be an API that only its author can use.
    """
    name = ticker.upper()
    if name not in TICKERS:
        return jsonify({"error": f"unknown fund {ticker!r}",
                        "known": TICKERS}), 400

    table = sv.monitor(BUNDLE, MATRIX)
    row = table.loc[table["fund"] == name]
    if row.empty:
        return jsonify({"error": f"no current observation for {name}"}), 404
    r = row.iloc[0]
    return jsonify({
        "fund": name,
        "as_of": str(pd.Timestamp(MATRIX["date"].max()).date()),
        "drift_today_pp": float(r["drift_today_pp"]),
        "projected_pp": float(r["projected_21d_pp"]),
        "interval_95_pp": [float(r["lower_95_pp"]), float(r["upper_95_pp"])],
        "projected_adjusted_pp": float(r["projected_adjusted_pp"]),
        "band": str(r["band_projected"]),
        "worst_case_band": str(r["worst_case_band"]),
        "action": str(r["action"]),
    })


@app.route("/run_full_analysis", methods=["GET"])
@app.route("/run_full_analysis/<amber>/<red>", methods=["GET"])
def run_full_analysis(amber=None, red=None):
    """The whole monitor, optionally against caller-supplied thresholds.

    The thresholds are the one input a caller should be able to change. Stage 07 set
    3pp and 5pp and left them open; Stage 12 closed the question of the *unit* but not
    of the *level*. "What would this look like at 2pp" is a question the principal can
    now answer without anyone opening a notebook.
    """
    a = AMBER_PP if amber is None else None
    r = RED_PP if red is None else None
    if amber is not None:
        a, err = _number(amber, "amber", low=0.01, high=100)
        if err:
            return jsonify({"error": err}), 400
    if red is not None:
        r, err = _number(red, "red", low=0.01, high=100)
        if err:
            return jsonify({"error": err}), 400
    if r <= a:
        return jsonify({"error": f"red ({r}) must be greater than amber ({a})"}), 400

    result = sv.run_full_analysis(matrix=MATRIX, bundle=BUNDLE, amber=a, red=r)
    result["monitor"] = result["monitor"].to_dict(orient="records")
    return jsonify(result)


@app.route("/plot", methods=["GET"])
def plot():
    """The drift chart as a PNG. `image/png`, so do not call .json() on it.

    Accepts `?amber=` so the band moves with the threshold the caller asked about.
    """
    amber = AMBER_PP
    if "amber" in request.args:
        amber, err = _number(request.args["amber"], "amber", low=0.01, high=100)
        if err:
            return jsonify({"error": err}), 400
    return Response(sv.plot_forecast_png(BUNDLE, MATRIX, amber=amber),
                    mimetype="image/png")


@app.route("/monitor.csv", methods=["GET"])
def monitor_csv():
    """Dana's table over HTTP, as a download.

    The whole Stage 12 delivery argument was that she works in Excel and will not run
    scripts. A URL that returns a CSV is the shortest path from this model to her
    spreadsheet, and it is why this route exists rather than only the JSON one.
    """
    table = sv.monitor(BUNDLE, MATRIX)
    return Response(
        table.to_csv(index=False),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=drift_monitor_current.csv"})


@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "no such route", "routes": ROUTES}), 404


@app.errorhandler(500)
def server_error(_):
    return jsonify({"error": "internal error, see the server log"}), 500


if __name__ == "__main__":
    print(f"prices : {PRICE_SOURCE}")
    print(f"model  : {MODEL_SOURCE} - {sv.describe_bundle(BUNDLE)}")
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5001)), debug=False)
