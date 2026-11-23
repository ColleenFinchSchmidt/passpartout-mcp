"""Postgres storage for discovered events.

Falls back to JSON files when DATABASE_URL is not set (local dev).
Never overwrites a good event list with an empty one.
"""

import json
import logging
import os
from datetime import date, datetime

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_conn = None


def _get_conn():
    global _conn
    if not DATABASE_URL:
        return None
    if _conn is not None:
        try:
            _conn.cursor().execute("SELECT 1")
            return _conn
        except Exception:
            _conn = None
    try:
        import psycopg2
        _conn = psycopg2.connect(DATABASE_URL)
        _conn.autocommit = True
        _ensure_table(_conn)
        return _conn
    except Exception as exc:
        logger.warning("Postgres connect failed: %s", exc)
        return None


def _ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS discovered_events (
                hotel_id TEXT PRIMARY KEY,
                events JSONB NOT NULL DEFAULT '[]',
                sources JSONB NOT NULL DEFAULT '[]',
                discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)


def save_events(hotel_id: str, events: list, sources: list) -> bool:
    """Save events to Postgres. Returns True on success.

    Never overwrites with an empty list — if events is empty,
    the existing row is kept unchanged.
    """
    if not events:
        logger.warning("Skipping save for %s: empty event list (keeping previous)", hotel_id)
        return False
    conn = _get_conn()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO discovered_events (hotel_id, events, sources, discovered_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (hotel_id) DO UPDATE
                SET events = EXCLUDED.events,
                    sources = EXCLUDED.sources,
                    discovered_at = EXCLUDED.discovered_at
            """, (hotel_id, json.dumps(events), json.dumps(sources)))
        return True
    except Exception as exc:
        logger.warning("Postgres save failed for %s: %s", hotel_id, exc)
        return False


def load_events(hotel_id: str) -> dict | None:
    """Load events from Postgres. Returns dict with events/sources/discovered or None."""
    conn = _get_conn()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT events, sources, discovered_at FROM discovered_events WHERE hotel_id = %s",
                (hotel_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "events": row[0] if isinstance(row[0], list) else json.loads(row[0]),
                "sources": row[1] if isinstance(row[1], list) else json.loads(row[1]),
                "discovered": row[2].date().isoformat() if row[2] else "",
            }
    except Exception as exc:
        logger.warning("Postgres load failed for %s: %s", hotel_id, exc)
        return None


def get_discovered_at(hotel_id: str) -> date | None:
    """When was the last successful discovery for this hotel?"""
    conn = _get_conn()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT discovered_at FROM discovered_events WHERE hotel_id = %s",
                (hotel_id,),
            )
            row = cur.fetchone()
            if row and row[0]:
                return row[0].date() if isinstance(row[0], datetime) else row[0]
            return None
    except Exception as exc:
        logger.warning("Postgres query failed for %s: %s", hotel_id, exc)
        return None
