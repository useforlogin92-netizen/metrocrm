import asyncio
from types import SimpleNamespace

import pytest

import app.routers.whatsapp_property_import as route_module
from app.services import whatsapp_property_import as importer
from app.services.whatsapp_property_import import analyze_sources, attachment_record, find_safe_project_matches, normalize_name, parse_property_text


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


def test_unattributed_attachment_blocks_auto_commit():
    from app.services.whatsapp_property_import import build_draft

    class FakeSession:
        def scalars(self, *args, **kwargs):
            class Result:
                def all(self):
                    return []
            return Result()

    draft = build_draft(
        "Sethia Pride Kandivali East",
        [{"filename": "catalog.pdf", "extracted_text": "2 BHK 900 Sq.ft ₹2.10 CRORE"}],
        FakeSession(),
    )
    assert draft["unattributed_sources"] == ["catalog.pdf"]
    assert draft["requires_manual_project_selection"] is True
    assert draft["safe_to_commit"] is False


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


def test_project_matching_uses_normalized_name():
    class ProjectRow:
        id = 42
        name = "Sethia Pride (Kandivali E)"
        developer_id = None
        city = "Mumbai"
        rera = "P518000046531"

    class DeveloperRow:
        name = "Sethia Infrastructure"

    class FakeSession:
        def scalars(self, *args, **kwargs):
            class Result:
                def all(self):
                    return [ProjectRow()]
            return Result()

        def get(self, model, object_id):
            return DeveloperRow()

    parsed = {"project_candidates": ["Sethia Pride Kandivali E"], "developer": "Sethia Infrastructure", "city": "Mumbai", "rera": "P518000046531"}
    result = find_safe_project_matches(FakeSession(), parsed)
    assert result["ambiguous"] is False
    assert result["matches"][0]["project_id"] == 42



def test_whatsapp_import_rejects_too_many_attachments_before_staging():
    files = [SimpleNamespace(filename=f"file-{i}.pdf") for i in range(route_module.MAX_ATTACHMENTS + 1)]
    with pytest.raises(ValueError, match="Maximum"):
        asyncio.run(route_module._stage(files, "too-many-test"))


def test_whatsapp_import_enforces_combined_attachment_size_and_cleans_staging(monkeypatch, tmp_path):
    class FakeUpload:
        def __init__(self, filename, data):
            self.filename = filename
            self.content_type = "application/pdf"
            self.data = data

        async def read(self, limit):
            return self.data[:limit]

    monkeypatch.setattr(route_module, "MAX_ATTACHMENT_BYTES", 10)
    monkeypatch.setattr(route_module, "MAX_TOTAL_ATTACHMENT_BYTES", 5)
    monkeypatch.setattr(route_module, "_root", lambda name: tmp_path / name)
    monkeypatch.setattr(route_module, "attachment_text", lambda filename, mime, data: "")
    monkeypatch.setattr(route_module, "attachment_record", lambda filename, mime, data: {
        "filename": filename, "mime_type": mime, "extracted_text_chars": 0,
    })
    files = [FakeUpload("one.pdf", b"123"), FakeUpload("two.pdf", b"456")]
    with pytest.raises(ValueError, match="Combined attachments"):
        asyncio.run(route_module._stage(files, "combined-size-test"))
    assert not (tmp_path / "property-import-staging" / "combined-size-test").exists()
