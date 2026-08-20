#!/usr/bin/env bash
# Deploy the Blue Toad Fleet to Google Cloud Run. Idempotent; safe to re-run.
set -euo pipefail

GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-threebatdrone-prod-420}"
REGION="${CLOUD_RUN_REGION:-us-central1}"
SERVICE_NAME="blue-toad-fleet"

echo "==> [1/3] Enabling Google Cloud Services on project: $GOOGLE_CLOUD_PROJECT"
gcloud services enable run.googleapis.com aiplatform.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com \
  --project "$GOOGLE_CLOUD_PROJECT"

echo "==> [2/3] Building and deploying $SERVICE_NAME to Cloud Run ($REGION)..."
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT="$GOOGLE_CLOUD_PROJECT",VERTEX_LOCATION=global \
  --project "$GOOGLE_CLOUD_PROJECT"

echo "==> [3/3] Fetching service status and public URL..."
URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --project "$GOOGLE_CLOUD_PROJECT" --format='value(status.url)')
echo "=================================================================="
echo "==> [✓] BLUE TOAD FLEET IS LIVE ON GOOGLE CLOUD RUN!"
echo "==> Live Gate Console: $URL"
echo "==> Health Endpoint:  $URL/health"
echo "==> Sourcing API:     $URL/api/lots"
echo "=================================================================="
