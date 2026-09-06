import pytest

from app.services.approval import ApprovalRequest, ApprovalType


def test_requester_cannot_reject_own_request():
    request = ApprovalRequest(ApprovalType.DATA_DELETE, requester_id=5, reason="test")
    with pytest.raises(ValueError, match="cannot reject"):
        request.reject(5)
