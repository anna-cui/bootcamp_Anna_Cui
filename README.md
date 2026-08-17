# Portfolio Drift Monitor

**Stage:** Problem Framing & Scoping (Stage 01)

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
  (Stage 01) -> this README and the memo in `docs/`
- Reproducible environment -> Tooling Setup (Stage 02) -> `requirements.txt`,
  `.env.example`
- Reusable weight and drift calculations -> Python Fundamentals (Stage 03) ->
  `src/utils.py`
- Pull and check the daily prices -> Data Acquisition & Ingestion (Stage 04) -> ingest
  script, raw pulls in `data/raw/`
- Keep raw and derived data so results can be re-created -> Data Storage (Stage 05) ->
  Parquet files in `data/processed/`

## Repo Plan

```
data/raw/         price pulls, never edited by hand
data/processed/   computed weights and drift
src/              helper functions
notebooks/        one notebook per stage
docs/             stakeholder memo
```

Commit at the end of each working session, push before each class, re-freeze
`requirements.txt` whenever a package is added. `.env` is never committed.
