#!/usr/bin/env bash
# Step 1 of the build order: enable every API GridMind depends on.
# Idempotent -- safe to re-run.
set -euo pipefail
source "$(dirname "$0")/env.sh"

gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  cloudresourcemanager.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  --project="$PROJECT_ID"

# Cloud Build runs as the default compute service account, which on projects
# created after ~2024 no longer receives the Editor role automatically. Without
# these grants `gcloud builds submit` fails with a confusing 403 about
# storage.objects.get on its own source upload bucket.
CB_SA="$(gcloud projects describe "$PROJECT_ID" \
         --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
echo "Granting Cloud Build permissions to ${CB_SA}"
for role in roles/cloudbuild.builds.builder roles/storage.objectAdmin \
            roles/artifactregistry.writer roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${CB_SA}" --role="$role" \
    --condition=None --quiet >/dev/null
done

echo "APIs enabled. Verify with: gcloud services list --enabled"
echo
echo "MANUAL STEP (no CLI equivalent): set a budget alert at"
echo "  Billing -> Budgets & Alerts -> Create Budget"
echo "  Recommended: \$50 cap, alerts at 50% / 90% / 100%."
