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


# Import model modules during startup so Base.metadata.create_all registers
# every feature table before the schema is created.
import app.crm_plus_models  # noqa: F401
import app.realestate_finance_models  # noqa: F401
