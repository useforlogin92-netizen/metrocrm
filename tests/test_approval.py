import pytest

from app.services.approval import ApprovalRequest, ApprovalStatus, ApprovalType


def test_download_request_starts_pending_and_needs_separate_approver():
    request = ApprovalRequest(ApprovalType.DATA_DOWNLOAD, requester_id=10, reason="Reporting")
    assert request.status is ApprovalStatus.PENDING
    approved = request.approve(20)
    assert approved.status is ApprovalStatus.APPROVED
    assert approved.approver_id == 20
    assert approved.decided_at is not None


def test_self_approval_is_rejected():
    request = ApprovalRequest(ApprovalType.DATA_DELETE, requester_id=10, reason="Duplicate")
    with pytest.raises(ValueError, match="cannot approve"):
        request.approve(10)


def test_terminal_request_cannot_be_decided_again():
    request = ApprovalRequest(ApprovalType.DATA_DOWNLOAD, requester_id=10, reason="Audit").reject(20)
    with pytest.raises(ValueError, match="pending"):
        request.approve(30)
