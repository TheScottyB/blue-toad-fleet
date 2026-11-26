"""Clean-clone guards for fixtures and portable test entry points."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = "data/aug22_gallery_4160518/images/001_838421457.jpg"


def _git(index: Path, *args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["GIT_INDEX_FILE"] = str(index)
    return subprocess.run(
        ["git", *args], cwd=ROOT, env=environment, capture_output=True, text=True)


def test_required_photo_can_be_readded_without_force(tmp_path):
    index = tmp_path / "index"
    assert _git(index, "read-tree", "HEAD").returncode == 0
    removed = _git(index, "rm", "--cached", "--", FIXTURE)
    assert removed.returncode == 0, removed.stderr
    added = _git(index, "add", "--", FIXTURE)
    assert added.returncode == 0, added.stderr


def test_release_code_has_no_personal_absolute_paths():
    offenders = []
    for folder in (ROOT / "scripts", ROOT / "infra"):
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".mjs", ".sh"}:
                if "/Users/scottybe/" in path.read_text(errors="ignore"):
                    offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
