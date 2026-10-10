# MetroCRM Blueprint Automation Gap Audit — 2026-10-10

## Scope and safety boundary

- Repository reviewed: `useforlogin92-netizen/metrocrm`.
- Live service: `metrocrm-live` on Render.
- Original scope is a standalone MetroCRM real-estate CRM. Multi-company SaaS/tenant architecture is not a requirement of the accepted blueprint.
- OM Krishna Group is out of scope. No OM Krishna Group repository, site, database, secret, or deployment is to be changed.
- Audit is read-only until changes are made on an isolated feature branch. Production changes require review, CI, and verified deployment.

## Evidence-based findings

### Existing foundations found in repository
- FastAPI, SQLAlchemy, Jinja2, SQLite/PostgreSQL support.
- Role and permission modules, session versioning, CSRF helpers, audit events.
- Lead assignment history, lead/follow-up/site-visit data models.
- WhatsApp property import/review flow and provider configuration endpoints.
- Encrypted full-backup service, retry state, scheduled backup jobs and backup alert adapters.
- Tests covering permissions, data visibility, property import, WhatsApp import, integrations, backup and restore.
- Lead & Visit Monitoring dashboard was merged as commit `f95e5c6f1891b8c67188391d9dea80bc6aaec16c`; its Render deployment was reported `live` at 2026-10-10 13:06 UTC.

### Gaps or items not yet proven end-to-end
1. **Lead assignment:** manager monitoring/reassignment exists. A workload-based recommendation plus explicit approval workflow is being added. User coverage areas, language, capacity and availability are not defined as reliable fields in the current User model, so recommendations must disclose that they are workload-based only.
2. **Team Lead authorization:** Team Leads must only act on leads owned by their team/direct reports. Unassigned leads are not exposed to Team Leads until an explicit team ownership rule exists.
3. **Follow-up/site-visit communication:** records and dashboard visibility exist; full deduplicated reminder scheduling, retry, delivery status, escalation matrix and inbound reply correlation need separate verification.
4. **Customer message lifecycle:** automated welcome, visit confirmation/reschedule, post-visit feedback and follow-up sequence are not considered complete without provider-backed tests.
5. **Property Research:** incoming property capture/review exists. AI-generated fields must remain drafts until explicit approval; no silent overwrite.
6. **External integrations:** configured/READY is not proof of a successful provider operation. Provider-specific adapters, credentials, webhook signature checks, idempotency and error handling require live or contract tests.
7. **Backup and restore:** code and tests exist. Actual configured destination copies and a production-safe database-plus-media restore drill remain unverified.
8. **Offline package:** portability, dependency install, startup/stop and restore smoke tests need separate verification.
9. **Reporting:** consistent cross-module filter semantics, conversions and data-scope enforcement need end-to-end tests.

## Initial implementation on isolated branch

Branch: `feature/automation-foundation-20261010`

- Added an explainable workload-based recommendation service; it does not mutate lead assignments.
- Added a management page and explicit CSRF-protected approval action. Approved assignments write both `LeadAssignmentHistory` and `AuditEvent`.
- Team Leads are restricted to leads assigned to their team/direct reports. They do not see globally unassigned leads.
- Added focused unit tests for ranking, ineligible callers, current owner exclusion, deterministic ties and limit.
- No production secrets or customer data are added to source control.

## Required validation before merge/deployment

- Run complete CI with deprecation warnings treated as errors.
- Add endpoint tests for Admin, Super Admin, TL team scope, non-manager denial, CSRF rejection, invalid caller IDs, audit/history persistence and assignment approval.
- Check query behavior against the deployed database engine and ensure the new router renders with real user/lead rows.
- Verify the latest Render deployment and health endpoint after any merge.
- Do not claim messaging automation or the complete Blueprint is done until provider-backed delivery and recovery tests pass.

## Next implementation phases

1. Assignment recommendation and approval, including full endpoint tests.
2. Reminder job with idempotency, escalation policy, delivery log and safe provider adapters.
3. Site-visit confirmation/reschedule/feedback lifecycle.
4. Property research draft/approval and duplicate/conflict review.
5. Property matching with transparent scoring and inventory freshness.
6. Manager Control Tower, conversion reporting and filter consistency.
7. Backup destination verification and isolated restore drill.
8. Offline package smoke test and final regression matrix.
