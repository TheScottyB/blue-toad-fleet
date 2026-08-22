"""Source downloads must fail closed without damaging the last usable cache."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image

from scripts.cache_gallery import download_image
from scripts.test_vertex_live import prepare_live_image
from src.intake.manifest import clean_caption


def _image(fmt: str = "WEBP") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (560, 420), (80, 90, 100)).save(buffer, format=fmt)
    return buffer.getvalue()


class _Response:
    def __init__(self, body: bytes, content_type: str):
        self._body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self._body


def test_verified_webp_download_is_atomic_and_records_evidence(tmp_path):
    body = _image("WEBP")

    def opener(_request, timeout):
        assert timeout == 15
        return _Response(body, "image/webp; charset=binary")

    destination = tmp_path / "photo.jpg"
    result = download_image("https://example.test/photo", destination, opener=opener)

    assert result.ok
    assert destination.read_bytes() == body
    assert result.sha256 == hashlib.sha256(body).hexdigest()
    assert (result.mime_type, result.width, result.height) == ("image/webp", 560, 420)
    assert not list(tmp_path.glob("*.partial"))


def test_html_response_fails_and_preserves_last_known_bytes(tmp_path):
    destination = tmp_path / "photo.jpg"
    destination.write_bytes(b"known-good-before-refresh")

    def opener(_request, timeout):
        return _Response(b"<html>challenge</html>", "text/html")

    result = download_image(
        "https://example.test/photo", destination, max_retries=1, opener=opener)

    assert not result.ok
    assert "not image" in result.error
    assert destination.read_bytes() == b"known-good-before-refresh"


def test_mime_mismatch_fails_without_publishing_bytes(tmp_path):
    destination = tmp_path / "photo.jpg"

    def opener(_request, timeout):
        return _Response(_image("WEBP"), "image/jpeg")

    result = download_image(
        "https://example.test/photo", destination, max_retries=1, opener=opener)

    assert not result.ok
    assert "bytes are image/webp" in result.error
    assert not destination.exists()


def test_interrupted_read_preserves_last_known_bytes(tmp_path):
    destination = tmp_path / "photo.jpg"
    destination.write_bytes(b"known-good-before-refresh")

    class BrokenResponse(_Response):
        def read(self):
            raise ConnectionError("connection reset mid-body")

    result = download_image(
        "https://example.test/photo",
        destination,
        max_retries=1,
        opener=lambda *_args, **_kwargs: BrokenResponse(b"", "image/webp"),
    )

    assert not result.ok
    assert "connection reset" in result.error
    assert destination.read_bytes() == b"known-good-before-refresh"


def test_caption_entities_are_decoded_once_at_ingestion():
    assert clean_caption("Preview image for M&amp;amp;Ms") == "M&amp;Ms"


def test_production_downloaders_do_not_disable_tls_verification():
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "scripts/cache_gallery.py",
        "scripts/recache_full_size.py",
        "scripts/dry_run_single_photo.py",
    ):
        source = (root / relative).read_text()
        assert "CERT_NONE" not in source
        assert "check_hostname = False" not in source
        assert "_create_unverified_context" not in source


def test_live_probe_detects_webp_in_a_jpg_named_file(tmp_path):
    path = tmp_path / "sample.jpg"
    path.write_bytes(_image("WEBP"))
    body, mime_type = prepare_live_image(path)
    assert body == path.read_bytes()
    assert mime_type == "image/webp"


def test_live_probe_refuses_text_only_fallback(tmp_path):
    missing = tmp_path / "missing.jpg"
    try:
        prepare_live_image(missing)
    except FileNotFoundError as exc:
        assert "requires a real sample image" in str(exc)
    else:  # pragma: no cover - documents the release-gate contract.
        raise AssertionError("missing sample must not become a text-only live probe")
