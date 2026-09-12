"""Guarded cleanup for the explicitly seeded Godrej Nest test inventory."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.database import get_db
from app.catalog_models import CatalogShare, CatalogShareVisit, PropertyMedia, PropertySocialProfile
from app.models import NearbyLocation, Project, SiteVisit, Token, Tower, Unit

router = APIRouter(tags=["godrej-test-admin"])


def _user(request: Request, db: Session):
    from app.main import _current_user
    return _current_user(request, db)


@router.post("/super-admin/property-data/delete-godrej-nest", dependencies=[Depends(require_csrf)])
def delete_godrej_nest_test_data(request: Request, db: Session = Depends(get_db)):
    """Delete only the known Godrej Nest test project and records owned by it."""
    actor = _user(request, db)
    if not actor or actor.role != "SUPER_ADMIN":
        return RedirectResponse("/dashboard", status_code=303)

    projects = db.scalars(
        select(Project).where(
            Project.name == "Godrej Nest",
            Project.city == "Mumbai",
            Project.locality == "Kandivali East",
            Project.rera == "P51800022159",
        )
    ).all()
    if not projects:
        return RedirectResponse("/super-admin/property-data?entity=Projects&message=No+Godrej+Nest+test+property+found", status_code=303)

    deleted = 0
    for project in projects:
        unit_ids = [u.id for u in db.scalars(select(Unit).where(Unit.project_id == project.id)).all()]
        share_ids = [s.id for s in db.scalars(select(CatalogShare).where(CatalogShare.project_id == project.id)).all()]

        if share_ids:
            deleted += db.execute(delete(CatalogShareVisit).where(CatalogShareVisit.share_id.in_(share_ids))).rowcount or 0
        deleted += db.execute(delete(CatalogShare).where(CatalogShare.project_id == project.id)).rowcount or 0
        deleted += db.execute(delete(PropertyMedia).where(PropertyMedia.project_id == project.id)).rowcount or 0
        deleted += db.execute(delete(PropertySocialProfile).where(PropertySocialProfile.project_id == project.id)).rowcount or 0
        deleted += db.execute(delete(NearbyLocation).where(NearbyLocation.project_id == project.id)).rowcount or 0
        deleted += db.execute(delete(SiteVisit).where(SiteVisit.project_id == project.id)).rowcount or 0
        deleted += db.execute(delete(Token).where(Token.project_id == project.id)).rowcount or 0
        if unit_ids:
            deleted += db.execute(delete(Unit).where(Unit.id.in_(unit_ids))).rowcount or 0
        deleted += db.execute(delete(Tower).where(Tower.project_id == project.id)).rowcount or 0
        db.delete(project)
        deleted += 1

    db.commit()
    return RedirectResponse(
        f"/super-admin/property-data?entity=Projects&message=Godrej+Nest+test+property+deleted+%28{deleted}+records%29",
        status_code=303,
    )
