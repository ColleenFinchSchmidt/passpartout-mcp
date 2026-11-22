"""Live weather forecasts from Open-Meteo, used to trigger getaway offers."""

import json
import logging
import time
from datetime import date, datetime
from urllib.error import URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CITY_COORDS = {
    "Milan": (45.46, 9.19),
    "Turin": (45.07, 7.69),
}

HOTEL_COORDS = {
    "h-como-1":      (46.01, 9.28),   # Varenna
    "h-langhe-1":    (44.64, 7.93),   # La Morra
    "h-liguria-1":   (44.35, 9.15),   # Camogli
    "h-garda-1":     (45.49, 10.61),  # Sirmione
    "h-valtellina-1": (46.47, 10.37), # Bormio
}

_cache: dict = {}
_cache_time: float = 0.0
_CACHE_TTL = 3600


def _fetch_one(lat: float, lon: float) -> dict | None:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&timezone=Europe/Rome&forecast_days=7"
    )
    try:
        req = Request(url, headers={"User-Agent": "passpartout-demo/1.0"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        return data.get("daily")
    except (URLError, OSError, json.JSONDecodeError, KeyError) as exc:
        logger.warning("Open-Meteo failed for (%.2f, %.2f): %s", lat, lon, exc)
        return None


def _fetch_all() -> dict[str, dict]:
    global _cache, _cache_time
    if _cache and (time.time() - _cache_time) < _CACHE_TTL:
        return _cache

    result: dict[str, dict] = {}
    for name, (lat, lon) in {**CITY_COORDS, **HOTEL_COORDS}.items():
        daily = _fetch_one(lat, lon)
        if daily:
            result[name] = daily

    if result:
        _cache = result
        _cache_time = time.time()
    return result


# ---- weather-code helpers ----

def _is_rainy(code: int) -> bool:
    return code in range(51, 68) or code in range(80, 83) or code in range(95, 100)

def _is_snowy(code: int) -> bool:
    return code in range(71, 78) or code in range(85, 87)

def _is_sunny(code: int) -> bool:
    return code in (0, 1)

def _is_grey(code: int) -> bool:
    return code in (2, 3, 45, 48) or _is_rainy(code)

def _describe_code(code: int) -> str:
    if _is_sunny(code):
        return "clear"
    if code in (2, 3):
        return "cloudy"
    if code in (45, 48):
        return "foggy"
    if _is_snowy(code):
        return "snowy"
    if _is_rainy(code):
        return "rainy"
    return "mixed"


def _weekend_indices(dates: list[str]) -> list[int]:
    """Indices of the nearest Fri-Sat-Sun block in the forecast.

    From Sunday 14:00 Rome time onward, skip the rest of the current
    weekend and return the coming Friday-to-Sunday instead.
    """
    now = datetime.now(ZoneInfo("Europe/Rome"))
    skip_today = now.weekday() == 6 and now.hour >= 14

    indices = []
    started = False
    for i, d in enumerate(dates):
        day = date.fromisoformat(d)
        if skip_today and day == now.date():
            continue
        wd = day.weekday()
        if wd in (4, 5, 6):  # Fri, Sat, Sun
            started = True
            indices.append(i)
        elif started:
            break
    return indices

def _midweek_indices(dates: list[str]) -> list[int]:
    return [i for i, d in enumerate(dates) if date.fromisoformat(d).weekday() in (0, 1, 2, 3)]


# ---- trigger evaluation ----

def _check_trigger(trigger_type: str, city_fc: dict, dest_fc: dict | None, city: str) -> str | None:
    """Return a reason string if the trigger fires, else None."""
    codes = city_fc["weather_code"]
    dates = city_fc["time"]

    if trigger_type == "city_rain":
        weekend = _weekend_indices(dates)
        city_rain_wk = [i for i in weekend if _is_rainy(codes[i])]
        # Only trigger if the hotel is drier than the city
        if dest_fc:
            hotel_rain_wk = [i for i in weekend
                             if i < len(dest_fc["weather_code"]) and _is_rainy(dest_fc["weather_code"][i])]
            if len(hotel_rain_wk) >= len(city_rain_wk):
                return None
        if city_rain_wk:
            rainy_dates = [dates[i] for i in city_rain_wk]
            return f"Rain forecast in {city} this weekend ({', '.join(rainy_dates)}), drier at the hotel"
        near = list(range(min(3, len(codes))))
        rainy_near = [dates[i] for i in near if _is_rainy(codes[i])]
        if rainy_near:
            return f"Rain expected in {city} ({', '.join(rainy_near)})"
        return None

    if trigger_type == "coast_sun_city_grey":
        if not dest_fc:
            return None
        for i in range(min(5, len(codes))):
            if _is_grey(codes[i]) and _is_sunny(dest_fc["weather_code"][i]):
                return f"Sun on the coast ({dates[i]}) while {city} is grey"
        return None

    if trigger_type == "mountain_snow":
        if not dest_fc:
            return None
        for i in range(len(dest_fc["weather_code"])):
            if _is_snowy(dest_fc["weather_code"][i]):
                return f"Snow forecast in the Alps ({dest_fc['time'][i]})"
        return None

    if trigger_type == "cool_spa":
        near = list(range(min(5, len(codes))))
        avg_max = sum(city_fc["temperature_2m_max"][i] for i in near) / max(len(near), 1)
        if avg_max < 15:
            return f"Cool days ahead in {city} ({avg_max:.0f} \u00b0C avg) \u2014 thermal spa weather"
        return None

    if trigger_type == "dry_countryside":
        if not dest_fc:
            return None
        if date.today().month not in (10, 11, 12, 1):
            return None
        mid = _midweek_indices(dest_fc["time"])
        if mid and all(dest_fc["precipitation_sum"][i] < 2 for i in mid):
            return "Dry days in the Langhe \u2014 truffle season is on"
        return None

    return None


# ---- public API used by server.py ----

def get_weather_moments(city: str, offers: list[dict]) -> dict:
    """Return weather summary + triggered moments for a city."""
    forecasts = _fetch_all()
    city_fc = forecasts.get(city)
    if not city_fc:
        return {"city": city, "weather": None, "moments": [], "triggered_offers": []}

    today_code = city_fc["weather_code"][0]
    today_max = city_fc["temperature_2m_max"][0]
    today_min = city_fc["temperature_2m_min"][0]

    weekend = _weekend_indices(city_fc["time"])
    if weekend:
        wk_codes = [city_fc["weather_code"][i] for i in weekend]
        wk_desc = " and ".join(dict.fromkeys(_describe_code(c) for c in wk_codes))
        first = city_fc["time"][weekend[0]]
        last = city_fc["time"][weekend[-1]]
        weekend_summary = f"{wk_desc} ({first} to {last})" if first != last else f"{wk_desc} ({first})"
    else:
        weekend_summary = None

    moments = []
    triggered = []
    for offer in offers:
        trigger_type = offer.get("weather_trigger")
        if not trigger_type:
            continue
        dest_fc = forecasts.get(offer["hotel_id"])
        reason = _check_trigger(trigger_type, city_fc, dest_fc, city)
        if reason:
            moments.append(reason)
            triggered.append(offer["id"])

    return {
        "city": city,
        "weather": {
            "today": f"{_describe_code(today_code)}, {today_max:.0f} \u00b0C (low {today_min:.0f} \u00b0C)",
            "weekend": weekend_summary,
            "source": "Open-Meteo (live forecast)",
        },
        "moments": moments,
        "triggered_offers": triggered,
    }


def is_offer_triggered(offer: dict, city: str) -> tuple[bool, str | None]:
    """Check if this offer's weather trigger is active. Returns (triggered, reason)."""
    trigger_type = offer.get("weather_trigger")
    if not trigger_type:
        return True, None
    forecasts = _fetch_all()
    city_fc = forecasts.get(city)
    if not city_fc:
        return True, None
    dest_fc = forecasts.get(offer["hotel_id"])
    reason = _check_trigger(trigger_type, city_fc, dest_fc, city)
    return reason is not None, reason


def get_offer_forecast(hotel_id: str) -> list[dict] | None:
    """Return the next few days' forecast for a hotel's destination."""
    forecasts = _fetch_all()
    fc = forecasts.get(hotel_id)
    if not fc:
        return None
    days = []
    for i in range(min(5, len(fc["time"]))):
        days.append({
            "date": fc["time"][i],
            "weather": _describe_code(fc["weather_code"][i]),
            "high": round(fc["temperature_2m_max"][i]),
            "low": round(fc["temperature_2m_min"][i]),
        })
    return days
