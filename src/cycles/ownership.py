"""Canonical writers for paths whose silent replacement would change evidence."""

PROTECTED_ARTIFACT_OWNERS = {
    "data/BlueToad_2026-08-22_BidSheet.xlsx": "scripts/run_vertex_pipeline.py",
    "data/aug22_absentee_bid_email.txt": "scripts/run_vertex_pipeline.py",
    "shops/{shop_id}/ACTIVE.json": "src/cycles/storage.py",
}
