//! `f017-native-generate`: bounded native text generation for GLM-5.2.
//!
//! Everything from the prompt text to the emitted answer runs in this
//! process: the GGUF tokenizer, the chat template, the checkpoint identity
//! rehash, prefill, decode and teardown. No Python is started and no Python
//! module is imported; the Python tooling in `scripts/research` is the
//! independent reference and test harness, never part of this path.
//!
//! The generated answer goes to stdout. Everything else - identity, phase
//! timings, token counts, finish reason, memory - goes to stderr as one JSON
//! object, so piping stdout gives exactly the model's text.
//!
//! Exit codes: 0 success, 2 usage or admission refusal, 3 identity or
//! verification failure, 4 runtime failure, 5 cancelled.

use f017_native::loader::{load_plan_only, SecureCheckpoint};
use f017_native::model::{ModelConfig, NativeMlxBackend, ScalarBackend};
use f017_native::session::{generate, logits_sha256, FinishReason, IncrementalText, Limits};
use f017_native::temporal::{execute_prefix_no_cache, RopePairing, SequenceState, TemporalConfig};
use serde_json::json;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Instant;
use tokenizer::{ChatMarkers, Tokenizer};

static CANCELLED: AtomicBool = AtomicBool::new(false);

extern "C" fn on_interrupt(_signal: i32) {
    CANCELLED.store(true, Ordering::Relaxed);
}

const USAGE: &str = "\
usage: f017-native-generate --model DIR [options]

  --model DIR              checkpoint directory, opened read-only
  --manifest FILE          shard identity record
                           (default docs/validation/glm52-checkpoint.json)
  --catalog FILE           tensor catalog
                           (default docs/research/glm52/raw/f016-c01-catalog-0001.json)
  --prompt TEXT            prompt text
  --prompt-file FILE       read the prompt from a file
  --prompt-stdin           read the prompt from stdin
  --raw-tokens LIST        DIAGNOSTIC ONLY: comma-separated token ids instead
                           of text; bypasses the tokenizer and the template
  --no-chat-template       encode the prompt text without the chat template
  --max-tokens N           bounded output length (default 8)
  --max-prompt-tokens N    refuse longer prompts (default 512)
  --max-positions N        retained-position ceiling (default 2048)
  --preflight-only         check identity metadata, the tokenizer and the
                           rendered prompt, then stop; no shard is rehashed
  --verify-only            rehash every shard, then stop
  --rope-pairing P         neox-half-split (default) or interleaved; which one
                           a GGUF conversion produced is a property of the
                           checkpoint, so it is selectable and reported
  --compare-no-cache       also recompute every position from a fresh state and
                           compare logits digests, to check the retained cache
                           against an implementation that cannot carry one
  --cpu                    scalar backend instead of the MLX GPU backend
  --help

Generation is greedy and deterministic; there is no sampling option.";

struct Arguments {
    model: PathBuf,
    manifest: PathBuf,
    catalog: PathBuf,
    prompt: Option<String>,
    raw_tokens: Option<Vec<u32>>,
    chat_template: bool,
    max_tokens: usize,
    max_prompt_tokens: usize,
    max_positions: usize,
    verify_only: bool,
    preflight_only: bool,
    rope_pairing: RopePairing,
    compare_no_cache: bool,
    cpu: bool,
}

fn parse_arguments() -> Result<Arguments, String> {
    let mut arguments = Arguments {
        model: PathBuf::new(),
        manifest: PathBuf::from("docs/validation/glm52-checkpoint.json"),
        catalog: PathBuf::from("docs/research/glm52/raw/f016-c01-catalog-0001.json"),
        prompt: None,
        raw_tokens: None,
        chat_template: true,
        max_tokens: 8,
        max_prompt_tokens: 512,
        max_positions: 2048,
        verify_only: false,
        preflight_only: false,
        rope_pairing: RopePairing::NeoxHalfSplit,
        compare_no_cache: false,
        cpu: false,
    };
    let mut iterator = std::env::args().skip(1);
    let mut prompt_sources = 0;
    while let Some(flag) = iterator.next() {
        let mut value = || {
            iterator
                .next()
                .ok_or_else(|| format!("{flag} needs a value"))
        };
        match flag.as_str() {
            "--help" | "-h" => {
                println!("{USAGE}");
                std::process::exit(0);
            }
            "--model" => arguments.model = PathBuf::from(value()?),
            "--manifest" => arguments.manifest = PathBuf::from(value()?),
            "--catalog" => arguments.catalog = PathBuf::from(value()?),
            "--prompt" => {
                arguments.prompt = Some(value()?);
                prompt_sources += 1;
            }
            "--prompt-file" => {
                let path = value()?;
                arguments.prompt =
                    Some(std::fs::read_to_string(&path).map_err(|e| format!("{path}: {e}"))?);
                prompt_sources += 1;
            }
            "--prompt-stdin" => {
                let mut text = String::new();
                std::io::stdin()
                    .read_to_string(&mut text)
                    .map_err(|e| e.to_string())?;
                arguments.prompt = Some(text);
                prompt_sources += 1;
            }
            "--raw-tokens" => {
                let raw = value()?;
                let mut tokens = Vec::new();
                for item in raw.split(',') {
                    tokens.push(
                        item.trim()
                            .parse::<u32>()
                            .map_err(|_| format!("not a token id: {item}"))?,
                    );
                }
                arguments.raw_tokens = Some(tokens);
                prompt_sources += 1;
            }
            "--no-chat-template" => arguments.chat_template = false,
            "--max-tokens" => {
                arguments.max_tokens = value()?.parse().map_err(|_| "--max-tokens")?
            }
            "--max-prompt-tokens" => {
                arguments.max_prompt_tokens = value()?.parse().map_err(|_| "--max-prompt-tokens")?
            }
            "--max-positions" => {
                arguments.max_positions = value()?.parse().map_err(|_| "--max-positions")?
            }
            "--verify-only" => arguments.verify_only = true,
            "--preflight-only" => arguments.preflight_only = true,
            "--compare-no-cache" => arguments.compare_no_cache = true,
            "--rope-pairing" => {
                arguments.rope_pairing = match value()?.as_str() {
                    "neox-half-split" => RopePairing::NeoxHalfSplit,
                    "interleaved" => RopePairing::Interleaved,
                    other => return Err(format!("unknown rope pairing {other}")),
                }
            }
            "--cpu" => arguments.cpu = true,
            other => return Err(format!("unknown flag {other}")),
        }
    }
    if arguments.model.as_os_str().is_empty() {
        return Err("--model is required".into());
    }
    if prompt_sources > 1 {
        return Err("give exactly one prompt source".into());
    }
    if prompt_sources == 0 && !(arguments.verify_only || arguments.preflight_only) {
        return Err("a prompt is required unless --verify-only".into());
    }
    Ok(arguments)
}

/// Cheap refusals first: nothing here rehashes 222 GB.
fn preflight(arguments: &Arguments) -> Result<(serde_json::Value, Tokenizer, ModelConfig), String> {
    let metadata = std::fs::symlink_metadata(&arguments.model)
        .map_err(|e| format!("{}: {e}", arguments.model.display()))?;
    if metadata.file_type().is_symlink() {
        return Err(format!(
            "{} is a symlink; give the canonical checkpoint directory",
            arguments.model.display()
        ));
    }
    if !metadata.is_dir() {
        return Err(format!("{} is not a directory", arguments.model.display()));
    }
    let (manifest, catalog) = load_plan_only(&arguments.manifest, &arguments.catalog)?;
    let config = ModelConfig::glm52();
    config.validate()?;
    if catalog.architecture != "glm-dsa" {
        return Err(format!(
            "unsupported architecture {}: this runtime implements glm-dsa only",
            catalog.architecture
        ));
    }
    let first = manifest
        .files
        .first()
        .ok_or("manifest has no shards")?
        .filename
        .clone();
    let head = arguments.model.join(&first);
    if !head.is_file() {
        return Err(format!("missing shard {}", head.display()));
    }
    let bytes = std::fs::read(&head).map_err(|e| format!("{}: {e}", head.display()))?;
    let gguf = gguf::Gguf::parse(&bytes).map_err(|e| format!("{}: {e:?}", head.display()))?;
    if gguf.architecture() != Some("glm-dsa") {
        return Err(format!(
            "shard architecture {:?} is not glm-dsa",
            gguf.architecture()
        ));
    }
    let expect = |suffix: &str, want: u64| -> Result<(), String> {
        let got = gguf
            .arch_meta(suffix)
            .and_then(|value| value.as_u64())
            .ok_or_else(|| format!("missing metadata {suffix}"))?;
        if got != want {
            return Err(format!("metadata {suffix} is {got}, expected {want}"));
        }
        Ok(())
    };
    expect("block_count", config.layer_count as u64)?;
    expect("embedding_length", config.hidden as u64)?;
    expect("vocab_size", config.vocab as u64)?;
    expect("attention.head_count", config.heads as u64)?;
    expect("attention.kv_lora_rank", config.kv_rank as u64)?;
    expect("attention.q_lora_rank", config.q_rank as u64)?;
    expect(
        "attention.key_length_mla",
        (config.qk_nope + config.qk_rope) as u64,
    )?;
    expect("attention.value_length_mla", config.value_dim as u64)?;
    expect("rope.dimension_count", config.qk_rope as u64)?;
    let indexer_top_k = gguf
        .arch_meta("attention.indexer.top_k")
        .and_then(|value| value.as_u64())
        .ok_or("missing metadata attention.indexer.top_k")? as usize;
    let tokenizer = Tokenizer::from_gguf(&gguf)
        .map_err(|error| format!("tokenizer unavailable in this checkpoint: {error:?}"))?;
    if tokenizer.n_vocab() != config.vocab {
        return Err(format!(
            "tokenizer vocabulary {} does not match the model's {}",
            tokenizer.n_vocab(),
            config.vocab
        ));
    }
    let identity = json!({
        "model_directory": arguments.model.display().to_string(),
        "architecture": "glm-dsa",
        "name": gguf.metadata.get("general.name").and_then(|value| value.as_str()),
        "checkpoint_set_sha256": manifest.checkpoint_set_sha256,
        "shards": manifest.files.len(),
        "total_bytes": manifest.total_bytes,
        "tensors": catalog.tensor_count,
        "vocabulary": tokenizer.n_vocab(),
        "indexer_top_k": indexer_top_k,
        "quantization_file_type": gguf.metadata.get("general.file_type").and_then(|value| value.as_u64()),
    });
    Ok((identity, tokenizer, config))
}

fn render_prompt(
    arguments: &Arguments,
    tokenizer: &Tokenizer,
) -> Result<(Vec<u32>, Vec<u32>, &'static str), String> {
    if let Some(tokens) = &arguments.raw_tokens {
        let markers = ChatMarkers::resolve(tokenizer).ok();
        let stops = markers
            .as_ref()
            .map(|m| {
                (0..tokenizer.n_vocab() as u32)
                    .filter(|id| m.is_stop(*id))
                    .collect()
            })
            .unwrap_or_default();
        return Ok((tokens.clone(), stops, "RAW_TOKEN_DIAGNOSTIC"));
    }
    let text = arguments.prompt.clone().unwrap_or_default();
    if !arguments.chat_template {
        // The model's own terminals do not depend on the chat template. An
        // empty stop set here meant a raw-text run could only ever end on
        // max-tokens, which is what stage B1 ran into.
        let ids = tokenizer.encode(&text);
        return Ok((ids, tokenizer.stop_ids.clone(), "RAW_TEXT_NO_TEMPLATE"));
    }
    let markers = ChatMarkers::resolve(tokenizer)
        .map_err(|error| format!("this checkpoint has no supported chat template: {error:?}"))?;
    let mut ids = markers.prologue();
    ids.extend(markers.render_user(tokenizer, &text));
    ids.extend(markers.open_assistant(tokenizer));
    let stops = (0..tokenizer.n_vocab() as u32)
        .filter(|id| markers.is_stop(*id))
        .collect::<Vec<_>>();
    Ok((ids, stops, "CHAT_TEMPLATE"))
}

/// Re-execute every prefix from a fresh state and compare logits digests with
/// the cached run.
///
/// This must use the same backend as the cached generation. Running it on the
/// scalar CPU path while the cached run used MLX compares two arithmetics, not
/// two cache strategies, and reports a disagreement that means nothing.
fn compare_no_cache(
    checkpoint: &mut f017_native::loader::SecureCheckpoint,
    backend: &mut impl f017_native::model::MatvecBackend,
    config: &TemporalConfig,
    prompt: &[u32],
    cached: &[String],
) -> Result<serde_json::Value, String> {
    let mut rows = Vec::new();
    let mut mismatches = 0usize;
    for length in 1..=prompt.len().min(cached.len()) {
        let (_, logits) = execute_prefix_no_cache(checkpoint, backend, config, &prompt[..length])?;
        let recomputed = logits_sha256(&logits);
        let agrees = recomputed == cached[length - 1];
        if !agrees {
            mismatches += 1;
        }
        rows.push(json!({
            "position": length - 1,
            "cached_logits_sha256": cached[length - 1],
            "recomputed_logits_sha256": recomputed,
            "agrees": agrees,
        }));
    }
    Ok(json!({
        "method": "each prefix re-executed from a fresh SequenceState on the same backend as the cached run",
        "positions_compared": rows.len(),
        "mismatches": mismatches,
        "result": if mismatches == 0 { "AGREE" } else { "DISAGREE" },
        "meaning": "an implementation that cannot hold a cache reproduces the cached path's logits exactly",
        "positions": rows,
    }))
}

fn run() -> Result<i32, (i32, String)> {
    unsafe {
        libc::signal(
            libc::SIGINT,
            on_interrupt as *const () as libc::sighandler_t,
        );
    }
    let arguments = parse_arguments().map_err(|error| (2, error))?;
    let started = Instant::now();
    let (identity, tokenizer, model) = preflight(&arguments).map_err(|error| (3, error))?;
    let preflight_seconds = started.elapsed().as_secs_f64();

    let indexer_top_k = identity["indexer_top_k"].as_u64().unwrap_or(0) as usize;
    let mut config = TemporalConfig::glm52();
    config.model = model.clone();
    config.indexer_top_k = indexer_top_k;
    config.rope_pairing = arguments.rope_pairing;
    config.max_positions = arguments.max_positions.min(indexer_top_k);
    config.validate().map_err(|error| (2, error))?;
    let limits = Limits {
        max_prompt_tokens: arguments.max_prompt_tokens,
        max_output_tokens: arguments.max_tokens,
    };
    limits.validate(&config).map_err(|error| (2, error))?;

    let (prompt, stops, prompt_mode) = render_prompt(&arguments, &tokenizer).map_err(|e| (2, e))?;
    if prompt.is_empty() && !(arguments.verify_only || arguments.preflight_only) {
        return Err((2, "the prompt encoded to no tokens".into()));
    }

    let mut diagnostics = json!({
        "schema": "pulsarmlx.f017.native-generate-diagnostics/1.0.0",
        "identity": identity,
        "prompt_mode": prompt_mode,
        "prompt_tokens": prompt.len(),
        "stop_token_ids": stops,
        "max_output_tokens": arguments.max_tokens,
        "max_positions": config.max_positions,
        "rope_pairing": format!("{:?}", config.rope_pairing),
        "attention_softmax_scale": config.attention_softmax_scale,
        "backend": if arguments.cpu { "SCALAR_CPU" } else { "NATIVE_RUST_MLX_GPU" },
        "python_inference_process": false,
        "phases_seconds": {
            "preflight": preflight_seconds,
        },
    });

    if arguments.preflight_only {
        diagnostics["result"] = json!("PREFLIGHT_PASS");
        diagnostics["prompt_token_ids"] = json!(prompt);
        eprintln!("{diagnostics}");
        return Ok(0);
    }

    let verify_start = Instant::now();
    let (manifest, catalog) =
        load_plan_only(&arguments.manifest, &arguments.catalog).map_err(|e| (3, e))?;
    let root = arguments
        .model
        .canonicalize()
        .map_err(|error| (3, error.to_string()))?;
    let mut checkpoint = SecureCheckpoint::open(&root, manifest, catalog).map_err(|e| (3, e))?;
    let verification_seconds = verify_start.elapsed().as_secs_f64();
    diagnostics["verified_checkpoint_set_sha256"] = json!(checkpoint.checkpoint_set_sha256);
    diagnostics["phases_seconds"]["checkpoint_identity_verification"] = json!(verification_seconds);

    if arguments.verify_only {
        diagnostics["result"] = json!("VERIFIED");
        eprintln!("{diagnostics}");
        return Ok(0);
    }

    let mut state = SequenceState::new(&config);
    let mut stdout = std::io::stdout();
    let mut text = IncrementalText::new(|ids: &[u32]| tokenizer.decode(ids));
    let mut sink = |bytes: &[u8]| {
        if !bytes.is_empty() {
            let _ = stdout.write_all(bytes);
            let _ = stdout.flush();
        }
    };
    let mut comparison: Option<serde_json::Value> = None;
    let outcome = if arguments.cpu {
        let produced = generate(
            &mut checkpoint,
            &mut ScalarBackend,
            &config,
            &mut state,
            &prompt,
            limits,
            &stops,
            &mut text,
            &mut sink,
            &CANCELLED,
        );
        if arguments.compare_no_cache {
            if let Ok(ref outcome) = produced {
                comparison = Some(
                    compare_no_cache(
                        &mut checkpoint,
                        &mut ScalarBackend,
                        &config,
                        &prompt,
                        &outcome.position_logits_sha256,
                    )
                    .map_err(|error| (4, error))?,
                );
            }
        }
        produced
    } else {
        let context = stream::MlxContext::new(stream::MlxDevice::Gpu, stream::MlxStreamMode::Owned)
            .map_err(|error| (4, error))?;
        let mut backend = NativeMlxBackend { context: &context };
        let result = generate(
            &mut checkpoint,
            &mut backend,
            &config,
            &mut state,
            &prompt,
            limits,
            &stops,
            &mut text,
            &mut sink,
            &CANCELLED,
        );
        if arguments.compare_no_cache {
            if let Ok(ref outcome) = result {
                comparison = Some(
                    compare_no_cache(
                        &mut checkpoint,
                        &mut backend,
                        &config,
                        &prompt,
                        &outcome.position_logits_sha256,
                    )
                    .map_err(|error| (4, error))?,
                );
            }
        }
        context.synchronize().map_err(|error| (4, error))?;
        result
    }
    .map_err(|error| (4, error))?;
    if let Some(value) = comparison {
        diagnostics["no_cache_comparison"] = value;
    }

    let cleanup_start = Instant::now();
    drop(checkpoint);
    state.reset();
    let cleanup_seconds = cleanup_start.elapsed().as_secs_f64();

    diagnostics["generation"] = serde_json::to_value(&outcome).unwrap_or(json!(null));
    diagnostics["decode_tokens_per_second"] = match outcome.decode_tokens_per_second() {
        Some(rate) => json!(rate),
        None => json!(null),
    };
    diagnostics["phases_seconds"]["prefill"] = json!(outcome.prefill_seconds);
    diagnostics["phases_seconds"]["first_token"] = json!(outcome.first_token_seconds);
    diagnostics["phases_seconds"]["decode_after_first"] = json!(outcome.decode_seconds);
    diagnostics["phases_seconds"]["cleanup"] = json!(cleanup_seconds);
    diagnostics["result"] = json!("COMPLETE");
    println!();
    eprintln!("{diagnostics}");
    Ok(match outcome.finish_reason {
        FinishReason::Cancelled => 5,
        _ => 0,
    })
}

fn main() {
    match run() {
        Ok(code) => std::process::exit(code),
        Err((code, message)) => {
            eprintln!(
                "{}",
                json!({
                    "schema": "pulsarmlx.f017.native-generate-diagnostics/1.0.0",
                    "result": "REFUSED",
                    "exit_code": code,
                    "error": message,
                })
            );
            std::process::exit(code);
        }
    }
}
