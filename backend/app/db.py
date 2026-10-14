"""SQLite persistence for investigations.

Connection-per-operation with WAL mode — simple, thread-safe, and adequate for
a single-instance MVP. Only investigation data is stored; no credentials, and
log content has already passed secret redaction before reaching this layer.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import get_settings
from .schemas import (
    Investigation,
    InvestigationSummary,
    Report,
    TimeWindow,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS investigations (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    provider TEXT NOT NULL,
    resource_id TEXT,
    scenario_id TEXT,
    status TEXT NOT NULL,
    severity_assessment TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    window_start TEXT,
    window_end TEXT,
    steps_json TEXT NOT NULL DEFAULT '[]',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    report_json TEXT,
    error TEXT,
    simulated INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_investigations_created ON investigations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_investigations_status ON investigations(status);
"""


def _connect() -> sqlite3.Connection:
    db_path = Path(get_settings().db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # Idempotent schema guard: background investigation threads may touch the
    # store before/after app lifespans (cheap no-op once tables exist).
    conn.executescript(_SCHEMA)
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def _dump(obj) -> dict:
    """Steps/evidence may be Pydantic models or already-serialized dicts
    (graph state stores plain dicts)."""
    return obj if isinstance(obj, dict) else obj.model_dump(mode="json")


def save_investigation(inv: Investigation) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO investigations
                (id, question, provider, resource_id, scenario_id, status, severity_assessment,
                 created_at, completed_at, window_start, window_end,
                 steps_json, evidence_json, report_json, error, simulated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                severity_assessment=excluded.severity_assessment,
                completed_at=excluded.completed_at,
                resource_id=excluded.resource_id,
                window_start=excluded.window_start,
                window_end=excluded.window_end,
                steps_json=excluded.steps_json,
                evidence_json=excluded.evidence_json,
                report_json=excluded.report_json,
                error=excluded.error,
                simulated=excluded.simulated
            """,
            (
                inv.id,
                inv.question,
                inv.provider,
                inv.resource_id,
                inv.scenario_id,
                inv.status,
                inv.report.severity_assessment if inv.report else None,
                inv.created_at.isoformat(),
                inv.completed_at.isoformat() if inv.completed_at else None,
                inv.time_window.start.isoformat() if inv.time_window else None,
                inv.time_window.end.isoformat() if inv.time_window else None,
                json.dumps([_dump(s) for s in inv.steps]),
                json.dumps([_dump(e) for e in inv.evidence]),
                inv.report.model_dump_json() if inv.report else None,
                inv.error,
                1 if inv.simulated else 0,
            ),
        )


def _row_to_investigation(row: sqlite3.Row) -> Investigation:
    window = None
    if row["window_start"] and row["window_end"]:
        window = TimeWindow(
            start=datetime.fromisoformat(row["window_start"]),
            end=datetime.fromisoformat(row["window_end"]),
        )
    return Investigation(
        id=row["id"],
        question=row["question"],
        provider=row["provider"],
        resource_id=row["resource_id"],
        scenario_id=row["scenario_id"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        time_window=window,
        steps=json.loads(row["steps_json"]),
        evidence=json.loads(row["evidence_json"]),
        report=Report.model_validate_json(row["report_json"]) if row["report_json"] else None,
        error=row["error"],
        simulated=bool(row["simulated"]),
    )


def get_investigation(inv_id: str) -> Investigation | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM investigations WHERE id = ?", (inv_id,)).fetchone()
    return _row_to_investigation(row) if row else None


def _row_to_summary(row: sqlite3.Row) -> InvestigationSummary:
    return InvestigationSummary(
        id=row["id"],
        question=row["question"],
        provider=row["provider"],
        resource_id=row["resource_id"],
        scenario_id=row["scenario_id"],
        status=row["status"],
        severity_assessment=row["severity_assessment"],
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        step_count=len(json.loads(row["steps_json"])),
        simulated=bool(row["simulated"]),
    )


def list_investigations(
    q: str | None = None,
    provider: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[InvestigationSummary], int]:
    clauses: list[str] = []
    params: list = []
    if q:
        clauses.append("(question LIKE ? OR resource_id LIKE ? OR id LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    if provider:
        clauses.append("provider = ?")
        params.append(provider)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    offset = (page - 1) * page_size
    with _connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM investigations {where}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"SELECT * FROM investigations {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()
    return [_row_to_summary(r) for r in rows], total
