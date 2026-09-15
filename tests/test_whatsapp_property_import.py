from app.services.whatsapp_property_import import analyze_sources, normalize_name, parse_property_text


def test_whatsapp_parser_extracts_project_and_configurations():
    parsed = parse_property_text(
        "SETHIA PRIDE KANDIVALI (E)\n"
        "1 BED - 365 Sq.ft - ₹1.18 CRORE+\n"
        "2 BED WITH DECK - 520 Sq.ft - ₹1.53 CRORE+\n"
        "RERA P518000046531\n"
        "Western Express Highway\n"
    )
    assert "Sethia Pride" in parsed["project_candidates"]
    assert parsed["rera"] == "P518000046531"
    assert len(parsed["unit_configurations"]) == 2
    assert parsed["unit_configurations"][0]["carpet_area"] == 365


def test_multiple_project_sources_are_never_silently_merged():
    parsed = analyze_sources(
        "Sethia Pride Kandivali East",
        [
            {"filename": "pride.jpg", "extracted_text": "SETHIA PRIDE KANDIVALI (E)"},
            {"filename": "other.pdf", "extracted_text": "PASSCODE HIGHWAY BONANZA KANDIVALI (E)"},
        ],
    )
    assert parsed["identity_conflict"] is True
    assert len(parsed["project_candidates"]) == 2


def test_project_name_normalization_is_stable():
    assert normalize_name("Sethia Pride (Kandivali E)") == "sethia pride kandivali e"


def test_source_identity_is_kept_per_attachment():
    parsed = analyze_sources(
        "",
        [{"filename": "brochure.pdf", "extracted_text": "SETHIA PRIDE KANDIVALI (E)"}],
    )
    assert parsed["source_identities"][0]["filename"] == "brochure.pdf"
    assert "Sethia Pride" in parsed["source_identities"][0]["projects"]
