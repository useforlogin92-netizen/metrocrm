"""Smoke tests for the static architecture inventory generator."""
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "architecture_inventory.py"


def test_inventory_scans_without_importing_application_and_finds_known_routes(tmp_path):
    output = tmp_path / "architecture-inventory.json"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(ROOT), "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    inventory = json.loads(output.read_text(encoding="utf-8"))

    assert inventory["mode"] == "static_ast_no_application_imports"
    assert inventory["python_file_count"] > 0
    assert inventory["parse_error_count"] == 0

    files = {item["path"]: item for item in inventory["files"]}
    assert "app/main.py" in files
    assert "app/routers/property_data.py" in files
    assert any(
        route["path"] == "/admin/property-data"
        for route in files["app/routers/property_data.py"]["routes"]
    )
    assert any(
        function["name"] == "role_allows"
        for function in files["app/permissions.py"]["functions"]
    )
