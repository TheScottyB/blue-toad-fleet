"""
Intake — the sanctioned ingestion boundary.

Nothing in this repository fetches the auction site. AuctionZip returns 403 to
automated requests, and scraping an auction house's gallery is not a thing we
want in a public repo under a named person. Instead the operator exports the
gallery once per cycle into a bucket, and everything downstream of that drop is
unattended.

That single human touch is the honest cost of a clean posture, and it is the
trigger for the run rather than a step inside it.

Intake reads a drop, normalises it into lots, and emits one work item per photo
for the Appraiser to fan out over. It is deliberately dumb: no model calls, no
judgment, just parsing and grouping — so that when the pipeline produces
nonsense, this is not where you have to look.
"""

from src.intake.manifest import (
    GalleryDrop, LotGroup, PhotoRef, TriagedPhoto, WorkItem,
    group_into_lots, parse_drop, plan_fanout,
)

__all__ = ["GalleryDrop", "LotGroup", "PhotoRef", "TriagedPhoto", "WorkItem",
           "group_into_lots", "parse_drop", "plan_fanout"]
