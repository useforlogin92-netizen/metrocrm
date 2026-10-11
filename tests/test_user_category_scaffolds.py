"""Validate role-category folder scaffolding and keep it aligned with the live Role enum."""
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "feature_manifest.json"
ROLE_SOURCE = ROOT / "app" / "permissions.py"


def test_user_category_manifest_matches_role_enum_and_has_scaffold():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    categories = data.get("user_categories", [])
    roles_in_manifest = [item["role"] for item in categories]

    source = ROLE_SOURCE.read_text(encoding="utf-8")
    enum_match = re.search(r"class Role\(StrEnum\):(.*?)(?:\n\nclass |\Z)", source, re.S)
    assert enum_match, "Could not find Role enum in app/permissions.py"
    roles_in_code = re.findall(r"^\s+([A-Z][A-Z0-9_]*)\s*=\s*['\"]", enum_match.group(1), re.M)

    assert set(roles_in_manifest) == set(roles_in_code), (
        f"Manifest roles {sorted(roles_in_manifest)} do not match Role enum {sorted(roles_in_code)}"
    )
    assert len(roles_in_manifest) == len(set(roles_in_manifest)), "Duplicate role in manifest"

    for item in categories:
        folder = ROOT / item["folder"]
        assert folder.is_dir(), f"Missing category folder: {item['folder']}"
        readme = folder / "README.md"
        assert readme.is_file(), f"Missing category boundary README: {readme.relative_to(ROOT)}"
        assert item["current_role_source"] == "app/permissions.py"
