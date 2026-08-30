# Lifecycle framework guide

**Stage 16.** The Applied Financial Engineering lifecycle mapped onto the Portfolio Drift
Monitor: one row per stage, the file or folder in this repo that holds that stage's work,
and the decision that was actually taken there.

All paths are relative to `project/` unless they start with `homework/`. The stage numbers
are the course's own: 01 to 16, with Stage 10 split into 10a (linear regression) and 10b
(time series and classification). Homework folders use the same numbers, so
`homework/homework07` is Stage 07 and `homework/homework10b` is Stage 10b.

---

## The map

| # | Lifecycle stage | Where it lives | What was decided |
|---|---|---|---|
| 01 | **Problem Framing & Scoping** | `README.md` (Problem Statement, Stakeholder & User, Useful Answer & Decision), `docs/stakeholder-memo.md` | Drift is reported in **percentage points**, red above 5pp and amber 3 to 5pp. Decision owner is the firm principal; the end user is **Dana**, a client-service associate who works in Excel and will not run scripts. That persona ended up driving every delivery choice in Stages 12 to 14 |
| 02 | **Tooling Setup** | `requirements.txt`, `.env.example`, `.gitignore`, `README.md` (Repo Plan) | Conda `bootcamp_env` on Python 3.10, every package pinned. The Alpha Vantage key is a **deliberate placeholder**, so code must test `!= 'dummy_key_123'` rather than truthiness, and every notebook takes the yfinance path by design |
| 03 | **Python Fundamentals** | `src/utils.py`, `src/config.py`, `notebooks/python_fundamentals_summary.ipynb` | Weight and drift arithmetic lives in one module, not in notebook cells. `flag_drift` and the amber/red constants are defined once so the memo, the CSV and the chart legend cannot disagree about where amber starts |
| 04 | **Data Acquisition / Ingestion** | `data/raw/api_yfinance_VTI-VXUS-BND_*.csv`, ingest cell in `notebooks/project_pipeline.ipynb` | Code against the **shape that comes back**, not the shape we remember: yfinance returns a MultiIndex for multi-ticker requests and a flat one for a single ticker, and the level order has changed between versions. Raw pulls are timestamped and never edited |
| 05 | **Data Storage** | `data/raw/`, `data/processed/`, `README.md` (Data Storage) | Raw is immutable and keeps its full history; **everything in `data/processed/` is derived and must be re-creatable by running the code**. Parquet for the pipeline, CSV only where a person opens the file |
| 06 | **Data Preprocessing** | `src/cleaning.py`, `README.md` (Data Cleaning) | Forward-fill missing closes **and flag every filled row** with `close_was_filled`; a silent fill is untraceable. `drop_incomplete_days` keeps only dates with a close for all three funds, which is why the panel is exactly 251 / 251 / 251 |
| 07 | **Outlier Analysis & Risk Assumptions** | `src/outliers.py`, `docs/outliers.md` | IQR over Z-score, with the threshold **stated rather than defaulted**, and a sensitivity sweep beside it. Outliers are kept: a large daily return is the signal, not noise. Left the pp-versus-relative unit question open for the principal, and Stage 12 closed it |
| 08 | **Exploratory Data Analysis** | `src/eda.py`, `docs/eda.md`, `notebooks/eda.ipynb` | Drift is a **trend, not noise**: BND correlates with time at -0.929, about -1.7pp per year. The date axis is business-daily, so the 114 missing calendar days are weekends and 10 named holidays rather than data loss. Carries an **"Amended after Stage 10a"** correction |
| 09 | **Feature Engineering** | `src/features.py`, `docs/features.md`, `README.md` (Feature Definitions) | One-hot the fund, because the panel is 251/251/251 exactly, so frequency encoding produces a **provably constant column**. Every window is causal and `assert_no_lookahead` tests it against a deliberately leaky build. Also carries an **"Amended after Stage 10a"** correction |
| 10a | **Modeling: Linear Regression** | `src/modeling.py`, `docs/modeling.md`, `notebooks/modeling_regression.ipynb` | Split **chronologically on dates, not rows**. It scored 0.692 against a random split's 0.501, contradicting what Stages 08 and 09 had predicted, and both docs were amended rather than quietly left wrong. A 21-day target leaves about **24 independent observations**, which constrains everything after this |
| 10b | **Modeling: Time Series & Classification** | `src/timeseries.py`, `docs/timeseries.md`, `notebooks/modeling_timeseries.ipynb` | Scaling goes **inside** the split via a `Pipeline`, and the leak is worth only 0.00001 RMSE because standardising is affine, which is worth knowing rather than assuming. The prescribed lag family beats persistence by 3.1% where Stage 10a's features beat it by 26%. Classification was not fitted because the flag is green on every one of 753 fund-days: there is no positive class to learn |
| 11 | **Evaluation & Risk Communication** | `src/evaluation.py`, `docs/evaluation.md`, `notebooks/evaluation.ipynb` | Publish the **prediction interval, not the confidence interval**: they differ by a factor of 11 and Dana reads one fund on one day. The block bootstrap **degenerates** at the block length this target needs, so every interval here is a floor rather than a bound. Carries two **"Amended after Stage 12"** corrections |
| 12 | **Results Reporting & Delivery Design** | `src/reporting.py`, `docs/reporting.md`, `notebooks/delivery.ipynb`, `reports/final_report.md`, `reports/drift_monitor_current.csv`, `reports/decision_log.json`, `reports/README.md` | **Two artifacts for two readers**, because a caveat Dana cannot act on hides the number she can. Stage 11's instruction to fix the per-fund bias with interactions turned out to be **impossible**, and finding out why was worth more than the fix: the interaction already exists as `abs_drift_rel`, and the bias is regime drift, not misspecification |
| 13 | **Productization** | `src/service.py`, `app.py`, `docs/productization.md`, `notebooks/productization.ipynb`, `model/model.pkl` | The saved model carries **residuals, not just coefficients**, because the published number is an interval and an interval needs them. The refactor was checked against the original notebook cells to **exactly zero** difference before anything shipped |
| 14 | **Deployment & Monitoring** | `docs/monitoring_plan.md`, `docs/handoff_plan.md`, `reports/dashboard_sketch.png`, `service.MONITOR_THRESHOLDS`, `service.monitoring_checks`, `reports/monitoring_status_*.csv` | Model quality is watched on a **63-day window**, because a 21-day window over three funds carries **3 independent observations** and a threshold on it would fire on noise. Three of thirteen checks report `no data`, stated rather than hidden, because the monitor has never run in production |
| 15 | **Orchestration & System Design** | `docs/orchestration_plan.md`, `src/run_step.py`, `reports/images/pipeline_dag.png` | **cron and a CLI, not Airflow**: a handful of tasks, one machine, one operator, a run that finishes in 0.10s. Retry is scoped to `(OSError,)` around the one genuinely transient fault, because retrying a deterministic failure only buries the error |
| 16 | **Lifecycle Review** | `docs/lifecycle_framework_guide.md` (this file), `docs/project_summary.md`, `README.md` | Nothing new was built. The repo was made legible: this map, a summary for a non-technical reader, and one final end-to-end run |

---

## Where each stage's homework lives

The project is the cumulative artifact; the homework folders hold the same stage worked on
a self-contained dataset. Homework sheets were issued through Stage 13; from Stage 14
onward the project is the assignment, so there is no `homework14/`, `homework15/` or
`homework16/`.

| Stage | Repo folder |
|---|---|
| 00 (pre-class setup) | `homework/homework00` |
| 01 to 09 | `homework/homework01` through `homework/homework09` |
| 10a, 10b | `homework/homework10a`, `homework/homework10b` |
| 11, 12, 13 | `homework/homework11`, `homework/homework12`, `homework/homework13` |
| 14, 15, 16 | project only |

---

## The spine

`notebooks/project_pipeline.ipynb` runs every stage above in order, top to bottom, in one
kernel: ingest, clean, outliers, EDA, features, both models, evaluation, delivery,
productization, monitoring, orchestration. It is **79 code cells** and it is the single
thing to run to confirm the whole chain still works.

Each stage's section ends with a self-check cell that recomputes the figures quoted in its
own markdown and prints PASS or FAIL. That exists because the pipeline pulls a **rolling
one-year window**, so the data moves underneath prose that was written once. It has earned
its place: on 2026-08-30 the pipeline pulled a fresh window and every figure from Stages 08
through 15 still reproduced.

---

## Three things this map should not hide

**Two documents were amended rather than corrected silently.** `docs/eda.md` and
`docs/features.md` each predicted that a chronological split would score worse than a random
one. Stage 10a measured the opposite. `docs/evaluation.md` recommended a bias correction
Stage 12 then proved impossible. In all three cases the original claim is left in place with
an amendment block beneath it, because a reader who cannot see what was believed earlier
cannot judge how much to trust what is claimed now.

**The largest lever was found late.** Swinging each assumption against BND's 95% upper
bound puts regime at 0.31pp, model specification at 0.10pp and interval shape at 0.02pp.
Stages 09 through 11 refined the third, fourth and fifth largest levers. The recommendation
that came out of the project is to lengthen the data window before touching the model again.

**One number constrains almost every decision after Stage 10a.** A 21-trading-day forward
target makes consecutive rows share 20 of their 21 days, so 501 training rows carry about
**24 independent observations**. That is why the six-parameter model beats the eleven, why
separate per-fund models are worse than a pooled one, why the regression's own standard
errors are used nowhere, and why the monitoring window is quarterly rather than monthly.

---

## Looking back

**Hardest stage.** Stage 11. Putting an honest interval on a 21-day-ahead forecast from one
year of overlapping data meant admitting that the block bootstrap the dependence requires
degenerates at that block length, so the published intervals are floors rather than bounds.

**Most reusable part.** `src/utils.py` and `src/service.py`. The drift arithmetic and the
model bundle are what every later stage, the API and the CLI all import; nothing else
would survive a change of dataset unchanged.

**Where it would fail if run tomorrow.** The data pull. Everything downstream is derived
from one yfinance request with no key and no contract, and the monitoring plan's first row
(price freshness) exists because that is the failure most likely to arrive first.
