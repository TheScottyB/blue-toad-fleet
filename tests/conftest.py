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
def _no_live_research_session(monkeypatch):
    """ResearchSession is the comps layer's only I/O boundary (a CDP tab on
    Seller Hub). Replace it for every test with one that refuses, so the
    unit suite can never touch live eBay — with the dedicated Chrome
    running, an unstubbed read made the comp suite slow and dependent on
    the live market (observed 2026-08-29). Tests that exercise the walk
    install their own fake."""
    from src.comps import live as _live

    class _NoNetwork:
        async def __aenter__(self):
            raise RuntimeError("unit tests must not open a live Seller Hub "
                               "session — stub ResearchSession or read_market")

        async def __aexit__(self, *exc):
            return None

    monkeypatch.setattr(_live, "ResearchSession", _NoNetwork)
