# Capability probe — super-resolution, appraisal impact, embeddings

Probed 2026-08-21 against Vertex project `threebatdrone-prod-420`, `location="global"`.
This file supersedes the probe's original scratchpad write-up, which was reviewed
externally on 2026-08-21 and found to overstate two of its numbers. **Corrections
from that review are marked inline and carried into every figure below.** The
re-analysis is reproducible from `scripts/probes/`.

---

## Recommendation

| Question | Answer |
|---|---|
| Which image model for enhancement? | **None.** Do not add an upscaling stage. |
| Does the accuracy justify it? | **No.** Bicubic wins 47 of 48 comparisons, and the upscale wrote a false lens serial into an appraisal that the 560px original had read correctly. |
| Are embeddings worth building the room graph on? | **Yes.** `gemini-embedding-2` beats dHash, a colour-histogram baseline, and sequence proximity on every metric. |

### The decision rule, stated up front

Enhancement is rejected under a **zero-tolerance rule on fabricated evidence**, not
on an accuracy margin. One demonstrated case of a generated image inserting a false
serial that a downstream appraisal transcribed at unchanged confidence is sufficient
to reject the stage, because nothing in the pipeline can distinguish that record
from a true one. This rule is what the evidence below supports; it is *not* a claim
about how often fabrication occurs. See "What this sample cannot tell you".

---

## TASK 1 — Super-resolution scored against ground truth

**Lots (8, all of them named):** BT-001 (Topps baseball cards), BT-002 (estate
costume jewelry), BT-053 (vintage trumpet), BT-054 (35mm camera), BT-063 (graded
card), BT-189 (Pink Floyd poster), BT-235 (Century of Progress bottle), BT-408
(carnival glass). Selection rule: varied categories among the lots that exist at
both resolutions.

**Source** = 560x420 WebP from `data/aug22_gallery_4160518/images/`.
**Truth** = the 1200x900 estatesales JPEG (fetched to scratchpad, not committed).
PSNR and SSIM are computed on the luma channel.

### Correction: the original scoring silently stretched the model outputs

The first pass resized every image to 1200x900 unconditionally. The model outputs
are 1200x896 and 2400x1792 — aspect 1.3393, not 4:3 — so the model arms were
stretched vertically by 900/896 while the bicubic arm, already 4:3, was not. That
asymmetry favoured bicubic and its size was never quantified.

Re-scored on the common 4:3-cropped region at 1200x896, every arm cropped
identically (`scripts/probes/rescore_upscaling.py`):

| Model | PSNR Δ vs bicubic (as-shipped) | PSNR Δ (aspect-preserving) | SSIM Δ (aspect-preserving) |
|---|---|---|---|
| gemini-3-pro-image | −4.48 | **−1.01** | −0.0224 |
| gemini-3.1-flash-image | −4.56 | **−1.20** | −0.0235 |
| gemini-3.1-flash-lite-image | −5.24 | **−2.88** | −0.0491 |

**The stretch accounted for roughly 3.5 dB of the original ~4.5 dB gap** — about
three quarters of it for the flash and pro tiers. The original report's "mean PSNR
deficit 4.5–5.2 dB" was wrong and is withdrawn.

A search over integer alignment shifts (±6 px, scored on the overlap, taking the
model's best) returns **(0, 0) for every arm**, so misregistration is not a factor
and the remaining gap is real.

### Correction: "0 of 24, not one, on any lot" is false

Under fair normalization the count is **47 of 48 comparisons favouring bicubic, not
48 of 48**. The exception: `gemini-3-pro-image` on **BT-001** beats bicubic on PSNR,
26.80 vs 26.39 (+0.41 dB). It loses on SSIM for the same lot. The original absolute
claim is withdrawn; the direction of the result is unchanged.

Worth noting where the one exception landed: BT-001 is a **baseball-card lot**, and
card lots are exactly where fabricated text is most expensive.

### The qualitative result, which is the disqualifying one

Large, already-legible text survives intact — the Pink Floyd poster's date and
admission lines reproduce correctly in all three models, and the embossed "Century
of Progress" bottle text stays correctly illegible in all three. The models did not
invent readable text where none was resolvable.

**Small, marginally-legible text is fabricated** — and that is the text an appraisal
turns on. Reading the same pixels on BT-054 (Minolta 35mm):

| Marking | Truth | bicubic | 3.1-flash-lite | 3.1-flash | 3-pro |
|---|---|---|---|---|---|
| Lens serial | 2331770 | 2331770 | 2331770 | 3231770 | 2231770 |
| Lens designation | ROKKOR-PF | ROKKOR-PF | ROKKOR-PP | ROKKOR-PF | ROKKOR-PP |
| Shutter dial | 1000 | 1000 | 1911 | 166/1880 | 1880 |
| Aperture | 1:2 | 1:2 | 1:9 | 1:2 | 1:2 |

On the graded card BT-063, `gemini-3.1-flash-image` rendered the brand **1977 TOFPS**
— crisply, confidently, wrongly. "TOPPS" is the single most value-bearing word on a
card lot.

The failure mode is the worst possible shape for this project: **the fabrication is
sharper and more legible than the truth**, so it reads as better evidence while being
false. Bicubic does not synthesize new detail — it stays blurry, which a reader can
still misjudge, but it cannot manufacture a digit that was not in the source.

---

## TASK 2 — Does upscaling change the appraisal?

**Method.** `src.appraiser.AppraisalEngine.appraise_lot`, three arms per lot, with
`category_hint` and `DEFAULT_STANDING_RULES` on every call. Arm (b) is the
pro-image output resampled to 1200x900, so the only difference from arm (c) is
pixel content, not resolution. Appraisal resolved to `gemini-3.6-flash` on all 9 calls.

### BT-054, 35mm camera — the upscale corrupted the record

| Arm | `marks_observed` | confidence |
|---|---|---|
| (a) 560x420 source | ROKKOR-PF, 1:2 f=45mm, **2331770**, 1000, minolta | medium |
| (b) pro-image upscale | minolta, MINOLTA ROKKOR-PF 1:2 f=45mm, **2231770** | medium |
| (c) true 1200x900 | MINOLTA ROKKOR-PF 1:2 f=45mm, **2331770**, 1000 | medium |

The appraiser transcribed the fabricated serial exactly as the image model drew it.
The 560x420 original — the photo we already have — got it right; the upscale made it
wrong, and dropped the `1000` shutter marking consistent with pro-image having
rendered it `1880`. **Confidence was medium in all three arms**, so a gate keyed on
confidence would pass the false serial through silently.

BT-002 (jewelry): `marks_observed` is empty at all three resolutions — going
560→1200 does not make a costume-jewelry hallmark legible by any route. BT-063
(graded card): all three arms read the grade correctly; the upscale arm dropped
`#77` and the copyright line the other two captured.

### What this sample cannot tell you — and the review was right about it

Each arm is **one call at `temperature=0.1` with no seed**
(`src/appraiser/engine.py:201`). Nine single stochastic samples cannot estimate how
*often* a given arm fabricates or drops a marking. This section is evidence that
fabrication **can** propagate into a record undetected — which under the zero-tolerance
rule above is sufficient — and it is **not** an estimate of a fabrication rate.
Repeating each arm several times in randomized order and reporting field-level
exact-match rates is the open experiment; it has not been run.

Likewise, 8 lots with one generation per model supports *"none of these 24 generated
samples improved fidelity"*. It does **not** support *"these models never improve
fidelity"*. The single jewelry lot shows no benefit for that lot in that run; it does
not confirm a general result about hallmarks.

---

## TASK 3 — Embeddings for the room graph

**Method.** All 462 gallery photos embedded with `gemini-embedding-2` (3072-d;
the model accepts image Parts directly — confirmed, not assumed). Passing a list of
images to `embed_content` returns **one fused vector, not one per image**, so this is
necessarily one call per photo. Distance is cosine on L2-normalised vectors.

**Ground truth** = 14 same-caption pairs at least 10 frames apart, taken from
`manifest.json`. The gap floor is what makes this a zone-grouping test rather than
near-duplicate matching.

### Baselines — three of them, not one

The original probe compared only against dHash. dHash is a *near-duplicate* hash and
is the wrong tool for "same room, different framing", so beating it says little. Two
harder baselines were added on review (`scripts/probes/task3_baselines.py`):

- **seq** — rank purely by |sequence difference|. If a photographer shoots a zone in
  one pass, frame proximity alone is a strong room-graph signal.
- **colorhist** — 32³ RGB histogram, chi-square distance. The classic
  scene-similarity baseline, and much stronger than dHash here.

| metric | gemini-embedding-2 | dHash | seq proximity | colour hist |
|---|---|---|---|---|
| median rank | **10.5** | 167.8 | 197.8 | 63.5 |
| mean rank | **14.5** | 169.8 | 210.6 | 123.8 |
| worst rank | **50** | 408.5 | 452 | 349 |
| recall@1 | **21.4%** | 0.0% | 0.0% | 7.1% |
| recall@5 | **42.9%** | 0.0% | 0.0% | 14.3% |
| recall@10 | **50.0%** | 0.0% | 0.0% | 14.3% |
| recall@25 | **85.7%** | 0.0% | 0.0% | 35.7% |

**On the dHash figures:** Hamming distances are integers over ~460 candidates, so
dozens of photos share a distance and the true partner's position inside its tie
block is arbitrary — it depends on the sort algorithm, not on the method. Every rank
above is therefore the tie-block midpoint (standard average-rank convention). The
probe's first pass used a naive sort and reported a dHash median of 165.0; the
reproducible tie-aware figure is 167.8. The difference is bookkeeping, not signal —
dHash never places a partner in the top 25 under either convention.

Chance median rank ≈ 231. **Sequence proximity never places a true partner in the
top 25** — the pairs are ≥10 frames apart by construction and 12 of 14 are more than
50 apart, so adjacency does not explain the result. The colour histogram is a real
step up from dHash and still loses to embeddings on every row.

**Full rank distribution** (embeddings, all 14 pairs, sorted):
1, 1, 1, 2, 3, 4, 9, 12, 16, 17, 18, 21, 48, 50.

### It groups by place, not by category

The top neighbours of seq 2 are `181, 180, 182, 179, 183, 178, 177` — a contiguous
run, 176-183: the photographer's pass at that display case. Seq 2 (frame 2, 174
frames earlier) links into that block. Seq 87, captioned "costume jewelry", is a
*plastic bin of tangled jewelry* — same category, different physical lot — and ranks
only #9 at cos 0.808, below the entire true-zone block. Same-place frames outrank
same-category frames, which is the property a room graph needs.

**Caveat, stated plainly:** same-caption is a proxy for same-zone. The (2, 181) pair
and the seq-87 discriminator were verified visually; the other 13 pairs rest on the
caption. Generic captions like "smalls" and "toys" — the two worst performers, at
ranks 48 and 50 — may well be different physical piles, which would mean the
aggregate understates true performance.

---

## Servability — what was actually exercised

Six models were **listed** at `location="global"` via `client.models.list()`.
Listing proves discoverability, not that inference succeeds under this project's
permissions, quota and request shape. Five of the six completed real inference:

| Model | Exercised? |
|---|---|
| gemini-3-pro-image | yes — 8 generations |
| gemini-3.1-flash-image | yes — 8 generations |
| gemini-3.1-flash-lite-image | yes — 8 generations |
| gemini-3.6-flash | yes — 9 appraisal calls |
| gemini-embedding-2 | yes — 462 embedding calls |
| **gemini-3.7-flash** | **listed only — never called** |

## Cost and quota, from the call log

| Model | calls | prompt tok | output tok | total tok | mean s/call |
|---|---|---|---|---|---|
| gemini-3.1-flash-lite-image | 8 | 1269 | 1120 | 2389 | 5.3 |
| gemini-3.1-flash-image | 8 | 1269 | 1680 | 2949 | 18.8 |
| gemini-3-pro-image | 8 | 709 | 1120 | 2128 | 29.0 |

Task 1 total: 24 images, 59,724 tokens, 425 s of successful call time. Task 2: 9
calls; the repo's own `routing.estimate_cost_usd` puts 9 appraisal-tier calls at
$0.0473. Task 3: 462 embedding calls.

USD list prices for the image and embedding tiers are **not** recorded in the repo —
`src/appraiser/routing.py` prices only the triage and appraisal text tiers — and were
not verified against an external source, so no dollar figure is put on Tasks 1 and 3.

**Quota note:** roughly 14 of 24 upscales needed 429 `RESOURCE_EXHAUSTED` backoff
retries, and `image_size="2K"` is rejected outright by `gemini-3.1-flash-lite-image`
(400 INVALID_ARGUMENT) while the flash and pro tiers accept it. Any batch use of
these models needs backoff built in from the start.

---

## Open, and honestly unresolved

1. **The SSIM implementation is unvalidated against a reference.** It is a direct
   numpy implementation (11x11 Gaussian, σ=1.5, C1/C2 per Wang et al. 2004) because
   scipy is not in `.venv`. The re-analysis reuses that same module, so it inherits
   any error in it. Nothing here has checked it against a known fixture.
2. **The repeat run has not happened** — one stochastic sample per arm, as above.
3. **11 of 14 Task-3 pairs rest on the caption**, not on visual confirmation.

## What follows from this

1. **Do not build an enhancement stage.** It costs money and wall-clock to make the
   record *less* true.
2. **If enhancement is ever revisited, bicubic is the honest baseline** — it wins 47
   of 48 comparisons and cannot fabricate a digit.
3. **Build the room graph on `gemini-embedding-2`.** Keep dHash for what it is good
   at: cross-gallery near-duplicate matching at Hamming ≤1/64.
4. **A cheap guard worth adding:** the same lot photographed in two frames should
   produce the same `marks_observed`. Seq 2/181 and the 176–183 block give a free
   consistency check on the appraiser — disagreement between two views of one tray
   is a signal worth surfacing.
