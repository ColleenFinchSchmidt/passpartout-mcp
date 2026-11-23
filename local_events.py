"""AI agent for discovering local events near each hotel.

Reads official tourism pages and local news, then uses Claude to extract
structured event data. Results are stored in Postgres (with file fallback).

Requires ANTHROPIC_API_KEY environment variable.
"""

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import anthropic
import httpx

from events_db import save_events, load_events, get_discovered_at

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
if not ANTHROPIC_API_KEY.isascii():
    ANTHROPIC_API_KEY = ANTHROPIC_API_KEY.encode("ascii", errors="ignore").decode("ascii").strip()
ANTHROPIC_MODEL = "claude-haiku-5-5"

_http = httpx.Client(
    headers={"User-Agent": "passpartout-events/1.0"},
    timeout=30,
)


def _fetch_page_text(url: str, max_chars: int = 15000) -> str | None:
    try:
        resp = _http.get(url, follow_redirects=True)
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "pdf" in ct or "octet-stream" in ct:
            logger.warning("Skipping non-HTML content from %s", url[:80])
            return None
        text = resp.text
        if "<html" in text.lower()[:200]:
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url[:80], exc)
        return None


def _ask_claude(system: str, user: str) -> str | None:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4000,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        for block in message.content:
            if block.type == "text":
                return block.text
        return None
    except Exception as exc:
        logger.error("Claude API error (%s): %s", type(exc).__name__, exc)
        return None


TOURISM_URLS: dict[str, list[str]] = {
    "h-como-1": [
        "https://labreva.com/en/events",
        "https://www.menaggio.com/en/",
    ],
    "bristol-stresa": [
        "https://www.distrettolaghi.it/en/events",
        "https://www.distrettolaghi.it/it/eventi",
        "https://www.illagomaggiore.com/it/eventi/",
    ],
}

HOTEL_LOCATION_LABEL: dict[str, str] = {
    "h-como-1": "Lake Como",
    "bristol-stresa": "Lago Maggiore (Stresa)",
}

EXTRACTION_SYSTEM = """You extract local events from web page text for a hotel in {location}, Italy.

Return ONLY a JSON array of events. Each event:
{{
  "name": "Event name",
  "dates": {{"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}},
  "place": "Town or venue name",
  "distance_km": estimated km from the hotel,
  "category": "food" | "music" | "art" | "nature" | "market" | "sport" | "festival" | "light-show" | "experience" | "other",
  "who": "families" | "couples" | "everyone" | "food lovers" | etc.,
  "relevance": 0.0-1.0 (how likely to motivate a trip),
  "summary": "One sentence description"
}}

Only include events:
- Within 25km of the hotel (include the distance_km for each)
- In the next 3 months
- That a tourist would travel for
- Confirmed by the source page (do NOT invent events)

Return [] if no relevant events found. Return ONLY valid JSON, no other text."""


def _load_cached(hotel_id: str, data_dir: Path) -> dict | None:
    """Load from Postgres first, then fall back to file."""
    db_data = load_events(hotel_id)
    if db_data and db_data.get("events"):
        return db_data
    events_file = data_dir / f"local_events_{hotel_id}.json"
    if events_file.exists():
        try:
            return json.loads(events_file.read_text())
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _is_cache_fresh(hotel_id: str, data_dir: Path) -> bool:
    """Check if the cache (DB or file) was refreshed today."""
    db_date = get_discovered_at(hotel_id)
    if db_date and (date.today() - db_date).days < 1:
        return True
    events_file = data_dir / f"local_events_{hotel_id}.json"
    if events_file.exists():
        try:
            data = json.loads(events_file.read_text())
            discovered = data.get("discovered", "")
            if discovered and (date.today() - date.fromisoformat(discovered[:10])).days < 1:
                return True
        except (json.JSONDecodeError, ValueError):
            pass
    return False


def discover_events(hotel: dict, data_dir: Path, cache_only: bool = False) -> dict:
    """Discover local events for a specific hotel.

    Stores results in Postgres (with file fallback).
    cache_only=True returns saved data, never calls APIs.
    """
    hotel_id = hotel["id"]

    if cache_only:
        cached = _load_cached(hotel_id, data_dir)
        if cached and cached.get("events"):
            cached["_from_cache"] = True
            return cached
        return {"events": [], "_from_cache": True, "_empty": True,
                "note": "No cached data yet. Data refreshes automatically once a day."}

    if _is_cache_fresh(hotel_id, data_dir):
        cached = _load_cached(hotel_id, data_dir)
        if cached:
            cached["_from_cache"] = True
            return cached

    if not ANTHROPIC_API_KEY:
        return {
            "error": "ANTHROPIC_API_KEY not set. Set it in your environment to enable event discovery.",
            "cost_note": "Event discovery uses Claude Haiku — roughly $0.01-0.03 per hotel per run.",
        }

    urls = TOURISM_URLS.get(hotel_id, TOURISM_URLS.get("h-como-1", []))
    location = HOTEL_LOCATION_LABEL.get(hotel_id, hotel.get("town", "Italy"))

    all_text = []
    sources_fetched = []
    for url in urls:
        text = _fetch_page_text(url)
        if text:
            all_text.append(f"--- Source: {url} ---\n{text}")
            sources_fetched.append(url)

    if not all_text:
        return {"events": [], "note": "Could not fetch any tourism pages."}

    today = date.today()
    end = today + timedelta(days=90)
    system_prompt = EXTRACTION_SYSTEM.format(location=location)
    prompt = (
        f"Hotel: {hotel['name']} in {hotel.get('town', 'Varenna')}, {location}.\n"
        f"Hotel coordinates: {hotel.get('lat', 45.88)}, {hotel.get('lon', 8.53)}.\n"
        f"Today: {today.isoformat()}. Look for events between {today.isoformat()} and {end.isoformat()}.\n\n"
        + "\n\n".join(all_text)
    )

    response = _ask_claude(system_prompt, prompt)
    if not response:
        return {"events": [], "note": "Claude API call failed."}

    try:
        start = response.find("[")
        end_idx = response.rfind("]") + 1
        events = json.loads(response[start:end_idx])
    except (json.JSONDecodeError, ValueError):
        return {"events": [], "note": "Could not parse Claude response.", "raw": response[:500]}

    # Store in Postgres (never overwrites with empty)
    saved_to_db = save_events(hotel_id, events, sources_fetched)

    # Also write file as fallback
    result = {
        "hotel": hotel["name"],
        "hotel_id": hotel_id,
        "discovered": today.isoformat(),
        "events": events,
        "sources": sources_fetched,
    }
    try:
        events_file = data_dir / f"local_events_{hotel_id}.json"
        events_file.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Could not write events file for %s: %s", hotel_id, exc)

    logger.info("Discovered %d events for %s (db=%s)", len(events), hotel["name"], saved_to_db)
    return result


def get_approved_events(hotel: dict, data_dir: Path) -> list[dict]:
    """Return non-hidden events for a specific hotel."""
    cached = _load_cached(hotel["id"], data_dir)
    if not cached:
        return []
    return [e for e in cached.get("events", []) if not e.get("hidden", False)]
