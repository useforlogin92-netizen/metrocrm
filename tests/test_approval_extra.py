from app.services.approval import ApprovalRequest, ApprovalStatus, ApprovalType


def test_rejection_is_terminal():
    request = ApprovalRequest(ApprovalType.DATA_DELETE, requester_id=1, reason="duplicate")
    rejected = request.reject(2)
    assert rejected.status is ApprovalStatus.REJECTED
    assert rejected.approver_id == 2
    assert rejected.decided_at is not None
