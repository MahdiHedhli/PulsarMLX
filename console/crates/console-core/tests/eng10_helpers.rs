//! ENG-10: helpers shared by the turn-driver tests (included by `#[path]`; as a test
//! target of its own it holds no test).
//!
//! The byte-level stand-in tokenizer of the donor's tests: one id per UTF-8 byte, special
//! tokens from 256 (`<|im_end|>` is 257, the end of a turn).
//!
//! Behavior reference: project-maya serve/server.py:2060-2083 at 7e68a30f.

#![allow(dead_code)]

use std::sync::{Arc, Mutex, PoisonError};
use std::time::Duration;

use console_core::engine::{EngineFactory, EngineSample, GenerationRequest, RequestId};
use console_core::fifo::{EngineFifo, FifoLog, LogCapture};
use console_core::turn::{
    CallerFinish, PingProgress, TurnDriver, TurnItem, TurnObserver, TurnOutcome, TurnRecord,
    TurnRequest, TurnSettings, TurnStart, TurnStream,
};

/// The context of the donor's test engines.
pub const CTX: u32 = 4096;

/// `<|im_end|>` of the byte tokenizer: the engine's end of a turn.
pub const END: u32 = 257;

/// The byte tokenizer's vocabulary: 256 bytes and 6 special tokens.
pub const VOCAB: u32 = 262;

/// Text as the byte tokenizer's ids.
pub fn enc(text: &str) -> Vec<u32> {
    text.bytes().map(u32::from).collect()
}

/// Text and the end of a turn.
pub fn answer(text: &str) -> Vec<u32> {
    let mut ids = enc(text);
    ids.push(END);
    ids
}

/// Byte ids back to text (special ids are dropped).
pub fn dec(ids: &[u32]) -> String {
    let bytes: Vec<u8> = ids.iter().filter_map(|&i| u8::try_from(i).ok()).collect();
    String::from_utf8_lossy(&bytes).into_owned()
}

/// Settings without timers, so a test's items do not depend on how long the driver
/// thread takes in real time.
pub fn quiet_settings() -> TurnSettings {
    TurnSettings {
        heartbeat: None,
        queue_ping: None,
        ..TurnSettings::default()
    }
}

/// What a recording observer saw, in order.
#[derive(Debug, Default, Clone)]
pub struct Seen(pub Arc<Mutex<Vec<String>>>);

impl Seen {
    pub fn push(&self, s: impl Into<String>) {
        self.0
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .push(s.into());
    }

    pub fn list(&self) -> Vec<String> {
        self.0
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clone()
    }
}

/// An observer that records each hook (generated counts are left out, records kept).
#[derive(Debug, Default, Clone)]
pub struct Recorder {
    pub seen: Seen,
    pub records: Arc<Mutex<Vec<TurnRecord>>>,
    pub samples: Arc<Mutex<Vec<EngineSample>>>,
    pub released: Arc<tokio::sync::Notify>,
}

impl Recorder {
    pub fn records(&self) -> Vec<TurnRecord> {
        self.records
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clone()
    }
}

impl TurnObserver for Recorder {
    fn queued(&self) {
        self.seen.push("queued");
    }
    fn dequeued(&self) {
        self.seen.push("dequeued");
    }
    fn active(&self, start: &TurnStart) {
        self.seen.push(format!(
            "active {} {} {}",
            start.phase, start.prompt_tokens, start.max_tokens
        ));
    }
    fn sample(&self, sample: &EngineSample) {
        self.samples
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .push(sample.clone());
    }
    fn place_released(&self) {
        self.seen.push("release");
        self.released.notify_one();
    }
    fn inactive(&self) {
        self.seen.push("inactive");
    }
    fn finished(&self, record: &TurnRecord) {
        self.seen.push(format!("finished {}", record.finish));
        self.records
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .push(record.clone());
    }
}

/// A driver over `factory` with one place, the given settings, a recorder and a
/// captured log.
pub async fn driver_with(
    factory: Arc<dyn EngineFactory>,
    settings: TurnSettings,
) -> (TurnDriver, Recorder, LogCapture) {
    let (log, cap) = FifoLog::capture();
    let rec = Recorder::default();
    let fifo = EngineFifo::with_log(1, log.clone());
    let driver = TurnDriver::start(factory, fifo, settings, Arc::new(rec.clone()), log)
        .await
        .unwrap_or_else(|e| panic!("start: {e}"));
    (driver, rec, cap)
}

/// [`driver_with`] with [`quiet_settings`].
pub async fn driver(factory: Arc<dyn EngineFactory>) -> (TurnDriver, Recorder, LogCapture) {
    driver_with(factory, quiet_settings()).await
}

/// A turn request for `prompt` with an answer budget.
pub fn request(prompt: &[u32], max_new: u32) -> TurnRequest {
    TurnRequest::new(GenerationRequest::new(
        RequestId(0),
        prompt.to_vec(),
        max_new,
    ))
}

/// What a consumer read from one turn.
#[derive(Debug)]
pub struct Read {
    pub tokens: Vec<u32>,
    pub pings: Vec<Option<PingProgress>>,
    pub outcome: TurnOutcome,
}

impl Read {
    pub fn text(&self) -> String {
        dec(&self.tokens)
    }
}

/// Reads a turn to its end as the server's stop detection does: at an id in `stops` the
/// answer is finished (the token is taken, then the engine is stopped).
pub async fn read_turn(mut stream: TurnStream, stops: &[u32]) -> Read {
    let mut tokens = Vec::new();
    let mut pings = Vec::new();
    loop {
        match stream.next().await {
            Some(TurnItem::Ping(p)) => pings.push(p),
            Some(TurnItem::Token(t)) => {
                if stops.contains(&t.id) {
                    stream.finish(CallerFinish::Stop);
                } else {
                    tokens.push(t.id);
                }
            }
            Some(TurnItem::Done(outcome)) => {
                assert!(stream.next().await.is_none(), "nothing follows Done");
                return Read {
                    tokens,
                    pings,
                    outcome: *outcome,
                };
            }
            None => panic!("the turn ended without Done"),
        }
    }
}

/// Waits (on the paused clock) until `cond` holds.
pub async fn until(cond: impl Fn() -> bool) {
    for _ in 0..100_000 {
        if cond() {
            return;
        }
        tokio::time::sleep(Duration::from_millis(1)).await;
    }
    panic!("condition not reached");
}
