from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import allowed_methods, authenticate_password, create_pending, verify_pending
from app.config import settings
from app.database import Base, engine, get_db
from app.models import AuditEvent, User
from app.security import hash_password
import app.models  # noqa: F401

app = FastAPI(title="MetroCRM", version="0.2.0")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, max_age=settings.session_max_age, https_only=settings.environment == "production", same_site="lax")
templates = Jinja2Templates(directory="app/templates")

@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/auth/setup")
def setup(username: str = Form(...), password: str = Form(...), role: str = Form("SUPER_ADMIN"), security_question: str = Form(""), security_answer: str = Form(""), db: Session = Depends(get_db)):
    if db.scalar(select(User.id).limit(1)) is not None:
        return JSONResponse({"error": "setup_already_completed"}, status_code=409)
    role = role.upper()
    if role != "SUPER_ADMIN":
        return JSONResponse({"error": "first_setup_must_create_super_admin"}, status_code=400)
    if not security_question.strip() or not security_answer.strip():
        return JSONResponse({"error": "super_admin_security_question_required"}, status_code=400)
    user = User(username=username.strip(), password_hash=hash_password(password), role=role, security_question=security_question.strip(), security_answer_hash=hash_password(security_answer.strip()), is_active=True, is_approved=True)
    db.add(user); db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/auth/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), method: str = Form(...), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == username.strip()))
    if not authenticate_password(user, password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password."}, status_code=401)
    methods = allowed_methods(user.role)
    if method not in methods:
        return templates.TemplateResponse("login.html", {"request": request, "error": "This verification method is not allowed for your role."}, status_code=403)
    token, otp = create_pending(user, method)
    request.session["pending_token"] = token
    destination = "registered mobile" if method == "mobile_otp" else "registered email" if method == "email_otp" else None
    if method == "security_question":
        return templates.TemplateResponse("verify.html", {"request": request, "token": token, "method": "Security Question", "destination": user.security_question, "test_otp": None})
    if method == "approval":
        return JSONResponse({"status": "approval_required", "message": "Authorized approver must approve this login request."}, status_code=202)
    return templates.TemplateResponse("verify.html", {"request": request, "token": token, "method": method.replace("_", " ").title(), "destination": destination, "test_otp": otp if settings.environment != "production" else None})

@app.post("/auth/verify")
def verify(request: Request, token: str = Form(...), value: str = Form(...), db: Session = Depends(get_db)):
    user_id = verify_pending(token, value.strip(), settings.otp_expiry_seconds, settings.otp_max_attempts)
    if not user_id:
        return JSONResponse({"error": "verification_failed"}, status_code=401)
    user = db.get(User, user_id)
    if not user or not user.is_active:
        return JSONResponse({"error": "account_disabled"}, status_code=403)
    request.session.clear(); request.session["user_id"] = user.id; request.session["session_version"] = user.session_version
    db.add(AuditEvent(actor_user_id=user.id, action="LOGIN_SUCCESS", entity_type="User", entity_id=str(user.id), details="Second-factor verification completed")); db.commit()
    return RedirectResponse("/dashboard", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id: return RedirectResponse("/", status_code=303)
    user = db.get(User, user_id)
    if not user or user.session_version != request.session.get("session_version"):
        request.session.clear(); return RedirectResponse("/", status_code=303)
    return HTMLResponse(f"<html><body><h1>MetroCRM Dashboard</h1><p>Welcome, {user.username}</p><p>Role: {user.role}</p><p><a href='/auth/logout'>Logout</a></p></body></html>")

@app.get("/auth/logout")
def logout(request: Request):
    request.session.clear(); return RedirectResponse("/", status_code=303)
