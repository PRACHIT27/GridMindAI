#!/usr/bin/env bash
# Move GridMind onto the VPC and take the specialists off the public internet.
#
# ORDER IS LOAD-BEARING. Egress first, ingress second.
#
#   If you set ingress=internal BEFORE giving the caller VPC egress, the caller
#   keeps sending over the public path, the callee refuses it, and the whole
#   system returns 403s that look exactly like an IAM misconfiguration. You
#   would then go debugging service accounts for an hour. Egress first means
#   the private path exists before anything starts requiring it.
#
# Rollback, if anything goes wrong:
#   gcloud run services update SERVICE --region=us-east4 --ingress=all
set -euo pipefail
source "$(dirname "$0")/../env.sh"

VPC="gridmind-vpc"
SUBNET="gridmind-subnet"

# ---------- step 1: give the CALLERS a path through the VPC ----------
# all-traffic, not private-ranges-only: *.run.app resolves to Google's PUBLIC
# addresses, so private-ranges-only would send those calls straight out and the
# callee would not see them as internal. Private Google Access on the subnet is
# what lets this reach Firestore, Vertex AI and run.app without Cloud NAT.
echo "== step 1: Direct VPC egress on the callers (orchestrator, gateway)"
for svc in orchestrator gateway; do
  echo "   $svc"
  gcloud run services update "$svc" \
    --region="$REGION" --project="$PROJECT_ID" \
    --network="$VPC" --subnet="$SUBNET" \
    --vpc-egress=all-traffic \
    --quiet >/dev/null
done

# ---------- step 2: take the CALLEES off the public internet ----------
echo
echo "== step 2: ingress=internal on the specialists"
for d in "${DOMAINS[@]}"; do
  echo "   ${d}-agent"
  gcloud run services update "${d}-agent" \
    --region="$REGION" --project="$PROJECT_ID" \
    --ingress=internal --quiet >/dev/null
done

echo
echo "== step 3: ingress=internal on the gateway"
# The gateway is only ever called by the orchestrator, which now has VPC
# egress -- so it has no reason to be internet-reachable either.
gcloud run services update gateway \
  --region="$REGION" --project="$PROJECT_ID" \
  --ingress=internal --quiet >/dev/null

# The orchestrator deliberately stays ingress=all. A human has to be able to
# submit a workload, and it is still --no-allow-unauthenticated, so it is
# reachable only with a valid token carrying run.invoker.
echo
echo "== final posture"
for s in power-agent cooling-agent facilities-agent cost-agent gateway orchestrator; do
  ing=$(gcloud run services describe "$s" --region="$REGION" --project="$PROJECT_ID" \
        --format="value(metadata.annotations['run.googleapis.com/ingress'])" 2>/dev/null \
        | tr -d '[:space:]')
  egr=$(gcloud run services describe "$s" --region="$REGION" --project="$PROJECT_ID" \
        --format="value(spec.template.metadata.annotations['run.googleapis.com/vpc-access-egress'])" \
        2>/dev/null | tr -d '[:space:]')
  printf '  %-18s ingress=%-10s egress=%s\n' "$s" "${ing:-all}" "${egr:-none}"
done

echo
echo "Verify the system still works end to end:"
echo "  bash scripts/smoke_deployed.sh"
