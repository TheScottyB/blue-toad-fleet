#!/usr/bin/env python3
"""Canonical orchestration entry point for the declared submission media build."""

try:
    from video_pipeline import main          # direct: python scripts/build_media.py
except ImportError:                          # module: python -m scripts.build_media
    from scripts.video_pipeline import main


if __name__ == "__main__":
    raise SystemExit(main())
