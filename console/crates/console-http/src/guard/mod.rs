//! Owned by API-03. API keys, CORS, the cross-site guards and the SEC-1 `Host` allowlist.
//!
//! [`Guard`] holds what the guards need from the configuration ([`GuardConfig`]: the bind
//! address, the API keys, the config's `cors_origins` and the optional `allowed_hosts`) and
//! answers each question the router and the route handlers ask about a request:
//!
//! - **API key** ([`Guard::authorized`]): the donor's `_authorized`. With no key configured
//!   every request passes. Otherwise the key is taken from `Authorization: Bearer <k>`
//!   (`bearer ` in any case, the rest stripped of Python whitespace), else from `x-api-key`,
//!   and must equal one of the keys of [`key_list`]. Keys are compared in constant time over
//!   their bytes (SEC-1.5; the donor uses `hmac.compare_digest`, the archived PulsarMLX
//!   serving crate its own constant-time loop). A refusal is 401 `authentication_error`
//!   "missing or wrong API key".
//! - **Response owner** ([`Guard::response_owner`]): `public` with no key configured, else
//!   the lowercase hex SHA-256 of the presented key ([`console_core::digest`]).
//! - **CORS** ([`Guard::cors_allow`], [`Guard::cors_headers`], [`Guard::preflight`]): only
//!   for a raw path under `/v1/` and only for an origin `cors_origins` lists (or `*`).
//! - **Foreign page** ([`Guard::is_foreign_page`]): an `Origin` that is neither this server
//!   (its text after `://` equal to the `Host` header) nor CORS-allowed is refused with 403
//!   `permission_error`. Under deviation SEC-1.2 the router asks this on every route, not
//!   only on POST and DELETE as the donor does, and `Origin: null` is never this server.
//! - **Own page** ([`Guard::own_page`], [`Guard::attach_page`]): the donor's `_own_page`
//!   and the content-type and origin check of its attachment route, for the handlers of the
//!   dashboard's mutating routes. The product name in the message follows BRAND-1.1.
//! - **JSON content type** ([`is_json_content_type`]): deviation SEC-1.3, every POST that
//!   takes JSON must say `application/json`; the rule (the media type before any `;`,
//!   trimmed, compared case-insensitively) is the archived serving crate's.
//! - **Loopback or key** ([`Guard::local_or_keyed`]): deviation SEC-1.4, a mutating admin or
//!   ops route from a client that is not on this computer needs an API key to be set.
//! - **`Host` allowlist** ([`Guard::host_allowed`]): deviation SEC-1.1, settled by the owner
//!   on 2026-11-14. See [`HostPolicy`] for the rule and the matching details.
//!
//! Nothing here admits an engine; the guards only decide whether a request is served.
//!
//! Behavior reference: project-maya serve/server.py:5383-5400 (`key_list`), 5780-5819
//! (`_cors_allow`, `end_headers`, `do_OPTIONS`, `_authorized`), 5821-5826
//! (`_response_owner`), 5508-5519 (the loopback gate of `_mapi_gate`), 6141-6150
//! (`_foreign_page`), 6327-6338 (`_own_page`) and 6434-6450 (the attachment route's check)
//! at 7e68a30f. The `Host`, `Origin`, content-type and key handling of SEC-1 takes the
//! archived serving crate as its reference (decision B8; tag
//! `archive/2026-09-21/feat/openai-serving`, `crates/serve-synthetic/src/lib.rs`, functions
//! `valid_host`, `valid_origin`, `valid_auth`, `constant_time_eq` and the content-type check
//! of `chat`).

use std::fmt;
use std::net::IpAddr;

use console_core::digest::sha256_hex;
use console_pyjson::dumps::{classify_number, dumps_str, PyNumber};
use console_pyjson::float_repr::repr_f64;
use console_pyjson::loads::truthy;
use console_pyjson::pystr;
use serde_json::Value;

use crate::error::ApiError;
use crate::transport::{py_repr, ClientGone, Headers, RequestHead, Responder};

/// The product name in user-facing refusals (BRAND-1.1, contracts/naming.md section 3.8).
pub const PRODUCT_NAME: &str = "PulsarMLX Console";

/// The response owner of every request while no API key is configured.
pub const PUBLIC_OWNER: &str = "public";

/// The 403 message of a request from another web page.
///
/// Behavior reference: project-maya serve/server.py:6148-6149 at 7e68a30f.
pub const FOREIGN_PAGE_MESSAGE: &str =
    "requests from other web pages are refused (the config's cors_origins lists the pages allowed)";

/// The 403 message of a request whose `Host` the allowlist refuses (deviation SEC-1.1; the
/// wording is this server's own, in the style of [`FOREIGN_PAGE_MESSAGE`]).
pub const HOST_REFUSED_MESSAGE: &str =
    "requests for other host names are refused (the config's allowed_hosts lists the names allowed)";

/// The 403 message of a mutating admin route asked from another computer while no API key
/// is set (deviation SEC-1.4; the wording is this server's own).
pub const LOCAL_ONLY_MESSAGE: &str =
    "set an API key to change this server's settings over the network";

/// The 403 message of a model-management route asked from another computer while no API
/// key is set.
///
/// Behavior reference: project-maya serve/server.py:5518 at 7e68a30f.
pub const MODEL_MANAGE_LOCAL_ONLY_MESSAGE: &str =
    "set an API key to download, delete or switch models over the network";

/// The 415 message of a body that is not sent as JSON.
///
/// Behavior reference: project-maya serve/server.py:6332 at 7e68a30f.
pub const SEND_JSON_MESSAGE: &str = "send application/json";

/// The 415 message of an attachment that is not sent as raw bytes.
///
/// Behavior reference: project-maya serve/server.py:6444 at 7e68a30f.
pub const SEND_FILE_MESSAGE: &str = "send the file's bytes as application/octet-stream";

/// The content types the attachment route accepts.
pub const ATTACH_CONTENT_TYPES: [&str; 2] = ["application/octet-stream", "application/pdf"];

/// The `Access-Control-Allow-Methods` value of a granted preflight.
pub const PREFLIGHT_METHODS: &str = "GET, POST, DELETE, OPTIONS";

/// The `Access-Control-Allow-Headers` value of a granted preflight that asked for none.
pub const PREFLIGHT_HEADERS: &str = "Content-Type, Authorization, x-api-key";

/// The `Access-Control-Max-Age` value of a granted preflight.
pub const PREFLIGHT_MAX_AGE: &str = "600";

/// The loopback names every [`HostPolicy::Allow`] accepts, with any port.
pub const LOOPBACK_HOSTS: [&str; 3] = ["localhost", "127.0.0.1", "[::1]"];

/// The 403 message of the own-page check for `what` (BRAND-1.1: the donor names itself).
///
/// Behavior reference: project-maya serve/server.py:6336 at 7e68a30f.
pub fn own_page_message(what: &str) -> String {
    format!("{what} only from {PRODUCT_NAME}'s own page")
}

/// The 403 message of the attachment route's origin check (BRAND-1.1).
///
/// Behavior reference: project-maya serve/server.py:6448 at 7e68a30f.
pub fn attach_foreign_message() -> String {
    format!("files are read only for {PRODUCT_NAME}'s own page")
}

// ---------------------------------------------------------------------------------------
// Refusals

/// A guard's answer to a request it refuses.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Refusal {
    /// An answer of the error model (401 `authentication_error`, 403 `permission_error`,
    /// the model-management 403 `{"error": <text>}`).
    Api(ApiError),
    /// `{"error": {"message": <text>}}` with a status: the donor's own-page answers (415
    /// "send application/json", 403 "... only from ...'s own page").
    Message {
        /// HTTP status.
        status: u16,
        /// Message text.
        message: String,
    },
}

impl Refusal {
    /// A `{"error": {"message": ...}}` refusal.
    pub fn message(status: u16, message: impl Into<String>) -> Self {
        Refusal::Message {
            status,
            message: message.into(),
        }
    }

    /// The 401 of a missing or wrong key.
    pub fn auth() -> Self {
        Refusal::Api(ApiError::Auth)
    }

    /// The 403 of a foreign page.
    pub fn foreign_page() -> Self {
        Refusal::Api(ApiError::permission(FOREIGN_PAGE_MESSAGE))
    }

    /// The 403 of a refused `Host` (SEC-1.1).
    pub fn host() -> Self {
        Refusal::Api(ApiError::permission(HOST_REFUSED_MESSAGE))
    }

    /// The 415 of a POST that is not JSON (SEC-1.3, with the donor's `_own_page` answer).
    pub fn not_json() -> Self {
        Refusal::message(415, SEND_JSON_MESSAGE)
    }

    /// The HTTP status.
    pub fn status(&self) -> u16 {
        match self {
            Refusal::Api(e) => e.status(),
            Refusal::Message { status, .. } => *status,
        }
    }

    /// The JSON body, as the donor's `_json` writes it.
    pub fn body(&self) -> String {
        match self {
            Refusal::Api(e) => e.body(),
            Refusal::Message { message, .. } => {
                format!(
                    "{{\"error\": {{\"message\": {}}}}}",
                    dumps_str(message, false)
                )
            }
        }
    }

    /// Writes the refusal as the answer.
    pub async fn answer(&self, responder: &mut Responder) -> Result<(), ClientGone> {
        match self {
            Refusal::Api(e) => responder.error(e).await,
            Refusal::Message { status, .. } => responder.json(*status, &self.body()).await,
        }
    }
}

// ---------------------------------------------------------------------------------------
// API keys

/// Python's `str(value)` for a configuration value: a string as it is, numbers as Python
/// prints them, `True`, `False`, `None`, and Python's `repr` inside lists and objects.
fn py_str(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        other => py_repr_value(other),
    }
}

fn py_repr_value(value: &Value) -> String {
    match value {
        Value::Null => String::from("None"),
        Value::Bool(true) => String::from("True"),
        Value::Bool(false) => String::from("False"),
        Value::Number(n) => match classify_number(n) {
            Ok(PyNumber::Int(digits)) => digits,
            Ok(PyNumber::Float(f)) => repr_f64(f),
            Err(_) => n.to_string(),
        },
        Value::String(s) => py_repr(s),
        Value::Array(items) => {
            let parts: Vec<String> = items.iter().map(py_repr_value).collect();
            format!("[{}]", parts.join(", "))
        }
        Value::Object(map) => {
            let parts: Vec<String> = map
                .iter()
                .map(|(k, v)| format!("{}: {}", py_repr(k), py_repr_value(v)))
                .collect();
            format!("{{{}}}", parts.join(", "))
        }
    }
}

/// The API keys the server accepts, from the API key setting: none for a false value
/// (absent, `""`, `[]`, `null`); for a list, each item as Python's `str()` and non-empty
/// (a key may contain a comma); otherwise the text split at commas, each piece stripped
/// of Python whitespace, empty pieces dropped (`"k1, k2"` is two keys).
///
/// Behavior reference: project-maya serve/server.py:5383-5390 at 7e68a30f.
pub fn key_list(value: &Value) -> Vec<String> {
    if !truthy(value) {
        return Vec::new();
    }
    match value {
        Value::Array(items) => items.iter().map(py_str).filter(|k| !k.is_empty()).collect(),
        other => py_str(other)
            .split(',')
            .map(|k| pystr::strip(k, None))
            .filter(|k| !k.is_empty())
            .map(str::to_owned)
            .collect(),
    }
}

/// Compares two byte strings in time that depends only on their lengths (SEC-1.5).
///
/// Taken from the archived serving crate's `constant_time_eq` (decision B8). Like Python's
/// `hmac.compare_digest`, a length difference is answered at once.
pub fn constant_time_eq(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    left.iter()
        .zip(right)
        .fold(0u8, |diff, (a, b)| diff | (a ^ b))
        == 0
}

/// The configured API keys. Its `Debug` output never shows a key.
#[derive(Clone, Default, PartialEq, Eq)]
pub struct ApiKeys {
    configured: bool,
    keys: Vec<String>,
}

impl fmt::Debug for ApiKeys {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ApiKeys")
            .field("configured", &self.configured)
            .field("count", &self.keys.len())
            .finish()
    }
}

impl ApiKeys {
    /// No key: every request is authorized and owned by [`PUBLIC_OWNER`].
    pub fn none() -> Self {
        Self::default()
    }

    /// The keys of an API key setting (a string or a list, as the run config and
    /// `console_core::config::RunConfig::api_key` give it). A setting that is true in
    /// Python but holds no key (`" , "`) counts as configured and accepts nothing, as in
    /// the donor.
    ///
    /// Behavior reference: project-maya serve/server.py:5811-5819 at 7e68a30f.
    pub fn from_setting(value: &Value) -> Self {
        Self {
            configured: truthy(value),
            keys: key_list(value),
        }
    }

    /// Whether a key is configured (the donor's `if not svc.api_key`).
    pub fn is_configured(&self) -> bool {
        self.configured
    }

    /// The number of accepted keys.
    pub fn len(&self) -> usize {
        self.keys.len()
    }

    /// True when no key is accepted.
    pub fn is_empty(&self) -> bool {
        self.keys.is_empty()
    }

    /// Whether `given` is one of the keys. An empty `given` never is. Every key is compared,
    /// each in constant time, so the time taken does not show which key matched.
    pub fn accepts(&self, given: &str) -> bool {
        if given.is_empty() {
            return false;
        }
        self.keys.iter().fold(false, |found, key| {
            found | constant_time_eq(given.as_bytes(), key.as_bytes())
        })
    }
}

/// The key a request presents: the text after `Bearer ` (any case) in the first
/// `Authorization` header, stripped of Python whitespace; else the first `x-api-key` header
/// as it is; else `""`.
///
/// Behavior reference: project-maya serve/server.py:5814-5815 and 5824-5825 at 7e68a30f.
pub fn presented_key(headers: &Headers) -> &str {
    let auth = headers.get("Authorization").unwrap_or("");
    let bearer = auth
        .as_bytes()
        .get(..7)
        .is_some_and(|p| p.eq_ignore_ascii_case(b"bearer "));
    if bearer {
        // The first seven bytes are ASCII, so byte 7 is a character boundary.
        return pystr::strip(auth.get(7..).unwrap_or(""), None);
    }
    headers.get("x-api-key").unwrap_or("")
}

// ---------------------------------------------------------------------------------------
// The Host allowlist (SEC-1.1)

/// One accepted `Host` name: the name, compared ASCII case-insensitively, and the port when
/// the entry names one.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HostPattern {
    name: String,
    port: Option<u16>,
}

impl HostPattern {
    /// The pattern of an `allowed_hosts` entry or a loopback name: `name` or `name:port`,
    /// an IPv6 address in brackets (`[fe80::1]`, `[fe80::1]:8095`). `None` for text that is
    /// not of that form; such an entry never matches.
    pub fn parse(text: &str) -> Option<Self> {
        let (name, port) = split_host(text)?;
        Some(Self {
            name: name.to_ascii_lowercase(),
            port,
        })
    }

    /// Whether a request's `Host` (already split) matches: same name in any ASCII case, and
    /// the same port when the pattern names one.
    fn matches(&self, name: &str, port: Option<u16>) -> bool {
        self.name.eq_ignore_ascii_case(name) && self.port.is_none_or(|p| port == Some(p))
    }
}

/// Splits a `Host` value into its name and optional port: `name`, `name:port`, `[v6]` or
/// `[v6]:port`. The port is one to five ASCII digits up to 65535. A name holds no
/// whitespace, control or non-ASCII character and no `:` outside brackets (an IPv6 address
/// must be bracketed). Anything else is `None`. Nothing is trimmed or normalized.
pub fn split_host(text: &str) -> Option<(&str, Option<u16>)> {
    let (name, rest) = if text.starts_with('[') {
        let close = text.find(']')?;
        (text.get(..=close)?, text.get(close + 1..)?)
    } else {
        match text.find(':') {
            Some(colon) => (text.get(..colon)?, text.get(colon..)?),
            None => (text, ""),
        }
    };
    let port = if rest.is_empty() {
        None
    } else {
        let digits = rest.strip_prefix(':')?;
        if digits.is_empty() || digits.len() > 5 || !digits.bytes().all(|b| b.is_ascii_digit()) {
            return None;
        }
        Some(digits.parse::<u16>().ok()?)
    };
    let inner = name
        .strip_prefix('[')
        .and_then(|n| n.strip_suffix(']'))
        .unwrap_or(name);
    let bracketed = inner.len() != name.len();
    let bad_char =
        |c: char| !c.is_ascii_graphic() || (!bracketed && c == ':') || c == '[' || c == ']';
    if inner.is_empty() || inner.chars().any(bad_char) {
        return None;
    }
    Some((name, port))
}

/// Whether `ip` is a loopback address: any of `127.0.0.0/8`, `::1`, or an IPv4-mapped
/// `127.0.0.0/8` address. This is wider than the donor's `_mapi_gate`, which accepts
/// exactly `127.0.0.1`, `::1` and `::ffff:127.0.0.1` (project-maya serve/server.py:5516-5517
/// at 7e68a30f); deviation SEC-1.4 speaks of a loopback peer.
pub fn is_loopback_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => v4.is_loopback(),
        IpAddr::V6(v6) => {
            v6.is_loopback() || v6.to_ipv4_mapped().is_some_and(|v4| v4.is_loopback())
        }
    }
}

/// Which `Host` values are served (deviation SEC-1.1, decided by the owner on 2026-11-14).
///
/// - On a loopback bind, only the loopback names [`LOOPBACK_HOSTS`] (any port) and the
///   names of the optional `allowed_hosts` list pass. The list is absent by default, so by
///   default only the loopback names pass.
/// - On a bind that is not loopback, `Host` is not checked, as in the donor, unless
///   `allowed_hosts` is set (even to an empty list); then only its names and the loopback
///   names pass.
///
/// Matching details, settled by API-03 from the archived serving crate's `valid_host`
/// (decision B8): the request must carry exactly one `Host` header (none, or two even if
/// equal, is refused); the value is used as it arrives, with no trimming, no trailing-dot
/// removal and no IPv6 normalization (`[::1]` passes, `[0:0:0:0:0:0:0:1]` and
/// `[::ffff:127.0.0.1]` do not), and must have the form [`split_host`] accepts. Where the
/// archived crate required its own port, the owner's rule accepts any port, and a missing
/// port (a client's default port) is accepted too. A list entry that names a port matches
/// only that port; one that names none matches any. Names are compared ASCII
/// case-insensitively (host names are case-insensitive and browsers send them lower-case),
/// where the archived crate compared fixed lower-case strings byte for byte.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum HostPolicy {
    /// Every `Host` is served (a non-loopback bind without `allowed_hosts`).
    Unrestricted,
    /// Only these names are served.
    Allow(Vec<HostPattern>),
}

impl HostPolicy {
    /// The policy for a server bound to `bind` with the optional `allowed_hosts` list.
    pub fn new(bind: IpAddr, allowed_hosts: Option<&[String]>) -> Self {
        if !is_loopback_ip(bind) && allowed_hosts.is_none() {
            return HostPolicy::Unrestricted;
        }
        let mut patterns: Vec<HostPattern> = LOOPBACK_HOSTS
            .iter()
            .filter_map(|name| HostPattern::parse(name))
            .collect();
        patterns.extend(
            allowed_hosts
                .unwrap_or(&[])
                .iter()
                .filter_map(|entry| HostPattern::parse(entry)),
        );
        HostPolicy::Allow(patterns)
    }

    /// Whether a request with these headers is served.
    pub fn allows(&self, headers: &Headers) -> bool {
        let HostPolicy::Allow(patterns) = self else {
            return true;
        };
        let mut values = headers.get_all("Host");
        let (Some(host), None) = (values.next(), values.next()) else {
            return false;
        };
        let Some((name, port)) = split_host(host) else {
            return false;
        };
        patterns.iter().any(|p| p.matches(name, port))
    }
}

/// The `allowed_hosts` entries that can never match, in list order: those [`split_host`]
/// rejects (an unbracketed IPv6 address such as `fe80::1`, a URL such as `http://box.lan`,
/// `box.lan:`, a port above 65535, a name with whitespace or a non-ASCII
/// character). [`HostPolicy::new`] leaves them out, so a request for the name the operator
/// meant is refused; API-08 reports them at start (log-safe, decision LD35) or refuses to
/// start. The accepted forms are `name`, `name:port`, `[v6]` and `[v6]:port`.
pub fn invalid_allowed_hosts(hosts: &[String]) -> Vec<&str> {
    hosts
        .iter()
        .map(String::as_str)
        .filter(|entry| HostPattern::parse(entry).is_none())
        .collect()
}

// ---------------------------------------------------------------------------------------
// Content types

/// Whether the request says its body is JSON (deviation SEC-1.3): the first `Content-Type`
/// header's media type, before any `;` and trimmed, equals `application/json` in any ASCII
/// case. A missing header is not JSON.
///
/// The rule is the archived serving crate's (decision B8). The donor's `_own_page` test,
/// `Content-Type` starting with `application/json`, stays in [`Guard::own_page`].
pub fn is_json_content_type(headers: &Headers) -> bool {
    headers.get("Content-Type").is_some_and(|value| {
        let media = value.split(';').next().unwrap_or("");
        media.trim().eq_ignore_ascii_case("application/json")
    })
}

// ---------------------------------------------------------------------------------------
// The guard

/// What the guards read from the configuration. API-08 builds it at start from the listen
/// address and the run config (`allowed_hosts` from API-15's
/// `console_core::config::RunConfig::allowed_hosts`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GuardConfig {
    bind: IpAddr,
    api_keys: ApiKeys,
    cors_origins: Vec<String>,
    allowed_hosts: Option<Vec<String>>,
}

impl GuardConfig {
    /// A configuration for a server bound to `bind`: no API key, no CORS origin and no
    /// `allowed_hosts`.
    pub fn new(bind: IpAddr) -> Self {
        Self {
            bind,
            api_keys: ApiKeys::none(),
            cors_origins: Vec::new(),
            allowed_hosts: None,
        }
    }

    /// With the keys of an API key setting ([`ApiKeys::from_setting`]).
    pub fn with_api_key(mut self, setting: &Value) -> Self {
        self.api_keys = ApiKeys::from_setting(setting);
        self
    }

    /// With these keys.
    pub fn with_api_keys(mut self, keys: ApiKeys) -> Self {
        self.api_keys = keys;
        self
    }

    /// With the config's `cors_origins`, as `console_core::config::parse_cors_origins` gives
    /// them (trailing `/` already removed).
    pub fn with_cors_origins(mut self, origins: Vec<String>) -> Self {
        self.cors_origins = origins;
        self
    }

    /// With the optional `allowed_hosts` list (SEC-1.1).
    pub fn with_allowed_hosts(mut self, hosts: Option<Vec<String>>) -> Self {
        self.allowed_hosts = hosts;
        self
    }

    /// The bind address.
    pub fn bind(&self) -> IpAddr {
        self.bind
    }

    /// The API keys.
    pub fn api_keys(&self) -> &ApiKeys {
        &self.api_keys
    }

    /// The CORS origins.
    pub fn cors_origins(&self) -> &[String] {
        &self.cors_origins
    }

    /// The `allowed_hosts` list.
    pub fn allowed_hosts(&self) -> Option<&[String]> {
        self.allowed_hosts.as_deref()
    }

    /// The `allowed_hosts` entries that can never match ([`invalid_allowed_hosts`]); empty
    /// when the list is absent or every entry is well formed.
    pub fn rejected_allowed_hosts(&self) -> Vec<&str> {
        invalid_allowed_hosts(self.allowed_hosts().unwrap_or(&[]))
    }
}

/// A CORS preflight answer: the status and the headers before the end-headers hook's.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Preflight {
    /// 204 when granted, else 403.
    pub status: u16,
    /// The headers, in the donor's order (`Content-Length: 0` last).
    pub headers: Vec<(String, String)>,
}

/// The guards of one server configuration.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Guard {
    config: GuardConfig,
    hosts: HostPolicy,
}

impl Guard {
    /// The guards for `config`.
    pub fn new(config: GuardConfig) -> Self {
        let hosts = HostPolicy::new(config.bind, config.allowed_hosts());
        Self { config, hosts }
    }

    /// The configuration.
    pub fn config(&self) -> &GuardConfig {
        &self.config
    }

    /// The `Host` policy.
    pub fn host_policy(&self) -> &HostPolicy {
        &self.hosts
    }

    /// Whether the request's `Host` is served (SEC-1.1).
    pub fn host_allowed(&self, head: &RequestHead) -> bool {
        self.hosts.allows(head.headers())
    }

    /// [`host_allowed`](Self::host_allowed) as a refusal: 403 `permission_error`.
    pub fn check_host(&self, head: &RequestHead) -> Result<(), Refusal> {
        if self.host_allowed(head) {
            Ok(())
        } else {
            Err(Refusal::host())
        }
    }

    /// The `Access-Control-Allow-Origin` value for this request, or `None`: only when
    /// `cors_origins` is set and the raw path (query dropped, trailing slashes kept) starts
    /// with `/v1/`; `*` when listed, else the request's `Origin` without trailing slashes
    /// when listed.
    ///
    /// Behavior reference: project-maya serve/server.py:5780-5788 at 7e68a30f.
    pub fn cors_allow(&self, head: &RequestHead) -> Option<String> {
        let origins = &self.config.cors_origins;
        let raw = head.path().split('?').next().unwrap_or("");
        if origins.is_empty() || !raw.starts_with("/v1/") {
            return None;
        }
        if origins.iter().any(|o| o == "*") {
            return Some(String::from("*"));
        }
        let origin = head
            .headers()
            .get("Origin")
            .unwrap_or("")
            .trim_end_matches('/');
        (!origin.is_empty() && origins.iter().any(|o| o == origin)).then(|| origin.to_owned())
    }

    /// The headers the donor's `end_headers` adds to every answer of this request:
    /// `Access-Control-Allow-Origin`, and `Vary: Origin` unless the value is `*`. None for a
    /// request whose `Host` the allowlist refuses, so that no CORS grant reaches a refused
    /// host name.
    ///
    /// Behavior reference: project-maya serve/server.py:5790-5797 at 7e68a30f.
    pub fn cors_headers(&self, head: &RequestHead) -> Vec<(String, String)> {
        if !self.host_allowed(head) {
            return Vec::new();
        }
        match self.cors_allow(head) {
            Some(allow) => {
                let star = allow == "*";
                let mut out = vec![(String::from("Access-Control-Allow-Origin"), allow)];
                if !star {
                    out.push((String::from("Vary"), String::from("Origin")));
                }
                out
            }
            None => Vec::new(),
        }
    }

    /// The preflight answer: 204 with the allowed methods, the asked headers (or the
    /// default list), the max age and `Content-Length: 0` when CORS allows the request;
    /// otherwise 403 with only `Content-Length: 0`. No key is asked.
    ///
    /// Behavior reference: project-maya serve/server.py:5799-5809 at 7e68a30f.
    pub fn preflight(&self, head: &RequestHead) -> Preflight {
        let mut headers = Vec::new();
        let status = if self.cors_allow(head).is_some() {
            let asked = head
                .headers()
                .get("Access-Control-Request-Headers")
                .filter(|v| !v.is_empty())
                .unwrap_or(PREFLIGHT_HEADERS);
            headers.push((
                String::from("Access-Control-Allow-Methods"),
                String::from(PREFLIGHT_METHODS),
            ));
            headers.push((
                String::from("Access-Control-Allow-Headers"),
                asked.to_owned(),
            ));
            headers.push((
                String::from("Access-Control-Max-Age"),
                String::from(PREFLIGHT_MAX_AGE),
            ));
            204
        } else {
            403
        };
        headers.push((String::from("Content-Length"), String::from("0")));
        Preflight { status, headers }
    }

    /// Whether `origin` is this server's own page: its text after the first `://` equals
    /// the first `Host` header (`""` when there is none). `Origin: null` never is
    /// (deviation SEC-1.2).
    ///
    /// Behavior reference: project-maya serve/server.py:6146 and 6335 at 7e68a30f.
    pub fn is_same_page(origin: &str, headers: &Headers) -> bool {
        if origin == "null" {
            return false;
        }
        let tail = origin.split_once("://").map_or(origin, |(_, rest)| rest);
        tail == headers.get("Host").unwrap_or("")
    }

    /// Whether the request comes from another web page: it has a non-empty `Origin` that is
    /// neither this server's own page nor CORS-allowed. A request without an `Origin` (curl,
    /// the SDKs) is not.
    ///
    /// Behavior reference: project-maya serve/server.py:6141-6150 at 7e68a30f.
    pub fn is_foreign_page(&self, head: &RequestHead) -> bool {
        let origin = head.headers().get("Origin").unwrap_or("");
        if origin.is_empty() || Self::is_same_page(origin, head.headers()) {
            return false;
        }
        self.cors_allow(head).is_none()
    }

    /// [`is_foreign_page`](Self::is_foreign_page) as a refusal: 403 `permission_error`.
    pub fn check_foreign_page(&self, head: &RequestHead) -> Result<(), Refusal> {
        if self.is_foreign_page(head) {
            Err(Refusal::foreign_page())
        } else {
            Ok(())
        }
    }

    /// Whether the request may pass the API key check: always with no key configured,
    /// otherwise when the presented key ([`presented_key`]) is one of the keys.
    ///
    /// Behavior reference: project-maya serve/server.py:5811-5819 at 7e68a30f.
    pub fn authorized(&self, head: &RequestHead) -> bool {
        let keys = &self.config.api_keys;
        !keys.is_configured() || keys.accepts(presented_key(head.headers()))
    }

    /// [`authorized`](Self::authorized) as a refusal: 401 `authentication_error`.
    pub fn check_key(&self, head: &RequestHead) -> Result<(), Refusal> {
        if self.authorized(head) {
            Ok(())
        } else {
            Err(Refusal::auth())
        }
    }

    /// The owner of the Responses records this request creates or reads: [`PUBLIC_OWNER`]
    /// with no key configured, else the lowercase hex SHA-256 of the presented key's UTF-8
    /// bytes (of `""` when none is presented).
    ///
    /// Behavior reference: project-maya serve/server.py:5821-5826 at 7e68a30f.
    pub fn response_owner(&self, head: &RequestHead) -> String {
        if !self.config.api_keys.is_configured() {
            return String::from(PUBLIC_OWNER);
        }
        sha256_hex(presented_key(head.headers()).as_bytes())
    }

    /// The donor's `_own_page(what)`, for the handlers of the dashboard's mutating routes:
    /// `Content-Type` must start with `application/json` (else 415 "send
    /// application/json"), and a non-empty `Origin` must be this server's own page (else
    /// 403 "<what> only from PulsarMLX Console's own page"; `Origin: null` is refused,
    /// SEC-1.2). CORS does not open these routes.
    ///
    /// Behavior reference: project-maya serve/server.py:6327-6338 at 7e68a30f.
    pub fn own_page(&self, head: &RequestHead, what: &str) -> Result<(), Refusal> {
        let headers = head.headers();
        if !headers
            .get("Content-Type")
            .unwrap_or("")
            .starts_with("application/json")
        {
            return Err(Refusal::not_json());
        }
        let origin = headers.get("Origin").unwrap_or("");
        if !origin.is_empty() && !Self::is_same_page(origin, headers) {
            return Err(Refusal::message(403, own_page_message(what)));
        }
        Ok(())
    }

    /// The attachment route's check: the media type of `Content-Type` (before any `;`,
    /// stripped, lower-cased) must be one of [`ATTACH_CONTENT_TYPES`] (else 415 "send the
    /// file's bytes as application/octet-stream"), and a non-empty `Origin` must be this
    /// server's own page (else 403 "files are read only for PulsarMLX Console's own page").
    /// The handler reads the body first, as the donor does.
    ///
    /// Behavior reference: project-maya serve/server.py:6434-6450 at 7e68a30f.
    pub fn attach_page(&self, head: &RequestHead) -> Result<(), Refusal> {
        let headers = head.headers();
        let value = headers.get("Content-Type").unwrap_or("");
        let media = pystr::strip(value.split(';').next().unwrap_or(""), None).to_ascii_lowercase();
        if !ATTACH_CONTENT_TYPES.contains(&media.as_str()) {
            return Err(Refusal::message(415, SEND_FILE_MESSAGE));
        }
        let origin = headers.get("Origin").unwrap_or("");
        if !origin.is_empty() && !Self::is_same_page(origin, headers) {
            return Err(Refusal::message(403, attach_foreign_message()));
        }
        Ok(())
    }

    /// Whether a client at `peer` may use a mutating admin or ops route (deviation SEC-1.4):
    /// always when an API key is configured (the key check has then passed), otherwise only
    /// from a loopback address ([`is_loopback_ip`], which accepts all of `127.0.0.0/8`
    /// where the donor's model-management gate accepts only `127.0.0.1`).
    ///
    /// Behavior reference: project-maya serve/server.py:5515-5519 at 7e68a30f (the gate's
    /// shape; the address set is SEC-1.4's loopback peer).
    pub fn local_or_keyed(&self, peer: IpAddr) -> bool {
        self.config.api_keys.is_configured() || is_loopback_ip(peer)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::{Ipv4Addr, Ipv6Addr};

    fn head(path: &str, headers: &[(&str, &str)]) -> RequestHead {
        let pairs = headers
            .iter()
            .map(|(k, v)| ((*k).to_owned(), (*v).to_owned()))
            .collect();
        RequestHead::new("GET", path, "HTTP/1.1", Headers::from_pairs(pairs))
    }

    fn loopback() -> IpAddr {
        IpAddr::V4(Ipv4Addr::LOCALHOST)
    }

    #[test]
    fn key_list_follows_python() {
        let s = |v: &str| Value::String(v.to_owned());
        assert_eq!(key_list(&s("k1, k2")), vec!["k1", "k2"]);
        assert_eq!(key_list(&s(" k1 ,, \u{a0}k2\u{2003} ,")), vec!["k1", "k2"]);
        assert_eq!(key_list(&s("")), Vec::<String>::new());
        assert_eq!(key_list(&s(" , ")), Vec::<String>::new());
        assert_eq!(key_list(&Value::Null), Vec::<String>::new());
        assert_eq!(key_list(&serde_json::json!([])), Vec::<String>::new());
        // A list keeps commas and spaces inside a key, and drops empty items only.
        assert_eq!(
            key_list(&serde_json::json!(["a,b", "", " c "])),
            vec!["a,b", " c "]
        );
        // str() of other values, as Python prints them.
        assert_eq!(
            key_list(&serde_json::json!([7, true, null, 1.5])),
            vec!["7", "True", "None", "1.5"]
        );
        assert_eq!(key_list(&serde_json::json!(12345)), vec!["12345"]);
        assert_eq!(key_list(&serde_json::json!(0)), Vec::<String>::new());
        assert_eq!(
            key_list(&serde_json::json!(["x", ["y"]])),
            vec!["x", "['y']"]
        );
        assert_eq!(key_list(&serde_json::json!({"a": "b"})), vec!["{'a': 'b'}"]);
    }

    #[test]
    fn keys_compare_whole_and_only_when_presented() {
        let keys = ApiKeys::from_setting(&Value::String("k1, k2".into()));
        assert!(keys.is_configured());
        assert_eq!(keys.len(), 2);
        assert!(keys.accepts("k1") && keys.accepts("k2"));
        assert!(!keys.accepts("k3") && !keys.accepts("k1, k2") && !keys.accepts(""));
        assert!(!keys.accepts("k") && !keys.accepts("k10"));
        // True in Python, but no key: configured, and nothing is accepted.
        let empty = ApiKeys::from_setting(&Value::String(" , ".into()));
        assert!(empty.is_configured() && empty.is_empty() && !empty.accepts(" , "));
        assert!(!ApiKeys::none().is_configured());
        assert_eq!(
            format!("{keys:?}"),
            "ApiKeys { configured: true, count: 2 }"
        );
        assert!(constant_time_eq(b"abc", b"abc"));
        assert!(!constant_time_eq(b"abc", b"abd") && !constant_time_eq(b"abc", b"ab"));
    }

    #[test]
    fn the_presented_key() {
        let k = |pairs: &[(&str, &str)]| presented_key(head("/", pairs).headers()).to_owned();
        assert_eq!(k(&[("Authorization", "Bearer  k1 ")]), "k1");
        assert_eq!(k(&[("authorization", "bEaReR k1")]), "k1");
        assert_eq!(k(&[("Authorization", "Bearer\tk1")]), "");
        assert_eq!(
            k(&[("Authorization", "Basic k1"), ("x-api-key", " k2")]),
            " k2"
        );
        assert_eq!(k(&[("X-Api-Key", "k2")]), "k2");
        assert_eq!(k(&[]), "");
        // The first Authorization header counts.
        assert_eq!(
            k(&[("Authorization", "Bearer a"), ("Authorization", "Bearer b")]),
            "a"
        );
    }

    #[test]
    fn authorization_and_the_owner() {
        let open = Guard::new(GuardConfig::new(loopback()));
        let h = head("/v1/models", &[]);
        assert!(open.authorized(&h));
        assert_eq!(open.response_owner(&h), PUBLIC_OWNER);
        let keyed =
            Guard::new(GuardConfig::new(loopback()).with_api_key(&Value::String("secret".into())));
        assert!(!keyed.authorized(&h));
        assert_eq!(keyed.check_key(&h), Err(Refusal::auth()));
        let with = head("/v1/models", &[("Authorization", "Bearer secret")]);
        assert!(keyed.authorized(&with));
        assert_eq!(
            keyed.response_owner(&with),
            "2bb80d537b1da3e38bd30361aa855686bde0eacd7162fef6a25fe97bf527a25b"
        );
        // A wrong key still has an owner (its digest); the key check refuses it first.
        assert_eq!(
            keyed.response_owner(&h),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }

    #[test]
    fn host_names_and_ports_split() {
        assert_eq!(split_host("localhost"), Some(("localhost", None)));
        assert_eq!(
            split_host("localhost:8095"),
            Some(("localhost", Some(8095)))
        );
        assert_eq!(split_host("[::1]:65535"), Some(("[::1]", Some(65535))));
        assert_eq!(split_host("[::1]"), Some(("[::1]", None)));
        for bad in [
            "",
            ":80",
            "localhost:",
            "localhost:65536",
            "localhost:123456",
            "localhost:8a",
            "localhost: 80",
            "localhost:80 ",
            " localhost",
            "::1",
            "[::1",
            "[]",
            "[::1]x",
            "[::1]:",
            "a b",
            "h\u{e9}te",
            "a:1:2",
            "x]",
        ] {
            assert_eq!(split_host(bad), None, "{bad:?}");
        }
    }

    #[test]
    fn the_host_policy_on_a_loopback_bind() {
        let policy = HostPolicy::new(loopback(), None);
        let allows = |hosts: &[&str]| {
            let pairs: Vec<(&str, &str)> = hosts.iter().map(|h| ("Host", *h)).collect();
            policy.allows(head("/", &pairs).headers())
        };
        for ok in [
            "localhost",
            "localhost:1",
            "127.0.0.1:8095",
            "[::1]:8095",
            "LocalHost:80",
        ] {
            assert!(allows(&[ok]), "{ok}");
        }
        for refused in [
            "evil.example",
            "evil.example:8095",
            "127.0.0.2",
            "[0:0:0:0:0:0:0:1]",
            "[::ffff:127.0.0.1]",
            "localhost.",
            "127.0.0.1:99999",
            "localhost.evil.example",
            "",
        ] {
            assert!(!allows(&[refused]), "{refused}");
        }
        assert!(!allows(&[]), "a missing Host is refused");
        assert!(
            !allows(&["localhost", "localhost"]),
            "two Host headers are refused"
        );
    }

    #[test]
    fn allowed_hosts_extend_the_loopback_names() {
        let list = vec![
            "Box.LAN:8095".to_owned(),
            "pulsar.local".to_owned(),
            "a b".to_owned(),
        ];
        for bind in [loopback(), IpAddr::V4(Ipv4Addr::UNSPECIFIED)] {
            let policy = HostPolicy::new(bind, Some(&list));
            let allows = |h: &str| policy.allows(head("/", &[("Host", h)]).headers());
            assert!(allows("box.lan:8095") && allows("BOX.LAN:8095"));
            assert!(!allows("box.lan:8096") && !allows("box.lan"));
            assert!(allows("pulsar.local") && allows("pulsar.local:1"));
            assert!(allows("localhost:9") && allows("[::1]"));
            assert!(!allows("a b") && !allows("evil.example"));
        }
    }

    #[test]
    fn entries_that_cannot_match_are_reported() {
        let list: Vec<String> = [
            "box.lan",
            "fe80::1",
            "[fe80::1]:8095",
            "http://box.lan",
            "box.lan:",
            "box.lan:70000",
            "b\u{fc}ro.lan",
            "a b",
            "Box.LAN:8095",
        ]
        .iter()
        .map(|s| (*s).to_owned())
        .collect();
        assert_eq!(
            invalid_allowed_hosts(&list),
            vec![
                "fe80::1",
                "http://box.lan",
                "box.lan:",
                "box.lan:70000",
                "b\u{fc}ro.lan",
                "a b"
            ]
        );
        let config = GuardConfig::new(loopback()).with_allowed_hosts(Some(list));
        assert_eq!(config.rejected_allowed_hosts().len(), 6);
        assert!(GuardConfig::new(loopback())
            .rejected_allowed_hosts()
            .is_empty());
        let fine = GuardConfig::new(loopback()).with_allowed_hosts(Some(vec!["[::1]".into()]));
        assert!(fine.rejected_allowed_hosts().is_empty());
    }

    #[test]
    fn a_non_loopback_bind_is_unrestricted_until_a_list_is_set() {
        let any = IpAddr::V4(Ipv4Addr::UNSPECIFIED);
        let policy = HostPolicy::new(any, None);
        assert_eq!(policy, HostPolicy::Unrestricted);
        assert!(policy.allows(head("/", &[("Host", "evil.example")]).headers()));
        assert!(policy.allows(head("/", &[]).headers()));
        let empty: Vec<String> = Vec::new();
        let only_loopback = HostPolicy::new(any, Some(&empty));
        assert!(only_loopback.allows(head("/", &[("Host", "127.0.0.1:1")]).headers()));
        assert!(!only_loopback.allows(head("/", &[("Host", "192.0.2.1")]).headers()));
        let lan = IpAddr::V4(Ipv4Addr::new(192, 0, 2, 1));
        assert_eq!(HostPolicy::new(lan, None), HostPolicy::Unrestricted);
        assert_ne!(
            HostPolicy::new(IpAddr::V6(Ipv6Addr::LOCALHOST), None),
            HostPolicy::Unrestricted
        );
    }

    #[test]
    fn loopback_peers() {
        assert!(is_loopback_ip(loopback()));
        assert!(is_loopback_ip(IpAddr::V4(Ipv4Addr::new(127, 1, 2, 3))));
        assert!(is_loopback_ip(IpAddr::V6(Ipv6Addr::LOCALHOST)));
        assert!(is_loopback_ip(IpAddr::V6(
            Ipv4Addr::LOCALHOST.to_ipv6_mapped()
        )));
        assert!(!is_loopback_ip(IpAddr::V4(Ipv4Addr::new(192, 0, 2, 1))));
        assert!(!is_loopback_ip(IpAddr::V4(Ipv4Addr::UNSPECIFIED)));
        let open = Guard::new(GuardConfig::new(loopback()));
        assert!(open.local_or_keyed(loopback()));
        assert!(!open.local_or_keyed(IpAddr::V4(Ipv4Addr::new(192, 0, 2, 1))));
        let keyed =
            Guard::new(GuardConfig::new(loopback()).with_api_key(&Value::String("k".into())));
        assert!(keyed.local_or_keyed(IpAddr::V4(Ipv4Addr::new(192, 0, 2, 1))));
    }

    #[test]
    fn cors_only_for_v1_and_listed_origins() {
        let page = "http://127.0.0.1:8090";
        let g = Guard::new(GuardConfig::new(loopback()).with_cors_origins(vec![page.into()]));
        let at = |path: &str, origin: &str| g.cors_allow(&head(path, &[("Origin", origin)]));
        assert_eq!(at("/v1/models", page).as_deref(), Some(page));
        assert_eq!(
            at("/v1/models", "http://127.0.0.1:8090//").as_deref(),
            Some(page)
        );
        assert_eq!(at("/v1/models?x=/v1/", page).as_deref(), Some(page));
        assert_eq!(at("/v1", page), None);
        assert_eq!(at("/settings", page), None);
        assert_eq!(at("/x?/v1/", page), None);
        assert_eq!(at("/v1/models", "http://evil.example"), None);
        assert_eq!(at("/v1/models", ""), None);
        let star = Guard::new(GuardConfig::new(loopback()).with_cors_origins(vec!["*".into()]));
        assert_eq!(star.cors_allow(&head("/v1/x", &[])).as_deref(), Some("*"));
        let h = head("/v1/x", &[("Host", "localhost")]);
        assert_eq!(
            star.cors_headers(&h),
            vec![("Access-Control-Allow-Origin".to_owned(), "*".to_owned())]
        );
        // A refused Host gets no CORS grant.
        assert!(star
            .cors_headers(&head("/v1/x", &[("Host", "evil.example")]))
            .is_empty());
        let none = Guard::new(GuardConfig::new(loopback()));
        assert_eq!(
            none.cors_allow(&head("/v1/models", &[("Origin", page)])),
            None
        );
    }

    #[test]
    fn foreign_and_own_pages() {
        let g = Guard::new(GuardConfig::new(loopback()));
        let foreign = |pairs: &[(&str, &str)]| g.is_foreign_page(&head("/x", pairs));
        assert!(!foreign(&[("Host", "127.0.0.1:1")]));
        assert!(!foreign(&[("Host", "127.0.0.1:1"), ("Origin", "")]));
        assert!(!foreign(&[
            ("Host", "127.0.0.1:1"),
            ("Origin", "http://127.0.0.1:1")
        ]));
        assert!(!foreign(&[
            ("Host", "127.0.0.1:1"),
            ("Origin", "https://127.0.0.1:1")
        ]));
        assert!(!foreign(&[
            ("Host", "127.0.0.1:1"),
            ("Origin", "127.0.0.1:1")
        ]));
        assert!(foreign(&[
            ("Host", "127.0.0.1:1"),
            ("Origin", "http://127.0.0.1:2")
        ]));
        assert!(foreign(&[
            ("Host", "127.0.0.1:1"),
            ("Origin", "http://evil.example")
        ]));
        // SEC-1.2: Origin null is never this server, even with a Host of "null".
        assert!(foreign(&[("Host", "null"), ("Origin", "null")]));
        assert!(foreign(&[("Host", "127.0.0.1:1"), ("Origin", "null")]));
        let json = ("Content-Type", "application/json; charset=utf-8");
        let own = |pairs: &[(&str, &str)]| {
            g.own_page(&head("/settings", pairs), "the settings can be changed")
        };
        assert_eq!(own(&[json, ("Host", "a")]), Ok(()));
        assert_eq!(own(&[json, ("Host", "a"), ("Origin", "http://a")]), Ok(()));
        assert_eq!(
            own(&[("Content-Type", "text/plain")]),
            Err(Refusal::not_json())
        );
        assert_eq!(
            own(&[("Content-Type", "Application/json")]),
            Err(Refusal::not_json())
        );
        assert_eq!(own(&[]), Err(Refusal::not_json()));
        let refused = own(&[json, ("Host", "a"), ("Origin", "null")]);
        assert_eq!(
            refused,
            Err(Refusal::message(
                403,
                "the settings can be changed only from PulsarMLX Console's own page"
            ))
        );
        assert_eq!(
            refused.err().map(|r| r.body()),
            Some(
                "{\"error\": {\"message\": \"the settings can be changed only from PulsarMLX \
                 Console's own page\"}}"
                    .to_owned()
            )
        );
        let attach = |pairs: &[(&str, &str)]| g.attach_page(&head("/attach", pairs));
        assert_eq!(
            attach(&[("Content-Type", " Application/PDF ; x=1")]),
            Ok(())
        );
        assert_eq!(
            attach(&[("Content-Type", "application/octet-stream")]),
            Ok(())
        );
        assert_eq!(
            attach(&[("Content-Type", "application/json")]),
            Err(Refusal::message(415, SEND_FILE_MESSAGE))
        );
        assert_eq!(
            attach(&[
                ("Content-Type", "application/pdf"),
                ("Host", "a"),
                ("Origin", "http://b")
            ]),
            Err(Refusal::message(
                403,
                "files are read only for PulsarMLX Console's own page"
            ))
        );
    }

    #[test]
    fn json_content_types() {
        let is = |v: &str| is_json_content_type(head("/", &[("Content-Type", v)]).headers());
        assert!(
            is("application/json")
                && is("Application/JSON")
                && is(" application/json ; charset=utf-8")
        );
        for no in [
            "text/plain",
            "application/x-www-form-urlencoded",
            "*/*",
            "application/jsonx",
            "",
            "multipart/form-data",
        ] {
            assert!(!is(no), "{no}");
        }
        assert!(!is_json_content_type(head("/", &[]).headers()));
    }

    #[test]
    fn preflights() {
        let page = "http://127.0.0.1:8090";
        let g = Guard::new(GuardConfig::new(loopback()).with_cors_origins(vec![page.into()]));
        let p = g.preflight(&head(
            "/v1/chat/completions",
            &[
                ("Origin", page),
                (
                    "Access-Control-Request-Headers",
                    "content-type,authorization",
                ),
            ],
        ));
        assert_eq!(p.status, 204);
        let names: Vec<&str> = p.headers.iter().map(|(k, _)| k.as_str()).collect();
        assert_eq!(
            names,
            [
                "Access-Control-Allow-Methods",
                "Access-Control-Allow-Headers",
                "Access-Control-Max-Age",
                "Content-Length"
            ]
        );
        assert_eq!(p.headers[1].1, "content-type,authorization");
        let p = g.preflight(&head(
            "/v1/x",
            &[("Origin", page), ("Access-Control-Request-Headers", "")],
        ));
        assert_eq!(p.headers[1].1, PREFLIGHT_HEADERS);
        let refused = g.preflight(&head("/settings", &[("Origin", page)]));
        assert_eq!(
            refused,
            Preflight {
                status: 403,
                headers: vec![("Content-Length".into(), "0".into())]
            }
        );
    }

    #[test]
    fn refusal_bodies() {
        assert_eq!(Refusal::not_json().status(), 415);
        assert_eq!(
            Refusal::not_json().body(),
            "{\"error\": {\"message\": \"send application/json\"}}"
        );
        assert_eq!(
            Refusal::host().body(),
            format!(
                "{{\"error\": {{\"type\": \"permission_error\", \"message\": \"{HOST_REFUSED_MESSAGE}\"}}}}"
            )
        );
        assert_eq!(Refusal::foreign_page().status(), 403);
        assert_eq!(
            Refusal::auth().body(),
            "{\"error\": {\"type\": \"authentication_error\", \"message\": \"missing or wrong API key\"}}"
        );
    }
}
