from __future__ import annotations

from fastapi.responses import HTMLResponse

from app.models import Developer, Project
from app.routers.caller_search import _project_level_rows
from app.routers.property_data_super_admin import _inject_project_selection


def test_caller_search_includes_project_without_units(db_session):
    developer = Developer(name="Test Developer")
    db_session.add(developer)
    db_session.flush()
    db_session.add(
        Project(
            developer_id=developer.id,
            name="Project Only Property",
            city="Mumbai",
            locality="Andheri East",
            construction_status="READY_TO_MOVE",
            description="2 BHK | 700 sq.ft",
        )
    )
    db_session.commit()

    rows = _project_level_rows(db_session, "Mumbai")

    assert len(rows) == 1
    assert rows[0]["project"] == "Project Only Property"
    assert rows[0]["property_type"] == "Project"
    assert rows[0]["locality"] == "Andheri East"


def test_super_admin_property_page_has_select_all_and_delete_controls():
    html = (
        '<html><body><h3>Projects Records</h3>'
        '<table class="pd-table"><thead><tr><th>ID</th><th>Primary Details</th><th>Action</th></tr></thead><tbody>'
        '<tr><td>253</td><td><b>Siddha Sky</b><br>Mumbai Andheri East</td>'
        '<td><a class="pd-btn" href="/super-admin/property-data?entity=Projects&amp;id=253">Edit</a></td></tr>'
        '</tbody></table></body></html>'
    )
    response = _inject_project_selection(HTMLResponse(html))
    body = response.body.decode("utf-8")

    assert 'id="property-select-all"' in body
    assert 'name="project_ids" value="253"' in body
    assert "/super-admin/property-data/delete-selected" in body
    assert "Delete Selected" in body
