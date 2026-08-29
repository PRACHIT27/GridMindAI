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
hr; echo "LAYER 2  --  NETWORK ISOLATION (VPC + internal ingress)"; hr
echo "The 4 specialists and the gateway are --ingress=internal: they have left"
echo "the public internet entirely. The orchestrator and gateway reach them via"
echo "Direct VPC egress, so their calls originate inside gridmind-vpc."
echo

COST_URL=$(url_of cost-agent)
GW_URL=$(url_of gateway)
ORCH_URL=$(url_of orchestrator)

if [[ -z "$COST_URL" || -z "$GW_URL" || -z "$ORCH_URL" ]]; then
  echo "  services not deployed; run infra/cloudrun/deploy.sh first."
else
  # The specialists and the gateway are --ingress=internal, so from the public
  # internet they are UNREACHABLE rather than merely refused. Google answers 404
  # -- it will not even confirm the service exists. That is a stronger result
  # than the 403 these returned before the VPC was applied: a 403 tells an
  # attacker there is something there worth attacking.
  check "anonymous             -> cost-agent (internal)" 404 \
        "$(curl -s -o /dev/null -w '%{http_code}' -m 20 "${COST_URL}/health")"
  check "valid identity        -> cost-agent (internal)" 404 \
        "$(call_as power-agent-sa "$COST_URL")"
  check "orchestrator-agent-sa -> cost-agent (internal)" 404 \
        "$(call_as orchestrator-agent-sa "$COST_URL")"
  check "gateway-agent-sa      -> cost-agent (internal)" 404 \
        "$(call_as gateway-agent-sa "$COST_URL")"
  check "anonymous             -> gateway (internal)" 404 \
        "$(curl -s -o /dev/null -w '%{http_code}' -m 20 "${GW_URL}/health")"

  echo
  echo "  Even the gateway's own identity is refused FROM OUT HERE -- the"
  echo "  permission is real, but this laptop is not in the VPC. Inside the VPC"
  echo "  that same identity is the only one that works, which is what makes the"
  echo "  negotiation below succeed at all."
  echo

  # The orchestrator stays reachable: a human has to be able to submit work.
  # It is still --no-allow-unauthenticated, so a token is required.
  check "anonymous             -> orchestrator (no token)" 403 \
        "$(curl -s -o /dev/null -w '%{http_code}' -m 20 "${ORCH_URL}/health")"
  check "you (authenticated)   -> orchestrator" 200 \
        "$(curl -s -o /dev/null -w '%{http_code}' -m 20 \
           -H "Authorization: Bearer $(gcloud auth print-identity-token | tr -d '[:space:]')" \
           "${ORCH_URL}/health")"
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
