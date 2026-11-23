"""Offer inventory, allocation and wave management.

Demo implementation: in-memory store with simulated sends/bookings.
Realistic metrics are generated deterministically for demo repeatability.
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ROME_TZ = ZoneInfo("Europe/Rome")

DEFAULT_BOOKING_RATE = 0.03
HOLD_DURATION_SECONDS = 600  # 10 minutes
DEFAULT_EXPIRY_HOURS = 48
DEFAULT_LAST_BOOKING_HOUR = 18  # 18:00 day before arrival
DEFAULT_WAVE_DELAY_HOURS = 24


@dataclass
class WaveMetrics:
    sent: int = 0
    opened: int = 0
    clicked: int = 0
    booked: int = 0


@dataclass
class Wave:
    wave_number: int
    city: str
    segment: str
    segment_label: str
    recipients: int = 0
    status: str = "pending"  # pending | sent | completed
    sent_at: datetime | None = None
    extra_added: str | None = None
    metrics: WaveMetrics = field(default_factory=WaveMetrics)

    def to_dict(self) -> dict:
        return {
            "wave_number": self.wave_number,
            "city": self.city,
            "segment": self.segment,
            "segment_label": self.segment_label,
            "recipients": self.recipients,
            "status": self.status,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "extra_added": self.extra_added,
            "metrics": {
                "sent": self.metrics.sent,
                "opened": self.metrics.opened,
                "clicked": self.metrics.clicked,
                "booked": self.metrics.booked,
            },
        }


@dataclass
class Hold:
    created_at: float  # time.time()
    guest_ref: str


@dataclass
class Offer:
    offer_id: str
    hotel_id: str
    check_in: str
    nights: int
    rooms_allocated: int
    rooms_booked: int = 0
    holds: list[Hold] = field(default_factory=list)
    waves: list[Wave] = field(default_factory=list)
    status: str = "active"  # active | sold_out | expired | closed
    auto_waves: bool = False
    wave_delay_hours: int = DEFAULT_WAVE_DELAY_HOURS
    expiry_hours: int = DEFAULT_EXPIRY_HOURS
    created_at: datetime | None = None
    booking_rate: float = DEFAULT_BOOKING_RATE
    notify_list: list[str] = field(default_factory=list)

    @property
    def rooms_held(self) -> int:
        self._expire_holds()
        return len(self.holds)

    @property
    def rooms_left(self) -> int:
        return max(0, self.rooms_allocated - self.rooms_booked - self.rooms_held)

    def _expire_holds(self):
        now = time.time()
        self.holds = [h for h in self.holds if (now - h.created_at) < HOLD_DURATION_SECONDS]

    def is_sold_out(self) -> bool:
        return self.rooms_left <= 0

    def expiry_time(self) -> datetime:
        """Earliest of: expiry_hours after first wave sent, or last booking time."""
        sent_times = [w.sent_at for w in self.waves if w.sent_at]
        if sent_times:
            wave_expiry = min(sent_times) + timedelta(hours=self.expiry_hours)
        else:
            wave_expiry = datetime.now(ROME_TZ) + timedelta(hours=self.expiry_hours)

        # Last booking time: day before arrival, 18:00
        from datetime import date as date_type
        arrival = date_type.fromisoformat(self.check_in)
        last_booking = datetime(
            arrival.year, arrival.month, arrival.day,
            DEFAULT_LAST_BOOKING_HOUR, 0, tzinfo=ROME_TZ
        ) - timedelta(days=1)

        return min(wave_expiry, last_booking)

    def is_expired(self) -> bool:
        return datetime.now(ROME_TZ) >= self.expiry_time()

    def to_dict(self) -> dict:
        return {
            "offer_id": self.offer_id,
            "hotel_id": self.hotel_id,
            "check_in": self.check_in,
            "nights": self.nights,
            "rooms_allocated": self.rooms_allocated,
            "rooms_booked": self.rooms_booked,
            "rooms_held": self.rooms_held,
            "rooms_left": self.rooms_left,
            "status": self._effective_status(),
            "auto_waves": self.auto_waves,
            "wave_delay_hours": self.wave_delay_hours,
            "expiry_hours": self.expiry_hours,
            "booking_rate": self.booking_rate,
            "waves": [w.to_dict() for w in self.waves],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expiry_time().isoformat(),
            "notify_waitlist": len(self.notify_list),
        }

    def _effective_status(self) -> str:
        if self.status == "closed":
            return "closed"
        if self.is_sold_out():
            return "sold_out"
        if self.is_expired():
            return "expired"
        return self.status


def _deterministic_seed(offer_id: str, wave_num: int) -> int:
    return int(hashlib.sha256(f"{offer_id}|w{wave_num}".encode()).hexdigest()[:8], 16)


def _simulate_wave_metrics(recipients: int, booking_rate: float,
                           seed: int) -> WaveMetrics:
    """Generate realistic-looking metrics deterministically."""
    import random
    rng = random.Random(seed)

    sent = recipients
    open_rate = rng.uniform(0.25, 0.45)
    opened = int(sent * open_rate)
    click_rate = rng.uniform(0.15, 0.35)
    clicked = int(opened * click_rate)
    booked = max(1, int(sent * booking_rate * rng.uniform(0.7, 1.3)))
    booked = min(booked, clicked)

    return WaveMetrics(sent=sent, opened=opened, clicked=clicked, booked=booked)


class InventoryStore:
    """In-memory offer inventory. Demo only — resets on restart."""

    def __init__(self):
        self.offers: dict[str, Offer] = {}

    def create_offer(
        self,
        hotel_id: str,
        check_in: str,
        nights: int,
        rooms_allocated: int,
        city_segments: list[dict],
        auto_waves: bool = False,
        booking_rate: float = DEFAULT_BOOKING_RATE,
    ) -> Offer:
        offer_id = f"off-{hashlib.sha256(f'{hotel_id}|{check_in}|{time.time()}'.encode()).hexdigest()[:8]}"
        now = datetime.now(ROME_TZ)

        offer = Offer(
            offer_id=offer_id,
            hotel_id=hotel_id,
            check_in=check_in,
            nights=nights,
            rooms_allocated=rooms_allocated,
            auto_waves=auto_waves,
            booking_rate=booking_rate,
            created_at=now,
        )

        # Build waves from city×segment list (sorted by score descending)
        for i, cs in enumerate(city_segments):
            recipients = int(rooms_allocated / max(booking_rate, 0.01))
            recipients = min(recipients, cs.get("contact_limit", 500))
            wave = Wave(
                wave_number=i + 1,
                city=cs["city"],
                segment=cs["segment"],
                segment_label=cs.get("segment_label", cs["segment"]),
                recipients=recipients,
            )
            offer.waves.append(wave)

        # Automatically send wave 1
        if offer.waves:
            self._send_wave(offer, offer.waves[0])

        self.offers[offer_id] = offer
        logger.info("Created offer %s: %d rooms, %d waves", offer_id, rooms_allocated, len(offer.waves))
        return offer

    def _send_wave(self, offer: Offer, wave: Wave):
        wave.status = "sent"
        wave.sent_at = datetime.now(ROME_TZ)
        seed = _deterministic_seed(offer.offer_id, wave.wave_number)
        wave.metrics = _simulate_wave_metrics(wave.recipients, offer.booking_rate, seed)
        offer.rooms_booked = min(
            offer.rooms_allocated,
            offer.rooms_booked + wave.metrics.booked,
        )
        logger.info("Wave %d sent for %s: %d recipients, %d booked (simulated)",
                     wave.wave_number, offer.offer_id, wave.recipients, wave.metrics.booked)

    def send_next_wave(self, offer_id: str, extra_to_add: str | None = None) -> dict:
        offer = self.offers.get(offer_id)
        if not offer:
            return {"error": f"Offer not found: {offer_id}"}
        if offer.is_sold_out():
            return {"error": "Offer is sold out"}
        if offer.is_expired():
            return {"error": "Offer has expired"}

        pending = [w for w in offer.waves if w.status == "pending"]
        if not pending:
            return {"error": "No more waves to send"}

        wave = pending[0]
        if extra_to_add:
            wave.extra_added = extra_to_add
        # Recalculate recipients based on remaining rooms
        wave.recipients = int(offer.rooms_left / max(offer.booking_rate, 0.01))
        wave.recipients = max(1, min(wave.recipients, 500))
        self._send_wave(offer, wave)
        return {"ok": True, "wave": wave.to_dict(), "offer": offer.to_dict()}

    def add_hold(self, offer_id: str, guest_ref: str) -> dict:
        offer = self.offers.get(offer_id)
        if not offer:
            return {"error": f"Offer not found: {offer_id}"}
        if offer.rooms_left <= 0:
            return {"error": "No rooms available", "sold_out": True}
        offer.holds.append(Hold(created_at=time.time(), guest_ref=guest_ref))
        return {"ok": True, "held_until": int(time.time() + HOLD_DURATION_SECONDS)}

    def book_room(self, offer_id: str, guest_ref: str) -> dict:
        offer = self.offers.get(offer_id)
        if not offer:
            return {"error": f"Offer not found: {offer_id}"}
        # Remove hold for this guest
        offer.holds = [h for h in offer.holds if h.guest_ref != guest_ref]
        if offer.rooms_booked >= offer.rooms_allocated:
            return {"error": "No rooms available", "sold_out": True}
        offer.rooms_booked += 1
        if offer.is_sold_out():
            offer.status = "sold_out"
        return {"ok": True, "offer": offer.to_dict()}

    def add_to_notify(self, offer_id: str, email: str) -> dict:
        offer = self.offers.get(offer_id)
        if not offer:
            return {"error": f"Offer not found: {offer_id}"}
        if email not in offer.notify_list:
            offer.notify_list.append(email)
        return {"ok": True, "waitlist_count": len(offer.notify_list)}

    def get_offer(self, offer_id: str) -> dict | None:
        offer = self.offers.get(offer_id)
        return offer.to_dict() if offer else None

    def list_offers(self, hotel_id: str | None = None) -> list[dict]:
        offers = self.offers.values()
        if hotel_id:
            offers = [o for o in offers if o.hotel_id == hotel_id]
        return [o.to_dict() for o in sorted(offers, key=lambda o: o.created_at or datetime.min, reverse=True)]

    def check_auto_waves(self):
        """Called periodically: send next wave for auto-wave offers past delay."""
        now = datetime.now(ROME_TZ)
        for offer in self.offers.values():
            if not offer.auto_waves or offer.is_sold_out() or offer.is_expired():
                continue
            sent_waves = [w for w in offer.waves if w.status == "sent"]
            pending = [w for w in offer.waves if w.status == "pending"]
            if not sent_waves or not pending:
                continue
            last_sent = max(w.sent_at for w in sent_waves if w.sent_at)
            if (now - last_sent).total_seconds() >= offer.wave_delay_hours * 3600:
                self.send_next_wave(offer.offer_id)


# Singleton store
store = InventoryStore()
