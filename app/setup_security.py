"""Bootstrap setup hardening for the first Super Admin account."""
from __future__ import annotations

import hmac
import secrets

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select

from app import main as main_module
from app.models import User
from app.security import hash_password

SETUP_CSRF_KEY = "initial_setup_csrf"
MIN_PASSWORD_LENGTH = 8
MAX_USERNAME_LENGTH = 100


def validate_setup_credentials(username: str, password: str, security_question: str, security_answer: str) -> str | None:
    username = username.strip()
    if not username or len(username) > MAX_USERNAME_LENGTH:
        return "invalid_username"
    if len(password) < MIN_PASSWORD_LENGTH:
        return "password_too_short"
    if not security_question.strip() or not security_answer.strip():
        return "super_admin_security_question_required"
    return None


def _setup_csrf(request: Request) -> str:
    token = request.session.get(SETUP_CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[SETUP_CSRF_KEY] = token
    return token


def _replace_setup_routes() -> None:
    main_module.app.router.routes[:] = [
        route for route in main_module.app.router.routes
        if getattr(route, "path", None) not in {"/setup", "/auth/setup"}
    ]

    @main_module.app.get("/setup", response_class=HTMLResponse)
    def secure_setup_page(request: Request):
        from app.database import SessionLocal
        with SessionLocal() as db:
            if db.scalar(select(User.id).limit(1)) is not None:
                return HTMLResponse("Setup has already been completed.", status_code=409)
        token = _setup_csrf(request)
        return HTMLResponse(f"""
        <!doctype html><html><head><title>MetroCRM Initial Setup</title>
        <meta name=viewport content=\"width=device-width,initial-scale=1\">
        <style>body{{font-family:Arial,sans-serif;background:#f5f7fb;display:flex;justify-content:center;padding:40px}}.card{{background:white;padding:28px;border-radius:12px;width:420px;box-shadow:0 4px 18px #0001}}label{{display:block;margin-top:14px;font-weight:600}}input{{width:100%;box-sizing:border-box;padding:10px;margin-top:6px;border:1px solid #bbb;border-radius:6px}}button{{width:100%;padding:12px;margin-top:22px;background:#2878e8;color:white;border:0;border-radius:6px;font-weight:600}}</style>
        </head><body><div class=card><h1>MetroCRM</h1><p>Create the first Super Admin account.</p>
        <form method=post action=\"/auth/setup\">
        <input type=hidden name=csrf_token value=\"{token}\">
        <label>Username</label><input name=username required maxlength=100 autocomplete=username>
        <label>Password</label><input name=password type=password required minlength=8 autocomplete=new-password>
        <label>Mobile (optional)</label><input name=mobile autocomplete=tel>
        <label>Email (optional)</label><input name=email type=email autocomplete=email>
        <label>Security Question</label><input name=security_question required>
        <label>Security Answer</label><input name=security_answer type=password required autocomplete=off>
        <input type=hidden name=role value=SUPER_ADMIN>
        <button type=submit>Create Super Admin</button></form></div></body></html>
        """)

    @main_module.app.post("/auth/setup")
    def secure_setup(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        role: str = Form("SUPER_ADMIN"),
        security_question: str = Form(""),
        security_answer: str = Form(""),
        mobile: str = Form(""),
        email: str = Form(""),
        csrf_token_value: str = Form("", alias="csrf_token"),
    ):
        expected = request.session.get(SETUP_CSRF_KEY)
        if not expected or not csrf_token_value or not hmac.compare_digest(str(expected), str(csrf_token_value)):
            return JSONResponse({"error": "csrf_validation_failed"}, status_code=403)
        from app.database import SessionLocal
        with SessionLocal() as db:
            if db.scalar(select(User.id).limit(1)) is not None:
                return JSONResponse({"error": "setup_already_completed"}, status_code=409)
            if role.upper() != "SUPER_ADMIN":
                return JSONResponse({"error": "first_setup_must_create_super_admin"}, status_code=400)
            error = validate_setup_credentials(username, password, security_question, security_answer)
            if error:
                return JSONResponse({"error": error}, status_code=400)
            user = User(
                username=username.strip(),
                password_hash=hash_password(password),
                role="SUPER_ADMIN",
                mobile=mobile.strip() or None,
                email=email.strip().lower() or None,
                security_question=security_question.strip(),
                security_answer_hash=hash_password(security_answer.strip()),
                is_active=True,
                is_approved=True,
            )
            db.add(user)
            db.commit()
        request.session.pop(SETUP_CSRF_KEY, None)
        return RedirectResponse("/", status_code=303)


_replace_setup_routes()
