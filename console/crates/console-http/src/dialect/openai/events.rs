//! The events of one answer, as the output stage hands them to the chunk writer: text of
//! the reasoning or of the answer, tool calls (streamed or whole) and MCP items.
//!
//! In M1 the plain output stage ([`super::PlainOutput`]) produces only content events. The
//! reasoning and tool-call events come from the output parsers of M2 (PRM-06, PRM-09,
//! PRM-16) and the MCP items from RSP-11 (M6); the chunk writer already renders each of
//! them as the donor does, so those packages plug in through [`super::AnswerStage`] alone.
//!
//! Behavior reference: project-maya serve/frontend.py:801-825 and serve/server.py:4973-4990
//! at 7e68a30f.

use console_pyjson::dumps::{dumps, DumpsOptions};
use serde_json::{Map, Value};

use crate::inference::InferenceError;

/// One tool call (the donor's `ToolCall`): its id, its name (namespace-qualified for
/// internal routing when it has a namespace), its arguments object and its namespace.
#[derive(Debug, Clone, PartialEq)]
pub struct ToolCall {
    /// `call_` and 24 hex characters, as the parser gives it.
    pub id: String,
    /// The function's name.
    pub name: String,
    /// The arguments, the donor's `dict`.
    pub arguments: Value,
    /// The namespace, when the call has one.
    pub namespace: Option<String>,
}

impl ToolCall {
    /// The OpenAI form of the call (`to_openai`): `{"id", "type": "function", "function":
    /// {"name", "arguments"}}` and `namespace` last when there is one. `arguments` gives
    /// the arguments text to send (`""` for a call streamed piece by piece); `None` sends
    /// the arguments object as `json.dumps(arguments, ensure_ascii=False)`. With a
    /// namespace, the name is the part after the first `::`.
    ///
    /// Behavior reference: project-maya serve/frontend.py:808-816 at 7e68a30f.
    pub fn to_openai(&self, arguments: Option<&str>) -> Result<Map<String, Value>, InferenceError> {
        let name = match &self.namespace {
            Some(_) => self
                .name
                .split_once("::")
                .map_or(self.name.as_str(), |(_, rest)| rest),
            None => self.name.as_str(),
        };
        let args = match arguments {
            Some(text) => text.to_owned(),
            None => dumps(&self.arguments, &DumpsOptions::wire())
                .map_err(|e| InferenceError::uncaught(e.python_type(), e.to_string()))?,
        };
        let mut function = Map::new();
        function.insert("name".into(), Value::String(name.to_owned()));
        function.insert("arguments".into(), Value::String(args));
        let mut call = Map::new();
        call.insert("id".into(), Value::String(self.id.clone()));
        call.insert("type".into(), Value::String("function".into()));
        call.insert("function".into(), Value::Object(function));
        if let Some(ns) = &self.namespace {
            call.insert("namespace".into(), Value::String(ns.clone()));
        }
        Ok(call)
    }
}

/// One event of an answer (the donor's `Event`, plus its MCP items). Text events carry the
/// OpenAI logprobs entries of their tokens when the request asked for them (empty when it
/// did not, or when no entry waited).
#[derive(Debug, Clone, PartialEq)]
pub enum AnswerEvent {
    /// Reasoning text (`delta.reasoning_content`). Empty text is skipped.
    Reasoning {
        /// The text.
        text: String,
        /// Its tokens' logprobs entries.
        logprobs: Vec<Value>,
    },
    /// Answer text (`delta.content`). Empty text is skipped.
    Content {
        /// The text.
        text: String,
        /// Its tokens' logprobs entries.
        logprobs: Vec<Value>,
    },
    /// A streamed call opens: its id and name, with empty arguments.
    ToolStart(ToolCall),
    /// A piece of a streamed call's arguments.
    ToolArgs {
        /// The id of the call [`AnswerEvent::ToolStart`] opened.
        id: String,
        /// The piece.
        text: String,
    },
    /// A whole call. One already streamed (same id) is skipped.
    ToolCall {
        /// The call.
        call: ToolCall,
        /// False when the model never closed the call's syntax.
        complete: bool,
    },
    /// An MCP item for the web app (`strata_mcp`, RSP-11).
    Mcp(Value),
}

#[cfg(test)]
mod tests {
    use super::*;
    use console_pyjson::dumps::to_wire;
    use serde_json::json;

    fn call(namespace: Option<&str>) -> ToolCall {
        ToolCall {
            id: "call_0123".into(),
            name: "files::lookup".into(),
            arguments: json!({"key": "é"}),
            namespace: namespace.map(str::to_owned),
        }
    }

    #[test]
    fn to_openai_has_the_donor_keys_in_order() {
        let plain = Value::Object(call(None).to_openai(None).unwrap_or_default());
        assert_eq!(
            to_wire(&plain).unwrap_or_default(),
            r#"{"id": "call_0123", "type": "function", "function": {"name": "files::lookup", "arguments": "{\"key\": \"é\"}"}}"#
        );
        let streamed = Value::Object(call(Some("files")).to_openai(Some("")).unwrap_or_default());
        assert_eq!(
            to_wire(&streamed).unwrap_or_default(),
            r#"{"id": "call_0123", "type": "function", "function": {"name": "lookup", "arguments": ""}, "namespace": "files"}"#
        );
    }
}
