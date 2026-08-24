#!/usr/bin/env python3
"""V6 authorization wrapper for the independent binary64 numerical core."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import f017_corrected_oracle_primary_numerics_v2 as numerical
from f017_corrected_oracle_authorization_v6 import PRIMARY_ROLE, parse_authorization, sha256_path, validate_checkpoint_root_descriptor
from f017_corrected_oracle_primary_target_source_v6 import PrimaryTargetSourceV6
from f017_corrected_oracle_wrapper_support_v6 import ROOT, bank, require_active

ORACLE_ID = "F017_INDEPENDENT_CPU_REFERENCE_V2"
CAPABILITY_SCHEMA = "pulsarmlx.f017.corrected-oracle-consumer-capability/6.0.0"
VALIDATION_SCHEMA = "pulsarmlx.f017.corrected-oracle-consumer-authorization-validation/6.0.0"
NUMERICAL_PATH = ROOT / "scripts/research/f017_corrected_oracle_primary_numerics_v2.py"
TARGET_SOURCE_PATH = ROOT / "scripts/research/f017_corrected_oracle_primary_target_source_v6.py"
DECODER_PATH = ROOT / "scripts/research/f017_oracle_primary_decoders.py"


def capability(interface: Path) -> dict:
    return {
        "schema": CAPABILITY_SCHEMA,
        "oracle_id": ORACLE_ID,
        "consumer_role": PRIMARY_ROLE,
        "authorization_schemas": ["pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/6.0.0"],
        "producer_path": Path(__file__).resolve().relative_to(ROOT).as_posix(),
        "producer_sha256": sha256_path(Path(__file__).resolve()),
        "target_source_path": TARGET_SOURCE_PATH.relative_to(ROOT).as_posix(),
        "target_source_sha256": sha256_path(TARGET_SOURCE_PATH),
        "numerical_authority_path": NUMERICAL_PATH.relative_to(ROOT).as_posix(),
        "numerical_authority_sha256": sha256_path(NUMERICAL_PATH),
        "decoder_path": DECODER_PATH.relative_to(ROOT).as_posix(),
        "decoder_sha256": sha256_path(DECODER_PATH),
        "interface_sha256": sha256_path(interface),
        "candidate_validation_command": "validate-authorization-candidate",
        "installed_validation_command": "validate-installed-authorization",
        "target_command": "target",
        "target_requires_installation_receipt": True,
    }


def validate(arguments, installed: bool) -> tuple[object, dict]:
    authority = parse_authorization(
        arguments.authorization,
        arguments.interface,
        role=PRIMARY_ROLE,
        executing_path=Path(__file__),
        target_source_path=TARGET_SOURCE_PATH,
        require_installed=installed,
        installation_receipt_path=arguments.installation_receipt if installed else None,
    )
    grant = authority.grant
    if grant["numerical_path"] != NUMERICAL_PATH.relative_to(ROOT).as_posix() or grant["numerical_sha256"] != sha256_path(NUMERICAL_PATH):
        raise ValueError("primary numerical authority")
    if grant["decoder_path"] != DECODER_PATH.relative_to(ROOT).as_posix() or grant["decoder_sha256"] != sha256_path(DECODER_PATH):
        raise ValueError("primary decoder authority")
    validate_checkpoint_root_descriptor(authority.document, arguments.checkpoint_root)
    report = {
        "schema": VALIDATION_SCHEMA,
        "result": "PASS",
        "mode": "INSTALLED" if installed else "CANDIDATE",
        "authorization_sha256": authority.sha256,
        "authorization_id": authority.document["authorization_id"],
        "package_attempt_id": authority.document["package_attempt_id"],
        "event_id": authority.document["primary_event_id"],
        "consumer_role": PRIMARY_ROLE,
        "producer_sha256": grant["producer_sha256"],
        "capability": capability(arguments.interface),
        "checkpoint_shard_opens": 0,
        "checkpoint_identity_hash_reads": 0,
        "checkpoint_mmaps": 0,
        "checkpoint_tensor_reads": 0,
        "numerical_operations": 0,
        "state_created": False,
    }
    return authority, report


def target(arguments) -> int:
    authority, _ = validate(arguments, True)
    require_active(authority.document["authority_scope"])
    if sha256_path(arguments.geometry.resolve(strict=True)) != authority.document["geometry_sha256"]:
        raise ValueError("geometry identity")
    source = PrimaryTargetSourceV6(
        authority.document,
        arguments.catalog,
        arguments.checkpoint_root,
        arguments.checkpoint_identity,
        arguments.access_event_root,
    )
    try:
        geometry = numerical.Geometry.from_json(json.loads(arguments.geometry.read_text()))
        result = numerical.execute(source, geometry, authority.document["context"]["prompt_token"], authority.document["context"]["position"])
    finally:
        source.close()
    bank(arguments.output, result)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capability"); cap.add_argument("interface", type=Path); cap.add_argument("output", type=Path)
    for name in ("validate-authorization-candidate", "validate-installed-authorization", "target"):
        command = sub.add_parser(name)
        command.add_argument("authorization", type=Path); command.add_argument("interface", type=Path)
        command.add_argument("checkpoint_root", type=Path); command.add_argument("output", type=Path)
        if name != "validate-authorization-candidate": command.add_argument("installation_receipt", type=Path)
        if name == "target":
            command.add_argument("catalog", type=Path); command.add_argument("geometry", type=Path)
            command.add_argument("checkpoint_identity", type=Path); command.add_argument("access_event_root", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "capability": bank(arguments.output, capability(arguments.interface)); return 0
    if arguments.command == "validate-authorization-candidate": _, report = validate(arguments, False); bank(arguments.output, report); return 0
    if arguments.command == "validate-installed-authorization": _, report = validate(arguments, True); bank(arguments.output, report); return 0
    return target(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
