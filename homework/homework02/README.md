# Homework 02 — Tooling Setup

Practice run of the standard project scaffold, built here before creating the
real one in `project/`.

## What I practised
- Created and activated the `bootcamp_env` conda environment (Python 3.10) and
  installed `python-dotenv`, `numpy`, and `jupyterlab`.
- Built the seven-folder structure, using `.gitkeep` files so git records
  folders that are still empty.
- Separated secrets from code: `.env.example` is committed as a template,
  `.env` holds the values and is excluded by `.gitignore`.
- Wrote `src/config.py` with `load_env()` and `get_key()` so notebooks read
  configuration through one helper instead of hardcoding paths or keys.
- Verified the setup in `notebooks/00_project_setup.ipynb`.
- Froze the environment to `requirements.txt` (96 packages).

## Structure
    data/raw/          inputs, unedited from the source
    data/processed/    derived by code; deletable and re-creatable
    notebooks/         00_project_setup.ipynb
    src/               config.py
    docs/              notes
    reports/           outputs for a reader
    model/             saved model objects

## Note on paths
The notebook sits in `notebooks/`, one level below `src/` and `.env`, so it opens
with a cell that steps up to the folder root before importing. Without it,
`from src.config import ...` fails depending on where Jupyter was launched.
