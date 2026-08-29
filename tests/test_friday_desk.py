"""Friday desk: walk → grouping/scope questions → envelope → clerk draft."""

import re

import pytest
from starlette.testclient import TestClient

from src.server import app, get_aug22_state


@pytest.fixture
def client():
    return TestClient(app)


def test_friday_desk_stages_run_in_order(client):
    html = client.get("/").text
    walk = html.find('data-stage="walk"')
    questions = html.find('data-stage="questions"')
    envelope = html.find('data-stage="envelope"')
    clerk = html.find('data-stage="clerk"')
    assert 0 <= walk < questions < envelope < clerk


def test_grouping_and_scope_questions_sort_ahead_of_appetite(client):
    html = client.get("/").text
    kinds = re.findall(r'<div class="meta">(\w+) &middot;', html)
    if "lot_grouping" in kinds and "appetite" in kinds:
        assert kinds.index("lot_grouping") < kinds.index("appetite")
    if "scope" in kinds and "appetite" in kinds:
        assert kinds.index("scope") < kinds.index("appetite")


def test_clerk_draft_is_on_the_desk(client):
    html = client.get("/").text
    assert 'data-stage="clerk"' in html
    assert "TOTAL COMMITTED PROXY BIDS" in html or "absentee" in html.lower()


def test_one_operator_token_on_the_friday_desk(client):
    html = client.get("/").text
    assert html.count('id="cycle-token"') == 1
    assert 'href="/walk"' in html


def test_sent_sheet_stays_frozen_on_the_friday_desk():
    _, _, _, _, sent, _, _ = get_aug22_state(sheet="sent")
    assert sent.allocated == 9
    assert sent.committed_max == 275.0
    assert sent.committed_all_in == 316.25
