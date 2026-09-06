from app.services.caller_search import BHK_OPTIONS, JODI_OPTIONS, filter_and_rank_properties


def test_search_options_cover_bhk_jodi_and_possession_deadline():
    assert BHK_OPTIONS == ["1 BHK", "2 BHK", "3 BHK", "4 BHK", "5 BHK", "More"]
    assert "2+1" in JODI_OPTIONS
    assert "4+4" in JODI_OPTIONS


def test_caller_search_returns_multiple_matching_properties():
    properties = [
        {
            "id": "MALAD-2BHK-01",
            "city": "Mumbai",
            "station": "Malad",
            "side": "West",
            "bhk": "2 BHK",
            "price": 18_000_000,
            "construction_status": "Under Construction",
            "possession_date": "2028-06-30",
        },
        {
            "id": "GOREGAON-2BHK-01",
            "city": "Mumbai",
            "station": "Goregaon",
            "side": "West",
            "bhk": "2 BHK",
            "price": 19_000_000,
            "construction_status": "Ready to Move",
            "possession_date": "2026-01-01",
        },
        {
            "id": "ANDHERI-2BHK-01",
            "city": "Mumbai",
            "station": "Andheri",
            "side": "East",
            "bhk": "2 BHK",
            "price": 20_000_000,
            "construction_status": "Under Construction",
            "possession_date": "2028-12-31",
        },
        {
            "id": "BANDRA-2BHK-01",
            "city": "Mumbai",
            "station": "Bandra",
            "side": "West",
            "bhk": "2 BHK",
            "price": 19_000_000,
            "construction_status": "Ready to Move",
            "possession_date": "2026-01-01",
        },
    ]
    filters = {
        "city": "Mumbai",
        "mumbai_station_from": "Malad",
        "mumbai_station_to": "Andheri",
        "mumbai_side": "Both",
        "bhk": ["2 BHK"],
        "budget_min": 15_000_000,
        "budget_max": 21_000_000,
        "construction_statuses": ["Under Construction", "Ready to Move"],
        "possession_by": 2028,
    }
    results = filter_and_rank_properties(filters, properties)
    ids = {result.property_id for result in results}
    assert {"MALAD-2BHK-01", "GOREGAON-2BHK-01", "ANDHERI-2BHK-01"} <= ids
    assert "BANDRA-2BHK-01" not in ids
