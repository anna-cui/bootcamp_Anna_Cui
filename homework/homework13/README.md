# Stage 13 Homework - Prediction API

A `LinearRegression` fitted on a two-feature synthetic dataset
(`make_regression(n_samples=100, n_features=2, noise=0.1, random_state=42)`), saved to
`model/model.pkl` with joblib. This app loads that file once at startup and serves
predictions from it over HTTP, so a program other than the notebook can use the model.

## Running it

    python app.py

The server starts on **http://127.0.0.1:5001** and loads `model/model.pkl` at startup.

**Why 5001 and not 5000.** macOS runs AirPlay Receiver on port 5000 from Monterey onward.
Flask either fails to bind or requests reach AirPlay and return 403, which looks like a
broken app. Override with `PORT=5002 python app.py` if 5001 is also busy.

## POST /predict

    curl -X POST http://127.0.0.1:5001/predict \
         -H "Content-Type: application/json" \
         -d '{"features": [0.1, 0.2]}'

Response:

    {"features":[0.1,0.2],"prediction":23.58961171297328}

## GET /predict/<f1>/<f2>

    curl http://127.0.0.1:5001/predict/0.1/0.2

Response:

    {"features":[0.1,0.2],"prediction":23.58961171297328}

Both routes use the same loaded model and return the same JSON shape, so a caller can
choose whichever suits it: a program posting JSON, or a person with a browser.

## Bad input

Every failure returns **HTTP 400** and a JSON body with an `error` key. Never a traceback,
and never HTML.

    curl http://127.0.0.1:5001/predict/abc/0.2

Response:

    {"error":"feature 0 is not a number: 'abc'"}

| What you send | What comes back |
|---|---|
| `POST` with no `features` key | 400, `missing 'features'...` |
| `POST` with the wrong number of features | 400, `expected exactly 2 features, got N` |
| `POST` with a non-number in the list | 400, `feature i is not a number` |
| `GET /predict/abc/0.2` | 400, `feature 0 is not a number: 'abc'` |
| any unknown URL | 404 JSON listing the real routes |

The path parameters are declared as strings and converted by hand. Using Flask's
`<float:f1>` converter instead would make `/predict/abc/0.2` fail to match the route at
all, returning a **404 HTML page** rather than the JSON 400 required here.

## Extra routes

| Route | Method | Returns |
|---|---|---|
| `/health` | GET | `{"status": "ok", "n_features": 2}`. Used by the notebook to wait for startup |
| `/retrain` | POST | Refits on a new `random_state`, overwrites `model/model.pkl`, and swaps the model into the **running** process. Reports the prediction before and after |
| `/plot` | GET | A PNG of the model response curve. `image/png`, so do not call `.json()` on it |

`/retrain` rebinds the module-level `model` with `global`. Rewriting the pickle alone would
change nothing until the process restarted.

## Logging

Every request is appended to `api.log` with its input and its prediction, including the
rejected ones and why they were rejected.

## Files

    homework13_productization_submission.ipynb   this notebook
    app.py                                       the API, written by section 3
    model/model.pkl                              the saved model
    api.log                                      request log
    reports/plot_route.png                       the /plot output, saved for the record
    README.md                                    this file
