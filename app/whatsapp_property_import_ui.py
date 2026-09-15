"""Small navigation injection for the WhatsApp property import workspace."""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class WhatsAppPropertyImportUIMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope.get("type") != "http" or path not in {"/admin/property-data", "/super-admin/property-data"}:
            await self.app(scope, receive, send)
            return
        started: Message | None = None
        chunks: list[bytes] = []

        async def capture(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = message
                return
            if message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                if started is None:
                    await send(message)
                    return
                headers = list(started.get("headers", []))
                content_type = next((v.lower() for k, v in headers if k.lower() == b"content-type"), b"")
                body = b"".join(chunks)
                if b"text/html" not in content_type:
                    await send(started); await send(message); return
                html = body.decode("utf-8", errors="replace")
                if "metrocrm-whatsapp-property-import" not in html:
                    base = "/super-admin/property-data" if path.startswith("/super-admin/") else "/admin/property-data"
                    link = f'<a id="metrocrm-whatsapp-property-import" class="pd-btn primary" href="{base}/whatsapp-import">📲 Property Data Received by WhatsApp</a>'
                    html = html.replace('<a class="pd-btn" href="/admin/media-catalog">🖼 Property Media Catalog</a>', '<a class="pd-btn" href="/admin/media-catalog">🖼 Property Media Catalog</a>' + link, 1)
                encoded = html.encode("utf-8")
                headers = [(k, v) for k, v in headers if k.lower() != b"content-length"]
                headers.append((b"content-length", str(len(encoded)).encode("ascii")))
                start = dict(started); start["headers"] = headers
                await send(start); await send({"type": "http.response.body", "body": encoded, "more_body": False})
                return
            await send(message)

        await self.app(scope, receive, capture)


def install_whatsapp_property_import_ui(app) -> None:
    app.add_middleware(WhatsAppPropertyImportUIMiddleware)
