import pytest

from app.routers.sales_property import _configuration_unit_number, _parse_parking, _parse_variants


def test_multiple_same_bhk_rows_and_multiple_bhk_are_preserved_with_pricing():
    raw = '[{"bhk":"1 BHK","carpet_area":"350","price_per_sqft":"10000","all_inclusive_price":"3500000","negotiable":"YES"},{"bhk":"1 BHK","carpet_area":"400","price_per_sqft":"10500","all_inclusive_price":"4200000","negotiable":"NO"},{"bhk":"2 BHK","carpet_area":"720","price_per_sqft":"12000","all_inclusive_price":"8640000","negotiable":"YES"}]'
    variants = _parse_variants(raw)
    assert len(variants) == 3
    assert [v["bhk"] for v in variants] == ["1 BHK", "1 BHK", "2 BHK"]
    assert variants[0]["carpet_area"] == "350"
    assert variants[0]["price_per_sqft"] == "10000"
    assert variants[0]["all_inclusive_price"] == "3500000"
    assert variants[0]["negotiable"] == "YES"
    assert variants[1]["negotiable"] == "NO"


def test_parking_is_optional_and_configured_by_bhk():
    parking = _parse_parking('{"1 BHK":1,"2 BHK":2,"3 BHK":1}')
    assert parking == {"1 BHK": 1, "2 BHK": 2, "3 BHK": 1}
    assert _parse_parking('{}') == {}
    assert _parse_parking('{"1 BHK":""}') == {}


def test_invalid_or_empty_configuration_is_rejected():
    with pytest.raises(ValueError):
        _parse_variants('[]')
    with pytest.raises(ValueError):
        _parse_variants('[{"bhk":"2 BHK","carpet_area":"650","price_per_sqft":"10000","all_inclusive_price":"6500000","negotiable":"YES"}]')
    with pytest.raises(ValueError):
        _parse_variants('[{"bhk":"2 BHK","carpet_area":"abc","price_per_sqft":"10000","all_inclusive_price":"6500000","negotiable":"YES"}]')
    with pytest.raises(ValueError):
        _parse_variants('[{"bhk":"2 BHK","carpet_area":"650","price_per_sqft":"","all_inclusive_price":"6500000","negotiable":"YES"}]')
    with pytest.raises(ValueError):
        _parse_variants('[{"bhk":"2 BHK","carpet_area":"650","price_per_sqft":"10000","all_inclusive_price":"6500000","negotiable":"MAYBE"}]')
    with pytest.raises(ValueError):
        _parse_parking('{"2 BHK":-1}')


def test_carpet_area_normalization_and_safe_unit_number():
    variants = _parse_variants('[{"bhk":"2 BHK","carpet_area":"150.00","price_per_sqft":"10000.00","all_inclusive_price":"1500000.00","negotiable":"NO"}]')
    assert variants[0]["carpet_area"] == "150"
    assert variants[0]["price_per_sqft"] == "10000.00"
    assert variants[0]["all_inclusive_price"] == "1500000.00"
    value = _configuration_unit_number("2 BHK", "650")
    assert value.startswith("CONFIG-2-BHK-650")
    assert all(ch.isalnum() or ch == "-" for ch in value)
