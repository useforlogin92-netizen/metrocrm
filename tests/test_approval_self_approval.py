import pytest

from app.services.approval import ApprovalRequest, ApprovalType


def test_requester_cannot_approve_own_request():
    request = ApprovalRequest(ApprovalType.DATA_DOWNLOAD, requester_id=5, reason="test")
    with pytest.raises(ValueError, match="cannot approve"):
        request.approve(5)
