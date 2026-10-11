# HR user category

HR-specific user/staff workflows and approved reports; do not grant CRM/customer access simply because a user has this role.

## Boundary rules

- This folder is the future home for role-specific routes, services, schemas, templates and tests.
- Shared login/password/session/CSRF/permission/database/audit code must remain centralized and be called through stable interfaces.
- Role folder placement is not an authorization control. Every route and service must enforce server-side role permissions and record sensitive mutations.
- Add a new function in this category only after checking its shared dependencies and adding focused plus regression tests.
- Migrate existing code into this folder incrementally; do not duplicate or move code here until imports, route registration, template references and tests are mapped.
- Do not change other categories or the OM Krishna Group project as part of category-specific work.
