"""Durable state. SQLite in the plugin's own data folder; survives gateway restarts.

Open with Store.open_default() inside Hermes (plugin_db), or Store(path) in tests.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from . import faults

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"  # no I, L, O, U, 0, 1
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS parks (
  code TEXT PRIMARY KEY, created_at REAL, expires_at REAL,
  job_id TEXT, job_name TEXT, execution_id TEXT, session_id TEXT, profile TEXT,
  tool TEXT, args_json TEXT, call_digest TEXT, classes TEXT, reasons TEXT,
  snapshot_json TEXT, status TEXT, decided_by TEXT, decided_at REAL,
  resume_session TEXT, executed_at REAL, result_excerpt TEXT, deliver_note TEXT
);
CREATE TABLE IF NOT EXISTS steps (
  execution_id TEXT, seq INTEGER, at REAL, tool TEXT, summary TEXT, ok INTEGER, excerpt TEXT,
  PRIMARY KEY (execution_id, seq)
);
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY, execution_id TEXT, job_id TEXT, job_name TEXT, role TEXT, at REAL
);
CREATE TABLE IF NOT EXISTS executed (call_digest TEXT, job_id TEXT, park_code TEXT, at REAL, PRIMARY KEY (call_digest, job_id));
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, code TEXT, kind TEXT, detail TEXT);
"""


@dataclass
class Park:
    code: str
    created_at: float
    expires_at: float
    job_id: str
    job_name: str
    execution_id: str
    session_id: str
    profile: str
    tool: str
    args: dict
    call_digest: str
    classes: list
    reasons: list
    snapshot: dict
    status: str
    decided_by: str | None = None
    decided_at: float | None = None
    resume_session: str | None = None
    executed_at: float | None = None
    result_excerpt: str | None = None


class Store:
    def __init__(self, path_or_conn, on_change: Optional[Callable[[str, str], None]] = None):
        self._lock = threading.RLock()
        self.on_change = on_change  # (code, status) after every committed transition
        self.conn = path_or_conn if isinstance(path_or_conn, sqlite3.Connection) else sqlite3.connect(str(path_or_conn), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
            self.conn.commit()

    @classmethod
    def open_default(cls, on_change=None) -> "Store":
        from plugins.plugin_storage import plugin_db  # public plugin API
        return cls(plugin_db("abeyance"), on_change=on_change)

    # sessions and runs
    def bind_session(self, session_id: str, execution_id: str, job_id: str, job_name: str, role: str) -> None:
        with self._lock:
            self.conn.execute("INSERT OR IGNORE INTO sessions VALUES (?,?,?,?,?,?)",
                              (session_id, execution_id, job_id, job_name, role, time.time()))
            self.conn.commit()

    def session_run(self, session_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()

    def frozen_park(self, execution_id: str) -> Park | None:
        row = self.conn.execute("SELECT * FROM parks WHERE execution_id=? ORDER BY created_at LIMIT 1", (execution_id,)).fetchone()
        return self._park(row) if row else None

    # steps
    def add_step(self, execution_id: str, tool: str, summary: str, ok: bool, excerpt: str) -> None:
        with self._lock:
            seq = self.conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM steps WHERE execution_id=?", (execution_id,)).fetchone()[0]
            self.conn.execute("INSERT INTO steps VALUES (?,?,?,?,?,?,?)",
                              (execution_id, seq, time.time(), tool, summary[:200], int(ok), excerpt[:300]))
            self.conn.commit()

    def steps(self, execution_id: str) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM steps WHERE execution_id=? ORDER BY seq", (execution_id,)))

    # parks
    def new_code(self) -> str:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
            if not self.conn.execute("SELECT 1 FROM parks WHERE code=?", (code,)).fetchone():
                return code

    def create_park(self, p: Park) -> Park:
        faults.check("store")
        with self._lock:
            self.conn.execute(
                "INSERT INTO parks (code,created_at,expires_at,job_id,job_name,execution_id,session_id,profile,tool,args_json,"
                "call_digest,classes,reasons,snapshot_json,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.code, p.created_at, p.expires_at, p.job_id, p.job_name, p.execution_id, p.session_id, p.profile, p.tool,
                 json.dumps(p.args, sort_keys=True), p.call_digest, json.dumps(p.classes), json.dumps(p.reasons),
                 json.dumps(p.snapshot, sort_keys=True), p.status))
            self.conn.commit()
        self.event(p.code, "parked", f"{p.tool} {p.classes}")
        self._changed(p.code, "parked")
        return p

    def get(self, code: str) -> Park | None:
        row = self.conn.execute("SELECT * FROM parks WHERE code=?", (code.upper(),)).fetchone()
        return self._park(row) if row else None

    def transition(self, code: str, expected: str, new: str, **fields) -> bool:
        """Compare-and-set on status. Returns False if another caller got there first (single use)."""
        faults.check("store")
        sets = ", ".join(["status=?"] + [f"{k}=?" for k in fields])
        with self._lock:
            cur = self.conn.execute(f"UPDATE parks SET {sets} WHERE code=? AND status=?",
                                    (new, *fields.values(), code.upper(), expected))
            self.conn.commit()
        if cur.rowcount:
            self.event(code, new, json.dumps(fields, default=str)[:300])
            self._changed(code.upper(), new)
        return bool(cur.rowcount)

    def _changed(self, code: str, status: str) -> None:
        if self.on_change is not None:
            try:
                self.on_change(code, status)
            except Exception:  # an event subscriber must never break a transition
                pass

    def list_parks(self, status: str | None = None, limit: int = 20) -> list[Park]:
        q, a = "SELECT * FROM parks", ()
        if status:
            q, a = q + " WHERE status=?", (status,)
        return [self._park(r) for r in self.conn.execute(q + " ORDER BY created_at DESC LIMIT ?", (*a, limit))]

    def resume_binding(self, session_id: str) -> Park | None:
        row = self.conn.execute("SELECT * FROM parks WHERE resume_session=? AND status='resumed' ORDER BY decided_at DESC LIMIT 1",
                                (session_id,)).fetchone()
        return self._park(row) if row else None

    def session_park(self, session_id: str) -> Park | None:
        """Latest park resumed in this session, whatever its status now (for exactly-once checks)."""
        row = self.conn.execute("SELECT * FROM parks WHERE resume_session=? ORDER BY decided_at DESC LIMIT 1",
                                (session_id,)).fetchone()
        return self._park(row) if row else None

    # exactly-once
    def mark_executed(self, call_digest: str, job_id: str, code: str) -> None:
        with self._lock:
            self.conn.execute("INSERT OR IGNORE INTO executed VALUES (?,?,?,?)", (call_digest, job_id, code, time.time()))
            self.conn.commit()

    def was_executed(self, call_digest: str, job_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM executed WHERE call_digest=? AND job_id=?", (call_digest, job_id)).fetchone()

    def event(self, code: str, kind: str, detail: str) -> None:
        with self._lock:
            self.conn.execute("INSERT INTO events (at,code,kind,detail) VALUES (?,?,?,?)", (time.time(), code, kind, detail[:500]))
            self.conn.commit()

    def events(self, code: str | None = None, limit: int = 50) -> list[sqlite3.Row]:
        if code:
            return list(self.conn.execute("SELECT * FROM events WHERE code=? ORDER BY id", (code.upper(),)))
        return list(self.conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)))

    @staticmethod
    def _park(row: sqlite3.Row) -> Park:
        return Park(code=row["code"], created_at=row["created_at"], expires_at=row["expires_at"], job_id=row["job_id"],
                    job_name=row["job_name"], execution_id=row["execution_id"], session_id=row["session_id"],
                    profile=row["profile"], tool=row["tool"], args=json.loads(row["args_json"] or "{}"),
                    call_digest=row["call_digest"], classes=json.loads(row["classes"] or "[]"),
                    reasons=json.loads(row["reasons"] or "[]"), snapshot=json.loads(row["snapshot_json"] or "{}"),
                    status=row["status"], decided_by=row["decided_by"], decided_at=row["decided_at"],
                    resume_session=row["resume_session"], executed_at=row["executed_at"],
                    result_excerpt=row["result_excerpt"])
