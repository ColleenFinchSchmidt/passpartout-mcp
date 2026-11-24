"""Offer inventory, allocation and wave management.

Persists to Postgres (same DATABASE_URL as events_db).
Simulated metrics are deterministic for demo repeatability.
"""

import hashlib
import json
import logging
import os
import random
import time
from datetime import date as date_type, datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ROME_TZ = ZoneInfo("Europe/Rome")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

DEFAULT_BOOKING_RATE = 0.03
HOLD_DURATION_SECONDS = 600  # 10 minutes
DEFAULT_EXPIRY_HOURS = 48
DEFAULT_LAST_BOOKING_HOUR = 18
DEFAULT_WAVE_DELAY_HOURS = 24

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
        _ensure_tables(_conn)
        return _conn
    except Exception as exc:
        logger.warning("Inventory Postgres connect failed: %s", exc)
        return None


def _ensure_tables(conn):
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS engine")
        # Migrate old public-schema tables if they exist
        for tbl in ("inventory_holds", "inventory_waves", "inventory_offers"):
            cur.execute(f"""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables
                               WHERE table_schema = 'public'
                               AND table_name = '{tbl}') THEN
                        ALTER TABLE public.{tbl} SET SCHEMA engine;
                    END IF;
                END $$;
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS engine.inventory_offers (
                offer_id      TEXT PRIMARY KEY,
                hotel_id      TEXT NOT NULL,
                check_in      TEXT NOT NULL,
                nights        INT NOT NULL,
                rooms_allocated INT NOT NULL,
                rooms_booked  INT NOT NULL DEFAULT 0,
                status        TEXT NOT NULL DEFAULT 'active',
                auto_waves    BOOLEAN NOT NULL DEFAULT FALSE,
                wave_delay_hours INT NOT NULL DEFAULT 24,
                expiry_hours  INT NOT NULL DEFAULT 48,
                booking_rate  REAL NOT NULL DEFAULT 0.03,
                notify_list   JSONB NOT NULL DEFAULT '[]',
                created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS engine.inventory_waves (
                id            SERIAL PRIMARY KEY,
                offer_id      TEXT NOT NULL REFERENCES engine.inventory_offers(offer_id),
                wave_number   INT NOT NULL,
                city          TEXT NOT NULL,
                segment       TEXT NOT NULL,
                segment_label TEXT NOT NULL,
                recipients    INT NOT NULL DEFAULT 0,
                status        TEXT NOT NULL DEFAULT 'pending',
                sent_at       TIMESTAMPTZ,
                extra_added   TEXT,
                sent          INT NOT NULL DEFAULT 0,
                opened        INT NOT NULL DEFAULT 0,
                clicked       INT NOT NULL DEFAULT 0,
                booked        INT NOT NULL DEFAULT 0,
                UNIQUE (offer_id, wave_number)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS engine.inventory_holds (
                id         SERIAL PRIMARY KEY,
                offer_id   TEXT NOT NULL REFERENCES engine.inventory_offers(offer_id),
                guest_ref  TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)


# ---- helpers ----

def _deterministic_seed(offer_id: str, wave_num: int) -> int:
    return int(hashlib.sha256(f"{offer_id}|w{wave_num}".encode()).hexdigest()[:8], 16)


def _simulate_wave_metrics(recipients: int, booking_rate: float, seed: int) -> dict:
    rng = random.Random(seed)
    sent = recipients
    opened = int(sent * rng.uniform(0.25, 0.45))
    clicked = int(opened * rng.uniform(0.15, 0.35))
    booked = max(1, int(sent * booking_rate * rng.uniform(0.7, 1.3)))
    booked = min(booked, clicked)
    return {"sent": sent, "opened": opened, "clicked": clicked, "booked": booked}


def _active_holds(conn, offer_id: str) -> int:
    """Count non-expired holds."""
    cutoff = time.time() - HOLD_DURATION_SECONDS
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM engine.inventory_holds WHERE offer_id = %s AND created_at >= %s",
            (offer_id, cutoff),
        )
        return cur.fetchone()[0]


def _expire_holds(conn, offer_id: str):
    cutoff = time.time() - HOLD_DURATION_SECONDS
    with conn.cursor() as cur:
        cur.execute("DELETE FROM engine.inventory_holds WHERE offer_id = %s AND created_at < %s",
                    (offer_id, cutoff))


def _expiry_time(check_in: str, expiry_hours: int, first_sent_at) -> str:
    if first_sent_at:
        wave_expiry = first_sent_at + timedelta(hours=expiry_hours)
    else:
        wave_expiry = datetime.now(ROME_TZ) + timedelta(hours=expiry_hours)
    arrival = date_type.fromisoformat(check_in)
    last_booking = datetime(
        arrival.year, arrival.month, arrival.day,
        DEFAULT_LAST_BOOKING_HOUR, 0, tzinfo=ROME_TZ
    ) - timedelta(days=1)
    return min(wave_expiry, last_booking).isoformat()


def _effective_status(status: str, rooms_allocated: int, rooms_booked: int,
                      holds: int, check_in: str, expiry_hours: int, first_sent_at) -> str:
    if status == "closed":
        return "closed"
    left = rooms_allocated - rooms_booked - holds
    if left <= 0:
        return "sold_out"
    exp = _expiry_time(check_in, expiry_hours, first_sent_at)
    if datetime.now(ROME_TZ).isoformat() >= exp:
        return "expired"
    return "active"


def _offer_to_dict(conn, offer_row, waves_rows) -> dict:
    (offer_id, hotel_id, check_in, nights, rooms_allocated, rooms_booked,
     status, auto_waves, wave_delay_hours, expiry_hours, booking_rate,
     notify_list, created_at) = offer_row

    _expire_holds(conn, offer_id)
    holds = _active_holds(conn, offer_id)
    rooms_left = max(0, rooms_allocated - rooms_booked - holds)

    first_sent = None
    waves = []
    for w in waves_rows:
        (_, _, wn, city, seg, seg_label, recip, wstatus, sent_at,
         extra, sent, opened, clicked, booked) = w
        if sent_at and (first_sent is None or sent_at < first_sent):
            first_sent = sent_at
        waves.append({
            "wave_number": wn, "city": city, "segment": seg,
            "segment_label": seg_label, "recipients": recip,
            "status": wstatus, "sent_at": sent_at.isoformat() if sent_at else None,
            "extra_added": extra,
            "metrics": {"sent": sent, "opened": opened, "clicked": clicked, "booked": booked},
        })

    notify = notify_list if isinstance(notify_list, list) else json.loads(notify_list or "[]")
    eff_status = _effective_status(status, rooms_allocated, rooms_booked,
                                   holds, check_in, expiry_hours, first_sent)

    return {
        "offer_id": offer_id, "hotel_id": hotel_id, "check_in": check_in,
        "nights": nights, "rooms_allocated": rooms_allocated,
        "rooms_booked": rooms_booked, "rooms_held": holds,
        "rooms_left": rooms_left, "status": eff_status,
        "auto_waves": auto_waves, "wave_delay_hours": wave_delay_hours,
        "expiry_hours": expiry_hours, "booking_rate": booking_rate,
        "waves": sorted(waves, key=lambda w: w["wave_number"]),
        "created_at": created_at.isoformat() if created_at else None,
        "expires_at": _expiry_time(check_in, expiry_hours, first_sent),
        "notify_waitlist": len(notify),
    }


# ---- public API ----

class InventoryStore:
    """Postgres-backed offer inventory."""

    def create_offer(self, hotel_id: str, check_in: str, nights: int,
                     rooms_allocated: int, city_segments: list[dict],
                     auto_waves: bool = False,
                     booking_rate: float = DEFAULT_BOOKING_RATE) -> dict:
        conn = _get_conn()
        if not conn:
            return {"error": "Database not available"}

        offer_id = f"off-{hashlib.sha256(f'{hotel_id}|{check_in}|{time.time()}'.encode()).hexdigest()[:8]}"

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO engine.inventory_offers
                    (offer_id, hotel_id, check_in, nights, rooms_allocated,
                     auto_waves, booking_rate)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (offer_id, hotel_id, check_in, nights, rooms_allocated,
                  auto_waves, booking_rate))

            for i, cs in enumerate(city_segments):
                recip = int(rooms_allocated / max(booking_rate, 0.01))
                recip = min(recip, cs.get("contact_limit", 500))
                cur.execute("""
                    INSERT INTO engine.inventory_waves
                        (offer_id, wave_number, city, segment, segment_label, recipients)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (offer_id, i + 1, cs["city"], cs["segment"],
                      cs.get("segment_label", cs["segment"]), recip))

        # Auto-send wave 1
        self._send_wave(offer_id, 1, booking_rate)

        logger.info("Created offer %s: %d rooms, %d waves", offer_id, rooms_allocated, len(city_segments))
        return self.get_offer(offer_id)

    def _send_wave(self, offer_id: str, wave_number: int, booking_rate: float):
        conn = _get_conn()
        if not conn:
            return
        seed = _deterministic_seed(offer_id, wave_number)
        with conn.cursor() as cur:
            cur.execute("SELECT recipients FROM engine.inventory_waves WHERE offer_id=%s AND wave_number=%s",
                        (offer_id, wave_number))
            row = cur.fetchone()
            if not row:
                return
            recip = row[0]

        metrics = _simulate_wave_metrics(recip, booking_rate, seed)
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE engine.inventory_waves
                SET status='sent', sent_at=NOW(),
                    sent=%s, opened=%s, clicked=%s, booked=%s
                WHERE offer_id=%s AND wave_number=%s
            """, (metrics["sent"], metrics["opened"], metrics["clicked"],
                  metrics["booked"], offer_id, wave_number))

            cur.execute("""
                UPDATE engine.inventory_offers
                SET rooms_booked = LEAST(rooms_allocated, rooms_booked + %s)
                WHERE offer_id = %s
            """, (metrics["booked"], offer_id))

        logger.info("Wave %d sent for %s: %d recipients, %d booked (simulated)",
                     wave_number, offer_id, recip, metrics["booked"])

    def send_next_wave(self, offer_id: str, extra_to_add: str | None = None) -> dict:
        conn = _get_conn()
        if not conn:
            return {"error": "Database not available"}

        offer = self.get_offer(offer_id)
        if not offer:
            return {"error": f"Offer not found: {offer_id}"}
        if offer["status"] == "sold_out":
            return {"error": "Offer is sold out"}
        if offer["status"] == "expired":
            return {"error": "Offer has expired"}

        pending = [w for w in offer["waves"] if w["status"] == "pending"]
        if not pending:
            return {"error": "No more waves to send"}

        wave = pending[0]
        wn = wave["wave_number"]

        # Recalculate recipients based on remaining rooms
        new_recip = int(offer["rooms_left"] / max(offer["booking_rate"], 0.01))
        new_recip = max(1, min(new_recip, 500))

        with conn.cursor() as cur:
            cur.execute("UPDATE engine.inventory_waves SET recipients=%s WHERE offer_id=%s AND wave_number=%s",
                        (new_recip, offer_id, wn))
            if extra_to_add:
                cur.execute("UPDATE engine.inventory_waves SET extra_added=%s WHERE offer_id=%s AND wave_number=%s",
                            (extra_to_add, offer_id, wn))

        self._send_wave(offer_id, wn, offer["booking_rate"])
        updated = self.get_offer(offer_id)
        sent_wave = next((w for w in updated["waves"] if w["wave_number"] == wn), None)
        return {"ok": True, "wave": sent_wave, "offer": updated}

    def add_hold(self, offer_id: str, guest_ref: str) -> dict:
        conn = _get_conn()
        if not conn:
            return {"error": "Database not available"}
        offer = self.get_offer(offer_id)
        if not offer:
            return {"error": f"Offer not found: {offer_id}"}
        if offer["rooms_left"] <= 0:
            return {"error": "No rooms available", "sold_out": True}
        with conn.cursor() as cur:
            cur.execute("INSERT INTO engine.inventory_holds (offer_id, guest_ref, created_at) VALUES (%s, %s, %s)",
                        (offer_id, guest_ref, time.time()))
        return {"ok": True, "held_until": int(time.time() + HOLD_DURATION_SECONDS)}

    def book_room(self, offer_id: str, guest_ref: str) -> dict:
        conn = _get_conn()
        if not conn:
            return {"error": "Database not available"}
        offer = self.get_offer(offer_id)
        if not offer:
            return {"error": f"Offer not found: {offer_id}"}
        with conn.cursor() as cur:
            cur.execute("DELETE FROM engine.inventory_holds WHERE offer_id=%s AND guest_ref=%s",
                        (offer_id, guest_ref))
            if offer["rooms_booked"] >= offer["rooms_allocated"]:
                return {"error": "No rooms available", "sold_out": True}
            cur.execute("UPDATE engine.inventory_offers SET rooms_booked = rooms_booked + 1 WHERE offer_id=%s",
                        (offer_id,))
        return {"ok": True, "offer": self.get_offer(offer_id)}

    def add_to_notify(self, offer_id: str, email: str) -> dict:
        conn = _get_conn()
        if not conn:
            return {"error": "Database not available"}
        with conn.cursor() as cur:
            cur.execute("SELECT notify_list FROM engine.inventory_offers WHERE offer_id=%s", (offer_id,))
            row = cur.fetchone()
            if not row:
                return {"error": f"Offer not found: {offer_id}"}
            current = row[0] if isinstance(row[0], list) else json.loads(row[0] or "[]")
            if email not in current:
                current.append(email)
                cur.execute("UPDATE engine.inventory_offers SET notify_list=%s WHERE offer_id=%s",
                            (json.dumps(current), offer_id))
        return {"ok": True, "waitlist_count": len(current)}

    def get_offer(self, offer_id: str) -> dict | None:
        conn = _get_conn()
        if not conn:
            return None
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM engine.inventory_offers WHERE offer_id=%s", (offer_id,))
            offer_row = cur.fetchone()
            if not offer_row:
                return None
            cur.execute("SELECT * FROM engine.inventory_waves WHERE offer_id=%s ORDER BY wave_number",
                        (offer_id,))
            waves = cur.fetchall()
        return _offer_to_dict(conn, offer_row, waves)

    def list_offers(self, hotel_id: str | None = None) -> list[dict]:
        conn = _get_conn()
        if not conn:
            return []
        with conn.cursor() as cur:
            if hotel_id:
                cur.execute("SELECT * FROM engine.inventory_offers WHERE hotel_id=%s ORDER BY created_at DESC",
                            (hotel_id,))
            else:
                cur.execute("SELECT * FROM engine.inventory_offers ORDER BY created_at DESC")
            offer_rows = cur.fetchall()

        result = []
        for orow in offer_rows:
            oid = orow[0]
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM engine.inventory_waves WHERE offer_id=%s ORDER BY wave_number", (oid,))
                waves = cur.fetchall()
            result.append(_offer_to_dict(conn, orow, waves))
        return result

    def check_auto_waves(self):
        conn = _get_conn()
        if not conn:
            return
        for offer in self.list_offers():
            if not offer["auto_waves"] or offer["status"] != "active":
                continue
            sent_waves = [w for w in offer["waves"] if w["status"] == "sent" and w["sent_at"]]
            pending = [w for w in offer["waves"] if w["status"] == "pending"]
            if not sent_waves or not pending:
                continue
            last_sent = max(datetime.fromisoformat(w["sent_at"]) for w in sent_waves)
            if (datetime.now(ROME_TZ) - last_sent).total_seconds() >= offer["wave_delay_hours"] * 3600:
                self.send_next_wave(offer["offer_id"])


store = InventoryStore()
