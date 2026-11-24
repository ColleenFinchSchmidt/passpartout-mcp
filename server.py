"""Passpartout demo: MCP server + REST API.

Lets an AI assistant (Claude, ChatGPT, ...) find and book private,
moment-triggered hotel offers within reach of a city.

DEMO ONLY: fictional hotels, simulated availability, no real bookings or payments.

Run locally:     python server.py            (http://127.0.0.1:8000)
Run for Claude:  python server.py --stdio
API docs:        http://127.0.0.1:8000/docs
MCP endpoint:    http://127.0.0.1:8000/mcp
"""

import hashlib
import logging
import os
import sys
import threading
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, EmailStr
from starlette.middleware.cors import CORSMiddleware

from data import DEMO_MEMBER_CODE, HOTELS, OFFERS
from weather import get_weather_moments, is_offer_triggered, get_offer_forecast
from moments_engine import evaluate_hotel, explain_moments, run_backtest, load_json, _free_rooms
from data_refresh import refresh_holidays
from local_events import discover_events, get_approved_events
from demand_signals import fetch_predicthq_events, fetch_competitor_prices
from inventory import store as inventory_store

# ---------- shared state ----------

HOTEL_BY_ID = {h["id"]: h for h in HOTELS}
OFFER_BY_ID = {o["id"]: o for o in OFFERS}
BOOKINGS: dict[str, dict] = {}

MOMENTS_DATA = Path(__file__).parent / "moments_data"

holidays_file = MOMENTS_DATA / "holidays.json"
if not holidays_file.exists() or (date.today() - date.fromisoformat(
        load_json(holidays_file).get("_generated", "2000-01-01"))).days > 30:
    refresh_holidays(MOMENTS_DATA)

MOMENTS_SETTINGS = load_json(MOMENTS_DATA / "settings.json")
MOMENTS_HOTELS = load_json(MOMENTS_DATA / "hotels.json")
MOMENTS_HOTEL_BY_ID = {h["id"]: h for h in MOMENTS_HOTELS}


ROME_TZ = ZoneInfo("Europe/Rome")
_log = logging.getLogger(__name__)


def _refresh_paid_caches(force_events: bool = False):
    """Refresh stale paid-API caches (once per day max per cache key).

    Called at startup and daily at 06:00 Rome time by the background scheduler.
    force_events=True: re-run AI event discovery regardless of cache freshness
    (used on startup/deploy so new extraction prompts take effect immediately).
    """
    for hotel in MOMENTS_HOTELS:
        lat = hotel.get("lat", 46.01)
        lon = hotel.get("lon", 9.28)
        region = hotel.get("region", "Lecco,Lombardy,Italy")
        town = hotel.get("town", "varenna")

        try:
            result = fetch_predicthq_events(lat, lon, radius_km=30, days_ahead=90)
            if result.get("_from_cache"):
                _log.info("PredictHQ cache fresh for %s", hotel["name"])
            elif "error" not in result:
                _log.info("PredictHQ cache refreshed for %s (%d events)", hotel["name"], len(result.get("events", [])))
        except Exception as exc:
            _log.warning("PredictHQ refresh failed for %s: %s", hotel["name"], exc)

        try:
            result = fetch_competitor_prices(location_name=region, keyword=f"hotel {town} lake como")
            if result.get("_from_cache"):
                _log.info("DataForSEO cache fresh for %s", hotel["name"])
            elif "error" not in result:
                _log.info("DataForSEO cache refreshed for %s (%d hotels)", hotel["name"], result.get("hotels_found", 0))
        except Exception as exc:
            _log.warning("DataForSEO refresh failed for %s: %s", hotel["name"], exc)

        try:
            result = discover_events(hotel, MOMENTS_DATA, force=force_events)
            if result.get("_from_cache"):
                _log.warning("Local events cache fresh for %s (cached=%d events)", hotel["name"], len(result.get("events", [])))
            elif "error" in result:
                _log.warning("Local events discovery error for %s: %s", hotel["name"], result["error"])
            else:
                _log.warning("Local events refreshed for %s (%d events found)", hotel["name"], len(result.get("events", [])))
        except Exception as exc:
            _log.warning("Local events refresh failed for %s: %s", hotel["name"], exc)


def _start_daily_scheduler():
    """Background thread: run _refresh_paid_caches() every day at 06:00 Rome time."""
    def _loop():
        while True:
            now = datetime.now(ROME_TZ)
            target = datetime.combine(now.date(), dtime(6, 0), tzinfo=ROME_TZ)
            if now >= target:
                target += timedelta(days=1)
            wait_secs = (target - now).total_seconds()
            _log.info("Daily cache refresh scheduled for %s (in %.0f min)",
                       target.strftime("%Y-%m-%d %H:%M %Z"), wait_secs / 60)
            threading.Event().wait(wait_secs)
            _log.info("Daily cache refresh starting")
            try:
                _refresh_paid_caches()
                _log.info("Daily cache refresh complete")
            except Exception as exc:
                _log.error("Daily cache refresh failed: %s", exc)

    t = threading.Thread(target=_loop, daemon=True, name="daily-cache-refresh")
    t.start()


def _needs_event_refresh() -> bool:
    """Only force event discovery if any hotel's data is older than 24h."""
    from events_db import get_discovered_at
    for hotel in MOMENTS_HOTELS:
        discovered = get_discovered_at(hotel["id"])
        if not discovered or (date.today() - discovered).days >= 1:
            return True
    return False


def _run_startup_refresh():
    """Run the initial cache refresh in a background thread so the server starts fast."""
    try:
        force = _needs_event_refresh()
        if force:
            _log.info("Event data >24h old — forcing rediscovery")
        _refresh_paid_caches(force_events=force)
        _log.info("Startup cache refresh complete")
    except Exception as exc:
        _log.error("Startup cache refresh failed: %s", exc)

threading.Thread(target=_run_startup_refresh, daemon=True, name="startup-refresh").start()
_start_daily_scheduler()

HOTEL_API_KEY = os.environ.get("HOTEL_API_KEY", "")


def require_hotel_api_key(x_api_key: str = Header(None)):
    """Protect /api/hotel/* endpoints. MCP tools bypass this."""
    if not HOTEL_API_KEY:
        return
    if x_api_key != HOTEL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Api-Key header.")


# ---------- helpers (used by both MCP tools and REST endpoints) ----------

def _parse_date(value: str | None) -> date:
    if not value:
        today = date.today()
        return today + timedelta(days=(5 - today.weekday()) % 7 or 7)
    return date.fromisoformat(value)


def _is_member(member_code: str | None) -> bool:
    return (member_code or "").strip().upper() == DEMO_MEMBER_CODE


def _rooms_left(offer_id: str, night: date) -> int:
    """Deterministic fake availability: 0-3 rooms per night."""
    h = hashlib.sha256(f"{offer_id}{night.isoformat()}".encode()).digest()[0]
    return h % 4


def _availability(offer: dict, check_in: date, nights: int) -> tuple[bool, str]:
    days_ahead = (check_in - date.today()).days
    lo, hi = offer["notice_days"]
    if days_ahead < lo or days_ahead > hi:
        return False, f"Offer is valid for stays {lo}-{hi} days from today."
    if nights < offer["min_nights"]:
        return False, f"Minimum stay is {offer['min_nights']} nights."
    for i in range(nights):
        night = check_in + timedelta(days=i)
        if offer["weekdays_only"] and night.weekday() in (4, 5):
            return False, "This offer is for Sunday-Thursday nights only."
        if _rooms_left(offer["id"], night) == 0:
            return False, f"Sold out on {night.isoformat()}."
    return True, "Available."


def _travel(hotel: dict, from_city: str) -> dict:
    t = hotel["from"].get(from_city, {})
    return {
        "by_car_minutes": t.get("car_min"),
        "by_train_minutes": t.get("train_min"),
        "station_walk_minutes": hotel.get("station_walk_min"),
        "station_pickup": hotel.get("pickup"),
    }


def _price(offer: dict, hotel: dict, nights: int, member: bool) -> dict:
    public_total = hotel["public_rate_eur"] * nights
    if not member:
        return {
            "price_shown": "public",
            "total_eur": public_total,
            "note": f"{offer['public_added_value']}. Members get a private rate.",
        }
    member_total = round(public_total * (1 - offer["member_discount_pct"] / 100))
    return {
        "price_shown": "member (private)",
        "total_eur": member_total,
        "you_save_eur": public_total - member_total,
        "note": "Private member rate. Please don't share it publicly.",
    }


def _offer_view(offer: dict, from_city: str, nights: int, member: bool) -> dict:
    hotel = HOTEL_BY_ID[offer["hotel_id"]]
    triggered, reason = is_offer_triggered(offer, from_city)
    view = {
        "offer_id": offer["id"],
        "title": offer["title"],
        "hotel": hotel["name"],
        "town": hotel["town"],
        "why_now": reason or offer["trigger"],
        "weather_triggered": triggered,
        "includes": offer["includes"],
        "travel_from_" + from_city.lower(): _travel(hotel, from_city),
        "nights": nights,
        "price": _price(offer, hotel, nights, member),
    }
    forecast = get_offer_forecast(offer["hotel_id"])
    if forecast:
        view["destination_forecast"] = forecast
    return view


def _find_getaways(
    from_city: str, check_in: str | None, nights: int, max_travel_minutes: int,
    travel_mode: str, max_total_eur: int | None, vibe: str | None, member_code: str | None,
) -> dict:
    start = _parse_date(check_in)
    member = _is_member(member_code)
    results, unavailable = [], []
    for offer in OFFERS:
        hotel = HOTEL_BY_ID[offer["hotel_id"]]
        t = hotel["from"].get(from_city)
        if not t:
            continue
        times = {"car": t.get("car_min"), "train": t.get("train_min")}
        modes = ["car", "train"] if travel_mode == "any" else [travel_mode]
        reachable = [times[m] for m in modes if times.get(m) is not None]
        if not reachable or min(reachable) > max_travel_minutes:
            continue
        if vibe and vibe.lower() not in hotel["vibe"]:
            continue
        ok, reason = _availability(offer, start, nights)
        if not ok:
            unavailable.append({"offer_id": offer["id"], "title": offer["title"], "reason": reason})
            continue
        view = _offer_view(offer, from_city, nights, member)
        if max_total_eur and view["price"]["total_eur"] > max_total_eur:
            continue
        results.append(view)
    return {
        "demo": True,
        "check_in": start.isoformat(),
        "member": member,
        "offers": results,
        "not_available_for_these_dates": unavailable,
    }


def _get_offer(offer_id: str, from_city: str, nights: int, member_code: str | None) -> dict:
    offer = OFFER_BY_ID.get(offer_id)
    if not offer:
        return {"error": f"No offer with id {offer_id}."}
    view = _offer_view(offer, from_city, nights, _is_member(member_code))
    view.update({
        "min_nights": offer["min_nights"],
        "bookable_days_ahead": offer["notice_days"],
        "sunday_to_thursday_only": offer["weekdays_only"],
        "demo": True,
    })
    return view


def _check_availability(offer_id: str, check_in: str, nights: int) -> dict:
    offer = OFFER_BY_ID.get(offer_id)
    if not offer:
        return {"error": f"No offer with id {offer_id}."}
    ok, reason = _availability(offer, _parse_date(check_in), nights)
    return {"offer_id": offer_id, "check_in": check_in, "nights": nights, "available": ok, "detail": reason}


def _book_offer(
    offer_id: str, check_in: str, nights: int,
    guest_name: str, guest_email: str, member_code: str | None,
) -> dict:
    offer = OFFER_BY_ID.get(offer_id)
    if not offer:
        return {"error": f"No offer with id {offer_id}."}
    start = _parse_date(check_in)
    ok, reason = _availability(offer, start, nights)
    if not ok:
        return {"booked": False, "reason": reason}
    hotel = HOTEL_BY_ID[offer["hotel_id"]]
    price = _price(offer, hotel, nights, _is_member(member_code))
    ref = "PP-" + hashlib.sha256(f"{offer_id}{check_in}{guest_email}".encode()).hexdigest()[:6].upper()
    BOOKINGS[ref] = {
        "offer_id": offer_id, "check_in": check_in, "nights": nights,
        "guest": guest_name, "email": guest_email, "total_eur": price["total_eur"],
    }
    return {
        "booked": True,
        "demo": True,
        "reference": ref,
        "hotel": hotel["name"],
        "check_in": start.isoformat(),
        "nights": nights,
        "total_eur": price["total_eur"],
        "payment_link": f"https://pay.example.com/demo/{ref}",
        "note": "Demo booking: no room was reserved and no payment will be taken.",
    }


# ========== MCP SERVER ==========

mcp = MCPServer(
    name="passpartout",
    title="Passpartout (demo)",
    instructions=(
        "Passpartout has two sides: GUEST tools help travellers find private hotel offers "
        "triggered by live weather (call current_moments first). HOTEL tools help hotel "
        "operators decide what to offer: suggest_offers shows today's suggestions with "
        "pricing, explain_moments_tool breaks down why each moment fires, and backtest_tool "
        "replays historical weather to show which weekends would have been flagged. "
        "Public prices show added value only; the real discount is shown only to members. "
        "Always say this is a demo with fictional hotels."
    ),
)


@mcp.tool()
def current_moments(city: str = "Milan") -> dict:
    """What's happening now that makes a short getaway from this city a good idea.
    Returns the live weather forecast and moments triggered by the forecast."""
    result = get_weather_moments(city, OFFERS)
    result["demo"] = True
    return result


@mcp.tool()
def find_getaways(
    from_city: str = "Milan", check_in: str | None = None, nights: int = 2,
    max_travel_minutes: int = 180, travel_mode: str = "any",
    max_total_eur: int | None = None, vibe: str | None = None,
    member_code: str | None = None,
) -> dict:
    """Find private hotel offers within reach of a city.

    from_city: 'Milan' or 'Turin' in the demo.
    check_in: YYYY-MM-DD (defaults to next Saturday).
    travel_mode: 'car', 'train' or 'any'.
    vibe: optional, e.g. 'lake', 'wine', 'sea', 'spa', 'mountains', 'romantic'.
    member_code: members see the private rate (demo code: DEMO-MEMBER).
    """
    return _find_getaways(from_city, check_in, nights, max_travel_minutes, travel_mode, max_total_eur, vibe, member_code)


@mcp.tool()
def get_offer(offer_id: str, from_city: str = "Milan", nights: int = 2, member_code: str | None = None) -> dict:
    """Full details of one offer."""
    return _get_offer(offer_id, from_city, nights, member_code)


@mcp.tool()
def check_availability(offer_id: str, check_in: str, nights: int = 2) -> dict:
    """Check whether an offer is available for given dates."""
    return _check_availability(offer_id, check_in, nights)


@mcp.tool()
def book_offer(
    offer_id: str, check_in: str, nights: int,
    guest_name: str, guest_email: str, member_code: str | None = None,
) -> dict:
    """Book an offer (DEMO: creates a fake booking and a fake payment link).
    Always confirm the dates, price and guest details with the traveller before calling."""
    return _book_offer(offer_id, check_in, nights, guest_name, guest_email, member_code)


# ========== HOTEL-SIDE MCP TOOLS ==========


def _resolve_hotel(hotel_id: str | None) -> dict | None:
    if hotel_id:
        return MOMENTS_HOTEL_BY_ID.get(hotel_id)
    if MOMENTS_HOTELS:
        return MOMENTS_HOTELS[0]
    return None


@mcp.tool()
def suggest_offers(hotel_id: str | None = None) -> dict:
    """Today's suggested offers for a hotel, with why now, nights, rooms,
    prices, and which guest city each targets.

    hotel_id: hotel to check (defaults to the demo hotel h-como-1).
    Returns the moments engine's suggestions based on live weather, air quality,
    holidays, seasonal events, and room availability."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        return {"error": f"Hotel not found: {hotel_id}. Available: {[h['id'] for h in MOMENTS_HOTELS]}"}
    suggestions = evaluate_hotel(hotel, MOMENTS_SETTINGS, MOMENTS_DATA)
    return {
        "hotel": hotel["name"],
        "hotel_id": hotel["id"],
        "date": date.today().isoformat(),
        "suggestions": suggestions,
        "settings_summary": {
            "min_score": MOMENTS_SETTINGS.get("min_score_to_fire"),
            "booking_window": MOMENTS_SETTINGS.get("booking_window_days"),
        },
        "demo": True,
    }


@mcp.tool()
def explain_moments_tool(
    hotel_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """Explain which moments are firing and why for a hotel over a date range.

    hotel_id: hotel to check (defaults to demo hotel).
    start/end: YYYY-MM-DD date range (defaults to next 7 days).
    Shows each source's score and reasons per day per guest city."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        return {"error": f"Hotel not found: {hotel_id}. Available: {[h['id'] for h in MOMENTS_HOTELS]}"}
    start_date = date.fromisoformat(start) if start else date.today()
    end_date = date.fromisoformat(end) if end else start_date + timedelta(days=6)
    if (end_date - start_date).days > 30:
        return {"error": "Date range too long (max 30 days)."}
    results = explain_moments(hotel, MOMENTS_SETTINGS, MOMENTS_DATA, start_date, end_date)
    return {
        "hotel": hotel["name"],
        "hotel_id": hotel["id"],
        "range": f"{start_date.isoformat()} to {end_date.isoformat()}",
        "days": results,
        "demo": True,
    }


@mcp.tool()
def backtest_tool(hotel_id: str | None = None, months: int = 12) -> dict:
    """Back-test: which weekends in the last N months would the engine have
    flagged, with reasons and scores. Uses real historical weather from Open-Meteo.

    hotel_id: hotel to check (defaults to demo hotel).
    months: how many months to look back (default 12, max 24).
    Returns flagged weekends with reasons, scores, and weather descriptions."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        return {"error": f"Hotel not found: {hotel_id}. Available: {[h['id'] for h in MOMENTS_HOTELS]}"}
    months = min(max(months, 1), 24)
    return run_backtest(hotel, MOMENTS_SETTINGS, months, MOMENTS_DATA)


@mcp.tool()
def refresh_data() -> dict:
    """Refresh auto-generated data: Italian public holidays (from the
    holidays Python package, includes Easter), auto-calculated ponti
    (bridge days), and regional school calendars (Lombardy, Piedmont).

    Call this to update the data files after adding a new year or region."""
    data = refresh_holidays(MOMENTS_DATA)
    return {
        "refreshed": data["_generated"],
        "public_holidays": len(data["public_holidays"]),
        "ponti": len(data["ponti"]),
        "school_periods": len(data["school_holidays"]),
    }


@mcp.tool()
def discover_local_events(hotel_id: str | None = None) -> dict:
    """Show previously discovered local events near the hotel (cached data).
    Events refresh automatically once a day at server startup.

    hotel_id: hotel to scan (defaults to demo hotel)."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        return {"error": f"Hotel not found: {hotel_id}"}
    return discover_events(hotel, MOMENTS_DATA, cache_only=True)


@mcp.tool()
def list_local_events(hotel_id: str | None = None) -> dict:
    """List discovered local events for a hotel. Events marked as hidden
    by the hotel are excluded.

    hotel_id: hotel to check (defaults to demo hotel)."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        return {"error": f"Hotel not found: {hotel_id}"}
    events = get_approved_events(hotel, MOMENTS_DATA)
    return {"events": events, "count": len(events)}


@mcp.tool()
def demand_events(hotel_id: str | None = None, days_ahead: int = 90) -> dict:
    """Upcoming events near a hotel from PredictHQ (cached data).
    Data refreshes automatically once a day at server startup.

    hotel_id: hotel to check (defaults to demo hotel).
    days_ahead: how far ahead to look (default 90 days)."""
    hotel = MOMENTS_HOTEL_BY_ID.get(hotel_id or "villa-glicine")
    if not hotel:
        return {"error": f"Hotel not found: {hotel_id}"}
    lat = hotel.get("lat", 46.01)
    lon = hotel.get("lon", 9.28)
    return fetch_predicthq_events(lat, lon, radius_km=30, days_ahead=days_ahead, cache_only=True)


@mcp.tool()
def competitor_prices(
    hotel_id: str | None = None,
    check_in: str = "",
    check_out: str = "",
) -> dict:
    """Competitor hotel prices from Google Hotels (cached data).
    Data refreshes automatically once a day at server startup.

    hotel_id: hotel to check (defaults to demo hotel).
    check_in: YYYY-MM-DD (defaults to 2 weeks from now).
    check_out: YYYY-MM-DD (defaults to check_in + 2 nights)."""
    hotel = MOMENTS_HOTEL_BY_ID.get(hotel_id or "villa-glicine")
    if not hotel:
        return {"error": f"Hotel not found: {hotel_id}"}
    location = hotel.get("region", "Lecco,Lombardy,Italy")
    keyword = f"hotel {hotel.get('town', 'varenna')} lake como"
    return fetch_competitor_prices(
        location_name=location,
        keyword=keyword,
        check_in=check_in,
        check_out=check_out,
        cache_only=True,
    )


# ========== REST API ==========

api = FastAPI(
    title="Passpartout API",
    description=(
        "REST API for the Passpartout demo. Find and book private, moment-triggered "
        "hotel offers within a short drive or train ride of Milan or Turin.\n\n"
        "**Demo only:** hotels are fictional, availability is simulated, bookings are fake.\n\n"
        "The MCP endpoint for AI assistants is at `/mcp`."
    ),
    version="1.0.0",
)


@api.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@api.get("/api/moments", tags=["Moments"])
def api_moments(city: str = Query("Milan", description="City name ('Milan' or 'Turin' in the demo)")):
    """Live weather and moments that trigger getaway offers from this city."""
    result = get_weather_moments(city, OFFERS)
    result["demo"] = True
    return result


@api.get("/api/offers", tags=["Offers"])
def api_find_offers(
    from_city: str = Query("Milan", description="Departure city"),
    check_in: str | None = Query(None, description="Check-in date (YYYY-MM-DD, defaults to next Saturday)"),
    nights: int = Query(2, ge=1, le=14, description="Number of nights"),
    max_travel_minutes: int = Query(180, ge=30, le=600, description="Max travel time in minutes"),
    travel_mode: str = Query("any", description="'car', 'train' or 'any'"),
    max_total_eur: int | None = Query(None, ge=1, description="Max total price in EUR"),
    vibe: str | None = Query(None, description="e.g. 'lake', 'wine', 'sea', 'spa', 'mountains', 'romantic'"),
    member_code: str | None = Query(None, description="Member code for private rates (demo: DEMO-MEMBER)"),
):
    """Search for available getaway offers."""
    return _find_getaways(from_city, check_in, nights, max_travel_minutes, travel_mode, max_total_eur, vibe, member_code)


@api.get("/api/offers/{offer_id}", tags=["Offers"])
def api_get_offer(
    offer_id: str,
    from_city: str = Query("Milan", description="Departure city"),
    nights: int = Query(2, ge=1, le=14, description="Number of nights"),
    member_code: str | None = Query(None, description="Member code for private rates"),
):
    """Get full details of one offer."""
    result = _get_offer(offer_id, from_city, nights, member_code)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@api.get("/api/offers/{offer_id}/availability", tags=["Availability"])
def api_check_availability(
    offer_id: str,
    check_in: str = Query(..., description="Check-in date (YYYY-MM-DD)"),
    nights: int = Query(2, ge=1, le=14, description="Number of nights"),
):
    """Check whether an offer is available for the given dates."""
    result = _check_availability(offer_id, check_in, nights)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


class BookingRequest(BaseModel):
    offer_id: str
    check_in: str
    nights: int
    guest_name: str
    guest_email: str
    member_code: str | None = None


@api.post("/api/bookings", tags=["Bookings"])
def api_book(booking: BookingRequest):
    """Book an offer (DEMO: creates a fake booking and payment link)."""
    result = _book_offer(
        booking.offer_id, booking.check_in, booking.nights,
        booking.guest_name, booking.guest_email, booking.member_code,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    if not result.get("booked"):
        raise HTTPException(status_code=409, detail=result.get("reason", "Not available"))
    return result


# ---------- Hotel-side REST endpoints ----------

@api.get("/api/hotel/suggest", tags=["Hotel tools"], dependencies=[Depends(require_hotel_api_key)])
def api_suggest_offers(
    hotel_id: str | None = Query(None, description="Hotel ID (defaults to demo hotel)"),
):
    """Today's suggested offers for a hotel with reasons, pricing and targets."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail=f"Hotel not found: {hotel_id}")
    suggestions = evaluate_hotel(hotel, MOMENTS_SETTINGS, MOMENTS_DATA)
    return {
        "hotel": hotel["name"],
        "hotel_id": hotel["id"],
        "date": date.today().isoformat(),
        "suggestions": suggestions,
        "_hotel_profile": {
            "id": hotel["id"],
            "name": hotel["name"],
            "town": hotel.get("town", ""),
            "amenities": hotel.get("amenities", []),
            "segments_wanted": hotel.get("segments_wanted", []),
            "segments_excluded": hotel.get("segments_excluded", []),
            "experiences": hotel.get("experiences", []),
            "extras": hotel.get("extras", []),
            "rooms": hotel.get("rooms", 0),
            "public_rate_eur": hotel.get("public_rate_eur", 0),
            "lowest_price_eur": hotel.get("lowest_price_eur", 0),
            "max_discount_pct": hotel.get("max_discount_pct", 0),
        },
        "demo": True,
    }


@api.get("/api/hotel/offers-timeline", tags=["Hotel tools"], dependencies=[Depends(require_hotel_api_key)])
def api_offers_timeline(
    hotel_id: str | None = Query(None, description="Hotel ID (defaults to demo hotel)"),
):
    """2-week timeline of offer periods with themes, aligned dates, and skip reasons."""
    from offer_timeline import evaluate_timeline
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail=f"Hotel not found: {hotel_id}")
    periods = evaluate_timeline(hotel, MOMENTS_SETTINGS, MOMENTS_DATA)
    rome_today = datetime.now(ZoneInfo("Europe/Rome")).date()
    return {
        "hotel": hotel["name"],
        "hotel_id": hotel["id"],
        "date": rome_today.isoformat(),
        "periods": periods,
        "_hotel_profile": {
            "id": hotel["id"],
            "name": hotel["name"],
            "town": hotel.get("town", ""),
            "rooms": hotel.get("rooms", 0),
            "public_rate_eur": hotel.get("public_rate_eur", 0),
            "lowest_price_eur": hotel.get("lowest_price_eur", 0),
            "max_discount_pct": hotel.get("max_discount_pct", 0),
            "amenities": hotel.get("amenities", []),
            "extras": hotel.get("extras", []),
        },
        "demo": True,
    }


@api.get("/api/debug/engine-counts", tags=["Debug"], dependencies=[Depends(require_hotel_api_key)])
def api_engine_counts():
    """Count rows in engine-schema tables to verify data survives deploys."""
    import psycopg2
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return {"error": "No DATABASE_URL"}
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    counts = {}
    with conn.cursor() as cur:
        for tbl in ("discovered_events", "inventory_offers", "inventory_waves", "inventory_holds"):
            try:
                cur.execute(f"SELECT COUNT(*) FROM engine.{tbl}")
                counts[tbl] = cur.fetchone()[0]
            except Exception as e:
                counts[tbl] = f"error: {e}"
                conn.rollback()
        cur.execute("""
            SELECT hotel_id, jsonb_array_length(events) AS event_count
            FROM engine.discovered_events
        """)
        counts["events_detail"] = [
            {"hotel_id": r[0], "event_count": r[1]} for r in cur.fetchall()
        ]
    conn.close()
    return counts


@api.get("/api/hotel/settings", tags=["Hotel tools"])
def api_hotel_settings():
    """Return segment definitions and configuration for the portal."""
    return {
        "segments": MOMENTS_SETTINGS.get("segments", {}),
        "amenity_segment_fit": MOMENTS_SETTINGS.get("amenity_segment_fit", {}),
        "signal_segment_weights": MOMENTS_SETTINGS.get("signal_segment_weights", {}),
    }


@api.get("/api/hotel/explain", tags=["Hotel tools"], dependencies=[Depends(require_hotel_api_key)])
def api_explain_moments(
    hotel_id: str | None = Query(None, description="Hotel ID (defaults to demo hotel)"),
    start: str | None = Query(None, description="Start date YYYY-MM-DD (defaults to today)"),
    end: str | None = Query(None, description="End date YYYY-MM-DD (defaults to start + 6 days)"),
):
    """Explain which moments fire for each day in a date range."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail=f"Hotel not found: {hotel_id}")
    start_date = date.fromisoformat(start) if start else date.today()
    end_date = date.fromisoformat(end) if end else start_date + timedelta(days=6)
    if (end_date - start_date).days > 30:
        raise HTTPException(status_code=400, detail="Date range too long (max 30 days)")
    results = explain_moments(hotel, MOMENTS_SETTINGS, MOMENTS_DATA, start_date, end_date)
    return {
        "hotel": hotel["name"],
        "range": f"{start_date.isoformat()} to {end_date.isoformat()}",
        "days": results,
        "demo": True,
    }


@api.get("/api/hotel/events", tags=["Hotel tools"], dependencies=[Depends(require_hotel_api_key)])
def api_events(
    hotel_id: str | None = Query(None, description="Hotel ID (defaults to demo hotel)"),
):
    """List discovered local events near the hotel."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail=f"Hotel not found: {hotel_id}")
    events = get_approved_events(hotel, MOMENTS_DATA)
    return {"events": events, "count": len(events)}


@api.post("/api/hotel/discover-events", tags=["Hotel tools"], dependencies=[Depends(require_hotel_api_key)])
def api_discover_events(
    hotel_id: str | None = Query(None, description="Hotel ID (defaults to demo hotel)"),
    force: bool = Query(False, description="Force rediscovery even if cache is fresh"),
):
    """Run the AI agent to discover local events. Requires ANTHROPIC_API_KEY."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail=f"Hotel not found: {hotel_id}")
    return discover_events(hotel, MOMENTS_DATA, force=force)


@api.get("/api/hotel/event-status", tags=["Hotel tools"])
def api_event_status():
    """Diagnostic: check event discovery configuration and status."""
    from local_events import ANTHROPIC_API_KEY as _ak, TOURISM_URLS
    from events_db import get_discovered_at, load_events
    status = {
        "anthropic_key_set": bool(_ak),
        "hotels": {},
    }
    for hotel in MOMENTS_HOTELS:
        hid = hotel["id"]
        discovered = get_discovered_at(hid)
        cached = load_events(hid)
        event_count = len(cached["events"]) if cached and cached.get("events") else 0
        status["hotels"][hid] = {
            "last_discovery": discovered.isoformat() if discovered else None,
            "cached_events": event_count,
            "tourism_urls": TOURISM_URLS.get(hid, []),
        }
    return status


@api.get("/api/hotel/event-debug", tags=["Hotel tools"])
def api_event_debug(
    hotel_id: str | None = Query("bristol-stresa", description="Hotel ID"),
):
    """Debug: test each step of the event discovery pipeline."""
    from local_events import _fetch_page_text, _ask_claude, TOURISM_URLS, ANTHROPIC_API_KEY as _ak, ANTHROPIC_MODEL
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail=f"Hotel not found: {hotel_id}")

    hid = hotel["id"]
    result = {"hotel_id": hid, "steps": {}}

    # Step 1: check key
    result["steps"]["anthropic_key"] = {"set": bool(_ak), "length": len(_ak) if _ak else 0, "model": ANTHROPIC_MODEL}

    # Step 2: test page fetch
    urls = TOURISM_URLS.get(hid, [])
    fetch_results = []
    for url in urls[:2]:
        try:
            text = _fetch_page_text(url, max_chars=5000)
            fetch_results.append({
                "url": url,
                "ok": text is not None,
                "length": len(text) if text else 0,
                "preview": text[:200] if text else None,
            })
        except Exception as exc:
            fetch_results.append({"url": url, "ok": False, "error": str(exc)})
    result["steps"]["page_fetch"] = fetch_results

    # Step 3: test Claude API with minimal prompt
    if _ak:
        try:
            test_resp = _ask_claude(
                "Return exactly: []. Nothing else.",
                "Test ping."
            )
            result["steps"]["claude_api"] = {
                "ok": test_resp is not None,
                "response_preview": test_resp[:100] if test_resp else None,
            }
        except Exception as exc:
            result["steps"]["claude_api"] = {"ok": False, "error": str(exc)}
    else:
        result["steps"]["claude_api"] = {"ok": False, "error": "No API key"}

    # Step 4: mini extraction with real page text
    if _ak and fetch_results and any(f.get("ok") for f in fetch_results):
        try:
            from local_events import EXTRACTION_SYSTEM, HOTEL_LOCATION_LABEL
            from datetime import date as d, timedelta
            location = HOTEL_LOCATION_LABEL.get(hid, "Italy")
            page_text = fetch_results[0].get("preview", "")[:1000]
            today = d.today()
            end_d = today + timedelta(days=90)
            sys_prompt = EXTRACTION_SYSTEM.format(location=location)
            user_prompt = (
                f"Hotel: {hotel['name']} in {hotel.get('town', 'Stresa')}, {location}.\n"
                f"Today: {today.isoformat()}. Events between {today.isoformat()} and {end_d.isoformat()}.\n\n"
                f"--- Source: {fetch_results[0]['url']} ---\n{page_text}"
            )
            resp = _ask_claude(sys_prompt, user_prompt)
            result["steps"]["mini_extraction"] = {
                "ok": resp is not None,
                "response_preview": resp[:500] if resp else None,
                "prompt_chars": len(user_prompt),
            }
        except Exception as exc:
            result["steps"]["mini_extraction"] = {"ok": False, "error": str(exc)}

    # Step 5: run full discovery and capture result
    try:
        disc_result = discover_events(hotel, MOMENTS_DATA, force=True)
        result["steps"]["full_discovery"] = {
            "event_count": len(disc_result.get("events", [])),
            "has_error": "error" in disc_result,
            "note": disc_result.get("note"),
            "error": disc_result.get("error"),
            "raw_preview": disc_result.get("raw", "")[:300] if disc_result.get("raw") else None,
        }
    except Exception as exc:
        result["steps"]["full_discovery"] = {"ok": False, "error": str(exc)}

    # Step 6: verify DB save
    try:
        from events_db import _get_conn as _ev_get_conn, load_events
        conn = _ev_get_conn()
        result["steps"]["db_check"] = {
            "conn_ok": conn is not None,
            "db_url_set": bool(os.environ.get("DATABASE_URL", "")),
        }
        if conn:
            cached = load_events(hid)
            result["steps"]["db_check"]["loaded_events"] = len(cached["events"]) if cached and cached.get("events") else 0
            result["steps"]["db_check"]["discovered_at"] = cached.get("discovered") if cached else None
    except Exception as exc:
        result["steps"]["db_check"] = {"ok": False, "error": str(exc)}

    return result


@api.get("/api/hotel/demand-events", tags=["Demand signals"], dependencies=[Depends(require_hotel_api_key)])
def api_demand_events(
    hotel_id: str | None = Query(None, description="Hotel ID (defaults to demo hotel)"),
    days_ahead: int = Query(90, ge=1, le=365, description="Days to look ahead"),
):
    """Upcoming events from PredictHQ that could drive travel demand. Requires PREDICTHQ_API_KEY."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail=f"Hotel not found: {hotel_id}")
    lat = hotel.get("lat", 46.01)
    lon = hotel.get("lon", 9.28)
    return fetch_predicthq_events(lat, lon, radius_km=30, days_ahead=days_ahead)


@api.get("/api/hotel/competitor-prices", tags=["Demand signals"], dependencies=[Depends(require_hotel_api_key)])
def api_competitor_prices(
    hotel_id: str | None = Query(None, description="Hotel ID (defaults to demo hotel)"),
    check_in: str = Query("", description="Check-in date YYYY-MM-DD (defaults to 2 weeks out)"),
    check_out: str = Query("", description="Check-out date YYYY-MM-DD (defaults to check_in + 2)"),
):
    """Competitor hotel prices from Google Hotels. Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail=f"Hotel not found: {hotel_id}")
    location = hotel.get("region", "Lecco,Lombardy,Italy")
    keyword = f"hotel {hotel.get('town', 'varenna')} lake como"
    return fetch_competitor_prices(
        location_name=location,
        keyword=keyword,
        check_in=check_in,
        check_out=check_out,
    )


@api.get("/api/hotel/backtest", tags=["Hotel tools"], dependencies=[Depends(require_hotel_api_key)])
def api_backtest(
    hotel_id: str | None = Query(None, description="Hotel ID (defaults to demo hotel)"),
    months: int = Query(12, ge=1, le=24, description="Months to look back"),
):
    """Back-test the moments engine over historical weather."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail=f"Hotel not found: {hotel_id}")
    result = run_backtest(hotel, MOMENTS_SETTINGS, months, MOMENTS_DATA)
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])
    return result


# ---------- Import / file parsing ----------

IMPORT_SYSTEM_PROMPT = """You are a hotel data extractor. You receive the text content of a file uploaded by a hotel (Excel, CSV, Word, PDF, or plain text). The file may be in Italian or English, have messy formatting, merged cells, or multiple sections.

Extract ALL data you can find into these categories:
- rooms: Room types, counts, availability windows
- occupancy: Past occupancy data (dates, rooms sold, percentages)
- rates: Rate rules, seasonal pricing, minimum stays
- guests: Guest names, emails, phones, marketing consent. Include ALL guests in rows, with marketing_consent: true or false. The portal will filter server-side.
- amenities: Hotel amenities/facilities
- extras: Add-on services, packages

For each category found, return:
1. "category": one of the above category names
2. "rows": array of extracted row objects with consistent keys
3. "columns": ordered list of the keys used
4. "mappings": object mapping original column headers (as found in file) to your standardised keys
5. "problems": array of {message, count?} for issues found. BE SPECIFIC with counts:
   - For guests: count rows without marketing consent: {"message": "without marketing consent (will not be stored)", "count": N}
   - For guests: count rows with missing email: {"message": "missing email address", "count": N}
   - For guests: count rows with missing phone: {"message": "missing phone number", "count": N}
   - For occupancy/dates: count unreadable dates: {"message": "dates could not be read", "count": N}
   - For any section: count duplicate rows: {"message": "duplicate rows", "count": N}
   - For any section: count rows with missing required fields: {"message": "rows with missing required fields", "count": N}

IMPORTANT: Include every row from the file (do NOT silently drop rows). Set marketing_consent: false for guests without explicit consent. The server enforces consent filtering.

For the "rows_in_file" field: count the total data rows in the original file (excluding headers).

Return valid JSON: {"sections": [...], "problems": [...], "rows_in_file": N}
problems at top level = file-wide issues.
If no data found, return {"sections": [], "problems": [{"message": "No recognisable hotel data found"}], "rows_in_file": 0}"""

@api.post("/api/import/parse-file", tags=["Hotel tools"], dependencies=[Depends(require_hotel_api_key)])
async def api_import_parse(file: UploadFile = File(...), model: str | None = Query(None, description="Override AI model (e.g. claude-sonnet-4-20250514)")):
    """Parse an uploaded hotel file using Claude and return structured preview."""
    from local_events import ANTHROPIC_API_KEY as _ak

    if not _ak:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

    max_size = 10 * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_size:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("xlsx", "xls", "csv", "docx", "pdf", "txt"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

    # Convert file to text
    text = ""
    if ext == "csv":
        text = contents.decode("utf-8", errors="replace")
    elif ext == "txt":
        text = contents.decode("utf-8", errors="replace")
    elif ext in ("xlsx", "xls"):
        try:
            import openpyxl
            import io
            wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
            parts = []
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                parts.append(f"=== Sheet: {sheet_name} ===")
                for row in ws.iter_rows(values_only=True):
                    vals = [str(c) if c is not None else "" for c in row]
                    if any(v.strip() for v in vals):
                        parts.append("\t".join(vals))
            text = "\n".join(parts)
        except Exception as exc:
            _log.warning("openpyxl failed for %s: %s", file.filename, exc)
            raise HTTPException(status_code=400, detail=f"Could not read Excel file: {exc}")
    elif ext == "docx":
        try:
            import docx
            import io
            doc = docx.Document(io.BytesIO(contents))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            for table in doc.tables:
                for row in table.rows:
                    text += "\n" + "\t".join(cell.text for cell in row.cells)
        except Exception as exc:
            _log.warning("python-docx failed for %s: %s", file.filename, exc)
            raise HTTPException(status_code=400, detail=f"Could not read Word file: {exc}")
    elif ext == "pdf":
        try:
            import fitz  # PyMuPDF
            import io
            pdf = fitz.open(stream=contents, filetype="pdf")
            parts = []
            for page in pdf:
                parts.append(page.get_text())
            text = "\n".join(parts)
        except Exception as exc:
            _log.warning("PDF read failed for %s: %s", file.filename, exc)
            raise HTTPException(status_code=400, detail=f"Could not read PDF: {exc}")

    if not text.strip():
        return {"fileName": file.filename, "sections": [], "problems": [{"message": "File appears empty"}], "cost_usd": 0, "rows_in_file": 0}

    from local_events import _ask_claude
    import json as _json
    import csv as _csv
    import io as _io

    total_lines = len([l for l in text.split("\n") if l.strip()])

    def _clean_json(raw: str):
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        return _json.loads(cleaned)

    # -------- STRUCTURED FILES (CSV/Excel): two-phase approach --------
    # Phase 1: Parse file ourselves into rows
    # Phase 2: Send sample to Claude for mapping only, apply to all rows
    parsed_rows = None
    headers = None

    if ext == "csv":
        try:
            decoded = contents.decode("utf-8", errors="replace")
            dialect = _csv.Sniffer().sniff(decoded[:2000])
            reader = _csv.reader(_io.StringIO(decoded), dialect)
            all_rows = list(reader)
            if all_rows:
                headers = all_rows[0]
                parsed_rows = all_rows[1:]
        except Exception:
            pass

    elif ext in ("xlsx", "xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(_io.BytesIO(contents), data_only=True)
            # Use the first sheet with data for structured parsing
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                sheet_rows = []
                for row in ws.iter_rows(values_only=True):
                    vals = [str(c) if c is not None else "" for c in row]
                    if any(v.strip() for v in vals):
                        sheet_rows.append(vals)
                if sheet_rows:
                    if headers is None:
                        headers = sheet_rows[0]
                        parsed_rows = sheet_rows[1:]
                    else:
                        parsed_rows.extend(sheet_rows[1:])
        except Exception:
            pass

    if parsed_rows is not None and headers and len(parsed_rows) > 50:
        # Large structured file: use mapping-only prompt
        sample_size = min(30, len(parsed_rows))
        sample_text = "\t".join(headers) + "\n"
        for row in parsed_rows[:sample_size]:
            sample_text += "\t".join(row[:len(headers)]) + "\n"

        mapping_prompt = f"""You are a hotel data mapper. I have a structured file with {len(parsed_rows)} rows.
Here are the headers and first {sample_size} rows as a sample.

DO NOT return the row data — I already have all {len(parsed_rows)} rows.
Instead, return a mapping plan I can apply to every row programmatically.

Return valid JSON:
{{
  "category": "guests"|"occupancy"|"rates"|"rooms"|"amenities"|"extras",
  "column_mapping": {{"original_header": "standardised_key", ...}},
  "problems": [{{"message": "...", "count": N}}, ...],
  "consent_column": "header name that indicates marketing consent" or null,
  "consent_true_values": ["sì", "si", "yes", "true"] (values meaning consent given),
  "skip_columns": ["columns to ignore"]
}}

For guests: use keys: first_name, last_name, email, phone, city, stays, last_stay_date, marketing_consent, consent_date.
For occupancy: use keys: date, rooms_occupied, total_rooms, occupancy_pct, avg_revenue.
Examine the sample data to count problems (missing consent, missing emails, bad dates) and estimate for the full {len(parsed_rows)} rows.

File: {file.filename}
Headers: {headers}

Sample data:
{sample_text}"""

        raw = _ask_claude(IMPORT_SYSTEM_PROMPT, mapping_prompt, max_tokens=4000, model=model)
        est_tokens = (len(IMPORT_SYSTEM_PROMPT) + len(mapping_prompt)) // 4
        cost_usd = round(est_tokens * 0.25 / 1_000_000, 4)

        if raw is None:
            return {"fileName": file.filename, "sections": [], "problems": [{"message": "AI mapping failed"}], "cost_usd": cost_usd, "rows_in_file": len(parsed_rows)}

        try:
            mapping = _clean_json(raw)
        except _json.JSONDecodeError:
            return {"fileName": file.filename, "sections": [], "problems": [{"message": "AI returned invalid mapping"}], "cost_usd": cost_usd, "rows_in_file": len(parsed_rows)}

        col_map = mapping.get("column_mapping", {})
        category = mapping.get("category", "guests")
        problems = mapping.get("problems", [])

        # Build header index
        header_idx = {h: i for i, h in enumerate(headers)}

        # Apply mapping to all rows
        mapped_rows = []
        for row in parsed_rows:
            obj = {}
            for orig, mapped_key in col_map.items():
                idx = header_idx.get(orig)
                if idx is not None and idx < len(row):
                    val = row[idx].strip()
                    if mapped_key == "marketing_consent":
                        consent_vals = mapping.get("consent_true_values", ["sì", "si", "yes", "true"])
                        obj[mapped_key] = val.lower() in [v.lower() for v in consent_vals]
                    elif mapped_key == "stays":
                        try:
                            obj[mapped_key] = int(val) if val else 0
                        except ValueError:
                            obj[mapped_key] = 0
                    elif mapped_key in ("occupancy_pct", "avg_revenue", "rooms_occupied", "total_rooms"):
                        try:
                            obj[mapped_key] = float(val.replace(",", ".").replace("%", "")) if val else None
                        except ValueError:
                            obj[mapped_key] = None
                    else:
                        obj[mapped_key] = val if val else None
            if any(v for v in obj.values()):
                mapped_rows.append(obj)

        columns = list(col_map.values())
        orig_mappings = {v: v for v in col_map.values()}

        return {
            "fileName": file.filename,
            "sections": [{
                "category": category,
                "rows": mapped_rows,
                "columns": columns,
                "mappings": {orig: col_map[orig] for orig in col_map},
                "problems": problems,
            }],
            "problems": [],
            "cost_usd": cost_usd,
            "rows_in_file": len(parsed_rows),
            "rows_extracted": len(mapped_rows),
        }

    # -------- SMALL / UNSTRUCTURED FILES: full AI extraction --------
    small_limit = 50_000
    if len(text) > small_limit:
        text = text[:small_limit] + f"\n\n[... truncated from {total_lines} lines ...]"

    user_msg = f"File name: {file.filename}\n\n{text}"
    est_tokens = (len(IMPORT_SYSTEM_PROMPT) + len(user_msg)) // 4
    raw = _ask_claude(IMPORT_SYSTEM_PROMPT, user_msg, max_tokens=16000, model=model)
    cost_usd = round(est_tokens * 0.25 / 1_000_000, 4)

    if raw is None:
        return {"fileName": file.filename, "sections": [], "problems": [{"message": "AI could not extract structured data"}], "cost_usd": cost_usd, "rows_in_file": total_lines}

    try:
        result = _clean_json(raw)
    except _json.JSONDecodeError:
        _log.warning("Claude returned non-JSON for import: %s", raw[:200])
        return {"fileName": file.filename, "sections": [], "problems": [{"message": "AI could not extract structured data from this file"}], "cost_usd": cost_usd, "rows_in_file": total_lines}

    result["fileName"] = file.filename
    result["cost_usd"] = round(cost_usd, 4)
    result.setdefault("rows_in_file", total_lines)
    return result


# ---------- Import → Engine integration ----------

@api.post("/api/import/apply", tags=["Hotel tools"], dependencies=[Depends(require_hotel_api_key)])
def api_import_apply(body: dict):
    """Apply imported data to the engine's data files so it's used immediately."""
    hotel_id = body.get("hotel_id", "bristol-stresa")
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail=f"Hotel not found: {hotel_id}")

    sections = body.get("sections", [])
    applied = {}

    for section in sections:
        cat = section.get("category")
        rows = section.get("rows", [])
        if not rows:
            continue

        if cat == "occupancy":
            free_rooms_data = {}
            total_rooms = hotel.get("rooms", 85)
            for row in rows:
                d = row.get("date") or row.get("data")
                occupied = row.get("rooms_occupied") or row.get("camere_occupate")
                pct = row.get("occupancy_pct") or row.get("occupazione_pct")
                if d and occupied is not None:
                    try:
                        free = max(0, total_rooms - int(occupied))
                        free_rooms_data[str(d)] = free
                    except (ValueError, TypeError):
                        pass
                elif d and pct is not None:
                    try:
                        occ_rate = float(str(pct).replace("%", "").replace(",", ".")) / 100
                        free = max(0, total_rooms - round(total_rooms * occ_rate))
                        free_rooms_data[str(d)] = free
                    except (ValueError, TypeError):
                        pass

            if free_rooms_data:
                avail_path = MOMENTS_DATA / "availability.json"
                existing = load_json(avail_path)
                if existing.get("hotel_id") != hotel_id:
                    existing = {"hotel_id": hotel_id, "free_rooms": {}}
                existing.setdefault("free_rooms", {}).update(free_rooms_data)
                avail_path.write_text(json.dumps(existing, indent=2))
                applied["occupancy"] = len(free_rooms_data)

        elif cat == "rates":
            hotel_cfg_path = MOMENTS_DATA / "hotels.json"
            hotels_list = load_json(hotel_cfg_path)
            for h in hotels_list:
                if h["id"] == hotel_id:
                    for row in rows:
                        if "public_rate" in row or "public_rate_eur" in row:
                            try:
                                h["public_rate_eur"] = int(row.get("public_rate_eur") or row.get("public_rate"))
                            except (ValueError, TypeError):
                                pass
                        if "lowest_price" in row or "lowest_price_eur" in row:
                            try:
                                h["lowest_price_eur"] = int(row.get("lowest_price_eur") or row.get("lowest_price"))
                            except (ValueError, TypeError):
                                pass
                        if "max_discount_pct" in row:
                            try:
                                h["max_discount_pct"] = int(row["max_discount_pct"])
                            except (ValueError, TypeError):
                                pass
                    break
            hotel_cfg_path.write_text(json.dumps(hotels_list, indent=2))
            applied["rates"] = len(rows)

        elif cat == "extras":
            hotel_cfg_path = MOMENTS_DATA / "hotels.json"
            hotels_list = load_json(hotel_cfg_path)
            for h in hotels_list:
                if h["id"] == hotel_id:
                    existing_extras = {e["id"]: e for e in h.get("extras", [])}
                    for row in rows:
                        eid = row.get("id") or row.get("name", "").lower().replace(" ", "_")
                        if eid:
                            existing_extras[eid] = {
                                "id": eid,
                                "name": row.get("name", eid),
                                "value_to_guest": row.get("value_to_guest", 0),
                                "cost_to_hotel": row.get("cost_to_hotel", 0),
                                "unit": row.get("unit", "per_stay"),
                                "limit": row.get("limit", "unlimited"),
                                "segments": row.get("segments", []),
                            }
                    h["extras"] = list(existing_extras.values())
                    break
            hotel_cfg_path.write_text(json.dumps(hotels_list, indent=2))
            applied["extras"] = len(rows)

        elif cat == "rooms":
            hotel_cfg_path = MOMENTS_DATA / "hotels.json"
            hotels_list = load_json(hotel_cfg_path)
            for h in hotels_list:
                if h["id"] == hotel_id:
                    total = 0
                    room_types = []
                    for row in rows:
                        count = row.get("count") or row.get("rooms") or row.get("numero")
                        try:
                            total += int(count) if count else 0
                        except (ValueError, TypeError):
                            pass
                        room_types.append(row.get("type") or row.get("tipo") or "unknown")
                    if total > 0:
                        h["rooms"] = total
                    h["room_types"] = room_types
                    break
            hotel_cfg_path.write_text(json.dumps(hotels_list, indent=2))
            applied["rooms"] = len(rows)

    # Reload hotels in memory
    global MOMENTS_HOTELS, MOMENTS_HOTEL_BY_ID
    MOMENTS_HOTELS = load_json(MOMENTS_DATA / "hotels.json")
    MOMENTS_HOTEL_BY_ID = {h["id"]: h for h in MOMENTS_HOTELS}

    return {"applied": applied, "hotel_id": hotel_id}


# ---------- Inventory REST endpoints ----------

class CreateOfferRequest(BaseModel):
    hotel_id: str
    check_in: str
    nights: int
    rooms_allocated: int
    city_segments: list[dict]
    auto_waves: bool = False
    booking_rate: float = 0.03


@api.post("/api/hotel/inventory", tags=["Inventory"], dependencies=[Depends(require_hotel_api_key)])
def api_create_offer(req: CreateOfferRequest):
    """Create an offer with room allocation and wave plan. Wave 1 sends immediately (simulated)."""
    offer = inventory_store.create_offer(
        hotel_id=req.hotel_id,
        check_in=req.check_in,
        nights=req.nights,
        rooms_allocated=req.rooms_allocated,
        city_segments=req.city_segments,
        auto_waves=req.auto_waves,
        booking_rate=req.booking_rate,
    )
    return offer.to_dict()


@api.get("/api/hotel/inventory", tags=["Inventory"], dependencies=[Depends(require_hotel_api_key)])
def api_list_offers(hotel_id: str | None = Query(None, description="Filter by hotel")):
    """List all offers with their inventory and wave status."""
    return {"offers": inventory_store.list_offers(hotel_id)}


@api.get("/api/hotel/inventory/{offer_id}", tags=["Inventory"], dependencies=[Depends(require_hotel_api_key)])
def api_get_inventory(offer_id: str):
    """Get inventory and wave detail for one offer."""
    data = inventory_store.get_offer(offer_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Offer not found: {offer_id}")
    return data


class SendWaveRequest(BaseModel):
    extra_to_add: str | None = None


@api.post("/api/hotel/inventory/{offer_id}/wave", tags=["Inventory"], dependencies=[Depends(require_hotel_api_key)])
def api_send_wave(offer_id: str, req: SendWaveRequest | None = None):
    """Send the next wave for an offer (optionally add an extra, not more discount)."""
    result = inventory_store.send_next_wave(offer_id, extra_to_add=req.extra_to_add if req else None)
    if "error" in result:
        raise HTTPException(status_code=409, detail=result["error"])
    return result


class HoldRequest(BaseModel):
    guest_ref: str


@api.post("/api/hotel/inventory/{offer_id}/hold", tags=["Inventory"], dependencies=[Depends(require_hotel_api_key)])
def api_add_hold(offer_id: str, req: HoldRequest):
    """Place a 10-minute hold on a room at checkout."""
    result = inventory_store.add_hold(offer_id, req.guest_ref)
    if "error" in result:
        status = 410 if result.get("sold_out") else 404
        raise HTTPException(status_code=status, detail=result["error"])
    return result


class BookRequest(BaseModel):
    guest_ref: str


@api.post("/api/hotel/inventory/{offer_id}/book", tags=["Inventory"], dependencies=[Depends(require_hotel_api_key)])
def api_book_room(offer_id: str, req: BookRequest):
    """Confirm a booking (removes hold, increments booked count)."""
    result = inventory_store.book_room(offer_id, req.guest_ref)
    if "error" in result:
        status = 410 if result.get("sold_out") else 404
        raise HTTPException(status_code=status, detail=result["error"])
    return result


class NotifyRequest(BaseModel):
    email: str


@api.post("/api/hotel/inventory/{offer_id}/notify", tags=["Inventory"], dependencies=[Depends(require_hotel_api_key)])
def api_add_notify(offer_id: str, req: NotifyRequest):
    """Add an email to the sold-out waitlist."""
    result = inventory_store.add_to_notify(offer_id, req.email)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ---------- Calendar / Rules / Results endpoints ----------


@api.get("/api/hotel/calendar", tags=["Hotel tools"], dependencies=[Depends(require_hotel_api_key)])
def api_calendar(
    hotel_id: str | None = Query(None, description="Hotel ID"),
    year: int | None = Query(None),
    month: int | None = Query(None),
):
    """Per-day calendar data for a month: free rooms, events, offers, holidays."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail=f"Hotel not found: {hotel_id}")

    rome_now = datetime.now(ROME_TZ)
    y = year or rome_now.year
    m = month or rome_now.month
    first_day = date(y, m, 1)
    if m == 12:
        last_day = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(y, m + 1, 1) - timedelta(days=1)

    holidays_path = MOMENTS_DATA / "holidays.json"
    holidays_data = load_json(holidays_path) if holidays_path.exists() else {}
    events = get_approved_events(hotel, MOMENTS_DATA)
    blackout_set = set(hotel.get("blackout_dates", []))

    school_holidays = set()
    ponti = set()
    for sh in holidays_data.get("school_holidays", {}).values():
        sd = date.fromisoformat(sh["from"])
        ed = date.fromisoformat(sh["to"])
        d = sd
        while d <= ed:
            school_holidays.add(d.isoformat())
            d += timedelta(days=1)
    for p in holidays_data.get("ponti", []):
        sd = date.fromisoformat(p["from"])
        ed = date.fromisoformat(p["to"])
        d = sd
        while d <= ed:
            ponti.add(d.isoformat())
            d += timedelta(days=1)

    offers_by_date = {}
    all_offers = inventory_store.list_offers(hotel["id"])
    for off in all_offers:
        ci = date.fromisoformat(off["check_in"])
        for i in range(off["nights"]):
            d_str = (ci + timedelta(days=i)).isoformat()
            if d_str not in offers_by_date:
                offers_by_date[d_str] = []
            offers_by_date[d_str].append({
                "offer_id": off["offer_id"],
                "rooms_allocated": off["rooms_allocated"],
                "rooms_booked": off["rooms_booked"],
                "status": off["status"],
            })

    days = []
    d = first_day
    while d <= last_day:
        ds = d.isoformat()
        free = _free_rooms(hotel, d, holidays_data)

        day_events = []
        for ev in events:
            ev_start = ev.get("start_date", "")
            ev_end = ev.get("end_date", "")
            if ev_start <= ds <= ev_end:
                day_events.append({"name": ev["name"], "place": ev.get("place", "")})

        markers = []
        if ds in school_holidays:
            markers.append("school_holiday")
        if ds in ponti:
            markers.append("ponte")
        if d.weekday() >= 4:
            markers.append("weekend")
        if ds in offers_by_date:
            markers.append("offer_sent")

        days.append({
            "date": ds,
            "weekday": d.strftime("%a"),
            "free_rooms": free,
            "total_rooms": hotel["rooms"],
            "blocked": ds in blackout_set,
            "events": day_events,
            "offers": offers_by_date.get(ds, []),
            "markers": markers,
        })
        d += timedelta(days=1)

    return {
        "hotel_id": hotel["id"],
        "year": y,
        "month": m,
        "days": days,
    }


class RulesUpdate(BaseModel):
    public_rate_eur: int | None = None
    lowest_price_eur: int | None = None
    max_discount_pct: int | None = None
    max_rooms_per_offer: int | None = None
    blackout_dates: list[str] | None = None
    booking_window_days: list[int] | None = None
    offer_lifetime_hours: int | None = None
    contact_cooldown_days: int | None = None
    auto_send: bool | None = None
    auto_waves: bool | None = None


@api.get("/api/hotel/rules", tags=["Hotel tools"], dependencies=[Depends(require_hotel_api_key)])
def api_get_rules(
    hotel_id: str | None = Query(None),
):
    """Get editable rules for the hotel."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail=f"Hotel not found: {hotel_id}")
    return {
        "public_rate_eur": hotel.get("public_rate_eur", 280),
        "lowest_price_eur": hotel.get("lowest_price_eur", 210),
        "max_discount_pct": hotel.get("max_discount_pct", 25),
        "max_rooms_per_offer": hotel.get("max_rooms_per_offer", 6),
        "blackout_dates": hotel.get("blackout_dates", []),
        "booking_window_days": MOMENTS_SETTINGS.get("booking_window_days", [2, 14]),
        "offer_lifetime_hours": 48,
        "contact_cooldown_days": MOMENTS_SETTINGS.get("contact_cooldown_days", 7),
        "min_score_to_fire": MOMENTS_SETTINGS.get("min_score_to_fire", 0.50),
        "auto_send": False,
        "auto_waves": False,
        "demo": True,
    }


@api.put("/api/hotel/rules", tags=["Hotel tools"], dependencies=[Depends(require_hotel_api_key)])
def api_update_rules(
    hotel_id: str | None = Query(None),
    rules: RulesUpdate = None,
):
    """Update rules (saves to Postgres in production; in demo, updates in-memory)."""
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail=f"Hotel not found: {hotel_id}")
    if rules is None:
        raise HTTPException(status_code=400, detail="No rules provided")

    updated = {}
    if rules.public_rate_eur is not None:
        hotel["public_rate_eur"] = rules.public_rate_eur
        updated["public_rate_eur"] = rules.public_rate_eur
    if rules.lowest_price_eur is not None:
        hotel["lowest_price_eur"] = rules.lowest_price_eur
        updated["lowest_price_eur"] = rules.lowest_price_eur
    if rules.max_discount_pct is not None:
        hotel["max_discount_pct"] = rules.max_discount_pct
        updated["max_discount_pct"] = rules.max_discount_pct
    if rules.max_rooms_per_offer is not None:
        hotel["max_rooms_per_offer"] = rules.max_rooms_per_offer
        updated["max_rooms_per_offer"] = rules.max_rooms_per_offer
    if rules.blackout_dates is not None:
        hotel["blackout_dates"] = rules.blackout_dates
        updated["blackout_dates"] = rules.blackout_dates
    if rules.booking_window_days is not None:
        MOMENTS_SETTINGS["booking_window_days"] = rules.booking_window_days
        updated["booking_window_days"] = rules.booking_window_days
    if rules.contact_cooldown_days is not None:
        MOMENTS_SETTINGS["contact_cooldown_days"] = rules.contact_cooldown_days
        updated["contact_cooldown_days"] = rules.contact_cooldown_days

    return {"ok": True, "updated": updated, "demo": True}


@api.get("/api/hotel/results", tags=["Hotel tools"], dependencies=[Depends(require_hotel_api_key)])
def api_results(
    hotel_id: str | None = Query(None),
):
    """Aggregated results from offer actions + inventory for the Results tab."""
    import psycopg2
    hotel = _resolve_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail=f"Hotel not found: {hotel_id}")

    db_url = os.environ.get("DATABASE_URL", "")
    actions = []
    if db_url:
        try:
            conn = psycopg2.connect(db_url)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT action, "guestCity", "checkIn", nights, "roomsToOffer",
                           "publicPriceEur", "privatePriceEur", "discountPct",
                           "targetSegment", "segmentScore", "packageType",
                           inclusions, "extrasValue", "extrasCost",
                           holdback, "createdAt"
                    FROM public."OfferAction"
                    WHERE "hotelId" = %s
                    ORDER BY "createdAt" DESC
                """, (hotel["id"],))
                cols = [d[0] for d in cur.description]
                for row in cur.fetchall():
                    actions.append(dict(zip(cols, row)))
            conn.close()
        except Exception as e:
            _log.warning("Results query failed: %s", e)

    inventory_offers = inventory_store.list_offers(hotel["id"])

    sent = [a for a in actions if a["action"] == "approved" and not a.get("holdback")]
    holdback = [a for a in actions if a["action"] == "approved" and a.get("holdback")]
    skipped = [a for a in actions if a["action"] == "skipped"]

    sim_bookings = 0
    sim_revenue = 0.0
    for off in inventory_offers:
        sim_bookings += off.get("rooms_booked", 0)
        sim_revenue += off.get("rooms_booked", 0) * off.get("nights", 2) * hotel.get("public_rate_eur", 280) * 0.80

    holdback_bookings = max(1, round(sim_bookings * 0.1)) if holdback else 0
    holdback_revenue = holdback_bookings * 2 * hotel.get("public_rate_eur", 280) * 0.90 if holdback else 0

    commission_rate = 0.15

    by_segment: dict[str, dict] = {}
    by_city: dict[str, dict] = {}
    by_extra: dict[str, dict] = {}

    for off in inventory_offers:
        for w in off.get("waves", []):
            seg = w.get("segment") or "unknown"
            city = w.get("city") or "unknown"
            m = w.get("metrics", {})
            by_segment.setdefault(seg, {"sent": 0, "booked": 0})
            by_segment[seg]["sent"] += m.get("sent", 0)
            by_segment[seg]["booked"] += m.get("booked", 0)
            by_city.setdefault(city, {"sent": 0, "booked": 0})
            by_city[city]["sent"] += m.get("sent", 0)
            by_city[city]["booked"] += m.get("booked", 0)

    for a in sent:
        incl = a.get("inclusions") or []
        if isinstance(incl, list):
            for item in incl:
                by_extra.setdefault(item, {"count": 0})
                by_extra[item]["count"] += 1

    extra_labels = {
        "late_checkout": "Late check-out",
        "welcome_prosecco": "Welcome prosecco",
        "spa_day": "Spa day",
        "parking": "Parking",
        "kids_free": "Kids stay free",
        "four_for_three": "4-for-3 nights",
        "breakfast": "Breakfast included",
        "minibar": "Minibar",
        "room_upgrade": "Room upgrade",
    }
    by_extra_labeled = {}
    for key, info in by_extra.items():
        label = extra_labels.get(key, key.replace("_", " ").title())
        by_extra_labeled[label] = info

    return {
        "hotel_id": hotel["id"],
        "tiles": {
            "offers_sent": len(sent),
            "offers_skipped": len(skipped),
            "sim_bookings": sim_bookings,
            "sim_revenue": round(sim_revenue),
            "commission": round(sim_revenue * commission_rate),
            "holdback_bookings": holdback_bookings,
            "holdback_revenue": round(holdback_revenue),
            "uplift_pct": round(((sim_revenue / max(holdback_revenue, 1)) - 1) * 100) if holdback_revenue > 0 else None,
        },
        "inventory": inventory_offers,
        "by_segment": by_segment,
        "by_city": by_city,
        "by_package": by_extra_labeled,
        "total_actions": len(actions),
        "demo": True,
    }


# ========== STARTUP ==========

if __name__ == "__main__":
    if "--stdio" in sys.argv:
        mcp.run("stdio")
    else:
        host = os.environ.get("HOST", "127.0.0.1")
        public_host = os.environ.get("PUBLIC_HOST", "localhost")
        security = TransportSecuritySettings(
            allowed_origins=[
                f"https://{public_host}",
                "https://claude.ai",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
            ],
            allowed_hosts=[
                public_host,
                f"{public_host}:*",
                "localhost",
                "localhost:*",
                "127.0.0.1",
                "127.0.0.1:*",
            ],
        )

        combined = mcp.streamable_http_app(
            streamable_http_path="/mcp",
            transport_security=security,
        )
        combined.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        combined.mount("/", app=api)

        uvicorn.run(combined, host=host, port=int(os.environ.get("PORT", "8000")))
