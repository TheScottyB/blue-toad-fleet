import json
from pathlib import Path

import numpy as np

from scripts.probes.rescore_upscaling import ssim


ROOT = Path(__file__).resolve().parents[1]


def test_ssim_matches_the_declared_closed_form_reference_fixture():
    fixture = json.loads((
        ROOT / "artifacts/signature_upscale_probe/ssim_reference_fixture.json"
    ).read_text())
    a = np.full(fixture["shape"], fixture["field_a"], dtype=float)
    b = np.full(fixture["shape"], fixture["field_b"], dtype=float)
    assert abs(ssim(a, b, L=fixture["data_range"]) - fixture["expected_ssim"]) \
        <= fixture["tolerance"]


def test_ssim_identity_is_one():
    image = np.arange(32 * 32, dtype=float).reshape(32, 32) % 256
    assert ssim(image, image) == 1.0


def test_embedding_probe_consumes_committed_json_not_untracked_npz():
    source = (ROOT / "scripts/probes/task3_baselines.py").read_text()
    assert "embeddings.json" in source
    assert "embeddings.npz" not in source
