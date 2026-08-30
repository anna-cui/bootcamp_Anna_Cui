# Productization - turning the analysis into a service

**Stage 13.** Companion to `src/service.py`, `app.py`, `notebooks/productization.ipynb`
and the setup section of `README.md`.

Twelve stages produced an analysis a person runs. This one produces a service another
program calls. The difference is not presentation: a notebook cannot be invoked, it re-runs
work that has not changed, and it interleaves the reasoning with the computation so neither
can be reused without dragging the other along.

Data through **2026-08-28**. Model unchanged from Stage 12: five features, six parameters,
MAE 0.176pp, 25.8% better than persistence.

---

## 1. The three results

1. **The refactor is provably the same analysis**, not a plausible rewrite of it. Every
   published quantity matches the original cells to better than 1e-12, and the check is an
   assertion rather than a printed reassurance.
2. **A pickle of the coefficients would have been a broken deliverable.** The number this
   project publishes is an interval, and an interval needs the residuals.
3. **The one input a caller can change is the threshold**, because it is the one question
   the project deliberately left open.

---

## 2. The refactor, and how it was checked

The project instructions ask for the original cells to be kept and the extracted functions
checked against them. That check is the entire value of the exercise: a refactor that
silently changes a number is worse than no refactor, because the changed number then enters
the app where nobody is looking for it.

`notebooks/productization.ipynb` section 3 compares the two paths:

| quantity | max difference |
|---|---|
| coefficients | 0 |
| test residuals | 0 |
| point forecast | 0 |
| interval lower bound | 0 |
| interval upper bound | 0 |
| MAE, bias | 0 |

Exactly zero, not "close enough", because the notebook feeds `service.py` the same frame in
the same order.

### The one place the two paths genuinely differ

Run inside `project_pipeline.ipynb` the same comparison is *not* bit-exact, and the reason
is worth recording.

**The Stage 10a pipeline section sorts its modelling frame by `(ticker, date)`.
`service.build_bundle` sorts by `(date, ticker)`**, matching `delivery.ipynb`. Both give
the same train and test sets, because `chronological_split` cuts on dates. Every published
quantity agrees to floating-point noise:

| quantity | max difference in the pipeline |
|---|---|
| coefficients | 1.2e-14 |
| point forecast | 6.7e-16 |
| interval bounds | 6.7e-16 and 8.9e-16 |
| MAE, bias | 1.7e-16, 5.6e-17 |
| residual **values**, compared sorted | 4.4e-15 |
| residual **vector**, compared as stored | **0.90** |

The last row is the finding. The residuals are the same 126 numbers in a different order.
Nothing the monitor publishes notices, because a least-squares solve and a percentile are
both order-invariant.

**One thing would notice.** Stage 11's block bootstrap resamples contiguous *dates*, so it
depends on which residual belongs to which date. That is why the bundle carries
`test_dates` and `test_tickers` beside `residuals` rather than the bare array: anything
order-dependent built later has what it needs, instead of silently pairing residuals with
the wrong days.

The pipeline check asserts on the published quantities at 1e-12 and on the sorted
residuals, and prints the ordering difference rather than suppressing it.

---

## 3. What the saved model has to contain

The obvious pickle holds `beta` and stops. That would have been wrong here, and the reason
traces straight back through the project.

Stage 11 established that a confidence interval and a prediction interval answer different
questions and differ by a factor of eleven, and that **Dana reads one fund on one day**, so
the prediction interval is the honest one. Stage 12 made it the published number. A
prediction interval is built from the percentiles of the test residuals.

**So a saved model containing only coefficients can produce a point forecast and cannot
produce the number this project publishes.** It is half a deliverable that looks like a
whole one.

The bundle carries:

| field | why |
|---|---|
| `beta`, `features` | the model, and the order its inputs go in |
| `residuals`, `test_dates`, `test_tickers` | the prediction interval, and anything order-dependent later |
| `per_fund_bias` | Stage 12's measured offsets, published beside the raw forecast |
| `cut_date`, `data_start`, `data_end`, `fitted_at` | provenance, see below |
| `mae`, `rmse`, `bias`, `n_train`, `n_test` | so a caller can judge the model without refitting it |

### The staleness risk, named rather than prevented

`get_bundle` prefers a saved model to refitting, which is the option the instructions ask
for and a real hazard: a pickle from last month against this month's prices returns a
forecast that looks current and is not.

The response is to make it visible. The fitted window is recorded in the bundle, printed by
`describe_bundle`, and returned by the API's `/health`. It is deliberately **not** enforced
by refusing to serve an old model, because a monitor that declines to answer is worse than
one that answers with its date attached, and the person asking can then judge.

---

## 4. The API

`app.py`, seven routes, Flask.

| Route | Method | Returns |
|---|---|---|
| `/health` | GET | Status plus provenance |
| `/predict` | POST | Prediction from a caller-supplied feature row |
| `/predict/<ticker>` | GET | Projected drift for one fund from its latest observation |
| `/run_full_analysis` | GET | The whole monitor as JSON |
| `/run_full_analysis/<amber>/<red>` | GET | The same, against caller-supplied thresholds |
| `/plot` | GET | The drift chart as `image/png`, accepts `?amber=` |
| `/monitor.csv` | GET | Dana's table as a CSV download |

Four decisions in it are worth stating.

**Everything expensive loads once at import time.** Prices, feature matrix and model
bundle. Flask imports the module once per process, so a route handler does no setup.
Rebuilding the feature matrix per request would take seconds and would hand concurrent
callers different answers as the rolling window moved underneath them.

**`/predict/<ticker>` takes a ticker, not five feature values.** The engineered features are
an implementation detail; the question a person has is "how is BND doing". An API that
requires `abs_drift_rel` over a URL is one only its author can use. The POST route is there
for a program that genuinely wants to supply a row.

**Path parameters are strings, converted by hand.** Flask's `<float:...>` converter looks
right and is wrong: `/run_full_analysis/abc/4` would fail to match the route at all and
return a **404 HTML page**, where what a caller needs is a **JSON 400** naming the problem.
Every failure in this app returns the same JSON shape, so a caller never has to branch on
whether it got JSON or HTML.

**`/monitor.csv` exists because of Stage 12's delivery argument.** Dana works in Excel and
will not run scripts. A URL returning a CSV is the shortest path from this model to her
spreadsheet, and it does not require anyone to re-run a notebook first.

---

## 5. The parameter a caller can change, and why it is that one

The instructions ask for a route where "user-provided inputs modify part of the analysis".
Almost anything could be exposed. The threshold is the right choice because it is the one
question this project deliberately left open.

Stage 07 set amber at 3pp and red at 5pp and left the decision with the principal. Stage 12
closed the question of the **unit** (percentage points against relative: 25.8% improvement
over persistence against 25.6%, the same number) but said nothing about the **level**.

So `/run_full_analysis/<amber>/<red>` answers a live question:

| amber | verdict |
|---|---|
| 3.0pp, as published | No fund needs attention. Widest upper bound 2.04pp |
| 2.0pp | **Review needed.** BND can reach 2.04pp |

**The verdict flips, and it flips on BND's interval rather than its point estimate.** BND
projects to 1.64pp, which clears a 2pp line; its 95% upper bound is 2.04pp, which does not.
That is precisely the distinction Stage 11 spent its length establishing, now reachable by
anyone with a browser.

---

## 6. Assumptions and risks introduced by this stage

Stage 13 adds no modelling assumptions. It adds operational ones.

| Assumption | If wrong |
|---|---|
| The saved model is current | A stale pickle serves confident forecasts against fresh prices. Mitigated by exposing the fitted window, not by refusing to serve |
| One process is enough | `app.run` is a development server: single-threaded, not hardened. Fine on one machine for a demonstration, wrong facing a network |
| The caller is trusted | There is no authentication. Anyone who can reach the port can call every route |
| `data/processed/` exists | Regenerated rather than committed, so a fresh clone must run the pipeline once first. `app.py` falls back to the newest raw CSV and otherwise says what to run |
| Port 5001 is free | 5000 is taken by AirPlay Receiver on macOS. `PORT` overrides |

---

## 7. Fresh-clone validation

The instructions ask for the README to be validated by cloning into a fresh environment.
The sequence in `README.md` is: clone, create the env, `pip install -r requirements.txt`,
copy `.env.example` to `.env`, run `project_pipeline.ipynb` top to bottom, then
`python app.py`.

**The ordering constraint is the part a reader would otherwise get wrong.** `data/processed/`
is derived and not committed, so the pipeline has to run before the API has anything to
serve. `app.py` degrades in a stated order rather than crashing: newest cleaned parquet,
then newest raw CSV, then a `FileNotFoundError` naming the notebook to run.

---

## 8. What Stage 13 changed, and what it did not

**Changed.** The analysis is callable: `src/service.py` holds the chain as functions,
`app.py` serves them, and the extraction was checked against the original cells rather than
assumed. The model is saved with everything the published number needs. Dana can fetch her
table over HTTP, and the principal can move a threshold the project left open.

**Not changed.** No data, no features, no model, no default thresholds. The monitor still
says the same thing it said at the end of Stage 12: no fund needs attention this month, the
widest upper bound is 2.04pp against 3pp, and every interval is a floor rather than a bound.
