"""Normalized location, property-catalog media and persistent share tables."""

from datetime import datetime, timezone

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


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
    media_type: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    file_url: Mapped[str] = mapped_column(String(1000))
    storage_key: Mapped[str | None] = mapped_column(String(500), index=True)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    file_size: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_shareable: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class PropertySocialProfile(Base):
    __tablename__ = "property_social_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), unique=True, index=True)
    brand_name: Mapped[str | None] = mapped_column(String(150))
    facebook_url: Mapped[str | None] = mapped_column(String(1000))
    instagram_url: Mapped[str | None] = mapped_column(String(1000))
    youtube_url: Mapped[str | None] = mapped_column(String(1000))
    whatsapp_url: Mapped[str | None] = mapped_column(String(1000))
    x_url: Mapped[str | None] = mapped_column(String(1000))
    linkedin_url: Mapped[str | None] = mapped_column(String(1000))
    website_url: Mapped[str | None] = mapped_column(String(1000))
    google_business_url: Mapped[str | None] = mapped_column(String(1000))
    share_message: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class CatalogShare(Base):
    __tablename__ = "catalog_shares"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)


class CatalogShareVisit(Base):
    __tablename__ = "catalog_share_visits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    share_id: Mapped[int] = mapped_column(ForeignKey("catalog_shares.id"), index=True)
    visitor_key_hash: Mapped[str] = mapped_column(String(64), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(500))
    page_url: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
