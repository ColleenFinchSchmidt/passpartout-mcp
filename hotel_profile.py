"""Hotel profile: amenities, segment fit, and preferences.

Computes how well a hotel fits each guest segment based on its amenities
and the amenity_segment_fit table in settings.json.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def compute_hotel_segment_fit(hotel: dict, settings: dict) -> dict[str, float]:
    """Return a 0-1 fit score per segment for this hotel.

    Averages the amenity_segment_fit values for the hotel's amenities,
    then zeros out excluded segments and boosts wanted ones slightly.
    """
    amenity_fit = settings.get("amenity_segment_fit", {})
    segments = settings.get("segments", {})
    hotel_amenities = hotel.get("amenities", [])
    wanted = set(hotel.get("segments_wanted", []))
    excluded = set(hotel.get("segments_excluded", []))

    if not hotel_amenities or not amenity_fit:
        return {seg: 0.5 for seg in segments}

    totals = {seg: 0.0 for seg in segments}
    counts = {seg: 0 for seg in segments}

    for amenity in hotel_amenities:
        fits = amenity_fit.get(amenity, {})
        for seg in segments:
            if seg in fits:
                totals[seg] += fits[seg]
                counts[seg] += 1

    result = {}
    for seg in segments:
        if seg in excluded:
            result[seg] = 0.0
        elif counts[seg] > 0:
            avg = totals[seg] / counts[seg]
            if seg in wanted:
                avg = min(avg * 1.1, 1.0)
            result[seg] = round(avg, 2)
        else:
            result[seg] = 0.5

    return result
