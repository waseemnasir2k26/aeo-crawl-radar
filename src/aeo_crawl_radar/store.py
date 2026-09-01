"""SQLite store so runs accumulate and can be diffed over time."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

SCHEMA_VERSION = 1

DEFAULT_DB = ".aeo-crawl-radar.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hits (
    id        INTEGER PRIMARY KEY,
    fp        TEXT    NOT NULL UNIQUE,
    ts        TEXT    NOT NULL,
    ts_epoch  INTEGER NOT NULL,
    ip        TEXT    NOT NULL DEFAULT '',
    host      TEXT    NOT NULL DEFAULT '',
    method    TEXT    NOT NULL DEFAULT 'GET',
    path      TEXT    NOT NULL DEFAULT '/',
    status    INTEGER NOT NULL DEFAULT 0,
    bytes     INTEGER NOT NULL DEFAULT 0,
    ua        TEXT    NOT NULL DEFAULT '',
    bot       TEXT    NOT NULL,
    vendor    TEXT    NOT NULL DEFAULT '',
    purpose   TEXT    NOT NULL DEFAULT '',
    is_ai     INTEGER NOT NULL DEFAULT 1,
    verified  TEXT    NOT NULL DEFAULT 'unchecked',
    source    TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_hits_ts   ON hits (ts_epoch);
CREATE INDEX IF NOT EXISTS idx_hits_bot  ON hits (bot);
CREATE INDEX IF NOT EXISTS idx_hits_path ON hits (path);

CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY,
    started_at TEXT    NOT NULL,
    files      TEXT    NOT NULL DEFAULT '',
    formats    TEXT    NOT NULL DEFAULT '',
    parsed     INTEGER NOT NULL DEFAULT 0,
    skipped    INTEGER NOT NULL DEFAULT 0,
    inserted   INTEGER NOT NULL DEFAULT 0,
    duplicates INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass
class IngestStats:
    parsed: int = 0
    skipped: int = 0
    bot_hits: int = 0
    inserted: int = 0
    duplicates: int = 0


def fingerprint(ev, bot_name: str) -> str:
    raw = "|".join(
        [
            ev.ts.astimezone(timezone.utc).isoformat(),
            ev.ip,
            ev.method,
            ev.path,
            str(ev.status),
            str(ev.bytes),
            ev.user_agent,
            bot_name,
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class Store:
    """Thin wrapper over a SQLite file. Idempotent inserts by row fingerprint."""

    def __init__(self, path=DEFAULT_DB):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    # ---- lifecycle ----------------------------------------------------
    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- writes -------------------------------------------------------
    def add_hits(self, rows: Iterable[dict]) -> tuple[int, int]:
        """Insert classified hits. Returns (inserted, duplicates)."""
        inserted = 0
        total = 0
        cur = self.conn.cursor()
        for r in rows:
            total += 1
            cur.execute(
                """INSERT OR IGNORE INTO hits
                   (fp, ts, ts_epoch, ip, host, method, path, status, bytes,
                    ua, bot, vendor, purpose, is_ai, verified, source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    r["fp"],
                    r["ts"],
                    r["ts_epoch"],
                    r["ip"],
                    r["host"],
                    r["method"],
                    r["path"],
                    r["status"],
                    r["bytes"],
                    r["ua"],
                    r["bot"],
                    r["vendor"],
                    r["purpose"],
                    int(r["is_ai"]),
                    r["verified"],
                    r["source"],
                ),
            )
            inserted += cur.rowcount
        self.conn.commit()
        return inserted, total - inserted

    def record_run(
        self,
        files: Sequence[str],
        formats: Sequence[str],
        stats: IngestStats,
    ) -> None:
        self.conn.execute(
            """INSERT INTO runs
               (started_at, files, formats, parsed, skipped, inserted, duplicates)
               VALUES (?,?,?,?,?,?,?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                ",".join(files),
                ",".join(sorted(set(formats))),
                stats.parsed,
                stats.skipped,
                stats.inserted,
                stats.duplicates,
            ),
        )
        self.conn.commit()

    # ---- reads --------------------------------------------------------
    def _window(self, since: datetime | None, until: datetime | None):
        clauses, params = [], []
        if since is not None:
            clauses.append("ts_epoch >= ?")
            params.append(int(since.timestamp()))
        if until is not None:
            clauses.append("ts_epoch <= ?")
            params.append(int(until.timestamp()))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    def count(self, since=None, until=None, ai_only=False) -> int:
        where, params = self._window(since, until)
        if ai_only:
            where = (where + " AND " if where else " WHERE ") + "is_ai = 1"
        row = self.conn.execute(f"SELECT COUNT(*) c FROM hits{where}", params).fetchone()
        return row["c"]

    def bot_summary(self, since=None, until=None, ai_only=True) -> list[dict]:
        where, params = self._window(since, until)
        if ai_only:
            where = (where + " AND " if where else " WHERE ") + "is_ai = 1"
        sql = f"""
            SELECT bot, vendor, purpose,
                   COUNT(*)                AS hits,
                   SUM(bytes)              AS bytes,
                   MIN(ts)                 AS first_seen,
                   MAX(ts)                 AS last_seen,
                   COUNT(DISTINCT path)    AS paths,
                   SUM(CASE WHEN verified='verified' THEN 1 ELSE 0 END) AS verified_hits,
                   SUM(CASE WHEN verified='failed'   THEN 1 ELSE 0 END) AS failed_hits
            FROM hits{where}
            GROUP BY bot, vendor, purpose
            ORDER BY hits DESC, bot ASC
        """
        return [dict(r) for r in self.conn.execute(sql, params)]

    def top_paths(self, bot=None, since=None, until=None, limit=10, ai_only=True) -> list[dict]:
        where, params = self._window(since, until)
        extra = []
        if ai_only:
            extra.append("is_ai = 1")
        if bot:
            extra.append("bot = ?")
            params.append(bot)
        if extra:
            where = (where + " AND " if where else " WHERE ") + " AND ".join(extra)
        sql = f"""
            SELECT path, COUNT(*) AS hits, SUM(bytes) AS bytes,
                   COUNT(DISTINCT bot) AS bots
            FROM hits{where}
            GROUP BY path ORDER BY hits DESC, path ASC LIMIT ?
        """
        return [dict(r) for r in self.conn.execute(sql, params + [limit])]

    def status_breakdown(self, since=None, until=None, ai_only=True) -> list[dict]:
        where, params = self._window(since, until)
        if ai_only:
            where = (where + " AND " if where else " WHERE ") + "is_ai = 1"
        sql = f"""
            SELECT status, COUNT(*) AS hits FROM hits{where}
            GROUP BY status ORDER BY hits DESC
        """
        return [dict(r) for r in self.conn.execute(sql, params)]

    def crawled_paths(self, since=None, until=None, ai_only=True) -> set[str]:
        where, params = self._window(since, until)
        if ai_only:
            where = (where + " AND " if where else " WHERE ") + "is_ai = 1"
        sql = f"SELECT DISTINCT path FROM hits{where}"
        return {r["path"] for r in self.conn.execute(sql, params)}

    def path_bot_map(self, since=None, until=None, ai_only=True) -> dict[str, set[str]]:
        where, params = self._window(since, until)
        if ai_only:
            where = (where + " AND " if where else " WHERE ") + "is_ai = 1"
        sql = f"SELECT DISTINCT path, bot FROM hits{where}"
        out: dict[str, set[str]] = {}
        for r in self.conn.execute(sql, params):
            out.setdefault(r["path"], set()).add(r["bot"])
        return out

    def time_bounds(self) -> tuple[datetime | None, datetime | None]:
        row = self.conn.execute(
            "SELECT MIN(ts_epoch) lo, MAX(ts_epoch) hi FROM hits"
        ).fetchone()
        if row is None or row["lo"] is None:
            return None, None
        return (
            datetime.fromtimestamp(row["lo"], tz=timezone.utc),
            datetime.fromtimestamp(row["hi"], tz=timezone.utc),
        )

    def rows(self, since=None, until=None, ai_only=True) -> list[dict]:
        where, params = self._window(since, until)
        if ai_only:
            where = (where + " AND " if where else " WHERE ") + "is_ai = 1"
        sql = (
            "SELECT ts, ip, host, method, path, status, bytes, ua, bot, vendor, "
            f"purpose, is_ai, verified, source FROM hits{where} ORDER BY ts_epoch"
        )
        return [dict(r) for r in self.conn.execute(sql, params)]
