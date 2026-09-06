from app.services.approval import ApprovalRequest, ApprovalType


def test_approval_created_time_is_set_when_decided():
    request = ApprovalRequest(ApprovalType.DATA_DOWNLOAD, requester_id=1, reason="audit").approve(2)
    assert request.created_at is not None
    assert request.decided_at is not None
