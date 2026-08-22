from src.intake.manifest import group_into_lots
from src.intake.spatial import (
    AdjacencyClaim, PhotoObservation, SpatiallyTaggedPhoto, SurfaceSignature, Zone,
    adjacency_graph, apply_trajectory, occupancy, observations_to_tagged,
    load_observations, spatial_same_lot,
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


class TestListingGraph:
    """Step 0 sees the listing, not a single photo.

    Cross-photo claims ('this photo's right edge shows photo 47') are
    invisible to per-photo triage.
    """

    def test_right_edge_claim_links_two_photos(self):
        obs = [
            PhotoObservation(
                photo_id="p1", zone=Zone.CENTER_ISLAND_1,
                surface=SurfaceSignature.BLUE_VINYL,
                adjacencies=(AdjacencyClaim("p1", "right", "p47"),),
            ),
            PhotoObservation(
                photo_id="p47", zone=Zone.CENTER_ISLAND_1,
                surface=SurfaceSignature.BLUE_VINYL,
            ),
        ]
        graph = adjacency_graph(obs)
        assert "p47" in graph["p1"]
        assert "p1" in graph["p47"]

    def test_observations_carry_zone_into_trajectory_tags(self):
        obs = [
            PhotoObservation(
                photo_id="p1", zone=Zone.SOUTH_UNDER_TABLE,
                surface=SurfaceSignature.CONCRETE, caption="Poppy Trail",
                summary="Poppy Trail dinnerware",
            ),
            PhotoObservation(
                photo_id="p2", zone=Zone.SOUTH_UNDER_TABLE,
                surface=SurfaceSignature.CONCRETE, caption="",
                summary="Poppy Trail dinnerware",
            ),
        ]
        tagged = observations_to_tagged(obs)
        groups = group_into_lots(apply_trajectory(tagged))
        assert len(groups) == 1
        assert groups[0].photo_ids == ("p1", "p2")

    def test_observation_import_requires_exact_source_and_photo_coverage(self, tmp_path):
        import hashlib
        import json

        manifest_bytes = b'{"photos":["p1","p2"]}'
        manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        path = tmp_path / "spatial.json"
        path.write_text(json.dumps({
            "schema_version": 1,
            "model": "gemini-3.6-flash",
            "manifest_sha256": manifest_sha,
            "observations": [
                {"photo_id": "p1", "zone": "center_island_1",
                 "surface_signature": "blue_vinyl", "summary": "cards",
                 "margin_neighbors": [], "adjacencies": []},
                {"photo_id": "p2", "zone": "unknown",
                 "surface_signature": "other", "summary": "",
                 "margin_neighbors": [], "adjacencies": []},
            ],
        }))
        rows = load_observations(
            path,
            expected_photo_ids={"p1", "p2"},
            expected_manifest_sha256=manifest_sha,
        )
        assert rows[0].zone is Zone.CENTER_ISLAND_1
        assert rows[1].zone is Zone.UNKNOWN

        raw = json.loads(path.read_text())
        raw["manifest_sha256"] = "stale"
        path.write_text(json.dumps(raw))
        import pytest
        with pytest.raises(ValueError, match="stale"):
            load_observations(
                path,
                expected_photo_ids={"p1", "p2"},
                expected_manifest_sha256=manifest_sha,
            )
