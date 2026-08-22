from src.intake.spatial import nearest_neighbor, reshoot_edges, SANITY_FLOOR

P2, P180, P181, P87 = "838421481", "838424264", "838424282", "838422448"
SEQ = {P2: 2, P180: 180, P181: 181, P87: 87}


def _vectors():
    """181 is closer to walk-adjacent 180 than to 2; 2 is still 181's
    non-adjacent best; 87 is far. Cosine is dot of these raw tuples
    after the implementation L2-normalizes (or equivalent)."""
    return {
        P181: (1.0, 0.0, 0.0),
        P180: (0.999, 0.0448, 0.0),   # ~0.999 with 181
        P2:   (0.906, -0.4232, 0.0),  # ~0.906 with 181; opposite side of 180 so nn(2)=181
        P87:  (0.0, 0.0, 1.0),
    }


class TestScopedNn:
    def test_over_all_photos_181_nearest_is_walk_adjacent_180(self):
        assert nearest_neighbor(
            P181, _vectors(), SEQ, exclude_walk_adjacent=False) == P180

    def test_scoped_nn_181_is_2(self):
        assert nearest_neighbor(P181, _vectors(), SEQ) == P2

    def test_scoped_nn_2_is_181(self):
        assert nearest_neighbor(P2, _vectors(), SEQ) == P181


class TestReshootEdges:
    def test_2_and_181_are_an_edge(self):
        assert frozenset({P2, P181}) in reshoot_edges(_vectors(), SEQ)

    def test_2_and_180_are_not_an_edge(self):
        assert frozenset({P2, P180}) not in reshoot_edges(_vectors(), SEQ)

    def test_2_and_87_are_not_an_edge(self):
        assert frozenset({P2, P87}) not in reshoot_edges(_vectors(), SEQ)

    def test_walk_adjacent_never_an_edge_even_if_closest(self):
        assert frozenset({P180, P181}) not in reshoot_edges(_vectors(), SEQ)

    def test_sanity_floor_vetoes_weak_mutual_pair(self):
        from src.intake.spatial import cosine
        weak = {"a": (1.0, 0.0), "b": (0.70, 0.71414)}
        seq = {"a": 1, "b": 50}
        assert cosine(weak["a"], weak["b"]) < SANITY_FLOOR
        assert reshoot_edges(weak, seq) == set()
