"""Deploy and Makefile wiring: scripts parse, IPv4 helper exports what gcloud needs."""

from __future__ import annotations

import os
import shutil
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


def test_deploy_script_stamps_the_commit_into_the_service_env():
    text = (ROOT / "infra" / "deploy.sh").read_text()
    assert "git rev-parse HEAD" in text
    service_env = next(
        line for line in text.splitlines() if line.startswith("SERVICE_ENV=")
    )
    assert "GIT_COMMIT=${GIT_COMMIT}" in service_env


# Isolate scratch repos from the workstation's git config: a global
# status.showUntrackedFiles or gpg setting must not decide these outcomes.
_GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "release-gate-test",
    "GIT_AUTHOR_EMAIL": "release-gate-test@example.invalid",
    "GIT_COMMITTER_NAME": "release-gate-test",
    "GIT_COMMITTER_EMAIL": "release-gate-test@example.invalid",
}


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True,
        env=_GIT_ENV,
    )


def _scratch_repo(tmp_path):
    repo = tmp_path / "scratch"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "tracked.txt").write_text("v1\n")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-q", "-m", "init", "--no-gpg-sign")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, sha


def _stamp_block():
    """The deploy script's GIT_COMMIT stamp lines, located by content so the
    extraction survives the script growing or shrinking around them."""
    lines = (ROOT / "infra" / "deploy.sh").read_text().splitlines()
    start = next(
        i for i, line in enumerate(lines) if line.startswith("GIT_COMMIT=")
    )
    end = next(
        i for i, line in enumerate(lines) if line.startswith("SERVICE_ENV=")
    )
    return "\n".join(lines[start:end])


def _run_stamp(repo, extra_path=None):
    script = (
        "set -euo pipefail\n" + _stamp_block() + '\necho "STAMP=$GIT_COMMIT"\n'
    )
    env = dict(_GIT_ENV)
    if extra_path is not None:
        env["PATH"] = f"{extra_path}:{env['PATH']}"
    return subprocess.run(
        ["bash", "-c", script], cwd=repo, capture_output=True, text=True,
        env=env,
    )


def test_stamp_block_stamps_a_clean_tree_with_the_bare_sha(tmp_path):
    repo, sha = _scratch_repo(tmp_path)
    result = _run_stamp(repo)
    assert result.returncode == 0, result.stderr
    assert f"STAMP={sha}" in result.stdout
    assert "-dirty" not in result.stdout


def test_stamp_block_marks_a_dirty_tree(tmp_path):
    repo, sha = _scratch_repo(tmp_path)
    (repo / "tracked.txt").write_text("v2\n")
    result = _run_stamp(repo)
    assert result.returncode == 0, result.stderr
    assert f"STAMP={sha}-dirty" in result.stdout


def test_stamp_block_refuses_to_stamp_when_git_status_fails(tmp_path):
    # A dirty tree whose `git status` errors (index.lock contention,
    # permissions) must never be stamped as a clean commit — the stamp is
    # parity evidence, so an unknown tree state has to fail closed.
    repo, sha = _scratch_repo(tmp_path)
    (repo / "tracked.txt").write_text("v2\n")
    real_git = shutil.which("git")
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    shim = shim_dir / "git"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        'for arg in "$@"; do\n'
        '  if [ "$arg" = "status" ]; then\n'
        "    echo 'fatal: Unable to create index.lock: File exists.' >&2\n"
        "    exit 128\n"
        "  fi\n"
        "done\n"
        f'exec "{real_git}" "$@"\n'
    )
    shim.chmod(0o755)
    result = _run_stamp(repo, extra_path=shim_dir)
    assert result.returncode != 0
    assert f"STAMP={sha}" not in result.stdout


def test_stamp_block_marks_untracked_only_dirt_despite_config_override(tmp_path):
    # status.showUntrackedFiles=no silently empties porcelain output for an
    # untracked-only dirty tree; the stamp must defeat the override.
    repo, sha = _scratch_repo(tmp_path)
    _git(repo, "config", "status.showUntrackedFiles", "no")
    (repo / "untracked.txt").write_text("not yet committed\n")
    result = _run_stamp(repo)
    assert result.returncode == 0, result.stderr
    assert f"STAMP={sha}-dirty" in result.stdout
