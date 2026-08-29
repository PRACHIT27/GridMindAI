"""Central configuration for every GridMind agent.

Kept in one place so a model swap or region change is a one-line edit rather
than a grep across six services.
"""
from __future__ import annotations

import os

PROJECT_ID: str = os.environ.get("GRIDMIND_PROJECT_ID", "gridmindai-507000")
PROJECT_NUMBER: str = "1036110596083"

# Cloud Run and Firestore live in Northern Virginia, colocated with the
# facility the seed data simulates.
REGION: str = os.environ.get("GRIDMIND_REGION", "us-east4")

# IMPORTANT: Gemini 3.5 is served ONLY from the Vertex AI `global` endpoint.
# Probing us-east4 and us-central1 for gemini-3.5-* returns 404, while the
# global endpoint returns 200. The hackathon requires "Gemini 3.5 or newer",
# so this must stay "global" -- pointing it at REGION silently drops us to a
# non-compliant model or fails outright.
VERTEX_LOCATION: str = os.environ.get("GRIDMIND_VERTEX_LOCATION", "global")

# Model tiering. There is no gemini-3.5-pro yet (404 on every endpoint), so we
# tier by THINKING BUDGET rather than by model family:
#   - specialists make one narrow domain judgment  -> lite, low thinking
#   - the orchestrator reconciles conflicting plans -> flash, high thinking
MODEL_SPECIALIST: str = os.environ.get("GRIDMIND_MODEL_SPECIALIST", "gemini-3.5-flash-lite")
MODEL_ORCHESTRATOR: str = os.environ.get("GRIDMIND_MODEL_ORCHESTRATOR", "gemini-3.5-flash")

# Gemini 3.5 models spend tokens on internal reasoning BEFORE emitting output.
# A tight cap yields finishReason=MAX_TOKENS with an empty candidate -- observed
# during setup: a 20-token cap produced 17 thought tokens and zero output.
# These ceilings leave room for thought plus a full JSON verdict.
# CRITICAL: thinking tokens are drawn from the SAME budget as output tokens.
# A 4096 thinking budget inside a 4096 ceiling leaves zero room for the answer
# and returns JSON truncated mid-string. The ceiling must comfortably exceed
# the thinking budget plus the largest expected response.
MAX_OUTPUT_TOKENS_SPECIALIST: int = 2048        # vs 512 thinking
MAX_OUTPUT_TOKENS_ORCHESTRATOR: int = 16384     # vs 4096 thinking

# Harness retry policy (see harness.py).
MAX_ATTEMPTS: int = 3
BACKOFF_MULTIPLIER: float = 1.0
BACKOFF_MAX_SECONDS: float = 8.0

# Negotiation is bounded so a disagreement can never burn the credit budget in
# an infinite re-prompt loop. Round 1 is the independent check; rounds 2-3 are
# reconciliation attempts. Unresolved after that => escalate to a human.
MAX_NEGOTIATION_ROUNDS: int = 3

# Which database each agent identity is permitted to touch. This mirrors the
# IAM Conditions applied in infra/iam/02_create_role_and_bind.sh -- the IAM
# binding is the enforcement, this dict is only for routing and for the
# gateway's allow/deny table.
DOMAIN_DATABASES: dict[str, str] = {
    "power": "power-db",
    "cooling": "cooling-db",
    "facilities": "facilities-db",
    "cost": "cost-db",
    "orchestrator": "shared-db",
}

SHARED_DATABASE: str = "shared-db"

# The single facility modelled in Phase 1.
FACILITY_ID: str = "iad-dc-01"
