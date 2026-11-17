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

from .schema import Product

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Product catalogue.
#
# Three fictional offerings written for this assignment. A salesperson picks
# ONE per research run, and that choice drives research, scoring, drafting and
# history. The capability lists below are the complete and only claims the app
# may make about each product: nothing else may be attributed to any of them,
# and none of them is attributed to any real company.
# ---------------------------------------------------------------------------
PRODUCTS: dict[str, Product] = {
    "receipt_tracking": Product(
        product_id="receipt_tracking",
        name="Expense receipt tracking",
        target_users="finance teams",
        description=(
            "Helps finance teams collect missing employee expense receipts, send "
            "reminders, and track outstanding receipts."
        ),
        capabilities=[
            "Collecting missing employee expense receipts",
            "Sending reminders for outstanding receipts",
            "Tracking which receipts are still outstanding",
        ],
    ),
    "vendor_onboarding": Product(
        product_id="vendor_onboarding",
        name="Vendor onboarding",
        target_users="procurement teams",
        description=(
            "Helps procurement teams collect supplier documents, flag missing "
            "information, and track onboarding approval."
        ),
        capabilities=[
            "Collecting supplier documents during onboarding",
            "Flagging missing or incomplete supplier information",
            "Tracking onboarding approval status",
        ],
    ),
    "invoice_matching": Product(
        product_id="invoice_matching",
        name="Invoice matching",
        target_users="accounts payable teams",
        description=(
            "Helps accounts payable teams compare supplier invoices with purchase "
            "orders and route quantity or price discrepancies for review."
        ),
        capabilities=[
            "Comparing supplier invoices with purchase orders",
            "Routing quantity or price discrepancies for review",
        ],
    ),
}

# The dropdown's default, and the product a run uses when none was chosen.
DEFAULT_PRODUCT_ID = "receipt_tracking"

# Runs saved before the product dropdown existed were all invoice-matching
# runs. They are displayed with that context and never rescored.
LEGACY_PRODUCT_ID = "invoice_matching"


def product(product_id: str | None) -> Product:
    """One catalogue entry, falling back to the default for an unknown id."""
    return PRODUCTS.get(product_id or "", PRODUCTS[DEFAULT_PRODUCT_ID])


def default_product() -> Product:
    return product(DEFAULT_PRODUCT_ID)


def legacy_product() -> Product:
    """The offering a pre-dropdown run was researched for, flagged as legacy."""
    base = PRODUCTS[LEGACY_PRODUCT_ID]
    return Product(
        product_id=base.product_id,
        name=base.name,
        target_users=base.target_users,
        description=base.description,
        capabilities=list(base.capabilities),
        legacy=True,
    )


def product_choices() -> list[tuple[str, str]]:
    """``(product_id, display name)`` in catalogue order, default first."""
    return [(pid, p.name) for pid, p in PRODUCTS.items()]

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
