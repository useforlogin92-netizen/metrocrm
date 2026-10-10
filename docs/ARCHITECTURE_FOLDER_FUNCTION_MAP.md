# MetroCRM Folder-wise / Function-wise Architecture Plan

Date: 2026-10-10
Scope: MetroCRM repository only (`useforlogin92-netizen/metrocrm`).
Status: Architecture plan and safe migration sequence; this document does not move or rewrite existing code.

## Non-negotiable safety rules

1. Keep MetroCRM independent. Do not touch the OM Krishna Group repository, site, login, database, secrets, or deployment.
2. Preserve the current FastAPI + SQLAlchemy stack. No rewrite or framework migration.
3. Do not move or rename existing files in a single large refactor.
4. First map routes, functions, templates, imports, models, database writes, permissions, and tests.
5. Migrate one feature slice at a time using compatibility imports or wrappers where needed.
6. No database schema/data changes merely to reorganize Python files.
7. Every change must include a file-level diff review, focused tests, full regression CI, and a deployment/rollback note.
8. A module boundary reduces risk but cannot guarantee zero cross-feature errors; shared dependencies must be tested.

## Target logical layout

This is the target structure. It is not a command to create duplicate files or move all current files immediately.

```text
app/
  main.py                         # application startup and router registration only over time
  core/
    config.py                     # configuration (migrate from app/config.py only after import audit)
    database.py                   # DB/session wiring (migrate from app/database.py only after audit)
    security/
      auth.py                     # authentication primitives (from app/auth.py after audit)
      csrf.py                     # CSRF primitives (from app/csrf.py after audit)
      permissions.py              # shared permission checks (from app/permissions.py after audit)
      sessions.py                 # session helpers, versioning, expiry
    navigation/
      registry.py                 # central page/menu registry, if safe to introduce
  features/
    home/
      router.py
      service.py
      schemas.py
      templates/
      tests/
    auth/
      router.py
      service.py
      schemas.py
      templates/
      tests/
      super_admin/
        router.py
        service.py
        schemas.py
        templates/
        tests/
      user_login/
        router.py
        service.py
        templates/
        tests/
    dashboard/
      router.py
      service.py
      templates/
      tests/
    properties/
      router.py
      service.py
      repository.py
      schemas.py
      templates/
      tests/
      data/
      search/
      master/
      submissions/
      imports/
      research_drafts/
      approvals/
      matching/
    leads/
      router.py
      service.py
      repository.py
      schemas.py
      templates/
      tests/
      assignment/
      followups/
      lifecycle/
    customers/
      router.py
      service.py
      schemas.py
      templates/
      tests/
    site_visits/
      router.py
      service.py
      templates/
      tests/
      reminders/
      feedback/
    callers/
      router.py
      service.py
      templates/
      tests/
      property_search/
      assistant/
      speech/
    users/
      router.py
      service.py
      templates/
      tests/
      approvals/
      activity_audit/
    integrations/
      router.py
      service.py
      providers/
      webhooks/
      templates/
      tests/
    communications/
      service.py
      templates/
      tests/
      whatsapp/
      email/
      message_templates/
      delivery_log/
    reports/
      router.py
      service.py
      templates/
      tests/
    accounting/
      router.py
      service.py
      models.py
      templates/
      tests/
    backups/
      router.py
      service.py
      scheduler.py
      restore/
      templates/
      tests/
  shared/
    models/                       # shared SQLAlchemy models, only after dependency review
    audit.py
    validators.py
    errors.py
templates/                        # shared base/layout only, if current template engine needs it
tests/
  unit/
  routes/
  permissions/
  integration/
  regression/
docs/
  ARCHITECTURE_FOLDER_FUNCTION_MAP.md
  FUNCTION_REGISTER.md
  CHANGELOG_FEATURES.md
  REGRESSION_MATRIX.md
```

## Feature ownership rule

Each visible dashboard/menu feature gets one owning feature folder. Its routes, business logic, schemas, page templates, assets and feature-specific tests should live together. A feature may call shared utilities through explicit interfaces; it must not copy shared authentication, permission, database or audit logic into its own folder.

Example: Property Data changes should be limited to `features/properties/data/` and its owning route/service/tests. If the change needs a shared model or permission helper, record that as an explicit dependency and add tests for the dependency; do not silently modify unrelated features.

Example: Super Admin login/authentication belongs under `features/auth/super_admin/`, while reusable authentication/session/CSRF/permission primitives belong under `core/security/`. This avoids duplicating security logic for each role.

## Current-repository mapping (initial, based on the current tree)

Existing code is partly grouped but also has many top-level modules and a large `app/main.py`. The following is an initial map, not proof that every function in each file belongs only to that feature:

- Application entry point/router registration: `app/main.py`, `app/main_portal.py`
- Shared security/access: `app/auth.py`, `app/access_control.py`, `app/permissions.py`, `app/csrf.py`, `app/oauth_compat.py`, `app/logout_cookie_hardening.py`
- Shared user/domain models: `app/models.py` plus specialist model modules such as `app/accounting_models.py`, `app/catalog_models.py`, `app/crm_plus_models.py`, `app/integration_models.py`, `app/marketing_models.py`, `app/property_submission_models.py`, `app/realestate_finance_models.py`
- Properties/catalog/master/submissions: `app/property_catalog.py`, `app/property_management_ui.py`, `app/property_master.py`, `app/property_submission_models.py`, and related routers/templates
- Caller tools: `app/routers/caller_*.py`, `app/routers/ai_caller.py`, `app/routers/caller_search.py`
- Reports: `app/routers/advanced_reports.py` and other report-related routers/templates
- Accounting: `app/accounting_logic.py`, `app/accounting_models.py`, `app/routers/accounting.py`
- Integrations: `app/integrations/`, `app/routers/integrations.py`, `app/integration_models.py`
- Backups: `app/routers/backups.py`, `app/routers/backup_devices.py`, and `app/services/backup*.py`
- Lead assignment/monitoring: `app/routers/lead_visit_monitoring.py`, `app/routers/lead_assignment_suggestions.py`, related service modules and tests

Before a file is moved, inspect all imports and route registration and verify whether it mixes unrelated responsibilities. Some existing files contain cross-feature code and need function-level extraction rather than a simple file move.

## Function register fields

For every route or business function, record:

- Stable function ID and human-readable purpose
- Current file and function name
- Target feature folder
- Inputs/outputs and side effects
- Database tables/models read and written
- Permissions/roles and data-scope rules
- Imports/callers/dependencies
- Template/API endpoint, if any
- Unit, route, permission and regression test paths
- Change history, current verification status, last passing commit

Do not store secrets, tokens, passwords, customer personal data, or production database dumps in this register.

## Safe migration phases

### Phase 0 — Baseline (read-only)
- Capture current main commit and production deploy commit.
- Build a route-to-file, template-to-route, function-to-caller, model-to-feature, and test-to-feature inventory.
- Record current CI results and a production health baseline.
- Confirm backup destinations and restore procedure without changing production data.

### Phase 1 — Tests and guardrails
- Add tests around currently working behaviour before moving code.
- Add an import/dependency map and a rule that each PR lists changed files, affected features, tests run, and rollback plan.
- Keep OM Krishna Group outside repository and deployment scope.

### Phase 2 — Low-risk feature slices
- Start with isolated leaf features that have clear ownership and few shared imports.
- Create target package folders and `__init__.py` as needed.
- Move one slice at a time, update imports in the same commit, and use temporary compatibility re-exports only where required.
- Run focused tests and the complete CI after each slice.

### Phase 3 — Shared boundaries
- Extract shared security, database, audit and model helpers only after caller/import mapping and regression coverage exist.
- Avoid circular imports; router modules should depend on services and shared contracts rather than importing the application entry point where possible.
- Do not change authentication semantics or database schema during a folder-only refactor.

### Phase 4 — Verify and release
- Review the complete diff and check for unrelated file changes.
- Require green CI, route smoke tests, permission tests and the regression matrix.
- Merge only after review; verify Render deploy SHA, health endpoint, login, dashboard and changed feature.
- If any regression occurs, roll back the isolated release rather than patching unrelated features in production.

## Definition of done for a feature change

- Only the feature folder and explicitly approved shared dependencies changed.
- Tests cover expected result, invalid input, permissions, CSRF where applicable, and side effects/audit.
- Full regression suite passes on the exact PR head commit.
- Deployment is not claimed until Render reports the matching commit as live and a smoke test succeeds.
- OM Krishna Group files, services, database and deployment remain untouched.
