import pytest

from app.routers.sales_property import _configuration_unit_number, _parse_parking, _parse_variants


def test_multiple_same_bhk_rows_and_multiple_bhk_are_preserved():
    variants = _parse_variants('[{"bhk":"1 BHK","carpet_areas":["350"]},{"bhk":"1 BHK","carpet_areas":["400"]},{"bhk":"1 BHK","carpet_areas":["420"]},{"bhk":"2 BHK","carpet_areas":["650"]},{"bhk":"2 BHK","carpet_areas":["720"]},{"bhk":"3 BHK","carpet_areas":["900"]},{"bhk":"4 BHK","carpet_areas":["1200"]}]')
    assert len(variants) == 7
    assert [v["bhk"] for v in variants[:3]] == ["1 BHK", "1 BHK", "1 BHK"]
    assert [v["carpet_areas"][0] for v in variants[:5]] == ["350", "400", "420", "650", "720"]


def test_parking_is_optional_and_configured_by_bhk():
    parking = _parse_parking('{"1 BHK":1,"2 BHK":2,"3 BHK":1}')
    assert parking == {"1 BHK": 1, "2 BHK": 2, "3 BHK": 1}
    assert _parse_parking('{}') == {}
    assert _parse_parking('{"1 BHK":""}') == {}


def test_invalid_or_empty_configuration_is_rejected():
    with pytest.raises(ValueError):
        _parse_variants('[]')
    with pytest.raises(ValueError):
        _parse_variants('[{"bhk":"2 BHK","carpet_areas":[]}]')
    with pytest.raises(ValueError):
        _parse_variants('[{"bhk":"2 BHK","carpet_areas":["abc"]}]')
    with pytest.raises(ValueError):
        _parse_parking('{"2 BHK":-1}')


def test_carpet_area_normalization_and_safe_unit_number():
    variants = _parse_variants('[{"bhk":"2 BHK","carpet_areas":["150.00","420.50"]}]')
    assert variants[0]["carpet_areas"] == ["150", "420.5"]
    value = _configuration_unit_number("2 BHK", "650")
    assert value.startswith("CONFIG-2-BHK-650")
    assert all(ch.isalnum() or ch == "-" for ch in value)
