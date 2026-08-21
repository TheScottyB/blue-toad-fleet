from src.intake.manifest import group_into_lots
from src.intake.spatial import (
    SpatiallyTaggedPhoto, SurfaceSignature, Zone,
    apply_trajectory, occupancy, spatial_same_lot,
)


def P(pid, caption="", summary="", same=False, is_lot=True,
      surface=SurfaceSignature.CONCRETE, zone=Zone.SOUTH_UNDER_TABLE,
      neighbors=()):
    return SpatiallyTaggedPhoto(
        photo_id=pid, caption=caption, summary=summary,
        is_lot=is_lot, same_lot_as_previous=same,
        surface=surface, zone=zone, margin_neighbors=tuple(neighbors),
    )


class TestTrajectoryClustering:
    def test_ten_under_table_box_photos_become_one_poppy_trail_lot(self):
        photos = [
            P("p1", caption="Poppy Trail dinnerware set", summary="Poppy Trail dinnerware"),
        ] + [
            P(f"p{i}", caption="", summary="Poppy Trail dinnerware")
            for i in range(2, 11)
        ]
        groups = group_into_lots(apply_trajectory(photos))
        assert len(groups) == 1
        assert groups[0].photo_ids == tuple(f"p{i}" for i in range(1, 11))

    def test_two_captioned_lots_on_the_same_table_stay_separate(self):
        photos = [
            P("p1", caption="Tonka crane", summary="Tonka crane",
              surface=SurfaceSignature.BLUE_VINYL, zone=Zone.CENTER_ISLAND_1),
            P("p2", caption="costume jewelry tray", summary="jewelry tray",
              surface=SurfaceSignature.BLUE_VINYL, zone=Zone.CENTER_ISLAND_1),
        ]
        groups = group_into_lots(apply_trajectory(photos))
        assert len(groups) == 2

    def test_zone_change_breaks_a_run(self):
        photos = [
            P("p1", caption="Poppy Trail", summary="Poppy Trail",
              zone=Zone.SOUTH_UNDER_TABLE),
            P("p2", caption="", summary="Poppy Trail",
              zone=Zone.NORTH_BACK_WALL),
        ]
        groups = group_into_lots(apply_trajectory(photos))
        assert len(groups) == 2

    def test_model_same_lot_flag_still_merges_in_the_same_zone(self):
        photos = [
            P("p1", caption="lantern", summary="railroad lantern",
              surface=SurfaceSignature.PINE_PLYWOOD, zone=Zone.EAST_SIDE_TABLES),
            P("p2", caption="another angle", summary="railroad lantern",
              same=True, surface=SurfaceSignature.PINE_PLYWOOD,
              zone=Zone.EAST_SIDE_TABLES),
        ]
        groups = group_into_lots(apply_trajectory(photos))
        assert len(groups) == 1


class TestCoVisibility:
    def test_uncaptioned_photo_anchors_to_previous_via_margin_neighbor(self):
        photos = [
            P("p1", caption="Dan Marino photo", summary="Dan Marino photo",
              surface=SurfaceSignature.BLUE_VINYL, zone=Zone.CENTER_ISLAND_1),
            P("p2", caption="", summary="",
              surface=SurfaceSignature.BLUE_VINYL, zone=Zone.CENTER_ISLAND_1,
              neighbors=("sliver of Dan Marino photo on left edge",)),
        ]
        assert spatial_same_lot(photos[0], photos[1]) is True
        groups = group_into_lots(apply_trajectory(photos))
        assert len(groups) == 1

    def test_unrelated_margin_text_does_not_merge_captioned_lots(self):
        photos = [
            P("p1", caption="Dan Marino photo", summary="Dan Marino photo",
              surface=SurfaceSignature.BLUE_VINYL, zone=Zone.CENTER_ISLAND_1),
            P("p2", caption="DiMaggio hat", summary="DiMaggio hat",
              surface=SurfaceSignature.BLUE_VINYL, zone=Zone.CENTER_ISLAND_1,
              neighbors=("sliver of Dan Marino photo on left edge",)),
        ]
        groups = group_into_lots(apply_trajectory(photos))
        assert len(groups) == 2


class TestOccupancy:
    def test_groups_land_in_the_primary_photo_zone(self):
        photos = [
            P("p1", caption="travel poster", summary="Northwest Orient poster",
              surface=SurfaceSignature.OTHER, zone=Zone.NORTH_BACK_WALL),
            P("p2", caption="Topps cards", summary="Topps cards",
              surface=SurfaceSignature.BLUE_VINYL, zone=Zone.CENTER_ISLAND_1),
        ]
        tagged = apply_trajectory(photos)
        groups = group_into_lots(tagged)
        occ = occupancy(photos, groups)
        assert groups[0].lot_key in occ[Zone.NORTH_BACK_WALL]
        assert groups[1].lot_key in occ[Zone.CENTER_ISLAND_1]
