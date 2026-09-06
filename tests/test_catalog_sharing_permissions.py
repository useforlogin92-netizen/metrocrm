from app.routers.catalog_sharing import _can_share
from app.models import User


def user(role: str, permissions: str = "{}") -> User:
    return User(
        username="test",
        password_hash="hash",
        role=role,
        permissions_json=permissions,
        is_active=True,
    )


def test_property_view_allows_catalog_sharing_for_standard_roles():
    assert _can_share(user("SALES_EXECUTIVE")) is True
    assert _can_share(user("TELECALLER")) is True


def test_user_restriction_can_disable_catalog_sharing():
    assert _can_share(user("SALES_EXECUTIVE", '{"deny":{"properties":["VIEW"]}}')) is False


def test_unknown_role_cannot_share():
    assert _can_share(user("UNKNOWN")) is False
