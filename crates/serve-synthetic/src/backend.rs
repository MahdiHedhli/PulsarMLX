use std::future::Future;
use std::pin::Pin;
use std::time::Duration;
use tokio::sync::{mpsc, watch};

use crate::{GENERATION_DEADLINE, MAX_OUTPUT_TOKENS, MODEL_ID};

pub const MAX_BACKEND_EVENTS: usize = 64;
pub const MAX_BACKEND_OUTPUT_BYTES: usize = 16 * 1024;
pub(crate) const BACKEND_EVENT_CAPACITY: usize = 4;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BackendRole {
    System,
    User,
    Assistant,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BackendMessage {
    pub role: BackendRole,
    pub content: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BackendRequest {
    pub model_id: String,
    pub messages: Vec<BackendMessage>,
    pub max_output_tokens: u16,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ActualUsage {
    pub prompt_tokens: usize,
    pub completion_tokens: usize,
}

impl ActualUsage {
    /// Returns the exact total when the provider counts can be represented.
    /// An overflow is a provider protocol failure rather than a plausible but
    /// false saturated total.
    pub fn total_tokens(self) -> Option<usize> {
        self.prompt_tokens.checked_add(self.completion_tokens)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BackendFinishReason {
    Stop,
    Length,
}

impl BackendFinishReason {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Stop => "stop",
            Self::Length => "length",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BackendFailure {
    Generation,
    Protocol,
}

impl BackendFailure {
    pub(crate) fn code(self) -> &'static str {
        match self {
            Self::Generation => "backend_failure",
            Self::Protocol => "backend_protocol_error",
        }
    }

    pub(crate) fn message(self) -> &'static str {
        match self {
            Self::Generation => "synthetic backend failed",
            Self::Protocol => "backend produced an invalid event sequence",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum BackendEvent {
    AssistantRole,
    TextDelta(String),
    Finished {
        reason: BackendFinishReason,
        usage: ActualUsage,
    },
    Failed(BackendFailure),
}

#[derive(Clone, Copy)]
pub struct BackendDescriptor {
    pub model_id: &'static str,
    pub owned_by: &'static str,
    pub capabilities: &'static [&'static str],
}

pub struct BackendCancellation {
    cancelled: watch::Receiver<bool>,
}

impl BackendCancellation {
    pub(crate) fn pair() -> (watch::Sender<bool>, Self) {
        let (sender, cancelled) = watch::channel(false);
        (sender, Self { cancelled })
    }

    pub fn is_cancelled(&self) -> bool {
        *self.cancelled.borrow()
    }

    pub async fn cancelled(&mut self) {
        while !self.is_cancelled() {
            if self.cancelled.changed().await.is_err() {
                return;
            }
        }
    }
}

pub type BackendFuture = Pin<Box<dyn Future<Output = ()> + Send + 'static>>;
pub type BackendEventSender = mpsc::Sender<BackendEvent>;

pub struct BackendSession {
    pub(crate) future: BackendFuture,
    pub(crate) worker: Option<std::sync::Arc<crate::runtime_adapter::Worker>>,
}

impl BackendSession {
    pub fn new(future: BackendFuture) -> Self {
        Self {
            future,
            worker: None,
        }
    }
}

pub trait CompletionBackend: Send + Sync {
    fn descriptor(&self) -> BackendDescriptor;

    fn begin(
        &self,
        request: BackendRequest,
        cancellation: BackendCancellation,
        events: BackendEventSender,
    ) -> Result<BackendSession, BackendFailure>;
}

pub(crate) struct SyntheticBackend;

impl CompletionBackend for SyntheticBackend {
    fn descriptor(&self) -> BackendDescriptor {
        BackendDescriptor {
            model_id: MODEL_ID,
            owned_by: "pulsarmlx-synthetic",
            capabilities: &["chat.completions", "streaming", "synthetic-only"],
        }
    }

    fn begin(
        &self,
        request: BackendRequest,
        mut cancellation: BackendCancellation,
        events: BackendEventSender,
    ) -> Result<BackendSession, BackendFailure> {
        let mode = SyntheticMode::from_request(&request);
        if mode == SyntheticMode::FailBefore {
            return Err(BackendFailure::Generation);
        }
        let future = Box::pin(async move {
            // This test-only mode makes backend admission observable to the
            // loopback SDK smoke test.  It emits the initial streaming role
            // only after the request owns its generation permit, then holds
            // that permit until the client cancels the stream.
            if mode == SyntheticMode::Hold {
                if !send(&mut cancellation, &events, BackendEvent::AssistantRole).await {
                    return;
                }
                cancellation.cancelled().await;
                return;
            }
            if mode == SyntheticMode::Slow
                && !cancel_or_sleep(
                    &mut cancellation,
                    GENERATION_DEADLINE + Duration::from_millis(250),
                )
                .await
            {
                return;
            }
            if !send(&mut cancellation, &events, BackendEvent::AssistantRole).await {
                return;
            }
            if mode == SyntheticMode::DisconnectProbe
                && !cancel_or_sleep(&mut cancellation, Duration::from_millis(250)).await
            {
                return;
            }
            if mode == SyntheticMode::FailAfter {
                let _ = send(
                    &mut cancellation,
                    &events,
                    BackendEvent::Failed(BackendFailure::Generation),
                )
                .await;
                return;
            }

            let (content, reason, completion_tokens) =
                render_output(mode, request.max_output_tokens);
            for chunk in utf8_chunks(&content) {
                if !send(
                    &mut cancellation,
                    &events,
                    BackendEvent::TextDelta(chunk.to_owned()),
                )
                .await
                {
                    return;
                }
            }
            let _ = send(
                &mut cancellation,
                &events,
                BackendEvent::Finished {
                    reason,
                    usage: ActualUsage {
                        prompt_tokens: request.messages.len(),
                        completion_tokens,
                    },
                },
            )
            .await;
        });
        Ok(BackendSession::new(future))
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum SyntheticMode {
    Success,
    Empty,
    DisconnectProbe,
    FailBefore,
    FailAfter,
    Slow,
    Hold,
}

impl SyntheticMode {
    fn from_request(request: &BackendRequest) -> Self {
        match request
            .messages
            .last()
            .map(|message| message.content.as_str())
        {
            Some("__synthetic_empty__") => Self::Empty,
            Some("__synthetic_disconnect__") => Self::DisconnectProbe,
            Some("__synthetic_fail_before__") => Self::FailBefore,
            Some("__synthetic_fail_after__") => Self::FailAfter,
            Some("__synthetic_slow__") => Self::Slow,
            Some("__synthetic_hold__") => Self::Hold,
            _ => Self::Success,
        }
    }
}

async fn send(
    cancellation: &mut BackendCancellation,
    events: &BackendEventSender,
    event: BackendEvent,
) -> bool {
    tokio::select! {
        biased;
        _ = cancellation.cancelled() => false,
        result = events.send(event) => result.is_ok(),
    }
}

async fn cancel_or_sleep(cancellation: &mut BackendCancellation, duration: Duration) -> bool {
    tokio::select! {
        biased;
        _ = cancellation.cancelled() => false,
        _ = tokio::time::sleep(duration) => true,
    }
}

fn render_output(mode: SyntheticMode, max_tokens: u16) -> (String, BackendFinishReason, usize) {
    if mode == SyntheticMode::Empty {
        return (String::new(), BackendFinishReason::Stop, 0);
    }
    let tokens = ["SYNTHETIC_OK:", " café", " 🚀"];
    let take = usize::from(max_tokens.min(MAX_OUTPUT_TOKENS)).min(tokens.len());
    let reason = if take < tokens.len() {
        BackendFinishReason::Length
    } else {
        BackendFinishReason::Stop
    };
    (tokens[..take].concat(), reason, take)
}

pub(crate) fn utf8_chunks(content: &str) -> Vec<&str> {
    if content.is_empty() {
        return Vec::new();
    }
    let mut cuts = vec![0usize];
    for (index, character) in content.char_indices() {
        let width = character.len_utf8();
        if width > 1 {
            cuts.push(index);
            cuts.push(index + width);
        }
    }
    cuts.push(content.len());
    cuts.dedup();
    cuts.windows(2)
        .filter(|window| window[0] < window[1])
        .map(|window| &content[window[0]..window[1]])
        .collect()
}
