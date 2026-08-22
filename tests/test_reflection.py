"""A convex reflection is a single-frame floor plan for the room graph."""
from src.intake.spatial import Zone
from src.spatial.reflection import BarnReflection, reflection_validates


class TestBarnReflection:
    def test_a_whole_building_reflection_covers_the_implied_graph(self):
        r = BarnReflection(
            source_photo_id="p-mirror",
            sees_whole_building=True,
            visible_zones=(
                Zone.NORTH_BACK_WALL, Zone.WEST_SIDE_TABLES,
                Zone.CENTER_ISLAND_1, Zone.CENTER_ISLAND_2,
                Zone.EAST_SIDE_TABLES, Zone.SOUTH_UNDER_TABLE,
            ),
        )
        implied = {Zone.CENTER_ISLAND_1, Zone.NORTH_BACK_WALL}
        assert reflection_validates(implied, r) is True

    def test_a_mirror_that_misses_a_graph_zone_fails(self):
        r = BarnReflection(
            source_photo_id="p-mirror",
            sees_whole_building=False,
            visible_zones=(Zone.NORTH_BACK_WALL,),
        )
        implied = {Zone.CENTER_ISLAND_1, Zone.NORTH_BACK_WALL}
        assert reflection_validates(implied, r) is False

    def test_empty_graph_is_vacuously_covered(self):
        r = BarnReflection(
            source_photo_id="p-mirror",
            sees_whole_building=False,
            visible_zones=(Zone.NORTH_BACK_WALL,),
        )
        assert reflection_validates(set(), r) is True
