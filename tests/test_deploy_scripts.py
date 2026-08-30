"""Deploy and Makefile wiring: scripts parse, IPv4 helper exports what gcloud needs."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_deploy_scripts_parse():
    for relative in (
        "infra/deploy.sh",
        "infra/provision_cycles.sh",
        "infra/gcloud_ipv4.sh",
    ):
        result = subprocess.run(
            ["bash", "-n", str(ROOT / relative)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{relative}: {result.stderr}"


def test_makefile_deploy_invokes_deploy_sh():
    result = subprocess.run(
        ["make", "-n", "deploy"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "./infra/deploy.sh" in result.stdout


def test_gcloud_ipv4_enables_site_packages_and_sitecustomize():
    """gcloud adds python -S unless CLOUDSDK_PYTHON_SITEPACKAGES is set; -S skips sitecustomize."""
    result = subprocess.run(
        [
            "bash",
            "-c",
            "set -euo pipefail; source ./infra/gcloud_ipv4.sh; "
            "printf '%s\\n' \"$CLOUDSDK_PYTHON_SITEPACKAGES\"; "
            "printf '%s\\n' \"$PYTHONPATH\"; "
            "test -f \"$PYTHONPATH/sitecustomize.py\" || "
            "test -f \"${PYTHONPATH%%:*}/sitecustomize.py\"",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "CLOUDSDK_PYTHON_SITEPACKAGES": "", "PYTHONPATH": ""},
    )
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines[0] == "1"
    assert "gcloud-ipv4" in lines[1]
