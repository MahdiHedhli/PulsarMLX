//! The non-stream collector (`openai_collect`): a completion's chunks as one
//! `chat.completion` object.
//!
//! Behavior reference: project-maya serve/server.py:5204-5246 at 7e68a30f.

use std::collections::BTreeMap;

use console_pyjson::loads::truthy;
use serde_json::{Map, Value};

/// A field of a JSON object, `None` when the value is not an object (the donor's chunks
/// always are).
fn field<'a>(v: &'a Value, key: &str) -> Option<&'a Value> {
    v.as_object().and_then(|m| m.get(key))
}

/// `x or []` for a list field.
fn list_of(v: Option<&Value>) -> &[Value] {
    match v {
        Some(Value::Array(a)) => a,
        _ => &[],
    }
}

/// `x or ""` for a text field.
fn text_of(v: Option<&Value>) -> &str {
    match v {
        Some(Value::String(s)) => s,
        _ => "",
    }
}

/// The chunks as one `chat.completion`: the content and the reasoning concatenated (no
/// content is `null`, no reasoning leaves the field out), tool-call pieces merged by
/// index (id, namespace, name and arguments), the MCP items gathered, the last chunk's
/// finish reason, usage and timings. Keep-alives and prompt-progress chunks are not
/// answer content. With `logprobs` (the request asked), the choice carries every text
/// chunk's entries in order: `content`, `refusal: null`, and `reasoning_content` when
/// there was reasoning. `None` without a chunk (the donor's `last` would be `None`; the
/// dialect always sends the first chunk).
///
/// Behavior reference: project-maya serve/server.py:5204-5246 at 7e68a30f.
pub fn collect(chunks: &[Value], logprobs: bool) -> Option<Value> {
    let mut content = String::new();
    let mut reasoning = String::new();
    let mut by_index: BTreeMap<i64, Map<String, Value>> = BTreeMap::new();
    let mut last: Option<&Value> = None;
    let mut mcp: Vec<Value> = Vec::new();
    let mut lp_content: Vec<Value> = Vec::new();
    let mut lp_reasoning: Vec<Value> = Vec::new();
    for c in chunks {
        if c.is_null() || field(c, "prompt_progress").is_some_and(truthy) {
            continue;
        }
        if let Some(item) = field(c, "strata_mcp").filter(|v| truthy(v)) {
            mcp.push(item.clone());
        }
        let choice = list_of(field(c, "choices")).first().unwrap_or(&Value::Null);
        if let Some(lp) = field(choice, "logprobs").filter(|v| truthy(v)) {
            lp_content.extend(list_of(field(lp, "content")).iter().cloned());
            lp_reasoning.extend(list_of(field(lp, "reasoning_content")).iter().cloned());
        }
        let delta = field(choice, "delta").unwrap_or(&Value::Null);
        content.push_str(text_of(field(delta, "content")));
        reasoning.push_str(text_of(field(delta, "reasoning_content")));
        for tc in list_of(field(delta, "tool_calls")) {
            let next = i64::try_from(by_index.len()).unwrap_or(i64::MAX);
            let index = field(tc, "index").and_then(Value::as_i64).unwrap_or(next);
            let cur = by_index.entry(index).or_insert_with(|| {
                let mut function = Map::new();
                function.insert("name".into(), Value::String(String::new()));
                function.insert("arguments".into(), Value::String(String::new()));
                let mut m = Map::new();
                m.insert("id".into(), Value::Null);
                m.insert("type".into(), Value::String("function".into()));
                m.insert("function".into(), Value::Object(function));
                m
            });
            if let Some(id) = field(tc, "id").filter(|v| truthy(v)) {
                cur.insert("id".into(), id.clone());
            }
            if let Some(ns) = field(tc, "namespace").filter(|v| !v.is_null()) {
                cur.insert("namespace".into(), ns.clone());
            }
            let f = field(tc, "function").unwrap_or(&Value::Null);
            if let Some(Value::Object(function)) = cur.get_mut("function") {
                for key in ["name", "arguments"] {
                    let piece = text_of(field(f, key));
                    if let Some(Value::String(s)) = function.get_mut(key) {
                        s.push_str(piece);
                    }
                }
            }
        }
        last = Some(c);
    }
    let last = last?;
    let mut msg = Map::new();
    msg.insert("role".into(), Value::String("assistant".into()));
    msg.insert(
        "content".into(),
        if content.is_empty() {
            Value::Null
        } else {
            Value::String(content)
        },
    );
    if !reasoning.is_empty() {
        msg.insert("reasoning_content".into(), Value::String(reasoning));
    }
    if !by_index.is_empty() {
        let calls = by_index.into_values().map(Value::Object).collect();
        msg.insert("tool_calls".into(), Value::Array(calls));
    }
    if !mcp.is_empty() {
        msg.insert("strata_mcp".into(), Value::Array(mcp));
    }
    let last_choice = list_of(field(last, "choices"))
        .first()
        .unwrap_or(&Value::Null);
    let mut choice = Map::new();
    choice.insert("index".into(), Value::from(0));
    choice.insert("message".into(), Value::Object(msg));
    choice.insert(
        "finish_reason".into(),
        field(last_choice, "finish_reason")
            .cloned()
            .unwrap_or(Value::Null),
    );
    if logprobs {
        let mut lp = Map::new();
        lp.insert("content".into(), Value::Array(lp_content));
        lp.insert("refusal".into(), Value::Null);
        if !lp_reasoning.is_empty() {
            lp.insert("reasoning_content".into(), Value::Array(lp_reasoning));
        }
        choice.insert("logprobs".into(), Value::Object(lp));
    }
    let mut out = Map::new();
    for key in ["id", "object", "created", "model"] {
        let value = match key {
            "object" => Value::String("chat.completion".into()),
            _ => field(last, key).cloned().unwrap_or(Value::Null),
        };
        out.insert(key.into(), value);
    }
    out.insert("choices".into(), Value::Array(vec![Value::Object(choice)]));
    out.insert(
        "usage".into(),
        field(last, "usage").cloned().unwrap_or(Value::Null),
    );
    if let Some(t) = field(last, "timings").filter(|v| truthy(v)) {
        out.insert("timings".into(), t.clone());
    }
    Some(Value::Object(out))
}

#[cfg(test)]
mod tests {
    use super::*;
    use console_pyjson::dumps::to_wire;
    use serde_json::json;

    fn chunk(delta: Value, finish: Value) -> Value {
        json!({"id": "chatcmpl-x", "object": "chat.completion.chunk", "created": 5, "model": "m",
               "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]})
    }

    #[test]
    fn content_reasoning_calls_and_usage() {
        let mut last = chunk(json!({}), json!("tool_calls"));
        if let Some(m) = last.as_object_mut() {
            m.insert("usage".into(), json!({"prompt_tokens": 1}));
            m.insert("timings".into(), json!({"cache_n": 0}));
        }
        let mut progress = chunk(json!({"content": "never"}), Value::Null);
        if let Some(m) = progress.as_object_mut() {
            m.insert("prompt_progress".into(), json!({"total": 1}));
        }
        let chunks = vec![
            chunk(json!({"role": "assistant", "content": ""}), Value::Null),
            progress,
            chunk(json!({"reasoning_content": "think"}), Value::Null),
            chunk(json!({"content": "Hi"}), Value::Null),
            chunk(
                json!({"tool_calls": [{"index": 0, "id": "call_a", "type": "function",
                                       "function": {"name": "look", "arguments": ""}, "namespace": "ns"}]}),
                Value::Null,
            ),
            chunk(
                json!({"tool_calls": [{"index": 0, "function": {"arguments": "{\"k\": 1}"}}]}),
                Value::Null,
            ),
            chunk(
                json!({"tool_calls": [{"index": 1, "id": "call_b", "type": "function",
                                       "function": {"name": "up", "arguments": "{}"}}]}),
                Value::Null,
            ),
            last,
        ];
        let out = collect(&chunks, false).unwrap_or_default();
        assert_eq!(
            to_wire(&out).unwrap_or_default(),
            r#"{"id": "chatcmpl-x", "object": "chat.completion", "created": 5, "model": "m", "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hi", "reasoning_content": "think", "tool_calls": [{"id": "call_a", "type": "function", "function": {"name": "look", "arguments": "{\"k\": 1}"}, "namespace": "ns"}, {"id": "call_b", "type": "function", "function": {"name": "up", "arguments": "{}"}}]}, "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 1}, "timings": {"cache_n": 0}}"#
        );
    }

    #[test]
    fn no_content_is_null_and_logprobs_are_gathered() {
        let mut text = chunk(json!({"content": ""}), Value::Null);
        if let Some(c) = text
            .pointer_mut("/choices/0")
            .and_then(Value::as_object_mut)
        {
            c.insert(
                "logprobs".into(),
                json!({"content": [{"token": "a"}], "refusal": null}),
            );
        }
        let mut last = chunk(json!({}), json!("stop"));
        if let Some(m) = last.as_object_mut() {
            m.insert("usage".into(), json!({}));
        }
        let out = collect(&[text, last], true).unwrap_or_default();
        assert_eq!(
            to_wire(&out).unwrap_or_default(),
            r#"{"id": "chatcmpl-x", "object": "chat.completion", "created": 5, "model": "m", "choices": [{"index": 0, "message": {"role": "assistant", "content": null}, "finish_reason": "stop", "logprobs": {"content": [{"token": "a"}], "refusal": null}}], "usage": {}}"#
        );
        assert_eq!(collect(&[], false), None);
    }
}
