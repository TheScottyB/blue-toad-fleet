"""
tests/test_cache_estatesales.py — Unit tests for EstateSales.NET cacher and intake.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.intake.estatesales import (
    EstateSalesListing, EstateSalesPicture, cache_estatesales_listing,
    download_estatesales_image, extract_sale_id, parse_listing_page,
)
from src.intake.manifest import parse_drop

# Minimal valid JPEG headers for testing
# 1200x900 JPEG (Appraisal Grade)
JPEG_1200x900 = (
    b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
    b"\xFF\xC0\x00\x11\x08\x03\x84\x04\xB0\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"  # 0384=900h, 04B0=1200w
    b"\xFF\xD9"
)

# 140x105 Thumbnail (Below Appraisal Grade)
JPEG_140x105 = (
    b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
    b"\xFF\xC0\x00\x11\x08\x00\x69\x00\x8C\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"  # 0069=105h, 008C=140w
    b"\xFF\xD9"
)

SAMPLE_NGRX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Antique Estate Collectible Auction in Genoa City, WI starts on 8/22/2026</title>
    <script>
    {"NGRX_STATE": {
        "feature.traditionalSaleViewState": {
            "activeId": "5042877",
            "entitiesById": {
                "5042877": {
                    "saleId": 5042877,
                    "name": "Antique Estate Collectible Auction",
                    "url": "https://www.estatesales.net/WI/Genoa-City/53128/5042877",
                    "plainTextDescription": "AUCTION SATURDAY August 22nd PREVIEW 9:00 AM",
                    "terms": "Cash, Credit, Wire",
                    "auctionUrl": "https://www.auctionzip.com/auction-123",
                    "seller": {
                        "name": "Blue Toad Auctions",
                        "primaryPhone": "(847) 707-9446",
                        "websiteUrl": "http://www.bluetoadauctions.com",
                        "orgId": 35888,
                        "isOrg": true
                    },
                    "locationInfo": {
                        "address": {
                            "addressLine1": "200 Elizabeth Lane",
                            "postalCode": {
                                "cityName": "Genoa City",
                                "stateCode": "WI",
                                "postalCodeNumber": "53128"
                            }
                        },
                        "latitude": 42.505284,
                        "longitude": -88.319005,
                        "mapUrl": "https://maps.google.com/sample"
                    },
                    "dates": [
                        {
                            "localStartDate": {"_value": "2026-08-22T10:00:00Z"},
                            "localEndDate": {"_value": "2026-08-22T14:00:00Z"},
                            "utcStartDate": {"_value": "2026-08-22T15:00:00Z"},
                            "utcEndDate": {"_value": "2026-08-22T19:00:00Z"}
                        }
                    ],
                    "pictureCount": 2,
                    "pictures": [
                        {
                            "id": 231255864,
                            "saleId": 5042877,
                            "pictureOrder": 0,
                            "width": 1200,
                            "height": 900,
                            "url": "https://picturescdn.estatesales.net/5042877/1-1/d1fd6c17.jpg",
                            "thumbnailUrl": "https://picturescdn.estatesales.net/5042877/1-2/d1fd6c17_t.jpg",
                            "description": "Vintage Topps Baseball Cards",
                            "isFeatured": true
                        },
                        {
                            "id": 231255862,
                            "saleId": 5042877,
                            "pictureOrder": 1,
                            "width": 1200,
                            "height": 900,
                            "url": "https://picturescdn.estatesales.net/5042877/1-1/ece067d6.jpg",
                            "thumbnailUrl": "https://picturescdn.estatesales.net/5042877/1-2/ece067d6_t.jpg",
                            "description": "Estate Costume Jewelry",
                            "isFeatured": false
                        }
                    ]
                }
            }
        }
    }}
    </script>
</head>
<body></body>
</html>
"""


def test_extract_sale_id():
    # Full URL variations
    assert extract_sale_id("https://www.estatesales.net/WI/Genoa-City/53128/5042877") == "5042877"
    assert extract_sale_id("https://www.estatesales.net/WI/Genoa-City/53128/5042877/") == "5042877"
    assert extract_sale_id("https://www.estatesales.net/WI/Genoa-City/53128/5042877?filter=1") == "5042877"
    assert extract_sale_id("https://www.estatesales.net/WI/Genoa-City/53128/5042877#gallery") == "5042877"
    assert extract_sale_id("https://www.estatesales.net/sale/5042877") == "5042877"
    assert extract_sale_id("https://www.estatesales.net/sales/5042877") == "5042877"

    # Bare ID string
    assert extract_sale_id("5042877") == "5042877"
    assert extract_sale_id("  5042877  ") == "5042877"

    # Non-sale inputs
    assert extract_sale_id("https://www.estatesales.net/WI/Genoa-City/53128") is None
    assert extract_sale_id("https://google.com") is None
    assert extract_sale_id("") is None


def test_parse_listing_page_ngrx():
    listing = parse_listing_page(SAMPLE_NGRX_HTML, fallback_sale_id="5042877")
    assert listing.sale_id == "5042877"
    assert listing.name == "Antique Estate Collectible Auction"
    assert listing.seller["name"] == "Blue Toad Auctions"
    assert listing.seller["phone"] == "(847) 707-9446"
    assert listing.location["city"] == "Genoa City"
    assert listing.location["state"] == "WI"
    assert listing.location["postal_code"] == "53128"
    assert listing.location["address"] == "200 Elizabeth Lane"
    assert listing.location["latitude"] == 42.505284
    assert listing.location["longitude"] == -88.319005

    assert len(listing.dates) == 1
    assert listing.dates[0]["local_start"] == "2026-08-22T10:00:00Z"

    assert len(listing.pictures) == 2
    p1 = listing.pictures[0]
    assert p1.id == "231255864"
    assert p1.picture_order == 0
    assert p1.width == 1200
    assert p1.height == 900
    assert p1.url == "https://picturescdn.estatesales.net/5042877/1-1/d1fd6c17.jpg"
    assert p1.description == "Vintage Topps Baseball Cards"
    assert p1.has_description is True
    assert p1.is_featured is True

    p2 = listing.pictures[1]
    assert p2.id == "231255862"
    assert p2.picture_order == 1
    assert p2.description == "Estate Costume Jewelry"


def test_parse_listing_page_fallback():
    fallback_html = """
    <html>
    <head><title>Sale in Genoa City</title></head>
    <body>
        <img src="https://picturescdn.estatesales.net/5042877/1-1/d1fd6c17-dc65-4ff4-9a8e-bfbc5a991923.jpg">
        <img src="https://picturescdn.estatesales.net/5042877/1-1/ece067d6-1e57-4f82-a4b4-8a21cf2cd2f6.jpg">
    </body>
    </html>
    """
    listing = parse_listing_page(fallback_html, fallback_sale_id="5042877")
    assert listing.sale_id == "5042877"
    assert len(listing.pictures) == 2
    assert listing.pictures[0].url.startswith("https://picturescdn.estatesales.net/5042877/1-1/")


def test_download_estatesales_image_success(tmp_path):
    dest = tmp_path / "images" / "001.jpg"

    mock_resp = MagicMock()
    mock_resp.read.return_value = JPEG_1200x900
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ok, msg = download_estatesales_image(
            url="https://picturescdn.estatesales.net/5042877/1-1/sample.jpg",
            dest_path=dest,
            verify_grade=True,
        )
        assert ok is True
        assert msg == "downloaded"
        assert dest.exists()
        assert dest.read_bytes() == JPEG_1200x900

        # Test idempotency (should return cached without re-downloading)
        ok_cached, msg_cached = download_estatesales_image(
            url="https://picturescdn.estatesales.net/5042877/1-1/sample.jpg",
            dest_path=dest,
            verify_grade=True,
        )
        assert ok_cached is True
        assert msg_cached == "cached"


def test_download_estatesales_image_rejects_thumbnail(tmp_path):
    dest = tmp_path / "images" / "thumb.jpg"

    mock_resp = MagicMock()
    mock_resp.read.return_value = JPEG_140x105
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ok, msg = download_estatesales_image(
            url="https://picturescdn.estatesales.net/5042877/1-2/thumb.jpg",
            dest_path=dest,
            verify_grade=True,
        )
        assert ok is False
        assert "below appraisal grade" in msg


def test_cache_estatesales_listing_pipeline(tmp_path):
    out_dir = tmp_path / "cache_5042877"

    mock_urlopen = MagicMock()
    # First call for HTML fetch, subsequent calls for images
    html_resp = MagicMock()
    html_resp.read.return_value = SAMPLE_NGRX_HTML.encode("utf-8")
    html_resp.__enter__.return_value = html_resp

    img_resp = MagicMock()
    img_resp.read.return_value = JPEG_1200x900
    img_resp.__enter__.return_value = img_resp

    mock_urlopen.side_effect = [html_resp, img_resp, img_resp]

    with patch("urllib.request.urlopen", mock_urlopen):
        result = cache_estatesales_listing(
            url_or_id="https://www.estatesales.net/WI/Genoa-City/53128/5042877",
            output_dir=out_dir,
            max_workers=2,
            download_images=True,
            verify_grade=True,
        )

    assert result["downloads"]["success"] == 2
    assert result["downloads"]["failed"] == 0

    # Verify manifest.json
    manifest_path = out_dir / "manifest.json"
    assert manifest_path.is_file()
    manifest_data = json.loads(manifest_path.read_text())
    assert manifest_data["listing_id"] == "5042877"
    assert manifest_data["total_photos"] == 2
    assert manifest_data["captioned_photos"] == 2
    assert len(manifest_data["photos"]) == 2

    # Verify compatibility with parse_drop
    entries = [
        {"name": p["filename"], "uri": p["full_url"], "caption": p["caption"]}
        for p in manifest_data["photos"]
    ]
    drop = parse_drop(cycle_id="test_cycle", listing_id="5042877", entries=entries)
    assert drop.cycle_id == "test_cycle"
    assert len(drop.photos) == 2
    assert drop.captioned == 2

    # Verify sale_metadata.json
    meta_path = out_dir / "sale_metadata.json"
    assert meta_path.is_file()
    meta_data = json.loads(meta_path.read_text())
    assert meta_data["sale_id"] == "5042877"
    assert meta_data["name"] == "Antique Estate Collectible Auction"
    assert meta_data["seller"]["name"] == "Blue Toad Auctions"
    assert meta_data["location"]["city"] == "Genoa City"
    assert meta_data["location"]["postal_code"] == "53128"


def test_cache_estatesales_no_images(tmp_path):
    out_dir = tmp_path / "cache_no_images"

    html_resp = MagicMock()
    html_resp.read.return_value = SAMPLE_NGRX_HTML.encode("utf-8")
    html_resp.__enter__.return_value = html_resp

    with patch("urllib.request.urlopen", return_value=html_resp):
        result = cache_estatesales_listing(
            url_or_id="5042877",
            output_dir=out_dir,
            download_images=False,
        )

    assert result["downloads"]["success"] == 0
    assert result["downloads"]["failed"] == 0
    assert (out_dir / "manifest.json").is_file()
    assert (out_dir / "sale_metadata.json").is_file()
