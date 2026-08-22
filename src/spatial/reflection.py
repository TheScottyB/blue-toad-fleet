"""A convex reflection is a single-frame floor plan.

The operator can see Bill in some mirror lots, and in one curved object the
whole building. That image validates the zone graph the other photos imply.
"""
from dataclasses import dataclass

from src.intake.spatial import Zone


@dataclass(frozen=True)
class BarnReflection:
    source_photo_id: str
    sees_whole_building: bool
    visible_zones: tuple[Zone, ...]
    notes: str = ""


def reflection_validates(implied_zones: set[Zone], reflection: BarnReflection) -> bool:
    """True if every zone the graph inferred appears in the reflection.

    A whole-building bounce covers any implied set. An empty graph is vacuously
    covered. A partial mirror that omits a zone the other photos placed is a
    disagreement, not a floor plan.
    """
    if not implied_zones:
        return True
    if reflection.sees_whole_building:
        return True
    visible = set(reflection.visible_zones)
    return implied_zones <= visible
