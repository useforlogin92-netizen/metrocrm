"""Guarded cleanup for the explicitly seeded Godrej Nest test inventory."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.csrf import require_csrf
from app.database import get_db
from app.catalog_models import CatalogShare, CatalogShareVisit, PropertyMedia, PropertySocialProfile, SalesPropertySubmission
from app.models import Booking, Commission, Developer, NearbyLocation, Project, SiteVisit, Token, Tower, Unit

router = APIRouter(tags=["godrej-test-admin"])


def _user(request: Request, db: Session):
    from app.main import _current_user
    return _current_user(request, db)


@router.post("/super-admin/property-data/delete-godrej-nest", dependencies=[Depends(require_csrf)])
def delete_godrej_nest_test_data(request: Request, db: Session = Depends(get_db)):
    """Delete only the known Godrej Nest test project and every linked test record."""
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
        project_id = project.id
        unit_ids = [u.id for u in db.scalars(select(Unit.id).where(Unit.project_id == project_id)).all()]

        # Delete dependent records before the project/unit rows so PostgreSQL FKs cannot block cleanup.
        booking_ids = [b.id for b in db.scalars(select(Booking.id).where(Booking.project_id == project_id)).all()]
        if booking_ids:
            deleted += db.execute(delete(Commission).where(Commission.booking_id.in_(booking_ids))).rowcount or 0
            deleted += db.execute(delete(Booking).where(Booking.id.in_(booking_ids))).rowcount or 0

        deleted += db.execute(delete(SiteVisit).where(or_(SiteVisit.project_id == project_id, SiteVisit.unit_id.in_(unit_ids) if unit_ids else False))).rowcount or 0
        deleted += db.execute(delete(Token).where(or_(Token.project_id == project_id, Token.unit_id.in_(unit_ids) if unit_ids else False))).rowcount or 0

        share_ids = [s.id for s in db.scalars(
            select(CatalogShare.id).where(
                or_(CatalogShare.project_id == project_id, CatalogShare.unit_id.in_(unit_ids) if unit_ids else False)
            )
        ).all()]
        if share_ids:
            deleted += db.execute(delete(CatalogShareVisit).where(CatalogShareVisit.share_id.in_(share_ids))).rowcount or 0
            deleted += db.execute(delete(CatalogShare).where(CatalogShare.id.in_(share_ids))).rowcount or 0

        deleted += db.execute(delete(PropertyMedia).where(or_(PropertyMedia.project_id == project_id, PropertyMedia.unit_id.in_(unit_ids) if unit_ids else False))).rowcount or 0
        deleted += db.execute(delete(PropertySocialProfile).where(PropertySocialProfile.project_id == project_id)).rowcount or 0
        deleted += db.execute(delete(SalesPropertySubmission).where(SalesPropertySubmission.property_type == "Projects", SalesPropertySubmission.record_id == project_id)).rowcount or 0
        deleted += db.execute(delete(NearbyLocation).where(NearbyLocation.project_id == project_id)).rowcount or 0
        deleted += db.execute(delete(Unit).where(Unit.project_id == project_id)).rowcount or 0
        deleted += db.execute(delete(Tower).where(Tower.project_id == project_id)).rowcount or 0

        developer_id = project.developer_id
        db.delete(project)
        deleted += 1
        db.flush()

        # Remove the test developer only when it is now orphaned; never affect another project.
        if developer_id is not None:
            remaining = db.scalar(select(Project.id).where(Project.developer_id == developer_id).limit(1))
            if remaining is None:
                developer = db.get(Developer, developer_id)
                if developer:
                    db.delete(developer)
                    deleted += 1

    db.commit()
    return RedirectResponse(
        f"/super-admin/property-data?entity=Projects&message=Godrej+Nest+test+property+deleted+%28{deleted}+records%29",
        status_code=303,
    )
