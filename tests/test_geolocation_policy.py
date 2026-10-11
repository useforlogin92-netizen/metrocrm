"""Regression tests for narrowly scoped browser geolocation permissions."""
import asyncio
import time

from starlette.requests import Request
from starlette.responses import Response

from app.main import enforce_idle_session


def _request(path: str) -> Request:
    return Request({
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
        "root_path": "",
        "session": {"user_id": 1, "last_activity": time.time()},
    })


async def _dispatch(path: str) -> Response:
    async def call_next(_request: Request) -> Response:
        return Response("ok")

    return await enforce_idle_session(_request(path), call_next)


def test_site_visit_routes_allow_same_origin_geolocation_only():
    response = asyncio.run(_dispatch("/site-visits"))
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=(self)"

    nested_response = asyncio.run(_dispatch("/site-visits/12/feedback"))
    assert nested_response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=(self)"


def test_other_authenticated_routes_keep_geolocation_disabled():
    for path in ("/caller/leads", "/admin/lead-monitoring", "/dashboard"):
        response = asyncio.run(_dispatch(path))
        assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
