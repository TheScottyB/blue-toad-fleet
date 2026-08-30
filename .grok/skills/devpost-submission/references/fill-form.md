# Load `docs/DEVPOST.md` onto the live Devpost form

Drive a **signed-in** Chrome. `open_page` / anonymous fetch hits the login wall and cannot type. The working Chrome is the same capture profile as `scripts/cdp_capture.py`.

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
