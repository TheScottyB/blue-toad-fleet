from pathlib import Path

import pytest

from scripts.run_vertex_pipeline import PipelineConfig, PipelineResult


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
