"""Batch grounded pricing that preserves evidence and distinguishes refusal from outage."""

from __future__ import annotations

import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Callable

from src.appraiser.engine import AppraisalEngine
from src.appraiser.pricing import (
    MIN_CALLS, MIN_SOLD_COMPS, median_price, price_is_usable, usable_sources,
)
from src.bidmath import Confidence as BidConfidence
from src.appraiser.routing import APPRAISAL_MODEL

PRICING_INPUT_VERSION = "grounded-price-v1"


def pricing_fingerprint(lot: dict) -> str:
    payload = {
        "version": PRICING_INPUT_VERSION,
        "lot_id": lot.get("lot_id"),
        "identification": lot.get("identification") or "",
        "category": lot.get("category") or "",
        "fit_score": lot.get("fit_score"),
    }
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def price_one_grounded(
    lot: dict,
    *,
    engine_factory: Callable[[], AppraisalEngine] = AppraisalEngine,
) -> dict:
    """Take three independent grounded samples for one identified lot."""
    engine = engine_factory()
    started_at = datetime.now(timezone.utc).isoformat()
    samples = []
    errors = []
    for _ in range(MIN_CALLS):
        try:
            samples.append(engine.price_lot_grounded(
                lot.get("identification") or "",
                lot.get("category") or "",
            ))
        except Exception as exc:
            samples.append(None)
            errors.append(f"{type(exc).__name__}: {exc}"[:500])

    merged = median_price(samples)
    return {
        "attempt_id": uuid.uuid4().hex,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "method": "vertex_google_search_grounding",
        "model": APPRAISAL_MODEL,
        "lot_id": lot["lot_id"],
        "identification": lot.get("identification") or "",
        "category": lot.get("category") or "other",
        "fit_score": lot.get("fit_score"),
        "input_sha256": pricing_fingerprint(lot),
        "attempt_complete": not errors,
        "usable": bool(price_is_usable(samples)),
        "low": merged.low if merged else None,
        "high": merged.high if merged else None,
        "sold_comp_count": merged.sold_comp_count if merged else 0,
        "sources": merged.sources if merged else [],
        "samples": [
            None if sample is None else {
                "low": sample.low,
                "high": sample.high,
                "sold_comp_count": sample.sold_comp_count,
                "sources": sample.sources,
            }
            for sample in samples
        ],
        "errors": errors,
    }


def _atomic_json(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(rows, indent=2) + "\n")
    tmp.replace(path)


def attempt_history_path(path: str | Path) -> Path:
    path = Path(path)
    return path.with_name(f"{path.stem}_attempts.json")


def _append_attempt(path: Path, row: dict) -> None:
    history_path = attempt_history_path(path)
    try:
        history = json.loads(history_path.read_text())
        if not isinstance(history, list):
            history = []
    except (OSError, json.JSONDecodeError):
        history = []
    history.append(row)
    _atomic_json(history_path, history)


class GroundedPricingPipeline:
    """Accept appraisals one at a time and research them concurrently."""

    def __init__(
        self,
        cache_path: str | Path,
        *,
        min_fit: float = 0.70,
        workers: int = 6,
        excluded_lot_ids: set[str] | None = None,
        engine_factory: Callable[[], AppraisalEngine] = AppraisalEngine,
        progress_callback=None,
    ):
        self.path = Path(cache_path)
        self.min_fit = min_fit
        self.excluded_lot_ids = excluded_lot_ids or set()
        self.engine_factory = engine_factory
        self.progress_callback = progress_callback
        self._executor = ThreadPoolExecutor(max_workers=max(1, workers))
        self._lock = Lock()
        self._lots: dict[str, dict] = {}
        self._results: dict[str, dict] = {}
        self._futures = {}
        self._errors: list[BaseException] = []
        self._finished = False
        try:
            self._cached = {
                row["lot_id"]: row for row in json.loads(self.path.read_text())
            }
        except Exception:
            self._cached = {}

    def submit(self, lot: dict) -> bool:
        """Queue one qualifying appraisal without waiting for other lots."""
        if self._finished:
            raise RuntimeError("grounded pricing pipeline is already finished")
        lot_id = lot.get("lot_id")
        if (
            not lot_id
            or lot_id in self._lots
            or lot_id in self.excluded_lot_ids
            or lot.get("error")
            or float(lot.get("fit_score") or 0) < self.min_fit
        ):
            return False

        self._lots[lot_id] = lot
        cached = self._cached.get(lot_id)
        if (
            cached
            and cached.get("attempt_complete")
            and cached.get("input_sha256") == pricing_fingerprint(lot)
        ):
            self._results[lot_id] = cached
            return True

        future = self._executor.submit(
            price_one_grounded, lot, engine_factory=self.engine_factory,
        )
        self._futures[future] = lot_id
        future.add_done_callback(self._record_result)
        return True

    def _record_result(self, future) -> None:
        lot_id = self._futures[future]
        try:
            row = future.result()
        except BaseException as exc:
            with self._lock:
                self._errors.append(exc)
            return

        with self._lock:
            self._results[lot_id] = row
            _append_attempt(self.path, row)
            # Keep unrelated old rows during a live run AND at finish(). A
            # cycle only re-judges the lots it submits; rows it never touched
            # are evidence, not leftovers — trimming them erased the operator's
            # alpha-lot comps on 2026-08-29 and dropped his kept lots from the
            # sheet downstream.
            snapshot = {**self._cached, **self._results}
            _atomic_json(self.path, [snapshot[key] for key in sorted(snapshot)])
            if self.progress_callback:
                self.progress_callback(len(self._results), len(self._lots))

    def finish(self) -> list[dict]:
        """Wait for queued research and return the current cycle's rows."""
        if not self._finished:
            self._executor.shutdown(wait=True)
            self._finished = True
        if self._errors:
            raise self._errors[0]
        ordered_lots = sorted(
            self._lots.values(),
            key=lambda lot: (-float(lot.get("fit_score") or 0), str(lot["lot_id"])),
        )
        rows = [self._results[lot["lot_id"]] for lot in ordered_lots]
        snapshot = {**self._cached, **self._results}
        _atomic_json(self.path, [snapshot[key] for key in sorted(snapshot)])
        return rows

    def shutdown(self) -> None:
        """Release workers after an upstream failure."""
        if not self._finished:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._finished = True


def run_grounded_pricing_batch(
    appraisals: list[dict],
    cache_path: str | Path,
    *,
    min_fit: float = 0.70,
    workers: int = 6,
    limit: int = 0,
    excluded_lot_ids: set[str] | None = None,
    engine_factory: Callable[[], AppraisalEngine] = AppraisalEngine,
    progress_callback=None,
) -> list[dict]:
    """Price every qualifying appraisal, reusing only fingerprint-matched attempts."""
    path = Path(cache_path)
    excluded = excluded_lot_ids or set()
    candidates = [
        lot for lot in appraisals
        if lot.get("lot_id") not in excluded
        and not lot.get("error")
        and float(lot.get("fit_score") or 0) >= min_fit
    ]
    candidates.sort(key=lambda lot: (-float(lot.get("fit_score") or 0),
                                     str(lot.get("lot_id") or "")))
    cached = {}
    if path.is_file():
        try:
            cached = {row["lot_id"]: row for row in json.loads(path.read_text())}
        except Exception:
            cached = {}
    reusable = {
        lot["lot_id"]: cached[lot["lot_id"]]
        for lot in candidates
        if lot["lot_id"] in cached
        and cached[lot["lot_id"]].get("attempt_complete")
        and cached[lot["lot_id"]].get("input_sha256") == pricing_fingerprint(lot)
    }
    todo = [lot for lot in candidates if lot["lot_id"] not in reusable]
    if limit:
        # Limit new spend, not the cache view. Repeated `--limit 5` runs should
        # add five lots at a time rather than deleting the five just completed.
        todo = todo[:limit]
    selected_ids = set(reusable) | {lot["lot_id"] for lot in todo}
    results = dict(reusable)

    if todo:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(
                    price_one_grounded, lot, engine_factory=engine_factory,
                ): lot["lot_id"]
                for lot in todo
            }
            completed = len(reusable)
            for future in as_completed(futures):
                lot_id = futures[future]
                results[lot_id] = future.result()
                _append_attempt(path, results[lot_id])
                completed += 1
                ordered = [results[k] for k in sorted(results)]
                _atomic_json(path, ordered)
                if progress_callback:
                    progress_callback(completed, len(selected_ids))

    ordered = [results[lot["lot_id"]] for lot in candidates
               if lot["lot_id"] in selected_ids]
    _atomic_json(path, ordered)
    return ordered


def grounded_reference_comps(rows: list[dict]) -> dict[str, dict]:
    """Convert only usable evidence rows into the pipeline's comp seam."""
    out = {}
    for row in rows:
        sources = usable_sources(row.get("sources") or [])
        try:
            low = float(row["low"])
            high = float(row["high"])
            sold_count = int(row.get("sold_comp_count") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if (not row.get("usable") or row.get("attempt_complete") is not True
                or row.get("errors") or low <= 0 or high < low
                or sold_count < MIN_SOLD_COMPS or not sources):
            continue
        out[row["lot_id"]] = {
            "low": low,
            "high": high,
            "sources": sold_count,
            "conf": BidConfidence.MEDIUM,
            "cat": row.get("category") or "other",
            "desc": row.get("identification") or row["lot_id"],
            "provenance": "grounded_search",
            "citations": sources,
        }
    return out


def grounded_status_reason(row: dict | None) -> str:
    """Explain why a lot still has no usable grounded price."""
    if not row:
        return "pending deep comps — verified sold-price evidence is still needed"
    if row.get("attempt_complete") is False or row.get("errors"):
        return "deep comps retry pending — the pricing research was interrupted"
    return "needs deeper comps — initial sold-price evidence was inconclusive"
