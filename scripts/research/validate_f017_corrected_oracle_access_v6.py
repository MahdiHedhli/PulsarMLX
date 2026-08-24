#!/usr/bin/env python3
"""Two-phase generation-v6 corrected-oracle authorization builder/installer.

Candidate bytes are never authority.  Installation is possible only after the
exact candidate has passed both real consumer validation-only commands.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from f017_corrected_oracle_authorization_v6 import canonical_bytes, read_regular_nofollow, strict_bytes
from f017_corrected_oracle_wrapper_support_v6 import ROOT, bank, require_active

INTERFACE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v6.json"
INERT = ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-corrected-full-checkpoint-oracle-inert-authorization-v6.json"
PRIMARY = ROOT / "scripts/research/f017_corrected_oracle_primary_v6.py"
SECONDARY = ROOT / "scripts/research/f017_corrected_oracle_secondary_v6.py"
INSTALL_RECEIPT_SCHEMA = "pulsarmlx.f017.corrected-oracle-authorization-installation-receipt/6.0.0"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def construct_candidate_from_inert(replacements: dict[str, Any], inert_path: Path = INERT) -> dict[str, Any]:
    """Construct a candidate through the production inert-template boundary.

    Every field other than the schema and generation must be supplied.  This
    prevents a future mint from silently promoting an inert identity or root.
    """
    inert = strict_bytes(read_regular_nofollow(inert_path))
    interface = strict_bytes(read_regular_nofollow(INTERFACE))
    if set(inert) != set(interface["top_level_keys"]):
        raise ValueError("inert template top-level census")
    if inert.get("schema") != interface["authorization_schema"] or inert.get("authority_generation") != 6:
        raise ValueError("inert template generation")
    if inert.get("state") != "INERT_FIXTURE" or inert.get("live") is not False:
        raise ValueError("inert template state")
    immutable = {"schema", "authority_generation"}
    expected = set(inert) - immutable
    if set(replacements) != expected:
        raise ValueError(f"candidate replacement census: {sorted(set(replacements) ^ expected)}")
    candidate = {"schema": inert["schema"], "authority_generation": 6, **replacements}
    if any(marker in candidate["authorization_id"] for marker in ("INERT", "FIXTURE", "TEST", "SYNTHETIC")):
        raise ValueError("inert identity promotion")
    return candidate


def render_candidate(document: dict[str, Any], output: Path) -> str:
    """Render exact candidate bytes without installing or creating state."""
    interface = strict_bytes(read_regular_nofollow(INTERFACE))
    if document.get("schema") != interface["authorization_schema"]:
        raise ValueError("v6 candidate schema")
    if set(document) != set(interface["top_level_keys"]):
        raise ValueError("candidate top-level census")
    if document.get("authority_generation") != 6 or document.get("state") != "AUTHORIZED" or document.get("live") is not True:
        raise ValueError("candidate lifecycle generation")
    data = canonical_bytes(document)
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    output.parent.resolve(strict=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    parent = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    if read_regular_nofollow(output) != data:
        raise ValueError("candidate readback bytes")
    return sha256_bytes(data)


def validate_candidate(
    candidate: Path,
    interface: Path,
    checkpoint_root: Path,
    report_root: Path,
) -> dict[str, Any]:
    """Run both exact consumer candidate boundaries in fresh processes."""
    candidate_sha = sha256_bytes(read_regular_nofollow(candidate))
    reports: dict[str, Any] = {}
    for role, consumer in (("primary", PRIMARY), ("secondary", SECONDARY)):
        report = report_root / f"{role}-candidate-validation.json"
        subprocess.run(
            [sys.executable, str(consumer), "validate-authorization-candidate", str(candidate), str(interface), str(checkpoint_root), str(report)],
            cwd=ROOT,
            check=True,
        )
        value = strict_bytes(read_regular_nofollow(report))
        if value.get("result") != "PASS" or value.get("authorization_sha256") != candidate_sha:
            raise ValueError(f"{role} candidate validation binding")
        if any(value.get(key) not in (0, False) for key in (
            "checkpoint_shard_opens", "checkpoint_identity_hash_reads",
            "checkpoint_mmaps", "checkpoint_tensor_reads",
            "numerical_operations", "state_created",
        )):
            raise ValueError(f"{role} candidate validation side effect")
        reports[role] = {
            "path": str(report),
            "sha256": sha256_bytes(read_regular_nofollow(report)),
            "event_id": value["event_id"],
        }
    return {
        "candidate_sha256": candidate_sha,
        "primary": reports["primary"],
        "secondary": reports["secondary"],
        "checkpoint_opens": 0,
        "checkpoint_reads": 0,
        "state_created": False,
        "result": "PASS",
    }


def install_candidate(
    candidate: Path,
    installed: Path,
    receipt_path: Path,
    handshake: dict[str, Any],
    *,
    operator_approval_sha256: str,
    allow_synthetic: bool = False,
    allow_rehearsal: bool = False,
) -> dict[str, Any]:
    """Exclusively install byte-identical candidate and bank its receipt."""
    data = read_regular_nofollow(candidate)
    document = strict_bytes(data)
    if document["authority_scope"] == "SYNTHETIC_QUALIFICATION":
        if not allow_synthetic:
            raise ValueError("synthetic installation requires explicit qualification boundary")
    elif document["authority_scope"] == "PRODUCTION_SHAPED_REHEARSAL":
        if not allow_rehearsal:
            raise ValueError("rehearsal installation requires explicit no-access boundary")
    else:
        require_active(document["authority_scope"])
        if Path(document["canonical_install_path"]) != installed:
            raise ValueError("canonical production installation path")
    if handshake.get("result") != "PASS" or handshake.get("candidate_sha256") != sha256_bytes(data):
        raise ValueError("dual-consumer handshake required")
    installed.parent.resolve(strict=True)
    descriptor = os.open(installed, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    parent = os.open(installed.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    installed_bytes = read_regular_nofollow(installed)
    if installed_bytes != data or strict_bytes(installed_bytes) != document:
        raise ValueError("candidate/install byte identity")
    installed_sha = sha256_bytes(installed_bytes)
    receipt = {
        "schema": INSTALL_RECEIPT_SCHEMA,
        "result": "PASS",
        "authorization_id": document["authorization_id"],
        "package_attempt_id": document["package_attempt_id"],
        "primary_event_id": document["primary_event_id"],
        "secondary_event_id": document["secondary_event_id"],
        "candidate_sha256": handshake["candidate_sha256"],
        "installed_authorization_sha256": installed_sha,
        "primary_validation_report_sha256": handshake["primary"]["sha256"],
        "secondary_validation_report_sha256": handshake["secondary"]["sha256"],
        "operator_approval_sha256": operator_approval_sha256,
        "installation_path": str(installed),
        "installation_timestamp_unix_ns": time.time_ns(),
        "candidate_install_byte_identity": True,
    }
    bank(receipt_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    render = sub.add_parser("render-candidate")
    render.add_argument("document", type=Path); render.add_argument("output", type=Path)
    validate = sub.add_parser("validate-candidate")
    validate.add_argument("candidate", type=Path); validate.add_argument("interface", type=Path)
    validate.add_argument("checkpoint_root", type=Path); validate.add_argument("report_root", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "render-candidate":
        document = strict_bytes(read_regular_nofollow(arguments.document))
        print(render_candidate(document, arguments.output))
        return 0
    arguments.report_root.mkdir(parents=False, exist_ok=False)
    print(canonical_bytes(validate_candidate(arguments.candidate, arguments.interface, arguments.checkpoint_root, arguments.report_root)).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
