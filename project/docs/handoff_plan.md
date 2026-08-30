# Handoff plan

**Stage 14.** What an on-call operator needs to run, check and repair the Portfolio Drift
Monitor without me. Companion to `docs/monitoring_plan.md`, which defines the thresholds
referenced below.

## Deployment path

- **Get it running.** Clone, `conda create -n bootcamp_env python=3.10`, `pip install -r
  project/requirements.txt`, `cp project/.env.example project/.env`. Then run
  `notebooks/project_pipeline.ipynb` top to bottom **before** starting the API: `data/processed/`
  is derived and not committed, so on a fresh clone there is nothing for `app.py` to serve.
  Full sequence in `project/README.md`, "Running this project from a fresh clone".

- **Start the service.** `cd project && python app.py`. It binds **127.0.0.1:5001**, not 5000,
  because macOS AirPlay Receiver holds 5000 and requests to it return 403 that look like an
  application fault. `PORT=5002 python app.py` moves it.

- **Confirm it is alive and current.** `curl http://127.0.0.1:5001/health`. Check
  **`prices_through`** and **`fitted_on.end`** in the response before trusting any number:
  `get_bundle` prefers the saved `model/model.pkl` to refitting, so a stale pickle will serve
  confident forecasts against fresh prices without complaining. This is the single most likely
  way to be wrong while everything appears healthy.

- **Know what is deployed.** This is a **development server**: single-threaded `app.run`, no
  authentication, no TLS, one process. It is correct for one analyst on one machine and must
  not face a network without a production WSGI server and an auth layer in front.

- **Refresh cadence.** Monthly, matching the 21-trading-day horizon. Re-run the pipeline, then
  restart `app.py` so it picks up the new bundle. A running process holds the old model in
  memory: **rewriting `model/model.pkl` alone changes nothing until the process restarts.**

## Runbook, by symptom

- **`/health` shows `prices_through` more than 4 calendar days old.** The pipeline did not run
  or yfinance failed. Re-run `notebooks/project_pipeline.ipynb`. If the vendor is down, publish
  nothing: a stale `drift_monitor_current.csv` is worse than an absent one, because its `as_of`
  column is the only thing distinguishing them and Dana reads the numbers first.

- **`app.py` fails at startup with `FileNotFoundError`.** No cleaned prices exist. The error
  names the notebook to run. This is the expected fresh-clone state, not a fault.

- **`/plot` is slow or times out while JSON routes are fine.** Expected ordering of failure:
  `/plot` renders matplotlib per request at a measured p95 of 225ms against 3 to 18ms for the
  JSON routes, so it degrades first under load. Restart before investigating anything deeper.

- **A fund's forecast looks wrong but the API is healthy.** Check `close_was_filled` and the
  per-ticker row counts (`251 / 251 / 251` when correct). A forward-filled close or an
  unbalanced panel corrupts the features silently; neither raises.

- **A flag fires.** No flag has ever fired: the widest drift in the observed year was 2.23pp
  against a 3pp amber line, so **the alert path is untested in production.** Treat the first
  one as a possible bug in the alerting before treating it as a portfolio event, and verify by
  hand against `GET /predict/<ticker>`.

- **Rolling MAE breaches 0.2121pp.** Compare against persistence *before* refitting. Below 0%
  improvement the model is worse than assuming today's drift holds, and should be pulled rather
  than retrained.

- **Roll back.** `git checkout <sha> -- project/model/model.pkl`, then restart `app.py`. The
  bundle carries `fitted_at`, `data_start` and `data_end`, so `/health` always identifies which
  version is in service. The principal approves rollbacks; the analyst performs them.

## Where things live

| Need | Location |
|---|---|
| Thresholds and owners | `docs/monitoring_plan.md` |
| Why each modelling choice was made | `reports/decision_log.json`, `docs/*.md` per stage |
| What the principal was told | `reports/final_report.md` |
| What Dana reads | `reports/drift_monitor_current.csv`, or `GET /monitor.csv` |
| Request and error log | `project/server.log` (gitignored, local to each run) |
| Issue tracker | GitHub issues on `anna-cui/bootcamp_Anna_Cui`, labelled by layer |

## Two things a successor must not undo

- **The published interval is a prediction interval, not a confidence interval.** It is 11
  times wider, and it is the correct one because Dana reads one fund on one day. Stage 11
  establishes this; Stage 12 acts on it.
- **The per-fund bias is not fixable by adding interactions.** `abs_drift_rel` is `abs_drift`
  divided by the target weight, so the interaction already exists and the design matrix goes
  singular. The bias is regime drift, not misspecification. Stage 12 documents the attempt so
  it does not have to be repeated.
