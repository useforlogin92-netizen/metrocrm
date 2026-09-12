"""Super Admin-only route for deleting the explicitly seeded Godrej Nest test property."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.database import get_db
from app.models import AuditEvent, User
from tools.seed_godrej_nest_test import delete_godrej_nest_test

router = APIRouter(tags=["godrej-test-property"])


def _user(request: Request, db: Session) -> User | None:
    from app.main import _current_user
    return _current_user(request, db)


@router.post("/super-admin/property-data/delete-godrej-nest", dependencies=[Depends(require_csrf)])
def delete_godrej_nest_test_route(request: Request, db: Session = Depends(get_db)):
    actor = _user(request, db)
    if not actor or actor.role != "SUPER_ADMIN":
        return RedirectResponse("/dashboard", status_code=303)
    try:
        project_id, tower_count, unit_count, media_count = delete_godrej_nest_test(db)
        if project_id is None:
            return RedirectResponse(
                "/super-admin/property-data?entity=Projects&message=Godrej+Nest+test+property+was+not+found",
                status_code=303,
            )
        db.add(AuditEvent(
            actor_user_id=actor.id,
            action="GODREJ_NEST_TEST_DATA_DELETED",
            entity_type="Projects",
            entity_id=str(project_id),
            details=json.dumps({
                "towers": tower_count,
                "units": unit_count,
                "media": media_count,
                "scope": "Mumbai + Kandivali East + RERA P51800022159",
            }),
        ))
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse(
            "/super-admin/property-data?entity=Projects&error=Godrej+Nest+test+data+delete+failed%3A+"
            + str(exc).replace(" ", "+")[:300],
            status_code=303,
        )
    return RedirectResponse(
        f"/super-admin/property-data?entity=Projects&message=Godrej+Nest+test+property+deleted+%28project+%23{project_id}%2C+{tower_count}+towers%2C+{unit_count}+units%2C+{media_count}+media%29",
        status_code=303,
    )
