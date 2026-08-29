#!/usr/bin/env bash
# Build once, deploy six Cloud Run services, then wire the invoker chain.
#
#   bash infra/cloudrun/deploy.sh            # build + deploy everything
#   bash infra/cloudrun/deploy.sh --no-build # redeploy using the last image
#
# COST SAFETY (a $300 credit is the whole budget):
#   --min-instances=0   every service scales to zero when idle; idle cost is $0
#   --max-instances=2   a runaway loop cannot spawn hundreds of containers
#   --cpu=1 --memory=1Gi and a concurrency of 8 keep each instance small
#
# SECURITY POSTURE:
#   --no-allow-unauthenticated on ALL six services. Nothing is publicly
#   reachable. Invocation rights are granted explicitly below, forming a chain:
#       you -> orchestrator -> gateway -> specialists
#   A specialist cannot be invoked by anything except the gateway, and the
#   orchestrator cannot reach a specialist except through it.
set -euo pipefail
source "$(dirname "$0")/../env.sh"

BUILD=1
[[ "${1:-}" == "--no-build" ]] && BUILD=0

REPO="gridmind"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/gridmind:latest"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# ---------- artifact registry ----------
if ! gcloud artifacts repositories describe "$REPO" --location="$REGION" \
     --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "== creating Artifact Registry repository"
  gcloud artifacts repositories create "$REPO" \
    --repository-format=docker --location="$REGION" \
    --description="GridMind agent images" --project="$PROJECT_ID"
fi

# ---------- build ----------
if [[ $BUILD -eq 1 ]]; then
  echo "== building image (single image for all six services)"
  gcloud builds submit "$ROOT" --tag "$IMAGE" --project="$PROJECT_ID"
fi

# ---------- specialists ----------
deploy_specialist() {
  local domain="$1"
  echo "== deploying ${domain}-agent"
  gcloud run deploy "${domain}-agent" \
    --image="$IMAGE" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --service-account="${domain}-agent-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
    --set-env-vars="GRIDMIND_ROLE=${domain},GRIDMIND_PROJECT_ID=${PROJECT_ID}" \
    --no-allow-unauthenticated \
    --min-instances=0 --max-instances=2 \
    --cpu=1 --memory=1Gi --concurrency=8 --timeout=300 \
    --quiet
}

for d in "${DOMAINS[@]}"; do deploy_specialist "$d"; done

url_of() {
  gcloud run services describe "$1" --region="$REGION" --project="$PROJECT_ID" \
    --format="value(status.url)" | tr -d '[:space:]'
}

POWER_URL=$(url_of power-agent)
COOLING_URL=$(url_of cooling-agent)
FACILITIES_URL=$(url_of facilities-agent)
COST_URL=$(url_of cost-agent)

# ---------- gateway ----------
echo "== deploying gateway"
gcloud run deploy gateway \
  --image="$IMAGE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --service-account="gateway-agent-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars="GRIDMIND_ROLE=gateway,GRIDMIND_PROJECT_ID=${PROJECT_ID},GRIDMIND_POWER_URL=${POWER_URL},GRIDMIND_COOLING_URL=${COOLING_URL},GRIDMIND_FACILITIES_URL=${FACILITIES_URL},GRIDMIND_COST_URL=${COST_URL}" \
  --no-allow-unauthenticated \
  --min-instances=0 --max-instances=2 \
  --cpu=1 --memory=512Mi --concurrency=16 --timeout=300 \
  --quiet

GATEWAY_URL=$(url_of gateway)

# ---------- orchestrator ----------
echo "== deploying orchestrator"
gcloud run deploy orchestrator \
  --image="$IMAGE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --service-account="orchestrator-agent-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars="GRIDMIND_ROLE=orchestrator,GRIDMIND_PROJECT_ID=${PROJECT_ID},GRIDMIND_GATEWAY_URL=${GATEWAY_URL}" \
  --no-allow-unauthenticated \
  --min-instances=0 --max-instances=2 \
  --cpu=1 --memory=1Gi --concurrency=4 --timeout=600 \
  --quiet

ORCH_URL=$(url_of orchestrator)

# ---------- invoker chain ----------
# Least privilege at the network layer, mirroring the database isolation.
echo "== wiring the invoker chain"

# gateway may invoke the four specialists -- and nothing else may.
for d in "${DOMAINS[@]}"; do
  gcloud run services add-iam-policy-binding "${d}-agent" \
    --region="$REGION" --project="$PROJECT_ID" \
    --member="serviceAccount:gateway-agent-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/run.invoker" --quiet >/dev/null
  echo "   gateway-agent-sa -> ${d}-agent"
done

# orchestrator may invoke the gateway -- so it cannot bypass the audit log.
gcloud run services add-iam-policy-binding gateway \
  --region="$REGION" --project="$PROJECT_ID" \
  --member="serviceAccount:orchestrator-agent-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.invoker" --quiet >/dev/null
echo "   orchestrator-agent-sa -> gateway"

# your own account may invoke the orchestrator, for testing and the demo.
ME=$(gcloud config get-value account 2>/dev/null)
gcloud run services add-iam-policy-binding orchestrator \
  --region="$REGION" --project="$PROJECT_ID" \
  --member="user:${ME}" --role="roles/run.invoker" --quiet >/dev/null
echo "   ${ME} -> orchestrator"

cat <<EOF

================================================================
DEPLOYED
  orchestrator   ${ORCH_URL}
  gateway        ${GATEWAY_URL}
  power-agent    ${POWER_URL}
  cooling-agent  ${COOLING_URL}
  facilities     ${FACILITIES_URL}
  cost-agent     ${COST_URL}

None are publicly reachable. Call the orchestrator with your own identity:

  curl -X POST "${ORCH_URL}/negotiate" \\
    -H "Authorization: Bearer \$(gcloud auth print-identity-token)" \\
    -H "Content-Type: application/json" \\
    -d '{"workload_id":"wl-2026-0842","scenario":"normal","format":"text"}'
================================================================
EOF
