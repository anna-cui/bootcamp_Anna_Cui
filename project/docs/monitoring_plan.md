# Monitoring plan

**Stage 14.** Model under monitoring: the Stage 13 six-parameter drift regression served by
`app.py`, forecasting absolute drift 21 trading days ahead. Companion:
`docs/handoff_plan.md`.

*Length: the prose below is 279 words, inside the 200-300 word brief. The two tables are
reference material for the on-call operator and are not counted.*

## The constraint that shapes everything below

The target is 21 trading days ahead, so **a forecast cannot be scored for 29 calendar
days**: the monitor cannot tell me the model broke today, only that it was broken a month
ago. Worse, `effective_sample_size` says a 21-day window over three funds carries **3
independent observations, not 63**. A monthly rolling MAE is therefore not a measurement,
and any threshold on one would fire on noise.

So model quality is monitored on a **63-day window (9 effective observations)**, and the
fast layers do the real work. Data and system checks run daily and catch the failures that
happen quickly; model checks run quarterly and catch the failures that happen slowly. The
business layer is checked monthly by a person, because no metric on this project has ever
fired.

## Failure modes, metrics, thresholds

| # | Layer | Failure mode | Metric | Threshold (current value) | First runbook step |
|---|---|---|---|---|---|
| 1 | **Data** | Vendor gap or a stale pull; the monitor silently serves last month's prices | `data_end` age from `/health` | **> 4 calendar days** (largest observed gap between trading days is exactly 4) | Re-run `project_pipeline.ipynb`; if yfinance is down, publish nothing rather than a stale CSV |
| 2 | **Data** | Forward-filled closes contaminate the features | `close_was_filled` sum over the window | **> 0** (currently **0**, so never yet exercised) | Identify the fund and dates; if more than 3 in 21 days, suppress that fund's forecast |
| 3 | **Data** | A ticker drops out and `drop_incomplete_days` silently shortens the panel | Row count per ticker | **not equal across all three** (currently **251 / 251 / 251**, exactly) | Check the vendor symbol; do not refit on an unbalanced panel |
| 4 | **Model** | Regime change, the dominant risk: Stage 12 measured it at **0.31pp**, three times the model specification | 21-day realized volatility against the training band | outside **p10-p90**: VTI 9.6-17.4, VXUS 10.4-24.2, BND 2.7-4.6 (latest 10.8 / 11.2 / 4.1) | Refit; widen the published interval; tell the principal the interval is now a floor |
| 5 | **Model** | Accuracy decays | 63-day rolling MAE | **> 0.2121pp**, the upper bound of the block-bootstrap CI [0.1437, 0.2121] on the current 0.1759 | Compare against persistence before refitting: below **0%** improvement the model is worse than doing nothing and must be pulled |
| 6 | **Model** | Per-fund bias drifts past the offsets published in Stage 12 | 63-day mean residual per fund | outside its interval: BND [0.058, 0.245], VTI [0.045, 0.177], VXUS [-0.185, 0.131] | Re-measure the offset; do not add interactions, Stage 12 showed the design matrix is singular |
| 7 | **System** | The API degrades or dies | p95 latency, non-2xx rate | JSON routes **> 100ms** (measured p95: `/health` 3.0, `/predict` 3.5, `/monitor.csv` 15.8, `/run_full_analysis` 17.9); `/plot` **> 1000ms** (measured 225); errors **> 1%** | Restart; check `server.log`. `/plot` renders matplotlib per request and is 50x the JSON routes, so it degrades first |
| 8 | **Business** | The monitor is ignored, or cries wolf | Flags raised per month; unactioned flags; days of warning before a 3pp crossing | **any** flag is an event (currently **0**; the year's widest drift was 2.23pp, so the alert path is **untested**); target **>= 10 trading days** of warning; unactioned flags **> 50%** means the threshold is wrong | Review with the principal. A flag nobody acts on is a threshold problem, not a model problem |

## Retraining

**Monthly, aligned to the 21-day horizon.** Retraining more often is meaningless: each
forecast takes 29 calendar days to become scoreable, so a fortnightly refit would be
judged on evidence that does not exist yet.

Out-of-cycle triggers: any of rows 4, 5 or 6 above.

## Ownership

| Role | Owner | Responsibility |
|---|---|---|
| Analyst | Anna Cui | Runs the monthly refit, updates the dashboard, first responder for rows 1-7 |
| Decision owner | Firm principal | Approves threshold changes, retraining out of cycle, and any rollback. Sole owner of row 8 |
| End user | Dana | Uses `drift_monitor_current.csv`; reports a stale `as_of` date to the analyst |

**Alerts** go to the analyst for rows 1-7 and to the principal for row 8, since only the
principal can act on a threshold being wrong. **Issues are logged as GitHub issues** on
`anna-cui/bootcamp_Anna_Cui`, labelled by layer, so the runbook and the history live
beside the code.

**Rollback** is `git checkout` of the previous `model/model.pkl` plus a pipeline re-run;
the bundle records `fitted_at` and its data window, so the version in service is always
identifiable from `/health`.

