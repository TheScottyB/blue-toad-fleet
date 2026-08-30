#!/usr/bin/env python3
"""Seal the Aug-22 cycle's artifact manifest through the real publisher.

Operator ruling 2026-08-29 ("local seal via cycle publisher", chosen over
waiving the check and over a full cloud publish): run the owned publisher
path — CycleRepository.publish_outputs — against a local file-backend store
over the resealed Aug-22 output, so the sealed manifest is produced by the
same code that seals cloud cycles, never hand-written.

One deliberate divergence from the cloud staging flow, and why it is the
ruling's own recipe rather than a shortcut: stage_directory normalizes the
manifest (rewrites local_paths, embeds image digests) for worker durability,
so a normalized staging could never satisfy _publication_facts, which
compares source_manifest_sha256 against the sha256 of the fixture file
itself. The seal therefore stages the gallery manifest bytes RAW; the
publisher then derives source_manifest_sha256 from those bytes, and the
collect check passes by construction. Image blobs are not staged — the
publisher only blobs the OUTPUT artifacts, and the fixture's images live in
the repository already.

The worker's wide-union question gate is not in this path by design: that
gate guards unreviewed fresh cycles, and this seal covers the operator-
reviewed Aug-22 fixture (see the 2026-08-29 ruling comment in
src/cycles/worker.py).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_vertex_pipeline import (
    email_artifact_path, pipeline_state_path, sheet_artifact_path,
)
from src.cycles.model import CycleRequest
from src.cycles.storage import CycleRepository, LocalObjectStore

AUG22_DATA_DIR = Path("data/aug22_gallery_4160518")


def aug22_output_artifacts() -> tuple[Path, ...]:
    """The cycle's own money artifacts — the set the cloud worker publishes.

    Paths come from the owner module's canonical path helpers, never restated
    as literals (the artifact-ownership referee enforces a single writer per
    protected path, and a reader restating the literal is indistinguishable
    from a second writer to that scan). submission_facts.json is deliberately
    NOT sealed: it derives from the sealed state and records the seal itself,
    so including it would be circular and stale on the next facts regen.
    """
    data_path = AUG22_DATA_DIR
    output_path = data_path.parent
    return (
        pipeline_state_path(data_path, output_path, False),
        email_artifact_path(data_path, output_path, False),
        sheet_artifact_path(data_path, output_path, False),
    )


def seal_cycle_outputs(
    *,
    store_root: Path,
    gallery_manifest: Path,
    output_dir: Path,
    request: CycleRequest,
    export_to: Path,
) -> Path:
    """Publish output_dir through the real publisher; export the sealed manifest.

    Returns the sealed manifest's path inside the store. export_to receives a
    byte-identical copy (asserted) for declaration under video_manifest.json.
    """
    repo = CycleRepository(LocalObjectStore(str(store_root)))
    raw_manifest = Path(gallery_manifest).read_bytes()
    request_record = request.as_dict()
    request_name = repo.request_name(request)
    if repo.objects.exists(request_name):
        existing = json.loads(repo.objects.get_bytes(request_name))
        drop = lambda d: {k: v for k, v in d.items() if k != "created_at"}  # noqa: E731
        if drop(existing) != drop(request_record):
            raise RuntimeError(
                "store holds a different request for this cycle id; "
                "use a fresh store root")
    else:
        repo.put_json(request_name, request_record, if_absent=True)
    input_name = f"{request.prefix}/input/manifest.json"
    if not repo.objects.exists(input_name):
        repo.objects.put_bytes(
            input_name, raw_manifest,
            content_type="application/json", if_absent=True,
        )
    staged = repo.objects.get_bytes(input_name)
    if hashlib.sha256(staged).hexdigest() != hashlib.sha256(raw_manifest).hexdigest():
        raise RuntimeError(
            "store already holds a different staged manifest for this cycle; "
            "use a fresh store root rather than resealing over it")

    manifest = repo.publish_outputs(request, output_dir)

    sealed_name = repo.artifact_manifest_name(request)
    sealed_bytes = repo.objects.get_bytes(sealed_name)
    if json.loads(sealed_bytes) != manifest:
        raise RuntimeError("publisher returned a manifest the store does not hold")
    export = Path(export_to)
    export.parent.mkdir(parents=True, exist_ok=True)
    export.write_bytes(sealed_bytes)
    sealed_path = Path(str(store_root)) / sealed_name
    return sealed_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store-root", type=Path, default=None,
        help="local store root (default: a fresh temporary directory)")
    parser.add_argument(
        "--export-to", type=Path,
        default=ROOT / AUG22_DATA_DIR / "artifact_manifest.json")
    args = parser.parse_args(argv)

    request = CycleRequest(
        cycle_id="2026-08-22",
        listing_id="4160518",
        auction_title="Blue Toad Auctions Estate Sale",
        auction_date="2026-08-22",
        timezone_name="America/Chicago",
        venue="200 Elizabeth Lane, Genoa City, WI",
        deadline="2026-08-21T16:00:00-05:00",
    )
    with tempfile.TemporaryDirectory(prefix="btf-seal-") as scratch:
        store_root = args.store_root or Path(scratch) / "store"
        output_dir = Path(scratch) / "output"
        output_dir.mkdir(parents=True)
        for rel in aug22_output_artifacts():
            source = ROOT / rel
            if not source.is_file():
                print(f"seal failed: missing output artifact {rel}", file=sys.stderr)
                return 1
            shutil.copy2(source, output_dir / source.name)
        try:
            seal_cycle_outputs(
                store_root=store_root,
                gallery_manifest=ROOT / AUG22_DATA_DIR / "manifest.json",
                output_dir=output_dir,
                request=request,
                export_to=args.export_to,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"seal failed: {exc}", file=sys.stderr)
            return 1
    exported = json.loads(Path(args.export_to).read_text())
    print(f"sealed artifact manifest exported: {args.export_to}")
    print(f"  schema_version: {exported['schema_version']}")
    print(f"  source_manifest_sha256: {exported['source_manifest_sha256']}")
    print(f"  artifacts: {sorted(exported['artifacts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
