from app.services.catalog_sharing import ContactSelection, build_share_payload, build_share_preview


def test_no_defaults_means_no_contacts_or_media():
    payload = build_share_payload(
        {"title": "Skyline", "internal_notes": "private"},
        selected_fields=set(),
        selected_media_ids=set(),
        media=[{"id": "1", "url": "/1.jpg"}],
        contacts={"salesperson": {"name": "Sales", "mobile": "9999999999"}},
    )
    assert payload == {"fields": {}, "media": [], "contacts": {}}


def test_selected_property_fields_are_shared_but_internal_fields_are_blocked():
    payload = build_share_payload(
        {"title": "Skyline", "price": 25000000, "internal_notes": "do not expose"},
        selected_fields={"title", "price", "internal_notes"},
    )
    assert payload["fields"] == {"title": "Skyline", "price": 25000000}
    assert "internal_notes" not in payload["fields"]


def test_media_requires_individual_selection():
    media = [
        {"id": "img-1", "url": "/1.jpg"},
        {"id": "img-2", "url": "/2.jpg"},
        {"id": "secret", "url": "/secret.pdf", "internal_only": True},
    ]
    payload = build_share_payload(
        {}, selected_media_ids={"img-2", "secret"}, media=media
    )
    assert [item["id"] for item in payload["media"]] == ["img-2"]


def test_salesperson_mobile_only():
    payload = build_share_payload(
        {},
        contacts={"salesperson": {"name": "A", "mobile": "98XXXXXX10", "whatsapp": "98XXXXXX10", "email": "a@example.com"}},
        contact_selections=(ContactSelection("salesperson", frozenset({"mobile"})),),
    )
    assert payload["contacts"] == {"salesperson": {"mobile": "98XXXXXX10"}}


def test_closing_manager_whatsapp_only():
    payload = build_share_payload(
        {},
        contacts={"closing_manager": {"name": "M", "mobile": "91XXXXXX20", "whatsapp": "91XXXXXX20", "email": "m@example.com"}},
        contact_selections=(ContactSelection("closing_manager", frozenset({"whatsapp"})),),
    )
    assert payload["contacts"] == {"closing_manager": {"whatsapp": "91XXXXXX20"}}


def test_multiple_contacts_are_independently_selectable():
    payload = build_share_payload(
        {},
        contacts={
            "salesperson": {"name": "S", "mobile": "1"},
            "company": {"name": "Company", "email": "office@example.com"},
            "custom": {"name": "Custom", "email": "custom@example.com"},
        },
        contact_selections=(
            ContactSelection("salesperson", frozenset({"name"})),
            ContactSelection("company", frozenset({"email"})),
            ContactSelection("custom", frozenset({"name", "email"})),
        ),
    )
    assert payload["contacts"] == {
        "salesperson": {"name": "S"},
        "company": {"email": "office@example.com"},
        "custom": {"name": "Custom", "email": "custom@example.com"},
    }


def test_invalid_contact_type_and_field_are_not_exposed():
    payload = build_share_payload(
        {},
        contacts={"salesperson": {"name": "S", "phone": "secret"}},
        contact_selections=(ContactSelection("unknown", frozenset({"phone"})), ContactSelection("salesperson", frozenset({"phone", "name"}))),
    )
    assert payload["contacts"] == {"salesperson": {"name": "S"}}


def test_preview_matches_actual_share_payload():
    args = dict(
        property_data={"title": "Skyline", "price": 100},
        selected_fields={"title", "price"},
        selected_media_ids={"1"},
        media=[{"id": "1", "url": "/1.jpg"}],
        contacts={"closing_manager": {"whatsapp": "91XXXXXX20"}},
        contact_selections=(ContactSelection("closing_manager", frozenset({"whatsapp"})),),
    )
    assert build_share_preview(**args) == build_share_payload(**args)
