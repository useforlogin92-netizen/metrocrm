from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.sessions import SessionMiddleware

from app import main

app = main.app


@app.middleware("http")
async def add_recovery_links(request: Request, call_next):
    response = await call_next(request)
    if request.method != "GET" or request.url.path not in {"/", "/admin/login", "/dashboard"}:
        return response
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        return response
    body = getattr(response, "body", None)
    if body is None:
        return response

    if request.url.path == "/":
        link = b'<a class="forgot-link" href="/forgot-password">Forgot your password?</a>'
        marker = b'<div class="super-note">'
        if marker not in body or b'href="/forgot-password"' in body:
            return response
        body = body.replace(marker, link + marker, 1)
    elif request.url.path == "/admin/login":
        link = b'<a class="forgot-link" href="/forgot-password">Forgot your password?</a>'
        marker = b'<div class="security-line">'
        if marker not in body or b'href="/forgot-password"' in body:
            return response
        body = body.replace(marker, link + marker, 1)
    elif request.url.path == "/dashboard":
        login_portal = str(request.session.get("login_portal", "")).lower()
        if login_portal not in {"admin", "super_admin"}:
            return response
        link = b'<a class="forgot-link" href="/password-reset-requests">Password Recovery Requests</a>'
        if b'href="/password-reset-requests"' in body:
            return response
        marker = b"</body>"
        body = body.replace(marker, link + marker, 1) if marker in body else body + link
    else:
        return response

    headers = dict(response.headers)
    headers.pop("content-length", None)
    return Response(content=body, status_code=response.status_code, headers=headers, media_type="text/html")


for _index, _middleware in enumerate(app.user_middleware):
    if _middleware.cls is SessionMiddleware:
        if _index:
            app.user_middleware.insert(0, app.user_middleware.pop(_index))
        break
