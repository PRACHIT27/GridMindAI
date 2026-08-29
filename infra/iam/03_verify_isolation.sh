#!/usr/bin/env bash
# Proves the IAM Conditions actually isolate the databases, rather than
# assuming they do. This is the "deliberate denial" demo moment: run it live
# and show that the denial comes from IAM itself, not from any application
# check we could have forgotten to write.
#
# WHAT THIS PROBES, AND WHY IT MATTERS
# ------------------------------------
# It calls the Firestore DATA API (documents.list) with an impersonated agent
# token -- the exact surface a Cloud Run agent uses through the client library.
#
# It deliberately does NOT use `gcloud firestore databases describe`. That hits
# the Firestore ADMIN API, which requires datastore.databases.getMetadata, a
# permission our least-privilege role omits on purpose. Testing that way makes
# every agent look locked out of its own database and tells you nothing about
# whether real data access is scoped.
#
# Prereq (testing only -- NOT granted to anything in the deployed system):
#   gcloud iam service-accounts add-iam-policy-binding SA_EMAIL \
#     --member="user:YOU@example.com" --role="roles/iam.serviceAccountTokenCreator"
set -uo pipefail
source "$(dirname "$0")/../env.sh"

probe() {  # -> prints HTTP status
  local sa="$1" db="$2" tok
  tok=$(gcloud auth print-access-token \
        --impersonate-service-account="${sa}@${PROJECT_ID}.iam.gserviceaccount.com" 2>/dev/null)
  [[ -z "$tok" ]] && { echo "000"; return; }
  curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $tok" \
    "https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/${db}/documents/zones?pageSize=1"
}

fails=0
check() {
  local sa="$1" db="$2" expect="$3"   # expect: allow|deny
  local code want
  code=$(probe "$sa" "$db")
  [[ "$expect" == "allow" ]] && want=200 || want=403

  if [[ "$code" == "$want" ]]; then
    printf '  PASS  %-22s -> %-14s HTTP %s (%s)\n' "$sa" "$db" "$code" "$expect"
  else
    printf '  FAIL  %-22s -> %-14s HTTP %s, expected %s (%s)\n' "$sa" "$db" "$code" "$want" "$expect"
    ((fails++))
  fi
}

echo "1. Each specialist agent reaches its own database:"
for d in "${DOMAINS[@]}"; do check "${d}-agent-sa" "${d}-db" allow; done

echo
echo "2. Cross-domain reads are refused by IAM, not by application code:"
check power-agent-sa      cost-db       deny
check cooling-agent-sa    power-db      deny
check facilities-agent-sa cooling-db    deny
check cost-agent-sa       facilities-db deny

echo
echo "3. The orchestrator sees verdicts only -- it cannot read raw domain data:"
check orchestrator-agent-sa shared-db     allow
for d in "${DOMAINS[@]}"; do check orchestrator-agent-sa "${d}-db" deny; done

echo
echo "4. Specialists cannot reach the shared negotiation log either:"
check power-agent-sa shared-db deny

echo
if [[ $fails -eq 0 ]]; then
  echo "ISOLATION VERIFIED -- every check passed."
else
  echo "$fails CHECK(S) FAILED -- isolation is not what the architecture claims."
  exit 1
fi
