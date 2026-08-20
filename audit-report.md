# Adversarial Audit — the Aug 20 Vertex gate

**Target:** one real `generate_content` call from `threebatdrone-prod-420`, on a 3.5+ model,
returning structured output valid against `APPRAISAL_SCHEMA`, for one real photo.
**Run:** 2026-08-19, against the working tree at `a5f4fbe`.
**Verdict:** **the gate cannot currently be attempted.** Three hard blockers, all verified
by command, none of them in the code under review.

Everything below was checked, not inferred. Where the first pass of this audit guessed, it
is marked and corrected.

---

## 1. Verified blockers

### B1 — the Vertex SDK is not installed
```
$ ls .venv/lib/python3.14/site-packages
_pytest  iniconfig  packaging  pip  pluggy  py.py  pygments  pytest
```
`google-genai`, `google-cloud-aiplatform` and `google-auth` are all absent. The venv holds
the test runner and nothing else. There is no client library to call Vertex with.

Secondary risk on the same line: the venv is **Python 3.14.4**. `google-genai` on 3.14 is
unproven here — if wheels are missing you are building from source on gate day. Check this
first, because it is the failure that eats an afternoon.

### B2 — there are no Application Default Credentials
```
$ ls ~/.config/gcloud/application_default_credentials.json
ls: ...: No such file or directory
```
`gcloud auth list` shows `beilsco@gmail.com` active and `gcloud config get-value project`
already returns `threebatdrone-prod-420`, so the CLI is fine. But the SDK does not read CLI
credentials — it reads ADC, which has never been created. Every call will 403 until it is.

### B3 — the photo does not exist
```
$ gcloud storage ls gs://blue-toad-intake/
ERROR: (gcloud.storage.ls) gs://blue-toad-intake not found: 404.
```
All 304 URIs in `data/2026-08-22/manifest.json` point into that bucket. There are also **no
image files anywhere in the repo** (`find` over the tree, excluding `.venv`/`.git`, returns
nothing). The manifest was written as a plan, and reads as a record.

The gate says *one real photo*. There isn't one. The gallery is at
`bluetoadauctions.com/morephotos.html` (NOTES.md:151) — pulling a single JPEG from there is
the shortest path, and the script below takes an `https://` URL directly so nothing needs a
bucket to exist first.

---

## 2. A false provenance claim in the code

`src/appraiser/schema.py:26` — `to_vertex`:

> Proven against the live endpoint 2026-08-19 — the schemas below 400 without this translation.

`NOTES.md:194` — same day:

> **The schedule is now the problem, not the design.** Zero lines have touched Vertex.

Both cannot be true, and B1–B3 say which one is. The translation may well be *right*; it has
not been *proven*, and a docstring that claims a live verification is exactly the kind of
thing that stops the next person re-checking it. Either run the gate and keep the sentence,
or cut the sentence today.

---

## 3. Corrections to the first pass of this audit

- **`to_vertex()` does not recurse into nested array items** — **wrong.** It recurses through
  `properties` and `items` both, and I confirmed the output directly: `maker` becomes
  `{"type": "string", "nullable": true}`, and `questions.items.properties.kind` survives with
  its enum intact. The input is not mutated. There is no bug here; do not spend gate day on it.
- **`demo/fixtures/crock.jpg`** — invented. No such file, and no fixture image exists (B3).
- **"parses cleanly into the `Appraisal` dataclass"** — it does not, and that is a real gap
  rather than a defect in either piece. `APPRAISAL_SCHEMA` emits `marks_observed`,
  `condition_notes`, `condition_penalty`, `value_magnitude_hint`, `questions`;
  `Appraisal` takes `lot_id, category, identification, attributes, confidence,
  est_value_hint`. No adapter exists between them. That seam is Aug 21 work, not Aug 20
  work — the gate should assert against the *schema*, which is what the script does.

Still standing from the first pass: `VERTEX_LOCATION=global` is load-bearing (the 3.5+
models are not in every regional endpoint), and `genai.Client(vertexai=True, ...)` is the
right entry point — the legacy `aiplatform` SDK is regional and will fight you over `global`.

One open item I could not settle without a live call: `condition_penalty` carries
`minimum`/`maximum`, which `to_vertex` passes through verbatim. Vertex's OpenAPI subset has
historically been picky about numeric constraints. If the call 400s on the schema, drop
those two keys first — the range is re-checked downstream in `bidmath` anyway.

---

## 4. The gate, as an executable

`scripts/test_vertex_live.py` (written, 197 lines). It preflights the three blockers above
before spending a token, accepts a local path / `https://` URL / `gs://` URI, sends real
image bytes, and validates the response against `APPRAISAL_SCHEMA` — required keys, both
enums, list types, the `[0,1]` penalty range, and every nested `questions[]` field.

The validator is itself tested: a clean payload returns no problems, and a deliberately
corrupted one produces exactly the seven expected violations. A gate nobody has watched
reject something is not a gate.

Latency is reported against the 5s budget but **not** enforced — a slow pass is still a
pass, and fan-out throughput is an Aug 23 problem.

```bash
cd /Users/scottybe/workspace/blue-toad-fleet && pip install google-genai && gcloud auth application-default login && python scripts/test_vertex_live.py --photo <one-real-photo-url> --caption "Vintage Topps Baseball Cards"
```

Exit codes: `0` pass · `1` gate failed · `2` preflight failed. Current state exits `2` on B1.

---

## 5. Order of operations

**Updated 2026-08-19 after execution. Blocker 1 is cleared; blocker 3 changed shape.**

1. ~~`pip install google-genai`~~ — **done.** `google-genai 2.19.0` installed clean on
   Python 3.14.4; `pydantic-core` and `websockets` both ship `cp314` arm64 wheels and
   `cryptography` used `cp311-abi3`. Nothing compiled. **The 3.12 fallback is unnecessary.**
2. `gcloud auth application-default login` — **still open, and needs a human.** It opens a
   browser OAuth flow; it cannot be run from a non-interactive session.
3. ~~Get one JPEG off `bluetoadauctions.com/morephotos.html`~~ — **withdrawn, this was
   wrong.** That page carries no photos. It is a 5 KB shell that injects an AuctionZip feed
   widget client-side (`az_feed_uid=35615`, `az_feed=129`); its only image is a Facebook
   badge. The photos live on AuctionZip, and NOTES.md:78 is a standing rule — *"No AuctionZip
   fetching, ever"* — which README.md:137 also states publicly. Fetching it would break a
   documented promise, and it 403s automated requests regardless.

   The designed path is the **sanctioned bucket drop**, and blocker 3 is really: that drop
   has never happened and `gs://blue-toad-intake` was never created. That is an owner action.

   **To unblock the gate today without touching AuctionZip**, use a photo the operator owns.
   `richmondgeneral/items/RG-0012/hero.png` (1.2 MB) is a Hallmark Keepsake Lionel GG-1
   locomotive — a real photo of a real object in `railroad`, one of the shop's own buy
   categories. It proves the integration; it just is not an auction lot.
4. Run the gate.
5. If it 400s on the schema: drop `minimum`/`maximum` from `condition_penalty`, retry.
   `bidmath` re-clamps the range anyway.
6. If it 404s on the model: `gemini-3.5-flash-lite` is the cheaper second try; a GA model
   proves the *integration* even if it does not satisfy the 3.5+ rule — prove transit first,
   then swap the string.
7. Paste the passing output and its latency into NOTES.md, and date the `to_vertex` docstring.

```bash
cd /Users/scottybe/workspace/blue-toad-fleet && .venv/bin/python scripts/test_vertex_live.py --photo /Users/scottybe/workspace/richmondgeneral/items/RG-0012/hero.png --caption "Hallmark Keepsake Lionel GG-1 Locomotive"
```
