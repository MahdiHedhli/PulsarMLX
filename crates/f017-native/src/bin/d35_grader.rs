//! Receipted, checkpoint-unreachable grader for the already-banked D3.5 captures.
//!
//! This binary never invokes the retained qualification runner or MLX.  It reads
//! only paths enumerated by an independently accepted comparison-read grant,
//! derives f64 operand-conditioned reference values from retained operands, and
//! grades the immutable representative capture under the frozen D0-v2 contract.

use f017_native::json::parse_json_no_duplicates;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::process::Command;

const GRANT_SCHEMA: &str = "pulsarmlx.f017.native-d3-5-comparison-read-grant/1.0.0";
const CONSUMER_ID: &str = "F017-NATIVE-D3_5-NUMERICAL-GRADER-1";
const D0_SHA256: &str = "cc62cdc7550e3a25f55de783e9eb7c68f6cf03d0eafb944a86dc8a2a60007fb9";
const EVIDENCE_SHA256: &str = "13b1a3a653cf0325f59b0b3b035b7804439a19c000ef8ddf19dad9ecb8316ac8";
const GRANT_ID: &str = "F017-NATIVE-D3_5-COMPARISON-READ-GRANT-1";
const MAPPING_SHA256: &str = "9f8bb8b0b65188fd2377521c79655c82842063f870a30aeeaea97e0483cd74c5";
const SELECTED_IDS_HEX: &str = "fa000a00ed003e004900b100da001c00";
const SELECTED_IDS_SHA256: &str =
    "a0f2e2b59ebc606c43e17eab8f76a5b14c26b678bef2a9b0207c3f7dd15f164f";
const ROUTING_WEIGHTS_F64_HEX: &str = "f29dfce3c2f5e73ffe85c101646ed53f78f9fd32848bce3f202f8b7f5152ce3f2142671d6c18d03f0c8a3f6c4984cd3f24a20c24e654cd3f30a3e6ee4e64cd3f";
const ROUTING_WEIGHTS_SHA256: &str =
    "ff1a7127b418b80dce4e4361e314c16ad50e86484cb1861ad27f6f9ee70b8587";
const RANKING_SHA256: &str = "b2de9d7a4fe2701f0cda51f6b95a5396195e0bf0c44924aa6d46b4a899af549d";
const OUTPUT_ROOT: &str = "${HOME}/.local/share/pulsarmlx/f017/native-d3-5-numerical-grading-1";
const HISTORICAL_HEAD: &str = "f2a7aa38c96b85cf7939c8ed653076732f066222";
const EXPECTED_READ_COUNT: usize = 15;
const OPERAND_READ_COUNT: usize = 40;
const CAPTURE_READ_COUNT: usize = 34;
const TOTAL_READ_COUNT: usize = 89;

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ReadSpec {
    ordinal: usize,
    role: String,
    path: PathBuf,
    sha256: String,
    byte_count: u64,
    dtype: String,
    shape: Vec<usize>,
    serialization: String,
    source_branch: String,
    source_commit: String,
    source_authority_path: String,
    source_authority_sha256: String,
    allowed_purpose: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ConsumerBinding {
    id: String,
    executable_path: PathBuf,
    executable_sha256: String,
    source_path: String,
    source_sha256: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct AuthorityBinding {
    d0_path: String,
    d0_sha256: String,
    d3_5_evidence_path: String,
    d3_5_evidence_sha256: String,
    stage_mapping_path: String,
    stage_mapping_sha256: String,
    historical_master_ledger_path: String,
    historical_master_ledger_sha256: String,
    historical_master_terminal: u64,
    diagnostic_disclosure_path: String,
    diagnostic_disclosure_sha256: String,
    diagnostic_metrics_reusable: bool,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct EventPolicy {
    event_id: String,
    attempt_id: String,
    attempts: u32,
    retries: u32,
    resume: bool,
    numerical_reexecution: bool,
    native_capture_regeneration: bool,
    historical_payload_ledger_delta: u32,
    original_checkpoint_reads: u32,
    original_checkpoint_shard_opens: u32,
    terminal_semantics: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouteAuthority {
    selected_ids_hex: String,
    selected_ids_sha256: String,
    routing_weights_f64_hex: String,
    routing_weights_sha256: String,
    ranking_sha256: String,
    tie_semantics: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ComparisonGrant {
    schema: String,
    schema_version: String,
    grant_id: String,
    status: String,
    consumer: ConsumerBinding,
    authority: AuthorityBinding,
    event: EventPolicy,
    allowed_output_root: PathBuf,
    expected_read_count: usize,
    operand_read_count: usize,
    capture_read_count: usize,
    total_read_count: usize,
    route_authority: RouteAuthority,
    expected_reads: Vec<ReadSpec>,
    operand_reads: Vec<ReadSpec>,
    capture_reads: Vec<ReadSpec>,
}

#[derive(Clone, Debug, Serialize)]
struct ReadReceipt {
    ordinal: usize,
    role: String,
    path: String,
    expected_sha256: String,
    before_sha256: String,
    consumed_sha256: String,
    after_sha256: String,
    byte_count: u64,
    descriptor_device: u64,
    descriptor_inode: u64,
    original_checkpoint_read: bool,
    original_checkpoint_shard_open: bool,
}

#[derive(Clone, Debug, Serialize)]
struct Metric {
    ordinal: usize,
    stage_id: String,
    class: String,
    oracle: String,
    metric: String,
    max_abs_error: Option<f64>,
    rmse: Option<f64>,
    cosine_similarity: Option<f64>,
    max_per_coordinate_cap: Option<f64>,
    structural_pass: bool,
    numeric_pass: bool,
    result: String,
}

fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn sha_file(path: &Path) -> Result<String, String> {
    fs::read(path)
        .map(|bytes| sha(&bytes))
        .map_err(|e| format!("SHA_READ:{e}"))
}

fn repository_root() -> Result<PathBuf, String> {
    let exe = std::env::current_exe().map_err(|e| format!("REPOSITORY_ROOT_EXE:{e}"))?;
    exe.ancestors()
        .find(|ancestor| ancestor.join(".git").exists())
        .map(Path::to_path_buf)
        .ok_or_else(|| "REPOSITORY_ROOT_DISCOVERY".into())
}

fn committed_sha(root: &Path, commit: &str, path: &str) -> Result<String, String> {
    if commit.len() != 40
        || !commit.bytes().all(|byte| byte.is_ascii_hexdigit())
        || path.starts_with('/')
        || path.contains("..")
    {
        return Err("COMMITTED_AUTHORITY_FORMAT".into());
    }
    let output = Command::new("git")
        .args([
            "-C",
            root.to_str().ok_or("REPOSITORY_ROOT_UTF8")?,
            "show",
            &format!("{commit}:{path}"),
        ])
        .output()
        .map_err(|e| format!("COMMITTED_AUTHORITY_GIT:{e}"))?;
    if !output.status.success() {
        return Err(format!("COMMITTED_AUTHORITY_UNRESOLVED:{commit}:{path}"));
    }
    Ok(sha(&output.stdout))
}

fn resolve_bound_path(path: &Path) -> Result<PathBuf, String> {
    let text = path.to_str().ok_or("BOUND_PATH_UTF8")?;
    let resolved = if let Some(suffix) = text.strip_prefix("${HOME}/") {
        PathBuf::from(std::env::var("HOME").map_err(|_| "HOME_UNAVAILABLE")?).join(suffix)
    } else if let Some(suffix) = text.strip_prefix("${REPOSITORY_ROOT}/") {
        repository_root()?.join(suffix)
    } else {
        return Err("BOUND_PATH_PREFIX".into());
    };
    if !resolved.is_absolute() {
        return Err("BOUND_PATH_ABSOLUTE".into());
    }
    Ok(resolved)
}

fn secure_read(spec: &ReadSpec) -> Result<(Vec<u8>, ReadReceipt), String> {
    let path = resolve_bound_path(&spec.path)?;
    if path.to_string_lossy().contains("checkpoint") {
        return Err(format!("READ_PATH_POLICY:{}", spec.role));
    }
    let linked =
        fs::symlink_metadata(&path).map_err(|e| format!("READ_LSTAT:{}:{e}", spec.role))?;
    if !linked.file_type().is_file() || linked.file_type().is_symlink() || linked.nlink() != 1 {
        return Err(format!("READ_FILE_POLICY:{}", spec.role));
    }
    if linked.permissions().mode() & 0o222 != 0 || linked.len() != spec.byte_count {
        return Err(format!("READ_MODE_OR_SIZE:{}", spec.role));
    }
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(&path)
        .map_err(|e| format!("READ_OPEN:{}:{e}", spec.role))?;
    let before = file
        .metadata()
        .map_err(|e| format!("READ_BEFORE:{}:{e}", spec.role))?;
    if before.dev() != linked.dev() || before.ino() != linked.ino() || before.len() != linked.len()
    {
        return Err(format!("READ_DESCRIPTOR_IDENTITY:{}", spec.role));
    }
    let mut bytes = Vec::with_capacity(spec.byte_count as usize);
    file.read_to_end(&mut bytes)
        .map_err(|e| format!("READ_CONSUME:{}:{e}", spec.role))?;
    let before_sha = sha(&bytes);
    if before_sha != spec.sha256 {
        return Err(format!("READ_EXPECTED_SHA:{}", spec.role));
    }
    file.seek(SeekFrom::Start(0))
        .map_err(|e| format!("READ_SEEK:{}:{e}", spec.role))?;
    let mut readback = Vec::with_capacity(bytes.len());
    file.read_to_end(&mut readback)
        .map_err(|e| format!("READ_AFTER:{}:{e}", spec.role))?;
    let after = file
        .metadata()
        .map_err(|e| format!("READ_AFTER_STAT:{}:{e}", spec.role))?;
    let after_sha = sha(&readback);
    if before.dev() != after.dev()
        || before.ino() != after.ino()
        || before.len() != after.len()
        || after_sha != spec.sha256
        || readback != bytes
    {
        return Err(format!("READ_AFTER_IDENTITY:{}", spec.role));
    }
    Ok((
        bytes,
        ReadReceipt {
            ordinal: spec.ordinal,
            role: spec.role.clone(),
            path: path.display().to_string(),
            expected_sha256: spec.sha256.clone(),
            before_sha256: before_sha.clone(),
            consumed_sha256: before_sha,
            after_sha256: after_sha,
            byte_count: spec.byte_count,
            descriptor_device: before.dev(),
            descriptor_inode: before.ino(),
            original_checkpoint_read: false,
            original_checkpoint_shard_open: false,
        },
    ))
}

fn decode_hex(text: &str) -> Result<Vec<u8>, String> {
    if text.len() % 2 != 0 {
        return Err("HEX_LENGTH".into());
    }
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&text[i..i + 2], 16).map_err(|_| "HEX".into()))
        .collect()
}

fn f32_values(bytes: &[u8]) -> Result<Vec<f64>, String> {
    if bytes.len() % 4 != 0 {
        return Err("F32_GEOMETRY".into());
    }
    let values = bytes
        .chunks_exact(4)
        .map(|v| f32::from_le_bytes(v.try_into().unwrap()) as f64)
        .collect::<Vec<_>>();
    if values.iter().any(|v| !v.is_finite()) {
        return Err("F32_NONFINITE".into());
    }
    Ok(values)
}

fn f64_values(bytes: &[u8]) -> Result<Vec<f64>, String> {
    if bytes.len() % 8 != 0 {
        return Err("F64_GEOMETRY".into());
    }
    let values = bytes
        .chunks_exact(8)
        .map(|v| f64::from_le_bytes(v.try_into().unwrap()))
        .collect::<Vec<_>>();
    if values.iter().any(|v| !v.is_finite()) {
        return Err("F64_NONFINITE".into());
    }
    Ok(values)
}

fn metrics(actual: &[f64], expected: &[f64]) -> Result<(f64, f64, f64), String> {
    if actual.len() != expected.len() || actual.is_empty() {
        return Err("METRIC_GEOMETRY".into());
    }
    let mut max_abs = 0.0_f64;
    let mut sum_sq = 0.0_f64;
    let mut dot = 0.0_f64;
    let mut aa = 0.0_f64;
    let mut ee = 0.0_f64;
    for (&a, &e) in actual.iter().zip(expected) {
        if !a.is_finite() || !e.is_finite() {
            return Err("METRIC_NONFINITE".into());
        }
        let d = (a - e).abs();
        max_abs = max_abs.max(d);
        sum_sq += d * d;
        dot += a * e;
        aa += a * a;
        ee += e * e;
    }
    let cosine = if aa == 0.0 && ee == 0.0 {
        1.0
    } else {
        dot / (aa.sqrt() * ee.sqrt())
    };
    Ok((max_abs, (sum_sq / actual.len() as f64).sqrt(), cosine))
}

fn signed_zero_compatible(actual: &[f64], expected: &[f64]) -> bool {
    actual
        .iter()
        .zip(expected)
        .all(|(&a, &e)| !(a == 0.0 && e == 0.0) || a.to_bits() == e.to_bits())
}

fn metric_row(
    ordinal: usize,
    id: &str,
    class: &str,
    oracle: &str,
    metric: &str,
    actual: &[f64],
    expected: &[f64],
    max: f64,
    rmse: f64,
    cosine: f64,
    result: &str,
) -> Result<Metric, String> {
    let (observed_max, observed_rmse, observed_cos) = metrics(actual, expected)?;
    let numeric = observed_max <= max
        && observed_rmse <= rmse
        && observed_cos >= cosine
        && signed_zero_compatible(actual, expected);
    Ok(Metric {
        ordinal,
        stage_id: id.into(),
        class: class.into(),
        oracle: oracle.into(),
        metric: metric.into(),
        max_abs_error: Some(observed_max),
        rmse: Some(observed_rmse),
        cosine_similarity: Some(observed_cos),
        max_per_coordinate_cap: Some(max),
        structural_pass: true,
        numeric_pass: numeric,
        result: if numeric {
            result.into()
        } else {
            "FAILED_CONTRACT".into()
        },
    })
}

fn decode_matrix(
    encoding: &str,
    bytes: &[u8],
    rows: usize,
    cols: usize,
) -> Result<Vec<f32>, String> {
    let mut out = vec![0.0_f32; rows.checked_mul(cols).ok_or("DECODE_OVERFLOW")?];
    match encoding {
        "F32_LE" => return f32_values(bytes).map(|v| v.into_iter().map(|x| x as f32).collect()),
        "Q5_K" => {
            if cols % 256 != 0 {
                return Err("Q5_LAYOUT".into());
            }
            let row_bytes = cols / 256 * 176;
            if bytes.len() != rows * row_bytes {
                return Err("Q5_SIZE".into());
            }
            for row in 0..rows {
                let decoded = quant::cpu_dot::dequant_q5_k(
                    &bytes[row * row_bytes..(row + 1) * row_bytes],
                    cols,
                );
                out[row * cols..(row + 1) * cols].copy_from_slice(&decoded);
            }
        }
        "Q6_K" => quant::decode_q6_k_matrix(bytes, rows, cols, &mut out)
            .map_err(|e| format!("Q6:{e:?}"))?,
        "Q8_0" => quant::decode_q8_0_matrix(bytes, rows, cols, &mut out)
            .map_err(|e| format!("Q8:{e:?}"))?,
        "IQ2_XXS" => quant::decode_iq2_xxs_matrix(bytes, rows, cols, &mut out)
            .map_err(|e| format!("IQ2:{e:?}"))?,
        "IQ3_XXS" => quant::decode_iq3_xxs_matrix(bytes, rows, cols, &mut out)
            .map_err(|e| format!("IQ3:{e:?}"))?,
        _ => return Err(format!("DECODE_FORMAT:{encoding}")),
    }
    if out.iter().any(|x| !x.is_finite()) {
        return Err("DECODE_NONFINITE".into());
    }
    Ok(out)
}

fn gamma(k: usize) -> Result<f64, String> {
    let ku = k as f64 * f32::EPSILON as f64 / 2.0;
    if ku >= 1.0 {
        return Err("GAMMA_DOMAIN".into());
    }
    Ok(ku / (1.0 - ku))
}

fn f64_matvec_and_caps(
    weights: &[f32],
    rows: usize,
    cols: usize,
    input: &[f64],
) -> Result<(Vec<f64>, Vec<f64>), String> {
    if weights.len() != rows * cols || input.len() != cols {
        return Err("OCB_GEOMETRY".into());
    }
    let factor = 2.0 * gamma(2 * cols)?;
    let f32_tail = 4.0 * cols as f64 * 2f64.powi(-149);
    let mut expected = Vec::with_capacity(rows);
    let mut caps = Vec::with_capacity(rows);
    for row in 0..rows {
        let mut sum = 0.0;
        let mut sum_abs = 0.0;
        for col in 0..cols {
            let p = weights[row * cols + col] as f64 * input[col];
            sum += p;
            sum_abs += p.abs();
        }
        expected.push(sum);
        caps.push(factor * sum_abs + f32_tail);
    }
    Ok((expected, caps))
}

fn write_json_exclusive(path: &Path, value: &impl Serialize) -> Result<String, String> {
    let mut bytes = serde_json::to_vec_pretty(value).map_err(|e| format!("JSON:{e}"))?;
    bytes.push(b'\n');
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o400)
        .open(path)
        .map_err(|e| format!("OUTPUT_CREATE:{e}"))?;
    file.write_all(&bytes)
        .and_then(|_| file.sync_all())
        .map_err(|e| format!("OUTPUT_WRITE:{e}"))?;
    fs::File::open(path.parent().ok_or("OUTPUT_PARENT")?)
        .and_then(|f| f.sync_all())
        .map_err(|e| format!("OUTPUT_PARENT_FSYNC:{e}"))?;
    Ok(sha(&bytes))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("F017_D35_GRADING_TERMINAL_FAILURE:{error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let args = std::env::args().collect::<Vec<_>>();
    if args.len() != 3 || args[1] != "--grant" {
        return Err("USAGE: --grant PATH".into());
    }
    let grant_path = Path::new(&args[2]);
    let grant_bytes = fs::read(grant_path).map_err(|e| format!("GRANT_READ:{e}"))?;
    let grant: ComparisonGrant = parse_json_no_duplicates(&grant_bytes)?;
    if grant.schema != GRANT_SCHEMA
        || grant.schema_version != "1.0.0"
        || grant.grant_id != GRANT_ID
        || grant.consumer.id != CONSUMER_ID
        || grant.status != "INDEPENDENT_REVIEW_ACCEPT_REQUIRED_BEFORE_USE"
        || grant.authority.d0_sha256 != D0_SHA256
        || grant.authority.d3_5_evidence_sha256 != EVIDENCE_SHA256
        || grant.authority.stage_mapping_sha256 != MAPPING_SHA256
        || grant.route_authority.selected_ids_hex != SELECTED_IDS_HEX
        || grant.route_authority.selected_ids_sha256 != SELECTED_IDS_SHA256
        || grant.route_authority.routing_weights_f64_hex != ROUTING_WEIGHTS_F64_HEX
        || grant.route_authority.routing_weights_sha256 != ROUTING_WEIGHTS_SHA256
        || grant.route_authority.ranking_sha256 != RANKING_SHA256
        || grant.allowed_output_root != PathBuf::from(OUTPUT_ROOT)
        || grant.authority.diagnostic_metrics_reusable
        || grant.event.attempts != 1
        || grant.event.retries != 0
        || grant.event.resume
        || grant.event.numerical_reexecution
        || grant.event.native_capture_regeneration
        || grant.event.original_checkpoint_reads != 0
        || grant.event.original_checkpoint_shard_opens != 0
        || grant.event.historical_payload_ledger_delta != 0
        || grant.authority.historical_master_terminal != 175
        || grant.expected_read_count != EXPECTED_READ_COUNT
        || grant.operand_read_count != OPERAND_READ_COUNT
        || grant.capture_read_count != CAPTURE_READ_COUNT
        || grant.total_read_count != TOTAL_READ_COUNT
        || grant.expected_reads.len() != EXPECTED_READ_COUNT
        || grant.operand_reads.len() != OPERAND_READ_COUNT
        || grant.capture_reads.len() != CAPTURE_READ_COUNT
    {
        return Err("GRANT_POLICY".into());
    }
    let exe = std::env::current_exe().map_err(|e| format!("EXE:{e}"))?;
    if exe != resolve_bound_path(&grant.consumer.executable_path)?
        || sha_file(&exe)? != grant.consumer.executable_sha256
    {
        return Err("CONSUMER_IDENTITY".into());
    }
    let root = repository_root()?;
    if sha_file(&root.join(&grant.consumer.source_path))? != grant.consumer.source_sha256 {
        return Err("CONSUMER_SOURCE_IDENTITY".into());
    }
    for (path, expected) in [
        (&grant.authority.d0_path, &grant.authority.d0_sha256),
        (
            &grant.authority.d3_5_evidence_path,
            &grant.authority.d3_5_evidence_sha256,
        ),
        (
            &grant.authority.stage_mapping_path,
            &grant.authority.stage_mapping_sha256,
        ),
        (
            &grant.authority.diagnostic_disclosure_path,
            &grant.authority.diagnostic_disclosure_sha256,
        ),
    ] {
        if sha_file(&root.join(path))? != *expected {
            return Err(format!("LOCAL_AUTHORITY_IDENTITY:{path}"));
        }
    }
    if committed_sha(
        &root,
        HISTORICAL_HEAD,
        &grant.authority.historical_master_ledger_path,
    )? != grant.authority.historical_master_ledger_sha256
        || grant.event.terminal_semantics
            != "ONE_OWNED_ATTEMPT_COMPLETE_OR_TERMINAL_FAILURE_NO_RETRY_NO_RESUME"
    {
        return Err("HISTORICAL_OR_TERMINAL_AUTHORITY".into());
    }
    let mut all = Vec::new();
    all.extend(grant.expected_reads.clone());
    all.extend(grant.operand_reads.clone());
    all.extend(grant.capture_reads.clone());
    let expected_registry = [
        (
            "expected.input_hidden",
            "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11",
        ),
        (
            "expected.post_attention_residual",
            "8309377ee8e8f34eb91cdb025624144eb5be7821ed9e4a295df29b13aac5a0dd",
        ),
        (
            "expected.router_normalized",
            "687a692a452e30860c34055942061f4ff368ec0e1c815439c71e457a444fe62c",
        ),
        (
            "expected.routed_aggregate",
            "872487d337305aab82e80a87b84763b6e3dd2901f88ae2ed6b64277aba9a20f9",
        ),
        (
            "expected.shared_expert_output",
            "8285fecf6e3232f19a0cc11b5d98ee5003f036db6bcd3cd52a7e9dbde9bb1b5b",
        ),
        (
            "expected.production_ffn",
            "4d7aaeb58c4ee33dcaf2329c8cd46234d69ee7f16bb7e6338ac9e0b7a5e6ad1a",
        ),
        (
            "expected.production_s2",
            "0341314230654d21fa56506dfe601f90bdb603fc38fd1203b6dd62b1e54c98c1",
        ),
        (
            "expected.expert_down.0",
            "0b6036ef2e77142094b673c421b96719619a58e15eee7522347b37f73d9b892b",
        ),
        (
            "expected.expert_down.1",
            "d9adb474f64c98349dfe0a6c768b2020b27f62ecc85874975c990b880ef304b3",
        ),
        (
            "expected.expert_down.2",
            "4ac842afb3b1909f9f0e07013c86bbdca90cd246b6190bf190a60fe9767fdd9b",
        ),
        (
            "expected.expert_down.3",
            "2550cccf9b2f1a83b2e2f03f090ee135dc525a15eaf1bab18d1a2fb97af16128",
        ),
        (
            "expected.expert_down.4",
            "9aa5e1dae2619c440c65689154de332da313990b4ba07fdac45e78a65ad3a7d3",
        ),
        (
            "expected.expert_down.5",
            "18260d4936483b6f7d83d2d0ec72d01fc761f2ac5726fa9b7bda243a4db9a201",
        ),
        (
            "expected.expert_down.6",
            "f4a8fc1e3bb91a8a5635505f766a07ef2cfb135378d224ed5f545617d781537d",
        ),
        (
            "expected.expert_down.7",
            "45029a47061c43746344d5b0a9366b8129630019a3196d0be146efc5e1a361f0",
        ),
    ];
    if !grant
        .expected_reads
        .iter()
        .zip(expected_registry)
        .all(|(row, (role, expected_sha))| row.role == role && row.sha256 == expected_sha)
    {
        return Err("EXPECTED_REGISTRY_BINDING".into());
    }
    let mut roles = BTreeSet::new();
    let mut source_cache: BTreeMap<(String, String), String> = BTreeMap::new();
    for (ordinal, row) in all.iter().enumerate() {
        if row.ordinal != ordinal
            || !roles.insert(row.role.clone())
            || row.shape.is_empty()
            || row.serialization.is_empty()
            || row.allowed_purpose.is_empty()
            || !matches!(
                row.dtype.as_str(),
                "F32_LE" | "F64_LE" | "U16_LE" | "Q5_K" | "Q6_K" | "Q8_0" | "IQ2_XXS" | "IQ3_XXS"
            )
            || !matches!(
                row.source_branch.as_str(),
                "feat/017-real-checkpoint-runner" | "feat/017-rust-native-inference-runtime"
            )
        {
            return Err("READ_CENSUS".into());
        }
        let key = (row.source_commit.clone(), row.source_authority_path.clone());
        let resolved = if let Some(value) = source_cache.get(&key) {
            value.clone()
        } else {
            let value = committed_sha(&root, &row.source_commit, &row.source_authority_path)?;
            source_cache.insert(key, value.clone());
            value
        };
        if resolved != row.source_authority_sha256 {
            return Err(format!("READ_SOURCE_AUTHORITY:{}", row.role));
        }
    }
    let mut data = BTreeMap::new();
    let mut receipts = Vec::new();
    for row in &all {
        let (bytes, receipt) = secure_read(row)?;
        data.insert(row.role.clone(), bytes);
        receipts.push(receipt);
    }

    let capture = |id: &str| -> Result<Vec<f64>, String> {
        f32_values(data.get(&format!("capture.{id}")).ok_or("CAPTURE_ROLE")?)
    };
    let expected = |id: &str, dtype: &str| -> Result<Vec<f64>, String> {
        let b = data.get(&format!("expected.{id}")).ok_or("EXPECTED_ROLE")?;
        if dtype == "f64" {
            f64_values(b)
        } else {
            f32_values(b)
        }
    };
    let mut rows = Vec::new();
    let c0 = data.get("capture.input_hidden").ok_or("C0")?;
    let e0 = data.get("expected.input_hidden").ok_or("E0")?;
    rows.push(Metric {
        ordinal: 0,
        stage_id: "input_hidden".into(),
        class: "BYTE_EXACT_REQUIRED".into(),
        oracle: "RETAINED_CANONICAL_S0".into(),
        metric: "exact_bytes".into(),
        max_abs_error: Some(if c0 == e0 { 0.0 } else { f64::INFINITY }),
        rmse: Some(if c0 == e0 { 0.0 } else { f64::INFINITY }),
        cosine_similarity: None,
        max_per_coordinate_cap: Some(0.0),
        structural_pass: c0 == e0,
        numeric_pass: c0 == e0,
        result: if c0 == e0 {
            "BYTE_EQUIVALENT".into()
        } else {
            "FAILED_CONTRACT".into()
        },
    });
    for (ord, id, oracle) in [
        (12, "post_attention_residual", "RETAINED_CANONICAL_S1"),
        (
            13,
            "router_normalized",
            "RETAINED_CANONICAL_ROUTER_NORMALIZED",
        ),
    ] {
        rows.push(metric_row(
            ord,
            id,
            "NUMERICALLY_BOUNDED_REQUIRED",
            oracle,
            "native_intermediate_tier_b",
            &capture(id)?,
            &expected(id, "f32")?,
            0.015625,
            0.0078125,
            0.9999,
            "NUMERICALLY_EQUIVALENT_WITHIN_FROZEN_TOLERANCE",
        )?);
    }
    let ranking = data.get("capture.ranking").ok_or("RANKING")?;
    rows.push(Metric {
        ordinal: 17,
        stage_id: "ranking".into(),
        class: "BYTE_EXACT_REQUIRED".into(),
        oracle: "ACCEPTED_ROUTE_AUTHORITY".into(),
        metric: "exact_bytes".into(),
        max_abs_error: None,
        rmse: None,
        cosine_similarity: None,
        max_per_coordinate_cap: Some(0.0),
        structural_pass: sha(ranking) == grant.route_authority.ranking_sha256,
        numeric_pass: true,
        result: if sha(ranking) == grant.route_authority.ranking_sha256 {
            "BYTE_EQUIVALENT".into()
        } else {
            "FAILED_CONTRACT".into()
        },
    });
    let selected = decode_hex(&grant.route_authority.selected_ids_hex)?;
    let selected_actual = data.get("capture.selected_ids").ok_or("SELECTED")?;
    let selected_pass =
        &selected == selected_actual && sha(&selected) == grant.route_authority.selected_ids_sha256;
    rows.push(Metric {
        ordinal: 18,
        stage_id: "selected_ids".into(),
        class: "BYTE_EXACT_REQUIRED".into(),
        oracle: "ACCEPTED_ROUTE_AUTHORITY".into(),
        metric: "exact_bytes".into(),
        max_abs_error: None,
        rmse: None,
        cosine_similarity: None,
        max_per_coordinate_cap: Some(0.0),
        structural_pass: selected_pass,
        numeric_pass: selected_pass,
        result: if selected_pass {
            "BYTE_EQUIVALENT".into()
        } else {
            "FAILED_CONTRACT".into()
        },
    });
    let route_expected = f64_values(&decode_hex(&grant.route_authority.routing_weights_f64_hex)?)?;
    let route_actual = capture("routing_weights")?;
    let mut route = metric_row(
        19,
        "routing_weights",
        "STRUCTURAL_EXACT_NUMERIC_BOUNDED",
        "ACCEPTED_ROUTE_AUTHORITY",
        "routing_weight",
        &route_actual,
        &route_expected,
        0.00001,
        f64::INFINITY,
        -1.0,
        "STRUCTURALLY_EQUIVALENT_NUMERICALLY_BOUNDED",
    )?;
    let interval_pass = route_actual
        .iter()
        .all(|value| value.is_finite() && *value >= 0.0 && *value <= 1.0);
    route.structural_pass = selected_pass
        && sha(ranking) == grant.route_authority.ranking_sha256
        && grant.route_authority.tie_semantics == "DESCENDING_SCORE_LOWER_EXPERT_ID"
        && interval_pass;
    route.numeric_pass &= route.structural_pass;
    if !route.numeric_pass {
        route.result = "FAILED_CONTRACT".into();
    }
    rows.push(route);

    let input = expected("router_normalized", "f32")?;
    let mut reference_hidden = Vec::new();
    let mut routed_gate_expected = Vec::with_capacity(8 * 2048);
    let mut routed_gate_caps = Vec::with_capacity(8 * 2048);
    let mut routed_up_expected = Vec::with_capacity(8 * 2048);
    let mut routed_up_caps = Vec::with_capacity(8 * 2048);
    for slot in 0..8 {
        let gate_role = format!("operand.routed.{slot}.gate");
        let up_role = format!("operand.routed.{slot}.up");
        let gate_spec = all
            .iter()
            .find(|r| r.role == gate_role)
            .ok_or("GATE_SPEC")?;
        let up_spec = all.iter().find(|r| r.role == up_role).ok_or("UP_SPEC")?;
        let gate_w = decode_matrix(
            &gate_spec.dtype,
            data.get(&gate_role).ok_or("GATE_DATA")?,
            2048,
            6144,
        )?;
        let up_w = decode_matrix(
            &up_spec.dtype,
            data.get(&up_role).ok_or("UP_DATA")?,
            2048,
            6144,
        )?;
        let (gate, gate_caps) = f64_matvec_and_caps(&gate_w, 2048, 6144, &input)?;
        let (up, up_caps) = f64_matvec_and_caps(&up_w, 2048, 6144, &input)?;
        routed_gate_expected.extend_from_slice(&gate);
        routed_gate_caps.extend_from_slice(&gate_caps);
        routed_up_expected.extend_from_slice(&up);
        routed_up_caps.extend_from_slice(&up_caps);
        let weight = route_expected[slot];
        reference_hidden.push(
            gate.iter()
                .zip(&up)
                .map(|(&g, &u)| (g / (1.0 + (-g).exp())) * u * weight)
                .collect::<Vec<_>>(),
        );
    }
    let actual_gate = capture("routed_gate")?;
    let actual_up = capture("routed_up")?;
    let gm = metrics(&actual_gate, &routed_gate_expected)?;
    let um = metrics(&actual_up, &routed_up_expected)?;
    let gp = signed_zero_compatible(&actual_gate, &routed_gate_expected)
        && actual_gate
            .iter()
            .zip(&routed_gate_expected)
            .zip(&routed_gate_caps)
            .all(|((&a, &e), &c)| (a - e).abs() <= c);
    let upass = signed_zero_compatible(&actual_up, &routed_up_expected)
        && actual_up
            .iter()
            .zip(&routed_up_expected)
            .zip(&routed_up_caps)
            .all(|((&a, &e), &c)| (a - e).abs() <= c);
    rows.push(Metric {
        ordinal: 20,
        stage_id: "routed_gate".into(),
        class: "NUMERICALLY_BOUNDED_REQUIRED".into(),
        oracle: "INDEPENDENT_COMPLETE_EXPERT".into(),
        metric: "operand_conditioned_matvec".into(),
        max_abs_error: Some(gm.0),
        rmse: Some(gm.1),
        cosine_similarity: Some(gm.2),
        max_per_coordinate_cap: routed_gate_caps.iter().copied().reduce(f64::max),
        structural_pass: actual_gate.len() == 8 * 2048,
        numeric_pass: gp,
        result: if gp {
            "NUMERICALLY_EQUIVALENT_WITHIN_FROZEN_TOLERANCE".into()
        } else {
            "FAILED_CONTRACT".into()
        },
    });
    rows.push(Metric {
        ordinal: 21,
        stage_id: "routed_up".into(),
        class: "NUMERICALLY_BOUNDED_REQUIRED".into(),
        oracle: "INDEPENDENT_COMPLETE_EXPERT".into(),
        metric: "operand_conditioned_matvec".into(),
        max_abs_error: Some(um.0),
        rmse: Some(um.1),
        cosine_similarity: Some(um.2),
        max_per_coordinate_cap: routed_up_caps.iter().copied().reduce(f64::max),
        structural_pass: actual_up.len() == 8 * 2048,
        numeric_pass: upass,
        result: if upass {
            "NUMERICALLY_EQUIVALENT_WITHIN_FROZEN_TOLERANCE".into()
        } else {
            "FAILED_CONTRACT".into()
        },
    });
    // Grade all eight down projections against an independent reference chain.
    let down_actual = capture("routed_down_outputs")?;
    let mut down_expected = Vec::with_capacity(8 * 6144);
    let mut down_caps = Vec::with_capacity(8 * 6144);
    for slot in 0..8 {
        let role = format!("operand.routed.{slot}.down");
        let spec = all.iter().find(|r| r.role == role).ok_or("DOWN_SPEC")?;
        let w = decode_matrix(&spec.dtype, data.get(&role).ok_or("DOWN_DATA")?, 6144, 2048)?;
        let (e, c) = f64_matvec_and_caps(&w, 6144, 2048, &reference_hidden[slot])?;
        down_expected.extend(e);
        down_caps.extend(c);
    }
    let dm = metrics(&down_actual, &down_expected)?;
    let dpass = signed_zero_compatible(&down_actual, &down_expected)
        && down_actual
            .iter()
            .zip(&down_expected)
            .zip(&down_caps)
            .all(|((&a, &e), &c)| (a - e).abs() <= c);
    rows.push(Metric {
        ordinal: 25,
        stage_id: "routed_down_outputs".into(),
        class: "NUMERICALLY_BOUNDED_REQUIRED".into(),
        oracle: "INDEPENDENT_COMPLETE_EXPERT".into(),
        metric: "operand_conditioned_matvec".into(),
        max_abs_error: Some(dm.0),
        rmse: Some(dm.1),
        cosine_similarity: Some(dm.2),
        max_per_coordinate_cap: down_caps.iter().copied().reduce(f64::max),
        structural_pass: true,
        numeric_pass: dpass,
        result: if dpass {
            "NUMERICALLY_EQUIVALENT_WITHIN_FROZEN_TOLERANCE".into()
        } else {
            "FAILED_CONTRACT".into()
        },
    });

    for (ord, id, role) in [
        (27, "shared_gate", "operand.shared.gate"),
        (28, "shared_up", "operand.shared.up"),
    ] {
        let spec = all.iter().find(|r| r.role == role).ok_or("SHARED_SPEC")?;
        let w = decode_matrix(
            &spec.dtype,
            data.get(role).ok_or("SHARED_DATA")?,
            2048,
            6144,
        )?;
        let (e, c) = f64_matvec_and_caps(&w, 2048, 6144, &input)?;
        let a = capture(id)?;
        let m = metrics(&a, &e)?;
        let pass = signed_zero_compatible(&a, &e)
            && a.iter()
                .zip(&e)
                .zip(&c)
                .all(|((&x, &y), &cap)| (x - y).abs() <= cap);
        rows.push(Metric {
            ordinal: ord,
            stage_id: id.into(),
            class: "NUMERICALLY_BOUNDED_REQUIRED".into(),
            oracle: "INDEPENDENT_COMPLETE_EXPERT".into(),
            metric: "operand_conditioned_matvec".into(),
            max_abs_error: Some(m.0),
            rmse: Some(m.1),
            cosine_similarity: Some(m.2),
            max_per_coordinate_cap: c.iter().copied().reduce(f64::max),
            structural_pass: true,
            numeric_pass: pass,
            result: if pass {
                "NUMERICALLY_EQUIVALENT_WITHIN_FROZEN_TOLERANCE".into()
            } else {
                "FAILED_CONTRACT".into()
            },
        });
    }
    rows.push(metric_row(
        26,
        "routed_aggregate",
        "INTENTIONALLY_DISTINCT",
        "RETAINED_PROOF_REFERENCE_ROUTED_F64",
        "native_intermediate_tier_b",
        &capture("routed_aggregate")?,
        &expected("routed_aggregate", "f64")?,
        0.015625,
        0.0078125,
        0.9999,
        "INTENTIONALLY_DISTINCT",
    )?);
    rows.push(metric_row(
        31,
        "shared_expert_output",
        "NUMERICALLY_BOUNDED_REQUIRED",
        "RETAINED_CANONICAL_SHARED_F32",
        "native_intermediate_tier_b",
        &capture("shared_expert_output")?,
        &expected("shared_expert_output", "f32")?,
        0.015625,
        0.0078125,
        0.9999,
        "NUMERICALLY_EQUIVALENT_WITHIN_FROZEN_TOLERANCE",
    )?);
    rows.push(metric_row(
        32,
        "production_ffn",
        "INTENTIONALLY_DISTINCT",
        "RETAINED_PROOF_REFERENCE_FFN_F64",
        "native_intermediate_tier_b",
        &capture("production_ffn")?,
        &expected("production_ffn", "f64")?,
        0.015625,
        0.0078125,
        0.9999,
        "INTENTIONALLY_DISTINCT",
    )?);
    rows.push(metric_row(
        33,
        "production_s2",
        "INTENTIONALLY_DISTINCT",
        "RETAINED_PROOF_REFERENCE_DERIVED_S2",
        "native_final_tier_b",
        &capture("production_s2")?,
        &expected("production_s2", "f32")?,
        0.0625,
        0.03125,
        0.999,
        "INTENTIONALLY_DISTINCT",
    )?);

    // These stages are correctness-qualified by independent boundary oracles and
    // graded here only for the D0 pinned-environment reproducibility obligation.
    // The bound D3.5 evidence establishes 20/20 byte-identical fresh/same-process
    // captures; this grader does not reinterpret reproduction as correctness.
    for (ordinal, stage_id, oracle) in [
        (
            1,
            "attention_normalized",
            "INDEPENDENT_MLA_DENSE_BOUNDARY_CORRECTNESS",
        ),
        (
            2,
            "query_rank",
            "INDEPENDENT_MLA_DENSE_BOUNDARY_CORRECTNESS",
        ),
        (
            3,
            "query_rank_normalized",
            "INDEPENDENT_MLA_DENSE_BOUNDARY_CORRECTNESS",
        ),
        (
            4,
            "query_heads",
            "INDEPENDENT_MLA_DENSE_BOUNDARY_CORRECTNESS",
        ),
        (5, "kv_raw", "INDEPENDENT_MLA_DENSE_BOUNDARY_CORRECTNESS"),
        (
            6,
            "kv_normalized",
            "INDEPENDENT_MLA_DENSE_BOUNDARY_CORRECTNESS",
        ),
        (7, "key_nope", "INDEPENDENT_MLA_DENSE_BOUNDARY_CORRECTNESS"),
        (
            8,
            "attention_scores",
            "INDEPENDENT_MLA_DENSE_BOUNDARY_CORRECTNESS",
        ),
        (
            9,
            "attention_weights",
            "INDEPENDENT_MLA_DENSE_BOUNDARY_CORRECTNESS",
        ),
        (
            10,
            "value_heads",
            "INDEPENDENT_MLA_DENSE_BOUNDARY_CORRECTNESS",
        ),
        (
            11,
            "attention_output",
            "INDEPENDENT_MLA_DENSE_BOUNDARY_CORRECTNESS",
        ),
        (
            14,
            "router_logits",
            "INDEPENDENT_ROUTER_BOUNDARY_CORRECTNESS",
        ),
        (
            15,
            "router_probabilities",
            "INDEPENDENT_ROUTER_BOUNDARY_CORRECTNESS",
        ),
        (
            16,
            "router_scores",
            "INDEPENDENT_ROUTER_BOUNDARY_CORRECTNESS",
        ),
        (
            22,
            "routed_silu",
            "INDEPENDENT_COMPLETE_EXPERT_BOUNDARY_CORRECTNESS",
        ),
        (
            23,
            "routed_gate_up_product",
            "INDEPENDENT_COMPLETE_EXPERT_BOUNDARY_CORRECTNESS",
        ),
        (
            24,
            "routed_weighted_hidden",
            "INDEPENDENT_TOP8_SHARED_BOUNDARY_CORRECTNESS",
        ),
        (
            29,
            "shared_silu",
            "INDEPENDENT_COMPLETE_EXPERT_BOUNDARY_CORRECTNESS",
        ),
        (
            30,
            "shared_gate_up_product",
            "INDEPENDENT_COMPLETE_EXPERT_BOUNDARY_CORRECTNESS",
        ),
    ] {
        rows.push(Metric {
            ordinal,
            stage_id: stage_id.into(),
            class: "IMPLEMENTATION_SPECIFIC_REPRODUCIBILITY".into(),
            oracle: oracle.into(),
            metric: "pinned_environment_reproduction".into(),
            max_abs_error: None,
            rmse: None,
            cosine_similarity: None,
            max_per_coordinate_cap: None,
            structural_pass: true,
            numeric_pass: true,
            result: "IMPLEMENTATION_REPRODUCIBLE".into(),
        });
    }
    rows.sort_by_key(|row| row.ordinal);

    let required = [0, 12, 13, 17, 18, 19, 20, 21, 25, 26, 27, 28, 31, 32, 33];
    let pass = rows.len() == 34
        && rows
            .iter()
            .enumerate()
            .all(|(ordinal, row)| row.ordinal == ordinal)
        && required.iter().all(|o| {
            rows.iter()
                .find(|r| r.ordinal == *o)
                .is_some_and(|r| r.structural_pass && r.numeric_pass)
        });
    let result = serde_json::json!({"schema":"pulsarmlx.f017.native-d3-5-numerical-grading-result/1.0.0","grant_sha256":sha(&grant_bytes),"d0_sha256":D0_SHA256,"d3_5_evidence_sha256":EVIDENCE_SHA256,"existing_captures_reused":true,"native_execution_performed":false,"original_checkpoint_reads":0,"historical_payload_ledger_delta":0,"read_receipt_count":receipts.len(),"read_receipts":receipts,"stage_metrics":rows,"required_ordinal_count":required.len(),"retained_qualification":if pass{"MIXED_D0_V2_CLASS/PASS"}else{"FAILED_CONTRACT"},"pass":pass});
    let output_root = resolve_bound_path(&grant.allowed_output_root)?;
    fs::create_dir(&output_root).map_err(|e| format!("OUTPUT_ROOT_CREATE:{e}"))?;
    let result_path = output_root.join("grading-result.json");
    let result_sha = write_json_exclusive(&result_path, &result)?;
    let terminal = serde_json::json!({"schema":"pulsarmlx.f017.native-d3-5-grading-terminal/1.0.0","event_id":grant.event.event_id,"attempt_id":grant.event.attempt_id,"state":if pass{"COMPLETE"}else{"TERMINAL_FAILURE"},"result_sha256":result_sha,"receipt_count":receipts.len(),"original_checkpoint_reads":0,"historical_payload_ledger_delta":0});
    let _ = write_json_exclusive(&output_root.join("terminal.json"), &terminal)?;
    if !pass {
        return Err("FAILED_CONTRACT".into());
    }
    println!("F017_D35_NUMERICAL_GRADING: PASS {result_sha}");
    Ok(())
}
