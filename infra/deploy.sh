#!/usr/bin/env bash
# Deploy the fleet to Cloud Run. Idempotent; safe to re-run.
set -euo pipefail
: "${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
REGION="${CLOUD_RUN_REGION:-us-central1}"

echo "==> enabling services"
gcloud services enable run.googleapis.com pubsub.googleapis.com \
  firestore.googleapis.com aiplatform.googleapis.com \
  secretmanager.googleapis.com cloudkms.googleapis.com \
  eventarc.googleapis.com cloudscheduler.googleapis.com \
  --project "$GOOGLE_CLOUD_PROJECT"

echo "==> TODO: topics, subscriptions with dead-letter, service accounts, deploys"
echo "    Filled in as components land. See docs/BROKER.md for the Broker's IAM shape."
