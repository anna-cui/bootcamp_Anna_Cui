# reports/ - the stakeholder-facing layer

## Two readers, two artifacts

**The firm principal** decides whether this model is trusted enough to change how the
portfolio is watched. That decision needs the caveats: the effective sample size, the bias
that cannot be specified away, the interval being a floor rather than a bound.
`final_report.md` is written for that reader.

**Dana**, the client-service associate, decides whether to raise a fund with the principal
this month. She works in Excel and does not run scripts. That decision needs a number, a
band and an action. `drift_monitor_current.csv` opens by double click and contains no model
vocabulary: no MAE, no residual, no interval half-width, just today's drift, the projection,
the worst case inside the published band, and what to do.

Splitting them is the point of this stage. A caveat Dana cannot act on hides the number she
can, and a number without caveats is not something the principal can sign off.

## Why a written report rather than a slide deck

The principal's question is "should I believe this", and the honest answer runs to several
paragraphs of assumption and caveat. A deck would force that into bullets, and the
compression is exactly where the meaning would go. A written report also survives being
re-read in three months by someone checking whether the numbers still hold, which is the
real review pattern for a monitor that runs continuously.

The deck-shaped need belongs to Dana, and a spreadsheet serves it better than slides do.

## Contents

| File | Reader | What it answers |
|---|---|---|
| `final_report.md` | firm principal | Should this model be trusted, and what would change the answer |
| `drift_monitor_current.csv` | Dana | Which funds need attention this month |
| `decision_log.json` | reviewer or successor | Why each choice was made, and what was rejected |
| `images/report_drift_and_forecast.png` | both | Is drift trending, and where does it go next |
| `images/report_tornado.png` | principal | Which assumption is worth arguing about |
| `images/report_bias_by_fund.png` | principal | How much of Stage 11's bias the smaller model removes |

Stage 08 to 11 diagnostic images also live in `images/` under their own prefixes
(`eda_`, `model_`, `ts_`, `eval_`). Those are working figures for the analyst, not
stakeholder artifacts, and the `report_` prefix marks the difference.

## Reproducing

`notebooks/delivery.ipynb`, run top to bottom, regenerates every file listed above.
`notebooks/project_pipeline.ipynb` runs the same section as part of the full chain.

The pipeline pulls a **rolling one-year window**, so a run months from now will move these
figures. The ones quoted in `final_report.md` are from **2026-08-28**, and that
date is printed in the report itself so a stale copy is detectable.
