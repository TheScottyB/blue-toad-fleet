from pathlib import Path

import pytest

from scripts.run_vertex_pipeline import (
    AppraisalStageResult,
    DecisionStageResult,
    IntakeStageResult,
    PipelineConfig,
    PipelineResult,
    run_appraisal_stage,
    run_decision_stage,
    run_intake_stage,
    write_bid_sheet_artifact,
    write_email_artifact,
    write_pipeline_state_artifact,
    exact_requested_rows,
)


def config(**changes):
    values = {
        "cycle_id": "cycle-1",
        "listing_id": "listing-1",
        "data_dir": Path("input"),
        "output_dir": Path("output"),
        "budget_cap": 600.0,
        "auto_send_threshold": 35.0,
        "auction_title": "Test Auction",
        "auction_date": "2026-09-05",
        "auction_timezone": "America/Chicago",
        "auction_deadline": "2026-09-04T20:00:00-05:00",
        "venue": "Test Venue",
    }
    values.update(changes)
    return PipelineConfig(**values)


def test_pipeline_config_is_frozen_and_path_typed():
    value = config(data_dir="input", output_dir="output")
    assert value.data_dir == Path("input")
    with pytest.raises(AttributeError):
        value.cycle_id = "changed"


def test_pipeline_config_rejects_missing_metadata_and_invalid_budget():
    with pytest.raises(ValueError, match="metadata"):
        config(venue="")
    with pytest.raises(ValueError, match="budget"):
        config(budget_cap=10, auto_send_threshold=20)


def test_runner_core_has_no_process_exit_or_import_path_mutation():
    source = Path("scripts/run_vertex_pipeline.py").read_text()
    assert "sys.exit(" not in source
    assert "sys.path" not in source
    assert ".__dict__" not in source


def test_pipeline_result_is_a_named_typed_boundary():
    assert "pipeline_state_path" in PipelineResult.__dataclass_fields__
    assert "decisions" in PipelineResult.__dataclass_fields__


def test_pipeline_orchestration_has_explicit_typed_stages():
    assert IntakeStageResult.__dataclass_params__.frozen
    assert AppraisalStageResult.__dataclass_params__.frozen
    assert DecisionStageResult.__dataclass_params__.frozen
    assert all(callable(stage) for stage in (
        run_intake_stage,
        run_appraisal_stage,
        run_decision_stage,
        write_email_artifact,
        write_bid_sheet_artifact,
        write_pipeline_state_artifact,
    ))


def test_batch_boundary_filters_superset_cache_and_rejects_missing_or_duplicate():
    rows = [
        {"lot_id": "BT-002", "value": 2},
        {"lot_id": "BT-001", "value": 1},
        {"lot_id": "BT-999", "value": 999},
    ]
    assert [row["lot_id"] for row in exact_requested_rows(
        rows, {"BT-001", "BT-002"}, label="test batch",
    )] == ["BT-001", "BT-002"]
    with pytest.raises(RuntimeError, match="missing"):
        exact_requested_rows(rows, {"BT-003"}, label="test batch")
    with pytest.raises(RuntimeError, match="duplicate"):
        exact_requested_rows(
            [{"lot_id": "BT-001"}, {"lot_id": "BT-001"}],
            {"BT-001"}, label="test batch",
        )


def test_operator_rulings_derive_only_from_kinded_entries():
    from scripts.run_vertex_pipeline import operator_lot_rulings
    from src.appraisal import QuestionKind

    approvals = {
        "BT-165": {"ruling_kind": "lot_grouping", "ruling": "sold by the piece"},
        "BT-385": {"ruling_kind": "scope", "ruling": "value the case alone"},
        "BT-002": {"ruling": "take all three trays at x3"},  # legacy: no kind
        "BT-001": {"fit": 0.9, "cap": 100.0},
    }
    rulings = operator_lot_rulings(approvals)
    assert {(r.kind, r.lot_ids) for r in rulings} == {
        (QuestionKind.LOT_GROUPING, ("BT-165",)),
        (QuestionKind.SCOPE, ("BT-385",)),
    }
    assert all(r.answer for r in rulings)
