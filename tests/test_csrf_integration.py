import warnings

from fastapi import Depends, FastAPI, Request

# Starlette currently touches a deprecated AnyIO alias during TestClient import.
# Keep strict project deprecation checks enabled while isolating this upstream import warning.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.csrf import csrf_token, require_csrf, require_csrf_either, require_csrf_header


def _client():
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-only-session-secret")

    @app.get("/token")
    def get_token(request: Request):
        return {"token": csrf_token(request)}

    @app.post("/form")
    def post_form(_csrf: None = Depends(require_csrf)):
        return {"ok": True}

    @app.post("/ajax")
    def post_ajax(_csrf: None = Depends(require_csrf_header)):
        return {"ok": True}

    @app.post("/either")
    def post_either(_csrf: None = Depends(require_csrf_either)):
        return {"ok": True}

    return TestClient(app)


def test_html_form_csrf_valid_token_passes_and_invalid_token_is_403():
    with _client() as client:
        token = client.get("/token").json()["token"]
        assert client.post("/form", data={"csrf_token": token}).status_code == 200
        assert client.post("/form", data={"csrf_token": "wrong"}).status_code == 403
        assert client.post("/form", data={}).status_code == 403


def test_ajax_csrf_header_valid_token_passes_and_invalid_or_missing_is_403():
    with _client() as client:
        token = client.get("/token").json()["token"]
        assert client.post("/ajax", headers={"X-CSRF-Token": token}).status_code == 200
        assert client.post("/ajax", headers={"X-CSRF-Token": "wrong"}).status_code == 403
        assert client.post("/ajax").status_code == 403


def test_dual_csrf_dependency_accepts_form_or_header_but_never_falls_back_from_bad_header():
    with _client() as client:
        token = client.get("/token").json()["token"]
        assert client.post("/either", data={"csrf_token": token}).status_code == 200
        assert client.post("/either", headers={"X-CSRF-Token": token}).status_code == 200
        assert client.post(
            "/either",
            data={"csrf_token": token},
            headers={"X-CSRF-Token": "wrong"},
        ).status_code == 403
