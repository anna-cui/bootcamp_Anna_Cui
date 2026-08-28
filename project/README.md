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
scrolls past, nothing downstream can tell them apart. A `close_was_filled` indicator is
the obvious Stage 09 feature and is not built yet.

**Output.** `data/processed/prices_clean_<YYYYMMDD-HHMM>.parquet`, so Stage 07 can
reproduce Stage 06 without re-downloading. Written through `write_df` and verified with
a reload, same as every other artifact in this project.
