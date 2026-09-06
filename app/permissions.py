from __future__ import annotations

from enum import StrEnum
from typing import Mapping


class Role(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    TL = "TL"
    SALES_EXECUTIVE = "SALES_EXECUTIVE"
    TELECALLER = "TELECALLER"
    ACCOUNTANT = "ACCOUNTANT"
    HR = "HR"


class Access(StrEnum):
    VIEW = "VIEW"
    CREATE = "CREATE"
    EDIT = "EDIT"
    DELETE = "DELETE"
    ASSIGN = "ASSIGN"
    REASSIGN = "REASSIGN"
    CLOSE = "CLOSE"
    EXPORT = "EXPORT"


class FieldVisibility(StrEnum):
    VIEW = "VIEW"
    MASKED = "MASKED"
    HIDDEN = "HIDDEN"


SENSITIVE_FIELDS = {
    "mobile",
    "alternate_mobile",
    "email",
    "address",
    "budget",
    "requirements",
    "internal_notes",
    "booking_amount",
    "sale_value",
    "financial_information",
    "documents",
}

# Export/delete are deliberately absent from ordinary role defaults.
# Data downloads and destructive deletion use the approval workflow in the
# application service layer rather than a menu-only permission.
ROLE_DEFAULTS: dict[Role, dict[str, set[Access]]] = {
    Role.SUPER_ADMIN: {"*": set(Access)},
    Role.ADMIN: {
        "leads": {Access.VIEW, Access.CREATE, Access.EDIT, Access.ASSIGN, Access.REASSIGN, Access.CLOSE},
        "customers": {Access.VIEW, Access.CREATE, Access.EDIT},
        "properties": {Access.VIEW, Access.CREATE, Access.EDIT},
        "followups": {Access.VIEW, Access.CREATE, Access.EDIT},
        "reports": {Access.VIEW},
    },
    Role.MANAGER: {
        "leads": {Access.VIEW, Access.CREATE, Access.EDIT, Access.ASSIGN, Access.REASSIGN, Access.CLOSE},
        "customers": {Access.VIEW, Access.CREATE, Access.EDIT},
        "properties": {Access.VIEW, Access.CREATE, Access.EDIT},
        "followups": {Access.VIEW, Access.CREATE, Access.EDIT},
        "reports": {Access.VIEW},
    },
    Role.TL: {
        "leads": {Access.VIEW, Access.EDIT, Access.ASSIGN, Access.REASSIGN},
        "customers": {Access.VIEW, Access.EDIT},
        "properties": {Access.VIEW},
        "followups": {Access.VIEW, Access.CREATE, Access.EDIT},
        "reports": {Access.VIEW},
    },
    Role.SALES_EXECUTIVE: {
        "leads": {Access.VIEW, Access.EDIT},
        "customers": {Access.VIEW, Access.CREATE, Access.EDIT},
        "properties": {Access.VIEW},
        "followups": {Access.VIEW, Access.CREATE, Access.EDIT},
    },
    Role.TELECALLER: {
        "leads": {Access.VIEW, Access.EDIT},
        "customers": {Access.VIEW, Access.CREATE, Access.EDIT},
        "properties": {Access.VIEW},
        "followups": {Access.VIEW, Access.CREATE, Access.EDIT},
    },
    Role.ACCOUNTANT: {
        "customers": {Access.VIEW},
        "reports": {Access.VIEW},
    },
    Role.HR: {
        "reports": {Access.VIEW},
    },
}


def role_allows(role: Role, module: str, action: Access) -> bool:
    permissions = ROLE_DEFAULTS.get(role, {})
    return action in permissions.get("*", set()) or action in permissions.get(module, set())


def user_allows(
    role: Role,
    module: str,
    action: Access,
    permissions: Mapping[str, object] | None = None,
) -> bool:
    """Resolve role defaults, then apply per-user additions/restrictions.

    Supported JSON shape:
      {"allow": {"leads": ["VIEW"]}, "deny": {"leads": ["EDIT"]}}
    A deny always wins, allowing an administrator to restrict a role default.
    """
    permissions = permissions or {}
    allowed = role_allows(role, module, action)
    allow = permissions.get("allow", {})
    deny = permissions.get("deny", {})
    if isinstance(allow, Mapping):
        values = allow.get(module, [])
        if isinstance(values, (list, tuple, set)) and action.value in values:
            allowed = True
    if isinstance(deny, Mapping):
        values = deny.get(module, [])
        if isinstance(values, (list, tuple, set)) and action.value in values:
            return False
    return allowed
