# Submission video workflow

`media/video_manifest.json` is the single declaration of every source,
recording, intermediate, narration track, and final output. Only
`scripts/assemble_final.py` may publish `media/blue_toad_fleet_demo.mp4`.

## Prerequisites

- Python dependencies from `requirements.txt` and `requirements-dev.txt`
- Node dependencies from `package-lock.json`
- Chrome, FFmpeg/FFprobe, and the Google Cloud CLI
- An authenticated read-only `gcloud` session for the Cloud Run proof
- `ELEVENLABS_API_KEY` only when regenerating narration
- The complete sanctioned gallery image drop referenced by the source manifest

## Stages

```bash
# Run the full tests, collect current facts, capture terminal proof,
# and render facts-driven cards/pages.
make video-prepare

# Generate new facts-resolved narration (this calls ElevenLabs).
.venv/bin/python scripts/video_pipeline.py narration

# Record the local gallery, grouping animation, live console, and proof terminal.
make video-record

# Normalize the four recordings and apply the declared lower thirds.
make video-compose

# Build and atomically publish the final cut.
.venv/bin/python scripts/video_pipeline.py assemble

# Non-mutating technical verification.
make video-verify
```

`make video` runs those stages end to end, including the external narration
request. Run it only when the copy is frozen and the live Cloud Run console is
ready to record.

## Failure behavior

- Facts are not published unless the full local test suite passes.
- Renderers reject facts whose hashed gallery, pipeline, model-output, or script
  sources have changed.
- Each Playwright page records into its own temporary directory and publishes
  only the video handle attached to that page.
- Missing anchors, challenge/sign-in pages, incomplete gallery images, missing
  terminal output, and failed commands stop the workflow.
- Beat durations come from FFprobe. Footage shorter than narration fails unless
  the manifest explicitly permits a bounded final-frame pad.
- The previous final MP4 remains intact until its replacement has one video
  stream, an audio stream, the declared dimensions and duration, and a size
  below the repository limit.
