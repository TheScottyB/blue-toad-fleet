#!/usr/bin/env python3
"""Capture the manifest-declared terminal proof commands without a shell."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from video_common import (
    VideoBuildError,
    atomic_write_text,
    display_path,
    load_json_object,
    project_path,
    require_keys,
)


def capture(manifest_value: str, output_value: str | None) -> None:
    manifest = load_json_object(manifest_value, "video manifest")
    terminal = manifest.get("recordings", {}).get("terminal", {})
    require_keys(terminal, ["steps", "commands"], "terminal recording")
    commands = terminal["commands"]
    if not isinstance(commands, list) or not commands:
        raise VideoBuildError("terminal recording must declare at least one command")
    steps: list[dict] = []
    for index, command in enumerate(commands, 1):
        if not isinstance(command, dict):
            raise VideoBuildError(f"terminal command {index} must be an object")
        require_keys(command, ["display", "argv"], f"terminal command {index}")
        argv = command["argv"]
        if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
            raise VideoBuildError(f"terminal command {index} argv must be a non-empty string list")
        try:
            result = subprocess.run(
                argv,
                cwd=project_path("."),
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except FileNotFoundError as exc:
            raise VideoBuildError(f"terminal proof program is missing: {argv[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise VideoBuildError(f"terminal proof command timed out: {command['display']}") from exc
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            raise VideoBuildError(
                f"terminal proof command failed ({command['display']}):\n{output[-2000:]}"
            )
        steps.append({"cmd": str(command["display"]), "out": output})
    destination = atomic_write_text(
        output_value or terminal["steps"], json.dumps(steps, indent=2) + "\n"
    )
    print(f"captured {len(steps)} terminal proof steps: {display_path(destination)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="media/video_manifest.json")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        capture(args.manifest, args.output)
    except (OSError, ValueError, VideoBuildError) as exc:
        print(f"terminal proof capture failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
