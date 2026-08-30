# Additional Info form (judges / organizers)

Page:
`https://devpost.com/submit-to/30845-all-things-agentic-hackathon/manage/submissions/1144616-blue-toad-fleet/additional-info/edit`

Paste-ready answers live in `docs/DEVPOST.md` under **Additional Info**. This file is the checkbox rules. Do not invent a second copy of the answers here.

## Checkboxes

**Sponsor / Special Prizes — Startup Excellence:** leave unchecked unless the operator supplies (1) an incorporated organization name and (2) a corporate email. `Richmond General` in the organization field is the shop name, not an opt-in.

**Which Google SDK did you use?**
- Check: **Google GenAI SDK (`google-genai`)** — `src/appraiser/engine.py` `genai.Client(vertexai=True, ...)`.
- Do not check: Agent Development Kit (ADK), Antigravity SDK, Genkit.
- Other: leave blank.

**Which Google Cloud Service(s) did you use?**
- Check: **Cloud Run** (hosted console + cycle job), **Firestore** (`BTF_MEMORY_BACKEND=firestore`, `/health` `memory_backend`), **Pub/Sub** (Eventarc GCS `object.v1.finalized` uses Pub/Sub transport; `infra/provision_cycles.sh`).
- Do not check: Cloud SQL, Google Kubernetes (GKE).
- Vertex AI is used; it is not on this checkbox list. Do not invent a box.

**Which Google AI Models did you use?**
Must include Gemini 3.5 or newer. Also list models the code actually calls:
`Gemini 3.6 Flash, Gemini 3.5 Flash Lite, Gemini 2.5 Flash (fallback), Gemma 4, Gemini Embedding 2`.
The form currently showing only the three Gemini Flash names is incomplete — Gemma 4 is the curator voice (`gemma-4-26b-a4b-it-maas`); Embedding 2 is the reviewed reshoot-edge path.

## Bonus URLs

- Content must be public, not unlisted, and must say it was created for this hackathon. The blog at `docs/blog/index.html` already has that disclosure.
- Social post must include `#AllThingsAgentic`. `docs/blog/SOCIAL_POST.md` is draft copy. Do not paste a page URL; paste the post permalink after Scott publishes. Empty is honest if unpublished.
- Architecture diagram file: `docs/architecture_diagram.png` (already uploaded on the form if present).

## Login

Use the capture Chrome in `references/fill-form.md`. If the tab is `secure.devpost.com/users/login`, wait for the operator to sign in there, then fill. Do not guess remaining widgets. Do not treat the login wall as the end of the recipe.