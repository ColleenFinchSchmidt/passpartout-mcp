"""Moment sources: each returns a score (0-1) and a plain-English reason.

Free APIs used:
- Open-Meteo Forecast: https://open-meteo.com (free for non-commercial, no key)
  Limit: fair use, no hard cap. Terms: CC BY 4.0 for data.
- Open-Meteo Air Quality: same terms.
- Open-Meteo Historical: same terms, archive endpoint.
"""

import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_http = httpx.Client(
    headers={"User-Agent": "passpartout-moments/1.0"},
    timeout=10,
)

# ---- cache ----

_cache: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 3600


def _cached_get(url: str) -> dict | None:
    now = time.time()
    if url in _cache and (now - _cache[url][0]) < _CACHE_TTL:
        return _cache[url][1]
    try:
        resp = _http.get(url)
        resp.raise_for_status()
        data = resp.json()
        _cache[url] = (now, data)
        return data
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.warning("API call failed: %s — %s", url[:80], exc)
        return None


# ---- WMO weather codes ----

def is_rainy(code: int) -> bool:
    return code in range(51, 68) or code in range(80, 83) or code in range(95, 100)

def is_snowy(code: int) -> bool:
    return code in range(71, 78) or code in range(85, 87)

def is_sunny(code: int) -> bool:
    return code in (0, 1)

def is_grey(code: int) -> bool:
    return code in (2, 3, 45, 48) or is_rainy(code)

def describe_code(code: int) -> str:
    if is_sunny(code): return "clear"
    if code in (2, 3): return "cloudy"
    if code in (45, 48): return "foggy"
    if is_snowy(code): return "snowy"
    if is_rainy(code): return "rainy"
    return "mixed"


# ---- 1. Weather forecast ----

def fetch_forecast(lat: float, lon: float, days: int = 7) -> dict | None:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&timezone=Europe/Rome&forecast_days={days}"
    )
    return _cached_get(url)


def fetch_historical(lat: float, lon: float, start: str, end: str) -> dict | None:
    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&timezone=Europe/Rome"
        f"&start_date={start}&end_date={end}"
    )
    return _cached_get(url)


def score_weather(hotel: dict, city: dict, settings: dict) -> dict:
    city_fc = fetch_forecast(city["coords"]["lat"], city["coords"]["lon"])
    hotel_fc = fetch_forecast(hotel["coords"]["lat"], hotel["coords"]["lon"])

    if not city_fc or not hotel_fc:
        return {"score": 0, "reasons": ["Weather data unavailable"], "details": {}}

    city_daily = city_fc["daily"]
    hotel_daily = hotel_fc["daily"]
    thresholds = settings.get("weather_thresholds", {})
    moments = hotel.get("moments_enabled", {})

    score = 0.0
    reasons = []

    dates = city_daily["time"]
    weekend_idx = [i for i, d in enumerate(dates) if date.fromisoformat(d).weekday() in (4, 5, 6)]
    midweek_idx = [i for i, d in enumerate(dates) if date.fromisoformat(d).weekday() in (0, 1, 2, 3)]

    city_codes = city_daily["weather_code"]
    hotel_codes = hotel_daily["weather_code"]

    if moments.get("rain_in_guest_city"):
        city_rain_wk = [i for i in weekend_idx if is_rainy(city_codes[i])]
        hotel_rain_wk = [i for i in weekend_idx if i < len(hotel_codes) and is_rainy(hotel_codes[i])]
        hotel_better = len(hotel_rain_wk) < len(city_rain_wk)
        if hotel_better and city_rain_wk:
            rainy_dates = [dates[i] for i in city_rain_wk]
            score = max(score, 0.8)
            reasons.append(f"Rain in {city['name']} this weekend ({', '.join(rainy_dates)}), drier at {hotel['town']}")
        elif hotel_better:
            near_rain = [dates[i] for i in range(min(3, len(city_codes))) if is_rainy(city_codes[i])]
            if near_rain:
                score = max(score, 0.5)
                reasons.append(f"Rain coming in {city['name']} ({', '.join(near_rain)}), drier at {hotel['town']}")

    if moments.get("snow_in_alps"):
        snowy_days = [hotel_daily["time"][i] for i in range(len(hotel_codes)) if is_snowy(hotel_codes[i])]
        if snowy_days:
            score = max(score, 0.7)
            reasons.append(f"Snow forecast at {hotel['town']} ({', '.join(snowy_days[:3])})")

    if moments.get("sunny_weekend_after_rain"):
        consec = thresholds.get("consecutive_rain_days_for_sunny_rebound", 3)
        rain_streak = 0
        for i in range(min(consec + 2, len(city_codes))):
            if is_rainy(city_codes[i]):
                rain_streak += 1
            else:
                break
        if rain_streak >= consec:
            sunny_wk = [dates[i] for i in weekend_idx if is_sunny(hotel_codes[i])]
            if sunny_wk:
                score = max(score, 0.9)
                reasons.append(
                    f"Sunny weekend at {hotel['town']} ({', '.join(sunny_wk)}) "
                    f"after {rain_streak} rainy days in {city['name']}"
                )

    hotel_penalty = 0.0
    hotel_rain_days = sum(1 for c in hotel_codes if is_rainy(c))
    hotel_grey_days = sum(1 for c in hotel_codes if is_grey(c))
    amenities = set(hotel.get("amenities", []))
    has_indoor = bool(amenities & {"spa", "pool", "restaurant", "gym"})

    if hotel_rain_days >= 3:
        if has_indoor:
            hotel_penalty = 0.10
            indoor = amenities & {"spa", "pool", "restaurant", "gym"}
            reasons.append(f"Rain at {hotel['town']} but {', '.join(sorted(indoor))} available — reduced penalty")
        else:
            hotel_penalty = 0.30
            reasons.append(f"Bad weather at {hotel['town']} ({hotel_rain_days} rainy days) — penalty applied")
    elif hotel_rain_days >= 2:
        if has_indoor:
            hotel_penalty = 0.05
            indoor = amenities & {"spa", "pool", "restaurant", "gym"}
            reasons.append(f"Light rain at {hotel['town']} — {', '.join(sorted(indoor))} makes it a plus")
        else:
            hotel_penalty = 0.20
            reasons.append(f"Rain at {hotel['town']} ({hotel_rain_days} days) — penalty applied")
    elif hotel_grey_days >= 4:
        hotel_penalty = 0.10
        reasons.append(f"Grey skies at {hotel['town']} — small penalty")

    if has_indoor and hotel_rain_days >= 2 and "spa" in amenities:
        score = max(score, 0.5)
        indoor = sorted(amenities & {"spa", "pool", "restaurant", "gym"})
        reasons.append(f"Spa escape — rain at {hotel['town']} makes {', '.join(indoor)} even more appealing")

    if moments.get("empty_midweek") and hotel_penalty == 0:
        nice_midweek = [dates[i] for i in midweek_idx
                        if is_sunny(hotel_codes[i]) or hotel_codes[i] in (2, 3)]
        if nice_midweek:
            score = max(score, 0.3)
            reasons.append(f"Nice midweek weather at {hotel['town']} ({', '.join(nice_midweek[:3])})")

    return {
        "score": round(score, 2),
        "hotel_weather_penalty": round(hotel_penalty, 2),
        "reasons": reasons,
        "details": {
            "city_today": describe_code(city_codes[0]),
            "hotel_today": describe_code(hotel_codes[0]),
            "city_temp_max": city_daily["temperature_2m_max"][0],
            "hotel_rain_days": hotel_rain_days,
            "hotel_grey_days": hotel_grey_days,
        },
    }


# ---- 2. Air quality ----

def fetch_air_quality(lat: float, lon: float) -> dict | None:
    url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=pm2_5,pm10,european_aqi"
        f"&timezone=Europe/Rome&forecast_days=3"
    )
    return _cached_get(url)


def score_air_quality(city: dict, settings: dict) -> dict:
    data = fetch_air_quality(city["coords"]["lat"], city["coords"]["lon"])
    if not data or "hourly" not in data:
        return {"score": 0, "reasons": [], "details": {}}

    hourly = data["hourly"]
    thresholds = settings.get("air_quality_thresholds", {})

    pm25_vals = [v for v in hourly.get("pm2_5", [])[:24] if v is not None]
    pm10_vals = [v for v in hourly.get("pm10", [])[:24] if v is not None]
    aqi_vals = [v for v in hourly.get("european_aqi", [])[:24] if v is not None]

    avg_pm25 = sum(pm25_vals) / max(len(pm25_vals), 1)
    avg_pm10 = sum(pm10_vals) / max(len(pm10_vals), 1)
    avg_aqi = sum(aqi_vals) / max(len(aqi_vals), 1)

    score = 0.0
    reasons = []

    if avg_pm25 > thresholds.get("pm25_bad_above", 25):
        score = max(score, 0.7)
        reasons.append(f"High PM2.5 in {city['name']} ({avg_pm25:.0f} µg/m³) — fresh lake air awaits")

    if avg_pm10 > thresholds.get("pm10_bad_above", 50):
        score = max(score, 0.6)
        reasons.append(f"High PM10 in {city['name']} ({avg_pm10:.0f} µg/m³)")

    if avg_aqi > thresholds.get("aqi_bad_above", 3):
        score = max(score, 0.5)
        reasons.append(f"Poor air quality index in {city['name']} (EU AQI {avg_aqi:.0f})")

    return {
        "score": round(score, 2),
        "reasons": reasons,
        "details": {"pm25": round(avg_pm25, 1), "pm10": round(avg_pm10, 1), "aqi": round(avg_aqi, 1)},
    }


# ---- 3. Holidays ----

def score_holidays(target_date: date, settings: dict, data_dir: Path,
                    stay_end: date | None = None) -> dict:
    """Score holidays only when the stay overlaps them."""
    holidays_file = data_dir / "holidays.json"
    if not holidays_file.exists():
        return {"score": 0, "reasons": [], "details": {}}

    if stay_end is None:
        stay_end = target_date + timedelta(days=1)

    hdata = json.loads(holidays_file.read_text())
    score = 0.0
    reasons = []

    for h in hdata.get("public_holidays", []):
        hdate = date.fromisoformat(h["date"])
        if target_date <= hdate <= stay_end:
            score = max(score, 0.7)
            reasons.append(f"{h['name']} ({h['date']}) during stay")

    for p in hdata.get("ponti", []):
        pfrom = date.fromisoformat(p["from"])
        pto = date.fromisoformat(p["to"])
        if target_date <= pto and stay_end >= pfrom:
            score = max(score, 0.9)
            reasons.append(f"{p['name']}")

    for period_name, period in hdata.get("school_holidays", {}).items():
        if period_name.startswith("_"):
            continue
        pfrom = date.fromisoformat(period["from"])
        pto = date.fromisoformat(period["to"])
        if target_date <= pto and stay_end >= pfrom:
            score = max(score, 0.4)
            reasons.append(f"School holidays ({period_name.replace('_', ' ')})")

    return {"score": round(score, 2), "reasons": reasons, "details": {}}


# ---- 4. Train strikes ----

def is_strike_blocking(target_date: date, travel_modes: list[str], data_dir: Path) -> tuple[bool, str]:
    strikes_file = data_dir / "strikes.json"
    if not strikes_file.exists():
        return False, ""

    sdata = json.loads(strikes_file.read_text())
    for s in sdata.get("strikes", []):
        sfrom = date.fromisoformat(s["from"])
        sto = date.fromisoformat(s["to"])
        if sfrom <= target_date <= sto and s.get("mode", "train") in travel_modes:
            return True, f"Transport strike on {target_date.isoformat()}: {s.get('note', '')}"

    return False, ""


# ---- 5. Events from real sources (replaces hand-written seasonal calendar) ----

MAX_SPECIFIC_EVENT_DAYS = 14

# Event weight by category/type — higher = more likely to motivate a trip
CATEGORY_WEIGHT = {
    "festivals": 0.9, "performing-arts": 0.8, "concerts": 0.8,
    "community": 0.7, "expos": 0.7, "conferences": 0.6,
    "sports": 0.3, "academic": 0.2, "school-holidays": 0.2,
}
# AI-discovered event_type weights
EVENT_TYPE_WEIGHT = {
    "festival": 0.9, "food_wine": 0.85, "classical_art": 0.8,
    "indie_music": 0.75, "market_fair": 0.7, "nature": 0.6,
    "sport": 0.3, "other": 0.5,
}
CROWD_WEIGHT = {"large": 1.0, "medium": 0.7, "small": 0.4}
AUDIENCE_WEIGHT = {"all_ages": 1.0, "families": 0.8, "adults": 0.8}


def _phq_event_weight(ev: dict) -> float:
    """Weight a PredictHQ event: category × rank. Low-tier sport = tiny weight."""
    cat = ev.get("category", "")
    rank = ev.get("rank") or ev.get("local_rank") or 50
    cat_w = CATEGORY_WEIGHT.get(cat, 0.5)
    rank_w = min(rank / 100, 1.0)
    return round(cat_w * rank_w, 3)


def _ai_event_weight(ev: dict) -> float:
    """Weight an AI-discovered event: type × crowd × audience."""
    etype = ev.get("event_type", "other")
    crowd = ev.get("crowd_size", "medium")
    audience = ev.get("audience", "all_ages")
    return round(
        EVENT_TYPE_WEIGHT.get(etype, 0.5)
        * CROWD_WEIGHT.get(crowd, 0.7)
        * AUDIENCE_WEIGHT.get(audience, 1.0),
        3,
    )


def _event_duration_days(ev: dict) -> int | None:
    """Return event duration in days, or None if dates are missing/invalid."""
    dates = ev.get("dates", {})
    efrom = dates.get("from", "")
    eto = dates.get("to", efrom)
    if not efrom:
        return None
    try:
        return (date.fromisoformat(eto) - date.fromisoformat(efrom)).days + 1
    except ValueError:
        return None


def _event_active_on(ev: dict, target_date: date) -> bool:
    """Is this event running on target_date?"""
    dates = ev.get("dates", {})
    efrom = dates.get("from", "")
    eto = dates.get("to", efrom)
    return bool(efrom) and efrom <= target_date.isoformat() <= eto


def score_seasonal(target_date: date, data_dir: Path, hotel_id: str | None = None,
                    hotel: dict | None = None) -> dict:
    from events_db import load_events
    from demand_signals import fetch_predicthq_events

    score = 0.0
    reasons = []
    also_on = []
    event_sources = []
    seen_names: set[str] = set()

    events_list = []
    fallback_source = None
    db_data = load_events(hotel_id) if hotel_id else None
    if db_data and db_data.get("events"):
        events_list = db_data["events"]
        sources = db_data.get("sources", [])
        if sources:
            fallback_source = sources[0]
    else:
        hotel_events_file = data_dir / f"local_events_{hotel_id}.json" if hotel_id else None
        if hotel_events_file and hotel_events_file.exists():
            try:
                edata = json.loads(hotel_events_file.read_text())
                events_list = edata.get("events", [])
                sources = edata.get("sources", [])
                if sources:
                    fallback_source = sources[0] if isinstance(sources[0], str) else None
            except (json.JSONDecodeError, KeyError):
                pass

    for ev in events_list:
        if ev.get("hidden") or not _event_active_on(ev, target_date):
            continue
        source_url = ev.get("source_url") or fallback_source
        if not source_url:
            continue
        duration = _event_duration_days(ev)
        weight = _ai_event_weight(ev)
        relevance = ev.get("relevance", 0.5) * weight
        label = f"{ev['name']} ({ev.get('place', 'nearby')})"
        is_highlight = (ev.get("relevance", 0) >= 0.7
                        and ev.get("crowd_size", "") == "large")
        if duration is not None and duration > MAX_SPECIFIC_EVENT_DAYS and not is_highlight:
            also_on.append(label)
            score = max(score, min(relevance * 0.4, 0.3))
        else:
            score = max(score, min(relevance, 0.8))
            reasons.append(label)
        seen_names.add(ev["name"].lower())
        event_sources.append({
            "name": ev["name"], "place": ev.get("place", ""),
            "source_url": source_url, "weight": weight,
        })

    # PredictHQ events (labelled "Source: PredictHQ")
    if hotel:
        lat = hotel.get("lat", hotel.get("coords", {}).get("lat"))
        lon = hotel.get("lon", hotel.get("coords", {}).get("lon"))
        if lat and lon:
            phq = fetch_predicthq_events(lat, lon, cache_only=True)
            for ev in phq.get("events", []):
                start_str = ev.get("start", "")[:10]
                end_str = (ev.get("end") or start_str)[:10]
                if not start_str or ev["name"].lower() in seen_names:
                    continue
                if not (start_str <= target_date.isoformat() <= end_str):
                    continue
                name = ev["name"]
                weight = _phq_event_weight(ev)
                relevance = weight
                try:
                    duration = (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days + 1
                except ValueError:
                    duration = 1
                label = f"{name} (nearby)"
                if duration > MAX_SPECIFIC_EVENT_DAYS:
                    also_on.append(label)
                    score = max(score, min(relevance * 0.4, 0.3))
                else:
                    score = max(score, min(relevance, 0.8))
                    reasons.append(label)
                seen_names.add(name.lower())
                event_sources.append({
                    "name": name, "place": "", "source_url": "Source: PredictHQ",
                    "weight": weight, "category": ev.get("category", ""),
                    "rank": ev.get("rank") or ev.get("local_rank") or 0,
                })

    return {"score": round(score, 2), "reasons": reasons, "also_on": also_on, "event_sources": event_sources, "details": {}}


# ---- 6. Event sources (placeholder) ----

def score_events(hotel: dict, target_date: date, settings: dict) -> dict:
    return {"score": 0, "reasons": [], "details": {}}
