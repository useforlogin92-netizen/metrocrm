def test_sales_property_routes_registered():
    from app.main_portal import app
    paths = {route.path for route in app.routes}
    assert "/admin/property-data/sales-link" in paths
    assert "/sales/property/{token}" in paths
    assert "/admin/property-data/sales-submissions" in paths
    assert "/admin/property-data/sales-submissions/{submission_id}/approve" in paths
    assert "/admin/property-data/sales-submissions/{submission_id}/reject" in paths


def test_sales_property_submission_model_has_approval_fields():
    from app.catalog_models import SalesPropertySubmission
    columns = set(SalesPropertySubmission.__table__.columns.keys())
    assert {"token_hash", "data_json", "status", "created_by_id", "reviewed_by_id", "review_note", "reviewed_at", "record_id"}.issubset(columns)
