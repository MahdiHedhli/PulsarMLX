//! Shared helpers of the API-08 tests: a test server with the OpenAI Chat Completions
//! dialect on `/v1/chat/completions` over a chosen synthetic engine, fixed completion ids
//! for the goldens, and the expected frames. Included by the `api08_*.rs` test files with
//! `#[path]`; as a test target of its own it holds no test.
#![allow(dead_code)]

use std::sync::{Arc, Mutex, PoisonError};
use std::time::Duration;

use console_core::engine::EngineFactory;
use console_core::turn::{TurnObserver, TurnRecord, TurnSettings};
use console_http::dialect::openai::{FixedStamp, OpenAiDialect};
use console_http::inference::Inference;
use console_http::router::Route;
use console_testkit::raw::{server_line, RawResponse};
use console_testkit::server::{TestServer, TestServerBuilder};
use console_tokenizer::byte_tok::ByteTokenizer;
use serde_json::Value;
use tokio::sync::Notify;

/// The fixed id of every completion in these tests.
pub const ID: &str = "chatcmpl-0123456789abcdef01234567";

/// The fixed `created` time.
pub const CREATED: i64 = 1_700_000_000;

/// The scripted engine's model name (deviation PLAN-2).
pub const MODEL: &str = "pulsar-console-synthetic";

/// The synthetic prompt of one user message `hi` is 73 byte tokens: the header line,
/// `user: hi` and `assistant:` (lead decision LD45; not a parity figure).
pub const HI_PROMPT_TOKENS: u32 = 73;

/// A generous bound for anything a test waits for.
pub const DEADLINE: Duration = Duration::from_secs(10);

/// The dialect the tests serve: the M1 stand-in prompt and plain output over the byte
/// tokenizer, with the fixed id and time.
pub fn dialect() -> OpenAiDialect {
    let tok = Arc::new(ByteTokenizer::new());
    let vocab = u32::try_from(tok.n_vocab()).ok();
    OpenAiDialect::synthetic(tok, Value::String(MODEL.into()), vocab).with_stamp(Arc::new(
        FixedStamp {
            id: ID.into(),
            created: CREATED,
        },
    ))
}

/// Turn settings with no timer: no heartbeat and no queue ping, so that a transcript
/// holds only what the engine and the dialect write.
pub fn quiet() -> TurnSettings {
    TurnSettings {
        heartbeat: None,
        queue_ping: None,
        ..TurnSettings::default()
    }
}

/// A builder with the dialect on the chat route over `engine`, timers off.
pub fn builder(engine: Arc<dyn EngineFactory>) -> TestServerBuilder {
    TestServer::builder()
        .engine(engine)
        .turn_settings(quiet())
        .route_with(Route::ChatCompletions, |parts| {
            let Some(driver) = parts.driver.clone() else {
                panic!("the test server was given no engine");
            };
            Arc::new(Inference::new(driver)).route(Arc::new(dialect()))
        })
}

/// A started server with the dialect over `engine`.
pub async fn server(engine: Arc<dyn EngineFactory>) -> TestServer {
    match builder(engine).start().await {
        Ok(s) => s,
        Err(e) => panic!("the test server did not start: {e}"),
    }
}

/// A chat request body: one user message `hi`, and the extra fields given as JSON text
/// (for example `"stream": true, "max_tokens": 20`).
pub fn chat(extra: &str) -> String {
    let sep = if extra.is_empty() { "" } else { ", " };
    format!("{{\"model\": \"m\", \"messages\": [{{\"role\": \"user\", \"content\": \"hi\"}}]{sep}{extra}}}")
}

/// POSTs `body` to the chat route.
pub async fn post(server: &TestServer, body: &str) -> RawResponse {
    server.post_json("/v1/chat/completions", &[], body).await
}

/// The raw answer with the `Date` value replaced by `<date>`.
pub fn normalized(r: &RawResponse) -> String {
    let text = String::from_utf8_lossy(&r.raw).into_owned();
    text.split("\r\n")
        .map(|line| {
            if line.starts_with("Date: ") {
                "Date: <date>"
            } else {
                line
            }
        })
        .collect::<Vec<_>>()
        .join("\r\n")
}

/// The head of a stream.
pub fn sse_head() -> String {
    format!(
        "HTTP/1.0 200 OK\r\n{}\r\nDate: <date>\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\n\r\n",
        server_line()
    )
}

/// The head of a JSON answer of `len` bytes with this status line.
pub fn json_head(status: &str, len: usize) -> String {
    format!(
        "HTTP/1.0 {status}\r\n{}\r\nDate: <date>\r\nContent-Type: application/json\r\nContent-Length: {len}\r\n\r\n",
        server_line()
    )
}

/// The start of every chunk, up to its delta.
pub fn chunk_head() -> String {
    format!(
        "{{\"id\": \"{ID}\", \"object\": \"chat.completion.chunk\", \"created\": {CREATED}, \"model\": \"{MODEL}\", \"choices\": [{{\"index\": 0, \"delta\": "
    )
}

/// One frame with `delta` (JSON text) and no finish reason.
pub fn frame(delta: &str) -> String {
    format!(
        "data: {}{delta}, \"finish_reason\": null}}]}}\n\n",
        chunk_head()
    )
}

/// The first frame of every stream.
pub fn first_frame() -> String {
    frame("{\"role\": \"assistant\", \"content\": \"\"}")
}

/// One content frame per character of `text` (one byte token each, ASCII only).
pub fn content_frames(text: &str) -> String {
    text.chars()
        .map(|c| {
            frame(&format!(
                "{{\"content\": {}}}",
                console_pyjson::dumps::dumps_str(&c.to_string(), false)
            ))
        })
        .collect()
}

/// The final frame: `finish`, the usage and, when given, the timings JSON text.
pub fn final_frame(finish: &str, prompt: u32, completion: u32, cached: u32) -> String {
    format!(
        "data: {}{{}}, \"finish_reason\": \"{finish}\"}}], \"usage\": {{\"prompt_tokens\": {prompt}, \"completion_tokens\": {completion}, \"total_tokens\": {}, \"prompt_tokens_details\": {{\"cached_tokens\": {cached}}}}}}}\n\n",
        chunk_head(),
        prompt + completion
    )
}

/// The frame that ends a stream.
pub const DONE: &str = "data: [DONE]\n\n";

/// The finished turns, with a signal at each one.
#[derive(Default, Clone)]
pub struct Finished {
    records: Arc<Mutex<Vec<TurnRecord>>>,
    changed: Arc<Notify>,
}

impl Finished {
    /// The records so far.
    pub fn records(&self) -> Vec<TurnRecord> {
        self.records
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clone()
    }

    /// Waits until `n` turns have finished.
    pub async fn wait(&self, n: usize) -> Vec<TurnRecord> {
        let wait = async {
            loop {
                let notified = self.changed.notified();
                let records = self.records();
                if records.len() >= n {
                    return records;
                }
                notified.await;
            }
        };
        match tokio::time::timeout(DEADLINE, wait).await {
            Ok(r) => r,
            Err(_) => panic!("{n} turn(s) did not finish: {:?}", self.records()),
        }
    }
}

impl TurnObserver for Finished {
    fn finished(&self, record: &TurnRecord) {
        self.records
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .push(record.clone());
        self.changed.notify_waiters();
    }
}
