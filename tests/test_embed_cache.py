import json

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


def test_seq_and_photo_id_json_yield_mergeable_bt_keys(tmp_path):
    """Both cache shapes must land in the server grouping space for seq 2/181."""
    from src.intake.embed import load_vectors
    photo_by_seq = {2: "BT-002", 181: "BT-181"}
    gallery_ids = {P2: "BT-002", P181: "BT-181"}
    sequences = {"BT-002": 2, "BT-181": 181}

    seq_p = tmp_path / "seq.json"
    seq_p.write_text(json.dumps({"2": [1.0, 0.0], "181": [0.0, 1.0]}))
    pid_p = tmp_path / "pid.json"
    pid_p.write_text(json.dumps({P2: [1.0, 0.0], P181: [0.0, 1.0]}))

    v_seq = load_vectors(seq_p, photo_by_seq, gallery_ids)
    v_pid = load_vectors(pid_p, photo_by_seq, gallery_ids)
    assert set(v_seq) == set(v_pid) == {"BT-002", "BT-181"}
    assert set(v_seq) <= set(sequences)
    assert set(v_pid) <= set(sequences)


def test_photo_id_json_without_alias_is_not_bt_keys(tmp_path):
    """The silent 0-vector failure: spec 3.1 keys dropped by a BT-00N filter."""
    from src.intake.embed import load_vectors
    p = tmp_path / "e.json"
    p.write_text(json.dumps({P2: [1.0, 0.0], P181: [0.0, 1.0]}))
    v = load_vectors(p, {2: "BT-002", 181: "BT-181"})
    assert set(v) == {P2, P181}
    assert "BT-002" not in v and "BT-181" not in v


def test_present_cache_with_unmapped_keys_logs_zero_vectors(tmp_path, capsys):
    from src.intake.embed import load_reshoot_edges
    p = tmp_path / "embeddings.json"
    p.write_text(json.dumps({"999999": [1.0, 0.0]}))
    edges = load_reshoot_edges(p, {2: "BT-002"}, {"BT-002": 2})
    assert edges == set()
    assert "0 vector" in capsys.readouterr().out.lower()


def test_corrupt_json_does_not_raise_from_server_load_path(tmp_path):
    from src.intake.embed import load_reshoot_edges
    p = tmp_path / "embeddings.json"
    p.write_text("{not json")
    assert load_reshoot_edges(p, {2: P2}, {P2: 2}) == set()


def test_mixed_length_vectors_are_walk_only(tmp_path):
    from src.intake.embed import load_reshoot_edges
    p = tmp_path / "embeddings.json"
    p.write_text(json.dumps({"2": [1.0, 0.0], "181": [1.0, 0.0, 0.0]}))
    edges = load_reshoot_edges(
        p, {2: P2, 181: P181}, {P2: 2, P181: 181},
    )
    assert edges == set()


def test_missing_cache_skips_cosine(tmp_path, monkeypatch):
    from src.intake import embed as embed_mod
    n = {"c": 0}

    def counted(*a, **k):
        n["c"] += 1
        return set()

    monkeypatch.setattr(embed_mod, "reshoot_edges", counted)
    edges = embed_mod.load_reshoot_edges(
        tmp_path / "nope.json", {2: "BT-002"}, {"BT-002": 2},
    )
    assert edges == set()
    assert n["c"] == 0


def test_edges_memoized_by_cache_mtime_size(tmp_path, monkeypatch):
    from src.intake import embed as embed_mod

    embed_mod._EDGE_MEMO.clear()
    p = tmp_path / "embeddings.json"
    p.write_text(json.dumps({"2": [1.0, 0.0], "181": [0.0, 1.0]}))
    n = {"c": 0}
    real = embed_mod.reshoot_edges

    def counted(vectors, sequences):
        n["c"] += 1
        return real(vectors, sequences)

    monkeypatch.setattr(embed_mod, "reshoot_edges", counted)
    photo_by_seq = {2: "BT-002", 181: "BT-181"}
    sequences = {"BT-002": 2, "BT-181": 181}
    embed_mod.load_reshoot_edges(p, photo_by_seq, sequences)
    embed_mod.load_reshoot_edges(p, photo_by_seq, sequences)
    assert n["c"] == 1
    p.write_text(json.dumps({"2": [1.0, 0.0], "181": [0.1, 0.9]}))
    embed_mod.load_reshoot_edges(p, photo_by_seq, sequences)
    assert n["c"] == 2
