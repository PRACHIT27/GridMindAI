#!/usr/bin/env bash
# Step 3a: one service account per agent.
#
# GCP service account ~= AWS IAM role assumed by a task / Azure managed
# identity. Each Cloud Run service runs AS one of these, so every Firestore
# call it makes carries that identity.
set -euo pipefail
source "$(dirname "$0")/../env.sh"

declare -A ACCOUNTS=(
  ["power-agent-sa"]="GridMind Power Agent"
  ["cooling-agent-sa"]="GridMind Cooling Agent"
  ["facilities-agent-sa"]="GridMind Facilities Agent"
  ["cost-agent-sa"]="GridMind Cost Agent"
  ["orchestrator-agent-sa"]="GridMind Orchestrator (shared-db only)"
  ["gateway-agent-sa"]="GridMind Agent Gateway"
)

for sa in "${!ACCOUNTS[@]}"; do
  email="${sa}@${PROJECT_ID}.iam.gserviceaccount.com"
  if gcloud iam service-accounts describe "$email" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "SKIP  $sa already exists"
  else
    echo "CREATE $sa"
    gcloud iam service-accounts create "$sa" \
      --display-name="${ACCOUNTS[$sa]}" \
      --project="$PROJECT_ID"
  fi
done

gcloud iam service-accounts list --project="$PROJECT_ID" --format="table(email,displayName)"
