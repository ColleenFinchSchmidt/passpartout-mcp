"""AI agent for discovering local events near each hotel.

Reads official tourism pages and local news, then uses Claude to extract
structured event data. Results are saved for the hotel to approve or hide.

Requires ANTHROPIC_API_KEY environment variable.
"""

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
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
        resp = _http.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 4000,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        for block in data["content"]:
            if block.get("type") == "text":
                return block["text"]
        return None
    except Exception as exc:
        logger.error("Claude API error: %s", exc)
        return None


TOURISM_URLS = {
    "varenna": [
        "https://labreva.com/en/events",
        "https://www.menaggio.com/en/",
    ],
    "bellagio": [
        "https://labreva.com/en/events",
        "https://www.menaggio.com/en/",
    ],
}

EXTRACTION_SYSTEM = """You extract local events from web page text for a hotel near Lake Como, Italy.

Return ONLY a JSON array of events. Each event:
{
  "name": "Event name",
  "dates": {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"},
  "place": "Town or venue",
  "distance_km": estimated km from the hotel,
  "category": "food" | "music" | "art" | "nature" | "market" | "sport" | "festival" | "other",
  "who": "families" | "couples" | "everyone" | "food lovers" | etc.,
  "relevance": 0.0-1.0 (how likely to motivate a trip),
  "summary": "One sentence description"
}

Only include events:
- Within 30km of the hotel
- In the next 3 months
- That a tourist would travel for

Return [] if no relevant events found. Return ONLY valid JSON, no other text."""


def discover_events(hotel: dict, data_dir: Path) -> dict:
    if not ANTHROPIC_API_KEY:
        return {
            "error": "ANTHROPIC_API_KEY not set. Set it in your environment to enable event discovery.",
            "cost_note": "Event discovery uses Claude Sonnet — roughly $0.01-0.03 per hotel per run.",
        }

    town = hotel.get("town", "").lower()
    urls = TOURISM_URLS.get(town, TOURISM_URLS.get("varenna", []))

    all_text = []
    for url in urls:
        text = _fetch_page_text(url)
        if text:
            all_text.append(f"--- Source: {url} ---\n{text}")

    if not all_text:
        return {"events": [], "note": "Could not fetch any tourism pages."}

    today = date.today()
    end = today + timedelta(days=90)
    prompt = (
        f"Hotel: {hotel['name']} in {hotel.get('town', 'Varenna')}, Lake Como.\n"
        f"Today: {today.isoformat()}. Look for events between {today.isoformat()} and {end.isoformat()}.\n\n"
        + "\n\n".join(all_text)
    )

    response = _ask_claude(EXTRACTION_SYSTEM, prompt)
    if not response:
        return {"events": [], "note": "Claude API call failed."}

    try:
        start = response.find("[")
        end_idx = response.rfind("]") + 1
        events = json.loads(response[start:end_idx])
    except (json.JSONDecodeError, ValueError):
        return {"events": [], "note": "Could not parse Claude response.", "raw": response[:500]}

    result = {
        "hotel": hotel["name"],
        "discovered": today.isoformat(),
        "events": events,
        "sources": urls,
    }

    events_file = data_dir / "local_events.json"
    events_file.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    logger.info("Discovered %d events for %s", len(events), hotel["name"])

    return result


def get_approved_events(data_dir: Path) -> list[dict]:
    events_file = data_dir / "local_events.json"
    if not events_file.exists():
        return []
    data = json.loads(events_file.read_text())
    return [e for e in data.get("events", []) if not e.get("hidden", False)]
