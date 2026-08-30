#!/usr/bin/env bash
# Cloud NAT for outbound traffic that Private Google Access does not cover.
#
# WHY THIS IS NEEDED
# The gateway and orchestrator run with --vpc-egress=all-traffic, because that
# is what makes their calls originate inside the VPC and therefore satisfy
# --ingress=internal on the services they call. The side effect is that ALL
# their outbound traffic now leaves through the subnet.
#
# Private Google Access carries the common Google API endpoints, which is why
# Firestore and Vertex AI kept working. It does NOT carry Model Armor's
# regional endpoint (modelarmor.us-east4.rep.googleapis.com), so that call had
# no route at all and died with ConnectTimeout.
#
# The failure was invisible in the obvious place. Model Armor fails CLOSED, so
# the gateway correctly refused every request with 422; the orchestrator then
# correctly failed safe and returned "escalated". Both layers behaved exactly
# as designed, and the end result looked like an agent decision rather than a
# missing network route.
#
# COST: a NAT gateway bills roughly $0.044/hour while in use, about $1/day,
# plus a small per-GB processing charge. On a $300 credit that is acceptable.
# The zero-cost alternative is a Cloud DNS private zone pointing
# *.googleapis.com at restricted.googleapis.com with a matching route -- more
# moving parts, and worth doing if this ever ran longer than a hackathon.
set -euo pipefail
source "$(dirname "$0")/../env.sh"

VPC="gridmind-vpc"
ROUTER="gridmind-router"
NAT="gridmind-nat"

if gcloud compute routers describe "$ROUTER" --region="$REGION" \
     --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "SKIP  router $ROUTER already exists"
else
  echo "CREATE router $ROUTER"
  gcloud compute routers create "$ROUTER" \
    --network="$VPC" --region="$REGION" --project="$PROJECT_ID"
fi

if gcloud compute routers nats describe "$NAT" --router="$ROUTER" \
     --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "SKIP  NAT $NAT already exists"
else
  echo "CREATE NAT $NAT"
  gcloud compute routers nats create "$NAT" \
    --router="$ROUTER" --region="$REGION" --project="$PROJECT_ID" \
    --auto-allocate-nat-external-ips \
    --nat-all-subnet-ip-ranges \
    --enable-logging --log-filter=ERRORS_ONLY
fi

echo
gcloud compute routers nats describe "$NAT" --router="$ROUTER" --region="$REGION" \
  --project="$PROJECT_ID" --format="value(name,natIpAllocateOption,sourceSubnetworkIpRangesToNat)"
echo
echo "Egress ready. Model Armor should now be reachable from the gateway."
