from enum import StrEnum


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


# Sensitive data export and deletion are deliberately not role defaults.
# They must go through the separate approval workflow (except Super Admin).
ROLE_DEFAULTS: dict[Role, set[Access]] = {
    Role.SUPER_ADMIN: set(Access),
    Role.ADMIN: {Access.VIEW, Access.CREATE, Access.EDIT, Access.ASSIGN, Access.REASSIGN, Access.CLOSE},
    Role.MANAGER: {Access.VIEW, Access.CREATE, Access.EDIT, Access.ASSIGN, Access.REASSIGN, Access.CLOSE},
    Role.TL: {Access.VIEW, Access.CREATE, Access.EDIT, Access.CLOSE},
    Role.SALES_EXECUTIVE: {Access.VIEW, Access.CREATE, Access.EDIT},
    Role.TELECALLER: {Access.VIEW, Access.CREATE, Access.EDIT},
    Role.ACCOUNTANT: {Access.VIEW, Access.CREATE, Access.EDIT},
    Role.HR: {Access.VIEW, Access.CREATE, Access.EDIT},
}


class FieldVisibility(StrEnum):
    VIEW = "VIEW"
    MASKED = "MASKED"
    HIDDEN = "HIDDEN"


SENSITIVE_FIELDS = {
    "mobile",
    "alternate_mobile",
    "email",
    "address",
    "budget_min",
    "budget_max",
    "requirement",
    "internal_notes",
    "booking_amount",
    "sale_value",
    "commission_amount",
    "documents",
}


def effective_access(role: Role, grants: set[Access] | None = None, denies: set[Access] | None = None) -> set[Access]:
    """Resolve role defaults, then user grants, then user restrictions."""
    access = set(ROLE_DEFAULTS[role])
    access.update(grants or set())
    access.difference_update(denies or set())
    return access


def has_access(role: Role, action: Access, grants: set[Access] | None = None, denies: set[Access] | None = None) -> bool:
    """Pure authorization check suitable for use at API/service boundaries."""
    return action in effective_access(role, grants, denies)


def can_assign_lead(role: Role, grants: set[Access] | None = None, denies: set[Access] | None = None) -> bool:
    return has_access(role, Access.ASSIGN, grants, denies)


def can_reassign_lead(role: Role, grants: set[Access] | None = None, denies: set[Access] | None = None) -> bool:
    return has_access(role, Access.REASSIGN, grants, denies)


def can_direct_export(role: Role, grants: set[Access] | None = None, denies: set[Access] | None = None) -> bool:
    """Only Super Admin may directly export; Admin exports require approval."""
    if role == Role.SUPER_ADMIN:
        return True
    return False


def can_direct_delete(role: Role, grants: set[Access] | None = None, denies: set[Access] | None = None) -> bool:
    """Only Super Admin may directly delete; other roles need approval."""
    if role == Role.SUPER_ADMIN:
        return True
    return False
