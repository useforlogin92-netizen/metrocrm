"""Backup destination adapters for local disks and cloud drives."""
from __future__ import annotations

import base64
import hashlib
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
    _, result = _request_json("https://oauth2.googleapis.com/token", method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"}, data=payload)
    token = result.get("access_token")
    if not token:
        raise RuntimeError("Google Drive token refresh did not return an access token")
    return token


def _google_upload(package: Path, relative_path: str) -> str:
    if not settings.backup_google_folder_id:
        raise RuntimeError("BACKUP_GOOGLE_FOLDER_ID is not configured")
    token = _refresh_google_token()
    metadata = json.dumps({"name": Path(relative_path).name, "parents": [settings.backup_google_folder_id]}).encode()
    request = urllib.request.Request(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,name",
        data=metadata,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": "application/octet-stream", "X-Upload-Content-Length": str(package.stat().st_size)},
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
    request = urllib.request.Request(upload_url, data=payload, headers={"Content-Type": "application/octet-stream", "Content-Length": str(len(payload)), "Content-Range": f"bytes 0-{len(payload) - 1}/{len(payload)}"}, method="PUT")
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
    payload = urllib.parse.urlencode({"client_id": settings.backup_onedrive_client_id, "client_secret": settings.backup_onedrive_client_secret, "refresh_token": settings.backup_onedrive_refresh_token, "grant_type": "refresh_token", "scope": "offline_access Files.ReadWrite"}).encode()
    _, result = _request_json(f"https://login.microsoftonline.com/{urllib.parse.quote(settings.backup_onedrive_tenant, safe='')}/oauth2/v2.0/token", method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"}, data=payload)
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
    _, session = _request_json(session_url, method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, data=body)
    upload_url = session.get("uploadUrl")
    if not upload_url:
        raise RuntimeError("OneDrive did not return an upload session URL")

    # 10 MiB is below Microsoft's 60 MiB fragment limit and is a multiple of 320 KiB.
    chunk_size = 10 * 1024 * 1024
    total = package.stat().st_size
    result: dict = {}
    with package.open("rb") as source:
        start = 0
        while start < total:
            chunk = source.read(chunk_size)
            end = start + len(chunk) - 1
            request = urllib.request.Request(upload_url, data=chunk, headers={"Content-Length": str(len(chunk)), "Content-Range": f"bytes {start}-{end}/{total}"}, method="PUT")
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


def _looks_like_unmounted_drive(path: Path) -> bool:
    raw = str(path)
    if ":\\" in raw or raw.startswith("\\\\"):
        return True
    return any(part in path.parts for part in ("mnt", "media", "run/media"))


def copy_to_external_drive(package: Path, relative_path: str) -> str:
    root = settings.backup_external_path.strip()
    if not root:
        raise RuntimeError("External backup path is not configured")
    root_path = Path(root).expanduser()
    if not root_path.exists():
        if _looks_like_unmounted_drive(root_path):
            raise RuntimeError(f"External backup device/path not found: {root_path}")
        root_path.mkdir(parents=True, exist_ok=True)
    if not root_path.is_dir():
        raise RuntimeError(f"External backup path is not a directory: {root_path}")
    destination = root_path / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if package.resolve() == destination.resolve():
        return str(destination)
    temp = destination.with_suffix(destination.suffix + ".part")
    try:
        shutil.copy2(package, temp)
        if temp.stat().st_size != package.stat().st_size:
            raise RuntimeError("External backup copy size verification failed")
        temp.replace(destination)
    finally:
        temp.unlink(missing_ok=True)
    return str(destination)


def configured_cloud_providers() -> list[str]:
    raw = settings.backup_cloud_providers.strip() or settings.backup_cloud_provider.strip()
    return [item.strip().lower() for item in raw.split(",") if item.strip() and item.strip().lower() not in {"none", "disabled"}]


def _b2_native_upload(package: Path, relative_path: str, bucket: str, access_key: str, secret_key: str) -> str:
    """Fallback transport for B2 when the S3-compatible connection is closed by the network."""
    basic = base64.b64encode(f"{access_key}:{secret_key}".encode("utf-8")).decode("ascii")
    _, auth = _request_json(
        "https://api.backblazeb2.com/b2api/v4/b2_authorize_account",
        headers={"Authorization": f"Basic {basic}"},
    )
    storage = auth.get("apiInfo", {}).get("storageApi", {})
    api_url = str(storage.get("apiUrl", "")).rstrip("/")
    authorization = str(auth.get("authorizationToken", ""))
    account_id = str(auth.get("accountId", ""))
    if not api_url or not authorization or not account_id:
        raise RuntimeError("Backblaze Native API authorization response was incomplete")

    bucket_id = None
    allowed_buckets = storage.get("allowed", {}).get("buckets", [])
    if isinstance(allowed_buckets, list):
        for item in allowed_buckets:
            if isinstance(item, dict) and item.get("name") == bucket and item.get("id"):
                bucket_id = str(item["id"])
                break
    if not bucket_id:
        _, bucket_result = _request_json(
            f"{api_url}/b2api/v4/b2_list_buckets",
            method="POST",
            headers={"Authorization": authorization, "Content-Type": "application/json"},
            data=json.dumps({"accountId": account_id, "bucketName": bucket}).encode("utf-8"),
        )
        buckets = bucket_result.get("buckets", [])
        if isinstance(buckets, list):
            for item in buckets:
                if isinstance(item, dict) and item.get("bucketName") == bucket and item.get("bucketId"):
                    bucket_id = str(item["bucketId"])
                    break
    if not bucket_id:
        raise RuntimeError(f"Backblaze bucket not found or key cannot list bucket: {bucket}")

    _, upload_target = _request_json(
        f"{api_url}/b2api/v4/b2_get_upload_url",
        method="POST",
        headers={"Authorization": authorization, "Content-Type": "application/json"},
        data=json.dumps({"bucketId": bucket_id}).encode("utf-8"),
    )
    upload_url = str(upload_target.get("uploadUrl", ""))
    upload_authorization = str(upload_target.get("authorizationToken", ""))
    if not upload_url or not upload_authorization:
        raise RuntimeError("Backblaze did not return an upload target")

    payload = package.read_bytes()
    sha1 = hashlib.sha1(payload).hexdigest()
    encoded_name = urllib.parse.quote(relative_path, safe="")
    request = urllib.request.Request(
        upload_url,
        data=payload,
        headers={
            "Authorization": upload_authorization,
            "X-Bz-File-Name": encoded_name,
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(payload)),
            "X-Bz-Content-Sha1": sha1,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Backblaze Native API upload failed with HTTP {exc.code}: {detail}") from exc

    if int(result.get("contentLength", -1)) != len(payload):
        raise RuntimeError("Backblaze Native API upload verification failed: size mismatch")
    if str(result.get("contentSha1", "")).lower() != sha1:
        raise RuntimeError("Backblaze Native API upload verification failed: SHA-1 mismatch")
    return f"b2://{bucket}/{relative_path}"


def upload_cloud(package: Path, relative_path: str, provider: str) -> str:
    if provider in {"s3", "s3_compatible"}:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError

        bucket = settings.backup_s3_bucket.strip()
        endpoint = settings.backup_s3_endpoint.strip().rstrip("/")
        access_key = settings.backup_s3_access_key.strip()
        secret_key = settings.backup_s3_secret_key.strip()
        if not bucket:
            raise RuntimeError("BACKUP_S3_BUCKET is not configured")
        if not endpoint:
            raise RuntimeError("BACKUP_S3_ENDPOINT is not configured")
        if not access_key or not secret_key:
            raise RuntimeError("BACKUP_S3_ACCESS_KEY and BACKUP_S3_SECRET_KEY must be configured")

        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        region = settings.backup_s3_region.strip() or None
        payload = package.read_bytes()
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                retries={"mode": "standard", "total_max_attempts": 5},
                s3={"addressing_style": "path"},
            ),
        )
        try:
            client.put_object(
                Bucket=bucket,
                Key=relative_path,
                Body=payload,
                Metadata={"sha256": digest},
                ContentLength=len(payload),
            )
            remote = client.head_object(Bucket=bucket, Key=relative_path)
            remote_size = int(remote.get("ContentLength", -1))
            remote_digest = str(remote.get("Metadata", {}).get("sha256", "")).lower()
            if remote_size != len(payload):
                raise RuntimeError(f"S3 upload verification failed: size {remote_size} != local {len(payload)}")
            if remote_digest != digest:
                raise RuntimeError("S3 upload verification failed: SHA-256 metadata mismatch")
            return f"s3://{bucket}/{relative_path}"
        except ClientError as exc:
            raise RuntimeError(f"Backblaze B2 S3 upload failed: {exc}") from exc
        except (BotoCoreError, OSError) as exc:
            try:
                return _b2_native_upload(package, relative_path, bucket, access_key, secret_key)
            except Exception as native_exc:
                raise RuntimeError(f"Backblaze B2 upload failed over S3 and Native API fallback: S3={exc}; Native={native_exc}") from native_exc
        except RuntimeError as exc:
            raise RuntimeError(f"Backblaze B2 S3 upload failed: {exc}") from exc
    if provider in {"google_drive", "gdrive", "google"}:
        return _google_upload(package, relative_path)
    if provider in {"onedrive", "one_drive", "microsoft"}:
        return _onedrive_upload(package, relative_path)
    raise RuntimeError(f"Unsupported backup cloud provider: {provider}")
