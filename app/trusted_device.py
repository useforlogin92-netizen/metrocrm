"""Trusted-device gate for the MetroCRM Super Admin portal.

The privileged browser session is unlocked only after a cryptographic
challenge is signed by a non-extractable browser key registered to the
Super Admin account. Registration itself requires a deployment secret.
"""

from __future__ import annotations

import base64
import json
import secrets
import time
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import main
from app.config import settings
from app.csrf import csrf_token, require_csrf_header
from app.database import SessionLocal, get_db
from app.models import AuditEvent, User
from app.trusted_device_models import TrustedDevice

app = main.app

DEVICE_NAME = "Satyapal Yadav PC"
CHALLENGE_KEY = "trusted_device_challenge"
CHALLENGE_EXPIRES = 120
DEVICE_SESSION_KEY = "trusted_device_id"
ENROLLMENT_CODE = "trusted_device_enrollment_code"

PUBLIC_PATHS = {
    "/super-admin/login",
    "/auth/super-admin/login",
    "/super-admin/device-required",
    "/super-admin/device/challenge",
    "/super-admin/device/register",
    "/super-admin/device/verify",
    "/auth/logout",
}


def _b64url_decode(value: str) -> bytes:
    value = value.strip()
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _public_key_from_jwk(jwk: dict):
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise ValueError("unsupported_public_key")
    x = int.from_bytes(_b64url_decode(str(jwk["x"])), "big")
    y = int.from_bytes(_b64url_decode(str(jwk["y"])), "big")
    return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()


def _validate_jwk(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("invalid_public_key")
    key = {
        "kty": raw.get("kty"),
        "crv": raw.get("crv"),
        "x": raw.get("x"),
        "y": raw.get("y"),
        "alg": raw.get("alg", "ES256"),
    }
    if not all(isinstance(key.get(item), str) and key[item] for item in ("kty", "crv", "x", "y")):
        raise ValueError("invalid_public_key")
    _public_key_from_jwk(key)
    return key


def _current_super_admin(request: Request, db: Session) -> User | None:
    user = main._current_user(request, db)
    return user if user and user.role.upper() == "SUPER_ADMIN" else None


def _active_device(db: Session, user_id: int, device_id: int | None) -> TrustedDevice | None:
    if not device_id:
        return None
    device = db.get(TrustedDevice, int(device_id))
    if not device or device.user_id != user_id or device.status != "ACTIVE":
        return None
    return device


def has_trusted_device(request: Request, db: Session) -> bool:
    user = main._current_user(request, db)
    if not user or user.role.upper() != "SUPER_ADMIN":
        return False
    return _active_device(db, user.id, request.session.get(DEVICE_SESSION_KEY)) is not None


def _set_challenge(request: Request) -> str:
    challenge = _b64url_encode(secrets.token_bytes(32))
    request.session[CHALLENGE_KEY] = {"value": challenge, "expires_at": time.time() + CHALLENGE_EXPIRES}
    return challenge


def _get_challenge(request: Request) -> str | None:
    item = request.session.get(CHALLENGE_KEY)
    if not isinstance(item, dict):
        return None
    if float(item.get("expires_at", 0)) < time.time():
        request.session.pop(CHALLENGE_KEY, None)
        return None
    return str(item.get("value") or "")


def _clear_challenge(request: Request) -> None:
    request.session.pop(CHALLENGE_KEY, None)


def _audit(db: Session, user: User, action: str, device: TrustedDevice | None, request: Request, details: dict | None = None) -> None:
    payload = dict(details or {})
    if device:
        payload.update({"device_id": device.id, "device_name": device.device_name})
    db.add(
        AuditEvent(
            actor_user_id=user.id,
            action=action,
            entity_type="TrustedDevice",
            entity_id=str(device.id) if device else None,
            details=json.dumps(payload),
        )
    )


@app.middleware("http")
async def enforce_trusted_super_admin_device(request: Request, call_next):
    """Block privileged Super Admin requests before their handlers execute."""
    if request.session.get("login_portal") == "super_admin":
        path = request.url.path
        is_public = path in PUBLIC_PATHS or path.startswith("/static/")
        if not is_public:
            try:
                with SessionLocal() as db:
                    user = main._current_user(request, db)
                    if user and user.role.upper() == "SUPER_ADMIN":
                        if not has_trusted_device(request, db):
                            target = request.url.path
                            if request.url.query:
                                target += "?" + request.url.query
                            return RedirectResponse(
                                "/super-admin/device-required?next=" + _b64url_encode(target.encode("utf-8")),
                                status_code=303,
                            )
            except Exception:
                # Security boundary must fail closed.
                return HTMLResponse(
                    "<h1>MetroCRM</h1><p>Super Admin access is temporarily blocked because device authorization could not be verified.</p>",
                    status_code=503,
                )
    return await call_next(request)


@app.get("/super-admin/device-required", response_class=HTMLResponse)
def trusted_device_required(request: Request, db: Session = Depends(get_db)):
    user = _current_super_admin(request, db)
    if not user:
        return RedirectResponse("/super-admin/login", status_code=303)
    if has_trusted_device(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    code_configured = bool(settings.trusted_device_enrollment_code.strip())
    token = csrf_token(request)
    return main.templates.TemplateResponse(
        request,
        "trusted_device_required.html",
        {
            "request": request,
            "username": user.username,
            "device_name": DEVICE_NAME,
            "csrf_token": token,
            "enrollment_configured": code_configured,
        },
    )


@app.get("/super-admin/device/challenge")
def trusted_device_challenge(request: Request, db: Session = Depends(get_db)):
    user = _current_super_admin(request, db)
    if not user:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    challenge = _set_challenge(request)
    return JSONResponse({"challenge": challenge, "expires_in": CHALLENGE_EXPIRES})


@app.post("/super-admin/device/register", dependencies=[Depends(require_csrf_header)])
async def register_trusted_device(request: Request, db: Session = Depends(get_db)):
    user = _current_super_admin(request, db)
    if not user:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    configured = settings.trusted_device_enrollment_code.strip()
    if not configured:
        return JSONResponse({"error": "device_enrollment_not_configured"}, status_code=503)

    body = await request.json()
    supplied_code = str(body.get("enrollment_code") or "")
    if not secrets.compare_digest(supplied_code, configured):
        _audit(db, user, "TRUSTED_DEVICE_ENROLLMENT_REJECTED", None, request, {"reason": "invalid_enrollment_code"})
        db.commit()
        return JSONResponse({"error": "invalid_enrollment_code"}, status_code=403)

    active = db.scalar(
        select(TrustedDevice).where(
            TrustedDevice.user_id == user.id,
            TrustedDevice.status == "ACTIVE",
        ).limit(1)
    )
    if active:
        return JSONResponse({"error": "trusted_device_already_registered"}, status_code=409)

    try:
        jwk = _validate_jwk(body.get("public_key"))
    except (KeyError, TypeError, ValueError, OverflowError):
        return JSONResponse({"error": "invalid_public_key"}, status_code=400)

    device = TrustedDevice(
        user_id=user.id,
        device_name=DEVICE_NAME,
        public_key_jwk=json.dumps(jwk, separators=(",", ":")),
        status="ACTIVE",
        last_seen_at=datetime.now(timezone.utc).replace(tzinfo=None),
        last_ip=request.client.host if request.client else None,
    )
    db.add(device)
    db.flush()
    request.session[DEVICE_SESSION_KEY] = device.id
    _audit(db, user, "TRUSTED_DEVICE_REGISTERED", device, request)
    db.commit()
    return JSONResponse({"status": "registered", "device_id": device.id, "device_name": DEVICE_NAME})


@app.post("/super-admin/device/verify", dependencies=[Depends(require_csrf_header)])
async def verify_trusted_device(request: Request, db: Session = Depends(get_db)):
    user = _current_super_admin(request, db)
    if not user:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    body = await request.json()
    try:
        device = _active_device(db, user.id, int(body.get("device_id")))
    except (TypeError, ValueError):
        device = None
    challenge = _get_challenge(request)
    if not device or not challenge:
        return JSONResponse({"error": "device_challenge_expired"}, status_code=403)

    try:
        signature = _b64url_decode(str(body.get("signature") or ""))
        if len(signature) != 64:
            raise ValueError("invalid_signature")
        raw = json.loads(device.public_key_jwk)
        public_key = _public_key_from_jwk(raw)
        r = int.from_bytes(signature[:32], "big")
        s = int.from_bytes(signature[32:], "big")
        der_signature = encode_dss_signature(r, s)
        public_key.verify(
            der_signature,
            challenge.encode("utf-8"),
            ec.ECDSA(hashes.SHA256()),
        )
    except Exception:
        _audit(db, user, "TRUSTED_DEVICE_VERIFICATION_FAILED", device, request)
        db.commit()
        _clear_challenge(request)
        return JSONResponse({"error": "device_verification_failed"}, status_code=403)

    request.session[DEVICE_SESSION_KEY] = device.id
    device.last_seen_at = datetime.now(timezone.utc).replace(tzinfo=None)
    device.last_ip = request.client.host if request.client else None
    _audit(db, user, "TRUSTED_DEVICE_VERIFIED", device, request)
    db.commit()
    _clear_challenge(request)
    return JSONResponse({"status": "verified", "device_name": device.device_name})


@app.post("/super-admin/device/revoke", dependencies=[Depends(require_csrf_header)])
async def revoke_trusted_device(request: Request, db: Session = Depends(get_db)):
    user = _current_super_admin(request, db)
    if not user:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await request.json()
    try:
        device = _active_device(db, user.id, int(body.get("device_id")))
    except (TypeError, ValueError):
        device = None
    if not device:
        return JSONResponse({"error": "device_not_found"}, status_code=404)
    device.status = "REVOKED"
    request.session.pop(DEVICE_SESSION_KEY, None)
    _audit(db, user, "TRUSTED_DEVICE_REVOKED", device, request)
    db.commit()
    return JSONResponse({"status": "revoked"})


def verify_signature_for_test(public_jwk: dict, challenge: str, signature_b64url: str) -> bool:
    """Small pure helper used by regression tests."""
    signature = _b64url_decode(signature_b64url)
    if len(signature) != 64:
        return False
    public_key = _public_key_from_jwk(public_jwk)
    der_signature = encode_dss_signature(
        int.from_bytes(signature[:32], "big"),
        int.from_bytes(signature[32:], "big"),
    )
    try:
        public_key.verify(der_signature, challenge.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        return True
    except Exception:
        return False
