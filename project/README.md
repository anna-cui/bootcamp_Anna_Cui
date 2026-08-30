# Portfolio Drift Monitor

**Stage:** Data Preprocessing (Stage 06)

## Problem Statement

A small advisory firm runs one model portfolio for its retail clients: 60% US equity
(VTI), 30% international equity (VXUS), 10% short-term bonds (BND). Because the three
funds move differently, the real weights drift away from those targets over time. A
strong equity year quietly turns 60/30/10 into something closer to 68/26/6, which is a
riskier portfolio than the client agreed to.

Today the firm only checks at the quarterly review, so a portfolio can sit off-target
for weeks before anyone notices. This project produces a daily report showing the current
weights, how far each one has drifted, and a flag when the gap gets too large. The point
is to find out today what the firm currently finds out three months from now.

## Stakeholder & User

**Decision owner: the firm's principal.** Sets the target weights and decides whether to
rebalance.

**User: the client service associate.** Opens the report each morning as part of an
existing checklist and raises anything flagged. Works in Excel, will not run a script, so
the output has to be a file that is already there.

The report needs to be ready before the morning client calls. Producing it overnight is
fine; this is not a trading tool.

## Useful Answer & Decision

**Descriptive.** The question is where the weights are now, not where they will be next
month. No forecast, on purpose.

**Metric:** drift in percentage points per fund, calculated as current weight minus
target weight.

**Decision trigger:** more than 5 percentage points off target is flagged red and raised
to the principal that day. Between 3 and 5 is amber, noted but no action. Under 3, no
mention.

**Artifact:** a daily CSV with one row per fund (target weight, current weight, drift,
flag), plus a chart of the weights over the past year.

## Assumptions & Constraints

- Daily adjusted closes for three tickers from yfinance. No API key, no paid data.
- Splits and dividends are assumed handled correctly by the data provider.
- Weights come from price movement only. Client deposits and withdrawals are not
  modeled, so this describes the model portfolio and not any one client's account.
- Three funds, one portfolio. No tax lots, no cash sleeve, no customization.
- The 5pp threshold is the principal's policy choice, not something this project sets
  out to optimize.
- Public market data only. No client account data.

## Known Unknowns / Risks

- The model's drift is not the same as a real client account's drift, and someone will
  eventually read it that way unless the file says otherwise.
- If 5pp turns out to fire every other month, the report gets ignored. I will check how
  often it would have triggered over the past three years before fixing the threshold.
- A stale or missing price produces a weight that looks plausible but is wrong, so the
  data gets validated on the way in.
- Every number depends on the last rebalance date, so that has to be an explicit input
  rather than a default hidden in the code.

## Lifecycle Mapping

Goal -> Stage -> Deliverable

- Agree what the report is for and what triggers action -> Problem Framing & Scoping
  (Stage 01) -> this README and `stakeholder-memo.md` in this folder
- Reproducible environment -> Tooling Setup (Stage 02) -> `requirements.txt`,
  `.env.example`
- Reusable weight and drift calculations -> Python Fundamentals (Stage 03) ->
  `src/utils.py`
- Pull and check the daily prices -> Data Acquisition & Ingestion (Stage 04) -> ingest
  script, raw pulls in `data/raw/`
- Keep raw and derived data so results can be re-created -> Data Storage (Stage 05) ->
  Parquet files in `data/processed/`

## Repo Plan

homework/              one folder per stage (homework00, homework01, ...)
project/               the drift monitor, scaffolded in Stage 02
├── data/raw/          price pulls, never edited by hand
├── data/processed/    computed weights and drift
├── src/               helper functions
├── notebooks/         project_pipeline.ipynb
├── reports/images/    charts saved by the code
├── model/             saved model objects
└── docs/              stakeholder memo
class_materials/       handouts; gitignored, never pushed

Commit at the end of each working session, push before each class, re-freeze
`requirements.txt` whenever a package is added. `.env` is never committed.

## Data Storage

| Folder | Holds | Rule |
|---|---|---|
| `data/raw/` | Price pulls exactly as acquired from yfinance | **Immutable.** Never edited by hand; a re-pull gets a new timestamped filename |
| `data/processed/` | The daily weights-and-drift table, derived by code | Deletable and re-creatable by re-running `notebooks/project_pipeline.ipynb` |

**Formats.** Raw pulls are **CSV** — human-readable, diffable in git, and small.
The processed table is **Parquet**, because it carries a datetime column and a
categorical flag that CSV would hand back as text.

**Paths come from `.env`**, never hardcoded:

    DATA_DIR_RAW=data/raw
    DATA_DIR_PROCESSED=data/processed

Read in Python via `os.getenv(...)` with a sensible default. `.env` is never
committed; `.env.example` is the committed template.

**Reading and writing** goes through `write_df` / `read_df` in `src/utils.py`,
which route on the file suffix, create missing directories, refuse to write an
empty frame, and parse any column whose name ends in `date`.

**Round trips are verified, not assumed.** After every save the pipeline
reloads the file and asserts shape, dtypes and values match the original.

## Data Cleaning

Cleaning sits on the boundary between `data/raw/` and `data/processed/`: after the
vendor pull is written to disk, before any weight is computed. Nothing downstream
touches the raw frame. The functions live in `src/cleaning.py` and every one of them
copies its input, returns a new frame, and reports what it changed.

**The rules here are deliberately not the homework's rules.**
`homework/homework06/src/cleaning.py` fills numeric blanks with the column median,
which is right for a cross-section of unrelated records. A price series is not a
cross-section. The median of a year of VTI closes is not a plausible price for any
particular Tuesday, and using it would invent a move the market never made. So a
missing close is carried forward from the last observation instead.

| Step | Rule | Why this one |
|---|---|---|
| 1 | Coerce `date` to datetime, `close` to float | CSV is text and forgets dtypes (Stage 05). Sorting and filling both depend on the real types |
| 2 | Sort by `(date, ticker)` | Forward fill walks row order; on an unsorted frame it propagates prices backwards through time |
| 3 | Drop duplicate `(date, ticker)`, keep last | Two closes for one fund on one day is a contradiction, not extra data. Keeping the later row assumes a resend is a correction |
| 4 | Non-positive closes become missing | A close of zero is a broken record, not a cheap fund |
| 5 | Forward fill within fund, limit 3 days | The last traded price is the standard stand-in for an unobserved close. The limit matters: filling further draws a flat line, which asserts zero volatility rather than admitting a gap |
| 6 | Drop any date missing a fund | Last, because step 5 may have repaired it |

**Step 6 is the one that matters, and it has no configurable alternative.** A weight is
a share of a total. If BND is absent on a Tuesday, weights built from VTI and VXUS alone
still sum to 1, over the wrong basket. Dropping a 10% sleeve divides the rest by 0.9,
which lifts a 60% target to 66.7% on its own: the pipeline reports VTI at about 67%, a
drift near 6.7pp, and fires a **red** flag on a day the portfolio was within half a point
of target. The number is not missing, it is wrong, and it looks entirely reasonable on
the report Dana opens.

That finding compounds the one recorded in Stage 05. Over a year of real closes the 5pp
red threshold never fires at all, so the only red flag this monitor would have produced
in that year is a data artifact. An alert that fires only on bad data trains its reader
to ignore it, which is the failure mode Stage 07's sensitivity analysis has to address.

**What the cleaning costs.** On the current pull, nothing: every counter in the log is
zero and the cleaned frame is row-for-row the raw pull. That is the expected result for
one vendor on three highly liquid funds, and it is also an uninformative test, so the
pipeline breaks a copy on purpose and checks the same code repairs it. On that damaged
copy the cost is four dropped days (about 1.6% of the window) and two forward-filled
closes carrying roughly 50 to 110 basis points of error each. The dropped days are the
expensive half and the defensible one. The forward fills are the cheap half and the one
to watch: they are estimates carrying the same dtype as observations, and once the log
scrolls past, nothing downstream can tell them apart. A `close_was_filled` indicator,
defined in the feature table below, was built in Stage 09 and closes that gap.

**Output.** `data/processed/prices_clean_<YYYYMMDD-HHMM>.parquet`, so Stage 07 can
reproduce Stage 06 without re-downloading. Written through `write_df` and verified with
a reload, same as every other artifact in this project.

## Feature Definitions

Built in Stage 09 by `src/features.py` and assembled by
`fe.build_feature_matrix(prices_clean, TARGET_WEIGHTS, prices_raw=raw_reloaded)`. The
reasoning and the evidence are in `docs/features.md`; this table is the definitions.

**Target.** `y_absdrift_fwd_21` - absolute drift in percentage points, 21 trading days
ahead. The horizon is a decision, not a default: today's absolute drift predicts
tomorrow's at 0.979, so a one-day target would be answered correctly by "the same as
today" and would teach a model nothing. At 21 days that falls to 0.689, and a month is
enough warning for the principal to act on.

| Feature | Definition | Why it exists |
|---|---|---|
| `abs_drift` | distance from target, in percentage points, ignoring direction | The quantity the amber and red thresholds are actually compared against |
| `abs_drift_rel` | `abs_drift` as a percent of that fund's target weight | Stage 07 left the pp-versus-relative unit question open. Within a fund this is the same number rescaled; across funds it is the only one of the two that compares |
| `drift_chg_1` | one-day change in drift | Stage 08 said build the rate, not the level. Kept as a recorded negative result: it correlates with the target at -0.010 |
| `drift_chg_5` | five-day change in drift | The same idea at a weekly step |
| `drift_slope_21` | OLS slope of drift over the last 21 trading days, in pp per year | Stage 08 fitted one line to the whole year and got -0.93 for BND. This is that line refitted to a moving window, so a model can see the trend steepening |
| `ret_1` | daily simple return, per fund | The raw input the drift is built from |
| `vol_21` | 21-day realized volatility, annualized, percent | Stage 08's volatility clustering. Correlates +0.57 with the target for BND and -0.23 for VTI, which is the clearest argument for keeping fund identity in the model |
| `eq_bond_spread_21` | target-weighted equity return minus bond return, 21-day trailing, annualized | The mechanism. Stage 08 traced the drift to this spread; every other feature describes the drift rather than its cause |
| `ticker_VTI`, `ticker_VXUS`, `ticker_BND` | one-hot fund indicators | See below |
| `ticker_target` | fund encoded by its policy weight (0.60 / 0.30 / 0.10) | A genuine ordinal carrying domain knowledge, unlike label encoding. Built as a candidate; constant within a fund, so it only helps a pooled model |
| `close_was_filled` | 1 where the close was forward-filled rather than observed | Closes the Stage 06 item above. Zero on a clean pull, verified to fire on a damaged copy. Kept in the pipeline, excluded from the model while it is constant |

**Why the fund identifier is one-hot encoded.** Stage 08's categorical profile is
251 / 251 / 251, exactly, because `drop_incomplete_days` keeps only dates with a close for
every fund. That single number decides the choice. Frequency encoding maps all three funds
to 0.3333, producing a column with one distinct value and zero information. Label encoding
assigns integers alphabetically (BND 0, VTI 1, VXUS 2), which tells a linear model that
VXUS is twice VTI; the resulting column correlates with the target at 0.042, against
-0.360, +0.217 and +0.143 for the three one-hot columns. One-hot invents no ordering and
costs three columns.

**Not built.** `drift_slope_63` was built and dropped: 24.70% missing, which fails Stage
08's own 20% gate, in exchange for a pooled correlation of -0.001. Target encoding is not
used, because computing a category mean outside the training split leaks the answer.

**Nothing is scaled.** Standardising here would fit the scaler on rows Stage 10b holds
out as a test set. Scaling belongs inside the split.

**Every window is causal, and it is tested.** `assert_no_lookahead` rebuilds the features
on a truncated history and compares the overlap. The pipeline runs it on all 11 modelling
features, then runs it against a deliberately leaky build to confirm the test itself
works.

## Reporting & Delivery

Built in Stage 12 by `src/reporting.py`, produced by `notebooks/delivery.ipynb`. The
reasoning is in `docs/reporting.md`; this section is the summary.

**The deliverable is two files, not one.** The firm principal decides whether to trust the
model, which needs the caveats. Dana decides whether to raise a fund this month, which
needs a number and a colour. A caveat Dana cannot act on hides the number she can, so:

| Artifact | Reader | Contains |
|---|---|---|
| `reports/final_report.md` | firm principal | Forecast, the bias finding, the sensitivity ordering, assumptions, next steps |
| `reports/drift_monitor_current.csv` | Dana | Drift today, projection, 95% band, worst case, and an `action` column. No model vocabulary |
| `reports/decision_log.json` | reviewer or successor | Six decisions across Stages 06, 07, 10a and 12, each with the alternative rejected and the risk taken |

**What the monitor currently says.** No fund needs attention in the next 21 trading days,
and that survives every assumption tested. VTI is projected at 0.64pp, VXUS at 0.99pp and
BND at 1.64pp, with the widest 95% upper bound across all scenarios at 2.14pp against an
amber line of 3pp. Against a persistence baseline the model improves mean absolute error
by 25.8%.

**Stage 11's handoff instruction turned out to be impossible, and that is the main
finding.** Stage 11 asked Stage 12 to correct a per-fund bias with interactions. Two things
block it, both measured rather than argued:

- **The interaction already exists.** `abs_drift_rel` is `abs_drift` divided by the target
  weight, to within 1.8e-15 across the whole panel, which makes it that interaction under
  another name. Adding it explicitly gives a singular design matrix, and a per-fund model
  cannot hold both columns at once. `fund_interactions` raises with the reason rather than
  letting a rank-deficient matrix through.
- **The bias is not in the training window.** In-sample per-fund bias is zero to machine
  precision because the fund dummies force it. The target itself rose 0.31pp between the
  training and test windows, and BND's rose 0.81pp. It is regime drift, not misfit.

Every attempt to add flexibility made things worse: separate per-fund models spend 15
parameters against about 24 independent observations, score MAE 0.216 where the pooled
6-parameter model scores 0.176, and leave all three funds biased rather than two. What
gets published is the **smaller** model plus a measured offset, labelled as an observation
rather than a fitted parameter.

**The project's priorities are reordered.** Swinging each assumption one at a time against
BND's 95% upper bound:

| Assumption | Swing |
|---|---|
| Regime, test window against training window | **0.31pp** |
| Bias adjustment, raw against measured offset | 0.15pp |
| Model specification, 6-param against 11-param | 0.10pp |
| Confidence level, 95% against 99% | 0.07pp |
| Interval shape, empirical against Gaussian | 0.02pp |

Regime beats specification three to one and interval shape twenty to one. Stages 09
through 11 refined the third, fourth and fifth largest levers. **The next unit of effort
belongs on the length of the data window, not on the model**, which is also the only fix
for Stage 11's finding that every interval here is a floor rather than a bound.

**Nothing about the data, the thresholds or the features changed in Stage 12.** It
packages what exists. The one modelling decision taken, preferring the 6-parameter
specification, ratifies a choice Stage 10a's variant sweep had already made on independent
evidence.

## Running this project from a fresh clone

Built in Stage 13. The reasoning is in `docs/productization.md`; this section is the
instructions.

```bash
git clone https://github.com/anna-cui/bootcamp_Anna_Cui.git
cd bootcamp_Anna_Cui/project
conda create -n bootcamp_env python=3.10
conda activate bootcamp_env
pip install -r requirements.txt
cp .env.example .env
```

`.env` holds a **deliberate placeholder** Alpha Vantage key, so every notebook takes the
yfinance path by design. Code tests `!= 'dummy_key_123'` rather than `bool(key)`, because
a placeholder is truthy.

Then, in order:

| Step | Command | What it does |
|---|---|---|
| 1 | `jupyter lab`, run `notebooks/project_pipeline.ipynb` top to bottom | Pulls a fresh year of prices, rebuilds everything, writes `data/processed/`, `reports/` and `model/model.pkl` |
| 2 | `python app.py` | Starts the API on http://127.0.0.1:5001 |
| 3 | `notebooks/productization.ipynb` | Calls the API and records the responses |

**Step 1 is required before step 2 on a fresh clone**, because `data/processed/` is
regenerated rather than committed. `app.py` falls back to the newest raw CSV and, failing
that, says exactly what to run.

**The pipeline pulls a rolling one-year window**, so figures move between runs. Every
notebook ends with a self-check cell that recomputes the numbers quoted in its own markdown
and prints PASS or FAIL, which is what catches prose drifting away from the data.

## The API

```bash
cd project
python app.py
```

**Port 5001, not 5000.** macOS runs AirPlay Receiver on 5000 from Monterey onward, so Flask
either fails to bind or requests reach AirPlay and return 403, which reads like a broken
app. Override with `PORT=5002 python app.py`.

The model, the prices and the feature matrix are loaded **once at import time**. Rebuilding
the feature matrix per request would take seconds and would give concurrent callers
different answers as the rolling window moved underneath them.

| Route | Method | Returns |
|---|---|---|
| `/health` | GET | Status plus provenance: which model, fitted on which window, prices through which date |
| `/predict` | POST | Prediction from a caller-supplied feature row |
| `/predict/<ticker>` | GET | Projected drift for one fund from its latest observation |
| `/run_full_analysis` | GET | The whole monitor as JSON |
| `/run_full_analysis/<amber>/<red>` | GET | The same, against caller-supplied thresholds |
| `/plot` | GET | The drift chart as `image/png`. Accepts `?amber=` |
| `/monitor.csv` | GET | Dana's table as a CSV download |

### Examples

```bash
curl http://127.0.0.1:5001/predict/BND
```

```json
{"fund": "BND", "as_of": "2026-08-28", "drift_today_pp": 1.7049,
 "projected_pp": 1.6406, "interval_95_pp": [1.3319, 2.0409],
 "projected_adjusted_pp": 1.4902, "band": "green",
 "worst_case_band": "green", "action": "no action"}
```

```bash
curl -X POST http://127.0.0.1:5001/predict \
     -H "Content-Type: application/json" \
     -d '{"features": [1.70, 17.05, 0.01, 0.05, 0.5]}'
```

The five features, in order, are `abs_drift`, `abs_drift_rel`, `drift_chg_1`,
`drift_chg_5`, `drift_slope_21`. `/health` lists them.

```bash
curl http://127.0.0.1:5001/run_full_analysis/2/4
curl -o monitor.csv http://127.0.0.1:5001/monitor.csv
curl -o drift.png "http://127.0.0.1:5001/plot?amber=2"
```

**Bad input returns HTTP 400 and a JSON body with an `error` key.** Never a traceback,
never HTML. Path parameters are declared as strings and converted by hand: Flask's
`<float:...>` converter would make `/run_full_analysis/abc/4` fail to match the route and
return a 404 HTML page instead of a usable error.

### Why the threshold is the parameter a caller can change

Stage 07 set amber at 3pp and red at 5pp and left the choice with the principal. Stage 12
closed the question of the *unit* (percentage points against relative, 25.8% improvement
over persistence against 25.6%) but said nothing about the *level*. So the threshold is the
one input where a caller's question is genuinely open, and
`/run_full_analysis/<amber>/<red>` answers it without anyone opening a notebook.

At 3pp no fund needs attention. At 2pp BND requires review, and it does so on its **95%
upper bound of 2.04pp** rather than its point forecast of 1.64pp, which is exactly the
distinction Stage 11 argued the monitor must publish.

## Stakeholder Handoff Summary

### Overview and purpose

The Portfolio Drift Monitor tracks how far a 60/30/10 VTI/VXUS/BND portfolio, bought at
target and never rebalanced, has drifted from those weights, and projects that drift 21
trading days ahead. It exists so the firm principal learns that a fund is approaching the
rebalancing threshold **before** it crosses, and so Dana can answer a client question
without waiting for an analyst.

### Key findings and recommendations

1. **No fund needs attention this month**, and that survives every assumption tested. VTI
   projects to 0.64pp, VXUS to 0.99pp, BND to 1.64pp, and the widest 95% upper bound across
   all scenarios is 2.14pp against an amber line of 3pp.
2. **The model beats a persistence baseline by 25.8%** on mean absolute error, using five
   features and six parameters.
3. **Report BND on its upper bound, not its point estimate.** It is the fund nearest amber
   and the fund the model is least right about, which is the worst of the three pairings.
4. **The next real improvement is a longer data window, not a better model.** Swinging each
   assumption against BND's upper bound: regime 0.31pp, bias adjustment 0.15pp, model
   specification 0.10pp, confidence level 0.07pp, interval shape 0.02pp. Four stages of
   modelling refinement went into the third-largest lever.

### Assumptions and limitations

| Assumption | If it is wrong |
|---|---|
| The next month resembles the last twelve | The largest single error source, worth 0.31pp on the headline. One year, one regime, no market stress in the window |
| The published bias offset carries forward | Worth 0.15pp. It is a measured observation from one window, not a fitted parameter |
| 42 test dates can describe their own uncertainty | They cannot at a 21-day timescale. **Every interval published here is a floor, not a bound** |
| Errors come from one distribution | BND's residuals are the least well behaved, and BND is the fund closest to amber |
| Prices arrive without gaps | Stage 06 fills them and `close_was_filled` flags them; currently constant, so untested in production |

A 21-day forward target makes consecutive rows share 20 of their 21 days, so 501 training
rows carry roughly **24 independent observations**. That single number constrains
everything: it is why the six-parameter model beats the eleven-parameter one, why separate
per-fund models are worse than a pooled one, and why the regression's own standard errors
are not used anywhere.

### Risks and potential issues

- **A stale saved model.** `get_bundle` prefers `model/model.pkl` to refitting, so a pickle
  from last month will serve confident forecasts against this month's prices. The fitted
  window is recorded in the bundle, printed by `describe_bundle` and returned by `/health`.
  **Check it before trusting a number.** Re-run the pipeline, or call
  `sv.get_bundle(prices, refit=True)`, to refresh.
- **The per-fund bias cannot be modelled away.** Stage 12 established that it is regime
  drift rather than misspecification: in-sample per-fund bias is zero by construction, and
  `abs_drift_rel` is already `abs_drift` interacted with the fund. Do not try to fix it with
  interactions; the design matrix is singular and the attempt has been made.
- **This is a development server.** `app.run` is single-threaded and not hardened. It is
  fine for a demonstration on one machine and is not what should face a network.
- **No authentication.** Anyone who can reach the port can call every route.

### Using the deliverables

| Artifact | Reader | How to use it |
|---|---|---|
| `reports/final_report.md` | firm principal | Read it. It carries the caveats needed to decide whether to trust the model |
| `reports/drift_monitor_current.csv` | Dana | Open in Excel. One row per fund, a band, and an `action` column. No model vocabulary |
| `GET /monitor.csv` | Dana | The same table without waiting for anyone to re-run a notebook |
| `reports/decision_log.json` | reviewer or successor | Six decisions with the alternative rejected and the risk taken |
| `docs/*.md` | analyst | One per stage, with the evidence behind each choice |
| `model/model.pkl` | another program | `sv.load_bundle()`. Carries residuals and bias offsets, not just coefficients |

### Suggested next steps

1. **Lengthen the data window** before touching the model. It is worth roughly three times
   more than any specification change available, and it is the only fix for the intervals
   being floors rather than bounds. A 21-day bootstrap block becomes usable near 200 test
   dates, about five years.
2. **Decide the threshold level.** `/run_full_analysis/<amber>/<red>` makes the question
   cheap to explore. The unit question is closed; the level is not.
3. **Schedule the pipeline** so the monitor refreshes without anyone opening Jupyter, and
   alert if `close_was_filled` stops being constant.
4. **Put the API behind something real** before it faces a network: a production server,
   and authentication.

## Monitoring and handoff

Built in Stage 14. Full plan in `docs/monitoring_plan.md`, runbook in
`docs/handoff_plan.md`, wireframe in `reports/dashboard_sketch.png`. The thresholds also
live in code as `service.MONITOR_THRESHOLDS`, so the document and the checks cannot drift
apart, and `service.monitoring_checks(matrix, bundle)` runs every one of them that current
data can answer.

**The horizon decides what is monitorable.** A forecast made today cannot be scored for 21
trading days, about 29 calendar days, so every model-quality metric lags by a month: the
monitor cannot say the model broke today, only that it was broken a month ago. Worse, a
21-day window over three funds carries **3 independent observations, not 63**, so a monthly
rolling MAE is not a measurement and a threshold on one would fire on noise. Model quality
is therefore watched on a **63-day window (9 observations)** while the data and system
checks do the daily work.

**Thresholds are anchored to measured values, not conventions.**

| Layer | Check | Threshold | Where the number comes from |
|---|---|---|---|
| Data | Price freshness | > 4 calendar days | The largest gap ever observed between consecutive trading days is exactly 4 |
| Data | Forward-filled closes | > 0 | Currently 0, so `close_was_filled` has never been exercised |
| Data | Rows per ticker | not all equal | Currently 251 / 251 / 251, enforced by `drop_incomplete_days` |
| Model | Realized volatility | outside p10-p90 | VTI 9.6-17.4, VXUS 10.4-24.2, BND 2.7-4.6, each fund's own training range |
| Model | 63-day rolling MAE | > 0.2121pp | Upper bound of Stage 11's block-bootstrap CI on the current 0.1759 |
| Model | Per-fund bias | outside its interval | The Stage 12 offsets with their bootstrap intervals |
| System | p95 latency | 100ms JSON, 1000ms `/plot` | Measured: `/health` 3.0ms, `/predict` 3.5ms, `/monitor.csv` 15.8ms, `/run_full_analysis` 17.9ms, `/plot` 225ms |
| Business | Any flag raised | any flag is an event | Zero have ever fired |

**`/plot` is 50 times slower than the JSON routes** because it renders matplotlib on every
request, so it is the route that degrades first under load. That ordering is worth knowing
before an incident rather than during one.

**Retraining is monthly**, aligned to the 21-day horizon, with out-of-cycle triggers on the
volatility, MAE and bias rows. Refitting more often would be judged on evidence that does
not exist yet.

**Ownership.** The analyst runs the refit and is first responder for the data, model and
system layers. The firm principal approves threshold changes, out-of-cycle retraining and
rollbacks, and owns the business layer, since only the decision owner can act on a
threshold being wrong. Dana reports a stale `as_of` date. Issues are logged as GitHub
issues labelled by layer.

**The honest gaps.** Three of the fourteen checks report `no data`, because this monitor
has never run in production: there is no history of served forecasts, no latency series and
no flags. The widest drift in the observed year was **2.23pp** against a 3pp amber line, so
**the alert path is untested**, and the runbook says to treat the first flag ever raised as
a possible bug in the alerting before treating it as a portfolio event.

### A note on chart colours

`reporting.FUND_COLOR` is the single definition of the per-fund palette, checked with a
colour-vision validator rather than chosen by eye. The values used by the Stage 12 and 13
charts (`#1f4e79` / `#c77b30` / `#4a7c59`) failed on two counts: the blue sat below the
readable lightness band, and the blue and green both fell under the chroma floor, so they
read as grey to some viewers. The green was also only marginally separable from the orange
under protanopia. The current values move the green toward teal, which is what fixes that
pair, and pass all five checks. The committed Stage 12 and 13 images predate this and still
use the old palette; regenerating them is a re-run away.
