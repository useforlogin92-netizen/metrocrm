from __future__ import annotations

from datetime import datetime

from app.models import AuditEvent, Developer, Project, SiteVisit, Unit, User
from app.property_management_ui import PropertyManagementUIMiddleware
from app.routers.property_management_security import _activity_rows, _delete_project


def test_project_delete_removes_property_only_records(db_session):
    developer = Developer(name="Test Developer")
    db_session.add(developer)
    db_session.flush()
    project = Project(developer_id=developer.id, name="Disposable Property", city="Mumbai")
    db_session.add(project)
    db_session.flush()
    db_session.add(Unit(project_id=project.id, unit_number="101", bhk="2 BHK"))
    db_session.commit()

    deleted, counts, error = _delete_project(db_session, project.id)
    assert error is None
    assert deleted is project
    assert counts["project"] == 1
    assert counts["units"] == 1
    db_session.commit()
    assert db_session.get(Project, project.id) is None
    assert db_session.query(Unit).filter(Unit.project_id == project.id).count() == 0


def test_project_delete_is_blocked_by_business_records(db_session):
    developer = Developer(name="Test Developer")
    db_session.add(developer)
    db_session.flush()
    project = Project(developer_id=developer.id, name="Booked Property", city="Mumbai")
    db_session.add(project)
    db_session.flush()
    db_session.add(
        SiteVisit(
            project_id=project.id,
            scheduled_at=datetime.now(),
            status="SCHEDULED",
        )
    )
    db_session.commit()

    deleted, counts, error = _delete_project(db_session, project.id)
    assert deleted is None
    assert counts == {}
    assert "site visits" in error
    db_session.rollback()
    assert db_session.get(Project, project.id) is project


def test_activity_rows_can_hide_admin_and_super_admin_for_admin_scope(db_session):
    super_admin = User(username="sa", password_hash="x", role="SUPER_ADMIN")
    admin = User(username="admin", password_hash="x", role="ADMIN")
    staff = User(username="staff", password_hash="x", role="USER")
    db_session.add_all([super_admin, admin, staff])
    db_session.flush()
    db_session.add_all(
        [
            AuditEvent(actor_user_id=super_admin.id, action="SA_ACTION"),
            AuditEvent(actor_user_id=admin.id, action="ADMIN_ACTION"),
            AuditEvent(actor_user_id=staff.id, action="STAFF_ACTION"),
        ]
    )
    db_session.commit()

    rows = _activity_rows(db_session, admin_scope=True)
    assert [row["action"] for row in rows] == ["STAFF_ACTION"]


def test_property_management_ui_injects_delete_and_activity_controls():
    html = """
    <html><body>
      <aside class="sidebar"><nav class="nav"><a href="/dashboard">Dashboard</a></nav></aside>
      <div class="profile-role">SUPER_ADMIN</div>
      <table class="pd-table"><tbody>
        <tr><td>42</td><td>Example Property</td><td><a class="pd-btn" href="/super-admin/property-data?entity=Projects&amp;id=42">Edit</a></td></tr>
      </tbody></table>
      <input type="hidden" name="csrf_token" value="csrf-value">
    </body></html>
    """
    rendered = PropertyManagementUIMiddleware._inject(html, "/super-admin/property-data")
    assert "User Activity & Audit" in rendered
    assert "projects/'+id+'/delete" in rendered
    assert "const base=location.pathname.startsWith('/super-admin/')" in rendered
    assert "csrf_token" in rendered
