from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))


def module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path); value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


executor = module("s1_executor", "scripts/research/f017_representative_s1_materialization_executor_v1.py")
wrapper = module("s1_wrapper", "scripts/research/f017_representative_s1_materialization_release_wrapper_v1.py")
wrapper_v2 = module("s1_wrapper_v2", "scripts/research/f017_representative_s1_materialization_release_wrapper_v2.py")
validator = module("s1_validator", "scripts/research/validate_f017_representative_s1_materialization_release_v1.py")


def test_same_oracle_local_is_captured_without_router_or_ffn():
    original = executor.oracle.compose_oracle
    def fake(hidden, vector, matvec, head_matvec):
        attention_output = np.ones(6144, dtype=np.float32)
        attention_residual = np.add(hidden, attention_output, dtype=np.float32)
        raise AssertionError("capture must stop before downstream work")
    executor.oracle.compose_oracle = fake
    try:
        hidden = np.zeros(6144, dtype=np.float32)
        observed = executor._capture_s1(lambda: executor.oracle.compose_oracle(hidden, None, None, None))
        assert observed.dtype == np.float32 and observed.shape == (6144,)
        assert np.all(observed == np.float32(1))
    finally:
        executor.oracle.compose_oracle = original


def test_descriptor_relative_no_replace_publication():
    with tempfile.TemporaryDirectory() as name:
        root = Path(name); os.chmod(root, 0o700); fd = wrapper.open_dir(root)
        try:
            assert wrapper.publish(fd, "s1.bin", b"fixture") == wrapper.sha(b"fixture")
            item = (root / "s1.bin").lstat()
            assert stat.S_IMODE(item.st_mode) == 0o400 and item.st_nlink == 1
            with pytest.raises(wrapper.ReleaseError, match="DESTINATION_EXISTS"):
                wrapper.publish(fd, "s1.bin", b"other")
        finally: os.close(fd)


def test_exclusive_attempt_directory_race():
    with tempfile.TemporaryDirectory() as name:
        target = Path(name) / "attempt-state"
        os.mkdir(target, 0o700)
        with pytest.raises(FileExistsError): os.mkdir(target, 0o700)


def test_execute_calls_authority_gate_before_state(monkeypatch):
    release, paths = {}, {"state": Path("must-not-exist")}
    monkeypatch.setattr(wrapper, "preflight", lambda path: (release, paths))
    monkeypatch.setattr(wrapper, "authorize", lambda *args: (_ for _ in ()).throw(wrapper.ReleaseError("TOKEN_AUTHORITY")))
    with pytest.raises(wrapper.ReleaseError, match="TOKEN_AUTHORITY"):
        wrapper.execute(Path("release.json"))


def test_v2_ledger_adapter_contract_is_integer():
    assert isinstance(wrapper_v2.current_ledger(), int)
    assert wrapper_v2.current_ledger() == 175


def test_v2_losing_concurrent_invocation_cannot_write_terminal(monkeypatch):
    with tempfile.TemporaryDirectory() as name:
        root = Path(name); os.chmod(root, 0o700)
        state = root / "attempt-state"; state.mkdir(mode=0o700)
        paths = {"root":root,"state":state,"outputs":root / "outputs","output":root / "outputs/s1","manifest":root / "outputs/manifest"}
        monkeypatch.setattr(wrapper_v2, "preflight", lambda path: ({}, paths))
        monkeypatch.setattr(wrapper_v2, "authorize", lambda *args: None)
        with pytest.raises(FileExistsError): wrapper_v2.execute(Path("release.json"))
        assert not (state / "terminal.json").exists()


def base_authorization_release():
    fixture_path = "scripts/research/validate_f017_representative_s1_materialization_release_v1.py"
    fixture_sha = validator.sha(ROOT / fixture_path)
    auth = {
        "schema":"pulsarmlx.f017.representative-s1-materialization-authorization","status":"PREPARED_REVIEW_REQUIRED","real_event_authorized":False,
        "s1_target":{"semantic_role":"LAYER3_POST_ATTENTION_RESIDUAL","stage_name":"post_attention_residual","formula":"f32(S0 + layer3_attention_output)","sha256":validator.EXPECTED_S1,"dtype":"little-endian-f32","shape":[6144],"byte_length":24576,"classification_before_event":"HASH_RETAINED_REPRODUCIBLE_NOT_BYTE_RETAINED"},
        "source_authority":{"real_execution_evidence":{"sha256":validator.EXPECTED_EVENT_EVIDENCE},"reproduction_contract":{"sha256":validator.EXPECTED_REPRODUCTION},"reproduction_producer":{"sha256":validator.EXPECTED_PRODUCER},"canonical_s0":{"sha256":"9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"},"attention_payloads":{"count":9,"packed_bytes":132900864,"inventory_bound_by_candidate":True,"checkpoint_fallback":False}},
        "accounting":{"ledger_before":175,"ledger_after":175,"checkpoint_reads":0,"shard_opens":0,"new_attention_executions":0,"future_s1_materializations":1,"expert_executions":0,"ffn_compositions":0,"s2_constructions":0},
        "stop_boundary":"AFTER_REPRESENTATIVE_S1_RETENTION_ONLY","prohibitions":{key:True for key in ("checkpoint_access","shard_open","new_real_attention_execution","router_execution","expert_execution","ffn_consumption","ffn_composition","s2_construction","retry","resume","second_attempt")}}
    release = {"schema":"pulsarmlx.f017.representative-s1-materialization-single-use-release","status":"PREPARED_FOR_INDEPENDENT_APPROVAL","real_event_authorized":False,"authorization_sha256":fixture_sha,
        "accounting":{"checkpoint_reads":0,"shard_opens":0,"new_attention_executions":0,"s1_materializations":1,"ffn_compositions":0,"s2_constructions":0,"ledger_before":175,"ledger_after":175},
        "single_use":{"exclusive_attempt_creation":True,"durable_attempt_start_before_reconstruction":True,"durable_materialization_start_before_reconstruction":True,"attempts":1,"no_retry":True,"no_resume":True,"no_second_attempt":True,"failure_after_attempt_start_consumes_release":True},
        "output_contract":{"expected_equals_produced_equals_readback":True,"sha256":validator.EXPECTED_S1,"publication":"DESCRIPTOR_RELATIVE_EXCLUSIVE_TEMP_FSYNC_NO_REPLACE_LINK_PARENT_FSYNC_DESCRIPTOR_READBACK"},
        "stop_boundary":"AFTER_REPRESENTATIVE_S1_RETENTION_ONLY","s2_interface_exposed":False,"ffn_input_exposed":False,
        "runtime_interface":{key:key for key in ("candidate","canonical_s0","canonical_s0_manifest","attention_retention_root","state_root","output_root","output")},"bindings":{"authorization":{"path":fixture_path,"sha256":fixture_sha}}}
    return auth, release


@pytest.mark.parametrize("mutation", [
    lambda a,r: a["s1_target"].update(sha256="0"*64),
    lambda a,r: a["s1_target"].update(stage_name="router_normalized"),
    lambda a,r: a["s1_target"].update(formula="f64(S0+attention)"),
    lambda a,r: a["source_authority"]["canonical_s0"].update(sha256="0"*64),
    lambda a,r: a["source_authority"]["attention_payloads"].update(count=8),
    lambda a,r: a["source_authority"]["attention_payloads"].update(checkpoint_fallback=True),
    lambda a,r: a["accounting"].update(checkpoint_reads=1),
    lambda a,r: a["accounting"].update(new_attention_executions=1),
    lambda a,r: a["accounting"].update(ffn_compositions=1),
    lambda a,r: a["accounting"].update(s2_constructions=1),
    lambda a,r: r["accounting"].update(s1_materializations=2),
    lambda a,r: r["single_use"].update(no_retry=False),
    lambda a,r: r["single_use"].update(exclusive_attempt_creation=False),
    lambda a,r: r["output_contract"].update(expected_equals_produced_equals_readback=False),
    lambda a,r: r.update(s2_interface_exposed=True),
    lambda a,r: r["runtime_interface"].update(checkpoint_path="bad"),
])
def test_load_bearing_mutations_fail(mutation):
    auth, release = base_authorization_release(); mutation(auth, release)
    with pytest.raises(validator.ValidationError): validator.validate(auth, release)


def test_wrong_size_nonfinite_and_source_alias_rejected():
    raw = executor.synthetic_fixture(); assert len(raw) == 24576 and np.isfinite(np.frombuffer(raw, dtype="<f4")).all()
    with tempfile.TemporaryDirectory() as name:
        item = Path(name) / "item"; item.write_bytes(b"x" * 16); os.chmod(item, 0o400)
        with pytest.raises(executor.S1Error, match="SOURCE_IDENTITY"): executor.require_immutable(item, "0"*64, 16)
        alias = Path(name) / "alias"; os.link(item, alias)
        with pytest.raises(executor.S1Error, match="SOURCE_WRITABLE_OR_LINKED"): executor.require_immutable(item, "0"*64, 16)


def test_writable_symlink_and_import_authority_mutations_rejected():
    with tempfile.TemporaryDirectory() as name:
        root = Path(name); target = root / "target"; target.write_bytes(b"fixture")
        with pytest.raises(executor.S1Error, match="SOURCE_WRITABLE_OR_LINKED"):
            executor.require_immutable(target, executor.sha256(b"fixture"), 7)
        os.chmod(target, 0o400); link = root / "link"; link.symlink_to(target)
        with pytest.raises(executor.S1Error, match="SOURCE_NOT_REGULAR"):
            executor.require_immutable(link, executor.sha256(b"fixture"), 7)
    auth, release = base_authorization_release()
    release["bindings"]["oracle"] = {"path":"scripts/research/prepare_f017_m1f0_real_reference.py","sha256":"0"*64}
    with pytest.raises(validator.ValidationError, match="BINDING_SHA"):
        validator.validate(auth, release)
