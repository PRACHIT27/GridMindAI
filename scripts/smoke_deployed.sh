#!/usr/bin/env bash
# Verify the deployed system: one public door, six internal services, and a
# full negotiation running end to end through the private path.
#
#   bash scripts/smoke_deployed.sh
set -uo pipefail
source "$(dirname "$0")/../infra/env.sh"

url_of() {
  gcloud run services describe "$1" --region="$REGION" --project="$PROJECT_ID" \
    --format="value(status.url)" 2>/dev/null | tr -d '[:space:]'
}

echo "== services"
gcloud run services list --region="$REGION" --project="$PROJECT_ID" \
  --format="table(metadata.name, status.url, spec.template.spec.serviceAccountName)"

WEB=$(url_of web)
[[ -z "$WEB" ]] && { echo "web not deployed"; exit 1; }

echo
echo "== public surface (no credentials at all)"
for p in health api/workloads api/decisions api/memory; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 30 "${WEB}/${p}")
  printf '  %-22s HTTP %s\n' "/$p" "$code"
done

echo
echo "== everything else must be UNREACHABLE from here"
# 404 rather than 403: ingress=internal means Google will not even acknowledge
# these services exist to a caller outside the VPC.
for svc in orchestrator gateway power-agent cooling-agent facilities-agent cost-agent; do
  u=$(url_of "$svc")
  [[ -z "$u" ]] && { printf '  %-18s NOT DEPLOYED\n' "$svc"; continue; }
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 20 "${u}/health")
  if [[ "$code" == "404" ]]; then
    printf '  PASS  %-18s HTTP 404 (internal)\n' "$svc"
  else
    printf '  FAIL  %-18s HTTP %s (expected 404)\n' "$svc" "$code"
  fi
done

echo
echo "== full negotiation via the public dashboard (60-90s)"
KEY="${GRIDMIND_DEMO_KEY:-}"
curl -s -m 700 -X POST "${WEB}/api/negotiate" \
  -H "Content-Type: application/json" \
  ${KEY:+-H "X-Demo-Key: ${KEY}"} \
  -d '{"workload_id":"wl-2026-0842","scenario":"normal"}' \
  | python -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print('  no JSON returned'); sys.exit(1)
if not d.get('decision'):
    print('  FAILED:', json.dumps(d)[:400]); sys.exit(1)
dec = d['decision']
print(f\"  outcome  {dec['outcome']}\")
print(f\"  zone     {dec['chosen_zone']}\")
print(f\"  delay    {dec['delay_hours']} h\")
print(f\"  rounds   {len(d['rounds'])}\")
for r in d['rounds']:
    v = ', '.join(f\"{x['agent']}={x['status']}/{x['target_zone']}\" for x in r['verdicts'])
    print(f\"   round {r['round']} [{r['conflict_type']}]: {v}\")
"

echo
echo "Dashboard: ${WEB}"
