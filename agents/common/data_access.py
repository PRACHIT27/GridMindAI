"""Part 2 of the constraint context: live facility state from Firestore.

THE SCOPED TOOL BOUNDARY
------------------------
Every Firestore read an agent performs goes through this module, and this
module can only ever open the ONE database that agent's identity is bound to.

The real enforcement is IAM, not this code. A Cloud Run service running as
power-agent-sa carries a conditional binding limiting it to power-db; if this
module were edited to open cost-db, Firestore would return 403 and the agent
would fail rather than leak. The assertion below is a fast, legible failure for
an obvious mistake -- not the security control. Verified empirically by
infra/iam/03_verify_isolation.sh.

GCP mapping for an AWS/Azure background: the Cloud Run service's service
account is the equivalent of an ECS task role or an Azure managed identity.
Application Default Credentials picks it up automatically inside Cloud Run, so
there are no keys to distribute -- one of the genuinely nicer parts of this
stack.
"""
from __future__ import annotations

import threading
from typing import Any

from google.cloud import firestore

from . import obs
from .auth import get_credentials
from .config import DOMAIN_DATABASES, PROJECT_ID, SHARED_DATABASE


class DatabaseAccessError(RuntimeError):
    """Raised when an agent asks for a database its identity has no claim to."""


_clients: dict[str, firestore.Client] = {}
_clients_lock = threading.Lock()


def _client(database: str) -> firestore.Client:
    """One client per database, shared across threads.

    Cached because constructing a Firestore client per request adds latency to
    a cold-start-sensitive, scale-to-zero service for no benefit.

    Locked rather than @lru_cache because the orchestrator calls four agents
    concurrently: lru_cache does not guarantee the factory runs once, so
    duplicate clients can be built and then garbage collected, closing a
    transport another thread is still using.
    """
    hit = _clients.get(database)
    if hit is not None:
        return hit
    with _clients_lock:
        if database not in _clients:
            _clients[database] = firestore.Client(
                project=PROJECT_ID, database=database, credentials=get_credentials())
        return _clients[database]


def client_for(domain: str) -> firestore.Client:
    """Open the single database this domain is permitted to read."""
    if domain not in DOMAIN_DATABASES:
        raise DatabaseAccessError(f"no database mapping for domain {domain!r}")
    return _client(DOMAIN_DATABASES[domain])


def shared_client() -> firestore.Client:
    """shared-db: workload_queue, negotiation_log, memory_bank.

    Reachable by the orchestrator only. A specialist agent calling this gets a
    403 from Firestore -- confirmed by the isolation test, check 4.
    """
    return _client(SHARED_DATABASE)


def read_zone_state(domain: str, *, correlation_id: str | None = None) -> dict[str, Any]:
    """Read this domain's view of every zone in the facility.

    Each domain database holds a `zones` collection keyed by the same zone ids,
    but with entirely different fields -- power knows about breakers, cooling
    knows about CDUs, facilities knows about rack counts. Same subject, four
    incompatible views. That mismatch IS the problem this system exists to
    solve, so it is modelled rather than smoothed away.
    """
    db = client_for(domain)
    with obs.timed("firestore_read", agent=domain, correlation_id=correlation_id,
                   database=DOMAIN_DATABASES[domain], collection="zones") as extra:
        zones = {doc.id: doc.to_dict() for doc in db.collection("zones").stream()}
        extra["zone_count"] = len(zones)

    if not zones:
        # Distinguish "the facility has no capacity" from "the seed script never
        # ran". Silently reasoning over an empty facility would produce a
        # confident, wrong verdict.
        obs.log("empty_zone_state", level="warn", agent=domain,
                correlation_id=correlation_id,
                message=f"{DOMAIN_DATABASES[domain]} has no zones; did the seed script run?")
    return zones


def read_domain_meta(domain: str, *, correlation_id: str | None = None) -> dict[str, Any]:
    """Facility-wide state for this domain that is not per-zone.

    Power keeps substation loading here, cooling keeps plant status, cost keeps
    month-to-date spend against budget.
    """
    db = client_for(domain)
    doc = db.collection("facility").document("current").get()
    if not doc.exists:
        obs.log("missing_facility_doc", level="warn", agent=domain,
                correlation_id=correlation_id, database=DOMAIN_DATABASES[domain])
        return {}
    return doc.to_dict() or {}


def read_live_data(domain: str, *, correlation_id: str | None = None) -> dict[str, Any]:
    """The complete live-state half of the constraint context for one domain."""
    return {
        "zones": read_zone_state(domain, correlation_id=correlation_id),
        "facility_state": read_domain_meta(domain, correlation_id=correlation_id),
    }
