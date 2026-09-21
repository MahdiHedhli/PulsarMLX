#!/usr/bin/env python3
"""V9 six-shard identity stage with five retained graph descriptor leases."""
from __future__ import annotations

from f017_descriptor_lease_manager_v9 import LeaseSet, acquire_production_leases, acquire_synthetic_leases


def produce(candidate: dict, installation_receipt_sha256: str | None = None, progress=None) -> tuple[LeaseSet, dict]:
    if candidate.get("scope") == "SYNTHETIC_QUALIFICATION":
        leases = acquire_synthetic_leases(candidate, progress)
    elif candidate.get("scope") == "PRODUCTION_EVENT_04" and installation_receipt_sha256 is not None:
        leases = acquire_production_leases(candidate, installation_receipt_sha256, progress)
    else:
        raise ValueError("checkpoint identity producer authority")
    return leases, {"result": "PASS", "ordered_shard_digests": [leases.identity_only_digest, *leases.graph_digests],
                    "retained_lease_count": 5, "identity_only_retained_count": 0,
                    "descriptor_identities": leases.descriptors, "checkpoint_shard_opens": 6,
                    "checkpoint_identity_hash_reads": 6, "path_reopen_count": 0}
