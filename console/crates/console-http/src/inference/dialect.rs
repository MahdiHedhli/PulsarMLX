//! The interface the client dialects plug into: [`Dialect`] parses and prepares one
//! request, and the [`DialectTurn`] it returns renders the turn's items as that dialect's
//! stream frames or collected body.
//!
//! API-08 (OpenAI Chat Completions), API-09 (Anthropic messages) and the Responses packages
//! implement these traits. The driver owns everything around them: the overloaded gate,
//! the boundary strip of internal keys (SEC-6.1), the attachment planner, the debug line,
//! the client watcher, the turn on the engine, the SSE head, keep-alives, write failures
//! and the error mapping.
//!
//! Behavior reference: project-maya serve/server.py:6566-6624 and 6680-6710 at 7e68a30f.

use std::future::Future;
use std::net::SocketAddr;
use std::pin::Pin;

use console_core::engine::CommittedToken;
use console_core::turn::{CallerFinish, PingProgress, TurnOutcome, TurnRequest};
use serde_json::{Map, Value};

use super::debug::DebugRequest;
use super::error::{InferenceError, StreamFault};
use super::hooks::AttachDialect;
use super::trace::TurnTrace;
use super::Inference;
use crate::guard::Guard;
use crate::transport::RequestHead;

/// The future [`Dialect::prepare`] returns.
pub type PrepareFuture<'a> =
    Pin<Box<dyn Future<Output = Result<PreparedTurn, InferenceError>> + Send + 'a>>;

/// One request handed to a dialect's preparation.
pub struct PrepareCall<'a> {
    /// The request body: a JSON object, with every top-level key beginning with `_`
    /// already removed (SEC-6.1) and its file parts expanded by the attachment planner.
    pub request: Map<String, Value>,
    /// The request head (for the dialect's own-page check, for example).
    pub head: &'a RequestHead,
    /// The guards in force for this request.
    pub guard: &'a Guard,
    /// The client's address.
    pub peer: SocketAddr,
    /// The server's inference state: the turn driver, the settings and the log.
    pub inference: &'a Inference,
    /// The request's trace: the dialect marks `prepare_start` and `prepared` around its
    /// prompt step, as the donor does.
    pub trace: &'a mut TurnTrace,
}

impl std::fmt::Debug for PrepareCall<'_> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PrepareCall")
            .field("request", &self.request)
            .field("path", &self.head.path())
            .field("peer", &self.peer)
            .finish_non_exhaustive()
    }
}

/// A client dialect: one per chat route.
pub trait Dialect: Send + Sync + 'static {
    /// The dialect the attachment planner reads the request's file parts in.
    fn attach_dialect(&self) -> AttachDialect;

    /// Parses and prepares one request: shared defaults, the request checks, the dialect's
    /// conversion to messages, the prompt (render, encode, the context rule through
    /// [`TurnDriver::context_budget`](console_core::turn::TurnDriver::context_budget)), and
    /// the turn request. Everything here happens before the first byte of the answer, so
    /// an error is answered with its own status. PRM-11 (M2) supplies the prompt step;
    /// its template and encoder refusals map through
    /// [`PromptFailure`](super::PromptFailure) (approved deviation P-8).
    fn prepare<'a>(&'a self, call: PrepareCall<'a>) -> PrepareFuture<'a>;
}

/// A prepared request: the turn to run and how to answer it.
pub struct PreparedTurn {
    /// The turn on the engine.
    pub turn: TurnRequest,
    /// Answer as a server-sent event stream (else one JSON body after the turn).
    pub stream: bool,
    /// Watch the client while the turn runs (the donor watches every request except a
    /// streamed web-app answer that outlives its connection, `strata_resume`). Turning it
    /// off only stops the watch: a failed write still cancels the turn and stops the
    /// engine, so the driver cannot serve `strata_resume` (an answer that runs on after its
    /// connection, the donor's `StreamJob`); API-10 needs its own path or a new hook for it.
    pub watch_client: bool,
    /// The monitor's name for the request's API (`openai`, `web`, `anthropic`); kept for
    /// the monitoring packages, not read in M1.
    pub api: &'static str,
    /// The debug line's fields, written when `PULSAR_CONSOLE_DEBUG` is set.
    pub debug: Option<DebugRequest>,
    /// The renderer of this turn's items.
    pub answer: Box<dyn DialectTurn>,
}

impl PreparedTurn {
    /// A turn answered by `answer`, with the client watched, no monitor tag and no debug
    /// line.
    pub fn new(turn: TurnRequest, stream: bool, answer: Box<dyn DialectTurn>) -> Self {
        Self {
            turn,
            stream,
            watch_client: true,
            api: "",
            debug: None,
            answer,
        }
    }
}

impl std::fmt::Debug for PreparedTurn {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PreparedTurn")
            .field("turn", &self.turn)
            .field("stream", &self.stream)
            .field("watch_client", &self.watch_client)
            .field("api", &self.api)
            .field("debug", &self.debug)
            .finish_non_exhaustive()
    }
}

/// What a dialect makes of one token.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Step {
    /// Frames to write now, each written and sent on its own (a stream only; a collecting
    /// answer returns none).
    pub frames: Vec<Vec<u8>>,
    /// The answer is finished here (a stop id, a stop string, the loop guard): the engine
    /// is stopped, and later tokens are not handed out.
    pub finish: Option<CallerFinish>,
}

impl Step {
    /// Nothing to write, the answer goes on.
    pub fn none() -> Self {
        Self::default()
    }

    /// One frame to write.
    pub fn frame(frame: Vec<u8>) -> Self {
        Self {
            frames: vec![frame],
            finish: None,
        }
    }

    /// The answer is finished, with these frames first.
    pub fn finish(frames: Vec<Vec<u8>>, why: CallerFinish) -> Self {
        Self {
            frames,
            finish: Some(why),
        }
    }
}

/// A dialect's own answer to a failure of its turn ([`DialectTurn::failed`]).
///
/// A variant that does not fit the moment (an [`Answer`](Self::Answer) after the stream
/// began, [`Frames`](Self::Frames) or [`LogAndClose`](Self::LogAndClose) before it) is
/// ignored, and the driver's mapping applies.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Failure {
    /// Before the first byte: this status and JSON body (the donor's Responses route
    /// answers 500 with its failed response object).
    Answer {
        /// HTTP status.
        status: u16,
        /// The JSON body.
        body: String,
    },
    /// After the stream began: these frames, then the stream ends (the donor's
    /// `response.failed` event).
    Frames(Vec<Vec<u8>>),
    /// After the stream began: the line `[console] request failed mid-answer: <message>`
    /// on standard error (the donor's `_fail`), and the connection closes.
    LogAndClose(String),
    /// The connection closes with nothing more written.
    Close,
}

/// The renderer of one turn's items in a dialect: OpenAI chunks, Anthropic events, or the
/// collected body. PRM-12's output pipeline (M2: detokenization, stops, markers, thinking)
/// runs inside [`token`](Self::token).
pub trait DialectTurn: Send + 'static {
    /// Frames written right after the SSE head, before the first item (a stream only).
    fn stream_start(&mut self) -> Vec<Vec<u8>> {
        Vec::new()
    }

    /// The frame for a keep-alive that carries prompt progress (a stream only): `None`
    /// writes the SSE comment `: keep-alive`; a dialect that reports prompt progress
    /// returns its own chunk. A keep-alive without progress is always the comment, and
    /// this method is not called for it (serve/server.py:6609-6610 and 6694-6695).
    fn progress(&mut self, progress: PingProgress) -> Option<Vec<u8>> {
        let _ = progress;
        None
    }

    /// One committed token. An error ends the turn (the engine is stopped and drained) and
    /// is answered as its class.
    fn token(&mut self, token: &CommittedToken) -> Result<Step, InferenceError>;

    /// The stream's last frames after a turn that did not fail (finish chunk, usage,
    /// `data: [DONE]`).
    fn stream_end(&mut self, outcome: &TurnOutcome) -> Result<Vec<Vec<u8>>, InferenceError>;

    /// The dialect's error event for a failure after the stream began (the donor writes
    /// OpenAI's `{"error": ...}` chunk and `data: [DONE]`, or Anthropic's `event: error`).
    fn stream_error(&mut self, fault: &StreamFault) -> Vec<Vec<u8>>;

    /// The JSON body of a collected answer after a turn that did not fail.
    fn body(&mut self, outcome: &TurnOutcome) -> Result<String, InferenceError>;

    /// The dialect's own answer to a failure of its turn: an error of the turn (its
    /// outcome, a lost driver), or one returned by [`token`](Self::token),
    /// [`stream_end`](Self::stream_end) or [`body`](Self::body). `started` is true once
    /// the stream's head was written. `None` (the default, used by OpenAI and Anthropic)
    /// applies the driver's mapping by class ([`InferenceError::before_start`] and
    /// [`InferenceError::after_start`]). The Responses dialect answers every failure
    /// itself, as the donor's `response_events` catches every exception: a 500 with the
    /// failed response object for a collected answer, a `response.failed` event in a
    /// stream (serve/responses.py:526-533, serve/server.py:6513-6515). A failure the
    /// dialect takes is not logged with a traceback, as the donor's handler never sees it.
    fn failed(&mut self, error: &InferenceError, started: bool) -> Option<Failure> {
        let _ = (error, started);
        None
    }
}
