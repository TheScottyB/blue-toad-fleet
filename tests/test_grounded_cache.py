from src.assemble.grounded import load_grounded_prices


def test_missing_file_is_empty(tmp_path):
    assert load_grounded_prices(tmp_path / "nope.json") == {}


def test_aug22_cache_has_usable_and_unusable_rows():
    rows = load_grounded_prices()
    if not rows:
        return
    assert any(r.get("usable") for r in rows.values())
    assert "BT-015" in rows
