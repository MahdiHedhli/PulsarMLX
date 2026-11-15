//! One chat completion's renderer on the inference driver: the output stage's events as
//! SSE frames (a stream) or gathered for the collector (a JSON body).
//!
//! Behavior reference: project-maya serve/server.py:4933-5008, 5204-5246 and 6584-6624 at
//! 7e68a30f.

use console_core::engine::CommittedToken;
use console_core::turn::{PingProgress, TurnOutcome};
use console_pyjson::dumps::to_wire;
use serde_json::{Map, Value};

use super::chunks::{data_frame, error_frames, ChunkWriter, DONE_FRAME};
use super::collect::collect;
use super::output::AnswerStage;
use crate::inference::{DialectTurn, InferenceError, Step, StreamFault};

/// The renderer of one chat completion.
pub struct OpenAiTurn {
    writer: ChunkWriter,
    stage: Box<dyn AnswerStage>,
    stream: bool,
    /// `return_progress` and `stream` are both truthy.
    progress: bool,
    /// The request asked for logprobs (the collector gathers them).
    logprobs: bool,
    /// A collected answer's chunks, the first one included.
    gathered: Vec<Value>,
}

impl std::fmt::Debug for OpenAiTurn {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("OpenAiTurn")
            .field("writer", &self.writer)
            .field("stream", &self.stream)
            .field("progress", &self.progress)
            .field("logprobs", &self.logprobs)
            .finish_non_exhaustive()
    }
}

impl OpenAiTurn {
    /// A renderer: the chunk writer, the output stage, whether the answer streams, whether
    /// prompt progress is sent (only in a stream), and whether logprobs were asked for.
    pub fn new(
        writer: ChunkWriter,
        stage: Box<dyn AnswerStage>,
        stream: bool,
        progress: bool,
        logprobs: bool,
    ) -> Self {
        let mut gathered = Vec::new();
        if !stream {
            // The donor's generator yields the first chunk before anything is queued.
            gathered.push(Value::Object(writer.first()));
        }
        Self {
            writer,
            stage,
            stream,
            progress: progress && stream,
            logprobs,
            gathered,
        }
    }

    /// Frames (a stream) or gathered chunks (a collected answer).
    fn emit(&mut self, chunks: Vec<Map<String, Value>>) -> Result<Vec<Vec<u8>>, InferenceError> {
        if !self.stream {
            self.gathered.extend(chunks.into_iter().map(Value::Object));
            return Ok(Vec::new());
        }
        chunks
            .into_iter()
            .map(|c| data_frame(&Value::Object(c)))
            .collect()
    }

    /// The last chunks after a turn that did not fail: the text still held, then the
    /// JSON-mode chunk and the final chunk.
    fn last(&mut self, outcome: &TurnOutcome) -> Result<Vec<Vec<u8>>, InferenceError> {
        let held = self.stage.finish()?;
        let mut chunks = self.writer.events(held)?;
        chunks.extend(self.writer.end(outcome));
        self.emit(chunks)
    }
}

impl DialectTurn for OpenAiTurn {
    fn stream_start(&mut self) -> Vec<Vec<u8>> {
        // A first chunk of plain strings always serializes.
        data_frame(&Value::Object(self.writer.first()))
            .map(|f| vec![f])
            .unwrap_or_default()
    }

    fn progress(&mut self, progress: PingProgress) -> Option<Vec<u8>> {
        if !self.progress {
            return None;
        }
        data_frame(&Value::Object(self.writer.progress(progress))).ok()
    }

    fn token(&mut self, token: &CommittedToken) -> Result<Step, InferenceError> {
        let step = self.stage.token(token)?;
        let chunks = self.writer.events(step.events)?;
        let frames = self.emit(chunks)?;
        Ok(Step {
            frames,
            finish: step.finish,
        })
    }

    fn stream_end(&mut self, outcome: &TurnOutcome) -> Result<Vec<Vec<u8>>, InferenceError> {
        let mut frames = self.last(outcome)?;
        frames.push(DONE_FRAME.to_vec());
        Ok(frames)
    }

    fn stream_error(&mut self, fault: &StreamFault) -> Vec<Vec<u8>> {
        error_frames(fault)
    }

    fn body(&mut self, outcome: &TurnOutcome) -> Result<String, InferenceError> {
        self.last(outcome)?;
        let out = collect(&self.gathered, self.logprobs).ok_or_else(|| {
            InferenceError::uncaught("TypeError", "'NoneType' object is not subscriptable")
        })?;
        to_wire(&out).map_err(|e| InferenceError::uncaught(e.python_type(), e.to_string()))
    }
}
