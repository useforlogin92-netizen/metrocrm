"""Compatibility and dedicated Super Admin user-creation routes.

The legacy create operation remains POST-only at /admin/users/create. A
Super Admin now gets a dedicated create endpoint so accounts created by the
final authority are immediately approved and do not enter an approval queue.
"""
from fastapi import Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import main
from app.csrf import require_csrf
from app.database import get_db
from app.models import User
from app.security import hash_password

app = main.app


@app.get("/admin/users/create")
def admin_users_create_page(request: Request):
    """Open the existing user-management page instead of exposing a POST URL."""
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/super-admin/users/create", dependencies=[Depends(require_csrf)])
def super_admin_create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    mobile: str = Form(""),
    email: str = Form(""),
    category: str = Form(""),
    team: str = Form(""),
    manager_id: str = Form(""),
    security_question: str = Form(""),
    security_answer: str = Form(""),
    db: Session = Depends(get_db),
):
    """Create a fully enabled, approved account when the actor is Super Admin."""
    actor = main._current_user(request, db)
    role = role.upper()
    if not actor or actor.role.upper() != "SUPER_ADMIN" or not main._can_manage_user(actor, target_role=role):
        return RedirectResponse("/admin/users?error=forbidden", status_code=303)
    if len(password) < 8 or not security_question.strip() or not security_answer.strip():
        return RedirectResponse("/admin/users?error=validation", status_code=303)
    manager = int(manager_id) if manager_id.isdigit() else None
    if not main._valid_reporting_manager(actor, manager, None, db):
        return RedirectResponse("/admin/users?error=manager", status_code=303)

    user = User(
        username=username.strip(),
        password_hash=hash_password(password),
        role=role,
        mobile=mobile.strip() or None,
        email=email.strip().lower() or None,
        category=category.strip() or None,
        team=team.strip() or None,
        reporting_manager_id=manager,
        security_question=security_question.strip(),
        security_answer_hash=hash_password(security_answer.strip()),
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    main._audit(db, actor.id, "USER_CREATED", user, {"role": role, "auto_approved": True})
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)
