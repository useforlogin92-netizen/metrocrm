"""Super Admin-only storage and persistence diagnostics."""
from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from app import main
from app.config import settings
from app.database import get_db
from app.models import AuditEvent, User

app = main.app


def _safe_db_label(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme.startswith("sqlite"):
        return f"SQLite · {parsed.path or 'local file'}"
    if parsed.scheme.startswith("postgres"):
        return f"PostgreSQL · {parsed.path.lstrip('/') or 'database'}"
    return parsed.scheme or "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@app.get("/super-admin/system/storage", response_class=HTMLResponse)
def storage_status(request: Request):
    db = next(get_db())
    try:
        user = main._current_user(request, db)
        if not user or user.role != "SUPER_ADMIN":
            return RedirectResponse("/super-admin/login", status_code=303)

        counts = {
            "users": int(db.scalar(select(func.count()).select_from(User)) or 0),
            "audit_events": int(db.scalar(select(func.count()).select_from(AuditEvent)) or 0),
        }
        root = Path(settings.backup_local_path).expanduser().resolve()
        backups = []
        if root.exists():
            for path in sorted(root.rglob("*.mcrmbackup"), key=lambda p: p.stat().st_mtime_ns, reverse=True)[:20]:
                stat = path.stat()
                backups.append({
                    "path": path.relative_to(root).as_posix(),
                    "size": stat.st_size,
                    "sha256": _sha256(path),
                    "modified": stat.st_mtime,
                })

        rows = "".join(
            f"<tr><td>{item['path']}</td><td>{item['size']:,}</td><td><code>{item['sha256']}</code></td></tr>"
            for item in backups
        ) or "<tr><td colspan='3'>No .mcrmbackup file found.</td></tr>"
        html = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MetroCRM · Storage Verification</title>
<style>body{{font-family:system-ui;background:#f4f7fb;color:#0f172a;margin:0;padding:28px}}.wrap{{max-width:1100px;margin:auto}}.card{{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:20px;margin-bottom:16px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}.label{{font-size:11px;color:#64748b;text-transform:uppercase;font-weight:800}}.value{{font-size:18px;font-weight:900;margin-top:5px}}table{{width:100%;border-collapse:collapse;font-size:12px}}th,td{{padding:9px;border-bottom:1px solid #e2e8f0;text-align:left;vertical-align:top}}code{{word-break:break-all;font-size:10px}}a{{color:#2563eb;font-weight:800;text-decoration:none}}</style></head><body><div class='wrap'>
<div class='card'><h2 style='margin-top:0'>Storage & Data Verification</h2><p>This page reads the database and the backup filesystem used by the running MetroCRM instance. It does not expose database credentials.</p><a href='/super-admin/backups/status'>← Backup Status</a></div>
<div class='grid'><div class='card'><div class='label'>Database</div><div class='value'>{_safe_db_label(settings.database_url)}</div></div><div class='card'><div class='label'>Users saved</div><div class='value'>{counts['users']}</div></div><div class='card'><div class='label'>Audit events saved</div><div class='value'>{counts['audit_events']}</div></div><div class='card'><div class='label'>Local backup root</div><div class='value' style='font-size:13px;word-break:break-all'>{root}</div></div></div>
<div class='card'><h3>Local encrypted backup files</h3><table><thead><tr><th>Relative path</th><th>Bytes</th><th>SHA-256</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class='card'><p style='margin:0;color:#64748b;font-size:12px'>A database row count of zero here means the running application has no saved users in the database it is actually connected to. A backup file is independently verifiable by its size and SHA-256.</p></div>
</div></body></html>"""
        return HTMLResponse(html)
    finally:
        db.close()
