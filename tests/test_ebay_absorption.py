"""Seller Hub imports compute the operator-defined count ratio only."""

import json
from pathlib import Path

import pytest

from scripts.import_ebay_absorption import import_capture
from src.evidence import load_absorption_evidence


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "data/comps/2026-08-22/BT-235/capture.json"


def test_committed_capture_validates_to_units_over_active():
    evidence = import_capture(CAPTURE, reviewer="richmond-general-owner")
    assert evidence.sold_units_last_365_days == 46
    assert evidence.sold_rows == 45
    assert evidence.active_listings_now == 46
    assert evidence.absorption == 1.0
    assert evidence.months_of_supply == 12.0
    assert "days_on_market" not in evidence.as_dict()
    assert set(evidence.source_sha256) >= {
        "capture", "screenshot_sold", "screenshot_active", "sold_rows",
    }


def test_cycle_sidecar_is_the_validated_capture_revision():
    sidecar = ROOT / "data/aug22_gallery_4160518/absorption_evidence.json"
    [record] = load_absorption_evidence(sidecar)
    imported = import_capture(CAPTURE, reviewer="richmond-general-owner")
    assert record == imported


def test_url_dayrange_cannot_substitute_for_the_displayed_window(tmp_path):
    raw = json.loads(CAPTURE.read_text())
    raw["sold"]["window_as_printed_by_page"] = "Jul 23, 2026 – Aug 21, 2026"
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(raw))
    for name in ("sold_365d.png", "active.png", "sold_365d.tsv"):
        (tmp_path / name).write_bytes((CAPTURE.parent / name).read_bytes())
    with pytest.raises(ValueError, match="365 days"):
        import_capture(path, reviewer="operator")


def test_incomplete_pagination_is_refused(tmp_path):
    raw = json.loads(CAPTURE.read_text())
    raw["sold"]["pages_walked"] = "offset 0 only (50 rows; more pages unknown)"
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(raw))
    for name in ("sold_365d.png", "active.png", "sold_365d.tsv"):
        (tmp_path / name).write_bytes((CAPTURE.parent / name).read_bytes())
    with pytest.raises(ValueError, match="pagination"):
        import_capture(path, reviewer="operator")
