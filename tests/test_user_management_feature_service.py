from datetime import datetime

import pytest

from app.features.users.service import filter_user_records, parse_permission_overrides


def _user(username, *, role="TELECALLER", email=None, mobile=None, category="Sales", team="Team A", active=True, approved=True, created_at=None):
    return type("UserFixture", (), {
        "username": username,
        "role": role,
        "email": email,
        "mobile": mobile,
        "category": category,
        "team": team,
        "is_active": active,
        "is_approved": approved,
        "created_at": created_at or datetime(2026, 10, 1, 10, 0),
    })()


def test_user_filter_combines_search_role_category_team_and_status():
    users = [
        _user("rahul", email="rahul@example.com"),
        _user("priya", role="SALES_EXECUTIVE", category="Field Sales", team="Team B"),
        _user("inactive", active=False),
        _user("pending", approved=False),
    ]

    result = filter_user_records(
        users,
        query="RAHUL@EXAMPLE.COM",
        role="TELECALLER",
        category="sales",
        team="team a",
        status="active",
        created_from="2026-10-01",
        created_to="2026-10-02",
    )

    assert [user.username for user in result] == ["rahul"]


def test_user_filter_pending_and_date_range():
    users = [
        _user("old", approved=False, created_at=datetime(2026, 9, 30)),
        _user("pending", approved=False, created_at=datetime(2026, 10, 3)),
        _user("approved", approved=True, created_at=datetime(2026, 10, 3)),
    ]

    result = filter_user_records(users, status="pending", created_from="2026-10-01", created_to="2026-10-03")
    assert [user.username for user in result] == ["pending"]


def test_permission_override_parser_accepts_known_actions_and_rejects_unknown_values():
    assert parse_permission_overrides('{"deny":{"leads":["DELETE"]}}') == {"deny": {"leads": ["DELETE"]}}
    with pytest.raises(ValueError):
        parse_permission_overrides('{"allow":{"leads":["ROOT_ACCESS"]}}')
    with pytest.raises(ValueError):
        parse_permission_overrides('{"unexpected":{}}')
