//! The lifecycle of one request: the steps before the turn, the collected answer and the
//! stream loop.
//!
//! Behavior reference: project-maya serve/server.py:6241-6297, 5019-5044, 6584-6624 and
//! 6692-6710 at 7e68a30f.

use std::net::SocketAddr;
use std::sync::Arc;

use console_core::engine::ControlHandle;
use console_core::request::{strip_internal_keys, text_file_limit};
use console_core::turn::{log_safe, TurnItem, TurnOutcome, TurnStream};

use super::dialect::{Dialect, DialectTurn, Failure, PrepareCall};
use super::error::{InferenceError, StreamFault};
use super::hooks::AttachCall;
use super::trace::TurnTrace;
use super::Inference;
use crate::error::{ApiError, LOG_PREFIX};
use crate::router::RouteRequest;
use crate::transport::{ClientWatch, Exchange};

/// The SSE comment of a keep-alive (clients ignore it).
///
/// Behavior reference: project-maya serve/server.py:6609-6610 at 7e68a30f.
pub const KEEP_ALIVE: &[u8] = b": keep-alive\n\n";

/// The failure of a turn whose stream ended without its outcome (the turn's task is
/// gone): the engine's driver is treated as dead, as `console_core::turn` does.
fn turn_lost() -> InferenceError {
    InferenceError::EngineDied {
        message: String::from("the engine's driver thread has ended"),
    }
}

/// Serves one request on a chat route.
pub(crate) async fn serve(inference: Arc<Inference>, dialect: Arc<dyn Dialect>, rq: RouteRequest) {
    let RouteRequest {
        mut exchange,
        body,
        guard,
        route: rq_route,
        marks,
        ..
    } = rq;
    let mut trace = TurnTrace::new(inference.settings().turn_trace);
    // The router received the request, then read and parsed its body (the donor's
    // `http`, `body` and `json` marks; the router keeps their instants).
    trace.mark_at("http", marks.received);
    if let Some(at) = marks.body {
        trace.mark_at("body", at);
    }
    match marks.json {
        Some(at) => trace.mark_at("json", at),
        None => trace.mark("json"),
    }
    if let Some(message) = inference.hooks().overloaded_message() {
        let _ = exchange
            .responder()
            .error(&ApiError::overloaded(message))
            .await;
        return;
    }
    // `Inference::register` admits only routes whose body the router reads as a JSON
    // object, before the gate above (the donor's order, serve/server.py:6241-6259).
    let Some(mut req) = body else {
        inference.error_log().line(&format!(
            "{LOG_PREFIX} the inference driver got no JSON body (route {rq_route:?})"
        ));
        return;
    };
    // Deviation SEC-6.1: internal markers are never taken from the client.
    strip_internal_keys(&mut req);
    let peer = exchange.peer_addr();
    let attachments = &inference.hooks().attachments;
    let call = AttachCall {
        dialect: dialect.attach_dialect(),
        want_images: attachments.want_images(),
        text_limit: text_file_limit(i64::from(inference.driver().max_context())),
        text_only: attachments.text_only(),
    };
    if let Err(e) = attachments.expand_request(&mut req, &call) {
        answer_before(&inference, &mut exchange, peer, &e).await;
        return;
    }
    let prepared = dialect
        .prepare(PrepareCall {
            request: req,
            head: exchange.head(),
            guard: &guard,
            peer,
            inference: &inference,
            trace: &mut trace,
        })
        .await;
    let prepared = match prepared {
        Ok(p) => p,
        Err(e) => {
            answer_before(&inference, &mut exchange, peer, &e).await;
            return;
        }
    };
    if inference.settings().debug {
        if let Some(debug) = &prepared.debug {
            match debug.line() {
                Ok(line) => inference.log().line(&line),
                Err(e) => {
                    answer_before(&inference, &mut exchange, peer, &e).await;
                    return;
                }
            }
        }
    }
    let prompt_tokens = prepared.turn.generation.prompt.len();
    // The watch reports the client's leaving; the turn is then cancelled through its
    // stream, so that its finish reads `cancel`, as the donor's `cancel.set()` does.
    let mut watch = if prepared.watch_client {
        exchange.watch_client(ControlHandle::new())
    } else {
        None
    };
    let stream = inference.driver().turn(prepared.turn);
    let mut run = Run {
        inference: &inference,
        exchange: &mut exchange,
        peer,
        trace,
        prompt_tokens,
        answer: prepared.answer,
    };
    if prepared.stream {
        run.stream(stream, &mut watch).await;
    } else {
        run.collect(stream, &mut watch).await;
    }
}

/// Resolves when the client is seen to go; never without a watch.
async fn gone(watch: &mut Option<ClientWatch>) {
    match watch.as_mut() {
        Some(w) => w.gone().await,
        None => std::future::pending::<()>().await,
    }
}

/// Logs the traceback line the donor prints for a malformed request (`traceback.print_exc`)
/// and for an exception its handler does not catch (`handle_error`).
///
/// Both go to the error log (standard error), as the donor's do.
fn log_traceback(inference: &Inference, peer: SocketAddr, e: &InferenceError) {
    match e {
        InferenceError::Uncaught { class, message } => inference.error_log().line(&format!(
            "{LOG_PREFIX} exception while serving a request from {peer}: {class}: {}",
            log_safe(message)
        )),
        _ => {
            if let Some(class) = e.traceback_class() {
                inference.error_log().line(&format!(
                    "{LOG_PREFIX} traceback: {class} in a request from {peer}: {}",
                    log_safe(&e.message())
                ));
            }
        }
    }
}

/// Answers `e` while nothing has been sent (the donor's `do_POST` handlers).
async fn answer_before(
    inference: &Inference,
    exchange: &mut Exchange,
    peer: SocketAddr,
    e: &InferenceError,
) {
    log_traceback(inference, peer, e);
    match e {
        InferenceError::Refused(refusal) => {
            let _ = refusal.answer(exchange.responder()).await;
        }
        other => {
            // An uncaught exception has no answer: the connection closes.
            if let Some(api) = other.api_error() {
                let _ = exchange.responder().error(&api).await;
            }
        }
    }
}

/// One running turn and the connection it answers.
struct Run<'a> {
    inference: &'a Inference,
    exchange: &'a mut Exchange,
    peer: SocketAddr,
    trace: TurnTrace,
    prompt_tokens: usize,
    answer: Box<dyn DialectTurn>,
}

impl Run<'_> {
    /// The trace line at the first token, unless the turn is cancelled (the donor returns
    /// before its trace when `cancel` is set, serve/server.py:1413-1417).
    fn first_token(&mut self, cancelled: bool) {
        if cancelled {
            return;
        }
        if let Some(line) = self.trace.first_token(self.prompt_tokens) {
            self.inference.log().line(&line);
        }
    }

    /// A failure while nothing has been sent: the dialect's own answer, else the driver's
    /// mapping by class.
    async fn fail_before(&mut self, e: &InferenceError) {
        match self.answer.failed(e, false) {
            Some(Failure::Answer { status, body }) => {
                let _ = self.exchange.responder().json(status, &body).await;
            }
            Some(Failure::Close) => {}
            _ => answer_before(self.inference, self.exchange, self.peer, e).await,
        }
    }

    /// The collected answer: the turn's items go to the dialect before any header is
    /// written, so a failure is answered with its own status.
    ///
    /// Behavior reference: project-maya serve/server.py:6596-6597 at 7e68a30f.
    async fn collect(&mut self, mut stream: TurnStream, watch: &mut Option<ClientWatch>) {
        let mut cancelled = false;
        let outcome = loop {
            tokio::select! {
                biased;
                () = gone(watch), if !cancelled => {
                    stream.cancel();
                    cancelled = true;
                }
                item = stream.next() => match item {
                    Some(TurnItem::Ping(_)) => {}
                    Some(TurnItem::Token(t)) => {
                        self.first_token(cancelled);
                        match self.answer.token(&t) {
                            Ok(step) => {
                                if let Some(why) = step.finish {
                                    stream.finish(why);
                                }
                            }
                            Err(e) => {
                                // Dropping the stream stops the engine and drains it.
                                drop(stream);
                                self.fail_before(&e).await;
                                return;
                            }
                        }
                    }
                    Some(TurnItem::Done(outcome)) => break outcome,
                    None => {
                        self.fail_before(&turn_lost()).await;
                        return;
                    }
                },
            }
        };
        if let Some(error) = outcome.error() {
            let e = InferenceError::from(error.clone());
            self.fail_before(&e).await;
            return;
        }
        match self.answer.body(&outcome) {
            Ok(body) => {
                // A client that left gets nothing; the write fails quietly.
                let _ = self.exchange.responder().json(200, &body).await;
            }
            Err(e) => self.fail_before(&e).await,
        }
    }

    /// Writes one frame; false when the client is gone (the write failed or timed out).
    async fn write(&mut self, frame: &[u8]) -> bool {
        self.exchange.responder().write_body(frame).await.is_ok()
    }

    /// Writes frames in order; false at the first failed write.
    async fn write_all(&mut self, frames: Vec<Vec<u8>>) -> bool {
        for frame in frames {
            if !self.write(&frame).await {
                return false;
            }
        }
        true
    }

    /// A failure after the stream began: the dialect's own answer, else by its class: the
    /// dialect's error event inside the write loop, else the mid-answer log line (the
    /// donor's `_fail`), else nothing.
    ///
    /// Behavior reference: project-maya serve/server.py:6616-6624, 6152-6158 and 6732-6734,
    /// serve/responses.py:526-533 at 7e68a30f.
    async fn fail_after_start(&mut self, e: &InferenceError) {
        match self.answer.failed(e, true) {
            Some(Failure::Frames(frames)) => {
                let _ = self.write_all(frames).await;
                return;
            }
            Some(Failure::LogAndClose(message)) => {
                let _ = self
                    .exchange
                    .responder()
                    .error(&ApiError::validation(message))
                    .await;
                return;
            }
            Some(Failure::Close) => return,
            Some(Failure::Answer { .. }) | None => {}
        }
        log_traceback(self.inference, self.peer, e);
        if let Some(fault) = e.stream_fault() {
            self.write_fault(&fault).await;
            return;
        }
        if let InferenceError::Fail(api) = e {
            // Logs "request failed mid-answer: <message>" and ends the answer.
            let _ = self.exchange.responder().error(api).await;
        }
    }

    async fn write_fault(&mut self, fault: &StreamFault) {
        let frames = self.answer.stream_error(fault);
        let _ = self.write_all(frames).await;
    }

    /// The stream: the SSE head, then each item as it comes.
    ///
    /// Behavior reference: project-maya serve/server.py:6605-6624 and 6692-6710 at
    /// 7e68a30f.
    async fn stream(&mut self, mut stream: TurnStream, watch: &mut Option<ClientWatch>) {
        if self.exchange.responder().sse_start().await.is_err() {
            client_left(stream);
            return;
        }
        let start = self.answer.stream_start();
        if !self.write_all(start).await {
            client_left(stream);
            return;
        }
        let mut cancelled = false;
        loop {
            tokio::select! {
                biased;
                () = gone(watch), if !cancelled => {
                    stream.cancel();
                    cancelled = true;
                }
                item = stream.next() => match item {
                    Some(TurnItem::Ping(p)) => {
                        // A keep-alive without progress is always the comment.
                        let frame = p
                            .and_then(|p| self.answer.progress(p))
                            .unwrap_or_else(|| KEEP_ALIVE.to_vec());
                        if !self.write(&frame).await {
                            client_left(stream);
                            return;
                        }
                    }
                    Some(TurnItem::Token(t)) => {
                        self.first_token(cancelled);
                        match self.answer.token(&t) {
                            Ok(step) => {
                                if let Some(why) = step.finish {
                                    stream.finish(why);
                                }
                                if !self.write_all(step.frames).await {
                                    client_left(stream);
                                    return;
                                }
                            }
                            Err(e) => {
                                drop(stream);
                                self.fail_after_start(&e).await;
                                return;
                            }
                        }
                    }
                    Some(TurnItem::Done(outcome)) => {
                        self.end(&outcome).await;
                        return;
                    }
                    None => {
                        self.fail_after_start(&turn_lost()).await;
                        return;
                    }
                },
            }
        }
    }

    /// The end of a stream: the dialect's last frames, or the turn's failure.
    async fn end(&mut self, outcome: &TurnOutcome) {
        if let Some(error) = outcome.error() {
            let e = InferenceError::from(error.clone());
            self.fail_after_start(&e).await;
            return;
        }
        match self.answer.stream_end(outcome) {
            Ok(frames) => {
                let _ = self.write_all(frames).await;
            }
            Err(e) => self.fail_after_start(&e).await,
        }
    }
}

/// A write failed: the client went away. The turn is cancelled and its stream dropped, so
/// the engine is stopped once and drained, and its place given back after the drain (the
/// donor's `cancel.set()` and `chunks.close()`).
fn client_left(stream: TurnStream) {
    stream.cancel();
    drop(stream);
}
