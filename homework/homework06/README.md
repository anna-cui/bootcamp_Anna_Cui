# Homework 06 - Data Preprocessing

**Course:** FRE 5040 Applied Financial Engineering
**Stage:** 06 - Data Preprocessing
**Submission notebook:** `homework06_data-preprocessing_submission.ipynb`

## What is in this folder

```
homework06/
  src/cleaning.py                                  reusable cleaning functions
  data/raw/sample_data.csv                         the provided raw dataset (7 x 6)
  data/processed/sample_data_cleaned.csv           cleaned, real units - the deliverable
  data/processed/sample_data_cleaned.parquet       same data, dtypes preserved
  data/processed/sample_data_scaled_minmax.csv     cleaned and 0-1 scaled, for modeling
  homework06_data-preprocessing_submission.ipynb   the walkthrough
  README.md
```

## Cleaning strategy

The dataset arrives with four separate problems, and they are handled in an order that
matters. Running these steps in a different sequence produces different numbers.

### 1. Repair disguised encodings first

`city` contains the literal string `'Unknown'`. Until that is converted to a real `NaN`,
pandas reports `city` as 0% missing and every count downstream is wrong. `'SF'` and
`'San Francisco'` are merged for the same reason - two spellings of one city otherwise
count as two cities.

`zipcode` is loaded with `dtype={'zipcode': 'string'}`. Zip codes are labels, not
quantities: read as integers they lose leading zeros and invite meaningless arithmetic.

### 2. Drop what is too sparse to trust - columns, then rows

The threshold is **50% present**, applied with `drop_missing(threshold=0.5, ...)`.

| | present | outcome |
|---|---|---|
| `extra_data` | 28.6% (2 of 7) | dropped - two observations cannot support a column |
| `income` | 57.1% (4 of 7) | kept - the most interesting variable in the set |
| row 5 | 40% (2 of 5) | dropped - no age, no income, city was `'Unknown'` |

Columns are dropped before rows deliberately. Once `extra_data` is gone, each row is
judged against 5 columns instead of 6, so no row is punished for a blank in a column
nobody is keeping.

The 50% figure is a judgement, not a rule. It happens to separate `extra_data` from
`income` cleanly; at 0.6 it would have taken `income` too. The gap between 28.6% and
57.1% is what makes the choice safe here, not the number itself.

### 3. Fill what is left - median, computed after the drops

`fill_missing_median` replaces the remaining numeric blanks with each column's median.
Median rather than mean because on six rows one extreme value moves the mean a long way
and the median barely at all. Filling assumes the blanks are **MCAR or MAR** (missing
completely at random, or at random given the other columns); if they are **MNAR** (missing
*because* of the value itself, say high earners declining to report income), no fill
recovers the pattern and the median hides it. The medians are computed on the surviving rows, so they
describe the data actually being kept.

Exactly three cells are imputed: `income` in rows 1 and 4, `score` in row 2. `age` is
never imputed - its only blank was in the row that was dropped.

**What this costs:** `income`'s standard deviation falls from about 7,071 to 5,502, a 22%
drop, because two of six values now sit exactly at the centre. Any confidence interval
built on `income` downstream will be too narrow.

### 4. Scale last, and into a separate file

`normalize_data` supports `'minmax'` (0-1) and `'standard'` (mean 0, population std 1,
matching scikit-learn's `StandardScaler` with `ddof=0`). Scaling is a preparation for a
particular model, not a fact about the data, so the canonical cleaned file keeps dollars
as dollars and the scaled version lives beside it.

## Assumptions and what breaks if they are wrong

| Assumption | If it is wrong |
|---|---|
| `extra_data` carries no signal | Its two values were the point, and I deleted the answer |
| `income` is missing at random (MCAR or MAR) | Missingness tracks income level (MNAR), and median filling erases the pattern |
| `'Unknown'` means missing | It was a deliberate category, and meaning became absence |
| `zipcode` is an identifier | Nothing - this one is safe |
| 50% is a sensible sparsity cut | A different cut keeps or kills `income` |

`'Beverly'` at zip 90210 is almost certainly `'Beverly Hills'` and was deliberately left
alone: correcting it means guessing the source's intent from one adjacent field, and a
guess dressed as a repair is worse than a known oddity.

## How to reproduce

```bash
conda activate bootcamp_env
cd homework/homework06
jupyter lab
```

Open `homework06_data-preprocessing_submission.ipynb`, Run All. The notebook regenerates
`data/raw/sample_data.csv` if it is absent and rewrites everything in `data/processed/`.
