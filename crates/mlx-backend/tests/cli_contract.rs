use serde_json::Value;
use std::process::{Command, Output};

const FIXTURE: &str = "fixtures/mlx/qwen3moe-ffn-generation-v1.json";
const BINARY: &str = env!("CARGO_BIN_EXE_pulsar-mlx");

fn run_cli(arguments: &[String]) -> Output {
    Command::new(BINARY)
        .args(arguments)
        .output()
        .expect("pulsar-mlx process starts")
}

fn valid_arguments() -> Vec<String> {
    [
        "qwen3moe-synthetic-generation",
        "--fixture",
        FIXTURE,
        "--prompt-ids",
        "1,2",
        "--max-new-tokens",
        "3",
        "--eos-token-id",
        "0",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect()
}

fn json_from(output: &Output, stream: &[u8]) -> Value {
    serde_json::from_slice(stream).unwrap_or_else(|error| {
        panic!(
            "CLI stream must be one JSON object: {error}; stdout={:?}; stderr={:?}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        )
    })
}

fn assert_no_unbounded_fields(value: &Value) {
    match value {
        Value::Object(fields) => {
            for (key, child) in fields {
                assert!(
                    !matches!(
                        key.as_str(),
                        "model_path"
                            | "path"
                            | "weights"
                            | "base64"
                            | "payload"
                            | "payload_bytes"
                            | "tensor_selector"
                    ),
                    "unbounded field leaked into CLI evidence: {key}"
                );
                assert_no_unbounded_fields(child);
            }
        }
        Value::Array(values) => values.iter().for_each(assert_no_unbounded_fields),
        _ => {}
    }
}

#[test]
fn qwen_synthetic_command_emits_computed_bounded_fixture_only_result() {
    let arguments = valid_arguments();
    let output = run_cli(&arguments);
    assert!(output.status.success(), "stderr={:?}", output.stderr);
    assert!(output.stderr.is_empty());
    let value = json_from(&output, &output.stdout);
    assert_eq!(value["status"], "passed");
    assert_eq!(value["validation"], "qwen3moe-synthetic-ffn-greedy-v1");
    assert_eq!(value["model_free"], true);
    assert_eq!(value["evaluated"], true);
    assert_eq!(value["fallback_used"], false);
    assert_eq!(value["generated_token_ids"], serde_json::json!([7, 9, 0]));
    assert_eq!(value["full_token_ids"], serde_json::json!([1, 2, 7, 9, 0]));
    assert_eq!(value["termination_reason"], "eos_token");
    assert_eq!(value["step_count"], 3);
    assert_no_unbounded_fields(&value);
}

#[test]
fn qwen_synthetic_command_rejects_wrong_fixture_and_invalid_bounds() {
    let mut wrong_fixture = valid_arguments();
    wrong_fixture[2] = "fixtures/mlx/generation-v1.json".to_owned();
    let output = run_cli(&wrong_fixture);
    assert!(!output.status.success());
    let value = json_from(&output, &output.stderr);
    assert_eq!(value["status"], "rejected");
    assert_eq!(value["evaluated"], false);
    assert_no_unbounded_fields(&value);

    let mut invalid_prompt = valid_arguments();
    invalid_prompt[4] = "".to_owned();
    let output = run_cli(&invalid_prompt);
    assert!(!output.status.success());
    let value = json_from(&output, &output.stderr);
    assert_eq!(value["status"], "rejected");
    assert_no_unbounded_fields(&value);

    let mut overlong_prompt = valid_arguments();
    overlong_prompt[4] = std::iter::repeat("1")
        .take(4_097)
        .collect::<Vec<_>>()
        .join(",");
    let output = run_cli(&overlong_prompt);
    assert!(!output.status.success());
    let value = json_from(&output, &output.stderr);
    assert_eq!(value["status"], "rejected");

    let mut invalid_max_new_tokens = valid_arguments();
    invalid_max_new_tokens[6] = "129".to_owned();
    let output = run_cli(&invalid_max_new_tokens);
    assert!(!output.status.success());
    let value = json_from(&output, &output.stderr);
    assert_eq!(value["status"], "rejected");
}

#[test]
fn qwen_synthetic_command_rejects_cancellation_without_reporting_success() {
    let mut arguments = valid_arguments();
    arguments.push("--cancel-before".to_owned());
    let output = run_cli(&arguments);
    assert!(!output.status.success());
    let value = json_from(&output, &output.stderr);
    assert_eq!(value["status"], "rejected");
    assert_eq!(value["evaluated"], false);
    assert_eq!(value["fallback_used"], false);
    assert_eq!(
        value["error"]["code"],
        "qwen3moe_synthetic_generation_rejected"
    );
    assert!(value["error"]["message"]
        .as_str()
        .is_some_and(|message| message.contains("cancelled")));
    assert_no_unbounded_fields(&value);
}
