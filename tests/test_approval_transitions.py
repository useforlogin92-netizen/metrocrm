import pytest

from app.services.approval import ApprovalRequest, ApprovalType


def test_approved_request_cannot_be_rejected():
    request = ApprovalRequest(ApprovalType.DATA_DOWNLOAD, requester_id=1, reason="report").approve(2)
    with pytest.raises(ValueError, match="pending"):
        request.reject(3)
