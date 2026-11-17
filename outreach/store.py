"""Run persistence.

Supabase Postgres when ``DATABASE_URL`` is configured, SQLite otherwise. The
schema is one table: the indexed columns the history view needs, plus the full
run as JSON so nothing is lost and no migration is needed when the run shape
changes.

    runs(run_id PK, created_at, updated_at, prospect_name, company,
         status, mode, payload)
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from . import config
from .schema import Run

_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    prospect_name TEXT NOT NULL,
    company       TEXT NOT NULL,
    status        TEXT NOT NULL,
    mode          TEXT NOT NULL,
    payload       TEXT NOT NULL
);
"""

_DDL_PG = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    prospect_name TEXT NOT NULL,
    company       TEXT NOT NULL,
    status        TEXT NOT NULL,
    mode          TEXT NOT NULL,
    payload       JSONB NOT NULL
);
"""


class Store:
    """Thin persistence layer over SQLite or Postgres."""

    def __init__(self) -> None:
        self.url = config.database_url()
        self.backend = "postgres" if self.url else "sqlite"
        self._pg = None
        if self.backend == "postgres":
            self._pg = _import_pg()
            if self._pg is None:
                # Degrade loudly rather than silently losing history.
                self.backend = "sqlite"
                self.url = None
                self.warning = (
                    "DATABASE_URL is set but no Postgres driver is installed "
                    "(pip install 'psycopg[binary]'). Falling back to local SQLite."
                )
            else:
                self.warning = ""
        else:
            self.warning = ""
        self._init_schema()

    # -------------------------------------------------------------- plumbing
    @contextmanager
    def _conn(self) -> Iterator[Any]:
        if self.backend == "postgres":
            conn = self._pg.connect(self.url)  # type: ignore[union-attr]
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(config.sqlite_path())
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _init_schema(self) -> None:
        ddl = _DDL_PG if self.backend == "postgres" else _DDL_SQLITE
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(ddl)

    def describe(self) -> str:
        if self.backend == "postgres":
            return "Supabase Postgres (hosted history)"
        return f"SQLite · {config.sqlite_path().name} (local history)"

    # ------------------------------------------------------------------ api
    def save(self, run: Run) -> None:
        """Insert or update one run. Idempotent -- never creates a duplicate."""
        payload = run.to_dict()
        blob = json.dumps(payload)
        with self._conn() as conn:
            cur = conn.cursor()
            if self.backend == "postgres":
                cur.execute(
                    """
                    INSERT INTO runs (run_id, created_at, updated_at, prospect_name,
                                      company, status, mode, payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (run_id) DO UPDATE SET
                        updated_at = EXCLUDED.updated_at,
                        prospect_name = EXCLUDED.prospect_name,
                        company = EXCLUDED.company,
                        status = EXCLUDED.status,
                        mode = EXCLUDED.mode,
                        payload = EXCLUDED.payload
                    """,
                    (
                        run.run_id, run.created_at, run.updated_at, run.prospect_name,
                        run.company, run.status, run.mode, blob,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO runs (run_id, created_at, updated_at, prospect_name,
                                      company, status, mode, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        updated_at = excluded.updated_at,
                        prospect_name = excluded.prospect_name,
                        company = excluded.company,
                        status = excluded.status,
                        mode = excluded.mode,
                        payload = excluded.payload
                    """,
                    (
                        run.run_id, run.created_at, run.updated_at, run.prospect_name,
                        run.company, run.status, run.mode, blob,
                    ),
                )

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Summary rows for the history view, newest first.

        Includes the selected signal, derived from the stored payload, so the
        history table can show one row per run with the signal on it.
        """
        sql = (
            "SELECT run_id, created_at, updated_at, prospect_name, company, status, "
            "mode, role, payload FROM runs ORDER BY created_at DESC LIMIT "
            + ("%s" if self.backend == "postgres" else "?")
        )
        # ``role`` is not a column; select the rest and derive what we need.
        sql = sql.replace("mode, role, payload", "mode, payload")
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            raw = [dict(zip(cols, r)) for r in rows]

        out: list[dict[str, Any]] = []
        for row in raw:
            payload = row.pop("payload", None)
            if isinstance(payload, (str, bytes)):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {}
            payload = payload or {}
            row["role"] = payload.get("role", "")
            row["product"] = _product_text(payload)
            row["signal"] = _signal_text(payload)
            out.append(row)
        return out

    def get(self, run_id: str) -> Run | None:
        ph = "%s" if self.backend == "postgres" else "?"
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT payload FROM runs WHERE run_id = {ph}", (run_id,))
            row = cur.fetchone()
        if not row:
            return None
        payload = row[0] if not isinstance(row, sqlite3.Row) else row["payload"]
        if isinstance(payload, (str, bytes)):
            payload = json.loads(payload)
        return Run.from_dict(payload)

    def delete(self, run_id: str) -> None:
        ph = "%s" if self.backend == "postgres" else "?"
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(f"DELETE FROM runs WHERE run_id = {ph}", (run_id,))


def _product_text(payload: dict[str, Any]) -> str:
    """The product this run was researched for, read from the stored payload.

    A payload with no product predates product selection; those runs were all
    invoice-matching runs and are labelled as such rather than left blank.
    """
    stored = payload.get("product") or {}
    name = str(stored.get("name") or "").strip()
    if not name:
        from . import config

        return config.PRODUCTS[config.LEGACY_PRODUCT_ID].name + " (before product choice)"
    if stored.get("legacy"):
        return name + " (before product choice)"
    return name


def _signal_text(payload: dict[str, Any]) -> str:
    """The active finding's claim with its score, or the reason there isn't one.

    Reads the stored payload only -- the history view never re-scores anything.
    """
    findings = payload.get("findings") or []
    claim = ""
    score_total: int | None = None

    active = payload.get("active_id") or ""
    if active:
        for f in findings:
            if (f or {}).get("finding_id") == active:
                claim = (f or {}).get("claim", "")
                break
        for sc in payload.get("scores") or []:
            if (sc or {}).get("finding_id") == active:
                total = (sc or {}).get("total")
                if isinstance(total, int):
                    score_total = total
                break
    if not claim:
        idx = payload.get("selected_index", -1)
        if isinstance(idx, int) and 0 <= idx < len(findings):
            claim = (findings[idx] or {}).get("claim", "")

    if claim:
        suffix = ""
        if score_total is not None:
            suffix = f" · {score_total} of 10"
            recommended = payload.get("recommended_id") or ""
            if recommended and active and recommended != active:
                suffix += " · reviewer's choice"
        elif payload.get("findings"):
            suffix = " · no score recorded"
        return claim + suffix

    status = payload.get("status", "")
    if status == "Needs clarification":
        return "— paused before research: identity not confirmed"
    if status:
        return f"— no signal selected ({status.lower()})"
    return "—"


def _import_pg():
    try:
        import psycopg  # type: ignore

        return psycopg
    except ImportError:
        pass
    try:
        import psycopg2  # type: ignore

        return psycopg2
    except ImportError:
        return None
