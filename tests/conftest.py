"""Suite-wide isolation from state that live runs leave on this machine."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_voice_cache(tmp_path, monkeypatch):
    """Point the console's Gemma voice cache at a path only this test can see.

    A local uvicorn run (no PYTEST_CURRENT_TEST, real Gemma client) writes a
    live voice to the default /tmp cache, and a matching-key entry there wins
    over the credential-free template fallback by design — so without this,
    whether the console tests pass depends on whether a preview server ran
    since the last `rm` (observed 2026-08-29). Tests that exercise the cache
    deliberately set BTF_VOICE_CACHE themselves, which overrides this.
    """
    monkeypatch.setenv("BTF_VOICE_CACHE", str(tmp_path / "btf_gemma_voice.json"))


@pytest.fixture(autouse=True)
def _no_live_api_cross_check(monkeypatch):
    """read_api_total_sold is an I/O boundary (CDP fetch of the aggregates
    API); stub it for every test so the unit suite never touches the
    network — with the dedicated Chrome running, the unstubbed call made
    the comp suite take 91s and depend on live eBay. Tests that exercise
    the cross-check override this with their own monkeypatch."""
    from src.comps import live as _live
    monkeypatch.setattr(_live, "read_api_total_sold",
                        lambda query, condition_id=None: None,
                        raising=False)
