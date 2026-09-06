from app.services.matching import score_match
from app.services.search_options import BHK_OPTIONS, JODI_OPTIONS, POSSESSION_YEARS, search_option_catalog


def test_search_options_cover_all_bhk_and_jodi():
    assert BHK_OPTIONS == ("1 BHK", "2 BHK", "3 BHK", "4 BHK", "5 BHK", "More than 5 BHK")
    assert "2+1" in JODI_OPTIONS
    assert "2+2" in JODI_OPTIONS
    assert "5+5" in JODI_OPTIONS


def test_possession_years_are_available_through_2050():
    assert POSSESSION_YEARS[0] >= 2026
    assert POSSESSION_YEARS[-1] == 2050
    assert 2026 in search_option_catalog()["possession_year"]
    assert 2028 in search_option_catalog()["possession_year"]
    assert 2050 in search_option_catalog()["possession_year"]


def test_multiple_bhk_and_jodi_configurations_match():
    customer = {"bhk": ["2 BHK", "3 BHK", "2+1"]}
    assert "bhk" in score_match(customer, {"id": 1, "bhk": "2 BHK"}).reasons
    assert "bhk" in score_match(customer, {"id": 2, "bhk": "2+1"}).reasons
    assert "bhk" not in score_match(customer, {"id": 3, "bhk": "4 BHK"}).reasons


def test_possession_by_year_matches_any_earlier_or_equal_year():
    customer = {"possession_by": 2028}
    assert "possession" in score_match(customer, {"id": 1, "possession_date": "2027-12-31"}).reasons
    assert "possession" in score_match(customer, {"id": 2, "possession_date": "2028-06-30"}).reasons
    assert "possession" not in score_match(customer, {"id": 3, "possession_date": "2029-01-01"}).reasons


def test_status_and_possession_year_are_both_filters_when_both_selected():
    customer = {"construction_statuses": ["Under Construction", "Ready to Move"], "possession_by": 2028}
    assert "possession" in score_match(customer, {"id": 1, "construction_status": "Under Construction", "rera_possession_date": "2028-10-01"}).reasons
    assert "possession" not in score_match(customer, {"id": 2, "construction_status": "Under Construction", "rera_possession_date": "2029-10-01"}).reasons
    assert "possession" not in score_match(customer, {"id": 3, "construction_status": "Upcoming", "rera_possession_date": "2028-01-01"}).reasons
