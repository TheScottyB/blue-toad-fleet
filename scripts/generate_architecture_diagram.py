#!/usr/bin/env python3
"""Render the architecture diagram from the verified submission facts."""

from __future__ import annotations

import argparse
import sys

import matplotlib.patches as patches
import matplotlib.pyplot as plt

from video_common import (
    VideoBuildError,
    atomic_media_output,
    display_path,
    load_json_object,
    load_verified_facts,
    project_path,
    require_keys,
)


def generate(manifest_value: str, output_value: str) -> None:
    manifest = load_json_object(manifest_value, "video manifest")
    facts = load_verified_facts(manifest)
    cycle, money, tests, runtime = (
        facts["cycle"],
        facts["money"],
        facts["tests"],
        facts["runtime"],
    )
    require_keys(
        cycle,
        ["photos", "groups", "appraised", "approved_bids", "duplicate_or_non_lot_photos"],
        "cycle facts",
    )
    require_keys(money, ["budget_cap", "committed_max"], "money facts")
    require_keys(tests, ["passed", "collected", "skipped"], "test facts")
    require_keys(runtime, ["python", "models"], "runtime facts")
    models = runtime["models"]

    figure, axis = plt.subplots(figsize=(16, 9), dpi=300)
    figure.patch.set_facecolor("#0f1115")
    axis.set_facecolor("#0f1115")
    axis.text(
        8.0,
        8.4,
        "BLUE TOAD FLEET — SYSTEM ARCHITECTURE",
        fontsize=20,
        fontweight="bold",
        color="#e8eaf0",
        ha="center",
        va="center",
    )
    axis.text(
        8.0,
        8.0,
        "Manifest-backed intake, Vertex AI appraisal, deterministic allocation, and a Cloud Run gate",
        fontsize=11,
        color="#a78bfa",
        ha="center",
        va="center",
    )

    def box(x, y, width, height, title, subtitle, border):
        axis.add_patch(
            patches.FancyBboxPatch(
                (x, y),
                width,
                height,
                boxstyle="round,pad=0.08,rounding_size=0.15",
                linewidth=1.8,
                edgecolor=border,
                facecolor="#171a21",
            )
        )
        axis.text(
            x + width / 2,
            y + height - 0.28,
            title,
            fontsize=11,
            fontweight="bold",
            color="#e8eaf0",
            ha="center",
            va="center",
        )
        axis.text(
            x + width / 2,
            y + height / 2 - 0.12,
            subtitle,
            fontsize=8.5,
            color="#a7b0c0",
            ha="center",
            va="center",
            multialignment="center",
        )

    def arrow(x1, y1, x2, y2, color="#78829a", label=""):
        axis.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops={
                "facecolor": color,
                "edgecolor": color,
                "width": 1.5,
                "headwidth": 7,
                "headlength": 7,
                "shrink": 0.05,
            },
        )
        if label:
            axis.text(
                (x1 + x2) / 2,
                (y1 + y2) / 2 + 0.15,
                label,
                fontsize=8,
                color="#38bdf8",
                ha="center",
                va="center",
                fontweight="bold",
            )

    box(
        0.8,
        4.5,
        3.2,
        2.6,
        "1. SANCTIONED INTAKE & GROUPING",
        f"• {cycle['photos']} manifest photos\n"
        f"• Sequential boundary signals\n"
        f"• Reviewed similarity edges\n"
        f"• {cycle['duplicate_or_non_lot_photos']} duplicate/non-lot views suppressed",
        "#38bdf8",
    )
    box(
        4.6,
        5.2,
        3.4,
        2.2,
        "2A. TRIAGE FAN-OUT",
        f"• Model: {models['triage']}\n"
        "• Structured worth-appraising decision\n"
        "• Caption authority protects boundaries\n"
        f"• {cycle['groups']} groups continue downstream",
        "#34d399",
    )
    box(
        4.6,
        2.4,
        3.4,
        2.4,
        "2B. DEEP APPRAISAL",
        f"• Model: {models['appraisal']}\n"
        "• Structured OpenAPI 3.0 schemas\n"
        "• Container boundary decomposition\n"
        f"• {cycle['appraised']} selected appraisals",
        "#a78bfa",
    )
    box(
        8.6,
        3.8,
        3.2,
        2.6,
        "3. DETERMINISTIC BIDMATH",
        "• Buy-in and condition rules\n"
        "• Choice-lot quantity mechanics\n"
        f"• Allocation within ${money['budget_cap']:.0f} cap\n"
        "• Uncited prices are refused\n"
        f"• {tests['passed']}/{tests['collected']} tests pass; {tests['skipped']} skip",
        "#fbbf24",
    )
    box(
        12.4,
        4.5,
        3.0,
        2.6,
        "4. GATE CONSOLE (CLOUD RUN)",
        "• Serverless operator review\n"
        "• Visible evidence and provenance\n"
        "• Question queue and keyed memory\n"
        "• Human approval remains explicit",
        "#f87171",
    )
    box(
        12.4,
        1.2,
        3.0,
        2.4,
        "5. SOURCING DRAFT",
        f"• {cycle['approved_bids']} allocated bids\n"
        f"• ${money['committed_max']:.2f} committed max\n"
        "• $5 bidding increments\n"
        "• Absentee fee included\n"
        "• Email and workbook artifacts",
        "#34d399",
    )

    arrow(4.0, 5.8, 4.6, 6.0, "#38bdf8", f"{cycle['photos']} photos")
    arrow(4.0, 5.0, 4.6, 3.8, "#a78bfa", "Grouped evidence")
    arrow(8.0, 6.0, 8.6, 5.4, "#34d399", "Triage results")
    arrow(8.0, 3.6, 8.6, 4.5, "#a78bfa", "Appraisals")
    arrow(11.8, 5.1, 12.4, 5.6, "#fbbf24", "Ranked decisions")
    arrow(13.9, 4.5, 13.9, 3.6, "#34d399", "Approved draft")
    axis.text(
        8.0,
        0.5,
        f"Google Cloud: Vertex AI · Cloud Run · Artifact Registry · Cloud Build · Python {runtime['python']}",
        fontsize=9.5,
        color="#78829a",
        ha="center",
        va="center",
    )
    axis.set_xlim(0, 16)
    axis.set_ylim(0, 9)
    axis.axis("off")
    plt.tight_layout()
    output = project_path(output_value)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with atomic_media_output(output) as temporary:
            plt.savefig(temporary, facecolor=figure.get_facecolor(), edgecolor="none")
    finally:
        plt.close(figure)
    print(f"wrote {display_path(output)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="media/video_manifest.json")
    parser.add_argument("--output", default="docs/architecture_diagram.png")
    args = parser.parse_args(argv)
    try:
        generate(args.manifest, args.output)
    except (OSError, ValueError, VideoBuildError) as exc:
        print(f"architecture diagram build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
