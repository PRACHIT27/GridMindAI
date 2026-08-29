#!/usr/bin/env bash
# Step 2: create one Firestore database per domain, plus a shared database.
#
# WHY separate databases instead of separate collections:
# Firestore Security Rules are only evaluated for client-SDK / Firebase Auth
# access. Our Cloud Run agents talk to Firestore server-to-server through the
# Admin SDK, which BYPASSES Security Rules entirely. Collection-level rules
# would therefore be security theater. IAM Conditions scoped to a database
# resource ARE enforced for client-library access, so the database is the
# smallest unit we can actually isolate.
#
# AWS analogy: this is closer to "one DynamoDB table per service with an IAM
# policy pinned to that table ARN" than to row-level access control.
set -euo pipefail
source "$(dirname "$0")/../env.sh"

# shared-db holds workload_queue, negotiation_log, memory_bank -- the
# collections the orchestrator and multiple agents legitimately share.
for db in "${DOMAINS[@]/%/-db}" shared-db; do
  if gcloud firestore databases describe --database="$db" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "SKIP  $db already exists"
  else
    echo "CREATE $db"
    gcloud firestore databases create \
      --database="$db" \
      --location="$REGION" \
      --type=firestore-native \
      --project="$PROJECT_ID"
  fi
done

gcloud firestore databases list --project="$PROJECT_ID" --format="table(name,locationId,type)"
