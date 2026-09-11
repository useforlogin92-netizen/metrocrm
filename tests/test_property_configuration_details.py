from app.routers.property_submissions import _normalise_configuration_details


def test_configuration_details_support_multiple_entries_for_same_bhk():
    details = _normalise_configuration_details(
        ["1 BHK", "1 BHK", "2 BHK"],
        ["350", "400.45", "650"],
        ["12000", "12500", "14000"],
        ["4200000", "4900000", "9100000"],
        ["Yes", "No", "On Request"],
        ["Available", "Limited", "Available"],
        ["4", "2", "6"],
    )
    assert len(details) == 3
    assert details[0]["configuration"] == "1 BHK"
    assert details[1]["configuration"] == "1 BHK"
    assert details[1]["carpet_area"] == "400.45"
    assert details[2]["rate_per_sqft"] == "14000"
    assert details[1]["bundle_price"] == "4900000"
    assert details[2]["available_units"] == "6"


def test_configuration_details_ignore_blank_rows_but_keep_zero_values():
    details = _normalise_configuration_details(
        ["", "3 BHK"], ["", "1000"], ["", "15000"], ["", "15000000"], ["", "No"], ["", "Available"], ["", "0"]
    )
    assert len(details) == 1
    assert details[0]["configuration"] == "3 BHK"
    assert details[0]["available_units"] == "0"
