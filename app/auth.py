from dataclasses import dataclass
from time import time
from typing import Literal

from app.security import generate_otp, otp_is_valid, verify_password

VerificationMethod = Literal["mobile_otp", "email_otp", "security_question", "approval"]

@dataclass
class PendingVerification:
    user_id: int
    method: VerificationMethod
    otp: str | None
    created_at: float
    expected_answer_hash: str | None = None
    attempts: int = 0

_pending: dict[str, PendingVerification] = {}


def allowed_methods(role: str) -> list[VerificationMethod]:
    role = role.upper()
    if role == "SUPER_ADMIN":
        return ["mobile_otp", "email_otp", "security_question"]
    if role == "ADMIN":
        return ["mobile_otp", "email_otp", "approval"]
    return ["mobile_otp", "email_otp", "approval"]


def authenticate_password(user, password: str) -> bool:
    return bool(user and user.is_active and verify_password(password, user.password_hash))


def create_pending(user, method: VerificationMethod, otp: str | None = None) -> tuple[str, str | None]:
    challenge = otp if method in ("mobile_otp", "email_otp") else None
    token = generate_otp() + str(user.id) + str(int(time()))
    expected = user.security_answer_hash if method == "security_question" else None
    if method == "approval" and not user.is_approved:
        raise ValueError("approval_not_granted")
    _pending[token] = PendingVerification(user.id, method, challenge, time(), expected)
    return token, challenge


def pending_method(token: str) -> VerificationMethod | None:
    pending = _pending.get(token)
    return pending.method if pending else None


def verify_pending(token: str, value: str, expiry_seconds: int, max_attempts: int) -> int | None:
    pending = _pending.get(token)
    if not pending or not otp_is_valid(pending.created_at, time(), expiry_seconds):
        _pending.pop(token, None)
        return None
    pending.attempts += 1
    if pending.attempts > max_attempts:
        _pending.pop(token, None)
        return None
    if pending.method in ("mobile_otp", "email_otp"):
        valid = value == pending.otp
    elif pending.method == "security_question":
        valid = bool(pending.expected_answer_hash) and verify_password(value, pending.expected_answer_hash)
    else:
        valid = value.strip().upper() == "APPROVED"
    if not valid:
        return None
    _pending.pop(token, None)
    return pending.user_id
