"""Durable object layout for complete auction cycles.

The repository writes READY last. Eventarc therefore observes a cycle only after
its normalized manifest and every full-resolution source image are durable.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
from typing import Protocol

from src.cycles.model import CycleRequest, CycleStatus, cycle_prefix, utc_now


class CycleConflict(RuntimeError):
    """An immutable cycle object or launch claim already exists."""


class CycleNotFound(RuntimeError):
    """The requested staged cycle does not exist."""


class ObjectStore(Protocol):
    backend_name: str

    def put_bytes(
        self, name: str, data: bytes, *, content_type: str,
        if_absent: bool = False,
    ) -> None: ...
    def get_bytes(self, name: str) -> bytes: ...
    def exists(self, name: str) -> bool: ...
    def delete(self, name: str) -> None: ...
    def names(self, prefix: str) -> list[str]: ...


def _object_name(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe object name: {name!r}")
    return str(path)


class LocalObjectStore:
    """Filesystem-backed object store for tests and credential-free development."""

    backend_name = "local"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, name: str) -> Path:
        return self.root / _object_name(name)

    def put_bytes(
        self, name: str, data: bytes, *, content_type: str,
        if_absent: bool = False,
    ) -> None:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if if_absent and path.exists():
            raise CycleConflict(f"object already exists: {name}")
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def get_bytes(self, name: str) -> bytes:
        path = self._path(name)
        if not path.is_file():
            raise CycleNotFound(name)
        return path.read_bytes()

    def exists(self, name: str) -> bool:
        return self._path(name).is_file()

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)

    def names(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if base.is_file():
            return [_object_name(prefix)]
        if not base.exists():
            return []
        return sorted(str(p.relative_to(self.root)).replace(os.sep, "/")
                      for p in base.rglob("*") if p.is_file())


class GCSObjectStore:
    """Google Cloud Storage adapter. Imported lazily for local testability."""

    backend_name = "gcs"

    def __init__(self, bucket: str, client=None):
        if not bucket:
            raise ValueError("bucket is required")
        if client is None:
            from google.cloud import storage
            client = storage.Client()
        self.bucket_name = bucket.removeprefix("gs://").rstrip("/")
        self._bucket = client.bucket(self.bucket_name)

    def put_bytes(
        self, name: str, data: bytes, *, content_type: str,
        if_absent: bool = False,
    ) -> None:
        from google.api_core.exceptions import PreconditionFailed
        blob = self._bucket.blob(_object_name(name))
        try:
            blob.upload_from_string(
                data,
                content_type=content_type,
                if_generation_match=0 if if_absent else None,
                checksum="auto",
            )
        except PreconditionFailed as exc:
            raise CycleConflict(f"object already exists: {name}") from exc

    def get_bytes(self, name: str) -> bytes:
        from google.api_core.exceptions import NotFound
        try:
            return self._bucket.blob(_object_name(name)).download_as_bytes(
                checksum="auto")
        except NotFound as exc:
            raise CycleNotFound(name) from exc

    def exists(self, name: str) -> bool:
        return self._bucket.blob(_object_name(name)).exists()

    def delete(self, name: str) -> None:
        from google.api_core.exceptions import NotFound
        try:
            self._bucket.blob(_object_name(name)).delete()
        except NotFound:
            pass

    def names(self, prefix: str) -> list[str]:
        return sorted(blob.name for blob in self._bucket.list_blobs(
            prefix=_object_name(prefix)))


def _json_bytes(data: dict) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()


class CycleRepository:
    """One stable object contract over local disk or Cloud Storage."""

    def __init__(self, objects: ObjectStore):
        self.objects = objects

    @property
    def backend_name(self) -> str:
        return self.objects.backend_name

    @staticmethod
    def request_name(request: CycleRequest) -> str:
        return f"{request.prefix}/control/request.json"

    @staticmethod
    def request_name_for(shop_id: str, cycle_id: str) -> str:
        return f"{cycle_prefix(shop_id, cycle_id)}/control/request.json"

    @staticmethod
    def ready_name(request: CycleRequest) -> str:
        return f"{request.prefix}/control/READY.json"

    @staticmethod
    def launch_name(request: CycleRequest) -> str:
        return f"{request.prefix}/control/LAUNCHED.json"

    @staticmethod
    def status_name(request: CycleRequest) -> str:
        return f"{request.prefix}/status/status.json"

    @staticmethod
    def active_name(shop_id: str) -> str:
        return f"shops/{shop_id}/ACTIVE.json"

    @staticmethod
    def artifact_manifest_name(request: CycleRequest) -> str:
        return f"{request.prefix}/output/artifact_manifest.json"

    def put_json(
        self, name: str, data: dict, *, if_absent: bool = False,
    ) -> None:
        self.objects.put_bytes(
            name, _json_bytes(data), content_type="application/json",
            if_absent=if_absent,
        )

    def get_json(self, name: str) -> dict:
        return json.loads(self.objects.get_bytes(name))

    def stage_directory(
        self,
        request: CycleRequest,
        source_dir: str | Path,
        *,
        ready: bool = True,
    ) -> dict:
        """Upload only the immutable manifest and the images it names.

        Existing appraisal caches and spreadsheets are deliberately excluded:
        a new cloud cycle must not inherit conclusions from a local run.
        """
        source = Path(source_dir).resolve()
        manifest_path = source / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"manifest not found: {manifest_path}")
        manifest = json.loads(manifest_path.read_text())
        photos = manifest.get("photos")
        if not isinstance(photos, list) or not photos:
            raise ValueError("manifest contains no photos")
        if str(manifest.get("listing_id")) != request.listing_id:
            raise ValueError(
                f"manifest listing {manifest.get('listing_id')} does not match "
                f"request {request.listing_id}")

        normalized = dict(manifest)
        normalized_photos = []
        resolved = []
        seen_names = set()
        for photo in photos:
            filename = Path(str(photo.get("filename") or "")).name
            if not filename or filename in seen_names:
                raise ValueError(f"missing or duplicate image filename: {filename!r}")
            seen_names.add(filename)
            candidates = [
                Path(str(photo.get("local_path") or "")),
                source / "images" / filename,
                source / filename,
            ]
            image = next((p for p in candidates if p.is_file()), None)
            if image is None:
                raise FileNotFoundError(f"full-resolution image missing: {filename}")
            if image.stat().st_size == 0:
                raise ValueError(f"image is empty: {image}")
            row = dict(photo)
            row["local_path"] = f"images/{filename}"
            row["source_object"] = f"{request.prefix}/input/images/{filename}"
            image_bytes = image.read_bytes()
            row["sha256"] = hashlib.sha256(image_bytes).hexdigest()
            row["byte_size"] = len(image_bytes)
            row["content_type"] = (
                mimetypes.guess_type(filename)[0] or "application/octet-stream")
            normalized_photos.append(row)
            resolved.append((filename, image_bytes, row["content_type"]))
        normalized["photos"] = normalized_photos
        normalized["total_photos"] = len(normalized_photos)

        sidecars: list[tuple[str, bytes]] = []
        absorption_path = source / "absorption_evidence.json"
        if absorption_path.is_file():
            from src.evidence import load_absorption_evidence
            load_absorption_evidence(absorption_path)
            sidecars.append(("absorption_evidence.json", absorption_path.read_bytes()))

        # A cycle ID is immutable. request.json is the creation lock.
        self.put_json(self.request_name(request), request.as_dict(), if_absent=True)
        try:
            manifest_bytes = _json_bytes(normalized)
            spatial_path = source / "spatial_observations.json"
            if spatial_path.is_file():
                raw_spatial = json.loads(spatial_path.read_text())
                original_manifest_sha = hashlib.sha256(
                    manifest_path.read_bytes()).hexdigest()
                if (
                    raw_spatial.get("schema_version") != 1
                    or raw_spatial.get("model") != "gemini-3.6-flash"
                    or raw_spatial.get("manifest_sha256") != original_manifest_sha
                ):
                    raise ValueError("spatial observations are stale or unsupported")
                spatial_ids = [
                    str(row.get("photo_id") or "")
                    for row in raw_spatial.get("observations") or []
                ]
                expected_ids = {str(row["photo_id"]) for row in normalized_photos}
                if len(spatial_ids) != len(set(spatial_ids)) or set(spatial_ids) != expected_ids:
                    raise ValueError("spatial observation coverage does not match manifest")
                raw_spatial["staged_from_manifest_sha256"] = original_manifest_sha
                raw_spatial["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
                sidecars.append(("spatial_observations.json", _json_bytes(raw_spatial)))
            self.objects.put_bytes(
                f"{request.prefix}/input/manifest.json",
                manifest_bytes,
                content_type="application/json",
                if_absent=True,
            )
            for filename, image_bytes, content_type in resolved:
                self.objects.put_bytes(
                    f"{request.prefix}/input/images/{filename}",
                    image_bytes,
                    content_type=content_type,
                    if_absent=True,
                )
            for filename, data in sidecars:
                self.objects.put_bytes(
                    f"{request.prefix}/input/{filename}", data,
                    content_type="application/json", if_absent=True,
                )
            self.write_status(CycleStatus.make(
                request, "staged", f"{len(resolved)} source images stored"))
            marker = self.ready_payload(request, manifest_bytes)
            if ready:
                self.put_json(self.ready_name(request), marker, if_absent=True)
            return marker
        except Exception:
            # request.json remains as an audit record; incomplete cycles cannot
            # launch because READY was not written.
            raise

    def ready_payload(
        self, request: CycleRequest, manifest_bytes: bytes | None = None,
    ) -> dict:
        manifest_bytes = manifest_bytes or self.objects.get_bytes(
            f"{request.prefix}/input/manifest.json")
        manifest = json.loads(manifest_bytes)
        return {
            "cycle_id": request.cycle_id,
            "shop_id": request.shop_id,
            "listing_id": request.listing_id,
            "photo_count": len(manifest.get("photos") or []),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        }

    def mark_ready(self, request: CycleRequest) -> dict:
        marker = self.ready_payload(request)
        self.put_json(self.ready_name(request), marker, if_absent=True)
        return marker

    def read_request(self, shop_id: str, cycle_id: str) -> CycleRequest:
        return CycleRequest.from_dict(
            self.get_json(self.request_name_for(shop_id, cycle_id)))

    def is_ready(self, request: CycleRequest) -> bool:
        return self.objects.exists(self.ready_name(request))

    def claim_launch(self, request: CycleRequest) -> bool:
        if not self.is_ready(request):
            raise CycleNotFound(f"cycle is not ready: {request.cycle_id}")
        try:
            self.put_json(
                self.launch_name(request),
                {"cycle_id": request.cycle_id, "shop_id": request.shop_id},
                if_absent=True,
            )
            return True
        except CycleConflict:
            return False

    def release_launch(self, request: CycleRequest) -> None:
        self.objects.delete(self.launch_name(request))

    def write_status(self, status: CycleStatus) -> None:
        name = f"{cycle_prefix(status.shop_id, status.cycle_id)}/status/status.json"
        if self.objects.exists(name):
            previous = CycleStatus.from_dict(self.get_json(name))
            legal = {
                "staged": {"staged", "running", "failed"},
                "running": {"running", "degraded", "validated", "failed"},
                "degraded": {"degraded", "running", "failed"},
                "validated": {"validated", "published", "failed"},
                "published": {"published"},
                "failed": {"failed", "running"},
            }
            if status.state not in legal[previous.state]:
                raise CycleConflict(
                    f"illegal cycle transition: {previous.state} -> {status.state}")
        self.put_json(name, status.as_dict())

    def read_status(self, request: CycleRequest) -> CycleStatus:
        return CycleStatus.from_dict(self.get_json(self.status_name(request)))

    def materialize_input(self, request: CycleRequest, destination: str | Path) -> Path:
        dest = Path(destination)
        prefix = f"{request.prefix}/input/"
        names = self.objects.names(prefix)
        if not names:
            raise CycleNotFound(f"no input objects for {request.cycle_id}")
        for name in names:
            rel = PurePosixPath(name).relative_to(PurePosixPath(prefix.rstrip("/")))
            target = dest.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.objects.get_bytes(name))

        manifest_path = dest / "manifest.json"
        durable_manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        manifest = json.loads(manifest_path.read_text())
        for photo in manifest.get("photos") or []:
            rel = PurePosixPath(str(photo["local_path"]))
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError(f"unsafe manifest local_path: {rel}")
            photo["local_path"] = str(dest.joinpath(*rel.parts))
        manifest["durable_manifest_sha256"] = durable_manifest_sha256
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        return dest

    def published_source_manifest(self, request: CycleRequest) -> dict:
        """Return a manifest whose photo identities survive worker teardown."""
        manifest = self.get_json(f"{request.prefix}/input/manifest.json")
        photos = []
        for raw in manifest.get("photos") or []:
            row = dict(raw)
            source_object = str(row.get("source_object") or "")
            if not source_object or not self.objects.exists(source_object):
                raise CycleNotFound(
                    f"durable source image is missing: {source_object or row.get('filename')}"
                )
            local_path = PurePosixPath(str(row.get("local_path") or ""))
            if local_path.is_absolute() or ".." in local_path.parts:
                raise ValueError(f"unsafe published local_path: {local_path}")
            row["local_path"] = str(local_path)
            row["source_object"] = source_object
            photos.append(row)
        manifest["photos"] = photos
        manifest["cycle_id"] = request.cycle_id
        manifest["shop_id"] = request.shop_id
        manifest["storage_backend"] = self.backend_name
        return manifest

    def write_published_source_manifest(
        self, request: CycleRequest, destination: str | Path,
    ) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_json_bytes(self.published_source_manifest(request)))
        return destination

    def upload_outputs(self, request: CycleRequest, output_dir: str | Path) -> list[str]:
        """Legacy compatibility wrapper; prefer :meth:`publish_outputs`."""
        manifest = self.publish_outputs(request, output_dir)
        return sorted(manifest["artifacts"])

    def publish_outputs(self, request: CycleRequest, output_dir: str | Path) -> dict:
        """Publish content-addressed artifacts, then seal their manifest last.

        Partial blob uploads are harmless: consumers discover a run only through
        the sealed artifact manifest named by ACTIVE.json.
        """
        root = Path(output_dir)
        if not root.is_dir():
            raise FileNotFoundError(f"output directory not found: {root}")
        artifacts: dict[str, dict] = {}
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel == "artifact_manifest.json":
                raise ValueError("artifact_manifest.json is owned by the publisher")
            data = path.read_bytes()
            if not data:
                raise ValueError(f"refusing to publish empty artifact: {rel}")
            digest = hashlib.sha256(data).hexdigest()
            name = f"{request.prefix}/output/blobs/{digest}/{rel}"
            if self.objects.exists(name):
                existing = self.objects.get_bytes(name)
                if hashlib.sha256(existing).hexdigest() != digest:
                    raise CycleConflict(f"content-address collision: {name}")
            else:
                self.objects.put_bytes(
                    name,
                    data,
                    content_type=(mimetypes.guess_type(path.name)[0]
                                  or "application/octet-stream"),
                    if_absent=True,
                )
            artifacts[rel] = {
                "object": name,
                "sha256": digest,
                "bytes": len(data),
                "content_type": (mimetypes.guess_type(path.name)[0]
                                 or "application/octet-stream"),
            }

        request_bytes = _json_bytes(request.as_dict())
        ready = self.ready_payload(request)
        state_path = root / "pipeline_state.json"
        if not state_path.is_file():
            raise ValueError("pipeline_state.json is required to seal artifact identities")
        state = json.loads(state_path.read_text())

        def identity_hash(value) -> str:
            return hashlib.sha256(_json_bytes({"value": value})).hexdigest()

        decisions = state.get("decisions") or []
        evidence = [
            {"lot_id": row.get("lot_id"), "comp": row.get("comp")}
            for row in decisions
        ]
        evidence.append({"external": state.get("external_evidence") or {}})
        manifest = {
            "schema_version": 2,
            "cycle_id": request.cycle_id,
            "shop_id": request.shop_id,
            "listing_id": request.listing_id,
            "cycle_request_sha256": hashlib.sha256(request_bytes).hexdigest(),
            "source_manifest_sha256": ready["manifest_sha256"],
            "model_identity_sha256": identity_hash(state.get("models") or {}),
            "rule_identity_sha256": identity_hash(state.get("standing_rules") or []),
            "evidence_identity_sha256": identity_hash(evidence),
            "decision_identity_sha256": identity_hash(decisions),
            "queue_identity_sha256": identity_hash(state.get("queue") or {}),
            "published_at": utc_now(),
            "artifacts": artifacts,
        }
        manifest_bytes = _json_bytes(manifest)
        manifest_name = self.artifact_manifest_name(request)
        if self.objects.exists(manifest_name):
            existing = self.objects.get_bytes(manifest_name)
            existing_manifest = json.loads(existing)
            # Timestamps may differ on a harmless retry; artifact identity may not.
            if existing_manifest.get("artifacts") != artifacts:
                raise CycleConflict(
                    f"cycle already has a different sealed artifact manifest: "
                    f"{request.cycle_id}"
                )
            return existing_manifest
        self.objects.put_bytes(
            manifest_name,
            manifest_bytes,
            content_type="application/json",
            if_absent=True,
        )
        return manifest

    def activate(self, request: CycleRequest, artifact_manifest: dict) -> None:
        artifacts = artifact_manifest.get("artifacts") or {}
        manifest_name = self.artifact_manifest_name(request)
        if not self.objects.exists(manifest_name):
            raise CycleNotFound("cannot activate an unsealed artifact set")
        manifest_sha256 = hashlib.sha256(
            self.objects.get_bytes(manifest_name)).hexdigest()
        self.put_json(self.active_name(request.shop_id), {
            "cycle_id": request.cycle_id,
            "shop_id": request.shop_id,
            "listing_id": request.listing_id,
            "artifact_manifest": manifest_name,
            "artifact_manifest_sha256": manifest_sha256,
            "artifacts": sorted(artifacts),
        })


def open_cycle_repository() -> CycleRepository | None:
    """Open configured cloud storage, or an explicit local development root."""
    local = os.environ.get("BTF_CYCLE_LOCAL_ROOT")
    if local:
        return CycleRepository(LocalObjectStore(local))
    bucket = os.environ.get("BTF_CYCLE_BUCKET")
    if bucket:
        return CycleRepository(GCSObjectStore(bucket))
    return None
