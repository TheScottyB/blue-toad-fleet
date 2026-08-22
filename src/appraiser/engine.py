"""
src/appraiser/engine.py — Live Vertex AI Triage and Appraisal Engine.

Executes real structured model inference via google-genai on Vertex AI:
- Stage 1: Triage using gemini-3.5-flash-lite / gemini-2.5-flash
- Stage 2: Structured Appraisal using gemini-3.6-flash / gemini-2.5-flash

Includes persistent caching to JSON for reproducibility, cost control,
and seamless offline operation.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Any, Callable

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from src.appraisal import Appraisal, Confidence, Question, QuestionKind, StandingRule
from src.appraiser.images import assert_appraisal_grade, image_mime_type, read_local_image
from src.appraiser.containers import CONTAINER_TYPES, NormalizedBox, crop_to_container
from src.appraiser.routing import TRIAGE_MODEL, APPRAISAL_MODEL, CURATOR_MODEL
from src.appraiser.pricing import (
    PRICE_SCHEMA, PRICING_SYSTEM, build_pricing_prompt,
    sources_from_response, parse_price_payload,
)
from src.appraiser.schema import (
    TRIAGE_SCHEMA, APPRAISAL_SCHEMA, CONTAINER_LOCATION_SCHEMA,
    CONTAINER_DECOMPOSITION_SCHEMA, to_vertex,
)
from src.appraiser.prompts import (
    TRIAGE_SYSTEM,
    APPRAISAL_SYSTEM,
    CONTAINER_LOCATION_SYSTEM,
    CONTAINER_DECOMPOSITION_SYSTEM,
    build_triage_prompt,
    build_appraisal_prompt,
    build_container_location_prompt,
    build_container_decomposition_prompt,
)


class AppraisalEngine:
    def __init__(
        self,
        project: Optional[str] = None,
        location: Optional[str] = None,
        triage_model: str = TRIAGE_MODEL,
        appraisal_model: str = APPRAISAL_MODEL,
    ):
        self.project = project or os.environ.get("GOOGLE_CLOUD_PROJECT", "threebatdrone-prod-420")
        self.location = location or os.environ.get("VERTEX_LOCATION", "global")
        self.triage_model = triage_model
        self.appraisal_model = appraisal_model
        self._client: Optional[Any] = None

    @property
    def client(self):
        if self._client is None and GENAI_AVAILABLE:
            try:
                self._client = genai.Client(
                    vertexai=True,
                    project=self.project,
                    location=self.location,
                )
            except Exception as e:
                print(f"[!] Warning: Could not initialize Vertex AI client: {e}", file=sys.stderr)
                self._client = None
        return self._client

    @staticmethod
    def will_use_cache(cache_path: Optional[Path | str], force_refresh: bool,
                       required_ids: Optional[set[str]] = None,
                       required_fields: Optional[set[str]] = None) -> bool:
        """
        Whether a batch with these arguments will serve from cache.

        Exists so callers can report what actually happened instead of guessing
        from whether the file is on disk — those are different questions, and
        conflating them made a --live run announce itself as cached.

        `required_ids` is the coverage check. "Non-empty list" is not the same
        as "has what I asked for": when the candidate set grew from 214 to 228
        the cache answered yes and fourteen lots were never appraised, one of
        them carrying a live bid. A cache that is missing anything requested is
        not a cache, it is a partial run wearing one.
        """
        if not cache_path or force_refresh:
            return False
        p = Path(cache_path)
        if not p.exists():
            return False
        try:
            cached = json.loads(p.read_text())
        except Exception:
            return False
        if not isinstance(cached, list) or not cached:
            return False
        if required_ids:
            have = {r.get("lot_id") or r.get("photo_id") for r in cached
                    if isinstance(r, dict)}
            if required_ids - have:
                return False
        if required_fields:
            for row in cached:
                if not isinstance(row, dict):
                    return False
                if any(row.get(f) in (None, "") for f in required_fields):
                    return False
        return True

    def triage_photo(
        self,
        photo_id: str,
        caption: str,
        image_bytes: Optional[bytes] = None,
        previous_summary: Optional[str] = None,
    ) -> dict:
        """Execute Stage 1 fast triage on a single photo."""
        if not self.client:
            raise RuntimeError("Vertex AI client is not available.")

        prompt_text = build_triage_prompt(caption=caption, previous_summary=previous_summary)
        contents = [prompt_text]
        if image_bytes:
            contents.append(types.Part.from_bytes(
                data=image_bytes, mime_type=image_mime_type(image_bytes) or "image/jpeg"))

        vertex_schema = to_vertex(TRIAGE_SCHEMA)
        models_to_try = [self.triage_model, "gemini-2.5-flash"]

        last_err = None
        for model in models_to_try:
            try:
                resp = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=TRIAGE_SYSTEM,
                        response_mime_type="application/json",
                        response_schema=vertex_schema,
                        temperature=0.1,
                    ),
                )
                data = json.loads(resp.text)
                data["photo_id"] = photo_id
                data["model_used"] = model
                return data
            except Exception as e:
                last_err = e
                continue

        raise RuntimeError(f"Triage failed for photo {photo_id}: {last_err}")

    def appraise_lot(
        self,
        lot_id: str,
        caption: str,
        image_bytes: Optional[bytes] = None,
        category_hint: Optional[str] = None,
        standing_rules: Optional[list[StandingRule]] = None,
        container_decomposition: Optional[dict] = None,
    ) -> dict:
        """
        Execute Stage 2 detailed structured appraisal on a candidate lot.

        The photo is checked before anything else — before the credential check,
        so that a thumbnail fails as a thumbnail rather than as a missing client
        when this runs offline.
        """
        assert_appraisal_grade(image_bytes, lot_id=lot_id)

        if not self.client:
            raise RuntimeError("Vertex AI client is not available.")

        prompt_text = build_appraisal_prompt(
            caption=caption,
            category_hint=category_hint,
            standing_rules=standing_rules,
            container_decomposition=container_decomposition,
        )
        contents = [prompt_text]
        if image_bytes:
            contents.append(types.Part.from_bytes(
                data=image_bytes, mime_type=image_mime_type(image_bytes) or "image/jpeg"))

        vertex_schema = to_vertex(APPRAISAL_SCHEMA)
        models_to_try = [self.appraisal_model, "gemini-2.5-flash"]

        last_err = None
        for model in models_to_try:
            try:
                resp = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=APPRAISAL_SYSTEM,
                        response_mime_type="application/json",
                        response_schema=vertex_schema,
                        temperature=0.1,
                    ),
                )
                data = json.loads(resp.text)
                data["lot_id"] = lot_id
                data["model_used"] = model
                if container_decomposition and container_decomposition.get("is_container_lot"):
                    # This is evidence supplied to the appraisal, not model output
                    # from APPRAISAL_SCHEMA, so preserve it beside the response.
                    data["container_decomposition"] = container_decomposition
                return data
            except Exception as e:
                last_err = e
                continue

        raise RuntimeError(f"Appraisal failed for lot {lot_id}: {last_err}")

    def locate_container(
        self,
        lot_id: str,
        caption: str,
        image_bytes: Optional[bytes] = None,
        spatial_context: Optional[str] = None,
    ) -> dict:
        """Find one defensible physical inclusion boundary in the full photo."""
        assert_appraisal_grade(image_bytes, lot_id=lot_id)
        if not self.client:
            raise RuntimeError("Vertex AI client is not available.")

        contents = [build_container_location_prompt(caption, spatial_context)]
        contents.append(types.Part.from_bytes(
            data=image_bytes, mime_type=image_mime_type(image_bytes) or "image/jpeg"))
        last_err = None
        for model in [self.appraisal_model, "gemini-2.5-flash"]:
            try:
                resp = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=CONTAINER_LOCATION_SYSTEM,
                        response_mime_type="application/json",
                        response_schema=to_vertex(CONTAINER_LOCATION_SCHEMA),
                        temperature=0.0,
                    ),
                )
                data = json.loads(resp.text)
                if not data.get("is_container_lot"):
                    data.update(container_type="none", boundary=None)
                elif NormalizedBox.from_mapping(data.get("boundary")) is None:
                    raise ValueError("model returned an invalid container boundary")
                elif data.get("container_type") not in set(CONTAINER_TYPES) - {"none"}:
                    raise ValueError("model returned an invalid container type")
                data["lot_id"] = lot_id
                data["model_used"] = model
                return data
            except Exception as e:
                last_err = e
        raise RuntimeError(f"Container location failed for lot {lot_id}: {last_err}")

    def decompose_container(
        self,
        lot_id: str,
        caption: str,
        image_bytes: Optional[bytes] = None,
        spatial_boundary: Optional[dict | NormalizedBox] = None,
        spatial_context: Optional[str] = None,
        container_type: Optional[str] = None,
    ) -> dict:
        """Crop one container out of room clutter, then itemize only that crop.

        ``spatial_boundary`` is the handoff from a Spatial Room Graph when one
        exists.  With no handoff, the locator pass derives it from the photo.
        The return value describes one auction lot; its ``contents`` are not
        independently priceable lots.
        """
        assert_appraisal_grade(image_bytes, lot_id=lot_id)

        supplied = (spatial_boundary if isinstance(spatial_boundary, NormalizedBox)
                    else NormalizedBox.from_mapping(spatial_boundary))
        if spatial_boundary is not None and supplied is None:
            raise ValueError(f"{lot_id}: supplied spatial boundary is invalid")
        if (supplied is not None and container_type is not None
                and container_type not in set(CONTAINER_TYPES) - {"none"}):
            raise ValueError(f"{lot_id}: supplied container type is invalid")

        if supplied is None:
            location = self.locate_container(
                lot_id=lot_id,
                caption=caption,
                image_bytes=image_bytes,
                spatial_context=spatial_context,
            )
            if not location.get("is_container_lot"):
                return {
                    **location,
                    "contents": [],
                    "background_exclusions": [],
                    "hidden_extent": "none",
                    "questions": [],
                }
            boundary = NormalizedBox.from_mapping(location["boundary"])
            resolved_type = location.get("container_type") or "other"
        else:
            boundary = supplied
            resolved_type = container_type or "other"
            location = {
                "lot_id": lot_id,
                "is_container_lot": True,
                "container_type": resolved_type,
                "boundary": boundary.as_dict(),
                "confidence": "high",
                "reason": spatial_context or "Boundary supplied by Spatial Room Graph.",
                "model_used": "spatial-room-graph",
            }

        cropped = crop_to_container(image_bytes, boundary)
        if not self.client:
            raise RuntimeError("Vertex AI client is not available.")

        contents = [build_container_decomposition_prompt(caption, resolved_type)]
        contents.append(types.Part.from_bytes(data=cropped, mime_type="image/jpeg"))
        last_err = None
        for model in [self.appraisal_model, "gemini-2.5-flash"]:
            try:
                resp = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=CONTAINER_DECOMPOSITION_SYSTEM,
                        response_mime_type="application/json",
                        response_schema=to_vertex(CONTAINER_DECOMPOSITION_SCHEMA),
                        temperature=0.1,
                    ),
                )
                data = json.loads(resp.text)
                return {
                    **location,
                    **data,
                    "lot_id": lot_id,
                    "is_container_lot": True,
                    "container_type": resolved_type,
                    "boundary": boundary.as_dict(),
                    "boundary_model_used": location.get("model_used"),
                    "model_used": model,
                }
            except Exception as e:
                last_err = e
        raise RuntimeError(f"Container decomposition failed for lot {lot_id}: {last_err}")

    def write_curator_voice(self, prompt: str, system: str = "") -> str:
        """
        Prose for the Gate console's pitch banner, written by Gemma.

        Free text on purpose — this is the one call in the system with no
        response schema, because it is the one call whose output is not a
        decision. Anything it says is checked against the sheet's own figures
        before it reaches the owner; see src/gate/pitch.py.
        """
        if not self.client:
            raise RuntimeError("Vertex AI client is not available.")

        cfg = types.GenerateContentConfig(temperature=0.4, max_output_tokens=300)
        if system:
            cfg.system_instruction = system
        resp = self.client.models.generate_content(
            model=CURATOR_MODEL, contents=[prompt], config=cfg)
        return (resp.text or "").strip()

    def price_lot_grounded(self, identification: str, category: str = ""):
        """
        One grounded price. Two calls, because Vertex will not give both at once.

        With a response_schema attached, grounding_metadata comes back with zero
        grounding_chunks — the search still runs and the queries are recorded,
        but the retrieved pages are not returned. Drop the schema and the same
        call yields six. Verified on the live endpoint both ways.

        Citations are not optional here: an uncited price is the model's opinion,
        and opinions are what this system exists not to bid on. So the grounded
        call runs free-text and keeps its chunks, and a second call — cheap, no
        tools, no search — reads the numbers out of that text into the schema.
        The second call sees only the first's prose, so it cannot introduce a
        figure the grounded pass did not find.
        """
        if not self.client:
            raise RuntimeError("Vertex AI client is not available.")

        grounded = self.client.models.generate_content(
            model=self.appraisal_model,
            contents=[build_pricing_prompt(identification, category)],
            config=types.GenerateContentConfig(
                system_instruction=PRICING_SYSTEM,
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.2,
            ),
        )
        prose = (grounded.text or "").strip()
        sources = sources_from_response(grounded)
        if not prose:
            return None

        extracted = self.client.models.generate_content(
            model=self.appraisal_model,
            contents=["Read the completed-sale figures out of this research note. "
                      "Report only what it states; invent nothing.\n\n" + prose],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=to_vertex(PRICE_SCHEMA),
                temperature=0.0,
            ),
        )
        try:
            payload = json.loads(extracted.text)
        except Exception:
            return None
        return parse_price_payload(payload, sources)

    def run_triage_batch(
        self,
        photos: list[dict],
        cache_path: Optional[Path | str] = None,
        force_refresh: bool = False,
        max_workers: int = 4,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[dict]:
        """
        Batch triage across a photo drop.
        Loads from cache_path if present unless force_refresh is True.
        """
        if self.will_use_cache(cache_path, force_refresh):
            return json.loads(Path(cache_path).read_text())

        results = []
        if not self.client:
            raise RuntimeError("Vertex AI client not available and no valid cache found.")

        total = len(photos)
        completed = 0

        # Execute sequentially or with a worker pool
        for idx, item in enumerate(photos):
            photo_id = item["photo_id"]
            caption = item.get("caption", "")
            img_bytes = read_local_image(item.get("local_path"))
            prev_sum = results[-1].get("summary") if results else None

            try:
                res = self.triage_photo(
                    photo_id=photo_id,
                    caption=caption,
                    image_bytes=img_bytes,
                    previous_summary=prev_sum,
                )
            except Exception as e:
                res = {
                    "photo_id": photo_id,
                    "is_lot": True,
                    "same_lot_as_previous": False,
                    "category": "other",
                    "summary": caption[:40] if caption else "Uncaptioned item",
                    "fit_score": 0.20,
                    "worth_appraising": False,
                    "needs_decomposition": False,
                    "error": str(e),
                }

            results.append(res)
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

        if cache_path:
            p = Path(cache_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(results, indent=2))

        return results

    def run_appraisal_batch(
        self,
        candidates: list[dict],
        standing_rules: Optional[list[StandingRule]] = None,
        cache_path: Optional[Path | str] = None,
        force_refresh: bool = False,
        max_workers: int = 4,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[dict]:
        """
        Batch appraisal on survivor candidate lots.
        Loads from cache_path if present unless force_refresh is True.
        """
        required = {c["lot_id"] for c in candidates if c.get("lot_id")}
        if self.will_use_cache(cache_path, force_refresh, required_ids=required):
            return json.loads(Path(cache_path).read_text())

        results = []
        if not self.client:
            raise RuntimeError(
                "Vertex AI client not available and no cache covering all "
                f"{len(required)} requested lot(s).")

        total = len(candidates)
        completed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_lot = {}
            for item in candidates:
                lot_id = item["lot_id"]
                caption = item.get("caption", "")
                cat_hint = item.get("category_hint")
                img_bytes = read_local_image(item.get("local_path"))
                kwargs = {
                    "lot_id": lot_id,
                    "caption": caption,
                    "image_bytes": img_bytes,
                    "category_hint": cat_hint,
                    "standing_rules": standing_rules,
                }
                if item.get("container_decomposition"):
                    kwargs["container_decomposition"] = item["container_decomposition"]
                f = executor.submit(self.appraise_lot, **kwargs)
                future_to_lot[f] = lot_id

            for f in as_completed(future_to_lot):
                lot_id = future_to_lot[f]
                try:
                    res = f.result()
                except Exception as e:
                    res = {
                        "lot_id": lot_id,
                        "identification": f"Lot {lot_id}",
                        "maker": None,
                        "period": None,
                        "marks_observed": [],
                        "category": "other",
                        "condition_notes": ["Uninspected due to evaluation error"],
                        "condition_penalty": 0.0,
                        "fit_score": 0.5,
                        "confidence": "low",
                        "value_magnitude_hint": 0.0,
                        "questions": [],
                        "is_container": False,
                        "contents": [],
                        "error": str(e),
                    }
                results.append(res)
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

        # Sort results by lot_id for deterministic output
        results.sort(key=lambda r: r.get("lot_id", ""))

        if cache_path:
            p = Path(cache_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(results, indent=2))

        return results

    def run_decomposition_batch(
        self,
        candidates: list[dict],
        cache_path: Optional[Path | str] = None,
        force_refresh: bool = False,
        max_workers: int = 4,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[dict]:
        """Spatially isolate and itemize every selected container candidate."""
        if not candidates:
            return []
        required = {c["lot_id"] for c in candidates if c.get("lot_id")}
        if self.will_use_cache(cache_path, force_refresh, required_ids=required):
            return json.loads(Path(cache_path).read_text())
        if not self.client:
            raise RuntimeError(
                "Vertex AI client not available and no cache covering all "
                f"{len(required)} requested container lot(s).")

        results = []
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_lot = {}
            for item in candidates:
                kwargs = {
                    "lot_id": item["lot_id"],
                    "caption": item.get("caption", ""),
                    "image_bytes": read_local_image(item.get("local_path")),
                    "spatial_context": item.get("spatial_context"),
                }
                if item.get("spatial_boundary") is not None:
                    kwargs["spatial_boundary"] = item["spatial_boundary"]
                if item.get("container_type"):
                    kwargs["container_type"] = item["container_type"]
                future = executor.submit(self.decompose_container, **kwargs)
                future_to_lot[future] = item["lot_id"]

            for future in as_completed(future_to_lot):
                lot_id = future_to_lot[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = {
                        "lot_id": lot_id,
                        "is_container_lot": False,
                        "container_type": "none",
                        "boundary": None,
                        "contents": [],
                        "background_exclusions": [],
                        "hidden_extent": "unknown",
                        "questions": [],
                        "error": str(e),
                    }
                results.append(result)
                completed += 1
                if progress_callback:
                    progress_callback(completed, len(candidates))

        results.sort(key=lambda r: r.get("lot_id", ""))
        if cache_path:
            path = Path(cache_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(results, indent=2))
        return results

    @staticmethod
    def parse_appraisal_to_domain(
        data: dict,
        category_override: Optional[str] = None,
    ) -> tuple[Appraisal, list[Question]]:
        """Convert a raw Vertex JSON appraisal response into domain dataclasses."""
        lot_id = data.get("lot_id", "UNKNOWN")
        category = category_override or data.get("category", "other")
        identification = data.get("identification", "")
        conf_str = data.get("confidence", "medium").lower()

        try:
            confidence = Confidence(conf_str)
        except ValueError:
            confidence = Confidence.MEDIUM

        est_val = float(data.get("value_magnitude_hint") or 0.0)

        appraisal = Appraisal(
            lot_id=lot_id,
            category=category,
            identification=identification,
            attributes={
                "maker": data.get("maker") or "Unknown",
                "period": data.get("period") or "Unknown",
                "condition_penalty": str(data.get("condition_penalty", 0.0)),
            },
            confidence=confidence,
            est_value_hint=est_val,
        )

        questions = []
        for q_data in data.get("questions", []):
            try:
                kind = QuestionKind(q_data.get("kind", "mark").lower())
            except ValueError:
                kind = QuestionKind.MARK

            questions.append(
                Question(
                    kind=kind,
                    category=category,
                    prompt=q_data.get("prompt", ""),
                    lot_ids=(lot_id,),
                    value_at_stake=est_val,
                    confidence_gap=float(q_data.get("confidence_gap", 0.5)),
                    wants_photo=bool(q_data.get("wants_photo", False)),
                )
            )

        return appraisal, questions
