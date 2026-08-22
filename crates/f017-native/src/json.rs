use serde::de::{DeserializeOwned, Error as DeError, MapAccess, SeqAccess, Visitor};
use serde::Deserialize;
use serde_json::{Map, Number, Value};
use std::fmt;

pub fn parse_json_no_duplicates<T: DeserializeOwned>(bytes: &[u8]) -> Result<T, String> {
    let mut deserializer = serde_json::Deserializer::from_slice(bytes);
    let value = NoDuplicateValue::deserialize(&mut deserializer)
        .map_err(|error| format!("invalid JSON: {error}"))?
        .0;
    deserializer
        .end()
        .map_err(|error| format!("trailing JSON data: {error}"))?;
    serde_json::from_value(value).map_err(|error| format!("JSON contract mismatch: {error}"))
}

struct NoDuplicateValue(Value);

impl<'de> Deserialize<'de> for NoDuplicateValue {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        deserializer.deserialize_any(NoDuplicateVisitor)
    }
}

struct NoDuplicateVisitor;

impl<'de> Visitor<'de> for NoDuplicateVisitor {
    type Value = NoDuplicateValue;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a JSON value without duplicate object keys")
    }

    fn visit_bool<E: DeError>(self, value: bool) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Bool(value)))
    }
    fn visit_i64<E: DeError>(self, value: i64) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Number(Number::from(value))))
    }
    fn visit_u64<E: DeError>(self, value: u64) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Number(Number::from(value))))
    }
    fn visit_f64<E: DeError>(self, value: f64) -> Result<Self::Value, E> {
        Number::from_f64(value)
            .map(Value::Number)
            .map(NoDuplicateValue)
            .ok_or_else(|| E::custom("non-finite JSON number"))
    }
    fn visit_str<E: DeError>(self, value: &str) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::String(value.to_owned())))
    }
    fn visit_string<E: DeError>(self, value: String) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::String(value)))
    }
    fn visit_none<E: DeError>(self) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Null))
    }
    fn visit_unit<E: DeError>(self) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Null))
    }
    fn visit_some<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        NoDuplicateValue::deserialize(deserializer)
    }
    fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut values = Vec::new();
        while let Some(value) = sequence.next_element::<NoDuplicateValue>()? {
            values.push(value.0);
        }
        Ok(NoDuplicateValue(Value::Array(values)))
    }
    fn visit_map<A>(self, mut object: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut values = Map::new();
        while let Some(key) = object.next_key::<String>()? {
            if values.contains_key(&key) {
                return Err(A::Error::custom(format!("duplicate object key {key:?}")));
            }
            values.insert(key, object.next_value::<NoDuplicateValue>()?.0);
        }
        Ok(NoDuplicateValue(Value::Object(values)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_duplicate_keys_at_any_depth() {
        assert!(parse_json_no_duplicates::<Value>(br#"{"a":1,"a":2}"#).is_err());
        assert!(parse_json_no_duplicates::<Value>(br#"{"a":{"b":1,"b":2}}"#).is_err());
    }
}
