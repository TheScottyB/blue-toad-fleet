"""
Grounded pricing — the one place this system is allowed to name a number.

Everything upstream refuses to. That was correct while there was nothing to
ground a price in: a dollar figure inferred from a photograph is a guess wearing
a number, and one bad row in sixty costs trust in the whole sheet. Search
grounding does not lower that standard, it just makes it reachable — a price
still has to trace to sold comparables somebody can go and look at.

Two failure modes were observed on the live endpoint before any of this was
built, and the design is shaped around them:

  Asked the same lot twice, the model answered $40-$60 and $40-$147.50. A single
  call is not a price, it is a sample. So: three independent calls, median each
  bound, and refuse the lot when they disagree beyond MAX_SPREAD_RATIO.

  Asked to report its sources into a schema field, it produced bare domains —
  "https://www.bssauction.com" — which cite nothing and cannot be checked. So
  citations are read from grounding_metadata, which the model does not author,
  and a bare domain is not accepted as evidence.

A refused price is not a failure. It is the lot going to the operator unpriced,
which is the same thing the system has always done when it could not know.
"""

from dataclasses import dataclass, field
from statistics import median
from urllib.parse import urlparse

# Below this many realised sales the range is an anecdote, not a comp set.
MIN_SOLD_COMPS = 2

# How far the three calls may disagree on the top of the range before the lot is
# refused. 2.0 would have passed the $60-vs-$147.50 split that prompted this.
MAX_SPREAD_RATIO = 1.6

MIN_CALLS = 3


@dataclass
class GroundedPrice:
    low: float
    high: float
    sold_comp_count: int = 0
    sources: list[str] = field(default_factory=list)


def usable_sources(urls) -> list[str]:
    """
    Citations that can actually be followed back to a sale.

    A bare domain is not one. When the model was asked to fill in a `sources`
    field it returned "https://www.bssauction.com" — true, useless, and
    indistinguishable from evidence at a glance. A citation needs a path.
    """
    out = []
    for u in urls or []:
        if not isinstance(u, str) or not u.strip():
            continue
        parsed = urlparse(u.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        if parsed.path.strip("/") == "" and not parsed.query:
            continue          # domain only
        out.append(u.strip())
    return out


def median_price(results) -> GroundedPrice | None:
    """
    One price from several independent calls.

    Median rather than mean: a single outlier should be outvoted, not averaged
    in. Sources are unioned because each call may have found different sales and
    all of them are evidence.
    """
    rows = [r for r in results if r is not None]
    if not rows:
        return None
    merged = []
    for r in rows:
        merged.extend(usable_sources(r.sources))
    return GroundedPrice(
        low=float(median([r.low for r in rows])),
        high=float(median([r.high for r in rows])),
        sold_comp_count=int(median([r.sold_comp_count for r in rows])),
        sources=sorted(set(merged)),
    )


def price_is_usable(results) -> bool:
    """
    Whether these calls agree well enough to put money behind.

    Every refusal here sends the lot to the operator unpriced rather than
    bidding on a number nobody can defend. That is the cheaper mistake: an
    unpriced lot costs a minute of his attention, a wrong one costs real money
    and the credibility of every other row on the sheet.
    """
    rows = [r for r in results if r is not None]
    if len(rows) < MIN_CALLS:
        return False
    if any(r.low <= 0 or r.high <= 0 or r.low > r.high for r in rows):
        return False
    if median([r.sold_comp_count for r in rows]) < MIN_SOLD_COMPS:
        return False
    if not any(usable_sources(r.sources) for r in rows):
        return False

    highs = [r.high for r in rows]
    if min(highs) <= 0 or max(highs) / min(highs) > MAX_SPREAD_RATIO:
        return False
    return True
