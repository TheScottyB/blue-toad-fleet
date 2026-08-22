#!/usr/bin/env python3
"""Run the declared submission-video workflow in explicit, reproducible stages."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "media/video_manifest.json"


def run(label: str, command: list[str]) -> None:
    print(f"\n[{label}] {' '.join(command)}", flush=True)
    try:
        subprocess.run(command, cwd=ROOT, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"required program is not installed: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"video stage failed: {label}") from exc


def python_script(name: str, *args: str) -> list[str]:
    return [sys.executable, str(ROOT / "scripts" / name), *args]


def node_script(name: str, *args: str) -> list[str]:
    return ["node", str(ROOT / "scripts" / name), *args]


def prepare(manifest: str) -> None:
    # Module execution gives the facts collector a stable package import path.
    run(
        "verified facts",
        [sys.executable, "-m", "scripts.build_submission_facts", "--manifest", manifest],
    )
    run("terminal proof", python_script("capture_terminal_proof.py", "--manifest", manifest))
    run("title cards", node_script("make_title_cards.mjs", "--manifest", manifest))
    run(
        "architecture diagram",
        python_script("generate_architecture_diagram.py", "--manifest", manifest),
    )
    run("gallery page", python_script("build_local_gallery.py", "--manifest", manifest))
    run("Beat 2 page", python_script("build_beat2.py", "--manifest", manifest))
    run("terminal page", python_script("build_terminal_replay.py", "--manifest", manifest))


def narration(manifest: str) -> None:
    run("narration", python_script("generate_narration.py", "--manifest", manifest))


def record(manifest: str) -> None:
    run("gallery recording", node_script("record_gallery.mjs", "--manifest", manifest))
    run("Beat 2 recording", node_script("record_beat2.mjs", "--manifest", manifest))
    run("walkthrough recording", node_script("record_walkthrough.mjs", "--manifest", manifest))
    run("terminal recording", node_script("record_terminal.mjs", "--manifest", manifest))


def compose(manifest: str) -> None:
    run("Beat 1 composite", python_script("build_beat1.py", "--manifest", manifest))
    run(
        "Beat 2 normalization",
        python_script("transcode_recording.py", "beat2", "--manifest", manifest),
    )
    run("Beat 3 overlays", python_script("build_beat3.py", "--manifest", manifest))
    run(
        "Beat 4 normalization",
        python_script("transcode_recording.py", "terminal", "--manifest", manifest),
    )


def assemble(manifest: str) -> None:
    run("final assembly", python_script("assemble_final.py", "--manifest", manifest))


def verify(manifest: str) -> None:
    run(
        "final verification",
        python_script("assemble_final.py", "--manifest", manifest, "--verify-only"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=["prepare", "narration", "record", "compose", "assemble", "verify", "all"],
    )
    parser.add_argument("--manifest", default=MANIFEST)
    args = parser.parse_args(argv)
    manifest = (
        os.path.relpath(Path(args.manifest).resolve(), ROOT)
        if Path(args.manifest).is_absolute()
        else args.manifest
    )
    try:
        if args.stage in {"prepare", "all"}:
            prepare(manifest)
        if args.stage in {"narration", "all"}:
            narration(manifest)
        if args.stage in {"record", "all"}:
            record(manifest)
        if args.stage in {"compose", "all"}:
            compose(manifest)
        if args.stage in {"assemble", "all"}:
            assemble(manifest)
        if args.stage == "verify":
            verify(manifest)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
