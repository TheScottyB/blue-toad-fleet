# Release evidence

**Status:** NOT READY  
**Generated:** 2026-08-29T21:59:00.031287+00:00  
**Commit:** `b938a220300f077f0b6bee6c01b793f4cc6ed267`  
**Python:** `3.14.4`

## Test invocation

- Command: `python -m pytest tests/ -q --junitxml=artifacts/release/pytest.xml`
- Collected: 885
- Passed: 878
- Skipped: 7
- Failed: 0
- Errors: 0

## Dependency identities

- `requirements.txt` — `e4d5b89a0738915ff977575ffaf015cdbf536bd7ec2d797c86104fa64411242d`
- `requirements-dev.txt` — `8c18e616f1179b3e0d3f86abdee5e3a137981f9d04640d981f364ba125c9deb3`

## Canonical cycle facts

- Blocked: pipeline state predates decision provenance; rerun the canonical pipeline

## Deployed revision parity

- Verdict: MISMATCH
- Local commit: `b938a220300f077f0b6bee6c01b793f4cc6ed267`
- Deployed commit: `eb1c1ac19b0dc099bbcc709880a0386ed1aabca6`
- Health endpoint: `https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/health`

## Release blockers

- the deployed revision does not match the audited commit
- canonical submission facts could not be sealed

## Non-mutating checks

- `git diff --check`: pass
- Full local pytest report: pass
- Canonical facts seal: fail
- Deployed revision parity: MISMATCH

Revision parity is a single read-only GET against the deployed /health
endpoint; an unreachable or unstamped deployment is recorded as UNVERIFIED,
never as a pass. This command does not deploy, transmit a bid, perform the
paid repeated Vertex probe, capture authenticated Seller Hub data, or replace
the final media. Those remain explicit operator hold points.
