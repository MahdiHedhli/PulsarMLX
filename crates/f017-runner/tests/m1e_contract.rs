use f017_runner::cli::RunnerMode;
use f017_runner::json::{sha256_bytes, sha256_file};
use serde_json::{json, Value};
use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};

fn artifact(root: &Path, role: &str, path: &str) -> Value {
    json!({"path_kind":"repository_relative","symbolic_path":path,"content_sha256":sha256_file(&root.join(path)).unwrap(),"logical_role":role})
}

fn base(temp: &Path) -> (Value, PathBuf) {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let private = temp.join("private");
    fs::create_dir(&private).unwrap();
    let env = temp.join("environment.json");
    let checkpoint = temp.join("checkpoint.json");
    let shard = temp.join("fake-shard.gguf");
    fs::write(&env, b"{}").unwrap();
    fs::write(&checkpoint, b"{}").unwrap();
    fs::write(&shard, b"metadata-only").unwrap();
    let roles = [
        ("boundary_contract","specs/017-rust-native-inference-runtime/contracts/m1e-expert-boundary-v1.json"),
        ("decoder_contract","specs/017-rust-native-inference-runtime/contracts/m1e-decoder-contract-v1.json"),
        ("scaffold_contract","specs/017-rust-native-inference-runtime/contracts/m1e-exact-scaffold-v1.json"),
        ("tier_b_contract","specs/017-rust-native-inference-runtime/contracts/m1e-expert-tier-b-v1.json"),
        ("repeat_integrity_contract","specs/017-rust-native-inference-runtime/contracts/m1e-repeat-integrity-v1.json"),
        ("timing_contract","specs/017-rust-native-inference-runtime/contracts/m1e-timing-v1.json"),
        ("evidence_schema","specs/017-rust-native-inference-runtime/contracts/m1e-evidence-v1.schema.json"),
        ("execution_config_schema","specs/017-rust-native-inference-runtime/contracts/m1e-execution-config-v1.schema.json"),
        ("path_resolution_contract","specs/017-rust-native-inference-runtime/contracts/m1d-artifact-path-resolution-v1.json"),
        ("activation_generator","scripts/research/generate_f017_m1e_activation.py"),
        ("execution_config_preparer","scripts/research/prepare_f017_m1e_execution.py"),
        ("real_reference_preparer","scripts/research/prepare_f017_m1e_real_reference.py"),
        ("independent_iq2_decoder","scripts/research/iq2_xxs_dequant.py"),
        ("independent_iq3_decoder","scripts/research/iq3_xxs_dequant.py"),
    ];
    let artifacts = roles
        .into_iter()
        .map(|(r, p)| (r.to_owned(), artifact(&root, r, p)))
        .collect::<serde_json::Map<_, _>>();
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
        json!({"role":role,"name":name,"layer":3,"expert":15,"quantization":q,"gguf_shape":gguf,"logical_matrix_shape":logical,"shard_ordinal":2,"offset":offset,"packed_length":len,"packed_row_width":row,"catalog_entry_sha256":catalog,"decoder_contract_sha256":"357a1989174b0ec86684549f8519bb7a47fdb8b8194fa985c8126d89d6339a00","path_kind":"bounded_checkpoint_range","allowed_read_count":1})
    };
    (
        json!({
            "schema":"pulsarmlx.f017.m1e-execution-config","schema_version":"1.0.0","status":"READY_TO_EXECUTE_M1_E","attempt":1,"attempt_consumed":false,
            "runtime_sha":env!("PULSARMLX_SOURCE_SHA"),"tooling_sha":env!("PULSARMLX_SOURCE_SHA"),
            "repository_root":{"path_kind":"absolute_private_local","path":root,"identity":env!("PULSARMLX_SOURCE_SHA")},
            "package_root":{"path_kind":"absolute_private_local","path":private,"identity":"m1e_attempt_1_private_package_root"},
            "activation_fixture":artifact(Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").as_path(),"activation_fixture","specs/017-rust-native-inference-runtime/fixtures/f017-m1e-activation-v1.json"),
            "activation_payload_sha256":"732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149",
            "repository_artifacts":artifacts,
            "local_artifacts":{
                "environment_manifest":{"path_kind":"absolute_private_local","path":env,"content_sha256":sha256_file(&env).unwrap()},
                "checkpoint_manifest":{"path_kind":"absolute_private_local","path":checkpoint,"content_sha256":sha256_file(&checkpoint).unwrap()},
                "target_shard":{"path_kind":"absolute_private_local","path":shard,"ordinal":2,"basename":"fake-shard.gguf","byte_size":fs::metadata(&shard).unwrap().len(),"content_sha256":"d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36"},
                "oracle_output":private.join("oracle.json"),"package_output":private.join("package.json"),"evidence_output":temp.join("evidence.json")},
            "prior_evidence":{"m1_a":"aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805","m1_b":"9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770","m1_c":"343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e","m1_d":"dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c"},
            "checkpoint_bindings":{"checkpoint_set_sha256":"d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee","catalog_sha256":"0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0","tensor_map_sha256":"ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223"},
            "expert":{"layer":3,"expert":15,"symbolic_id":"blk.3.expert.15"},
            "tensors":[tensor("gate","blk.3.ffn_gate_exps.weight","IQ2_XXS",3423197024,3244032,1584,"42e379023728565d323fff8b120f2c6dff6fa50f10d9ad1cceb3e3597af36354"),tensor("up","blk.3.ffn_up_exps.weight","IQ2_XXS",4268636000,3244032,1584,"011ccab7ca2293da5b0d1112172b2dccd4b2cdb2482672dd217f996280223119"),tensor("down","blk.3.ffn_down_exps.weight","IQ3_XXS",2203342688,4816896,784,"1c7a04eb897d242a621a09c6dfb78c3e92b407dff44ddf8cf67187dae50081e1")],
            "runner":{"mode":"fixture_expert","memory_floor_bytes":1},
            "execution":{"conceptual_expert_count":1,"repeat_count":10,"native_dispatch_count":30,"maximum_payload_count":3,"maximum_positional_reads":3,"maximum_shard_opens":1,"compressed_byte_budget":11304960,"auto_retry":false,"stop_before_m1_f":true}
        }),
        temp.join("config.json"),
    )
}

fn load(
    value: &Value,
    path: &Path,
) -> Result<f017_runner::m1e_execution_config::Loaded, f017_runner::RunnerError> {
    let bytes = serde_json::to_vec(value).unwrap();
    fs::write(path, &bytes).unwrap();
    f017_runner::m1e_execution_config::load(path, &sha256_bytes(&bytes), true)
}

#[test]
fn preflight_accepts_only_the_immutable_one_expert_config() {
    let temp = std::env::temp_dir().join(format!("f017-m1e-{}", std::process::id()));
    let _ = fs::remove_dir_all(&temp);
    fs::create_dir(&temp).unwrap();
    let (value, path) = base(&temp);
    let loaded = load(&value, &path).unwrap();
    assert_eq!(loaded.config.mode, RunnerMode::M1ePreflight);
    assert!(!loaded.document.attempt_consumed);
    let _ = fs::remove_dir_all(temp);
}

#[test]
fn wrong_expert_tensor_fixture_attempt_and_dispatch_fail_closed() {
    let mutations: Vec<(&str, Box<dyn Fn(&mut Value)>)> = vec![
        ("expert", Box::new(|v| v["expert"]["expert"] = json!(16))),
        (
            "gate",
            Box::new(|v| v["tensors"][0]["name"] = json!("blk.3.ffn_gate_exps.other")),
        ),
        (
            "quantization",
            Box::new(|v| v["tensors"][0]["quantization"] = json!("Q8_0")),
        ),
        (
            "shape",
            Box::new(|v| v["tensors"][0]["logical_matrix_shape"] = json!([2048, 2048])),
        ),
        (
            "decoder",
            Box::new(|v| v["tensors"][0]["decoder_contract_sha256"] = json!("0".repeat(64))),
        ),
        (
            "truncated",
            Box::new(|v| v["tensors"][0]["packed_length"] = json!(3_244_031)),
        ),
        (
            "router",
            Box::new(|v| v["tensors"][0]["role"] = json!("router")),
        ),
        (
            "fixture_hash",
            Box::new(|v| v["activation_payload_sha256"] = json!("0".repeat(64))),
        ),
        (
            "consumed",
            Box::new(|v| v["attempt_consumed"] = json!(true)),
        ),
        (
            "fixture",
            Box::new(|v| {
                v["activation_fixture"]["symbolic_path"] =
                    json!("specs/017-real-checkpoint-runner/fixtures/f017-m1e-activation-v1.json")
            }),
        ),
        ("attempt", Box::new(|v| v["attempt"] = json!(2))),
        (
            "dispatch",
            Box::new(|v| v["execution"]["native_dispatch_count"] = json!(29)),
        ),
        (
            "second",
            Box::new(|v| {
                let duplicate = v["tensors"][0].clone();
                v["tensors"].as_array_mut().unwrap().push(duplicate)
            }),
        ),
    ];
    for (name, mutate) in mutations {
        let temp = std::env::temp_dir().join(format!("f017-m1e-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&temp);
        fs::create_dir(&temp).unwrap();
        let (mut value, path) = base(&temp);
        mutate(&mut value);
        assert!(load(&value, &path).is_err(), "{name}");
        let _ = fs::remove_dir_all(temp);
    }
}

#[test]
fn execution_config_mutation_after_preflight_is_rejected() {
    let temp = std::env::temp_dir().join(format!("f017-m1e-mut-{}", std::process::id()));
    let _ = fs::remove_dir_all(&temp);
    fs::create_dir(&temp).unwrap();
    let (value, path) = base(&temp);
    let loaded = load(&value, &path).unwrap();
    fs::write(&path, b"{}").unwrap();
    assert!(f017_runner::m1e_execution_config::verify_unchanged(
        loaded.config.execution_config.as_ref().unwrap()
    )
    .is_err());
    let _ = fs::remove_dir_all(temp);
}

#[test]
fn config_only_cli_rejects_duplicate_manual_and_environment_style_overrides() {
    for args in [
        vec![
            "--m1e-execution-config",
            "a",
            "--execution-config-sha256",
            "b",
            "--checkpoint-manifest",
            "c",
        ],
        vec![
            "--m1e-execution-config",
            "a",
            "--m1e-execution-config",
            "b",
            "--execution-config-sha256",
            "c",
        ],
        vec![
            "--m1e-preflight-only",
            "a",
            "--execution-config-sha256",
            "b",
            "--repository-root",
            "c",
        ],
    ] {
        let result = f017_runner::cli::parse_args(args.into_iter().map(OsString::from));
        assert!(result.is_err());
    }
}
