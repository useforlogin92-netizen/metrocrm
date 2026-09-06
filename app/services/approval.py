from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class ApprovalType(StrEnum):
    DATA_DOWNLOAD = "DATA_DOWNLOAD"
    DATA_DELETE = "DATA_DELETE"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class ApprovalRequest:
    """Immutable application-level approval record.

    Persistence belongs to the database model/service layer. Keeping the
    state transition rules here makes them independently testable and prevents
    callers from treating a request as approved merely because it was created.
    """

    request_type: ApprovalType
    requester_id: int
    reason: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    approver_id: int | None = None
    created_at: datetime | None = None
    decided_at: datetime | None = None

    def approve(self, approver_id: int) -> "ApprovalRequest":
        if self.status is not ApprovalStatus.PENDING:
            raise ValueError("Only pending approval requests can be approved")
        if approver_id == self.requester_id:
            raise ValueError("Requester cannot approve their own request")
        return ApprovalRequest(
            request_type=self.request_type,
            requester_id=self.requester_id,
            reason=self.reason,
            status=ApprovalStatus.APPROVED,
            approver_id=approver_id,
            created_at=self.created_at or datetime.now(timezone.utc),
            decided_at=datetime.now(timezone.utc),
        )

    def reject(self, approver_id: int) -> "ApprovalRequest":
        if self.status is not ApprovalStatus.PENDING:
            raise ValueError("Only pending approval requests can be rejected")
        if approver_id == self.requester_id:
            raise ValueError("Requester cannot reject their own request")
        return ApprovalRequest(
            request_type=self.request_type,
            requester_id=self.requester_id,
            reason=self.reason,
            status=ApprovalStatus.REJECTED,
            approver_id=approver_id,
            created_at=self.created_at or datetime.now(timezone.utc),
            decided_at=datetime.now(timezone.utc),
        )
