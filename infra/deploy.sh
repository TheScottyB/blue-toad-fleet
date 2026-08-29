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
# --source . uploads the working tree, not HEAD, so a dirty tree must not be
# stamped as a clean commit — release-check compares this value against the
# audited local HEAD, and a false stamp would manufacture parity evidence.
GIT_COMMIT="$(git rev-parse HEAD)"
# The status check fails closed: set -e does not abort on a command
# substitution failing inside a condition, so a status error (index.lock
# contention, permissions) must be caught explicitly or a dirty tree gets
# stamped as clean. --untracked-files=normal defeats a
# status.showUntrackedFiles=no config override that would empty the output
# for an untracked-only dirty tree.
if ! TREE_STATUS="$(git status --porcelain --untracked-files=normal)"; then
  echo "==> ERROR: 'git status' failed; the working tree state is unknown" >&2
  echo "==> Refusing to deploy rather than stamp an unverified tree as clean" >&2
  exit 1
fi
if [ -n "$TREE_STATUS" ]; then
  GIT_COMMIT="${GIT_COMMIT}-dirty"
fi
SERVICE_ENV="GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT},VERTEX_LOCATION=global,BTF_MEMORY_BACKEND=firestore,BTF_FIRESTORE_DATABASE=blue-toad,BTF_CYCLE_BUCKET=${BUCKET},BTF_CYCLE_JOB=${JOB_NAME},BTF_SHOP_ID=richmond-general,OPERATOR_ACTOR=richmond-general-owner,CLOUD_RUN_REGION=${REGION},GIT_COMMIT=${GIT_COMMIT}"
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

# The runtime roles must exist BEFORE the service boots, not after. They used
# to be granted only by provision_cycles.sh at step 3 — downstream of the
# deploy — which worked only while the server silently downgraded a failed
# Firestore init to container disk. With memory failing closed (as it must:
# the silent path was telling the operator "applied" for standing rules that
# evaporated on instance recycle), the first boot needs datastore.user or the
# revision dies on startup and step 3 is never reached. Idempotent; the same
# loop in provision_cycles.sh simply re-asserts them.
echo "==> [1b/4] Granting runtime roles to $RUNTIME_ACCOUNT..."
for role in roles/aiplatform.user roles/datastore.user roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member="serviceAccount:${RUNTIME_ACCOUNT}" \
    --role="$role" --condition=None >/dev/null
done

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
