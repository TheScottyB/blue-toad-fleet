"""Every audit finding has one stable current verdict and matching checkbox."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TODO = ROOT / "docs/TODO.md"
EVIDENCE = ROOT / "docs/evidence/2026-08-22-todo-rebaseline.md"

EXPECTED = (
    *(f"A{i}" for i in range(1, 8)),
    "B0", "B1", "B2", "B3", "B4-video", "B4-SSIM", "B5", "B6", "B7", "B8",
    *(f"C{i}" for i in range(1, 10)),
    *(f"D{i}" for i in range(1, 4)),
    *(f"E{i}" for i in range(1, 4)),
    *(f"F{i}" for i in range(0, 22)),
)
FINAL = {"closed-with-evidence", "superseded"}
VALID = FINAL | {"open", "intentionally-deferred"}


def _body_rows(text: str) -> dict[str, bool]:
    rows = re.findall(
        r"^- \[([ x])\] \*\*([A-F]\d+(?:-[A-Za-z]+)?)\.", text, re.MULTILINE,
    )
    assert len(rows) == len({item_id for _, item_id in rows})
    return {item_id: checked == "x" for checked, item_id in rows}


def _status_rows(text: str) -> dict[str, str]:
    rows = re.findall(
        r"^\| ([A-F]\d+(?:-[A-Za-z]+)?) \| ([a-z-]+) \|", text, re.MULTILINE,
    )
    assert len(rows) == len({item_id for item_id, _ in rows})
    return dict(rows)


def test_todo_has_exactly_the_54_stable_ids_once():
    rows = _body_rows(TODO.read_text())
    assert tuple(rows) == EXPECTED


def test_every_finding_has_one_valid_verdict_and_matching_checkbox():
    text = TODO.read_text()
    body = _body_rows(text)
    statuses = _status_rows(text)
    assert tuple(statuses) == EXPECTED
    assert set(statuses.values()) <= VALID
    assert {item_id for item_id, checked in body.items() if checked} == {
        item_id for item_id, status in statuses.items() if status in FINAL
    }


def test_evidence_ledger_has_one_row_for_every_finding():
    statuses = _status_rows(EVIDENCE.read_text())
    assert tuple(statuses) == EXPECTED
    assert set(statuses.values()) <= VALID
