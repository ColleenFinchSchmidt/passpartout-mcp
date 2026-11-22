"""Step 3: Demand signals from external APIs.

Two data sources, each gated behind its own API key:

  PREDICTHQ_API_KEY  — PredictHQ event-demand intelligence (free tier: 2 locations)
  DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD — DataForSEO Google Hotels competitor pricing

Both are optional.  When a key is missing the function returns a helpful
error dict instead of crashing.

Results are cached to disk and refreshed once per day to protect costs.
"""

import base64
import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

PREDICTHQ_API_KEY = os.environ.get("PREDICTHQ_API_KEY", "")
DATAFORSEO_LOGIN = os.environ.get("DATAFORSEO_LOGIN", "")
DATAFORSEO_PASSWORD = os.environ.get("DATAFORSEO_PASSWORD", "")

_http = httpx.Client(timeout=30)

CACHE_DIR = Path(__file__).parent / "moments_data" / "cache"
CACHE_DIR.mkdir(exist_ok=True)
_CACHE_MAX_AGE_HOURS = 24


def _read_cache(key: str) -> dict | None:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        fetched = data.get("_cached_at", "")
        if fetched and (date.today() - date.fromisoformat(fetched[:10])).days < 1:
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _write_cache(key: str, data: dict) -> None:
    data["_cached_at"] = date.today().isoformat()
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

# ---------------------------------------------------------------------------
# PredictHQ — event demand intelligence
# ---------------------------------------------------------------------------

def fetch_predicthq_events(
    lat: float,
    lon: float,
    radius_km: int = 30,
    days_ahead: int = 90,
    limit: int = 20,
    force_refresh: bool = False,
) -> dict:
    """Fetch upcoming events near a location from PredictHQ."""
    if not PREDICTHQ_API_KEY:
        return {
            "error": "PREDICTHQ_API_KEY not set.",
            "signup": "Free tier at https://www.predicthq.com/pricing — covers 2 locations.",
        }

    cache_key = f"predicthq_{lat}_{lon}_{radius_km}_{days_ahead}"
    if not force_refresh:
        cached = _read_cache(cache_key)
        if cached:
            cached["_from_cache"] = True
            return cached

    today = date.today()
    end = today + timedelta(days=days_ahead)

    params = {
        "within": f"{radius_km}km@{lat},{lon}",
        "active.gte": today.isoformat(),
        "active.lte": end.isoformat(),
        "category": "conferences,expos,concerts,festivals,performing-arts,sports,community",
        "sort": "rank",
        "limit": str(limit),
    }

    try:
        resp = _http.get(
            "https://api.predicthq.com/v1/events/",
            params=params,
            headers={
                "Authorization": f"Bearer {PREDICTHQ_API_KEY}",
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:300]
        logger.error("PredictHQ API error %s: %s", exc.response.status_code, body)
        return {"error": f"PredictHQ API error {exc.response.status_code}", "detail": body}
    except Exception as exc:
        logger.error("PredictHQ request failed: %s", exc)
        return {"error": str(exc)}

    events = []
    for item in data.get("results", []):
        events.append({
            "name": item.get("title", ""),
            "category": item.get("category", ""),
            "start": item.get("start", ""),
            "end": item.get("end", ""),
            "rank": item.get("rank"),
            "local_rank": item.get("local_rank"),
            "location": item.get("location", []),
            "labels": item.get("labels", []),
        })

    result = {
        "source": "PredictHQ",
        "location": f"{lat},{lon}",
        "radius_km": radius_km,
        "period": f"{today.isoformat()} to {end.isoformat()}",
        "count": data.get("count", 0),
        "events": events,
    }
    _write_cache(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# DataForSEO — competitor hotel pricing via Google Hotels
# ---------------------------------------------------------------------------

def fetch_competitor_prices(
    location_name: str,
    keyword: str = "",
    check_in: str = "",
    check_out: str = "",
    adults: int = 2,
    currency: str = "EUR",
    force_refresh: bool = False,
) -> dict:
    """Fetch competitor hotel prices from Google Hotels via DataForSEO."""
    if not DATAFORSEO_LOGIN or not DATAFORSEO_PASSWORD:
        return {
            "error": "DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD not set.",
            "signup": "Pay-as-you-go at https://dataforseo.com — ~$0.004 per live query.",
        }

    if not check_in:
        check_in = (date.today() + timedelta(days=14)).isoformat()
    if not check_out:
        check_out = (date.today() + timedelta(days=16)).isoformat()

    cache_key = f"dataforseo_{location_name}_{check_in}_{check_out}".replace(",", "_").replace(" ", "_")
    if not force_refresh:
        cached = _read_cache(cache_key)
        if cached:
            cached["_from_cache"] = True
            return cached

    creds = base64.b64encode(
        f"{DATAFORSEO_LOGIN}:{DATAFORSEO_PASSWORD}".encode()
    ).decode()

    task = {
        "location_name": location_name,
        "language_code": "en",
        "currency": currency,
        "check_in": check_in,
        "check_out": check_out,
        "adults": adults,
    }
    if keyword:
        task["keyword"] = keyword

    try:
        resp = _http.post(
            "https://api.dataforseo.com/v3/business_data/google/hotel_searches/live",
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/json",
            },
            content=json.dumps([task]),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:300]
        logger.error("DataForSEO API error %s: %s", exc.response.status_code, body)
        return {"error": f"DataForSEO API error {exc.response.status_code}", "detail": body}
    except Exception as exc:
        logger.error("DataForSEO request failed: %s", exc)
        return {"error": str(exc)}

    hotels = []
    for task_result in data.get("tasks", []):
        for result in task_result.get("result", []) or []:
            for item in result.get("items", []) or []:
                hotel_entry = {
                    "name": item.get("title", ""),
                    "stars": item.get("stars"),
                    "rating": item.get("rating"),
                    "reviews": item.get("reviews_count"),
                }
                prices = item.get("prices", {}) or {}
                if prices:
                    hotel_entry["price"] = prices.get("price")
                    hotel_entry["price_before_discount"] = prices.get("price_without_discount")
                    hotel_entry["currency"] = prices.get("currency", currency)
                hotels.append(hotel_entry)

    cost_info = data.get("tasks", [{}])[0].get("cost", 0)

    result = {
        "source": "DataForSEO / Google Hotels",
        "location": location_name,
        "check_in": check_in,
        "check_out": check_out,
        "api_cost": cost_info,
        "hotels_found": len(hotels),
        "hotels": hotels[:20],
    }
    _write_cache(cache_key, result)
    return result
