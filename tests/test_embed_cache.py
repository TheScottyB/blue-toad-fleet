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


def test_present_cache_without_review_logs_walk_only(tmp_path, capsys):
    from src.intake.embed import load_reshoot_edges
    p = tmp_path / "embeddings.json"
    p.write_text(json.dumps({"999999": [1.0, 0.0]}))
    edges = load_reshoot_edges(p, {2: "BT-002"}, {"BT-002": 2})
    assert edges == set()
    assert "no current approved" in capsys.readouterr().out.lower()


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


def test_request_path_never_computes_unreviewed_edges(tmp_path, monkeypatch):
    from src.intake import embed as embed_mod

    embed_mod._EDGE_MEMO.clear()
    p = tmp_path / "embeddings.json"
    p.write_text(json.dumps({"2": [1.0, 0.0], "181": [0.0, 1.0]}))
    n = {"c": 0}
    def counted(*_args, **_kwargs):
        n["c"] += 1
        return set()

    monkeypatch.setattr(embed_mod, "reshoot_edges", counted)
    photo_by_seq = {2: "BT-002", 181: "BT-181"}
    sequences = {"BT-002": 2, "BT-181": 181}
    assert embed_mod.load_reshoot_edges(p, photo_by_seq, sequences) == set()
    assert embed_mod.load_reshoot_edges(p, photo_by_seq, sequences) == set()
    p.write_text(json.dumps({"2": [1.0, 0.0], "181": [0.1, 0.9]}))
    assert embed_mod.load_reshoot_edges(p, photo_by_seq, sequences) == set()
    assert n["c"] == 0


def test_dump_vectors_round_trips_photo_id_keys(tmp_path):
    from src.intake.embed import dump_vectors, load_vectors
    p = tmp_path / "embeddings.json"
    dump_vectors(p, {P2: [1.0, 0.0], P181: [0.0, 1.0]})
    v = load_vectors(p, {2: P2, 181: P181})
    assert set(v) == {P2, P181}
    assert v[P2][0] == 1.0


def test_dump_vectors_does_not_overwrite_unrelated_ids(tmp_path):
    from src.intake.embed import dump_vectors, load_vectors
    p = tmp_path / "embeddings.json"
    dump_vectors(p, {P2: [1.0, 0.0]})
    dump_vectors(p, {P2: [1.0, 0.0], P181: [0.0, 1.0]})
    v = load_vectors(p, {2: P2, 181: P181})
    assert set(v) == {P2, P181}


def test_approved_sidecar_merges_2_181(tmp_path):
    """Only an evidence-bearing approved record can affect grouping."""
    from src.intake.embed import dump_reshoot_edges, load_reshoot_edges

    cache = tmp_path / "embeddings.json"
    cache.write_text(json.dumps({P2: [1.0, 0.0], P181: [0.0, 1.0]}))
    dump_reshoot_edges(
        cache,
        {frozenset({P2, P181})},
        status="approved",
        reviewer="operator",
        reviewed_at="2026-08-22T01:00:00-05:00",
        evidence="same photographed tray group",
    )
    edges = load_reshoot_edges(
        cache,
        {2: "BT-002", 181: "BT-181"},
        {"BT-002": 2, "BT-181": 181},
        gallery_ids={P2: "BT-002", P181: "BT-181"},
    )
    assert frozenset({"BT-002", "BT-181"}) in edges


def test_proposed_edge_cannot_change_grouping(tmp_path):
    from src.intake.embed import dump_reshoot_edges, load_reshoot_edges

    cache = tmp_path / "embeddings.json"
    cache.write_text(json.dumps({P2: [1.0, 0.0], P181: [0.0, 1.0]}))
    dump_reshoot_edges(cache, {frozenset({P2, P181})})
    assert load_reshoot_edges(
        cache,
        {2: P2, 181: P181},
        {P2: 2, P181: 181},
    ) == set()


def test_aug22_sidecar_pins_2_181_not_180_or_87():
    """The committed merge table is what GET / uses. Pin the live pair."""
    from pathlib import Path
    from src.intake.embed import load_reshoot_edges

    cache = Path("data/aug22_gallery_4160518/embeddings.json")
    sidecar = cache.with_name("reshoot_edges.json")
    if not sidecar.is_file():
        import pytest
        pytest.skip("reshoot_edges.json not in tree")
    photo_by_seq = {2: "BT-002", 180: "BT-180", 181: "BT-181", 87: "BT-087"}
    sequences = {"BT-002": 2, "BT-180": 180, "BT-181": 181, "BT-087": 87}
    gallery_ids = {
        "838421481": "BT-002",
        "838424264": "BT-180",
        "838424282": "BT-181",
        "838422448": "BT-087",
    }
    edges = load_reshoot_edges(
        cache, photo_by_seq, sequences, gallery_ids=gallery_ids,
    )
    assert frozenset({"BT-002", "BT-181"}) in edges
    assert frozenset({"BT-002", "BT-180"}) not in edges
    assert frozenset({"BT-002", "BT-087"}) not in edges


def test_sidecar_skips_all_pairs_cosine(tmp_path, monkeypatch):
    from src.intake import embed as embed_mod

    embed_mod._EDGE_MEMO.clear()
    cache = tmp_path / "embeddings.json"
    cache.write_text(json.dumps({P2: [1.0, 0.0], P181: [0.0, 1.0]}))
    embed_mod.dump_reshoot_edges(
        cache,
        {frozenset({P2, P181})},
        status="approved",
        reviewer="operator",
        reviewed_at="2026-08-22T01:00:00-05:00",
    )
    n = {"c": 0}

    def counted(*a, **k):
        n["c"] += 1
        return set()

    monkeypatch.setattr(embed_mod, "reshoot_edges", counted)
    embed_mod.load_reshoot_edges(
        cache,
        {2: "BT-002", 181: "BT-181"},
        {"BT-002": 2, "BT-181": 181},
        gallery_ids={P2: "BT-002", P181: "BT-181"},
    )
    assert n["c"] == 0


def test_pair_publication_preserves_last_good_pair_on_interruption(tmp_path):
    from src.intake.embed import publish_embedding_pair, sidecar_path

    cache = tmp_path / "embeddings.json"
    cache.write_text('{"old": [1, 0]}')
    sidecar_path(cache).write_text('{"old": true}')

    def interrupt():
        raise RuntimeError("simulated interruption")

    try:
        publish_embedding_pair(
            cache,
            {P2: [1.0, 0.0], P181: [0.0, 1.0]},
            {frozenset({P2, P181})},
            required_ids={P2, P181},
            manifest_sha256="manifest-hash",
            after_vector_replace=interrupt,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("simulated interruption should propagate")

    assert cache.read_text() == '{"old": [1, 0]}'
    assert sidecar_path(cache).read_text() == '{"old": true}'


def test_pair_publication_refuses_partial_or_mixed_dimension_cache(tmp_path):
    from src.intake.embed import publish_embedding_pair

    cache = tmp_path / "embeddings.json"
    for vectors in ({P2: [1.0, 0.0]}, {P2: [1.0], P181: [0.0, 1.0]}):
        try:
            publish_embedding_pair(
                cache,
                vectors,
                set(),
                required_ids={P2, P181},
                manifest_sha256="manifest-hash",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("invalid pair must be refused")
    assert not cache.exists()
