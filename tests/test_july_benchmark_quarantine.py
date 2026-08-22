"""The invalid historical A/B output cannot leak into a submission release."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_historical_runner_refuses_to_publish(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_july11_benchmark.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "historical/unverified" in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_judged_copy_does_not_cite_corrupt_benchmark_figures_or_artifact():
    forbidden = (
        "14,340",
        "1,910",
        "2,196.50",
        "BlueToad_2026-07-11_Benchmark_Comparison.xlsx",
    )
    for relative in ("README.md", "docs/DEVPOST.md"):
        text = (ROOT / relative).read_text()
        for claim in forbidden:
            assert claim not in text, f"{relative} still presents quarantined {claim}"


def test_quarantined_runner_contains_no_synthetic_release_path():
    source = (ROOT / "scripts/run_july11_benchmark.py").read_text()
    assert "VALUATION_TAXONOMY" not in source
    assert "openpyxl" not in source
    assert "zip(lots, decisions)" not in source
