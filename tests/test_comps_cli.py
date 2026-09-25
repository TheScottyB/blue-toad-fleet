"""
The comps CLI — the same reads as the MCP tools, callable from any shell.

The CLI must be a THIN wrapper over the exact tool functions the MCP server
exposes, so its JSON matches a tool call and there is one source of truth.
Refusals exit 1 with the reason on stderr — a wrong number never leaves as
exit 0. I/O is stubbed at read_market.
"""

import json
from pathlib import Path

import pytest

from src.comps import (UnknownConditionId, parse_active_response,
                       parse_sold_response)
from src.comps import live
from scripts import comps_cli

FIX = Path(__file__).parent / "fixtures" / "comps"
WINDOW = "Sep 25, 2025 – Sep 25, 2026"


@pytest.fixture
def market(monkeypatch):
    def fake_read_market(query, condition_id=None):
        from src.comps import require_known_condition
        require_known_condition(condition_id)
        return live.Market(
            sold=parse_sold_response(
                (FIX / "sold_heineken_2026-09-25.ndjson").read_text(),
                window=WINDOW),
            active=parse_active_response(
                (FIX / "active_heineken_2026-09-25.ndjson").read_text()),
            window_ms=(0, 1), raw={})
    monkeypatch.setattr(live, "read_market", fake_read_market)
    monkeypatch.setattr(live, "select_comps", lambda ident, titles: [
        {"index": i, "verdict": "comp", "reason": "same"}
        for i in range(len(titles))])


class TestAbsorptionCommand:
    def test_prints_the_tool_dict_as_json(self, market, capsys):
        assert comps_cli.main(["absorption", "heineken special dark mirror"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["sold_units_365d"] == 5
        assert out["active_now"] == 19
        assert out["channel"] == "eBay only — not store or other channels"

    def test_condition_id_reaches_the_read(self, market, capsys):
        assert comps_cli.main(["absorption", "q", "--condition-id", "3000"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["condition_scope"]["label"] == "Used"

    def test_unknown_condition_is_a_refusal_not_a_number(self, market, capsys):
        assert comps_cli.main(["absorption", "q", "--condition-id", "42"]) == 1
        err = capsys.readouterr().err
        assert "UnknownConditionId" in err and "read refused" in err


class TestCompsCommand:
    def test_prints_screened_comps_with_prices(self, market, capsys):
        assert comps_cli.main(["comps", "the item", "--query", "heineken"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["query"] == "heineken"
        assert out["comp_selection"]["comp_price_band"] == [15.0, 45.0]

    def test_query_defaults_to_identification(self, market, capsys):
        assert comps_cli.main(["comps", "the item"]) == 0
        assert json.loads(capsys.readouterr().out)["query"] == "the item"

    def test_rows_out_writes_every_row_and_keeps_stdout_compact(
            self, market, capsys, tmp_path):
        dest = tmp_path / "rows" / "sold.json"
        assert comps_cli.main(["comps", "the item", "--rows-out",
                               str(dest)]) == 0
        out = json.loads(capsys.readouterr().out)
        assert "sold_rows" not in out and out["rows_out"] == str(dest)
        saved = json.loads(dest.read_text())
        assert len(saved["rows"]) == 5 and saved["window"] == WINDOW
        assert all(r["price"] is not None and r["verdict"] == "comp"
                   for r in saved["rows"])


class TestRefusals:
    def test_any_read_failure_exits_1_with_the_reason(self, monkeypatch,
                                                      capsys):
        def boom(query, condition_id=None):
            raise live.CDPUnavailable("the dedicated Chrome is not answering")
        monkeypatch.setattr(live, "read_market", boom)
        assert comps_cli.main(["absorption", "q"]) == 1
        err = capsys.readouterr().err
        assert "CDPUnavailable" in err and "read refused" in err

    def test_the_timeout_is_a_refusal(self, monkeypatch, capsys):
        def hang(query, condition_id=None):
            import time
            time.sleep(5)
        monkeypatch.setattr(live, "read_market", hang)
        assert comps_cli.main(["absorption", "q", "--timeout", "1"]) == 1
        assert "TimeoutError" in capsys.readouterr().err


class TestHelp:
    @pytest.mark.parametrize("argv", [["--help"], ["absorption", "--help"],
                                      ["comps", "--help"]])
    def test_help_exits_zero(self, argv, capsys):
        with pytest.raises(SystemExit) as e:
            comps_cli.main(argv)
        assert e.value.code == 0

    def test_help_names_the_refusals_and_the_timeout(self, capsys):
        with pytest.raises(SystemExit):
            comps_cli.main(["--help"])
        text = capsys.readouterr().out
        assert "never \"sold 0\"" in text and "--timeout" in text
