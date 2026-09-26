from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from app import models  # noqa: F401
from app.trusted_device import (
    DEVICE_NAME,
    has_trusted_device,
    verify_signature_for_test,
)
from app.trusted_device_models import TrustedDevice


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _jwk(public_key) -> dict:
    numbers = public_key.public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url(numbers.x.to_bytes(32, "big")),
        "y": _b64url(numbers.y.to_bytes(32, "big")),
        "alg": "ES256",
        "key_ops": ["verify"],
    }


def _raw_signature(private_key, challenge: str) -> str:
    der = private_key.sign(challenge.encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return _b64url(raw)


def test_trusted_device_table_is_registered():
    assert "trusted_devices" in TrustedDevice.metadata.tables


def test_non_extractable_device_signature_contract_round_trips():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = _jwk(private_key.public_key())
    challenge = "metrocrm-device-challenge"
    signature = _raw_signature(private_key, challenge)

    assert verify_signature_for_test(public_jwk, challenge, signature) is True
    assert verify_signature_for_test(public_jwk, challenge + "-tampered", signature) is False


def test_trusted_device_is_bound_to_the_super_admin_user(db_session):
    from app.models import User

    user = User(
        username="satyapal",
        password_hash="test",
        role="SUPER_ADMIN",
        is_active=True,
        is_approved=True,
        session_version=1,
    )
    db_session.add(user)
    db_session.commit()

    device = TrustedDevice(
        user_id=user.id,
        device_name=DEVICE_NAME,
        public_key_jwk=json.dumps(_jwk(ec.generate_private_key(ec.SECP256R1()).public_key())),
        status="ACTIVE",
    )
    db_session.add(device)
    db_session.commit()

    class SessionStub:
        def get(self, key):
            return {
                "user_id": user.id,
                "session_version": user.session_version,
                "trusted_device_id": device.id,
            }.get(key)

    class RequestStub:
        session = SessionStub()

    assert has_trusted_device(RequestStub(), db_session) is True


def test_inactive_device_does_not_grant_trusted_access(db_session):
    from app.models import User

    user = User(
        username="satyapal2",
        password_hash="test",
        role="SUPER_ADMIN",
        is_active=True,
        is_approved=True,
        session_version=1,
    )
    db_session.add(user)
    db_session.commit()

    device = TrustedDevice(
        user_id=user.id,
        device_name=DEVICE_NAME,
        public_key_jwk="{}",
        status="REVOKED",
    )
    db_session.add(device)
    db_session.commit()

    class SessionStub:
        def get(self, key):
            return {
                "user_id": user.id,
                "session_version": user.session_version,
                "trusted_device_id": device.id,
            }.get(key)

    class RequestStub:
        session = SessionStub()

    assert has_trusted_device(RequestStub(), db_session) is False
