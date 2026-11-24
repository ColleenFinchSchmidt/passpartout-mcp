"""Generate headline themes and plain-language reasons per city×segment.

Calls Claude Haiku once per suggestion, caches by signal hash.
"""

import hashlib
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = "claude-haiku-5-5"

_theme_cache: dict[str, tuple[float, dict]] = {}
_THEME_TTL = 7200  # 2 hours


def _cache_key(hotel_id: str, check_in: str, cities: list[str],
               segments: list[str], signal_summary: str) -> str:
    raw = f"{hotel_id}|{check_in}|{','.join(sorted(cities))}|{','.join(sorted(segments))}|{signal_summary}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _ask_claude(system: str, user: str) -> str | None:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
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
        logger.warning("Theme generation failed: %s", exc)
        return None


THEME_SYSTEM = """You write short marketing copy for a hotel's private flash-sale offers.
Given a hotel, the target city, a guest segment, and the signals that triggered the offer,
write a punchy headline theme and 2-3 short reasons — in English and Italian.

Rules:
- The theme is 3-7 words, evocative, specific to this segment and these signals.
  Examples: "Lights on the lake", "Swap smog for lake air", "Christmas on the lakefront",
  "Quiet lake before the holidays", "Spa weekend while Milan shivers".
- PRIORITY: When events are listed (festivals, markets, lights, exhibitions), the theme MUST
  reference the strongest event by name or concept. Events always beat air quality or haze as
  the lead signal. Only fall back to weather/air themes when no events are active.
- "Spa escape" only when rain/bad weather at the hotel is the top signal AND no events.
- Reasons are 1 sentence each, plain language, factual. No scores, no "AQI", no "penalty".
  The first reason should mention the strongest event by name when one exists.
  Mention weather conditions naturally as supporting reasons, not leads.
- "Also on" items (theatre seasons, dance seasons, long-running programmes) are background
  context ONLY. Never use them as a headline theme or as a main reason. They may appear in
  an "also on" aside at most, never as the lead.
- Italian translations should be natural, not literal.

Return ONLY valid JSON, no other text:
{
  "rows": {
    "<city>|<segment>": {
      "theme_en": "...",
      "theme_it": "...",
      "reasons_en": ["...", "..."],
      "reasons_it": ["...", "..."]
    }
  }
}"""


def generate_themes(
    hotel_name: str,
    hotel_id: str,
    hotel_town: str,
    check_in: str,
    nights: int,
    cities: list[str],
    segments: list[dict],
    reasons: list[str],
    also_on: list[str],
    event_sources: list[dict],
    source_scores: dict,
) -> dict:
    """Generate themed copy for each city×segment row.

    Returns {"<city>|<segment>": {"theme_en": ..., "theme_it": ..., ...}}
    """
    seg_keys = [s["segment"] for s in segments]
    signal_summary = "|".join(sorted(reasons[:6]))
    key = _cache_key(hotel_id, check_in, cities, seg_keys, signal_summary)

    now = time.time()
    if key in _theme_cache and (now - _theme_cache[key][0]) < _THEME_TTL:
        return _theme_cache[key][1]

    events_text = ""
    if event_sources:
        events_text = "Active events (use these for themes and reasons): " + ", ".join(
            f"{e['name']} ({e.get('place', '')})" for e in event_sources[:8]
        )
    if also_on:
        events_text += "\nAlso on (background only — do NOT use as theme or reason): " + ", ".join(also_on[:6])

    prompt = f"""Hotel: {hotel_name} in {hotel_town}
Stay: {check_in}, {nights} nights
Target cities: {', '.join(cities)}
Segments: {', '.join(f"{s['segment']} ({s['label']})" for s in segments)}

{events_text if events_text else "No local events during this stay."}

Other signals:
{chr(10).join(f'- {r}' for r in reasons)}

Source scores: weather={source_scores.get('weather', 0)}, air={source_scores.get('air_quality', 0)}, seasonal={source_scores.get('seasonal', 0)}, holiday={source_scores.get('holiday', 0)}

Generate themes for each city × segment combination. If events are listed above, the theme must reference them."""

    response = _ask_claude(THEME_SYSTEM, prompt)
    if not response:
        result = _fallback_themes(cities, segments, reasons, hotel_town)
        _theme_cache[key] = (now, result)
        return result

    try:
        import re
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```\w*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        data = json.loads(cleaned)
        result = data.get("rows", data)
        _theme_cache[key] = (now, result)
        return result
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Theme JSON parse failed: %s — raw[:200]: %s", exc, (response or "")[:200])
        result = _fallback_themes(cities, segments, reasons, hotel_town)
        _theme_cache[key] = (now, result)
        return result


def _fallback_themes(cities: list[str], segments: list[dict],
                     reasons: list[str], hotel_town: str) -> dict:
    """Non-Claude fallback: clean up raw reasons into plain language."""
    result = {}
    clean_reasons = []
    for r in reasons[:3]:
        clean = r.replace(" — penalty applied", "").replace(" — reduced penalty", "")
        clean = clean.replace(" — fresh lake air awaits", "")
        if "EU AQI" in clean:
            clean = clean.split("(")[0].strip()
        if "µg/m³" in clean:
            clean = clean.split("(")[0].strip()
        clean_reasons.append(clean)

    for city in cities:
        for seg in segments:
            key = f"{city}|{seg['segment']}"
            result[key] = {
                "theme_en": f"Escape to {hotel_town}",
                "theme_it": f"Fuga a {hotel_town}",
                "reasons_en": clean_reasons[:3] if clean_reasons else [f"Get away to {hotel_town}"],
                "reasons_it": clean_reasons[:3] if clean_reasons else [f"Una fuga a {hotel_town}"],
            }
    return result
