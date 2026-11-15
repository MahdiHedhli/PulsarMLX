//! Substitution tokens.
//!
//! Committed scenario files must not hold literal host addresses in host fields, real
//! ports, machine paths or key values long enough to look like a credential: the
//! commit-time scan refuses them. A scenario writes a token instead, and the runner
//! expands it once it knows the value:
//!
//! - `{{loopback}}`: the loopback address the server under test listens on;
//! - `{{port}}`: the port it listens on, known only after it has started;
//! - `{{tmp}}`: the per-scenario temporary directory (the data directory's parent);
//! - `{{key_short}}`: an API key shorter than 16 characters, made up for the run.
//!
//! A token is `{{` followed by lower-case letters and underscores and then `}}`. Any such
//! sequence must be one of the four names, anywhere in any string value of a scenario
//! (object keys are never expanded); other text containing braces is left alone, so a
//! body may carry `{{ x }}` or a lone `{{`. Expansion is a single pass: the expanded
//! values are never scanned again.

use serde_json::{Map, Value};

use super::error::{ErrorKind, Result, ScenarioError};
use super::json;

/// The tokens the format defines, without braces.
pub const TOKENS: &[&str] = &["loopback", "port", "tmp", "key_short"];

/// The longest a `{{key_short}}` value may be. Shorter than 16 characters, so that no
/// expanded scenario written to a log or a report looks like a credential to the scan.
pub const KEY_SHORT_MAX_CHARS: usize = 15;

/// One token occurrence found in a string: the byte range of `{{name}}` and the name.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Occurrence<'a> {
    start: usize,
    end: usize,
    name: &'a str,
}

/// Every `{{name}}` sequence in `s`, left to right, whatever the name.
fn occurrences(s: &str) -> Vec<Occurrence<'_>> {
    let bytes = s.as_bytes();
    let mut found = Vec::new();
    let mut at = 0usize;
    while let Some(rel) = s.get(at..).and_then(|rest| rest.find("{{")) {
        let open = at + rel;
        let name_start = open + 2;
        let mut name_end = name_start;
        while bytes
            .get(name_end)
            .is_some_and(|b| b.is_ascii_lowercase() || *b == b'_')
        {
            name_end += 1;
        }
        let closes = bytes.get(name_end) == Some(&b'}') && bytes.get(name_end + 1) == Some(&b'}');
        if name_end > name_start && closes {
            if let Some(name) = s.get(name_start..name_end) {
                found.push(Occurrence {
                    start: open,
                    end: name_end + 2,
                    name,
                });
            }
            at = name_end + 2;
        } else {
            at = open + 1;
        }
    }
    found
}

/// Fails on the first string anywhere in `value` that holds an undefined token.
pub(crate) fn check_tokens(value: &Value, pointer: &str) -> Result<()> {
    match value {
        Value::String(s) => {
            for occ in occurrences(s) {
                if !TOKENS.contains(&occ.name) {
                    return Err(ScenarioError::new(
                        pointer,
                        ErrorKind::UnknownToken {
                            token: format!("{{{{{}}}}}", occ.name),
                        },
                    ));
                }
            }
            Ok(())
        }
        Value::Array(items) => items
            .iter()
            .enumerate()
            .try_for_each(|(i, item)| check_tokens(item, &json::index(pointer, i))),
        Value::Object(map) => map
            .iter()
            .try_for_each(|(k, v)| check_tokens(v, &json::child(pointer, k))),
        _ => Ok(()),
    }
}

/// The run-time values of the substitution tokens. A token without a value cannot be
/// expanded: the scenario fails with [`ErrorKind::UnboundToken`] at the string that
/// uses it, so a configuration written before the server has a port cannot silently
/// carry an unexpanded `{{port}}`.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Substitutions {
    loopback: Option<String>,
    port: Option<u16>,
    tmp: Option<String>,
    key_short: Option<String>,
}

impl Substitutions {
    /// No token has a value yet.
    pub fn new() -> Self {
        Self::default()
    }

    /// Sets `{{loopback}}`. Refused when empty or when it holds whitespace, a control
    /// character or `{{`.
    pub fn with_loopback(mut self, address: &str) -> Result<Self> {
        plain_value("loopback", address)?;
        self.loopback = Some(address.to_string());
        Ok(self)
    }

    /// Sets `{{port}}`.
    pub fn with_port(mut self, port: u16) -> Self {
        self.port = Some(port);
        self
    }

    /// Sets `{{tmp}}`. Refused when empty or when it holds a control character or `{{`.
    pub fn with_tmp(mut self, path: &str) -> Result<Self> {
        if path.is_empty() || path.chars().any(char::is_control) || path.contains("{{") {
            return Err(ScenarioError::invalid(
                "",
                "the {{tmp}} value must be a non-empty path without control characters or {{",
            ));
        }
        self.tmp = Some(path.to_string());
        Ok(self)
    }

    /// Sets `{{key_short}}`: 1 to [`KEY_SHORT_MAX_CHARS`] characters from
    /// `[A-Za-z0-9._-]`.
    pub fn with_key_short(mut self, key: &str) -> Result<Self> {
        let ok = !key.is_empty()
            && key.chars().count() <= KEY_SHORT_MAX_CHARS
            && key
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'));
        if !ok {
            return Err(ScenarioError::invalid(
                "",
                format!(
                    "the {{{{key_short}}}} value must be 1 to {KEY_SHORT_MAX_CHARS} characters from [A-Za-z0-9._-]"
                ),
            ));
        }
        self.key_short = Some(key.to_string());
        Ok(self)
    }

    /// The value of token `name`, when set.
    pub fn value(&self, name: &str) -> Option<String> {
        match name {
            "loopback" => self.loopback.clone(),
            "port" => self.port.map(|p| p.to_string()),
            "tmp" => self.tmp.clone(),
            "key_short" => self.key_short.clone(),
            _ => None,
        }
    }

    /// `s` with every token replaced by its value. `pointer` names `s` in errors.
    pub fn expand_str(&self, s: &str, pointer: &str) -> Result<String> {
        let mut out = String::with_capacity(s.len());
        let mut last = 0usize;
        for occ in occurrences(s) {
            let token = || format!("{{{{{}}}}}", occ.name);
            if !TOKENS.contains(&occ.name) {
                return Err(ScenarioError::new(
                    pointer,
                    ErrorKind::UnknownToken { token: token() },
                ));
            }
            let Some(value) = self.value(occ.name) else {
                return Err(ScenarioError::new(
                    pointer,
                    ErrorKind::UnboundToken { token: token() },
                ));
            };
            out.push_str(s.get(last..occ.start).unwrap_or_default());
            out.push_str(&value);
            last = occ.end;
        }
        out.push_str(s.get(last..).unwrap_or_default());
        Ok(out)
    }

    /// A copy of `value` with every string value expanded; object keys are kept as
    /// written.
    pub fn expand_value(&self, value: &Value, pointer: &str) -> Result<Value> {
        Ok(match value {
            Value::String(s) => Value::String(self.expand_str(s, pointer)?),
            Value::Array(items) => Value::Array(
                items
                    .iter()
                    .enumerate()
                    .map(|(i, item)| self.expand_value(item, &json::index(pointer, i)))
                    .collect::<Result<Vec<_>>>()?,
            ),
            Value::Object(map) => {
                let mut out = Map::new();
                for (k, v) in map {
                    out.insert(k.clone(), self.expand_value(v, &json::child(pointer, k))?);
                }
                Value::Object(out)
            }
            other => other.clone(),
        })
    }
}

fn plain_value(name: &str, value: &str) -> Result<()> {
    if value.is_empty()
        || value.chars().any(|c| c.is_whitespace() || c.is_control())
        || value.contains("{{")
    {
        return Err(ScenarioError::invalid(
            "",
            format!("the {{{{{name}}}}} value must be non-empty, without whitespace, control characters or {{{{"),
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn full() -> Substitutions {
        Substitutions::new()
            .with_loopback("127.0.0.1")
            .unwrap()
            .with_port(40123)
            .with_tmp("/tmp/cnf-x")
            .unwrap()
            .with_key_short("k-12")
            .unwrap()
    }

    #[test]
    fn every_token_expands() {
        let s = full()
            .expand_str(
                "http://{{loopback}}:{{port}}/v1 {{tmp}}/a Bearer {{key_short}}",
                "/p",
            )
            .unwrap();
        assert_eq!(s, "http://127.0.0.1:40123/v1 /tmp/cnf-x/a Bearer k-12");
    }

    #[test]
    fn text_with_braces_that_is_not_a_token_is_left_alone() {
        let subs = full();
        for s in [
            "{{ messages }}",
            "{{",
            "}}",
            "{{}}",
            "{{Port}}",
            "{{port",
            "{{{{port}}}}",
        ] {
            let got = subs.expand_str(s, "/p");
            if s == "{{{{port}}}}" {
                // the inner sequence is a token: only it is replaced
                assert_eq!(got.unwrap(), "{{40123}}");
            } else {
                assert_eq!(got.unwrap(), s);
            }
        }
    }

    #[test]
    fn unknown_token_is_refused_at_load_and_at_expansion() {
        let err = check_tokens(&json!({"a": ["x", "{{loopbak}}"]}), "").unwrap_err();
        assert_eq!(err.pointer, "/a/1");
        assert_eq!(
            err.kind,
            ErrorKind::UnknownToken {
                token: "{{loopbak}}".into()
            }
        );
        let err = full().expand_str("{{host_name}}", "/q").unwrap_err();
        assert_eq!(err.pointer, "/q");
    }

    #[test]
    fn unbound_token_is_refused() {
        let subs = Substitutions::new().with_loopback("127.0.0.1").unwrap();
        let err = subs.expand_str("{{loopback}}:{{port}}", "/x").unwrap_err();
        assert_eq!(
            err.kind,
            ErrorKind::UnboundToken {
                token: "{{port}}".into()
            }
        );
    }

    #[test]
    fn expansion_is_one_pass() {
        let subs = Substitutions::new().with_tmp("/t/{x}").unwrap();
        assert_eq!(subs.expand_str("{{tmp}}", "").unwrap(), "/t/{x}");
    }

    #[test]
    fn values_are_checked() {
        assert!(Substitutions::new().with_loopback("").is_err());
        assert!(Substitutions::new().with_loopback("127.0.0.1 x").is_err());
        assert!(Substitutions::new().with_tmp("").is_err());
        assert!(Substitutions::new().with_tmp("/a\nb").is_err());
        assert!(Substitutions::new().with_key_short("").is_err());
        assert!(Substitutions::new()
            .with_key_short("0123456789abcdef")
            .is_err());
        assert!(Substitutions::new().with_key_short("bad key").is_err());
        assert!(Substitutions::new()
            .with_key_short("0123456789abcde")
            .is_ok());
    }

    #[test]
    fn keys_are_not_expanded() {
        let v = full()
            .expand_value(&json!({"{{port}}": "{{port}}"}), "")
            .unwrap();
        assert_eq!(v, json!({"{{port}}": "40123"}));
    }
}
