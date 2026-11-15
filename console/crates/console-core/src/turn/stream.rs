//! The consumer's side of a turn: the items a turn produces, its outcome, and the stream
//! the HTTP side reads them from.
//!
//! The turn itself runs in a spawned task (see [`TurnDriver::turn`](super::TurnDriver::turn)).
//! Dropping the [`TurnStream`] only sets the turn's cancel: the task still sends STOP to
//! the engine (the cancel the engine reads between steps), waits for the engine call to
//! return (the drain), and only then gives the FIFO place back.

use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Arc;

use tokio::sync::mpsc;
use tokio::time::Instant;

use crate::engine::{CommittedToken, ControlHandle, EngineStop, PromptProgress};
use crate::fifo::FifoLog;
use crate::request::RequestError;

use super::error::TurnError;
use super::figures::{py_round, request_timings, RequestTimings, SegmentFigures};
use super::hooks::{TurnObserver, TurnRecord};
use super::log::LOG_PREFIX;

/// The payload of a keep-alive while the engine reads the prompt: llama.cpp's
/// `prompt_progress` fields, from the engine's latest prompt progress of this call.
///
/// Behavior reference: project-maya serve/server.py:4491-4496 at 7e68a30f.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PingProgress {
    /// The prompt's tokens.
    pub total: u32,
    /// What the conversation cache already held.
    pub cache: u32,
    /// Tokens read so far.
    pub processed: u32,
    /// The prompt read's own clock, rounded to whole milliseconds (Python's `round`).
    pub time_ms: i64,
}

impl PingProgress {
    /// The payload of a progress event, or the error Python's `round` raises on its time:
    /// `ValueError` "cannot convert float NaN to integer" for a NaN and `OverflowError`
    /// "cannot convert float infinity to integer" for an infinity. A finite time beyond
    /// the 64-bit range saturates (Python's integer would not).
    ///
    /// Behavior reference: project-maya serve/server.py:4491-4496 at 7e68a30f.
    pub fn from_progress(p: &PromptProgress) -> Result<Self, RequestError> {
        if p.ms.is_nan() {
            return Err(RequestError::invalid("cannot convert float NaN to integer"));
        }
        if p.ms.is_infinite() {
            return Err(RequestError::Overflow(
                "cannot convert float infinity to integer".to_owned(),
            ));
        }
        // A rounded finite float converts with saturation at the 64-bit bounds.
        #[allow(clippy::cast_possible_truncation)]
        let time_ms = py_round(p.ms, 0) as i64;
        Ok(Self {
            total: p.total,
            cache: p.reused,
            processed: p.read,
            time_ms,
        })
    }
}

/// How a turn ended, before the caller's own decision is applied.
#[derive(Debug, Clone, PartialEq)]
pub enum TurnEnd {
    /// The engine calls ended without failure; the last call's stop, as the engine saw it.
    /// The finish on the wire is the caller's (stop detection belongs to console-prompt);
    /// the engine's stop tells a pause cut from an end.
    Ended(crate::engine::EngineStop),
    /// The engine's numbers went non-finite after tokens were sent: the answer ends there
    /// and what was sent stands (the donor's finish `length`).
    NonFiniteCut,
    /// The cancel was set before the engine was called: nothing was asked of it.
    CancelledBeforeEngine,
    /// The turn failed.
    Failed(TurnError),
}

/// Why the caller stopped reading tokens (see [`TurnStream::finish`]).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CallerFinish {
    /// A stop id, a stop string or the loop guard ended the answer.
    Stop,
    /// A token limit the caller enforces ended the answer.
    Length,
}

/// The end of a turn, as the consumer receives it.
#[derive(Debug, Clone, PartialEq)]
pub struct TurnOutcome {
    /// How it ended.
    pub end: TurnEnd,
    /// The donor's finish word: `stop`, `length`, `cancel`, `error` or `disconnect`.
    pub finish: &'static str,
    /// The prompt length.
    pub prompt_tokens: u32,
    /// The tokens the request took: those the consumer took (the donor counts every token
    /// it takes, a stop token included), and an id outside the vocabulary that ended the
    /// turn (the donor counts it before its tokenizer raises).
    pub completion_tokens: u32,
    /// This request's engine figures, merged over its calls (`None`: the engine reported
    /// none).
    pub figures: Option<SegmentFigures>,
    /// llama.cpp's `timings` (`None`: the engine keeps no clock).
    pub timings: Option<RequestTimings>,
    /// The cancel (client gone or shutdown) was set when the turn ended.
    pub cancelled: bool,
}

impl TurnOutcome {
    /// The cached prompt tokens on the wire: the timings' `cache_n`, 0 without a clock.
    ///
    /// Behavior reference: project-maya serve/server.py:4769-4771 at 7e68a30f.
    pub fn cached_tokens(&self) -> u32 {
        self.timings.map_or(0, |t| t.cache_n)
    }

    /// The error, when the turn failed.
    pub fn error(&self) -> Option<&TurnError> {
        match &self.end {
            TurnEnd::Failed(e) => Some(e),
            _ => None,
        }
    }
}

/// One item of a turn.
#[derive(Debug, Clone, PartialEq)]
pub enum TurnItem {
    /// A keep-alive: while queued (`None`), on the engine's prompt progress, and when the
    /// engine has been quiet for the heartbeat interval (the latest progress of the call,
    /// or `None`). SSE writes `: keep-alive` or a `prompt_progress` chunk.
    Ping(Option<PingProgress>),
    /// A committed token, in order.
    Token(CommittedToken),
    /// The end; nothing follows it.
    Done(Box<TurnOutcome>),
}

/// What the turn's task sends at its end; the stream turns it into a [`TurnOutcome`] with
/// its own count of the tokens it handed out.
#[derive(Debug)]
pub(crate) struct RawDone {
    pub(crate) end: TurnEnd,
    pub(crate) prompt_tokens: u32,
    pub(crate) figures: Option<SegmentFigures>,
    /// Tokens the request took that were not handed out (an id outside the vocabulary);
    /// counted only when the turn ends with that failure.
    pub(crate) extra_tokens: u32,
    /// The turn reached the engine (it gets a history row and a done line).
    pub(crate) counted: bool,
    pub(crate) started: Instant,
    pub(crate) first_at: Option<Instant>,
}

/// An item on the channel from the turn's task to the stream.
#[derive(Debug)]
pub(crate) enum Item {
    Ping(Option<PingProgress>),
    Token(CommittedToken),
    Done(RawDone),
}

/// State shared by a turn's task and its stream.
pub(crate) struct StreamShared {
    /// Tokens the stream handed to the consumer.
    pub(crate) consumed: AtomicU32,
    /// The consumer cancelled (client gone, shutdown).
    pub(crate) client_cancel: AtomicBool,
    /// The stream was dropped before the end (the donor's `GeneratorExit`).
    pub(crate) disconnected: AtomicBool,
    /// The caller's finish, once it stopped reading: 0 none, 1 stop, 2 length.
    pub(crate) caller: AtomicU32,
    /// The end was booked (history row and done line), exactly once.
    pub(crate) booked: AtomicBool,
    pub(crate) observer: Arc<dyn TurnObserver>,
    pub(crate) log: FifoLog,
}

impl StreamShared {
    pub(crate) fn new(observer: Arc<dyn TurnObserver>, log: FifoLog) -> Self {
        Self {
            consumed: AtomicU32::new(0),
            client_cancel: AtomicBool::new(false),
            disconnected: AtomicBool::new(false),
            caller: AtomicU32::new(0),
            booked: AtomicBool::new(false),
            observer,
            log,
        }
    }

    fn caller(&self) -> Option<CallerFinish> {
        match self.caller.load(Ordering::Acquire) {
            1 => Some(CallerFinish::Stop),
            2 => Some(CallerFinish::Length),
            _ => None,
        }
    }

    /// The outcome of `raw` with the tokens the consumer took, and, once per turn, the
    /// turn's history row and done line for a turn that reached the engine.
    ///
    /// A failure that reaches the stream after the consumer stopped reading (the server's
    /// finish, or a dropped stream) lies after the point where the consumer stopped: the
    /// turn's task runs ahead of the consumer, and the stream hands out no token after a
    /// finish. The donor never decodes that far; its drain swallows what follows. Such a
    /// failure is therefore part of the drain: the end is a cancelled stop, and the
    /// caller's finish, or `disconnect`, decides the word.
    ///
    /// Behavior reference: project-maya serve/server.py:1451-1500, 4507-4518 at 7e68a30f.
    pub(crate) fn conclude(&self, raw: RawDone) -> TurnOutcome {
        let disconnected = self.disconnected.load(Ordering::Acquire);
        let caller = self.caller();
        let end = match raw.end {
            TurnEnd::Failed(_) if caller.is_some() || disconnected => {
                TurnEnd::Ended(EngineStop::Cancelled)
            }
            end => end,
        };
        let extra = if matches!(end, TurnEnd::Failed(_)) {
            raw.extra_tokens
        } else {
            0
        };
        let n = self.consumed.load(Ordering::Acquire).saturating_add(extra);
        let cancelled = self.client_cancel.load(Ordering::Acquire) || disconnected;
        let finish = finish_word(&end, caller, cancelled, disconnected);
        let timings = raw
            .figures
            .as_ref()
            .and_then(|f| request_timings(raw.prompt_tokens, n, f));
        let outcome = TurnOutcome {
            end,
            finish,
            prompt_tokens: raw.prompt_tokens,
            completion_tokens: n,
            figures: raw.figures,
            timings,
            cancelled,
        };
        if raw.counted && !self.booked.swap(true, Ordering::AcqRel) {
            self.log.line(&done_line(
                &outcome,
                raw.started,
                raw.first_at,
                Instant::now(),
            ));
            self.observer.finished(&TurnRecord {
                finish,
                prompt_tokens: outcome.prompt_tokens,
                output_tokens: n,
                cancelled,
                figures: outcome.figures,
                timings,
            });
        }
        outcome
    }
}

/// The donor's finish word for a turn's end. A dropped stream is `disconnect` (the donor's
/// `GeneratorExit`, whatever was under way). An error the donor's `run` does not catch (an
/// `IndexError` from the tokenizer, an `OverflowError` from `round`) leaves its finish at
/// the default `length`; every other error is `error`. A cancel is `cancel`; otherwise the
/// caller's decision, and `length` when it made none.
///
/// Behavior reference: project-maya serve/server.py:4400, 4646-4680, 4719-4720 at 7e68a30f.
pub(crate) fn finish_word(
    end: &TurnEnd,
    caller: Option<CallerFinish>,
    cancelled: bool,
    disconnected: bool,
) -> &'static str {
    match end {
        _ if disconnected => "disconnect",
        TurnEnd::Failed(TurnError::Request(e))
            if matches!(e.python_type(), "IndexError" | "OverflowError") =>
        {
            "length"
        }
        TurnEnd::Failed(_) => "error",
        TurnEnd::NonFiniteCut => "length",
        TurnEnd::CancelledBeforeEngine => "cancel",
        _ if cancelled => "cancel",
        _ => match caller {
            Some(CallerFinish::Stop) => "stop",
            Some(CallerFinish::Length) | None => "length",
        },
    }
}

/// The donor's done line: tokens, seconds, the rate (the engine's decode clock when there
/// is one, else the tokens after the first over the time since it), the finish, the
/// cancel, and the expert cache's hit rate when the engine reported lookups.
///
/// Behavior reference: project-maya serve/server.py:4752-4765 at 7e68a30f.
fn done_line(o: &TurnOutcome, started: Instant, first: Option<Instant>, now: Instant) -> String {
    let n = o.completion_tokens;
    let el = now.saturating_duration_since(started).as_secs_f64();
    let engine_rate = o.figures.and_then(|f| match (f.generated, f.decode_ms) {
        (Some(g), Some(ms)) if n != 0 && g != 0 && ms != 0.0 => Some(f64::from(g) / (ms / 1000.0)),
        _ => None,
    });
    let rate = match (engine_rate, first) {
        (Some(r), _) => r,
        (None, Some(ft)) if n > 1 && now > ft => {
            f64::from(n - 1) / now.saturating_duration_since(ft).as_secs_f64()
        }
        _ => 0.0,
    };
    let hit = o.figures.and_then(|f| match (f.hits, f.lookups) {
        (Some(h), Some(l)) if l != 0 => Some(py_round(f64::from(h) / f64::from(l), 3)),
        _ => None,
    });
    let hit_msg = hit.map_or_else(String::new, |h| {
        format!(", expert cache {:.1}% hit", h * 100.0)
    });
    let cancel = if o.cancelled { "True" } else { "False" };
    format!(
        "{LOG_PREFIX} done: {n} tokens in {el:.0} s ({rate:.1} tok/s) ({}, cancel={cancel}){hit_msg}",
        o.finish
    )
}

/// The consumer's side of one turn: its items in order, ending with exactly one
/// [`TurnItem::Done`].
///
/// - [`TurnStream::finish`]: the server decided the answer is finished (a stop id or
///   string, the loop guard, its own limit). The engine is stopped (the seam's cancel);
///   later tokens are not handed out and do not count.
/// - [`TurnStream::cancel`]: the client went away or the server shuts down. The finish is
///   `cancel`.
/// - Dropping the stream: the consumer went away mid-stream (the donor's `GeneratorExit`).
///   The engine is stopped and drained, and the place given back, by the turn's task.
pub struct TurnStream {
    rx: mpsc::Receiver<Item>,
    control: ControlHandle,
    shared: Arc<StreamShared>,
    done: bool,
}

impl std::fmt::Debug for TurnStream {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("TurnStream")
            .field("consumed", &self.shared.consumed.load(Ordering::Relaxed))
            .field("done", &self.done)
            .finish()
    }
}

impl TurnStream {
    pub(crate) fn new(
        rx: mpsc::Receiver<Item>,
        control: ControlHandle,
        shared: Arc<StreamShared>,
    ) -> Self {
        Self {
            rx,
            control,
            shared,
            done: false,
        }
    }

    /// The next item; `None` after [`TurnItem::Done`].
    pub async fn next(&mut self) -> Option<TurnItem> {
        if self.done {
            return None;
        }
        loop {
            match self.rx.recv().await? {
                Item::Ping(p) => return Some(TurnItem::Ping(p)),
                Item::Token(t) => {
                    if self.shared.caller().is_some() {
                        continue;
                    }
                    self.shared.consumed.fetch_add(1, Ordering::AcqRel);
                    return Some(TurnItem::Token(t));
                }
                Item::Done(raw) => {
                    self.done = true;
                    return Some(TurnItem::Done(Box::new(self.shared.conclude(raw))));
                }
            }
        }
    }

    /// The server decided the answer is finished: the engine is stopped, and no later
    /// token is handed out or counted. The first call decides the caller's finish.
    pub fn finish(&mut self, why: CallerFinish) {
        let code = match why {
            CallerFinish::Stop => 1,
            CallerFinish::Length => 2,
        };
        let _ = self
            .shared
            .caller
            .compare_exchange(0, code, Ordering::AcqRel, Ordering::Acquire);
        self.control.cancel();
    }

    /// The client went away, or the server shuts down: the engine is stopped, and the
    /// finish is `cancel`.
    pub fn cancel(&self) {
        self.shared.client_cancel.store(true, Ordering::Release);
        self.control.cancel();
    }

    /// The turn's control state: for pause and wrap requests (fair slices, shutdown).
    pub fn control(&self) -> &ControlHandle {
        &self.control
    }

    /// Tokens handed out so far.
    pub fn consumed(&self) -> u32 {
        self.shared.consumed.load(Ordering::Acquire)
    }
}

impl Drop for TurnStream {
    fn drop(&mut self) {
        if self.done {
            return;
        }
        // The consumer went away: only the cancel is set here. The task stops the engine,
        // drains it and gives the place back; whichever side holds the end books it.
        self.shared.disconnected.store(true, Ordering::Release);
        self.control.cancel();
        self.rx.close();
        while let Ok(item) = self.rx.try_recv() {
            if let Item::Done(raw) = item {
                let _ = self.shared.conclude(raw);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ping_payload_rounds_like_python() {
        let p = |ms| PromptProgress {
            read: 4096,
            total: 8192,
            reused: 2048,
            ms,
            tok_s: None,
        };
        let got = PingProgress::from_progress(&p(251.0)).unwrap();
        assert_eq!(
            got,
            PingProgress {
                total: 8192,
                cache: 2048,
                processed: 4096,
                time_ms: 251
            }
        );
        assert_eq!(PingProgress::from_progress(&p(0.5)).unwrap().time_ms, 0);
        assert_eq!(PingProgress::from_progress(&p(1.5)).unwrap().time_ms, 2);
        assert_eq!(PingProgress::from_progress(&p(2.5)).unwrap().time_ms, 2);
        let nan = PingProgress::from_progress(&p(f64::NAN)).unwrap_err();
        assert_eq!(
            (nan.python_type(), nan.message()),
            ("ValueError", "cannot convert float NaN to integer")
        );
        let inf = PingProgress::from_progress(&p(f64::NEG_INFINITY)).unwrap_err();
        assert_eq!(inf.python_type(), "OverflowError");
    }

    #[test]
    fn finish_words_follow_the_donor() {
        let ended = TurnEnd::Ended(EngineStop::Stop { token: None });
        assert_eq!(
            finish_word(&ended, Some(CallerFinish::Stop), false, false),
            "stop"
        );
        assert_eq!(finish_word(&ended, None, false, false), "length");
        assert_eq!(
            finish_word(&ended, Some(CallerFinish::Stop), true, false),
            "cancel"
        );
        assert_eq!(finish_word(&ended, None, true, true), "disconnect");
        assert_eq!(
            finish_word(&TurnEnd::NonFiniteCut, None, true, false),
            "length"
        );
        assert_eq!(
            finish_word(&TurnEnd::CancelledBeforeEngine, None, false, false),
            "cancel"
        );
        let err = TurnEnd::Failed(TurnError::stopping());
        assert_eq!(
            finish_word(&err, Some(CallerFinish::Stop), true, false),
            "error"
        );
        assert_eq!(
            finish_word(&err, Some(CallerFinish::Stop), true, true),
            "disconnect"
        );
        let oov = TurnEnd::Failed(TurnError::out_of_vocabulary(300, 262));
        assert_eq!(finish_word(&oov, None, false, false), "length");
    }
}
