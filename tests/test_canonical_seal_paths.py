"""The canonical rerun must agree three ways: find the fixture caches, seal
pipeline_state.json where media/video_manifest.json points, and keep the money
artifacts on their protected historical paths. This exact drift — cache lookup
following --output-dir, state sealing where the facts collector never looks —
burned two aborted full-price runs on 2026-08-29."""

import json
from pathlib import Path

from scripts.run_vertex_pipeline import (
    email_artifact_path,
    pipeline_cache_dir,
    pipeline_state_path,
    publish_absorption_evidence,
    sheet_artifact_path,
)
from src.cycles.ownership import PROTECTED_ARTIFACT_OWNERS

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path("data/aug22_gallery_4160518")


def test_canonical_invocation_agrees_three_ways():
    # The canonical invocation: the fixture data dir, no explicit output.
    output_dir = None
    output_path = DATA_DIR.parent
    explicit = bool(output_dir)

    # 1. Caches are cycle inputs living beside the manifest; the lookup must
    #    be the data dir no matter where outputs are routed.
    assert pipeline_cache_dir(DATA_DIR, output_dir) == DATA_DIR
    assert pipeline_cache_dir(DATA_DIR, Path("somewhere/else")) == DATA_DIR

    # 2. The state seals exactly where the facts collector reads.
    manifest = json.loads((ROOT / "media" / "video_manifest.json").read_text())
    assert pipeline_state_path(DATA_DIR, output_path, explicit) == Path(
        manifest["sources"]["pipeline_state"]
    )

    # 3. The money artifacts stay on their protected historical paths,
    #    refereed by the ownership declaration itself.
    assert str(email_artifact_path(DATA_DIR, output_path, explicit)) in (
        PROTECTED_ARTIFACT_OWNERS
    )
    assert str(sheet_artifact_path(DATA_DIR, output_path, explicit)) in (
        PROTECTED_ARTIFACT_OWNERS
    )


def test_explicit_output_keeps_publishable_artifacts_in_output_dir():
    # The cloud worker publishes everything from its own output_dir; an
    # explicit run must keep state and artifacts there while still finding
    # the caches staged in its input dir.
    data_path, output_path = Path("input"), Path("output")
    assert pipeline_cache_dir(data_path, output_path) == data_path
    assert pipeline_state_path(data_path, output_path, True) == (
        output_path / "pipeline_state.json"
    )
    assert email_artifact_path(data_path, output_path, True) == (
        output_path / "absentee_bid_email.txt"
    )
    assert sheet_artifact_path(data_path, output_path, True) == (
        output_path / "bid_sheet.xlsx"
    )


def test_absorption_publish_treats_same_file_as_a_no_op(tmp_path):
    # output_dir == data_dir crashed the 2026-08-29 paid run at its very last
    # step with shutil.SameFileError — after every appraisal was bought.
    source = tmp_path / "absorption_evidence.json"
    source.write_text("[]")
    assert publish_absorption_evidence(source, tmp_path, True, True) is False
    assert source.read_text() == "[]"

    elsewhere = tmp_path / "out"
    elsewhere.mkdir()
    assert publish_absorption_evidence(source, elsewhere, True, True) is True
    assert (elsewhere / "absorption_evidence.json").read_text() == "[]"

    # The canonical (non-explicit) run never publishes a copy.
    assert publish_absorption_evidence(source, elsewhere, False, True) is False
