#!/usr/bin/env python3
"""Generate the versioned evidence snapshot consumed by video renderers.

The snapshot is published atomically only after the full local test suite passes.
Photo/group counts are recomputed through the same grouping functions as the
application instead of copied from prose or old title cards.
"""

from __future__ import annotations

import argparse
import json
import platform
import shlex
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from scripts.run_vertex_pipeline import trusted_lot_flags
from scripts.video_common import (
    VideoBuildError,
    atomic_write_text,
    display_path,
    load_json_object,
    project_path,
    require_file,
    require_keys,
    sha256_file,
)
from src.appraiser.routing import APPRAISAL_MODEL, CURATOR_MODEL, TRIAGE_MODEL
from src.intake import (
    TriagedPhoto,
    group_into_lots,
    load_reshoot_edges,
    merge_reshoots,
)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=project_path("."),
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _test_counts(junit_path: Path) -> dict:
    try:
        root = ET.parse(junit_path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise VideoBuildError(f"invalid pytest JUnit report: {exc}") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise VideoBuildError("pytest JUnit report contains no test suites")
    totals = {
        key: sum(int(float(suite.attrib.get(key, 0))) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    totals["passed"] = (
        totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
    )
    if totals["tests"] <= 0 or totals["passed"] < 0:
        raise VideoBuildError("pytest JUnit report contains impossible test totals")
    return {
        "collected": totals["tests"],
        "passed": totals["passed"],
        "skipped": totals["skipped"],
        "failed": totals["failures"],
        "errors": totals["errors"],
    }


def _run_tests() -> tuple[dict, str]:
    with tempfile.TemporaryDirectory(prefix="blue-toad-video-tests-") as directory:
        report = Path(directory) / "pytest.xml"
        command = [sys.executable, "-m", "pytest", "-q", f"--junitxml={report}"]
        result = subprocess.run(
            command,
            cwd=project_path("."),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            tail = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-30:])
            raise VideoBuildError(
                "submission facts were not published because pytest failed:\n" + tail
            )
        return _test_counts(report), shlex.join(command[:-1] + ["--junitxml=<temporary>"])


def _load_test_results(junit_value: str) -> tuple[dict, str]:
    report = require_file(junit_value, "pytest JUnit report")
    counts = _test_counts(report)
    if counts["failed"] or counts["errors"]:
        raise VideoBuildError("refusing to publish facts from a failing JUnit report")
    return counts, f"pytest report: {display_path(report)}"


def _group_counts(
    gallery: dict,
    triage: list,
    embedding_cache: Path,
    manifest_sha256: str,
) -> tuple[int, int, int]:
    photos = gallery.get("photos")
    if not isinstance(photos, list) or not photos:
        raise VideoBuildError("gallery manifest has no photos")
    verdicts = {
        item.get("photo_id"): item
        for item in triage
        if isinstance(item, dict) and item.get("photo_id")
    }
    if len(verdicts) != len(photos):
        raise VideoBuildError(
            f"triage coverage is {len(verdicts)}/{len(photos)}; refusing partial video facts"
        )

    triaged: list[TriagedPhoto] = []
    for index, photo in enumerate(photos):
        caption = str(photo.get("caption") or "")
        is_lot, same = trusted_lot_flags(
            verdicts.get(photo.get("photo_id")),
            caption,
            bool(index and photos[index - 1].get("has_caption")),
            index,
        )
        triaged.append(
            TriagedPhoto(
                photo_id=str(photo["photo_id"]),
                caption=caption,
                is_lot=is_lot,
                same_lot_as_previous=same,
            )
        )

    sequential_groups = group_into_lots(triaged)
    photo_by_sequence = {int(photo["sequence"]): str(photo["photo_id"]) for photo in photos}
    sequences = {str(photo["photo_id"]): int(photo["sequence"]) for photo in photos}
    edges = load_reshoot_edges(
        embedding_cache,
        photo_by_sequence,
        sequences,
        expected_manifest_sha256=manifest_sha256,
    )
    groups = merge_reshoots(sequential_groups, edges)
    return len(groups), len(photos) - len(groups), len(edges)


def collect(manifest_value: str, output_value: str | None, junit_value: str | None) -> Path:
    video_manifest = load_json_object(manifest_value, "video manifest")
    require_keys(video_manifest, ["schema_version", "facts", "sources"], "video manifest")
    sources = video_manifest["sources"]
    require_keys(
        sources,
        [
            "gallery_manifest",
            "triage_results",
            "appraisal_results",
            "embedding_cache",
            "reshoot_edges",
            "pipeline_state",
        ],
        "video sources",
    )
    source_paths = {name: require_file(value, f"video source {name}") for name, value in sources.items()}

    gallery = load_json_object(source_paths["gallery_manifest"], "gallery manifest")
    pipeline_state = load_json_object(source_paths["pipeline_state"], "pipeline state")
    try:
        triage = json.loads(source_paths["triage_results"].read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VideoBuildError(f"invalid triage results: {exc}") from exc
    if not isinstance(triage, list):
        raise VideoBuildError("triage results must be a JSON list")

    groups, duplicates, similarity_edges = _group_counts(
        gallery,
        triage,
        source_paths["embedding_cache"],
        sha256_file(source_paths["gallery_manifest"]),
    )

    summary = pipeline_state.get("summary")
    if not isinstance(summary, dict):
        raise VideoBuildError("pipeline state has no summary object")
    required_summary = [
        "allocated",
        "skipped",
        "committed_max",
        "committed_all_in",
        "needs_human_pricing",
    ]
    require_keys(summary, required_summary, "pipeline summary")
    state_groups = int(summary.get("total_lots", pipeline_state.get("total_lots_count", -1)))
    if state_groups != groups:
        raise VideoBuildError(
            f"pipeline state reports {state_groups} groups but canonical grouping produces "
            f"{groups}; rerun the canonical pipeline before rendering video facts"
        )
    classified_groups = (
        int(summary["allocated"])
        + int(summary["skipped"])
        + int(summary["needs_human_pricing"])
    )
    if classified_groups != groups:
        raise VideoBuildError(
            f"pipeline summary classifies {classified_groups}/{groups} groups; "
            "refusing contradictory video facts"
        )
    photos = len(gallery["photos"])
    captioned = sum(bool(photo.get("has_caption")) for photo in gallery["photos"])
    payload = json.loads(source_paths["appraisal_results"].read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise VideoBuildError("appraisal results must be a JSON list")
    appraised = len(payload)
    tests, test_command = (
        _load_test_results(junit_value) if junit_value else _run_tests()
    )

    commit = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain"))
    snapshot = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git": {"commit": commit, "dirty": dirty},
        "cycle": {
            "cycle_id": pipeline_state.get("cycle_id"),
            "listing_id": pipeline_state.get("listing_id"),
            "photos": photos,
            "captioned_photos": captioned,
            "uncaptioned_photos": photos - captioned,
            "groups": groups,
            "duplicate_or_non_lot_photos": duplicates,
            "similarity_edges": similarity_edges,
            "appraised": appraised,
            "approved_bids": int(summary["allocated"]),
            "skipped": int(summary["skipped"]),
            "needs_human_pricing": int(summary["needs_human_pricing"]),
        },
        "money": {
            "budget_cap": float(pipeline_state["budget_cap"]),
            "committed_max": float(summary["committed_max"]),
            "committed_all_in": float(summary["committed_all_in"]),
        },
        "tests": {**tests, "command": test_command},
        "runtime": {
            "python": platform.python_version(),
            "models": {
                "triage": TRIAGE_MODEL,
                "appraisal": APPRAISAL_MODEL,
                "curator": CURATOR_MODEL,
            },
        },
        "source_sha256": {
            name: sha256_file(path) for name, path in sorted(source_paths.items())
        },
    }
    output = output_value or str(video_manifest["facts"])
    return atomic_write_text(output, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="media/video_manifest.json")
    parser.add_argument("--output")
    parser.add_argument(
        "--junitxml",
        help="use an existing successful pytest JUnit report instead of running pytest",
    )
    args = parser.parse_args(argv)
    try:
        output = collect(args.manifest, args.output, args.junitxml)
    except (OSError, ValueError, VideoBuildError) as exc:
        print(f"facts collection failed: {exc}", file=sys.stderr)
        return 1
    print(f"wrote verified submission facts: {display_path(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
