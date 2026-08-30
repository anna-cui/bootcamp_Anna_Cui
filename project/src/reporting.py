"""Delivery design - turning a fitted model into something a person acts on. Stage 12.

Every prior module in `src/` answered a question about the data. This one
answers a question about the **reader**, and the two have different correct
answers. Stage 11 ended with a forecast, an interval, and a named bias. None of
those is a decision. This module is the layer that turns them into one.

Three things drive the design.

**The audience is split and the split is real.** The firm principal decides
whether the model is trusted; Dana reads one fund on one day and acts. The
principal needs the caveats, because they are deciding whether to believe the
thing. Dana needs a number and a colour, because she is deciding whether to
send an email, and a caveat she cannot act on is noise that hides the number
she can. Two artifacts, not one document with a summary at the top.

**A bias you cannot fit is a bias you must publish.** Stage 11 recommended
correcting the per-fund bias with interactions. `specification_sweep` was
written to do that and instead established that it cannot be done: an OLS fit
with fund dummies drives the in-sample per-fund residual mean to zero by
construction, so every point of the *test* bias is out-of-sample drift that no
re-specification can see. `regime_shift` measures the drift directly. The
correct response is an adjusted point forecast and an interval wide enough to
carry the rest, not a bigger model.

**A sensitivity table is only honest if the reader can see which assumption
moved the answer.** `sensitivity_table` records deltas against one baseline and
`tornado_data` sorts them by absolute swing, so the assumption that matters
appears at the top rather than wherever it happened to be written down.

One structural finding is worth recording here because it is invisible from the
feature list: `abs_drift_rel` is `abs_drift` divided by the fund's target
weight, which makes it **already** the per-fund interaction of `abs_drift`.
`fund_interactions` will therefore refuse to build that particular term, and a
per-fund model cannot contain both columns at once. That is a property of the
Stage 09 feature set, not a bug, and `fund_interactions` raises rather than
letting a rank-deficient design matrix through.

Nothing here modifies its input, matching every other module in `src/`.
"""

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .utils import AMBER_PP, RED_PP

# The order every stakeholder-facing table uses. Largest target weight first,
# because that is the order the principal thinks about the portfolio in, and it
# should not change between artifacts.
DISPLAY_ORDER = ["VTI", "VXUS", "BND"]

# One colour per fund, defined once. The same argument as `traffic_light`: a
# reader who learns the mapping on one chart must not relearn it on the next, and
# that only holds if the mapping lives in one place.
#
# Checked against a colour-vision validator rather than chosen by eye. The
# earlier values (#1f4e79 / #c77b30 / #4a7c59, used by the Stage 12 and 13
# charts) failed on two counts: the blue sat below the readable lightness band,
# and the blue and green fell under the chroma floor, so both read as grey. The
# green was also only just separable from the orange under protanopia. Moving
# the green toward teal is what fixes that pair: red-green confusion is the
# common deficiency, and teal escapes it where a leaf green cannot.
FUND_COLOR = {"VTI": "#3d7fd6", "VXUS": "#c26a1c", "BND": "#12907f"}

# Status colours are reserved for the drift bands and never reused for a fund.
# Always paired with the band's name in text, so the state is never carried by
# colour alone.
BAND_COLOR = {"green": "#12907f", "amber": "#c26a1c", "red": "#c0392b"}


# --- audience-facing formatting ------------------------------------------

def traffic_light(drift_pp, amber=AMBER_PP, red=RED_PP):
    """Map a drift in percentage points to the band the monitor publishes.

    Thin on purpose. It exists so the band is computed in exactly one place:
    the memo, the CSV and the chart legend disagreeing about where amber starts
    is the kind of error a reader cannot detect and cannot recover from.
    """
    v = abs(float(drift_pp))
    if v >= red:
        return "red"
    if v >= amber:
        return "amber"
    return "green"


def monitor_table(forecast, current_drift, tickers, per_fund_bias=None,
                  amber=AMBER_PP, red=RED_PP):
    """The table Dana opens in Excel: one row per fund, no model vocabulary.

    Takes the forecast frame `prediction_interval` returns and attaches what a
    reader actually needs - today's drift, the projected drift, the band each
    falls in, and the worst case inside the published interval.

    `worst_case_band` is the column that earns this function. A point forecast
    of 1.6pp and an upper bound of 2.0pp are the same decision today, but they
    stop being the same decision the moment either crosses 3, and a reader who
    sees only the point estimate cannot tell how close that is.

    `per_fund_bias` applies the Stage 11 correction when supplied. It is a
    measured offset from the test window rather than a fitted parameter, so it
    is optional and the uncorrected column is kept beside it.
    """
    if len(forecast) != len(tickers) or len(forecast) != len(current_drift):
        raise ValueError("forecast, current_drift and tickers must align")

    out = pd.DataFrame({
        "fund": list(tickers),
        "drift_today_pp": np.asarray(current_drift, dtype=float),
        "projected_21d_pp": forecast["point"].to_numpy(dtype=float),
        "lower_95_pp": forecast["lo"].to_numpy(dtype=float),
        "upper_95_pp": forecast["hi"].to_numpy(dtype=float),
    })
    if per_fund_bias is not None:
        out["projected_adjusted_pp"] = (
            out["projected_21d_pp"] - out["fund"].map(per_fund_bias).astype(float))
    out["band_today"] = out["drift_today_pp"].map(lambda v: traffic_light(v, amber, red))
    out["band_projected"] = out["projected_21d_pp"].map(lambda v: traffic_light(v, amber, red))
    out["worst_case_band"] = out["upper_95_pp"].map(lambda v: traffic_light(v, amber, red))
    out["action"] = np.where(out["worst_case_band"] == "green", "no action",
                             "review with principal")
    order = {t: i for i, t in enumerate(DISPLAY_ORDER)}
    out = out.sort_values("fund", key=lambda s: s.map(order).fillna(99))
    return out.reset_index(drop=True).round(4)


# --- the bias question ----------------------------------------------------

def fund_interactions(df, base_features, interact, dummies=("ticker_VTI", "ticker_VXUS")):
    """Add per-fund interaction columns, refusing the ones that are redundant.

    Interacting a feature with the fund dummies is the standard fix for a
    coefficient that should differ by group. On this feature set one such term
    is already present under another name: `abs_drift_rel` is `abs_drift`
    divided by the target weight, so it is a fixed linear combination of
    `abs_drift` interacted with the three funds. Adding the explicit
    interaction alongside it makes the design matrix singular.

    Raising here rather than in `fit_ols` puts the error next to the reason.
    """
    redundant = {"abs_drift"} if "abs_drift_rel" in base_features else set()
    bad = redundant.intersection(interact)
    if bad:
        raise ValueError(
            f"{sorted(bad)} cannot be interacted with the fund while "
            "'abs_drift_rel' is in the model: abs_drift_rel is abs_drift "
            "divided by the target weight, so it is already that interaction. "
            "Drop abs_drift_rel first, or leave this term out.")

    out = df.copy()
    names = list(base_features)
    for col in interact:
        for dummy in dummies:
            new = f"{col}_x_{dummy.split('_')[-1]}"
            out[new] = out[col].to_numpy() * out[dummy].to_numpy()
            names.append(new)
    return out, names


def regime_shift(train, test, target, group="ticker"):
    """How far the target itself moved between the two windows.

    This is the diagnostic that decides whether a measured test bias is worth
    re-specifying for. A model fitted with group dummies has zero in-sample
    bias per group by construction, so any out-of-sample bias is either the
    features failing or the world moving. Comparing the raw target means
    separates the two without fitting anything.
    """
    rows = []
    for name in sorted(set(train[group]) | set(test[group])):
        a = float(train.loc[train[group] == name, target].mean())
        b = float(test.loc[test[group] == name, target].mean())
        rows.append({group: name, "train_mean": a, "test_mean": b, "shift": b - a})
    rows.append({group: "ALL", "train_mean": float(train[target].mean()),
                 "test_mean": float(test[target].mean()),
                 "shift": float(test[target].mean() - train[target].mean())})
    return pd.DataFrame(rows).set_index(group).round(4)


def specification_sweep(specs, group_labels, target_test):
    """Score competing specifications on one split, with per-group bias.

    `specs` maps a name to that specification's test residuals and parameter
    count, so every candidate is scored on identical rows and the comparison is
    between the specifications rather than between how each was run.

    Per-group bias is reported beside pooled MAE because a specification can
    improve one and worsen the other, and on this project several do. A single
    ranking column would hide exactly the trade-off the choice turns on.
    """
    labels = np.asarray(group_labels)
    rows = []
    for name, spec in specs.items():
        r = np.asarray(spec["resid"], dtype=float)
        if len(r) != len(labels):
            raise ValueError(f"{name}: residual length does not match group labels")
        row = {"spec": name, "k": int(spec["k"]),
               "mae": float(np.mean(np.abs(r))),
               "rmse": float(np.sqrt(np.mean(r ** 2))),
               "bias": float(np.mean(r))}
        for g in DISPLAY_ORDER:
            m = labels == g
            if m.any():
                row[f"bias_{g}"] = float(r[m].mean())
        rows.append(row)
    return pd.DataFrame(rows).set_index("spec").round(4)


# --- sensitivity ----------------------------------------------------------

def sensitivity_table(baseline, scenarios, headline):
    """Deltas against one baseline, with the assumption named in every row.

    `scenarios` maps an assumption label to a dict carrying at least
    `headline`. The delta and percent columns are computed here rather than by
    each caller so a sign convention cannot drift between artifacts.
    """
    if headline not in baseline:
        raise KeyError(f"baseline has no {headline!r}")
    base = float(baseline[headline])
    rows = [{"scenario": "baseline", "assumption": baseline.get("assumption", "as published"),
             headline: base, "delta": 0.0, "pct_change": 0.0}]
    for name, s in scenarios.items():
        if headline not in s:
            raise KeyError(f"scenario {name!r} has no {headline!r}")
        v = float(s[headline])
        rows.append({"scenario": name, "assumption": s.get("assumption", ""),
                     headline: v, "delta": v - base,
                     "pct_change": 100.0 * (v - base) / base if base else np.nan})
    return pd.DataFrame(rows).round(4)


def tornado_data(baseline_value, swings):
    """Order assumptions by how far each moves the headline, widest first.

    A tornado chart is only worth drawing if the bars are sorted, because the
    sort *is* the finding: it says which assumption the reader should argue
    about. `swings` maps a label to (low, high) headline values.
    """
    rows = []
    for label, (lo, hi) in swings.items():
        lo, hi = float(lo), float(hi)
        rows.append({"assumption": label, "low": lo, "high": hi,
                     "low_delta": lo - baseline_value,
                     "high_delta": hi - baseline_value,
                     "swing": abs(hi - lo)})
    return (pd.DataFrame(rows).sort_values("swing", ascending=False)
            .reset_index(drop=True).round(4))


# --- decisions ------------------------------------------------------------

class DecisionLog:
    """Every modelling choice with its rationale, alternatives and risk.

    The lecture's version, with one field added and one rule changed. The added
    field is `stage`, because on this project the choices span twelve stages
    and a reviewer's first question is where a decision was made. The changed
    rule is that `alternatives` and `risk` are required rather than optional: a
    logged decision with no alternative recorded is a decision nobody can
    audit, which is the failure the log exists to prevent.
    """

    FIELDS = ["stage", "step", "decision", "rationale", "alternatives", "risk", "impact"]

    def __init__(self):
        self.entries = []

    def add(self, stage, step, decision, rationale, alternatives, risk, impact=""):
        if not str(alternatives).strip():
            raise ValueError(f"{step!r}: record the alternative that was rejected")
        if not str(risk).strip():
            raise ValueError(f"{step!r}: record what goes wrong if this is the wrong call")
        self.entries.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "stage": stage, "step": step, "decision": decision,
            "rationale": rationale, "alternatives": alternatives,
            "risk": risk, "impact": impact})
        return self

    def to_df(self):
        if not self.entries:
            return pd.DataFrame(columns=["timestamp"] + self.FIELDS)
        return pd.DataFrame(self.entries)

    def save(self, path="reports/decision_log.json"):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.entries, indent=2), encoding="utf-8")
        return p


def export_for_excel(df, path, index=False):
    """Write a CSV the end user opens directly, and say where it went.

    Dana does not run scripts, so the last mile of this project is a file with
    a stable name in a known folder. Parquet is the right format for the
    pipeline and the wrong one here, and that difference is the whole point of
    this stage.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=index)
    return p
