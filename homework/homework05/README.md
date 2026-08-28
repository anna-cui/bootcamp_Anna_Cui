# Homework 05 — Data Storage

A reproducible storage layer: environment-driven paths, CSV and Parquet round
trips, reload validation, and IO utilities that route by file suffix.

## Data Storage

### Folder structure

| Folder | Holds | Rule |
|---|---|---|
| `data/raw/` | Inputs exactly as acquired, plus the source JSON | **Immutable.** Never edited by hand; a new version gets a new filename |
| `data/processed/` | Derived tables written by code | Deletable and re-creatable by re-running the notebook |

### Formats used, and why

- **CSV in `raw/`** — human-readable, diffable in git, universally accepted.
  Costs: no schema, no dtypes, no nested structure. A date column returns as
  text unless the reader is explicitly told to parse it.
- **Parquet in `processed/`** — columnar, compressed, preserves dtypes, fast to
  read. Costs: binary, not diffable, needs an engine (`pyarrow` here).

Rule of thumb: CSV for small exchange files, Parquet for analysis-ready tables.

### How the code reads and writes

Paths come from `.env` via `os.getenv`, never hardcoded:

    DATA_DIR_RAW=data/raw
    DATA_DIR_PROCESSED=data/processed

`write_df(df, path)` and `read_df(path)` route on the file suffix. They create
missing parent directories, refuse to write an empty DataFrame, raise a clear
message when the Parquet engine is absent, and parse any column whose name
ends in `date`.

### Validation on reload

Shape equality · required columns present · `price` numeric · `date` datetime ·
values numerically equal to the original.

## Changes made to the starter

1. **Added a random seed.** The starter generated prices with no seed, so every
   run produced different data under a different filename.
2. **`read_df` no longer reads the file twice** — the header is read once and
   reused to find date columns.
3. **`read_df` parses any `*date` column**, not only one named exactly `date`.
4. **`write_df` refuses an empty frame**, which otherwise saves silently.

## Files

    data/raw/sample_<YYYYMMDD-HHMM>.csv           the CSV round trip
    data/raw/unstructured_<...>.json              nested source of truth
    data/raw/nested_<...>.csv                     nested data, flattened by CSV
    data/processed/sample_<...>.parquet           the Parquet round trip
    data/processed/nested_<...>.parquet           nested data, structure preserved
