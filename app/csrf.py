import hmac
import secrets

from fastapi import Form, HTTPException, Request

CSRF_SESSION_KEY = "csrf_token"


def csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


def require_csrf(request: Request, supplied: str = Form("", alias="csrf_token")) -> None:
    expected = request.session.get(CSRF_SESSION_KEY)
    if not expected or not supplied or not hmac.compare_digest(str(expected), str(supplied)):
        raise HTTPException(status_code=403, detail="csrf_validation_failed")
