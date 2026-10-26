"""SQLite persistence: the storefront's order index, guard decisions, tickets and policy."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    persona TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS orders_index (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    session_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    capture_id TEXT,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    reason TEXT NOT NULL,
    claim TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL,
    status TEXT NOT NULL,
    checks TEXT NOT NULL,
    risk TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    transcript TEXT NOT NULL DEFAULT '[]',
    refund_id TEXT,
    error TEXT,
    resolved_by TEXT,
    resolved_note TEXT,
    resolved_at TEXT,
    mode TEXT NOT NULL DEFAULT 'agentguard',
    thread_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_decisions_customer ON decisions(customer_id, created_at);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    session_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    summary TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Statuses that count as money that has left, or is about to leave, the merchant.
ACTIVE_STATUSES = ("executed", "approved", "pending")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Store:
    def __init__(self, path: Path | str = ":memory:"):
        self.path = None if str(path) == ":memory:" else Path(path)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after a database was first created."""
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(decisions)")}
        for column, ddl in (("mode", "TEXT NOT NULL DEFAULT 'agentguard'"), ("thread_id", "TEXT")):
            if column not in have:
                self._conn.execute(f"ALTER TABLE decisions ADD COLUMN {column} {ddl}")

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def reset(self) -> None:
        with self._lock:
            for table in ("customers", "orders_index", "decisions", "tickets"):
                self._conn.execute(f"DELETE FROM {table}")
            self._conn.execute("DELETE FROM sqlite_sequence")
            self._conn.commit()

    # -- customers & orders (the storefront's own records) -------------------
    def add_customer(self, customer_id: str, name: str, email: str, persona: str = "") -> None:
        self._exec(
            "INSERT OR REPLACE INTO customers VALUES (?, ?, ?, ?)",
            (customer_id, name, email, persona),
        )

    def customers(self) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM customers ORDER BY name")

    def customer(self, customer_id: str) -> dict[str, Any] | None:
        rows = self._all("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
        return rows[0] if rows else None

    def add_order(self, order_id: str, customer_id: str, label: str = "") -> None:
        self._exec(
            "INSERT OR REPLACE INTO orders_index VALUES (?, ?, ?, ?)",
            (order_id, customer_id, label, utcnow().isoformat()),
        )

    def orders_for(self, customer_id: str) -> list[str]:
        rows = self._all(
            "SELECT order_id FROM orders_index WHERE customer_id = ? ORDER BY created_at",
            (customer_id,),
        )
        return [r["order_id"] for r in rows]

    def all_orders(self) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM orders_index ORDER BY created_at")

    # -- decisions -------------------------------------------------------------
    def insert_decision(self, row: dict[str, Any]) -> int:
        row = {**row, "created_at": row.get("created_at") or utcnow().isoformat()}
        for key in ("checks", "risk", "transcript"):
            if not isinstance(row.get(key), str):
                row[key] = json.dumps(row.get(key, []), default=str)
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        cur = self._exec(f"INSERT INTO decisions ({cols}) VALUES ({marks})", tuple(row.values()))
        return int(cur.lastrowid)

    def update_decision(self, decision_id: int, **fields: Any) -> None:
        sets = ", ".join(f"{k} = ?" for k in fields)
        self._exec(f"UPDATE decisions SET {sets} WHERE id = ?", (*fields.values(), decision_id))

    _DECISIONS = (
        "SELECT d.*, c.name AS customer_name FROM decisions d "
        "LEFT JOIN customers c ON c.customer_id = d.customer_id"
    )

    def get_decision(self, decision_id: int) -> dict[str, Any] | None:
        rows = self._all(f"{self._DECISIONS} WHERE d.id = ?", (decision_id,))
        return _decode(rows[0]) if rows else None

    def list_decisions(self, limit: int = 200, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self._all(
                f"{self._DECISIONS} WHERE d.status = ? ORDER BY d.id DESC LIMIT ?", (status, limit)
            )
        else:
            rows = self._all(f"{self._DECISIONS} ORDER BY d.id DESC LIMIT ?", (limit,))
        return [_decode(r) for r in rows]

    def refund_activity(self, customer_id: str, days: int = 30) -> tuple[int, Decimal]:
        """Refunds issued, approved or awaiting review for a customer in the window."""
        since = (utcnow() - timedelta(days=days)).isoformat()
        marks = ", ".join("?" for _ in ACTIVE_STATUSES)
        rows = self._all(
            f"SELECT amount FROM decisions WHERE customer_id = ? AND created_at >= ? AND status IN ({marks})",
            (customer_id, since, *ACTIVE_STATUSES),
        )
        return len(rows), sum((Decimal(r["amount"]) for r in rows), Decimal("0"))

    def pending_for_capture(self, capture_id: str) -> list[dict[str, Any]]:
        return self._all(
            "SELECT id, amount FROM decisions WHERE capture_id = ? AND status = 'pending'",
            (capture_id,),
        )

    # -- tickets ----------------------------------------------------------------
    def add_ticket(self, session_id: str, customer_id: str, summary: str) -> int:
        cur = self._exec(
            "INSERT INTO tickets (created_at, session_id, customer_id, summary) VALUES (?,?,?,?)",
            (utcnow().isoformat(), session_id, customer_id, summary),
        )
        return int(cur.lastrowid)

    def tickets(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM tickets ORDER BY id DESC LIMIT ?", (limit,))

    # -- key/value settings (policy) ------------------------------------------
    def get_setting(self, key: str) -> Any | None:
        rows = self._all("SELECT value FROM settings WHERE key = ?", (key,))
        return json.loads(rows[0]["value"]) if rows else None

    def set_setting(self, key: str, value: Any) -> None:
        self._exec("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value, default=str)))


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("checks", "risk", "transcript"):
        if isinstance(row.get(key), str):
            row[key] = json.loads(row[key])
    return row
