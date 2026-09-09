from app.main import app
from app.catalog_models import PropertySocialProfile


def _paths():
    return {getattr(route, "path", None) for route in app.routes}


def test_offline_lead_import_and_template_routes_exist():
    paths = _paths()
    assert "/admin/leads/offline-import" in paths
    assert "/admin/leads/offline-import/template" in paths
    assert "/super-admin/lead-import-notifications" in paths


def test_property_social_management_route_exists():
    paths = _paths()
    assert "/admin/property-data/social" in paths


def test_property_social_profile_has_customer_facing_channels():
    columns = {column.name for column in PropertySocialProfile.__table__.columns}
    assert {"facebook_url", "instagram_url", "youtube_url", "whatsapp_url", "website_url"}.issubset(columns)
