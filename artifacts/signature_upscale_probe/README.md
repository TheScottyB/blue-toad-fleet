# Peyton Manning signature upscaling probe

## Conclusion

This crop supports the narrower claim that generative enlargement is not safe as
authoritative evidence. It also supports the operator's observation that the
models can work intermittently: Gemini 3.1 Flash repetition 2 slightly beat
Lanczos on signature-region PSNR (27.65 vs. 27.55 dB), but it lost on
signature-region SSIM (0.7907 vs. 0.8179) and on both whole-crop metrics. No
generative result beat the best classical method on both metrics.

Four identical Gemini 3.1 Flash requests produced visibly and measurably
different reconstructions. Their pairwise signature-region SSIM was
0.8335–0.8456. More importantly, those outputs agreed with each other more than
any one agreed with ground truth (0.7806–0.7907), showing a shared reconstruction
bias as well as run-to-run variation.

The OpenAI image edits were the clearest failures: both redrew the autograph and
fabric into crisp synthetic detail. Two identical low-input runs varied widely,
scoring 12.22 dB / 0.3693 SSIM and 18.44 dB / 0.5644 SSIM in the signature
region.

## Inputs and alignment

- Low-resolution input: AuctionZip's 560x420 image already cached at
  `data/aug22_gallery_4160518/images/004_838421497.jpg`.
- Ground truth: the matching 1200x900 EstateSales image saved as
  `source/full_1200.jpg`.
- Low crop: normalized source rectangle `(x=196, y=126, w=126, h=168)`, rotated
  clockwise to 168x126.
- Truth crop: the exact 15:7-scaled rectangle
  `(x=420, y=270, w=270, h=360)`, rotated clockwise to 360x270.

The 1200x896 Gemini outputs were padded by two white pixels at the top and bottom
to 1200x900 before resizing to 360x270. They were not stretched to change aspect
ratio. The OpenAI output was an exact 4:3 image and was resized directly.

## Methods

Classical variants were produced with ImageMagick at 360x270:

- nearest-neighbor (`Point`)
- bilinear (`Triangle`)
- bicubic (`Catrom`, equivalent to the common a=-0.5 cubic kernel)
- Lanczos
- RobidouxSharp
- bicubic plus a mild unsharp mask

Generative variants used the same input crop and preservation prompt:

- Gemini 3.1 Flash Lite Image, one run
- Gemini 3.1 Flash Image, four identical low-input runs
- Gemini 3 Pro Image, one run
- OpenAI built-in image edit, two low-input runs

All Gemini calls used `temperature=0.0`. Image-model sampling remains
non-deterministic despite that setting.

The OpenAI arm used the built-in image-editing tool with the same core request:
"Faithfully upscale the exact input crop" while preserving the exact crop,
geometry, orientation, signature strokes, ink gaps, threads, wrinkles, seams,
colors, boundaries, and all ambiguity; it explicitly prohibited invented
strokes, restored letters, synthetic text, added fabric detail, reframing,
cropping, rotation, and perspective changes.

## Scores

PSNR and SSIM are computed on 8-bit luma. SSIM uses an 11x11 Gaussian window,
sigma 1.5, and Wang et al. C1/C2 constants. The signature ROI is
`(left=0, top=25, right=275, bottom=145)` in the 360x270 normalized crop.

| Variant | ROI PSNR | ROI SSIM | Whole PSNR | Whole SSIM |
|---|---:|---:|---:|---:|
| Bicubic + unsharp | 27.50 | **0.8193** | 29.32 | **0.8051** |
| Lanczos | 27.55 | 0.8179 | **29.39** | 0.8046 |
| Bicubic | 27.37 | 0.8165 | 29.22 | 0.8038 |
| RobidouxSharp | 27.11 | 0.8114 | 29.01 | 0.8007 |
| Bilinear | 26.85 | 0.8068 | 28.77 | 0.7973 |
| Gemini 3.1 Flash r2 | **27.65** | 0.7907 | 26.78 | 0.7400 |
| Gemini 3.1 Flash r3 | 27.06 | 0.7896 | 26.39 | 0.7434 |
| Nearest | 25.60 | 0.7877 | 27.44 | 0.7804 |
| Gemini 3.1 Flash r1 | 27.51 | 0.7844 | 26.76 | 0.7357 |
| Gemini 3.1 Flash r4 | 26.95 | 0.7806 | 26.33 | 0.7352 |
| Gemini 3 Pro r1 | 26.28 | 0.7550 | 25.93 | 0.7071 |
| Gemini 3.1 Flash Lite r1 | 26.44 | 0.7301 | 26.15 | 0.6909 |
| OpenAI image edit r2 | 18.44 | 0.5644 | 19.06 | 0.5345 |
| OpenAI image edit r1 | 12.22 | 0.3693 | 13.24 | 0.3915 |

## Visual findings

- Classical methods preserve ambiguous strokes as ambiguous. Bicubic + unsharp
  and Lanczos are the strongest choices for inspection.
- Gemini sometimes creates a more legible-looking signature, but it changes the
  fabric weave, ink thickness, gaps, terminal loop, and isolated ink mark to the
  right of the signature.
- The repeated Gemini Flash outputs share a common reconstructed signature while
  differing in smaller stroke and texture details. Agreement between generated
  runs is therefore not independent corroboration.
- OpenAI's edit strongly reconstructs both the weave and handwriting. It is a
  useful demonstration of apparent clarity becoming fabricated evidence.

## Artifacts

- `comparisons/classical_montage.png` — truth and classical methods
- `comparisons/generative_montage.png` — truth and generative methods
- `comparisons/signature_roi_montage.png` — enlarged autograph comparison
- `comparisons/low_input_repeat_montage.png` — source-first full-crop sheet
- `comparisons/low_input_repeat_signature_montage.png` — source-first signature sheet
- `comparisons/difference_montage.png` — fixed-scale (4x) luma differences
- `scores.json` — all scores and Gemini repeat-consistency results
- `vertex_runs.json` — model names, output dimensions, and hashes
- `vertex_repeat_runs.json` — fresh fourth Gemini Flash run and hash
- `score_variants.py` — reproducible metric implementation
- `run_vertex_edits.py` — exact Vertex requests and prompt

## Recommended use

Use Lanczos or mild bicubic sharpening for human inspection. If a generative
variant is shown at all, label it as a non-evidentiary reconstruction and never
accept a stroke visible only in that variant.
