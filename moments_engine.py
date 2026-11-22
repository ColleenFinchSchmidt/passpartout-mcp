"""Moments engine: combines sources, checks constraints, produces offer suggestions.

Also includes a backtest function that replays historical weather.
"""

import hashlib
import json
import time
from collections import Counter
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

    suggestions = []

    for city in hotel["guest_cities"]:
        if _was_contacted_recently(city["name"], contacts, cooldown, today):
            continue

        weather = score_weather(hotel, city, settings)
        air = score_air_quality(city, settings)

        for days_out in range(window_lo, window_hi + 1):
            check_in = today + timedelta(days=days_out)

            if _is_blacked_out(check_in, hotel.get("blackout_dates", [])):
                continue

            blocked, strike_reason = is_strike_blocking(
                check_in, hotel.get("travel_modes", []), data_dir
            )
            if blocked:
                continue

            holidays = score_holidays(check_in, settings, data_dir)
            seasonal = score_seasonal(check_in, data_dir)
            events = score_events(hotel, check_in, settings)

            windows = _available_nights(
                avail, check_in, min_nights, hotel["max_rooms_per_offer"]
            )
            if not windows:
                continue

            best_window = windows[0]
            avail_score = min(best_window["rooms_free"] / max(hotel["rooms"], 1) * 2, 1.0)

            combined = (
                weather["score"] * weights.get("weather", 0.35)
                + air["score"] * weights.get("air_quality", 0.10)
                + holidays["score"] * weights.get("holiday", 0.20)
                + seasonal["score"] * weights.get("seasonal", 0.15)
                + avail_score * weights.get("availability", 0.20)
            )

            if combined < min_score:
                continue

            all_reasons = (
                weather["reasons"]
                + air["reasons"]
                + holidays["reasons"]
                + seasonal["reasons"]
                + events["reasons"]
            )
            if not all_reasons:
                continue

            price = _compute_price(hotel, best_window["nights"], combined, settings)

            suggestion = {
                "hotel": hotel["name"],
                "hotel_id": hotel["id"],
                "guest_city": city["name"],
                "check_in": best_window["check_in"],
                "nights": best_window["nights"],
                "rooms_to_offer": best_window["rooms_to_offer"],
                "rooms_free": best_window["rooms_free"],
                "score": round(combined, 3),
                "price": price,
                "reasons": all_reasons,
                "source_scores": {
                    "weather": weather["score"],
                    "air_quality": air["score"],
                    "holiday": holidays["score"],
                    "seasonal": seasonal["score"],
                    "events": events["score"],
                    "availability": round(avail_score, 2),
                },
            }
            suggestions.append(suggestion)

    best_per_city: dict[str, dict] = {}
    for s in suggestions:
        key = s["guest_city"]
        if key not in best_per_city or s["score"] > best_per_city[key]["score"]:
            best_per_city[key] = s

    return sorted(best_per_city.values(), key=lambda s: -s["score"])


def explain_moments(hotel: dict, settings: dict, data_dir: Path,
                    start_date: date, end_date: date) -> list[dict]:
    """Explain which moments fire for each date in a range."""
    results = []
    d = start_date
    while d <= end_date:
        day_result = {"date": d.isoformat(), "weekday": d.strftime("%A"), "sources": {}}

        for city in hotel["guest_cities"]:
            weather = score_weather(hotel, city, settings)
            air = score_air_quality(city, settings)
            holidays = score_holidays(d, settings, data_dir)
            seasonal = score_seasonal(d, data_dir)
            blocked, strike_note = is_strike_blocking(d, hotel.get("travel_modes", []), data_dir)

            weights = settings.get("score_weights", {})
            combined = (
                weather["score"] * weights.get("weather", 0.35)
                + air["score"] * weights.get("air_quality", 0.10)
                + holidays["score"] * weights.get("holiday", 0.20)
                + seasonal["score"] * weights.get("seasonal", 0.15)
            )

            all_reasons = (
                weather["reasons"] + air["reasons"]
                + holidays["reasons"] + seasonal["reasons"]
            )
            if blocked:
                all_reasons.append(f"BLOCKED: {strike_note}")

            day_result["sources"][city["name"]] = {
                "combined_score": round(combined, 3),
                "fires": combined >= settings.get("min_score_to_fire", 0.5) and not blocked,
                "weather": {"score": weather["score"], "reasons": weather["reasons"]},
                "air_quality": {"score": air["score"], "reasons": air["reasons"]},
                "holidays": {"score": holidays["score"], "reasons": holidays["reasons"]},
                "seasonal": {"score": seasonal["score"], "reasons": seasonal["reasons"]},
                "strike_blocked": blocked,
                "all_reasons": all_reasons,
            }

        results.append(day_result)
        d += timedelta(days=1)

    return results


def _simulated_free_rooms(hotel: dict, d: date) -> int:
    """Deterministic fake occupancy for backtesting (no real history)."""
    total = hotel["rooms"]
    dow = d.weekday()
    base = 0.75 if dow in (4, 5) else 0.60 if dow == 6 else 0.45
    m = d.month
    if m in (7, 8):
        base += 0.20
    elif m in (6, 9):
        base += 0.10
    elif m == 12:
        base += 0.15
    elif m in (1, 2, 3):
        base -= 0.10
    h = int(hashlib.sha256(d.isoformat().encode()).hexdigest()[:8], 16)
    base += ((h % 20) - 10) / 100.0
    return max(total - round(total * max(0.05, min(0.95, base))), 0)


def run_backtest(hotel: dict, settings: dict, months: int = 12,
                 data_dir: Path | None = None) -> dict:
    """Replay historical weather + holidays + seasonal + occupancy, flag weekends."""
    if data_dir is None:
        data_dir = Path(__file__).parent / "moments_data"

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=months * 30)

    min_score = settings.get("min_score_to_fire", 0.25)
    blackout_md = {bd[5:] for bd in hotel.get("blackout_dates", [])}

    # Redistribute air-quality weight (no historical AQ data)
    w = settings.get("score_weights", {})
    aq = w.get("air_quality", 0.10)
    bt_w = {
        "weather": w.get("weather", 0.35) + aq * 0.4,
        "holiday": w.get("holiday", 0.20) + aq * 0.3,
        "seasonal": w.get("seasonal", 0.15) + aq * 0.15,
        "availability": w.get("availability", 0.20) + aq * 0.15,
    }

    # Fetch historical weather
    hotel_data = _cached_get(
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={hotel['coords']['lat']}&longitude={hotel['coords']['lon']}"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&timezone=Europe/Rome&start_date={start_date.isoformat()}&end_date={end_date.isoformat()}"
    )

    city_data = {}
    for city in hotel["guest_cities"]:
        time.sleep(0.3)
        city_data[city["name"]] = _cached_get(
            f"https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={city['coords']['lat']}&longitude={city['coords']['lon']}"
            f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"
            f"&timezone=Europe/Rome&start_date={start_date.isoformat()}&end_date={end_date.isoformat()}"
        )

    if not hotel_data or not all(city_data.values()):
        return {"error": "Could not fetch historical weather data."}

    hotel_daily = hotel_data["daily"]
    hotel_index = {d: i for i, d in enumerate(hotel_daily["time"])}

    rows = []
    d = start_date
    while d <= end_date:
        if d.weekday() == 4:  # Friday
            fri, sat, sun = d, d + timedelta(days=1), d + timedelta(days=2)
            weekend_dates = [fri, sat, sun]

            # Blackout check (year-agnostic): skip if any weekend day is blacked out
            if any(wd.strftime("%m-%d") in blackout_md for wd in weekend_dates):
                d += timedelta(days=1)
                continue

            for city_name, cdata in city_data.items():
                if not cdata:
                    continue
                city_daily = cdata["daily"]
                city_index = {dd: i for i, dd in enumerate(city_daily["time"])}

                # --- Weather scoring ---
                weather_score = 0.0
                weather_reasons = []
                moment_types = []

                city_wk_codes = []
                hotel_wk_codes = []
                for wd in weekend_dates:
                    ci = city_index.get(wd.isoformat())
                    hi = hotel_index.get(wd.isoformat())
                    if ci is not None:
                        city_wk_codes.append(city_daily["weather_code"][ci])
                    if hi is not None:
                        hotel_wk_codes.append(hotel_daily["weather_code"][hi])

                if not city_wk_codes:
                    d += timedelta(days=1)
                    continue

                rain_days_city = sum(1 for c in city_wk_codes if is_rainy(c))
                rain_days_hotel = sum(1 for c in hotel_wk_codes if is_rainy(c))
                hotel_better = rain_days_hotel < rain_days_city
                if hotel_better and rain_days_city >= 2:
                    weather_score = max(weather_score, 0.8)
                    weather_reasons.append(
                        f"Rain in {city_name} ({rain_days_city}/3 days), drier at hotel"
                    )
                    moment_types.append("rain_escape")
                elif hotel_better and rain_days_city == 1:
                    weather_score = max(weather_score, 0.4)
                    weather_reasons.append(
                        f"Some rain in {city_name}, drier at hotel"
                    )
                    moment_types.append("rain_escape")

                snow_days = sum(1 for c in hotel_wk_codes if is_snowy(c))
                if snow_days > 0:
                    weather_score = max(weather_score, 0.7)
                    weather_reasons.append(
                        f"Snow at {hotel['town']} ({snow_days} days)"
                    )
                    moment_types.append("snow")

                pre_fri = []
                for back in range(1, 4):
                    pre_d = (fri - timedelta(days=back)).isoformat()
                    ci = city_index.get(pre_d)
                    if ci is not None:
                        pre_fri.append(city_daily["weather_code"][ci])
                if len(pre_fri) >= 3 and all(is_rainy(c) for c in pre_fri):
                    sunny_wk = sum(
                        1 for c in hotel_wk_codes if is_sunny(c)
                    )
                    if sunny_wk >= 1:
                        weather_score = max(weather_score, 0.9)
                        weather_reasons.append(
                            f"Sunny rebound at hotel after rain in {city_name}"
                        )
                        moment_types.append("sunny_rebound")

                # --- Holiday scoring ---
                holidays = score_holidays(fri, settings, data_dir)
                for r in holidays.get("reasons", []):
                    rl = r.lower()
                    if "ponte" in rl or "bridge" in rl:
                        moment_types.append("ponte")
                    elif "school" in rl:
                        moment_types.append("school_holiday")
                    elif holidays["score"] > 0:
                        moment_types.append("public_holiday")

                # --- Seasonal scoring ---
                seasonal = score_seasonal(fri, data_dir)
                if seasonal["score"] > 0:
                    moment_types.append("seasonal")

                # --- Availability scoring (simulated occupancy) ---
                free = _simulated_free_rooms(hotel, fri)
                avail_score = min(free / max(hotel["rooms"], 1) * 2, 1.0)
                if avail_score > 0.6:
                    moment_types.append("low_occupancy")

                # --- Combine with backtest weights ---
                combined = (
                    weather_score * bt_w["weather"]
                    + holidays["score"] * bt_w["holiday"]
                    + seasonal["score"] * bt_w["seasonal"]
                    + avail_score * bt_w["availability"]
                )

                all_reasons = (
                    weather_reasons
                    + holidays.get("reasons", [])
                    + seasonal.get("reasons", [])
                )
                if avail_score > 0.6:
                    all_reasons.append(
                        f"Low occupancy ({free}/{hotel['rooms']} rooms free)"
                    )

                flagged = combined >= min_score

                rows.append({
                    "weekend_friday": fri.isoformat(),
                    "city": city_name,
                    "flagged": flagged,
                    "score": round(combined, 3),
                    "moment_types": list(set(moment_types)),
                    "reasons": all_reasons,
                    "city_weather": [describe_code(c) for c in city_wk_codes],
                    "hotel_weather": [describe_code(c) for c in hotel_wk_codes],
                    "source_scores": {
                        "weather": round(weather_score, 2),
                        "holiday": holidays["score"],
                        "seasonal": seasonal["score"],
                        "availability": round(avail_score, 2),
                    },
                })

        d += timedelta(days=1)

    # Filter to flagged, then apply 1-per-guest-per-week cap
    flagged_all = [r for r in rows if r["flagged"]]
    flagged_all.sort(key=lambda r: -r["score"])
    kept = []
    kept_dates: dict[str, list[date]] = {}
    for row in flagged_all:
        city = row["city"]
        fri = date.fromisoformat(row["weekend_friday"])
        if any(abs((fri - p).days) < 7 for p in kept_dates.get(city, [])):
            continue
        kept.append(row)
        kept_dates.setdefault(city, []).append(fri)
    kept.sort(key=lambda r: r["weekend_friday"])

    # Per-month and per-moment-type counts
    month_counts: Counter = Counter()
    type_counts: Counter = Counter()
    for row in kept:
        month_counts[row["weekend_friday"][:7]] += 1
        for t in row["moment_types"]:
            type_counts[t] += 1

    return {
        "hotel": hotel["name"],
        "period": f"{start_date.isoformat()} to {end_date.isoformat()}",
        "months": months,
        "total_weekends": len(rows),
        "flagged_before_dedup": len(flagged_all),
        "flagged_weekends": len(kept),
        "flag_rate_pct": round(len(kept) / max(len(rows), 1) * 100, 1),
        "per_month": dict(sorted(month_counts.items())),
        "per_type": dict(type_counts.most_common()),
        "thresholds": {
            "min_score": min_score,
            "backtest_weights": {k: round(v, 3) for k, v in bt_w.items()},
            "note": "Air-quality weight redistributed (no historical AQ data)",
        },
        "flagged": kept,
        "demo": True,
    }
