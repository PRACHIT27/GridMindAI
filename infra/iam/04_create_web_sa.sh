#!/usr/bin/env bash
# Identity for the public web tier.
#
# THIS IS THE ONLY INTERNET-FACING SERVICE, so it gets the weakest identity in
# the system:
#
#   * READ-ONLY Firestore -- it displays decisions, it never writes one
#   * shared-db ONLY, by IAM condition -- it cannot read power, cooling,
#     facilities or cost data even if the container is fully compromised
#   * NO model access -- it cannot call Gemini, so it cannot be turned into a
#     way to spend the credit directly
#   * run.invoker on the orchestrator and nothing else
#
# Worth stating plainly: the public surface is the most likely thing to be
# attacked, so it holds the least. An attacker who owns this container gets
# read access to a queue of workload requests and a log of past decisions --
# not the facility.
set -euo pipefail
source "$(dirname "$0")/../env.sh"

HERE="$(dirname "$0")"
SA="web-bff-sa"
EMAIL="${SA}@${PROJECT_ID}.iam.gserviceaccount.com"

if gcloud iam service-accounts describe "$EMAIL" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "SKIP  $SA already exists"
else
  echo "CREATE $SA"
  gcloud iam service-accounts create "$SA" \
    --display-name="GridMind Web BFF (public, read-only)" \
    --project="$PROJECT_ID"
fi

if gcloud iam roles describe gridmindWebRead --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam roles update gridmindWebRead --project="$PROJECT_ID" \
    --file="$HERE/gridmind_web_read_role.yaml" --quiet >/dev/null
  echo "UPDATE role gridmindWebRead"
else
  gcloud iam roles create gridmindWebRead --project="$PROJECT_ID" \
    --file="$HERE/gridmind_web_read_role.yaml" --quiet >/dev/null
  echo "CREATE role gridmindWebRead"
fi

echo "BIND  $SA -> shared-db (read-only, conditional)"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${EMAIL}" \
  --role="projects/${PROJECT_ID}/roles/gridmindWebRead" \
  --condition="expression=resource.type == \"firestore.googleapis.com/Database\" && resource.name == \"projects/${PROJECT_ID}/databases/shared-db\",title=web_only_shared_db,description=Public web tier may read shared-db only" \
  --quiet >/dev/null

echo "BIND  $SA -> log writer"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${EMAIL}" \
  --role="roles/logging.logWriter" --condition=None --quiet >/dev/null

echo
echo "Done. Note what this identity does NOT have: no Firestore writes, no"
echo "access to any domain database, and no Vertex AI permission at all."
