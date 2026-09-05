from __future__ import annotations

import ast
from collections.abc import Mapping
import inspect
import os
from pathlib import Path
import sys
import threading

import pytest

import f017_event06_minimum_gate_path_v1 as path
import qualify_f017_event06_minimum_gate_path_v1 as qualification_module
from f017_result_envelope_v11 import ResultEnvelopeError
from qualify_f017_event06_minimum_gate_path_v1 import qualify


def _unseal_graph_owned_test_leaf(target: Path) -> None:
    descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        path._set_user_immutable(descriptor, False)
    finally:
        os.close(descriptor)


@pytest.fixture(scope="module")
def qualification() -> dict[str, object]:
    return qualify()


def test_minimum_path_has_one_execution_entry_and_one_nonexecuting_closeout() -> None:
    assert path.__all__ == (
        "execute_event06_minimum_gate_path",
        "closeout_interrupted_event06_minimum_gate_path",
    )
    for public in (
        path.execute_event06_minimum_gate_path,
        path.closeout_interrupted_event06_minimum_gate_path,
    ):
        signature = inspect.signature(public)
        assert tuple(signature.parameters) == ("collapsed_go_bytes",)
        parameter = signature.parameters["collapsed_go_bytes"]
        assert parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert all(
            item.kind
            not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
            for item in signature.parameters.values()
        )


def test_closeout_without_durable_start_has_zero_execution_effects(
    tmp_path: Path,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_386_925_000
    seed = b"F017-S42-NONEXECUTING-CLOSEOUT"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    validated = path._validate_go_bytes(raw, profile, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        str(validated.get("human_decision_sha256")),
        intercept=False,
    )

    result = path._invoke_public_closeout_qualification(
        raw, runtime, now_unix_ns=now
    )

    assert result == {
        "result": "NO_DURABLE_PACKAGE_START",
        "terminal_written": False,
        "checkpoint_effects": 0,
        "numerical_effects": 0,
    }
    assert not runtime.storage.package_directory.exists()
    assert runtime.storage._package_fd is None
    assert runtime.integration_state.snapshot() == {"package_starts": 0}
    provider = runtime.checkpoint_effect
    assert type(provider) is path._SyntheticCheckpointProvider
    assert provider.physical_identity_producer_calls == 0
    assert provider.producer_checkpoint_binding_checks == 0
    assert provider.producer_checkpoint_shard_opens == 0
    assert provider.producer_checkpoint_identity_hash_reads == 0
    numerical = runtime.numerical_effect
    assert type(numerical) is path._SyntheticNumericalProvider
    assert numerical.executions == {"PRIMARY": 0, "SECONDARY": 0}
    assert runtime.observed_effects["checkpoint_root_resolutions"] == 0
    assert runtime.observed_effects["checkpoint_opens"] == 0
    assert runtime.observed_effects["numerical_executions"] == 0


def test_qualification_root_rejects_live_overlap_and_intermediate_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_package = tmp_path / "live-package"
    live_checkpoint = tmp_path / "live-checkpoint"
    live_package.mkdir()
    live_checkpoint.mkdir()
    (live_package / "child").mkdir()
    (live_checkpoint / "child").mkdir()
    monkeypatch.setattr(path, "_LIVE_PACKAGE_PARENT", live_package)
    monkeypatch.setattr(path, "_LIVE_CHECKPOINT_ROOT", live_checkpoint)

    opened: list[object] = []
    real_open = os.open

    def tracked_open(target, flags, mode=0o777, *, dir_fd=None):
        opened.append(target)
        return real_open(target, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(path.os, "open", tracked_open)
    for live in (live_package, live_checkpoint):
        for candidate in (live, live / "child", live.parent):
            opened.clear()
            with pytest.raises(ValueError, match="overlap a live root"):
                path._qualification_root(candidate)
            assert opened == []

    safe = tmp_path / "safe"
    safe.mkdir()
    for index, live in enumerate((live_package, live_checkpoint), start=1):
        alias = safe / f"alias-{index}"
        alias.symlink_to(live, target_is_directory=True)
        opened.clear()
        with pytest.raises(ValueError, match="nonsymlink directory"):
            path._qualification_root(alias / "child")
        assert live not in opened
        assert str(live) not in opened
        assert live.name not in opened

    opened.clear()
    double_anchor = Path("//" + str(tmp_path).lstrip("/"))
    with pytest.raises(ValueError, match="noncanonical"):
        path._qualification_root(double_anchor)
    assert opened == []

    opened.clear()
    with pytest.raises(ValueError, match="overlap a live root"):
        path._qualification_root(Path("/Applications"))
    assert opened == []

    opened.clear()
    with pytest.raises(ValueError, match="fixed canonical absolute path"):
        path._open_directory_chain(double_anchor, create=False)
    assert opened == []


@pytest.mark.parametrize("replacement_kind", ["directory", "symlink"])
def test_synthetic_checkpoint_provider_rejects_fixture_leaf_replacement(
    tmp_path: Path,
    replacement_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_386_950_000
    seed = b"F017-S41-CHECKPOINT-FIXTURE-IDENTITY"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    validated = path._validate_go_bytes(raw, profile, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path, path._sha(seed), intercept=False
    )
    installed = path._build_installed_authority(validated, runtime)
    provider = runtime.checkpoint_effect
    assert type(provider) is path._SyntheticCheckpointProvider

    checkpoint_root = tmp_path / runtime.synthetic_checkpoint_leaf
    original = tmp_path / f"original-{replacement_kind}"
    checkpoint_root.rename(original)
    if replacement_kind == "directory":
        checkpoint_root.mkdir(mode=0o700)
    else:
        checkpoint_root.symlink_to(original, target_is_directory=True)

    opened_parents: list[int] = []
    original_open_chain = path._open_directory_chain

    def track_parent(candidate: Path, *, create: bool) -> int:
        descriptor = original_open_chain(candidate, create=create)
        opened_parents.append(descriptor)
        return descriptor

    monkeypatch.setattr(path, "_open_directory_chain", track_parent)
    with pytest.raises((OSError, ValueError)):
        provider._require_graph_owned_checkpoint_binding(installed, runtime.storage)
    assert len(opened_parents) == 2
    for descriptor in opened_parents:
        with pytest.raises(OSError):
            os.fstat(descriptor)
    assert provider.physical_identity_producer_calls == 0
    assert provider.producer_checkpoint_shard_opens == 0
    assert provider.producer_checkpoint_identity_hash_reads == 0


def test_synthetic_checkpoint_provider_rejects_leaf_replacement_after_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_386_975_000
    seed = b"F017-S41-CHECKPOINT-LEAF-IDENTITY"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path, path._sha(seed), intercept=False
    )
    provider = runtime.checkpoint_effect
    assert type(provider) is path._SyntheticCheckpointProvider
    original = path._SyntheticCheckpointProvider._require_graph_owned_checkpoint_binding
    replaced_name = str(profile.shards[0]["filename"])

    def replace_after_binding(
        current: object,
        authority: object,
        storage: object,
    ) -> int:
        checkpoint_fd = original(current, authority, storage)
        os.unlink(replaced_name, dir_fd=checkpoint_fd)
        replacement = os.open(
            replaced_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=checkpoint_fd,
        )
        os.close(replacement)
        return checkpoint_fd

    monkeypatch.setattr(
        path._SyntheticCheckpointProvider,
        "_require_graph_owned_checkpoint_binding",
        replace_after_binding,
    )
    with pytest.raises(path._IdentityHandoffFailure) as captured:
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)
    assert captured.value.release_outcome["attempted_closures"] == 5
    assert captured.value.release_outcome["successful_closures"] == 5
    assert captured.value.release_outcome["live_leases_after_release"] == 0
    assert provider.physical_identity_producer_calls == 1
    assert provider.producer_checkpoint_shard_opens == 6
    assert provider.producer_checkpoint_identity_hash_reads == 6


def test_synthetic_checkpoint_root_close_failure_releases_producer_leases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_386_990_000
    seed = b"F017-S41-CHECKPOINT-ROOT-CLOSE-FAILURE"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path, path._sha(seed), intercept=False
    )
    original_close = path._close_synthetic_checkpoint_root_descriptor

    def close_then_raise(descriptor: int) -> None:
        original_close(descriptor)
        raise OSError("injected checkpoint root close completion error")

    monkeypatch.setattr(
        path, "_close_synthetic_checkpoint_root_descriptor", close_then_raise
    )
    with pytest.raises(path._IdentityHandoffFailure) as captured:
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)
    assert captured.value.cause_type == "OSError"
    assert captured.value.release_outcome["attempted_closures"] == 5
    assert captured.value.release_outcome["successful_closures"] == 5
    assert captured.value.release_outcome["live_leases_after_release"] == 0


def test_source_derived_gate_and_bypass_closure(
    qualification: dict[str, object],
) -> None:
    closure = qualification["source_derived_closure"]
    assert isinstance(closure, dict)
    assert closure["required_gates_enforced"] == "17/17"
    assert closure["extra_required_gates"] == 0
    assert closure["uncovered_required_gates"] == 0
    assert closure["removed_mechanisms_still_gating"] == 0
    assert closure["implementation_dependencies_remaining"] == 0
    assert closure["optional_diagnostics_mandatory"] == 0
    assert closure["public_production_exports"] == [
        "execute_event06_minimum_gate_path",
        "closeout_interrupted_event06_minimum_gate_path",
    ]
    assert closure["public_execution_exports"] == [
        "execute_event06_minimum_gate_path"
    ]
    assert closure["public_nonexecuting_closeout_exports"] == [
        "closeout_interrupted_event06_minimum_gate_path"
    ]
    assert closure["public_signature_parameters"] == ["collapsed_go_bytes"]
    assert closure["public_closeout_signature_parameters"] == [
        "collapsed_go_bytes"
    ]
    assert closure["prohibited_public_closeout_parameters"] == []
    assert closure["closeout_execution_entry_reachable"] is False
    assert closure["closeout_gate_symbols"] == []
    assert closure["closeout_effectful_execution_calls"] == []
    assert closure["closeout_is_nonexecuting"] is True
    assert closure["public_raw_identity_inputs"] == 0
    assert closure["public_storage_location_inputs"] == 0
    surface = closure["superseded_surface"]
    assert isinstance(surface, dict)
    assert surface["effectful_entrypoints_checked"] == 32
    assert surface["sequence39_explicit_tombstones"] == 27
    assert surface["historical_intrinsic_fail_closed"] == 5
    assert surface["uncensused_effectful_public_root_count"] == 0
    assert surface["uncensused_effectful_public_roots"] == []
    assert surface["callable_legacy_or_superseded_bypasses"] == 0
    assert all(
        item["exported"] is False
        and item["first_effect_is_raise"] is True
        and item["runtime_fail_closed_before_effect"] is True
        and item["private_qualification_symbol_present"] is True
        and item["private_qualification_symbol_exported"] is False
        for item in surface["effectful_entrypoint_rows"]
        if item["closure_class"] == "SEQUENCE39_EXPLICIT_TOMBSTONE"
    )
    assert all(
        item["runtime_fail_closed_before_effect"] is True
        and item["effect_calls"] == []
        for item in surface["effectful_entrypoint_rows"]
        if item["closure_class"] == "HISTORICAL_INTRINSIC_FAIL_CLOSED"
    )

    imports = closure["recursive_imported_producer_consumer_inventory"]
    assert imports["source_only"] is True
    assert imports["entry_module"] == "f017_event06_minimum_gate_path_v1"
    assert imports["module_count"] == len(imports["modules"])
    assert imports["module_count"] > 1
    imported_names = {item["module"] for item in imports["modules"]}
    assert len(imported_names) == imports[
        "module_count"
    ]
    assert "f017_event06_execution_plan_v1" not in imported_names
    assert "f017_event06_numerical_bridge_v1" not in imported_names
    assert "f017_event06_numerical_bridge_v2" not in imported_names
    assert all(len(item["sha256"]) == 64 for item in imports["modules"])


def test_all_sixteen_dependency_equivalence_classes_are_source_mapped_and_removed(
    qualification: dict[str, object],
) -> None:
    mapping = qualification["source_derived_closure"][
        "implementation_dependency_resolution"
    ]
    assert isinstance(mapping, dict)
    assert mapping["mapped"] == mapping["expected"] == 16
    assert mapping["remaining"] == 0
    assert mapping["remaining_ids"] == []
    assert mapping["renamed_nested_indirect_equivalents_checked"] is True
    rows = mapping["rows"]
    assert [item["mechanism_id"] for item in rows] == [
        "M018",
        "M019",
        "M020",
        "M021",
        "M022",
        "M023",
        "M024",
        "M025",
        "M026",
        "M027",
        "M028",
        "M029",
        "M030",
        "M031",
        "M032",
        "M035",
    ]
    assert all(item["resolved"] is True for item in rows)
    assert all(item["separate_normative_dependency_present"] is False for item in rows)


def test_each_retained_gate_has_a_source_derived_schema_and_type_mapping(
    qualification: dict[str, object],
) -> None:
    rows = qualification["source_derived_closure"][
        "retained_gate_schema_type_mapping"
    ]
    assert len(rows) == 17
    assert [item["mechanism_id"] for item in rows] == [
        f"M{index:03d}" for index in range(1, 18)
    ]
    assert len({item["gate_symbol"] for item in rows}) == 17
    assert all(len(item["source_sha256"]) == 64 for item in rows)


def test_exactly_three_private_seams_and_contextvar_is_only_a_sealed_carrier(
    qualification: dict[str, object],
) -> None:
    seams = qualification["source_derived_closure"][
        "synthetic_interposition_seams"
    ]
    assert seams["seam_count"] == 3
    assert [item["class"] for item in seams["seams"]] == [
        "_SyntheticCheckpointProvider",
        "_SyntheticNumericalProvider",
        "_SyntheticStorageBinding",
    ]
    assert seams["all_seams_private"] is True
    assert seams["all_seams_seal_guarded"] is True
    assert seams["contextvar_bindings"] == ["_QUALIFICATION_INVOCATION"]
    assert seams["contextvar_carrier_fields"] == [
        "seal",
        "runtime",
        "now_unix_ns",
        "collapsed_go_sha256",
    ]
    assert seams["contextvar_is_public_export"] is False
    assert seams["contextvar_is_public_parameter"] is False
    assert seams["public_effect_injection_inputs"] == 0
    assert seams["contextvar_classification"].endswith("NOT_A_FOURTH_SEAM")


def test_package_start_consumed_gate_and_identity_key_censuses_are_derived(
    qualification: dict[str, object],
) -> None:
    closure = qualification["source_derived_closure"]
    relation = closure["package_start_consumed_gate_relation"]
    assert relation["result"] == "PASS"
    assert relation["consume_line"] < relation["durable_start_bank_line"]
    assert relation["durable_start_bank_line"] < relation[
        "one_shot_state_consume_line"
    ]
    assert relation["executor_consumed_assignment_line"] < relation[
        "executor_first_identity_effect_line"
    ]
    assert relation["synthetic_fixture_build_line"] < relation[
        "executor_consumed_assignment_line"
    ]
    assert relation["synthetic_fixture_precedes_package_start"] is True
    assert relation["package_start_without_consumed_gate"] == 0
    effect_guards = {
        item["consumer"]: item for item in relation["effect_guards"]
    }
    assert set(effect_guards) == {
        "_ProductionCheckpointEffect.run",
        "_SyntheticCheckpointProvider.run",
    }
    for item in effect_guards.values():
        assert item["guard_line"] < item["first_effect_line"]
        assert item["consumed_gate_is_first_argument"] is True

    identities = closure["package_identity_key_census"]
    assert identities["result"] == "PASS"
    assert identities["distinct_identity_key_count"] == 4
    assert identities["package_identity_keys_per_identity"] == 1
    assert set(identities["key_occurrences"].values()) == {1}
    assert identities["alias_keys"] == []
    assert identities["identity_plan_compatibility_value"] is None
    assert identities["identity_plan_is_separately_supplied"] is False
    assert identities["identity_plan_is_separately_validated"] is False
    assert identities["identity_authority_field_count"] == 21
    assert "event_identity_plan_sha256" in identities[
        "removed_identity_ceremony_fields"
    ]

    evidence = closure["identity_success_leaf_census"]
    expected_evidence_leaves = {
        "access-journal.json",
        "identity-core.json",
        "identity-manifest.json",
        "identity-receipt.json",
        "identity-terminal.json",
        "lease-manifest.json",
        "shard-receipts.json",
        *(f"access-prefix-{sequence:02d}.json" for sequence in range(1, 25)),
    }
    assert evidence["derivation"] == "AST_PRODUCER_EXPORT_AND_LITERAL_RANGE"
    assert evidence["producer_export"] == "identity_success_evidence_leaves"
    assert evidence["composer_uses_producer_export"] is True
    assert evidence["base_leaf_count"] == 7
    assert evidence["access_prefix_leaf_count"] == 24
    assert evidence["leaf_count"] == 31
    assert evidence["leaves"] == sorted(expected_evidence_leaves)
    assert set(path._SUCCESS_PHYSICAL_IDENTITY_FILES) == expected_evidence_leaves

    stage_receipt = closure["stage_receipt_binding_census"]
    assert stage_receipt["authority_keys"] == [
        "stage",
        "authorization_id",
        "package_attempt_id",
        "stage_event_id",
        "package_start_sha256",
    ]
    assert stage_receipt["digest_field"] == "stage_authority_sha256"
    assert stage_receipt["digest_rederived_on_read"] is True
    assert stage_receipt["unvalidated_subject_sha256_present"] is False

    ownership = closure["predicate_ownership"]
    assert ownership["accepted_retained_owner_mechanisms"] == [
        f"M{index:03d}" for index in range(1, 18)
    ]
    assert {
        "M001", "M003", "M004", "M006", "M009", "M012", "M013"
    } <= set(ownership["observed_owner_mechanisms"])
    assert ownership["expected_component_count"] > 0
    assert ownership["expected_component_count"] == ownership[
        "observed_component_count"
    ]
    assert ownership["missing_component_count"] == 0
    assert ownership["extra_component_count"] == 0
    assert ownership["expected_predicate_count"] > 0
    assert ownership["expected_predicate_count"] == ownership[
        "observed_predicate_count"
    ]
    assert ownership["missing_predicate_count"] == 0
    assert ownership["extra_predicate_count"] == 0
    assert ownership["owned_predicate_count"] == len(
        ownership["owned_predicate_rows"]
    )
    assert ownership["unowned_predicate_count"] == 0
    assert ownership["unowned_predicates"] == []
    assert ownership["new_independently_enforceable_mechanisms"] == 0
    assert ownership["no_eighteenth_required_gate"] is True


def test_predicate_census_detects_unowned_production_checks_and_prunes_qualification() -> None:
    source = Path(path.__file__).read_text(encoding="utf-8")
    baseline = qualification_module._predicate_ownership_census(ast.parse(source))
    injected = source.replace(
        "        _validate_fresh_integration_state(runtime.integration_state, runtime.scope)\n",
        "        if os.getpid() < 0:\n"
        "            raise RuntimeError('UNOWNED_SEQUENCE39_CHECK')\n"
        "        _validate_fresh_integration_state(runtime.integration_state, runtime.scope)\n",
        1,
    )
    mutated = qualification_module._predicate_ownership_census(ast.parse(injected))
    assert mutated["result"] == "FAIL"
    assert mutated["new_independently_enforceable_mechanisms"] > 0
    assert mutated["unowned_predicate_count"] > 0

    qualification_only = source.replace(
        "def _qualification_go(profile: _AuthorityProfile, human_seed: bytes,\n",
        "def _qualification_probe_only() -> None:\n"
        "    if os.getpid() < 0:\n"
        "        raise RuntimeError('QUALIFICATION_ONLY_CHECK')\n\n\n"
        "def _qualification_go(profile: _AuthorityProfile, human_seed: bytes,\n",
        1,
    )
    pruned = qualification_module._predicate_ownership_census(
        ast.parse(qualification_only)
    )
    assert pruned["result"] == "PASS"
    assert pruned["expected_component_count"] == baseline[
        "expected_component_count"
    ]
    assert pruned["expected_predicate_count"] == baseline[
        "expected_predicate_count"
    ]


def test_storage_rejects_directory_retarget_and_symlink_substitution(
    tmp_path: Path,
) -> None:
    replacement_root = tmp_path / "replacement"
    replacement_root.mkdir()
    replacement = path._SyntheticStorageBinding(
        path._SYNTHETIC_STORAGE_SEAL,
        replacement_root,
        "retarget",
    )
    replacement.prepare()
    replacement_displaced = replacement.package_directory.with_name(
        "minimum-gate-retarget-displaced"
    )
    replacement.package_directory.rename(replacement_displaced)
    replacement.package_directory.mkdir()
    with pytest.raises(RuntimeError, match="canonical package directory identity"):
        replacement.bank("must-not-bank.json", {"result": "FAIL"})
    assert not (replacement.package_directory / "must-not-bank.json").exists()
    assert not (replacement_displaced / "must-not-bank.json").exists()
    replacement.close()

    symlink_root = tmp_path / "symlink"
    symlink_root.mkdir()
    symlink = path._SyntheticStorageBinding(
        path._SYNTHETIC_STORAGE_SEAL,
        symlink_root,
        "substitution",
    )
    symlink.prepare()
    symlink_displaced = symlink.package_directory.with_name(
        "minimum-gate-substitution-displaced"
    )
    symlink.package_directory.rename(symlink_displaced)
    symlink.package_directory.symlink_to(symlink_displaced, target_is_directory=True)
    with pytest.raises(OSError):
        symlink.bank("must-not-bank.json", {"result": "FAIL"})
    assert not (symlink_displaced / "must-not-bank.json").exists()
    symlink.close()


def test_legacy_path_call_is_descriptor_anchored_during_directory_retarget(
    tmp_path: Path,
) -> None:
    storage = path._SyntheticStorageBinding(
        path._SYNTHETIC_STORAGE_SEAL,
        tmp_path,
        "in-call-retarget",
    )
    storage.prepare()
    displaced = storage.package_directory.with_name(
        "minimum-gate-in-call-retarget-displaced"
    )

    def retarget_and_write(child: Path) -> None:
        storage.package_directory.rename(displaced)
        storage.package_directory.mkdir()
        child.mkdir(exist_ok=True)
        (child / "legacy-writer-output.bin").write_bytes(b"descriptor-anchored")

    with pytest.raises(RuntimeError, match="canonical package directory identity"):
        storage.anchored_path_call("legacy-output", retarget_and_write)
    assert not (
        storage.package_directory / "legacy-output" / "legacy-writer-output.bin"
    ).exists()
    assert (
        displaced / "legacy-output" / "legacy-writer-output.bin"
    ).read_bytes() == b"descriptor-anchored"
    storage._set_existing_leaf_immutability(
        False, verify_canonical_path=False
    )
    storage.close()


def test_storage_descriptor_closes_after_success_and_preopen_failure(
    tmp_path: Path,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_350_000_000
    cases = (
        ("success", b"F017-S39-STORAGE-CLOSE-SUCCESS", False),
        ("preopen", b"F017-S39-STORAGE-CLOSE-PREOPEN", True),
    )
    for name, seed, intercept in cases:
        root = tmp_path / name
        root.mkdir()
        raw = path._qualification_go(profile, seed, now_unix_ns=now)
        runtime = path._qualification_runtime(
            root,
            path._sha(seed),
            intercept=intercept,
        )
        runtime.storage.prepare()
        descriptor = runtime.storage._package_fd
        assert type(descriptor) is int

        if intercept:
            with pytest.raises(RuntimeError, match="^PREOPEN_INTERCEPTED$"):
                path._invoke_public_qualification(raw, runtime, now_unix_ns=now)
        else:
            assert path._invoke_public_qualification(
                raw, runtime, now_unix_ns=now
            )["result"] == "PASS"

        assert runtime.storage._package_fd is None
        assert runtime.storage._package_identity is None
        with pytest.raises(OSError):
            os.fstat(descriptor)


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="pthread_fchdir_np is the fixed Darwin storage anchor",
)
def test_thread_local_storage_anchor_survives_process_cwd_churn(
    tmp_path: Path,
) -> None:
    storage = path._SyntheticStorageBinding(
        path._SYNTHETIC_STORAGE_SEAL,
        tmp_path,
        "cwd-churn",
    )
    storage.prepare()
    outside_a = tmp_path / "outside-a"
    outside_b = tmp_path / "outside-b"
    for outside in (outside_a, outside_b):
        outside.mkdir()
        (outside / "anchored-output").mkdir()

    original_cwd_fd = os.open(".", os.O_RDONLY | os.O_DIRECTORY)
    start = threading.Event()
    churned = threading.Event()
    stop = threading.Event()
    worker_errors: list[BaseException] = []

    def churn_process_cwd() -> None:
        try:
            if not start.wait(timeout=5):
                raise AssertionError("anchored operation did not start")
            while not stop.is_set():
                os.chdir(outside_a)
                churned.set()
                os.chdir(outside_b)
        except BaseException as exc:
            worker_errors.append(exc)
        finally:
            churned.set()

    worker = threading.Thread(target=churn_process_cwd, daemon=True)
    worker.start()
    try:
        def write_while_cwd_churns(child: Path) -> None:
            start.set()
            assert churned.wait(timeout=5)
            try:
                for ordinal in range(32):
                    (child / f"artifact-{ordinal:02d}.bin").write_bytes(
                        b"descriptor-anchored"
                    )
            finally:
                stop.set()

        storage.anchored_path_call("anchored-output", write_while_cwd_churns)
    finally:
        start.set()
        stop.set()
        worker.join(timeout=5)
        os.fchdir(original_cwd_fd)
        os.close(original_cwd_fd)
        storage._set_existing_leaf_immutability(
            False, verify_canonical_path=False
        )
        storage.close()

    assert not worker.is_alive()
    assert worker_errors == []
    assert len(list((storage.package_directory / "anchored-output").iterdir())) == 32
    assert list((outside_a / "anchored-output").iterdir()) == []
    assert list((outside_b / "anchored-output").iterdir()) == []


def test_m008_rejects_oracle_disagreement_even_with_valid_thresholds() -> None:
    comparison = {
        "thresholds": {
            "max_absolute_error": path._MAX_ABS_LIMIT,
            "rmse": path._RMSE_LIMIT,
            "cosine_minimum": path._COSINE_MINIMUM,
        },
        "classification": "ORACLE_DISAGREEMENT",
    }
    with pytest.raises(ValueError, match="comparison classification"):
        path._gate_m008_comparison_rules(comparison)


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    (
        ("primary-logits", "payload SHA mismatch"),
        ("identity-evidence", "identity evidence leaf immutability"),
    ),
)
def test_m016_revalidates_banked_bytes_after_comparison(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_error: str,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_375_000_000
    seed = f"F017-S39-M016-{mutation}".encode("ascii")
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._gate_m016_immutable_result_closure
    closure_reached = False

    def mutate_then_close(
        primary: dict[str, object],
        secondary: dict[str, object],
        comparison: dict[str, object],
        comparison_terminal_sha256: str,
        identity: object,
        bridge: object,
        storage: object,
    ) -> dict[str, object]:
        nonlocal closure_reached
        closure_reached = True
        assert (
            runtime.storage.package_directory / "comparison-terminal.json"
        ).is_file()
        if mutation == "primary-logits":
            artifacts = primary["artifacts"]
            assert isinstance(artifacts, dict)
            manifest = artifacts["manifest"]
            assert isinstance(manifest, dict)
            logits_record = manifest["payloads"][2]
            logits_path = (
                runtime.storage.package_directory
                / "primary"
                / logits_record["path_role"]
            )
            _unseal_graph_owned_test_leaf(logits_path)
            mutated = bytearray(logits_path.read_bytes())
            mutated[-1] ^= 1
            logits_path.write_bytes(mutated)
        else:
            evidence_path = (
                runtime.storage.package_directory / "identity" / "access-journal.json"
            )
            _unseal_graph_owned_test_leaf(evidence_path)
            evidence = path._parse_artifact_bytes(evidence_path.read_bytes())
            assert isinstance(evidence, dict)
            evidence["checkpoint_shard_opens"] = 5
            evidence_path.write_bytes(path._canonical_bytes(evidence))
        return original(
            primary,
            secondary,
            comparison,
            comparison_terminal_sha256,
            identity,
            bridge,
            storage,
        )

    monkeypatch.setattr(
        path,
        "_gate_m016_immutable_result_closure",
        mutate_then_close,
    )
    with pytest.raises(ValueError, match=expected_error):
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert closure_reached is True
    assert runtime.storage._package_fd is None
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal["state"] == "TERMINAL_FAILURE"
    assert terminal["failed_stage"] == "COMPARISON_TERMINAL"


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    (
        ("primary-logits", "package success leaf is not immutable"),
        ("identity-evidence", "package success leaf is not immutable"),
        ("release-report", "package success leaf is not immutable"),
        (
            "receipt-derived-accounting",
            "package success leaf is not immutable",
        ),
        ("package-receipt", "package success leaf is not immutable"),
        (
            "v11-result-closure",
            "package success leaf is not immutable",
        ),
    ),
)
def test_package_terminal_revalidates_every_raw_closure_leaf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_error: str,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_376_000_000
    seed = f"F017-S39-TERMINAL-CLOSURE-{mutation}".encode("ascii")
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original_stop = path._gate_m004_stop_boundary
    mutated = False

    def mutate_at_terminal(stage_stop: object, stage: str, observed_runtime: object) -> None:
        nonlocal mutated
        original_stop(stage_stop, stage, observed_runtime)
        if stage != "PACKAGE_TERMINAL" or mutated:
            return
        mutated = True
        package = runtime.storage.package_directory
        if mutation == "primary-logits":
            manifest = path._parse_artifact_bytes(
                (package / "primary" / "primary-payload-manifest.json").read_bytes()
            )
            payload = package / "primary" / manifest["payloads"][2]["path_role"]
            _unseal_graph_owned_test_leaf(payload)
            raw_payload = bytearray(payload.read_bytes())
            raw_payload[-1] ^= 1
            payload.write_bytes(raw_payload)
            return
        leaf = {
            "release-report": "release-report.json",
            "receipt-derived-accounting": "receipt-derived-accounting.json",
            "package-receipt": "package-receipt.json",
            "v11-result-closure": "v11-result-closure.json",
        }.get(mutation)
        target = (
            package / "identity" / "access-journal.json"
            if mutation == "identity-evidence"
            else package / str(leaf)
        )
        _unseal_graph_owned_test_leaf(target)
        if mutation == "identity-evidence":
            evidence = path._parse_artifact_bytes(target.read_bytes())
            evidence["checkpoint_shard_opens"] = 5
            target.write_bytes(path._canonical_bytes(evidence))
        else:
            target.write_bytes(target.read_bytes() + b" ")

    monkeypatch.setattr(path, "_gate_m004_stop_boundary", mutate_at_terminal)
    with pytest.raises((ValueError, ResultEnvelopeError), match=expected_error):
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert mutated is True
    assert runtime.storage._package_fd is None
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal["state"] == "TERMINAL_FAILURE"
    assert terminal["failed_stage"] == "RELEASE_TERMINAL"


def test_success_terminal_post_commit_identity_revalidation_preserves_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_377_000_000
    seed = b"F017-S39-SUCCESS-TERMINAL-COMMIT-BOUNDARY"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._StorageBinding._verify_package_path_identity
    original_cleanup = path._close_storage_after_outcome
    post_terminal_checks: list[str] = []
    cleanup_started = False

    def reject_post_terminal_check(storage: object) -> None:
        terminal = storage.package_directory / "package-terminal.json"
        if terminal.exists():
            post_terminal_checks.append(
                "PRECOMMIT_RESERVATION"
                if terminal.stat().st_size == 0
                else storage.scope
            )
        original(storage)

    def mark_cleanup(storage: object) -> None:
        nonlocal cleanup_started
        cleanup_started = True
        original_cleanup(storage)

    monkeypatch.setattr(
        path._StorageBinding,
        "_verify_package_path_identity",
        reject_post_terminal_check,
    )
    monkeypatch.setattr(path, "_close_storage_after_outcome", mark_cleanup)
    result = path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert result["result"] == "PASS"
    # The terminal is reserved at package start, so ordinary descriptor-bound
    # banking performs many canonical checks while it is still empty.  Atomic
    # publication deliberately performs a final package-path revalidation
    # after the complete terminal inode is renamed into place.  That check is
    # inside the commit recovery boundary and therefore cannot reclassify the
    # already proven terminal.
    assert post_terminal_checks.count("PRECOMMIT_RESERVATION") > 1
    assert cleanup_started is True
    assert runtime.storage.scope in post_terminal_checks
    assert set(post_terminal_checks) == {
        "PRECOMMIT_RESERVATION",
        runtime.storage.scope,
    }
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal["outcome"] == "COMPLETE_SUCCESS"
    assert terminal["result"] == "PASS"


def test_post_terminal_storage_close_error_cannot_reclassify_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_378_000_000
    seed = b"F017-S39-POST-TERMINAL-STORAGE-CLOSE"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._StorageBinding.close
    close_attempts = 0

    def close_then_raise(storage: object) -> None:
        nonlocal close_attempts
        close_attempts += 1
        original(storage)
        raise OSError("post-terminal close diagnostic")

    monkeypatch.setattr(path._StorageBinding, "close", close_then_raise)
    result = path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert result["result"] == "PASS"
    assert close_attempts == 1
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal["outcome"] == "COMPLETE_SUCCESS"
    assert terminal["result"] == "PASS"


def test_public_success_result_is_deeply_immutable(
    tmp_path: Path,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_378_500_000
    seed = b"F017-S39-DEEPLY-IMMUTABLE-SUCCESS-RESULT"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    result = path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    comparison = result["comparison"]
    assert isinstance(comparison, Mapping)
    with pytest.raises(TypeError):
        comparison["classification"] = "FORGED"  # type: ignore[index]
    primary_top = comparison["primary_top32_ids"]
    assert isinstance(primary_top, tuple)


def test_raw_closure_is_immutable_during_terminal_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_379_000_000
    seed = b"F017-S39-IMMUTABLE-RAW-CLOSURE-COMMIT"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._StorageBinding._commit_reserved_success_terminal
    mutation_rejected = False

    def attempt_mutation_then_commit(
        storage: object,
        descriptor: int,
        value: object,
        stop: object,
        expected_sha256: str,
    ) -> None:
        nonlocal mutation_rejected
        receipt = storage.package_directory / "package-receipt.json"
        try:
            receipt.write_bytes(receipt.read_bytes() + b" ")
        except OSError:
            mutation_rejected = True
        original(storage, descriptor, value, stop, expected_sha256)

    monkeypatch.setattr(
        path._StorageBinding,
        "_commit_reserved_success_terminal",
        attempt_mutation_then_commit,
    )
    result = path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert result["result"] == "PASS"
    assert mutation_rejected is True


def test_terminal_is_immutable_before_directory_durability_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_380_000_000
    seed = b"F017-S39-IMMUTABLE-TERMINAL-DIRSYNC"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original_fsync = path.os.fsync
    mutation_rejected = False

    def attempt_terminal_mutation(descriptor: int) -> None:
        nonlocal mutation_rejected
        terminal = runtime.storage.package_directory / "package-terminal.json"
        if (
            descriptor == runtime.storage._package_fd
            and terminal.exists()
            and not mutation_rejected
        ):
            try:
                terminal.write_bytes(terminal.read_bytes() + b" ")
            except OSError:
                mutation_rejected = True
        original_fsync(descriptor)

    monkeypatch.setattr(path.os, "fsync", attempt_terminal_mutation)
    result = path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert result["result"] == "PASS"
    assert mutation_rejected is True
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal["outcome"] == "COMPLETE_SUCCESS"
    assert terminal["result"] == "PASS"


def test_package_root_is_immutable_across_success_terminal_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_381_000_000
    seed = b"F017-S39-IMMUTABLE-PACKAGE-ROOT-COMMIT"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._set_user_immutable
    retarget_rejected = False

    def attempt_root_retarget(descriptor: int, enabled: bool) -> None:
        nonlocal retarget_rejected
        original(descriptor, enabled)
        if (
            enabled
            and descriptor == runtime.storage._package_fd
            and not retarget_rejected
        ):
            displaced = runtime.storage.package_directory.with_name(
                runtime.storage.package_directory.name + "-displaced"
            )
            try:
                runtime.storage.package_directory.rename(displaced)
            except OSError:
                retarget_rejected = True

    monkeypatch.setattr(path, "_set_user_immutable", attempt_root_retarget)
    result = path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert result["result"] == "PASS"
    assert retarget_rejected is True
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal["outcome"] == "COMPLETE_SUCCESS"
    assert terminal["result"] == "PASS"


def test_sealed_success_inventory_rejects_new_root_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_382_000_000
    seed = b"F017-S39-SEALED-INVENTORY-NEW-ROOT-ENTRY"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._StorageBinding._verify_exact_success_inventory
    insertion_rejected = False

    def attempt_insertion_then_verify(storage: object, descriptor: int) -> None:
        nonlocal insertion_rejected
        try:
            os.open(
                "uncommitted-extra-leaf.bin",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=storage._package_fd,
            )
        except OSError:
            insertion_rejected = True
        original(storage, descriptor)

    monkeypatch.setattr(
        path._StorageBinding,
        "_verify_exact_success_inventory",
        attempt_insertion_then_verify,
    )
    result = path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert result["result"] == "PASS"
    assert insertion_rejected is True


def test_preexisting_unbound_entry_forces_package_terminal_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_383_000_000
    seed = b"F017-S39-UNBOUND-ROOT"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._gate_m004_stop_boundary
    inserted = False

    def insert_before_final_seal(
        stop: object, stage: str, observed_runtime: object
    ) -> None:
        nonlocal inserted
        original(stop, stage, observed_runtime)
        if stage == "PACKAGE_TERMINAL":
            parent = runtime.storage.package_directory
            (parent / "uncommitted-extra-leaf.bin").write_bytes(b"UNBOUND")
            inserted = True

    monkeypatch.setattr(path, "_gate_m004_stop_boundary", insert_before_final_seal)
    with pytest.raises(ValueError, match="entry census"):
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert inserted is True
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal["state"] == "TERMINAL_FAILURE"
    assert terminal["failed_stage"] == "RELEASE_TERMINAL"
    assert terminal["result"] == "FAIL"


def test_deep_hostile_unbound_directory_cannot_suppress_failure_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_383_125_000
    seed = b"F017-S39-DEEP-HOSTILE-UNBOUND-DIRECTORY"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._gate_m004_stop_boundary
    inserted = False

    def insert_deep_chain(
        stop: object, stage: str, observed_runtime: object
    ) -> None:
        nonlocal inserted
        original(stop, stage, observed_runtime)
        if stage != "PACKAGE_TERMINAL":
            return
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        root_fd = os.open(runtime.storage.package_directory, flags)
        current_fd = root_fd
        try:
            os.mkdir("hostile-depth", dir_fd=current_fd)
            child_fd = os.open("hostile-depth", flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = child_fd
            for _index in range(1_100):
                os.mkdir("d", dir_fd=current_fd)
                child_fd = os.open("d", flags, dir_fd=current_fd)
                os.close(current_fd)
                current_fd = child_fd
            inserted = True
        finally:
            os.close(current_fd)

    monkeypatch.setattr(path, "_gate_m004_stop_boundary", insert_deep_chain)
    with pytest.raises(ValueError, match="root entry census"):
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert inserted is True
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal["state"] == "TERMINAL_FAILURE"
    assert terminal["failed_stage"] == "RELEASE_TERMINAL"
    assert terminal["result"] == "FAIL"

    # CPython's recursive temporary-directory cleanup cannot itself traverse
    # this adversarial depth.  The platform finder removes only the exact
    # synthetic hostile subtree after the assertion has completed.
    removed = path.subprocess.run(
        [
            "/usr/bin/find",
            str(runtime.storage.package_directory / "hostile-depth"),
            "-depth",
            "-delete",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert removed.returncode == 0, removed.stderr


@pytest.mark.parametrize("role", ["primary", "secondary"])
def test_nested_unbound_entry_is_sealed_then_rejected_by_exact_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_383_250_000
    seed = f"F017-S39-UNBOUND-{role.upper()}".encode("ascii")
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._StorageBinding._seal_held_directory_tree
    inserted = False

    def insert_then_seal(directory_fd: int) -> None:
        nonlocal inserted
        if not inserted and f"{role}-full_logits.bin" in os.listdir(directory_fd):
            descriptor = os.open(
                "uncommitted-extra-leaf.bin",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
            try:
                os.write(descriptor, b"UNBOUND")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            inserted = True
        original(directory_fd)

    monkeypatch.setattr(
        path._StorageBinding,
        "_seal_held_directory_tree",
        staticmethod(insert_then_seal),
    )
    with pytest.raises(ValueError, match="directory entry census"):
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert inserted is True
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal["state"] == "TERMINAL_FAILURE"
    assert terminal["failed_stage"] == "RELEASE_TERMINAL"
    assert terminal["result"] == "FAIL"


def test_result_writer_seals_before_tree_sealer_can_retain_write_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_383_375_000
    seed = b"F017-S39-WRITER-SEALS-BEFORE-TREE-SEAL"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._StorageBinding._seal_held_directory_tree
    open_rejected = False

    def attempt_retain_then_seal(directory_fd: int) -> None:
        nonlocal open_rejected
        if "primary-full_logits.bin" in os.listdir(directory_fd):
            try:
                retained = os.open(
                    "primary-full_logits.bin",
                    os.O_RDWR | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
            except OSError:
                open_rejected = True
            else:
                os.close(retained)
        original(directory_fd)

    monkeypatch.setattr(
        path._StorageBinding,
        "_seal_held_directory_tree",
        staticmethod(attempt_retain_then_seal),
    )
    result = path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert result["result"] == "PASS"
    assert open_rejected is True


def test_unbound_fifo_fails_closed_without_blocking_terminalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_383_500_000
    seed = b"F017-S39-UNBOUND-FIFO"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._gate_m004_stop_boundary

    def insert_fifo(stop: object, stage: str, observed_runtime: object) -> None:
        original(stop, stage, observed_runtime)
        if stage == "PACKAGE_TERMINAL":
            os.mkfifo(runtime.storage.package_directory / "unbound-fifo")

    monkeypatch.setattr(path, "_gate_m004_stop_boundary", insert_fifo)
    with pytest.raises(ValueError, match="package success root entry census"):
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal["state"] == "TERMINAL_FAILURE"
    assert terminal["failed_stage"] == "RELEASE_TERMINAL"
    assert terminal["result"] == "FAIL"


def test_package_start_reservation_rejects_exact_success_terminal_injection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_384_000_000
    seed = b"F017-S39-RESERVED-TERMINAL-EXACT-INJECTION"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._StorageBinding._commit_reserved_success_terminal
    collision_rejected = False
    content_rejected = False

    def attempt_exact_terminal_then_commit(
        storage: object,
        descriptor: int,
        value: object,
        stop: object,
        expected_sha256: str,
    ) -> None:
        nonlocal collision_rejected, content_rejected
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        try:
            competing = os.open(
                "package-terminal.json",
                flags,
                0o400,
                dir_fd=storage._package_fd,
            )
        except FileExistsError:
            collision_rejected = True
        else:
            os.close(competing)
        terminal = storage.package_directory / "package-terminal.json"
        try:
            terminal.write_bytes(path._canonical_bytes(dict(value)))
        except OSError:
            content_rejected = True
        original(storage, descriptor, value, stop, expected_sha256)

    monkeypatch.setattr(
        path._StorageBinding,
        "_commit_reserved_success_terminal",
        attempt_exact_terminal_then_commit,
    )
    result = path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert result["result"] == "PASS"
    assert collision_rejected is True
    assert content_rejected is True


def test_success_terminal_closes_held_writer_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_384_250_000
    seed = b"F017-S39-SUCCESS-TERMINAL-WRITER-CLOSED"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._StorageBinding._commit_reserved_success_terminal
    writer_rejected = False

    def commit_then_attempt_writer(
        storage: object,
        descriptor: int,
        value: object,
        stop: object,
        expected_sha256: str,
    ) -> None:
        nonlocal writer_rejected
        original(storage, descriptor, value, stop, expected_sha256)
        try:
            os.write(descriptor, b" ")
        except OSError:
            writer_rejected = True

    monkeypatch.setattr(
        path._StorageBinding,
        "_commit_reserved_success_terminal",
        commit_then_attempt_writer,
    )
    result = path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert result["result"] == "PASS"
    assert writer_rejected is True
    terminal_raw = (
        runtime.storage.package_directory / "package-terminal.json"
    ).read_bytes()
    assert path._sha(terminal_raw) == result["package_terminal_sha256"]


def test_failure_terminal_closes_held_writer_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_384_500_000
    seed = b"F017-S39-FAILURE-TERMINAL-WRITER-CLOSED"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
        fault_stage="PRIMARY_RESULT_TERMINAL",
    )
    original = path._StorageBinding._bank_failure_terminal
    writer_rejected = False

    def bank_then_attempt_writer(storage: object, value: object) -> None:
        nonlocal writer_rejected
        descriptor = storage._terminal_fd
        original(storage, value)
        try:
            os.write(descriptor, b" ")
        except OSError:
            writer_rejected = True

    monkeypatch.setattr(
        path._StorageBinding,
        "_bank_failure_terminal",
        bank_then_attempt_writer,
    )
    with pytest.raises(RuntimeError, match="INJECTED_STOP"):
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert writer_rejected is True
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal["state"] == "TERMINAL_FAILURE"


def test_success_atomic_publish_then_diagnostic_error_preserves_committed_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_384_625_000
    seed = b"F017-S39-SUCCESS-DOWNGRADE-DIAGNOSTIC"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._StorageBinding._publish_reserved_terminal_atomically
    observed = False

    def publish_then_raise(
        storage: object,
        descriptor: int,
        raw_terminal: bytes,
        stop: object,
    ) -> None:
        nonlocal observed
        original(storage, descriptor, raw_terminal, stop)
        assert storage._terminal_writer_retired is True
        observed = True
        raise OSError("post-publication success diagnostic")

    monkeypatch.setattr(
        path._StorageBinding,
        "_publish_reserved_terminal_atomically",
        publish_then_raise,
    )
    result = path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert observed is True
    assert result["result"] == "PASS"
    terminal_raw = (
        runtime.storage.package_directory / "package-terminal.json"
    ).read_bytes()
    terminal = path._parse_artifact_bytes(terminal_raw)
    assert terminal["outcome"] == "COMPLETE_SUCCESS"
    assert path._sha(terminal_raw) == result["package_terminal_sha256"]


def test_failure_atomic_publish_then_diagnostic_error_preserves_original_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_384_750_000
    seed = b"F017-S39-FAILURE-DOWNGRADE-DIAGNOSTIC"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
        fault_stage="PRIMARY_RESULT_TERMINAL",
    )
    original = path._StorageBinding._publish_reserved_terminal_atomically
    observed = False

    def publish_then_raise(
        storage: object,
        descriptor: int,
        raw_terminal: bytes,
        stop: object,
    ) -> None:
        nonlocal observed
        original(storage, descriptor, raw_terminal, stop)
        assert storage._terminal_writer_retired is True
        observed = True
        raise OSError("post-publication failure diagnostic")

    monkeypatch.setattr(
        path._StorageBinding,
        "_publish_reserved_terminal_atomically",
        publish_then_raise,
    )
    with pytest.raises(RuntimeError, match="INJECTED_STOP"):
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert observed is True
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal["state"] == "TERMINAL_FAILURE"
    assert terminal["failed_stage"] == "IDENTITY_TERMINAL"
    assert terminal["failure_type"] == "RuntimeError"


@pytest.mark.parametrize(
    ("fault_stage", "expected_state"),
    (
        (None, "COMPLETE_SUCCESS"),
        ("PRIMARY_RESULT_TERMINAL", "TERMINAL_FAILURE"),
    ),
)
def test_terminal_reservation_close_after_kernel_success_is_not_reclassified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault_stage: str | None,
    expected_state: str,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_384_875_000
    seed = f"F017-S39-CLOSE-AFTER-SUCCESS-{expected_state}".encode("ascii")
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
        fault_stage=fault_stage,
    )
    original_close = path.os.close
    injected = False

    def close_then_report_error(descriptor: int) -> None:
        nonlocal injected
        if (
            not injected
            and descriptor == runtime.storage._terminal_fd
        ):
            injected = True
            original_close(descriptor)
            raise OSError("terminal writer close diagnostic")
        original_close(descriptor)

    monkeypatch.setattr(path.os, "close", close_then_report_error)
    if fault_stage is None:
        result = path._invoke_public_qualification(raw, runtime, now_unix_ns=now)
        assert result["result"] == "PASS"
    else:
        with pytest.raises(RuntimeError, match="INJECTED_STOP"):
            path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert injected is True
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal.get("outcome", terminal.get("state")) == expected_state


def test_failure_terminal_seals_retained_predecessor_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_385_000_000
    seed = b"F017-S39-FAILURE-TERMINAL-RETAINED-DESCRIPTOR"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
        fault_stage="PRIMARY_RESULT_TERMINAL",
    )
    original = path._StorageBinding._bank_failure_terminal
    mutation_rejected = False

    def retain_descriptor_then_bank(storage: object, value: object) -> None:
        nonlocal mutation_rejected
        flags = os.O_RDWR | os.O_NOFOLLOW
        try:
            retained = os.open(
                "failure-accounting.json", flags, dir_fd=storage._package_fd
            )
        except OSError:
            mutation_rejected = True
            original(storage, value)
            return
        try:
            original(storage, value)
            try:
                os.lseek(retained, 0, os.SEEK_END)
                os.write(retained, b" ")
                os.fsync(retained)
            except OSError:
                mutation_rejected = True
        finally:
            os.close(retained)

    monkeypatch.setattr(
        path._StorageBinding,
        "_bank_failure_terminal",
        retain_descriptor_then_bank,
    )
    with pytest.raises(RuntimeError, match="INJECTED_STOP"):
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert mutation_rejected is True
    package = runtime.storage.package_directory
    terminal = path._parse_artifact_bytes(
        (package / "package-terminal.json").read_bytes()
    )
    accounting_raw = (package / "failure-accounting.json").read_bytes()
    assert terminal["failure_accounting_sha256"] == path._sha(accounting_raw)
    assert terminal["state"] == "TERMINAL_FAILURE"


def test_partial_success_terminal_write_rolls_back_to_truthful_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_386_000_000
    seed = b"F017-S39-PARTIAL-SUCCESS-TERMINAL-WRITE"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original_open = path.os.open
    original_write = path.os.write
    injected = False
    staged_terminal_descriptor: int | None = None

    def capture_staged_terminal(
        target: object, flags: int, *args: object, **kwargs: object
    ) -> int:
        nonlocal staged_terminal_descriptor
        descriptor = original_open(target, flags, *args, **kwargs)
        if (
            isinstance(target, str)
            and target.startswith(
                f".{runtime.storage.package_directory.name}.terminal-stage-"
            )
        ):
            staged_terminal_descriptor = descriptor
        return descriptor

    def partial_then_fail(descriptor: int, value: object) -> int:
        nonlocal injected
        if descriptor == staged_terminal_descriptor and not injected:
            injected = True
            original_write(descriptor, bytes(value)[:7])
            raise OSError("injected partial success terminal write")
        return original_write(descriptor, value)

    monkeypatch.setattr(path.os, "open", capture_staged_terminal)
    monkeypatch.setattr(path.os, "write", partial_then_fail)
    with pytest.raises(OSError, match="injected partial"):
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert injected is True
    terminal_raw = (
        runtime.storage.package_directory / "package-terminal.json"
    ).read_bytes()
    assert not terminal_raw.startswith(b"\x00")
    terminal = path._parse_artifact_bytes(terminal_raw)
    assert terminal["state"] == "TERMINAL_FAILURE"
    assert terminal["failed_stage"] == "RELEASE_TERMINAL"
    assert terminal["result"] == "FAIL"


def test_package_path_retarget_preserves_original_failure_and_terminalizes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_386_500_000
    seed = b"F017-S39-PACKAGE-PATH-RETARGET-TERMINAL"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
    )
    original = path._gate_m004_stop_boundary
    canonical = runtime.storage.package_directory
    displaced = canonical.with_name(canonical.name + "-displaced")

    def retarget_before_terminal(
        stop: object, stage: str, observed_runtime: object
    ) -> None:
        original(stop, stage, observed_runtime)
        if stage == "PACKAGE_TERMINAL":
            canonical.rename(displaced)
            canonical.mkdir()

    monkeypatch.setattr(path, "_gate_m004_stop_boundary", retarget_before_terminal)
    with pytest.raises(
        RuntimeError, match="canonical package directory identity changed"
    ):
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    terminal = path._parse_artifact_bytes(
        (displaced / "package-terminal.json").read_bytes()
    )
    assert terminal["state"] == "TERMINAL_FAILURE"
    assert terminal["failed_stage"] == "RELEASE_TERMINAL"
    assert terminal["failure_type"] == "RuntimeError"
    assert terminal["result"] == "FAIL"


def test_post_release_failure_accounts_for_actual_completed_release(
    tmp_path: Path,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_386_750_000
    seed = b"F017-S39-POST-RELEASE-FAILURE-ACCOUNTING"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path,
        path._sha(seed),
        intercept=False,
        fault_stage="PACKAGE_TERMINAL",
    )
    with pytest.raises(RuntimeError, match="INJECTED_STOP_AT_PACKAGE_TERMINAL"):
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    package = runtime.storage.package_directory
    accounting = path._parse_artifact_bytes(
        (package / "failure-accounting.json").read_bytes()
    )
    release = accounting["emergency_release_outcome"]
    assert release["attempted_closures"] == 5
    assert release["successful_closures"] == 5
    assert release["live_leases_after_release"] == 0
    assert release["result"] == "PASS"
    assert release["release_disposition"] == "ALREADY_RELEASED"
    terminal = path._parse_artifact_bytes(
        (package / "package-terminal.json").read_bytes()
    )
    assert terminal["emergency_release_result"] == "PASS"
    assert terminal["emergency_release_disposition"] == "ALREADY_RELEASED"


def test_synthetic_public_path_uses_physical_v12_checkpoint_and_closes_real_fds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_386_875_000
    seed = b"F017-S41-PHYSICAL-SYNTHETIC-IDENTITY"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path, path._sha(seed), intercept=False
    )
    original = path._run_identity_stage
    observed: dict[str, object] = {"calls": 0}

    def observe_physical_identity(
        authority: object,
        *,
        package_attempt_id: str,
        package_durable_start: bool,
        evidence_directory: Path | None = None,
    ) -> tuple[object, dict[str, object]]:
        observed["calls"] = int(observed["calls"]) + 1
        checkpoint_root = Path(str(authority.get("checkpoint_root")))
        observed["checkpoint_root"] = checkpoint_root
        leases, report = original(
            authority,
            package_attempt_id=package_attempt_id,
            package_durable_start=package_durable_start,
            evidence_directory=evidence_directory,
        )
        observed["leases"] = leases
        observed["descriptors"] = tuple(leases.inherited_fds())
        observed["report"] = dict(report)
        assert evidence_directory is not None
        observed["evidence_leaves"] = set(os.listdir(evidence_directory))
        return leases, report

    monkeypatch.setattr(path, "_run_identity_stage", observe_physical_identity)
    result = path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert result["result"] == "PASS"
    assert observed["calls"] == 1
    checkpoint_root = observed["checkpoint_root"]
    assert isinstance(checkpoint_root, Path)
    assert checkpoint_root.resolve(strict=True).is_relative_to(tmp_path.resolve(strict=True))
    assert checkpoint_root != path._LIVE_CHECKPOINT_ROOT
    expected_checkpoint_leaves = {
        *(str(item["filename"]) for item in profile.shards),
        *path._SYNTHETIC_CHECKPOINT_BENIGN_EXTRA_LEAVES,
    }
    assert set(os.listdir(checkpoint_root)) == expected_checkpoint_leaves
    assert observed["evidence_leaves"] == set(path._SUCCESS_PHYSICAL_IDENTITY_FILES)
    report = observed["report"]
    assert isinstance(report, dict)
    assert report["operation_class"] == "CHECKPOINT_IDENTITY_QUALIFICATION"
    assert report["checkpoint_shard_opens"] == 6
    assert report["checkpoint_identity_hash_reads"] == 6
    leases = observed["leases"]
    assert leases.closed is True
    for descriptor in observed["descriptors"]:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_malformed_post_producer_counter_releases_physical_leases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_386_900_000
    seed = b"F017-S41-MALFORMED-PRODUCER-COUNTER"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path, path._sha(seed), intercept=False
    )
    original = path._ProductionCheckpointEffect.run
    observed: dict[str, object] = {}

    def corrupt_counter(
        effect: object,
        consumed_gate: object,
        authority: object,
        storage: object,
    ) -> object:
        outcome = original(effect, consumed_gate, authority, storage)
        observed["leases"] = outcome.leases
        observed["descriptors"] = tuple(outcome.leases.inherited_fds())
        malformed = dict(outcome.report)
        malformed["checkpoint_shard_opens"] = "6"
        return path._IdentityOutcome(
            outcome.authority,
            outcome.leases,
            malformed,
            outcome.read_receipts,
            outcome.identity_receipt_sha256,
            outcome.identity_terminal_sha256,
            outcome.access_census_sha256,
        )

    monkeypatch.setattr(path._ProductionCheckpointEffect, "run", corrupt_counter)
    with pytest.raises(
        path._IdentityHandoffFailure,
        match="checkpoint identity evidence handoff failed",
    ) as captured:
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    leases = observed["leases"]
    assert leases.closed is True
    for descriptor in observed["descriptors"]:
        with pytest.raises(OSError):
            os.fstat(descriptor)
    assert captured.value.cause_type == "TypeError"
    assert captured.value.release_outcome["attempted_closures"] == 5
    assert captured.value.release_outcome["successful_closures"] == 5
    assert captured.value.release_outcome["live_leases_after_release"] == 0
    package = runtime.storage.package_directory
    release = path._parse_artifact_bytes(
        (package / "emergency-release-report.json").read_bytes()
    )
    accounting = path._parse_artifact_bytes(
        (package / "failure-accounting.json").read_bytes()
    )
    terminal = path._parse_artifact_bytes(
        (package / "package-terminal.json").read_bytes()
    )
    assert release["attempted_closures"] == 5
    assert release["successful_closures"] == 5
    assert release["live_leases"] == 0
    assert release["result"] == "PASS"
    assert accounting["emergency_release_outcome"]["result"] == "PASS"
    assert terminal["failure_wrapper_type"] == "_IdentityHandoffFailure"
    assert terminal["emergency_release_result"] == "PASS"


def test_malformed_counter_release_exception_is_not_hidden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_386_925_000
    seed = b"F017-S41-MALFORMED-COUNTER-RELEASE-EXCEPTION"
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path, path._sha(seed), intercept=False
    )
    original_run = path._ProductionCheckpointEffect.run
    original_release = path._LeaseSet.release

    def corrupt_counter(
        effect: object,
        consumed_gate: object,
        authority: object,
        storage: object,
    ) -> object:
        outcome = original_run(effect, consumed_gate, authority, storage)
        malformed = dict(outcome.report)
        malformed["checkpoint_identity_hash_reads"] = "6"
        return path._IdentityOutcome(
            outcome.authority,
            outcome.leases,
            malformed,
            outcome.read_receipts,
            outcome.identity_receipt_sha256,
            outcome.identity_terminal_sha256,
            outcome.access_census_sha256,
        )

    def release_then_raise(leases: object) -> object:
        original_release(leases)
        raise OSError("injected release completion exception")

    monkeypatch.setattr(path._ProductionCheckpointEffect, "run", corrupt_counter)
    monkeypatch.setattr(path._LeaseSet, "release", release_then_raise)
    with pytest.raises(path._IdentityHandoffFailure) as captured:
        path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    assert captured.value.cause_type == "TypeError"
    assert captured.value.release_evidence_error_type == "OSError"
    assert captured.value.release_outcome["result"] == "RELEASE_EXCEPTION"
    assert captured.value.release_outcome["successful_closures"] == 5
    assert captured.value.release_outcome["live_leases_after_release"] == 0
    package = runtime.storage.package_directory
    terminal = path._parse_artifact_bytes(
        (package / "package-terminal.json").read_bytes()
    )
    accounting = path._parse_artifact_bytes(
        (package / "failure-accounting.json").read_bytes()
    )
    assert terminal["emergency_release_result"] == "RELEASE_EXCEPTION"
    assert accounting["emergency_release_outcome"]["successful_closures"] == 5
    assert accounting["emergency_release_outcome"]["live_leases_after_release"] == 0


def test_release_authority_is_production_complete_and_scope_separated() -> None:
    synthetic = path._authority_profile(synthetic=True)
    production = path._authority_profile(synthetic=False)
    closure = synthetic.release_authority["runtime_source_closure"]
    closure_paths = {item["path"] for item in closure}
    required = {
        "scripts/research/f017_event06_minimum_gate_path_v1.py",
        "scripts/research/f017_checkpoint_identity_authority_v12.py",
        "scripts/research/f017_checkpoint_identity_producer_v12.py",
        "scripts/research/f017_descriptor_lease_manager_v10.py",
        "scripts/research/f017_bounded_artifact_decode_v1.py",
        "scripts/research/f017_canonical_serialization_v10.py",
        "scripts/research/f017_corrected_oracle_primary_wrapper_v11.py",
        "scripts/research/f017_corrected_oracle_primary_target_source_v11.py",
        "scripts/research/f017_corrected_oracle_secondary_wrapper_v11.py",
        "scripts/research/f017_corrected_oracle_secondary_target_source_v11.py",
        "scripts/research/f017_result_artifacts_v11.py",
        "scripts/research/f017_result_envelope_v11.py",
        "scripts/research/f017_result_bundle_builder_v11.py",
        "scripts/research/f017_binary_comparison_authority_v11.py",
    }
    assert required <= closure_paths
    assert "scripts/research/f017_v11_full_geometry_fixture.py" not in closure_paths
    assert synthetic.release_authority["authority_scope"] == "SYNTHETIC"
    assert production.release_authority["authority_scope"] == "PRODUCTION"
    assert synthetic.release_authority_sha256 != production.release_authority_sha256
    assert synthetic.release_authority[
        "runtime_source_closure_sha256"
    ] == path._contract_sha256(closure)
    assert production.release_authority[
        "sequence39_prompt_path"
    ] == path._SEQUENCE39_PROMPT_PATH


def test_synthetic_qualification_go_cannot_cross_the_production_boundary() -> None:
    synthetic = path._authority_profile(synthetic=True)
    production = path._authority_profile(synthetic=False)
    now = 39_200_000_000
    raw = path._qualification_go(
        synthetic, b"F017-S39-SCOPE-SEPARATION", now_unix_ns=now
    )
    with pytest.raises(ValueError, match="collapsed GO release authority"):
        path._gate_m003_fail_closed_preflight(
            raw, production, now_unix_ns=now
        )


def test_production_preflight_rejects_a_wrong_observed_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    production = path._authority_profile(synthetic=False)
    now = 39_250_000_000
    raw = path._qualification_go(
        production, b"F017-S39-WRONG-HOST", now_unix_ns=now
    )
    monkeypatch.setattr(
        path,
        "_observe_target_machine",
        lambda: {
            "target_machine": "ANOTHER_HOST",
            "brand": "Apple M2 Max",
            "architecture": "arm64",
        },
    )
    with pytest.raises(ValueError, match="target-machine resource binding"):
        path._gate_m003_fail_closed_preflight(
            raw, production, now_unix_ns=now
        )


def test_target_machine_observation_matches_mac_studio_m1_ultra() -> None:
    assert dict(path._observe_target_machine()) == {
        "target_machine": "MAC_STUDIO_M1_ULTRA",
        "brand": "Apple M1 Ultra",
        "architecture": "arm64",
    }


def test_minimum_identity_authority_rejects_removed_plan_alias(
    tmp_path: Path,
) -> None:
    profile = path._authority_profile(synthetic=True)
    seed = b"F017-S39-IDENTITY-PLAN-SUBSTITUTION"
    now = 39_100_000_000
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    go = path._gate_m003_fail_closed_preflight(
        raw, profile, now_unix_ns=now
    )
    runtime = path._qualification_runtime(
        tmp_path, path._sha(seed), intercept=False
    )
    installed = path._build_installed_authority(go, runtime)
    mutated = installed.as_dict()
    mutated["event_identity_plan_sha256"] = "f" * 64
    with pytest.raises(Exception, match="minimum installed authority key census"):
        path._validate_installed_bytes(path._canonical_bytes(mutated))


def test_consumed_gate_rejects_a_substituted_installed_authority(
    tmp_path: Path,
) -> None:
    profile = path._authority_profile(synthetic=True)
    seed = b"F017-S39-INSTALLED-AUTHORITY-SUBSTITUTION"
    now = 39_300_000_000
    raw = path._qualification_go(profile, seed, now_unix_ns=now)
    go = path._gate_m003_fail_closed_preflight(
        raw, profile, now_unix_ns=now
    )
    runtime = path._qualification_runtime(
        tmp_path, path._sha(seed), intercept=False
    )
    installed = path._build_installed_authority(go, runtime)
    consumed = path._consume_package_start_gate(
        path._package_gate(go, installed, runtime)
    )
    alternate_root = tmp_path / "alternate-checkpoint"
    alternate_root.mkdir()
    mutated = installed.as_dict()
    mutated["checkpoint_root"] = str(alternate_root)
    substituted = path._validate_installed_bytes(path._canonical_bytes(mutated))
    assert substituted.source_sha256 != installed.source_sha256
    with pytest.raises(TypeError, match="exact consumed package-start gate"):
        path._require_consumed_gate(consumed, substituted)


def test_all_retained_gate_mutations_fail_closed(
    qualification: dict[str, object],
) -> None:
    mutations = qualification["retained_gate_mutations"]
    assert isinstance(mutations, dict)
    assert mutations["passed"] == mutations["total"] == 17
    assert mutations["unexpected_passes"] == 0
    assert all(
        item["rejected"] is True and item["protected_effect_reached"] is False
        for item in mutations["cases"]
    )


def test_optional_diagnostics_are_independently_and_jointly_non_gating(
    qualification: dict[str, object],
) -> None:
    omission = qualification["optional_diagnostic_omission"]
    assert isinstance(omission, dict)
    assert omission["independent_cases"] == 5
    assert omission["combined_cases"] == 1
    assert all(item["result"] == "PASS" for item in omission["cases"])


def test_one_shot_contention_and_terminal_have_one_winner(
    qualification: dict[str, object],
) -> None:
    one_shot = qualification["one_shot_contention"]
    assert isinstance(one_shot, dict)
    assert one_shot["contenders"] == 2
    assert one_shot["independent_contender_runtimes"] == 2
    assert one_shot["shared_process_local_one_shot_state"] is False
    assert (
        one_shot["winner_selected_by"]
        == "O_EXCL_PACKAGE_TERMINAL_RESERVATION"
    )
    assert one_shot["winners"] == 1
    assert one_shot["losers_before_package_start"] == 1
    assert one_shot["loser_error_type"] == "FileExistsError"
    assert one_shot["loser_checkpoint_root_resolutions"] == 0
    assert one_shot["loser_checkpoint_opens"] == 0
    assert one_shot["loser_physical_identity_producer_calls"] == 0
    assert one_shot["replay_physical_identity_producer_calls"] == 0
    assert one_shot["loser_numerical_operations"] == 0
    assert one_shot["terminal_winners_per_package"] == 1
    assert one_shot["second_attempt_rejected"] is True
    assert one_shot["second_attempt_uses_third_fresh_runtime"] is True
    assert one_shot["second_attempt_uses_distinct_canonical_go_bytes"] is True
    assert one_shot["second_attempt_preserves_human_decision_sha256"] is True
    assert one_shot["first_go_sha256"] != one_shot["replay_go_sha256"]
    assert one_shot["second_attempt_error_type"] == "FileExistsError"
    assert one_shot["second_attempts_reaching_package_start"] == 0
    assert one_shot["competing_terminal_rejected"] is True


def test_every_retained_stage_stops_with_truthful_prefix(
    qualification: dict[str, object],
) -> None:
    failures = qualification["retained_stage_failures"]
    assert isinstance(failures, dict)
    assert failures["passed"] == failures["total"] == 11
    assert all(item["fabricated_successor_receipts"] == 0 for item in failures["cases"])
    assert {
        item["stage"]: item["furthest_durable_stage"]
        for item in failures["cases"]
    } == {
        "PREPARED": None,
        "INSTALLED": None,
        "PACKAGE_START_ELIGIBLE_DRY_STOP": None,
        "PACKAGE_START": None,
        "IDENTITY_TERMINAL": "PACKAGE_START",
        "PRIMARY_RESULT_TERMINAL": "IDENTITY_TERMINAL",
        "SECONDARY_RESULT_TERMINAL": "PRIMARY_RESULT_TERMINAL",
        "COMPARISON_TERMINAL": "SECONDARY_RESULT_TERMINAL",
        "RELEASE_TERMINAL": "COMPARISON_TERMINAL",
        "ACCOUNTING_CLOSURE": "RELEASE_TERMINAL",
        "PACKAGE_TERMINAL": "RELEASE_TERMINAL",
    }


def test_missing_required_public_paths_fail_before_shard_or_successor_effects(
    qualification: dict[str, object],
) -> None:
    rehearsals = qualification["missing_required_public_path_rehearsals"]
    assert rehearsals["result"] == "PASS"
    assert rehearsals["missing_required_shard_preopen_failures"] == "6/6"
    assert rehearsals["checkpoint_shard_opens"] == 0
    assert rehearsals["checkpoint_identity_hash_reads"] == 0
    assert rehearsals["successor_effects"] == "0/0/0/0"
    assert rehearsals["terminal_failures_banked"] == 6
    assert [item["missing_ordinal"] for item in rehearsals["cases"]] == list(
        range(1, 7)
    )
    assert all(item["result"] == "PASS" for item in rehearsals["cases"])


def test_full_public_path_uses_bounded_physical_synthetic_identity(
    qualification: dict[str, object],
) -> None:
    assert qualification["root_census_policy"] == "REQUIRED_SUBSET_EXTRAS_IGNORED"
    assert qualification["required_shard_names"] == 6
    assert qualification["required_shards_present_with_extra_leaves"] == "PASS"
    assert qualification["exact_required_shard_open_names"] == "6/6"
    assert qualification["full_call_path_dry_run_with_synthetic_authority"] == "PASS"
    trace = qualification["production_component_trace"]
    component_count = trace["production_component_count"]
    assert component_count == len(trace["production_components_exercised"])
    assert component_count > 17
    expected_count = trace["source_derived_expected_component_count"]
    exercised_count = trace["source_derived_exercised_component_count"]
    assert expected_count == len(
        trace["source_derived_expectation"]["expected_components"]
    )
    assert exercised_count == len(trace["source_derived_exercised_components"])
    assert trace["source_derived_missing_component_count"] == 0
    assert trace["source_derived_missing_components"] == []
    assert trace["source_derived_unexpected_component_count"] == 0
    assert trace["source_derived_unexpected_components"] == []
    expectation = trace["source_derived_expectation"]
    assert expectation["composition_derivation"] == (
        "DIRECT_IMPORT_CALLS_PLUS_IMPORTED_FUNCTION_LOCAL_CALL_GRAPH"
    )
    transitive_boundaries = {
        "f017_event06_minimum_gate_contract_v1._validate_accounting_document",
        "f017_event06_minimum_gate_contract_v1._validate_identity_read_receipts",
        "f017_event06_minimum_gate_contract_v1._validate_package_terminal_document",
    }
    assert set(expectation["transitive_external_boundary_names"]) == (
        transitive_boundaries
    )
    assert expectation["transitive_external_boundary_count"] == len(
        transitive_boundaries
    )
    direct_boundaries = set(expectation["direct_external_boundary_names"])
    assert direct_boundaries.isdisjoint(transitive_boundaries)
    composition_edges = {
        (item["caller"], item["callee"])
        for item in expectation["source_derived_composition_edges"]
    }
    assert {
        (
            "f017_event06_minimum_gate_contract_v1._validate_accounting_closure",
            "f017_event06_minimum_gate_contract_v1._validate_accounting_document",
        ),
        (
            "f017_event06_minimum_gate_contract_v1._validate_accounting_document",
            "f017_event06_minimum_gate_contract_v1._validate_identity_read_receipts",
        ),
        (
            "f017_event06_minimum_gate_contract_v1._validate_package_terminal",
            "f017_event06_minimum_gate_contract_v1._validate_package_terminal_document",
        ),
    }.issubset(composition_edges)
    assert trace["source_derived_transitive_boundary_count"] == len(
        transitive_boundaries
    )
    assert set(trace["source_derived_transitive_boundaries_exercised"]) == (
        transitive_boundaries
    )
    assert trace["source_derived_transitive_boundaries_uncovered"] == []
    assert trace["source_derived_transitive_boundary_composition"] == "3/3"
    changed = qualification["source_derived_closure"][
        "changed_typed_boundary_census"
    ]
    expected_callables = {
        "f017_checkpoint_identity_lifecycle_v12.IdentityAccessCensus",
        "f017_checkpoint_identity_lifecycle_v12.IdentityAuthorityError",
        "f017_checkpoint_identity_lifecycle_v12.IdentityDescriptorDisposition",
        "f017_checkpoint_identity_lifecycle_v12.IdentityOperationObservation",
        "f017_checkpoint_identity_lifecycle_v12.failure",
        "f017_checkpoint_identity_lifecycle_v12.with_failure_context",
        (
            "f017_checkpoint_identity_producer_v12."
            "IdentityAccessPrefixValidationError"
        ),
        "f017_checkpoint_identity_producer_v12.identity_success_evidence_leaves",
        (
            "f017_checkpoint_identity_producer_v12."
            "missing_identity_access_prefix_census"
        ),
        (
            "f017_checkpoint_identity_producer_v12."
            "validate_banked_identity_access_prefix"
        ),
        (
            "f017_checkpoint_identity_producer_v12."
            "validate_banked_identity_evidence"
        ),
        (
            "f017_event06_minimum_gate_contract_v1."
            "_validate_accounting_closure"
        ),
        (
            "f017_event06_minimum_gate_contract_v1."
            "_validate_accounting_document"
        ),
        (
            "f017_event06_minimum_gate_contract_v1."
            "_validate_package_terminal"
        ),
        (
            "f017_event06_minimum_gate_contract_v1."
            "_validate_package_terminal_document"
        ),
        "f017_event06_minimum_gate_path_v1.execute_event06_minimum_gate_path",
        (
            "f017_event06_minimum_gate_path_v1."
            "closeout_interrupted_event06_minimum_gate_path"
        ),
    }
    expected_schemas = {
        "pulsarmlx.f017.checkpoint-identity-access-census/12.1.0",
        "pulsarmlx.f017.checkpoint-identity-access-journal/12.1.0",
        "pulsarmlx.f017.checkpoint-identity-access-prefix-genesis/12.1.0",
        "pulsarmlx.f017.checkpoint-identity-access-prefix-receipt/12.1.0",
        "pulsarmlx.f017.checkpoint-identity-core/12.1.0",
        "pulsarmlx.f017.checkpoint-identity-lease-manifest/12.1.0",
        "pulsarmlx.f017.checkpoint-identity-manifest/12.1.0",
        "pulsarmlx.f017.checkpoint-identity-receipt/12.1.0",
        "pulsarmlx.f017.checkpoint-identity-shard-receipts/12.1.0",
        "pulsarmlx.f017.checkpoint-identity-terminal/12.1.0",
        "pulsarmlx.f017.event06-minimum-gate-failure-accounting/1.1.0",
        "pulsarmlx.f017.event06-minimum-gate-package-terminal/1.1.0",
        "pulsarmlx.f017.event06-minimum-gate-stage-receipt/1.1.0",
    }
    callable_rows = changed["changed_callable_or_carrier_boundaries"]
    schema_rows = changed["version_forward_schema_boundaries"]
    assert {row["boundary"] for row in callable_rows} == expected_callables
    assert {row["boundary"] for row in schema_rows} == expected_schemas
    assert changed["changed_callable_or_carrier_boundary_count"] == 17
    assert changed["version_forward_schema_boundary_count"] == 13
    assert changed["changed_typed_boundaries_total"] == 30
    assert changed["changed_typed_boundaries_with_composition_tests"] == 30
    assert all(row["composition_tested"] is True for row in callable_rows)
    assert all(row["composition_tested"] is True for row in schema_rows)
    assert changed["uncovered_changed_boundary_count"] == 0
    assert changed["uncovered_changed_boundaries"] == []
    assert changed["extraneous_changed_boundary_count"] == 0
    assert changed["extraneous_changed_boundaries"] == []
    assert qualification["changed_typed_boundaries_total"] == 30
    assert qualification[
        "changed_typed_boundaries_with_composition_tests"
    ] == 30
    assert qualification["uncovered_or_extraneous_changed_boundaries"] == "0/0"
    assert trace["expected_denominator_independent_of_observed_profile"] is True
    assert qualification["production_path_components_exercised"] == (
        f"{exercised_count}/{expected_count}"
    )
    assert trace["actual_call_trace_not_handwritten_census"] is True
    exercised_components = set(trace["source_derived_exercised_components"])
    assert (
        "f017_checkpoint_identity_producer_v12._minimum_gate_produce"
        in exercised_components
    )
    assert (
        "f017_checkpoint_identity_producer_v12.validate_banked_identity_evidence"
        in exercised_components
    )
    assert trace["active_imported_producer_consumer_module_count"] == len(
        trace["active_imported_producer_consumer_modules"]
    )
    assert qualification["original_checkpoint_root_resolutions"] == 0
    assert (
        qualification["original_checkpoint_opens_hashes_payload_reads_mmaps"]
        == "0/0/0/0"
    )
    assert qualification["primary_secondary_real_executions"] == "0/0"
    assert qualification["full_model_inference"] == "NONE"
    assert qualification["real_registry_ledger_or_terminal_writes"] == 0
    assert (
        qualification[
            "physical_v12_identity_producer_on_graph_owned_synthetic_checkpoint"
        ]
        == "PASS"
    )
    assert qualification["physical_v12_identity_producer_calls"] == 1
    assert qualification["synthetic_checkpoint_binding_checks"] == 1
    assert (
        qualification[
            "synthetic_checkpoint_opens_identity_hash_reads_payload_bytes_mmaps"
        ]
        == "6/6/0/0"
    )
    assert qualification["graph_owned_synthetic_checkpoint_required_leaves"] == 6
    assert (
        qualification["graph_owned_synthetic_checkpoint_benign_extra_leaves"]
        == 1
    )
    assert qualification["graph_owned_fixture_leaf_creation_opens"] == 7
    assert qualification["graph_owned_fixture_benign_extra_creation_opens"] == 1
    assert (
        qualification["identity_producer_extra_leaf_open_follow_stat_hash"]
        == "0/0/0/0"
    )
    full_path = qualification["full_call_path"]
    assert full_path["physical_v12_identity_producer_calls"] == 1
    assert full_path["synthetic_checkpoint_binding_checks"] == 1
    assert full_path["synthetic_checkpoint_shard_opens"] == 6
    assert full_path["synthetic_checkpoint_identity_hash_reads"] == 6
    assert full_path["synthetic_checkpoint_payload_bytes_read"] == 0
    assert full_path["synthetic_checkpoint_mmaps"] == 0
    assert full_path["graph_owned_fixture_leaf_creation_opens"] == 7
    assert full_path["graph_owned_fixture_benign_extra_creation_opens"] == 1
    assert (
        full_path["identity_producer_extra_leaf_open_follow_stat_hash"]
        == "0/0/0/0"
    )
    assert qualification["historical_master_ledger"] == 175
    assert qualification["event06_executed"] is False
    assert (
        qualification["synthetic_decision_authority_source"]
        == "GRAPH_OWNED_TEMPORARY_BYTES"
    )
    assert qualification["synthetic_decision_count"] > 0
    assert qualification["synthetic_decision_digest_equals_consumed_go"] is False
    assert qualification["synthetic_authority_production_consumable"] is False
    assert qualification["synthetic_scope_boundary"]["result"] == "PASS"
    assert (
        qualification["synthetic_scope_boundary"][
            "checkpoint_set_sha256_unequal"
        ]
        is True
    )
    assert (
        qualification["synthetic_scope_boundary"][
            "all_shard_size_digest_pairs_unequal"
        ]
        is True
    )
    assert (
        qualification["synthetic_scope_boundary"][
            "protected_production_effects"
        ]
        == 0
    )
    assert qualification["result"] == "PASS"

    synthetic = qualification["synthetic_identity_accounting"]
    expected_instantiated = sum(
        item["instantiated"] for item in synthetic["sources"].values()
    )
    expected_consumed = sum(
        item["consumed"] for item in synthetic["sources"].values()
    )
    assert synthetic["instantiated"] == expected_instantiated
    assert synthetic["consumed"] == expected_consumed
    assert synthetic["instantiated"] >= synthetic["consumed"] > 0
    assert synthetic["all_consumptions_receipt_bound"] is True
    assert qualification["synthetic_identities_instantiated_or_consumed"] == (
        f"{expected_instantiated}/{expected_consumed}"
    )


def test_exact_foreign_start_race_is_never_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_386_999_100
    raw = path._qualification_go(
        profile, b"F017-S42-FOREIGN-START-RACE", now_unix_ns=now
    )
    go = path._validate_go_bytes(raw, profile, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path, str(go.get("human_decision_sha256")), intercept=False
    )
    runtime.storage.prepare()
    expected = path._derive_expected_package_start_receipt(go, runtime)
    expected_raw = path._canonical_bytes(expected)
    stop = path._StopBoundary(runtime.storage)
    original = path._StorageBinding._bank_leaf
    inserted = False

    def insert_foreign_exact_start(storage, leaf, value, **kwargs):
        nonlocal inserted
        if leaf == "package-start.json" and not inserted:
            inserted = True
            descriptor = os.open(
                leaf,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=storage._package_fd,
            )
            try:
                assert os.write(descriptor, expected_raw) == len(expected_raw)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.fsync(storage._package_fd)
        return original(storage, leaf, value, **kwargs)

    monkeypatch.setattr(path._StorageBinding, "_bank_leaf", insert_foreign_exact_start)
    with pytest.raises(FileExistsError):
        runtime.storage.bank_package_start(expected, stop)
    assert inserted is True
    assert stop.package_started is False
    assert all(kind != "PACKAGE_START" for kind, _digest in stop.receipts)
    assert stop.expected_package_start_raw is None
    assert runtime.storage._owned_package_start_identity is None
    # The foreign exact start is not adopted into the in-memory stop boundary,
    # but its appearance after reservation makes reservation deletion unsafe.
    # Retain the exact empty immutable terminal so a fresh observer sees a
    # terminal-bearing durable prefix instead of a stranded start marker.
    terminal_path = runtime.storage.package_directory / "package-terminal.json"
    assert terminal_path.is_file()
    terminal_descriptor = os.open(terminal_path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        terminal_stat = os.fstat(terminal_descriptor)
        assert terminal_stat.st_size == 0
        assert terminal_stat.st_nlink == 1
        assert terminal_stat.st_uid == os.getuid()
        assert terminal_stat.st_flags & path.stat.UF_IMMUTABLE
    finally:
        os.close(terminal_descriptor)
    assert runtime.storage._terminal_claim_held is True
    assert (
        runtime.storage.package_directory / "package-start.json"
    ).read_bytes() == expected_raw
    assert runtime.observed_effects["checkpoint_opens"] == 0
    assert runtime.observed_effects["numerical_executions"] == 0
    runtime.storage.close()


def test_restart_start_derivation_uses_only_the_frozen_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = path._authority_profile(synthetic=True)
    now = 39_386_999_200
    raw = path._qualification_go(
        profile, b"F017-S42-PURE-RESTART-DERIVATION", now_unix_ns=now
    )
    go = path._validate_go_bytes(raw, profile, now_unix_ns=now)
    runtime = path._qualification_runtime(
        tmp_path, str(go.get("human_decision_sha256")), intercept=False
    )

    def unexpected_source_read(_relative: str) -> str:
        raise AssertionError("restart derivation reread mutable source")

    monkeypatch.setattr(path, "_file_sha", unexpected_source_read)
    expected = path._derive_expected_package_start_receipt(go, runtime)
    assert expected["package_attempt_id"] == path._identities(go)[
        "package_attempt_id"
    ]
    assert expected["result"] == "PASS"
    assert not runtime.storage.package_directory.exists()
    assert runtime.observed_effects["checkpoint_opens"] == 0
    assert runtime.observed_effects["numerical_executions"] == 0
