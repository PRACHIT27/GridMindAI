#!/usr/bin/env bash
# Verify the deployed backend: every service healthy, the invoker chain wired
# correctly, and the full negotiation running end to end on Cloud Run.
#
#   bash scripts/smoke_deployed.sh
set -uo pipefail
source "$(dirname "$0")/../infra/env.sh"

TOKEN=$(gcloud auth print-identity-token)

url_of() {
  gcloud run services describe "$1" --region="$REGION" --project="$PROJECT_ID" \
    --format="value(status.url)" 2>/dev/null | tr -d '[:space:]'
}

echo "== services deployed"
gcloud run services list --region="$REGION" --project="$PROJECT_ID" \
  --format="table(metadata.name, status.url, spec.template.spec.serviceAccountName)"

echo
echo "== health checks"
# NOTE: these run as YOU. If you are project Owner, Owner carries run.invoker
# across the whole project, so every service answers 200 and this proves only
# that the containers are up -- nothing about the invoker chain.
# To actually test the invoker chain, run scripts/demo_denial.sh, which
# impersonates the service accounts that run in production.
for svc in power-agent cooling-agent facilities-agent cost-agent gateway orchestrator; do
  u=$(url_of "$svc")
  if [[ -z "$u" ]]; then
    printf '  %-16s NOT DEPLOYED\n' "$svc"; continue
  fi
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "${u}/health")
  case "$svc:$code" in
    orchestrator:200) note="reachable by you, as intended" ;;
    gateway:403)      note="only the orchestrator may invoke -- correct" ;;
    *:403)            note="only the gateway may invoke -- correct" ;;
    *:200)            note="reachable" ;;
    *)                note="unexpected" ;;
  esac
  printf '  %-16s HTTP %-4s %s\n' "$svc" "$code" "$note"
done

ORCH=$(url_of orchestrator)
[[ -z "$ORCH" ]] && { echo "orchestrator not deployed"; exit 1; }

echo
echo "== running a full negotiation on Cloud Run (this takes 30-90s)"
curl -s -X POST "${ORCH}/negotiate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"workload_id":"wl-2026-0842","scenario":"normal","format":"text"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['report'])"
