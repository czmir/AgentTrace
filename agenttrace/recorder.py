from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agenttrace.core import Trace


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
        for cb in list(self._subscribers):
            try:
                cb(event, data)
            except Exception:
                pass

    def save_trace(self, trace: Trace) -> None:
        payload = json.dumps(trace.to_dict(), default=str)
        metadata = json.dumps(trace.metadata, default=str)
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
                    trace.name,
                    trace.status.value,
                    trace.started_at,
                    trace.ended_at,
                    metadata,
                    payload,
                    now,
                ),
            )
            conn.commit()
        self.emit_event("trace_updated", {"trace_id": trace.id})

    def get_trace(self, trace_id: str) -> Trace | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT payload FROM traces WHERE id = ?", (trace_id,)).fetchone()
        if not row:
            return None
        data = json.loads(row["payload"])
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
                "name": r["name"],
                "status": r["status"],
                "started_at": r["started_at"],
                "ended_at": r["ended_at"],
                "metadata": json.loads(r["metadata"] or "{}"),
            }
            for r in rows
        ]

    def delete_trace(self, trace_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM traces WHERE id = ?", (trace_id,))
            conn.commit()
            return cur.rowcount > 0

    def save_eval_run(self, run_id: str, dataset: str, summary: dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO eval_runs (id, dataset, created_at, summary) VALUES (?, ?, ?, ?)",
                (run_id, dataset, time.time(), json.dumps(summary, default=str)),
            )
            conn.commit()