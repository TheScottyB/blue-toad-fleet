#!/usr/bin/env python3
"""Build the manifest-backed local gallery page used by the Beat 1 recorder."""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

from video_common import (
    VideoBuildError,
    atomic_write_text,
    display_path,
    load_json_object,
    project_path,
    require_keys,
)


def build(video_manifest_value: str, output_value: str | None = None) -> Path:
    video_manifest = load_json_object(video_manifest_value, "video manifest")
    require_keys(video_manifest, ["sources", "recordings"], "video manifest")
    source_value = video_manifest["sources"].get("gallery_manifest")
    recording = video_manifest["recordings"].get("gallery", {})
    if not source_value or "page" not in recording:
        raise VideoBuildError("video manifest does not declare gallery source/page")
    gallery = load_json_object(source_value, "gallery manifest")
    photos = gallery.get("photos")
    if not isinstance(photos, list) or not photos:
        raise VideoBuildError("gallery manifest has no photos")

    cells: list[str] = []
    missing: list[str] = []
    for photo in photos:
        if not isinstance(photo, dict) or "local_path" not in photo:
            raise VideoBuildError("gallery photo is missing local_path")
        image = project_path(str(photo["local_path"]))
        if not image.is_file() or image.stat().st_size == 0:
            missing.append(display_path(image))
            continue
        # Cached AuctionZip manifests contain HTML character references. Decode
        # that source representation once, then escape for this HTML boundary.
        caption = html.escape(
            html.unescape(str(photo.get("caption") or "")), quote=True
        )
        css_class = "cap" if caption else "nocap"
        cells.append(
            f'<figure><img loading="eager" src="{html.escape(image.as_uri(), quote=True)}" '
            f'alt="photo {int(photo.get("sequence", 0))}">'
            f'<figcaption class="{css_class}">{caption or "&nbsp;"}</figcaption></figure>'
        )
    if missing:
        preview = ", ".join(missing[:5])
        suffix = "..." if len(missing) > 5 else ""
        raise VideoBuildError(
            f"gallery page requires all {len(photos)} images; missing {len(missing)}: "
            f"{preview}{suffix}"
        )

    captioned = sum(bool(photo.get("has_caption")) for photo in photos)
    uncaptioned = len(photos) - captioned
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Blue Toad Auctions gallery</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#fff;font-family:Georgia,"Times New Roman",serif}}
.hdr{{padding:18px 26px;border-bottom:2px solid #c00}}
.hdr b{{color:#c00;font-size:22px}} .hdr span{{color:#333;font-size:15px;margin-left:14px}}
.grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;padding:20px 26px}}
figure{{margin:0}}img{{width:100%;height:190px;object-fit:cover;border:1px solid #6a86c8;display:block;background:#eee}}
figcaption{{text-align:center;font-weight:bold;font-size:14px;padding:6px 2px 0;line-height:1.25;min-height:34px}}
.nocap{{color:#bbb}}
</style></head><body data-photo-count="{len(photos)}">
<div class="hdr"><b>Click Photos to Enlarge</b><span>[ View Auction listing ]</span>
<span>Photos Per Page: All &nbsp;|&nbsp; {len(photos)} photos &nbsp;&middot;&nbsp; {uncaptioned} without captions</span></div>
<div class="grid">{"".join(cells)}</div></body></html>'''
    return atomic_write_text(output_value or recording["page"], page)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="media/video_manifest.json")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        output = build(args.manifest, args.output)
    except (OSError, ValueError, VideoBuildError) as exc:
        print(f"gallery page build failed: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {display_path(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
