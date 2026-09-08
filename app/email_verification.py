from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EmailVerification(Base):
    __tablename__ = "email_verifications"
    __table_args__ = (UniqueConstraint("user_id", name="uq_email_verification_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


# main.app already exists when this module is imported by app.main. Register
# the data-operations router here so the portal and direct main app expose the
# same controlled import/export/report features without duplicating app setup.
from app.main import app as _app
from app.routers.data_tools import router as data_tools_router

_app.include_router(data_tools_router)
