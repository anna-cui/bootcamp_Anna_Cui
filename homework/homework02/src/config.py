"""Configuration helpers: load environment variables and read keys."""

import os
from pathlib import Path

from dotenv import load_dotenv


def load_env(dotenv_path=None):
    """Load variables from a .env file into the process environment.

    Defaults to the .env sitting beside this package's parent folder,
    so it works no matter which directory the caller runs from.
    """
    if dotenv_path is None:
        dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    return load_dotenv(dotenv_path)


def get_key(name="API_KEY", default=None):
    """Return the value of an environment variable, or `default` if unset."""
    return os.getenv(name, default)
