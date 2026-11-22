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
import os
import sys
from datetime import date, timedelta

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, EmailStr

from data import DEMO_MEMBER_CODE, HOTELS, MOMENTS, OFFERS

# ---------- shared state ----------

HOTEL_BY_ID = {h["id"]: h for h in HOTELS}
OFFER_BY_ID = {o["id"]: o for o in OFFERS}
BOOKINGS: dict[str, dict] = {}


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
    return {
        "offer_id": offer["id"],
        "title": offer["title"],
        "hotel": hotel["name"],
        "town": hotel["town"],
        "why_now": offer["trigger"],
        "includes": offer["includes"],
        "travel_from_" + from_city.lower(): _travel(hotel, from_city),
        "nights": nights,
        "price": _price(offer, hotel, nights, member),
    }


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
        "Passpartout finds private hotel offers within a short car or train ride of the "
        "traveller's city, triggered by moments (weather, events, empty dates). "
        "Public prices show added value only; the real discount is shown only to members. "
        "Always say this is a demo with fictional hotels."
    ),
)


@mcp.tool()
def current_moments(city: str = "Milan") -> dict:
    """What's happening now that makes a short getaway from this city a good idea
    (weather, events, empty dates). Simulated in the demo."""
    return {"city": city, "moments": MOMENTS.get(city, []), "demo": True}


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
    """What's happening now that triggers getaway offers from this city."""
    return {"city": city, "moments": MOMENTS.get(city, []), "demo": True}


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


# ========== STARTUP ==========

if __name__ == "__main__":
    if "--stdio" in sys.argv:
        mcp.run("stdio")
    else:
        public_host = os.environ.get("PUBLIC_HOST")
        host = os.environ.get("HOST", "127.0.0.1")
        security = (
            TransportSecuritySettings(allowed_hosts=[public_host, f"{public_host}:*"])
            if public_host else None
        )

        mcp_app = mcp.streamable_http_app(
            streamable_http_path="/mcp",
            transport_security=security,
            host=host,
        )
        api.mount("/mcp", mcp_app.routes[0].app)

        uvicorn.run(api, host=host, port=int(os.environ.get("PORT", "8000")))
