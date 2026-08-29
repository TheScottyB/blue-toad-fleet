"""Exactly one supported entry point owns each authoritative artifact."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from src.cycles.ownership import PROTECTED_ARTIFACT_OWNERS


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_august_runner_refuses_and_writes_nothing(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_aug22_cycle.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "legacy runner cannot write" in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_every_declared_owner_exists_and_is_unique():
    assert len(PROTECTED_ARTIFACT_OWNERS) == len(set(PROTECTED_ARTIFACT_OWNERS))
    for owner in PROTECTED_ARTIFACT_OWNERS.values():
        assert (ROOT / owner).is_file(), owner


def test_no_non_owner_script_claims_protected_literal_paths():
    declaration = ROOT / "src" / "cycles" / "ownership.py"
    for protected, owner in PROTECTED_ARTIFACT_OWNERS.items():
        if "{" in protected:
            continue
        claimers = []
        for directory in ("src", "scripts", "demo", "infra"):
            for path in (ROOT / directory).rglob("*"):
                if path.suffix not in {".py", ".mjs"}:
                    continue
                if path == ROOT / owner or path == declaration:
                    continue
                if protected in path.read_text():
                    claimers.append(str(path.relative_to(ROOT)))
        assert claimers == [], f"{protected} also claimed by {claimers}"
