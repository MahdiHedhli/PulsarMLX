//! The chunks of one chat completion (`openai_chunks`): the first chunk, one chunk per
//! answer event, the prompt-progress chunk, the JSON-mode chunk and the final chunk with
//! the usage; and their SSE frames.
//!
//! Each chunk is `{"id": "chatcmpl-<24 hex>", "object": "chat.completion.chunk", "created":
//! <epoch seconds>, "model": <the model name>, "choices": [{"index": 0, "delta": {...},
//! "finish_reason": null}]}`, written as `data: <json>\n\n` with Python's
//! `json.dumps(c, ensure_ascii=False)`. The error event of a stream that has begun uses
//! Python's defaults instead (`ensure_ascii=True`), as the donor's handler writes it.
//!
//! Behavior reference: project-maya serve/server.py:4933-5008 and 6605-6624 at 7e68a30f.

use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};

use console_core::request::pyrepr::repr_str;
use console_core::turn::{PingProgress, RequestTimings, TurnOutcome};
use console_pyjson::dumps::{float_value, to_python_default, to_wire};
use console_pyjson::ids::chatcmpl_id;
use serde_json::{Map, Value};

use super::events::AnswerEvent;
use super::json_mode::json_from_text;
use crate::error::MalformedCategory;
use crate::inference::{InferenceError, StreamFault};

/// The frame that ends a stream.
pub const DONE_FRAME: &[u8] = b"data: [DONE]\n\n";

/// Where a completion's id and `created` time come from: `chatcmpl-` and 24 random hex
/// characters, and the epoch seconds, by default. Tests give fixed ones for their goldens.
pub trait ChunkStamp: Send + Sync + 'static {
    /// The id and the `created` time of one completion.
    fn stamp(&self) -> Result<(String, i64), InferenceError>;
}

/// The donor's stamp: `"chatcmpl-" + uuid.uuid4().hex[:24]` from operating-system
/// randomness, and `int(time.time())`.
///
/// Behavior reference: project-maya serve/server.py:4936 at 7e68a30f.
#[derive(Debug, Clone, Copy, Default)]
pub struct SystemStamp;

impl ChunkStamp for SystemStamp {
    fn stamp(&self) -> Result<(String, i64), InferenceError> {
        let id = chatcmpl_id().map_err(|e| InferenceError::uncaught("OSError", e.to_string()))?;
        let created = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_or(0, |d| i64::try_from(d.as_secs()).unwrap_or(i64::MAX));
        Ok((id, created))
    }
}

/// A fixed id and time, for tests and goldens.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FixedStamp {
    /// The id.
    pub id: String,
    /// The `created` time.
    pub created: i64,
}

impl ChunkStamp for FixedStamp {
    fn stamp(&self) -> Result<(String, i64), InferenceError> {
        Ok((self.id.clone(), self.created))
    }
}

/// One SSE data frame of `chunk`: `data: ` and `json.dumps(chunk, ensure_ascii=False)`.
pub fn data_frame(chunk: &Value) -> Result<Vec<u8>, InferenceError> {
    let json =
        to_wire(chunk).map_err(|e| InferenceError::uncaught(e.python_type(), e.to_string()))?;
    Ok(format!("data: {json}\n\n").into_bytes())
}

/// The error event of a stream that has begun, then the stream's end: `data:
/// {"error": {"type": "server_error", "message": <m>}}` with Python's default
/// `json.dumps` (ASCII escapes), then `data: [DONE]`. An engine death's message already
/// ends with "; the next request restarts it".
///
/// Behavior reference: project-maya serve/server.py:6618-6624 at 7e68a30f.
pub fn error_frames(fault: &StreamFault) -> Vec<Vec<u8>> {
    let mut inner = Map::new();
    inner.insert("type".into(), Value::String("server_error".into()));
    inner.insert("message".into(), Value::String(fault.message.clone()));
    let mut err = Map::new();
    err.insert("error".into(), Value::Object(inner));
    // A JSON object of two strings always serializes.
    let json = to_python_default(&Value::Object(err)).unwrap_or_default();
    vec![
        format!("data: {json}\n\n").into_bytes(),
        DONE_FRAME.to_vec(),
    ]
}

/// llama.cpp's `timings` object of a request, in the donor's key order; the draft fields
/// only when the engine reported drafts.
///
/// Behavior reference: project-maya serve/server.py:4785-4793 at 7e68a30f.
pub fn timings_value(t: &RequestTimings) -> Value {
    let opt = |v: Option<f64>| v.map_or(Value::Null, float_value);
    let mut m = Map::new();
    m.insert("cache_n".into(), Value::from(t.cache_n));
    m.insert("prompt_n".into(), Value::from(t.prompt_n));
    m.insert("prompt_ms".into(), float_value(t.prompt_ms));
    m.insert("prompt_per_token_ms".into(), opt(t.prompt_per_token_ms));
    m.insert("prompt_per_second".into(), opt(t.prompt_per_second));
    m.insert("predicted_n".into(), Value::from(t.predicted_n));
    m.insert("predicted_ms".into(), float_value(t.predicted_ms));
    m.insert(
        "predicted_per_token_ms".into(),
        opt(t.predicted_per_token_ms),
    );
    m.insert("predicted_per_second".into(), opt(t.predicted_per_second));
    if let Some((offered, accepted)) = t.drafts {
        m.insert("draft_n".into(), Value::from(offered));
        m.insert("draft_n_accepted".into(), Value::from(accepted));
    }
    Value::Object(m)
}

/// The finish reason on the wire: `tool_calls` when a call was sent and the answer
/// stopped, `stop` for a cancel, else the turn's own (`stop` or `length`).
///
/// Behavior reference: project-maya serve/server.py:4997 at 7e68a30f.
pub fn wire_finish(finish: &str, calls: u64) -> &str {
    if calls > 0 && finish == "stop" {
        "tool_calls"
    } else if finish == "cancel" {
        "stop"
    } else {
        finish
    }
}

/// The writer of one completion's chunks.
#[derive(Debug, Clone)]
pub struct ChunkWriter {
    id: String,
    created: i64,
    model: Value,
    want_lp: bool,
    json_mode: bool,
    /// JSON mode: the content held until the end, and its entries.
    held: Vec<String>,
    held_lp: Vec<Value>,
    /// Tool calls sent so far.
    calls: u64,
    /// Calls sent piece by piece: id to index.
    streamed: HashMap<String, u64>,
}

impl ChunkWriter {
    /// A writer for one completion: its id and time, the model name, whether the request
    /// asked for logprobs, and whether it asked for JSON (`response_format` of type
    /// `json_object` or `json_schema`).
    pub fn new(id: String, created: i64, model: Value, want_lp: bool, json_mode: bool) -> Self {
        Self {
            id,
            created,
            model,
            want_lp,
            json_mode,
            held: Vec::new(),
            held_lp: Vec::new(),
            calls: 0,
            streamed: HashMap::new(),
        }
    }

    /// The tool calls sent so far.
    pub fn calls(&self) -> u64 {
        self.calls
    }

    /// A chunk with this delta and finish reason.
    pub fn chunk(&self, delta: Map<String, Value>, finish: Option<&str>) -> Map<String, Value> {
        let mut choice = Map::new();
        choice.insert("index".into(), Value::from(0));
        choice.insert("delta".into(), Value::Object(delta));
        choice.insert(
            "finish_reason".into(),
            finish.map_or(Value::Null, |f| Value::String(f.to_owned())),
        );
        let mut c = Map::new();
        c.insert("id".into(), Value::String(self.id.clone()));
        c.insert(
            "object".into(),
            Value::String("chat.completion.chunk".into()),
        );
        c.insert("created".into(), Value::from(self.created));
        c.insert("model".into(), self.model.clone());
        c.insert("choices".into(), Value::Array(vec![Value::Object(choice)]));
        c
    }

    /// The first chunk: `{"role": "assistant", "content": ""}`.
    pub fn first(&self) -> Map<String, Value> {
        let mut delta = Map::new();
        delta.insert("role".into(), Value::String("assistant".into()));
        delta.insert("content".into(), Value::String(String::new()));
        self.chunk(delta, None)
    }

    /// A text chunk; with logprobs asked, its choice carries `logprobs` `{"content": [],
    /// "refusal": null}` with the entries under `key`.
    fn text_chunk(&self, key: &str, text: String, entries: Vec<Value>) -> Map<String, Value> {
        let mut delta = Map::new();
        delta.insert(key.to_owned(), Value::String(text));
        let mut c = self.chunk(delta, None);
        if self.want_lp {
            let mut lp = Map::new();
            lp.insert("content".into(), Value::Array(Vec::new()));
            lp.insert("refusal".into(), Value::Null);
            lp.insert(key.to_owned(), Value::Array(entries));
            if let Some(Value::Object(choice)) = c
                .get_mut("choices")
                .and_then(Value::as_array_mut)
                .and_then(|a| a.first_mut())
            {
                choice.insert("logprobs".into(), Value::Object(lp));
            }
        }
        c
    }

    /// The chunk of a keep-alive that carries the prompt's progress: an empty delta and
    /// llama.cpp's top-level `prompt_progress` `{total, cache, processed, time_ms}`.
    ///
    /// Behavior reference: project-maya serve/server.py:4963-4970 at 7e68a30f.
    pub fn progress(&self, p: PingProgress) -> Map<String, Value> {
        let mut pp = Map::new();
        pp.insert("total".into(), Value::from(p.total));
        pp.insert("cache".into(), Value::from(p.cache));
        pp.insert("processed".into(), Value::from(p.processed));
        pp.insert("time_ms".into(), Value::from(p.time_ms));
        let mut c = self.chunk(Map::new(), None);
        c.insert("prompt_progress".into(), Value::Object(pp));
        c
    }

    /// The chunks of these events, in order. A content event in JSON mode is held for the
    /// end; empty texts give nothing; a whole call already streamed is skipped. A piece of
    /// arguments for a call that was never opened is the donor's `KeyError`.
    pub fn events(
        &mut self,
        events: Vec<AnswerEvent>,
    ) -> Result<Vec<Map<String, Value>>, InferenceError> {
        let mut out = Vec::new();
        for ev in events {
            match ev {
                AnswerEvent::Reasoning { text, logprobs } => {
                    if !text.is_empty() {
                        out.push(self.text_chunk("reasoning_content", text, logprobs));
                    }
                }
                AnswerEvent::Content { text, logprobs } => {
                    if text.is_empty() {
                        continue;
                    }
                    if self.json_mode {
                        self.held.push(text);
                        self.held_lp.extend(logprobs);
                        continue;
                    }
                    out.push(self.text_chunk("content", text, logprobs));
                }
                AnswerEvent::ToolStart(call) => {
                    let index = self.calls;
                    self.streamed.insert(call.id.clone(), index);
                    self.calls += 1;
                    let mut entry = Map::new();
                    entry.insert("index".into(), Value::from(index));
                    entry.extend(call.to_openai(Some(""))?);
                    out.push(self.tool_chunk(entry));
                }
                AnswerEvent::ToolArgs { id, text } => {
                    let Some(&index) = self.streamed.get(&id) else {
                        return Err(InferenceError::malformed(
                            MalformedCategory::KeyError,
                            repr_str(&id),
                        ));
                    };
                    let mut function = Map::new();
                    function.insert("arguments".into(), Value::String(text));
                    let mut entry = Map::new();
                    entry.insert("index".into(), Value::from(index));
                    entry.insert("function".into(), Value::Object(function));
                    out.push(self.tool_chunk(entry));
                }
                AnswerEvent::ToolCall { call, .. } => {
                    if self.streamed.contains_key(&call.id) {
                        continue;
                    }
                    let mut entry = Map::new();
                    entry.insert("index".into(), Value::from(self.calls));
                    entry.extend(call.to_openai(None)?);
                    self.calls += 1;
                    out.push(self.tool_chunk(entry));
                }
                AnswerEvent::Mcp(item) => {
                    let mut c = self.chunk(Map::new(), None);
                    c.insert("strata_mcp".into(), item);
                    out.push(c);
                }
            }
        }
        Ok(out)
    }

    fn tool_chunk(&self, entry: Map<String, Value>) -> Map<String, Value> {
        let mut delta = Map::new();
        delta.insert(
            "tool_calls".into(),
            Value::Array(vec![Value::Object(entry)]),
        );
        self.chunk(delta, None)
    }

    /// The last chunks after a turn that did not fail: in JSON mode the held answer as one
    /// content chunk (`json_from_text` of the joined text, with all its entries), then the
    /// final chunk: an empty delta, the finish reason, the usage and, when the engine
    /// keeps a clock, llama.cpp's `timings`.
    ///
    /// Behavior reference: project-maya serve/server.py:4994-5008 at 7e68a30f.
    pub fn end(&mut self, outcome: &TurnOutcome) -> Vec<Map<String, Value>> {
        let mut out = Vec::new();
        if !self.held.is_empty() {
            let text = json_from_text(&self.held.concat());
            let entries = std::mem::take(&mut self.held_lp);
            self.held.clear();
            out.push(self.text_chunk("content", text, entries));
        }
        let finish = wire_finish(outcome.finish, self.calls);
        let mut last = self.chunk(Map::new(), Some(finish));
        let pt = u64::from(outcome.prompt_tokens);
        let ct = u64::from(outcome.completion_tokens);
        let mut details = Map::new();
        details.insert("cached_tokens".into(), Value::from(outcome.cached_tokens()));
        let mut usage = Map::new();
        usage.insert("prompt_tokens".into(), Value::from(pt));
        usage.insert("completion_tokens".into(), Value::from(ct));
        usage.insert("total_tokens".into(), Value::from(pt + ct));
        usage.insert("prompt_tokens_details".into(), Value::Object(details));
        last.insert("usage".into(), Value::Object(usage));
        if let Some(t) = &outcome.timings {
            last.insert("timings".into(), timings_value(t));
        }
        out.push(last);
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::dialect::openai::events::ToolCall;
    use crate::inference::FaultClass;
    use console_core::engine::EngineStop;
    use console_core::turn::TurnEnd;
    use serde_json::json;

    fn writer(want_lp: bool, json_mode: bool) -> ChunkWriter {
        ChunkWriter::new(
            "chatcmpl-0123456789abcdef01234567".into(),
            1_700_000_000,
            json!("pulsar-console-synthetic"),
            want_lp,
            json_mode,
        )
    }

    fn frames(chunks: Vec<Map<String, Value>>) -> String {
        chunks
            .into_iter()
            .map(|c| {
                String::from_utf8(data_frame(&Value::Object(c)).unwrap_or_default())
                    .unwrap_or_default()
            })
            .collect()
    }

    fn outcome(finish: &'static str, prompt: u32, completion: u32) -> TurnOutcome {
        TurnOutcome {
            end: TurnEnd::Ended(EngineStop::Length),
            finish,
            prompt_tokens: prompt,
            completion_tokens: completion,
            figures: None,
            timings: None,
            cancelled: false,
        }
    }

    const HEAD: &str = r#"{"id": "chatcmpl-0123456789abcdef01234567", "object": "chat.completion.chunk", "created": 1700000000, "model": "pulsar-console-synthetic", "choices": [{"index": 0, "delta": "#;

    #[test]
    fn reasoning_text_and_the_final_chunk() {
        let mut w = writer(false, false);
        let mut chunks = vec![w.first()];
        let evs = vec![
            AnswerEvent::Reasoning {
                text: "plan".into(),
                logprobs: vec![],
            },
            AnswerEvent::Content {
                text: String::new(),
                logprobs: vec![],
            },
            AnswerEvent::Content {
                text: "hé".into(),
                logprobs: vec![],
            },
        ];
        chunks.extend(w.events(evs).unwrap_or_default());
        chunks.extend(w.end(&outcome("stop", 7, 3)));
        let want = format!(
            "data: {HEAD}{{\"role\": \"assistant\", \"content\": \"\"}}, \"finish_reason\": null}}]}}\n\n\
             data: {HEAD}{{\"reasoning_content\": \"plan\"}}, \"finish_reason\": null}}]}}\n\n\
             data: {HEAD}{{\"content\": \"hé\"}}, \"finish_reason\": null}}]}}\n\n\
             data: {HEAD}{{}}, \"finish_reason\": \"stop\"}}], \"usage\": {{\"prompt_tokens\": 7, \"completion_tokens\": 3, \"total_tokens\": 10, \"prompt_tokens_details\": {{\"cached_tokens\": 0}}}}}}\n\n"
        );
        assert_eq!(frames(chunks), want);
    }

    fn call(id: &str) -> ToolCall {
        ToolCall {
            id: id.into(),
            name: "lookup".into(),
            arguments: json!({"key": "alpha"}),
            namespace: None,
        }
    }

    #[test]
    fn streamed_and_whole_tool_calls() {
        let mut w = writer(false, false);
        let evs = vec![
            AnswerEvent::ToolStart(call("call_a")),
            AnswerEvent::ToolArgs {
                id: "call_a".into(),
                text: "{\"key\": ".into(),
            },
            AnswerEvent::ToolArgs {
                id: "call_a".into(),
                text: "\"alpha\"}".into(),
            },
            AnswerEvent::ToolCall {
                call: call("call_a"),
                complete: true,
            },
            AnswerEvent::ToolCall {
                call: call("call_b"),
                complete: true,
            },
        ];
        let mut chunks = w.events(evs).unwrap_or_default();
        chunks.extend(w.end(&outcome("stop", 2, 9)));
        let want = format!(
            "data: {HEAD}{{\"tool_calls\": [{{\"index\": 0, \"id\": \"call_a\", \"type\": \"function\", \"function\": {{\"name\": \"lookup\", \"arguments\": \"\"}}}}]}}, \"finish_reason\": null}}]}}\n\n\
             data: {HEAD}{{\"tool_calls\": [{{\"index\": 0, \"function\": {{\"arguments\": \"{{\\\"key\\\": \"}}}}]}}, \"finish_reason\": null}}]}}\n\n\
             data: {HEAD}{{\"tool_calls\": [{{\"index\": 0, \"function\": {{\"arguments\": \"\\\"alpha\\\"}}\"}}}}]}}, \"finish_reason\": null}}]}}\n\n\
             data: {HEAD}{{\"tool_calls\": [{{\"index\": 1, \"id\": \"call_b\", \"type\": \"function\", \"function\": {{\"name\": \"lookup\", \"arguments\": \"{{\\\"key\\\": \\\"alpha\\\"}}\"}}}}]}}, \"finish_reason\": null}}]}}\n\n\
             data: {HEAD}{{}}, \"finish_reason\": \"tool_calls\"}}], \"usage\": {{\"prompt_tokens\": 2, \"completion_tokens\": 9, \"total_tokens\": 11, \"prompt_tokens_details\": {{\"cached_tokens\": 0}}}}}}\n\n"
        );
        assert_eq!(frames(chunks), want);
        // Arguments for a call that never opened: the donor's KeyError.
        let err = w.events(vec![AnswerEvent::ToolArgs {
            id: "call_z".into(),
            text: "x".into(),
        }]);
        assert_eq!(
            err.err().map(|e| e.message()),
            Some("malformed request (KeyError: 'call_z')".to_owned())
        );
    }

    #[test]
    fn logprobs_ride_with_text_and_json_mode_holds_the_answer() {
        let mut w = writer(true, true);
        let entry = json!({"token": "{", "logprob": -0.1, "bytes": [123], "top_logprobs": []});
        let evs = vec![
            AnswerEvent::Reasoning {
                text: "r".into(),
                logprobs: vec![json!({"token": "r"})],
            },
            AnswerEvent::Content {
                text: "Sure: {\"a\": 1}".into(),
                logprobs: vec![entry.clone()],
            },
            AnswerEvent::Content {
                text: " ok".into(),
                logprobs: vec![entry],
            },
        ];
        let mut chunks = w.events(evs).unwrap_or_default();
        assert_eq!(chunks.len(), 1);
        chunks.extend(w.end(&outcome("length", 1, 2)));
        let text = frames(chunks);
        assert!(text.starts_with(&format!(
            "data: {HEAD}{{\"reasoning_content\": \"r\"}}, \"finish_reason\": null, \"logprobs\": {{\"content\": [], \"refusal\": null, \"reasoning_content\": [{{\"token\": \"r\"}}]}}}}]}}\n\n"
        )));
        assert!(text.contains(&format!(
            "data: {HEAD}{{\"content\": \"{{\\\"a\\\": 1}}\"}}, \"finish_reason\": null, \"logprobs\": {{\"content\": [{{\"token\": \"{{\", \"logprob\": -0.1, \"bytes\": [123], \"top_logprobs\": []}}, {{\"token\": \"{{\", \"logprob\": -0.1, \"bytes\": [123], \"top_logprobs\": []}}], \"refusal\": null}}}}]}}\n\n"
        )));
        assert!(text.ends_with("\"finish_reason\": \"length\"}], \"usage\": {\"prompt_tokens\": 1, \"completion_tokens\": 2, \"total_tokens\": 3, \"prompt_tokens_details\": {\"cached_tokens\": 0}}}\n\n"));
    }

    #[test]
    fn progress_mcp_cancel_and_error_frames() {
        let mut w = writer(false, false);
        let p = PingProgress {
            total: 8192,
            cache: 2048,
            processed: 4096,
            time_ms: 251,
        };
        assert_eq!(
            frames(vec![w.progress(p)]),
            format!("data: {HEAD}{{}}, \"finish_reason\": null}}], \"prompt_progress\": {{\"total\": 8192, \"cache\": 2048, \"processed\": 4096, \"time_ms\": 251}}}}\n\n")
        );
        let mcp = w
            .events(vec![AnswerEvent::Mcp(json!({"tool": "x"}))])
            .unwrap_or_default();
        assert_eq!(
            frames(mcp),
            format!("data: {HEAD}{{}}, \"finish_reason\": null}}], \"strata_mcp\": {{\"tool\": \"x\"}}}}\n\n")
        );
        assert_eq!(wire_finish("cancel", 0), "stop");
        assert_eq!(wire_finish("cancel", 2), "stop");
        assert_eq!(wire_finish("length", 2), "length");
        assert_eq!(wire_finish("stop", 1), "tool_calls");
        let died = StreamFault {
            class: FaultClass::EngineDied,
            message: "the engine stopped unexpectedly (exit code -9); the next request restarts it"
                .into(),
        };
        let bytes: Vec<u8> = error_frames(&died).concat();
        assert_eq!(
            String::from_utf8(bytes).unwrap_or_default(),
            "data: {\"error\": {\"type\": \"server_error\", \"message\": \"the engine stopped unexpectedly (exit code -9); the next request restarts it\"}}\n\ndata: [DONE]\n\n"
        );
        // ensure_ascii=True for the error event only.
        let err = StreamFault {
            class: FaultClass::Value,
            message: "héllo".into(),
        };
        assert_eq!(
            error_frames(&err).first().cloned().unwrap_or_default(),
            b"data: {\"error\": {\"type\": \"server_error\", \"message\": \"h\\u00e9llo\"}}\n\n"
                .to_vec()
        );
    }

    #[test]
    fn timings_in_the_donor_order() {
        let t = RequestTimings {
            cache_n: 5,
            prompt_n: 20,
            prompt_ms: 40.0,
            prompt_per_token_ms: Some(2.0),
            prompt_per_second: Some(500.0),
            predicted_n: 3,
            predicted_ms: 60.0,
            predicted_per_token_ms: None,
            predicted_per_second: None,
            drafts: Some((4, 3)),
        };
        assert_eq!(
            to_wire(&timings_value(&t)).unwrap_or_default(),
            r#"{"cache_n": 5, "prompt_n": 20, "prompt_ms": 40.0, "prompt_per_token_ms": 2.0, "prompt_per_second": 500.0, "predicted_n": 3, "predicted_ms": 60.0, "predicted_per_token_ms": null, "predicted_per_second": null, "draft_n": 4, "draft_n_accepted": 3}"#
        );
    }
}
