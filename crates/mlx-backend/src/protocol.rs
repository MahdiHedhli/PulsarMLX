//! Bounded protocol-v1 envelopes for the persistent MLX worker.

use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::{Map, Number, Value};
use std::collections::BTreeSet;
use std::fmt;

pub const PROTOCOL_VERSION: u32 = 1;
pub const MAX_REQUEST_BYTES: usize = 64 * 1024;
pub const MAX_RESPONSE_BYTES: usize = 1024 * 1024;
pub const MAX_PROTOCOL_MESSAGE_CHARS: usize = 512;

const MAX_IDENTIFIER_CHARS: usize = 128;
const MAX_NESTING_DEPTH: usize = 16;
const MAX_LIST_ITEMS: usize = 4096;
const MAX_DEVICE_COUNT: usize = 64;
const MAX_CAPABILITY_COUNT: usize = 256;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WorkerErrorKind {
    Spawn,
    Io,
    HelloNegotiation,
    Protocol,
    MessageTooLarge,
    RequestIdMismatch,
    Timeout,
    UnexpectedEof,
    NonZeroExit,
    ProcessCrashed,
    StdoutContamination,
    Remote,
}

#[derive(Debug, Clone, PartialEq)]
pub struct WorkerError {
    kind: WorkerErrorKind,
    worker_code: Option<String>,
    message: String,
    retryable: Option<bool>,
    details: Option<Value>,
    exit_code: Option<i32>,
}

impl WorkerError {
    pub(crate) fn new(kind: WorkerErrorKind, message: impl AsRef<str>) -> Self {
        Self {
            kind,
            worker_code: None,
            message: sanitize_message(message.as_ref()),
            retryable: None,
            details: None,
            exit_code: None,
        }
    }

    pub fn with_exit_code(mut self, exit_code: i32) -> Self {
        self.exit_code = Some(exit_code);
        self
    }

    fn from_remote(error: RemoteErrorEnvelope) -> Result<Self, Self> {
        if !stable_worker_error_code(&error.code) {
            return Err(Self::new(
                WorkerErrorKind::StdoutContamination,
                "worker returned an unknown error code",
            ));
        }
        if error.message.trim().is_empty() {
            return Err(Self::new(
                WorkerErrorKind::StdoutContamination,
                "worker returned an empty error message",
            ));
        }
        if !error.details.is_object() {
            return Err(Self::new(
                WorkerErrorKind::StdoutContamination,
                "worker error details must be an object",
            ));
        }

        Ok(Self {
            kind: WorkerErrorKind::Remote,
            worker_code: Some(error.code),
            message: sanitize_message(&error.message),
            retryable: Some(error.retryable),
            details: Some(sanitize_json(error.details)),
            exit_code: None,
        })
    }

    pub fn kind(&self) -> WorkerErrorKind {
        self.kind
    }

    pub fn worker_code(&self) -> Option<&str> {
        self.worker_code.as_deref()
    }

    pub fn message(&self) -> &str {
        &self.message
    }

    pub fn retryable(&self) -> Option<bool> {
        self.retryable
    }

    pub fn details(&self) -> Option<&Value> {
        self.details.as_ref()
    }

    pub fn exit_code(&self) -> Option<i32> {
        self.exit_code
    }
}

impl fmt::Display for WorkerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        if let Some(code) = self.worker_code() {
            write!(formatter, "{code}: {}", self.message)
        } else {
            write!(formatter, "{}", self.message)
        }
    }
}

impl std::error::Error for WorkerError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ProtocolLimits {
    max_request_bytes: usize,
    max_response_bytes: usize,
    max_nesting_depth: usize,
    max_list_items: usize,
}

impl Default for ProtocolLimits {
    fn default() -> Self {
        Self {
            max_request_bytes: MAX_REQUEST_BYTES,
            max_response_bytes: MAX_RESPONSE_BYTES,
            max_nesting_depth: MAX_NESTING_DEPTH,
            max_list_items: MAX_LIST_ITEMS,
        }
    }
}

impl ProtocolLimits {
    pub fn max_request_bytes(&self) -> usize {
        self.max_request_bytes
    }

    pub fn max_response_bytes(&self) -> usize {
        self.max_response_bytes
    }

    pub fn negotiated(&self, advertised: &WorkerAdvertisedLimits) -> Result<Self, WorkerError> {
        let max_request_bytes = usize::try_from(advertised.max_request_bytes)
            .map_err(|_| hello_error("worker request limit is not representable"))?;
        let max_response_bytes = usize::try_from(advertised.max_response_bytes)
            .map_err(|_| hello_error("worker response limit is not representable"))?;
        if max_request_bytes == 0
            || max_response_bytes == 0
            || max_request_bytes > self.max_request_bytes
            || max_response_bytes > self.max_response_bytes
        {
            return Err(hello_error("worker limits exceed the protocol-v1 bounds"));
        }
        Ok(Self {
            max_request_bytes,
            max_response_bytes,
            max_nesting_depth: self.max_nesting_depth,
            max_list_items: self.max_list_items,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HelloExpectation {
    protocol: u32,
    worker_version: String,
    mlx_version: String,
}

impl HelloExpectation {
    pub fn new(
        protocol: u32,
        worker_version: impl Into<String>,
        mlx_version: impl Into<String>,
    ) -> Result<Self, WorkerError> {
        let worker_version = worker_version.into();
        let mlx_version = mlx_version.into();
        if protocol != PROTOCOL_VERSION {
            return Err(hello_error("unsupported expected protocol version"));
        }
        validate_identifier(
            &worker_version,
            "worker version",
            WorkerErrorKind::HelloNegotiation,
        )?;
        validate_identifier(
            &mlx_version,
            "MLX version",
            WorkerErrorKind::HelloNegotiation,
        )?;
        Ok(Self {
            protocol,
            worker_version,
            mlx_version,
        })
    }
}

#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RequestEnvelope {
    protocol: u32,
    request_id: u64,
    op: String,
    params: Map<String, Value>,
}

impl RequestEnvelope {
    pub fn new(
        request_id: u64,
        op: impl Into<String>,
        params: Map<String, Value>,
    ) -> Result<Self, WorkerError> {
        let op = op.into();
        validate_operation(&op)?;
        validate_value_limits(&Value::Object(params.clone()), &ProtocolLimits::default())?;
        Ok(Self {
            protocol: PROTOCOL_VERSION,
            request_id,
            op,
            params,
        })
    }

    pub fn empty(request_id: u64, op: impl Into<String>) -> Result<Self, WorkerError> {
        Self::new(request_id, op, Map::new())
    }

    pub fn protocol(&self) -> u32 {
        self.protocol
    }

    pub fn request_id(&self) -> u64 {
        self.request_id
    }

    pub fn op(&self) -> &str {
        &self.op
    }

    pub fn params(&self) -> &Map<String, Value> {
        &self.params
    }

    pub fn encode_line(&self, limits: &ProtocolLimits) -> Result<Vec<u8>, WorkerError> {
        let mut encoded = serde_json::to_vec(self).map_err(|_| {
            WorkerError::new(
                WorkerErrorKind::Protocol,
                "request envelope could not be encoded",
            )
        })?;
        if encoded.len() > limits.max_request_bytes {
            return Err(WorkerError::new(
                WorkerErrorKind::MessageTooLarge,
                "request line exceeds the configured byte limit",
            ));
        }
        encoded.push(b'\n');
        Ok(encoded)
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WorkerDevice {
    id: String,
    kind: String,
}

impl WorkerDevice {
    pub fn id(&self) -> &str {
        &self.id
    }

    pub fn kind(&self) -> &str {
        &self.kind
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WorkerCapabilities {
    operations: Vec<String>,
    dtypes: Vec<String>,
}

impl WorkerCapabilities {
    pub fn operations(&self) -> &[String] {
        &self.operations
    }

    pub fn dtypes(&self) -> &[String] {
        &self.dtypes
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WorkerAdvertisedLimits {
    max_request_bytes: u64,
    max_response_bytes: u64,
    max_fixture_elements: u64,
}

impl WorkerAdvertisedLimits {
    pub fn max_request_bytes(&self) -> u64 {
        self.max_request_bytes
    }

    pub fn max_response_bytes(&self) -> u64 {
        self.max_response_bytes
    }

    pub fn max_fixture_elements(&self) -> u64 {
        self.max_fixture_elements
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WorkerHello {
    protocol: u32,
    op: String,
    worker_version: String,
    python_version: String,
    python_arch: String,
    mlx_version: String,
    macos_version: String,
    metal_available: bool,
    gpu_count: u64,
    devices: Vec<WorkerDevice>,
    capabilities: WorkerCapabilities,
    limits: WorkerAdvertisedLimits,
}

impl WorkerHello {
    pub fn protocol(&self) -> u32 {
        self.protocol
    }

    pub fn request_id(&self) -> Option<u64> {
        None
    }

    pub fn worker_version(&self) -> &str {
        &self.worker_version
    }

    pub fn python_version(&self) -> &str {
        &self.python_version
    }

    pub fn python_arch(&self) -> &str {
        &self.python_arch
    }

    pub fn mlx_version(&self) -> &str {
        &self.mlx_version
    }

    pub fn macos_version(&self) -> &str {
        &self.macos_version
    }

    pub fn metal_available(&self) -> bool {
        self.metal_available
    }

    pub fn gpu_count(&self) -> u64 {
        self.gpu_count
    }

    pub fn devices(&self) -> &[WorkerDevice] {
        &self.devices
    }

    pub fn capabilities(&self) -> &WorkerCapabilities {
        &self.capabilities
    }

    pub fn limits(&self) -> &WorkerAdvertisedLimits {
        &self.limits
    }
}

pub fn parse_hello_line(
    line: &[u8],
    expected: &HelloExpectation,
    limits: &ProtocolLimits,
) -> Result<WorkerHello, WorkerError> {
    let value = parse_stdout_json_line(line, limits.max_response_bytes, limits)?;
    let hello: WorkerHello = serde_json::from_value(value).map_err(|_| {
        WorkerError::new(
            WorkerErrorKind::StdoutContamination,
            "worker hello envelope is malformed",
        )
    })?;

    if hello.protocol != expected.protocol || hello.protocol != PROTOCOL_VERSION {
        return Err(hello_error(
            "worker protocol version does not match the pin",
        ));
    }
    if hello.op != "hello" {
        return Err(hello_error("first worker message is not a hello"));
    }
    if hello.worker_version != expected.worker_version {
        return Err(hello_error("worker version does not match the pin"));
    }
    if hello.mlx_version != expected.mlx_version {
        return Err(hello_error("MLX version does not match the pin"));
    }

    validate_hello_metadata(&hello, limits)?;
    Ok(hello)
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct RawResponseEnvelope {
    protocol: u32,
    request_id: u64,
    ok: bool,
    result: Option<Value>,
    error: Option<RemoteErrorEnvelope>,
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct RemoteErrorEnvelope {
    code: String,
    message: String,
    retryable: bool,
    details: Value,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ResponseEnvelope {
    protocol: u32,
    request_id: u64,
    result: Result<Value, WorkerError>,
}

impl ResponseEnvelope {
    pub fn protocol(&self) -> u32 {
        self.protocol
    }

    pub fn request_id(&self) -> u64 {
        self.request_id
    }

    pub fn into_result(self) -> Result<Value, WorkerError> {
        self.result
    }
}

pub fn parse_response_line(
    line: &[u8],
    expected_request_id: u64,
    limits: &ProtocolLimits,
) -> Result<ResponseEnvelope, WorkerError> {
    let value = parse_stdout_json_line(line, limits.max_response_bytes, limits)?;
    let raw: RawResponseEnvelope = serde_json::from_value(value).map_err(|_| {
        WorkerError::new(
            WorkerErrorKind::StdoutContamination,
            "worker response envelope is malformed",
        )
    })?;

    if raw.protocol != PROTOCOL_VERSION {
        return Err(WorkerError::new(
            WorkerErrorKind::Protocol,
            "worker response protocol version does not match",
        ));
    }
    if raw.request_id != expected_request_id {
        return Err(WorkerError::new(
            WorkerErrorKind::RequestIdMismatch,
            "worker response request ID does not match the active request",
        ));
    }

    let result = match (raw.ok, raw.result, raw.error) {
        (true, Some(result), None) if result.is_object() => Ok(result),
        (false, None, Some(error)) => Err(WorkerError::from_remote(error)?),
        _ => {
            return Err(WorkerError::new(
                WorkerErrorKind::StdoutContamination,
                "worker response success and error fields are inconsistent",
            ));
        }
    };

    Ok(ResponseEnvelope {
        protocol: raw.protocol,
        request_id: raw.request_id,
        result,
    })
}

fn validate_hello_metadata(
    hello: &WorkerHello,
    local_limits: &ProtocolLimits,
) -> Result<(), WorkerError> {
    for (value, label) in [
        (&hello.python_version, "Python version"),
        (&hello.python_arch, "Python architecture"),
        (&hello.macos_version, "macOS version"),
    ] {
        validate_identifier(value, label, WorkerErrorKind::HelloNegotiation)?;
    }

    if hello.devices.len() > MAX_DEVICE_COUNT
        || u64::try_from(hello.devices.len()).ok() != Some(hello.gpu_count)
    {
        return Err(hello_error("worker device inventory is inconsistent"));
    }
    for device in &hello.devices {
        validate_identifier(&device.id, "device ID", WorkerErrorKind::HelloNegotiation)?;
        validate_identifier(
            &device.kind,
            "device kind",
            WorkerErrorKind::HelloNegotiation,
        )?;
    }

    validate_capabilities(&hello.capabilities.operations, "operation")?;
    validate_capabilities(&hello.capabilities.dtypes, "dtype")?;
    for required in ["health", "shutdown"] {
        if !hello
            .capabilities
            .operations
            .iter()
            .any(|operation| operation == required)
        {
            return Err(hello_error("worker omits a required protocol operation"));
        }
    }

    let advertised_request = usize::try_from(hello.limits.max_request_bytes)
        .map_err(|_| hello_error("worker request limit is not representable"))?;
    let advertised_response = usize::try_from(hello.limits.max_response_bytes)
        .map_err(|_| hello_error("worker response limit is not representable"))?;
    if advertised_request == 0
        || advertised_response == 0
        || hello.limits.max_fixture_elements == 0
        || advertised_request > local_limits.max_request_bytes
        || advertised_response > local_limits.max_response_bytes
    {
        return Err(hello_error("worker limits exceed the protocol-v1 bounds"));
    }
    Ok(())
}

fn validate_capabilities(values: &[String], label: &str) -> Result<(), WorkerError> {
    if values.is_empty() || values.len() > MAX_CAPABILITY_COUNT {
        return Err(hello_error("worker capability inventory is not bounded"));
    }
    let mut unique = BTreeSet::new();
    for value in values {
        validate_identifier(value, label, WorkerErrorKind::HelloNegotiation)?;
        if !unique.insert(value.as_str()) {
            return Err(hello_error(
                "worker capability inventory contains duplicates",
            ));
        }
    }
    Ok(())
}

fn parse_stdout_json_line(
    line: &[u8],
    max_bytes: usize,
    limits: &ProtocolLimits,
) -> Result<Value, WorkerError> {
    let payload = framed_payload(line, max_bytes)?;
    let NoDuplicateValue(value) =
        serde_json::from_slice::<NoDuplicateValue>(payload).map_err(|_| {
            WorkerError::new(
                WorkerErrorKind::StdoutContamination,
                "worker stdout is not one valid JSON object",
            )
        })?;
    if !value.is_object() {
        return Err(WorkerError::new(
            WorkerErrorKind::StdoutContamination,
            "worker stdout JSON root must be an object",
        ));
    }
    validate_value_limits(&value, limits)?;
    Ok(value)
}

fn framed_payload(line: &[u8], max_bytes: usize) -> Result<&[u8], WorkerError> {
    let Some(payload) = line.strip_suffix(b"\n") else {
        return Err(WorkerError::new(
            WorkerErrorKind::StdoutContamination,
            "worker stdout message is not LF terminated",
        ));
    };
    if payload.is_empty() || payload.ends_with(b"\r") || payload.contains(&b'\n') {
        return Err(WorkerError::new(
            WorkerErrorKind::StdoutContamination,
            "worker stdout framing is invalid",
        ));
    }
    if payload.len() > max_bytes {
        return Err(WorkerError::new(
            WorkerErrorKind::MessageTooLarge,
            "worker stdout line exceeds the configured byte limit",
        ));
    }
    Ok(payload)
}

fn validate_value_limits(value: &Value, limits: &ProtocolLimits) -> Result<(), WorkerError> {
    fn visit(value: &Value, depth: usize, limits: &ProtocolLimits) -> Result<(), WorkerError> {
        if depth > limits.max_nesting_depth {
            return Err(WorkerError::new(
                WorkerErrorKind::MessageTooLarge,
                "protocol JSON nesting exceeds the configured bound",
            ));
        }
        match value {
            Value::Array(values) => {
                if values.len() > limits.max_list_items {
                    return Err(WorkerError::new(
                        WorkerErrorKind::MessageTooLarge,
                        "protocol JSON list exceeds the configured bound",
                    ));
                }
                for value in values {
                    visit(value, depth + 1, limits)?;
                }
            }
            Value::Object(values) => {
                if values.len() > limits.max_list_items {
                    return Err(WorkerError::new(
                        WorkerErrorKind::MessageTooLarge,
                        "protocol JSON object exceeds the configured bound",
                    ));
                }
                for value in values.values() {
                    visit(value, depth + 1, limits)?;
                }
            }
            _ => {}
        }
        Ok(())
    }
    visit(value, 1, limits)
}

fn validate_identifier(value: &str, label: &str, kind: WorkerErrorKind) -> Result<(), WorkerError> {
    if value.is_empty()
        || value.trim() != value
        || value.chars().count() > MAX_IDENTIFIER_CHARS
        || value.chars().any(char::is_control)
    {
        return Err(WorkerError::new(
            kind,
            format!("{label} is missing or invalid"),
        ));
    }
    Ok(())
}

fn validate_operation(operation: &str) -> Result<(), WorkerError> {
    validate_identifier(operation, "operation", WorkerErrorKind::Protocol)?;
    if !operation
        .bytes()
        .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
    {
        return Err(WorkerError::new(
            WorkerErrorKind::Protocol,
            "request operation is not a stable protocol identifier",
        ));
    }
    Ok(())
}

fn hello_error(message: impl AsRef<str>) -> WorkerError {
    WorkerError::new(WorkerErrorKind::HelloNegotiation, message)
}

fn stable_worker_error_code(code: &str) -> bool {
    matches!(
        code,
        "protocol_mismatch"
            | "message_too_large"
            | "malformed_request"
            | "unsupported_operation"
            | "invalid_shape"
            | "invalid_dtype"
            | "invalid_layout"
            | "invalid_byte_count"
            | "runtime_version_mismatch"
            | "unsupported_host"
            | "metal_unavailable"
            | "device_unavailable"
            | "evaluation_failed"
            | "comparison_failed"
            | "resource_limit"
            | "internal_worker_error"
    )
}

fn sanitize_message(message: &str) -> String {
    let mut sanitized = String::new();
    for token in message.split_whitespace() {
        if !sanitized.is_empty() {
            sanitized.push(' ');
        }
        if sensitive_token(token) {
            sanitized.push_str("<redacted>");
        } else {
            sanitized.push_str(token);
        }
    }
    if sanitized.is_empty() {
        sanitized.push_str("worker operation failed");
    }

    let mut bounded: String = sanitized.chars().take(MAX_PROTOCOL_MESSAGE_CHARS).collect();
    if sanitized.chars().count() > MAX_PROTOCOL_MESSAGE_CHARS {
        bounded.pop();
        bounded.push('…');
    }
    bounded
}

fn sensitive_token(token: &str) -> bool {
    let uppercase = token.to_ascii_uppercase();
    token.starts_with('/')
        || token.starts_with("~/")
        || token.contains("/Users/")
        || token.contains("/home/")
        || token.contains("\\Users\\")
        || ((uppercase.contains("TOKEN")
            || uppercase.contains("SECRET")
            || uppercase.contains("PASSWORD"))
            && token.contains('='))
}

fn sanitize_json(value: Value) -> Value {
    match value {
        Value::String(value) => Value::String(sanitize_message(&value)),
        Value::Array(values) => Value::Array(values.into_iter().map(sanitize_json).collect()),
        Value::Object(values) => Value::Object(
            values
                .into_iter()
                .map(|(key, value)| {
                    let uppercase = key.to_ascii_uppercase();
                    let value = if uppercase.contains("TOKEN")
                        || uppercase.contains("SECRET")
                        || uppercase.contains("PASSWORD")
                    {
                        Value::String("<redacted>".to_owned())
                    } else {
                        sanitize_json(value)
                    };
                    (key, value)
                })
                .collect(),
        ),
        value => value,
    }
}

struct NoDuplicateValue(Value);

impl<'de> Deserialize<'de> for NoDuplicateValue {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
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

    fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Bool(value)))
    }

    fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Number(Number::from(value))))
    }

    fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Number(Number::from(value))))
    }

    fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Number::from_f64(value)
            .map(Value::Number)
            .map(NoDuplicateValue)
            .ok_or_else(|| E::custom("non-finite JSON number"))
    }

    fn visit_str<E>(self, value: &str) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        self.visit_string(value.to_owned())
    }

    fn visit_string<E>(self, value: String) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::String(value)))
    }

    fn visit_none<E>(self) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Null))
    }

    fn visit_unit<E>(self) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Null))
    }

    fn visit_some<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        NoDuplicateValue::deserialize(deserializer)
    }

    fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut values = Vec::new();
        while let Some(NoDuplicateValue(value)) = sequence.next_element()? {
            values.push(value);
        }
        Ok(NoDuplicateValue(Value::Array(values)))
    }

    fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut values = Map::new();
        while let Some((key, NoDuplicateValue(value))) = map.next_entry::<String, _>()? {
            if values.insert(key, value).is_some() {
                return Err(de::Error::custom("duplicate JSON object key"));
            }
        }
        Ok(NoDuplicateValue(Value::Object(values)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const HELLO: &str = r#"{"protocol":1,"op":"hello","worker_version":"fake-worker-v1","python_version":"3.12.0","python_arch":"arm64","mlx_version":"0.32.0","macos_version":"15.0","metal_available":true,"gpu_count":1,"devices":[{"id":"gpu","kind":"gpu"}],"capabilities":{"operations":["health","shutdown"],"dtypes":["float32"]},"limits":{"max_request_bytes":65536,"max_response_bytes":1048576,"max_fixture_elements":1024}}
"#;

    fn expectation() -> HelloExpectation {
        HelloExpectation::new(PROTOCOL_VERSION, "fake-worker-v1", "0.32.0").expect("valid pins")
    }

    #[test]
    fn hello_negotiates_exact_pins_capabilities_and_limits() {
        let local_limits = ProtocolLimits::default();
        let hello =
            parse_hello_line(HELLO.as_bytes(), &expectation(), &local_limits).expect("valid hello");

        assert_eq!(hello.protocol(), PROTOCOL_VERSION);
        assert_eq!(hello.request_id(), None);
        assert_eq!(hello.worker_version(), "fake-worker-v1");
        assert_eq!(hello.capabilities().operations(), ["health", "shutdown"]);
        assert_eq!(hello.devices()[0].id(), "gpu");

        let effective = local_limits
            .negotiated(hello.limits())
            .expect("advertised limits are bounded");
        assert_eq!(effective.max_request_bytes(), MAX_REQUEST_BYTES);
        assert_eq!(effective.max_response_bytes(), MAX_RESPONSE_BYTES);
    }

    #[test]
    fn hello_rejects_mismatched_pins_and_duplicate_json_keys() {
        let limits = ProtocolLimits::default();
        let wrong = HelloExpectation::new(PROTOCOL_VERSION, "fake-worker-v2", "0.32.0")
            .expect("valid alternate pin");
        assert_eq!(
            parse_hello_line(HELLO.as_bytes(), &wrong, &limits)
                .expect_err("mismatched pin")
                .kind(),
            WorkerErrorKind::HelloNegotiation
        );

        let duplicate = b"{\"protocol\":1,\"protocol\":1}\n";
        assert_eq!(
            parse_hello_line(duplicate, &expectation(), &limits)
                .expect_err("duplicate key")
                .kind(),
            WorkerErrorKind::StdoutContamination
        );
    }

    #[test]
    fn request_encoding_is_one_bounded_protocol_line() {
        let request = RequestEnvelope::empty(7, "health").expect("valid request");
        let encoded = request
            .encode_line(&ProtocolLimits::default())
            .expect("bounded request");
        assert_eq!(
            encoded,
            b"{\"protocol\":1,\"request_id\":7,\"op\":\"health\",\"params\":{}}\n"
        );
    }

    #[test]
    fn response_ids_and_structured_remote_errors_are_enforced() {
        let limits = ProtocolLimits::default();
        let success =
            b"{\"protocol\":1,\"request_id\":7,\"ok\":true,\"result\":{\"ready\":true}}\n";
        assert_eq!(
            parse_response_line(success, 8, &limits)
                .expect_err("mismatched ID")
                .kind(),
            WorkerErrorKind::RequestIdMismatch
        );

        let remote = b"{\"protocol\":1,\"request_id\":7,\"ok\":false,\"error\":{\"code\":\"device_unavailable\",\"message\":\"failed at /Users/private/model.gguf TOKEN=value\",\"retryable\":false,\"details\":{\"path\":\"/private/model.gguf\"}}}\n";
        let error = parse_response_line(remote, 7, &limits)
            .expect("valid remote envelope")
            .into_result()
            .expect_err("remote failure stays an error");
        assert_eq!(error.kind(), WorkerErrorKind::Remote);
        assert_eq!(error.worker_code(), Some("device_unavailable"));
        assert_eq!(error.message(), "failed at <redacted> <redacted>");
        assert_eq!(error.retryable(), Some(false));
        assert!(!error
            .details()
            .expect("sanitized details")
            .to_string()
            .contains("/private"));
    }

    #[test]
    fn response_framing_and_line_limits_are_strict() {
        let limits = ProtocolLimits::default();
        assert_eq!(
            parse_response_line(b"{}", 1, &limits)
                .expect_err("missing LF")
                .kind(),
            WorkerErrorKind::StdoutContamination
        );

        let mut oversized = vec![b' '; MAX_RESPONSE_BYTES + 1];
        oversized.push(b'\n');
        assert_eq!(
            parse_response_line(&oversized, 1, &limits)
                .expect_err("oversized line")
                .kind(),
            WorkerErrorKind::MessageTooLarge
        );
    }
}
