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
        "location", "budget", "bhk", "property_type", "area", "possession"
    }


def test_rank_properties_orders_best_first_and_filters():
    customer = {"preferred_locations": ["Borivali"], "budget_min": 100, "budget_max": 200, "bhk": "2"}
    properties = [
        {"id": 2, "location": "Borivali", "price": 150, "bhk": "2"},
        {"id": 1, "location": "Borivali", "price": 150, "bhk": "3"},
        {"id": 3, "location": "Thane", "price": 150, "bhk": "2"},
    ]
    ranked = rank_properties(customer, properties, minimum_score=40)
    assert [item.property_id for item in ranked] == [2]
