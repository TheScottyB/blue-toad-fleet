#!/usr/bin/env python3
"""
scripts/cdp_capture.py — screenshot a page to disk, autonomously.

Exists because the comp reports need proof an agent cannot fabricate. Text is
the medium agents make things up in; a screenshot is not. Every other route was
tried and failed:

  - the in-app browser tool reports a successful `save_to_disk` and writes no
    file that exists anywhere on the machine
  - Playwright reaches neither eBay Seller Hub (redirects to a CAPTCHA) nor
    eBay's public sold search ("Pardon Our Interruption") — it is fingerprinted
    as automation before it renders anything
  - OS `screencapture` cannot target the automated browser window, and the one
    attempt captured an unrelated window from another session

What works is a real Chrome, launched once with remote debugging on its own
profile, driven over the DevTools Protocol. Real Chrome is not bot-blocked, and
`Page.captureScreenshot` returns bytes this script writes itself.

Start the browser once:

    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
      --remote-debugging-port=9222 --user-data-dir=$HOME/.btf-chrome-profile \\
      --no-first-run --no-default-browser-check about:blank &

Then:

    python scripts/cdp_capture.py <url> <out.png> [--full] [--wait 3]

The profile persists, so any site needing a login needs it once, by hand, in
that window — never per run, and never per lot.

eBay specifically: the homepage loads fine cookieless, but `LH_Sold=1` searches
and all of Seller Hub redirect to signin. That is eBay gating sold data behind
auth, not a limitation of this script. Sign in once in the dedicated window and
every capture after that is unattended.

The exit code is the contract. 0 means the screenshot is of the page you asked
for; 2 means it landed on a signin or challenge page and the image is NOT comp
data. Callers must check it — a report carrying a picture of a login screen
under the heading "proof" is worse than a report with no picture at all.
"""

import argparse
import asyncio
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import websockets

CDP = "http://127.0.0.1:9222"


def open_tab(url: str) -> dict:
    """Create a tab already pointed at the URL, and return its target.

    Navigating an ALREADY-ATTACHED target tears the WebSocket down mid-command
    — Chrome can swap the renderer, which invalidates the session and surfaces
    as a bare ConnectionResetError. Creating the tab pre-navigated sidesteps it
    entirely: attach once, to something that is already where it needs to be.
    """
    req = urllib.request.Request(
        f"{CDP}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.URLError as e:
        raise SystemExit(
            f"could not open a tab on the CDP endpoint ({e}) — is the dedicated "
            f"Chrome running? see this module's docstring for the launch command")


def close_tab(tid: str) -> None:
    try:
        urllib.request.urlopen(f"{CDP}/json/close/{tid}", timeout=5).read()
    except Exception:
        pass


async def capture(url: str, out: Path, full: bool, wait: float,
                  width: int = 1920, height: int = 1400) -> dict:
    tab = open_tab(url)
    await asyncio.sleep(wait)
    async with websockets.connect(tab["webSocketDebuggerUrl"],
                                  max_size=64 * 1024 * 1024) as ws:
        n = 0

        async def send(method, params=None):
            nonlocal n
            n += 1
            await ws.send(json.dumps({"id": n, "method": method,
                                      "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == n:
                    if "error" in msg:
                        raise SystemExit(f"{method}: {msg['error']}")
                    return msg.get("result", {})

        await send("Page.enable")
        # The default window is narrower than the aggregate strip, so the
        # right-hand figures - Sell-through and Total sellers - fall off the
        # edge. A screenshot missing the numbers it exists to evidence is not
        # evidence, so force a viewport wide enough to hold the whole row.
        await send("Emulation.setDeviceMetricsOverride",
                   {"width": width, "height": height,
                    "deviceScaleFactor": 2, "mobile": False})
        await asyncio.sleep(1.5)

        # Read back what actually loaded. A redirect to a signin or challenge
        # page still screenshots successfully, and a report carrying a picture
        # of a CAPTCHA while claiming to show comps is worse than no picture.
        info = await send("Runtime.evaluate", {
            "expression": "JSON.stringify({u:location.href,t:document.title})",
            "returnByValue": True})
        landed = json.loads(info["result"]["value"])

        shot = await send("Page.captureScreenshot",
                          {"format": "png", "captureBeyondViewport": bool(full)})
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(shot["data"]))
        result = {"bytes": out.stat().st_size, **landed}
    close_tab(tab["id"])
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("--full", action="store_true", help="whole scrollable page")
    ap.add_argument("--wait", type=float, default=3.0)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1400)
    a = ap.parse_args()

    r = asyncio.run(capture(a.url, Path(a.out), a.full, a.wait,
                            a.width, a.height))
    print(f"  wrote {a.out}  {r['bytes']:,} bytes")
    print(f"  landed on: {r['t']}")
    print(f"  url:       {r['u'][:110]}")
    if any(w in r["t"].lower() for w in ("captcha", "security measure",
                                         "pardon our interruption", "sign in")):
        print("  !! CHALLENGE OR SIGNIN PAGE — this image is not comp data")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
