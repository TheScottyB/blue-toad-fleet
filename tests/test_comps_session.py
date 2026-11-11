"""
The research session's two 2026-11-11 behaviours, with no live Chrome:

  - tab reuse: a read attaches to the Seller Hub research tab that is already
    open and leaves it open, instead of opening and closing a tab (which was
    a whole window) per query;
  - in-tab retry: a page that comes back suspiciously empty is asked again
    before the read is refused — and is still refused if it stays empty.
"""

import asyncio
import json
import urllib.parse
from pathlib import Path

import pytest

from src.comps import SuspectEmpty, split_modules
from src.comps import live
from src.comps.live import ResearchSession as RealSession  # before conftest swaps it

FIX = Path(__file__).parent / "fixtures" / "comps"
SOLD = (FIX / "sold_heineken_2026-09-25.ndjson").read_text()
ACTIVE = (FIX / "active_heineken_2026-09-25.ndjson").read_text()
SOLD_ZERO = (FIX / "sold_zero_2026-09-25.ndjson").read_text()
# zero rows WITHOUT eBay's zero-results message: the suspect-empty shape
SILENT_EMPTY = "\n".join(json.dumps(m) for m in split_modules(SOLD_ZERO)
                         if m["_type"] != "PageErrorModule")

RESEARCH = {"type": "page", "id": "AAA",
            "url": "https://www.ebay.com/sh/research?marketplace=EBAY-US&tabName=SOLD",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/AAA"}


@pytest.fixture(autouse=True)
def _pinned_window(monkeypatch):
    monkeypatch.setattr(live, "year_window", lambda now=None: (
        1758800000000, 1790336000000, "Sep 25, 2025 – Sep 25, 2026"))


# --- tab reuse -------------------------------------------------------------------

class TestPickResearchTab:
    def test_picks_the_open_research_page(self):
        other = {"type": "page", "id": "B", "url": "about:blank"}
        assert live.pick_research_tab([other, RESEARCH]) is RESEARCH

    def test_ignores_signin_workers_and_idless_targets(self):
        targets = [
            {"type": "page", "id": "S", "url": "https://signin.ebay.com/ws/eBayISAPI.dll"},
            {"type": "service_worker", "id": "W", "url": RESEARCH["url"]},
            {"type": "page", "url": RESEARCH["url"]},
            {"type": "page", "id": "X", "url": "https://www.ebay.com/sh/ovw"},
        ]
        assert live.pick_research_tab(targets) is None

    def test_a_non_list_answer_is_no_tab(self):
        assert live.pick_research_tab(None) is None
        assert live.pick_research_tab({"error": "x"}) is None

    def test_ws_url_is_rebuilt_when_chrome_omits_it(self):
        assert live._ws_url(RESEARCH) == RESEARCH["webSocketDebuggerUrl"]
        assert live._ws_url({"id": "ZZ"}) == "ws://127.0.0.1:9222/devtools/page/ZZ"


class _Sock:
    closed = 0

    async def close(self):
        _Sock.closed += 1


@pytest.fixture
def cdp(monkeypatch):
    """Record every CDP HTTP call and websocket attach; no browser."""
    calls = {"json": [], "attached": [], "closed_tabs": []}
    state = {"targets": [], "ready": lambda tab: None}

    def fake_cdp_json(path, method="GET", timeout=10):
        calls["json"].append((method, path.split("?")[0]))
        if path == "/json":
            return state["targets"]
        if path.startswith("/json/new"):
            return {"type": "page", "id": "NEW", "url": live._BOOT_URL,
                    "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/NEW"}
        raise AssertionError(path)

    async def fake_connect(url, **kw):
        calls["attached"].append(url)
        return _Sock()

    async def fake_ready(self, timeout=60.0):
        state["ready"](self._tab)

    class _Resp:
        def read(self):
            return b"Target is closing"

    def fake_urlopen(url, timeout=5):
        calls["closed_tabs"].append(str(url).rsplit("/", 1)[-1])
        return _Resp()

    _Sock.closed = 0
    monkeypatch.setattr(live, "_cdp_json", fake_cdp_json)
    monkeypatch.setattr(live.websockets, "connect", fake_connect)
    monkeypatch.setattr(RealSession, "_wait_ready", fake_ready)
    monkeypatch.setattr(live.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(live, "_KEEP_TAB", True)
    return calls, state


def _enter_exit():
    async def go():
        async with RealSession() as sess:
            return sess.reused, sess._tab["id"]
    return asyncio.run(go())


class TestSessionReusesTheTab:
    def test_attaches_to_the_open_tab_and_leaves_it_open(self, cdp):
        calls, state = cdp
        state["targets"] = [RESEARCH]
        assert _enter_exit() == (True, "AAA")
        assert ("PUT", "/json/new") not in calls["json"]     # no new tab/window
        assert calls["closed_tabs"] == []                     # and none closed
        assert _Sock.closed == 1                              # only our socket

    def test_opens_one_when_none_is_open_and_still_leaves_it(self, cdp):
        calls, state = cdp
        assert _enter_exit() == (False, "NEW")
        assert calls["json"] == [("GET", "/json"), ("PUT", "/json/new")]
        assert calls["closed_tabs"] == []

    def test_a_stuck_open_tab_falls_back_to_a_fresh_one(self, cdp):
        calls, state = cdp
        state["targets"] = [RESEARCH]

        def ready(tab):
            if tab["id"] == "AAA":
                raise TimeoutError("not ready")
        state["ready"] = ready
        assert _enter_exit() == (False, "NEW")
        assert calls["attached"][0].endswith("/AAA")
        assert calls["attached"][1].endswith("/NEW")

    def test_keep_tab_off_closes_it_like_before(self, cdp, monkeypatch):
        calls, state = cdp
        monkeypatch.setattr(live, "_KEEP_TAB", False)
        assert _enter_exit() == (False, "NEW")
        assert calls["closed_tabs"] == ["NEW"]


# --- in-tab retry ----------------------------------------------------------------

class FlakySession:
    """Answers each (tab, offset) from a queue; the last body repeats."""
    script: dict = {}
    requests: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def get(self, path):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        key = (q["tabName"][0], int(q["offset"][0]))
        FlakySession.requests.append(key)
        bodies = FlakySession.script[key]
        return bodies.pop(0) if len(bodies) > 1 else bodies[0]


@pytest.fixture
def flaky(monkeypatch):
    FlakySession.script = {("ACTIVE", 0): [ACTIVE]}
    FlakySession.requests = []
    monkeypatch.setattr(live, "ResearchSession", FlakySession)
    monkeypatch.setattr(live, "_EMPTY_RETRY_PAUSES", (0, 0))
    return FlakySession


class TestSuspectEmptyIsAskedAgain:
    def test_an_empty_first_answer_then_rows_is_a_read_not_a_refusal(
            self, flaky, capsys):
        flaky.script[("SOLD", 0)] = [SILENT_EMPTY, SOLD]
        m = live.read_market("q")
        assert m.sold.sold_units == 5
        assert flaky.requests.count(("SOLD", 0)) == 2
        assert "asking again" in capsys.readouterr().err

    def test_still_empty_after_every_retry_is_still_refused(self, flaky):
        flaky.script[("SOLD", 0)] = [SILENT_EMPTY]
        with pytest.raises(SuspectEmpty):
            live.read_market("q")
        assert flaky.requests.count(("SOLD", 0)) == 3      # 1 ask + 2 retries

    def test_a_genuine_zero_is_not_retried(self, flaky):
        flaky.script[("SOLD", 0)] = [SOLD_ZERO]
        m = live.read_market("q")
        assert m.sold.genuine_zero
        assert flaky.requests.count(("SOLD", 0)) == 1

    def test_the_active_read_is_retried_too(self, flaky):
        flaky.script[("SOLD", 0)] = [SOLD]
        flaky.script[("ACTIVE", 0)] = ["", ACTIVE]          # empty body first
        m = live.read_market("q")
        assert m.active.total_active == 19
        assert flaky.requests.count(("ACTIVE", 0)) == 2
