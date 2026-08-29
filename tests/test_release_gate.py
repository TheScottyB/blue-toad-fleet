"""The release gate reports blockers without mutating an external system."""

import http.server
import json
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path

from scripts.build_release_report import (
    _facts_blockers,
    _revision_parity,
    build_report,
)

ROOT = Path(__file__).resolve().parents[1]

# Port 9 (discard) is closed on any sane workstation: the connection is
# refused immediately, which is exactly the "deploy unreachable" case.
UNREACHABLE_HEALTH = "http://127.0.0.1:9/health"


def _junit(path: Path) -> Path:
    path.write_text(
        '<testsuites><testsuite tests="3" failures="0" errors="0" skipped="1"/>'
        '</testsuites>'
    )
    return path


class _HealthHandler(http.server.BaseHTTPRequestHandler):
    payload: dict = {}

    def do_GET(self):
        body = json.dumps(self.payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@contextmanager
def _health_endpoint(payload: dict):
    handler = type("Handler", (_HealthHandler,), {"payload": payload})
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/health"
    finally:
        server.shutdown()


def _local_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
        check=True,
    ).stdout.strip()


def test_facts_blockers_require_release_eligibility_and_clean_tree():
    assert _facts_blockers({
        "publication": {"release_eligible": True},
        "git": {"dirty": False},
    }) == []
    blockers = _facts_blockers({
        "publication": {
            "release_eligible": False,
            "reason": "allocated lots have unresolved questions",
            "blocking_lot_ids": ["BT-002"],
        },
        "git": {"dirty": True},
    })
    assert any("unresolved questions" in item for item in blockers)
    assert any("BT-002" in item for item in blockers)
    assert any("dirty working tree" in item for item in blockers)


def test_current_historical_fixture_produces_a_written_blocked_report(tmp_path):
    output, blockers = build_report(
        _junit(tmp_path / "pytest.xml"), tmp_path / "RELEASE.md",
        health_url=UNREACHABLE_HEALTH,
    )
    text = output.read_text()
    assert blockers
    assert "**Status:** NOT READY" in text
    assert "Collected: 3" in text
    assert "Canonical cycle facts" in text
    assert "does not deploy" in text


def test_revision_parity_fails_closed():
    assert _revision_parity("abc", "abc", None) == ("MATCH", None)
    assert _revision_parity("abc", "def", None)[0] == "MISMATCH"

    verdict, detail = _revision_parity("abc", None, "connection refused")
    assert verdict == "UNVERIFIED"
    assert "connection refused" in detail

    # An unknown local commit can never manufacture a MATCH.
    assert _revision_parity("unknown", "abc", None)[0] == "UNVERIFIED"
    # Nor can an absent deployed commit with no recorded error.
    assert _revision_parity("abc", None, None)[0] == "UNVERIFIED"


def test_unreachable_deploy_is_recorded_unverified_never_as_a_pass(tmp_path):
    output, blockers = build_report(
        _junit(tmp_path / "pytest.xml"), tmp_path / "RELEASE.md",
        health_url=UNREACHABLE_HEALTH,
    )
    text = output.read_text()
    assert "- Deployed revision parity: UNVERIFIED" in text
    assert "- Verdict: UNVERIFIED" in text
    assert any("parity is unverified" in item for item in blockers)


def test_matching_deployed_commit_is_recorded_as_match(tmp_path):
    head = _local_head()
    with _health_endpoint({"git_commit": head}) as url:
        output, blockers = build_report(
            _junit(tmp_path / "pytest.xml"), tmp_path / "RELEASE.md",
            health_url=url,
        )
    text = output.read_text()
    assert "- Deployed revision parity: MATCH" in text
    assert f"- Deployed commit: `{head}`" in text
    assert not any("parity" in item for item in blockers)
    assert not any("audited commit" in item for item in blockers)


def test_mismatched_deployed_commit_blocks_release(tmp_path):
    with _health_endpoint({"git_commit": "0" * 40}) as url:
        output, blockers = build_report(
            _junit(tmp_path / "pytest.xml"), tmp_path / "RELEASE.md",
            health_url=url,
        )
    text = output.read_text()
    assert "- Deployed revision parity: MISMATCH" in text
    assert any("does not match the audited commit" in item for item in blockers)


def test_health_payload_without_a_commit_is_unverified(tmp_path):
    with _health_endpoint({"status": "healthy"}) as url:
        output, blockers = build_report(
            _junit(tmp_path / "pytest.xml"), tmp_path / "RELEASE.md",
            health_url=url,
        )
    text = output.read_text()
    assert "- Deployed revision parity: UNVERIFIED" in text
    assert any("parity is unverified" in item for item in blockers)


def test_deploy_script_stamps_the_commit_into_the_service_env():
    text = (ROOT / "infra" / "deploy.sh").read_text()
    assert "git rev-parse HEAD" in text
    service_env = next(
        line for line in text.splitlines() if line.startswith("SERVICE_ENV=")
    )
    assert "GIT_COMMIT=${GIT_COMMIT}" in service_env
