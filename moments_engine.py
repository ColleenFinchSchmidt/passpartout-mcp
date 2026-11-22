"""Moments engine: combines sources, checks constraints, produces offer suggestions.

Also includes a backtest function that replays historical weather.
"""

import json
import time
from datetime import date, timedelta
from pathlib import Path

from moments_sources import (
    _cached_get,
    describe_code,
    fetch_forecast,
    is_rainy,
    is_snowy,
    is_sunny,
    is_strike_blocking,
    score_air_quality,
    score_events,
    score_holidays,
    score_seasonal,
    score_weather,
)


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text())


def _available_nights(
    avail: dict, start: date, min_nights: int, max_rooms: int,
) -> list[dict]:
    free_rooms = avail.get("free_rooms", {})
    windows = []

    for length in range(min_nights, min_nights + 5):
        nights_ok = True
        min_free = None
        for i in range(length):
            d = (start + timedelta(days=i)).isoformat()
            free = free_rooms.get(d, 0)
            if free < 1:
                nights_ok = False
                break
            min_free = min(min_free, free) if min_free is not None else free

        if nights_ok and min_free is not None:
            rooms_to_offer = min(min_free, max_rooms)
            windows.append({
                "check_in": start.isoformat(),
                "nights": length,
                "rooms_free": min_free,
                "rooms_to_offer": rooms_to_offer,
            })

    return windows


def _is_blacked_out(d: date, blackout: list[str]) -> bool:
    return d.isoformat() in blackout


def _compute_price(hotel: dict, nights: int, combined_score: float, settings: dict) -> dict:
    pricing = settings.get("pricing", {})
    base_disc = pricing.get("base_discount_pct", 15)
    max_disc = pricing.get("high_score_discount_pct", 25)
    score_for_max = pricing.get("score_for_max_discount", 0.8)

    disc_pct = base_disc + (max_disc - base_disc) * min(combined_score / score_for_max, 1.0)
    disc_pct = min(disc_pct, hotel["max_discount_pct"])

    public_total = hotel["public_rate_eur"] * nights
    private_rate = round(hotel["public_rate_eur"] * (1 - disc_pct / 100))
    private_rate = max(private_rate, hotel["lowest_price_eur"])
    private_total = private_rate * nights

    return {
        "public_rate_per_night": hotel["public_rate_eur"],
        "public_total": public_total,
        "private_rate_per_night": private_rate,
        "private_total": private_total,
        "discount_pct": round(disc_pct, 1),
        "you_save": public_total - private_total,
    }


def _was_contacted_recently(city_name: str, contacts: dict, cooldown: int, today: date) -> bool:
    last = contacts.get("last_contact", {}).get(city_name)
    if not last:
        return False
    return (today - date.fromisoformat(last)).days < cooldown


def evaluate_hotel(hotel: dict, settings: dict, data_dir: Path, today: date | None = None) -> list[dict]:
    today = today or date.today()
    avail = load_json(data_dir / "availability.json")
    contacts = load_json(data_dir / "contacts.json")

    window_lo, window_hi = settings["booking_window_days"]
    min_nights = settings.get("min_nights", 2)
    cooldown = settings.get("contact_cooldown_days", 7)
    min_score = settings.get("min_score_to_fire", 0.5)
    weights = settings.get("score_weights", {})
