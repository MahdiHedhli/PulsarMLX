#![cfg(all(target_os = "macos", pulsar_native_mlx))]

use f017_runner::artifact_paths::classify_runtime_drift;
use f017_runner::evidence::Evidence;
use f017_runner::json::{parse_json_no_duplicates, sha256_bytes, sha256_file};
use serde_json::{json, Value};
use std::fs::{self, File};
use std::os::unix::fs::FileExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);
const GATE_OFFSET: u64 = 3_423_197_024;
const UP_OFFSET: u64 = 4_268_636_000;
const DOWN_OFFSET: u64 = 2_203_342_688;
const GATE_LEN: usize = 3_244_032;
const UP_LEN: usize = 3_244_032;
const DOWN_LEN: usize = 4_816_896;

fn artifact(root: &Path, role: &str, path: &str) -> Value {
    json!({"path_kind":"repository_relative","symbolic_path":path,"content_sha256":sha256_file(&root.join(path)).unwrap(),"logical_role":role})
}
fn zeros_hash(bytes: usize) -> String {
    sha256_bytes(&vec![0_u8; bytes])
}
fn stage(count: usize) -> Value {
    let raw = vec![0_u8; count * 4];
    json!({"sha256":sha256_bytes(&raw),"bytes_hex":hex(&raw)})
}
fn bound(count: usize) -> Value {
    let raw = vec![0_u8; count * 8];
    json!({"sha256":sha256_bytes(&raw),"f64_hex":hex(&raw)})
}
fn hex(bytes: &[u8]) -> String {
    const H: &[u8; 16] = b"0123456789abcdef";
    let mut s = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        s.push(H[(b >> 4) as usize] as char);
        s.push(H[(b & 15) as usize] as char);
    }
    s
}

fn setup() -> (PathBuf, String, PathBuf, PathBuf) {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let temp = std::env::temp_dir().join(format!(
        "f017-m1e-native-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&temp).unwrap();
    let shard = temp.join("fixture-shard-2.gguf");
    let file = File::create(&shard).unwrap();
    file.set_len(UP_OFFSET + UP_LEN as u64).unwrap();
    file.write_all_at(&vec![0; GATE_LEN], GATE_OFFSET).unwrap();
    file.write_all_at(&vec![0; UP_LEN], UP_OFFSET).unwrap();
    file.write_all_at(&vec![0; DOWN_LEN], DOWN_OFFSET).unwrap();
    file.sync_all().unwrap();
    let first = temp.join("fixture-shard-1.gguf");
    fs::write(&first, b"fixture").unwrap();
    let checkpoint = temp.join("checkpoint.json");
    let set = "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee";
    let catalog = "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0";
    fs::write(&checkpoint,serde_json::to_vec(&json!({"schema":"pulsarmlx.f017.checkpoint-manifest","schema_version":"1.0.0","kind":"fixture","immutable_revision":"m1e-synthetic-v1","architecture":"glm-dsa","tokenizer_identity":"fixture-tokenizer","checkpoint_set_sha256":set,"catalog_sha256":catalog,"tensor_count":3,"shards":[{"filename":"fixture-shard-1.gguf","size_bytes":7,"sha256":zeros_hash(1)},{"filename":"fixture-shard-2.gguf","size_bytes":fs::metadata(&shard).unwrap().len(),"sha256":zeros_hash(2)}]})).unwrap()).unwrap();
    let activation_doc: Value =
        serde_json::from_slice(
            &fs::read(root.join(
                "specs/017-rust-native-inference-runtime/fixtures/f017-m1e-activation-v1.json",
            ))
            .unwrap(),
        )
        .unwrap();
    let gate_packed = zeros_hash(GATE_LEN);
    let up_packed = zeros_hash(UP_LEN);
    let down_packed = zeros_hash(DOWN_LEN);
    let gate_payload = temp.join("gate-packed.bin");
    let up_payload = temp.join("up-packed.bin");
    let down_payload = temp.join("down-packed.bin");
    fs::write(&gate_payload, vec![0_u8; GATE_LEN]).unwrap();
    fs::write(&up_payload, vec![0_u8; UP_LEN]).unwrap();
    fs::write(&down_payload, vec![0_u8; DOWN_LEN]).unwrap();
    let preparer =
        sha256_file(&root.join("scripts/research/prepare_f017_m1e_real_reference.py")).unwrap();
    let oracle_doc = json!({"schema":"pulsarmlx.f017.m1e-oracle-package","schema_version":"1.0.0","generator":{"source_sha256":preparer},"matrices":{"gate":{"packed_sha256":gate_packed,"decoded_sha256":zeros_hash(2048*6144*4)},"up":{"packed_sha256":up_packed,"decoded_sha256":zeros_hash(2048*6144*4)},"down":{"packed_sha256":down_packed,"decoded_sha256":zeros_hash(6144*2048*4)}},"activation":{"sha256":activation_doc["activation"]["payload_sha256"],"bytes_hex":activation_doc["activation"]["bytes_hex"],"element_count":6144},"stages":{"gate":stage(2048),"up":stage(2048),"activated_hidden":stage(2048),"final_output":stage(6144)},"bounds":{"gate":bound(2048),"up":bound(2048),"activated_hidden":bound(2048),"final_output":bound(6144)},"derived_global":{"max_absolute_bound":0.0,"rmse_bound":0.0,"cosine_minimum":null},"timings":{"decoder_gate_seconds":0.0,"decoder_up_seconds":0.0,"decoder_down_seconds":0.0,"oracle_gate_seconds":0.0,"oracle_up_seconds":0.0,"oracle_activation_seconds":0.0,"oracle_down_seconds":0.0},"finalization":{"preparation_started_at":"1","oracle_completed_at":"2","completion_marker":"m1e_oracle_finalized_sequence_0","immutable_after_finalization":true}});
    let oracle = temp.join("oracle.json");
    fs::write(&oracle, serde_json::to_vec(&oracle_doc).unwrap()).unwrap();
    let payload = |role: &str, name: &str, digest: &str| json!({"path_kind":"package_relative","symbolic_path":name,"content_sha256":digest,"logical_role":format!("{role}_packed_payload"),"package_artifact_id":format!("m1e-synthetic-{role}-packed-v1")});
    let package_doc = json!({"schema":"pulsarmlx.f017.m1e-package","schema_version":"1.0.0","package_kind":"checkpoint_free_fixture","checkpoint_set_sha256":set,"catalog_sha256":catalog,"tensor_map_sha256":"ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223","source_checkpoint_read_count":3,"tensors":[{"role":"gate","name":"blk.3.ffn_gate_exps.weight","shard_ordinal":2,"offset":GATE_OFFSET,"packed_length":GATE_LEN,"quantization":"IQ2_XXS","matrix_shape":[2048,6144],"packed_sha256":gate_packed,"payload":payload("gate","gate-packed.bin",&gate_packed)},{"role":"up","name":"blk.3.ffn_up_exps.weight","shard_ordinal":2,"offset":UP_OFFSET,"packed_length":UP_LEN,"quantization":"IQ2_XXS","matrix_shape":[2048,6144],"packed_sha256":up_packed,"payload":payload("up","up-packed.bin",&up_packed)},{"role":"down","name":"blk.3.ffn_down_exps.weight","shard_ordinal":2,"offset":DOWN_OFFSET,"packed_length":DOWN_LEN,"quantization":"IQ3_XXS","matrix_shape":[6144,2048],"packed_sha256":down_packed,"payload":payload("down","down-packed.bin",&down_packed)}],"oracle":{"path_kind":"package_relative","symbolic_path":"oracle.json","content_sha256":sha256_file(&oracle).unwrap(),"logical_role":"independent_oracle","package_artifact_id":"m1e-synthetic-oracle-v1"},"one_attempt":true});
    let package = temp.join("package.json");
    fs::write(&package, serde_json::to_vec(&package_doc).unwrap()).unwrap();
    let environment = temp.join("environment.json");
    fs::write(&environment,format!("{{\"schema\":\"pulsarmlx.f017.fixture-environment\",\"schema_version\":1,\"architecture\":\"{}\",\"purpose\":\"checkpoint_free_ci\"}}\n",std::env::consts::ARCH)).unwrap();
    let roles = [
        (
            "attempt_3_handoff",
            "docs/architecture/reviews/f017-m1-e-attempt-3-handoff.md",
        ),
        (
            "boundary_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-expert-boundary-v1.json",
        ),
        (
            "decoder_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-decoder-contract-v2.json",
        ),
        (
            "scaffold_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-exact-scaffold-v1.json",
        ),
        (
            "tier_b_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-expert-tier-b-v1.json",
        ),
        (
            "repeat_integrity_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-repeat-integrity-v1.json",
        ),
        (
            "timing_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-timing-v1.json",
        ),
        (
            "evidence_schema",
            "specs/017-rust-native-inference-runtime/contracts/m1e-evidence-v1.schema.json",
        ),
        (
            "execution_config_schema",
            "specs/017-rust-native-inference-runtime/contracts/m1e-execution-config-v3.schema.json",
        ),
        (
            "preparer_input_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-real-reference-preparer-input-v3.json",
        ),
        (
            "path_resolution_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1d-artifact-path-resolution-v1.json",
        ),
        (
            "trusted_repository_identity_contract",
            "specs/017-rust-native-inference-runtime/contracts/trusted-repository-identity-v2.json",
        ),
        (
            "activation_generator",
            "scripts/research/generate_f017_m1e_activation.py",
        ),
        (
            "execution_config_preparer",
            "scripts/research/prepare_f017_m1e_execution.py",
        ),
        (
            "real_reference_preparer",
            "scripts/research/prepare_f017_m1e_real_reference.py",
        ),
        (
            "independent_iq2_decoder",
            "scripts/research/iq2_xxs_dequant.py",
        ),
        (
            "independent_iq3_decoder",
            "scripts/research/iq3_xxs_dequant.py",
        ),
        (
            "third_iq3_decoder",
            "scripts/research/iq3_xxs_spec_decoder.py",
        ),
        (
            "iq3_order_regression",
            "specs/017-rust-native-inference-runtime/fixtures/f017-iq3-xxs-order-regression-v1.json",
        ),
    ];
    let artifacts = roles
        .into_iter()
        .map(|(r, p)| (r.to_owned(), artifact(&root, r, p)))
        .collect::<serde_json::Map<_, _>>();
    let mut artifacts = artifacts;
    artifacts.insert(
        "authorized_launcher".into(),
        artifact(
            &root,
            "authorized_launcher",
            "scripts/research/run_f017_m1e_authorized.py",
        ),
    );
    let tensor = |role: &str,
                  name: &str,
                  q: &str,
                  offset: u64,
                  len: u64,
                  row: u64,
                  catalog: &str| {
        let (gguf, logical) = if role == "down" {
            (json!([2048, 6144, 256]), json!([6144, 2048]))
        } else {
            (json!([6144, 2048, 256]), json!([2048, 6144]))
        };
        json!({"role":role,"name":name,"layer":3,"expert":15,"quantization":q,"gguf_shape":gguf,"logical_matrix_shape":logical,"shard_ordinal":2,"offset":offset,"packed_length":len,"packed_row_width":row,"catalog_entry_sha256":catalog,"decoder_contract_sha256":"9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84","path_kind":"bounded_checkpoint_range","allowed_read_count":1})
    };
    let output = temp.join("evidence.json");
    let runtime = env!("PULSARMLX_SOURCE_SHA");
    let drift = classify_runtime_drift(&root, runtime, runtime).unwrap();
    let drift_sha = sha256_bytes(&serde_json::to_vec(&drift).unwrap());
    let runner_path = Path::new(env!("CARGO_BIN_EXE_f017-glm52-runner"));
    let config_doc = json!({"schema":"pulsarmlx.f017.m1e-execution-config","schema_version":"3.0.0","status":"READY_TO_EXECUTE_M1_E","attempt":2,"attempt_consumed":false,"compiled_runtime_sha":runtime,"tooling_sha":runtime,"authorization_head_sha":runtime,"trusted_repository_identity":{"contract_version":"f017-trusted-repository-identity-v2","contract_sha256":sha256_file(&root.join("specs/017-rust-native-inference-runtime/contracts/trusted-repository-identity-v2.json")).unwrap(),"compiled_runtime_sha":runtime,"tooling_sha":runtime,"authorization_head_sha":runtime,"runtime_drift_classification_sha256":drift_sha},"executable_identity":{"sha256":sha256_file(runner_path).unwrap(),"build_profile":"release","architecture":std::env::consts::ARCH,"feature_flags":["pulsar_native_mlx"]},"repository_root":{"path_kind":"absolute_private_local","path":root,"identity":runtime},"package_root":{"path_kind":"absolute_private_local","path":temp,"identity":"m1e_attempt_2_private_package_root"},"activation_fixture":artifact(Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").as_path(),"activation_fixture","specs/017-rust-native-inference-runtime/fixtures/f017-m1e-activation-v1.json"),"activation_payload_sha256":"732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149","repository_artifacts":artifacts,"local_artifacts":{"environment_manifest":{"path_kind":"absolute_private_local","path":environment,"content_sha256":sha256_file(&environment).unwrap()},"checkpoint_manifest":{"path_kind":"absolute_private_local","path":checkpoint,"content_sha256":sha256_file(&checkpoint).unwrap()},"target_shard":{"path_kind":"absolute_private_local","path":shard,"ordinal":2,"basename":"fixture-shard-2.gguf","byte_size":fs::metadata(&shard).unwrap().len(),"content_sha256":"d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36"},"oracle_output":oracle,"package_output":package,"evidence_output":output},"prior_evidence":{"m1_a":"aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805","m1_b":"9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770","m1_c":"343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e","m1_d":"dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c","m1_e_attempt_1":"346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119"},"checkpoint_bindings":{"checkpoint_set_sha256":set,"catalog_sha256":catalog,"tensor_map_sha256":"ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223"},"expert":{"layer":3,"expert":15,"symbolic_id":"blk.3.expert.15"},"tensors":[tensor("gate","blk.3.ffn_gate_exps.weight","IQ2_XXS",GATE_OFFSET,GATE_LEN as u64,1584,"42e379023728565d323fff8b120f2c6dff6fa50f10d9ad1cceb3e3597af36354"),tensor("up","blk.3.ffn_up_exps.weight","IQ2_XXS",UP_OFFSET,UP_LEN as u64,1584,"011ccab7ca2293da5b0d1112172b2dccd4b2cdb2482672dd217f996280223119"),tensor("down","blk.3.ffn_down_exps.weight","IQ3_XXS",DOWN_OFFSET,DOWN_LEN as u64,784,"1c7a04eb897d242a621a09c6dfb78c3e92b407dff44ddf8cf67187dae50081e1")],"runner":{"mode":"fixture_expert","memory_floor_bytes":1},"execution":{"conceptual_expert_count":1,"repeat_count":10,"native_dispatch_count":30,"maximum_payload_count":3,"maximum_positional_reads":3,"maximum_shard_opens":1,"compressed_byte_budget":11304960,"auto_retry":false,"stop_before_m1_f":true}});
    let mut config_doc = config_doc;
    config_doc["attempt"] = json!(3);
    config_doc["package_root"]["identity"] = json!("m1e_attempt_3_private_package_root");
    config_doc["prior_evidence"]["m1_e_attempt_2"] =
        json!("8912e523963cfa8822fe6472ec30be31a78c4c3648fba34caf6c41055efd7e00");
    config_doc["local_artifacts"]["runner_binary"] = json!({
        "path_kind":"absolute_private_local",
        "path":env!("CARGO_BIN_EXE_f017-glm52-runner"),
        "content_sha256":sha256_file(Path::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))).unwrap()
    });
    config_doc["local_artifacts"]["oracle_launcher"] = json!({
        "path_kind":"absolute_private_local",
        "path":"/usr/bin/true",
        "content_sha256":sha256_file(Path::new("/usr/bin/true")).unwrap()
    });
    config_doc["local_artifacts"]["attempt_state_output"] = json!(temp.join("attempt-state.json"));
    config_doc["local_artifacts"]["preflight_evidence_output"] =
        json!(temp.join("preflight-evidence.json"));
    let bytes = serde_json::to_vec(&config_doc).unwrap();
    let digest = sha256_bytes(&bytes);
    let config = temp.join("config.json");
    fs::write(&config, bytes).unwrap();
    (config, digest, output, temp)
}

fn run(diverge: bool) -> (std::process::ExitStatus, Evidence, PathBuf) {
    let (config, digest, output, temp) = setup();
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let mut c = Command::new(root.join(".venv/bin/python"));
    c.current_dir(std::env::temp_dir())
        .arg(root.join("scripts/research/run_f017_m1e_authorized.py"))
        .args(["--execution-config"])
        .arg(config)
        .args(["--execution-config-sha256", &digest]);
    if diverge {
        c.env("PULSAR_F017_TEST_DIVERGE_M1E_REPEAT", "5");
    }
    let status = c.status().unwrap();
    let evidence = parse_json_no_duplicates(&fs::read(output).unwrap()).unwrap();
    (status, evidence, temp)
}

fn setup_with_v3_preparer() -> (PathBuf, String, PathBuf, PathBuf) {
    let (config, _, output, temp) = setup();
    let mut document: Value = serde_json::from_slice(&fs::read(&config).unwrap()).unwrap();
    let oracle = PathBuf::from(
        document["local_artifacts"]["oracle_output"]
            .as_str()
            .unwrap(),
    );
    let package = PathBuf::from(
        document["local_artifacts"]["package_output"]
            .as_str()
            .unwrap(),
    );
    fs::remove_file(oracle).unwrap();
    fs::remove_file(package).unwrap();
    let uv = Command::new("which").arg("uv").output().unwrap();
    assert!(uv.status.success());
    let uv = PathBuf::from(String::from_utf8(uv.stdout).unwrap().trim());
    let uv_sha = sha256_file(&uv).unwrap();
    document["local_artifacts"]["oracle_launcher"] = json!({
        "path_kind":"absolute_private_local",
        "path":uv,
        "content_sha256":uv_sha
    });
    let bytes = serde_json::to_vec(&document).unwrap();
    let digest = sha256_bytes(&bytes);
    fs::write(&config, bytes).unwrap();
    (config, digest, output, temp)
}

fn run_with_oracle_mutation(
    rebind_package_hash: bool,
    mutate: impl FnOnce(&mut serde_json::Value),
) -> (std::process::ExitStatus, Evidence, PathBuf) {
    let (config, digest, output, temp) = setup();
    let config_doc: serde_json::Value =
        serde_json::from_slice(&fs::read(&config).unwrap()).unwrap();
    let oracle = PathBuf::from(
        config_doc["local_artifacts"]["oracle_output"]
            .as_str()
            .unwrap(),
    );
    let package = PathBuf::from(
        config_doc["local_artifacts"]["package_output"]
            .as_str()
            .unwrap(),
    );
    let mut oracle_doc: serde_json::Value =
        serde_json::from_slice(&fs::read(&oracle).unwrap()).unwrap();
    mutate(&mut oracle_doc);
    fs::write(&oracle, serde_json::to_vec(&oracle_doc).unwrap()).unwrap();
    if rebind_package_hash {
        let mut package_doc: serde_json::Value =
            serde_json::from_slice(&fs::read(&package).unwrap()).unwrap();
        package_doc["oracle"]["content_sha256"] = json!(sha256_file(&oracle).unwrap());
        fs::write(&package, serde_json::to_vec(&package_doc).unwrap()).unwrap();
    }

    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let status = Command::new(root.join(".venv/bin/python"))
        .current_dir(std::env::temp_dir())
        .arg(root.join("scripts/research/run_f017_m1e_authorized.py"))
        .args(["--execution-config"])
        .arg(config)
        .args(["--execution-config-sha256", &digest])
        .status()
        .unwrap();
    let evidence = parse_json_no_duplicates(&fs::read(output).unwrap()).unwrap();
    (status, evidence, temp)
}

#[test]
fn exact_config_preflight_is_repeatable_and_non_consuming() {
    let (config, digest, output, temp) = setup();
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    for _ in 0..2 {
        let result = Command::new(root.join(".venv/bin/python"))
            .current_dir(std::env::temp_dir())
            .arg(root.join("scripts/research/run_f017_m1e_authorized.py"))
            .args(["--execution-config"])
            .arg(&config)
            .args(["--execution-config-sha256", &digest, "--preflight-only"])
            .output()
            .unwrap();
        assert!(result.status.success());
        assert_eq!(result.stdout, b"READY_TO_EXECUTE_M1_E\n");
    }
    assert!(!temp.join("attempt-state.json").exists());
    assert!(!temp.join("preflight-evidence.json").exists());
    assert!(!output.exists());
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn canonical_real_shaped_synthetic_expert_uses_one_config_and_thirty_native_dispatches() {
    let (status, evidence, temp) = run(false);
    assert!(status.success());
    evidence.validate_success_ready().unwrap();
    assert_eq!(evidence.execution.expert_execution_count, 1);
    assert_eq!(evidence.execution.dispatch.native, 30);
    assert_eq!(
        evidence
            .execution
            .numerical
            .expert_repeat_integrity
            .outputs
            .len(),
        10
    );
    assert!(
        evidence
            .execution
            .numerical
            .expert_repeat_integrity
            .final_output_all_equal
    );
    assert!(evidence.lifecycle.reconciled);
    let mut fallback = evidence.clone();
    fallback.execution.dispatch.fallback = 1;
    assert!(fallback.validate_success_ready().is_err());
    let mut dispatch = evidence.clone();
    dispatch.execution.dispatch.native = 29;
    assert!(dispatch.validate_success_ready().is_err());
    let mut lifecycle = evidence.clone();
    lifecycle.lifecycle.post.in_flight_work.value = Some(1);
    assert!(lifecycle.validate_success_ready().is_err());
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn canonical_v3_config_invokes_updated_preparer_before_native_expert() {
    let (config, digest, output, temp) = setup_with_v3_preparer();
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let result = Command::new(root.join(".venv/bin/python"))
        .current_dir(std::env::temp_dir())
        .arg(root.join("scripts/research/run_f017_m1e_authorized.py"))
        .args(["--execution-config"])
        .arg(config)
        .args(["--execution-config-sha256", &digest])
        .status()
        .unwrap();
    assert!(result.success());
    let evidence: Evidence = parse_json_no_duplicates(&fs::read(output).unwrap()).unwrap();
    evidence.validate_success_ready().unwrap();
    assert_eq!(evidence.execution.expert_execution_count, 1);
    assert_eq!(evidence.execution.dispatch.native, 30);
    assert_eq!(
        evidence
            .execution
            .numerical
            .expert_repeat_integrity
            .outputs
            .len(),
        10
    );
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn changed_intermediate_rejects_even_when_final_hashes_stay_equal() {
    let (status, evidence, temp) = run(true);
    assert!(!status.success());
    assert_eq!(
        evidence.result.first_failure.as_ref().unwrap().code,
        "m1e_repeat_divergence"
    );
    assert!(
        evidence
            .execution
            .numerical
            .expert_repeat_integrity
            .final_output_all_equal
    );
    assert!(
        !evidence
            .execution
            .numerical
            .expert_repeat_integrity
            .gate_all_equal
    );
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn stale_oracle_content_and_candidate_before_completion_fail_closed() {
    let (status, evidence, temp) = run_with_oracle_mutation(false, |oracle| {
        oracle["stale_unbound_field"] = json!(true);
    });
    assert!(!status.success());
    assert_eq!(
        evidence.result.first_failure.as_ref().unwrap().code,
        "m1d_artifact_hash"
    );
    fs::remove_dir_all(temp).unwrap();

    let (status, evidence, temp) = run_with_oracle_mutation(true, |oracle| {
        oracle["finalization"]["oracle_completed_at"] = json!(u128::MAX.to_string());
    });
    assert!(!status.success());
    assert_eq!(
        evidence.result.first_failure.as_ref().unwrap().code,
        "m1e_oracle_order"
    );
    fs::remove_dir_all(temp).unwrap();
}
