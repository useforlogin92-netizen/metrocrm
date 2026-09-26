from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(40), index=True)
    category: Mapped[str | None] = mapped_column(String(80))
    team: Mapped[str | None] = mapped_column(String(100))
    reporting_manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    mobile: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    security_question: Mapped[str | None] = mapped_column(String(255))
    security_answer_hash: Mapped[str | None] = mapped_column(String(255))
    permissions_json: Mapped[str] = mapped_column(Text, default="{}")
    field_visibility_json: Mapped[str] = mapped_column(Text, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    mobile: Mapped[str | None] = mapped_column(String(30), index=True)
    alternate_mobile: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class CustomerRequirement(Base):
    __tablename__ = "customer_requirements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    buy_rent: Mapped[str | None] = mapped_column(String(20))
    property_category: Mapped[str | None] = mapped_column(String(30))
    locations_json: Mapped[str] = mapped_column(Text, default="[]")
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    bhk: Mapped[str | None] = mapped_column(String(50))
    property_type: Mapped[str | None] = mapped_column(String(100))
    carpet_area_min: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    carpet_area_max: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    possession_requirement: Mapped[str | None] = mapped_column(String(100))
    furnishing: Mapped[str | None] = mapped_column(String(50))
    parking: Mapped[str | None] = mapped_column(String(100))
    project_preference: Mapped[str | None] = mapped_column(Text)
    developer_preference: Mapped[str | None] = mapped_column(Text)
    loan_required: Mapped[bool] = mapped_column(Boolean, default=False)
    purpose: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    source: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(50), default="NEW", index=True)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    original_owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    requirement: Mapped[str | None] = mapped_column(Text)
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    preferred_location: Mapped[str | None] = mapped_column(Text)
    bhk: Mapped[str | None] = mapped_column(String(30))
    property_type: Mapped[str | None] = mapped_column(String(80))
    buy_rent: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class LeadAssignmentHistory(Base):
    __tablename__ = "lead_assignment_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    from_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class FollowUp(Base):
    __tablename__ = "followups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    assigned_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    purpose: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)

class Developer(Base):
    __tablename__ = "developers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    contact: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    developer_id: Mapped[int] = mapped_column(ForeignKey("developers.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    state: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100), index=True)
    locality: Mapped[str | None] = mapped_column(String(150), index=True)
    sector: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(Text)
    pincode: Mapped[str | None] = mapped_column(String(10), index=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    rera: Mapped[str | None] = mapped_column(String(100))
    possession_date: Mapped[datetime | None] = mapped_column(DateTime)
    builder_commitment_date: Mapped[datetime | None] = mapped_column(DateTime)
    construction_status: Mapped[str | None] = mapped_column(String(50))
    amenities_json: Mapped[str] = mapped_column(Text, default="[]")
    photos_json: Mapped[str] = mapped_column(Text, default="[]")
    brochure: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Tower(Base):
    __tablename__ = "towers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    floors: Mapped[int | None] = mapped_column(Integer)
    possession_date: Mapped[datetime | None] = mapped_column(DateTime)
    details: Mapped[str | None] = mapped_column(Text)

class Unit(Base):
    __tablename__ = "units"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    tower_id: Mapped[int | None] = mapped_column(ForeignKey("towers.id"), index=True)
    unit_number: Mapped[str] = mapped_column(String(50), index=True)
    floor: Mapped[int | None] = mapped_column(Integer)
    total_building_floors: Mapped[int | None] = mapped_column(Integer)
    bhk: Mapped[str | None] = mapped_column(String(50))
    property_type: Mapped[str | None] = mapped_column(String(100))
    carpet_area: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    built_up_area: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    super_built_up_area: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    plot_area: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    price_per_sqft: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    parking: Mapped[str | None] = mapped_column(String(100))
    facing: Mapped[str | None] = mapped_column(String(50))
    furnishing: Mapped[str | None] = mapped_column(String(50))
    possession: Mapped[str | None] = mapped_column(String(100))
    rera: Mapped[str | None] = mapped_column(String(100))
    availability: Mapped[str | None] = mapped_column(String(50), index=True)
    status: Mapped[str | None] = mapped_column(String(50), index=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    amenities_json: Mapped[str] = mapped_column(Text, default="[]")
    photos_json: Mapped[str] = mapped_column(Text, default="[]")
    floor_plan: Mapped[str | None] = mapped_column(String(500))
    brochure: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    other_details: Mapped[str | None] = mapped_column(Text)

class PropertyConfiguration(Base):
    """Project-level saleable configuration; one row per configuration/area combination."""
    __tablename__ = "property_configurations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    configuration: Mapped[str] = mapped_column(String(50), index=True)
    carpet_area: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    price_including_all: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    rate_per_sqft: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    bundle_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    negotiation: Mapped[str | None] = mapped_column(String(10))
    availability: Mapped[str | None] = mapped_column(String(50), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    source_details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class NearbyLocation(Base):
    __tablename__ = "nearby_locations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    category: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))
    distance: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[str | None] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)

class DataRequest(Base):
    __tablename__ = "data_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    entity_type: Mapped[str] = mapped_column(String(80))
    filters_json: Mapped[str] = mapped_column(Text, default="{}")
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    approval_reason: Mapped[str | None] = mapped_column(Text)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class SiteVisit(Base):
    __tablename__ = "site_visits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), index=True)
    sales_employee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    conducted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(50), default="SCHEDULED")
    outcome: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Token(Base):
    __tablename__ = "tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), index=True)
    token_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    token_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    payment_mode: Mapped[str | None] = mapped_column(String(50))
    receipt_reference: Mapped[str | None] = mapped_column(String(200))
    salesperson_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    closing_manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE")
    refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    documents_json: Mapped[str] = mapped_column(Text, default="[]")
    notes: Mapped[str | None] = mapped_column(Text)

class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), index=True)
    booking_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    booking_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    sale_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(50), default="BOOKED")
    documents_json: Mapped[str] = mapped_column(Text, default="[]")
    notes: Mapped[str | None] = mapped_column(Text)

class Commission(Base):
    __tablename__ = "commissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    developer_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    commission_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    payable_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    received_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), default=0)
    pending_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), default=0)
    payment_date: Mapped[datetime | None] = mapped_column(DateTime)
    remarks: Mapped[str | None] = mapped_column(Text)
