//! The prompt step of a chat completion: the request's messages to prompt token ids.
//!
//! [`PromptBuilder`] is the seam the prompt packages of M2 implement, in two steps that
//! the dialect calls in the donor's order (`_openai`): [`PromptBuilder::convert`] is
//! `openai_to_messages` (PRM-06: the messages, the tools and the template's keyword
//! arguments, with the JSON-format note and the late system messages of PRM-16); then the
//! dialect reads the answer budget (`int(max_completion_tokens or max_tokens or 0)`) and
//! marks `prepare_start`; then [`PromptBuilder::prepare`] is `Service.prepare` (PRM-03,
//! PRM-08, PRM-11: the chat template, the encoding, the thinking flag and the forced tool
//! call), given the converted messages, the requested budget and the internal flags of
//! `with_shared` (the GLM-DSA template's `level_shared`). The two steps must stay apart:
//! a request with both an invalid `max_tokens` and a prompt the template refuses gets the
//! `max_tokens` error, as in the donor, and `prepare_start` does not time the conversion.
//!
//! In M1 there is no chat template, so [`SyntheticPrompt`] stands in: a fixed form of role
//! and content lines authored for PulsarMLX Console, encoded with the tokenizer and no
//! special literals (lead decision LD45, 2026-11-15). It is not a vendor template and not
//! a fallback: from M2 on, start-up fails without a configured template (binding decision
//! B4). The token counts it gives are not the donor's, so nothing that asserts prompt token
//! counts or rendered prompts is a parity figure in M1.
//!
//! The stand-in walks the messages as the donor's loop does, so that a request the donor
//! refuses while converting its messages is refused here with the same Python class: a
//! `messages` that cannot be iterated is a `TypeError`, an entry that is not an object an
//! `AttributeError`, a content part whose text is not a string a `TypeError` (unless the
//! content carries a picture or a video, where the donor keeps the list), a tool call that
//! is not an object (or whose `function` is not one) an `AttributeError`, and a tool call
//! whose string `arguments` is not JSON the `ValueError` of `json.loads` (the first three
//! classes are 400 `malformed request (...)` under approved deviation P-3; the last is a
//! 400 `invalid_request_error`). What the stand-in does not check is the media sources
//! themselves (`_image_source`, M6) and the template's own refusals (PRM-03).
//!
//! Behavior reference: project-maya serve/frontend.py:176-182, 299-350, 561-566 and
//! 685-724 at 7e68a30f.

use std::sync::Arc;

use console_core::request::pynum::{kind, PyInt};
use console_core::request::pyrepr::str_value;
use console_core::request::InternalFlags;
use console_pyjson::loads::{loads, truthy};
use console_tokenizer::bpe::Tokenize;
use serde_json::{Map, Value};

use crate::error::MalformedCategory;
use crate::inference::InferenceError;

/// A request's messages after the conversion step (`openai_to_messages`).
#[derive(Debug, Clone, PartialEq, Default)]
pub struct ConvertedPrompt {
    /// The converted messages (the debug line reads them).
    pub messages: Vec<Value>,
    /// The number of tools offered to the template.
    pub tools: usize,
    /// The template's keyword arguments (empty in M1).
    pub kwargs: Map<String, Value>,
}

/// A request's prompt, as the prepare step built it.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct BuiltPrompt {
    /// The template opened a reasoning block.
    pub thinking: bool,
    /// The whole prompt, tokenized.
    pub ids: Vec<u32>,
}

/// The prompt step of the OpenAI dialect, in the donor's two steps (see the module
/// documentation for the order the dialect calls them in). M2's prompt packages replace
/// [`SyntheticPrompt`] here; their template and encoder refusals map through
/// [`PromptFailure`](crate::inference::PromptFailure) (approved deviation P-8).
pub trait PromptBuilder: Send + Sync + 'static {
    /// Whether the template is GLM-DSA's (the donor's `svc.template.glm_dsa`), which
    /// `with_shared` needs to set [`InternalFlags::level_shared`].
    fn glm_dsa(&self) -> bool {
        false
    }

    /// `openai_to_messages`: the request (already checked by `check_request`) to the
    /// messages, the tools and the template's keyword arguments.
    fn convert(&self, request: &Map<String, Value>) -> Result<ConvertedPrompt, InferenceError>;

    /// `Service.prepare`: the converted request to the prompt ids and the thinking flag.
    /// `max_new` is the requested answer budget; `flags` are `with_shared`'s.
    fn prepare(
        &self,
        converted: &ConvertedPrompt,
        max_new: &PyInt,
        flags: &InternalFlags,
    ) -> Result<BuiltPrompt, InferenceError>;
}

/// The first line of every synthetic prompt: it says what the prompt is.
pub const SYNTHETIC_PROMPT_HEADER: &str = "pulsar-console synthetic prompt (not a chat template)";

/// The line that ends every synthetic prompt, where the answer starts.
pub const SYNTHETIC_PROMPT_TAIL: &str = "assistant:";

/// The M1 stand-in prompt step (lead decision LD45): the header line, one `<role>:
/// <content>` line per message, then `assistant:`, encoded with the tokenizer and no
/// special literals, so client text never becomes a control token.
#[derive(Clone)]
pub struct SyntheticPrompt {
    tok: Arc<dyn Tokenize + Send + Sync>,
}

impl std::fmt::Debug for SyntheticPrompt {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SyntheticPrompt").finish_non_exhaustive()
    }
}

impl SyntheticPrompt {
    /// The stand-in over `tok` (the byte tokenizer in M1).
    pub fn new(tok: Arc<dyn Tokenize + Send + Sync>) -> Self {
        Self { tok }
    }

    /// The prompt text of `messages` (converted messages, as [`openai_messages`] gives
    /// them).
    pub fn render(messages: &[Value]) -> String {
        let mut text = String::from(SYNTHETIC_PROMPT_HEADER);
        text.push('\n');
        for m in messages {
            let role = m.get("role").map_or_else(|| "None".to_owned(), str_value);
            let content = m.get("content").and_then(Value::as_str).unwrap_or("");
            text.push_str(&role);
            text.push_str(": ");
            text.push_str(content);
            text.push('\n');
        }
        text.push_str(SYNTHETIC_PROMPT_TAIL);
        text
    }
}

impl PromptBuilder for SyntheticPrompt {
    fn convert(&self, request: &Map<String, Value>) -> Result<ConvertedPrompt, InferenceError> {
        Ok(ConvertedPrompt {
            messages: openai_messages(request)?,
            tools: tool_count(request)?,
            kwargs: Map::new(),
        })
    }

    fn prepare(
        &self,
        converted: &ConvertedPrompt,
        _max_new: &PyInt,
        _flags: &InternalFlags,
    ) -> Result<BuiltPrompt, InferenceError> {
        let text = Self::render(&converted.messages);
        let ids = self.tok.encode(&text, false, &[]).map_err(|e| {
            InferenceError::uncaught(
                "ValueError",
                format!("the prompt could not be encoded: {e}"),
            )
        })?;
        Ok(BuiltPrompt {
            thinking: false,
            ids,
        })
    }
}

/// Python's `TypeError` for iterating a value that cannot be iterated.
fn not_iterable(v: &Value) -> InferenceError {
    InferenceError::malformed(
        MalformedCategory::TypeError,
        format!("'{}' object is not iterable", kind(v).type_name()),
    )
}

/// Python's `AttributeError` for `x.get(...)` on a value that is not a dict.
fn no_get(v: &Value) -> InferenceError {
    InferenceError::malformed(
        MalformedCategory::AttributeError,
        format!("'{}' object has no attribute 'get'", kind(v).type_name()),
    )
}

/// Python's `AttributeError` for `x.get(...)` on a string (a character of a string, or
/// a key of a dict, being iterated).
fn str_no_get() -> InferenceError {
    InferenceError::malformed(
        MalformedCategory::AttributeError,
        "'str' object has no attribute 'get'",
    )
}

/// The dicts a Python `for x in value: x.get(...)` loop reads from a decoded JSON value,
/// without building anything per item: a list's items (borrowed); an empty string or dict
/// gives none; a non-empty string or dict fails on its first item (a `str`) with the
/// `AttributeError`; anything else is the `TypeError` of iterating it.
fn dict_items(v: &Value) -> Result<&[Value], InferenceError> {
    match v {
        Value::Array(items) => Ok(items),
        Value::String(s) if s.is_empty() => Ok(&[]),
        Value::Object(m) if m.is_empty() => Ok(&[]),
        Value::String(_) | Value::Object(_) => Err(str_no_get()),
        other => Err(not_iterable(other)),
    }
}

/// `_has_media(content)`: a list with a picture or video part.
///
/// Behavior reference: project-maya serve/frontend.py:185-186 and 299-301 at 7e68a30f.
fn has_media(content: Option<&Value>) -> bool {
    const MEDIA: [&str; 6] = [
        "image_url",
        "input_image",
        "image",
        "video_url",
        "input_video",
        "video",
    ];
    match content {
        Some(Value::Array(parts)) => parts.iter().any(|p| {
            p.get("type")
                .and_then(Value::as_str)
                .is_some_and(|t| MEDIA.contains(&t))
        }),
        _ => false,
    }
}

/// The stand-in's text of a content that carries media (the donor's `_parts_of` list
/// form): the string texts of its text parts, joined; a text that is not a string is kept
/// by the donor as it is, and adds nothing here.
fn media_text(content: Option<&Value>) -> String {
    let mut out = String::new();
    if let Some(Value::Array(parts)) = content {
        for p in parts {
            let Value::Object(p) = p else {
                continue;
            };
            let text_type = match p.get("type") {
                None | Some(Value::Null) => true,
                Some(Value::String(t)) => t == "text" || t == "input_text",
                Some(_) => false,
            };
            if let (true, Some(Value::String(s))) = (text_type, p.get("text")) {
                out.push_str(s);
            }
        }
    }
    out
}

/// The donor's walk of an assistant message's `tool_calls` (already truthy): each call
/// must be a dict, its `function` (or the call itself) a dict, and string `arguments`
/// that are not blank must be JSON (`json.loads`, whose failure is a `ValueError`).
///
/// Behavior reference: project-maya serve/frontend.py:688-697 at 7e68a30f.
fn check_tool_calls(calls: &Value) -> Result<(), InferenceError> {
    let items = match calls {
        Value::Array(items) => items.as_slice(),
        Value::String(_) | Value::Object(_) => return Err(str_no_get()),
        other => return Err(not_iterable(other)),
    };
    for c in items {
        let Value::Object(call) = c else {
            return Err(no_get(c));
        };
        let function = call.get("function").unwrap_or(c);
        let Value::Object(f) = function else {
            return Err(no_get(function));
        };
        if let Some(Value::String(args)) = f.get("arguments") {
            if !console_pyjson::pystr::strip(args, None).is_empty() {
                if let Err(e) = loads(args) {
                    return Err(if e.is_value_error() {
                        InferenceError::value(e.to_string())
                    } else {
                        InferenceError::uncaught(e.python_type(), e.to_string())
                    });
                }
            }
        }
    }
    Ok(())
}

/// `_text_of(content)`: no content is `""`, a string is itself, otherwise the texts of the
/// parts of type `text`, `input_text` or none, joined. A part's text that is not a string
/// is Python's `TypeError` from `"".join`.
///
/// Behavior reference: project-maya serve/frontend.py:176-182 at 7e68a30f.
pub fn text_of(content: Option<&Value>) -> Result<String, InferenceError> {
    let content = match content {
        None | Some(Value::Null) => return Ok(String::new()),
        Some(Value::String(s)) => return Ok(s.clone()),
        Some(v) => v,
    };
    let mut out = String::new();
    let mut k = 0usize;
    let parts: &[Value] = match content {
        Value::Array(items) => items,
        // A dict's keys and a string's characters are never dicts: no text.
        Value::Object(_) | Value::String(_) => &[],
        other => return Err(not_iterable(other)),
    };
    for part in parts {
        let Value::Object(p) = part else {
            continue;
        };
        let text_type = match p.get("type") {
            None | Some(Value::Null) => true,
            Some(Value::String(t)) => t == "text" || t == "input_text",
            Some(_) => false,
        };
        if !text_type {
            continue;
        }
        match p.get("text") {
            None => {}
            Some(Value::String(s)) => out.push_str(s),
            Some(other) => {
                return Err(InferenceError::malformed(
                    MalformedCategory::TypeError,
                    format!(
                        "sequence item {k}: expected str instance, {} found",
                        kind(other).type_name()
                    ),
                ))
            }
        }
        k += 1;
    }
    Ok(out)
}

/// The request's messages as the stand-in renders them, read with the donor's loop: a
/// `developer` role is `system`; each message's content is its text (for a user, tool or
/// assistant message that carries pictures or videos, the text of its text parts: the
/// media are M6's and are not rendered in M1); an assistant message's tool calls are
/// walked as the donor walks them; an assistant message with no content, no tool calls
/// and no reasoning is left out; a system message after the first becomes a user
/// message, in place.
///
/// Behavior reference: project-maya serve/frontend.py:561-566 and 677-707 at 7e68a30f.
pub fn openai_messages(request: &Map<String, Value>) -> Result<Vec<Value>, InferenceError> {
    let items = match request.get("messages") {
        None => &[],
        Some(v) => dict_items(v)?,
    };
    let mut out = Vec::new();
    for m in items {
        let Value::Object(m) = m else {
            return Err(no_get(m));
        };
        let mut role = m.get("role").cloned().unwrap_or(Value::Null);
        if role.as_str() == Some("developer") {
            role = Value::String("system".into());
        }
        let parts_role = matches!(role.as_str(), Some("user" | "tool" | "assistant"));
        let media = parts_role && has_media(m.get("content"));
        let content = if media {
            media_text(m.get("content"))
        } else {
            text_of(m.get("content"))?
        };
        let assistant = role.as_str() == Some("assistant");
        let calls = match m.get("tool_calls") {
            Some(c) if truthy(c) => {
                check_tool_calls(c)?;
                true
            }
            _ => false,
        };
        let reasoning = m.get("reasoning_content").is_some_and(truthy);
        // Content with media is a non-empty list in the donor: never an empty turn.
        if assistant && !media && content.is_empty() && !calls && !reasoning {
            continue;
        }
        let mut one = Map::new();
        one.insert("role".into(), role);
        one.insert("content".into(), Value::String(content));
        out.push(Value::Object(one));
    }
    for (i, m) in out.iter_mut().enumerate() {
        if i > 0 && m.get("role").and_then(Value::as_str) == Some("system") {
            if let Some(obj) = m.as_object_mut() {
                obj.insert("role".into(), Value::String("user".into()));
            }
        }
    }
    Ok(out)
}

/// The number of tools the donor offers the template: the request's `tools` (falsy is
/// none), unless `tool_choice` is `"none"`.
///
/// Behavior reference: project-maya serve/frontend.py:708-712 at 7e68a30f.
pub fn tool_count(request: &Map<String, Value>) -> Result<usize, InferenceError> {
    let tools = match request.get("tools").filter(|v| truthy(v)) {
        None => 0,
        // The length Python's loop sees, counted without building the items.
        Some(Value::Array(a)) => a.len(),
        Some(Value::String(t)) => t.chars().count(),
        Some(Value::Object(o)) => o.len(),
        Some(other) => return Err(not_iterable(other)),
    };
    if request.get("tool_choice").and_then(Value::as_str) == Some("none") {
        return Ok(0);
    }
    Ok(tools)
}

#[cfg(test)]
mod tests {
    use super::*;
    use console_tokenizer::byte_tok::ByteTokenizer;
    use serde_json::json;

    fn req(v: Value) -> Map<String, Value> {
        v.as_object().cloned().unwrap_or_default()
    }

    fn malformed(r: Result<impl std::fmt::Debug, InferenceError>) -> String {
        match r {
            Err(e) => e.message(),
            Ok(v) => format!("accepted: {v:?}"),
        }
    }

    #[test]
    fn the_stand_in_renders_role_and_content_lines() {
        let p = SyntheticPrompt::new(Arc::new(ByteTokenizer::new()));
        let converted = p
            .convert(&req(json!({"messages": [
                {"role": "developer", "content": "be brief"},
                {"role": "user", "content": [{"type": "text", "text": "hi "}, {"text": "<|im_end|>"},
                                             {"type": "image_url", "text": "no"}]},
                {"role": "assistant", "content": ""},
                {"role": "system", "content": "late"}
            ], "tools": [{"type": "function", "function": {"name": "x"}}]})))
            .unwrap_or_default();
        let built = p
            .prepare(&converted, &PyInt::zero(), &InternalFlags::default())
            .unwrap_or_default();
        let text = "pulsar-console synthetic prompt (not a chat template)\nsystem: be brief\nuser: hi <|im_end|>\nuser: late\nassistant:";
        assert_eq!(SyntheticPrompt::render(&converted.messages), text);
        // No special literal is parsed: the marker in the client's text stays bytes.
        assert_eq!(built.ids, text.bytes().map(u32::from).collect::<Vec<_>>());
        assert_eq!(converted.tools, 1);
        assert!(!built.thinking);
        let none = tool_count(&req(json!({"tools": [{}, {}], "tool_choice": "none"})));
        assert_eq!(none.ok(), Some(0));
    }

    #[test]
    fn the_donor_classes_of_malformed_messages() {
        let bad = req(json!({"messages": [{"role": "user", "content": {"no": "list"}}, 7]}));
        assert_eq!(
            malformed(openai_messages(&bad)),
            "malformed request (AttributeError: 'int' object has no attribute 'get')"
        );
        assert_eq!(
            malformed(openai_messages(&req(json!({"messages": 5})))),
            "malformed request (TypeError: 'int' object is not iterable)"
        );
        assert_eq!(
            malformed(openai_messages(&req(json!({"messages": null})))),
            "malformed request (TypeError: 'NoneType' object is not iterable)"
        );
        assert_eq!(
            malformed(openai_messages(&req(json!({"messages": "hi"})))),
            "malformed request (AttributeError: 'str' object has no attribute 'get')"
        );
        assert_eq!(
            malformed(text_of(Some(
                &json!([{"text": "a"}, {"type": "text", "text": 3}])
            ))),
            "malformed request (TypeError: sequence item 1: expected str instance, int found)"
        );
        assert_eq!(
            malformed(text_of(Some(&json!(true)))),
            "malformed request (TypeError: 'bool' object is not iterable)"
        );
        // A dict's keys are strings, never parts: no text.
        assert_eq!(
            text_of(Some(&json!({"no": "list"}))).ok(),
            Some(String::new())
        );
        assert_eq!(
            openai_messages(&req(json!({"messages": {}})))
                .map(|m| m.len())
                .ok(),
            Some(0)
        );
        assert_eq!(
            malformed(tool_count(&req(json!({"tools": 3})))),
            "malformed request (TypeError: 'int' object is not iterable)"
        );
    }

    #[test]
    fn the_donor_walk_of_tool_calls_and_media() {
        let with_calls = |calls: Value| {
            req(json!({"messages": [{"role": "assistant", "content": null, "tool_calls": calls}]}))
        };
        assert_eq!(
            malformed(openai_messages(&with_calls(
                json!([{"function": {"name": "f", "arguments": "{bad"}}])
            ))),
            "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"
        );
        assert_eq!(
            malformed(openai_messages(&with_calls(json!([7])))),
            "malformed request (AttributeError: 'int' object has no attribute 'get')"
        );
        assert_eq!(
            malformed(openai_messages(&with_calls(json!([{"function": null}])))),
            "malformed request (AttributeError: 'NoneType' object has no attribute 'get')"
        );
        assert_eq!(
            malformed(openai_messages(&with_calls(json!("x")))),
            "malformed request (AttributeError: 'str' object has no attribute 'get')"
        );
        assert_eq!(
            malformed(openai_messages(&with_calls(json!(3)))),
            "malformed request (TypeError: 'int' object is not iterable)"
        );
        // Blank or JSON arguments, a mapping, or a call with no `function` are accepted,
        // and a turn with tool calls is kept.
        let ok = openai_messages(&with_calls(json!([
            {"function": {"name": "f", "arguments": "  "}},
            {"function": {"name": "g", "arguments": "{\"a\": 1}"}},
            {"name": "h", "arguments": {"a": 1}}
        ])));
        assert_eq!(ok.map(|m| m.len()).ok(), Some(1));
        // With a picture, a text that is not a string is no TypeError, and an
        // assistant turn with only a picture is kept.
        let media = req(json!({"messages": [
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}},
                                         {"type": "text", "text": 3}, {"text": "see"}]},
            {"role": "assistant", "content": [{"type": "image", "source": {}}]},
            {"role": "system", "content": [{"type": "image_url"}, {"text": 3}]}
        ]}));
        assert_eq!(
            malformed(openai_messages(&media)),
            "malformed request (TypeError: sequence item 0: expected str instance, int found)"
        );
        let media = req(json!({"messages": [
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}},
                                         {"type": "text", "text": 3}, {"text": "see"}]},
            {"role": "assistant", "content": [{"type": "image", "source": {}}]}
        ]}));
        let got = openai_messages(&media).unwrap_or_default();
        assert_eq!(got.len(), 2);
        assert_eq!(got[0]["content"], "see");
    }

    #[test]
    fn a_long_string_is_refused_without_building_one_value_per_character() {
        // 8 MiB: building one Value per character would take hundreds of MiB and seconds.
        let long = "a".repeat(8 << 20);
        let started = std::time::Instant::now();
        assert_eq!(
            malformed(openai_messages(&req(json!({"messages": long.clone()})))),
            "malformed request (AttributeError: 'str' object has no attribute 'get')"
        );
        assert_eq!(
            tool_count(&req(json!({"tools": long.clone()}))).ok(),
            Some(8 << 20)
        );
        assert_eq!(
            text_of(Some(&Value::String(long))).ok().map(|t| t.len()),
            Some(8 << 20)
        );
        assert!(
            started.elapsed() < std::time::Duration::from_secs(2),
            "{:?}",
            started.elapsed()
        );
    }
}
