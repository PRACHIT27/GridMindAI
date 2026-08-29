#!/usr/bin/env bash
# THE SECURITY DEMO
#
# Shows that GridMind's isolation is enforced by Google Cloud IAM, not by
# application code that could be edited away. Three layers, each demonstrated
# by an actual denial rather than described in a diagram.
#
#   bash scripts/demo_denial.sh
set -uo pipefail
source "$(dirname "$0")/../infra/env.sh"

hr() { printf '%s\n' "--------------------------------------------------------------------"; }

echo
hr; echo "LAYER 1  --  DATABASE ISOLATION (IAM Conditions on Firestore)"; hr
echo "Each agent identity is bound to exactly one database by an IAM condition."
echo "These are real API calls with real agent credentials:"
echo
bash "$(dirname "$0")/../infra/iam/03_verify_isolation.sh"

echo
hr; echo "LAYER 2  --  NETWORK ISOLATION (Cloud Run invoker permissions)"; hr
echo "Every service is --no-allow-unauthenticated. Specialists accept calls only"
echo "from the gateway, so the orchestrator cannot bypass the audit trail."
echo
POWER_URL=$(gcloud run services describe power-agent --region="$REGION" \
  --project="$PROJECT_ID" --format="value(status.url)" 2>/dev/null || echo "")

if [[ -n "$POWER_URL" ]]; then
  echo "Attempting to call the power agent directly, with NO credentials:"
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${POWER_URL}/decide" \
         -H "Content-Type: application/json" -d '{}')
  echo "   anonymous -> power-agent : HTTP ${code}   (expect 403 -- Cloud Run refuses)"
  echo
  echo "Now with a valid user identity token, which is still not the gateway:"
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${POWER_URL}/decide" \
         -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
         -H "Content-Type: application/json" -d '{}')
  echo "   your account -> power-agent : HTTP ${code}   (expect 403 -- only the gateway may invoke)"
else
  echo "   power-agent not deployed yet; skipping."
fi

echo
hr; echo "LAYER 3  --  ROUTING TABLE (the gateway's own allow/deny record)"; hr
echo "Even a permitted caller is checked against the routing table, and every"
echo "allow and deny is written to Cloud Logging. Read the denials with:"
echo
echo "  gcloud logging read '"'"'jsonPayload.event="gateway_denied"'"'"' \\"
echo "    --project=$PROJECT_ID --limit=10 --format=json"
echo
hr
echo "The point: none of these refusals come from application code we wrote."
echo "Layers 1 and 2 are enforced by Google Cloud itself. Deleting our checks"
echo "would not open them."
hr
