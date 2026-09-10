from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.sessions import SessionMiddleware

from app import main

app = main.app


@app.middleware("http")
async def add_staff_recovery_link(request: Request, call_next):
    response = await call_next(request)
    if request.url.path != "/" or request.method != "GET":
        return response
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        return response
    body = getattr(response, "body", None)
    if body is None:
        return response
    marker = b'<div class="super-note">'
    link = b'<a class="forgot-link" href="/forgot-password">Forgot your password?</a>'
    if marker in body and link not in body:
        body = body.replace(marker, link + marker, 1)
        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(content=body, status_code=response.status_code, headers=headers, media_type="text/html")
    return response

for _index, _middleware in enumerate(app.user_middleware):
    if _middleware.cls is SessionMiddleware:
        if _index:
            app.user_middleware.insert(0, app.user_middleware.pop(_index))
        break
