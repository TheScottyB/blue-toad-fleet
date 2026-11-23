"""Offline EstateSales.NET cacher guards: real routes, NGRX_STATE only, atomic downloads."""

from __future__ import annotations

import hashlib
import io
import json

import pytest
from PIL import Image

from scripts.cache_estatesales import (
    cache_estatesales,
    main,
    parse_listing_html,
    parse_sale_url,
)
from src.intake.manifest import parse_drop


def _jpeg(width: int = 1200, height: int = 900) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (60, 80, 100)).save(buf, format="JPEG")
    return buf.getvalue()


class _Response:
    def __init__(self, body: bytes, content_type: str = "image/jpeg"):
        self._body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self._body


def _ngrx_html(pictures: list[dict], sale_id: str = "5042877") -> str:
    payload = {
        "NGRX_STATE": {
            "feature.traditionalSaleViewState": {
                "activeId": sale_id,
                "entitiesById": {
                    sale_id: {
                        "saleId": int(sale_id),
                        "name": "Antique Estate Collectible Auction",
                        "pictures": pictures,
                    }
                },
            }
        }
    }
    return f"<!DOCTYPE html><html><head><script>{json.dumps(payload)}</script></head></html>"


SAMPLE_PICTURES = [
    {
        "id": 231255862,
        "pictureOrder": 1,
        "width": 325,
        "height": 260,
        "url": "https://picturescdn.estatesales.net/5042877/1-2/thumb-only.jpg",
        "thumbnailUrl": "https://picturescdn.estatesales.net/5042877/1-2/29526291.jpg",
        "description": "vintage Pens &amp; pencils",
        "images": [
            {
                "width": 1200,
                "height": 900,
                "url": "https://picturescdn.estatesales.net/5042877/1-1/ece067d6.jpg",
            },
            {
                "width": 325,
                "height": 260,
                "url": "https://picturescdn.estatesales.net/5042877/1-2/29526291.jpg",
            },
        ],
    },
    {
        "id": 231255864,
        "pictureOrder": 0,
        "width": 1200,
        "height": 900,
        "url": "https://picturescdn.estatesales.net/5042877/1-1/d1fd6c17.jpg",
        "thumbnailUrl": "https://picturescdn.estatesales.net/5042877/1-2/0462177a.jpg",
        "description": "",
    },
]


def test_parse_sale_url_accepts_routable_paths_and_rejects_404_shortcuts():
    assert parse_sale_url("https://www.estatesales.net/WI/Genoa-City/53128/5042877") == (
        "5042877",
        "https://www.estatesales.net/WI/Genoa-City/53128/5042877",
    )
    assert parse_sale_url(
        "https://www.EstateSales.NET/WI/Genoa-City/53128/traditional/5042877/?utm=1#top"
    ) == (
        "5042877",
        "https://www.estatesales.net/WI/Genoa-City/53128/traditional/5042877",
    )

    for invalid in (
        "5042877",
        "https://www.estatesales.net/sale/5042877",
        "https://www.estatesales.net/WI/Genoa-City/53128",
        "https://evil.example/estatesales.net/WI/Genoa-City/53128/5042877",
        "",
    ):
        with pytest.raises(ValueError):
            parse_sale_url(invalid)


def test_parse_listing_html_orders_by_picture_order_and_decodes_entities_once():
    name, pictures = parse_listing_html(_ngrx_html(SAMPLE_PICTURES), "5042877")
    assert name == "Antique Estate Collectible Auction"
    assert [p["es_order"] for p in pictures] == [0, 1]
    assert [p["photo_id"] for p in pictures] == ["231255864", "231255862"]
    assert pictures[0]["caption"] == ""
    assert pictures[1]["caption"] == "vintage Pens & pencils"
    assert pictures[1]["full_url"] == "https://picturescdn.estatesales.net/5042877/1-1/ece067d6.jpg"


def test_parse_listing_html_fails_closed_on_missing_or_unsafe_payloads():
    # Thumbnail and full-size CDN URLs do not share UUIDs; raw <img> scraping must never run.
    html = '<img src="https://picturescdn.estatesales.net/5042877/1-2/0462177a.jpg">'
    with pytest.raises(ValueError, match="no NGRX_STATE"):
        parse_listing_html(html, "5042877")

    with pytest.raises(ValueError, match="sale 9999999 not present"):
        parse_listing_html(_ngrx_html(SAMPLE_PICTURES, sale_id="5042877"), "9999999")

    traversal_pic = [{"id": "../escape", "pictureOrder": 0, "url": "https://example.test/a.jpg"}]
    with pytest.raises(ValueError, match="unsafe picture id"):
        parse_listing_html(_ngrx_html(traversal_pic), "5042877")

    file_scheme_pic = [{"id": "123", "pictureOrder": 0, "url": "file:///etc/passwd"}]
    with pytest.raises(ValueError, match="invalid picture 123 URL"):
        parse_listing_html(_ngrx_html(file_scheme_pic), "5042877")


def test_cache_estatesales_writes_verified_manifest_compatible_with_intake(tmp_path):
    body = _jpeg(1200, 900)
    html = _ngrx_html(SAMPLE_PICTURES).encode("utf-8")

    def opener(req, timeout=15):
        if req.full_url.startswith("https://www.estatesales.net/"):
            return _Response(html, "text/html; charset=utf-8")
        assert req.headers.get("Referer") == "https://www.estatesales.net/"
        return _Response(body, "image/jpeg")

    out_dir = tmp_path / "es_5042877"
    rc = cache_estatesales(
        "https://www.estatesales.net/WI/Genoa-City/53128/5042877",
        output_dir=out_dir,
        max_workers=2,
        opener=opener,
    )
    assert rc == 0

    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["listing_id"] == "5042877"
    assert manifest["source"] == "estatesales.net"
    assert manifest["total_photos"] == 2
    assert manifest["captioned_photos"] == 1
    assert not (out_dir / "sale_metadata.json").exists()

    first = manifest["photos"][0]
    assert first["filename"] == "001_231255864.jpg"
    assert first["sha256"] == hashlib.sha256(body).hexdigest()
    assert (first["mime_type"], first["width"], first["height"]) == ("image/jpeg", 1200, 900)
    assert first["download_status"] == "usable"
    assert (out_dir / "images" / "001_231255864.jpg").read_bytes() == body

    drop = parse_drop(
        cycle_id="es_cycle",
        listing_id=manifest["listing_id"],
        entries=[
            {"name": p["filename"], "uri": p["full_url"], "caption": p["caption"]}
            for p in manifest["photos"]
        ],
    )
    assert len(drop.photos) == 2
    assert drop.captioned == 1


def test_cache_estatesales_no_images_skips_binary_downloads_and_images_dir(tmp_path):
    html = _ngrx_html(SAMPLE_PICTURES).encode("utf-8")
    calls = []

    def opener(req, timeout=15):
        calls.append(req.full_url)
        return _Response(html, "text/html")

    out_dir = tmp_path / "es_meta_only"
    rc = cache_estatesales(
        "https://www.estatesales.net/WI/Genoa-City/53128/5042877",
        output_dir=out_dir,
        download_images=False,
        opener=opener,
    )
    assert rc == 0
    assert calls == ["https://www.estatesales.net/WI/Genoa-City/53128/5042877"]
    assert (out_dir / "manifest.json").is_file()
    assert not (out_dir / "images").exists()


def test_cache_estatesales_returns_nonzero_when_image_is_below_appraisal_grade(tmp_path):
    thumb = _jpeg(140, 105)
    html = _ngrx_html(SAMPLE_PICTURES[:1]).encode("utf-8")

    def opener(req, timeout=15):
        if req.full_url.startswith("https://www.estatesales.net/"):
            return _Response(html, "text/html")
        return _Response(thumb, "image/jpeg")

    out_dir = tmp_path / "es_bad"
    rc = cache_estatesales(
        "https://www.estatesales.net/WI/Genoa-City/53128/5042877",
        output_dir=out_dir,
        max_workers=1,
        opener=opener,
    )
    assert rc == 1
    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["photos"][0]["download_status"] == "failed"
    assert "not an appraisal-grade image" in manifest["photos"][0]["download_error"]
    assert not (out_dir / "images" / "001_231255862.jpg").exists()


def test_cli_rejects_bare_sale_id_and_short_route_with_nonzero_exit(capsys):
    for bad in ("5042877", "https://www.estatesales.net/sale/5042877"):
        assert main([bad]) == 1
        assert "404 on /sale/<id>" in capsys.readouterr().err
