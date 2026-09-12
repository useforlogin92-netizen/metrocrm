import app.routers.property_data as property_data


def test_property_data_route_uses_safe_staging_importer():
    assert property_data._import_workbook.__module__ == "app.services.property_import"
    assert property_data._import_workbook.__name__ == "import_property_workbook"
