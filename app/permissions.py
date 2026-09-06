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


def effective_access(role: Role, grants: set[Access] | None = None, denies: set[Access] | None = None) -> set[Access]:
    access = set(ROLE_DEFAULTS[role])
    access.update(grants or set())
    access.difference_update(denies or set())
    return access
