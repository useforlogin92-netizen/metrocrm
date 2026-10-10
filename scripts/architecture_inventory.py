"""Build a static, non-executing inventory of MetroCRM routes, functions and imports.

This script deliberately parses Python source with ast instead of importing the app,
so inventory generation cannot start schedulers, connect to databases, or mutate data.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any


def _literal_route(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _route_decorators(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        if call is None or not isinstance(call.func, ast.Attribute):
            continue
        owner = call.func.value
        if not (isinstance(owner, ast.Name) and owner.id in {"router", "app"}):
            continue
        method = call.func.attr.lower()
        if method not in {"get", "post", "put", "patch", "delete", "api_route", "websocket"}:
            continue
        route = _literal_route(call.args[0]) if call.args else None
        if route is not None:
            found.append({"method": method.upper(), "path": route})
    return found


def scan_python_file(path: Path, root: Path) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    source = path.read_text(encoding="utf-8", errors="replace")
    result: dict[str, Any] = {
        "path": relative,
        "imports": [],
        "functions": [],
        "routes": [],
        "template_references": sorted(set(re.findall(
            r"(?:TemplateResponse\s*\(\s*|get_template\s*\(\s*)['\"]([^'\"]+\.html)['\"]",
            source,
        ))),
    }
    try:
        tree = ast.parse(source, filename=relative)
    except SyntaxError as exc:
        result["parse_error"] = f"line {exc.lineno}: {exc.msg}"
        return result

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result["imports"].extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result["imports"].append("." * node.level + (node.module or ""))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result["functions"].append({
                "name": node.name,
                "line": node.lineno,
                "async": isinstance(node, ast.AsyncFunctionDef),
            })
            result["routes"].extend({
                **route,
                "function": node.name,
                "line": node.lineno,
            } for route in _route_decorators(node))
    result["imports"] = sorted(set(result["imports"]))
    result["functions"].sort(key=lambda item: (item["line"], item["name"]))
    result["routes"].sort(key=lambda item: (item["line"], item["path"]))
    return result


def build_inventory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = root / "docs" / "feature_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    py_files = sorted(
        path for path in root.rglob("*.py")
        if not any(part in {".git", ".venv", "venv", "__pycache__"} for part in path.parts)
    )
    scanned = [scan_python_file(path, root) for path in py_files]
    feature_by_path: dict[str, list[str]] = {}
    for feature in manifest.get("features", []):
        for current_path in feature.get("current_paths", []):
            feature_by_path.setdefault(current_path, []).append(feature["id"])
    for item in scanned:
        item["manifest_features"] = feature_by_path.get(item["path"], [])
    return {
        "schema_version": 1,
        "repository": manifest.get("repository", "unknown"),
        "baseline_commit": manifest.get("baseline_commit"),
        "mode": "static_ast_no_application_imports",
        "python_file_count": len(scanned),
        "parse_error_count": sum("parse_error" in item for item in scanned),
        "route_count": sum(len(item["routes"]) for item in scanned),
        "function_count": sum(len(item["functions"]) for item in scanned),
        "files": scanned,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()
    inventory = build_inventory(args.root)
    rendered = json.dumps(inventory, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 1 if inventory["parse_error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
