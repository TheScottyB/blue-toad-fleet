"""Shop labor to process a won lot. Deterministic; no model call."""

from src.bidmath import LaborAspect

# Exact category strings — REFERENCE_COMPS cats plus the appraiser enum.
_SHELF = {
    "jewelry",
    "dinnerware / pottery",
}

_RESEARCH = {
    "phonograph / records",
    "books",
    "book",
    "silver",
    "stoneware",
    "railroad",
    "railroadiana",
    "coins",
    "paper",
    "ephemera",
}

# Most live lots sit in the constrained enum ("other", "vintage toys").
# Identification has to carry the aspect when category cannot.
_SHELF_NEEDLES = ("jewelry", "dinnerware")
_RESEARCH_NEEDLES = (
    "hallmarked", "hallmark on", "maker's mark", "makers mark", "uncertified",
    "phonograph", "edison", "ephemera",
)


def labor_aspect(
    category: str,
    *,
    is_container: bool = False,
    contents: tuple[str, ...] = (),
    identification: str = "",
) -> LaborAspect:
    cat = (category or "").casefold().strip()
    blob = f"{cat} {identification}".casefold()
    if cat in _SHELF or any(k in blob for k in _SHELF_NEEDLES):
        return LaborAspect.SHELF
    if cat in _RESEARCH:
        return LaborAspect.RESEARCH
    if is_container and len(contents) >= 3:
        return LaborAspect.RESEARCH
    if any(k in blob for k in _RESEARCH_NEEDLES):
        return LaborAspect.RESEARCH
    return LaborAspect.LIST
