//! Retained-only full-graph qualification producer.
//!
//! The fixture source has no filesystem/checkpoint API after construction.
//! Only tensor math is substituted: attempt ownership, the native context,
//! live accounting, receipt emission, terminalization, and mandatory stop use
//! the same stream-domain producer as a future real bounded P1.

use f017_native::model::{execute_one_token, ModelConfig, NativeMlxBackend};
use f017_native::synthetic::{SyntheticFixture, SyntheticSource};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::Path;
use stream::{
    execute_inert_bounded_p1_once, BoundedP1Math, MlxContext, P1AttemptAuthority, P1RuntimeIdentity,
};

struct SyntheticFullGraph {
    source: SyntheticSource,
    config: ModelConfig,
    expected: u32,
    invocations: u32,
}
impl BoundedP1Math for SyntheticFullGraph {
    fn backend_id(&self) -> &'static str {
        "INERT_NO_CHECKPOINT_FULL_NATIVE_MODEL"
    }
    fn execute_one(&mut self, context: &MlxContext, prompt_token: u32) -> Result<u32, String> {
        if self.invocations != 0 {
            return Err("synthetic full graph attempted more than once".into());
        }
        self.invocations += 1;
        let result = execute_one_token(
            &mut self.source,
            &mut NativeMlxBackend { context },
            &self.config,
            prompt_token,
        )?;
        if result != self.expected {
            return Err(format!("synthetic token mismatch {result}"));
        }
        Ok(result)
    }
}

#[derive(Serialize)]
struct ResultDoc {
    schema: &'static str,
    fixture_sha256: String,
    authorization_id: String,
    attempt_id: String,
    prompt_token: u32,
    expected_token: u32,
    result_token: u32,
    generated_token_count: u32,
    mandatory_stop_observed: bool,
    terminal_state: String,
    historical_master_delta: u64,
    original_checkpoint_reads: u32,
    full_real_checkpoint_inference_executed: bool,
}

fn main() -> Result<(), String> {
    let args = std::env::args().collect::<Vec<_>>();
    if args.len() != 5 {
        return Err("usage: synthetic-p1 FIXTURE INERT_AUTHORITY STATE_ROOT SUMMARY".into());
    }
    let raw = fs::read(&args[1]).map_err(|e| e.to_string())?;
    let fixture: SyntheticFixture = f017_native::json::parse_json_no_duplicates(&raw)?;
    let (source, config, prompt, expected) = SyntheticSource::from_fixture(fixture)?;
    let authority_raw = fs::read(&args[2]).map_err(|e| e.to_string())?;
    let authority: P1AttemptAuthority =
        f017_native::json::parse_json_no_duplicates(&authority_raw)?;
    if authority.prompt_token != prompt || authority.expected_token != expected {
        return Err("fixture/authority token mismatch".into());
    }
    let runtime = P1RuntimeIdentity {
        mlx_version: "0.31.2".into(),
        mlx_c_version: "0.6.0".into(),
        architecture: "arm64".into(),
        machine_brand: "Apple M1 Ultra".into(),
        stream_origin: "EXPLICIT_OWNED_GPU_DEVICE".into(),
        native_handle_owned: true,
        deallocation_responsibility: "THIS_INVOCATION".into(),
    };
    let mut math = SyntheticFullGraph {
        source,
        config,
        expected,
        invocations: 0,
    };
    let receipt =
        execute_inert_bounded_p1_once(Path::new(&args[3]), &authority, runtime, &mut math)
            .map_err(|e| e.to_string())?;
    if math.invocations != 1 {
        return Err("synthetic execution census mismatch".into());
    }
    let doc = ResultDoc {
        schema: "pulsarmlx.f017.native-tiny-full-model-result/2.0.0",
        fixture_sha256: format!("{:x}", Sha256::digest(&raw)),
        authorization_id: receipt.authorization_id,
        attempt_id: receipt.attempt_id,
        prompt_token: receipt.prompt_token,
        expected_token: expected,
        result_token: receipt.result_token,
        generated_token_count: receipt.generated_token_count,
        mandatory_stop_observed: receipt.mandatory_stop_observed,
        terminal_state: receipt.terminal_state,
        historical_master_delta: receipt.historical_master_delta,
        original_checkpoint_reads: 0,
        full_real_checkpoint_inference_executed: false,
    };
    let path = Path::new(&args[4]);
    use std::io::Write;
    use std::os::unix::fs::OpenOptionsExt;
    let mut f = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o400)
        .open(path)
        .map_err(|e| e.to_string())?;
    let mut out = serde_json::to_vec(&doc).map_err(|e| e.to_string())?;
    out.push(b'\n');
    f.write_all(&out).map_err(|e| e.to_string())?;
    f.sync_all().map_err(|e| e.to_string())?;
    Ok(())
}
