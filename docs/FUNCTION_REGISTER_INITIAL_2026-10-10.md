# MetroCRM Function / Dashboard Menu Inventory (Initial)

Date: 2026-10-10
Repository snapshot: `f95e5c6f1891b8c67188391d9dea80bc6aaec16c` (main baseline)
Purpose: provide a traceable starting inventory for the folder-wise refactor. This is not yet a complete static call graph; shared helpers, all route handlers and indirect imports still need automated extraction and review.

## Dashboard menu to current code (initial mapping)

| Dashboard item / feature | Current known files | Notes / migration target |
|---|---|---|
| Home / Dashboard | `app/main.py`, `app/templates/dashboard.html`, `app/templates/base.html` | Dashboard rendering is currently in the application entry point. Extract only after route/session/template context dependencies are mapped. Target: `app/features/dashboard/`. |
| Login / Super Admin login | `app/main.py`, `app/auth.py`, `app/security.py`, `app/csrf.py`, `app/permissions.py`, `app/templates/login.html`, `app/templates/admin_login.html` | Keep authentication primitives shared. Role-specific screen/workflow can be feature-owned, but do not duplicate password/session/CSRF logic. Target: `app/features/auth/` + `app/core/security/`. |
| Caller Property Search | `app/routers/caller_search.py`, `app/services/caller_search.py`, `app/location_catalog.py`, `app/templates/caller_search.html` | Search UI, query/service and location catalogue dependencies need mapping. Target: `app/features/callers/property_search/`. |
| Property Data | `app/routers/property_data.py`, `app/routers/property_data_super_admin.py`, `app/property_catalog.py`, `app/property_management_ui.py`, `app/property_master.py`, `app/services/property_pricing.py`, `app/templates/property_data.html` | Admin and Super Admin variants share property functionality; preserve explicit authorization boundaries and avoid duplicating logic. Target: `app/features/properties/data/` and `master/`. |
| SM Property Submissions | `app/routers/property_submissions.py`, `app/routers/sales_property.py`, `app/property_submission_models.py`, related `app/templates/property_submission*.html`, `app/templates/sales_property*.html` | Separate public token forms, Sales submissions, and Admin approval UI as submodules within a single property-submissions feature. Keep draft/review/approve boundary. |
| User Management | `app/main.py`, `app/routers/user_management_compat.py`, `app/models.py`, `app/permissions.py`, `app/templates/admin_users.html` | Role visibility and team scope are sensitive shared dependencies. Map all registration/approval endpoints before moving. |
| Integrations | `app/routers/integrations.py`, `app/integrations/`, `app/integration_models.py`, `app/services/integrations.py`, `app/services/integration_secrets.py`, `app/templates/integrations_providers.html`, `integration_logs.html`, `integration_property_visits.html` | Separate provider contracts, secrets, webhooks, and UI. Configured status alone is not proof of a live provider operation. |
| Visit Alerts | `app/routers/integrations.py`, `app/routers/lead_visit_monitoring.py`, `app/services/backup_alerts.py`, related visit models | The UI label may span integration alerts and visit monitoring. Exact data source and schedule must be verified before extraction. |
| Lead & Visit Monitoring | `app/routers/lead_visit_monitoring.py`, `app/models.py`, `app/permissions.py` | Known routes: `/admin/lead-monitoring`, `/admin/lead-monitoring/reassign-lead`, `/admin/lead-monitoring/reassign-visit`. Target: `app/features/leads/monitoring/` and `app/features/site_visits/monitoring/` only after shared policy mapping. |
| User Approvals | `app/main.py`, `app/services/approval.py`, `app/templates/pending_users.html`, `app/models.py` | Confirm exact endpoints and approval lifecycle before moving. Target: `app/features/users/approvals/`. |
| Login Approval Requests | `app/routers/password_recovery.py`, `app/routers/password_reset_requests.py`, `app/routers/recovery_login_link.py`, `app/auth.py`, templates | Keep account approval, password reset and login recovery distinct subflows, even if the navigation groups them together. |
| Backup Status / Backup & Restore | `app/routers/backups.py`, `app/routers/backup_devices.py`, `app/services/backup.py`, `backup_alerts.py`, `backup_application.py`, `backup_destinations.py`, `backup_devices.py`, `backup_restore.py`, `backup_scheduler.py`, `app/templates/backup_status.html` | Target: `app/features/backups/`. Verify destination copies and restore drill separately from code tests. |
| My Profile | `app/main.py`, `app/templates/profile.html`, `app/models.py` | Confirm profile routes and any shared session logic before extraction. |
| User Activity & Audit | `app/main.py`, `app/models.py`, audit-related routes/templates (exact mapping pending) | Keep audit writes centralized and non-optional for sensitive mutations. |
| Reports | `app/routers/advanced_reports.py`, other report routes, report templates | Split staff/business/advanced reports by subfeature but share filter/scope rules. |
| Business Reports | `app/routers/advanced_reports.py`, accounting/report models and templates | Verify financial filters, export authorization and data-scope tests. |
| Accounting & Expenses | `app/routers/accounting.py`, `app/accounting_logic.py`, `app/accounting_models.py`, `app/realestate_finance_models.py` | Target: `app/features/accounting/`; preserve financial transaction semantics and period-close controls. |
| WhatsApp / Property import | `app/routers/whatsapp.py`, `app/routers/whatsapp_property_import.py`, `app/services/whatsapp.py`, `app/services/whatsapp_property_import.py`, `app/services/property_import.py`, `app/templates/whatsapp.html` | Keep incoming data as draft/review until approved; preserve unknown fields rather than inventing data. |
| Caller Assistant / AI Caller | `app/routers/ai_caller.py`, `app/routers/caller_assistant.py`, `app/routers/caller_speech.py`, `app/routers/caller_speech_settings.py`, `app/services/ai_caller.py` | Split assistant, speech and settings into separate submodules; do not mix model/provider calls with UI rendering. |
| Lead Import / Offline Import | `app/routers/lead_import.py`, lead models and `lead_offline_import.html` | Target: `app/features/leads/imports/`; retain dedupe, permission and audit tests. |
| Property update | `app/routers/property_update.py`, `app/services/property_update_engine.py`, related template | Keep update validation, review and write logic separate. |
| Marketing | `app/routers/marketing.py`, `app/marketing_models.py`, `app/marketing_security.py` | Separate campaign administration from public campaign token/lead capture. |
| Catalog sharing / media catalog | `app/routers/catalog_sharing.py`, `app/routers/media_catalog.py`, `app/services/catalog_sharing.py`, `app/services/catalog_renderer.py`, catalog models/templates | Distinguish catalog content from property master data. |
| Real-estate finance / quotations | `app/routers/realestate_finance.py`, `app/routers/accounting.py`, `app/realestate_finance_models.py` | Avoid duplicate router registration while extracting accounting as a subfeature. |
| Health / system storage | `app/routers/health.py`, `app/routers/system_storage.py`, database/config modules | Treat health endpoints and system administration as restricted infrastructure concerns. |

## Confirmed route samples from source

- Property Data routes in `app/routers/property_data.py`: `/admin/property-data`, `/admin/property-data/template`, `/admin/property-data/import`, `/admin/property-data/bulk-modify`, `/admin/property-data/save`, property export request/download and Super Admin export request approval/rejection.
- Super Admin property data routes in `app/routers/property_data_super_admin.py`: `/super-admin/property-data`, template/import/save/delete-selected/export.
- WhatsApp property import in `app/routers/whatsapp_property_import.py`: Admin/Super Admin analyze, submission review/update/commit, Super Admin reject.
- Property submissions in `app/routers/property_submissions.py`: public token form, SM token form, Admin/Super Admin create/approve/request-correction/revoke.
- Backup routes in `app/routers/backups.py`: status/status.json/configure/run/restore and Google Drive/OneDrive callbacks, plus backup-agent endpoints.
- Integrations in `app/routers/integrations.py`: provider list/configure/run/sync, property visits and integration logs.
- Accounting in `app/routers/accounting.py`: accounting entries, journal, financials, periods/close, export.
- Reports in `app/routers/advanced_reports.py`: advanced reports, staff reports, business reports/export and Super Admin business reports.

## Automation that should be added after the inventory stabilizes

1. **Architecture manifest:** a machine-readable registry linking menu key → route module → service → templates → models → tests → owner feature.
2. **Changed-file scope check:** PR workflow reports the features and shared files touched. It warns or fails if a change crosses unrelated feature boundaries without an explicit allowlist/reason.
3. **Route/template integrity test:** assert every referenced template exists and key menu routes are registered.
4. **Import-cycle check:** prevent new circular imports during extraction.
5. **Focused + full regression CI:** run affected-feature tests first, then the full suite on every PR; full suite remains the merge gate.
6. **Migration safety guard:** any DB schema migration is separately reviewed and never bundled into a folder-only refactor.
7. **Release evidence:** record tested commit SHA, CI run, deployed SHA, health result, changed feature and rollback instructions.

These automations must be introduced incrementally. A strict changed-file blocker should not be enabled until the initial manifest is accurate, otherwise it could block necessary shared fixes or encourage bypasses.

## Known limitations / next inventory pass

- This is a human-reviewed initial mapping, not a complete function-by-function call graph.
- `app/main.py` contains core routes and router registration; exact ownership must be extracted before splitting.
- Several model files are shared across features.
- Menu labels may combine multiple route modules; for example Visit Alerts and User Activity & Audit need exact route/template discovery.
- Before the first code move, generate a route table from FastAPI registration and scan imports, template references, model reads/writes, scheduler tasks and tests. Then review the output against this document.
