#!/usr/bin/env python3
"""Authorization-v3 entry point for the unchanged binary64 primary oracle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

import f017_corrected_oracle_primary as numerical
from f017_corrected_oracle_authorization_v3 import (
    CONTRACT_SCHEMA,
    PRIMARY_ROLE,
    SCHEMA,
    load_and_validate,
    read_regular_nofollow,
    sha256_path,
    strict_bytes,
    strict_path,
)

ROOT = Path(__file__).resolve().parents[2]
ORACLE_ID = "F017_INDEPENDENT_CPU_REFERENCE_V1"
CAPABILITY_SCHEMA = "pulsarmlx.f017.corrected-oracle-consumer-capability/1.0.0"
VALIDATION_SCHEMA = "pulsarmlx.f017.corrected-oracle-consumer-authorization-validation/1.0.0"


def _bank(path: Path, value: dict) -> str:
    data = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
        read_descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        with os.fdopen(read_descriptor, "rb") as source:
            observed = source.read()
    finally:
        os.close(parent)
    if observed != data or strict_bytes(observed) != value:
        raise ValueError("primary report exact readback")
    return hashlib.sha256(observed).hexdigest()


def capability(contract_path: Path) -> dict:
    contract = strict_path(contract_path)
    if contract.get("schema") != CONTRACT_SCHEMA:
        raise ValueError("v3 scientific contract required")
    binding = contract["bindings"]["primary"]
    executing = Path(__file__).resolve(strict=True)
    if binding["path"] != executing.relative_to(ROOT).as_posix() or binding["sha256"] != sha256_path(executing):
        raise ValueError("primary capability producer binding")
    return {
        "schema": CAPABILITY_SCHEMA,
        "oracle_id": ORACLE_ID,
        "consumer_role": PRIMARY_ROLE,
        "authorization_schemas": [SCHEMA],
        "scientific_access_contract_schemas": [CONTRACT_SCHEMA],
        "producer_path": binding["path"],
        "producer_sha256": binding["sha256"],
        "decoder_path": contract["bindings"]["primary_decoders"]["path"],
        "decoder_sha256": contract["bindings"]["primary_decoders"]["sha256"],
        "target_command": "target",
        "validation_only_command": "validate-live-authorization",
        "numerical_authority_path": "scripts/research/f017_corrected_oracle_primary.py",
        "numerical_authority_sha256": contract["unchanged_numerical_authorities"]["primary_oracle_sha256"],
    }


def validate_live(authorization: Path, contract_path: Path, catalog: Path,
                  checkpoint_root: Path, *, root_phase: str = "PRE_MINT_OR_HANDSHAKE") -> tuple[object, dict]:
    authority = load_and_validate(
        authorization, contract_path, ROOT, require_live=True,
        role=PRIMARY_ROLE, executing_path=Path(__file__),
        root_phase=root_phase,
    )
    expected_catalog = (ROOT / authority.document["checkpoint_catalog_path"]).resolve(strict=True)
    if catalog.resolve(strict=True) != expected_catalog or sha256_path(expected_catalog) != authority.document["checkpoint_catalog_sha256"]:
        raise ValueError("primary catalog identity")
    if checkpoint_root.resolve(strict=True) != Path(authority.document["checkpoint_root"]):
        raise ValueError("primary checkpoint root identity")
    report = {
        "schema": VALIDATION_SCHEMA,
        "result": "PASS",
        "authorization_sha256": authority.sha256,
        "authorization_schema": SCHEMA,
        "authorization_id": authority.document["authorization_id"],
        "event_id": authority.primary.event_id,
        "consumer_role": PRIMARY_ROLE,
        "producer_sha256": authority.primary.producer_sha256,
        "capability": capability(contract_path),
        "checkpoint_shard_opens": 0,
        "checkpoint_identity_hash_reads": 0,
        "checkpoint_mmaps": 0,
        "checkpoint_tensor_reads": 0,
        "numerical_operations": 0,
        "state_created": False,
        "authorization_created": False,
    }
    return authority, report


class StreamingCatalogSourceV3(numerical.StreamingCatalogSource):
    """v3-authorized reader reusing the unchanged primary numerical surface."""

    def __init__(self, authority, catalog: Path, checkpoint_root: Path):
        auth = authority.document
        root = checkpoint_root.resolve(strict=True)
        document = strict_path(catalog)
        self.records = {item["name"]: item for item in document["tensors"]}
        self.shards = {item["filename"]: item for item in auth["shards"]}
        self.root, self.auth = root, auth
        self.handles: dict[str, int] = {}
        self.reads: dict[str, dict[str, int]] = {}
        event_root = os.environ.get("F017_ORACLE_ACCESS_EVENT_DIR")
        if not event_root:
            raise ValueError("durable access-event directory required")
        self.event_root = Path(event_root)
        self.event_root.mkdir(mode=0o700, parents=False, exist_ok=False)
        self.sequence = 0
        identity_path = os.environ.get("F017_ORACLE_CHECKPOINT_IDENTITY")
        if not identity_path:
            raise ValueError("checkpoint identity evidence required")
        self._event("CHECKPOINT_IDENTITY_EVIDENCE_READ_ATTEMPT", identity_path, "STARTED_READ_ONLY_NOFOLLOW")
        try:
            identity_file = Path(identity_path)
            identity_bytes = read_regular_nofollow(identity_file)
            identity = strict_bytes(identity_bytes)
            if identity.get("authorization_id") != auth["authorization_id"] or identity.get("result") != "PASS" or identity.get("shards") != auth["shards"]:
                raise ValueError("checkpoint identity evidence mismatch")
            self._event("CHECKPOINT_IDENTITY_EVIDENCE_READ_RESULT", identity_path, "PASS_BOUND", len(identity_bytes))
        except Exception as exc:
            self._event("CHECKPOINT_IDENTITY_EVIDENCE_READ_RESULT", identity_path, f"FAIL_{type(exc).__name__}")
            raise


def target(arguments) -> int:
    authority, _ = validate_live(
        arguments.authorization, arguments.contract, arguments.catalog,
        arguments.checkpoint_root, root_phase="POST_PACKAGE_START",
    )
    if sha256_path(arguments.geometry.resolve(strict=True)) != authority.document["geometry_sha256"]:
        raise ValueError("geometry identity mismatch")
    source = StreamingCatalogSourceV3(authority, arguments.catalog, arguments.checkpoint_root)
    try:
        result = numerical.execute(
            source,
            numerical.Geometry.from_json(strict_path(arguments.geometry)),
            authority.document["prompt_token"],
            authority.document["position"],
        )
    finally:
        source.close()
    _bank(arguments.output, result)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capability")
    cap.add_argument("contract", type=Path)
    cap.add_argument("output", type=Path)
    check = sub.add_parser("validate-live-authorization")
    check.add_argument("authorization", type=Path)
    check.add_argument("contract", type=Path)
    check.add_argument("catalog", type=Path)
    check.add_argument("checkpoint_root", type=Path)
    check.add_argument("output", type=Path)
    run = sub.add_parser("target")
    run.add_argument("authorization", type=Path)
    run.add_argument("contract", type=Path)
    run.add_argument("catalog", type=Path)
    run.add_argument("checkpoint_root", type=Path)
    run.add_argument("geometry", type=Path)
    run.add_argument("output", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "capability":
        _bank(arguments.output, capability(arguments.contract))
        return 0
    if arguments.command == "validate-live-authorization":
        _, report = validate_live(arguments.authorization, arguments.contract, arguments.catalog, arguments.checkpoint_root)
        _bank(arguments.output, report)
        return 0
    return target(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
