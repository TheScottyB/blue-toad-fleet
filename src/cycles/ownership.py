"""Canonical writers for paths whose silent replacement would change evidence."""

PROTECTED_ARTIFACT_OWNERS = {
    "data/BlueToad_2026-08-22_BidSheet.xlsx": "scripts/run_vertex_pipeline.py",
    "data/aug22_absentee_bid_email.txt": "scripts/run_vertex_pipeline.py",
    "media/blue_toad_fleet_demo.mp4": "scripts/assemble_final.py",
    "media/submission_facts.json": "scripts/build_submission_facts.py",
    "shops/{shop_id}/ACTIVE.json": "src/cycles/storage.py",
}
