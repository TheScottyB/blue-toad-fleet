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
from src.appraiser.images import assert_appraisal_grade, read_local_image
from src.appraiser.routing import TRIAGE_MODEL, APPRAISAL_MODEL
from src.appraiser.schema import TRIAGE_SCHEMA, APPRAISAL_SCHEMA, to_vertex
from src.appraiser.prompts import (
    TRIAGE_SYSTEM,
    APPRAISAL_SYSTEM,
    build_triage_prompt,
    build_appraisal_prompt,
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
    def will_use_cache(cache_path: Optional[Path | str], force_refresh: bool) -> bool:
        """
        Whether a batch with these arguments will serve from cache.

        Exists so callers can report what actually happened instead of guessing
        from whether the file is on disk — those are different questions, and
        conflating them made a --live run announce itself as cached.
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
        return isinstance(cached, list) and len(cached) > 0

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
            contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))

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
        )
        contents = [prompt_text]
        if image_bytes:
            contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))

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
                return data
            except Exception as e:
                last_err = e
                continue

        raise RuntimeError(f"Appraisal failed for lot {lot_id}: {last_err}")

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
        if self.will_use_cache(cache_path, force_refresh):
            return json.loads(Path(cache_path).read_text())

        results = []
        if not self.client:
            raise RuntimeError("Vertex AI client not available and no valid cache found.")

        total = len(candidates)
        completed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_lot = {}
            for item in candidates:
                lot_id = item["lot_id"]
                caption = item.get("caption", "")
                cat_hint = item.get("category_hint")
                img_bytes = read_local_image(item.get("local_path"))

                f = executor.submit(
                    self.appraise_lot,
                    lot_id=lot_id,
                    caption=caption,
                    image_bytes=img_bytes,
                    category_hint=cat_hint,
                    standing_rules=standing_rules,
                )
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
