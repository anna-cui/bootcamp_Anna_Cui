# reports/ - who each artifact is for

## Audience

Two readers, two different decisions, and that is why there are two artifacts rather than
one document with a summary at the top.

**The firm principal** decides whether this model is trusted enough to change how the
portfolio is watched. That decision needs the caveats: the effective sample size, the
bias that cannot be specified away, the interval being a floor. `final_report.md` is
written for that reader.

**Dana**, the client-service associate, decides whether to raise a fund with the principal
this month. She works in Excel and does not run scripts. That decision needs a number, a
band and an action. `drift_monitor_current.csv` is written for that reader, opens by double
click, and contains no model vocabulary.

## Why a written report rather than a deck

The principal's question is "should I believe this", and the honest answer runs to several
paragraphs of assumption and caveat. A deck would force that into bullets, and the
compression is exactly where the meaning would go. A written report is also the format
that survives being read three months from now by someone deciding whether the numbers
still hold, which is the actual review pattern for a monitor.

The deck-shaped need is Dana's, and a spreadsheet serves it better than slides do.

## Contents

| File | Reader | What it answers |
|---|---|---|
| `final_report.md` | firm principal | Should this model be trusted, and what would change the answer |
| `drift_monitor_current.csv` | Dana | Which funds need attention this month |
| `decision_log.json` | reviewer or successor | Why each choice was made and what was rejected |
| `images/drift_history_and_forecast.png` | both | Is drift trending, and where does it go next |
| `images/specification_accuracy_vs_bias.png` | principal | Which model, given accuracy and bias both matter |
| `images/tornado_assumptions.png` | principal | Which assumption is worth arguing about |
| `images/bias_by_fund.png` | principal | How much of the flagged bias the smaller model removes |

## Reproducing

`homework12_results-reporting-delivery-design_submission.ipynb`, run top to bottom,
regenerates every file listed above. Data is a rolling one-year window, so figures move
between runs; the ones quoted in `final_report.md` are from
2026-08-28.
