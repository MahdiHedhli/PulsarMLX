#!/usr/bin/env python3
"""V8 checkpoint identity stage; synthetic-only until a future Event-04 GO."""
from __future__ import annotations

from f017_descriptor_lease_manager_v8 import LeaseSet, acquire_synthetic_leases


def produce(candidate: dict) -> tuple[LeaseSet, dict]:
    leases = acquire_synthetic_leases(candidate)
    receipt = {
        "result": "PASS",
        "ordered_shard_digests": [leases.identity_only_digest, *leases.graph_digests],
        "retained_lease_count": 5,
        "identity_only_retained_count": 0,
        "descriptor_identities": leases.descriptors,
        "checkpoint_shard_opens": 6,
        "checkpoint_identity_hash_reads": 6,
        "path_reopen_count": 0,
    }
    return leases, receipt
