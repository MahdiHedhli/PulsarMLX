#!/usr/bin/env python3
"""Two-phase V9 authorizer.

Rehearsal helpers are usable now.  The production candidate renderer is called
only by checkpoint-free instantiability tests; canonical installation requires
a separately banked readiness declaration and fresh operator approval and is
never invoked by this preparation phase.
"""
from __future__ import annotations

import hashlib
import ast
import json
import os
import re
import subprocess
import time
from pathlib import Path

from f017_canonical_serialization_v8 import bank_exclusive, sha256_bytes, strict_bytes
from f017_corrected_oracle_authorization_v9 import LIVE_KEYS, SCHEMA, parse_candidate, production_shards
from f017_corrected_oracle_primary_v9 import validate_candidate as validate_primary
from f017_corrected_oracle_secondary_v9 import validate_candidate as validate_secondary
from f017_memory_gate_v9 import observe


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_PLAN = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-production-tensor-plan-v9.json"
RUNTIME_MANIFEST = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-runtime-authority-manifest-v9.json"
READINESS_MAX_AGE_NS = 30 * 24 * 60 * 60 * 1_000_000_000
READINESS_KEYS = {"schema", "F017_CORRECTED_ORACLE_EVENT04_EXECUTION_READINESS",
                  "READY_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_GO",
                  "ACTIVE_CORRECTED_ORACLE_GENERATION", "accepted_implementation_head",
                  "accepted_authority_manifest_sha256", "accepted_at_unix_ns"}
RUNTIME_ENTRY_PATHS = (
    "scripts/research/validate_f017_corrected_oracle_access_v9.py",
    "scripts/research/execute_f017_corrected_oracle_event_v9.py",
    "scripts/research/f017_corrected_oracle_primary_v9.py",
    "scripts/research/f017_corrected_oracle_secondary_v9.py",
)


def _sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def _local_import_closure(entry_paths: tuple[str, ...] = RUNTIME_ENTRY_PATHS) -> set[str]:
    """Independently derive the repository-local runtime import closure."""
    research = ROOT / "scripts/research"
    pending = list(entry_paths); closure: set[str] = set()
    while pending:
        relative = pending.pop()
        if relative in closure:
            continue
        path = ROOT / relative
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, SyntaxError, UnicodeError) as exc:
            raise ValueError(f"runtime import closure parse: {relative}") from exc
        closure.add(relative)
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [item.name.split(".", 1)[0] for item in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module.split(".", 1)[0]]
            for module in modules:
                dependency = research / f"{module}.py"
                relative_dependency = f"scripts/research/{module}.py"
                if dependency.is_file() and relative_dependency not in closure:
                    pending.append(relative_dependency)
    return closure


def _manifest() -> dict:
    manifest = strict_bytes(RUNTIME_MANIFEST.read_bytes())
    if type(manifest) is not dict or type(manifest.get("implementation")) is not dict:
        raise ValueError("runtime authority manifest")
    return manifest


def _implementation_head() -> str:
    paths = [binding["path"] for binding in _manifest()["implementation"].values()]
    try:
        value = subprocess.check_output(
            ["git", "log", "-1", "--format=%H", "--", *paths], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("implementation measurement head") from exc
    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError("implementation measurement head")
    return value


def _validate_implementation_authority(head: object, expected_manifest_sha256: object) -> dict:
    """Bind the full import closure to exact Git bytes and current process bytes."""
    if type(head) is not str or re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise ValueError("accepted implementation head")
    if type(expected_manifest_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256) is None:
        raise ValueError("accepted authority manifest digest")
    if _sha(RUNTIME_MANIFEST) != expected_manifest_sha256:
        raise ValueError("accepted authority manifest digest")
    implementation = _manifest()["implementation"]
    bound_paths: set[str] = set()
    for name, binding in implementation.items():
        if type(name) is not str or type(binding) is not dict or set(binding) != {"path", "sha256"}:
            raise ValueError("runtime implementation binding census")
        path = binding["path"]; digest = binding["sha256"]
        if (type(path) is not str or path in bound_paths or type(digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
            raise ValueError("runtime implementation binding")
        bound_paths.add(path)
    closure = _local_import_closure()
    if not closure.issubset(bound_paths):
        raise ValueError(f"unbound runtime import closure: {sorted(closure - bound_paths)}")
    for binding in implementation.values():
        path = binding["path"]
        try:
            measured = subprocess.check_output(
                ["git", "show", f"{head}:{path}"], cwd=ROOT, stderr=subprocess.DEVNULL,
            )
            current = (ROOT / path).read_bytes()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError(f"implementation byte measurement: {path}") from exc
        measured_sha = hashlib.sha256(measured).hexdigest()
        current_sha = hashlib.sha256(current).hexdigest()
        if measured_sha != binding["sha256"] or current_sha != binding["sha256"] or current != measured:
            raise ValueError(f"implementation byte binding: {path}")
    return {"result": "PASS", "implementation_head": head,
            "bound_path_count": len(bound_paths), "runtime_import_closure_count": len(closure)}


def _canonical_future_path(value: object, name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{name} type")
    path = Path(value)
    if not path.is_absolute() or str(path.resolve(strict=False)) != value:
        raise ValueError(f"{name} must be canonical")
    return value


def _validate_operator_authorities(approval: object, readiness: object, readiness_sha: str) -> tuple[dict, dict]:
    approval_keys = {"schema", "result", "active_generation", "authorization_id", "package_attempt_id",
                     "primary_event_id", "secondary_event_id", "checkpoint_root", "shards",
                     "canonical_authorization_path", "installation_receipt_path", "emergency_evidence_root",
                     "terminal_fallback_evidence_root", "authority_manifest_sha256",
                     "readiness_declaration_sha256", "approved_at_unix_ns", "approval_expires_at_unix_ns"}
    if (type(approval) is not dict or set(approval) != approval_keys
            or approval.get("schema") != "pulsarmlx.f017.corrected-oracle-event04-operator-approval/9.0.0"):
        raise ValueError("operator approval census")
    if approval["result"] != "APPROVED_FOR_ONE_EVENT_04" or approval["active_generation"] != "V9":
        raise ValueError("operator approval posture")
    if (type(readiness) is not dict or set(readiness) != READINESS_KEYS
            or readiness.get("schema") != "pulsarmlx.f017.event04-execution-readiness-declaration/9.0.0"
            or readiness.get("F017_CORRECTED_ORACLE_EVENT04_EXECUTION_READINESS") != "ACCEPTED"
            or readiness.get("READY_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_GO") != "YES"
            or readiness.get("ACTIVE_CORRECTED_ORACLE_GENERATION") != "V9"):
        raise ValueError("execution-readiness authority")
    now = time.time_ns()
    if type(readiness["accepted_at_unix_ns"]) is not int or readiness["accepted_at_unix_ns"] < 0:
        raise ValueError("readiness time")
    for key in ("approved_at_unix_ns", "approval_expires_at_unix_ns"):
        if type(approval[key]) is not int or approval[key] < 0:
            raise ValueError("approval time")
    if not approval["approved_at_unix_ns"] <= now <= approval["approval_expires_at_unix_ns"]:
        raise ValueError("operator approval freshness")
    if approval["readiness_declaration_sha256"] != readiness_sha:
        raise ValueError("operator approval/readiness binding")
    manifest_sha = _sha(RUNTIME_MANIFEST)
    if (readiness["accepted_authority_manifest_sha256"] != manifest_sha
            or approval["authority_manifest_sha256"] != manifest_sha
            or not 0 <= now - readiness["accepted_at_unix_ns"] <= READINESS_MAX_AGE_NS):
        raise ValueError("accepted implementation authority binding")
    _validate_implementation_authority(readiness["accepted_implementation_head"], manifest_sha)
    _canonical_future_path(approval["checkpoint_root"], "checkpoint_root")
    path_fields = ("canonical_authorization_path", "installation_receipt_path", "emergency_evidence_root",
                   "terminal_fallback_evidence_root")
    canonical_paths = [_canonical_future_path(approval[name], name) for name in path_fields]
    if len(set(canonical_paths)) != len(canonical_paths):
        raise ValueError("operator approval path uniqueness")
    return approval, readiness


def render_rehearsal_candidate(checkpoint_root: Path, shards: list[dict], catalog_path: Path,
                               output: Path, identity_suffix: str, *, scope: str,
                               manifest_path: Path | None = None) -> dict:
    """Render non-authoritative candidate bytes after the required mint-time gate."""
    identity_suffix = identity_suffix.replace("_", "-")
    gate = observe(enforce=False)
    candidate = {
        "schema": SCHEMA, "state": "REHEARSAL_CANDIDATE", "live": False, "scope": scope, "authority_generation": 9,
        "authorization_id": f"F017-V9-QUAL-AUTH-{identity_suffix}", "package_attempt_id": f"F017-V9-QUAL-PACKAGE-{identity_suffix}",
        "primary_event_id": f"F017-V9-QUAL-PRIMARY-{identity_suffix}", "secondary_event_id": f"F017-V9-QUAL-SECONDARY-{identity_suffix}",
        "causal_dag_sha256": _sha(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-causal-artifact-dag-v8.json"),
        "numerical_contract_sha256": _sha(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json"),
        "primary_numerical_sha256": _sha(ROOT / "scripts/research/f017_corrected_oracle_primary_numerics_v2.py"),
        "secondary_numerical_sha256": _sha(ROOT / "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py"),
        "checkpoint_root": str(checkpoint_root), "shards": shards, "attempts": 1, "retries": 0, "resume": False,
        "active_generation": "V9", "synthetic_root_manifest_path": str(manifest_path) if manifest_path else None,
        "synthetic_root_manifest_sha256": _sha(manifest_path) if manifest_path else None,
        "tensor_catalog_path": str(catalog_path), "tensor_catalog_sha256": _sha(catalog_path), "mint_memory_gate": gate,
    }
    digest = bank_exclusive(output, candidate)
    primary = validate_primary(output); secondary = validate_secondary(output)
    if primary["candidate_sha256"] != digest or secondary["candidate_sha256"] != digest:
        raise ValueError("candidate validation digest divergence")
    return {"result": "PASS", "candidate_sha256": digest, "candidate": candidate, "primary": primary, "secondary": secondary,
            "checkpoint_opens": 0, "checkpoint_reads": 0, "state_created": False}


def validate_existing_candidate(path: Path) -> dict:
    candidate, digest = parse_candidate(path)
    return {"candidate": candidate, "candidate_sha256": digest, "primary": validate_primary(path), "secondary": validate_secondary(path)}


def install_rehearsal_candidate(candidate_path: Path, installed_path: Path, receipt_path: Path) -> dict:
    """Exercise exact no-replace installation mechanics at a noncanonical path only."""
    report = validate_existing_candidate(candidate_path); raw = candidate_path.read_bytes()
    installed_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = installed_path.open("xb")
    try:
        descriptor.write(raw); descriptor.flush(); os.fsync(descriptor.fileno())
    finally: descriptor.close()
    directory = os.open(installed_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try: os.fsync(directory)
    finally: os.close(directory)
    readback = installed_path.read_bytes()
    if readback != raw or sha256_bytes(readback) != report["candidate_sha256"]: raise ValueError("candidate/install byte identity")
    receipt = {"schema": "pulsarmlx.f017.corrected-oracle-installation-receipt/9.0.0", "authority": False,
               "installation_kind": "NONCANONICAL_REHEARSAL", "authorization_id": report["candidate"]["authorization_id"],
               "package_attempt_id": report["candidate"]["package_attempt_id"], "candidate_sha256": report["candidate_sha256"],
               "installed_sha256": sha256_bytes(readback), "installed_path": str(installed_path.resolve()),
               "primary_validation_sha256": sha256_bytes(json.dumps(report["primary"], sort_keys=True, separators=(",", ":")).encode()),
               "secondary_validation_sha256": sha256_bytes(json.dumps(report["secondary"], sort_keys=True, separators=(",", ":")).encode()),
               "candidate_install_bytes_equal": True, "result": "PASS"}
    receipt_sha = bank_exclusive(receipt_path, receipt); return {**receipt, "receipt_sha256": receipt_sha}


def validate_installed_rehearsal(installed_path: Path, receipt_path: Path) -> dict:
    report = validate_existing_candidate(installed_path); receipt = strict_bytes(receipt_path.read_bytes())
    expected = {"schema", "authority", "installation_kind", "authorization_id", "package_attempt_id", "candidate_sha256",
                "installed_sha256", "installed_path", "primary_validation_sha256", "secondary_validation_sha256",
                "candidate_install_bytes_equal", "result"}
    if type(receipt) is not dict or set(receipt) != expected or receipt["schema"] != "pulsarmlx.f017.corrected-oracle-installation-receipt/9.0.0":
        raise ValueError("installation receipt census")
    candidate = report["candidate"]; installed_sha = sha256_bytes(installed_path.read_bytes())
    if receipt["authority"] is not False or receipt["installation_kind"] != "NONCANONICAL_REHEARSAL" or receipt["result"] != "PASS" or receipt["candidate_install_bytes_equal"] is not True:
        raise ValueError("installation receipt posture")
    if (receipt["authorization_id"] != candidate["authorization_id"] or receipt["package_attempt_id"] != candidate["package_attempt_id"]
            or receipt["candidate_sha256"] != report["candidate_sha256"] or receipt["installed_sha256"] != installed_sha
            or receipt["candidate_sha256"] != installed_sha or receipt["installed_path"] != str(installed_path.resolve())):
        raise ValueError("installation receipt binding")
    return {"result": "PASS", "candidate": candidate, "candidate_sha256": report["candidate_sha256"],
            "installation_receipt_sha256": sha256_bytes(receipt_path.read_bytes()), "primary": report["primary"], "secondary": report["secondary"],
            "checkpoint_opens": 0, "checkpoint_reads": 0, "state_created": False, "numerical_operations": 0}


def render_operator_go_candidate(approval_path: Path, readiness_path: Path, catalog_path: Path, output: Path) -> dict:
    """Render future Event-04 candidate bytes; rendering does not install authority."""
    approval = strict_bytes(approval_path.read_bytes()); readiness = strict_bytes(readiness_path.read_bytes())
    readiness_sha = _sha(readiness_path)
    _validate_operator_authorities(approval, readiness, readiness_sha)
    if catalog_path.resolve() != PRODUCTION_PLAN.resolve() or approval["shards"] != production_shards():
        raise ValueError("operator approval checkpoint authority")
    plan_raw = catalog_path.read_bytes()
    candidate = {
        "schema": SCHEMA, "state": "OPERATOR_APPROVED_CANDIDATE", "live": False, "scope": "PRODUCTION_EVENT_04",
        "authority_generation": 9, "authorization_id": approval["authorization_id"],
        "package_attempt_id": approval["package_attempt_id"], "primary_event_id": approval["primary_event_id"],
        "secondary_event_id": approval["secondary_event_id"],
        "causal_dag_sha256": _sha(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-causal-artifact-dag-v8.json"),
        "numerical_contract_sha256": _sha(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json"),
        "primary_numerical_sha256": _sha(ROOT / "scripts/research/f017_corrected_oracle_primary_numerics_v2.py"),
        "secondary_numerical_sha256": _sha(ROOT / "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py"),
        "checkpoint_root": approval["checkpoint_root"], "shards": approval["shards"], "attempts": 1, "retries": 0,
        "resume": False, "active_generation": "V9", "synthetic_root_manifest_path": None,
        "synthetic_root_manifest_sha256": None, "tensor_catalog_path": str(catalog_path.resolve()),
        "tensor_catalog_sha256": hashlib.sha256(plan_raw).hexdigest(), "mint_memory_gate": observe(enforce=True),
        "operator_approval_path": str(approval_path.resolve()), "operator_approval_sha256": _sha(approval_path),
        "canonical_authorization_path": approval["canonical_authorization_path"],
        "installation_receipt_path": approval["installation_receipt_path"],
        "emergency_evidence_root": approval["emergency_evidence_root"],
        "terminal_fallback_evidence_root": approval["terminal_fallback_evidence_root"],
        "authority_manifest_sha256": approval["authority_manifest_sha256"],
        "execution_readiness_declaration_path": str(readiness_path.resolve()),
        "execution_readiness_declaration_sha256": readiness_sha,
    }
    if set(candidate) != LIVE_KEYS:
        raise ValueError("future-live candidate census")
    digest = bank_exclusive(output, candidate)
    primary = validate_primary(output); secondary = validate_secondary(output)
    if primary["candidate_sha256"] != digest or secondary["candidate_sha256"] != digest:
        raise ValueError("future-live dual validation divergence")
    return {"result": "PASS", "authority_created": False, "candidate_sha256": digest, "candidate": candidate,
            "primary": primary, "secondary": secondary, "checkpoint_opens": 0, "checkpoint_reads": 0}


def validate_live_candidate_for_install(candidate_path: Path) -> dict:
    """Revalidate every irreversible-install gate from exact candidate bytes."""
    report = validate_existing_candidate(candidate_path); candidate = report["candidate"]
    if candidate["scope"] != "PRODUCTION_EVENT_04":
        raise ValueError("production installation scope")
    approval_path = Path(candidate["operator_approval_path"])
    readiness_path = Path(candidate["execution_readiness_declaration_path"])
    try:
        if str(approval_path.resolve(strict=True)) != candidate["operator_approval_path"]:
            raise ValueError("operator approval path binding")
        if str(readiness_path.resolve(strict=True)) != candidate["execution_readiness_declaration_path"]:
            raise ValueError("execution readiness path binding")
        approval = strict_bytes(approval_path.read_bytes()); readiness = strict_bytes(readiness_path.read_bytes())
    except OSError as exc:
        raise ValueError("operator authority read") from exc
    readiness_sha = _sha(readiness_path)
    if _sha(approval_path) != candidate["operator_approval_sha256"]:
        raise ValueError("operator approval digest binding")
    if readiness_sha != candidate["execution_readiness_declaration_sha256"]:
        raise ValueError("execution readiness digest binding")
    _validate_operator_authorities(approval, readiness, readiness_sha)
    approval_to_candidate = {
        "authorization_id": "authorization_id", "package_attempt_id": "package_attempt_id",
        "primary_event_id": "primary_event_id", "secondary_event_id": "secondary_event_id",
        "checkpoint_root": "checkpoint_root", "shards": "shards",
        "canonical_authorization_path": "canonical_authorization_path",
        "installation_receipt_path": "installation_receipt_path",
        "emergency_evidence_root": "emergency_evidence_root",
        "terminal_fallback_evidence_root": "terminal_fallback_evidence_root",
        "authority_manifest_sha256": "authority_manifest_sha256",
        "readiness_declaration_sha256": "execution_readiness_declaration_sha256",
    }
    if any(approval[source] != candidate[target] for source, target in approval_to_candidate.items()):
        raise ValueError("operator approval candidate binding")
    try:
        plan_resolved = Path(candidate["tensor_catalog_path"]).resolve(strict=True)
    except OSError as exc:
        raise ValueError("production tensor plan path") from exc
    if (plan_resolved != PRODUCTION_PLAN.resolve(strict=True)
            or _sha(plan_resolved) != candidate["tensor_catalog_sha256"]
            or candidate["shards"] != production_shards()):
        raise ValueError("production tensor and checkpoint authority")
    raw = candidate_path.read_bytes()
    if sha256_bytes(raw) != report["candidate_sha256"]:
        raise ValueError("candidate changed during installation validation")
    return report


def _cleanup_unconsumed_roots(paths: list[Path]) -> None:
    for path in reversed(paths):
        try:
            path.rmdir()
        except OSError:
            pass


def _bank_installation_failure(roots: tuple[Path, Path], payload: dict) -> None:
    for root in roots:
        try:
            if str(root.resolve(strict=True)) != str(root) or root.is_symlink() or not root.is_dir():
                continue
            bank_exclusive(root / "installation-failure-capsule.json", payload)
            return
        except (OSError, ValueError):
            continue


def install_operator_go_candidate(candidate_path: Path) -> dict:
    """Atomically install exact approved bytes and bank their activation receipt."""
    report = validate_live_candidate_for_install(candidate_path); candidate = report["candidate"]
    installed_path = Path(candidate["canonical_authorization_path"])
    receipt_path = Path(candidate["installation_receipt_path"])
    if installed_path.exists() or receipt_path.exists():
        raise FileExistsError("Event-04 authority or receipt already exists")
    emergency = Path(candidate["emergency_evidence_root"])
    terminal_fallback = Path(candidate["terminal_fallback_evidence_root"])
    created_roots: list[Path] = []
    try:
        for label, root in (("emergency", emergency), ("terminal fallback", terminal_fallback)):
            root.parent.mkdir(parents=True, exist_ok=True)
            if str(root.resolve(strict=False)) != str(root):
                raise ValueError(f"{label} root lost canonical identity")
            root.mkdir(mode=0o700, exist_ok=False); created_roots.append(root)
    except Exception as exc:
        _cleanup_unconsumed_roots(created_roots)
        raise ValueError("production evidence root creation") from exc
    raw = candidate_path.read_bytes()
    try:
        installed_path.parent.mkdir(parents=True, exist_ok=True)
        if str(installed_path.resolve(strict=False)) != str(installed_path):
            raise ValueError("authorization install path lost canonical identity")
        with installed_path.open("xb") as sink:
            sink.write(raw); sink.flush(); os.fsync(sink.fileno())
    except Exception:
        _cleanup_unconsumed_roots(created_roots)
        raise
    directory = os.open(installed_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try: os.fsync(directory)
    finally: os.close(directory)
    readback = installed_path.read_bytes()
    if readback != raw or sha256_bytes(readback) != report["candidate_sha256"]:
        raise ValueError("production candidate/install byte identity")
    receipt = {"schema": "pulsarmlx.f017.corrected-oracle-installation-receipt/9.0.0", "authority": True,
               "installation_kind": "CANONICAL_EVENT04_NO_REPLACE", "authorization_id": candidate["authorization_id"],
               "package_attempt_id": candidate["package_attempt_id"], "candidate_sha256": report["candidate_sha256"],
               "installed_sha256": sha256_bytes(readback), "installed_path": str(installed_path.resolve()),
               "operator_approval_sha256": candidate["operator_approval_sha256"],
               "execution_readiness_declaration_sha256": candidate["execution_readiness_declaration_sha256"],
               "emergency_evidence_root": str(emergency.resolve()),
               "terminal_fallback_evidence_root": str(terminal_fallback.resolve()),
               "candidate_install_bytes_equal": True, "result": "PASS"}
    try:
        receipt_sha = bank_exclusive(receipt_path, receipt)
    except Exception as exc:
        _bank_installation_failure((emergency, terminal_fallback), {
            "schema": "pulsarmlx.f017.corrected-oracle-installation-failure/9.0.0",
            "authorization_id": candidate["authorization_id"], "package_attempt_id": candidate["package_attempt_id"],
            "installed_sha256": sha256_bytes(readback), "source_exception_class": type(exc).__name__,
            "classification": "INSTALLATION_RECEIPT_BANKING_FAILURE", "mandatory_stop": True,
        })
        raise ValueError("production installation receipt banking") from exc
    return {**receipt, "receipt_sha256": receipt_sha}


def validate_installed_operator_go(installed_path: Path, receipt_path: Path) -> dict:
    report = validate_existing_candidate(installed_path); candidate = report["candidate"]
    if candidate["scope"] != "PRODUCTION_EVENT_04" or str(installed_path.resolve()) != candidate["canonical_authorization_path"]:
        raise ValueError("canonical installed authorization")
    receipt = strict_bytes(receipt_path.read_bytes())
    expected = {"schema", "authority", "installation_kind", "authorization_id", "package_attempt_id", "candidate_sha256",
                "installed_sha256", "installed_path", "operator_approval_sha256", "execution_readiness_declaration_sha256",
                "emergency_evidence_root", "terminal_fallback_evidence_root",
                "candidate_install_bytes_equal", "result"}
    if type(receipt) is not dict or set(receipt) != expected or receipt["authority"] is not True or receipt["result"] != "PASS":
        raise ValueError("production installation receipt")
    digest = sha256_bytes(installed_path.read_bytes())
    if (receipt["installation_kind"] != "CANONICAL_EVENT04_NO_REPLACE" or receipt["candidate_sha256"] != digest
            or receipt["installed_sha256"] != digest or receipt["authorization_id"] != candidate["authorization_id"]
            or receipt["package_attempt_id"] != candidate["package_attempt_id"]
            or receipt["operator_approval_sha256"] != candidate["operator_approval_sha256"]
            or receipt["execution_readiness_declaration_sha256"] != candidate["execution_readiness_declaration_sha256"]
            or receipt["emergency_evidence_root"] != candidate["emergency_evidence_root"]
            or receipt["terminal_fallback_evidence_root"] != candidate["terminal_fallback_evidence_root"]):
        raise ValueError("production installation binding")
    return {"result": "PASS", "authority": True, "candidate": candidate, "candidate_sha256": digest,
            "installation_receipt_sha256": sha256_bytes(receipt_path.read_bytes()), "checkpoint_opens": 0, "checkpoint_reads": 0}
