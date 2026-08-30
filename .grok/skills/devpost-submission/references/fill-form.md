# Load `docs/DEVPOST.md` onto the live Devpost form

Drive a **signed-in** Chrome. `open_page` / anonymous fetch hits the login wall and cannot type. Checked 2026-08-29: the capture profile (`scripts/cdp_capture.py`) was NOT signed into Devpost — the operator's own Chrome (claude-in-chrome) was, and is the working surface. Try it first.

## Lessons from the 2026-08-29 fill (each one cost a correction)

- **The form's EXISTING content is a claims hazard, not a base.** The saved
  story and gallery predated the claims boundary: the old "About" carried the
  pole-barn Spatial Room Graph, the Topps `<14 day 4x` quote, July's $14,340
  A/B, "12 bids / $335 / $385.25", "flawless… sub-second", "160 tests"; four
  gallery captions repeated them, one asserted auto-send. Diff every field
  against `docs/SUBMISSION_CLAIMS.md` before assuming only additions are
  needed.
- **Vet gallery images by their PIXELS, not their filenames.**
  `docs/screenshots/01-gate-console.png` and `05-the-sheet.png` render the
  old console: "POLE BARN SHOWROOM TOPOLOGY", "12 BID(S)", AUTO-SEND badges,
  BT-181 allocated. No caption cures banned pixels. Use `00-raw-auction-gallery.png`,
  fresh `cdp_capture.py` shots of the live console `/` and `/walk`, and the
  Cloud-Run revisions capture instead.
- **Image captions cap at 140 characters** — the form flags overage with a
  red negative counter and refuses that caption on save.
- **Additional Info arrived pre-filled WRONG:** SDK was set to
  "Agent Development Kit (ADK)" and models listed only the three Flash names.
  A green step-checkmark does not mean the answers are right — enumerate the
  selects and verify against `additional-info.md` every time.
- **The Built-with tag widget is an autocomplete**: type, wait for the search
  dropdown to settle (~2s), then Enter. Rapid type+Enter silently drops tags.
- **Video demo link accepts only YouTube/Facebook/Vimeo/Youku URLs** — the
  GitHub MP4 does not satisfy it. Published: `https://youtu.be/PaLRNZLHi0c`
  (public, @threebatdrone, 2026-08-29). To upload a >10MB file the browser
  file-upload tool cannot carry it (10MB cap): click YouTube Studio's
  "Select files", then drive the native macOS dialog via System Events
  (Cmd+Shift+G → absolute path → Return → Return). Audience "not made for
  kids" was already the channel default.
- **Save & continue advances only when every required field passes** — the
  step indicator can lag one render behind; re-load the edit page and read
  values back to confirm persistence rather than trusting the header.

## Start the profile (once per machine boot)

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 --user-data-dir=$HOME/.btf-chrome-profile \
  --no-first-run --no-default-browser-check \
  "https://devpost.com/submit-to/30845-all-things-agentic-hackathon/manage/submissions/1144616-blue-toad-fleet/project_details/edit" &
```

If the tab is `secure.devpost.com/users/login`, **wait for the operator to sign in in that window**. Then continue. Do not invent credentials. Do not guess widgets that are not on the page.

## Project details

URL: `.../project_details/edit`

Fill from `docs/DEVPOST.md` **Form Fields Quick Reference** and **Project Story**. Visible labels on the page win over this file. Paste, do not paraphrase money.

| Visible control | Source |
|---|---|
| Tagline | DEVPOST tagline |
| Built with | Form Fields **Built with (Tags)** |
| Try it out | Form Fields **Try it out** links |
| Inspiration / What it does / How we built it / Challenges / Accomplishments / What we learned / What's next | matching DEVPOST headings |
| Demo video | `media/blue_toad_fleet_demo.mp4` |
| Gallery images | `docs/screenshots/00-raw-auction-gallery.png`, `01-gate-console.png`, `05-the-sheet.png`. Add `media/video_inputs/cloud_console/revisions.png` for Cloud Run proof. Skip `02-showroom-topology.png` (historical; do not present as a pole-barn map). |

**Save** (Update project). Do **not** click the hackathon **Submit** control unless the operator said to submit.

Read the saved page back against DEVPOST.md. Mismatched money or models → fix from the file, do not invent.

## Additional Info

URL: `.../additional-info/edit`

Paste from DEVPOST.md **Additional Info**. Checkbox rules: `additional-info.md`. Upload `docs/architecture_diagram.png` into the architecture-diagram control.

Save. Do not Submit unless asked.

## After save

Tell the operator which URLs were saved and that Submit was not clicked. Re-probe `/health` `git_commit` vs `HEAD` if any filled sentence claims the live console.
