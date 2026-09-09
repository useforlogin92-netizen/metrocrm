import pytest

from app.routers.sales_property import _configuration_unit_number, _parse_variants


def test_multiple_bhk_and_multiple_carpet_areas_are_preserved():
    variants = _parse_variants('[{"bhk":"1 BHK","carpet_areas":["150","400","420"]},{"bhk":"2 BHK","carpet_areas":["650","720"]},{"bhk":"3 BHK","carpet_areas":["900"]},{"bhk":"4 BHK","carpet_areas":["1200"]},{"bhk":"Jodi","carpet_areas":["1800"]}]')
    assert len(variants) == 5
    assert variants[0]["carpet_areas"] == ["150", "400", "420"]
    assert variants[1]["bhk"] == "2 BHK"
    assert variants[4]["bhk"] == "Jodi"


def test_invalid_or_empty_configuration_is_rejected():
    with pytest.raises(ValueError):
        _parse_variants('[]')
    with pytest.raises(ValueError):
        _parse_variants('[{"bhk":"2 BHK","carpet_areas":[]}]')
    with pytest.raises(ValueError):
        _parse_variants('[{"bhk":"2 BHK","carpet_areas":["abc"]}]')


def test_configuration_unit_number_is_stable_and_safe():
    value = _configuration_unit_number("2 BHK", "650")
    assert value.startswith("CONFIG-2-BHK-650")
    assert all(ch.isalnum() or ch == "-" for ch in value)
