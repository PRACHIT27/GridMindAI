#!/usr/bin/env bash
# Shared configuration for all GridMind infra scripts.
# Source this: `source infra/env.sh`

export PROJECT_ID="gridmindai-507000"
export PROJECT_NUMBER="1036110596083"

# Firestore + Cloud Run colocated in Northern Virginia ("Data Center Alley"),
# which is also the facility our seed data simulates.
export REGION="us-east4"

# One database per domain. Isolation is enforced by IAM Conditions (see
# 02_create_role_and_bind.sh), NOT by Firestore Security Rules -- those do not
# apply to server-side Admin SDK access.
# Not exported: bash cannot export arrays. These scripts `source` env.sh.
DOMAINS=(power cooling facilities cost)
export CUSTOM_ROLE="gridmindAgentAccess"

gcloud config set project "$PROJECT_ID" >/dev/null 2>&1
