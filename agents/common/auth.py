"""Credential resolution for both Cloud Run and a local developer machine.

IN CLOUD RUN there is nothing to do: the service runs as its bound service
account and Application Default Credentials picks it up from the metadata
server. No keys, no files, no secrets to rotate. (Same idea as an ECS task role
or an Azure managed identity.)

LOCALLY, ADC normally requires `gcloud auth application-default login`, which
opens a browser. To keep a first run from dead-ending on that, this module
falls back to the access token from the developer's existing gcloud session.

The fallback is DEVELOPMENT ONLY. It is never used in Cloud Run, because ADC
resolves first there. It also supports --impersonate-service-account, which is
what lets a developer reproduce exactly what one agent identity can and cannot
see.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

import google.auth
from google.auth.credentials import Credentials
from google.oauth2.credentials import Credentials as TokenCredentials

from . import obs

_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

# The orchestrator runs all four specialists CONCURRENTLY. Without this lock
# and cache, four threads each shell out to `gcloud auth print-access-token` at
# the same instant; the calls collide and some return empty, so agents fail
# their retries and the harness fails them safe to "infeasible". The symptom is
# brutal to read -- three agents refusing a request for no stated reason, an
# entire negotiation round wasted, and real money spent on the retries.
#
# One token fetch, shared across threads, refreshed before it expires.
_lock = threading.Lock()
_cache: dict[str, tuple[str, float]] = {}
_TOKEN_TTL_SECONDS = 45 * 60      # gcloud tokens last ~60 min; refresh early


def _gcloud_token(impersonate: str | None) -> str | None:
    """Fetch a token, once, and share it across threads."""
    key = impersonate or "__default__"

    with _lock:
        hit = _cache.get(key)
        if hit and time.monotonic() < hit[1]:
            return hit[0]

        cmd = ["gcloud", "auth", "print-access-token"]
        if impersonate:
            cmd.append(f"--impersonate-service-account={impersonate}")
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=90,
                                 shell=os.name == "nt")
        except (OSError, subprocess.SubprocessError):
            return None

        token = out.stdout.strip()
        if not token:
            return None
        _cache[key] = (token, time.monotonic() + _TOKEN_TTL_SECONDS)
        return token


def get_credentials() -> Credentials | None:
    """Resolve credentials, preferring ADC.

    Returns None when ADC works, so callers can simply omit the argument and
    let each client library resolve for itself -- the normal Cloud Run path.
    """
    impersonate = os.environ.get("GRIDMIND_IMPERSONATE_SA")

    if not impersonate:
        try:
            google.auth.default(scopes=_SCOPES)
            return None
        except google.auth.exceptions.DefaultCredentialsError:
            pass

    token = _gcloud_token(impersonate)
    if token is None:
        raise RuntimeError(
            "No credentials available. In Cloud Run this cannot happen. Locally, run:\n"
            "  gcloud auth application-default login\n"
            "or ensure `gcloud auth print-access-token` succeeds."
        )

    obs.log("using_local_gcloud_credentials", level="warn",
            impersonating=impersonate or "(active gcloud account)",
            message="Development credential fallback in use -- not a Cloud Run path.")
    return TokenCredentials(token=token)
