"""Cloud Run Job entrypoint: materialize, process, publish, activate."""

from __future__ import annotations

import json
import hashlib
import os
import tempfile
import traceback
from pathlib import Path

from src.cycles.model import CycleStatus
from src.cycles.storage import open_cycle_repository
from src.evidence import load_absorption_evidence


def _load_standing_rules(shop_id: str):
    """Read durable cross-cycle policy; never silently downgrade Firestore."""
    from src.memory import open_rule_store

    store = open_rule_store()
    requested = (os.environ.get("BTF_MEMORY_BACKEND") or "").strip().lower()
    if requested == "firestore" and store.backend_name != "firestore":
        raise RuntimeError("Firestore standing-rule memory is unavailable")
    return tuple(store.active_rules(shop_id))


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        raise RuntimeError(f"pipeline produced no readable {path.name}") from exc


def _require_publishable_output(input_dir: Path, output_dir: Path) -> None:
    """Require complete live evidence before a cloud cycle becomes active."""
    manifest = _read_json(input_dir / "manifest.json")
    expected_ids = {str(row["photo_id"]) for row in manifest.get("photos") or []}
    triage = _read_json(output_dir / "triage_results.json")
    actual_ids = {str(row.get("photo_id")) for row in triage}
    if not expected_ids or actual_ids != expected_ids or len(triage) != len(expected_ids):
        missing = len(expected_ids - actual_ids)
        unexpected = len(actual_ids - expected_ids)
        raise RuntimeError(
            f"triage coverage mismatch: {missing} missing, {unexpected} unexpected"
        )
    failed_triage = [row for row in triage
                     if row.get("error") or not row.get("model_used")]
    if failed_triage:
        raise RuntimeError(
            f"Vertex triage failed for {len(failed_triage)} of {len(triage)} photos; "
            "cloud outputs were not activated"
        )

    appraisals = _read_json(output_dir / "appraisal_results.json")
    appraisal_ids = [str(row.get("lot_id")) for row in appraisals]
    if len(appraisal_ids) != len(set(appraisal_ids)):
        raise RuntimeError("appraisal output contains duplicate lot ids")
    failed_appraisals = [row for row in appraisals
                         if row.get("error") or not row.get("model_used")]
    if failed_appraisals:
        raise RuntimeError(
            f"Vertex appraisal failed for {len(failed_appraisals)} of "
            f"{len(appraisals)} candidate lots; cloud outputs were not activated"
        )

    grounded = _read_json(output_dir / "grounded_prices.json")
    interrupted_pricing = [row for row in grounded
                           if not row.get("attempt_complete") or row.get("errors")]
    if interrupted_pricing:
        raise RuntimeError(
            f"grounded pricing was interrupted for {len(interrupted_pricing)} of "
            f"{len(grounded)} candidate lots; cloud outputs were not activated"
        )
    if grounded:
        history_path = output_dir / "grounded_prices_attempts.json"
        history = _read_json(history_path)
        current_ids = {str(row.get("lot_id")) for row in grounded}
        history_ids = {str(row.get("lot_id")) for row in history}
        if not current_ids <= history_ids:
            raise RuntimeError("grounded pricing attempt history is incomplete")

    decomposition = output_dir / "decomposition_results.json"
    if decomposition.exists():
        rows = _read_json(decomposition)
        failures = [row for row in rows
                    if row.get("error") or not row.get("model_used")]
        if failures:
            raise RuntimeError(
                f"container analysis failed for {len(failures)} of {len(rows)} lots; "
                "cloud outputs were not activated"
            )

    state = _read_json(output_dir / "pipeline_state.json")
    if int(state.get("photos_count", -1)) != len(expected_ids):
        raise RuntimeError("pipeline snapshot does not reconcile to its source manifest")
    coverage = state.get("coverage") or {}
    if set(coverage.get("source_photo_ids") or []) != expected_ids:
        raise RuntimeError("pipeline coverage source ids do not match the manifest")
    if set(coverage.get("triage_success_ids") or []) != expected_ids:
        raise RuntimeError("pipeline coverage does not account for every triage result")
    requested_appraisals = coverage.get("appraisal_requested_ids") or []
    successful_appraisals = coverage.get("appraisal_success_ids") or []
    if (len(requested_appraisals) != len(set(requested_appraisals))
            or set(requested_appraisals) != set(successful_appraisals)
            or set(successful_appraisals) != set(appraisal_ids)):
        raise RuntimeError("appraisal requested/successful coverage does not reconcile")
    requested_decomposition = coverage.get("decomposition_requested_ids") or []
    successful_decomposition = coverage.get("decomposition_success_ids") or []
    if (len(requested_decomposition) != len(set(requested_decomposition))
            or set(requested_decomposition) != set(successful_decomposition)):
        raise RuntimeError("container decomposition coverage does not reconcile")

    decisions = state.get("decisions")
    summary = state.get("summary")
    if not isinstance(decisions, list) or not isinstance(summary, dict):
        raise RuntimeError("pipeline snapshot has no typed decision reconciliation")
    decision_ids = [str(row.get("lot_id")) for row in decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise RuntimeError("pipeline decisions contain duplicate lot ids")
    allocated = [row for row in decisions if row.get("allocated") and not row.get("speculative")]
    for row in allocated:
        comp = row.get("comp") or {}
        if (int(comp.get("source_count") or 0) <= 0
                or comp.get("provenance") not in {"grounded_search", "operator_reference"}):
            raise RuntimeError(f"allocated lot lacks usable comp provenance: {row.get('lot_id')}")
        if row.get("mechanic") == "unknown" or row.get("needs_mechanic_ruling"):
            raise RuntimeError(f"allocated lot has unresolved mechanic: {row.get('lot_id')}")
    committed_max = round(sum(float(row.get("committed_max") or 0) for row in allocated), 2)
    committed_all_in = round(sum(float(row.get("committed_all_in") or 0) for row in allocated), 2)
    if (committed_max != round(float(summary.get("committed_max") or 0), 2)
            or committed_all_in != round(float(summary.get("committed_all_in") or 0), 2)
            or int(summary.get("allocated") or 0) != len(allocated)):
        raise RuntimeError("pipeline decision money does not reconcile to its summary")
    if committed_all_in > float(state.get("budget_cap") or 0):
        raise RuntimeError("pipeline decisions exceed the all-in budget cap")
    # DELIBERATELY WIDE (operator ruling, 2026-08-29): the release gate blocks
    # asked-only per the queue contract — an operator has reviewed that fixture
    # and its deferred/dropped lots ship flagged. This publication gate guards
    # UNREVIEWED fresh-cycle output, where nobody has seen the sheet at all,
    # so the full asked+deferred+dropped union stays the fail-closed posture.
    unresolved = set((state.get("queue") or {}).get("unresolved_lot_ids") or [])
    affected = sorted(unresolved & {str(row["lot_id"]) for row in allocated})
    if affected:
        raise RuntimeError(
            "allocated lots still have unresolved money-bearing questions: "
            + ", ".join(affected))

    absorption_input = input_dir / "absorption_evidence.json"
    absorption_output = output_dir / "absorption_evidence.json"
    absorption_state = (state.get("external_evidence") or {}).get("absorption") or {}
    if absorption_input.is_file():
        records = load_absorption_evidence(absorption_input)
        if not absorption_output.is_file():
            raise RuntimeError("verified absorption evidence was not attached to output")
        revision = hashlib.sha256(absorption_input.read_bytes()).hexdigest()
        if hashlib.sha256(absorption_output.read_bytes()).hexdigest() != revision:
            raise RuntimeError("published absorption evidence differs from cycle input")
        if (
            absorption_state.get("status") != "verified"
            or absorption_state.get("revision_sha256") != revision
            or {record.lot_id for record in records} - set(decision_ids)
        ):
            raise RuntimeError("absorption evidence does not reconcile to cycle state")
    elif absorption_state.get("status") != "unavailable":
        raise RuntimeError("cycle claims absorption evidence that was not staged")
    for name in ("manifest.json", "bid_sheet.xlsx", "absentee_bid_email.txt"):
        path = output_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"pipeline output is missing or empty: {name}")


def run_cycle() -> int:
    cycle_id = os.environ.get("BTF_CYCLE_ID", "")
    shop_id = os.environ.get("BTF_SHOP_ID", "richmond-general")
    repo = open_cycle_repository()
    if repo is None:
        raise RuntimeError("BTF_CYCLE_BUCKET or BTF_CYCLE_LOCAL_ROOT is required")
    request = repo.read_request(shop_id, cycle_id)
    if not repo.is_ready(request):
        raise RuntimeError(f"cycle {cycle_id} has no READY marker")

    try:
        current = repo.read_status(request)
        if current.state == "published":
            print(f"cycle {cycle_id} already published; retry is a no-op")
            return 0
    except Exception:
        pass

    repo.write_status(CycleStatus.make(request, "running", "Cloud Run Job started"))
    try:
        with tempfile.TemporaryDirectory(prefix=f"btf-{cycle_id}-") as tmp:
            root = Path(tmp)
            data_dir = repo.materialize_input(request, root / "input")
            output_dir = root / "output"
            output_dir.mkdir(parents=True, exist_ok=True)

            # Import here so status can record an initialization failure.
            from scripts.run_vertex_pipeline import (
                PipelineConfig, execute_pipeline,
            )
            standing_rules = _load_standing_rules(request.shop_id)
            execute_pipeline(PipelineConfig(
                cycle_id=request.cycle_id,
                listing_id=request.listing_id,
                data_dir=data_dir,
                output_dir=output_dir,
                budget_cap=request.budget_cap,
                auto_send_threshold=request.auto_send_threshold,
                auction_title=request.auction_title,
                auction_date=request.auction_date,
                auction_timezone=request.timezone_name,
                auction_deadline=request.deadline,
                venue=request.venue,
                email_to=request.email_to,
                force_live_vertex=False,
                # Historic Aug-22 hand entries are not portable across sales.
                # A fresh cycle starts from its own full gallery and refuses
                # pricing until its own grounded comp stage supplies evidence.
                reference_comps={},
                operator_approved={},
                standing_rules=standing_rules,
                cycle_questions=(),
                enable_grounded_pricing=True,
            ))
            # run_pipeline needs worker-local absolute paths while appraising.
            # The published manifest is rebuilt from the immutable input so none
            # of those temporary paths can escape into durable output.
            repo.write_published_source_manifest(
                request, output_dir / "manifest.json")
            _require_publishable_output(data_dir, output_dir)
            repo.write_status(CycleStatus.make(
                request, "validated", "All publication gates passed"))
            artifact_manifest = repo.publish_outputs(request, output_dir)
            artifacts = sorted(artifact_manifest["artifacts"])
            repo.activate(request, artifact_manifest)
            repo.write_status(CycleStatus.make(
                request, "published", "Cloud processing complete",
                artifacts=artifacts,
            ))
            print(f"cycle {cycle_id} published with {len(artifacts)} artifacts")
        return 0
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"[:1000]
        repo.write_status(CycleStatus.make(request, "failed", detail))
        # Cloud Run's execution retry can run immediately, and an operator can
        # relaunch after fixing credentials or quota. A succeeded run keeps the
        # claim, so duplicate READY deliveries remain harmless.
        repo.release_launch(request)
        traceback.print_exc()
        raise


if __name__ == "__main__":
    raise SystemExit(run_cycle())
