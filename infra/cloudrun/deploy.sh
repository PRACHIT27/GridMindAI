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
# NETWORK POSTURE (see infra/network/):
#   The 4 specialists and the gateway are --ingress=internal: unreachable from
#   the internet at all, not merely rejected. The orchestrator and gateway get
#   Direct VPC egress so their calls originate INSIDE the VPC and therefore
#   qualify as internal. Both halves are required -- ingress=internal without
#   the caller's VPC egress breaks every call with a 403 that looks like IAM.
#   Run infra/network/01_create_vpc.sh before deploying.
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
VPC="gridmind-vpc"
SUBNET="gridmind-subnet"
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

# ---------- preflight ----------
# Import every role before spending a build on them. Cloud Run reports an
# import-time error as "container failed to start and listen on PORT", which
# says nothing about the actual cause -- you then read the container logs to
# discover a one-line NameError. This check surfaces the real traceback in two
# seconds instead of eight minutes.
PY="${PYTHON:-./.venv/Scripts/python.exe}"
[[ -x "$PY" ]] || PY="python"

# Static undefined-name check FIRST. The import check below cannot catch a name
# that is only referenced inside a request handler: the module imports fine, the
# container starts fine, and the failure appears the first time a real request
# arrives. That exact bug shipped a gateway whose every call 500'd on a missing
# `import json`, which surfaced only as agents mysteriously escalating.
if "$PY" -m pyflakes --version >/dev/null 2>&1; then
  echo "== preflight: pyflakes"
  if ! "$PY" -m pyflakes agents/ seed/ server.py 2>&1 | grep -v "imported but unused" \
       | grep -v "f-string is missing placeholders" | grep . ; then
    echo "   ok  no undefined names"
  else
    echo
    echo "Aborting before build -- fix the above."
    exit 1
  fi
else
  echo "== preflight: pyflakes not installed, skipping static check"
fi

echo "== preflight: importing all roles"
for role in "${DOMAINS[@]}" orchestrator gateway web; do
  if ! GRIDMIND_ROLE="$role" "$PY" -c "import server" >/tmp/gm_preflight.txt 2>&1; then
    echo "   FAILED to import role '$role':"
    tail -12 /tmp/gm_preflight.txt | sed 's/^/     /'
    echo
    echo "Aborting before build. Fix the import and re-run."
    exit 1
  fi
  echo "   ok  $role"
done

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
    --ingress=internal \
    --min-instances=0 --max-instances=2 \
    --cpu=1 --memory=1Gi --concurrency=8 --timeout=300 \
    --quiet
}

for d in "${DOMAINS[@]}"; do deploy_specialist "$d"; done

url_of() {
  # Retried: a transient DNS or token-refresh blip here returns an empty URL,
  # and under `set -e` that aborts the deploy HALFWAY -- specialists updated,
  # gateway and orchestrator left on the previous image. A partially deployed
  # system is worse than a failed deploy, because it looks like it worked.
  local out
  for _ in 1 2 3 4 5; do
    out=$(gcloud run services describe "$1" --region="$REGION" --project="$PROJECT_ID" \
          --format="value(status.url)" 2>/dev/null | tr -d '[:space:]')
    [[ -n "$out" ]] && { echo "$out"; return 0; }
    sleep 4
  done
  echo "could not resolve URL for service '$1' after 5 attempts" >&2
  return 1
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
  --ingress=internal \
  --network="$VPC" --subnet="$SUBNET" --vpc-egress=all-traffic \
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
  --ingress=internal \
  --network="$VPC" --subnet="$SUBNET" --vpc-egress=all-traffic \
  --min-instances=0 --max-instances=2 \
  --cpu=1 --memory=1Gi --concurrency=4 --timeout=600 \
  --quiet

ORCH_URL=$(url_of orchestrator)

# ---------- public web tier ----------
# The ONLY internet-facing service. Everything above is now ingress=internal.
# It is --allow-unauthenticated because it has to be -- it is a public
# dashboard -- which is exactly why it runs as web-bff-sa: read-only, shared-db
# only, and no Vertex AI permission at all. The most exposed service holds the
# least privilege in the system.
#
# MAX-INSTANCES=1 ON web IS DELIBERATE AND LOAD-BEARING.
# The rate limiter holds its counters in memory. Cloud Run scales horizontally
# (like Fargate), so N instances means N independent counters: a "60 per day"
# cap silently becomes 60*N, and a caller who lands on a fresh instance skips
# the per-IP cooldown entirely. That defeats the one control standing between a
# public trigger and a drained credit.
# One instance at concurrency 40 is far more than a demo dashboard needs. The
# right fix at real scale is a shared counter, but the web tier's identity is
# deliberately READ-ONLY -- and widening it so a rate limiter can write state
# would be a poor trade for the isolation it buys.
#
# The demo key is a rate-limit bypass for live walkthroughs, not an auth
# boundary. It is passed as an env var rather than a Secret Manager reference
# because it protects a spending cap, not data -- nothing behind it is
# confidential, and every read path is already public by design.
echo "== deploying gridmind (public)"
DEMO_KEY="${GRIDMIND_DEMO_KEY:-$(openssl rand -hex 12 2>/dev/null || echo gridmind-demo)}"
gcloud run deploy gridmind \
  --image="$IMAGE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --service-account="web-bff-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars="GRIDMIND_ROLE=web,GRIDMIND_PROJECT_ID=${PROJECT_ID},GRIDMIND_ORCHESTRATOR_URL=${ORCH_URL},GRIDMIND_DEMO_KEY=${DEMO_KEY}" \
  --allow-unauthenticated \
  --ingress=all \
  --network="$VPC" --subnet="$SUBNET" --vpc-egress=all-traffic \
  --min-instances=0 --max-instances=1 \
  --cpu=1 --memory=512Mi --concurrency=40 --timeout=600 \
  --quiet

WEB_URL=$(url_of gridmind)

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

# the web tier may invoke the orchestrator -- the only way in from outside.
gcloud run services add-iam-policy-binding orchestrator \
  --region="$REGION" --project="$PROJECT_ID" \
  --member="serviceAccount:web-bff-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.invoker" --quiet >/dev/null
echo "   web-bff-sa -> orchestrator"

# your own account too, so you can still drive the orchestrator directly for
# debugging from inside the VPC or via `gcloud run services proxy`.
ME=$(gcloud config get-value account 2>/dev/null)
gcloud run services add-iam-policy-binding orchestrator \
  --region="$REGION" --project="$PROJECT_ID" \
  --member="user:${ME}" --role="roles/run.invoker" --quiet >/dev/null
echo "   ${ME} -> orchestrator"

# ---------- publish the agent registry ----------
# Deploy-time, with the DEPLOYER's credentials. The agents cannot publish their
# own entries: each is bound by IAM Condition to its own domain database and
# has no write access to shared-db. Granting some would contradict the very
# scope the entry advertises, so publication belongs here -- the same way a
# real registry is populated by CI rather than by the running workload.
echo
echo "== publishing agent registry"
"$PY" -m scripts.publish_registry 2>/dev/null | tail -8 || \
  echo "   WARNING: registry publish failed (services are still up)"

cat <<EOF

================================================================
DEPLOYED

  PUBLIC (the only one)
    gridmind       ${WEB_URL}

  INTERNAL -- unreachable from the internet, 404 from outside the VPC
    orchestrator   ${ORCH_URL}
    gateway        ${GATEWAY_URL}
    power-agent    ${POWER_URL}
    cooling-agent  ${COOLING_URL}
    facilities     ${FACILITIES_URL}
    cost-agent     ${COST_URL}

  Demo key (skips the public rate limit):
    ${DEMO_KEY}

Open the dashboard:  ${WEB_URL}
Verify the posture:  bash scripts/demo_denial.sh
================================================================
EOF
