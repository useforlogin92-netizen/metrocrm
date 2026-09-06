from app.services.approval import ApprovalRequest, ApprovalStatus, ApprovalType


def test_pending_request_is_not_implicitly_approved():
    request = ApprovalRequest(ApprovalType.DATA_DOWNLOAD, requester_id=1, reason="report")
    assert request.status is ApprovalStatus.PENDING
    assert request.approver_id is None
