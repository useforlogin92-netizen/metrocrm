from openpyxl import load_workbook

from app.routers.property_data import PROPERTY_SHEETS, _property_workbook


def test_property_template_contains_only_property_sheets():
    workbook = load_workbook(_property_workbook(), data_only=True)
    assert workbook.sheetnames == ["Instructions", "Developers", "Projects", "Towers", "Units", "NearbyLocations", "Examples"]
    assert workbook["Projects"]["A1"].value == "id"
    assert workbook["Units"]["D1"].value == "unit_number"
    assert workbook["NearbyLocations"]["B1"].value == "project_id"
    assert set(PROPERTY_SHEETS) == {"Developers", "Projects", "Towers", "Units", "NearbyLocations"}


def test_property_data_routes_are_registered_in_production_app():
    from app.main_portal import app
    paths = {route.path for route in app.routes}
    assert "/admin/property-data" in paths
    assert "/admin/property-data/template" in paths
    assert "/admin/property-data/import" in paths
    assert "/admin/property-data/save" in paths


def test_property_data_ui_has_download_upload_and_online_edit_controls():
    from pathlib import Path
    template = Path("app/templates/property_data.html").read_text(encoding="utf-8")
    assert "/admin/property-data/template" in template
    assert "/admin/property-data/import" in template
    assert "/admin/property-data/save" in template
    assert "Edit" in template
    assert "Download Property Template" in template
