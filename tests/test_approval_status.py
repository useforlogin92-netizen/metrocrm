from app.services.approval import ApprovalStatus


def test_approval_statuses_are_explicit():
    assert {ApprovalStatus.PENDING.value, ApprovalStatus.APPROVED.value, ApprovalStatus.REJECTED.value, ApprovalStatus.EXPIRED.value} == {"PENDING", "APPROVED", "REJECTED", "EXPIRED"}
