from app.services.approval import ApprovalType


def test_supported_data_request_types():
    assert ApprovalType.DATA_DOWNLOAD.value == "DATA_DOWNLOAD"
    assert ApprovalType.DATA_DELETE.value == "DATA_DELETE"
