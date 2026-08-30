# Release evidence

- **Status:** READY FOR OPERATOR HOLD POINTS
- **Generated:** 2026-08-30T04:15:36.905067+00:00
- **Commit:** `0a6e85a1f887e90da4b137043206a3a9c957c6c9`
- **Python:** `3.14.4`

## Test invocation

- Command: `python -m pytest tests/ -q --junitxml=artifacts/release/pytest.xml`
- Collected: 1019
- Passed: 1012
- Skipped: 7
- Failed: 0
- Errors: 0

## Dependency identities

- `requirements.txt` — `e4d5b89a0738915ff977575ffaf015cdbf536bd7ec2d797c86104fa64411242d`
- `requirements-dev.txt` — `8c18e616f1179b3e0d3f86abdee5e3a137981f9d04640d981f364ba125c9deb3`

## Canonical cycle facts

- Snapshot identity: `1dfc4261ff3f8f562ff04be634062d76f5622ce79f70db499816b52c669a9890`
- Artifact manifest: `32139b6e7acd5ecf9b5b31b80047b49d875102b3a4e80b75055b8296cc6be960`
- Flagged non-blocking allocated lots: 45 deferred (desk-cannot-answer), 27 dropped (over queue cap) — these ship flagged low-confidence per the queue contract

## Deployed revision parity

- Verdict: MATCH
- Local commit: `0a6e85a1f887e90da4b137043206a3a9c957c6c9`
- Deployed commit: `0a6e85a1f887e90da4b137043206a3a9c957c6c9`
- Health endpoint: `https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/health`

## Release blockers

- None.

## Non-mutating checks

- `git diff --check`: pass
- Full local pytest report: pass
- Canonical facts seal: pass
- Deployed revision parity: MATCH

Revision parity is a single read-only GET against the deployed /health
endpoint; an unreachable or unstamped deployment is recorded as UNVERIFIED,
never as a pass. This command does not deploy, transmit a bid, perform the
paid repeated Vertex probe, capture authenticated Seller Hub data, or replace
the final media. Those remain explicit operator hold points.
