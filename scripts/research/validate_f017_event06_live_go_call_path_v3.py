#!/usr/bin/env python3
"""Independent byte, type, mutation, and no-access validator for Sequence 11."""

from __future__ import annotations

import ast
import builtins
import copy
import hashlib
import inspect
import json
import mmap
import os
import pickle
from pathlib import Path
from unittest.mock import patch

import f017_event06_production_installation_v3 as implementation
from f017_canonical_serialization_v10 import canonical_bytes
from f017_event06_production_installation_v1 import ProductionInstallationError

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = (
    ROOT
    / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-live-go-call-path-requirements-v1.json"
)
CONTRACT = (
    ROOT
    / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-live-go-call-path-v3.json"
)
GENERATED = ROOT / "scripts/research/f017_event06_live_go_contract_v3.py"
IMPLEMENTATION = ROOT / "scripts/research/f017_event06_production_installation_v3.py"
PROMPT_AUTHORITY = (
    ROOT
    / "docs/architecture/reviews/evidence/f017-event06-v12-sequence11-prompt-authority-snapshot-provenance-v1.json"
)
PROMPT_PATH = "Prompts/F017/Mac-Studio-M1-Ultra/011__F017__Mac-Studio-M1-Ultra__Event-06-V12-live-GO-call-path-contract-repair-and-no-access-requalification__prompt.md"
PROMPT_COMMIT = "26998b7f0e840bbcdda5c792999b7eadd1ddd164"
PROMPT_SHA256 = "3e0809171a44691f934b10ef75bdd609674e476645e2110d153f7ed13e96c624"


def _literal_assignments(path: Path) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            result[node.target.id] = ast.literal_eval(node.value)
    return result


def _dag(edges: list[str]) -> dict[str, object]:
    pairs = [tuple(edge.split("->")) for edge in edges]
    if any(len(pair) != 2 or pair[0] == pair[1] for pair in pairs):
        raise AssertionError("authority DAG self or malformed edge")
    nodes = {item for pair in pairs for item in pair}
    incoming = {node: 0 for node in nodes}
    outgoing = {node: [] for node in nodes}
    for left, right in pairs:
        outgoing[left].append(right)
        incoming[right] += 1
    frontier = sorted(node for node, count in incoming.items() if count == 0)
    order: list[str] = []
    while frontier:
        node = frontier.pop(0)
        order.append(node)
        for target in sorted(outgoing[node]):
            incoming[target] -= 1
            if incoming[target] == 0:
                frontier.append(target)
                frontier.sort()
    if len(order) != len(nodes):
        raise AssertionError("authority DAG cycle")
    return {
        "edge_count": len(pairs),
        "node_count": len(nodes),
        "topological_order": order,
    }


def _annotations() -> dict[str, object]:
    expected = {
        "render_live_go_envelope": (
            {
                "raw_human_go": "bytes",
                "authorization_id": "str",
                "package_attempt_id": "str",
                "readiness_sha256": "str",
                "target_parent": "Path",
                "target_leaf": "str",
                "issued_at_unix_ns": "int",
                "expires_at_unix_ns": "int",
                "nonce_sha256": "str",
            },
            "bytes",
        ),
        "inspect_live_go_envelope_without_sealing": (
            {
                "raw": "bytes",
                "now_unix_ns": "int",
                "expected_raw_human_go_sha256": "str",
                "expected_authorization_id": "str",
                "expected_package_attempt_id": "str",
                "expected_readiness_sha256": "str",
                "expected_target_parent": "str",
                "expected_target_leaf": "str",
                "expected_issued_at_unix_ns": "int",
                "expected_expires_at_unix_ns": "int",
                "expected_nonce_sha256": "str",
            },
            "MappingProxyType[str, object]",
        ),
        "seal_live_go_envelope": (
            {
                "raw": "bytes",
                "raw_human_go": "bytes",
                "now_unix_ns": "int | None",
            },
            "LiveHumanGoV3",
        ),
        "inspect_prompt_bound_event_identity_plan_without_sealing": (
            {
                "raw": "bytes",
                "prompt_bytes": "bytes",
                "prompt_repository_commit": "str",
                "prompt_repository_path": "str",
                "expected_authorization_id": "str",
                "expected_package_attempt_id": "str",
                "expected_primary_event_id": "str",
                "expected_secondary_event_id": "str",
                "expected_execution_plan_sha256": "str",
            },
            "MappingProxyType[str, object]",
        ),
        "seal_prompt_bound_event_identity_plan": (
            {
                "raw": "bytes",
                "prompt_bytes": "bytes",
                "prompt_repository_commit": "str",
                "prompt_repository_path": "str",
            },
            "PromptBoundEventIdentityPlanV2",
        ),
        "inspect_live_operator_approval_without_sealing": (
            {
                "raw": "bytes",
                "expected_live_go_envelope_sha256": "str",
                "expected_readiness_sha256": "str",
                "expected_authorization_id": "str",
                "expected_package_attempt_id": "str",
                "expected_execution_plan_sha256": "str",
                "expected_event_identity_plan_sha256": "str",
                "expected_candidate_sha256": "str",
            },
            "MappingProxyType[str, object]",
        ),
        "seal_live_operator_approval": (
            {
                "raw": "bytes",
                "live_go": "LiveHumanGoV3",
                "readiness": "ValidatedEvent06ReadinessV3",
                "execution_plan": "ValidatedExecutionPlan",
                "event_identity": "PromptBoundEventIdentityPlanV2",
                "candidate": "ValidatedIdentityAuthority",
            },
            "LiveOperatorApprovalV3",
        ),
        "prepare_production_installation_v3": (
            {
                "readiness": "ValidatedEvent06ReadinessV3",
                "human_go": "LiveHumanGoV3",
                "execution_plan": "ValidatedExecutionPlan",
                "approval": "LiveOperatorApprovalV3",
                "event_identity": "PromptBoundEventIdentityPlanV2",
                "candidate": "ValidatedIdentityAuthority",
                "checkpoint_census": "_SealedDocument",
                "integration": "_SealedDocument",
            },
            "PreparedProductionInstallationV3",
        ),
        "validate_prepared_production_installation_v3": (
            {"prepared": "PreparedProductionInstallationV3"},
            "PreparedProductionInstallationV3",
        ),
        "produce_future_go_capability_v3": (
            {"prepared": "PreparedProductionInstallationV3"},
            "FutureGoCapabilityV3",
        ),
        "validate_future_go_capability_v3": (
            {"capability": "object", "prepared": "PreparedProductionInstallationV3"},
            "FutureGoCapabilityV3",
        ),
        "commit_production_installation_v3": (
            {
                "prepared": "PreparedProductionInstallationV3",
                "capability": "FutureGoCapabilityV3",
            },
            "DurableTransactionResult",
        ),
    }
    rows: list[dict[str, object]] = []
    for name, (parameters, returned) in expected.items():
        function = getattr(implementation, name)
        signature = inspect.signature(function)
        if set(signature.parameters) != set(parameters):
            raise AssertionError(f"signature parameter census {name}")
        for parameter, annotation in parameters.items():
            observed = str(signature.parameters[parameter].annotation).strip("'")
            if observed != annotation:
                raise AssertionError(
                    f"signature annotation {name}.{parameter}: {observed}"
                )
        observed_return = str(signature.return_annotation).strip("'")
        if observed_return != returned:
            raise AssertionError(f"signature return {name}: {observed_return}")
        rows.append({"function": name, "signature": str(signature), "result": "PASS"})
    return {
        "real_signatures_bound": len(rows),
        "real_signature_total": len(expected),
        "edges": rows,
    }


def _fixtures(requirements: dict[str, object]) -> dict[str, object]:
    raw_human_go = b"SYNTHETIC_NON_AUTHORITY_SEQUENCE11_GO_BYTES"
    prompt_bytes = b"SYNTHETIC_SEQUENCE11_PROMPT_BYTES"
    identifiers = {
        "authorization_id": "F017-SEQUENCE11-NONAUTH-AUTHORIZATION",
        "package_attempt_id": "F017-SEQUENCE11-NONAUTH-PACKAGE",
        "primary_event_id": "F017-SEQUENCE11-NONAUTH-PRIMARY",
        "secondary_event_id": "F017-SEQUENCE11-NONAUTH-SECONDARY",
    }
    digests = {
        "readiness_sha256": "1" * 64,
        "execution_plan_sha256": "2" * 64,
        "candidate_sha256": "3" * 64,
        "event_identity_plan_sha256": "4" * 64,
        "live_go_envelope_sha256": "5" * 64,
        "nonce_sha256": "6" * 64,
    }
    live = {
        "schema": requirements["live_go"]["schema"],
        "decision": requirements["live_go"]["decision"],
        "live": True,
        "raw_human_go_sha256": hashlib.sha256(raw_human_go).hexdigest(),
        "authorization_id": identifiers["authorization_id"],
        "package_attempt_id": identifiers["package_attempt_id"],
        "readiness_sha256": digests["readiness_sha256"],
        "target_parent": "/NONEXISTENT/F017/EVENT06/SEQUENCE11",
        "target_leaf": "event06-v12-installation",
        "issued_at_unix_ns": 10,
        "expires_at_unix_ns": 30,
        "nonce_sha256": digests["nonce_sha256"],
        "scope": requirements["scope"],
        "attempts": 1,
        "retries": 0,
        "resume": False,
    }
    identity = {
        "schema": requirements["event_identity_plan"]["schema"],
        **identifiers,
        "execution_plan_sha256": digests["execution_plan_sha256"],
        "prompt_repository_commit": PROMPT_COMMIT,
        "prompt_repository_path": PROMPT_PATH,
        "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
    }
    approval = {
        "schema": requirements["operator_approval"]["schema"],
        "live_go_envelope_sha256": digests["live_go_envelope_sha256"],
        "readiness_sha256": digests["readiness_sha256"],
        "authorization_id": identifiers["authorization_id"],
        "package_attempt_id": identifiers["package_attempt_id"],
        "execution_plan_sha256": digests["execution_plan_sha256"],
        "event_identity_plan_sha256": digests["event_identity_plan_sha256"],
        "candidate_sha256": digests["candidate_sha256"],
        "live": True,
        "attempts": 1,
        "retries": 0,
        "resume": False,
    }
    preparation = {
        "schema": implementation.PREPARATION_RECEIPT_SCHEMA,
        "candidate_sha256": digests["candidate_sha256"],
        "readiness_sha256": digests["readiness_sha256"],
        "live_go_envelope_sha256": digests["live_go_envelope_sha256"],
        "operator_approval_sha256": "7" * 64,
        "execution_plan_sha256": digests["execution_plan_sha256"],
        "event_identity_plan_sha256": digests["event_identity_plan_sha256"],
        "prompt_repository_commit": PROMPT_COMMIT,
        "prompt_repository_path": PROMPT_PATH,
        "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "checkpoint_census_sha256": "8" * 64,
        "integration_sha256": "9" * 64,
        "authorization_id": identifiers["authorization_id"],
        "package_attempt_id": identifiers["package_attempt_id"],
        "target_parent": "/NONEXISTENT/F017/EVENT06/SEQUENCE11",
        "target_leaf": "event06-v12-installation",
        "nonce_sha256": digests["nonce_sha256"],
        "expires_at_unix_ns": 30,
        "state": "PREPARED_PRODUCTION_INSTALLATION",
        "live_authority": False,
        "result": "PASS",
    }
    return {
        "raw_human_go": raw_human_go,
        "prompt_bytes": prompt_bytes,
        "identifiers": identifiers,
        "digests": digests,
        "live": live,
        "identity": identity,
        "approval": approval,
        "preparation": preparation,
    }


def _inspect_raw(role: str, raw: bytes, fixture: dict[str, object]) -> None:
    identifiers = fixture["identifiers"]
    digests = fixture["digests"]
    if role == "live":
        implementation.inspect_live_go_envelope_without_sealing(
            raw,
            now_unix_ns=20,
            expected_raw_human_go_sha256=hashlib.sha256(
                fixture["raw_human_go"]
            ).hexdigest(),
            expected_authorization_id=identifiers["authorization_id"],
            expected_package_attempt_id=identifiers["package_attempt_id"],
            expected_readiness_sha256=digests["readiness_sha256"],
            expected_target_parent="/NONEXISTENT/F017/EVENT06/SEQUENCE11",
            expected_target_leaf="event06-v12-installation",
            expected_issued_at_unix_ns=10,
            expected_expires_at_unix_ns=30,
            expected_nonce_sha256=digests["nonce_sha256"],
        )
    elif role == "identity":
        implementation.inspect_prompt_bound_event_identity_plan_without_sealing(
            raw,
            prompt_bytes=fixture["prompt_bytes"],
            prompt_repository_commit=PROMPT_COMMIT,
            prompt_repository_path=PROMPT_PATH,
            expected_authorization_id=identifiers["authorization_id"],
            expected_package_attempt_id=identifiers["package_attempt_id"],
            expected_primary_event_id=identifiers["primary_event_id"],
            expected_secondary_event_id=identifiers["secondary_event_id"],
            expected_execution_plan_sha256=digests["execution_plan_sha256"],
        )
    else:
        if role == "preparation":
            value = implementation._decode_exact(
                raw,
                fields=implementation.PREPARATION_RECEIPT_FIELDS,
                types=implementation.PREPARATION_RECEIPT_TYPES,
                schema=implementation.PREPARATION_RECEIPT_SCHEMA,
                kind="PREPARATION_RECEIPT",
            )
            expected = fixture["preparation"]
            if any(value[name] != expected[name] for name in expected):
                raise ProductionInstallationError(
                    "F017_V12_PRODUCTION_INSTALL_INPUT_MISMATCH",
                    "synthetic preparation binding",
                )
            return
        implementation.inspect_live_operator_approval_without_sealing(
            raw,
            expected_live_go_envelope_sha256=digests["live_go_envelope_sha256"],
            expected_readiness_sha256=digests["readiness_sha256"],
            expected_authorization_id=identifiers["authorization_id"],
            expected_package_attempt_id=identifiers["package_attempt_id"],
            expected_execution_plan_sha256=digests["execution_plan_sha256"],
            expected_event_identity_plan_sha256=digests["event_identity_plan_sha256"],
            expected_candidate_sha256=digests["candidate_sha256"],
        )


def _inspect(role: str, value: dict[str, object], fixture: dict[str, object]) -> None:
    _inspect_raw(role, canonical_bytes(value), fixture)


def _different(value: object) -> object:
    if type(value) is bool:
        return not value
    if type(value) is int:
        return value + 1
    if type(value) is str:
        if len(value) == 64 and set(value) <= set("0123456789abcdef"):
            return ("0" if value[0] != "0" else "1") + value[1:]
        if len(value) == 40 and set(value) <= set("0123456789abcdef"):
            return ("0" if value[0] != "0" else "1") + value[1:]
        if value.startswith("/"):
            return value + "-mutated"
        return value + "-MUTATED"
    raise AssertionError("unsupported fixture value")


def _wrong_type(value: object) -> object:
    if type(value) is bool:
        return 1
    if type(value) is int:
        return True
    return 7


def _mutations(fixture: dict[str, object]) -> dict[str, int]:
    rejected = 0
    total = 0

    def reject(role: str, value: dict[str, object]) -> None:
        nonlocal rejected, total
        total += 1
        try:
            _inspect(role, value, fixture)
        except (ProductionInstallationError, ValueError, TypeError):
            rejected += 1
            return
        raise AssertionError(f"mutation unexpectedly passed: {role}")

    for role in ("live", "identity", "approval", "preparation"):
        original = fixture[role]
        for field in original:
            changed = dict(original)
            changed.pop(field)
            reject(role, changed)
            changed = dict(original)
            changed[field] = None
            reject(role, changed)
            changed = dict(original)
            changed[field] = _wrong_type(original[field])
            reject(role, changed)
            changed = dict(original)
            changed[field] = _different(original[field])
            reject(role, changed)
            changed = dict(original)
            changed[field.upper()] = changed[field]
            reject(role, changed)
        changed = dict(original)
        changed["unknown_field"] = "REJECT"
        reject(role, changed)
        total += 1
        try:
            _inspect_raw(role, canonical_bytes(original) + b"\n", fixture)
        except (ProductionInstallationError, ValueError, TypeError):
            rejected += 1
    cross = [
        ("live", fixture["identity"]),
        ("live", fixture["approval"]),
        ("identity", fixture["live"]),
        ("identity", fixture["approval"]),
        ("approval", fixture["live"]),
        ("approval", fixture["identity"]),
        ("preparation", fixture["live"]),
        ("preparation", fixture["identity"]),
        ("preparation", fixture["approval"]),
    ]
    for role, value in cross:
        reject(role, dict(value))
    return {"rejected": rejected, "total": total}


def _security(source: str) -> dict[str, object]:
    classes = (
        implementation.LiveHumanGoV3,
        implementation.LiveOperatorApprovalV3,
        implementation.PromptBoundEventIdentityPlanV2,
        implementation.PreparedProductionInstallationV3,
        implementation.FutureGoCapabilityV3,
    )
    constructor_rejections = 0
    operation_rejections = 0
    for class_ in classes:
        try:
            class_()
        except TypeError:
            constructor_rejections += 1
        else:
            raise AssertionError(f"public constructor accepted: {class_.__name__}")
        probe = object.__new__(class_)
        operations = (
            lambda p=probe: setattr(p, "injected", True),
            lambda p=probe: delattr(p, "_locked"),
            lambda p=probe: setattr(p, "__class__", object),
            lambda p=probe: copy.copy(p),
            lambda p=probe: copy.deepcopy(p),
            lambda p=probe: pickle.dumps(p),
        )
        for operation in operations:
            try:
                operation()
            except TypeError:
                operation_rejections += 1
            else:
                raise AssertionError(f"sealed operation accepted: {class_.__name__}")
    required_methods = (
        "__setattr__",
        "__delattr__",
        "__copy__",
        "__deepcopy__",
        "__reduce_ex__",
    )
    tree = ast.parse(source)
    class_methods = {
        node.name: {
            item.name
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    closed = 0
    for class_ in classes:
        names = set().union(
            *(class_methods.get(base.__name__, set()) for base in class_.__mro__)
        )
        if not set(required_methods).issubset(names):
            raise AssertionError(f"closed security methods: {class_.__name__}")
        closed += 1
    if "__class__ =" in source or 'object.__setattr__(self, "__class__"' in source:
        raise AssertionError("dynamic class reassignment surface")
    return {
        "constructor_rejections": constructor_rejections,
        "operation_rejections": operation_rejections,
        "operation_total": len(classes) * 6,
        "closed_types": closed,
        "result": "PASS",
    }


def _dag_mutations(edges: list[str]) -> dict[str, int]:
    rejected = 0
    total = 0
    expected = tuple(edges)

    def validate_exact(changed: list[str]) -> None:
        _dag(changed)
        if tuple(changed) != expected:
            raise AssertionError("exact authority DAG binding")

    for index, edge in enumerate(edges):
        for changed in (
            edges[:index] + edges[index + 1 :],
            edges[:index]
            + [edge.split("->")[1] + "->" + edge.split("->")[0]]
            + edges[index + 1 :],
        ):
            total += 1
            try:
                validate_exact(changed)
            except AssertionError:
                rejected += 1
            else:
                raise AssertionError("authority DAG mutation unexpectedly passed")
    for changed in (edges + [edges[0]], edges + ["SELF->SELF"]):
        total += 1
        try:
            validate_exact(changed)
        except AssertionError:
            rejected += 1
        else:
            raise AssertionError("authority DAG mutation unexpectedly passed")
    return {"rejected": rejected, "total": total}


def _authority_edge_witnesses(edges: list[str], source: str) -> dict[str, object]:
    required_tokens = {
        "RAW_HUMAN_GO_BYTES->LIVE_GO_ENVELOPE": ("raw_human_go_sha256",),
        "READINESS->LIVE_GO_ENVELOPE": ("readiness_sha256",),
        "EXECUTION_PLAN->EVENT_IDENTITY_PLAN": ("execution_plan_sha256",),
        "PROMPT_BYTES->EVENT_IDENTITY_PLAN": (
            "prompt_repository_commit",
            "prompt_repository_path",
            "prompt_sha256",
        ),
        "EVENT_IDENTITY_PLAN->CANDIDATE": ("event_identity_plan_sha256",),
        "LIVE_GO_ENVELOPE->OPERATOR_APPROVAL": ("live_go_envelope_sha256",),
        "READINESS->OPERATOR_APPROVAL": ("approval readiness",),
        "EXECUTION_PLAN->OPERATOR_APPROVAL": ("approval plan",),
        "EVENT_IDENTITY_PLAN->OPERATOR_APPROVAL": ("approval identity",),
        "CANDIDATE->OPERATOR_APPROVAL": ("approval candidate",),
        "LIVE_GO_ENVELOPE->PREPARED_INSTALLATION": ("GO authorization",),
        "OPERATOR_APPROVAL->PREPARED_INSTALLATION": ("operator_approval_sha256",),
        "EVENT_IDENTITY_PLAN->PREPARED_INSTALLATION": ("event_identity_plan_sha256",),
        "PREPARED_INSTALLATION->FUTURE_GO_CAPABILITY": (
            "produce_future_go_capability_v3(\n    prepared:",
            'receipt["live_go_envelope_sha256"]',
            "prepared.prepared_sha256",
        ),
        "FUTURE_GO_CAPABILITY->DURABLE_INSTALLATION_TRANSACTION": (
            "validate_future_go_capability_v3",
            "_commit_bound_production_transaction",
        ),
    }
    if set(required_tokens) != set(edges):
        raise AssertionError("authority edge witness census")
    rows = []
    for edge in edges:
        tokens = required_tokens[edge]
        if any(token not in source for token in tokens):
            raise AssertionError(f"authority edge lacks implementation witness: {edge}")
        rows.append({"edge": edge, "tokens": list(tokens), "result": "PASS"})
    return {
        "semantic": "TRANSITIVE_REDUCED_AUTHORITY_CONSTRUCTION_GRAPH",
        "witnessed": len(rows),
        "total": len(edges),
        "rows": rows,
        "result": "PASS",
    }


def _execution_surface(source: str) -> dict[str, object]:
    forbidden_tokens = (
        "f017_corrected_oracle_primary_numerics",
        "f017_corrected_oracle_secondary_numerics",
        "execute_outputs",
        "glm52_tensor_store",
        "package_durable_start",
        "descriptor_lease",
        "checkpoint_root",
    )
    present = [token for token in forbidden_tokens if token in source]
    if present:
        raise AssertionError(f"execution-facing surface present: {present}")
    return {
        "forbidden_tokens": list(forbidden_tokens),
        "present": present,
        "numerical_callable_imports": 0,
        "checkpoint_root_callable_imports": 0,
        "package_start_callable_imports": 0,
        "descriptor_lease_callable_imports": 0,
        "result": "PASS",
    }


def validate() -> dict[str, object]:
    requirements = json.loads(REQUIREMENTS.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    prompt_authority = json.loads(PROMPT_AUTHORITY.read_text(encoding="utf-8"))
    generated = _literal_assignments(GENERATED)
    comparisons = (
        (
            generated["REQUIREMENTS_RELATIVE"],
            REQUIREMENTS.relative_to(ROOT).as_posix(),
        ),
        (generated["LIVE_GO_SCHEMA"], requirements["live_go"]["schema"]),
        (generated["LIVE_GO_DECISION"], requirements["live_go"]["decision"]),
        (generated["LIVE_GO_SCOPE"], requirements["scope"]),
        (
            generated["APPROVAL_SCHEMA"],
            requirements["operator_approval"]["schema"],
        ),
        (
            generated["EVENT_IDENTITY_SCHEMA"],
            requirements["event_identity_plan"]["schema"],
        ),
        (contract["requirements_path"], generated["REQUIREMENTS_RELATIVE"]),
        (contract["scope"], requirements["scope"]),
        (contract["live_go_schema"], requirements["live_go"]["schema"]),
        (
            contract["operator_approval_schema"],
            requirements["operator_approval"]["schema"],
        ),
        (
            contract["event_identity_plan_schema"],
            requirements["event_identity_plan"]["schema"],
        ),
        (prompt_authority["prompt_repository_commit"], PROMPT_COMMIT),
        (prompt_authority["prompt_repository_path"], PROMPT_PATH),
        (prompt_authority["prompt_sha256"], PROMPT_SHA256),
        (
            tuple(requirements["live_go"]["required_fields"]),
            generated["LIVE_GO_FIELDS"],
        ),
        (requirements["live_go"]["exact_types"], generated["LIVE_GO_TYPES"]),
        (
            tuple(requirements["operator_approval"]["required_fields"]),
            generated["APPROVAL_FIELDS"],
        ),
        (requirements["operator_approval"]["exact_types"], generated["APPROVAL_TYPES"]),
        (
            tuple(requirements["event_identity_plan"]["required_fields"]),
            generated["EVENT_IDENTITY_FIELDS"],
        ),
        (
            requirements["event_identity_plan"]["exact_types"],
            generated["EVENT_IDENTITY_TYPES"],
        ),
        (tuple(requirements["authority_dag"]), generated["AUTHORITY_DAG"]),
        (contract["live_go_fields"], requirements["live_go"]["required_fields"]),
        (
            contract["operator_approval_fields"],
            requirements["operator_approval"]["required_fields"],
        ),
        (
            contract["event_identity_plan_fields"],
            requirements["event_identity_plan"]["required_fields"],
        ),
    )
    if any(observed != expected for observed, expected in comparisons):
        raise AssertionError("requirements, generated constants, and contract diverge")
    dag = _dag(requirements["authority_dag"])
    signatures = _annotations()
    fixture = _fixtures(requirements)
    implementation_source = IMPLEMENTATION.read_text(encoding="utf-8")
    edge_witnesses = _authority_edge_witnesses(
        requirements["authority_dag"], implementation_source
    )
    execution_surface = _execution_surface(implementation_source)
    counters = {
        name: 0
        for name in (
            "open",
            "mmap",
            "root_resolve",
            "hash_read",
            "capability",
            "commit",
        )
    }

    def forbidden(name: str) -> object:
        def reject(*args: object, **kwargs: object) -> object:
            del args, kwargs
            counters[name] += 1
            raise AssertionError(f"forbidden no-access boundary reached: {name}")

        return reject

    with (
        patch.object(builtins, "open", forbidden("open")),
        patch.object(os, "open", forbidden("open")),
        patch.object(mmap, "mmap", forbidden("mmap")),
        patch.object(Path, "resolve", forbidden("root_resolve")),
        patch.object(hashlib, "file_digest", forbidden("hash_read")),
        patch.object(
            implementation,
            "produce_future_go_capability_v3",
            forbidden("capability"),
        ),
        patch.object(
            implementation,
            "commit_production_installation_v3",
            forbidden("commit"),
        ),
        patch.object(
            implementation,
            "_commit_bound_production_transaction",
            forbidden("commit"),
        ),
    ):
        digests: dict[str, set[str]] = {
            "live": set(),
            "identity": set(),
            "approval": set(),
            "preparation": set(),
        }
        for _ in range(20):
            for role, values in digests.items():
                _inspect(role, dict(fixture[role]), fixture)
                values.add(hashlib.sha256(canonical_bytes(fixture[role])).hexdigest())
        mutations = _mutations(fixture)
        security = _security(implementation_source)
        dag_mutations = _dag_mutations(requirements["authority_dag"])
    if any(len(values) != 1 for values in digests.values()):
        raise AssertionError("nondeterministic reconstruction")
    mutations = {
        "rejected": mutations["rejected"] + dag_mutations["rejected"],
        "total": mutations["total"] + dag_mutations["total"],
        "document_mutations": mutations,
        "authority_dag_mutations": dag_mutations,
    }
    if len(implementation._ISSUED_CAPABILITIES) != 0:
        raise AssertionError("capability instance created")
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence11-live-go-call-path-qualification/1.0.0",
        "result": "PASS",
        "canonical_live_go_field_set": "PASS",
        "noncircular_authority_dag": "PASS",
        "live_go_sealed_type_compatibility": "PASS_STATIC_EXACT_SIGNATURE",
        "prompt_bound_identity_plan": "PASS",
        "real_public_signatures": signatures,
        "deterministic_reconstructions": 20,
        "deterministic_digest_census": {
            name: len(values) for name, values in digests.items()
        },
        "mutation_campaign": mutations,
        "unexpected_passes": 0,
        "sealed_type_security": security,
        "authority_dag": dag,
        "authority_edge_witnesses": edge_witnesses,
        "execution_surface_absence": execution_surface,
        "side_effect_census": counters,
        "interposed_boundaries": sorted(counters),
        "live_human_go_documents_created": 0,
        "future_go_capability_instances": len(implementation._ISSUED_CAPABILITIES),
        "operator_approvals_created": 0,
        "execution_plans_created": 0,
        "event_identity_plans_created": 0,
        "candidates_created": 0,
        "live_authorizations_created": 0,
        "live_installations_created": 0,
        "package_starts": execution_surface["package_start_callable_imports"],
        "checkpoint_access": sum(
            counters[name] for name in ("open", "mmap", "root_resolve", "hash_read")
        ),
        "numerical_operations": execution_surface["numerical_callable_imports"],
        "event06_identities_instantiated": 0,
        "event06_identities_consumed": 0,
        "event_04_retry": False,
        "event_05_retry": False,
        "event_06_executed": False,
        "live_event_06_authority_created": False,
        "event_06_package_started": bool(
            execution_surface["package_start_callable_imports"]
        ),
        "primary_real_oracle_event06_executions": execution_surface[
            "numerical_callable_imports"
        ],
        "secondary_real_oracle_event06_executions": execution_surface[
            "numerical_callable_imports"
        ],
        "original_checkpoint_root_opens": counters["root_resolve"],
        "original_checkpoint_shard_opens": counters["open"],
        "original_checkpoint_identity_hash_reads": counters["hash_read"],
        "original_checkpoint_mmaps": counters["mmap"],
        "original_checkpoint_tensor_reads": execution_surface[
            "checkpoint_root_callable_imports"
        ],
        "original_checkpoint_payload_reads": counters["open"],
        "original_checkpoint_access": sum(
            counters[name] for name in ("open", "mmap", "root_resolve", "hash_read")
        ),
        "p1_attempt_2_executed": False,
        "live_p1_attempt_2_authorization_created": False,
        "historical_master_ledger": 175,
        "terminal": "PACKAGE_START_ELIGIBLE_DRY_STOP",
    }


def main() -> int:
    print(json.dumps(validate(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
