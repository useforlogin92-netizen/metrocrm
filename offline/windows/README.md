# MetroCRM Offline Development - Windows

This folder prepares MetroCRM for local/offline development on a Windows PC without requiring Render at runtime.

## What local mode uses

- SQLite database: `./metrocrm.db`
- Local uploads: `./uploads`
- Local backups: `./backups`
- Local FastAPI server: `http://127.0.0.1:8000`
- External lead/WhatsApp/email integrations are disabled or kept in test mode by the local environment template.
- Real credentials and secrets stay only in the local `.env` file and are never committed.

## Setup

1. Install Python 3.11+ and Git on the Windows PC.
2. Open PowerShell in the MetroCRM repository folder.
3. Run:

``
powershell
Set-ExecutionPolicy -Scope Process Bypass
.\offline\windows\SETUP-WINDOWS.ps1
```

4. Start MetroCRM:

``
cmd
offline\\windows\\RUN-METROCRM.bat
```

5. Open `http://127.0.0.1:8000`.

## Backup

Run:

``
powershell
.\offline\windows\BACKUP-METROCRM.ps1
```

The backup contains the local database, uploads, local backups and the non-secret environment template. It deliberately excludes `.env`, `.git`, `venv` and other secrets.

## Important

This does not magically copy the Render PostgreSQL database into the PC. To preserve existing live CRM data, a database export from the live database must be obtained and restored separately. The local setup is ready to use SQLite for continued development once the required data is migrated.
