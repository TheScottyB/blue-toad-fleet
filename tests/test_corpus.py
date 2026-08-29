"""
Full-corpus coverage.

The pipeline appraised twelve lots the owner had already picked, which is the
one workload that does not need a pipeline — he can shortlist twelve himself.
The claim worth making is that it reads the whole sale: 462 photographs, every
lot, and a question queue that stays small anyway.

Stage 1 decides what deserves a slow look. These tests pin the selection rule,
because "which lots did we skip" is the question a bad sourcing sheet cannot
answer afterwards.
"""

import pytest

from scripts.run_vertex_pipeline import select_appraisal_candidates


def triaged(photo_id, worth=True, fit=0.5, summary="thing"):
    return {"photo_id": photo_id, "worth_appraising": worth,
            "fit_score": fit, "summary": summary, "is_lot": True,
            "same_lot_as_previous": False}


def photo(seq, pid, caption="", path="data/x.jpg"):
    return {"sequence": seq, "photo_id": pid, "caption": caption,
            "local_path": path, "has_caption": bool(caption)}


class TestSelection:
    def test_a_photo_triage_liked_becomes_a_candidate(self):
        got = select_appraisal_candidates(
            [triaged("p1")], [photo(1, "p1", "crock")], always_include=set())
        assert [c["lot_id"] for c in got] == ["BT-001"]

    def test_a_photo_triage_rejected_is_still_appraised(self):
        got = select_appraisal_candidates(
            [triaged("p1", worth=False)], [photo(1, "p1")], always_include=set())
        assert [c["lot_id"] for c in got] == ["BT-001"]

    def test_an_owner_selected_lot_is_appraised_even_if_triage_rejected_it(self):
        """
        He overrules the fit score knowingly — the jewellery he buys for the
        storefront triages at 0.1. His picks must never be silently dropped by
        a cheaper model upstream.
        """
        got = select_appraisal_candidates(
            [triaged("p1", worth=False, fit=0.1)], [photo(1, "p1")],
            always_include={"BT-001"})
        assert [c["lot_id"] for c in got] == ["BT-001"]

    def test_candidates_carry_what_the_appraiser_needs(self):
        got = select_appraisal_candidates(
            [triaged("p1", summary="Red Wing crock")],
            [photo(1, "p1", "crock", path="data/img/1.jpg")], always_include=set())
        c = got[0]
        assert c["local_path"] == "data/img/1.jpg"
        assert c["caption"]

    def test_a_photo_with_no_triage_verdict_is_still_appraised(self):
        """Absent evidence is not evidence of absence — an untriaged photo is unknown, not junk."""
        got = select_appraisal_candidates([], [photo(1, "p1")], always_include=set())
        assert [c["lot_id"] for c in got] == ["BT-001"]

    def test_selection_is_ordered_by_sequence(self):
        tri = [triaged("p3"), triaged("p1"), triaged("p2")]
        ph = [photo(3, "p3"), photo(1, "p1"), photo(2, "p2")]
        got = select_appraisal_candidates(tri, ph, always_include=set())
        assert [c["lot_id"] for c in got] == ["BT-001", "BT-002", "BT-003"]

    def test_the_uncaptioned_still_get_a_caption_from_triage(self):
        got = select_appraisal_candidates(
            [triaged("p1", summary="brass railroad lantern")],
            [photo(1, "p1", caption="")], always_include=set())
        assert "lantern" in got[0]["caption"]


class TestHowFarTriageIsTrusted:
    """
    Stage 1 is a cheap model given one photograph and a caption. It is good at
    "is this worth a slow look" and unreliable about lot boundaries.

    On the first live corpus run it marked BT-181 — captioned "estate costume
    jewelry" by the auction house — as another angle of the necklaces two photos
    earlier. group_into_lots merged it away, it stopped being a lot, and a bid
    the owner had capped at $25 silently left the sheet. Nothing errored.

    A caption the house wrote outranks a flag the model guessed.
    """

    def test_a_captioned_photo_is_never_merged_into_its_neighbour(self):
        from scripts.run_vertex_pipeline import trusted_lot_flags
        is_lot, same = trusted_lot_flags(
            {"is_lot": True, "same_lot_as_previous": True},
            caption="estate costume jewelry", previous_captioned=True, index=181)
        assert same is False

    def test_an_uncaptioned_photo_still_follows_triage(self):
        from scripts.run_vertex_pipeline import trusted_lot_flags
        _, same = trusted_lot_flags(
            {"is_lot": True, "same_lot_as_previous": True},
            caption="", previous_captioned=True, index=182)
        assert same is True

    def test_triage_can_still_split_a_captioned_photo_off(self):
        """Overriding a merge is not overriding everything — a False stays False."""
        from scripts.run_vertex_pipeline import trusted_lot_flags
        _, same = trusted_lot_flags(
            {"is_lot": True, "same_lot_as_previous": False},
            caption="brass lantern", previous_captioned=True, index=5)
        assert same is False

    def test_with_no_triage_verdict_the_caption_heuristic_stands(self):
        from scripts.run_vertex_pipeline import trusted_lot_flags
        is_lot, same = trusted_lot_flags(
            None, caption="", previous_captioned=True, index=7)
        assert (is_lot, same) == (False, True)

    def test_the_first_photo_is_never_an_angle_of_something_earlier(self):
        from scripts.run_vertex_pipeline import trusted_lot_flags
        _, same = trusted_lot_flags(None, caption="", previous_captioned=False, index=0)
        assert same is False
