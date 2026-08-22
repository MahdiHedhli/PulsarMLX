from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "scripts/research/validate_f017_failure_evidence_v3.py"
SPEC = importlib.util.spec_from_file_location("failure_v3", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def counter(value: int = 0) -> dict[str, int]:
    return {name: value for name in MODULE.COUNTERS}


def attempt(tmp_path: Path) -> Path:
    root = tmp_path / "ATTEMPT"
    root.mkdir()
    pre = {"schema":"pulsarmlx.f017.native-bounded-p1-accounting-snapshot/1.0.0","phase":"PRE_EXECUTION","authorization_id":"AUTH","attempt_id":"ATTEMPT","captured_at_unix_ns":1,"counters":counter()}
    post = {"schema":"pulsarmlx.f017.native-bounded-p1-accounting-snapshot/1.0.0","phase":"POST_SYNCHRONIZATION_PRE_TOKEN_COMPARISON","authorization_id":"AUTH","attempt_id":"ATTEMPT","captured_at_unix_ns":2,"counters":counter(1)}
    access = {"schema":"pulsarmlx.f017.native-bounded-p1-access-census/1.0.0","authorization_id":"AUTH","attempt_id":"ATTEMPT","event_count":1,"shard_open_count":0,"shard_identity_rehash_count":0,"read_only_private_map_count":0,"tensor_lookup_count":0,"tensor_first_use_count":1,"tensor_reuse_count":0,"page_residency_observation_count":0,"historical_explicit_payload_extraction_count":0,"unexpected_access_attempt_count":0,"fallback_attempt_count":0,"alternate_root_attempt_count":0,"events":[{"schema":"pulsarmlx.f017.native-bounded-p1-access-event/1.0.0","sequence":0,"kind":"TENSOR_FIRST_USE","authority_id":"fixture","sha256":"a"*64,"size_bytes":16,"tensor_name":"fixture","result":"PASS","recorded_at_unix_ns":1}]}
    diagnostic = {"schema":"pulsarmlx.f017.native-bounded-p1-diagnostic-manifest/1.0.0","backend":"INERT_NO_CHECKPOINT_TEST","serialization":"F32_LE_DIRECT_PRODUCTION_BUFFER_HASHES","synchronization":"SYNC","direct_production_bytes":True,"layers":[],"final_hidden_state_sha256":"b"*64,"final_norm_sha256":"c"*64,"full_logits_sha256":"d"*64,"logits_dtype":"little-endian-f32","logits_shape":[4],"top_token_ids":[7],"top_logit_f32_bits":[1065353216],"selected_token":7,"expected_token":21615,"tie_rule":"LOWEST_TOKEN_ID_ON_EQUAL_F32_LOGIT"}
    for name, value in (("pre-accounting-snapshot.json",pre),("post-accounting-snapshot.json",post),("access-census.json",access),("numerical-diagnostic-manifest.json",diagnostic)):
        write(root/name,value)
    (root / "access-events").mkdir()
    write(root / "access-events/00000000.json", access["events"][0])
    receipt = {key: None for key in MODULE.RECEIPT_KEYS}
    receipt.update({"schema":"pulsarmlx.f017.native-bounded-p1-execution-receipt/3.0.0","event_class":"NATIVE_P1_INERT_MATH_BOUNDARY_REHEARSAL","authorization_id":"AUTH","attempt_id":"ATTEMPT","contract_sha256":"a"*64,"executor_sha256":"b"*64,"git_head":"c"*40,"checkpoint_manifest_sha256":"d"*64,"checkpoint_catalog_sha256":"e"*64,"checkpoint_set_sha256":"f"*64,"historical_master_ledger_sha256":"1"*64,"historical_master_before":175,"historical_master_after":175,"historical_master_delta":0,"native_event_delta":0,"runtime":{"mlx_version":"0.31.2","mlx_c_version":"0.6.0","architecture":"arm64","machine_brand":"Apple M1 Ultra","stream_origin":"EXPLICIT_OWNED_GPU_DEVICE","native_handle_owned":True,"deallocation_responsibility":"THIS_INVOCATION"},"pre_snapshot_sha256":MODULE.sha256(root/"pre-accounting-snapshot.json"),"post_snapshot_sha256":MODULE.sha256(root/"post-accounting-snapshot.json"),"access_census_sha256":MODULE.sha256(root/"access-census.json"),"numerical_diagnostic_manifest_sha256":MODULE.sha256(root/"numerical-diagnostic-manifest.json"),"prompt_token":9703,"expected_token":21615,"produced_token":7,"generated_token_count":1,"execution_result":"TOKEN_MISMATCH","error_class":"TOKEN_MISMATCH","mandatory_stop_observed":True,"terminal_state":"TERMINAL_FAILURE_NO_RETRY","started_at_unix_ns":1,"completed_at_unix_ns":3})
    write(root/"execution-receipt.json",receipt)
    terminal = {key: None for key in MODULE.TERMINAL_KEYS}
    terminal.update({"schema":"pulsarmlx.f017.native-bounded-p1-terminal/2.0.0","state":"TERMINAL_FAILURE_NO_RETRY","authorization_id":"AUTH","attempt_id":"ATTEMPT","owner_pid":1,"ownership_nonce":"owned","receipt_count":1,"receipt_sha256":MODULE.sha256(root/"execution-receipt.json"),"pre_snapshot_sha256":receipt["pre_snapshot_sha256"],"post_snapshot_sha256":receipt["post_snapshot_sha256"],"access_census_sha256":receipt["access_census_sha256"],"numerical_diagnostic_manifest_sha256":receipt["numerical_diagnostic_manifest_sha256"],"produced_token":7,"error_class":"TOKEN_MISMATCH","terminalized_at_unix_ns":4,"retry_permitted":False})
    write(root/"terminal.json",terminal)
    return root


def test_complete_token_mismatch_evidence_validates(tmp_path: Path):
    assert MODULE.validate(attempt(tmp_path))["execution_result"] == "TOKEN_MISMATCH"


@pytest.mark.parametrize("target, mutation", [
    ("terminal.json", lambda d: d.update(receipt_sha256="0"*64)),
    ("execution-receipt.json", lambda d: d.update(mandatory_stop_observed=False)),
    ("execution-receipt.json", lambda d: d.update(extra="forbidden")),
    ("pre-accounting-snapshot.json", lambda d: d["counters"].pop("callback_count")),
    ("post-accounting-snapshot.json", lambda d: d["counters"].update(callback_count=True)),
    ("access-census.json", lambda d: d["events"][0].update(sequence=2)),
    ("access-census.json", lambda d: d.update(tensor_first_use_count=0)),
    ("numerical-diagnostic-manifest.json", lambda d: d.update(selected_token=8)),
    ("execution-receipt.json", lambda d: d["runtime"].update(extra="forbidden")),
    ("execution-receipt.json", lambda d: d.update(completed_at_unix_ns=0)),
])
def test_mutations_fail_closed(tmp_path: Path, target: str, mutation):
    root = attempt(tmp_path)
    value = MODULE.strict_json(root/target)
    mutation(value)
    write(root/target,value)
    with pytest.raises(ValueError):
        MODULE.validate(root)
