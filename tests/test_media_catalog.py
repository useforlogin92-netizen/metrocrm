from __future__ import annotations

from app.catalog_models import PropertyMedia
from app.models import Developer, Project
from app.routers.catalog_sharing import CatalogShareRequest, _payload


def _project(db_session, name: str) -> Project:
    developer = Developer(name=f"{name} Developer")
    db_session.add(developer)
    db_session.flush()
    project = Project(developer_id=developer.id, name=name, city="Mumbai", locality="Kandivali East")
    db_session.add(project)
    db_session.flush()
    return project


def test_catalog_share_only_includes_shareable_media_bound_to_requested_project(db_session):
    project_a = _project(db_session, "Project A")
    project_b = _project(db_session, "Project B")
    allowed = PropertyMedia(project_id=project_a.id, media_type="PROPERTY_IMAGE", title="Allowed", file_url="/media/property/a.jpg", is_shareable=True)
    private = PropertyMedia(project_id=project_a.id, media_type="PROPERTY_IMAGE", title="Private", file_url="/media/property/private.jpg", is_shareable=False)
    other = PropertyMedia(project_id=project_b.id, media_type="PROPERTY_IMAGE", title="Other", file_url="/media/property/b.jpg", is_shareable=True)
    db_session.add_all([allowed, private, other])
    db_session.commit()

    request = CatalogShareRequest(
        property_data={"project": project_a.name},
        selected_media_ids=[str(allowed.id), str(private.id), str(other.id)],
        media=[
            {"id": str(allowed.id), "url": allowed.file_url},
            {"id": str(private.id), "url": private.file_url},
            {"id": str(other.id), "url": other.file_url},
        ],
        project_id=project_a.id,
    )
    payload = _payload(request, db_session)

    assert [item["id"] for item in payload["media"]] == [str(allowed.id)]
    assert payload["media"][0]["url"] == "/media/property/a.jpg"


def test_catalog_share_does_not_trust_client_supplied_media_when_selection_is_empty(db_session):
    project = _project(db_session, "Project")
    request = CatalogShareRequest(
        property_data={"project": project.name},
        selected_media_ids=[],
        media=[{"id": "attacker", "url": "https://attacker.example/secret.jpg", "internal_only": False}],
        project_id=project.id,
    )
    payload = _payload(request, db_session)
    assert payload["media"] == []
