from datetime import datetime
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    mobile: Mapped[str | None] = mapped_column(String(30), index=True)
    alternate_mobile: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class LeadAssignmentHistory(Base):
    __tablename__ = "lead_assignment_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    from_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
