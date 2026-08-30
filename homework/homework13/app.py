"""Stage 13 homework - a two-route prediction API over a saved model."""

import io
import logging
import os

import joblib
import matplotlib
matplotlib.use('Agg')          # no display on a server process
import matplotlib.pyplot as plt
import numpy as np
from flask import Flask, Response, jsonify, request

MODEL_PATH = 'model/model.pkl'
N_FEATURES = 2

# Loaded ONCE, at import time. Flask imports this module once per process, so this
# runs once however many requests arrive. Inside a route it would re-read the file
# from disk on every call.
model = joblib.load(MODEL_PATH)

app = Flask(__name__)

logging.basicConfig(
    filename='api.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)


def _predict(values):
    """One prediction path shared by both routes, so they cannot disagree."""
    return float(model.predict([values])[0])


def _coerce(raw):
    """Return (values, error). Never raises - the caller turns error into a 400."""
    if raw is None:
        return None, "missing 'features': send {'features': [f1, f2]}"
    if not isinstance(raw, (list, tuple)):
        return None, f"'features' must be a list of {N_FEATURES} numbers, got {type(raw).__name__}"
    if len(raw) != N_FEATURES:
        return None, f"expected exactly {N_FEATURES} features, got {len(raw)}"
    values = []
    for i, v in enumerate(raw):
        if isinstance(v, bool):      # bool is an int subclass; reject it explicitly
            return None, f"feature {i} is a boolean, expected a number"
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            return None, f"feature {i} is not a number: {v!r}"
    return values, None


@app.route('/health', methods=['GET'])
def health():
    """Cheap readiness probe. The notebook polls this to know the server is up."""
    return jsonify({'status': 'ok', 'n_features': N_FEATURES})


@app.route('/predict', methods=['POST'])
def predict_post():
    data = request.get_json(silent=True) or {}
    values, error = _coerce(data.get('features'))
    if error:
        app.logger.info('POST /predict rejected: %s', error)
        return jsonify({'error': error}), 400
    prediction = _predict(values)
    app.logger.info('POST /predict features=%s prediction=%.6f', values, prediction)
    return jsonify({'prediction': prediction, 'features': values})


@app.route('/predict/<f1>/<f2>', methods=['GET'])
def predict_get(f1, f2):
    # Declared as strings on purpose. With <float:f1> a request to /predict/abc/0.2
    # would not match this route at all and Flask would return a 404 HTML page,
    # where the requirement is a JSON 400.
    values, error = _coerce([f1, f2])
    if error:
        app.logger.info('GET /predict rejected: %s', error)
        return jsonify({'error': error}), 400
    prediction = _predict(values)
    app.logger.info('GET /predict features=%s prediction=%.6f', values, prediction)
    return jsonify({'prediction': prediction, 'features': values})


@app.route('/retrain', methods=['POST'])
def retrain():
    """Stretch: refit, overwrite the pickle, and swap the model in the LIVE process.

    The `global` is the whole point. Rewriting the file alone would change nothing
    for a running server, because the old object stays bound in memory until the
    process restarts.
    """
    global model
    from sklearn.datasets import make_regression
    from sklearn.linear_model import LinearRegression

    payload = request.get_json(silent=True) or {}
    seed = payload.get('random_state', 7)
    try:
        seed = int(seed)
    except (TypeError, ValueError):
        return jsonify({'error': f'random_state must be an integer, got {seed!r}'}), 400

    before = _predict([0.1, 0.2])
    X, y = make_regression(n_samples=100, n_features=N_FEATURES, noise=0.1,
                           random_state=seed)
    refitted = LinearRegression().fit(X, y)
    joblib.dump(refitted, MODEL_PATH)
    model = refitted
    after = _predict([0.1, 0.2])

    app.logger.info('POST /retrain seed=%s before=%.6f after=%.6f', seed, before, after)
    return jsonify({'retrained': True, 'random_state': seed,
                    'prediction_before': before, 'prediction_after': after,
                    'changed': before != after})


@app.route('/plot', methods=['GET'])
def plot():
    """Stretch: a PNG, not JSON. Returns image/png so a browser renders it."""
    grid = np.linspace(-2, 2, 60)
    preds = [_predict([g, 0.0]) for g in grid]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(grid, preds, color='#1f4e79', lw=2)
    ax.axhline(0, color='grey', lw=0.8)
    ax.set_title('Model response to feature 1, with feature 2 held at 0', loc='left')
    ax.set_xlabel('feature 1')
    ax.set_ylabel('prediction')
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=110)
    plt.close(fig)                 # a server process must not leak figures
    buf.seek(0)
    app.logger.info('GET /plot rendered %d bytes', buf.getbuffer().nbytes)
    return Response(buf.getvalue(), mimetype='image/png')


@app.errorhandler(404)
def not_found(_):
    """Even an unknown URL answers in JSON, so a caller never has to parse HTML."""
    return jsonify({'error': 'no such route',
                    'routes': ['POST /predict', 'GET /predict/<f1>/<f2>',
                               'POST /retrain', 'GET /plot', 'GET /health']}), 404


if __name__ == '__main__':
    # Port from the environment, defaulting to 5001. NOT 5000: macOS AirPlay
    # Receiver binds 5000, and requests reach AirPlay instead of Flask.
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', 5001)), debug=False)
