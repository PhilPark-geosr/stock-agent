from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


def load_environment() -> None:
    # Always load project .env and prefer it over stale process env vars.
    load_dotenv(_ENV_FILE, override=True)
