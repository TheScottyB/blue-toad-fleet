"""The cloud boundary: immutable inputs, one launch, durable outputs."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.cycles import (
    CloudRunJobLauncher, CycleConflict, CycleRepository, CycleRequest,
    GCSObjectStore, LocalObjectStore,
)


def cycle_request(**overrides):
    values = {
        "cycle_id": "2026-09-05",
        "listing_id": "12345",
        "auction_title": "September Estate Auction",
        "auction_date": "2026-09-05",
        "timezone_name": "America/Chicago",
        "venue": "200 Test Lane, Genoa City, WI",
        "deadline": "2026-09-04T20:00:00-05:00",
    }
    values.update(overrides)
    return CycleRequest(**values)


def gallery(root: Path, listing_id="12345") -> Path:
    source = root / "gallery"
    images = source / "images"
    images.mkdir(parents=True)
    photos = []
    for seq, pid in ((1, "9001"), (2, "9002")):
        filename = f"{seq:03d}_{pid}.jpg"
        (images / filename).write_bytes(b"full-resolution-jpeg-" + bytes([seq]))
        photos.append({
            "sequence": seq,
            "photo_id": pid,
            "filename": filename,
            "caption": f"Lot {seq}",
            "has_caption": True,
            "thumb_url": f"//example/{pid}_th",
            "full_url": f"//example/{pid}_fl",
            # Prove staging does not preserve a machine-specific path.
            "local_path": str(images / filename),
        })
    (source / "manifest.json").write_text(json.dumps({
        "listing_id": listing_id,
        "total_photos": 2,
        "captioned_photos": 2,
        "photos": photos,
    }))
    # A local conclusion from an earlier run must not become cloud input.
    (source / "appraisal_results.json").write_text('[{"stale": true}]')
    return source


def add_absorption(source: Path) -> None:
    (source / "absorption_evidence.json").write_text(json.dumps({
        "schema_version": 1,
        "lot_id": "BT-001",
        "query": "test",
        "marketplace": "EBAY-US",
        "window_start": "2025-09-04",
        "window_end": "2026-09-04",
        "displayed_window": "Sep 4, 2025 – Sep 4, 2026",
        "sold_units_last_365_days": 2,
        "sold_rows": 2,
        "active_listings_now": 1,
        "sold_pages_complete": True,
        "sold_page_count": 1,
        "captured_at": "2026-09-04T12:00:00-05:00",
        "reviewer": "operator",
        "source_sha256": {"capture": "a" * 64},
    }))


@pytest.fixture
def staged(tmp_path):
    objects = LocalObjectStore(tmp_path / "objects")
    repo = CycleRepository(objects)
    request = cycle_request(budget_cap=725)
    marker = repo.stage_directory(request, gallery(tmp_path), ready=True)
    return repo, request, marker, objects


def test_stage_uploads_manifest_and_every_named_image_then_ready(staged):
    repo, request, marker, objects = staged
    names = objects.names(request.prefix)
    assert names[-1]  # stable sorted listing exists
    assert repo.ready_name(request) in names
    assert f"{request.prefix}/input/images/001_9001.jpg" in names
    assert f"{request.prefix}/input/images/002_9002.jpg" in names
    assert not any("appraisal_results" in n for n in names)
    manifest = repo.get_json(f"{request.prefix}/input/manifest.json")
    assert manifest["photos"][0]["local_path"] == "images/001_9001.jpg"
    assert marker["photo_count"] == 2
    assert len(marker["manifest_sha256"]) == 64


def test_stage_carries_only_validated_optional_absorption_evidence(tmp_path):
    source = gallery(tmp_path)
    add_absorption(source)
    objects = LocalObjectStore(tmp_path / "objects")
    repo = CycleRepository(objects)
    request = cycle_request()
    repo.stage_directory(request, source, ready=True)
    assert objects.exists(f"{request.prefix}/input/absorption_evidence.json")


def test_stage_validates_and_rebinds_spatial_observations_to_durable_manifest(tmp_path):
    source = gallery(tmp_path)
    original_sha = hashlib.sha256((source / "manifest.json").read_bytes()).hexdigest()
    (source / "spatial_observations.json").write_text(json.dumps({
        "schema_version": 1,
        "model": "gemini-3.6-flash",
        "manifest_sha256": original_sha,
        "observations": [
            {"photo_id": photo_id, "zone": "unknown",
             "surface_signature": "other", "summary": "",
             "margin_neighbors": [], "adjacencies": []}
            for photo_id in ("9001", "9002")
        ],
    }))
    objects = LocalObjectStore(tmp_path / "objects")
    repo = CycleRepository(objects)
    request = cycle_request()
    marker = repo.stage_directory(request, source, ready=True)
    spatial = repo.get_json(f"{request.prefix}/input/spatial_observations.json")
    assert spatial["staged_from_manifest_sha256"] == original_sha
    assert spatial["manifest_sha256"] == marker["manifest_sha256"]


def test_cycle_id_is_immutable_and_launch_is_exactly_once(staged, tmp_path):
    repo, request, _, _ = staged
    with pytest.raises(CycleConflict):
        repo.stage_directory(request, gallery(tmp_path / "again"), ready=True)
    assert repo.claim_launch(request) is True
    assert repo.claim_launch(request) is False


def test_cycle_request_requires_execution_metadata():
    with pytest.raises(TypeError):
        CycleRequest(cycle_id="2026-09-05", listing_id="12345")
    with pytest.raises(ValueError, match="explicit UTC offset"):
        cycle_request(deadline="2026-09-04T16:00:00")


def test_generic_cycle_questions_cannot_name_historic_lots():
    from scripts.run_vertex_pipeline import validate_cycle_questions
    from src.appraisal import Question, QuestionKind

    question = Question(
        kind=QuestionKind.APPETITE,
        category="vintage tools",
        prompt="Historic question",
        lot_ids=("BT-083",),
    )
    with pytest.raises(ValueError, match="outside this cycle: BT-083"):
        validate_cycle_questions((question,), {"BT-001", "BT-002"})
    assert validate_cycle_questions((), {"BT-001"}) == ()


def test_worker_materialization_rewrites_paths_to_ephemeral_disk(staged, tmp_path):
    repo, request, _, _ = staged
    dest = repo.materialize_input(request, tmp_path / "job")
    manifest = json.loads((dest / "manifest.json").read_text())
    image = Path(manifest["photos"][0]["local_path"])
    assert image.is_absolute()
    assert image.read_bytes().startswith(b"full-resolution")
    assert manifest["photos"][0]["source_object"].endswith(
        "/input/images/001_9001.jpg")


def test_worker_processes_cloud_copy_and_publishes_outputs(
    monkeypatch, staged, tmp_path,
):
    from src.cycles import worker
    from scripts import run_vertex_pipeline

    repo, request, _, objects = staged
    monkeypatch.setenv("BTF_CYCLE_LOCAL_ROOT", str(objects.root))
    monkeypatch.setenv("BTF_CYCLE_ID", request.cycle_id)
    monkeypatch.setenv("BTF_SHOP_ID", request.shop_id)

    observed = {}
    monkeypatch.setattr(worker, "_load_standing_rules",
                        lambda _shop_id: ("durable-rule",))

    def fake_pipeline(**kwargs):
        manifest = json.loads((Path(kwargs["data_dir"]) / "manifest.json").read_text())
        observed["image_exists"] = Path(manifest["photos"][0]["local_path"]).is_file()
        observed["reference_comps"] = kwargs["reference_comps"]
        observed["auction_title"] = kwargs["auction_title"]
        observed["auction_deadline"] = kwargs["auction_deadline"]
        observed["standing_rules"] = kwargs["standing_rules"]
        observed["cycle_questions"] = kwargs["cycle_questions"]
        output = Path(kwargs["output_dir"])
        (output / "triage_results.json").write_text(
            '[{"photo_id":"9001","model_used":"gemini-test"},'
            '{"photo_id":"9002","model_used":"gemini-test"}]')
        (output / "appraisal_results.json").write_text(
            '[{"lot_id":"BT-001","model_used":"gemini-test"}]')
        (output / "grounded_prices.json").write_text("[]")
        (output / "pipeline_state.json").write_text(json.dumps({
            "photos_count": 2,
            "budget_cap": 725.0,
            "summary": {"allocated": 0, "committed_max": 0, "committed_all_in": 0},
            "decisions": [],
            "queue": {"unresolved_lot_ids": []},
            "external_evidence": {"absorption": {"status": "unavailable"}},
            "coverage": {
                "source_photo_ids": ["9001", "9002"],
                "triage_success_ids": ["9001", "9002"],
                "appraisal_requested_ids": ["BT-001"],
                "appraisal_success_ids": ["BT-001"],
                "decomposition_requested_ids": [],
                "decomposition_success_ids": [],
            },
        }))
        (output / "manifest.json").write_text('{"published": true}')
        (output / "bid_sheet.xlsx").write_bytes(b"workbook")
        (output / "absentee_bid_email.txt").write_text("draft")

    monkeypatch.setattr(run_vertex_pipeline, "run_pipeline", fake_pipeline)
    assert worker.run_cycle() == 0
    assert observed == {
        "image_exists": True,
        "reference_comps": {},
        "auction_title": request.auction_title,
        "auction_deadline": request.deadline,
        "standing_rules": ("durable-rule",),
        "cycle_questions": (),
    }
    status = repo.read_status(request)
    assert status.state == "published"
    assert set(status.artifacts) == {
        "absentee_bid_email.txt", "appraisal_results.json", "bid_sheet.xlsx",
        "grounded_prices.json", "manifest.json", "pipeline_state.json",
        "triage_results.json",
    }
    active = repo.get_json(repo.active_name(request.shop_id))
    assert active["cycle_id"] == request.cycle_id
    artifact_manifest = repo.get_json(active["artifact_manifest"])
    bid_sheet = artifact_manifest["artifacts"]["bid_sheet.xlsx"]
    assert objects.exists(bid_sheet["object"])
    published_record = artifact_manifest["artifacts"]["manifest.json"]
    published = json.loads(objects.get_bytes(published_record["object"]))
    photo = published["photos"][0]
    assert not Path(photo["local_path"]).is_absolute()
    assert objects.get_bytes(photo["source_object"]).startswith(b"full-resolution")


def test_worker_does_not_activate_caption_fallback_and_allows_retry(
    monkeypatch, staged,
):
    from src.cycles import worker
    from scripts import run_vertex_pipeline

    repo, request, _, objects = staged
    assert repo.claim_launch(request) is True
    monkeypatch.setenv("BTF_CYCLE_LOCAL_ROOT", str(objects.root))
    monkeypatch.setenv("BTF_CYCLE_ID", request.cycle_id)
    monkeypatch.setenv("BTF_SHOP_ID", request.shop_id)

    def failed_vertex(**kwargs):
        output = Path(kwargs["output_dir"])
        (output / "triage_results.json").write_text(
            '[{"photo_id":"9001","error":"quota"},'
            '{"photo_id":"9002","model_used":"gemini-test"}]')

    monkeypatch.setattr(run_vertex_pipeline, "run_pipeline", failed_vertex)
    with pytest.raises(RuntimeError, match="failed for 1 of 2 photos"):
        worker.run_cycle()
    assert repo.read_status(request).state == "failed"
    assert repo.claim_launch(request) is True, "failed work must be retryable"
    assert not objects.exists(repo.active_name(request.shop_id))


def test_missing_image_blocks_ready_marker(tmp_path):
    source = gallery(tmp_path)
    (source / "images/002_9002.jpg").unlink()
    repo = CycleRepository(LocalObjectStore(tmp_path / "objects"))
    request = cycle_request()
    with pytest.raises(FileNotFoundError):
        repo.stage_directory(request, source, ready=True)
    assert not repo.is_ready(request)


class Response:
    status_code = 200
    text = "ok"

    def json(self):
        return {"name": "operations/run-123"}


class Session:
    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((url, json, timeout))
        return Response()


def test_job_launcher_passes_only_the_cloud_cycle_coordinates():
    session = Session()
    launcher = CloudRunJobLauncher(
        "project", "us-central1", "cycle-job", "cycle-bucket", session=session)
    request = cycle_request()
    assert launcher.launch(request) == "operations/run-123"
    url, payload, timeout = session.calls[0]
    assert url.endswith("/jobs/cycle-job:run")
    env = payload["overrides"]["containerOverrides"][0]["env"]
    assert {x["name"]: x["value"] for x in env} == {
        "BTF_CYCLE_BUCKET": "cycle-bucket",
        "BTF_CYCLE_ID": "2026-09-05",
        "BTF_SHOP_ID": "richmond-general",
    }
    assert timeout == 30


class Launcher:
    configured = True

    def __init__(self):
        self.calls = []

    def launch(self, request):
        self.calls.append(request)
        return "operations/test-launch"


def test_eventarc_ready_event_launches_once(monkeypatch, staged):
    from src import server

    repo, request, _, _ = staged
    launcher = Launcher()
    monkeypatch.setattr(server, "CYCLES", repo)
    monkeypatch.setattr(server, "CYCLE_JOBS", launcher)
    monkeypatch.setenv("BTF_CYCLE_BUCKET", "test-cycle-bucket")
    client = TestClient(server.app)
    event = {"data": {
        "bucket": "test-cycle-bucket",
        "name": repo.ready_name(request),
    }}
    first = client.post("/api/events/storage", json=event)
    second = client.post("/api/events/storage", json=event)
    assert first.status_code == 202 and first.json()["launched"] is True
    assert second.status_code == 202 and second.json()["deduplicated"] is True
    assert len(launcher.calls) == 1
    status = client.get(f"/api/cycles/{request.cycle_id}").json()["status"]
    assert status["state"] == "running"


def test_console_start_marks_staged_cycle_ready_and_launches(monkeypatch, tmp_path):
    from src import server

    objects = LocalObjectStore(tmp_path / "objects")
    repo = CycleRepository(objects)
    request = cycle_request()
    repo.stage_directory(request, gallery(tmp_path), ready=False)
    launcher = Launcher()
    monkeypatch.setattr(server, "CYCLES", repo)
    monkeypatch.setattr(server, "CYCLE_JOBS", launcher)
    monkeypatch.delenv("K_SERVICE", raising=False)

    response = TestClient(server.app).post(
        "/api/cycles/start", json={"cycle_id": request.cycle_id})
    assert response.status_code == 202
    assert response.json()["launched"] is True
    assert repo.is_ready(request)
    assert len(launcher.calls) == 1


def test_non_ready_storage_event_is_ignored(monkeypatch, staged):
    from src import server

    repo, _, _, _ = staged
    monkeypatch.setattr(server, "CYCLES", repo)
    monkeypatch.setattr(server, "CYCLE_JOBS", Launcher())
    monkeypatch.setenv("BTF_CYCLE_BUCKET", "test-cycle-bucket")
    response = TestClient(server.app).post("/api/events/storage", json={"data": {
        "bucket": "test-cycle-bucket",
        "name": "shops/richmond-general/cycles/2026-09-05/input/001.jpg",
    }})
    assert response.status_code == 202
    assert response.json()["ignored"] is True


def test_gcs_adapter_uses_generation_precondition_for_creation():
    class Blob:
        def __init__(self):
            self.kwargs = None

        def upload_from_string(self, data, **kwargs):
            self.kwargs = kwargs

    class Bucket:
        def __init__(self):
            self.the_blob = Blob()

        def blob(self, _name):
            return self.the_blob

    class Client:
        def __init__(self):
            self.the_bucket = Bucket()

        def bucket(self, _name):
            return self.the_bucket

    client = Client()
    store = GCSObjectStore("bucket", client=client)
    store.put_bytes("safe/name", b"x", content_type="text/plain", if_absent=True)
    assert client.the_bucket.the_blob.kwargs["if_generation_match"] == 0
    assert client.the_bucket.the_blob.kwargs["checksum"] == "auto"
