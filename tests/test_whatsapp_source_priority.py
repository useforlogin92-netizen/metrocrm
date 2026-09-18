from app.services.whatsapp_property_import import analyze_sources


def test_brochure_is_primary_source_for_conflicting_fields():
    result = analyze_sources(
        "Project: Sethia Pride\nCity: Mumbai\nPrice: 1.13 Cr",
        [
            {
                "filename": "official-brochure.pdf",
                "mime_type": "application/pdf",
                "extracted_text": "Project: Passcode Highway Bonanza\nCity: Mumbai\nPrice: 1.25 Cr",
            },
        ],
    )

    assert result["source_priority"] == "BROCHURE/PDF > WHATSAPP > IMAGE/VIDEO"
    assert result["project_candidates"] == ["Passcode Highway Bonanza"]
    assert result["project"] == "Passcode Highway Bonanza"
    assert result["source_identity_warning"] is True
    assert result["identity_conflict"] is False
    assert any(item["field"] == "project" for item in result["field_conflicts"]) is False


def test_whatsapp_fills_blank_fields_when_brochure_has_no_value():
    result = analyze_sources(
        "Project: Sethia Pride\nContact: 9920854306",
        [
            {
                "filename": "official-brochure.pdf",
                "mime_type": "application/pdf",
                "extracted_text": "Project: Sethia Pride\nCity: Mumbai",
            },
        ],
    )

    assert result["project"] == "Sethia Pride"
    assert result["city"] == "Mumbai"
    assert result["contact_phone"] == "9920854306"
