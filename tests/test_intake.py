import pytest
from src.intake import GalleryDrop, parse_drop, plan_fanout
from src.intake.manifest import clean_caption, lot_number_from


def entry(name, caption="", uri=None):
    return {"name": name, "caption": caption, "uri": uri or f"gs://b/{name}"}


class TestCleanCaption:
    def test_strips_the_auctionzip_preview_wrapper(self):
        assert clean_caption("Preview image for Hamm's sign") == "Hamm's sign"

    def test_is_case_insensitive(self):
        assert clean_caption("PREVIEW IMAGE FOR crock") == "crock"

    def test_leaves_normal_captions_alone(self):
        assert clean_caption("Red Wing 5 gallon crock") == "Red Wing 5 gallon crock"

    def test_handles_empty_and_none(self):
        assert clean_caption("") == "" and clean_caption(None) == ""


class TestLotNumber:
    @pytest.mark.parametrize("cap,want", [
        ("Lot 47 - Hamm's sign", "47"),
        ("lot #128 crock", "128"),
        ("#9 railroad lantern", "9"),
        ("Hamm's sign, 1960s", None),
        ("", None),
    ])
    def test_extraction(self, cap, want):
        assert lot_number_from(cap) == want


class TestParseDrop:
    def test_keeps_images_and_records_what_it_skipped(self):
        d = parse_drop("c1", "L1", [
            entry("fp001.jpg", "crock"), entry("notes.txt"), entry("fp002.png", "sign"),
        ])
        assert len(d.photos) == 2
        assert d.skipped == ["notes.txt"]

    def test_orders_by_filename_not_input_order(self):
        d = parse_drop("c1", "L1", [entry("fp003.jpg"), entry("fp001.jpg"), entry("fp002.jpg")])
        assert [p.photo_id for p in d.photos] == ["fp001", "fp002", "fp003"]

    def test_sequence_is_dense_and_zero_based(self):
        d = parse_drop("c1", "L1", [entry("a.jpg"), entry("skip.pdf"), entry("b.jpg")])
        assert [p.sequence for p in d.photos] == [0, 1]

    def test_counts_captioned_photos(self):
        d = parse_drop("c1", "L1", [entry("a.jpg", "crock"), entry("b.jpg", "")])
        assert d.captioned == 1 and len(d.photos) == 2

    def test_empty_drop_is_safe(self):
        d = parse_drop("c1", "L1", [])
        assert d.photos == [] and d.captioned == 0


class TestFanout:
    def test_one_item_per_photo(self):
        d = parse_drop("c1", "L1", [entry(f"fp{i:03d}.jpg", f"item {i}") for i in range(428)])
        assert len(plan_fanout(d)) == 428

    def test_idempotency_keys_are_unique_and_stable(self):
        d = parse_drop("c1", "L1", [entry(f"fp{i}.jpg") for i in range(20)])
        keys = [i.idempotency_key for i in plan_fanout(d)]
        assert len(set(keys)) == 20
        assert keys == [i.idempotency_key for i in plan_fanout(d)]

    def test_uncaptioned_photo_inherits_previous_caption_as_context(self):
        d = parse_drop("c1", "L1", [
            entry("fp001.jpg", "Red Wing crock"), entry("fp002.jpg", ""),
        ])
        items = plan_fanout(d)
        assert items[1].previous_caption == "Red Wing crock"

    def test_captioned_photo_gets_no_previous_context(self):
        d = parse_drop("c1", "L1", [entry("fp001.jpg", "crock"), entry("fp002.jpg", "sign")])
        assert plan_fanout(d)[1].previous_caption is None

    def test_context_carries_across_a_run_of_uncaptioned_photos(self):
        d = parse_drop("c1", "L1", [
            entry("fp001.jpg", "Red Wing crock"),
            entry("fp002.jpg", ""), entry("fp003.jpg", ""),
        ])
        items = plan_fanout(d)
        assert items[1].previous_caption == "Red Wing crock"
        assert items[2].previous_caption == "Red Wing crock"

    def test_lot_hint_is_carried_when_present(self):
        d = parse_drop("c1", "L1", [entry("fp001.jpg", "Lot 47 crock")])
        assert plan_fanout(d)[0].lot_hint == "47"

    def test_first_photo_has_no_previous_context(self):
        d = parse_drop("c1", "L1", [entry("fp001.jpg", "")])
        assert plan_fanout(d)[0].previous_caption is None
