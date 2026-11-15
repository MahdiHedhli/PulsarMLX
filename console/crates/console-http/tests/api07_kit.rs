//! Shared helpers of the API-07 lifecycle tests: a server with the lifecycle driver on the
//! chat-completions route, a probe dialect, an observer that records the turn's events,
//! and a raw socket client. Included by the `api07_*.rs` test files with `#[path]`; as a
//! test target of its own it holds no test.
//!
//! The probe dialect stands in for the dialects of API-08 and API-09: the prompt is the
//! bytes of the first message's text (the byte tokenizer of the donor's tests: one id per
//! byte, `<|im_end|>` is 257, 262 ids in all), the answer is one `data: {"text": ...}`
//! frame per byte, then `data: {"finish": ..., "completion_tokens": n}` and `data: [DONE]`,
//! or one JSON body. A request can ask it to fail on purpose with `"probe_fail": {"at":
//! <step>, "class": <class>}`, and to skip the client watcher with `"probe_watch": false`.
//! With `"probe_failed": "own"` it answers its failures itself, as the Responses dialect
//! does (a 500 with a failed object before the first byte, a `response.failed` event
//! after it); with `"log"` or `"close"` it picks the mid-answer log line or a plain close
//! after the first byte. `"probe_gen_start": true` makes it mark `gen_start` on the turn
//! trace, a stand-in for M3's line-protocol client.
//! The raw client is a small loopback socket helper; the shared kit of API-19 replaces it.
#![allow(dead_code)]

use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::sync::atomic::{AtomicI64, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex, PoisonError};
use std::time::Duration;

use console_core::engine::{CommittedToken, EngineFactory, GenerationRequest, RequestId};
use console_core::fifo::{EngineFifo, FifoLog, LogCapture};
use console_core::request::openai_max_tokens;
use console_core::turn::{
    CallerFinish, TurnDriver, TurnObserver, TurnOutcome, TurnRecord, TurnRequest, TurnSettings,
};
use console_http::error::{ApiError, MalformedCategory};
use console_http::guard::{GuardConfig, Refusal};
use console_http::inference::{
    AttachDialect, DebugRequest, Dialect, DialectTurn, Failure, Inference, InferenceError,
    InferenceHooks, InferenceSettings, PrepareCall, PrepareFuture, PreparedTurn, PromptFailure,
    Step, StreamFault,
};
use console_http::router::{Route, Router};
use console_http::transport::{bind, Handler, TransportConfig};
use console_pyjson::dumps::dumps_str;
use serde_json::{Map, Value};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::{oneshot, watch};
use tokio::task::JoinSet;

/// A generous bound for anything a test waits for.
pub const DEADLINE: Duration = Duration::from_secs(10);

/// The context of the donor's test engines.
pub const CTX: u32 = 4096;

/// `<|im_end|>` of the byte tokenizer.
pub const END: u32 = 257;

/// The byte tokenizer's vocabulary.
pub const VOCAB: u32 = 262;

/// The loopback address.
pub const LOOPBACK: IpAddr = IpAddr::V4(Ipv4Addr::LOCALHOST);

/// Text as byte ids.
pub fn enc(text: &str) -> Vec<u32> {
    text.bytes().map(u32::from).collect()
}

/// Text and the end of a turn.
pub fn answer(text: &str) -> Vec<u32> {
    let mut ids = enc(text);
    ids.push(END);
    ids
}

// ------------------------------------------------------------------------- the record

#[derive(Default)]
struct RecordInner {
    events: Mutex<Vec<String>>,
    queued: AtomicI64,
    records: Mutex<Vec<TurnRecord>>,
}

/// What the observer and the test engines saw, in order, with a change signal to wait on.
#[derive(Clone)]
pub struct Record {
    inner: Arc<RecordInner>,
    changed: Arc<watch::Sender<u64>>,
}

impl Default for Record {
    fn default() -> Self {
        Self {
            inner: Arc::default(),
            changed: Arc::new(watch::Sender::new(0)),
        }
    }
}

impl Record {
    /// Appends an event.
    pub fn push(&self, event: impl Into<String>) {
        self.inner
            .events
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .push(event.into());
        self.changed.send_modify(|n| *n = n.wrapping_add(1));
    }

    /// The events so far.
    pub fn events(&self) -> Vec<String> {
        self.inner
            .events
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clone()
    }

    /// Requests waiting in the queue now (the donor's `status["queued"]`).
    pub fn queued(&self) -> i64 {
        self.inner.queued.load(Ordering::SeqCst)
    }

    /// The finished turns' records.
    pub fn records(&self) -> Vec<TurnRecord> {
        self.inner
            .records
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clone()
    }

    /// Waits until `cond` holds, re-checking at every recorded change.
    pub async fn wait(&self, what: &str, cond: impl Fn(&Record) -> bool) {
        let mut rx = self.changed.subscribe();
        let ok = tokio::time::timeout(DEADLINE, rx.wait_for(|_| cond(self))).await;
        assert!(
            matches!(ok, Ok(Ok(_))),
            "{what}: not reached; events {:?}",
            self.events()
        );
    }
}

impl TurnObserver for Record {
    fn queued(&self) {
        self.inner.queued.fetch_add(1, Ordering::SeqCst);
        self.push("queued");
    }
    fn dequeued(&self) {
        self.inner.queued.fetch_sub(1, Ordering::SeqCst);
        self.push("dequeued");
    }
    fn place_released(&self) {
        self.push("release");
    }
    fn finished(&self, record: &TurnRecord) {
        self.inner
            .records
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .push(record.clone());
        self.push(format!("finished {}", record.finish));
    }
}

// --------------------------------------------------------------------- the probe dialect

/// A failure the probe produces on purpose.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProbeFail {
    /// `prepare`, `token`, `end` or `body`.
    pub at: String,
    /// The error class (see [`ProbeFail::error`]).
    pub class: String,
    /// For `token`: the tokens taken before it fails.
    pub after: u64,
}

impl ProbeFail {
    fn read(req: &Map<String, Value>) -> Option<Self> {
        let f = req.get("probe_fail")?.as_object()?;
        Some(Self {
            at: f.get("at")?.as_str()?.to_owned(),
            class: f.get("class")?.as_str()?.to_owned(),
            after: f.get("after").and_then(Value::as_u64).unwrap_or(0),
        })
    }

    /// The error of each class name.
    pub fn error(&self) -> InferenceError {
        match self.class.as_str() {
            "bad_body" => ApiError::bad_body(413, "too large").into(),
            "job" => ApiError::job(409, "the job is busy").into(),
            "store_busy" => ApiError::store_busy("the store is busy").into(),
            "value" => InferenceError::value("temperature: a number"),
            "overflow" => InferenceError::context_overflow(
                "maximum context length is 4096 tokens; prompt (5000 tokens) leaves no room to \
                 answer in the context; requests are never truncated",
            ),
            "died" => InferenceError::EngineDied {
                message: "the engine stopped unexpectedly (exit code -9)".into(),
            },
            "protocol" => InferenceError::Server {
                status: 500,
                message: "engine protocol violation: token after the end".into(),
            },
            "start_failed" => InferenceError::Server {
                status: 503,
                message: "the engine exited before it was ready".into(),
            },
            "key" => InferenceError::malformed(MalformedCategory::KeyError, "'messages'"),
            "type" => InferenceError::malformed(MalformedCategory::TypeError, "not a list"),
            "index" => InferenceError::malformed(
                MalformedCategory::IndexError,
                "token id 300 is outside the vocabulary (262)",
            ),
            "attribute" => InferenceError::malformed(
                MalformedCategory::AttributeError,
                "'str' object has no attribute 'get'",
            ),
            "template" => PromptFailure::template_raise("tools are not supported here").into(),
            "encoder" => PromptFailure::encoder_assertion("a tool result without a call").into(),
            "refused" => {
                Refusal::message(403, "MCP tools can be used only from the own page").into()
            }
            "permission" => ApiError::permission("not here").into(),
            "uncaught" => InferenceError::uncaught(
                "OverflowError",
                "cannot convert float infinity to integer",
            ),
            other => panic!("unknown probe class {other}"),
        }
    }
}

/// The probe dialect.
#[derive(Default)]
pub struct Probe {
    /// Preparations started.
    pub prepares: AtomicUsize,
    /// The request maps the preparations received.
    pub seen: Mutex<Vec<Map<String, Value>>>,
}

impl Probe {
    /// The last request a preparation received.
    pub fn last_seen(&self) -> Option<Map<String, Value>> {
        self.seen
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .last()
            .cloned()
    }

    fn prepare_now(&self, call: PrepareCall<'_>) -> Result<PreparedTurn, InferenceError> {
        self.prepares.fetch_add(1, Ordering::SeqCst);
        let req = call.request;
        self.seen
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .push(req.clone());
        let fail = ProbeFail::read(&req);
        if let Some(f) = fail.as_ref().filter(|f| f.at == "prepare") {
            return Err(f.error());
        }
        let messages: Vec<Value> = req
            .get("messages")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        let content = messages
            .first()
            .and_then(|m| m.get("content"))
            .and_then(Value::as_str)
            .ok_or_else(|| InferenceError::malformed(MalformedCategory::KeyError, "'content'"))?;
        let prompt = enc(content);
        let max = openai_max_tokens(&req)?;
        call.trace.mark("prepare_start");
        let max_new = call
            .inference
            .driver()
            .context_budget(prompt.len(), Some(&max))?;
        call.trace.mark("prepared");
        if req.get("probe_gen_start") == Some(&Value::Bool(true)) {
            call.trace.mark("gen_start");
        }
        let own = req
            .get("probe_failed")
            .and_then(Value::as_str)
            .map(str::to_owned);
        let stream = req.get("stream") == Some(&Value::Bool(true));
        let mut generation = GenerationRequest::new(RequestId(0), prompt.clone(), max_new);
        generation.stop_ids = Arc::from(vec![END]);
        let mut turn = TurnRequest::new(generation);
        turn.vocab_size = Some(VOCAB);
        let debug =
            DebugRequest::from_request("probe", &req, &messages, 0, max_new, true, prompt.len());
        let mut prepared = PreparedTurn::new(
            turn,
            stream,
            Box::new(ProbeTurn {
                stream,
                text: Vec::new(),
                fail,
                taken: 0,
                own,
            }),
        );
        prepared.watch_client = req.get("probe_watch") != Some(&Value::Bool(false));
        prepared.api = "probe";
        prepared.debug = Some(debug);
        Ok(prepared)
    }
}

impl Dialect for Probe {
    fn attach_dialect(&self) -> AttachDialect {
        AttachDialect::OpenAi
    }

    fn prepare<'a>(&'a self, call: PrepareCall<'a>) -> PrepareFuture<'a> {
        Box::pin(async move { self.prepare_now(call) })
    }
}

/// The probe's renderer of one turn.
struct ProbeTurn {
    stream: bool,
    text: Vec<u8>,
    fail: Option<ProbeFail>,
    taken: u64,
    own: Option<String>,
}

impl ProbeTurn {
    fn fails_at(&self, at: &str) -> Option<InferenceError> {
        self.fail
            .as_ref()
            .filter(|f| f.at == at)
            .map(ProbeFail::error)
    }
}

/// One SSE data frame.
pub fn data(json: &str) -> Vec<u8> {
    format!("data: {json}\n\n").into_bytes()
}

impl DialectTurn for ProbeTurn {
    fn token(&mut self, token: &CommittedToken) -> Result<Step, InferenceError> {
        if let Some(f) = self.fail.as_ref().filter(|f| f.at == "token") {
            if self.taken == f.after {
                return Err(f.error());
            }
        }
        self.taken += 1;
        if token.id == END {
            return Ok(Step::finish(Vec::new(), CallerFinish::Stop));
        }
        let Ok(byte) = u8::try_from(token.id) else {
            return Err(InferenceError::malformed(
                MalformedCategory::IndexError,
                "a special token",
            ));
        };
        self.text.push(byte);
        if !self.stream {
            return Ok(Step::none());
        }
        let piece = String::from_utf8_lossy(&[byte]).into_owned();
        Ok(Step::frame(data(&format!(
            "{{\"text\": {}}}",
            dumps_str(&piece, false)
        ))))
    }

    fn stream_end(&mut self, outcome: &TurnOutcome) -> Result<Vec<Vec<u8>>, InferenceError> {
        if let Some(e) = self.fails_at("end") {
            return Err(e);
        }
        Ok(vec![
            data(&format!(
                "{{\"finish\": \"{}\", \"completion_tokens\": {}}}",
                outcome.finish, outcome.completion_tokens
            )),
            b"data: [DONE]\n\n".to_vec(),
        ])
    }

    fn stream_error(&mut self, fault: &StreamFault) -> Vec<Vec<u8>> {
        vec![
            data(&format!(
                "{{\"error\": {{\"type\": \"server_error\", \"message\": {}}}}}",
                dumps_str(&fault.message, true)
            )),
            b"data: [DONE]\n\n".to_vec(),
        ]
    }

    fn body(&mut self, outcome: &TurnOutcome) -> Result<String, InferenceError> {
        if let Some(e) = self.fails_at("body") {
            return Err(e);
        }
        let text = String::from_utf8_lossy(&self.text).into_owned();
        Ok(format!(
            "{{\"text\": {}, \"finish\": \"{}\", \"completion_tokens\": {}}}",
            dumps_str(&text, false),
            outcome.finish,
            outcome.completion_tokens
        ))
    }

    fn failed(&mut self, error: &InferenceError, started: bool) -> Option<Failure> {
        let failed = format!(
            "{{\"status\": \"failed\", \"error\": {{\"code\": \"server_error\", \"message\": {}}}}}",
            dumps_str(&error.to_string(), false)
        );
        match (self.own.as_deref()?, started) {
            ("own", false) => Some(Failure::Answer {
                status: 500,
                body: failed,
            }),
            ("own", true) => Some(Failure::Frames(vec![format!(
                "event: response.failed\ndata: {failed}\n\n"
            )
            .into_bytes()])),
            ("log", true) => Some(Failure::LogAndClose(error.to_string())),
            ("close", true) => Some(Failure::Close),
            // A variant that does not fit the moment: the driver's mapping applies.
            ("log", false) => Some(Failure::Frames(Vec::new())),
            _ => None,
        }
    }
}

// ---------------------------------------------------------------------------- the server

/// What a test server is built from.
pub struct Setup {
    pub factory: Arc<dyn EngineFactory>,
    pub turn: TurnSettings,
    pub hooks: InferenceHooks,
    pub settings: InferenceSettings,
}

impl Setup {
    /// `factory` with timers off, the M1 hooks and the settings off.
    pub fn new(factory: Arc<dyn EngineFactory>) -> Self {
        Self {
            factory,
            turn: TurnSettings {
                heartbeat: None,
                queue_ping: None,
                ..TurnSettings::default()
            },
            hooks: InferenceHooks::default(),
            settings: InferenceSettings::default(),
        }
    }
}

/// A running server with the driver on `/v1/chat/completions`.
pub struct Harness {
    pub addr: SocketAddr,
    pub driver: TurnDriver,
    pub record: Record,
    pub log: LogCapture,
    /// The error log (traceback and uncaught-exception lines).
    pub errors: LogCapture,
    pub probe: Arc<Probe>,
    stop: Option<oneshot::Sender<()>>,
    task: tokio::task::JoinHandle<JoinSet<()>>,
}

impl Harness {
    /// Starts the engine and serves on a loopback port chosen by the system.
    pub async fn start(setup: Setup) -> Self {
        let (log, capture) = FifoLog::capture();
        let (error_log, errors) = FifoLog::capture();
        let record = Record::default();
        let fifo = EngineFifo::with_log(1, log.clone());
        let driver = TurnDriver::start(
            setup.factory,
            fifo,
            setup.turn,
            Arc::new(record.clone()),
            log.clone(),
        )
        .await
        .unwrap_or_else(|e| panic!("start: {e}"));
        let inference = Arc::new(
            Inference::new(driver.clone())
                .with_hooks(setup.hooks)
                .with_settings(setup.settings)
                .with_log(log)
                .with_error_log(error_log),
        );
        let probe = Arc::new(Probe::default());
        let mut router = Router::new(GuardConfig::new(LOOPBACK));
        let replaced = inference.register(&mut router, Route::ChatCompletions, probe.clone());
        assert!(replaced.is_none());
        let listener = bind(SocketAddr::new(LOOPBACK, 0), TransportConfig::default())
            .unwrap_or_else(|e| panic!("bind: {e}"));
        let addr = listener
            .local_addr()
            .unwrap_or_else(|e| panic!("addr: {e}"));
        let handler: Arc<dyn Handler> = Arc::new(router);
        let (stop, stopped) = oneshot::channel::<()>();
        let task = tokio::spawn(listener.serve(handler, async move {
            let _ = stopped.await;
        }));
        Self {
            addr,
            driver,
            record,
            log: capture,
            errors,
            probe,
            stop: Some(stop),
            task,
        }
    }

    /// Opens a connection and sends a chat-completions request with `body`, the way the
    /// donor's raw-socket tests do; the answer is left unread.
    pub async fn send(&self, body: &str) -> TcpStream {
        let mut s = TcpStream::connect(self.addr)
            .await
            .unwrap_or_else(|e| panic!("connect: {e}"));
        let request = format!(
            "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: \
             application/json\r\nContent-Length: {}\r\n\r\n{body}",
            body.len()
        );
        s.write_all(request.as_bytes())
            .await
            .unwrap_or_else(|e| panic!("write: {e}"));
        s
    }

    /// Sends `body` and reads the whole answer.
    pub async fn call(&self, body: &str) -> RawResponse {
        let mut s = self.send(body).await;
        parse_response(&read_to_eof(&mut s).await)
    }

    /// Stops accepting.
    pub async fn stop(mut self) {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
        let _ = (&mut self.task).await;
    }
}

/// A chat body with one user message `text`, the answer budget and the stream flag, and
/// `extra` keys (`, "k": v` form) appended.
pub fn chat(text: &str, max_tokens: i64, stream: bool, extra: &str) -> String {
    format!(
        "{{\"model\": \"m\", \"max_tokens\": {max_tokens}, \"stream\": {stream}, \"messages\": \
         [{{\"role\": \"user\", \"content\": {}}}]{extra}}}",
        dumps_str(text, false)
    )
}

// ------------------------------------------------------------------------ the raw client

/// Reads until end of file (a reset ends it too) within [`DEADLINE`].
pub async fn read_to_eof(s: &mut TcpStream) -> Vec<u8> {
    let mut raw = Vec::new();
    let mut buf = [0u8; 8192];
    let done = tokio::time::timeout(DEADLINE, async {
        loop {
            match s.read(&mut buf).await {
                Ok(0) | Err(_) => break,
                Ok(n) => raw.extend_from_slice(buf.get(..n).unwrap_or_default()),
            }
        }
    })
    .await;
    assert!(
        done.is_ok(),
        "no end of file within the deadline; got {:?}",
        String::from_utf8_lossy(&raw)
    );
    raw
}

/// Reads until `done` holds for what arrived, or end of file, within [`DEADLINE`].
pub async fn read_until(s: &mut TcpStream, done: impl Fn(&[u8]) -> bool) -> Vec<u8> {
    let mut got = Vec::new();
    let mut buf = [0u8; 8192];
    let result = tokio::time::timeout(DEADLINE, async {
        while !done(&got) {
            match s.read(&mut buf).await {
                Ok(0) | Err(_) => break,
                Ok(n) => got.extend_from_slice(buf.get(..n).unwrap_or_default()),
            }
        }
    })
    .await;
    assert!(
        result.is_ok(),
        "timed out with {:?}",
        String::from_utf8_lossy(&got)
    );
    got
}

/// How often `needle` occurs in `haystack`.
pub fn count(haystack: &[u8], needle: &[u8]) -> usize {
    if needle.is_empty() {
        return 0;
    }
    haystack
        .windows(needle.len())
        .filter(|w| *w == needle)
        .count()
}

/// A raw response.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawResponse {
    pub raw: Vec<u8>,
    /// 0 when nothing arrived.
    pub status: u16,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

impl RawResponse {
    /// The first header named `name` (any case).
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|(k, _)| k.eq_ignore_ascii_case(name))
            .map(|(_, v)| v.as_str())
    }

    /// The header names in order.
    pub fn header_names(&self) -> Vec<&str> {
        self.headers.iter().map(|(k, _)| k.as_str()).collect()
    }

    /// The body as text.
    pub fn text(&self) -> String {
        String::from_utf8_lossy(&self.body).into_owned()
    }

    /// The body as JSON (`null` when it is not JSON).
    pub fn json(&self) -> Value {
        serde_json::from_slice(&self.body).unwrap_or(Value::Null)
    }

    /// The text the probe's stream frames carry, in order.
    pub fn streamed_text(&self) -> String {
        self.text()
            .split("\n\n")
            .filter_map(|frame| frame.strip_prefix("data: "))
            .filter_map(|json| serde_json::from_str::<Value>(json).ok())
            .filter_map(|v| v.get("text").and_then(Value::as_str).map(str::to_owned))
            .collect()
    }
}

/// Splits a raw response into its status, headers and body. An empty response has status 0.
pub fn parse_response(raw: &[u8]) -> RawResponse {
    let split = raw
        .windows(4)
        .position(|w| w == b"\r\n\r\n")
        .unwrap_or(raw.len());
    let head = String::from_utf8_lossy(raw.get(..split).unwrap_or_default()).into_owned();
    let body = raw.get(split + 4..).unwrap_or_default().to_vec();
    let mut lines = head.split("\r\n");
    let status = lines
        .next()
        .and_then(|l| l.split(' ').nth(1))
        .and_then(|c| c.parse().ok())
        .unwrap_or(0);
    let headers = lines
        .filter_map(|l| l.split_once(": "))
        .map(|(k, v)| (k.to_owned(), v.to_owned()))
        .collect();
    RawResponse {
        raw: raw.to_vec(),
        status,
        headers,
        body,
    }
}
