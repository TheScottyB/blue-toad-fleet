# Brief: the canonical rerun cannot seal — F21 path wiring defect — captain lane, 2026-08-29

**Status: APPROVED by the operator 2026-08-29 and delivered — committed to
master and messaged to the pipeline lane's session.**

To: pipeline lane (F21 / release-parity work)
From: captain lane
Re: the release gate's last blocker is unreachable with the current wiring,
and the run that tries is priced at full corpus

## Context

Your F21 landing is in (`aafd548`), the release gate runs, and its report is
green on everything — 874/0, dependency hashes, parity MATCH — except one
blocker: *"pipeline state predates decision provenance; rerun the canonical
pipeline"* (`scripts/collect_submission_facts.py:161`). The operator ordered
the rerun. Two attempts were stopped (nothing promoted either time — the
atomic staging held), because the wiring the rerun depends on does not line
up. No relaunch until this is fixed by its owner: you.

## The defect triangle, line-cited

1. **The seal reads state from the fixture directory.** The facts collector
   resolves source paths from `media/video_manifest.json`, whose
   `pipeline_state` entry (line 69) is
   `data/aug22_gallery_4160518/pipeline_state.json`.
2. **The F21 writer puts state in `output_path`.**
   `write_pipeline_state_artifact` writes `output_path /
   "pipeline_state.json"` (`scripts/run_vertex_pipeline.py:1184`).
3. **`output_dir` also silently controls the CACHE lookup.**
   `cache_path = Path(output_dir) if output_dir else data_path`
   (`scripts/run_vertex_pipeline.py:1340`), while `main()` defaults
   `--output-dir` to `data` (`:1438`).

Consequences, per invocation:

| Invocation | Caches found? | State lands where the seal reads? |
|---|---|---|
| CLI default (`--output-dir data`) | **No** — looks in `data/`, which has none → full live run | No (`data/pipeline_state.json`) |
| `output_dir=None` (function default) | Yes | No (`data/pipeline_state.json` via `data_path.parent`) |
| `output_dir=data/aug22_gallery_4160518` | Yes | Yes — but email/xlsx artifacts then land in the fixture dir, off their historical `data/` paths |

No invocation currently finds the caches, writes state where the manifest
points, AND keeps the money artifacts on their canonical paths. The literal
default is the worst of the three: it pays for everything and seals nothing.

## The second cost driver — your call to make deliberately

Even with paths fixed, `AppraisalEngine.will_use_cache` is all-or-nothing
(`src/appraiser/engine.py:133-137`): one missing required id fails the whole
batch to live. The current candidate set is the 415 lot-group primaries
(verified by re-executing `run_intake_stage`: 462 photos → 415 groups → 415
candidates); the 228-entry cache matches 227 of them (BT-181 is cached but no
longer a candidate — absorbed into the group primaried by 838421481), so 188
are uncached — and the all-or-nothing gate turns that into **415 live
appraisal calls**, not 188. Whether to keep all-or-nothing (a coherence
guarantee) or allow per-lot cache reuse with live fill-in (less than half the
spend) is a design decision, not a bug — decide it explicitly and say which
in the fix.

## The asks

1. Make one blessed canonical invocation that simultaneously: finds the
   fixture caches, writes `pipeline_state.json` where
   `media/video_manifest.json` points, and keeps the authoritative money
   artifacts on their historical paths (F0 ownership tests are the referee).
2. Pin it with a test: the canonical invocation's resolved cache path, state
   path, and the manifest's `pipeline_state` entry must agree — this exact
   three-way drift is what burned two aborted runs today.
3. Rule on all-or-nothing vs incremental cache reuse, in a comment where
   `will_use_cache` is called from the appraisal stage.
4. Reply through the operator when landed; the captain relaunches the rerun
   on their order and the release report goes for READY.

Working-tree state you inherit: clean except the untracked NOT-READY
`docs/evidence/RELEASE.md` from today's gate run; both your backup stashes
still exist untouched.
