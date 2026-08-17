# Stakeholder Memo: Portfolio Drift Monitor

**To:** Firm principal
**From:** Anna Cui
**Date:** August 2026

## The problem

Our model portfolio is 60% VTI, 30% VXUS, 10% BND. Prices move, so the real weights
drift away from those targets. Today we only notice at the quarterly review, which means
a portfolio can sit off-target for weeks before anyone says anything.

## What I will build

A daily CSV showing, for each of the three funds:

| Field | Meaning |
|---|---|
| `target_weight` | 0.60 / 0.30 / 0.10 |
| `current_weight` | what it actually is today |
| `drift_pp` | the gap, in percentage points |
| `flag` | green under 3pp, amber 3 to 5pp, red over 5pp |

Plus a chart of the weights over the past year.

## Who uses it

Dana, our client service associate. She goes through a checklist every morning before
the 10am client calls. This is one more line on it. She opens the file, looks at the flag
column, and tells you about anything red.

Two things she has said that shaped the design:

- "I find out we're off-target when I'm building the quarterly deck."
- "If it needs Python, it's not happening."

So the output is a file that is already sitting there, not a script to run.

## What it does not do

- It does not predict anything. It reports where the weights are today.
- It does not recommend a trade. It flags, you decide.
- It tracks the model, not individual client accounts. Real accounts differ because
  clients add and withdraw money at different times.

## What I need from you

1. The date of the last rebalance. Every number depends on it.
2. Confirmation that 5pp is the right threshold to start with. I will show you how often
   it would have fired over the past three years, and you can move it.
3. Ten minutes with Dana to agree the columns before I build it.

## Risks

- If the flag fires too often, Dana stops reading it. That is the main way this fails.
- A bad price from the data provider gives a wrong weight that still looks reasonable,
  so I will check the data on the way in.
- Where to set the threshold is your call, not something the data can answer.
