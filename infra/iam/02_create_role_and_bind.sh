#!/usr/bin/env bash
# Step 3b: create the two custom roles, then bind each service account to
# EXACTLY the one database it is allowed to touch, using an IAM Condition.
#
# THE LOAD-BEARING IDEA
# ---------------------
# Firestore does not support resource-level IAM policies -- you cannot attach a
# policy to a single database the way you attach one to an S3 bucket. So the
# binding is made at the PROJECT level and then narrowed with a condition on
# resource.name. Google documents that IAM conditions are enforced when a
# database is accessed "outside of the Google Cloud console, such as with the
# REST API or the client libraries" -- which is exactly how our Cloud Run
# agents connect.
#
# The payoff: orchestrator-agent-sa is bound only to shared-db, so it is
# ARCHITECTURALLY INCAPABLE of reading raw power/cooling/facilities/cost data.
# "The orchestrator only sees verdicts" stops being a code-review promise and
# becomes a property of the platform.
set -euo pipefail
source "$(dirname "$0")/../env.sh"

HERE="$(dirname "$0")"

# ---------- custom roles ----------
create_or_update_role() {
  local role_id="$1" file="$2"
  if gcloud iam roles describe "$role_id" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "UPDATE role $role_id"
    gcloud iam roles update "$role_id" --project="$PROJECT_ID" --file="$file" --quiet
  else
    echo "CREATE role $role_id"
    gcloud iam roles create "$role_id" --project="$PROJECT_ID" --file="$file" --quiet
  fi
}

create_or_update_role "$CUSTOM_ROLE"        "$HERE/gridmind_agent_role.yaml"
create_or_update_role "gridmindModelInvoker" "$HERE/gridmind_model_invoker_role.yaml"

# ---------- database-scoped Firestore bindings ----------
bind_db() {
  local sa="$1" db="$2"
  local email="${sa}@${PROJECT_ID}.iam.gserviceaccount.com"
  echo "BIND  $sa -> $db (conditional)"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${email}" \
    --role="projects/${PROJECT_ID}/roles/${CUSTOM_ROLE}" \
    --condition="expression=resource.type == \"firestore.googleapis.com/Database\" && resource.name == \"projects/${PROJECT_ID}/databases/${db}\",title=only_${db//-/_},description=Restricts ${sa} to ${db}" \
    --quiet >/dev/null
}

# Each specialist agent sees ONE database: its own domain. It does not get
# shared-db -- the workload request arrives in the request body from the
# gateway, so it has no reason to read the queue directly.
for d in "${DOMAINS[@]}"; do
  bind_db "${d}-agent-sa" "${d}-db"
done

# The orchestrator gets shared-db and nothing else. This is the whole claim.
bind_db "orchestrator-agent-sa" "shared-db"

# ---------- model access + logging (unconditional, but minimal) ----------
# --condition=None is REQUIRED here: once a policy contains any conditional
# binding, gcloud refuses to add an unconditional one non-interactively unless
# you say so explicitly.
for sa in power-agent-sa cooling-agent-sa facilities-agent-sa cost-agent-sa orchestrator-agent-sa; do
  email="${sa}@${PROJECT_ID}.iam.gserviceaccount.com"
  echo "BIND  $sa -> Vertex AI predict + log writer"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${email}" \
    --role="projects/${PROJECT_ID}/roles/gridmindModelInvoker" \
    --condition=None --quiet >/dev/null
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${email}" \
    --role="roles/logging.logWriter" \
    --condition=None --quiet >/dev/null
done

# The gateway brokers calls; it never touches Firestore or a model itself.
echo "BIND  gateway-agent-sa -> log writer"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:gateway-agent-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter" \
  --condition=None --quiet >/dev/null

echo
echo "Done. Inspect the conditional bindings with:"
echo "  gcloud projects get-iam-policy $PROJECT_ID --format=json | jq '.bindings[] | select(.condition)'"
