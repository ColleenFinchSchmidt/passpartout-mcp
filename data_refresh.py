"""Auto-generate holidays.json from public data sources.

Replaces hand-written holiday/ponti/school-calendar data with:
  - Italian public holidays from the `holidays` Python package (includes Easter)
  - Auto-calculated ponti (bridge days) from holiday placement
  - Regional school calendars (hard-coded per region, updated yearly)
"""

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import holidays as holidays_lib

logger = logging.getLogger(__name__)


def _italian_holidays(years: list[int]) -> list[dict]:
    it = holidays_lib.Italy(years=years)
    return [
        {"date": d.isoformat(), "name": name}
        for d, name in sorted(it.items())
    ]


def _calculate_ponti(public_holidays: list[dict]) -> list[dict]:
    ponti = []
    holiday_dates = {h["date"]: h["name"] for h in public_holidays}

    for h in public_holidays:
        d = date.fromisoformat(h["date"])
        dow = d.weekday()
        name = h["name"]

        if dow == 3:  # Thursday → Friday is ponte
            fri = d + timedelta(days=1)
            if fri.isoformat() not in holiday_dates:
                ponti.append({
                    "from": d.isoformat(),
                    "to": (d + timedelta(days=3)).isoformat(),
                    "name": f"Ponte {name} (Thu–Sun)",
                })

        elif dow == 1:  # Tuesday → Monday is ponte
            mon = d - timedelta(days=1)
            if mon.isoformat() not in holiday_dates:
                ponti.append({
                    "from": (d - timedelta(days=2)).isoformat(),
                    "to": d.isoformat(),
                    "name": f"Ponte {name} (Sat–Tue)",
                })

    return ponti


SCHOOL_CALENDARS = {
    "lombardy": {
        "2025-2026": {
            "christmas_break": {"from": "2025-12-23", "to": "2026-01-06"},
            "carnival_break": {"from": "2026-02-14", "to": "2026-02-18"},
            "easter_break": {"from": "2026-04-02", "to": "2026-04-07"},
            "summer_break": {"from": "2026-06-08", "to": "2026-09-13"},
        },
        "2026-2027": {
            "christmas_break": {"from": "2026-12-23", "to": "2027-01-06"},
            "carnival_break": {"from": "2027-02-13", "to": "2027-02-17"},
            "easter_break": {"from": "2027-03-25", "to": "2027-03-30"},
            "summer_break": {"from": "2027-06-08", "to": "2027-09-13"},
        },
    },
    "piedmont": {
        "2025-2026": {
            "christmas_break": {"from": "2025-12-22", "to": "2026-01-06"},
            "carnival_break": {"from": "2026-02-14", "to": "2026-02-18"},
            "easter_break": {"from": "2026-04-02", "to": "2026-04-07"},
            "summer_break": {"from": "2026-06-10", "to": "2026-09-13"},
        },
        "2026-2027": {
            "christmas_break": {"from": "2026-12-23", "to": "2027-01-06"},
            "carnival_break": {"from": "2027-02-13", "to": "2027-02-17"},
            "easter_break": {"from": "2027-03-25", "to": "2027-03-30"},
            "summer_break": {"from": "2027-06-10", "to": "2027-09-13"},
        },
    },
}


def _school_holidays_for_period(start: date, end: date,
                                regions: list[str] = None) -> dict:
    regions = regions or ["lombardy", "piedmont"]
    merged: dict[str, dict] = {}

    for region in regions:
        cal = SCHOOL_CALENDARS.get(region, {})
        for year_key, periods in cal.items():
            for period_name, span in periods.items():
                pfrom = date.fromisoformat(span["from"])
                pto = date.fromisoformat(span["to"])
                if pto < start or pfrom > end:
                    continue
                key = f"{period_name}_{year_key}"
                if key not in merged:
                    merged[key] = {
                        "from": max(pfrom, start).isoformat(),
                        "to": min(pto, end).isoformat(),
                    }
                else:
                    existing_from = date.fromisoformat(merged[key]["from"])
                    existing_to = date.fromisoformat(merged[key]["to"])
                    merged[key] = {
                        "from": min(existing_from, max(pfrom, start)).isoformat(),
                        "to": max(existing_to, min(pto, end)).isoformat(),
                    }

    return merged


def refresh_holidays(data_dir: Path, months_ahead: int = 18) -> dict:
    today = date.today()
    start = today - timedelta(days=365)
    end = today + timedelta(days=months_ahead * 30)

    years = list(range(start.year, end.year + 1))
    public = _italian_holidays(years)
    ponti = _calculate_ponti(public)
    school = _school_holidays_for_period(start, end)

    data = {
        "_generated": today.isoformat(),
        "_source": "holidays Python package + auto-calculated ponti + regional school calendars",
        "public_holidays": public,
        "ponti": ponti,
        "school_holidays": school,
    }

    out = data_dir / "holidays.json"
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    logger.info("Refreshed %s: %d holidays, %d ponti, %d school periods",
                out, len(public), len(ponti), len(school))
    return data
