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


def _validate_csrf(request: Request, supplied: str) -> None:
    expected = request.session.get(CSRF_SESSION_KEY)
    if not expected or not supplied or not hmac.compare_digest(str(expected), str(supplied)):
        raise HTTPException(status_code=403, detail="csrf_validation_failed")


def require_csrf(request: Request, supplied: str = Form("", alias="csrf_token")) -> None:
    _validate_csrf(request, supplied)


def require_csrf_header(request: Request) -> None:
    """Validate the CSRF token carried by JSON requests in X-CSRF-Token."""
    _validate_csrf(request, request.headers.get("X-CSRF-Token", ""))



def require_csrf_either(request: Request, supplied: str = Form("", alias="csrf_token")) -> None:
    """Accept a form token or X-CSRF-Token for endpoints supporting both clients.

    If the header is present it takes precedence; an invalid header never falls
    back to a valid form field, preventing ambiguous token validation.
    """
    header_token = request.headers.get("X-CSRF-Token")
    token = header_token if header_token is not None else supplied
    _validate_csrf(request, token)
