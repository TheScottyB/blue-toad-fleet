#!/usr/bin/env python3
"""Build the non-mutating release report and fail while release evidence is blocked."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from scripts.collect_submission_facts import _test_counts, collect
from scripts.video_common import VideoBuildError, atomic_write_text, project_path

DEPLOYED_HEALTH_URL = "https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/health"


def _git(*args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args], cwd=project_path("."), capture_output=True, text=True,
        check=False,
    )
    return result.returncode, (result.stdout or result.stderr).strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fetch_deployed_commit(url: str, timeout: float = 10.0) -> tuple[str | None, str | None]:
    """Return (deployed_commit, error); exactly one side is set."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        return None, str(exc) or exc.__class__.__name__
    commit = payload.get("git_commit") if isinstance(payload, dict) else None
    if not commit or commit == "unknown":
        return None, "the deployed /health payload does not carry a git commit"
    return str(commit), None


def _revision_parity(
    local_commit: str, deployed_commit: str | None, error: str | None,
) -> tuple[str, str | None]:
    """Compare the audited commit against the deployed one, failing closed.

    Anything short of two known, equal commits is UNVERIFIED or MISMATCH —
    "could not check" must never resolve to the permissive verdict.
    """
    if local_commit == "unknown":
        return "UNVERIFIED", "the local commit could not be resolved"
    if deployed_commit is None:
        return "UNVERIFIED", error or "no deployed commit and no recorded error"
    if deployed_commit == local_commit:
        return "MATCH", None
    return "MISMATCH", None


def _facts_lines(facts: dict | None, facts_error: str | None) -> str:
    """Operator-facing facts rows. Flagged deferred/dropped allocated lots are
    rendered — non-blocking by the queue's contract, but never invisible: 148
    triage questions were once dropped over cap with no review trail."""
    if not facts:
        return f"- Blocked: {facts_error or 'unknown facts error'}"
    publication = facts.get("publication") or {}
    lines = (
        "- Snapshot identity: `" + str(facts.get("snapshot_identity_sha256")) + "`\n"
        "- Artifact manifest: `" + str(
            publication.get("artifact_manifest_sha256") or "unavailable") + "`"
    )
    deferred = publication.get("flagged_deferred_lot_ids") or []
    dropped = publication.get("flagged_dropped_lot_ids") or []
    if deferred or dropped:
        lines += (
            f"\n- Flagged non-blocking allocated lots: {len(deferred)} deferred "
            f"(desk-cannot-answer), {len(dropped)} dropped (over queue cap) — "
            "these ship flagged low-confidence per the queue contract"
        )
    return lines


def _facts_blockers(snapshot: dict) -> list[str]:
    blockers: list[str] = []
    publication = snapshot.get("publication") or {}
    if not publication.get("release_eligible"):
        reason = publication.get("reason") or "cycle facts are not release eligible"
        blockers.append(str(reason))
        lots = publication.get("blocking_lot_ids") or []
        if lots:
            blockers.append("unresolved allocated lots: " + ", ".join(map(str, lots)))
    if (snapshot.get("git") or {}).get("dirty"):
        blockers.append("facts snapshot was generated from a dirty working tree")
    return blockers


def build_report(
    junit_path: str | Path,
    output_path: str | Path,
    *,
    manifest_path: str | Path = "media/video_manifest.json",
    health_url: str = DEPLOYED_HEALTH_URL,
) -> tuple[Path, list[str]]:
    root = project_path(".")
    junit = Path(junit_path)
    counts = _test_counts(junit)
    blockers: list[str] = []
    if counts["failed"] or counts["errors"]:
        blockers.append("the local pytest report contains failures or errors")

    diff_code, diff_output = _git("diff", "--check")
    if diff_code:
        blockers.append("git diff --check failed")

    commit_code, commit = _git("rev-parse", "HEAD")
    if commit_code:
        commit = "unknown"

    deployed_commit, parity_error = _fetch_deployed_commit(health_url)
    parity, parity_detail = _revision_parity(commit, deployed_commit, parity_error)
    if parity == "MISMATCH":
        blockers.append(
            "the deployed revision does not match the audited commit",
        )
    elif parity == "UNVERIFIED":
        blockers.append(
            f"deployed revision parity is unverified: {parity_detail}",
        )

    facts: dict | None = None
    facts_error: str | None = None
    with tempfile.TemporaryDirectory(prefix="blue-toad-release-facts-") as directory:
        target = Path(directory) / "submission_facts.json"
        try:
            collect(str(manifest_path), str(target), str(junit))
            facts = json.loads(target.read_text())
            blockers.extend(_facts_blockers(facts))
        except (OSError, ValueError, VideoBuildError) as exc:
            facts_error = str(exc)
            blockers.append("canonical submission facts could not be sealed")

    dependency_files = [
        path for path in (root / "requirements.txt", root / "requirements-dev.txt")
        if path.is_file()
    ]
    dependency_lines = "\n".join(
        f"- `{path.relative_to(root)}` — `{_sha(path)}`" for path in dependency_files
    ) or "- No dependency manifests found."
    facts_lines = _facts_lines(facts, facts_error)
    blocker_lines = "\n".join(f"- {item}" for item in blockers) or "- None."
    parity_lines = (
        f"- Verdict: {parity}\n"
        f"- Local commit: `{commit}`\n"
        f"- Deployed commit: `{deployed_commit or 'unavailable'}`\n"
        f"- Health endpoint: `{health_url}`"
    )
    if parity_detail:
        parity_lines += f"\n- Detail: {parity_detail}"
    status = "READY FOR OPERATOR HOLD POINTS" if not blockers else "NOT READY"
    report = f"""# Release evidence

- **Status:** {status}
- **Generated:** {datetime.now(timezone.utc).isoformat()}
- **Commit:** `{commit}`
- **Python:** `{platform.python_version()}`

## Test invocation

- Command: `python -m pytest tests/ -q --junitxml=artifacts/release/pytest.xml`
- Collected: {counts['collected']}
- Passed: {counts['passed']}
- Skipped: {counts['skipped']}
- Failed: {counts['failed']}
- Errors: {counts['errors']}

## Dependency identities

{dependency_lines}

## Canonical cycle facts

{facts_lines}

## Deployed revision parity

{parity_lines}

## Release blockers

{blocker_lines}

## Non-mutating checks

- `git diff --check`: {'pass' if diff_code == 0 else 'fail'}
- Full local pytest report: {'pass' if not counts['failed'] and not counts['errors'] else 'fail'}
- Canonical facts seal: {'pass' if facts is not None else 'fail'}
- Deployed revision parity: {parity}

Revision parity is a single read-only GET against the deployed /health
endpoint; an unreachable or unstamped deployment is recorded as UNVERIFIED,
never as a pass. This command does not deploy, transmit a bid, perform the
paid repeated Vertex probe, capture authenticated Seller Hub data, or replace
the final media. Those remain explicit operator hold points.
"""
    output = atomic_write_text(output_path, report)
    return output, blockers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junitxml", required=True)
    parser.add_argument("--output", default="docs/evidence/RELEASE.md")
    parser.add_argument("--manifest", default="media/video_manifest.json")
    parser.add_argument("--health-url", default=DEPLOYED_HEALTH_URL)
    args = parser.parse_args(argv)
    try:
        output, blockers = build_report(
            args.junitxml, args.output, manifest_path=args.manifest,
            health_url=args.health_url,
        )
    except (OSError, ValueError, VideoBuildError) as exc:
        print(f"release report failed: {exc}", file=sys.stderr)
        return 2
    print(f"wrote release report: {output}")
    if blockers:
        print("release blocked: " + "; ".join(blockers), file=sys.stderr)
        return 1
    print("release checks passed; operator hold points remain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
