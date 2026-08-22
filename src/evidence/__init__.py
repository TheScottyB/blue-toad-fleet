"""Typed external evidence records."""

from src.evidence.model import AbsorptionEvidence, load_absorption_evidence
from src.evidence.telemetry import StageRecord, UsageRecord, UsageTelemetry

__all__ = [
    "AbsorptionEvidence", "load_absorption_evidence",
    "StageRecord", "UsageRecord", "UsageTelemetry",
]
