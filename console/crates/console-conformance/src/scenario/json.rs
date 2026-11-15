//! Strict JSON reading and the small typed checks the loaders are built from.
//!
//! `serde_json` keeps the last of two equal keys without a word. A scenario that says
//! `"max_context"` twice is a mistake that would silently change what is tested, so the
//! reader here refuses it: before the document is parsed into a value, a second pass of
//! the same reader walks it and fails on the first repeated key, naming the object by its
//! JSON pointer. Nesting depth is bounded by `serde_json`'s own recursion limit (128).

use std::cell::RefCell;
use std::collections::HashSet;
use std::fmt;

use serde::de::{self, DeserializeSeed, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Value};

use super::error::{ErrorKind, Result, ScenarioError};

/// Parses `text` as one JSON document of at most `limit` bytes, refusing repeated keys.
pub(crate) fn parse_strict(text: &str, limit: usize) -> Result<Value> {
    if text.len() > limit {
        return Err(ScenarioError::new("", ErrorKind::TooLarge { limit }));
    }
    let slot = RefCell::new(None);
    let mut de = serde_json::Deserializer::from_str(text);
    let checked = DupCheck {
        pointer: String::new(),
        slot: &slot,
    }
    .deserialize(&mut de)
    .and_then(|()| de.end());
    if let Err(err) = checked {
        if let Some((pointer, key)) = slot.into_inner() {
            return Err(ScenarioError::new(pointer, ErrorKind::DuplicateKey { key }));
        }
        return Err(syntax(&err));
    }
    serde_json::from_str(text).map_err(|err| syntax(&err))
}

fn syntax(err: &serde_json::Error) -> ScenarioError {
    let full = err.to_string();
    // serde_json appends " at line L column C"; the position is reported separately.
    let message = match full.rfind(" at line ") {
        Some(cut) => full[..cut].to_string(),
        None => full,
    };
    ScenarioError::new(
        "",
        ErrorKind::Syntax {
            line: err.line(),
            column: err.column(),
            message,
        },
    )
}

/// Walks a document and records the first repeated key with the pointer of its object.
struct DupCheck<'s> {
    pointer: String,
    slot: &'s RefCell<Option<(String, String)>>,
}

impl<'de> DeserializeSeed<'de> for DupCheck<'_> {
    type Value = ();

    fn deserialize<D: de::Deserializer<'de>>(
        self,
        deserializer: D,
    ) -> std::result::Result<(), D::Error> {
        deserializer.deserialize_any(self)
    }
}

impl<'de> Visitor<'de> for DupCheck<'_> {
    type Value = ();

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("any JSON value")
    }

    fn visit_bool<E: de::Error>(self, _: bool) -> std::result::Result<(), E> {
        Ok(())
    }
    fn visit_i64<E: de::Error>(self, _: i64) -> std::result::Result<(), E> {
        Ok(())
    }
    fn visit_u64<E: de::Error>(self, _: u64) -> std::result::Result<(), E> {
        Ok(())
    }
    fn visit_f64<E: de::Error>(self, _: f64) -> std::result::Result<(), E> {
        Ok(())
    }
    fn visit_str<E: de::Error>(self, _: &str) -> std::result::Result<(), E> {
        Ok(())
    }
    fn visit_unit<E: de::Error>(self) -> std::result::Result<(), E> {
        Ok(())
    }
    fn visit_none<E: de::Error>(self) -> std::result::Result<(), E> {
        Ok(())
    }

    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> std::result::Result<(), A::Error> {
        let mut index = 0usize;
        while seq
            .next_element_seed(DupCheck {
                pointer: format!("{}/{index}", self.pointer),
                slot: self.slot,
            })?
            .is_some()
        {
            index += 1;
        }
        Ok(())
    }

    // With `arbitrary_precision` a number arrives as a one-entry map under a private key;
    // that map has no repeated key, so it passes like any other value.
    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> std::result::Result<(), A::Error> {
        let mut seen = HashSet::new();
        while let Some(key) = map.next_key::<String>()? {
            let child = child(&self.pointer, &key);
            if !seen.insert(key.clone()) {
                *self.slot.borrow_mut() = Some((self.pointer.clone(), key));
                return Err(de::Error::custom("duplicate key"));
            }
            map.next_value_seed(DupCheck {
                pointer: child,
                slot: self.slot,
            })?;
        }
        Ok(())
    }
}

/// The pointer of member `key` of the object at `pointer` (RFC 6901 escaping).
pub(crate) fn child(pointer: &str, key: &str) -> String {
    let escaped = key.replace('~', "~0").replace('/', "~1");
    format!("{pointer}/{escaped}")
}

/// The pointer of element `index` of the array at `pointer`.
pub(crate) fn index(pointer: &str, index: usize) -> String {
    format!("{pointer}/{index}")
}

/// The JSON type name of a value, as error messages give it.
pub(crate) fn kind_name(value: &Value) -> &'static str {
    match value {
        Value::Null => "null",
        Value::Bool(_) => "boolean",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Array(_) => "array",
        Value::Object(_) => "object",
    }
}

fn wrong(pointer: &str, expected: &'static str, value: &Value) -> ScenarioError {
    ScenarioError::new(
        pointer,
        ErrorKind::WrongType {
            expected,
            found: kind_name(value),
        },
    )
}

/// An object being checked: its members and its pointer.
pub(crate) struct Obj<'a> {
    pub(crate) map: &'a Map<String, Value>,
    pub(crate) pointer: String,
}

impl<'a> Obj<'a> {
    /// `value` as an object, or a type error.
    pub(crate) fn of(value: &'a Value, pointer: &str) -> Result<Self> {
        match value {
            Value::Object(map) => Ok(Self {
                map,
                pointer: pointer.to_string(),
            }),
            other => Err(wrong(pointer, "object", other)),
        }
    }

    /// Fails on the first key, in document order, that `allowed` does not list.
    pub(crate) fn allow_only(&self, allowed: &[&str]) -> Result<()> {
        match self.map.keys().find(|k| !allowed.contains(&k.as_str())) {
            Some(field) => Err(ScenarioError::new(
                self.pointer.clone(),
                ErrorKind::UnknownField {
                    field: field.clone(),
                },
            )),
            None => Ok(()),
        }
    }

    /// The member `key` and its pointer, when present.
    pub(crate) fn get(&self, key: &str) -> Option<(&'a Value, String)> {
        self.map.get(key).map(|v| (v, child(&self.pointer, key)))
    }

    /// The member `key` and its pointer, or a missing-field error.
    pub(crate) fn required(&self, key: &'static str) -> Result<(&'a Value, String)> {
        self.get(key).ok_or_else(|| {
            ScenarioError::new(self.pointer.clone(), ErrorKind::MissingField { field: key })
        })
    }

    /// Fails when both `first` and `second` are present.
    pub(crate) fn exclusive(&self, first: &'static str, second: &'static str) -> Result<()> {
        if self.map.contains_key(first) && self.map.contains_key(second) {
            return Err(ScenarioError::new(
                self.pointer.clone(),
                ErrorKind::Exclusive { first, second },
            ));
        }
        Ok(())
    }
}

/// `value` as a string of at most `max_chars` characters.
pub(crate) fn string<'a>(value: &'a Value, pointer: &str, max_chars: usize) -> Result<&'a str> {
    match value {
        Value::String(s) => {
            if s.chars().count() > max_chars {
                return Err(ScenarioError::new(
                    pointer,
                    ErrorKind::TooLong { limit: max_chars },
                ));
            }
            Ok(s)
        }
        other => Err(wrong(pointer, "string", other)),
    }
}

/// `value` as a non-empty string of at most `max_chars` characters.
pub(crate) fn nonempty_string<'a>(
    value: &'a Value,
    pointer: &str,
    max_chars: usize,
) -> Result<&'a str> {
    let s = string(value, pointer, max_chars)?;
    if s.is_empty() {
        return Err(ScenarioError::new(pointer, ErrorKind::Empty));
    }
    Ok(s)
}

/// `value` as a boolean.
pub(crate) fn boolean(value: &Value, pointer: &str) -> Result<bool> {
    match value {
        Value::Bool(b) => Ok(*b),
        other => Err(wrong(pointer, "boolean", other)),
    }
}

/// `value` as an integer in `min..=max`.
pub(crate) fn uint(value: &Value, pointer: &str, min: u64, max: u64) -> Result<u64> {
    let Value::Number(n) = value else {
        return Err(wrong(pointer, "integer", value));
    };
    let range = || ScenarioError::new(pointer, ErrorKind::OutOfRange { min, max });
    match n.as_u64() {
        Some(v) if (min..=max).contains(&v) => Ok(v),
        Some(_) => Err(range()),
        None if n.is_i64() => Err(range()),
        // A fraction, an exponent form or an integer beyond 64 bits.
        None => match n.as_f64() {
            Some(f)
                if f.fract() == 0.0
                    && n.to_string()
                        .bytes()
                        .all(|b| b.is_ascii_digit() || b == b'-') =>
            {
                Err(range())
            }
            _ => Err(ScenarioError::new(
                pointer,
                ErrorKind::WrongType {
                    expected: "integer",
                    found: "number with a fraction or exponent",
                },
            )),
        },
    }
}

/// `value` as a finite number greater than zero and at most `max`.
pub(crate) fn positive_number(value: &Value, pointer: &str, max: f64) -> Result<f64> {
    let Value::Number(n) = value else {
        return Err(wrong(pointer, "number", value));
    };
    match n.as_f64() {
        Some(f) if f.is_finite() && f > 0.0 && f <= max => Ok(f),
        _ => Err(ScenarioError::invalid(
            pointer,
            format!("must be a number greater than 0 and at most {max}"),
        )),
    }
}

/// `value` as an array of at most `limit` entries.
pub(crate) fn array<'a>(value: &'a Value, pointer: &str, limit: usize) -> Result<&'a [Value]> {
    match value {
        Value::Array(items) => {
            if items.len() > limit {
                return Err(ScenarioError::new(pointer, ErrorKind::TooMany { limit }));
            }
            Ok(items)
        }
        other => Err(wrong(pointer, "array", other)),
    }
}

/// `value` as a non-empty array of at most `limit` entries.
pub(crate) fn nonempty_array<'a>(
    value: &'a Value,
    pointer: &str,
    limit: usize,
) -> Result<&'a [Value]> {
    let items = array(value, pointer, limit)?;
    if items.is_empty() {
        return Err(ScenarioError::new(pointer, ErrorKind::Empty));
    }
    Ok(items)
}

/// `value` as an object of at most `limit` members.
pub(crate) fn object_limited<'a>(
    value: &'a Value,
    pointer: &str,
    limit: usize,
) -> Result<&'a Map<String, Value>> {
    match value {
        Value::Object(map) => {
            if map.len() > limit {
                return Err(ScenarioError::new(pointer, ErrorKind::TooMany { limit }));
            }
            Ok(map)
        }
        other => Err(wrong(pointer, "object", other)),
    }
}

/// Fails with a type error naming `expected` for `value` at `pointer`.
pub(crate) fn type_error(pointer: &str, expected: &'static str, value: &Value) -> ScenarioError {
    wrong(pointer, expected, value)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn duplicate_key_is_refused_with_the_object_pointer() {
        let err = parse_strict(r#"{"a": {"b/c": [1, {"x": 1, "x": 2}]}}"#, 1024).unwrap_err();
        assert_eq!(err.pointer, "/a/b~1c/1");
        assert_eq!(err.kind, ErrorKind::DuplicateKey { key: "x".into() });
    }

    #[test]
    fn duplicate_top_level_key_names_the_document() {
        let err = parse_strict(r#"{"id": "a", "id": "b"}"#, 1024).unwrap_err();
        assert_eq!(err.pointer, "");
        assert_eq!(err.kind, ErrorKind::DuplicateKey { key: "id".into() });
    }

    #[test]
    fn numbers_and_nested_values_pass() {
        let v = parse_strict(
            r#"{"n": 1.50, "m": [1, -2, 3e2], "s": "x", "t": null, "u": true}"#,
            1024,
        )
        .unwrap();
        // arbitrary_precision keeps the number text exactly.
        assert_eq!(v["n"].to_string(), "1.50");
    }

    #[test]
    fn syntax_error_reports_line_and_column() {
        let err = parse_strict("{\n  \"a\": ,\n}", 1024).unwrap_err();
        match err.kind {
            ErrorKind::Syntax { line, column, .. } => assert_eq!((line, column), (2, 8)),
            other => panic!("unexpected {other:?}"),
        }
        assert_eq!(err.pointer, "");
    }

    #[test]
    fn trailing_text_is_a_syntax_error() {
        let err = parse_strict("{} {}", 1024).unwrap_err();
        assert!(matches!(err.kind, ErrorKind::Syntax { .. }), "{err}");
    }

    #[test]
    fn oversize_document_is_refused_before_parsing() {
        let err = parse_strict("[1, 2, 3]", 4).unwrap_err();
        assert_eq!(err.kind, ErrorKind::TooLarge { limit: 4 });
    }

    #[test]
    fn deep_nesting_is_a_syntax_error_not_a_crash() {
        let text = format!("{}{}", "[".repeat(200), "]".repeat(200));
        let err = parse_strict(&text, 4096).unwrap_err();
        assert!(matches!(err.kind, ErrorKind::Syntax { .. }), "{err}");
    }

    #[test]
    fn pointer_escaping_follows_rfc_6901() {
        assert_eq!(child("", "a~b/c"), "/a~0b~1c");
        assert_eq!(index("/x", 3), "/x/3");
    }

    #[test]
    fn uint_bounds_and_types() {
        let p = "/p";
        assert_eq!(uint(&serde_json::json!(5), p, 1, 9).unwrap(), 5);
        assert_eq!(
            uint(&serde_json::json!(0), p, 1, 9).unwrap_err().kind,
            ErrorKind::OutOfRange { min: 1, max: 9 }
        );
        assert_eq!(
            uint(&serde_json::json!(-3), p, 1, 9).unwrap_err().kind,
            ErrorKind::OutOfRange { min: 1, max: 9 }
        );
        let frac: Value = serde_json::from_str("1.5").unwrap();
        assert!(matches!(
            uint(&frac, p, 1, 9).unwrap_err().kind,
            ErrorKind::WrongType {
                expected: "integer",
                ..
            }
        ));
        let huge: Value = serde_json::from_str("123456789012345678901234567890").unwrap();
        assert_eq!(
            uint(&huge, p, 1, 9).unwrap_err().kind,
            ErrorKind::OutOfRange { min: 1, max: 9 }
        );
        assert!(matches!(
            uint(&serde_json::json!("5"), p, 1, 9).unwrap_err().kind,
            ErrorKind::WrongType {
                expected: "integer",
                found: "string"
            }
        ));
    }
}
