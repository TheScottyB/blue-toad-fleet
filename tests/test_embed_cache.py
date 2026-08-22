P2, P181 = "838421481", "838424282"


def test_missing_cache_is_empty(tmp_path):
    from src.intake.embed import load_vectors
    assert load_vectors(tmp_path / "nope.json", {2: P2}) == {}


def test_seq_keys_translate_to_photo_ids(tmp_path):
    from src.intake.embed import load_vectors
    p = tmp_path / "e.json"
    p.write_text('{"2": [1,0], "181": [0,1]}')
    v = load_vectors(p, {2: P2, 181: P181})
    assert set(v) == {P2, P181}


def test_photo_id_keys_used_as_is(tmp_path):
    from src.intake.embed import load_vectors
    p = tmp_path / "e.json"
    p.write_text(f'{{"{P2}": [1, 0], "{P181}": [0, 1]}}')
    v = load_vectors(p, {2: P2, 181: P181})
    assert set(v) == {P2, P181}
    assert v[P2] == [1, 0]
