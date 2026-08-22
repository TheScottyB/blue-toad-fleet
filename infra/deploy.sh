#!/usr/bin/env bash
# Deploy the Blue Toad Fleet to Google Cloud Run. Idempotent; safe to re-run.
set -euo pipefail

GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-threebatdrone-prod-420}"
REGION="${CLOUD_RUN_REGION:-us-central1}"
SERVICE_NAME="blue-toad-fleet"
JOB_NAME="${BTF_CYCLE_JOB:-blue-toad-cycle-processor}"
BUCKET="${BTF_CYCLE_BUCKET:-${GOOGLE_CLOUD_PROJECT}-blue-toad-cycles}"
RUNTIME_ACCOUNT_NAME="${BTF_RUNTIME_ACCOUNT_NAME:-blue-toad-fleet-runtime}"
RUNTIME_ACCOUNT="${RUNTIME_ACCOUNT_NAME}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"
OPERATOR_SECRET="${BTF_OPERATOR_SECRET:-operator-token}"
SERVICE_ENV="GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT},VERTEX_LOCATION=global,BTF_MEMORY_BACKEND=firestore,BTF_FIRESTORE_DATABASE=blue-toad,BTF_CYCLE_BUCKET=${BUCKET},BTF_CYCLE_JOB=${JOB_NAME},BTF_SHOP_ID=richmond-general,OPERATOR_ACTOR=richmond-general-owner,CLOUD_RUN_REGION=${REGION}"
SECRET_ARGS=()

echo "==> [1/4] Enabling Google Cloud Services on project: $GOOGLE_CLOUD_PROJECT"
gcloud services enable run.googleapis.com aiplatform.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com \
  firestore.googleapis.com secretmanager.googleapis.com \
  --project "$GOOGLE_CLOUD_PROJECT"

# The cycle provisioner creates the shared runtime identity and private bucket.
# It deploys the processor after the service below exists.
gcloud iam service-accounts describe "$RUNTIME_ACCOUNT" \
  --project "$GOOGLE_CLOUD_PROJECT" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$RUNTIME_ACCOUNT_NAME" \
    --display-name="Blue Toad Fleet runtime" \
    --project "$GOOGLE_CLOUD_PROJECT"

if gcloud secrets describe "$OPERATOR_SECRET" \
  --project "$GOOGLE_CLOUD_PROJECT" >/dev/null 2>&1; then
  gcloud secrets add-iam-policy-binding "$OPERATOR_SECRET" \
    --project "$GOOGLE_CLOUD_PROJECT" \
    --member="serviceAccount:${RUNTIME_ACCOUNT}" \
    --role=roles/secretmanager.secretAccessor >/dev/null
  SECRET_ARGS=(--set-secrets "OPERATOR_TOKEN=${OPERATOR_SECRET}:latest")
else
  echo "==> Note: Secret Manager secret '$OPERATOR_SECRET' was not found"
  echo "==> Browser mutation controls will stay disabled"
fi

echo "==> [2/4] Building and deploying $SERVICE_NAME to Cloud Run ($REGION)..."
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "$RUNTIME_ACCOUNT" \
  --set-env-vars "$SERVICE_ENV" \
  "${SECRET_ARGS[@]}" \
  --project "$GOOGLE_CLOUD_PROJECT"

echo "==> [3/4] Provisioning Cloud Storage, Cloud Run Job, and Eventarc..."
GOOGLE_CLOUD_PROJECT="$GOOGLE_CLOUD_PROJECT" \
CLOUD_RUN_REGION="$REGION" \
BTF_SERVICE_NAME="$SERVICE_NAME" \
BTF_CYCLE_BUCKET="$BUCKET" \
BTF_CYCLE_JOB="$JOB_NAME" \
BTF_RUNTIME_ACCOUNT_NAME="$RUNTIME_ACCOUNT_NAME" \
  ./infra/provision_cycles.sh

echo "==> [4/4] Fetching service status and public URL..."
URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --project "$GOOGLE_CLOUD_PROJECT" --format='value(status.url)')
echo "=================================================================="
echo "==> [✓] BLUE TOAD FLEET IS LIVE ON GOOGLE CLOUD RUN!"
echo "==> Live Gate Console: $URL"
echo "==> Health Endpoint:  $URL/health"
echo "==> Sourcing API:     $URL/api/lots"
echo "=================================================================="
