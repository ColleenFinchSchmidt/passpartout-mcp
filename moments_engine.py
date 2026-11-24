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
    is_grey,
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
try:
    from hotel_profile import compute_hotel_segment_fit
    from local_events import event_segment_weights
except ImportError:
    compute_hotel_segment_fit = None
    event_segment_weights = None


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


SEGMENT_MIX = {
    "young_couples":  {"min_discount_pct": 15, "preferred": ["spa_day", "welcome_prosecco"]},
    "retirees":       {"min_discount_pct": 10, "preferred": ["dinner", "late_checkout"]},
    "families":       {"min_discount_pct":  8, "preferred": ["parking", "boat_borromean"]},
    "remote_workers": {"min_discount_pct": 12, "preferred": ["late_checkout", "spa_pass"]},
    "friends_groups": {"min_discount_pct": 10, "preferred": ["welcome_prosecco", "boat_borromean"]},
}

SEGMENT_INCLUSIONS_FALLBACK = {
    "young_couples": ["spa_access", "aperitivo"],
    "retirees": ["dinner", "late_checkout", "garden_tour"],
    "families": ["kids_free", "extra_bed"],
    "remote_workers": ["workspace", "long_stay_rate"],
    "friends_groups": ["group_activity", "wine_tasting"],
}


def _extra_stay_multiplier(unit: str, nights: int, guests: int = 2) -> int:
    if unit == "per_night_per_person":
        return nights * guests
    elif unit == "per_stay_per_person":
        return guests
    elif unit == "per_night_per_room":
        return nights
    else:
        return 1


def _compute_segment_package(
    hotel: dict, nights: int, combined_score: float,
    segment: dict, settings: dict, check_in: date | None = None,
) -> dict:
    """Build a per-segment package that maximises guest-perceived value.

    Algorithm:
    1. Compute total budget from score (same formula as before).
    2. Reserve the segment's minimum headline discount.
    3. Fill extras by value/cost ratio (free first, then preferred, then rest).
    4. Give any leftover budget back as additional discount.
    Guardrail: total give-away never exceeds max_discount_pct of public total.
    """
    base_price = _compute_price(hotel, nights, combined_score, settings)
    seg_key = segment["segment"]
    mix = SEGMENT_MIX.get(seg_key, {"min_discount_pct": 10, "preferred": []})

    public_rate = hotel["public_rate_eur"]
    public_total = public_rate * nights
    max_giveaway = public_rate * hotel["max_discount_pct"] / 100 * nights

    score_disc_pct = min(base_price["discount_pct"], hotel["max_discount_pct"])
    total_budget = public_rate * score_disc_pct / 100 * nights

    min_disc_pct = min(mix["min_discount_pct"], hotel["max_discount_pct"])

    headline_rate = round(public_rate * (1 - min_disc_pct / 100))
    headline_rate = max(headline_rate, hotel["lowest_price_eur"])
    headline_discount_total = (public_rate - headline_rate) * nights

    guests = 2
    hotel_extras = hotel.get("extras", [])
    candidates = []
    if hotel_extras:
        preferred_ids = set(mix.get("preferred", []))
        for ex in hotel_extras:
            if seg_key not in ex.get("segments", []):
                continue
            avail = ex.get("available_months")
            if avail and check_in and check_in.month not in avail:
                continue
            unit = ex.get("unit", "per_stay_per_room")
            mult = _extra_stay_multiplier(unit, nights, guests)
            cost = ex["cost_to_hotel"] * mult
            value = ex["value_to_guest"] * mult
            candidates.append({
                "id": ex["id"],
                "name": ex["name"],
                "value_to_guest": ex["value_to_guest"],
                "cost_to_hotel": ex["cost_to_hotel"],
                "unit": unit,
                "limit": ex.get("limit", ""),
                "stay_value": value,
                "stay_cost": cost,
                "is_preferred": ex["id"] in preferred_ids,
            })
    else:
        hotel_experiences = set(hotel.get("experiences", []))
        possible = SEGMENT_INCLUSIONS_FALLBACK.get(seg_key, [])
        for inc in possible:
            if inc in hotel_experiences or inc in (
                "kids_free", "extra_bed", "late_checkout", "workspace",
                "long_stay_rate", "group_activity",
            ):
                candidates.append({
                    "id": inc, "name": inc.replace("_", " ").title(),
                    "value_to_guest": 0, "cost_to_hotel": 0,
                    "unit": "per_stay_per_room", "limit": "",
                    "stay_value": 0, "stay_cost": 0,
                    "is_preferred": False,
                })

    extras_budget = max(0, total_budget - headline_discount_total)

    free_extras = [c for c in candidates if c["stay_cost"] == 0]
    paid = [c for c in candidates if c["stay_cost"] > 0]

    # Deduplicate same-amenity extras (e.g. spa_pass vs spa_day):
    # keep the per-stay variant when the per-night one exceeds budget.
    amenity_groups: dict[str, list] = {}
    for c in paid:
        prefix = c["id"].rsplit("_", 1)[0]
        amenity_groups.setdefault(prefix, []).append(c)
    deduped_paid = []
    for prefix, group in amenity_groups.items():
        if len(group) == 1:
            deduped_paid.extend(group)
        else:
            per_stay = [c for c in group if "per_stay" in c["unit"]]
            per_night = [c for c in group if "per_night" in c["unit"]]
            if per_stay and per_night:
                cheapest_per_stay = min(per_stay, key=lambda c: c["stay_cost"])
                cheapest_per_night = min(per_night, key=lambda c: c["stay_cost"])
                if cheapest_per_night["stay_cost"] * 2 <= extras_budget:
                    deduped_paid.append(cheapest_per_night)
                else:
                    deduped_paid.append(cheapest_per_stay)
            else:
                deduped_paid.extend(group)

    paid_preferred = sorted(
        [c for c in deduped_paid if c["is_preferred"]],
        key=lambda c: c["stay_value"] / max(c["stay_cost"], 0.01),
        reverse=True,
    )
    paid_rest = sorted(
        [c for c in deduped_paid if not c["is_preferred"]],
        key=lambda c: c["stay_value"] / max(c["stay_cost"], 0.01),
        reverse=True,
    )

    extras = list(free_extras)
    total_extras_cost = 0
    total_extras_value = sum(c["stay_value"] for c in free_extras)
    for c in paid_preferred + paid_rest:
        if total_extras_cost + c["stay_cost"] <= extras_budget:
            extras.append(c)
            total_extras_cost += c["stay_cost"]
            total_extras_value += c["stay_value"]

    leftover = extras_budget - total_extras_cost
    if leftover > 0:
        final_rate = headline_rate - int(leftover / nights)
        final_rate = max(final_rate, hotel["lowest_price_eur"])
    else:
        final_rate = headline_rate

    discount_total = (public_rate - final_rate) * nights
    if discount_total + total_extras_cost > max_giveaway:
        final_rate = -(-int(public_rate * nights - max_giveaway + total_extras_cost) // nights)
        final_rate = max(final_rate, hotel["lowest_price_eur"])
        discount_total = (public_rate - final_rate) * nights

    private_total = final_rate * nights

    disc_pct = round((1 - final_rate / public_rate) * 100, 1)
    total_giveaway = discount_total + total_extras_cost

    return {
        "public_rate_per_night": public_rate,
        "public_total": public_total,
        "private_rate_per_night": final_rate,
        "private_total": private_total,
        "discount_pct": disc_pct,
        "you_save": public_total - private_total,
        "extras": [{
            "id": e["id"], "name": e["name"],
            "value_to_guest": e["value_to_guest"],
            "cost_to_hotel": e["cost_to_hotel"],
            "unit": e["unit"], "limit": e["limit"],
            "stay_value": e["stay_value"],
            "stay_cost": e["stay_cost"],
        } for e in extras],
        "extras_value_total": round(total_extras_value),
        "extras_cost_total": round(total_extras_cost),
        "total_giveaway": round(total_giveaway),
        "nights": nights,
        "guests": guests,
        "starting_mix": segment.get("starting_mix", ""),
    }


def _was_contacted_recently(city_name: str, contacts: dict, cooldown: int, today: date) -> bool:
    last = contacts.get("last_contact", {}).get(city_name)
    if not last:
        return False
    return (today - date.fromisoformat(last)).days < cooldown


# ---------------------------------------------------------------------------
# Additive scoring: each signal adds its contribution, total capped at 1.0.
# ---------------------------------------------------------------------------

def _classify_holidays(holiday_result: dict) -> dict:
    reasons = holiday_result.get("reasons", [])
    score = holiday_result.get("score", 0)
    is_ponte = any("ponte" in r.lower() or "bridge" in r.lower() for r in reasons)
    is_school = any("school" in r.lower() for r in reasons)
    return {
        "ponte": is_ponte,
        "school": is_school,
        "public": score > 0 and not is_ponte and not is_school,
    }


def _active_signals(check_in: date, weather_score: float, air_score: float,
                    holiday_result: dict, seasonal_result: dict,
                    days_out: int) -> list[str]:
    """Determine which demand signals are active for this moment."""
    signals = []
    dow = check_in.weekday()
    is_weekend = dow >= 4

    if weather_score >= 0.5 and is_weekend:
        signals.append("rainy_weekend")
    if air_score >= 0.4:
        signals.append("smog_grey_week")
    if dow in (0, 1, 2, 3):
        signals.append("midweek_dates")

    h = _classify_holidays(holiday_result)
    if h["ponte"]:
        signals.append("long_weekend")
    if h["school"]:
        signals.append("school_holidays")
    if days_out <= 4:
        signals.append("short_notice")
    if seasonal_result.get("score", 0) > 0:
        for r in seasonal_result.get("reasons", []):
            signals.append("seasonal_gardens")
            break

    return signals


def _per_segment_scores(
    moment_strength: float,
    active_signals: list[str],
    hotel: dict,
    settings: dict,
    seasonal_events: list[dict] | None = None,
) -> list[dict]:
    """Compute per-segment scores: moment × segment_weight × hotel_fit.

    Returns a sorted list of {segment, label, score, reasons} for segments
    above 0.3 threshold, top 2 max.
    """
    segments = settings.get("segments", {})
    if not segments:
        return []
    weight_table = settings.get("signal_segment_weights", {})
    if compute_hotel_segment_fit:
        hotel_fit = compute_hotel_segment_fit(hotel, settings)
    else:
        hotel_fit = {seg: 0.5 for seg in segments}
    excluded = set(hotel.get("segments_excluded", []))

    results = []
    for seg_key, seg_info in segments.items():
        if seg_key in excluded:
            continue

        signal_weights = []
        for signal in active_signals:
            w = weight_table.get(signal, {}).get(seg_key, 0.3)
            signal_weights.append(w)

        if seasonal_events and event_segment_weights:
            for ev in seasonal_events:
                ev_weights = event_segment_weights(ev, settings)
                signal_weights.append(ev_weights.get(seg_key, 0.3))

        if not signal_weights:
            continue

        avg_weight = sum(signal_weights) / len(signal_weights)
        fit = hotel_fit.get(seg_key, 0.5)
        seg_score = moment_strength * avg_weight * fit

        if seg_score >= 0.3:
            results.append({
                "segment": seg_key,
                "label": seg_info.get("label", seg_key),
                "score": round(seg_score, 3),
                "segment_weight": round(avg_weight, 2),
                "hotel_fit": fit,
                "channels": seg_info.get("channels", []),
                "starting_mix": seg_info.get("starting_mix", ""),
            })

    results.sort(key=lambda x: -x["score"])
    return results[:2]


def _additive_score(
    weather_raw: float,
    aq_raw: float,
    seasonal_raw: float,
    free_rooms: int,
    total_rooms: int,
    holiday_result: dict,
    min_free_rooms: int = 1,
    hotel_weather_penalty: float = 0.0,
) -> float:
    empty_ratio = max(0, free_rooms / max(total_rooms, 1))

    if empty_ratio < 0.30:
        return 0.0

    score = 0.0
    score += min(weather_raw * 0.45, 0.40)
    score += min(aq_raw * 0.35, 0.25)
    score += min(seasonal_raw * 0.45, 0.30)
    score += min(empty_ratio * 0.35, 0.30)

    if free_rooms >= min_free_rooms:
        h = _classify_holidays(holiday_result)
        if h["ponte"]:
            score += 0.20
        if h["school"]:
            score += 0.10
        if h["public"] and empty_ratio > 0.30:
            score += 0.05

    score -= hotel_weather_penalty

    return max(min(score, 1.0), 0.0)


# ---------------------------------------------------------------------------
# Realistic Lake Como occupancy model (replaces random SHA-256 noise)
# ---------------------------------------------------------------------------

def _realistic_occupancy_rate(hotel: dict, d: date, holidays_data: dict) -> float:
    m = d.month
    dow = d.weekday()
    is_weekend = dow >= 4

    if m in (7, 8):
        base = 0.92 if is_weekend else 0.78
    elif m in (6, 9):
        base = 0.72 if is_weekend else 0.50
    elif m in (4, 5, 10):
        base = 0.58 if is_weekend else 0.38
    elif m == 11:
        base = 0.30 if is_weekend else 0.15
    else:
        base = 0.35 if is_weekend else 0.20

    md = d.strftime("%m-%d")
    prev_md = (d - timedelta(days=1)).strftime("%m-%d")
    next_md = (d + timedelta(days=1)).strftime("%m-%d")
    nearby = {prev_md, md, next_md}

    for h in holidays_data.get("public_holidays", []):
        if h["date"][5:] in nearby:
            base = max(base, 0.88 if is_weekend else 0.72)

    for p in holidays_data.get("ponti", []):
        if p["from"][5:] <= md <= p["to"][5:]:
            base = max(base, 0.85)

    if (m == 12 and d.day >= 23) or (m == 1 and d.day <= 2):
        base = max(base, 0.82)
    if m == 8 and 14 <= d.day <= 16:
        base = max(base, 0.95)

    h = int(hashlib.sha256(d.isoformat().encode()).hexdigest()[:8], 16)
    noise = ((h % 7) - 3) / 100.0
    return max(0.05, min(0.98, base + noise))


def _free_rooms(hotel: dict, d: date, holidays_data: dict) -> int:
    total = hotel["rooms"]
    occ = _realistic_occupancy_rate(hotel, d, holidays_data)
    return max(total - round(total * occ), 0)


# ---------------------------------------------------------------------------
# Live scoring
# ---------------------------------------------------------------------------

def _build_availability(hotel: dict, data_dir: Path, start: date, end: date) -> dict:
    """Generate availability from the occupancy model for dates not in the JSON."""
    holidays_path = data_dir / "holidays.json"
    holidays_data = json.loads(holidays_path.read_text()) if holidays_path.exists() else {}
    free = {}
    d = start
    while d <= end:
        free[d.isoformat()] = _free_rooms(hotel, d, holidays_data)
        d += timedelta(days=1)
    return {"free_rooms": free}


def evaluate_hotel(hotel: dict, settings: dict, data_dir: Path, today: date | None = None) -> list[dict]:
    today = today or date.today()
    avail_file = load_json(data_dir / "availability.json")
    contacts = load_json(data_dir / "contacts.json")

    window_lo, window_hi = settings["booking_window_days"]
    min_nights = settings.get("min_nights", 2)
    cooldown = settings.get("contact_cooldown_days", 7)
    min_score = settings.get("min_score_to_fire", 0.5)
    min_free = settings.get("min_free_rooms", 1)

    file_hotel = avail_file.get("hotel_id")
    if file_hotel and file_hotel == hotel["id"]:
        avail = avail_file
    else:
        avail = _build_availability(
            hotel, data_dir,
            today + timedelta(days=window_lo),
            today + timedelta(days=window_hi + min_nights + 5),
        )

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

            check_out = check_in + timedelta(days=min_nights)
            holidays = score_holidays(check_in, settings, data_dir, stay_end=check_out)
            seasonal = score_seasonal(check_in, data_dir, hotel_id=hotel["id"], hotel=hotel)
            events = score_events(hotel, check_in, settings)

            windows = _available_nights(
                avail, check_in, min_nights, hotel["max_rooms_per_offer"]
            )
            if not windows:
                continue

            best_window = windows[0]

            combined = _additive_score(
                weather["score"],
                air["score"],
                seasonal["score"],
                best_window["rooms_free"],
                hotel["rooms"],
                holidays,
                min_free,
                hotel_weather_penalty=weather.get("hotel_weather_penalty", 0.0),
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
            empty_ratio = best_window["rooms_free"] / max(hotel["rooms"], 1)

            also_on = seasonal.get("also_on", [])
            event_sources = seasonal.get("event_sources", [])

            active_sigs = _active_signals(
                check_in, weather["score"], air["score"],
                holidays, seasonal, days_out,
            )
            top_segments = _per_segment_scores(
                combined, active_sigs, hotel, settings,
            )
            for seg in top_segments:
                seg["package"] = _compute_segment_package(
                    hotel, best_window["nights"], combined, seg, settings,
                    check_in=check_in,
                )

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
                "also_on": also_on,
                "event_sources": event_sources,
                "target_segments": top_segments,
                "source_scores": {
                    "weather": weather["score"],
                    "air_quality": air["score"],
                    "holiday": holidays["score"],
                    "seasonal": seasonal["score"],
                    "events": events["score"],
                    "availability": round(empty_ratio, 2),
                },
            }
            suggestions.append(suggestion)

    best_per_city: dict[str, dict] = {}
    for s in suggestions:
        key = s["guest_city"]
        if key not in best_per_city or s["score"] > best_per_city[key]["score"]:
            best_per_city[key] = s

    per_city = sorted(best_per_city.values(), key=lambda s: -s["score"])

    merged: dict[str, dict] = {}
    for s in per_city:
        key = f"{s['check_in']}|{s['nights']}"
        if key not in merged:
            merged[key] = {
                "hotel": s["hotel"],
                "hotel_id": s["hotel_id"],
                "guest_cities": [s["guest_city"]],
                "check_in": s["check_in"],
                "nights": s["nights"],
                "rooms_to_offer": s["rooms_to_offer"],
                "rooms_free": s["rooms_free"],
                "score": s["score"],
                "price": s["price"],
                "reasons": list(s["reasons"]),
                "also_on": list(s.get("also_on", [])),
                "event_sources": list(s.get("event_sources", [])),
                "target_segments": s.get("target_segments", []),
                "source_scores": dict(s["source_scores"]),
            }
        else:
            m = merged[key]
            m["guest_cities"].append(s["guest_city"])
            if s["score"] > m["score"]:
                m["score"] = s["score"]
            for r in s["reasons"]:
                if r not in m["reasons"]:
                    m["reasons"].append(r)
            for a in s.get("also_on", []):
                if a not in m["also_on"]:
                    m["also_on"].append(a)
            existing_names = {e["name"] for e in m["event_sources"]}
            for e in s.get("event_sources", []):
                if e["name"] not in existing_names:
                    m["event_sources"].append(e)

    return sorted(merged.values(), key=lambda s: -s["score"])


def explain_moments(hotel: dict, settings: dict, data_dir: Path,
                    start_date: date, end_date: date) -> list[dict]:
    min_free = settings.get("min_free_rooms", 1)
    avail = _build_availability(hotel, data_dir, start_date, end_date)

    results = []
    d = start_date
    while d <= end_date:
        day_result = {"date": d.isoformat(), "weekday": d.strftime("%A"), "sources": {}}
        free_rooms = avail["free_rooms"].get(d.isoformat(), hotel["rooms"])

        for city in hotel["guest_cities"]:
            weather = score_weather(hotel, city, settings)
            air = score_air_quality(city, settings)
            holidays = score_holidays(d, settings, data_dir, stay_end=d + timedelta(days=2))
            seasonal = score_seasonal(d, data_dir, hotel_id=hotel["id"], hotel=hotel)
            blocked, strike_note = is_strike_blocking(d, hotel.get("travel_modes", []), data_dir)

            combined = _additive_score(
                weather["score"],
                air["score"],
                seasonal["score"],
                free_rooms,
                hotel["rooms"],
                holidays,
                min_free,
                hotel_weather_penalty=weather.get("hotel_weather_penalty", 0.0),
            )

            all_reasons = (
                weather["reasons"] + air["reasons"]
                + holidays["reasons"] + seasonal["reasons"]
            )
            if blocked:
                all_reasons.append(f"BLOCKED: {strike_note}")

            active_sigs = _active_signals(
                d, weather["score"], air["score"], holidays, seasonal, 0,
            )
            top_segments = _per_segment_scores(
                combined, active_sigs, hotel, settings,
            )

            day_result["sources"][city["name"]] = {
                "combined_score": round(combined, 3),
                "fires": combined >= settings.get("min_score_to_fire", 0.5) and not blocked,
                "weather": {"score": weather["score"], "reasons": weather["reasons"]},
                "air_quality": {"score": air["score"], "reasons": air["reasons"]},
                "holidays": {"score": holidays["score"], "reasons": holidays["reasons"]},
                "seasonal": {"score": seasonal["score"], "reasons": seasonal["reasons"]},
                "also_on": seasonal.get("also_on", []),
                "event_sources": seasonal.get("event_sources", []),
                "availability": {"free_rooms": free_rooms, "total_rooms": hotel["rooms"]},
                "target_segments": top_segments,
                "strike_blocked": blocked,
                "all_reasons": all_reasons,
            }

        results.append(day_result)
        d += timedelta(days=1)

    return results


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

def _seasonal_aq_score(city: dict, d: date) -> float:
    """Estimate AQ score from month for Po Valley cities (Milan, Turin, etc.).

    Only the worst winter months (Dec-Feb) reliably hit "Poor" EU AQI (>60).
    Spring/autumn are usually "Moderate" and should not trigger."""
    lat = city.get("coords", {}).get("lat", 0)
    if lat < 44.0 or lat > 46.5:
        return 0.0
    m = d.month
    if m in (12, 1, 2):
        return 0.6
    return 0.0


def _fetch_historical_aq(lat: float, lon: float, start: date, end: date) -> dict:
    """Fetch historical AQ from Open-Meteo. Returns {date_str: {pm25, pm10, aqi}}."""
    data = _cached_get(
        f"https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=pm2_5,pm10,european_aqi"
        f"&timezone=Europe/Rome"
        f"&start_date={start.isoformat()}&end_date={end.isoformat()}"
    )
    if not data or "hourly" not in data:
        return {}
    hourly = data["hourly"]
    times = hourly.get("time", [])
    pm25 = hourly.get("pm2_5", [])
    pm10 = hourly.get("pm10", [])
    aqi = hourly.get("european_aqi", [])
    daily: dict = {}
    for i, t in enumerate(times):
        day_str = t[:10]
        if day_str not in daily:
            daily[day_str] = {"pm25": [], "pm10": [], "aqi": []}
        if i < len(pm25) and pm25[i] is not None:
            daily[day_str]["pm25"].append(pm25[i])
        if i < len(pm10) and pm10[i] is not None:
            daily[day_str]["pm10"].append(pm10[i])
        if i < len(aqi) and aqi[i] is not None:
            daily[day_str]["aqi"].append(aqi[i])
    result = {}
    for day_str, vals in daily.items():
        result[day_str] = {
            "pm25": sum(vals["pm25"]) / max(len(vals["pm25"]), 1),
            "pm10": sum(vals["pm10"]) / max(len(vals["pm10"]), 1),
            "aqi": sum(vals["aqi"]) / max(len(vals["aqi"]), 1),
        }
    return result


def _real_aq_score(aq_day: dict) -> float:
    """Score a single day's AQ from real Open-Meteo data.

    EU AQI bands: 0-20 Good, 20-40 Fair, 40-60 Moderate, 60-80 Poor, 80+ Very Poor.
    Only "Poor" and above should trigger a moment.
    """
    if aq_day.get("pm25", 0) > 35:
        return 0.7
    if aq_day.get("pm10", 0) > 50:
        return 0.6
    if aq_day.get("aqi", 0) > 60:
        return 0.5
    return 0.0


MAX_RECURRING_EVENT_DAYS = 14


def _load_recurring_events(hotel_id: str, data_dir: Path, start: date, end: date) -> list:
    """Load this year's discovered events and project them onto the backtest period.

    Only keeps dated/highlight events (<=14 days). Season-long programmes
    like theatre seasons or year-round cultural series are excluded.
    """
    from events_db import load_events
    db_data = load_events(hotel_id) if hotel_id else None
    events_list = []
    if db_data and db_data.get("events"):
        events_list = db_data["events"]
    else:
        hotel_events_file = data_dir / f"local_events_{hotel_id}.json" if hotel_id else None
        if hotel_events_file and hotel_events_file.exists():
            try:
                edata = json.loads(hotel_events_file.read_text())
                events_list = edata.get("events", [])
            except (json.JSONDecodeError, KeyError):
                pass
    if not events_list:
        return []
    projected = []
    for ev in events_list:
        if ev.get("hidden"):
            continue
        dates = ev.get("dates", {})
        efrom = dates.get("from", "")
        eto = dates.get("to", efrom)
        if not efrom:
            continue
        try:
            orig_start = date.fromisoformat(efrom)
            orig_end = date.fromisoformat(eto)
        except ValueError:
            continue
        duration = (orig_end - orig_start).days + 1
        if duration > MAX_RECURRING_EVENT_DAYS:
            continue
        for year_offset in (-1, -2):
            try:
                shifted_start = orig_start.replace(year=orig_start.year + year_offset)
                shifted_end = orig_end.replace(year=orig_end.year + year_offset)
            except ValueError:
                continue
            if shifted_end < start or shifted_start > end:
                continue
            projected.append({
                **ev,
                "dates": {"from": shifted_start.isoformat(), "to": shifted_end.isoformat()},
                "recurring": True,
            })
    return projected


def run_backtest(hotel: dict, settings: dict, months: int = 12,
                 data_dir: Path | None = None) -> dict:
    if data_dir is None:
        data_dir = Path(__file__).parent / "moments_data"

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=months * 30)

    min_score = settings.get("min_score_to_fire", 0.50)
    min_free = settings.get("min_free_rooms", 1)
    blackout_md = {bd[5:] for bd in hotel.get("blackout_dates", [])}
    hotel_id = hotel.get("id", hotel.get("hotel_id", ""))
    has_spa = bool({"spa", "indoor_pool"} & set(hotel.get("amenities", [])))

    holidays_path = data_dir / "holidays.json"
    holidays_data = json.loads(holidays_path.read_text()) if holidays_path.exists() else {}

    recurring_events = _load_recurring_events(hotel_id, data_dir, start_date, end_date)

    hotel_data = _cached_get(
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={hotel['coords']['lat']}&longitude={hotel['coords']['lon']}"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&timezone=Europe/Rome&start_date={start_date.isoformat()}&end_date={end_date.isoformat()}"
    )

    city_data = {}
    city_aq_data = {}
    aq_source = "real"
    for city in hotel["guest_cities"]:
        time.sleep(0.3)
        city_data[city["name"]] = _cached_get(
            f"https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={city['coords']['lat']}&longitude={city['coords']['lon']}"
            f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"
            f"&timezone=Europe/Rome&start_date={start_date.isoformat()}&end_date={end_date.isoformat()}"
        )
        time.sleep(0.3)
        aq = _fetch_historical_aq(
            city["coords"]["lat"], city["coords"]["lon"], start_date, end_date
        )
        if aq:
            city_aq_data[city["name"]] = aq
    if not city_aq_data:
        aq_source = "estimate"

    if not hotel_data or not all(city_data.values()):
        return {"error": "Could not fetch historical weather data."}

    hotel_daily = hotel_data["daily"]
    hotel_index = {d: i for i, d in enumerate(hotel_daily["time"])}

    rows = []
    d = start_date
    while d <= end_date:
        if d.weekday() in (1, 4):
            is_weekend = d.weekday() == 4
            stay_type = "weekend" if is_weekend else "midweek"
            stay_dates = [d + timedelta(days=i) for i in range(3)]

            if any(sd.strftime("%m-%d") in blackout_md for sd in stay_dates):
                d += timedelta(days=1)
                continue

            free = _free_rooms(hotel, d, holidays_data)
            if free < min_free:
                d += timedelta(days=1)
                continue

            for city_name, cdata in city_data.items():
                if not cdata:
                    continue
                city_daily = cdata["daily"]
                city_index = {dd: i for i, dd in enumerate(city_daily["time"])}

                weather_score = 0.0
                weather_reasons = []
                weather_types = []

                city_codes = []
                hotel_codes = []
                for sd in stay_dates:
                    ci = city_index.get(sd.isoformat())
                    hi = hotel_index.get(sd.isoformat())
                    if ci is not None:
                        city_codes.append(city_daily["weather_code"][ci])
                    if hi is not None:
                        hotel_codes.append(hotel_daily["weather_code"][hi])

                if not city_codes:
                    d += timedelta(days=1)
                    continue

                rain_city = sum(1 for c in city_codes if is_rainy(c))
                rain_hotel = sum(1 for c in hotel_codes if is_rainy(c))
                grey_hotel = sum(1 for c in hotel_codes if is_grey(c))

                hotel_weather_penalty = 0.0
                spa_escape_bonus = 0.0
                if rain_hotel >= 2 and has_spa:
                    spa_escape_bonus = 0.15 if rain_hotel >= 3 else 0.10
                    weather_reasons.append(
                        f"Spa escape: rain at hotel ({rain_hotel} days) — cosy spa getaway"
                    )
                    weather_types.append("spa_escape")
                elif rain_hotel >= 3:
                    hotel_weather_penalty = 0.30
                    weather_reasons.append(f"Bad weather at hotel ({rain_hotel} rainy days) — penalty")
                elif rain_hotel >= 2:
                    hotel_weather_penalty = 0.20
                    weather_reasons.append(f"Rain at hotel ({rain_hotel} days) — penalty")
                elif grey_hotel >= 3:
                    hotel_weather_penalty = 0.10

                hotel_better = rain_hotel < rain_city
                if hotel_better and rain_city >= 2:
                    weather_score = max(weather_score, 0.8)
                    weather_reasons.append(
                        f"Rain in {city_name} ({rain_city}/3 days), drier at hotel"
                    )
                    weather_types.append("rain_escape")
                elif hotel_better and rain_city == 1:
                    weather_score = max(weather_score, 0.4)
                    weather_reasons.append(f"Some rain in {city_name}, drier at hotel")
                    weather_types.append("rain_escape")

                snow_days = sum(1 for c in hotel_codes if is_snowy(c))
                if snow_days > 0:
                    weather_score = max(weather_score, 0.7)
                    weather_reasons.append(f"Snow at {hotel['town']} ({snow_days} days)")
                    weather_types.append("snow")

                pre_codes = []
                for back in range(1, 4):
                    pre_d = (d - timedelta(days=back)).isoformat()
                    ci = city_index.get(pre_d)
                    if ci is not None:
                        pre_codes.append(city_daily["weather_code"][ci])
                if len(pre_codes) >= 3 and all(is_rainy(c) for c in pre_codes):
                    sunny = sum(1 for c in hotel_codes if is_sunny(c))
                    if sunny >= 1:
                        weather_score = max(weather_score, 0.9)
                        weather_reasons.append(
                            f"Sunny rebound at hotel after rain in {city_name}"
                        )
                        weather_types.append("sunny_rebound")

                holidays = score_holidays(d, settings, data_dir)
                seasonal = score_seasonal(d, data_dir, hotel_id=hotel_id)

                recurring_score = 0.0
                recurring_reasons = []
                for rev in recurring_events:
                    from moments_sources import _event_active_on, _ai_event_weight
                    if _event_active_on(rev, d):
                        w = _ai_event_weight(rev)
                        recurring_score = max(recurring_score, min(w * rev.get("relevance", 0.5), 0.8))
                        recurring_reasons.append(f"{rev['name']} (recurring)")
                seasonal_total = max(seasonal["score"], recurring_score)

                city_aq = city_aq_data.get(city_name, {})
                day_aq = city_aq.get(d.isoformat())
                if day_aq:
                    aq_score = _real_aq_score(day_aq)
                else:
                    aq_score = _seasonal_aq_score(city, d)

                combined = _additive_score(
                    weather_score + spa_escape_bonus, aq_score, seasonal_total,
                    free, hotel["rooms"], holidays, min_free,
                    hotel_weather_penalty=hotel_weather_penalty,
                )

                moment_types = list(set(weather_types))
                if aq_score >= 0.5:
                    moment_types.append("poor_air_quality")
                h_class = _classify_holidays(holidays)
                empty_ratio = free / max(hotel["rooms"], 1)
                if h_class["ponte"] and free >= min_free:
                    moment_types.append("ponte")
                if h_class["school"] and free >= min_free:
                    moment_types.append("school_holiday")
                if h_class["public"] and free >= min_free and empty_ratio > 0.30:
                    moment_types.append("public_holiday")
                if seasonal_total > 0:
                    moment_types.append("seasonal")
                if recurring_reasons:
                    moment_types.append("recurring_event")
                if empty_ratio >= 0.40:
                    moment_types.append("low_occupancy")
                if hotel_weather_penalty > 0 and not has_spa:
                    moment_types.append("hotel_rain_penalty")

                all_reasons = (
                    weather_reasons
                    + holidays.get("reasons", [])
                    + seasonal.get("reasons", [])
                    + recurring_reasons
                )
                if aq_score >= 0.5:
                    aq_label = "real data" if day_aq else "seasonal estimate"
                    all_reasons.append(f"Poor air quality in {city_name} ({aq_label})")
                if empty_ratio >= 0.40:
                    all_reasons.append(f"Low occupancy ({free}/{hotel['rooms']} rooms free)")

                rows.append({
                    "date": d.isoformat(),
                    "stay_type": stay_type,
                    "city": city_name,
                    "flagged": combined >= min_score,
                    "score": round(combined, 3),
                    "moment_types": list(set(moment_types)),
                    "reasons": all_reasons,
                    "city_weather": [describe_code(c) for c in city_codes],
                    "hotel_weather": [describe_code(c) for c in hotel_codes],
                    "free_rooms": free,
                    "source_scores": {
                        "weather": round(weather_score, 2),
                        "air_quality": round(aq_score, 2),
                        "aq_source": "real" if day_aq else "estimate",
                        "spa_escape": round(spa_escape_bonus, 2),
                        "hotel_weather_penalty": round(hotel_weather_penalty, 2),
                        "holiday": holidays["score"],
                        "seasonal": round(seasonal_total, 2),
                        "occupancy": round(empty_ratio, 2),
                    },
                })

        d += timedelta(days=1)

    flagged_all = [r for r in rows if r["flagged"]]
    flagged_all.sort(key=lambda r: -r["score"])
    kept = []
    kept_dates: dict[str, list[date]] = {}
    for row in flagged_all:
        city = row["city"]
        row_date = date.fromisoformat(row["date"])
        if any(abs((row_date - p).days) < 7 for p in kept_dates.get(city, [])):
            continue
        kept.append(row)
        kept_dates.setdefault(city, []).append(row_date)
    kept.sort(key=lambda r: r["date"])

    month_counts: Counter = Counter()
    type_counts: Counter = Counter()
    for row in kept:
        month_counts[row["date"][:7]] += 1
        for t in row["moment_types"]:
            type_counts[t] += 1

    return {
        "hotel": hotel["name"],
        "period": f"{start_date.isoformat()} to {end_date.isoformat()}",
        "months": months,
        "total_dates_checked": len(rows),
        "flagged_before_dedup": len(flagged_all),
        "flagged_total": len(kept),
        "per_month": dict(sorted(month_counts.items())),
        "per_type": dict(type_counts.most_common()),
        "aq_source": aq_source,
        "has_spa": has_spa,
        "recurring_events_loaded": len(recurring_events),
        "scoring": {
            "model": "additive",
            "min_score": min_score,
            "note": "Signals add up (capped at 1.0); holidays gated by room availability",
        },
        "flagged": kept,
        "demo": True,
    }
