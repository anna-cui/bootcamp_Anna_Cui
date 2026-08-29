"""Uncertainty, scenarios and subgroup diagnostics - Stage 11.

Stage 10a produced a model and then refused to quote a single interval from it.
The reason was specific: a 21-day forward target makes consecutive rows share 20
of their 21 days, so 501 training rows carry roughly 24 independent
observations, and every standard error the regression reports is computed as
though there were 501. This module is the attempt to say something honest about
uncertainty anyway.

The central tool is the **moving block bootstrap**. Ordinary bootstrap
resampling draws rows independently, which assumes they *are* independent. On
this data they are not, so an iid bootstrap inherits exactly the error that made
Stage 10a's p-values unusable. Resampling contiguous blocks of dates instead
keeps neighbouring rows together, so the dependence survives the resampling.

**`block_length_sweep` is the function that matters most here**, and not for the
reason it was written. A block bootstrap needs the block to be at least as long
as the dependence, which here means 21 days, and it needs enough distinct block
positions to actually resample. With a 42-day test window those two requirements
are in direct conflict: at block 21 there are only 22 possible starting
positions, and at block 42 there is exactly one, so the "interval" collapses to
a point. The sweep makes that visible instead of returning a confident number
from a degenerate estimator.

Two further distinctions the lecture draws, both of which change what the
monitor may promise:

**A confidence interval and a prediction interval answer different questions.**
A CI asks where the true average relationship sits, and narrows as data
accumulates. A PI asks where one new observation will land, and barely narrows
because a single point brings its own noise. On this project they differ by a
factor of eleven. Dana reads one fund on one day, so the PI is the honest one.

**A Gaussian interval and an empirical one differ in the tail, not the middle.**
Which way they differ is a property of the residuals and has to be measured
rather than assumed.

Nothing here modifies its input, matching every other module in `src/`.
"""

import numpy as np
import pandas as pd
from scipy import stats

DEFAULT_BOOT = 2000
DEFAULT_SEED = 111


# --- metrics -------------------------------------------------------------

def mae(residuals):
    """Mean absolute error, from residuals rather than from a pair of vectors."""
    return float(np.abs(np.asarray(residuals, dtype=float)).mean())


def rmse(residuals):
    """Root mean squared error."""
    r = np.asarray(residuals, dtype=float)
    return float(np.sqrt((r ** 2).mean()))


def bias(residuals):
    """Mean residual: positive means the model predicts too low.

    Reported alongside MAE throughout, because they fail differently. A large
    MAE with zero bias is noise. A large MAE that is mostly bias is a model
    that is wrong in a fixed direction, which is both worse and easier to fix.
    """
    return float(np.asarray(residuals, dtype=float).mean())


# --- bootstraps ----------------------------------------------------------

def iid_bootstrap(residuals, stat_fn=mae, n_boot=DEFAULT_BOOT, seed=DEFAULT_SEED,
                  level=0.95):
    """Ordinary bootstrap: resample rows independently, with replacement.

    Included as the comparison, not as the recommendation. Drawing rows
    independently assumes they are independent, which on a panel with a
    21-day overlapping target they are not. The interval it returns is the one
    you get by making the same assumption that made Stage 10a's p-values
    unusable.
    """
    r = np.asarray(residuals, dtype=float)
    if len(r) < 10:
        raise ValueError("too few residuals to bootstrap")
    rng = np.random.default_rng(seed)
    n = len(r)
    draws = np.array([stat_fn(r[rng.integers(0, n, n)]) for _ in range(n_boot)])
    a = (1 - level) / 2
    lo, hi = np.percentile(draws, [100 * a, 100 * (1 - a)])
    return {"point": stat_fn(r), "mean": float(draws.mean()),
            "lo": float(lo), "hi": float(hi), "width": float(hi - lo),
            "n_boot": n_boot, "method": "iid"}


def block_bootstrap(frame, residuals, stat_fn=mae, block=21, date_col="date",
                    n_boot=DEFAULT_BOOT, seed=DEFAULT_SEED, level=0.95):
    """Moving block bootstrap over contiguous dates, keeping all groups per date.

    Blocks are drawn over *dates*, and every row sharing a date travels with it,
    so the cross-sectional structure of a fund-day panel is preserved along with
    the time dependence.

    `block` should be at least as long as the dependence being modelled. For a
    21-day forward target that means 21.

    Returns `n_distinct_starts` and `blocks_per_draw` because **they are how you
    tell whether the interval means anything**. With `n_distinct_starts` close
    to 1 every replicate is nearly the original sample and the interval is
    narrow for the wrong reason. `block_length_sweep` exists to show that.
    """
    r = np.asarray(residuals, dtype=float)
    if date_col not in frame.columns:
        raise KeyError(f"column {date_col!r} not found")
    if len(frame) != len(r):
        raise ValueError("frame and residuals have different lengths")
    if block < 1:
        raise ValueError("block must be at least 1 day")

    dates = np.sort(pd.to_datetime(frame[date_col]).unique())
    n_dates = len(dates)
    stamps = pd.to_datetime(frame[date_col]).to_numpy()
    rows_for_date = [np.where(stamps == d)[0] for d in dates]

    block = min(block, n_dates)
    n_blocks = int(np.ceil(n_dates / block))
    n_starts = max(n_dates - block, 0) + 1

    rng = np.random.default_rng(seed)
    draws = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, n_starts, n_blocks)
        idx = np.concatenate([np.concatenate(rows_for_date[s:s + block])
                              for s in starts])
        draws[b] = stat_fn(r[idx])

    a = (1 - level) / 2
    lo, hi = np.percentile(draws, [100 * a, 100 * (1 - a)])
    return {"point": stat_fn(r), "mean": float(draws.mean()),
            "lo": float(lo), "hi": float(hi), "width": float(hi - lo),
            "block": int(block), "n_dates": int(n_dates),
            "n_distinct_starts": int(n_starts), "blocks_per_draw": int(n_blocks),
            "n_boot": n_boot, "method": "block"}


def block_length_sweep(frame, residuals, stat_fn=mae, blocks=(1, 3, 5, 10, 21, 42),
                       date_col="date", n_boot=DEFAULT_BOOT, seed=DEFAULT_SEED,
                       level=0.95):
    """Interval width against block length, with the degeneracy made visible.

    Read the `n_distinct_starts` column first and the `width` column second.

    Two effects run in opposite directions as the block grows. Longer blocks
    preserve more dependence, which should *widen* the interval, because
    dependent data carries less information than its row count suggests. But
    longer blocks also leave fewer distinct positions to draw from, which
    *narrows* it, because every replicate starts to look like the original
    sample. The second effect is an artifact and it wins at the long end.

    A width that falls as the block grows past some point is not evidence that
    the dependence is mild. It is evidence that the sample is too short to
    measure the dependence at that scale.
    """
    rows = []
    for b in blocks:
        out = block_bootstrap(frame, residuals, stat_fn, block=b,
                              date_col=date_col, n_boot=n_boot, seed=seed,
                              level=level)
        rows.append({"block_days": out["block"],
                     "blocks_per_draw": out["blocks_per_draw"],
                     "n_distinct_starts": out["n_distinct_starts"],
                     "lo": out["lo"], "hi": out["hi"], "width": out["width"]})
    return pd.DataFrame(rows).set_index("block_days").round(4)


# --- intervals -----------------------------------------------------------

def gaussian_intervals(residuals, level=0.95):
    """Confidence and prediction half-widths under a normal-error assumption.

    CI scales as sigma / sqrt(n); PI as sigma. The whole difference is that a
    single future observation carries its own noise, and averaging does not
    remove it. On a sample of any size the PI is therefore much the wider, and
    the ratio is roughly sqrt(n).
    """
    r = np.asarray(residuals, dtype=float)
    if len(r) < 3:
        raise ValueError("need at least 3 residuals")
    sigma = float(r.std(ddof=1))
    z = float(stats.norm.ppf(1 - (1 - level) / 2))
    n = len(r)
    return {"sigma": sigma, "n": n, "level": level,
            "ci_half_width": z * sigma / np.sqrt(n),
            "pi_half_width": z * sigma,
            "pi_over_ci": float(np.sqrt(n))}


def empirical_intervals(residuals, level=0.95):
    """Prediction half-width read from the residual percentiles themselves.

    Makes no distributional assumption, so comparing it against
    `gaussian_intervals` measures what the normal assumption is worth. The
    comparison belongs in the tail: the two agree in the middle almost by
    construction and separate where risk reports live.

    `skew` and `excess_kurtosis` are returned because the ratio alone does not
    say *why* the two differ, and the direction matters. Positive excess
    kurtosis means the normal understates the tail; negative means it overstates
    it, which is the safer way to be wrong.
    """
    r = np.asarray(residuals, dtype=float)
    if len(r) < 10:
        raise ValueError("too few residuals for an empirical quantile")
    a = (1 - level) / 2
    lo, hi = np.percentile(r, [100 * a, 100 * (1 - a)])
    return {"level": level, "lo": float(lo), "hi": float(hi),
            "pi_half_width": float((hi - lo) / 2),
            "skew": float(stats.skew(r)),
            "excess_kurtosis": float(stats.kurtosis(r))}


def interval_comparison(residuals, levels=(0.80, 0.95, 0.99)):
    """Gaussian against empirical at several levels, with the ratio.

    The ratio column is the answer to "what is the normality assumption worth".
    Above 1 the empirical band is wider, so the normal understates the tail.
    Below 1 the normal is conservative.
    """
    rows = []
    for lvl in levels:
        g = gaussian_intervals(residuals, lvl)
        e = empirical_intervals(residuals, lvl)
        rows.append({"level": lvl,
                     "gaussian_pi": g["pi_half_width"],
                     "empirical_pi": e["pi_half_width"],
                     "ratio": e["pi_half_width"] / g["pi_half_width"],
                     "gaussian_ci": g["ci_half_width"]})
    return pd.DataFrame(rows).set_index("level").round(4)


def prediction_interval(point_forecasts, residuals, level=0.95):
    """Attach an empirical prediction interval to point forecasts.

    Uses residual percentiles rather than a normal multiple, so the band
    inherits any asymmetry in the errors. This is the interval a monitor should
    publish: it answers "where will this fund actually be", not "where is the
    average relationship".
    """
    p = np.asarray(point_forecasts, dtype=float)
    e = empirical_intervals(residuals, level)
    return pd.DataFrame({"point": p, "lo": p + e["lo"], "hi": p + e["hi"]})


# --- subgroups and scenarios --------------------------------------------

def subgroup_report(frame, residuals, group="ticker", date_col="date",
                    block=10, n_boot=DEFAULT_BOOT, seed=DEFAULT_SEED,
                    level=0.95):
    """Per-group error and bias, each with a block-bootstrap interval.

    The bias interval is the point of this function. A group whose bias
    interval excludes zero is one the pooled model is **systematically** wrong
    about, which a pooled MAE cannot reveal and which no amount of extra data
    will fix, because it is not noise.

    `block` defaults to 10 rather than 21 here: a per-group slice has a third of
    the dates, so a 21-day block would leave almost no distinct positions. That
    is a compromise and it is stated rather than hidden.
    """
    if group not in frame.columns:
        raise KeyError(f"column {group!r} not found")
    r = np.asarray(residuals, dtype=float)
    if len(frame) != len(r):
        raise ValueError("frame and residuals have different lengths")

    rows = []
    for level_name, part in frame.groupby(group, sort=True):
        mask = (frame[group] == level_name).to_numpy()
        sub = frame.loc[mask].reset_index(drop=True)
        sub_r = r[mask]
        b = block_bootstrap(sub, sub_r, bias, block=block, date_col=date_col,
                            n_boot=n_boot, seed=seed, level=level)
        m = block_bootstrap(sub, sub_r, mae, block=block, date_col=date_col,
                            n_boot=n_boot, seed=seed, level=level)
        rows.append({group: level_name, "n": int(mask.sum()),
                     "mae": m["point"], "mae_lo": m["lo"], "mae_hi": m["hi"],
                     "bias": b["point"], "bias_lo": b["lo"], "bias_hi": b["hi"],
                     "bias_excludes_zero": bool(b["lo"] > 0 or b["hi"] < 0),
                     "bias_share_of_mae": abs(b["point"]) / m["point"]})
    return pd.DataFrame(rows).set_index(group).round(4)


def scenario_table(scenarios):
    """Collect scenario results into one frame with a consistent column order.

    `scenarios` maps a name to a dict of already-computed numbers. Deliberately
    thin: the value is in running every scenario through the same split and the
    same metric so the comparison is between the assumptions rather than
    between how each was run, and that discipline belongs in the caller.
    """
    if not scenarios:
        raise ValueError("no scenarios to tabulate")
    return pd.DataFrame(scenarios).T
