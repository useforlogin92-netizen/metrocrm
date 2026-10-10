from app.permissions import Access, Role, user_allows


def test_sales_roles_cannot_assign_or_export_by_default():
    assert not user_allows(Role.SALES_EXECUTIVE, "leads", Access.ASSIGN)
    assert not user_allows(Role.SALES_EXECUTIVE, "leads", Access.REASSIGN)
    assert not user_allows(Role.SALES_EXECUTIVE, "customers", Access.EXPORT)


def test_management_roles_can_assign_leads():
    assert user_allows(Role.MANAGER, "leads", Access.ASSIGN)
    assert user_allows(Role.TL, "leads", Access.REASSIGN)


def test_user_deny_overrides_role_default_and_allow_can_add_right():
    assert not user_allows(
        Role.MANAGER,
        "leads",
        Access.ASSIGN,
        {"deny": {"leads": ["ASSIGN"]}},
    )
    assert user_allows(
        Role.SALES_EXECUTIVE,
        "leads",
        Access.ASSIGN,
        {"allow": {"leads": ["ASSIGN"]}},
    )


def test_super_admin_is_unrestricted_by_role_defaults():
    assert user_allows(Role.SUPER_ADMIN, "anything", Access.DELETE)
    assert user_allows(Role.SUPER_ADMIN, "anything", Access.EXPORT)


def test_super_admin_deny_override_cannot_remove_any_right():
    restrictive_overrides = {
        "deny": {
            "*": [action.value for action in Access],
            "leads": [action.value for action in Access],
            "users": [action.value for action in Access],
            "accounting": [action.value for action in Access],
        }
    }
    for module in ("anything", "leads", "users", "accounting", "site_visits", "bookings"):
        for action in Access:
            assert user_allows(Role.SUPER_ADMIN, module, action, restrictive_overrides)


def test_super_admin_rights_are_independent_of_empty_or_unknown_override_data():
    assert all(
        user_allows(Role.SUPER_ADMIN, "any_module", action, {})
        for action in Access
    )
    assert user_allows(
        Role.SUPER_ADMIN, "leads", Access.DELETE,
        {"deny": {"leads": ["DELETE"]}},
    )
