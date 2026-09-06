from app.services.catalog_renderer import render_customer_catalog


def test_customer_renderer_escapes_html_and_renders_selected_content():
    html = render_customer_catalog(
        {
            "fields": {"title": '<script>alert(1)</script>', "price": "₹1 Cr"},
            "media": [{"id": "p1", "title": "Front", "url": "https://example.com/p.jpg"}],
            "contacts": {"closing_manager": {"whatsapp": "+9198XXXXXX10"}},
        },
        title="Selected Property",
    )
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "₹1 Cr" in html
    assert "Front" in html
    assert "closing_manager" not in html
    assert "WhatsApp" in html
