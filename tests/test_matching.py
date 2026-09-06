from app.services.matching import rank_properties, score_match


def test_exact_match_scores_all_supported_dimensions():
    customer = {
        "preferred_locations": ["Andheri"],
        "budget_min": 100,
        "budget_max": 200,
        "bhk": "2",
        "property_type": "Apartment",
        "carpet_area_min": 700,
        "carpet_area_max": 900,
        "possession_requirement": "Ready to Move",
    }
    property_ = {
        "id": 7,
        "location": "Andheri West",
        "price": 150,
        "bhk": "2",
        "property_type": "Apartment",
        "carpet_area": 800,
        "possession": "Ready to Move",
    }
    result = score_match(customer, property_)
    assert result.property_id == 7
    assert result.score == 100
    assert set(result.reasons) == {
        "location:location", "budget", "bhk", "property_type", "area", "possession"
    }


def test_rank_properties_orders_best_first_and_filters():
    customer = {"preferred_locations": ["Borivali"], "budget_min": 100, "budget_max": 200, "bhk": "2"}
    properties = [
        {"id": 2, "location": "Borivali", "price": 150, "bhk": "2"},
        {"id": 1, "location": "Borivali", "price": 150, "bhk": "3"},
        {"id": 3, "location": "Thane", "price": 150, "bhk": "2"},
    ]
    ranked = rank_properties(customer, properties, minimum_score=60)
    assert [item.property_id for item in ranked] == [2]


def test_pin_is_stronger_than_broader_city_match():
    customer = {"state": "Maharashtra", "city": "Mumbai", "pincodes": ["400053"]}
    exact_pin = {"id": 10, "state": "Maharashtra", "city": "Mumbai", "pincode": "400053"}
    same_city = {"id": 11, "state": "Maharashtra", "city": "Mumbai", "pincode": "400070"}
    exact = score_match(customer, exact_pin)
    broader = score_match(customer, same_city)
    assert exact.score > broader.score
    assert exact.location_level == "pincode"


def test_mumbai_priority_breaks_equal_score_ties():
    customer = {"state": "Maharashtra", "city": "Pune", "budget_min": 100, "budget_max": 200}
    properties = [
        {"id": 20, "state": "Maharashtra", "city": "Mumbai", "price": 150},
        {"id": 21, "state": "Maharashtra", "city": "Pune", "price": 150},
    ]
    ranked = rank_properties(customer, properties, minimum_score=10)
    assert [item.property_id for item in ranked] == [21, 20]
