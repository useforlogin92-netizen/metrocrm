"""Application/runtime snapshot helpers for MetroCRM disaster recovery."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

# Files/directories that contain runtime state, secrets, caches, or generated backups
# are intentionally excluded. The source tree, deployment manifests and dependency
# declarations remain in the snapshot so a clean system can be rebuilt.
_EXCLUDED_NAMES = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "backups", "uploads",
    ".mypy_cache", ".ruff_cache", ".tox", "node_modules"
}
_EXCLUDED_FILES = {".env", ".env.local", ".env.production"}


def _repository_root() -> Path:
    return Path.cwd().resolve()


def _should_include(path: Path) -> bool:
    if path.name in _EXCLUDED_NAMES or path.name in _EXCLUDED_FILES:
        return False
    try:
        relative = path.resolve().relative_to(_repository_root())
    except ValueError:
        return False
    return not any(part in _EXCLUDED_NAMES or part in _EXCLUDED_FILES for part in relative.parts)


def add_application_snapshot(archive, root: Path | None = None) -> dict[str, object]:
    """Add the runnable CRM source/deployment tree and a SHA-256 manifest."""
    root = (root or _repository_root()).resolve()
    manifest: list[dict[str, object]] = []
    files = 0
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not _should_include(path):
            continue
        relative = path.relative_to(root).as_posix()
        # Never allow an application snapshot to accidentally contain local secrets.
        if Path(relative).name in _EXCLUDED_FILES:
            continue
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        archive.write(path, f"application/{relative}")
        manifest.append({"path": relative, "size": size, "sha256": digest.hexdigest()})
        files += 1
        total_bytes += size
    archive.writestr("application/manifest.json", json.dumps({"version": 1, "files": manifest}, indent=2, sort_keys=True))
    return {"files": files, "bytes": total_bytes, "root": str(root)}


def application_exclusion_names() -> set[str]:
    return set(_EXCLUDED_NAMES) | set(_EXCLUDED_FILES)
