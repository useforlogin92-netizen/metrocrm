import pytest

from app.services.approval import ApprovalRequest, ApprovalType


def test_rejected_request_cannot_be_approved():
    request = ApprovalRequest(ApprovalType.DATA_DELETE, requester_id=1, reason="duplicate").reject(2)
    with pytest.raises(ValueError, match="pending"):
        request.approve(3)
