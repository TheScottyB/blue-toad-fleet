#!/usr/bin/env bash
# Provision the durable cycle bucket, processor job, and READY event trigger.
set -euo pipefail

GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-threebatdrone-prod-420}"
REGION="${CLOUD_RUN_REGION:-us-central1}"
SERVICE_NAME="${BTF_SERVICE_NAME:-blue-toad-fleet}"
JOB_NAME="${BTF_CYCLE_JOB:-blue-toad-cycle-processor}"
BUCKET="${BTF_CYCLE_BUCKET:-${GOOGLE_CLOUD_PROJECT}-blue-toad-cycles}"
TRIGGER_NAME="${BTF_CYCLE_TRIGGER:-blue-toad-cycle-ready}"
RUNTIME_ACCOUNT_NAME="${BTF_RUNTIME_ACCOUNT_NAME:-blue-toad-fleet-runtime}"
RUNTIME_ACCOUNT="${RUNTIME_ACCOUNT_NAME}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"

echo "==> Enabling cycle-processing APIs"
gcloud services enable \
  run.googleapis.com aiplatform.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com firestore.googleapis.com storage.googleapis.com \
  eventarc.googleapis.com pubsub.googleapis.com iamcredentials.googleapis.com \
  --project "$GOOGLE_CLOUD_PROJECT"

if ! gcloud iam service-accounts describe "$RUNTIME_ACCOUNT" \
  --project "$GOOGLE_CLOUD_PROJECT" >/dev/null 2>&1; then
  echo "==> Creating runtime service account"
  gcloud iam service-accounts create "$RUNTIME_ACCOUNT_NAME" \
    --display-name="Blue Toad Fleet runtime" \
    --project "$GOOGLE_CLOUD_PROJECT"
fi

for role in roles/aiplatform.user roles/datastore.user roles/logging.logWriter roles/eventarc.eventReceiver; do
  gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member="serviceAccount:${RUNTIME_ACCOUNT}" \
    --role="$role" \
    --condition=None \
    --quiet >/dev/null
done

if ! gcloud storage buckets describe "gs://${BUCKET}" \
  --project "$GOOGLE_CLOUD_PROJECT" >/dev/null 2>&1; then
  echo "==> Creating private regional cycle bucket gs://${BUCKET}"
  gcloud storage buckets create "gs://${BUCKET}" \
    --project "$GOOGLE_CLOUD_PROJECT" \
    --location "$REGION" \
    --uniform-bucket-level-access \
    --public-access-prevention
fi
gcloud storage buckets update "gs://${BUCKET}" \
  --public-access-prevention \
  --project "$GOOGLE_CLOUD_PROJECT" >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${RUNTIME_ACCOUNT}" \
  --role=roles/storage.objectAdmin \
  --project "$GOOGLE_CLOUD_PROJECT" >/dev/null

echo "==> Deploying the asynchronous cycle processor"
gcloud run jobs deploy "$JOB_NAME" \
  --source . \
  --region "$REGION" \
  --project "$GOOGLE_CLOUD_PROJECT" \
  --service-account "$RUNTIME_ACCOUNT" \
  --command python \
  --args=-m,src.cycles.worker \
  --tasks 1 \
  --parallelism 1 \
  --cpu 2 \
  --memory 2Gi \
  --max-retries 1 \
  --task-timeout 2h \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT},VERTEX_LOCATION=global,BTF_CYCLE_BUCKET=${BUCKET},BTF_SHOP_ID=richmond-general,BTF_MEMORY_BACKEND=firestore,BTF_FIRESTORE_DATABASE=blue-toad"

# The service uses per-execution environment overrides to tell the one shared
# job which immutable cycle to process. Google documents roles/run.developer as
# the role required for jobs.run with overrides.
gcloud run jobs add-iam-policy-binding "$JOB_NAME" \
  --region "$REGION" \
  --project "$GOOGLE_CLOUD_PROJECT" \
  --member="serviceAccount:${RUNTIME_ACCOUNT}" \
  --role=roles/run.developer >/dev/null

# Direct Cloud Storage events use Pub/Sub transport internally.
PROJECT_NUMBER="$(gcloud projects describe "$GOOGLE_CLOUD_PROJECT" --format='value(projectNumber)')"
STORAGE_AGENT="service-${PROJECT_NUMBER}@gs-project-accounts.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
  --member="serviceAccount:${STORAGE_AGENT}" \
  --role=roles/pubsub.publisher \
  --condition=None \
  --quiet >/dev/null

gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$GOOGLE_CLOUD_PROJECT" \
  --member="serviceAccount:${RUNTIME_ACCOUNT}" \
  --role=roles/run.invoker >/dev/null

if gcloud eventarc triggers describe "$TRIGGER_NAME" \
  --location "$REGION" --project "$GOOGLE_CLOUD_PROJECT" >/dev/null 2>&1; then
  echo "==> Updating READY event destination"
  gcloud eventarc triggers update "$TRIGGER_NAME" \
    --location "$REGION" \
    --project "$GOOGLE_CLOUD_PROJECT" \
    --destination-run-service "$SERVICE_NAME" \
    --destination-run-region "$REGION" \
    --destination-run-path /api/events/storage \
    --service-account "$RUNTIME_ACCOUNT"
else
  echo "==> Creating Cloud Storage finalized trigger"
  gcloud eventarc triggers create "$TRIGGER_NAME" \
    --location "$REGION" \
    --project "$GOOGLE_CLOUD_PROJECT" \
    --destination-run-service "$SERVICE_NAME" \
    --destination-run-region "$REGION" \
    --destination-run-path /api/events/storage \
    --event-filters="type=google.cloud.storage.object.v1.finalized" \
    --event-filters="bucket=${BUCKET}" \
    --service-account "$RUNTIME_ACCOUNT"
fi

echo "==> Cycle infrastructure ready"
echo "    Bucket: gs://${BUCKET}"
echo "    Job:    ${JOB_NAME}"
echo "    Trigger:${TRIGGER_NAME}"
