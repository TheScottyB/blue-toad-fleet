#!/usr/bin/env python3
"""Build the terminal-replay page from the declared captured command output."""

from __future__ import annotations

import argparse
import html
import json
import sys

from video_common import (
    VideoBuildError,
    atomic_write_text,
    display_path,
    load_json_object,
    project_path,
    require_file,
    require_keys,
)


def build(manifest_value: str, output_value: str | None) -> None:
    manifest = load_json_object(manifest_value, "video manifest")
    terminal = manifest.get("recordings", {}).get("terminal", {})
    require_keys(terminal, ["steps", "page"], "terminal recording")
    steps_path = require_file(terminal["steps"], "captured terminal steps")
    try:
        steps = json.loads(steps_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VideoBuildError(f"invalid captured terminal steps: {exc}") from exc
    if not isinstance(steps, list) or not steps:
        raise VideoBuildError("captured terminal steps must be a non-empty list")
    hold_ms = int(terminal.get("hold_ms", 2700))
    if hold_ms <= 0:
        raise VideoBuildError("terminal hold_ms must be positive")
    shot_hold_ms = int(terminal.get("shot_hold_ms", 8000))
    if shot_hold_ms <= 0:
        raise VideoBuildError("terminal shot_hold_ms must be positive")
    shot_blocks: list[str] = []
    for index, shot_value in enumerate(terminal.get("console_shots") or []):
        shot_path = require_file(shot_value, f"console shot {index + 1}")
        shot_blocks.append(
            f'<div class="shot"><img src="{shot_path.resolve().as_uri()}"></div>'
        )

    blocks: list[str] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise VideoBuildError(f"terminal step {index + 1} must be an object")
        require_keys(step, ["cmd", "out"], f"terminal step {index + 1}")
        # This text node is read with textContent; only the literal closing tag
        # needs neutralizing so source data cannot terminate the script element.
        command = str(step["cmd"]).replace("</script>", "<\\/script>")
        output = html.escape(str(step["out"]))
        blocks.append(
            f'<div class="step" data-i="{index}"><div class="cmd">'
            f'<span class="p">rg@richmond</span><span class="c">:~/blue-toad-fleet$</span> '
            f'<span class="t"></span><span class="cur">▋</span></div>'
            f'<pre class="out">{output}</pre>'
            f'<script type="text/plain" class="src">{command}</script></div>'
        )

    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>proof</title><style>
*{{box-sizing:border-box;margin:0}}body{{width:1600px;height:900px;background:#080b11;padding:52px 60px;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:19px;line-height:1.65;color:#cbd5e1;overflow:hidden}}
.step{{display:none;margin-bottom:20px}}.step.on{{display:block}}.p{{color:#34d399}}.c{{color:#64748b}}.t{{color:#f1f5f9}}.cmd{{white-space:pre-wrap}}.cur{{color:#22d3ee;animation:b 1s steps(2) infinite}}@keyframes b{{50%{{opacity:0}}}}.out{{color:#94a3b8;white-space:pre-wrap;margin-top:4px}}.out:empty{{display:none}}
.shot{{position:fixed;inset:0;display:none;align-items:center;justify-content:center;background:#080b11;z-index:5}}.shot.on{{display:flex}}.shot img{{max-width:100%;max-height:100%}}
</style></head><body>{''.join(shot_blocks)}{''.join(blocks)}<script>
const steps=[...document.querySelectorAll('.step')];const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{{await sleep(900);for(const shot of [...document.querySelectorAll('.shot')]){{shot.classList.add('on');await sleep({shot_hold_ms});shot.classList.remove('on')}}for(const [index,step] of steps.entries()){{step.classList.add('on');const source=step.querySelector('.src').textContent;const typed=step.querySelector('.t');const output=step.querySelector('.out');const saved=output.textContent;output.textContent='';for(const character of source){{typed.textContent+=character;await sleep(26)}}await sleep(420);step.querySelector('.cur').style.display='none';output.textContent=saved;await sleep({hold_ms});if(document.body.scrollHeight>900)steps[index-2]?.classList.remove('on')}}document.title='done'}})();
</script></body></html>'''
    destination = atomic_write_text(output_value or terminal["page"], page)
    print(f"wrote {display_path(destination)} ({len(steps)} steps)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="media/video_manifest.json")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        build(args.manifest, args.output)
    except (OSError, ValueError, VideoBuildError) as exc:
        print(f"terminal page build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
