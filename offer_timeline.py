"""Build a 2-week timeline of offer periods for the hotel portal.

Each period is either 'this midweek', 'this weekend', 'next midweek',
'next weekend'. For each period we either produce an offer (with
event-aligned dates and Claude-generated themes) or explain why not.
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from moments_engine import (
    _additive_score,
    _available_nights,
    _build_availability,
    _classify_holidays,
    _compute_price,
    _compute_segment_package,
    _is_blacked_out,
    _per_segment_scores,
    _active_signals,
    load_json,
)
from moments_sources import (
    is_strike_blocking,
    score_air_quality,
    score_events,
    score_holidays,
    score_seasonal,
    score_weather,
)
from offer_themes import generate_themes

logger = logging.getLogger(__name__)


def _define_periods(today: date) -> list[dict]:
    """Define the 4 periods covering the next ~2 weeks."""
    dow = today.weekday()  # 0=Mon

    periods = []

    # This midweek: today (or next Mon) through Thursday
    if dow <= 3:  # Mon-Thu
        mw_start = today + timedelta(days=1)  # tomorrow at earliest
        mw_end_dow = 3  # Thursday
        mw_end = today + timedelta(days=(mw_end_dow - dow))
        if mw_end >= mw_start:
            periods.append({
                "id": "this_midweek",
                "label_en": "This midweek",
                "label_it": "Questa settimana",
                "type": "midweek",
                "start": mw_start,
                "end": mw_end,
            })

    # This weekend: Fri-Sun
    days_to_fri = (4 - dow) % 7
    if days_to_fri == 0 and dow == 4:
        days_to_fri = 0
    we_start = today + timedelta(days=days_to_fri)
    we_end = we_start + timedelta(days=2)  # Sunday
    if we_start > today or dow >= 4:  # allow if we're in the weekend
        if dow >= 4:
            we_start = max(today + timedelta(days=1), we_start)
        periods.append({
            "id": "this_weekend",
            "label_en": "This weekend",
            "label_it": "Questo fine settimana",
            "type": "weekend",
            "start": we_start,
            "end": we_end,
        })

    # Next midweek
    days_to_next_mon = (7 - dow) % 7
    if days_to_next_mon == 0:
        days_to_next_mon = 7
    next_mon = today + timedelta(days=days_to_next_mon)
    next_thu = next_mon + timedelta(days=3)
    periods.append({
        "id": "next_midweek",
        "label_en": "Next midweek",
        "label_it": "Prossima settimana",
        "type": "midweek",
        "start": next_mon,
        "end": next_thu,
    })

    # Next weekend
    next_fri = next_mon + timedelta(days=4)
    next_sun = next_fri + timedelta(days=2)
    periods.append({
        "id": "next_weekend",
        "label_en": "Next weekend",
        "label_it": "Prossimo fine settimana",
        "type": "weekend",
        "start": next_fri,
        "end": next_sun,
    })

    # Week after midweek
    week2_mon = next_mon + timedelta(days=7)
    week2_thu = week2_mon + timedelta(days=3)
    periods.append({
        "id": "week2_midweek",
        "label_en": "In two weeks (midweek)",
        "label_it": "Fra due settimane (infrasettimanale)",
        "type": "midweek",
        "start": week2_mon,
        "end": week2_thu,
    })

    # Week after weekend
    week2_fri = week2_mon + timedelta(days=4)
    week2_sun = week2_fri + timedelta(days=2)
    periods.append({
        "id": "week2_weekend",
        "label_en": "In two weeks (weekend)",
        "label_it": "Fra due settimane (fine settimana)",
        "type": "weekend",
        "start": week2_fri,
        "end": week2_sun,
    })

    return periods


def _best_event_in_range(start: date, end: date, event_sources: list[dict],
                          also_on: list[str], hotel_id: str, data_dir: Path) -> dict | None:
    """Find the strongest event active during this period."""
    from events_db import load_events
    db_data = load_events(hotel_id)
    if not db_data or not db_data.get("events"):
        return None

    best = None
    best_weight = 0
    for ev in db_data["events"]:
        if ev.get("hidden"):
            continue
        dates = ev.get("dates", {})
        efrom = dates.get("from", "")
        eto = dates.get("to", efrom)
        if not efrom:
            continue
        if efrom > end.isoformat() or eto < start.isoformat():
            continue
        weight = 0
        for es in event_sources:
            if es.get("name") == ev.get("name"):
                weight = es.get("weight", 0.5)
                break
        if weight == 0:
            from moments_sources import _ai_event_weight
            weight = _ai_event_weight(ev)
        if weight > best_weight:
            best_weight = weight
            best = ev
    return best


def _pick_check_in(period: dict, best_event: dict | None, min_nights: int) -> date:
    """Pick the best check-in within the period, aligned to the strongest event."""
    start = period["start"]
    end = period["end"]

    if best_event:
        dates = best_event.get("dates", {})
        ev_from = date.fromisoformat(dates.get("from", start.isoformat()))
        ev_to = date.fromisoformat(dates.get("to", end.isoformat()))
        ideal = max(start, ev_from - timedelta(days=1))
        ideal = min(ideal, end - timedelta(days=min_nights - 1))
        ideal = max(ideal, start)
        return ideal

    if period["type"] == "weekend":
        return start
    return start


def _why_these_dates(check_in: date, nights: int, best_event: dict | None,
                     holiday_reasons: list[str]) -> dict:
    """Explain why we picked these particular dates."""
    checkout = check_in + timedelta(days=nights)
    if best_event:
        name = best_event.get("name", "event")
        dates = best_event.get("dates", {})
        ev_from = dates.get("from", "")
        ev_to = dates.get("to", "")
        if ev_from and ev_to:
            return {
                "en": f"Overlaps with {name} ({_fmt_date(ev_from)} – {_fmt_date(ev_to)})",
                "it": f"Coincide con {name} ({_fmt_date(ev_from)} – {_fmt_date(ev_to)})",
            }
        return {
            "en": f"Overlaps with {name}",
            "it": f"Coincide con {name}",
        }
    if holiday_reasons:
        reason = holiday_reasons[0]
        return {"en": reason, "it": reason}
    dow_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][check_in.weekday()]
    if check_in.weekday() >= 4:
        return {
            "en": f"Weekend getaway ({dow_name})",
            "it": f"Fuga del fine settimana ({dow_name})",
        }
    return {
        "en": f"Midweek escape",
        "it": f"Fuga infrasettimanale",
    }


def _fmt_date(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{d.day} {months[d.month - 1]}"


def _skip_reason(scores: dict, reasons: list[str], min_score: float,
                 rooms_free: int, hotel_rain: bool, has_events: bool) -> dict:
    """Human-readable reason why this period doesn't have an offer."""
    combined = scores.get("combined", 0)

    if rooms_free < 1:
        return {
            "en": "Hotel nearly full",
            "it": "Hotel quasi pieno",
            "code": "full",
        }

    parts_en = []
    parts_it = []
    if scores.get("weather", 0) < 0.3 and hotel_rain:
        parts_en.append("rain at the lake")
        parts_it.append("pioggia al lago")
    elif scores.get("weather", 0) < 0.3:
        parts_en.append("no strong weather signal")
        parts_it.append("nessun segnale meteo forte")
    if not has_events:
        parts_en.append("no events nearby")
        parts_it.append("nessun evento in zona")
    if scores.get("air_quality", 0) < 0.3:
        parts_en.append("city air is OK")
        parts_it.append("aria in città OK")

    if parts_en:
        reason_en = ", ".join(parts_en).capitalize()
        reason_it = ", ".join(parts_it).capitalize()
    else:
        reason_en = "Signals too weak"
        reason_it = "Segnali troppo deboli"

    return {
        "en": f"{reason_en} — score {combined:.2f} of {min_score:.2f} needed",
        "it": f"{reason_it} — punteggio {combined:.2f} su {min_score:.2f} necessario",
        "code": "weak",
    }


def evaluate_timeline(hotel: dict, settings: dict, data_dir: Path,
                      today: date | None = None) -> list[dict]:
    """Evaluate all periods in the next 2 weeks, returning offer or skip for each."""
    if today is None:
        today = datetime.now(ZoneInfo("Europe/Rome")).date()
    min_nights = settings.get("min_nights", 2)
    min_score = settings.get("min_score_to_fire", 0.5)
    min_free = settings.get("min_free_rooms", 1)

    avail = _build_availability(
        hotel, data_dir,
        today + timedelta(days=1),
        today + timedelta(days=21),
    )

    periods = _define_periods(today)
    results = []

    for period in periods:
        period_result = _evaluate_period(
            period, hotel, settings, data_dir, avail,
            min_nights, min_score, min_free, today,
        )
        results.append(period_result)

    return results


def _evaluate_period(period: dict, hotel: dict, settings: dict, data_dir: Path,
                     avail: dict, min_nights: int, min_score: float,
                     min_free: int, today: date) -> dict:
    """Evaluate a single period: produce an offer or a skip reason."""
    best_suggestion = None
    best_score = 0
    all_scores = {}
    all_reasons = []
    best_rooms_free = 0
    hotel_rain = False
    has_events = False

    forecast_horizon = 7
    for city in hotel["guest_cities"]:
        weather = score_weather(hotel, city, settings)
        air = score_air_quality(city, settings)
        if "rain at" in " ".join(weather.get("reasons", [])).lower():
            hotel_rain = True

        best_day_score = 0
        best_day_data = None

        d = period["start"]
        while d <= period["end"]:
            if _is_blacked_out(d, hotel.get("blackout_dates", [])):
                d += timedelta(days=1)
                continue

            blocked, _ = is_strike_blocking(d, hotel.get("travel_modes", []), data_dir)
            if blocked:
                d += timedelta(days=1)
                continue

            days_out = (d - today).days
            if days_out < forecast_horizon:
                w_score = weather["score"]
                w_penalty = weather.get("hotel_weather_penalty", 0.0)
                a_score = air["score"]
                w_reasons = weather["reasons"]
                a_reasons = air["reasons"]
            else:
                w_score = 0.0
                w_penalty = 0.0
                a_score = 0.0
                w_reasons = []
                a_reasons = []

            check_out = d + timedelta(days=min_nights)
            holidays = score_holidays(d, settings, data_dir, stay_end=check_out)
            seasonal = score_seasonal(d, data_dir, hotel_id=hotel["id"], hotel=hotel)

            if seasonal.get("event_sources"):
                has_events = True

            windows = _available_nights(avail, d, min_nights, hotel["max_rooms_per_offer"])
            if not windows:
                d += timedelta(days=1)
                continue

            best_window = windows[0]
            rooms_free = best_window["rooms_free"]
            best_rooms_free = max(best_rooms_free, rooms_free)

            combined = _additive_score(
                w_score, a_score, seasonal["score"],
                rooms_free, hotel["rooms"], holidays, min_free,
                hotel_weather_penalty=w_penalty,
            )

            if combined > best_day_score:
                best_day_score = combined
                reasons = (
                    w_reasons + a_reasons
                    + holidays["reasons"] + seasonal["reasons"]
                )
                best_day_data = {
                    "check_in": d,
                    "nights": best_window["nights"],
                    "rooms_free": rooms_free,
                    "rooms_to_offer": best_window["rooms_to_offer"],
                    "combined": combined,
                    "weather": weather if days_out < forecast_horizon else {"score": 0, "reasons": [], "hotel_weather_penalty": 0},
                    "air": air if days_out < forecast_horizon else {"score": 0, "reasons": []},
                    "holidays": holidays,
                    "seasonal": seasonal,
                    "reasons": reasons,
                    "source_scores": {
                        "weather": w_score,
                        "air_quality": a_score,
                        "holiday": holidays["score"],
                        "seasonal": seasonal["score"],
                        "availability": round(rooms_free / max(hotel["rooms"], 1), 2),
                    },
                    "city": city["name"],
                }

            d += timedelta(days=1)

        if best_day_data and best_day_score > best_score:
            best_score = best_day_score
            best_suggestion = best_day_data
            all_scores = best_day_data["source_scores"]
            all_reasons = best_day_data["reasons"]

    # Build the period result
    base = {
        "id": period["id"],
        "label_en": period["label_en"],
        "label_it": period["label_it"],
        "type": period["type"],
        "start": period["start"].isoformat(),
        "end": period["end"].isoformat(),
        "rooms_free": best_rooms_free,
    }

    if not best_suggestion or best_score < min_score:
        all_scores["combined"] = best_score
        base["has_offer"] = False
        base["skip_reason"] = _skip_reason(
            all_scores, all_reasons, min_score,
            best_rooms_free, hotel_rain, has_events,
        )
        base["score"] = round(best_score, 3)
        base["can_create"] = best_rooms_free >= min_free
        return base

    # We have an offer — build it with event-aligned dates and themes
    check_in = best_suggestion["check_in"]
    seasonal = best_suggestion["seasonal"]
    holidays = best_suggestion["holidays"]
    event_sources = seasonal.get("event_sources", [])
    also_on = seasonal.get("also_on", [])

    best_event = _best_event_in_range(
        period["start"], period["end"],
        event_sources, also_on, hotel["id"], data_dir,
    )

    aligned_check_in = _pick_check_in(period, best_event, min_nights)
    windows = _available_nights(avail, aligned_check_in, min_nights, hotel["max_rooms_per_offer"])
    if not windows:
        aligned_check_in = check_in
        windows = _available_nights(avail, aligned_check_in, min_nights, hotel["max_rooms_per_offer"])

    if not windows:
        base["has_offer"] = False
        base["skip_reason"] = {"en": "No availability for aligned dates", "it": "Nessuna disponibilità per le date", "code": "full"}
        base["score"] = round(best_score, 3)
        base["can_create"] = False
        return base

    best_window = windows[0]
    nights = best_window["nights"]
    combined = best_score

    why_dates = _why_these_dates(aligned_check_in, nights, best_event, holidays.get("reasons", []))

    price = _compute_price(hotel, nights, combined, settings)
    active_sigs = _active_signals(
        aligned_check_in, all_scores.get("weather", 0), all_scores.get("air_quality", 0),
        holidays, seasonal, (aligned_check_in - today).days,
    )
    top_segments = _per_segment_scores(combined, active_sigs, hotel, settings)
    for seg in top_segments:
        seg["package"] = _compute_segment_package(
            hotel, nights, combined, seg, settings, check_in=aligned_check_in,
        )

    cities = [c["name"] for c in hotel["guest_cities"]]

    # Generate themes via Claude
    row_themes = generate_themes(
        hotel_name=hotel["name"],
        hotel_id=hotel["id"],
        hotel_town=hotel.get("town", ""),
        check_in=aligned_check_in.isoformat(),
        nights=nights,
        cities=cities,
        segments=top_segments,
        reasons=all_reasons,
        also_on=also_on,
        event_sources=event_sources,
        source_scores=all_scores,
    )

    base["has_offer"] = True
    base["score"] = round(combined, 3)
    base["suggestion"] = {
        "hotel": hotel["name"],
        "hotel_id": hotel["id"],
        "guest_cities": cities,
        "check_in": aligned_check_in.isoformat(),
        "nights": nights,
        "rooms_to_offer": best_window["rooms_to_offer"],
        "rooms_free": best_window["rooms_free"],
        "score": round(combined, 3),
        "price": price,
        "reasons": all_reasons,
        "also_on": also_on,
        "event_sources": event_sources,
        "target_segments": top_segments,
        "source_scores": all_scores,
        "why_these_dates": why_dates,
        "row_themes": row_themes,
    }

    return base
