#!/usr/bin/env bash
# THE SECURITY DEMO
#
# Shows that GridMind's isolation is enforced by Google Cloud IAM, not by
# application code that could be edited away. Every line below is a real API
# call with real credentials -- nothing is simulated.
#
#   bash scripts/demo_denial.sh
#
# WHY THIS DOES NOT TEST WITH YOUR OWN ACCOUNT
# You are project Owner, and Owner carries run.invoker across the whole
# project. Calling a service as yourself therefore succeeds everywhere and
# proves nothing about the invoker chain. Each check below impersonates the
# SERVICE ACCOUNT that actually runs in production, which is the only identity
# whose permissions matter.
#
# Prereq (testing only, never granted to the deployed system):
#   gcloud iam service-accounts add-iam-policy-binding SA_EMAIL \
#     --member="user:YOU@example.com" --role="roles/iam.serviceAccountTokenCreator"
set -uo pipefail
source "$(dirname "$0")/../infra/env.sh"

hr() { printf '%s\n' "-------------------------------------------------------------------------"; }

sa() { echo "$1@${PROJECT_ID}.iam.gserviceaccount.com"; }

url_of() {
  gcloud run services describe "$1" --region="$REGION" --project="$PROJECT_ID" \
    --format="value(status.url)" 2>/dev/null | tr -d '[:space:]'
}

# Call a Cloud Run service AS a given service account.
call_as() {
  local as_sa="$1" url="$2" tok
  tok=$(gcloud auth print-identity-token \
        --impersonate-service-account="$(sa "$as_sa")" \
        --audiences="$url" 2>/dev/null | tr -d '[:space:]')
  [[ -z "$tok" ]] && { echo "TOKEN_FAIL"; return; }
  curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $tok" "${url}/health"
}

check() {  # label expected actual
  if [[ "$3" == "$2" ]]; then printf '  PASS  %-46s HTTP %s\n' "$1" "$3"
  else printf '  FAIL  %-46s HTTP %s (expected %s)\n' "$1" "$3" "$2"; fi
}

echo
hr; echo "LAYER 1  --  DATA ISOLATION (IAM Conditions on Firestore)"; hr
echo "Each agent identity is bound to exactly ONE database by an IAM condition."
echo "Firestore itself refuses the rest:"
echo
bash "$(dirname "$0")/../infra/iam/03_verify_isolation.sh"

echo
hr; echo "LAYER 2  --  NETWORK ISOLATION (Cloud Run invoker permissions)"; hr
echo "Every service is --no-allow-unauthenticated. Specialists accept calls only"
echo "from the gateway, so the orchestrator cannot bypass the audit trail."
echo

COST_URL=$(url_of cost-agent)
GW_URL=$(url_of gateway)

if [[ -z "$COST_URL" || -z "$GW_URL" ]]; then
  echo "  services not deployed; run infra/cloudrun/deploy.sh first."
else
  code=$(curl -s -o /dev/null -w "%{http_code}" "${COST_URL}/health")
  check "anonymous          -> cost-agent" 403 "$code"
  check "power-agent-sa     -> cost-agent" 403 "$(call_as power-agent-sa "$COST_URL")"
  check "power-agent-sa     -> gateway"    403 "$(call_as power-agent-sa "$GW_URL")"
  check "orchestrator-agent-sa -> cost-agent (must go via gateway)" 403 \
        "$(call_as orchestrator-agent-sa "$COST_URL")"
  check "gateway-agent-sa   -> cost-agent (the ONE allowed path)" 200 \
        "$(call_as gateway-agent-sa "$COST_URL")"
fi

echo
hr; echo "LAYER 3  --  ROUTING TABLE (the gateway's own allow/deny record)"; hr
echo "Even a permitted caller is checked against the gateway's routing table,"
echo "and every allow and deny is written to Cloud Logging. Read them with:"
echo
echo "  gcloud logging read 'jsonPayload.event=\"gateway_denied\"' \\"
echo "    --project=$PROJECT_ID --limit=10"
echo "  gcloud logging read 'jsonPayload.event=\"gateway_allowed\"' \\"
echo "    --project=$PROJECT_ID --limit=10"
echo
hr
echo "The point: none of these refusals come from code we wrote. Layers 1 and 2"
echo "are enforced by Google Cloud itself -- deleting our checks would not open"
echo "them. Layer 3 adds the audit trail that IAM alone does not provide."
hr
