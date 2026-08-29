# Release evidence

- **Status:** NOT READY
- **Generated:** 2026-08-29T23:41:26.562748+00:00
- **Commit:** `1efe68cc882c76d6b981e77f6a50b07eb655c56a`
- **Python:** `3.14.4`

## Test invocation

- Command: `python -m pytest tests/ -q --junitxml=artifacts/release/pytest.xml`
- Collected: 949
- Passed: 942
- Skipped: 7
- Failed: 0
- Errors: 0

## Dependency identities

- `requirements.txt` — `e4d5b89a0738915ff977575ffaf015cdbf536bd7ec2d797c86104fa64411242d`
- `requirements-dev.txt` — `8c18e616f1179b3e0d3f86abdee5e3a137981f9d04640d981f364ba125c9deb3`

## Canonical cycle facts

- Snapshot identity: `8680532cfd9fa2891f86b5ac63e34121ac6f10bc985411f5b1dc7d9b307a62ee`
- Artifact manifest: `unavailable`

## Deployed revision parity

- Verdict: MISMATCH
- Local commit: `1efe68cc882c76d6b981e77f6a50b07eb655c56a`
- Deployed commit: `a1f41ae74ec4e506cec4c18435748561cbdd840f`
- Health endpoint: `https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/health`

## Release blockers

- the deployed revision does not match the audited commit
- allocated lots have unresolved questions
- unresolved allocated lots: BT-001, BT-002, BT-021, BT-038, BT-039, BT-041, BT-043, BT-048, BT-050, BT-066, BT-081, BT-082, BT-087, BT-113, BT-143, BT-159, BT-165, BT-179, BT-187, BT-203, BT-213, BT-235, BT-242, BT-247, BT-256, BT-274, BT-329, BT-332, BT-337, BT-348, BT-362, BT-372, BT-373, BT-384, BT-385, BT-388, BT-394, BT-398, BT-404, BT-432, BT-434, BT-436, BT-441, BT-447, BT-450, BT-457

## Non-mutating checks

- `git diff --check`: pass
- Full local pytest report: pass
- Canonical facts seal: pass
- Deployed revision parity: MISMATCH

Revision parity is a single read-only GET against the deployed /health
endpoint; an unreachable or unstamped deployment is recorded as UNVERIFIED,
never as a pass. This command does not deploy, transmit a bid, perform the
paid repeated Vertex probe, capture authenticated Seller Hub data, or replace
the final media. Those remain explicit operator hold points.
