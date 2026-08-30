"""One pipeline task, runnable from the command line. Stage 15.

    python src/run_step.py --step score

The task is **score**: load the newest cleaned prices, load or fit the model, and write
the monitor table Dana reads. It was chosen out of the eight tasks in
`docs/orchestration_plan.md` for three reasons. It is the task whose output someone is
waiting for, so automating it is worth something. It is deterministic, so it can be
re-run safely after any failure upstream. And it sits at the point in the DAG where a
scheduled run either produces the deliverable or does not, which makes it the natural
thing to put a cron entry on.

Two design decisions are worth stating, because both are the opposite of the obvious.

**Retry wraps the read, not the whole task.** Retrying is only correct for *transient*
faults. Everything this task computes is deterministic: if `build_bundle` raises, it will
raise identically on the next attempt, and retrying a deterministic failure only delays
the error and buries it under noise. The one genuinely transient fault here is reading a
parquet while the upstream `clean` task is part-way through writing it, so the retry goes
exactly there and nowhere else.

**The output is written twice, on purpose.** A timestamped file is the checkpoint and the
audit trail; a stable-named copy is what Dana opens. Writing only the timestamped file
would mean she has to know today's date to find her spreadsheet; writing only the stable
name would destroy the history the monitoring plan depends on.

Both writes go through a temporary file and an atomic rename, so a reader never sees a
half-written CSV. That is the same race the retry exists for, handled from the other side.
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from src import service as sv
from src.utils import AMBER_PP, RED_PP, read_df

LOG = logging.getLogger("run_step")

DEFAULT_PROC = ROOT / "data" / "processed"
DEFAULT_RAW = ROOT / "data" / "raw"
DEFAULT_REPORTS = ROOT / "reports"
DEFAULT_MODEL = ROOT / "model" / "model.pkl"
DEFAULT_LOG = ROOT / "logs" / "run_step.log"


def retry(fn, *args, n_tries=3, delay=2.0, transient=(OSError,), **kwargs):
    """Call `fn`, retrying only on faults that can plausibly clear on their own.

    Linear backoff: 2s, 4s, 6s. The `transient` tuple is narrow by design. Catching
    `Exception` here would swallow a rank-deficient design matrix or a missing column and
    retry it three times before reporting it, which turns a clear error into a slow
    mysterious one.
    """
    last = None
    for attempt in range(1, n_tries + 1):
        try:
            return fn(*args, **kwargs)
        except transient as exc:
            last = exc
            if attempt == n_tries:
                break
            wait = delay * attempt
            LOG.warning("attempt %d/%d failed (%s: %s), retrying in %.0fs",
                        attempt, n_tries, type(exc).__name__, exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"{getattr(fn, '__name__', fn)} failed after {n_tries} attempts") from last


def _write_atomic(df, path, index=False):
    """Write a CSV via a temp file and an atomic rename.

    A reader that opens the file mid-write sees a truncated CSV and no error, which is
    the worst failure shape available: silently wrong rather than loudly broken.
    `os.replace` is atomic within a filesystem, so a reader sees either the old file or
    the new one.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=index)
    os.replace(tmp, path)
    return path


def _resolve_prices(prices_path=None):
    """Newest cleaned parquet, else newest raw CSV. Says which it picked."""
    if prices_path:
        p = Path(prices_path)
        if not p.exists():
            raise FileNotFoundError(f"--prices {p} does not exist")
        return p
    clean = sorted(DEFAULT_PROC.glob("prices_clean_*.parquet"))
    if clean:
        return clean[-1]
    raw = sorted(DEFAULT_RAW.glob("api_yfinance_*.csv"))
    if not raw:
        raise FileNotFoundError(
            "no price data found. Run the ingest and clean tasks first "
            "(notebooks/project_pipeline.ipynb).")
    return raw[-1]


def score(prices_path=None, model_path=DEFAULT_MODEL, reports_dir=DEFAULT_REPORTS,
          proc_dir=DEFAULT_PROC, amber=AMBER_PP, red=RED_PP, refit=False, stamp=None):
    """Produce the current drift monitor table. Returns a dict of what it did.

    Deterministic given its inputs, which is what makes it safe to re-run: the same
    prices and the same model give a byte-identical CSV.
    """
    t0 = time.perf_counter()
    LOG.info("step=score start refit=%s amber=%.2f red=%.2f", refit, amber, red)

    src_path = _resolve_prices(prices_path)
    LOG.info("input prices: %s", src_path.relative_to(ROOT) if ROOT in src_path.parents else src_path)

    # The one transient fault: reading while `clean` is still writing.
    def _load(p):
        return read_df(p) if str(p).endswith("parquet") else pd.read_csv(p)

    prices = retry(_load, src_path)
    prices["date"] = pd.to_datetime(prices["date"])
    LOG.info("loaded %d rows, %d funds, through %s",
             len(prices), prices["ticker"].nunique(),
             pd.Timestamp(prices["date"].max()).date())

    bundle, source = sv.get_bundle(prices, path=model_path, refit=refit)
    LOG.info("model %s: %s", source, sv.describe_bundle(bundle))

    matrix = sv.build_matrix(prices, bundle["target_weights"], bundle["horizon"])
    table = sv.monitor(bundle, matrix, amber=amber, red=red)

    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M")
    checkpoint = _write_atomic(table, Path(proc_dir) / f"monitor_{stamp}.csv")
    current = _write_atomic(table, Path(reports_dir) / "drift_monitor_current.csv")
    LOG.info("checkpoint -> %s", checkpoint.relative_to(ROOT))
    LOG.info("published   -> %s", current.relative_to(ROOT))

    worst = float(table["upper_95_pp"].max())
    flagged = table.loc[table["worst_case_band"] != "green", "fund"].tolist()
    for _, r in table.iterrows():
        LOG.info("  %-5s today %.2fpp  projected %.2fpp  upper %.2fpp  %s",
                 r["fund"], r["drift_today_pp"], r["projected_21d_pp"],
                 r["upper_95_pp"], r["worst_case_band"])
    if flagged:
        LOG.warning("ATTENTION: %s %s amber on the upper bound, review with the principal",
                    ", ".join(flagged), "reaches" if len(flagged) == 1 else "reach")
    else:
        LOG.info("no fund needs attention: widest upper bound %.2fpp against amber %.1fpp",
                 worst, amber)

    elapsed = time.perf_counter() - t0
    LOG.info("step=score done rows=%d elapsed=%.2fs", len(table), elapsed)
    return {"step": "score", "input": str(src_path), "model_source": source,
            "checkpoint": str(checkpoint), "published": str(current),
            "rows": len(table), "worst_case_pp": worst, "flagged": flagged,
            "elapsed_s": round(elapsed, 3), "stamp": stamp}


STEPS = {"score": score}


def _configure_logging(level, log_file):
    """Log to stdout so a scheduler captures it, and to a file so a person can read it."""
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        handlers=handlers, force=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="run_step.py",
        description="Run one Portfolio Drift Monitor pipeline task. "
                    "See docs/orchestration_plan.md for the full task list.")
    parser.add_argument("--step", default="score", choices=sorted(STEPS),
                        help="which task to run (default: score)")
    parser.add_argument("--prices", default=None,
                        help="path to a prices file; default is the newest in data/processed")
    parser.add_argument("--model", default=str(DEFAULT_MODEL), help="path to model.pkl")
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS))
    parser.add_argument("--proc-dir", default=str(DEFAULT_PROC))
    parser.add_argument("--amber", type=float, default=AMBER_PP)
    parser.add_argument("--red", type=float, default=RED_PP)
    parser.add_argument("--refit", action="store_true",
                        help="refit and overwrite the saved model instead of loading it")
    parser.add_argument("--stamp", default=None,
                        help="override the checkpoint timestamp; used by the "
                             "idempotency test so two runs write the same filename")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--log-file", default=str(DEFAULT_LOG))
    args = parser.parse_args(argv)

    _configure_logging(args.log_level, args.log_file)

    if args.red <= args.amber:
        LOG.error("red (%.2f) must be greater than amber (%.2f)", args.red, args.amber)
        return 2

    try:
        result = STEPS[args.step](
            prices_path=args.prices, model_path=Path(args.model),
            reports_dir=Path(args.reports_dir), proc_dir=Path(args.proc_dir),
            amber=args.amber, red=args.red, refit=args.refit, stamp=args.stamp)
    except Exception as exc:
        # Non-zero exit is how a scheduler learns the step failed. Logged with a
        # traceback so the log alone is enough to diagnose it.
        LOG.exception("step=%s FAILED: %s", args.step, exc)
        return 1

    LOG.info("result: %s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
