# MetroCRM Pre-Change Backup Manifest
Backup date: 2026-10-10 (Asia/Kolkata)
Purpose: preserve a known-good reference before any further work. No production code, data, environment variables, or deployment settings were changed by this backup operation.

## GitHub source snapshot
- Repository: https://github.com/useforlogin92-netizen/metrocrm (private)
- Default branch at inspection: main
- Source snapshot branch: backup/pre-change-2026-10-10-main-snapshot
- Main commit observed: 84f4c7aa5a0d8bec44fcf48f7895bb1828e61a83
- Snapshot branch was created from main; inspect branch/commit history in GitHub before restore.
- Related repository visible in connected GitHub account: https://github.com/useforlogin92-netizen/real-estate-caller-system
- Related repository snapshot branch: backup/pre-change-2026-10-10-main-snapshot (created from its main branch; current SHA not captured in this manifest).

## Render service configuration snapshot (non-secret fields only)
- Workspace ID: tea-dadf38mkb8uc7398rgvg
- Service: metrocrm-live
- Service ID: srv-daf5j4ou01pc738ueg30
- Dashboard: https://dashboard.render.com/web/srv-daf5j4ou01pc738ueg30
- Public URL: https://metrocrm-live.onrender.com
- Repository: https://github.com/useforlogin92-netizen/metrocrm
- Branch: main
- Runtime: Python
- Build command: pip install -r requirements.txt
- Start command: uvicorn app.main_portal:app --host 0.0.0.0 --port $PORT
- Region: Oregon
- Plan: free
- Auto deploy: enabled on commit
- Root directory: empty
- Health check path: empty
- Service was not modified and no deploy was triggered.

## Backup coverage and important limits
- This manifest and GitHub branches are source/configuration reference backups, NOT a verified full runtime backup.
- Render workspace listing showed no Render-managed Postgres or Key Value instances. This does NOT prove that the app has no external database.
- Database connection strings, API tokens, OAuth secrets, encryption keys, and all other secret values are intentionally not stored here.
- Database dump, uploaded files/media, persistent disks, complete environment variable names/values, Google Drive and OneDrive cloud artifacts, and a restorable Render runtime snapshot have NOT been verified or downloaded by this operation.
- The service has an application-level backup configuration in app/config.py; actual backup destinations and latest successful backup artifacts still need to be verified through the app's authorized Super Admin backup interface and the connected cloud accounts.
- Latest 10 Render deploy records inspected included repeated build_failed statuses; this manifest does not represent a successful deployment.
- Never commit .env, service tokens, OAuth secrets, database URLs, or encryption keys to GitHub. Store secret recovery material in an approved password manager/secure vault separately.
