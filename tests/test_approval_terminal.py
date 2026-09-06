from app.services.approval import ApprovalRequest, ApprovalStatus, ApprovalType


def test_approved_request_records_approver():
    request = ApprovalRequest(ApprovalType.DATA_DOWNLOAD, requester_id=1, reason="audit").approve(2)
    assert request.status == ApprovalStatus.APPROVED
    assert request.approver_id == 2
