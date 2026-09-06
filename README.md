# MetroCRM

Self-hosted Real Estate Channel Partner CRM.

## Status
Fresh clean foundation. Development is test-first and modular.

## Architecture
FastAPI + SQLAlchemy + SQLite (local) / PostgreSQL-ready + Jinja2.

## Security principles
- Role and user-specific permissions are enforced server-side.
- Super Admin is the highest security authority.
- Customer personal data is field-level VIEW/MASKED/HIDDEN.
- Admin exports/deletes require Super Admin approval.
- Non-admin staff do not receive export rights by default.
- No real credentials, OTPs, or security answers belong in source control.
