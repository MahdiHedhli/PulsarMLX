//! Owned by API-08. OpenAI Chat Completions: request handling, SSE chunks and the
//! non-stream collector, on the inference driver of API-07.
//!
//! # One request
//!
//! [`OpenAiDialect`] implements [`Dialect`]: the driver has already applied its overloaded
//! gate, removed every top-level key beginning with `_` (deviation SEC-6.1) and expanded
//! attachments. Then, in the donor's order (`_openai`):
//!
//! 1. the shared Chat settings fill what the request leaves out (`with_shared`), and the
//!    monitor's tag is `web` for `strata_resume: true`, else `openai`;
//! 2. `check_request` checks the sampling fields, `logit_bias`, `ablate`, `ignore_eos` and
//!    `logprobs` against the engine's capabilities (a `ValueError` is a 400);
//! 3. the prompt step's conversion ([`PromptBuilder::convert`], `openai_to_messages`)
//!    converts the messages;
//! 4. the answer budget is `int(max_completion_tokens or max_tokens or 0)`; the trace marks
//!    `prepare_start`; the prompt step's preparation ([`PromptBuilder::prepare`],
//!    `Service.prepare`) builds the prompt with `with_shared`'s internal flags, and the
//!    context rule of the turn driver applies (`max_new`);
//! 5. the turn request is built: the prompt, the budget, the sampling the run's defaults,
//!    the shared settings and the request give together, the logit biases, the logprobs
//!    asked for and the end-of-turn ids; the output stage ([`OutputPipeline`]) and the chunk
//!    writer are started, and the completion's id and time are drawn.
//!
//! The answer is a stream of chunks when `stream` is truthy, else one `chat.completion`
//! body from the collector. `model`, `n`, `user` and `stream_options` are ignored, as the
//! donor ignores them; the `model` field of every chunk is the configured model name, which
//! for the scripted engine is `pulsar-console-synthetic` (deviation PLAN-2).
//!
//! # Seams
//!
//! The M1 subset is plain content (the approved plan's "chat completions for plain
//! content"). The prompt step is the synthetic stand-in of lead decision LD45
//! ([`SyntheticPrompt`]) until the prompt packages of M2 implement [`PromptBuilder`]
//! (PRM-03, PRM-06, PRM-08, PRM-11, PRM-16). The output stage is [`PlainOutput`] until
//! the output pipeline of M2 implements [`OutputPipeline`] with the parsers of PRM-06,
//! PRM-09 and PRM-16 (reasoning, tool calls, markers inside code); the chunk writer
//! already renders their events ([`AnswerEvent`]). The MCP tools of `strata_mcp` are
//! RSP-11's (M6): with no MCP hub the donor ignores the flag, as here. A streamed web-app
//! answer that outlives its connection (`strata_resume` with `stream`, the donor's
//! `StreamJob`) is API-10's: here it streams on its connection without the client watch.
//! JSON mode holds the answer and sends `json_from_text` of it at the end, as the donor's
//! chunks do; the JSON instruction the donor adds to the prompt arrives with PRM-06.
//!
//! Nothing here admits an engine: every engine reaches the dialect through the turn
//! driver's admission step and its synthetic-only guard. Nothing here is qualified beyond
//! synthetic backends.
//!
//! Behavior reference: project-maya serve/server.py:6566-6624, 4909-4930, 4933-5008,
//! 5204-5246 and 571-596 at 7e68a30f.

mod chunks;
mod collect;
mod events;
mod json_mode;
mod logprobs;
mod output;
mod prompt;
mod turn;

use std::sync::{Arc, PoisonError, RwLock};

use console_core::engine::{GenerationRequest, Penalties, RequestId, Sampling};
use console_core::request::{
    check_request, client_stop_strings, openai_max_tokens, with_shared, CheckContext,
    Dialect as SharedDialect, SharedDefaults,
};
use console_core::sampling::{effective_sampling, KeyValue, ResolvedSampling};
use console_core::turn::TurnRequest;
use console_pyjson::loads::truthy;
use console_tokenizer::bpe::Tokenize;
use serde_json::{Map, Value};

use crate::inference::{
    AttachDialect, DebugRequest, Dialect, InferenceError, PrepareCall, PrepareFuture, PreparedTurn,
};

pub use chunks::{
    data_frame, error_frames, timings_value, wire_finish, ChunkStamp, ChunkWriter, FixedStamp,
    SystemStamp, DONE_FRAME,
};
pub use collect::collect;
pub use events::{AnswerEvent, ToolCall};
pub use json_mode::json_from_text;
pub use logprobs::{logprob_entry, token_piece, LOGPROB_FLOOR};
pub use output::{AnswerStage, OutputPipeline, OutputSpec, PlainOutput, StageStep, StopMarkers};
pub use prompt::{
    openai_messages, text_of, tool_count, BuiltPrompt, ConvertedPrompt, PromptBuilder,
    SyntheticPrompt, SYNTHETIC_PROMPT_HEADER, SYNTHETIC_PROMPT_TAIL,
};
pub use turn::OpenAiTurn;

/// The shared Chat settings, as the settings route of API-13 will update them.
pub type SharedHandle = Arc<RwLock<SharedDefaults>>;

/// The OpenAI Chat Completions dialect.
pub struct OpenAiDialect {
    model: Value,
    sampling_defaults: Map<String, Value>,
    shared: SharedHandle,
    vocab_size: Option<u32>,
    check_vocab: Option<u64>,
    prompt: Arc<dyn PromptBuilder>,
    output: Arc<dyn OutputPipeline>,
    stamp: Arc<dyn ChunkStamp>,
}

impl std::fmt::Debug for OpenAiDialect {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("OpenAiDialect")
            .field("model", &self.model)
            .field("sampling_defaults", &self.sampling_defaults)
            .field("vocab_size", &self.vocab_size)
            .finish_non_exhaustive()
    }
}

impl OpenAiDialect {
    /// The M1 dialect over `tok`: the synthetic stand-in prompt (LD45), the plain output
    /// stage, the system stamp, no sampling defaults, no shared settings, and `model` as
    /// the model name of every chunk. `vocab_size` is the tokenizer's id range (an engine
    /// token beyond it is the donor's `IndexError`).
    pub fn synthetic(
        tok: Arc<dyn Tokenize + Send + Sync>,
        model: Value,
        vocab_size: Option<u32>,
    ) -> Self {
        Self {
            model,
            sampling_defaults: Map::new(),
            shared: Arc::new(RwLock::new(SharedDefaults::new())),
            vocab_size,
            check_vocab: None,
            prompt: Arc::new(SyntheticPrompt::new(Arc::clone(&tok))),
            output: Arc::new(PlainOutput::new(tok)),
            stamp: Arc::new(SystemStamp),
        }
    }

    /// With this prompt step (M2's prompt packages).
    pub fn with_prompt(mut self, prompt: Arc<dyn PromptBuilder>) -> Self {
        self.prompt = prompt;
        self
    }

    /// With this output pipeline (M2's output pipeline).
    pub fn with_output(mut self, output: Arc<dyn OutputPipeline>) -> Self {
        self.output = output;
        self
    }

    /// With this stamp (fixed ids and times for goldens).
    pub fn with_stamp(mut self, stamp: Arc<dyn ChunkStamp>) -> Self {
        self.stamp = stamp;
        self
    }

    /// With the run's sampling defaults (the config's `sampling` block or the model's own).
    pub fn with_sampling_defaults(mut self, defaults: Map<String, Value>) -> Self {
        self.sampling_defaults = defaults;
        self
    }

    /// With this handle on the shared Chat settings.
    pub fn with_shared(mut self, shared: SharedHandle) -> Self {
        self.shared = shared;
        self
    }

    /// With the vocabulary size the `logit_bias` checks use (`len(tok.tokens)`; `None` or
    /// 0 skips them, as for the byte tokenizer).
    pub fn with_check_vocab(mut self, vocab: Option<u64>) -> Self {
        self.check_vocab = vocab;
        self
    }

    /// The model name of every chunk.
    pub fn model(&self) -> &Value {
        &self.model
    }

    fn shared_now(&self) -> SharedDefaults {
        self.shared
            .read()
            .unwrap_or_else(PoisonError::into_inner)
            .clone()
    }

    fn prepare_now(&self, call: PrepareCall<'_>) -> Result<PreparedTurn, InferenceError> {
        let shared = self.shared_now();
        let glm_dsa = self.prompt.glm_dsa();
        let (mut req, flags) = with_shared(&call.request, SharedDialect::OpenAi, &shared, glm_dsa);
        let resume = req.get("strata_resume") == Some(&Value::Bool(true));
        let api = if resume { "web" } else { "openai" };
        let driver = call.inference.driver();
        let caps = driver.descriptor().map(|d| d.caps).unwrap_or_default();
        let ctx = CheckContext {
            caps,
            vocab_size: self.check_vocab,
            end_ids: self.output.end_ids(),
        };
        let checked = check_request(&mut req, &ctx)?;
        // The donor's order: convert the messages, read the budget, mark, then prepare.
        let converted = self.prompt.convert(&req)?;
        let max = openai_max_tokens(&req)?;
        call.trace.mark("prepare_start");
        let built = self.prompt.prepare(&converted, &max, &flags)?;
        let max_new = driver.context_budget(built.ids.len(), Some(&max))?;
        call.trace.mark("prepared");
        let sampling = effective_sampling(&self.sampling_defaults, &shared, &req);
        let resolved = ResolvedSampling::resolve(&sampling)?;
        let mut generation = GenerationRequest::new(RequestId(0), built.ids.clone(), max_new);
        generation.sampling = engine_sampling(&resolved, checked.logit_bias.as_ref());
        generation.stop_ids = Arc::from(self.output.stop_ids());
        generation.logprobs = checked.logprobs;
        generation.ablate = checked.ablate;
        let mut turn = TurnRequest::new(generation);
        turn.vocab_size = self.vocab_size;
        let stream = req.get("stream").is_some_and(truthy);
        let progress = req.get("return_progress").is_some_and(truthy) && stream;
        let want_lp = checked.logprobs.is_some();
        let json_mode = match req.get("response_format") {
            Some(Value::Object(rf)) => matches!(
                rf.get("type").and_then(Value::as_str),
                Some("json_object" | "json_schema")
            ),
            _ => false,
        };
        let stage = self.output.stage(&OutputSpec {
            thinking: built.thinking,
            logprobs: checked.logprobs,
            client_stops: client_stop_strings(&sampling),
        });
        let (id, created) = self.stamp.stamp()?;
        let writer = ChunkWriter::new(id, created, self.model.clone(), want_lp, json_mode);
        let debug = DebugRequest::from_request(
            "openai",
            &req,
            &converted.messages,
            converted.tools,
            max_new,
            built.thinking,
            built.ids.len(),
        );
        let answer = OpenAiTurn::new(writer, stage, stream, progress, want_lp);
        let mut prepared = PreparedTurn::new(turn, stream, Box::new(answer));
        // The donor watches every request but a streamed web-app answer.
        prepared.watch_client = !(stream && resume);
        prepared.api = api;
        prepared.debug = Some(debug);
        Ok(prepared)
    }
}

impl Dialect for OpenAiDialect {
    fn attach_dialect(&self) -> AttachDialect {
        AttachDialect::OpenAi
    }

    fn prepare<'a>(&'a self, call: PrepareCall<'a>) -> PrepareFuture<'a> {
        Box::pin(async move { self.prepare_now(call) })
    }
}

/// The engine's sampling parameters from the resolved sampling keys and the checked
/// biases: a greedy request is temperature 0; a seed is kept when it fits the engine's
/// 64 bits (`true` is 1, as Python's `int`); a penalty window beyond 64 bits is left to
/// the engine's default.
///
/// Behavior reference: project-maya serve/server.py:1217-1319 at 7e68a30f.
fn engine_sampling(
    r: &ResolvedSampling,
    bias: Option<&console_core::request::LogitBias>,
) -> Sampling {
    let seed = match &r.seed {
        Some(KeyValue::Int(i)) => i.to_u64(),
        Some(KeyValue::Bool(true)) => Some(1),
        _ => None,
    };
    let penalties = r
        .penalties
        .as_ref()
        .map_or_else(Penalties::default, |p| Penalties {
            repeat: p.repeat,
            presence: p.presence,
            frequency: p.frequency,
            last_n: p.last_n.to_i64(),
        });
    Sampling {
        temperature: if r.greedy { Some(0.0) } else { r.temperature },
        top_p: r.top_p,
        top_k: r.top_k,
        min_p: r.min_p,
        seed,
        penalties,
        logit_bias: Arc::from(bias.map(|b| b.sorted()).unwrap_or_default()),
    }
}
