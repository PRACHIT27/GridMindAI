#!/usr/bin/env bash
# Network isolation for GridMind.
#
# WHAT THIS BUYS US
# Before this, all six services were --ingress=all: publicly ROUTABLE, but
# every request had to carry a valid Google-signed token. Solid, and still only
# one layer -- an attacker anywhere on the internet could reach the TLS endpoint
# and attempt to authenticate.
#
# After this, the four specialists and the gateway are --ingress=internal:
# unreachable from the internet at all, not "reachable but rejected". The only
# way in is from inside this VPC. The orchestrator stays reachable (with auth)
# because a human has to be able to submit a workload.
#
# HOW CLOUD RUN TALKS TO CLOUD RUN PRIVATELY
# Two halves, and BOTH are required -- this is the part that trips people up:
#
#   1. ingress=internal on the callee   -> refuses anything not from the VPC
#   2. Direct VPC egress on the caller  -> routes its outbound calls THROUGH
#                                          the VPC, so it qualifies as internal
#
# Set only (1) and the gateway can no longer reach the specialists: its traffic
# still leaves over the public path and gets refused. The system breaks with a
# 403 that looks like an IAM problem and is not one.
#
# We use DIRECT VPC EGRESS (--network/--subnet), not a Serverless VPC Access
# connector. The connector approach runs 2+ e2-micro VMs continuously, roughly
# $10/month of idle burn against a $300 credit. Direct VPC egress has no such
# standing cost and is the current recommended path.
#
# PRIVATE GOOGLE ACCESS IS NOT OPTIONAL HERE
# With egress routed through the VPC, calls to Firestore and Vertex AI leave
# via the subnet. Without Private Google Access those calls need a public route
# -- meaning Cloud NAT, another running resource to pay for. With it enabled,
# the subnet reaches Google APIs over Google's internal network directly. So
# this one flag is the difference between working-and-free and
# broken-or-paying-for-NAT.
set -euo pipefail
source "$(dirname "$0")/../env.sh"

VPC="gridmind-vpc"
SUBNET="gridmind-subnet"
RANGE="10.20.0.0/24"

if gcloud compute networks describe "$VPC" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "SKIP  VPC $VPC already exists"
else
  echo "CREATE VPC $VPC (custom mode -- no auto subnets in regions we do not use)"
  gcloud compute networks create "$VPC" \
    --subnet-mode=custom \
    --description="GridMind private network for Cloud Run service-to-service traffic" \
    --project="$PROJECT_ID"
fi

if gcloud compute networks subnets describe "$SUBNET" --region="$REGION" \
     --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "SKIP  subnet $SUBNET already exists"
else
  echo "CREATE subnet $SUBNET ($RANGE in $REGION) with Private Google Access"
  gcloud compute networks subnets create "$SUBNET" \
    --network="$VPC" \
    --region="$REGION" \
    --range="$RANGE" \
    --enable-private-ip-google-access \
    --project="$PROJECT_ID"
fi

# Cloud Run's Direct VPC egress needs the subnet to permit its traffic. The
# default-deny posture of a custom VPC means we state explicitly what may flow:
# only internal traffic within our own range, on the ports our services use.
if ! gcloud compute firewall-rules describe gridmind-allow-internal \
     --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "CREATE firewall rule gridmind-allow-internal"
  gcloud compute firewall-rules create gridmind-allow-internal \
    --network="$VPC" \
    --allow=tcp:443,tcp:8080,icmp \
    --source-ranges="$RANGE" \
    --description="Allow GridMind services to reach each other inside the VPC" \
    --project="$PROJECT_ID"
fi

echo
gcloud compute networks subnets describe "$SUBNET" --region="$REGION" \
  --project="$PROJECT_ID" \
  --format="table(name,ipCidrRange,privateIpGoogleAccess,network.basename())"
echo
echo "VPC ready. Apply it with: bash infra/network/02_apply_ingress.sh"
