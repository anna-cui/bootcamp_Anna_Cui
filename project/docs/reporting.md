# Delivery design - what the monitor publishes, to whom, and what it rests on

**Stage 12.** Companion to `src/reporting.py`, `notebooks/delivery.ipynb` and the artifacts
in `reports/`.

Eleven stages produced a model. This one produces a decision, and the two are different
artifacts. Three questions had to be settled before anything could be published: whether
Stage 11's bias could be corrected, which assumption the conclusion actually rests on, and
who the document is for.

Data through **2026-08-28**. Seed 111, 2000 resamples, 95% level. Test set 126 fund-days
over 42 dates, unchanged from Stage 11.

---

## 1. The three results that shaped the deliverable

1. **Stage 11's instruction to correct the per-fund bias with interactions cannot be
   carried out**, for a reason that changes where the remaining risk sits.
2. **Regime moves the headline three times further than the model specification**, which
   reorders what the project should do next.
3. **The conclusion is robust to every assumption tested**, so the report can state
   something rather than hedge.

---

## 2. The bias question, closed

Stage 11 measured a systematic under-prediction of **+0.215pp** for VTI and **+0.134pp**
for BND, both intervals excluding zero, and recommended per-fund interactions on the
grounds that the fund dummies already existed. Building them produced two independent rank
failures.

### The structural cause

**`abs_drift_rel` is `abs_drift` divided by the fund's target weight.** Measured, not
assumed: the maximum discrepancy across the whole panel is **1.8e-15**. That makes it, in
the pooled model, exactly `abs_drift` interacted with the fund.

Two consequences follow, and both were hit:

| Attempt | What happens |
|---|---|
| Pooled model plus explicit `abs_drift x fund` | Singular. The explicit term is a linear combination of what `abs_drift_rel` already contributes |
| Separate model per fund | Singular. Inside one fund, `abs_drift_rel` is a constant multiple of `abs_drift` |

`fund_interactions` raises on the first with a message naming the reason, rather than
letting a rank-deficient matrix reach `fit_ols`. **The interaction Stage 11 asked for was
in the model before Stage 11 asked.**

### The bias is not in the training window

The stronger finding is that no per-fund term could have helped regardless. In-sample
per-fund bias for the 11-parameter model:

| Fund | in-sample bias |
|---|---|
| VTI | -0.000000 |
| VXUS | -0.000000 |
| BND | -0.000000 |

Zero to machine precision, because OLS with group dummies forces it. **Every point of the
test bias is out-of-sample.** A per-fund parameter fitted on the training window is fitted
on a window where the thing it would correct does not exist.

### What actually moved

| | train mean | test mean | shift |
|---|---|---|---|
| VTI | 0.4707 | 0.6030 | **+0.13** |
| VXUS | 0.9725 | 0.9463 | -0.03 |
| BND | 0.7350 | 1.5494 | **+0.81** |
| **all** | **0.7261** | **1.0329** | **+0.31** |

The target itself rose **0.31pp** between windows and BND's rose **0.81pp**. The model
under-predicts because the world moved, not because the specification is wrong.

### The sweep agrees from the other direction

Four specifications, one split:

| specification | parameters | MAE | bias | VTI | VXUS | BND |
|---|---|---|---|---|---|---|
| pooled 11-param (Stage 10a) | 11 | 0.1915 | +0.095 | +0.215 | -0.063 | +0.134 |
| **pooled 6-param (5 features)** | **6** | **0.1759** | **+0.080** | **+0.081** | **+0.009** | +0.150 |
| slope x fund interaction | 13 | 0.1810 | +0.065 | +0.228 | -0.056 | **+0.023** |
| separate model per fund | 15 | 0.2156 | +0.075 | +0.186 | -0.144 | +0.183 |

**Every attempt to add flexibility loses.** The 15-parameter version spends more than half
the available effective sample size, scores the worst MAE of the four, and leaves all three
funds biased rather than two. The slope interaction fixes BND and makes VTI worse, which is
what fitting a level shift as though it were a slope looks like.

**The 6-parameter specification wins outright on MAE and cuts VTI's bias from +0.215 to
+0.081 and VXUS's to +0.009**, effectively zero. It is the same specification Stage 10a's
variant sweep already preferred. Stage 12 did not find a new model, it found that the model
already chosen was also the answer to a question asked later.

### What gets published

The 6-parameter model, with a **measured offset** printed beside the raw forecast and
labelled as an observation from the test window rather than a fitted parameter, because
that is what it is and a reader who mistakes one for the other will over-trust it.

---

## 3. Which assumption the answer rests on

Listing assumptions is easy and nearly useless: a list implies they matter equally. They do
not. Each was swung once against the headline that would actually trigger action, **BND's
95% upper bound**, since BND is the fund closest to amber.

| assumption | alternative | headline | swing |
|---|---|---|---|
| **Regime** | training window instead of test window | 1.73pp | **0.31pp** |
| Bias adjustment | measured offset instead of raw | 1.89pp | 0.15pp |
| Model specification | 11-param instead of 6-param | 2.14pp | 0.10pp |
| Confidence level | 99% instead of 95% | 2.12pp | 0.07pp |
| Interval shape | Gaussian instead of empirical | 2.03pp | 0.02pp |

Published value: **2.04pp**.

**Regime beats specification roughly three to one and interval shape by twenty to one.**

That ordering is uncomfortable and it is the most useful thing in this document. Stage 09
argued about features, Stage 10a about specification, Stage 10b about lag families, Stage
11 about interval construction. **Those are the third, fourth and fifth largest levers.**
The largest is the length and character of the data window, which no stage has addressed
because it is not a modelling choice.

It is also the same fix Stage 11 identified for a different problem: the block bootstrap
degenerates at the block length this target requires, and only a longer window repairs it.
Two independent lines of reasoning now point at the same next step.

---

## 4. What the monitor publishes

| Fund | drift today | projected 21 days | 95% interval | bias-adjusted | band |
|---|---|---|---|---|---|
| VTI | 0.56pp | 0.64pp | [0.33, 1.04] | 0.56pp | green |
| VXUS | 1.15pp | 0.99pp | [0.68, 1.39] | 0.98pp | green |
| BND | 1.70pp | 1.64pp | [1.33, 2.04] | 1.49pp | green |

**No fund needs attention this month, and the statement survives every assumption tested.**
Across all five swings BND's upper bound stays between **1.73pp and 2.14pp** against an
amber line of **3pp**. Against a persistence baseline the model improves MAE by **25.8%**.

`monitor_table` reports `worst_case_band` from the upper bound rather than the point
forecast. A point of 1.64 and an upper bound of 2.04 are the same decision today and stop
being the same decision the moment either crosses 3, and a reader shown only the point
cannot tell how close that is.

---

## 5. Two readers, two artifacts

This is the part of the stage that is a design decision rather than a measurement.

| | firm principal | Dana |
|---|---|---|
| Decides | whether to trust the model | whether to raise a fund this month |
| Needs | effective sample size, the bias that cannot be fixed, the interval being a floor | a number, a band, an action |
| Gets | `reports/final_report.md` | `reports/drift_monitor_current.csv` |

**A caveat Dana cannot act on hides the number she can.** She works in Excel and does not
run scripts, so the CSV contains no MAE, no residual, no interval half-width. It opens by
double click and has an `action` column.

**A number without caveats is not something the principal can sign off.** The report keeps
all of them, including the ones that make the model look weaker, because a principal who
discovers a caveat later stops trusting the whole monitor.

### Why a written report rather than a deck

The principal's question is "should I believe this", and the honest answer runs to several
paragraphs of assumption. A deck forces that into bullets and the compression is exactly
where the meaning lives. A report also survives being re-read in three months by someone
checking whether the numbers still hold, which is the real review pattern for a monitor
that runs continuously. The deck-shaped need is Dana's, and a spreadsheet serves it better
than slides would.

### The decision log

`reports/decision_log.json` records six choices across Stages 06, 07, 10a and 12 with
rationale, alternatives rejected, and risk. `DecisionLog.add` requires `alternatives` and
`risk` rather than defaulting them to empty, because a logged decision with no alternative
recorded is one nobody can audit, which is the failure the log exists to prevent.

---

## 6. Assumptions, and what breaks if they are wrong

| Assumption | If wrong |
|---|---|
| The next month resembles the last twelve | The largest single error source, worth 0.31pp on the headline. One year, one regime, no market stress |
| The measured offset carries forward | Worth 0.15pp. It is an observation from one window, not a parameter, and may not persist |
| 42 test dates can bound their own uncertainty | Stage 11 showed they cannot at a 21-day timescale. Every interval is a **floor** |
| Errors come from one distribution | BND's residuals are the least well behaved, and BND is the fund closest to amber |
| Persistence is the right baseline | The 25.8% improvement claim depends on it |

### Sensitive to

- **the length of the data window**, more than to any modelling choice available;
- **which fund is asked about**: BND still carries +0.150pp of bias under the recommended
  model, and is the fund nearest amber.

### Not sensitive to

- **the model specification**, at 0.10pp;
- **the interval shape**, at 0.02pp;
- **the threshold unit**, closed in Stage 11 at 25.8% against 25.6%.

---

## 7. Production monitoring

| Risk | What to watch |
|---|---|
| Regime change, the dominant risk | Realized volatility against the 13% / 17% / 4% band; re-estimate outside it |
| The published offset stops applying | Rolling per-fund mean residual; alert if it moves outside the interval quoted here |
| The interval is a floor | Re-run Stage 11's block sweep as the window lengthens; a 21-day block becomes usable near 200 test dates |
| A stale report circulates | `final_report.md` prints its own data date; anything not matching the latest pipeline run is out of date |
| Vendor gaps return | `close_was_filled`, built in Stage 09 and currently constant; alert if it stops being |

---

## 8. What Stage 12 changed, and what it did not

**Changed.** The project has a deliverable, split by audience. Stage 11's handoff
instruction is corrected in place, with the amendment recorded in `docs/evaluation.md`
rather than silently dropped. The project's priorities are reordered by measurement: the
data window before the model.

**Not changed.** No data, no thresholds, no features. Stage 12 packages what exists; it
does not adjust it. The one modelling decision taken here, preferring the 6-parameter
specification, ratifies a choice Stage 10a's variant sweep had already made on independent
evidence.
