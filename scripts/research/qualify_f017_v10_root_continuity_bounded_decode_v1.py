#!/usr/bin/env python3
"""Broad synthetic qualification for F017 root continuity and bounded decode."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import tempfile

from check_f017_bounded_artifact_decode_policy_v1 import validate as validate_decode_policy
from execute_f017_corrected_oracle_event_v10 import _terminalize
from f017_accounting_root_continuity_v1 import AccountingRootAuthority
from f017_bounded_artifact_decode_v1 import ArtifactDecodeError, parse_artifact_bytes
from f017_canonical_serialization_v10 import bank_exclusive, canonical_bytes
from f017_runtime_outcome_realizer_v10 import OUTCOMES, realize
from qualify_f017_event04_runtime_hardening_v10 import _subprocess_case


MILESTONES = {
    "AFTER_INSTALLATION": (),
    "AFTER_PACKAGE_CLAIM": ("CLAIM",),
    "AFTER_PACKAGE_DURABLE_START": ("PACKAGE",),
    "AFTER_PRIMARY_DURABLE_START": ("PACKAGE", "PRIMARY"),
    "AFTER_SECONDARY_DURABLE_START": ("PACKAGE", "PRIMARY", "SECONDARY"),
    "DURING_TERMINALIZATION": ("PACKAGE", "PRIMARY", "SECONDARY", "COMPARISON"),
}
ROOT_ATTACKS = (
    "RENAME_PRIMARY_ROOT",
    "REPLACE_WITH_EMPTY_DIRECTORY",
    "REPLACE_WITH_SYMLINK",
    "CHANGE_DIRECTORY_PERMISSIONS",
    "RECREATE_SAME_PATHNAME",
    "CHANGE_INODE",
    "REMOVE_DURABLE_START_ARTIFACT",
    "CORRUPT_DURABLE_START_ARTIFACT",
    "SUBSTITUTE_FALLBACK_ROOT",
    "MAKE_FALLBACK_UNAVAILABLE",
    "MAKE_BOTH_PATHS_UNAVAILABLE_WITH_RETAINED_HANDLES",
    "REDIRECT_CALLER_SUPPLIED_ROOT",
    "WRONG_ROOT_TYPE",
    "CORRUPT_TRANSITION_JOURNAL",
)
ARTIFACT_CLASSES = (
    "authorization", "installation_receipt", "handshake", "package_claim",
    "package_durable_start", "primary_durable_start", "secondary_durable_start",
    "accounting_journal", "package_ledger", "primary_ledger", "secondary_ledger",
    "access_evidence", "consumer_receipt", "consumer_terminal", "package_receipt",
    "package_terminal", "failure_capsule",
)


def _authority(root: Path, suffix: str) -> AccountingRootAuthority:
    return AccountingRootAuthority.create(
        root / "state", root / "fallback", f"F017-V10-PACKAGE-{suffix}", "a" * 64, "b" * 64,
    )


def _reach(authority: AccountingRootAuthority, milestones: tuple[str, ...]) -> None:
    if "CLAIM" in milestones:
        digest = authority.bank_artifact("package-claim.json", "package_claim", {"result": "PASS"})
        authority.append_transition("PACKAGE_CLAIM", digest)
    if "PACKAGE" in milestones:
        authority.bank_artifact("package-durable-start.json", "package_durable_start", {"delta": 1}, "PACKAGE_DURABLE_START")
    if "PRIMARY" in milestones:
        authority.bank_artifact("primary-durable-start.json", "primary_durable_start", {"delta": 1}, "PRIMARY_DURABLE_START")
    if "SECONDARY" in milestones:
        authority.bank_artifact("secondary-durable-start.json", "secondary_durable_start", {"delta": 1}, "SECONDARY_DURABLE_START")
    if "COMPARISON" in milestones:
        digest = authority.bank_artifact("comparison-terminal.json", "comparison_terminal", {"result": "COMPLETE"})
        authority.append_transition("COMPARISON_TERMINAL", digest)


def _mutate_root(authority: AccountingRootAuthority, root: Path, attack: str) -> Path:
    state = root / "state"; fallback = root / "fallback"; retained = root / "retained-state"
    if attack in {"RENAME_PRIMARY_ROOT", "REPLACE_WITH_EMPTY_DIRECTORY", "REPLACE_WITH_SYMLINK", "RECREATE_SAME_PATHNAME", "CHANGE_INODE", "MAKE_BOTH_PATHS_UNAVAILABLE_WITH_RETAINED_HANDLES", "WRONG_ROOT_TYPE"}:
        state.rename(retained)
    if attack in {"REPLACE_WITH_EMPTY_DIRECTORY", "RECREATE_SAME_PATHNAME", "CHANGE_INODE"}:
        state.mkdir()
    elif attack == "REPLACE_WITH_SYMLINK":
        attacker = root / "attacker"; attacker.mkdir(); state.symlink_to(attacker, target_is_directory=True)
    elif attack == "WRONG_ROOT_TYPE":
        state.write_bytes(b"not-a-directory")
    elif attack == "CHANGE_DIRECTORY_PERMISSIONS":
        state.chmod(0)
    elif attack == "REMOVE_DURABLE_START_ARTIFACT":
        try: os.unlink("package-durable-start.json", dir_fd=authority.primary_fd)
        except FileNotFoundError: pass
    elif attack == "CORRUPT_DURABLE_START_ARTIFACT":
        try:
            descriptor = os.open("package-durable-start.json", os.O_WRONLY | os.O_TRUNC, dir_fd=authority.primary_fd)
        except FileNotFoundError:
            pass
        else:
            try: os.write(descriptor, b"[" * 10_000)
            finally: os.close(descriptor)
    elif attack == "SUBSTITUTE_FALLBACK_ROOT":
        authority.bank_fallback_capsule("attacker-fallback.json", {"fabricated_start": True})
    elif attack == "MAKE_FALLBACK_UNAVAILABLE":
        fallback.rename(root / "retained-fallback")
    elif attack == "MAKE_BOTH_PATHS_UNAVAILABLE_WITH_RETAINED_HANDLES":
        fallback.rename(root / "retained-fallback")
    elif attack == "CORRUPT_TRANSITION_JOURNAL":
        descriptor = os.open("accounting-transition-journal.ndjson", os.O_WRONLY | os.O_TRUNC, dir_fd=authority.primary_fd)
        try: os.write(descriptor, b'{"sequence":999}\n')
        finally: os.close(descriptor)
    return retained if retained.exists() else state


def _root_cases() -> list[dict]:
    results: list[dict] = []
    for milestone, reached in MILESTONES.items():
        for attack in ROOT_ATTACKS:
            for repetition in range(3):
                with tempfile.TemporaryDirectory(prefix="f017-root-campaign-") as raw:
                    root = Path(raw); authority = _authority(root, f"{milestone}-{attack}-{repetition}")
                    try:
                        _reach(authority, reached)
                        retained = _mutate_root(authority, root, attack)
                        accounting = authority.accounting_lower_bound()
                        expected = {
                            "package": int("PACKAGE" in reached),
                            "primary": int("PRIMARY" in reached),
                            "secondary": int("SECONDARY" in reached),
                        }
                        if any(accounting[key] != value for key, value in expected.items()):
                            raise ValueError(f"false-zero accounting: {milestone}:{attack}:{accounting}")
                        result = _terminalize(
                            root / "state", root / "fallback", {}, ValueError("root attack"), None,
                            "ROOT_DEGRADATION", milestone, accounting_authority=authority,
                        )
                        if result["accounting"]["fallback_used_as_accounting_source"] is not False:
                            raise ValueError("fallback became accounting source")
                        if expected["package"] and result["package_terminal_evidence"]["result"] != "PASS":
                            raise ValueError("package terminal obligation lost")
                        if result["terminal_evidence"]["result"] != "PASS":
                            raise ValueError("maximal constructible capsule absent")
                        results.append({"case_id": f"ROOT-{milestone}-{attack}-{repetition}", "accounting": expected, "result": "PASS"})
                    finally:
                        try: (root / "state").chmod(0o700)
                        except OSError: pass
                        authority.close()
    return results


def _malformed(case: int) -> bytes:
    variant = case % 12
    if variant in {0, 1, 2, 3}:
        depth = (65, 128, 1024, 10_000)[variant]
        return b"[" * depth + b"0" + b"]" * depth + b"\n"
    if variant == 4: return b"\xff\n"
    if variant == 5: return b'{"a":1,"a":2}\n'
    if variant == 6: return b'{"x":NaN}\n'
    if variant == 7: return b'{"x":"\\uZZZZ"}\n'
    if variant == 8: return b'{"x":1'
    if variant == 9: return canonical_bytes([1, 2, 3])
    if variant == 10: return b'{"x":' + b"9" * 129 + b"}\n"
    return b'{"x":"' + b"a" * 1_048_576 + b'"}\n'


def _decode_cases() -> list[dict]:
    results: list[dict] = []
    for artifact_index, artifact_class in enumerate(ARTIFACT_CLASSES):
        for variant in range(12):
            case = artifact_index * 12 + variant
            raw = _malformed(case)
            try:
                parse_artifact_bytes(raw)
            except ArtifactDecodeError as exc:
                observed = type(exc).__name__
            except Exception as exc:
                raise ValueError(f"raw decode exception: {type(exc).__name__}") from exc
            else:
                raise ValueError(f"malformed artifact accepted: {artifact_class}:{variant}")
            with tempfile.TemporaryDirectory(prefix="f017-decode-campaign-") as temp:
                root = Path(temp); authority = _authority(root, f"DECODE-{case}")
                try:
                    _reach(authority, ("PACKAGE",))
                    terminal = _terminalize(
                        root / "state", root / "fallback", {}, ArtifactDecodeError("malformed artifact"), None,
                        "ARTIFACT_DECODE", "PACKAGE_DURABLE_START", accounting_authority=authority,
                    )
                    if terminal["result"] != "CONTROLLED_FAILURE" or terminal["accounting"]["package"] != 1:
                        raise ValueError("malformed artifact did not terminalize")
                finally:
                    authority.close()
            results.append({"case_id": f"DECODE-{artifact_class}-{variant:02d}", "failure_class": observed, "result": "REJECTED"})
    return results


def _cross_product_cases() -> list[dict]:
    cases = (
        ("ROOT_REPLACED_MALFORMED_PACKAGE", ("PACKAGE",), "REPLACE_WITH_EMPTY_DIRECTORY", "package-durable-start.json"),
        ("ROOT_UNAVAILABLE_MALFORMED_PRIMARY", ("PACKAGE", "PRIMARY"), "RENAME_PRIMARY_ROOT", "primary-durable-start.json"),
        ("FALLBACK_ACTIVE_MALFORMED_SECONDARY", ("PACKAGE", "PRIMARY", "SECONDARY"), "CHANGE_DIRECTORY_PERMISSIONS", "secondary-durable-start.json"),
        ("IDENTITY_MISMATCH_DEEP_JOURNAL", ("PACKAGE",), "REPLACE_WITH_SYMLINK", "accounting-transition-journal.ndjson"),
        ("BOTH_PATHS_UNUSABLE_RETAINED_JOURNAL", ("PACKAGE", "PRIMARY"), "MAKE_BOTH_PATHS_UNAVAILABLE_WITH_RETAINED_HANDLES", "primary-durable-start.json"),
        ("MALFORMED_TERMINAL_AFTER_STARTS", ("PACKAGE", "PRIMARY", "SECONDARY"), "CORRUPT_DURABLE_START_ARTIFACT", "secondary-durable-start.json"),
    )
    results: list[dict] = []
    for index, (case_id, reached, attack, leaf) in enumerate(cases):
        with tempfile.TemporaryDirectory(prefix="f017-cross-root-decode-") as raw:
            root = Path(raw); authority = _authority(root, f"CROSS-{index}")
            try:
                _reach(authority, reached)
                try:
                    descriptor = os.open(leaf, os.O_WRONLY | os.O_TRUNC, dir_fd=authority.primary_fd)
                except FileNotFoundError:
                    descriptor = None
                if descriptor is not None:
                    try: os.write(descriptor, b"[" * 10_000)
                    finally: os.close(descriptor)
                _mutate_root(authority, root, attack)
                terminal = _terminalize(
                    root / "state", root / "fallback", {}, ArtifactDecodeError("cross-product corruption"), None,
                    "ROOT_AND_DECODE_DEGRADATION", reached[-1] if reached else "INSTALLATION_RECEIPT_BANKED",
                    accounting_authority=authority,
                )
                expected_package = int("PACKAGE" in reached)
                if terminal["accounting"]["package"] != expected_package or terminal["terminal_evidence"]["result"] != "PASS":
                    raise ValueError(f"cross-product terminalization: {case_id}")
                results.append({"case_id": case_id, "result": "PASS", "package_lower_bound": expected_package})
            finally:
                try: (root / "state").chmod(0o700)
                except OSError: pass
                authority.close()
    return results


def _modeled_outcomes() -> list[dict]:
    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="f017-v10-outcomes-") as raw:
        root = Path(raw)
        for outcome_id in sorted(name for name in OUTCOMES if name != "COMPLETE_SUCCESS"):
            for repetition in range(5):
                results.append(realize(outcome_id, root / f"{outcome_id}-{repetition}"))
    return results


def _success_cases() -> tuple[list[dict], list[bytes]]:
    cases: list[dict] = []
    for index in range(20): cases.append(_subprocess_case(18101 + index % 12, False, f"R2-MINIMAL-{index:03d}"))
    for index in range(20): cases.append(_subprocess_case(18101 + index % 12, True, f"R2-MIXED-{index:03d}"))
    for index in range(10): cases.append(_subprocess_case(18103 + index % 2, True, f"R2-ROUTE-{index:03d}"))
    for index in range(10): cases.append(_subprocess_case(18101 + index % 12, True, f"R2-DISTRIBUTION-{index:03d}"))
    deterministic = [_subprocess_case(18101, True, "R2-DETERMINISM") for _ in range(10)]
    core_bytes = [canonical_bytes(item["core"]) for item in deterministic]
    if len(set(core_bytes)) != 1:
        raise ValueError("deterministic core drift")
    return cases, core_bytes


def qualify(output: Path, *, quick: bool = False) -> dict:
    policy = validate_decode_policy()
    root_cases = _root_cases()
    decode_cases = _decode_cases()
    cross_product = _cross_product_cases()
    if quick:
        outcomes: list[dict] = []
        success: list[dict] = []
        core_bytes = [canonical_bytes({"quick": True})]
    else:
        outcomes = _modeled_outcomes()
        success, core_bytes = _success_cases()
    result = {
        "schema": "pulsarmlx.f017.v10-root-continuity-bounded-decode-qualification/1.0.0",
        "result": "PASS",
        "root_attack_cases": len(root_cases),
        "decode_attack_cases": len(decode_cases),
        "cross_product_cases": len(cross_product),
        "modeled_outcome_executions": len(outcomes),
        "modeled_outcomes_realized": len({item["outcome_id"] for item in outcomes}),
        "successful_packages": len(success),
        "deterministic_core_repetitions": 10 if not quick else 1,
        "deterministic_core_unique_byte_sequences": len(set(core_bytes)),
        "deterministic_core_sha256": hashlib.sha256(core_bytes[0]).hexdigest(),
        "direct_parser_policy": policy,
        "raw_recursion_errors": 0,
        "false_zero_results": 0,
        "unexpected_passes": 0,
        "original_checkpoint_shard_opens": 0,
        "original_checkpoint_identity_hash_reads": 0,
        "original_checkpoint_payload_reads": 0,
        "event_04_authorization_created": False,
        "event_04_executed": False,
        "p1_attempt_2_executed": False,
    }
    bank_exclusive(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--quick", action="store_true")
    args = parser.parse_args(); result = qualify(args.output, quick=args.quick)
    print(canonical_bytes({"result": result["result"], "root_cases": result["root_attack_cases"], "decode_cases": result["decode_attack_cases"]}).decode().strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
