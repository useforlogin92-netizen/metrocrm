from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from starlette.requests import Request

from app.models import AuditEvent, Booking, Commission, Customer, Developer, Lead, Project, User
from app.routers import commissions


def _request(path="/crm/advanced/commissions", method="GET"):
    return Request({"type": "http", "method": method, "path": path, "headers": [], "query_string": b"", "session": {}})


def _booking_fixture(db_session, employee, manager, customer_name="Commission Customer", sale_value="10000000"):
    customer = Customer(name=customer_name, mobile="9876501111")
    developer = Developer(name="Commission Developer")
    db_session.add_all([customer, developer])
    db_session.flush()
    project = Project(developer_id=developer.id, name="Commission Residency", city="Mumbai")
    db_session.add(project)
    db_session.flush()
    lead = Lead(customer_id=customer.id, source="WEBSITE", status="BOOKED", assigned_user_id=employee.id)
    db_session.add(lead)
    db_session.flush()
    booking = Booking(
        customer_id=customer.id, lead_id=lead.id, project_id=project.id, booking_date=datetime(2026, 10, 1),
        sale_value=Decimal(sale_value), booking_amount=Decimal("100000"), employee_id=employee.id,
        manager_id=manager.id if manager else None, status="BOOKED",
    )
    db_session.add(booking)
    db_session.commit()
    return booking, project, customer


def test_manager_can_create_audited_commission_from_booking_sale_value(db_session, monkeypatch):
    manager = User(username="commission-manager", password_hash="x", role="MANAGER", is_active=True, is_approved=True)
    db_session.add(manager)
    db_session.flush()
    employee = User(username="commission-sales-exec", password_hash="x", role="SALES_EXECUTIVE", reporting_manager_id=manager.id, is_active=True, is_approved=True)
    db_session.add(employee)
    db_session.flush()
    booking, project, _ = _booking_fixture(db_session, employee, manager)
    monkeypatch.setattr(commissions, "_actor", lambda request, db: manager)
    monkeypatch.setattr(commissions, "require_csrf", lambda request, token: None)

    response = commissions.create_commission(
        request=_request(method="POST"), booking_id=booking.id, commission_percent=Decimal("2.5"),
        amount=None, payable_amount=None, remarks="Developer confirmed", db=db_session,
    )

    record = db_session.query(Commission).one()
    event = db_session.query(AuditEvent).filter_by(action="COMMISSION_RECORD_CREATED").one()
    assert response.status_code == 303
    assert record.booking_id == booking.id
    assert record.project_id == project.id
    assert record.employee_id == employee.id
    assert record.amount == Decimal("250000.00")
    assert record.payable_amount == Decimal("250000.00")
    assert record.received_amount == Decimal("0.00")
    assert record.pending_amount == Decimal("250000.00")
    assert event.actor_user_id == manager.id
    assert event.entity_id == str(record.id)


def test_admin_can_record_partial_commission_receipt_and_overpayment_is_rejected(db_session, monkeypatch):
    admin = User(username="commission-admin", password_hash="x", role="ADMIN", is_active=True, is_approved=True)
    employee = User(username="commission-receipt-owner", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    db_session.add_all([admin, employee])
    db_session.flush()
    booking, project, _ = _booking_fixture(db_session, employee, admin, "Receipt Customer", "8000000")
    record = Commission(
        booking_id=booking.id, employee_id=employee.id, project_id=project.id, developer_id=project.developer_id,
        commission_percent=Decimal("2.5"), amount=Decimal("200000"), payable_amount=Decimal("180000"),
        received_amount=Decimal("30000"), pending_amount=Decimal("150000"),
    )
    db_session.add(record)
    db_session.commit()
    monkeypatch.setattr(commissions, "_actor", lambda request, db: admin)
    monkeypatch.setattr(commissions, "require_csrf", lambda request, token: None)

    overpayment = commissions.receive_commission_payment(
        record.id, _request("/crm/advanced/commissions/1/receive", "POST"), Decimal("150001"), db_session
    )
    assert overpayment.status_code == 400
    assert db_session.query(Commission).one().received_amount == Decimal("30000")

    response = commissions.receive_commission_payment(
        record.id, _request(f"/crm/advanced/commissions/{record.id}/receive", "POST"), Decimal("50000"), db_session
    )
    db_session.refresh(record)
    event = db_session.query(AuditEvent).filter_by(action="COMMISSION_PAYMENT_RECEIVED").one()
    assert response.status_code == 303
    assert record.received_amount == Decimal("80000.00")
    assert record.pending_amount == Decimal("100000.00")
    assert record.payment_date is not None
    assert event.actor_user_id == admin.id


def test_sales_executive_commission_register_is_scoped_to_own_bookings(db_session, monkeypatch):
    executive = User(username="commission-own-exec", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    other = User(username="commission-other-exec", password_hash="x", role="SALES_EXECUTIVE", is_active=True, is_approved=True)
    admin = User(username="commission-fixture-admin", password_hash="x", role="ADMIN", is_active=True, is_approved=True)
    db_session.add_all([executive, other, admin])
    db_session.flush()
    own_booking, own_project, own_customer = _booking_fixture(db_session, executive, admin, "Own Commission Customer", "5000000")
    other_booking, other_project, other_customer = _booking_fixture(db_session, other, admin, "Other Commission Customer", "7000000")
    db_session.add_all([
        Commission(booking_id=own_booking.id, employee_id=executive.id, project_id=own_project.id,
                   developer_id=own_project.developer_id, commission_percent=Decimal("2"), amount=Decimal("100000"),
                   payable_amount=Decimal("100000"), received_amount=Decimal("0"), pending_amount=Decimal("100000")),
        Commission(booking_id=other_booking.id, employee_id=other.id, project_id=other_project.id,
                   developer_id=other_project.developer_id, commission_percent=Decimal("2"), amount=Decimal("140000"),
                   payable_amount=Decimal("140000"), received_amount=Decimal("0"), pending_amount=Decimal("140000")),
    ])
    db_session.commit()
    monkeypatch.setattr(commissions, "_actor", lambda request, db: executive)
    monkeypatch.setattr(commissions, "csrf_token", lambda request: "test-csrf")

    response = commissions.commission_tracker(_request(), db_session)
    html = response.body.decode()

    assert response.status_code == 200
    assert "Own Commission Customer" in html
    assert "Other Commission Customer" not in html
    assert "Record Receipt" not in html
    assert "Record Expected Commission" not in html


def test_accountant_cannot_open_commission_register(db_session, monkeypatch):
    accountant = User(username="commission-accountant", password_hash="x", role="ACCOUNTANT", is_active=True, is_approved=True)
    db_session.add(accountant)
    db_session.commit()
    monkeypatch.setattr(commissions, "_actor", lambda request, db: accountant)

    response = commissions.commission_tracker(_request(), db_session)

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_commission_register_route_is_registered_on_live_app():
    from app.main_portal import app

    routes = {(getattr(route, "path", None), tuple(sorted(getattr(route, "methods", set()) or set()))) for route in app.routes}
    assert ("/crm/advanced/commissions", ("GET",)) in routes
    assert ("/crm/advanced/commissions", ("POST",)) in routes
    assert ("/crm/advanced/commissions/{commission_id}/receive", ("POST",)) in routes
