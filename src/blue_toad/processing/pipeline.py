"""Pipeline entry: run_puzzle wraps the core puzzle_loop and returns PuzzleState."""

from __future__ import annotations

from collections.abc import Callable

from src.blue_toad.processing.models import PhotoPiece, PuzzleState
from src.blue_toad.processing.puzzle import puzzle_loop


def run_puzzle(
    pieces: list[PhotoPiece],
    *,
    proposal_edges: set[frozenset[str]],
    identify: Callable[[tuple[str, ...]], dict[str, tuple[str, str]]],
    max_rounds: int = 3,
) -> PuzzleState:
    return puzzle_loop(
        pieces,
        proposal_edges=proposal_edges,
        identify=identify,
        max_rounds=max_rounds,
    )
