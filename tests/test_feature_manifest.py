"""Guard the MetroCRM feature manifest against stale current-path mappings.

Target folders are intentionally allowed not to exist until their feature is migrated.
"""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "feature_manifest.json"


def test_feature_manifest_has_unique_ids_and_required_fields():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    features = data["features"]

    ids = [feature["id"] for feature in features]
    assert len(ids) == len(set(ids)), "feature IDs must be unique"
    assert features, "manifest must list at least one feature"

    for feature in features:
        assert feature.get("label")
        assert feature.get("current_paths")
        assert feature.get("target_root")
        assert all(not Path(path).is_absolute() for path in feature["current_paths"])


def test_every_declared_current_path_exists_in_repository():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    missing = []
    for feature in data["features"]:
        for relative_path in feature["current_paths"]:
            if not (ROOT / relative_path).exists():
                missing.append(f"{feature['id']}: {relative_path}")

    assert not missing, "Stale current-path entries in docs/feature_manifest.json:\n" + "\n".join(missing)


def test_declared_feature_tests_exist():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    missing = []
    for feature in data["features"]:
        for relative_path in feature.get("tests", []):
            if not (ROOT / relative_path).is_file():
                missing.append(f"{feature['id']}: {relative_path}")

    assert not missing, "Missing declared feature tests:\n" + "\n".join(missing)
