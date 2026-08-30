# Release evidence

- **Status:** NOT READY
- **Generated:** 2026-08-30T00:31:06.940341+00:00
- **Commit:** `80eed4404abded2bb2209c52dd84379176d1d154`
- **Python:** `3.14.4`

## Test invocation

- Command: `python -m pytest tests/ -q --junitxml=artifacts/release/pytest.xml`
- Collected: 977
- Passed: 970
- Skipped: 7
- Failed: 0
- Errors: 0

## Dependency identities

- `requirements.txt` — `e4d5b89a0738915ff977575ffaf015cdbf536bd7ec2d797c86104fa64411242d`
- `requirements-dev.txt` — `8c18e616f1179b3e0d3f86abdee5e3a137981f9d04640d981f364ba125c9deb3`

## Canonical cycle facts

- Snapshot identity: `65f3ff9fa040066a91c9243a1b44637394165c9a538c3279050edbbe4592cdfc`
- Artifact manifest: `unavailable`
- Flagged non-blocking allocated lots: 45 deferred (desk-cannot-answer), 27 dropped (over queue cap) — these ship flagged low-confidence per the queue contract

## Deployed revision parity

- Verdict: MISMATCH
- Local commit: `80eed4404abded2bb2209c52dd84379176d1d154`
- Deployed commit: `a523a6e19ea50e4579771d237e80233e250112c4`
- Health endpoint: `https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/health`

## Release blockers

- the deployed revision does not match the audited commit
- no sealed artifact manifest is declared
- facts snapshot was generated from a dirty working tree

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
