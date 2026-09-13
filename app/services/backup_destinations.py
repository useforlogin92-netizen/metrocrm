"""Backup destination adapters for local disks and cloud drives."""
from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from app.config import settings


def _request_json(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, data: bytes | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def _refresh_google_token() -> str:
    if not all((settings.backup_google_client_id, settings.backup_google_client_secret, settings.backup_google_refresh_token)):
        raise RuntimeError("Google Drive OAuth credentials are not fully configured")
    payload = urllib.parse.urlencode({
        "client_id": settings.backup_google_client_id,
        "client_secret": settings.backup_google_client_secret,
        "refresh_token": settings.backup_google_refresh_token,
        "grant_type": "refresh_token",
    }).encode()
    _, result = _request_json(
        "https://oauth2.googleapis.com/token",
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=payload,
    )
    token = result.get("access_token")
    if not token:
        raise RuntimeError("Google Drive token refresh did not return an access token")
    return token


def _google_upload(package: Path, relative_path: str) -> str:
    if not settings.backup_google_folder_id:
        raise RuntimeError("BACKUP_GOOGLE_FOLDER_ID is not configured")
    token = _refresh_google_token()
    metadata = json.dumps({
        "name": Path(relative_path).name,
        "parents": [settings.backup_google_folder_id],
    }).encode()
    request = urllib.request.Request(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,name",
        data=metadata,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "application/octet-stream",
            "X-Upload-Content-Length": str(package.stat().st_size),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            upload_url = response.headers.get("Location")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Google Drive upload session failed with HTTP {exc.code}: {detail}") from exc
    if not upload_url:
        raise RuntimeError("Google Drive did not return a resumable upload URL")

    payload = package.read_bytes()
    request = urllib.request.Request(
        upload_url,
        data=payload,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(payload)),
            "Content-Range": f"bytes 0-{len(payload) - 1}/{len(payload)}",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Google Drive upload failed with HTTP {exc.code}: {detail}") from exc
    file_id = result.get("id")
    if not file_id:
        raise RuntimeError("Google Drive upload completed without a file id")
    return f"https://drive.google.com/file/d/{file_id}"


def _refresh_microsoft_token() -> str:
    if not all((settings.backup_onedrive_client_id, settings.backup_onedrive_client_secret, settings.backup_onedrive_refresh_token)):
        raise RuntimeError("OneDrive OAuth credentials are not fully configured")
    payload = urllib.parse.urlencode({
        "client_id": settings.backup_onedrive_client_id,
        "client_secret": settings.backup_onedrive_client_secret,
        "refresh_token": settings.backup_onedrive_refresh_token,
        "grant_type": "refresh_token",
        "scope": "offline_access Files.ReadWrite",
    }).encode()
    _, result = _request_json(
        f"https://login.microsoftonline.com/{urllib.parse.quote(settings.backup_onedrive_tenant, safe='')}/oauth2/v2.0/token",
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=payload,
    )
    token = result.get("access_token")
    if not token:
        raise RuntimeError("OneDrive token refresh did not return an access token")
    return token


def _onedrive_upload(package: Path, relative_path: str) -> str:
    token = _refresh_microsoft_token()
    folder = "/".join(part.strip("/") for part in settings.backup_onedrive_folder_path.split("/") if part.strip("/"))
    filename = Path(relative_path).name
    item_path = f"{folder}/{filename}" if folder else filename
    session_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{urllib.parse.quote(item_path, safe='/')}:/createUploadSession"
    body = json.dumps({"item": {"@microsoft.graph.conflictBehavior": "replace", "name": filename}}).encode()
    _, session = _request_json(
        session_url,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=body,
    )
    upload_url = session.get("uploadUrl")
    if not upload_url:
        raise RuntimeError("OneDrive did not return an upload session URL")

    # Microsoft Graph requires each fragment to be smaller than 60 MiB and aligned to 320 KiB.
    chunk_size = 10 * 1024 * 1024
    total = package.stat().st_size
    result: dict = {}
    with package.open("rb") as source:
        start = 0
        while start < total:
            chunk = source.read(chunk_size)
            end = start + len(chunk) - 1
            request = urllib.request.Request(
                upload_url,
                data=chunk,
                headers={
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start}-{end}/{total}",
                },
                method="PUT",
            )
            try:
                with urllib.request.urlopen(request, timeout=300) as response:
                    raw = response.read()
                    result = json.loads(raw.decode("utf-8")) if raw else {}
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:1000]
                raise RuntimeError(f"OneDrive upload failed with HTTP {exc.code}: {detail}") from exc
            start = end + 1
    item_id = result.get("id", "")
    return f"https://onedrive.live.com/?id={urllib.parse.quote(item_id)}" if item_id else "onedrive://uploaded"


def copy_to_external_drive(package: Path, relative_path: str) -> str:
    root = settings.backup_external_path.strip()
    if not root:
        raise RuntimeError("External backup path is not configured")
    root_path = Path(root).expanduser()
    if not root_path.exists():
        raise RuntimeError(f"External backup device/path not found: {root_path}")
    if not root_path.is_dir():
        raise RuntimeError(f"External backup path is not a directory: {root_path}")
    destination = root_path / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if package.resolve() == destination.resolve():
        return str(destination)
    shutil.copy2(package, destination)
    return str(destination)


def configured_cloud_providers() -> list[str]:
    raw = settings.backup_cloud_providers.strip() or settings.backup_cloud_provider.strip()
    return [item.strip().lower() for item in raw.split(",") if item.strip() and item.strip().lower() not in {"none", "disabled"}]


def upload_cloud(package: Path, relative_path: str, provider: str) -> str:
    if provider in {"s3", "s3_compatible"}:
        import boto3
        client = boto3.client(
            "s3",
            endpoint_url=settings.backup_s3_endpoint or None,
            aws_access_key_id=settings.backup_s3_access_key or None,
            aws_secret_access_key=settings.backup_s3_secret_key or None,
            region_name=settings.backup_s3_region or None,
        )
        client.upload_file(str(package), settings.backup_s3_bucket, relative_path)
        return f"s3://{settings.backup_s3_bucket}/{relative_path}"
    if provider in {"google_drive", "gdrive", "google"}:
        return _google_upload(package, relative_path)
    if provider in {"onedrive", "one_drive", "microsoft"}:
        return _onedrive_upload(package, relative_path)
    raise RuntimeError(f"Unsupported backup cloud provider: {provider}")
