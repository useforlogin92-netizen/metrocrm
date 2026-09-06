"""Normalized location and property-catalog media tables."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LocationMaster(Base):
    __tablename__ = "location_master"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country: Mapped[str] = mapped_column(String(80), default="India", index=True)
    state: Mapped[str | None] = mapped_column(String(100), index=True)
    district: Mapped[str | None] = mapped_column(String(100), index=True)
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    locality: Mapped[str | None] = mapped_column(String(150), index=True)
    pincode: Mapped[str | None] = mapped_column(String(10), index=True)
    level: Mapped[str] = mapped_column(String(30), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)
    aliases_json: Mapped[str] = mapped_column(Text, default="[]")
    latitude: Mapped[float | None] = mapped_column()
    longitude: Mapped[float | None] = mapped_column()
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CustomerLocationPreference(Base):
    __tablename__ = "customer_location_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_requirement_id: Mapped[int] = mapped_column(ForeignKey("customer_requirements.id"), index=True)
    state: Mapped[str | None] = mapped_column(String(100), index=True)
    district: Mapped[str | None] = mapped_column(String(100), index=True)
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    locality: Mapped[str | None] = mapped_column(String(150), index=True)
    pincode: Mapped[str | None] = mapped_column(String(10), index=True)
    min_priority: Mapped[int] = mapped_column(Integer, default=0)


class PropertyMedia(Base):
    __tablename__ = "property_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), index=True)
    media_type: Mapped[str] = mapped_column(String(30), index=True)  # IMAGE, VIDEO, FLOOR_PLAN, BROCHURE, OTHER
    title: Mapped[str | None] = mapped_column(String(255))
    file_url: Mapped[str] = mapped_column(String(1000))
    storage_key: Mapped[str | None] = mapped_column(String(500), index=True)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    file_size: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_shareable: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
