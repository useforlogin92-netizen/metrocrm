from app.services import whatsapp_property_import as importer
from app.services.whatsapp_property_import import analyze_sources, attachment_record, normalize_name, parse_property_text


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


def test_same_developer_different_projects_still_conflict():
    parsed = analyze_sources(
        "Developer: Sethia Infrastructure",
        [
            {"filename": "a.pdf", "extracted_text": "SETHIA PRIDE KANDIVALI (E) SETHIA INFRASTRUCTURE"},
            {"filename": "b.pdf", "extracted_text": "PASSCODE HIGHWAY BONANZA SETHIA INFRASTRUCTURE"},
        ],
    )
    assert parsed["identity_conflict"] is True
    assert set(parsed["project_candidates"]) == {"Sethia Pride", "Passcode Highway Bonanza"}


def test_unattributed_attachment_requires_manual_review():
    parsed = analyze_sources(
        "Sethia Pride Kandivali East",
        [{"filename": "catalog.pdf", "extracted_text": "2 BHK 900 Sq.ft ₹2.10 CRORE"}],
    )
    assert parsed["unattributed_sources"] == ["catalog.pdf"]


def test_project_name_normalization_is_stable():
    assert normalize_name("Sethia Pride (Kandivali E)") == "sethia pride kandivali e"


def test_source_identity_is_kept_per_attachment():
    parsed = analyze_sources(
        "",
        [{"filename": "brochure.pdf", "extracted_text": "SETHIA PRIDE KANDIVALI (E)"}],
    )
    assert parsed["source_identities"][0]["filename"] == "brochure.pdf"
    assert "Sethia Pride" in parsed["source_identities"][0]["projects"]


def test_video_attachment_uses_video_extractor(monkeypatch):
    monkeypatch.setattr(importer, "extract_video_text", lambda data, suffix=".mp4": "SETHIA PRIDE KANDIVALI (E)")
    record = attachment_record("tour.mov", "video/quicktime", b"video")
    assert record["extracted_text_chars"] > 0
    assert record["mime_type"] == "video/quicktime"
