from app.location_catalog import mumbai_station_range_matches
from app.services.matching import rank_properties


def test_mumbai_malad_to_andheri_includes_all_intermediate_stations():
    customer = {
        "city": "Mumbai",
        "mumbai_station_from": "Malad",
        "mumbai_station_to": "Andheri",
        "mumbai_side": "Both",
        "bhk": "2",
        "budget_min": 100,
        "budget_max": 200,
    }
    properties = [
        {"id": 1, "city": "Mumbai", "station": "Malad", "side": "West", "bhk": "2", "price": 150},
        {"id": 2, "city": "Mumbai", "station": "Goregaon", "side": "East", "bhk": "2", "price": 150},
        {"id": 3, "city": "Mumbai", "station": "Andheri", "side": "West", "bhk": "2", "price": 150},
        {"id": 4, "city": "Mumbai", "station": "Bandra", "side": "West", "bhk": "2", "price": 150},
    ]
    ranked = rank_properties(customer, properties, minimum_score=70)
    assert [item.property_id for item in ranked] == [1, 2, 3]


def test_mumbai_side_filter_is_east_or_west_or_both():
    assert mumbai_station_range_matches(property_station="Malad", from_station="Malad", to_station="Andheri", side="East", property_side="East")
    assert not mumbai_station_range_matches(property_station="Malad", from_station="Malad", to_station="Andheri", side="East", property_side="West")
    assert mumbai_station_range_matches(property_station="Malad", from_station="Malad", to_station="Andheri", side="Both", property_side="West")


def test_multiple_locations_are_supported():
    customer = {"city": "Mumbai", "preferred_locations": ["Borivali", "Malad", "Andheri"], "bhk": "2"}
    properties = [
        {"id": 1, "city": "Mumbai", "locality": "Borivali West", "bhk": "2"},
        {"id": 2, "city": "Mumbai", "locality": "Malad East", "bhk": "2"},
        {"id": 3, "city": "Mumbai", "locality": "Powai", "bhk": "2"},
    ]
    ranked = rank_properties(customer, properties, minimum_score=40)
    assert {item.property_id for item in ranked} == {1, 2}
