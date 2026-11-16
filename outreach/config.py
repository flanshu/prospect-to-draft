"""Configuration and credential loading.

Credentials are read from (in order):
  1. Streamlit secrets (``.streamlit/secrets.toml`` locally, Secrets UI on
     Streamlit Community Cloud)
  2. Process environment / ``.env`` file
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Fixed seller profile for the prototype.
# Shown in the UI so a reviewer can see why a finding was selected.
# Nothing beyond this sentence may be claimed about the product.
# ---------------------------------------------------------------------------
SELLER_PROFILE = (
    "We sell software that helps accounts payable teams match supplier "
    "invoices to purchase orders and route discrepancies to a reviewer."
)

SELLER_CAPABILITIES = [
    "Matching supplier invoices to purchase orders",
    "Routing invoice/PO discrepancies to a human reviewer",
]

# Gemini models. Flash is fast enough for a live demo while still supporting
# the google_search grounding tool.
RESEARCH_MODEL = "gemini-2.5-flash"
REASONING_MODEL = "gemini-2.5-flash"

MAX_FINDINGS = 3
# Keep the number of grounded search calls per run small so a live demo stays
# responsive and cheap.
RESEARCH_QUERY_BUDGET = 3


def _from_streamlit_secrets(name: str) -> str | None:
    try:
        import streamlit as st
    except Exception:  # pragma: no cover - streamlit always present in app
        return None
    try:
        value = st.secrets.get(name)  # type: ignore[attr-defined]
    except Exception:
        # No secrets.toml present -> accessing st.secrets raises.
        return None
    return str(value) if value else None


def get_setting(name: str, default: str | None = None) -> str | None:
    """Return a configuration value from Streamlit secrets or the environment."""
    return _from_streamlit_secrets(name) or os.getenv(name) or default


def google_api_key() -> str | None:
    return get_setting("GOOGLE_API_KEY")


def database_url() -> str | None:
    """Postgres connection string (Supabase). Falls back to SQLite when unset."""
    return get_setting("DATABASE_URL")


def sqlite_path() -> Path:
    return PROJECT_ROOT / "outreach_runs.db"


def credentials_available() -> bool:
    return bool(google_api_key())
