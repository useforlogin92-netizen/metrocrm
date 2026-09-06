from app.services.approval import ApprovalRequest, ApprovalType


def test_reason_is_preserved():
    request = ApprovalRequest(ApprovalType.DATA_DOWNLOAD, requester_id=1, reason="monthly report")
    assert request.reason == "monthly report"
