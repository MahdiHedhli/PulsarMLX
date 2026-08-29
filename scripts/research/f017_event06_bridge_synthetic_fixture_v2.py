#!/usr/bin/env python3
"""Synthetic-only prompt-bound bridge fixtures; never resolve checkpoint paths."""
from __future__ import annotations

import hashlib
import shutil
import stat
import tempfile
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority
from f017_descriptor_lease_manager_v10 import LeaseRecord, LeaseSet
from f017_event06_numerical_bridge_v1 import bind_identity_stage
from f017_event06_numerical_bridge_v2 import produce_identity_bridge_input, derive_bridge
from f017_event06_sequence14_fixture_v1 import build_sequence14_qualification

PROMPT_BYTES = b"SYNTHETIC NON-AUTHORITY SEQUENCE 12 PROMPT\n"
PROMPT_COMMIT = "1" * 40
PROMPT_PATH = "Prompts/F017/SYNTHETIC-NON-AUTHORITY-SEQUENCE-12.md"


def runtime_fixture_values(*, qualification_root: Path | None = None):
    """Compose the accepted collapsed producer with the numerical bridge.

    The checkpoint boundary is interposed after the real installed triple.  No
    checkpoint alias or original path is resolved; descriptor identities and
    identity receipts are deterministic qualification-only values.
    """
    fixture_root = (
        qualification_root
        if qualification_root is not None
        else Path(tempfile.gettempdir()) / "f017-seq17-bridge-runtime-fixture"
    )
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    try:
        package = build_sequence14_qualification(
            fixture_root, now_unix_ns=4_000_000_000_000_000_000
        )
        event_identity = package["identity"]
        plan = package["plan"]
        installed_triple = package["installed"]
        actual_installed = installed_triple.authority
    finally:
        if qualification_root is None and fixture_root.exists():
            shutil.rmtree(fixture_root)
    if qualification_root is None:
        installed_value = {
            "schema": "pulsarmlx.f017.corrected-oracle-checkpoint-identity-installed-authority/12.1.0",
            "generation": "V12",
            "authority_scope": "SYNTHETIC_NON_AUTHORITY",
            "operation_class": "QUALIFICATION_ONLY",
            "authorization_id": event_identity.get("authorization_id"),
            "package_attempt_id": event_identity.get("package_attempt_id"),
            "checkpoint_set_sha256": actual_installed.get("checkpoint_set_sha256"),
            "event_identity_plan_sha256": event_identity.source_sha256,
            "installation_receipt_sha256": "b" * 64,
        }
        installed = ValidatedIdentityAuthority(
            tuple(sorted(installed_value.items())),
            hashlib.sha256(canonical_bytes(installed_value)).hexdigest(),
            "INSTALLED",
        )
    else:
        installed = actual_installed
    package_attempt_id = plan.get("package_attempt_id")
    shards = plan.get("shards")
    descriptors = [{
        "device": 1, "inode": ordinal, "mode": stat.S_IFREG | 0o600,
        "size": shards[ordinal - 1]["size_bytes"],
        "mtime_ns": ordinal, "ctime_ns": ordinal,
        "shard_ordinal": ordinal, "role": "GRAPH_PAYLOAD",
        "lease_id": f"LEASE-{package_attempt_id}-{ordinal}",
    } for ordinal in range(2, 7)]
    leases = LeaseSet(
        [LeaseRecord(item, 2000 + item["shard_ordinal"]) for item in descriptors],
        hashlib.sha256(b"synthetic-identity-only").hexdigest(),
        [item["sha256"] for item in shards[1:]],
    )
    report = {
        "result": "PASS", "authority_scope": "SYNTHETIC_NON_AUTHORITY",
        "operation_class": "IDENTITY_ONLY", "generation": "V12",
        "ordered_shard_digests": [item["sha256"] for item in shards],
        "checkpoint_shard_opens": 6, "checkpoint_identity_hash_reads": 6,
        "retained_lease_count": 5, "identity_only_retained_count": 0,
        "descriptor_identities": descriptors, "path_reopen_count": 0,
        "evidence": {
            "access_journal_sha256": "1" * 64, "shard_receipts_sha256": "2" * 64,
            "lease_manifest_sha256": "3" * 64, "deterministic_core_sha256": "4" * 64,
            "identity_manifest_sha256": "5" * 64, "identity_receipt_sha256": "6" * 64,
            "identity_terminal_sha256": "7" * 64, "identity_terminal_state": "COMPLETE",
        },
    }
    identity_stage = bind_identity_stage(installed, leases, report)
    bridge_input = produce_identity_bridge_input(event_identity, installed, plan)
    bridge = derive_bridge(bridge_input, installed, identity_stage, plan)
    values = (bridge, bridge_input, event_identity, installed, leases, report, identity_stage, plan)
    if qualification_root is not None:
        return values + (installed_triple,)
    return values


if __name__ == "__main__":
    bridge, bridge_input, event_identity, *_ = runtime_fixture_values()
    print(bridge.sha256, bridge_input.sha256, event_identity.source_sha256)
