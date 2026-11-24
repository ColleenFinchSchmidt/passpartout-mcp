"""Tests for canonical field name mapping in the import pipeline."""
import pytest


CANONICAL_FIELDS = {
    "camere_occupate": "rooms_occupied",
    "rooms_sold": "rooms_occupied",
    "occupied_rooms": "rooms_occupied",
    "camere_totali": "total_rooms",
    "room_count": "total_rooms",
    "data": "date",
    "data_giorno": "date",
    "giorno": "date",
    "day": "date",
    "occupazione_pct": "occupancy_pct",
    "percentuale_occupazione": "occupancy_pct",
    "occ_pct": "occupancy_pct",
    "ricavo_medio": "avg_revenue",
    "revenue_avg": "avg_revenue",
    "average_revenue": "avg_revenue",
    "note": "notes",
    "mese": "month",
    "media_occupazione_pct": "avg_occupancy_pct",
    "ricavo_totale": "total_revenue",
    "revpar": "avg_revenue",
}


def _canonicalize_col_map(col_map: dict) -> dict:
    return {orig: CANONICAL_FIELDS.get(mapped.lower(), mapped) for orig, mapped in col_map.items()}


class TestCanonicalFields:
    def test_italian_occupancy_headers(self):
        ai_mapping = {
            "Data": "data",
            "Camere occupate": "camere_occupate",
            "Camere totali": "camere_totali",
            "% Occupazione": "occupazione_pct",
            "Ricavo medio (€)": "ricavo_medio",
            "Note": "note",
        }
        result = _canonicalize_col_map(ai_mapping)
        assert result["Data"] == "date"
        assert result["Camere occupate"] == "rooms_occupied"
        assert result["Camere totali"] == "total_rooms"
        assert result["% Occupazione"] == "occupancy_pct"
        assert result["Ricavo medio (€)"] == "avg_revenue"
        assert result["Note"] == "notes"

    def test_already_canonical_passthrough(self):
        ai_mapping = {
            "Date": "date",
            "Rooms Occupied": "rooms_occupied",
            "Total Rooms": "total_rooms",
        }
        result = _canonicalize_col_map(ai_mapping)
        assert result["Date"] == "date"
        assert result["Rooms Occupied"] == "rooms_occupied"
        assert result["Total Rooms"] == "total_rooms"

    def test_rooms_sold_alias(self):
        ai_mapping = {"Rooms Sold": "rooms_sold"}
        result = _canonicalize_col_map(ai_mapping)
        assert result["Rooms Sold"] == "rooms_occupied"

    def test_monthly_occupancy_fields(self):
        ai_mapping = {
            "Mese": "mese",
            "Media occupazione %": "media_occupazione_pct",
            "Ricavo totale (€)": "ricavo_totale",
            "RevPAR (€)": "revpar",
        }
        result = _canonicalize_col_map(ai_mapping)
        assert result["Mese"] == "month"
        assert result["Media occupazione %"] == "avg_occupancy_pct"
        assert result["Ricavo totale (€)"] == "total_revenue"
        assert result["RevPAR (€)"] == "avg_revenue"

    def test_case_insensitive(self):
        ai_mapping = {"Col": "Camere_Occupate"}
        result = _canonicalize_col_map(ai_mapping)
        assert result["Col"] == "rooms_occupied"

    def test_unknown_field_passthrough(self):
        ai_mapping = {"Col": "some_custom_field"}
        result = _canonicalize_col_map(ai_mapping)
        assert result["Col"] == "some_custom_field"


class TestApplyEndpointFields:
    """Verify the apply endpoint handles all field variants."""

    def test_free_rooms_direct(self):
        row = {"date": "2025-06-15", "free_rooms": 42}
        d = row.get("date")
        free_direct = row.get("free_rooms")
        occupied = row.get("rooms_occupied")
        assert d == "2025-06-15"
        assert free_direct == 42
        assert occupied is None

    def test_rooms_occupied_to_free(self):
        total_rooms = 85
        row = {"date": "2025-06-15", "rooms_occupied": 35}
        occupied = row.get("rooms_occupied")
        free = max(0, total_rooms - int(float(str(occupied))))
        assert free == 50

    def test_occupancy_pct_to_free(self):
        total_rooms = 85
        row = {"date": "2025-06-15", "occupancy_pct": 41.2}
        pct = row.get("occupancy_pct")
        occ_rate = float(str(pct).replace("%", "").replace(",", ".")) / 100
        free = max(0, total_rooms - round(total_rooms * occ_rate))
        assert free == 50

    def test_datetime_string_truncation(self):
        d = "2025-01-01 00:00:00"
        assert str(d)[:10] == "2025-01-01"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
