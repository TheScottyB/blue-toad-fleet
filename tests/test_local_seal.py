"""The local seal runs the real publisher and satisfies the collect check.

Operator ruling 2026-08-29 ("local seal via cycle publisher"): the Aug-22
fixture's artifact manifest is produced by CycleRepository.publish_outputs
against a file-backend store — not hand-written — staging the gallery
manifest bytes RAW so the sealed source_manifest_sha256 equals the sha256 of
the fixture file, which is exactly what _publication_facts compares against.
"""

import hashlib
import json
from pathlib import Path

from scripts.collect_submission_facts import _publication_facts
from scripts.seal_aug22_artifacts import seal_cycle_outputs
from src.cycles.model import CycleRequest


def _request() -> CycleRequest:
    return CycleRequest(
        cycle_id="2099-01-01",
        listing_id="999",
        auction_title="Test Sale",
        auction_date="2099-01-01",
        timezone_name="America/Chicago",
        venue="Test Venue",
        deadline="2098-12-31T16:00:00-06:00",
    )


def test_seal_runs_the_real_publisher_and_collect_accepts_it(tmp_path):
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    manifest_path = gallery / "manifest.json"
    manifest_path.write_text(json.dumps({
        "listing_id": "999",
        "photos": [{"photo_id": "p1", "filename": "a.jpg",
                    "sequence": 1, "caption": "x", "has_caption": True}],
    }))
    state = {"decisions": [], "summary": {}, "queue": {}}
    outputs = tmp_path / "out"
    outputs.mkdir()
    (outputs / "pipeline_state.json").write_text(json.dumps(state))
    (outputs / "email.txt").write_text("draft")

    sealed = seal_cycle_outputs(
        store_root=tmp_path / "store",
        gallery_manifest=manifest_path,
        output_dir=outputs,
        request=_request(),
        export_to=tmp_path / "artifact_manifest.json",
    )

    exported = json.loads((tmp_path / "artifact_manifest.json").read_text())
    assert exported == json.loads(Path(sealed).read_text())
    assert exported["schema_version"] == 2
    assert exported["source_manifest_sha256"] == hashlib.sha256(
        manifest_path.read_bytes()).hexdigest()
    assert "pipeline_state.json" in exported["artifacts"]

    publication = _publication_facts(
        {"sources": {"gallery_manifest": str(manifest_path),
                     "artifact_manifest": str(tmp_path / "artifact_manifest.json")}},
        {"gallery_manifest": manifest_path},
    )
    assert publication["release_eligible"] is True
    assert publication["status"] == "published"


def test_seal_is_idempotent_for_identical_outputs(tmp_path):
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    (gallery / "manifest.json").write_text(json.dumps({
        "listing_id": "999", "photos": [{"photo_id": "p1", "filename": "a.jpg"}],
    }))
    outputs = tmp_path / "out"
    outputs.mkdir()
    (outputs / "pipeline_state.json").write_text(json.dumps({"decisions": []}))

    kwargs = dict(
        store_root=tmp_path / "store",
        gallery_manifest=gallery / "manifest.json",
        output_dir=outputs,
        request=_request(),
        export_to=tmp_path / "artifact_manifest.json",
    )
    first = json.loads(Path(seal_cycle_outputs(**kwargs)).read_text())
    second = json.loads(Path(seal_cycle_outputs(**kwargs)).read_text())
    assert first["artifacts"] == second["artifacts"]
