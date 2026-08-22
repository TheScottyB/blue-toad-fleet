"""Safety and reproducibility guards for the submission-video workflow."""

from __future__ import annotations

import json
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.video_common import (
    VideoBuildError,
    atomic_media_output,
    load_verified_facts,
    media_duration,
    sha256_file,
)
from src.intake.manifest import clean_caption


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
VIDEO_MANIFEST = ROOT / "media" / "video_manifest.json"


def test_one_authoritative_final_video_owner():
    manifest = json.loads(VIDEO_MANIFEST.read_text())
    assert manifest["final_output"] == "media/blue_toad_fleet_demo.mp4"
    assert (SCRIPTS / "assemble_final.py").is_file()
    assert not (SCRIPTS / "build_video.py").exists()
    owners = []
    for path in SCRIPTS.glob("*"):
        if path.suffix not in {".py", ".mjs"}:
            continue
        if "blue_toad_fleet_demo.mp4" in path.read_text():
            owners.append(path.name)
    assert owners == []  # The authoritative path lives only in the manifest.


def test_video_inputs_and_outputs_are_declared():
    manifest = json.loads(VIDEO_MANIFEST.read_text())
    assert manifest["schema_version"] == 1
    assert manifest["producers"]["final"] == "scripts/assemble_final.py"
    for producer in manifest["producers"].values():
        assert (ROOT / producer).is_file()
    assert len(manifest["beats"]) == 4
    for beat in manifest["beats"]:
        assert set(beat) == {"name", "video", "audio", "max_video_pad_seconds"}
    for name in ("gallery", "beat2", "walkthrough", "terminal"):
        assert manifest["recordings"][name]["output"].endswith(".webm")
    assert manifest["recordings"]["terminal"]["steps"].endswith(".json")


def test_recorders_do_not_scan_a_shared_directory_or_use_global_tmp_pages():
    names = [
        "record_gallery.mjs",
        "record_beat2.mjs",
        "record_terminal.mjs",
        "record_walkthrough.mjs",
        "build_local_gallery.py",
        "build_beat2.py",
        "build_terminal_replay.py",
    ]
    for name in names:
        source = (SCRIPTS / name).read_text()
        assert "readdirSync" not in source
        assert "/tmp/" not in source
    helper = (SCRIPTS / "video_recording.mjs").read_text()
    assert "page.video()" in helper
    assert "mkdtempSync" in helper


def test_assembler_probes_durations_and_publishes_atomically():
    source = (SCRIPTS / "assemble_final.py").read_text()
    assert "media_duration(" in source
    assert "atomic_media_output(" in source
    assert "blue-toad-facts-sha256" in source
    assert "release_eligible" in source
    for stale_duration in ("68.498866", "63.111837", "57.817687", "38.127166"):
        assert stale_duration not in source


def test_atomic_media_output_preserves_last_known_good_on_failure(tmp_path):
    destination = tmp_path / "final.mp4"
    destination.write_bytes(b"known-good")
    with pytest.raises(RuntimeError):
        with atomic_media_output(destination) as temporary:
            temporary.write_bytes(b"partial")
            raise RuntimeError("encoder failed")
    assert destination.read_bytes() == b"known-good"
    assert not list(tmp_path.glob(".*.mp4"))


def test_verified_facts_reject_changed_sources(tmp_path):
    source = tmp_path / "source.json"
    source.write_text('{"version": 1}')
    facts = tmp_path / "facts.json"
    facts.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cycle": {},
                "money": {},
                "tests": {},
                "runtime": {},
                "source_sha256": {"source": sha256_file(source)},
            }
        )
    )
    manifest = {"facts": str(facts), "sources": {"source": str(source)}}
    assert load_verified_facts(manifest)["schema_version"] == 1
    source.write_text('{"version": 2}')
    with pytest.raises(VideoBuildError, match="stale for: source"):
        load_verified_facts(manifest)


def test_narration_placeholders_keep_underscored_fact_names(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    narration = importlib.import_module("generate_narration")
    rendered = narration.render_facts(
        "{{cycle.duplicate_or_non_lot_photos}} and {{money.committed_max|usd}}",
        {
            "cycle": {"duplicate_or_non_lot_photos": 109},
            "money": {"committed_max": 275},
        },
    )
    assert rendered == "109 and 275.00 dollars"


def test_gallery_renderer_escapes_third_party_caption(tmp_path):
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"not decoded by the HTML renderer")
    gallery = tmp_path / "gallery.json"
    gallery.write_text(
        json.dumps(
            {
                "photos": [
                    {
                        "sequence": 1,
                        "photo_id": "p1",
                        "local_path": str(image),
                        "caption": clean_caption('M&amp;Ms <script>alert("x")</script>'),
                        "has_caption": True,
                    }
                ]
            }
        )
    )
    output = tmp_path / "gallery.html"
    manifest = tmp_path / "video.json"
    manifest.write_text(
        json.dumps(
            {
                "sources": {"gallery_manifest": str(gallery)},
                "recordings": {"gallery": {"page": str(output)}},
            }
        )
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "build_local_gallery.py"),
            "--manifest",
            str(manifest),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    rendered = output.read_text()
    assert "M&amp;Ms" in rendered
    assert "M&amp;amp;Ms" not in rendered
    assert "<script>alert" not in rendered
    assert "&lt;script&gt;alert" in rendered


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not installed")
def test_short_footage_cannot_overwrite_existing_final(tmp_path):
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.wav"
    close = tmp_path / "close.png"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.2",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "1",
            str(audio),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=64x64", "-frames:v", "1",
            str(close),
        ],
        check=True,
    )
    destination = tmp_path / "final.mp4"
    destination.write_bytes(b"known-good-final")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "final_output": str(destination),
                "final_contract": {
                    "width": 64,
                    "height": 64,
                    "fps": 30,
                    "max_bytes": 1000000,
                    "duration_tolerance_seconds": 0.2,
                },
                "encoder": {
                    "video_codec": "libx264",
                    "crf": 30,
                    "preset": "ultrafast",
                    "audio_codec": "aac",
                    "audio_bitrate": "64k",
                },
                "close": {"card": str(close), "duration_seconds": 0.2},
                "beats": [
                    {
                        "name": "short",
                        "video": str(video),
                        "audio": str(audio),
                        "max_video_pad_seconds": 0,
                    }
                ],
            }
        )
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "assemble_final.py"), "--manifest", str(manifest)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "shorter than its narration" in result.stderr
    assert destination.read_bytes() == b"known-good-final"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not installed")
def test_assembler_retains_declared_close_card(tmp_path):
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.wav"
    close = tmp_path / "close.png"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=64x64:r=30:d=0.5",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "0.5",
            str(audio),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=64x64", "-frames:v", "1",
            str(close),
        ],
        check=True,
    )
    destination = tmp_path / "final.mp4"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "final_output": str(destination),
                "final_contract": {
                    "width": 64,
                    "height": 64,
                    "fps": 30,
                    "max_bytes": 1000000,
                    "duration_tolerance_seconds": 0.15,
                },
                "encoder": {
                    "video_codec": "libx264",
                    "crf": 30,
                    "preset": "ultrafast",
                    "audio_codec": "aac",
                    "audio_bitrate": "64k",
                },
                "close": {"card": str(close), "duration_seconds": 0.2},
                "beats": [
                    {
                        "name": "beat",
                        "video": str(video),
                        "audio": str(audio),
                        "max_video_pad_seconds": 0.05,
                    }
                ],
            }
        )
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "assemble_final.py"), "--manifest", str(manifest)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert media_duration(destination) == pytest.approx(0.7, abs=0.08)
