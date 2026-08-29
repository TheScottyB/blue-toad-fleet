# tests/core/test_image.py
import pytest
from src.blue_toad.processing.image import sha256_bytes, validate_image_bytes


def test_sha256_bytes_is_stable():
    assert sha256_bytes(b"hello") == sha256_bytes(b"hello")
    assert sha256_bytes(b"hello") != sha256_bytes(b"world")
    assert len(sha256_bytes(b"hello")) == 64


def test_validate_image_bytes_rejects_empty_and_returns_hash():
    with pytest.raises(ValueError):
        validate_image_bytes(b"")
    digest = validate_image_bytes(b"x" * 32)
    assert digest == sha256_bytes(b"x" * 32)
