"""Re-score the super-resolution probe with an aspect-preserving normalization.

The probe's first pass sent every image through a scorer that did an unconditional
`resize((1200, 900))` -- a SILENT STRETCH. The model outputs are 1200x896 and
2400x1792 (aspect 1.3393); the truth and the bicubic baseline are 4:3 (1.3333). So
the model arms were stretched vertically by 900/896 and the bicubic arm was not.
That asymmetry favours bicubic, and its size was never quantified. It turned out to
be about 3.5 dB of a 4.5 dB gap.

Three normalizations over the same 8 lots:

  A  as-shipped        stretch everything to 1200x900
  B  aspect-preserving compare on the common 4:3-cropped region at 1200x896,
                       every arm -- including bicubic -- cropped identically
  C  B + best global integer shift in [-6, 6], scored on the overlap, taking the
                       model's BEST score, so an alignment argument gets its
                       strongest form. In practice this returns (0, 0) everywhere.

The probe artifacts (truth JPEGs, model outputs, 560px sources, upscale_log.json,
baseline.json) are NOT committed -- they are ~6 MB of third-party imagery. Pass the
directory holding them as argv[1]. See docs/CAPABILITY_PROBE.md for the results.

    .venv/bin/python scripts/probes/rescore_upscaling.py <probe-artifacts-dir>
"""
import json
import pathlib
import sys

import numpy as np
from PIL import Image

W, H_4X3, H_CROP = 1200, 900, 896   # 896 = the model arms' own aspect at width 1200
SHIFT_RADIUS = 6


def _gauss1d(size=11, sigma=1.5):
    x = np.arange(size) - (size - 1) / 2.0
    g = np.exp(-(x ** 2) / (2.0 * sigma ** 2))
    return g / g.sum()


def _filt(img, k):
    out = np.apply_along_axis(lambda m: np.convolve(m, k, mode="valid"), 0, img)
    return np.apply_along_axis(lambda m: np.convolve(m, k, mode="valid"), 1, out)


def ssim(a, b, L=255.0):
    """Mean SSIM over the luma channel. 11x11 Gaussian, Wang et al. 2004.

    The implementation is checked against the closed-form constant-field fixture
    in ``artifacts/signature_upscale_probe/ssim_reference_fixture.json``.  For a
    constant field, the Wang et al. equation reduces independently to its
    luminance term, making the expected value exact without a second library.
    """
    a, b = a.astype(np.float64), b.astype(np.float64)
    k = _gauss1d()
    C1, C2 = (0.01 * L) ** 2, (0.03 * L) ** 2
    mu_a, mu_b = _filt(a, k), _filt(b, k)
    mu_a2, mu_b2, mu_ab = mu_a * mu_a, mu_b * mu_b, mu_a * mu_b
    num = (2 * mu_ab + C1) * (2 * (_filt(a * b, k) - mu_ab) + C2)
    den = ((mu_a2 + mu_b2 + C1)
           * ((_filt(a * a, k) - mu_a2) + (_filt(b * b, k) - mu_b2) + C2))
    return float((num / den).mean())


def psnr(a, b, L=255.0):
    mse = float(((a.astype(np.float64) - b.astype(np.float64)) ** 2).mean())
    return float("inf") if mse == 0 else float(10.0 * np.log10(L * L / mse))


def _luma(im):
    a = np.asarray(im.convert("RGB")).astype(np.float64)
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def stretch(path):
    """Normalization A: what the first pass did. Ignores aspect ratio."""
    im = Image.open(path)
    return _luma(im if im.size == (W, H_4X3) else im.resize((W, H_4X3), Image.BICUBIC))


def aspect(path):
    """Normalization B: resize to width 1200 preserving the file's OWN aspect, then
    centre-crop to 1200x896. Nothing is stretched; a 4:3 source loses 2 rows top
    and bottom, and every arm loses exactly the same rows."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    im = im.resize((W, max(1, round(h * W / w))), Image.BICUBIC)
    top = (im.size[1] - H_CROP) // 2
    return _luma(im.crop((0, top, W, top + H_CROP)))


def best_shift(t, m, r=SHIFT_RADIUS):
    """Normalization C: max PSNR over integer shifts, scored on the overlap only."""
    best = None
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            a = t[max(0, dy):t.shape[0] + min(0, dy), max(0, dx):t.shape[1] + min(0, dx)]
            b = m[max(0, -dy):m.shape[0] + min(0, -dy),
                  max(0, -dx):m.shape[1] + min(0, -dx)]
            rows, cols = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
            a, b = a[:rows, :cols], b[:rows, :cols]
            p = psnr(a, b)
            if best is None or p > best[0]:
                best = (p, ssim(a, b), dx, dy)
    return best


def main(artifacts):
    art = pathlib.Path(artifacts)
    base = {r["seq"]: r for r in json.load(open(art / "baseline.json"))}
    recs = [r for r in json.load(open(art / "upscale_log.json")) if r.get("ok")]

    out = []
    for r in recs:
        b, src = base[r["seq"]], art / "src560" / f"{r['seq']:03d}.webp"
        row = {k: r[k] for k in ("model", "seq", "lot_id", "caption")}
        row["dims"] = r["dims"]
        for name, norm in (("A", stretch), ("B", aspect)):
            t, m, bc = norm(b["truth"]), norm(r["path"]), norm(src)
            row[name] = dict(psnr=psnr(t, m), ssim=ssim(t, m),
                             bic_psnr=psnr(t, bc), bic_ssim=ssim(t, bc))
        t, m, bc = aspect(b["truth"]), aspect(r["path"]), aspect(src)
        pm, sm, dx, dy = best_shift(t, m)
        pb, sb, bdx, bdy = best_shift(t, bc)
        row["C"] = dict(psnr=pm, ssim=sm, shift=[dx, dy],
                        bic_psnr=pb, bic_ssim=sb, bic_shift=[bdx, bdy])
        out.append(row)
        print(f"  scored {r['model']:<28} seq {r['seq']:>3}", flush=True)

    json.dump(out, open(art / "rescore.json", "w"), indent=2)

    print(f"\n{'model':<30}{'norm':>6}{'PSNR':>8}{'bicub':>8}{'delta':>8}   "
          f"{'SSIM':>8}{'bicub':>8}{'delta':>9}{'wins':>8}")
    for model in sorted({r["model"] for r in out}):
        rs = [r for r in out if r["model"] == model]
        n = len(rs)
        for norm in ("A", "B", "C"):
            mp = sum(r[norm]["psnr"] for r in rs) / n
            bp = sum(r[norm]["bic_psnr"] for r in rs) / n
            ms = sum(r[norm]["ssim"] for r in rs) / n
            bs = sum(r[norm]["bic_ssim"] for r in rs) / n
            wins = sum((r[norm]["psnr"] > r[norm]["bic_psnr"])
                       + (r[norm]["ssim"] > r[norm]["bic_ssim"]) for r in rs)
            print(f"{model if norm == 'A' else '':<30}{norm:>6}{mp:>8.2f}{bp:>8.2f}"
                  f"{mp - bp:>+8.2f}   {ms:>8.4f}{bs:>8.4f}{ms - bs:>+9.4f}"
                  f"{wins:>5}/{2 * n}")
        print()

    shifts = {tuple(r["C"]["shift"]) for r in out} | {tuple(r["C"]["bic_shift"]) for r in out}
    print(f"alignment shifts found: {shifts}"
          + ("  -> misregistration is not the explanation"
             if shifts == {(0, 0)} else "  -> some arms ARE shifted"))
    for norm in "ABC":
        w = sum((r[norm]["psnr"] > r[norm]["bic_psnr"])
                + (r[norm]["ssim"] > r[norm]["bic_ssim"]) for r in out)
        print(f"  norm {norm}: a model beat bicubic on {w} of {2 * len(out)} comparisons")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
