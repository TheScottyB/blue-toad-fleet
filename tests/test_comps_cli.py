"""
The comps CLI — the same reads as the MCP tools, callable from any shell.

The CLI must be a THIN wrapper over the exact tool functions the MCP server
exposes (scripts/comps_mcp_server.ebay_absorption / ebay_comps), so its JSON
is identical to a tool call byte-for-byte and there is a single source of
truth for what a read returns. Guards (UnknownConditionId, NonAnnualWindow,
SuspectEmpty, ChallengePage) must exit nonzero with the message on stderr —
a wrong number must never leave as exit 0.

I/O is stubbed at the same boundary as the other suites (read_sold /
_read_active / read_api_total_sold via conftest).
"""

import json

import pytest

from src.comps import ActivePage, SoldPage, SoldRow, UnknownConditionId
from src.comps import live
from scripts import comps_cli


@pytest.fixture
def one_row_market(monkeypatch):
    sold = SoldPage(
        window="Aug 21, 2025 – Aug 21, 2026",
        rows=[SoldRow(title="Vintage Boston Champion Pencil Sharpener",
                      price=33.30, qty=6, date="Jul 15, 2026")],
        avg_price=24.11,
        avg_shipping=8.83,
        filters=[],
    )
    active = ActivePage(total_active=46, filters=[])
    monkeypatch.setattr(live, "read_sold",
                        lambda query, condition_id=None: sold)
    monkeypatch.setattr(live, "read_active",
                        lambda query, condition_id=None: active)

    async def fake_active(query, condition_id=None):
        return active

    monkeypatch.setattr(live, "_read_active", fake_active)
    monkeypatch.setattr(live, "select_comps", lambda ident, titles: None)
    return sold


class TestAbsorptionCommand:
    def test_prints_the_tool_dict_as_json(self, one_row_market, capsys):
        rc = comps_cli.main(["absorption", "boston champion"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["sold_units_365d"] == 6
        assert out["active_now"] == 46
        assert out["channel"] == "eBay only — not store or other channels"

    def test_condition_id_reaches_the_read(self, one_row_market, capsys):
        rc = comps_cli.main(["absorption", "q", "--condition-id", "3000"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["condition_scope"] == {"condition_id": 3000,
                                          "label": "Used"}

    def test_an_unknown_condition_exits_nonzero_with_the_reason(
            self, one_row_market, capsys):
        rc = comps_cli.main(["absorption", "q", "--condition-id", "42"])
        assert rc != 0
        err = capsys.readouterr().err
        assert "42" in err and "refused" in err


class TestCompsCommand:
    def test_runs_the_full_read(self, one_row_market, capsys):
        rc = comps_cli.main(["comps", "the item", "--query", "boston"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["identification"] == "the item"
        assert out["query"] == "boston"
        assert out["comp_selection"] == (
            "UNAVAILABLE — figures above are UNFILTERED")

    def test_query_defaults_to_the_identification(
            self, one_row_market, capsys):
        rc = comps_cli.main(["comps", "the item"])
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["query"] == "the item"


class TestHelpIsOperatorDocumentation:
    """--help is the operator's manual; it must state the contract.

    The tool's central promise — nonzero exit = the read was REFUSED,
    never "sold 0" — and its one prerequisite (the CDP Chrome on 9222)
    have to be visible from the shell, not only in a docstring nobody
    running the binary ever opens."""

    def test_top_level_help_states_the_exit_contract(self, capsys):
        with pytest.raises(SystemExit) as exc:
            comps_cli.main(["--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "REFUSED" in out
        assert 'never "sold 0"' in out
        assert "9222" in out

    def test_absorption_help_documents_the_arguments(self, capsys):
        with pytest.raises(SystemExit):
            comps_cli.main(["absorption", "--help"])
        out = capsys.readouterr().out
        assert "keywords" in out            # what `query` is
        assert "3000" in out                # a condition-id example
        assert "refused" in out             # unknown ids refuse, not ignore

    def test_comps_help_documents_the_arguments(self, capsys):
        with pytest.raises(SystemExit):
            comps_cli.main(["comps", "--help"])
        out = capsys.readouterr().out
        assert "identification" in out
        assert "screenshot" in out          # what --with-evidence saves
        assert "default" in out             # --query falls back to the id


class TestGuardsExitLoud:
    def test_a_live_guard_error_is_exit_nonzero_not_a_traceback(
            self, monkeypatch, capsys):
        def boom(query, condition_id=None):
            raise UnknownConditionId("synthetic guard failure")

        monkeypatch.setattr(live, "read_sold", boom)
        rc = comps_cli.main(["absorption", "q"])
        assert rc != 0
        assert "synthetic guard failure" in capsys.readouterr().err
