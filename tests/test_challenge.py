from types import SimpleNamespace

from src.gate.challenge import ChallengeEvidence, select_challenge


def _evidence(**changes):
    values = {
        "revision": "r1",
        "citations": ("https://example.test/source",),
        "source_sha256": ("a" * 64,),
        "cycle_id": "cycle-1",
        "manifest_sha256": "b" * 64,
        "comp_low": 100.0,
        "comp_high": 150.0,
    }
    values.update(changes)
    return ChallengeEvidence(**values)


def _decision(lot_id="BT-001", category="cards", allocated=True):
    return SimpleNamespace(
        lot_id=lot_id, category=category, allocated=allocated, max_bid=35.0,
    )


def _rule(category="cards", answer="SKIP — overstocked"):
    return SimpleNamespace(kind="appetite", category=category, answer=answer)


def test_selects_exact_current_rule_lot_and_revision():
    challenge = select_challenge(
        [_decision()], {"BT-001": "Topps cards"}, [_rule()],
        {"BT-001": _evidence()}, cycle_id="cycle-1", manifest_sha256="b" * 64,
    )
    assert challenge is not None
    assert challenge.lot_id == "BT-001"
    assert challenge.evidence.revision == "r1"


def test_missing_or_stale_evidence_hides_challenge():
    common = ([_decision()], {"BT-001": "Topps cards"}, [_rule()])
    assert select_challenge(
        *common, {}, cycle_id="cycle-1", manifest_sha256="b" * 64,
    ) is None
    assert select_challenge(
        *common, {"BT-001": _evidence(cycle_id="old")},
        cycle_id="cycle-1", manifest_sha256="b" * 64,
    ) is None


def test_unmatched_rule_or_unallocated_lot_hides_challenge():
    evidence = {"BT-001": _evidence()}
    assert select_challenge(
        [_decision(category="tools")], {}, [_rule()], evidence,
        cycle_id="cycle-1", manifest_sha256="b" * 64,
    ) is None
    assert select_challenge(
        [_decision(allocated=False)], {}, [_rule()], evidence,
        cycle_id="cycle-1", manifest_sha256="b" * 64,
    ) is None
