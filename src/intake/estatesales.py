"""
src/intake/estatesales.py — Offline Cacher and Intake for EstateSales.NET listings.

Handles extracting structured sale metadata and 1200x900 appraisal-grade images
from EstateSales.NET listings (such as cross-listed Blue Toad Fleet auctions).
"""

from __future__ import annotations

import json
import re
import ssl
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.appraiser.images import (MIN_APPRAISAL_EDGE, image_dimensions,
                                  is_appraisal_grade)
from src.intake.manifest import clean_caption

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)

# Regex to extract sale ID from various EstateSales.NET URL forms or bare numbers
_SALE_ID_URL_PATTERN = re.compile(
    r"(?:estatesales\.net/(?:[^/]+/){3}|/sale/|/sales/|^)(\d{5,10})(?:[/?#]|$)",
    re.IGNORECASE,
)

# Regex to find embedded NgRx state in script tags
_NGRX_STATE_PATTERN = re.compile(
    r'<script[^>]*>\s*(\{"NGRX_STATE".*?\})\s*</script>', re.DOTALL
)

# Regex for CDN photo URLs
_CDN_PHOTO_PATTERN = re.compile(
    r"https?://picturescdn\.estatesales\.net/(\d+)/([^/]+)/([a-f0-9\-]+\.jpg)",
    re.IGNORECASE,
)


@dataclass
class EstateSalesPicture:
    """One photo record from EstateSales.NET."""
    id: str
    sale_id: str
    picture_order: int
    url: str
    thumbnail_url: str = ""
    width: int = 0
    height: int = 0
    thumbnail_width: int = 0
    thumbnail_height: int = 0
    description: str = ""
    is_featured: bool = False

    @property
    def has_description(self) -> bool:
        return bool(self.description.strip())


@dataclass
class EstateSalesListing:
    """Complete metadata and photo list for an EstateSales.NET sale."""
    sale_id: str
    url: str
    name: str
    seller: dict[str, Any] = field(default_factory=dict)
    location: dict[str, Any] = field(default_factory=dict)
    dates: list[dict[str, Any]] = field(default_factory=list)
    description: str = ""
    picture_count: int = 0
    pictures: list[EstateSalesPicture] = field(default_factory=list)
    terms: str = ""
    auction_url: str = ""

    @property
    def captioned_count(self) -> int:
        return sum(1 for p in self.pictures if p.has_description)


def extract_sale_id(url_or_id: str) -> str | None:
    """Extract numeric sale ID from a URL or raw ID string."""
    cleaned = (url_or_id or "").strip()
    if cleaned.isdigit():
        return cleaned
    m = _SALE_ID_URL_PATTERN.search(cleaned)
    return m.group(1) if m else None


def resolve_sale_url(url_or_id: str) -> str:
    """Resolve an input URL or numeric sale ID to a full listing URL."""
    cleaned = (url_or_id or "").strip()
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned

    sale_id = extract_sale_id(cleaned)
    if not sale_id:
        return cleaned

    if sale_id == "5042877":
        return f"https://www.estatesales.net/WI/Genoa-City/53128/{sale_id}"

    return f"https://www.estatesales.net/sale/{sale_id}"


def fetch_listing_html(url: str, timeout: float = 25.0) -> str:
    """Fetch listing HTML from EstateSales.NET with standard browser headers."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_listing_page(html: str, fallback_sale_id: str | None = None, source_url: str = "") -> EstateSalesListing:
    """
    Parse an EstateSales.NET HTML page, extracting NgRx state or fallback CDN photos.
    """
    state = None
    ngrx_match = _NGRX_STATE_PATTERN.search(html)
    if ngrx_match:
        try:
            state = json.loads(ngrx_match.group(1)).get("NGRX_STATE")
        except Exception:
            state = None

    if state:
        return _parse_from_ngrx_state(state, fallback_sale_id=fallback_sale_id, source_url=source_url)

    return _parse_from_html_fallback(html, fallback_sale_id=fallback_sale_id, source_url=source_url)


def _parse_from_ngrx_state(
    state: dict[str, Any], fallback_sale_id: str | None = None, source_url: str = ""
) -> EstateSalesListing:
    """Extract listing information from NgRx state structure."""
    # Locate sale view state (e.g. feature.traditionalSaleViewState or similar)
    sale_view = (
        state.get("feature.traditionalSaleViewState")
        or state.get("feature.saleViewState")
        or {}
    )

    entities = sale_view.get("entitiesById", {})
    active_id = str(sale_view.get("activeId") or fallback_sale_id or "")

    entity = entities.get(active_id)
    if not entity and entities:
        # Pick the first entity if active_id not specifically keyed
        first_key = next(iter(entities.keys()))
        entity = entities[first_key]
        active_id = str(first_key)

    if not entity:
        # Try finding in other state slices
        for k, v in state.items():
            if isinstance(v, dict) and "entitiesById" in v:
                entities = v["entitiesById"]
                if entities:
                    first_key = next(iter(entities.keys()))
                    entity = entities[first_key]
                    active_id = str(first_key)
                    break

    if not entity:
        return _parse_from_html_fallback("", fallback_sale_id=active_id or fallback_sale_id, source_url=source_url)

    sale_id = str(entity.get("saleId") or entity.get("id") or active_id)
    name = entity.get("name") or "Estate Sale"
    raw_desc = entity.get("plainTextDescription") or entity.get("htmlDescription") or ""
    terms = entity.get("terms") or ""
    auction_url = entity.get("auctionUrl") or ""

    # Parse seller
    seller_raw = entity.get("seller") or {}
    seller = {
        "name": seller_raw.get("name", ""),
        "phone": seller_raw.get("primaryPhone", ""),
        "website": seller_raw.get("websiteUrl", ""),
        "org_id": seller_raw.get("orgId"),
        "is_org": seller_raw.get("isOrg", False),
    }

    # Parse location
    loc_raw = entity.get("locationInfo") or {}
    addr_raw = loc_raw.get("address") or {}
    postal_raw = addr_raw.get("postalCode") or {}
    location = {
        "address": addr_raw.get("addressLine1", ""),
        "city": postal_raw.get("cityName", "") or entity.get("postalCodeCityName", ""),
        "state": postal_raw.get("stateCode", ""),
        "postal_code": postal_raw.get("postalCodeNumber", ""),
        "latitude": loc_raw.get("latitude"),
        "longitude": loc_raw.get("longitude"),
        "map_url": loc_raw.get("mapUrl", ""),
    }

    # Parse dates
    dates_raw = entity.get("dates") or []
    dates = []
    for d in dates_raw:
        dates.append({
            "local_start": (d.get("localStartDate") or {}).get("_value"),
            "local_end": (d.get("localEndDate") or {}).get("_value"),
            "utc_start": (d.get("utcStartDate") or {}).get("_value"),
            "utc_end": (d.get("utcEndDate") or {}).get("_value"),
        })

    # Parse pictures
    pictures_raw = entity.get("pictures") or []
    pictures: list[EstateSalesPicture] = []

    for p in pictures_raw:
        pid = str(p.get("id", ""))
        p_order = int(p.get("pictureOrder", len(pictures)))
        p_url = p.get("url", "")
        p_thumb = p.get("thumbnailUrl", "")
        p_width = int(p.get("width", 1200))
        p_height = int(p.get("height", 900))
        p_thumb_w = int(p.get("thumbnailWidth", 325))
        p_thumb_h = int(p.get("thumbnailHeight", 260))
        p_desc = clean_caption(p.get("description", ""))
        p_feat = bool(p.get("isFeatured", False))

        # Check images array if high-res variant is listed there
        for img in p.get("images", []):
            w = int(img.get("width", 0))
            if w > p_width:
                p_width = w
                p_height = int(img.get("height", 0))
                p_url = img.get("url", p_url)

        pictures.append(
            EstateSalesPicture(
                id=pid,
                sale_id=sale_id,
                picture_order=p_order,
                url=p_url,
                thumbnail_url=p_thumb,
                width=p_width,
                height=p_height,
                thumbnail_width=p_thumb_w,
                thumbnail_height=p_thumb_h,
                description=p_desc,
                is_featured=p_feat,
            )
        )

    # Sort by picture_order
    pictures.sort(key=lambda x: x.picture_order)

    return EstateSalesListing(
        sale_id=sale_id,
        url=source_url or entity.get("url") or f"https://www.estatesales.net/sale/{sale_id}",
        name=name,
        seller=seller,
        location=location,
        dates=dates,
        description=raw_desc,
        picture_count=len(pictures),
        pictures=pictures,
        terms=terms,
        auction_url=auction_url,
    )


def _parse_from_html_fallback(
    html: str, fallback_sale_id: str | None = None, source_url: str = ""
) -> EstateSalesListing:
    """Fallback parser scanning HTML markup for picture CDN URLs and title."""
    title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
    name = title_match.group(1).strip() if title_match else "Estate Sale"

    # Extract all distinct CDN image URLs
    seen_urls: set[str] = set()
    pictures: list[EstateSalesPicture] = []
    sale_id = fallback_sale_id or "0"

    for match in _CDN_PHOTO_PATTERN.finditer(html):
        sid, variant, fname = match.groups()
        full_url = match.group(0)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        if not sale_id or sale_id == "0":
            sale_id = sid

        # variant 1-1 is full size (1200x900), 1-2 is thumbnail (325x260)
        is_full = variant == "1-1"
        photo_id = fname.split(".")[0]

        pictures.append(
            EstateSalesPicture(
                id=photo_id,
                sale_id=sale_id,
                picture_order=len(pictures),
                url=full_url if is_full else full_url.replace("/1-2/", "/1-1/"),
                thumbnail_url=full_url if not is_full else full_url.replace("/1-1/", "/1-2/"),
                width=1200,
                height=900,
            )
        )

    return EstateSalesListing(
        sale_id=sale_id,
        url=source_url,
        name=name,
        picture_count=len(pictures),
        pictures=pictures,
    )


def download_estatesales_image(
    url: str,
    dest_path: Path,
    max_retries: int = 3,
    timeout: float = 20.0,
    verify_grade: bool = True,
) -> tuple[bool, str]:
    """
    Download a single image from EstateSales.NET CDN to local disk with verification.
    """
    if dest_path.exists() and dest_path.stat().st_size > 0:
        if verify_grade:
            data = dest_path.read_bytes()
            if not is_appraisal_grade(data):
                dims = image_dimensions(data)
                return False, f"cached file below appraisal grade: {dims}"
        return True, "cached"

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    clean_url = "https:" + url if url.startswith("//") else url
    req = urllib.request.Request(
        clean_url,
        headers={
            "User-Agent": _USER_AGENT,
            "Referer": "https://www.estatesales.net/",
        },
    )

    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                data = resp.read()

            if verify_grade and not is_appraisal_grade(data):
                dims = image_dimensions(data)
                size_desc = f"{dims[0]}x{dims[1]}" if dims else f"{len(data)} bytes"
                return False, f"served image below appraisal grade ({size_desc})"

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(data)
            return True, "downloaded"
        except Exception as e:
            if attempt == max_retries - 1:
                return False, f"failed after {max_retries} attempts: {e}"
            time.sleep(0.5 * (attempt + 1))

    return False, "exhausted retries"


def cache_estatesales_listing(
    url_or_id: str,
    output_dir: Path | str,
    max_workers: int = 8,
    download_images: bool = True,
    verify_grade: bool = True,
) -> dict[str, Any]:
    """
    Fetch listing metadata, write manifest & metadata JSON, and download all photos.
    """
    sale_id = extract_sale_id(url_or_id)
    if not sale_id:
        raise ValueError(f"Could not extract sale ID from: {url_or_id}")

    url = resolve_sale_url(url_or_id)

    out = Path(output_dir)
    images_dir = out / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Fetching EstateSales.NET listing for sale {sale_id}...")
    html = fetch_listing_html(url)
    listing = parse_listing_page(html, fallback_sale_id=sale_id, source_url=url)

    if not listing.pictures:
        raise RuntimeError(f"No photos found for EstateSales.NET listing {sale_id}")

    print(f"[+] Found {len(listing.pictures)} photos for '{listing.name}'")

    # Format standard manifest entries matching Blue Toad Fleet intake schema
    manifest_entries = []
    for seq_idx, pic in enumerate(listing.pictures, start=1):
        filename = f"{seq_idx:03d}_{pic.id}.jpg"
        local_dest = images_dir / filename

        manifest_entries.append({
            "sequence": seq_idx,
            "picture_order": pic.picture_order,
            "photo_id": str(pic.id),
            "filename": filename,
            "caption": pic.description,
            "has_caption": bool(pic.description),
            "width": pic.width,
            "height": pic.height,
            "thumb_url": pic.thumbnail_url or pic.url,
            "full_url": pic.url,
            "local_path": str(local_dest),
        })

    manifest_payload = {
        "listing_id": listing.sale_id,
        "source": "estatesales.net",
        "url": listing.url,
        "name": listing.name,
        "total_photos": len(manifest_entries),
        "captioned_photos": sum(1 for e in manifest_entries if e["has_caption"]),
        "photos": manifest_entries,
    }

    manifest_file = out / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_payload, indent=2))
    print(f"[✓] Saved manifest to {manifest_file}")

    metadata_payload = {
        "sale_id": listing.sale_id,
        "name": listing.name,
        "url": listing.url,
        "seller": listing.seller,
        "location": listing.location,
        "dates": listing.dates,
        "description": listing.description,
        "terms": listing.terms,
        "auction_url": listing.auction_url,
        "picture_count": len(listing.pictures),
    }

    metadata_file = out / "sale_metadata.json"
    metadata_file.write_text(json.dumps(metadata_payload, indent=2))
    print(f"[✓] Saved sale metadata to {metadata_file}")

    download_results = {"success": 0, "failed": 0, "failures": []}

    if download_images:
        print(f"[*] Downloading {len(manifest_entries)} full-resolution images with {max_workers} threads...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_entry = {
                executor.submit(
                    download_estatesales_image,
                    e["full_url"],
                    Path(e["local_path"]),
                    verify_grade=verify_grade,
                ): e
                for e in manifest_entries
            }

            for future in as_completed(future_to_entry):
                entry = future_to_entry[future]
                ok, status = future.result()
                if ok:
                    download_results["success"] += 1
                else:
                    download_results["failed"] += 1
                    download_results["failures"].append((entry["sequence"], entry["photo_id"], status))

        print(
            f"[✓] Successfully cached {download_results['success']}/{len(manifest_entries)} "
            f"images into {images_dir}"
        )
        if download_results["failed"] > 0:
            print(f"[!] {download_results['failed']} photo(s) failed download or grade check", file=sys.stderr)

    return {
        "manifest": manifest_payload,
        "metadata": metadata_payload,
        "downloads": download_results,
    }
