"""Room-graph embeddings against three baselines, not one.

The probe's first pass compared `gemini-embedding-2` only against dHash. dHash is a
NEAR-DUPLICATE hash; it is the wrong tool for "same room, different framing", so
beating it says very little. Two harder baselines were added on review:

  seq        rank purely by |sequence difference|. If the photographer shoots a zone
             in one pass, frame proximity alone is a strong room-graph signal, and
             an embedding has to beat it to be worth 462 API calls per gallery.
  colorhist  32^3 RGB histogram, chi-square distance. The classic scene-similarity
             baseline and far stronger than dHash here.

Protocol: ground truth is same-caption pairs at least MIN_GAP frames apart, from
`manifest.json`. The gap floor is what makes this a zone-grouping test rather than
near-duplicate matching. Distance for embeddings is cosine on L2-normalised vectors.

The committed ``embeddings.json`` is the model output.  Image baselines use the
manifest's sanctioned cache; missing images fail with the exact recovery command
instead of relying on an uncommitted NPZ.

    .venv/bin/python scripts/probes/task3_baselines.py
"""
import argparse
import hashlib
import json
import pathlib
from collections import defaultdict

import numpy as np
from PIL import Image

IMAGES = pathlib.Path("data/aug22_gallery_4160518/images")
MANIFEST = pathlib.Path("data/aug22_gallery_4160518/manifest.json")
MIN_GAP = 10
HIST_BINS = 32


def dhash8(path):
    """The 8x8 difference hash named as `dhash8` in estatesales_link.json."""
    a = np.asarray(Image.open(path).convert("L").resize((9, 8), Image.LANCZOS),
                   dtype=np.int16)
    v = 0
    for bit in (a[:, 1:] > a[:, :-1]).flatten():
        v = (v << 1) | int(bit)
    return v


def hamming(a, b):
    return bin(a ^ b).count("1")


def color_hist(path):
    a = np.asarray(Image.open(path).convert("RGB").resize((128, 128), Image.BILINEAR))
    h, _ = np.histogramdd(a.reshape(-1, 3), bins=(HIST_BINS,) * 3, range=((0, 256),) * 3)
    h = h.flatten()
    return h / h.sum()


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(output=None):
    manifest = json.loads(MANIFEST.read_text())
    vectors = json.loads(pathlib.Path(
        "data/aug22_gallery_4160518/embeddings.json").read_text())
    seq_to_id = {int(row["sequence"]): str(row["photo_id"])
                 for row in manifest["photos"]}
    emb = {
        sequence: np.asarray(vectors[photo_id], dtype=float)
        for sequence, photo_id in seq_to_id.items()
        if photo_id in vectors
    }
    paths = {int(p.name[:3]): p for p in sorted(IMAGES.glob("*.jpg"))}
    missing = sorted(set(emb) - set(paths))
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} sanctioned baseline images are missing; run "
            "`python -m scripts.cache_gallery --manifest "
            "data/aug22_gallery_4160518/manifest.json` before this probe"
        )
    hashes = {s: dhash8(p) for s, p in paths.items()}
    seqs = sorted(set(emb) & set(hashes))
    idx = {s: i for i, s in enumerate(seqs)}

    M = np.stack([emb[s] for s in seqs])
    M /= np.linalg.norm(M, axis=1, keepdims=True)
    print(f"building colour histograms for {len(seqs)} photos ...", flush=True)
    H = np.stack([color_hist(paths[s]) for s in seqs])

    def rank(scores, q, t, bigger_is_better):
        """Tie-aware rank of t among all candidates except q.

        dHash Hamming distances are integers over ~460 candidates, so dozens of
        photos share a distance and a naive argsort assigns the true partner an
        ARBITRARY position inside its tie block -- the number then depends on the
        sort algorithm, not on the method. This returns the midpoint of the tie
        block (the standard average-rank convention), which is reproducible.
        Embedding cosines and chi-square distances are floats and rarely tie, so
        this is a no-op for them.
        """
        s = -scores if bigger_is_better else scores
        keep = np.array([k != q for k in seqs])
        s, st = s[keep], s[idx[t]]
        better = int((s < st).sum())
        tied = int((s == st).sum())          # includes t itself
        return better + (tied + 1) / 2.0

    def r_emb(q, t):
        s = M @ M[idx[q]]
        return rank(s, q, t, True), float(s[idx[t]])

    def r_dhash(q, t):
        s = np.array([hamming(hashes[q], hashes[k]) for k in seqs], float)
        return rank(s, q, t, False), hamming(hashes[q], hashes[t])

    def r_seq(q, t):
        return rank(np.array([abs(k - q) for k in seqs], float), q, t, False), abs(t - q)

    def r_color(q, t):
        a = H[idx[q]]
        s = (0.5 * (H - a) ** 2 / (H + a + 1e-12)).sum(1)
        return rank(s, q, t, False), float(s[idx[t]])

    groups = defaultdict(list)
    for p in manifest["photos"]:
        c = (p.get("caption") or "").strip().lower()
        if c:
            groups[c].append(p["sequence"])
    pairs = []
    for caption, members in groups.items():
        members = sorted(x for x in members if x in idx)
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                if members[j] - members[i] >= MIN_GAP:
                    pairs.append((members[i], members[j], caption))

    print(f"\nN={len(seqs)} photos; {len(pairs)} non-adjacent same-caption pairs "
          f"(gap>={MIN_GAP})\n")
    print(f"{'a':>4}{'b':>5}{'gap':>5} | {'emb':>5}{'cos':>7} | {'dHash':>6} | "
          f"{'seq':>5} | {'color':>6} | caption")
    ranks = defaultdict(list)
    for a, b, caption in sorted(pairs, key=lambda x: -(x[1] - x[0])):
        (re_, cos), (rd, _), (rs, _), (rc, _) = r_emb(a, b), r_dhash(a, b), r_seq(a, b), r_color(a, b)
        for k, v in (("emb", re_), ("dhash", rd), ("seq", rs), ("color", rc)):
            ranks[k].append(v)
        print(f"{a:>4}{b:>5}{b - a:>5} | {re_:>5.0f}{cos:>7.3f} | {rd:>6.1f} | "
              f"{rs:>5.0f} | {rc:>6.0f} | {caption[:30]}")

    cols = ("emb", "dhash", "seq", "color")
    print(f"\n{'metric':<16}" + "".join(f"{c:>12}" for c in cols))
    for name, fn in (("median rank", np.median), ("mean rank", np.mean),
                     ("worst rank", np.max), ("best rank", np.min)):
        print(f"{name:<16}" + "".join(f"{fn(ranks[c]):>12.1f}" for c in cols))
    for k in (1, 5, 10, 25):
        print(f"{'recall@' + str(k):<16}"
              + "".join(f"{(np.array(ranks[c]) <= k).mean():>12.1%}" for c in cols))
    print(f"\nchance median rank ~ {len(seqs) // 2}")
    print("embedding rank distribution, sorted: "
          + str([int(r) for r in sorted(ranks["emb"])]))

    report = {
        "schema_version": 1,
        "inputs": {
            "manifest_sha256": _sha256(MANIFEST),
            "embeddings_sha256": _sha256(pathlib.Path(
                "data/aug22_gallery_4160518/embeddings.json")),
            "image_count": len(paths),
        },
        "pair_count": len(pairs),
        "rank": {key: [float(value) for value in ranks[key]] for key in cols},
        "recall_at_25": {
            key: float((np.asarray(ranks[key]) <= 25).mean()) for key in cols
        },
    }
    if output:
        pathlib.Path(output).write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    args = parser.parse_args()
    main(args.output)
