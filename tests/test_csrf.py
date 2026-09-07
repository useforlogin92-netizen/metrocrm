import pytest
from fastapi import HTTPException

from app.csrf import csrf_token, require_csrf


class FakeRequest:
    def __init__(self):
        self.session = {}


def test_csrf_token_is_stable_per_session():
    request = FakeRequest()
    first = csrf_token(request)
    second = csrf_token(request)
    assert first == second
    assert len(first) >= 32


def test_csrf_dependency_rejects_missing_or_wrong_token():
    request = FakeRequest()
    token = csrf_token(request)
    with pytest.raises(HTTPException):
        require_csrf(request, "")
    with pytest.raises(HTTPException):
        require_csrf(request, "wrong")
    require_csrf(request, token)
