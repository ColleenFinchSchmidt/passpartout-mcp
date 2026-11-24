"""Postgres-backed storage for imported hotel data.

Replaces JSON-file storage so imported availability, rates, extras,
and room config survive Railway container deploys.
"""

import json
import logging
import os

_log = logging.getLogger(__name__)
_conn = None


def _get_conn():
    global _conn
    if _conn is not None:
        try:
            _conn.cursor().execute("SELECT 1")
            return _conn
        except Exception:
            _conn = None
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return None
    try:
        import psycopg2
        _conn = psycopg2.connect(db_url)
        _conn.autocommit = True
        _ensure_tables(_conn)
        return _conn
    except Exception as exc:
        _log.warning("engine_db connect failed: %s", exc)
        return None


def _ensure_tables(conn):
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS engine")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS engine.imported_availability (
                hotel_id  TEXT NOT NULL,
                date      TEXT NOT NULL,
                free_rooms INT NOT NULL,
                PRIMARY KEY (hotel_id, date)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS engine.imported_hotel_config (
                hotel_id  TEXT PRIMARY KEY,
                config    JSONB NOT NULL DEFAULT '{}'
            )
        """)


# ---------- availability ----------

def get_imported_free_rooms(hotel_id: str) -> dict[str, int]:
    conn = _get_conn()
    if not conn:
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT date, free_rooms FROM engine.imported_availability WHERE hotel_id = %s",
                (hotel_id,),
            )
            return {row[0]: row[1] for row in cur.fetchall()}
    except Exception as exc:
        _log.warning("get_imported_free_rooms failed: %s", exc)
        return {}


def upsert_free_rooms(hotel_id: str, free_rooms: dict[str, int]) -> int:
    conn = _get_conn()
    if not conn:
        return 0
    count = 0
    try:
        with conn.cursor() as cur:
            for d, free in free_rooms.items():
                cur.execute("""
                    INSERT INTO engine.imported_availability (hotel_id, date, free_rooms)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (hotel_id, date)
                    DO UPDATE SET free_rooms = EXCLUDED.free_rooms
                """, (hotel_id, str(d), int(free)))
                count += 1
        return count
    except Exception as exc:
        _log.warning("upsert_free_rooms failed: %s", exc)
        return 0


# ---------- hotel config (rates, extras, rooms) ----------

def get_hotel_config(hotel_id: str) -> dict:
    conn = _get_conn()
    if not conn:
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT config FROM engine.imported_hotel_config WHERE hotel_id = %s",
                (hotel_id,),
            )
            row = cur.fetchone()
            if row:
                cfg = row[0]
                return cfg if isinstance(cfg, dict) else json.loads(cfg)
            return {}
    except Exception as exc:
        _log.warning("get_hotel_config failed: %s", exc)
        return {}


def upsert_hotel_config(hotel_id: str, updates: dict) -> bool:
    conn = _get_conn()
    if not conn:
        return False
    try:
        existing = get_hotel_config(hotel_id)
        existing.update(updates)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO engine.imported_hotel_config (hotel_id, config)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (hotel_id)
                DO UPDATE SET config = %s::jsonb
            """, (hotel_id, json.dumps(existing), json.dumps(existing)))
        return True
    except Exception as exc:
        _log.warning("upsert_hotel_config failed: %s", exc)
        return False


def delete_hotel_data(hotel_id: str) -> bool:
    """Delete all imported data for a hotel (availability + config)."""
    conn = _get_conn()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM engine.imported_availability WHERE hotel_id = %s", (hotel_id,))
            avail_deleted = cur.rowcount
            cur.execute("DELETE FROM engine.imported_hotel_config WHERE hotel_id = %s", (hotel_id,))
            config_deleted = cur.rowcount
        _log.info("Deleted hotel data for %s: %d availability rows, %d config rows", hotel_id, avail_deleted, config_deleted)
        return True
    except Exception as exc:
        _log.warning("delete_hotel_data failed: %s", exc)
        return False


def apply_hotel_config_to_memory(hotel: dict, hotel_id: str):
    """Apply persisted config overrides (rates, extras, rooms) to in-memory hotel dict."""
    cfg = get_hotel_config(hotel_id)
    if not cfg:
        return
    if "lowest_price_eur" in cfg:
        hotel["lowest_price_eur"] = cfg["lowest_price_eur"]
    if "max_discount_pct" in cfg:
        hotel["max_discount_pct"] = cfg["max_discount_pct"]
    if "public_rate_eur" in cfg:
        hotel["public_rate_eur"] = cfg["public_rate_eur"]
    if "rooms" in cfg:
        hotel["rooms"] = cfg["rooms"]
    if "room_types" in cfg:
        hotel["room_types"] = cfg["room_types"]
    if "extras" in cfg:
        hotel["extras"] = cfg["extras"]
