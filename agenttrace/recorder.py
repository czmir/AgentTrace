from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agenttrace.core import Span, Trace
from agenttrace.redact import redact_trace_payload


class TraceRecorder:
    """SQLite-backed trace storage with optional live event subscribers."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        path = Path(db_path or Path.home() / ".agenttrace" / "traces.db")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = path
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[str, dict[str, Any]], None]] = []
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    metadata TEXT,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_traces_started ON traces(started_at DESC);
                CREATE TABLE IF NOT EXISTS live_spans (
                    trace_id TEXT NOT NULL,
                    span_id TEXT NOT NULL,
                    started_ns INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (trace_id, span_id)
                );
                CREATE TABLE IF NOT EXISTS eval_runs (
                    id TEXT PRIMARY KEY,
                    dataset TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    summary TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def subscribe(self, callback: Callable[[str, dict[str, Any]], None]) -> Callable[[], None]:
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe

    def emit_event(self, event: str, data: dict[str, Any]) -> None:
        data = redact_trace_payload(data)
        for cb in list(self._subscribers):
            try:
                cb(event, data)
            except Exception:
                pass

    def save_trace(self, trace: Trace) -> None:
        safe_trace = redact_trace_payload(trace.to_dict())
        payload = json.dumps(safe_trace, default=str)
        metadata = json.dumps(safe_trace["metadata"], default=str)
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO traces (id, name, status, started_at, ended_at, metadata, payload, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    ended_at=excluded.ended_at,
                    metadata=excluded.metadata,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    trace.id,
                    safe_trace["name"],
                    trace.status.value,
                    trace.started_at,
                    trace.ended_at,
                    metadata,
                    payload,
                    now,
                ),
            )
            conn.execute("DELETE FROM live_spans WHERE trace_id = ?", (trace.id,))
            conn.commit()
        self.emit_event("trace_updated", {"trace_id": trace.id})

    def save_span(self, trace: Trace, span: Span) -> None:
        """Persist the current span while the trace session is open."""
        payload = json.dumps(redact_trace_payload(span.to_dict()), default=str)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO live_spans (trace_id, span_id, started_ns, payload)
                SELECT ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM traces WHERE id = ?)
                ON CONFLICT(trace_id, span_id) DO UPDATE SET payload=excluded.payload
                """,
                (trace.id, span.id, span.start_ns, payload, trace.id),
            )
            conn.commit()
        self.emit_event("trace_updated", {"trace_id": trace.id})

    def get_trace(self, trace_id: str) -> Trace | None:
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN")
            row = conn.execute("SELECT payload FROM traces WHERE id = ?", (trace_id,)).fetchone()
            if not row:
                return None
            pending = conn.execute(
                "SELECT payload FROM live_spans WHERE trace_id = ? ORDER BY started_ns, rowid",
                (trace_id,),
            ).fetchall()
        data = redact_trace_payload(json.loads(row["payload"]))
        if pending:
            spans = {span["id"]: span for span in data.get("spans", [])}
            for update in pending:
                span = json.loads(update["payload"])
                spans[span["id"]] = span
            data["spans"] = list(spans.values())
            if data.get("root_span_id") is None:
                data["root_span_id"] = next(
                    (span["id"] for span in spans.values() if span.get("parent_id") is None), None,
                )
        return Trace.model_validate(data)

    def list_traces(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, status, started_at, ended_at, metadata
                FROM traces ORDER BY started_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "name": redact_trace_payload({"name": r["name"]})["name"],
                "status": r["status"],
                "started_at": r["started_at"],
                "ended_at": r["ended_at"],
                "metadata": redact_trace_payload(json.loads(r["metadata"] or "{}")),
            }
            for r in rows
        ]

    def delete_trace(self, trace_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM traces WHERE id = ?", (trace_id,))
            conn.execute("DELETE FROM live_spans WHERE trace_id = ?", (trace_id,))
            conn.commit()
            return cur.rowcount > 0

    def save_eval_run(self, run_id: str, dataset: str, summary: dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO eval_runs (id, dataset, created_at, summary) VALUES (?, ?, ?, ?)",
                (run_id, dataset, time.time(), json.dumps(summary, default=str)),
            )
            conn.commit()
