from pathlib import Path

import pytest

from scripts.cdp_capture import (
    CaptureRejected, atomic_publish_png, validate_capture_landing,
)


ROOT = Path(__file__).resolve().parents[1]


def test_challenge_or_wrong_page_is_refused():
    with pytest.raises(CaptureRejected, match="sign-in"):
        validate_capture_landing(
            "https://example.test/research", "https://example.test/login",
            "Sign in", "Sign in to continue", ("Total active listings",),
        )
    with pytest.raises(CaptureRejected, match="marker"):
        validate_capture_landing(
            "https://example.test/research", "https://example.test/research",
            "Research", "No aggregate here", ("Total active listings",),
        )


def test_invalid_capture_preserves_last_known_good(tmp_path):
    output = tmp_path / "evidence.png"
    output.write_bytes(b"known-good")
    with pytest.raises(CaptureRejected, match="valid PNG"):
        atomic_publish_png(output, b"<html>captcha</html>")
    assert output.read_bytes() == b"known-good"


def test_screenshot_set_is_staged_before_any_publication():
    source = (ROOT / "scripts/capture_screenshots.mjs").read_text()
    capture = source.index("completed.push")
    publish = source.index("for (const [partial, destination] of completed)")
    assert capture < publish
    assert "mkdtempSync" in source
