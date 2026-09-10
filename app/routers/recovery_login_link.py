from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.sessions import SessionMiddleware

from app import main

app = main.app


@app.middleware("http")
async def add_recovery_links(request: Request, call_next):
    response = await call_next(request)
    if request.method != "GET" or request.url.path not in {"/", "/dashboard"}:
        return response
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        return response
    body = getattr(response, "body", None)
    if body is None:
        return response

    links = []
    if request.url.path == "/":
        links.append(b'<a class="forgot-link" href="/forgot-password">Forgot your password?</a>')
    login_portal = str(request.session.get("login_portal", "")).lower()
    if request.url.path == "/dashboard" and login_portal in {"admin", "super_admin"}:
        links.append(b'<a class="forgot-link" href="/password-reset-requests">Password Recovery Requests</a>')
    if not links:
        return response

    marker = b'<div class="super-note">'
    if request.url.path == "/" and marker in body and b'href="/forgot-password"' not in body:
        body = body.replace(marker, links[0] + marker, 1)
    elif request.url.path == "/dashboard" and b'href="/password-reset-requests"' not in body:
        marker = b"</body>"
        if marker in body:
            body = body.replace(marker, links[0] + marker, 1)
        else:
            body += links[0]
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
