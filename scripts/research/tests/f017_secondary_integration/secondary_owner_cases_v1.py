"""Focused authority-owner and active source-separation qualification.

All reads target tiny files created inside the already sealed fixture root.
The production candidate is built from the exact coordinator function body;
no execution identity is added to that candidate by this test.
"""
import ast
import hashlib
import json
import os
from pathlib import Path

import f017_secondary_read_observation_v1 as observation
import validate_f017_v11_execution_authority_v1 as authority_validator
from secondary_cases_v1 import Fixture, canonical
from secondary_oracle_v1 import require_complete, require_incomplete, validate_requests


def _production_candidate(fixture, view):
    source_path = Path(view) / "scripts/research/f017_event06_minimum_gate_path_v1.py"
    source = source_path.read_text()
    tree = ast.parse(source, filename=str(source_path))
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == "_target_candidate"]
    if len(functions) != 1:
        raise AssertionError("EXACT_PRODUCTION_CANDIDATE_FUNCTION")
    contract = fixture.root / "synthetic-contract.json"
    contract.write_bytes(canonical({"shards": [{"size_bytes": 0}]
        + [{"size_bytes": 256} for _ in range(5)]}))
    namespace = {
        "_ValidatedBridge": dict,
        "_ROOT": fixture.root,
        "_CHECKPOINT_CONTRACT": contract.name,
        "_SYNTHETIC_CHECKPOINT_CONTRACT": contract.name,
        "_TENSOR_PLAN": "catalog.json",
        "_parse_artifact_bytes": lambda raw: json.loads(raw),
        "_file_sha": lambda relative: hashlib.sha256(
            (fixture.root / relative).read_bytes()).hexdigest(),
    }
    module = ast.Module(body=functions, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(source_path), "exec"), namespace)
    candidate = namespace["_target_candidate"]({
        "authority_scope": "SYNTHETIC",
        "primary_numerical_sha256": hashlib.sha256(b"primary").hexdigest(),
        "secondary_numerical_sha256": hashlib.sha256(b"secondary").hexdigest(),
    })
    expected = {"active_generation", "primary_numerical_sha256",
        "secondary_numerical_sha256", "tensor_catalog_path",
        "tensor_catalog_sha256", "shards"}
    if set(candidate) != expected or "package_attempt_id" in candidate or "secondary_event_id" in candidate:
        raise AssertionError("PRODUCTION_CANDIDATE_IDENTITY_COPIES_ABSENT")
    return candidate


def _attachment_without_read(fixture):
    fixture.open()
    attachment = fixture.finish("RAISED")
    if fixture.transcript:
        raise AssertionError("PRE_IO_REFUSAL_DELEGATED")
    require_incomplete(attachment)
    return attachment


def _record(results, work, name, fixture, attachment, expected, detail=None):
    validate_requests(fixture.transcript)
    if expected == "COMPLETE":
        require_complete(attachment, fixture.transcript)
    else:
        require_incomplete(attachment)
    row = {"case": name, "result": "PASS", "expected": expected,
           "transcript": fixture.transcript, "attachment": attachment,
           "detail": detail}
    results.append(row)
    with (Path(work) / ("owner-case-%03d.json" % len(results))).open("xb") as output:
        output.write(canonical(row))
        output.flush()
        os.fsync(output.fileno())


def _validate_separation(paths):
    authority_validator._validate_active_target_source_separation(
        paths["primary"], paths["secondary"], paths["prefix"],
        paths["factory"], paths["production"])


def _separation_cases(work, view):
    source = Path(view) / "scripts/research"
    originals = {
        "primary": source / "f017_corrected_oracle_primary_wrapper_v11.py",
        "secondary": source / "f017_corrected_oracle_secondary_wrapper_v11.py",
        "prefix": source / "f017_secondary_read_observation_prefix_v1.py",
        "factory": source / "f017_secondary_read_observation_factory_v1.py",
        "production": source / "f017_event06_minimum_gate_path_v1.py",
    }
    _validate_separation(originals)
    results = []
    mutations = {
        "primary-source-substitution": ("secondary", None,
            "\nfrom f017_corrected_oracle_primary_target_source_v11 import source_from_inherited_descriptors\n"),
        "stale-secondary-producer": ("prefix",
            ("from f017_secondary_read_observation_factory_v1 import create_descriptor_store",
             "from f017_corrected_oracle_secondary_target_source_v11 import source_from_inherited_descriptors as create_descriptor_store"), None),
        "shared-source-callback": ("factory",
            ("from f017_secondary_descriptor_source_v1 import SecondaryDescriptorStore",
             "from f017_corrected_oracle_primary_target_source_v11 import source_from_inherited_descriptors as SecondaryDescriptorStore"), None),
        "fake-spelling-comment": ("secondary",
            ("from f017_secondary_read_observation_prefix_v1 import open_secondary_descriptor_prefix",
             "from f017_secondary_missing_prefix_v1 import open_secondary_descriptor_prefix"),
            "\n# f017_secondary_read_observation_prefix_v1 open_secondary_descriptor_prefix\n"),
        "missing-candidate-validation": ("secondary",
            ("    validate_candidate_document(candidate)\n", "    pass  # candidate validation removed by mutation\n"), None),
        "prefix-symbol-rebinding": ("secondary", None,
            "\nopen_secondary_descriptor_prefix = lambda *args, **kwargs: None\n"),
        "missing-owner-forwarding": ("factory",
            ("_observation_owner=_observation_owner", "_observation_owner=None"), None),
        "wrong-package-bridge-key": ("production",
            ('package_attempt_id=str(bridge.get("package_attempt_id"))',
             'package_attempt_id=str(bridge.get("authorization_id"))'), None),
        "wrong-secondary-bridge-key": ("production",
            ('consumer_event_id=str(bridge.get("secondary_event_id"))',
             'consumer_event_id=str(bridge.get("primary_event_id"))'), None),
    }
    mutation_root = Path(work) / "separation-mutations"
    mutation_root.mkdir(mode=0o700)
    for index, (name, (target, replacement, suffix)) in enumerate(mutations.items(), 1):
        paths = dict(originals)
        raw = originals[target].read_text()
        if replacement is not None:
            old, new = replacement
            count = raw.count(old)
            if count == 0:
                raise AssertionError("MUTATION_TARGET_ABSENT:" + name)
            raw = raw.replace(old, new)
        if suffix is not None:
            raw += suffix
        mutated = mutation_root / ("%02d-%s.py" % (index, name))
        mutated.write_text(raw)
        paths[target] = mutated
        failure = None
        try:
            _validate_separation(paths)
        except ValueError as error:
            failure = str(error)
        if not failure:
            raise AssertionError("SEPARATION_MUTATION_UNEXPECTED_PASS:" + name)
        _validate_separation(originals)
        results.append({"case": name, "result": "PASS", "expected": "REJECT",
                        "failure": failure, "restored": "PASS"})
    return results


def run(case_id, work, view):
    if case_id != "INTEGRATION":
        raise ValueError("FIXED_SECONDARY_OWNER_CASE")
    results = []

    f = Fixture(work, "production-no-identity-copies")
    try:
        f.candidate = _production_candidate(f, view)
        f.mode = "real-pread"
        f.open()
        raw = f.read()
        attachment = f.finish()
        _record(results, work, "production-no-identity-copies", f, attachment,
                "COMPLETE", {"returned_hex": raw.hex(),
                "candidate_keys": sorted(f.candidate),
                "authority_binding": dict(f.authority)})
    finally:
        f.cleanup()

    f = Fixture(work, "equal-optional-copies")
    try:
        f.candidate = _production_candidate(f, view)
        f.candidate.update(package_attempt_id=f.authority["package_attempt_id"],
                           secondary_event_id=f.authority["consumer_event_id"],
                           role="SECONDARY", consumer_role="SECONDARY")
        f.open(); f.read()
        _record(results, work, "equal-optional-copies", f, f.finish(), "COMPLETE")
    finally:
        f.cleanup()

    candidate_mutations = (
        ("conflicting-package-copy", "package_attempt_id", "WRONG-PACKAGE"),
        ("malformed-package-copy", "package_attempt_id", 1),
        ("conflicting-event-copy", "secondary_event_id", "WRONG-EVENT"),
        ("malformed-event-copy", "secondary_event_id", False),
        ("wrong-role", "role", "PRIMARY"),
        ("wrong-consumer-role", "consumer_role", "PRIMARY"),
    )
    for name, key, value in candidate_mutations:
        f = Fixture(work, name)
        try:
            f.candidate = _production_candidate(f, view)
            f.candidate[key] = value
            attachment = _attachment_without_read(f)
            _record(results, work, name, f, attachment, "INCOMPLETE",
                    {"failure": attachment["measurement_failure"]})
        finally:
            f.cleanup()

    authority_mutations = (
        ("missing-authority-package", "package_attempt_id", None, True),
        ("malformed-authority-package", "package_attempt_id", "bad_value", False),
        ("missing-authority-event", "consumer_event_id", None, True),
        ("malformed-authority-event", "consumer_event_id", 7, False),
    )
    for name, key, value, remove in authority_mutations:
        f = Fixture(work, name)
        try:
            f.candidate = _production_candidate(f, view)
            if remove:
                f.authority.pop(key)
            else:
                f.authority[key] = value
            attachment = _attachment_without_read(f)
            _record(results, work, name, f, attachment, "INCOMPLETE",
                    {"failure": attachment["measurement_failure"]})
        finally:
            f.cleanup()

    for mode in ("short", "error"):
        f = Fixture(work, "production-" + mode)
        try:
            f.candidate = _production_candidate(f, view)
            f.open(); f.mode = mode
            failure = None
            try:
                f.read()
                raise AssertionError("EXPECTED_READ_FAILURE")
            except (OSError, ValueError) as error:
                failure = str(error)
            attachment = f.finish("RAISED")
            _record(results, work, "production-" + mode, f, attachment,
                    "COMPLETE", {"read_failure": failure,
                    "truthful_prefix": attachment["validated_prefix_counters"]})
        finally:
            f.cleanup()

    for mode in ("missing-owner", "replaced-owner", "reused-owner"):
        f = Fixture(work, mode)
        try:
            f.candidate = _production_candidate(f, view)
            f.open(); f.read()
            if mode == "missing-owner":
                f.prefix.store._observation_owner = None
            elif mode == "replaced-owner":
                f.prefix.store._observation_owner = object()
            else:
                f.prefix.owner.bind(f.prefix.store, f.candidate, f.identities)
            attachment = f.finish()
            _record(results, work, mode, f, attachment, "INCOMPLETE",
                    {"failure": attachment["measurement_failure"]})
        finally:
            f.cleanup()

    f = Fixture(work, "durable-closure-failure")
    original_fsync = observation.os.fsync
    try:
        f.candidate = _production_candidate(f, view)
        f.open(); f.read()
        def fail_fsync(descriptor):
            if descriptor == f.prefix.owner.directory_fd:
                raise OSError("SYNTHETIC_DURABLE_CLOSURE_FAILURE")
            return original_fsync(descriptor)
        observation.os.fsync = fail_fsync
        attachment = f.finish()
        observation.os.fsync = original_fsync
        _record(results, work, "durable-closure-failure", f, attachment,
                "INCOMPLETE", {"failure": attachment["measurement_failure"]})
    finally:
        observation.os.fsync = original_fsync
        f.cleanup()

    f = Fixture(work, "cross-attempt-readback")
    try:
        f.candidate = _production_candidate(f, view)
        f.open(); f.read()
        good = f.finish(); require_complete(good, f.transcript)
        bad = f.back(consumer_event_id="DIFFERENT-SECONDARY-EVENT")
        _record(results, work, "cross-attempt-readback", f, bad, "INCOMPLETE",
                {"good_closure": "COMPLETE", "failure": bad["measurement_failure"]})
    finally:
        f.cleanup()

    separation = _separation_cases(work, view)
    report = {
        "schema": "pulsarmlx.f017.secondary-owner-ci-focused-qualification/1",
        "result": "PASS", "owner_cases": results,
        "separation_cases": separation,
        "production_candidate_identity_source": "EXACT_COORDINATOR_TARGET_CANDIDATE_FUNCTION",
        "predecessor_qualification": "REUSED_NOT_RERUN:38_CASES_PER_ROOT;76_ROWS;12_MUTATION_FAMILIES",
        "numerical_equivalence": {"returned_descriptor_bytes_and_request_order": "PASS_EXERCISED_DIMENSION",
            "numpy_numerical_core": "NOT_RUN", "native": "NOT_RUN", "full_model": "NOT_RUN"},
        "open_findings": ["F017-SEC-02", "F017-SEC-03", "F017-SEC-04", "F017-SEC-05",
                          "PRIMARY_OWNER_COMPLETENESS", "NATIVE_FULL_FORWARD"],
        "checkpoint_access": 0, "event06_retry_or_go": False,
        "p1_authority": False, "historical_master_ledger": 175,
    }
    raw = canonical(report)
    if len(raw) > 1048576:
        raise ValueError("FOCUSED_REPORT_BOUND")
    (Path(work) / "secondary-owner-cases.json").write_bytes(raw)
    return {"result": "PASS", "owner_case_count": len(results),
            "separation_case_count": len(separation),
            "report": "secondary-owner-cases.json", "report_bytes": len(raw),
            "report_sha256": hashlib.sha256(raw).hexdigest(),
            "checkpoint_access": 0, "numerical_decode": "NOT_RUN"}
