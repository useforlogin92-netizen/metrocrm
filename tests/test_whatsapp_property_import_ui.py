import pytest

from app.whatsapp_property_import_ui import WhatsAppPropertyImportUIMiddleware


async def _rendered_html(path: str) -> str:
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/html; charset=utf-8")]})
        await send({
            "type": "http.response.body",
            "body": (
                b'<html><body>'
                b'<input name="csrf_token" value="csrf-test">'
                + (
                    b'<a class="pd-btn" href="/super-admin/media-catalog">MEDIA</a>'
                    if path.startswith("/super-admin/")
                    else b'<a class="pd-btn" href="/admin/media-catalog">MEDIA</a>'
                )
                + b'</body></html>'
            ),
        })

    middleware = WhatsAppPropertyImportUIMiddleware(app)
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await middleware({"type": "http", "path": path, "method": "GET", "headers": []}, receive, send)
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body").decode("utf-8")


@pytest.mark.anyio
async def test_super_admin_property_data_injects_whatsapp_capture_modal():
    html = await _rendered_html("/super-admin/property-data")
    assert 'id="metrocrm-whatsapp-property-import"' in html
    assert 'id="metrocrm-whatsapp-modal"' in html
    assert 'action="/super-admin/property-data/whatsapp-import/analyze"' in html
    assert 'id="metrocrm-whatsapp-text"' in html
    assert 'name="files"' in html


@pytest.mark.anyio
async def test_admin_property_data_injects_whatsapp_capture_modal():
    html = await _rendered_html("/admin/property-data")
    assert 'id="metrocrm-whatsapp-property-import"' in html
    assert 'id="metrocrm-whatsapp-modal"' in html
    assert 'action="/admin/property-data/whatsapp-import/analyze"' in html


@pytest.mark.anyio
async def test_legacy_whatsapp_review_queue_is_normalized_to_capture_button(): 
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/html; charset=utf-8")]})
        await send({
            "type": "http.response.body",
            "body": (
                b'<html><body>'
                b'<a class="pd-btn primary" href="/super-admin/property-data/whatsapp-import">📋 WhatsApp Review Queue</a>'
                b'</body></html>'
            ),
        })

    middleware = WhatsAppPropertyImportUIMiddleware(app)
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await middleware({"type": "http", "path": "/super-admin/property-data", "method": "GET", "headers": []}, receive, send)
    html = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body").decode("utf-8")
    assert 'id="metrocrm-whatsapp-property-import"' in html
    assert "WhatsApp Review Queue" not in html
    assert 'id="metrocrm-whatsapp-modal"' in html
