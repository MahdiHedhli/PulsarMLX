//! The debug line of one request (`PULSAR_CONSOLE_DEBUG`, the donor's `MAYA_DEBUG`): one
//! compact line per request while diagnosing blank or empty turns.
//!
//! The line is the donor's, with the `[console]` prefix (B2):
//!
//! ```text
//! [console] req <api>: msgs=<n> tools=<n> max_tokens_raw=<repr>/<repr> max_new=<n>
//!     thinking=<True|False> stream=<True|False> prompt_tokens=<n> last=<repr>:<repr>
//! ```
//!
//! (one line; wrapped here). The values are Python's `repr`s; the preview is the last
//! message's text, its first 80 characters with each newline replaced by a space. As in
//! the donor, a content part whose `text` is not a string makes the line's `join` fail with
//! a `TypeError`, which the request answers as a malformed request (P-3), and a last
//! message that is not an object fails with an `AttributeError`. The line is made log-safe
//! (LD35) before it is written.
//!
//! Behavior reference: project-maya serve/server.py:4796-4808 at 7e68a30f.

use console_core::request::pyrepr::{repr_str, repr_value, str_value};
use console_core::turn::log_safe;
use serde_json::{Map, Value};

use super::error::InferenceError;
use crate::error::{MalformedCategory, LOG_PREFIX};

/// The longest preview of the last message, in characters.
pub const DEBUG_PREVIEW_CHARS: usize = 80;

/// What the debug line of one request shows, gathered by the dialect after its prompt is
/// prepared.
#[derive(Debug, Clone, PartialEq)]
pub struct DebugRequest {
    /// The dialect's name in the line (`openai`, `anthropic`, `responses`).
    pub api: &'static str,
    /// The request's `max_tokens`, as sent (`None` when absent).
    pub max_tokens: Option<Value>,
    /// The request's `max_completion_tokens`, as sent.
    pub max_completion_tokens: Option<Value>,
    /// Python's `bool(req.get("stream"))`.
    pub stream: bool,
    /// The number of messages after the dialect's conversion.
    pub messages: usize,
    /// The last of them (`None` when there are none).
    pub last: Option<Value>,
    /// The number of tools offered to the template.
    pub tools: usize,
    /// The answer budget after the context rule.
    pub max_new: u32,
    /// Thinking is on.
    pub thinking: bool,
    /// The prompt's length in tokens.
    pub prompt_tokens: usize,
}

impl DebugRequest {
    /// The fields the line reads from the request and its converted messages.
    pub fn from_request(
        api: &'static str,
        req: &Map<String, Value>,
        messages: &[Value],
        tools: usize,
        max_new: u32,
        thinking: bool,
        prompt_tokens: usize,
    ) -> Self {
        Self {
            api,
            max_tokens: req.get("max_tokens").cloned(),
            max_completion_tokens: req.get("max_completion_tokens").cloned(),
            stream: req.get("stream").is_some_and(truthy),
            messages: messages.len(),
            last: messages.last().cloned(),
            tools,
            max_new,
            thinking,
            prompt_tokens,
        }
    }

    /// The debug line, or the error the donor's line raises (see the module
    /// documentation).
    pub fn line(&self) -> Result<String, InferenceError> {
        let empty = Map::new();
        let last = match &self.last {
            None => &empty,
            Some(Value::Object(m)) => m,
            Some(other) => {
                return Err(InferenceError::malformed(
                    MalformedCategory::AttributeError,
                    format!("'{}' object has no attribute 'get'", py_type(other)),
                ))
            }
        };
        let body = match last.get("content") {
            Some(Value::Array(parts)) => Some(Value::String(join_texts(parts)?)),
            other => other.cloned(),
        };
        let text = match &body {
            Some(v) if truthy(v) => str_value(v),
            _ => String::new(),
        };
        let preview: String = text
            .chars()
            .take(DEBUG_PREVIEW_CHARS)
            .collect::<String>()
            .replace('\n', " ");
        let line = format!(
            "{LOG_PREFIX} req {}: msgs={} tools={} max_tokens_raw={}/{} max_new={} thinking={} \
             stream={} prompt_tokens={} last={}:{}",
            self.api,
            self.messages,
            self.tools,
            repr_opt(self.max_tokens.as_ref()),
            repr_opt(self.max_completion_tokens.as_ref()),
            self.max_new,
            py_bool(self.thinking),
            py_bool(self.stream),
            self.prompt_tokens,
            repr_opt(last.get("role")),
            repr_str(&preview),
        );
        Ok(log_safe(&line))
    }
}

/// `" ".join(p.get("text", "") for p in parts if isinstance(p, dict))`: a `TypeError` when
/// an item is not a string, numbered among the joined items as Python numbers them.
fn join_texts(parts: &[Value]) -> Result<String, InferenceError> {
    let mut out: Vec<&str> = Vec::new();
    for part in parts {
        let Value::Object(m) = part else { continue };
        match m.get("text") {
            None => out.push(""),
            Some(Value::String(s)) => out.push(s),
            Some(other) => {
                return Err(InferenceError::malformed(
                    MalformedCategory::TypeError,
                    format!(
                        "sequence item {}: expected str instance, {} found",
                        out.len(),
                        py_type(other)
                    ),
                ))
            }
        }
    }
    Ok(out.join(" "))
}

/// Python's `repr` of an optional value (`None` when absent).
fn repr_opt(v: Option<&Value>) -> String {
    v.map_or_else(|| String::from("None"), repr_value)
}

fn py_bool(b: bool) -> &'static str {
    if b {
        "True"
    } else {
        "False"
    }
}

/// The Python type name of a decoded JSON value.
fn py_type(v: &Value) -> &'static str {
    match v {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(n) if n.is_i64() || n.is_u64() || is_integer_text(&n.to_string()) => "int",
        Value::Number(_) => "float",
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

/// True for the text of an integer literal (an integer beyond 64 bits keeps its digits
/// under `arbitrary_precision`).
fn is_integer_text(text: &str) -> bool {
    let digits = text.strip_prefix('-').unwrap_or(text);
    !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit())
}

/// Python's truth value of a decoded JSON value.
pub(crate) fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => match n.as_f64() {
            Some(f) => f != 0.0,
            None => true,
        },
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn loads(text: &str) -> Value {
        console_pyjson::loads::loads(text).unwrap_or_else(|e| panic!("{e}"))
    }

    fn object(text: &str) -> Map<String, Value> {
        match loads(text) {
            Value::Object(m) => m,
            other => panic!("not an object: {other:?}"),
        }
    }

    #[test]
    fn the_line_has_the_donors_fields_and_reprs() {
        let req = object(r#"{"max_tokens": -1, "stream": true, "messages": []}"#);
        let messages = vec![loads(r#"{"role": "user", "content": "hi\nthere 'x'"}"#)];
        let d = DebugRequest::from_request("openai", &req, &messages, 0, 4086, true, 2);
        assert_eq!(
            d.line().unwrap_or_else(|e| panic!("{e}")),
            "[console] req openai: msgs=1 tools=0 max_tokens_raw=-1/None max_new=4086 \
             thinking=True stream=True prompt_tokens=2 last='user':\"hi there 'x'\""
        );
    }

    #[test]
    fn content_parts_are_joined_and_the_preview_is_cut() {
        let req = object(r#"{"max_completion_tokens": 7.5, "stream": 0}"#);
        let long = "a".repeat(100);
        let messages = vec![
            loads(r#"{"role": "system", "content": "s"}"#),
            loads(&format!(
                r#"{{"role": "user", "content": [{{"type": "text", "text": "x"}}, "skip", {{"type": "image"}}, {{"text": "{long}"}}]}}"#
            )),
        ];
        let d = DebugRequest::from_request("anthropic", &req, &messages, 3, 10, false, 99);
        let line = d.line().unwrap_or_else(|e| panic!("{e}"));
        let preview: String = format!("x  {long}").chars().take(80).collect();
        assert_eq!(
            line,
            format!(
                "[console] req anthropic: msgs=2 tools=3 max_tokens_raw=None/7.5 max_new=10 \
                 thinking=False stream=False prompt_tokens=99 last='user':'{preview}'"
            )
        );
    }

    #[test]
    fn no_messages_and_odd_content() {
        let req = Map::new();
        let d = DebugRequest::from_request("openai", &req, &[], 0, 1, true, 0);
        assert!(d
            .line()
            .unwrap_or_else(|e| panic!("{e}"))
            .ends_with("prompt_tokens=0 last=None:''"));
        let messages = vec![loads(r#"{"role": "user", "content": {"a": 1}}"#)];
        let d = DebugRequest::from_request("openai", &req, &messages, 0, 1, true, 0);
        assert!(d
            .line()
            .unwrap_or_else(|e| panic!("{e}"))
            .ends_with("last='user':\"{'a': 1}\""));
        let messages = vec![loads(r#"{"role": "user", "content": null}"#)];
        let d = DebugRequest::from_request("openai", &req, &messages, 0, 1, true, 0);
        assert!(d
            .line()
            .unwrap_or_else(|e| panic!("{e}"))
            .ends_with("last='user':''"));
    }

    #[test]
    fn a_text_that_is_not_a_string_is_a_type_error() {
        let req = Map::new();
        let messages = vec![loads(
            r#"{"role": "user", "content": [{"text": "a"}, 5, {"text": 3}]}"#,
        )];
        let d = DebugRequest::from_request("openai", &req, &messages, 0, 1, true, 0);
        assert_eq!(
            d.line(),
            Err(InferenceError::malformed(
                MalformedCategory::TypeError,
                "sequence item 1: expected str instance, int found"
            ))
        );
        let messages = vec![loads(r#""just text""#)];
        let d = DebugRequest::from_request("openai", &req, &messages, 0, 1, true, 0);
        assert_eq!(
            d.line(),
            Err(InferenceError::malformed(
                MalformedCategory::AttributeError,
                "'str' object has no attribute 'get'"
            ))
        );
    }

    #[test]
    fn engine_or_client_text_stays_on_one_line() {
        let req = Map::new();
        let messages = vec![loads(r#"{"role": "us\u0085er", "content": "a\u2028b"}"#)];
        let d = DebugRequest::from_request("openai", &req, &messages, 0, 1, true, 0);
        let line = d.line().unwrap_or_else(|e| panic!("{e}"));
        assert!(
            !line.contains('\u{2028}') && !line.contains('\u{85}'),
            "{line}"
        );
        assert_eq!(line.lines().count(), 1);
    }

    #[test]
    fn truth_values_follow_python() {
        for (text, want) in [
            ("null", false),
            ("false", false),
            ("0", false),
            ("0.0", false),
            ("\"\"", false),
            ("[]", false),
            ("{}", false),
            ("1", true),
            ("-0.5", true),
            ("\"0\"", true),
            ("[0]", true),
            ("{\"a\": null}", true),
        ] {
            assert_eq!(truthy(&loads(text)), want, "{text}");
        }
        assert_eq!(py_type(&loads("123456789012345678901234567890")), "int");
        assert_eq!(py_type(&loads("1.5")), "float");
        assert_eq!(py_type(&loads("1e5")), "float");
    }
}
