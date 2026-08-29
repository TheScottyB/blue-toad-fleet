from src.assemble import AppraisedPhoto, assemble_lots
from src.assemble.labor import labor_aspect
from src.bidmath import (
    BidMechanic, CompEstimate, Confidence, LaborAspect, Lot, elect,
    price_lot, remainder_opportunity,
)


class TestLaborAspect:
    def test_jewelry_trays_are_shelf_stock(self):
        assert labor_aspect("jewelry", is_container=True,
                            contents=("tray 12", "tray 14")) is LaborAspect.SHELF

    def test_jewelry_in_identification_is_shelf_even_when_category_is_other(self):
        # Live lots outside REFERENCE_COMPS land in the constrained enum
        # ("other"), so the identification has to carry the aspect.
        assert labor_aspect(
            "other",
            identification="Assorted estate costume jewelry in plastic tote",
        ) is LaborAspect.SHELF

    def test_bulk_dinnerware_is_shelf(self):
        assert labor_aspect("dinnerware / pottery") is LaborAspect.SHELF

    def test_phonograph_is_research(self):
        assert labor_aspect("phonograph / records") is LaborAspect.RESEARCH

    def test_edison_in_identification_is_research(self):
        assert labor_aspect(
            "other",
            identification="Lot of Edison phonograph cylinder records",
        ) is LaborAspect.RESEARCH

    def test_a_busy_container_is_research(self):
        assert labor_aspect(
            "vintage smalls", is_container=True,
            contents=("a", "b", "c", "d"),
        ) is LaborAspect.RESEARCH

    def test_a_hallmark_in_the_identification_is_research(self):
        assert labor_aspect(
            "other", identification="sterling spoon, hallmark on reverse",
        ) is LaborAspect.RESEARCH

    def test_hallmark_the_brand_is_not_research(self):
        assert labor_aspect(
            "vintage toys",
            identification="Be My Valentine Hallmark Special Edition Barbie",
        ) is LaborAspect.LIST

    def test_stoneware_is_research(self):
        assert labor_aspect("stoneware") is LaborAspect.RESEARCH

    def test_plain_toys_are_one_listing(self):
        assert labor_aspect("vintage toys") is LaborAspect.LIST

    def test_assemble_stamps_labor_on_the_lot(self):
        lots = assemble_lots([
            AppraisedPhoto(
                photo_id="BT-002", caption="trays",
                identification="estate jewelry", category="jewelry",
                is_container=True, contents=("tray 12", "tray 14"),
            ),
        ])
        assert lots[0].labor is LaborAspect.SHELF
        assert price_lot(lots[0]).labor is LaborAspect.SHELF

    def test_price_lot_and_remainder_keep_the_lot_labor(self):
        lot = elect(Lot(
            lot_id="BT-041", caption="edison rolls",
            category="phonograph / records", fit_score=0.9,
            condition_penalty=0.0,
            comp=CompEstimate(low=100, high=130, source_count=3,
                              confidence=Confidence.HIGH),
            mechanic=BidMechanic.CHOICE, unit_count=4, units_wanted=1,
            labor=LaborAspect.RESEARCH,
        ), k=1)
        d = price_lot(lot)
        assert d.labor is LaborAspect.RESEARCH
        r = remainder_opportunity(d, floor=5.0)
        assert r is not None
        assert r.labor is LaborAspect.RESEARCH


def test_console_shows_labor_on_the_card():
    from dataclasses import replace
    from src.gate import render_console
    from tests.test_gate import _lot, _view
    lots = [replace(_lot(0), category="jewelry", labor=LaborAspect.SHELF)]
    h = render_console(_view(lots=lots))
    assert ">shelf<" in h
    assert 'class="tag shelf"' in h
